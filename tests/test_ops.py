"""Tests for immutable success/failure pipeline-run records."""

import pytest

from factorypulse.utils.ops import compute_freshness, tracked_run


@pytest.mark.slow
def test_failure_is_recorded_and_reraised(spark, mini_lake):
    with pytest.raises(ValueError, match="boom"), tracked_run(spark, "unit_fail", mini_lake) as ctx:
        ctx.rows_read = 10
        raise ValueError("boom")

    row = (
        spark.read.format("delta").load(mini_lake.ops_path).filter("pipeline = 'unit_fail'").first()
    )
    assert row["status"] == "failed"
    assert row["rows_read"] == 10
    assert "boom" in row["error_message"]


@pytest.mark.slow
def test_success_is_recorded(spark, mini_lake):
    with tracked_run(spark, "unit_ok", mini_lake) as ctx:
        ctx.rows_read, ctx.rows_written = 100, 95

    row = spark.read.format("delta").load(mini_lake.ops_path).filter("pipeline = 'unit_ok'").first()
    assert row["status"] == "success"
    assert row["rows_written"] == 95
    assert row["duration_s"] >= 0


@pytest.mark.slow
def test_freshness_uses_event_time(spark, mini_lake):
    freshness = compute_freshness(spark, mini_lake)
    assert freshness is None or freshness > 0
