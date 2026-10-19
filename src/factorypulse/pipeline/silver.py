"""Silver layer: validate, quarantine, deduplicate, and standardize."""

from __future__ import annotations

import click
from pyspark import StorageLevel
from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from factorypulse.config import Settings, settings
from factorypulse.quality.rules import telemetry_reject_reason
from factorypulse.spark import get_spark, maybe_persist, maybe_unpersist
from factorypulse.utils.run_context import RunContext


def split_valid_invalid(df: DataFrame, reason: Column) -> tuple[DataFrame, DataFrame]:
    """Evaluate the reason once, then expose clean and rejected branches."""
    tagged = df.withColumn("reject_reason", reason)
    return (
        tagged.filter(F.col("reject_reason").isNull()).drop("reject_reason"),
        tagged.filter(F.col("reject_reason").isNotNull()),
    )


def deduplicate(df: DataFrame, key: str, order_by: list[Column]) -> DataFrame:
    """Keep exactly one deterministically ordered row for each business key."""
    window = Window.partitionBy(key).orderBy(*order_by)
    return df.withColumn("_rn", F.row_number().over(window)).filter("_rn = 1").drop("_rn")


def build_silver_telemetry(
    spark: SparkSession, ctx: RunContext, cfg: Settings | None = None
) -> dict[str, int]:
    """Build clean telemetry and append invalid source rows to quarantine."""
    cfg = cfg or settings
    bronze = spark.read.format("delta").load(cfg.bronze_path("telemetry"))
    rows_read = bronze.count()
    ctx.rows_read += rows_read

    valid_machine_ids = [
        row.machine_id
        for row in (
            spark.read.format("delta")
            .load(cfg.bronze_path("machines"))
            .select("machine_id")
            .distinct()
            .collect()
        )
    ]
    clean, rejected = split_valid_invalid(bronze, telemetry_reject_reason(valid_machine_ids))

    # Rejects are small enough to persist. This prevents evaluating every
    # quality expression once for the write and again for the count.
    rejected = maybe_persist(rejected, StorageLevel.MEMORY_AND_DISK)
    n_rejected = rejected.count()
    (
        rejected.withColumn("_quarantined_at", F.current_timestamp())
        .withColumn("_quarantine_batch", F.lit(ctx.run_id))
        .write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .save(cfg.quarantine_path("telemetry"))
    )
    maybe_unpersist(rejected)
    ctx.rows_rejected += n_rejected

    deduped = maybe_persist(
        deduplicate(
            clean,
            key="event_id",
            order_by=[F.col("_ingested_at").desc(), F.col("_source_file").desc()],
        ),
        StorageLevel.DISK_ONLY,
    )
    rows_written = deduped.count()
    duplicates_removed = rows_read - n_rejected - rows_written

    silver = (
        deduped.withColumn("machine_id", F.upper(F.trim("machine_id")))
        .withColumn("failure_type", F.upper(F.trim("failure_type")))
        .withColumn("shift_name", F.lower(F.trim("shift_name")))
        .withColumn(
            "temp_diff_k",
            F.round(F.col("process_temp_k") - F.col("air_temp_k"), 2),
        )
        .withColumn("event_date", F.to_date("event_time"))
        .withColumn("event_hour", F.hour("event_time"))
        .withColumn("_silver_at", F.current_timestamp())
    )
    (
        silver.repartition("event_date")
        .write.format("delta")
        .mode("overwrite")
        # Set per-write, not via spark.conf: serverless compute rejects
        # setting spark.sql.sources.partitionOverwriteMode on the session, and
        # relying on ambient session state makes correctness depend on which
        # runtime happens to execute this.
        .option("partitionOverwriteMode", "dynamic")
        .partitionBy("event_date")
        .save(cfg.silver_path("telemetry"))
    )
    maybe_unpersist(deduped)

    ctx.rows_written += rows_written
    return {
        "rows_read": rows_read,
        "rejected": n_rejected,
        "duplicates_removed": duplicates_removed,
        "rows_written": rows_written,
    }


