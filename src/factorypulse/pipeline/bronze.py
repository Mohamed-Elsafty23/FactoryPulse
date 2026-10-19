"""Bronze layer: faithful raw capture with additive lineage only."""

from __future__ import annotations

from datetime import datetime, timezone

import click
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from factorypulse.config import Settings, settings
from factorypulse.pipeline.jdbc import read_table
from factorypulse.spark import get_spark
from factorypulse.utils.run_context import RunContext

TELEMETRY_SCHEMA = StructType(
    [
        StructField("event_id", StringType(), True),
        StructField("machine_id", StringType(), True),
        StructField("plant_id", StringType(), True),
        StructField("line_id", StringType(), True),
        StructField("machine_type", StringType(), True),
        StructField("event_time", TimestampType(), True),
        StructField("shift_name", StringType(), True),
        StructField("air_temp_k", DoubleType(), True),
        StructField("process_temp_k", DoubleType(), True),
        StructField("temp_diff_k", DoubleType(), True),
        StructField("rotational_speed_rpm", IntegerType(), True),
        StructField("torque_nm", DoubleType(), True),
        StructField("power_w", DoubleType(), True),
        StructField("tool_wear_min", IntegerType(), True),
        StructField("failure_type", StringType(), True),
        StructField("is_failure", BooleanType(), True),
        StructField("machine_status", StringType(), True),
        StructField("repair_minutes", IntegerType(), True),
        StructField("source_system", StringType(), True),
    ]
)


def _source_file_col(df: DataFrame):
    """Per-row source file path, for file-based relations only.

    Unity Catalog rejects ``input_file_name()`` outright
    (UC_COMMAND_NOT_SUPPORTED) and directs callers to the hidden ``_metadata``
    column. But ``_metadata`` only exists for file-based sources: JDBC reads
    and in-memory DataFrames have no file, and referencing it there fails
    analysis. ``input_file_name()`` used to paper over that by returning an
    empty string, so probe for the column and fall back to NULL instead.
    """
    try:
        df.select(F.col("_metadata.file_path"))
    except Exception:
        return F.lit(None).cast("string")
    return F.col("_metadata.file_path")


def add_lineage(df: DataFrame, ctx: RunContext, source_system: str) -> DataFrame:
    """Add traceability metadata without changing any source column."""
    ingested_at = datetime.now(timezone.utc)
    return (
        df.withColumn("_ingested_at", F.lit(ingested_at).cast("timestamp"))
        .withColumn("_source_system", F.lit(source_system))
        .withColumn("_source_file", _source_file_col(df))
        .withColumn("_batch_id", F.lit(ctx.run_id))
    )


def build_bronze_telemetry(
    spark: SparkSession, ctx: RunContext, cfg: Settings | None = None
) -> int:
    """Land raw telemetry Parquet into a date-partitioned Delta table."""
    cfg = cfg or settings
    landing_path = cfg.landing_path("telemetry")
    raw = (
        spark.read.schema(TELEMETRY_SCHEMA)
        .option("basePath", landing_path)
        .parquet(landing_path)
        # Partition from event time so deliberately missing timestamps remain
        # missing in Bronze and use Delta's null partition sentinel.
        .withColumn("event_date", F.to_date("event_time"))
    )
    output = add_lineage(raw, ctx, "telemetry_simulator")
    (
        # Hash-partition by date before writing so each date is handled by one
        # task. Without this, every upstream file can create a tiny file in
        # every date directory (thousands of files for this dataset).
        output.repartition("event_date")
        .write.format("delta")
        .mode("overwrite")
        .option("mergeSchema", "true")
        # Set per-write, not via spark.conf: serverless compute rejects
        # setting spark.sql.sources.partitionOverwriteMode on the session.
        .option("partitionOverwriteMode", "dynamic")
        .partitionBy("event_date")
        .save(cfg.bronze_path("telemetry"))
    )

    written = spark.read.format("delta").load(cfg.bronze_path("telemetry")).count()
    ctx.rows_read += written
    ctx.rows_written += written
    return written


def build_bronze_reference(
    spark: SparkSession, ctx: RunContext, cfg: Settings | None = None
) -> dict[str, int]:
    """Fully snapshot the four small operational source tables."""
    cfg = cfg or settings
    counts: dict[str, int] = {}
    for table in ("machines", "plants", "work_orders", "production_orders"):
        if cfg.is_local:
            source = read_table(spark, f"ops.{table}", cfg)
            output = add_lineage(source, ctx, "postgres_ops").withColumn(
                "_source_file", F.lit(f"jdbc:ops.{table}")
            )
        else:
            # ADF is the Azure ingestion boundary. Reading its partitioned
            # Parquet landing output keeps Databricks independent of source
            # database credentials and preserves the source file in lineage.
            source = spark.read.option("recursiveFileLookup", "true").parquet(
                cfg.landing_path(table)
            )
            output = add_lineage(source, ctx, "azure_sql_via_adf")
        (
            output.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .save(cfg.bronze_path(table))
        )
        count = output.count()
        counts[table] = count
        ctx.rows_read += count
        ctx.rows_written += count
    return counts


@click.command()
@click.option("--telemetry/--no-telemetry", default=True)
@click.option("--reference/--no-reference", default=True)
def main(telemetry: bool, reference: bool) -> None:
    """Build selected Bronze datasets."""
    context = RunContext(pipeline="bronze")
    spark = get_spark("bronze", shuffle_partitions=16)
    try:
        print(f"\n{context}  starting bronze layer")
        if telemetry:
            count = build_bronze_telemetry(spark, context)
            print(f"  bronze.telemetry          : {count:,} rows")
        if reference:
            for table, count in build_bronze_reference(spark, context).items():
                print(f"  bronze.{table:<19s}: {count:,} rows")

        result = context.finish()
        print(f"\n  total written : {result['rows_written']:,}")
        print(f"  duration      : {result['duration_s']:.1f}s\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
