from datetime import datetime

import pytest
from pyspark.sql import functions as F

from factorypulse.pipeline.silver import deduplicate, split_valid_invalid
from factorypulse.quality.rules import telemetry_reject_reason

VALID_IDS = ["MC-01", "MC-02"]


def _row(**overrides):
    row = {
        "event_id": "MC-01-202510010900",
        "machine_id": "MC-01",
        "event_time": datetime(2025, 10, 1, 9),
        "air_temp_k": 300.0,
        "process_temp_k": 310.0,
        "torque_nm": 40.0,
        "rotational_speed_rpm": 1500,
        "tool_wear_min": 100,
        "failure_type": "NONE",
        "machine_status": "RUNNING",
        "repair_minutes": 0,
        "_ingested_at": datetime(2025, 10, 2),
        "_source_file": "a.parquet",
    }
    row.update(overrides)
    return row


@pytest.fixture
def frame(spark):
    def make(rows):
        return spark.createDataFrame([_row(**row) for row in rows])

    return make


@pytest.mark.slow
def test_clean_row_passes(frame):
    clean, rejected = split_valid_invalid(frame([{}]), telemetry_reject_reason(VALID_IDS))
    assert clean.count() == 1
    assert rejected.count() == 0


@pytest.mark.slow
def test_orphan_machine_id_is_rejected(frame):
    _, rejected = split_valid_invalid(
        frame([{"machine_id": "MC-99"}]), telemetry_reject_reason(VALID_IDS)
    )
    assert rejected.first()["reject_reason"] == "orphan_machine_id"


@pytest.mark.slow
def test_out_of_range_torque_is_rejected(frame):
    _, rejected = split_valid_invalid(
        frame([{"torque_nm": 400.0}]), telemetry_reject_reason(VALID_IDS)
    )
    assert rejected.first()["reject_reason"] == "torque_out_of_range"


@pytest.mark.slow
def test_stopped_machine_with_zero_rpm_is_valid(frame):
    clean, rejected = split_valid_invalid(
        frame([{"machine_status": "DOWN", "rotational_speed_rpm": 0, "torque_nm": 0.0}]),
        telemetry_reject_reason(VALID_IDS),
    )
    assert rejected.count() == 0
    assert clean.count() == 1


@pytest.mark.slow
def test_running_machine_with_zero_rpm_is_rejected(frame):
    _, rejected = split_valid_invalid(
        frame([{"rotational_speed_rpm": 0}]), telemetry_reject_reason(VALID_IDS)
    )
    assert rejected.first()["reject_reason"] == "rpm_out_of_range"


@pytest.mark.slow
def test_invalid_failure_type_is_rejected(frame):
    _, rejected = split_valid_invalid(
        frame([{"failure_type": "XXX"}]), telemetry_reject_reason(VALID_IDS)
    )
    assert rejected.first()["reject_reason"] == "invalid_failure_type"


@pytest.mark.slow
def test_negative_duration_is_rejected(frame):
    _, rejected = split_valid_invalid(
        frame([{"repair_minutes": -5}]), telemetry_reject_reason(VALID_IDS)
    )
    assert rejected.first()["reject_reason"] == "negative_duration"


@pytest.mark.slow
def test_dedup_keeps_latest(frame):
    output = deduplicate(
        frame(
            [
                {"_ingested_at": datetime(2025, 10, 1), "torque_nm": 10.0},
                {"_ingested_at": datetime(2025, 10, 3), "torque_nm": 30.0},
                {"_ingested_at": datetime(2025, 10, 2), "torque_nm": 20.0},
            ]
        ),
        "event_id",
        [F.col("_ingested_at").desc(), F.col("_source_file").desc()],
    )
    assert output.count() == 1
    assert output.first()["torque_nm"] == 30.0


@pytest.mark.slow
def test_dedup_is_deterministic_on_ingestion_time_tie(frame):
    same_time = datetime(2025, 10, 1)
    output = deduplicate(
        frame(
            [
                {"_ingested_at": same_time, "_source_file": "a.parquet"},
                {"_ingested_at": same_time, "_source_file": "b.parquet"},
            ]
        ),
        "event_id",
        [F.col("_ingested_at").desc(), F.col("_source_file").desc()],
    )
    assert output.count() == 1
    assert output.first()["_source_file"] == "b.parquet"