def build_silver_reference(
    spark: SparkSession, ctx: RunContext, cfg: Settings | None = None
) -> dict[str, int]:
    """Clean reference facts; machine SCD2 is intentionally deferred to Phase 08."""
    cfg = cfg or settings
    counts: dict[str, int] = {}

    work_orders = spark.read.format("delta").load(cfg.bronze_path("work_orders"))
    clean_work_orders = (
        work_orders.filter(F.col("machine_id").isNotNull() & F.col("opened_at").isNotNull())
        .withColumn(
            "response_minutes",
            (F.col("started_at").cast("long") - F.col("opened_at").cast("long")) / 60,
        )
        .withColumn(
            "repair_minutes",
            (F.col("closed_at").cast("long") - F.col("started_at").cast("long")) / 60,
        )
        .withColumn(
            "total_downtime_minutes",
            (F.col("closed_at").cast("long") - F.col("opened_at").cast("long")) / 60,
        )
        .withColumn("is_closed", F.col("closed_at").isNotNull())
        .filter(F.coalesce(F.col("repair_minutes"), F.lit(0)) >= 0)
    )
    (
        clean_work_orders.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(cfg.silver_path("work_orders"))
    )
    counts["work_orders"] = clean_work_orders.count()

    production_orders = spark.read.format("delta").load(cfg.bronze_path("production_orders"))
    clean_production_orders = (
        production_orders.filter(F.col("machine_id").isNotNull())
        .withColumn("total_qty", F.col("good_qty") + F.col("scrap_qty"))
        .withColumn(
            "quality_rate",
            F.when(
                (F.col("good_qty") + F.col("scrap_qty")) > 0,
                F.col("good_qty") / (F.col("good_qty") + F.col("scrap_qty")),
            ).otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            "actual_runtime_minutes",
            (F.col("actual_end").cast("long") - F.col("actual_start").cast("long")) / 60,
        )
        .withColumn(
            "planned_runtime_minutes",
            (F.col("planned_end").cast("long") - F.col("planned_start").cast("long")) / 60,
        )
        .withColumn("production_date", F.to_date("planned_start"))
    )
    (
        clean_production_orders.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(cfg.silver_path("production_orders"))
    )
    counts["production_orders"] = clean_production_orders.count()

    plants = spark.read.format("delta").load(cfg.bronze_path("plants"))
    (
        plants.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(cfg.silver_path("plants"))
    )
    counts["plants"] = plants.count()

    total = sum(counts.values())
    ctx.rows_read += total
    ctx.rows_written += total
    return counts


@click.command()
def main() -> None:
    """Run the complete Silver layer."""
    context = RunContext(pipeline="silver")
    spark = get_spark("silver", shuffle_partitions=16)
    try:
        print(f"\n{context}  starting silver layer")
        stats = build_silver_telemetry(spark, context)
        print("\n  telemetry")
        print(f"    rows read          : {stats['rows_read']:,}")
        print(
            f"    rejected           : {stats['rejected']:,} "
            f"({stats['rejected'] / stats['rows_read'] * 100:.2f}%)"
        )
        print(f"    duplicates removed : {stats['duplicates_removed']:,}")
        print(f"    rows written       : {stats['rows_written']:,}")

        print("\n  reference")
        for table, count in build_silver_reference(spark, context).items():
            print(f"    silver.{table:<20s}: {count:,}")

        print("\n  rejection breakdown for this run")
        (
            spark.read.format("delta")
            .load(settings.quarantine_path("telemetry"))
            .filter(F.col("_quarantine_batch") == context.run_id)
            .groupBy("reject_reason")
            .count()
            .orderBy(F.desc("count"))
            .show(truncate=False)
        )
        result = context.finish()
        print(f"  duration : {result['duration_s']:.1f}s\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
