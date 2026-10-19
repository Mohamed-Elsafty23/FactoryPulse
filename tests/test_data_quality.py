"""The ten required data-quality tests, run against the miniature local lake."""

import pytest
from pyspark.sql import functions as F

from factorypulse.quality.rules import RANGES, VALID_FAILURE_TYPES

pytestmark = pytest.mark.slow


def test_01_event_id_is_unique(silver):
    df = silver("telemetry")
    total, distinct = df.count(), df.select("event_id").distinct().count()
    assert total == distinct, f"{total - distinct} duplicate event_id values survived Silver"


def test_02_no_orphan_machine_ids(spark, silver, mini_lake):
    machines = spark.read.format("delta").load(mini_lake.bronze_path("machines"))
    orphans = silver("telemetry").join(machines, "machine_id", "left_anti").count()
    assert orphans == 0, f"{orphans} Silver rows reference a non-existent machine"


def test_03_sensors_within_physical_ranges(silver):
    df = silver("telemetry")
    bad_any_state = df.filter(
        ~F.col("air_temp_k").between(*RANGES["air_temp_k"])
        | ~F.col("process_temp_k").between(*RANGES["process_temp_k"])
        | ~F.col("tool_wear_min").between(*RANGES["tool_wear_min"])
    ).count()
    bad_running = (
        df.filter(F.col("machine_status") == "RUNNING")
        .filter(
            ~F.col("torque_nm").between(*RANGES["torque_nm"])
            | ~F.col("rotational_speed_rpm").between(*RANGES["rotational_speed_rpm"])
        )
        .count()
    )
    assert bad_any_state == 0, f"{bad_any_state} rows outside state-independent ranges"
    assert bad_running == 0, f"{bad_running} RUNNING rows outside motion ranges"


def test_04_no_negative_durations(gold):
    downtime = gold("fact_downtime")
    negative = downtime.filter(F.col("downtime_minutes") < 0).count()
    assert negative == 0, f"{negative} downtime intervals have negative duration"
    bad_order = downtime.filter(F.col("downtime_end") < F.col("downtime_start")).count()
    assert bad_order == 0, f"{bad_order} intervals end before they start"


def test_05_failure_type_in_enum(silver):
    bad = (
        silver("telemetry")
        .filter(~F.col("failure_type").isin(VALID_FAILURE_TYPES))
        .select("failure_type")
        .distinct()
        .collect()
    )
    assert not bad, f"unexpected failure types: {[row[0] for row in bad]}"


def test_06_no_duplicate_rows_after_dedup(silver):
    df = silver("telemetry").select(
        "event_id", "machine_id", "event_time", "torque_nm", "rotational_speed_rpm"
    )
    assert df.count() == df.distinct().count(), "fully duplicate rows survived dedup"


def test_07_silver_gold_reconciliation(silver, gold):
    silver_count = silver("telemetry").count()
    gold_count = gold("fact_machine_event").count()
    detail = "Fan-out: SCD2 intervals overlap or the range join is wrong."
    if gold_count < silver_count:
        detail = "Row loss: a join dropped rows with no matching dimension value."
    assert silver_count == gold_count, f"silver={silver_count:,} gold={gold_count:,}. {detail}"


def test_08_scd2_no_overlapping_intervals(gold):
    left = gold("dim_machine").alias("a")
    overlaps = left.join(
        gold("dim_machine").alias("b"),
        (F.col("a.machine_id") == F.col("b.machine_id"))
        & (F.col("a.machine_sk") != F.col("b.machine_sk"))
        & (F.col("a.valid_from") < F.col("b.valid_to"))
        & (F.col("b.valid_from") < F.col("a.valid_to")),
    ).count()
    assert overlaps == 0, f"{overlaps} overlapping SCD2 interval pairs"


def test_09_scd2_exactly_one_current_row(gold):
    bad = (
        gold("dim_machine")
        .groupBy("machine_id")
        .agg(F.sum(F.col("is_current").cast("int")).alias("current_count"))
        .filter(F.col("current_count") != 1)
        .collect()
    )
    assert not bad, f"machines without exactly one current row: {[row.machine_id for row in bad]}"


def test_10_rerun_is_idempotent(spark, mini_lake, gold):
    from factorypulse.pipeline.gold import build_fact_machine_event
    from factorypulse.utils.run_context import RunContext

    before = gold("fact_machine_event").count()
    build_fact_machine_event(spark, RunContext(pipeline="rerun"), mini_lake)
    after = spark.read.format("delta").load(mini_lake.gold_path("fact_machine_event")).count()
    assert (
        before == after
    ), f"re-running Gold changed row count ({before:,} -> {after:,}); check overwrite semantics"
