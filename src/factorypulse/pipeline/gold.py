"""Gold layer: star schema facts, dimensions, and aggregates."""

from __future__ import annotations

import click
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from factorypulse.config import Settings, settings
from factorypulse.pipeline.dimensions import (
    build_dim_date,
    build_dim_failure_type,
    build_dim_plant,
    build_dim_shift,
)
from factorypulse.spark import get_spark
from factorypulse.utils.run_context import RunContext


def _write(df: DataFrame, path: str, partition_by: str | None = None) -> int:
    """Overwrite one Delta table and return its row count."""
    writer = (
        df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .option("partitionOverwriteMode", "static")
    )
    if partition_by:
        writer = writer.partitionBy(partition_by)
    writer.save(path)
    return df.count()


def point_in_time_machine_join(
    facts: DataFrame, dim_machine: DataFrame, timestamp_col: str
) -> DataFrame:
    """Bind every aliased `s` fact to the machine version valid at its timestamp."""
    dm = dim_machine.select(
        "machine_sk", "machine_id", "plant_id", "line_id", "criticality", "valid_from", "valid_to"
    ).alias("d")
    return facts.alias("s").join(
        F.broadcast(dm),
        (F.col("s.machine_id") == F.col("d.machine_id"))
        & (F.col(f"s.{timestamp_col}") >= F.col("d.valid_from"))
        & (F.col(f"s.{timestamp_col}") < F.col("d.valid_to")),
        "inner",
    )


def build_fact_machine_event(
    spark: SparkSession, ctx: RunContext, cfg: Settings | None = None
) -> int:
    """Build one fact row per machine sensor reading timestamp."""
    cfg = cfg or settings
    silver = spark.read.format("delta").load(cfg.silver_path("telemetry"))
    dim_machine = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    dim_shift = spark.read.format("delta").load(cfg.gold_path("dim_shift"))
    dim_plant = spark.read.format("delta").load(cfg.gold_path("dim_plant"))
    dim_ft = spark.read.format("delta").load(cfg.gold_path("dim_failure_type"))

    joined = (
        point_in_time_machine_join(silver, dim_machine, "event_time")
        .join(F.broadcast(dim_shift.alias("sh")), F.col("s.shift_name") == F.col("sh.shift_name"))
        .join(F.broadcast(dim_plant.alias("p")), F.col("d.plant_id") == F.col("p.plant_id"))
        .join(F.broadcast(dim_ft.alias("ft")), F.col("s.failure_type") == F.col("ft.code"))
    )
    fact = joined.select(
        F.col("s.event_id").alias("event_id"),
        F.col("s._batch_id").alias("_batch_id"),
        F.col("d.machine_sk").alias("machine_sk"),
        F.date_format("s.event_time", "yyyyMMdd").cast("int").alias("date_sk"),
        F.col("sh.shift_sk").alias("shift_sk"),
        F.col("p.plant_sk").alias("plant_sk"),
        F.col("ft.failure_type_sk").alias("failure_type_sk"),
        F.col("s.event_time").alias("event_time"),
        F.col("s.event_date").alias("event_date"),
        F.col("s.air_temp_k").alias("air_temp_k"),
        F.col("s.process_temp_k").alias("process_temp_k"),
        F.col("s.temp_diff_k").alias("temp_diff_k"),
        F.col("s.rotational_speed_rpm").alias("rotational_speed_rpm"),
        F.col("s.torque_nm").alias("torque_nm"),
        F.col("s.power_w").alias("power_w"),
        F.col("s.tool_wear_min").alias("tool_wear_min"),
        F.col("s.is_failure").alias("is_failure"),
        (F.col("s.machine_status") == "RUNNING").alias("is_running"),
    )
    count = _write(fact, cfg.gold_path("fact_machine_event"), "event_date")
    ctx.rows_written += count
    return count


def sessionize_downtime(silver: DataFrame, cfg: Settings) -> DataFrame:
    """Collapse consecutive DOWN readings into one interval per island."""
    base = silver.select("machine_id", "event_time", "machine_status", "failure_type", "shift_name")
    order = Window.partitionBy("machine_id").orderBy("event_time")
    by_status = Window.partitionBy("machine_id", "machine_status").orderBy("event_time")
    down = (
        base.withColumn("rn_all", F.row_number().over(order))
        .withColumn("rn_status", F.row_number().over(by_status))
        .filter(F.col("machine_status") == "DOWN")
        .withColumn("grp", F.col("rn_all") - F.col("rn_status"))
    )
    intervals = down.groupBy("machine_id", "grp").agg(
        F.min("event_time").alias("downtime_start"),
        F.max("event_time").alias("downtime_end_reading"),
        F.count("*").alias("reading_count"),
        F.min(
            F.when(
                F.col("failure_type") != "NONE",
                F.struct("event_time", "failure_type"),
            )
        )["failure_type"].alias("failure_type"),
        F.min_by("shift_name", "event_time").alias("shift_name"),
    )
    return (
        intervals.withColumn(
            "downtime_end", F.col("downtime_end_reading") + F.expr("INTERVAL 1 MINUTE")
        )
        .withColumn("downtime_minutes", F.col("reading_count").cast("int"))
        .withColumn(
            "downtime_cost_eur",
            F.round(F.col("downtime_minutes") / 60 * cfg.downtime_cost_eur_per_hour, 2),
        )
        .withColumn("failure_type", F.coalesce("failure_type", F.lit("RNF")))
        .withColumn("is_planned", F.lit(False))
        .withColumn(
            "downtime_id",
            F.concat_ws("-", "machine_id", F.date_format("downtime_start", "yyyyMMddHHmm")),
        )
    )


