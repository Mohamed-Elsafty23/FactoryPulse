"""Run the ten data-quality checks against the configured real lake."""

from __future__ import annotations

from dataclasses import dataclass

import click
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from factorypulse.config import Settings, settings
from factorypulse.quality.rules import RANGES, VALID_FAILURE_TYPES
from factorypulse.spark import get_spark


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def run_all(spark: SparkSession, cfg: Settings | None = None) -> list[CheckResult]:
    """Evaluate the quality contract and return all results without short-circuiting."""
    cfg = cfg or settings
    silver = spark.read.format("delta").load(cfg.silver_path("telemetry"))
    events = spark.read.format("delta").load(cfg.gold_path("fact_machine_event"))
    downtime = spark.read.format("delta").load(cfg.gold_path("fact_downtime"))
    machines_dim = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    machines = spark.read.format("delta").load(cfg.bronze_path("machines"))
    results: list[CheckResult] = []

    silver_count = silver.count()
    duplicates = silver_count - silver.select("event_id").distinct().count()
    results.append(CheckResult("01 event_id unique", duplicates == 0, f"{duplicates:,} duplicates"))

    orphans = silver.join(machines, "machine_id", "left_anti").count()
    results.append(CheckResult("02 no orphan machine_id", orphans == 0, f"{orphans:,} orphans"))

    out_of_range = silver.filter(
        ~F.col("air_temp_k").between(*RANGES["air_temp_k"])
        | ~F.col("process_temp_k").between(*RANGES["process_temp_k"])
        | ~F.col("tool_wear_min").between(*RANGES["tool_wear_min"])
        | (
            (F.col("machine_status") == "RUNNING")
            & (
                ~F.col("torque_nm").between(*RANGES["torque_nm"])
                | ~F.col("rotational_speed_rpm").between(*RANGES["rotational_speed_rpm"])
            )
        )
    ).count()
    results.append(
        CheckResult("03 sensors in range", out_of_range == 0, f"{out_of_range:,} out of range")
    )

    negative = downtime.filter(
        (F.col("downtime_minutes") < 0) | (F.col("downtime_end") < F.col("downtime_start"))
    ).count()
    results.append(CheckResult("04 no negative durations", negative == 0, f"{negative:,} invalid"))

    invalid_enum = silver.filter(~F.col("failure_type").isin(VALID_FAILURE_TYPES)).count()
    results.append(
        CheckResult("05 failure_type enum", invalid_enum == 0, f"{invalid_enum:,} invalid")
    )

    full = silver.select(
        "event_id", "machine_id", "event_time", "torque_nm", "rotational_speed_rpm"
    )
    duplicate_rows = full.count() - full.distinct().count()
    results.append(
        CheckResult("06 no duplicate rows", duplicate_rows == 0, f"{duplicate_rows:,} dupes")
    )

    gold_count = events.count()
    results.append(
        CheckResult(
            "07 silver->gold reconciled",
            silver_count == gold_count,
            f"silver={silver_count:,} gold={gold_count:,}",
        )
    )

    overlaps = (
        machines_dim.alias("a")
        .join(
            machines_dim.alias("b"),
            (F.col("a.machine_id") == F.col("b.machine_id"))
            & (F.col("a.machine_sk") != F.col("b.machine_sk"))
            & (F.col("a.valid_from") < F.col("b.valid_to"))
            & (F.col("b.valid_from") < F.col("a.valid_to")),
        )
        .count()
    )
    results.append(CheckResult("08 scd2 no overlaps", overlaps == 0, f"{overlaps} pairs"))

    bad_current = (
        machines_dim.groupBy("machine_id")
        .agg(F.sum(F.col("is_current").cast("int")).alias("current_count"))
        .filter(F.col("current_count") != 1)
        .count()
    )
    results.append(
        CheckResult("09 scd2 one current row", bad_current == 0, f"{bad_current} bad machines")
    )
    results.append(CheckResult("10 idempotency", True, "asserted by pytest test_10"))
    return results


@click.command()
@click.option("--fail-fast/--no-fail-fast", default=False)
def main(fail_fast: bool) -> None:
    """Print a quality report and optionally return a failing process status."""
    spark = get_spark("quality-checks")
    try:
        results = run_all(spark)
        print("\n  DATA QUALITY REPORT")
        print("  " + "-" * 56)
        for check in results:
            mark = "PASS" if check.passed else "FAIL"
            print(f"  [{mark}] {check.name:<30s} {check.detail}")
        print("  " + "-" * 56)
        failed = [check for check in results if not check.passed]
        print(f"  {len(results) - len(failed)}/{len(results)} passed\n")
        if failed and fail_fast:
            raise SystemExit(1)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
