"""Tests for the Gold star-schema transformations."""

from datetime import date, datetime

import pytest
from pyspark.sql import functions as F

from factorypulse.config import Settings
from factorypulse.pipeline.dimensions import (
    build_dim_date,
    build_dim_failure_type,
    build_dim_plant,
    build_dim_shift,
)
from factorypulse.pipeline.gold import (
    GRAIN_COMMENTS,
    _write,
    apply_comments,
    build_agg_machine_daily,
    build_fact_downtime,
    build_fact_machine_event,
    build_fact_work_order,
)
from factorypulse.utils.run_context import RunContext


@pytest.fixture
def cfg(tmp_path):
    class TestSettings(Settings):
        def silver_path(self, table: str) -> str:
            return f"file://{tmp_path}/silver/{table}"

        def gold_path(self, table: str) -> str:
            return f"file://{tmp_path}/gold/{table}"

    return TestSettings()


def _save(df, path):
    df.write.format("delta").mode("overwrite").save(path)


@pytest.mark.slow
def test_date_dimension_is_contiguous_and_uses_iso_weekdays(spark):
    rows = build_dim_date(spark, "2025-10-03", "2025-10-06").orderBy("date").collect()
    assert [row["date"] for row in rows] == [
        date(2025, 10, 3),
        date(2025, 10, 4),
        date(2025, 10, 5),
        date(2025, 10, 6),
    ]
    assert [(row["day_of_week"], row["is_weekend"]) for row in rows] == [
        (5, False),
        (6, True),
        (7, True),
        (1, False),
    ]
    assert rows[-1]["day_name_de"] == "Montag"
    assert rows[0]["month_name_de"] == "Oktober"
    assert rows[0]["date_sk"] == 20251003


@pytest.mark.slow
def test_gold_build_reconciles_and_preserves_grains(spark, cfg):
    plants = spark.createDataFrame(
        [("PL-A", "Plant A", "DE", "Europe/Berlin")],
        "plant_id STRING, plant_name STRING, country STRING, timezone STRING",
    )
    _save(plants, cfg.silver_path("plants"))
    _write(build_dim_date(spark, "2025-01-01", "2025-01-02"), cfg.gold_path("dim_date"))
    _write(build_dim_shift(spark), cfg.gold_path("dim_shift"))
    _write(build_dim_failure_type(spark), cfg.gold_path("dim_failure_type"))
    _write(build_dim_plant(spark, cfg), cfg.gold_path("dim_plant"))

    machines = spark.createDataFrame(
        [
            (
                1,
                "MC-01",
                "PL-A",
                "LN-1",
                "low",
                datetime(2025, 1, 1),
                datetime(2025, 1, 1, 0, 3),
                False,
            ),
            (
                2,
                "MC-01",
                "PL-A",
                "LN-2",
                "low",
                datetime(2025, 1, 1, 0, 3),
                datetime(9999, 12, 31),
                True,
            ),
        ],
        "machine_sk LONG, machine_id STRING, plant_id STRING, line_id STRING, criticality STRING, "
        "valid_from TIMESTAMP, valid_to TIMESTAMP, is_current BOOLEAN",
    )
    _save(machines, cfg.gold_path("dim_machine"))

    telemetry = spark.createDataFrame(
        [
            ("E0", "MC-01", datetime(2025, 1, 1, 0, 0), "RUNNING", "NONE", False),
            ("E1", "MC-01", datetime(2025, 1, 1, 0, 1), "DOWN", "NONE", False),
            ("E2", "MC-01", datetime(2025, 1, 1, 0, 2), "DOWN", "TWF", True),
            ("E3", "MC-01", datetime(2025, 1, 1, 0, 3), "RUNNING", "NONE", False),
            ("E4", "MC-01", datetime(2025, 1, 1, 0, 4), "DOWN", "NONE", False),
        ],
        "event_id STRING, machine_id STRING, event_time TIMESTAMP, machine_status STRING, "
        "failure_type STRING, is_failure BOOLEAN",
    )
    telemetry = (
        telemetry.withColumn("event_date", telemetry.event_time.cast("date"))
        .withColumn("_batch_id", F.lit("test-batch"))
        .withColumn("shift_name", F.lit("night"))
        .withColumn("air_temp_k", telemetry.event_time.cast("long") * 0 + 300.0)
        .withColumn("process_temp_k", telemetry.event_time.cast("long") * 0 + 310.0)
        .withColumn("temp_diff_k", telemetry.event_time.cast("long") * 0 + 10.0)
        .withColumn("rotational_speed_rpm", telemetry.event_time.cast("long") * 0 + 1500.0)
        .withColumn("torque_nm", telemetry.event_time.cast("long") * 0 + 40.0)
        .withColumn("power_w", telemetry.event_time.cast("long") * 0 + 6283.0)
        .withColumn("tool_wear_min", telemetry.event_time.cast("long") * 0 + 5.0)
    )
    _save(telemetry, cfg.silver_path("telemetry"))

    work_orders = spark.createDataFrame(
        [
            (
                "WO-1",
                "MC-01",
                "corrective",
                "TWF",
                "high",
                datetime(2025, 1, 1, 0, 4),
                datetime(2025, 1, 1, 1, 0),
                5.0,
                51.0,
                56.0,
                1.0,
                20.0,
            )
        ],
        "work_order_id STRING, machine_id STRING, wo_type STRING, failure_type STRING, "
        "priority STRING, opened_at TIMESTAMP, closed_at TIMESTAMP, response_minutes DOUBLE, "
        "repair_minutes DOUBLE, total_downtime_minutes DOUBLE, labour_hours DOUBLE, parts_cost_eur DOUBLE",
    )
    _save(work_orders, cfg.silver_path("work_orders"))

    ctx = RunContext("gold-test")
    assert build_fact_machine_event(spark, ctx, cfg) == telemetry.count() == 5
    event_fact = spark.read.format("delta").load(cfg.gold_path("fact_machine_event"))
    assert [row.machine_sk for row in event_fact.orderBy("event_time").collect()] == [1, 1, 1, 2, 2]
    assert event_fact.join(machines, "machine_sk", "left_anti").count() == 0
    assert event_fact.select("_batch_id").distinct().first()["_batch_id"] == "test-batch"

    assert build_fact_downtime(spark, ctx, cfg) == 2
    downtime = spark.read.format("delta").load(cfg.gold_path("fact_downtime"))
    intervals = downtime.orderBy("downtime_start").collect()
    assert [(row.machine_sk, row.downtime_minutes) for row in intervals] == [(1, 2), (2, 1)]
    assert [row.failure_type_sk for row in intervals] == [1, 5]
    assert [row.downtime_cost_eur for row in intervals] == [80.0, 40.0]

    assert build_fact_work_order(spark, ctx, cfg) == 1
    work_order = spark.read.format("delta").load(cfg.gold_path("fact_work_order")).first()
    assert work_order.machine_sk == 2
    assert work_order.is_preventive is False

    assert build_agg_machine_daily(spark, ctx, cfg) == 2
    daily = spark.read.format("delta").load(cfg.gold_path("agg_machine_daily"))
    assert "mtbf" not in daily.columns
    assert set(daily.columns) >= {"operating_hours", "failure_count", "availability"}

    apply_comments(spark, cfg)
    for table, expected in GRAIN_COMMENTS.items():
        detail = spark.sql(f"DESCRIBE DETAIL delta.`{cfg.gold_path(table)}`").first()
        assert detail["description"] == expected
