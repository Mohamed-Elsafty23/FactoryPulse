"""FactoryPulse command-line interface."""

from __future__ import annotations

from datetime import datetime

import click

from factorypulse.config import settings
from factorypulse.spark import get_spark
from factorypulse.utils.ops import tracked_run


@click.group()
def cli() -> None:
    """FactoryPulse pipeline and operations commands."""


@cli.command()
@click.option("--effective-from", default=None, help="SCD2 version start (YYYY-MM-DD).")
@click.option("--skip-telemetry", is_flag=True, help="Process reference data only.")
def run(effective_from: str | None, skip_telemetry: bool) -> None:
    """Run Bronze, Silver, SCD2, Gold, and quality sequentially."""
    from factorypulse.pipeline.bronze import build_bronze_reference, build_bronze_telemetry
    from factorypulse.pipeline.dimensions import (
        build_dim_failure_type,
        build_dim_plant,
        build_dim_shift,
    )
    from factorypulse.pipeline.gold import (
        apply_comments,
        build_agg_machine_daily,
        build_fact_downtime,
        build_fact_machine_event,
        build_fact_work_order,
    )
    from factorypulse.pipeline.scd2 import merge_dim_machine
    from factorypulse.pipeline.silver import build_silver_reference, build_silver_telemetry
    from factorypulse.quality.checks import run_all

    spark = get_spark("factorypulse-pipeline", shuffle_partitions=16)
    effective = datetime.fromisoformat(effective_from) if effective_from else datetime.now()
    try:
        with tracked_run(spark, "bronze") as ctx:
            if not skip_telemetry:
                build_bronze_telemetry(spark, ctx)
            build_bronze_reference(spark, ctx)

        with tracked_run(spark, "silver") as ctx:
            if not skip_telemetry:
                build_silver_telemetry(spark, ctx)
            build_silver_reference(spark, ctx)

        with tracked_run(spark, "scd2_dim_machine") as ctx:
            source = spark.read.format("delta").load(settings.bronze_path("machines"))
            stats = merge_dim_machine(spark, source, effective)
            ctx.rows_read = source.count()
            ctx.rows_written = stats.get("changed", 0) + stats.get("new", 0)
            print(f"      scd2: {stats}")

        with tracked_run(spark, "gold") as ctx:
            for name, frame in (
                ("dim_shift", build_dim_shift(spark)),
                ("dim_plant", build_dim_plant(spark)),
                ("dim_failure_type", build_dim_failure_type(spark)),
            ):
                frame.write.format("delta").mode("overwrite").option(
                    "overwriteSchema", "true"
                ).save(settings.gold_path(name))
                ctx.rows_written += frame.count()

            build_fact_machine_event(spark, ctx)
            build_fact_downtime(spark, ctx)
            build_fact_work_order(spark, ctx)
            build_agg_machine_daily(spark, ctx)
            apply_comments(spark)

        with tracked_run(spark, "quality") as ctx:
            results = run_all(spark)
            failed = [check for check in results if not check.passed]
            for check in results:
                mark = "PASS" if check.passed else "FAIL"
                print(f"      [{mark}] {check.name}: {check.detail}")
            if failed:
                raise RuntimeError(f"{len(failed)} data-quality checks failed")

        print("\n  pipeline complete\n")
    finally:
        spark.stop()


@cli.command()
@click.option("--limit", default=20, type=click.IntRange(min=1), show_default=True)
def ops(limit: int) -> None:
    """Show recent pipeline runs."""
    from pyspark.sql import functions as F

    spark = get_spark("ops-report")
    try:
        (
            spark.read.format("delta")
            .load(settings.ops_path)
            .orderBy(F.desc("started_at"))
            .select(
                "pipeline",
                "status",
                "started_at",
                F.round("duration_s", 1).alias("sec"),
                "rows_read",
                "rows_written",
                "rows_rejected",
                F.round(F.col("freshness_s") / 3600, 2).alias("fresh_h"),
                "git_sha",
            )
            .show(limit, truncate=False)
        )
    finally:
        spark.stop()


@cli.command(name="platform-kpis")
def platform_kpis() -> None:
    """Print the platform KPIs defined in the KPI dictionary."""
    from pyspark.sql import functions as F

    spark = get_spark("platform-kpis")
    try:
        ops_df = spark.read.format("delta").load(settings.ops_path)
        print("\n  PLATFORM KPIs")
        print("  " + "-" * 52)

        total = ops_df.count()
        successes = ops_df.filter(F.col("status") == "success").count()
        success_rate = successes / total * 100 if total else 0.0
        print(f"  pipeline success rate : {success_rate:5.1f}%   (SLA > 95%)")

        totals = ops_df.agg(
            F.sum("rows_rejected").alias("rejected"), F.sum("rows_read").alias("read")
        ).first()
        rejected_rate = totals["rejected"] / totals["read"] * 100 if totals["read"] else 0.0
        print(f"  rejected-record rate  : {rejected_rate:5.2f}%   (SLA < 2%)")

        fresh = (
            ops_df.filter(F.col("freshness_s").isNotNull()).orderBy(F.desc("started_at")).first()
        )
        if fresh:
            hours = fresh["freshness_s"] / 3600
            print(f"  data freshness        : {hours:5.1f}h   (SLA < 1h)")
            if hours > 1:
                print("       ^ expected: the simulated dataset is historical, not live.")
        else:
            print("  data freshness        : unavailable")
        print("  " + "-" * 52 + "\n")
    finally:
        spark.stop()


if __name__ == "__main__":
    cli()