def build_fact_downtime(spark: SparkSession, ctx: RunContext, cfg: Settings | None = None) -> int:
    """Build one fact row per continuous machine downtime interval."""
    cfg = cfg or settings
    silver = spark.read.format("delta").load(cfg.silver_path("telemetry"))
    intervals = sessionize_downtime(silver, cfg)
    dim_machine = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    dim_shift = spark.read.format("delta").load(cfg.gold_path("dim_shift"))
    dim_plant = spark.read.format("delta").load(cfg.gold_path("dim_plant"))
    dim_ft = spark.read.format("delta").load(cfg.gold_path("dim_failure_type"))

    joined = (
        point_in_time_machine_join(intervals, dim_machine, "downtime_start")
        .join(F.broadcast(dim_shift.alias("sh")), F.col("s.shift_name") == F.col("sh.shift_name"))
        .join(F.broadcast(dim_plant.alias("p")), F.col("d.plant_id") == F.col("p.plant_id"))
        .join(F.broadcast(dim_ft.alias("ft")), F.col("s.failure_type") == F.col("ft.code"))
    )
    fact = joined.select(
        F.col("s.downtime_id").alias("downtime_id"),
        F.col("d.machine_sk").alias("machine_sk"),
        F.date_format("s.downtime_start", "yyyyMMdd").cast("int").alias("date_sk"),
        F.col("sh.shift_sk").alias("shift_sk"),
        F.col("p.plant_sk").alias("plant_sk"),
        F.col("ft.failure_type_sk").alias("failure_type_sk"),
        F.col("s.downtime_start").alias("downtime_start"),
        F.col("s.downtime_end").alias("downtime_end"),
        F.col("s.downtime_minutes").alias("downtime_minutes"),
        F.col("s.downtime_cost_eur").alias("downtime_cost_eur"),
        F.col("s.is_planned").alias("is_planned"),
        F.to_date("s.downtime_start").alias("downtime_date"),
    )
    count = _write(fact, cfg.gold_path("fact_downtime"), "downtime_date")
    ctx.rows_written += count
    return count


def build_fact_work_order(spark: SparkSession, ctx: RunContext, cfg: Settings | None = None) -> int:
    """Build one fact row per maintenance work order."""
    cfg = cfg or settings
    work_orders = spark.read.format("delta").load(cfg.silver_path("work_orders"))
    dim_machine = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    joined = point_in_time_machine_join(work_orders, dim_machine, "opened_at")
    fact = joined.select(
        F.col("s.work_order_id").alias("work_order_id"),
        F.col("d.machine_sk").alias("machine_sk"),
        F.date_format("s.opened_at", "yyyyMMdd").cast("int").alias("date_sk"),
        F.col("s.wo_type").alias("wo_type"),
        F.col("s.failure_type").alias("failure_type"),
        F.col("s.priority").alias("priority"),
        F.col("s.opened_at").alias("opened_at"),
        F.col("s.closed_at").alias("closed_at"),
        F.col("s.response_minutes").alias("response_minutes"),
        F.col("s.repair_minutes").alias("repair_minutes"),
        F.col("s.total_downtime_minutes").alias("total_downtime_minutes"),
        F.col("s.labour_hours").alias("labour_hours"),
        F.col("s.parts_cost_eur").alias("parts_cost_eur"),
        (F.col("s.wo_type") == "preventive").alias("is_preventive"),
    )
    count = _write(fact, cfg.gold_path("fact_work_order"))
    ctx.rows_written += count
    return count


def build_agg_machine_daily(
    spark: SparkSession, ctx: RunContext, cfg: Settings | None = None
) -> int:
    """Build machine-day additive KPI components, never pre-averaged MTBF."""
    cfg = cfg or settings
    events = spark.read.format("delta").load(cfg.gold_path("fact_machine_event"))
    downtime = spark.read.format("delta").load(cfg.gold_path("fact_downtime"))
    event_agg = events.groupBy("machine_sk", "date_sk", "plant_sk").agg(
        F.count("*").alias("reading_count"),
        F.sum(F.col("is_running").cast("int")).alias("running_minutes"),
        F.sum(F.col("is_failure").cast("int")).alias("failure_count"),
        F.avg("air_temp_k").alias("avg_air_temp_k"),
        F.avg("process_temp_k").alias("avg_process_temp_k"),
        F.avg(F.when(F.col("is_running"), F.col("torque_nm"))).alias("avg_torque_nm"),
        F.avg(F.when(F.col("is_running"), F.col("rotational_speed_rpm"))).alias("avg_rpm"),
        F.max("tool_wear_min").alias("max_tool_wear_min"),
    )
    downtime_agg = downtime.groupBy("machine_sk", "date_sk").agg(
        F.sum("downtime_minutes").alias("downtime_minutes"),
        F.sum("downtime_cost_eur").alias("downtime_cost_eur"),
        F.count("*").alias("downtime_events"),
    )
    aggregate = (
        event_agg.join(downtime_agg, ["machine_sk", "date_sk"], "left")
        .fillna(0, subset=["downtime_minutes", "downtime_cost_eur", "downtime_events"])
        .withColumn("operating_hours", F.round(F.col("running_minutes") / 60, 4))
        .withColumn("downtime_hours", F.round(F.col("downtime_minutes") / 60, 4))
        .withColumn(
            "availability",
            F.when(
                F.col("operating_hours") + F.col("downtime_hours") > 0,
                F.col("operating_hours") / (F.col("operating_hours") + F.col("downtime_hours")),
            ),
        )
    )
    count = _write(aggregate, cfg.gold_path("agg_machine_daily"))
    ctx.rows_written += count
    return count


GRAIN_COMMENTS = {
    "fact_machine_event": "GRAIN: one row per machine per sensor reading timestamp (1-minute resolution). Measures are additive except tool_wear_min (semi-additive: use MAX, not SUM).",
    "fact_downtime": "GRAIN: one row per continuous interval during which one machine was not producing. Built from consecutive DOWN readings via gaps-and-islands. downtime_minutes and downtime_cost_eur are additive.",
    "fact_work_order": "GRAIN: one row per maintenance work order. Joined to the machine version valid at opened_at.",
    "dim_machine": "SCD Type 2. GRAIN: one row per machine per version. Join facts on machine_sk, never machine_id. Tracked attributes: plant_id, line_id, model, machine_type, criticality, is_active.",
    "dim_date": "GRAIN: one row per calendar day. Contiguous — mark as date table in Power BI.",
    "dim_shift": "GRAIN: one row per shift definition (early/late/night).",
    "dim_plant": "GRAIN: one row per plant.",
    "dim_failure_type": "GRAIN: one row per failure mode from the AI4I taxonomy.",
    "agg_machine_daily": "GRAIN: one row per machine per day. Stores KPI COMPONENTS, not ratios: MTBF = SUM(operating_hours)/SUM(failure_count). Never average the availability column across rows.",
}


def apply_comments(spark: SparkSession, cfg: Settings | None = None) -> None:
    """Attach grain documentation as a property on every Gold Delta table."""
    cfg = cfg or settings
    for table, comment in GRAIN_COMMENTS.items():
        escaped = comment.replace("'", "''")
        spark.sql(
            f"ALTER TABLE delta.`{cfg.gold_path(table)}` "
            f"SET TBLPROPERTIES ('comment' = '{escaped}')"
        )


@click.command()
@click.option("--start", default="2025-10-01", show_default=True)
@click.option("--end", default="2026-12-31", show_default=True)
def main(start: str, end: str) -> None:
    """Build the complete Gold star schema."""
    ctx = RunContext(pipeline="gold")
    spark = get_spark("gold", shuffle_partitions=16)
    cfg = settings
    try:
        print(f"\n{ctx}  starting gold layer")
        print("  dimensions")
        dimensions = {
            "dim_date": build_dim_date(spark, start, end),
            "dim_shift": build_dim_shift(spark),
            "dim_plant": build_dim_plant(spark, cfg),
            "dim_failure_type": build_dim_failure_type(spark),
        }
        for table, frame in dimensions.items():
            print(f"    {table:<18s}: {_write(frame, cfg.gold_path(table)):,}")
        print("    dim_machine       : built by Phase 08 (SCD2)")

        print("  facts")
        print(f"    fact_machine_event: {build_fact_machine_event(spark, ctx, cfg):,}")
        print(f"    fact_downtime     : {build_fact_downtime(spark, ctx, cfg):,}")
        print(f"    fact_work_order   : {build_fact_work_order(spark, ctx, cfg):,}")
        print("  aggregates")
        print(f"    agg_machine_daily : {build_agg_machine_daily(spark, ctx, cfg):,}")
        apply_comments(spark, cfg)
        print("  grain comments applied")
        print(f"\n  duration : {ctx.finish()['duration_s']:.1f}s\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
