from datetime import datetime

import pytest
from pyspark.sql import functions as F

from factorypulse.simulator.defects import inject_defects
from factorypulse.simulator.generate import generate_telemetry
from factorypulse.simulator.roster import ROSTER


@pytest.fixture(scope="module")
def sample(spark):
    return generate_telemetry(spark, 20_000, datetime(2025, 10, 1)).cache()


@pytest.mark.slow
def test_row_count_is_exact(sample):
    assert sample.count() == 20_000


@pytest.mark.slow
def test_all_machines_present(sample):
    assert sample.select("machine_id").distinct().count() == len(ROSTER)


@pytest.mark.slow
def test_event_id_is_unique(sample):
    assert sample.select("event_id").distinct().count() == sample.count()


@pytest.mark.slow
def test_start_date_is_not_shifted_by_host_timezone(sample):
    first = (
        sample.orderBy("event_time")
        .select(
            F.date_format("event_time", "yyyy-MM-dd HH:mm:ss").alias("event_time"), "event_date"
        )
        .first()
    )
    assert first.event_time == "2025-10-01 00:00:00"
    assert first.event_date.isoformat() == "2025-10-01"


@pytest.mark.slow
def test_failure_rate_matches_ai4i(sample):
    """Simulated failures should land near the real 3.39%."""
    rate = sample.filter("is_failure").count() / sample.count()
    assert 0.02 < rate < 0.06, f"failure rate {rate:.4f} is implausible"


@pytest.mark.slow
def test_rpm_torque_are_negatively_correlated(sample):
    correlation = sample.filter("machine_status = 'RUNNING'").stat.corr(
        "rotational_speed_rpm", "torque_nm"
    )
    assert correlation < -0.7, f"correlation {correlation:.3f} does not reproduce AI4I physics"


@pytest.mark.slow
def test_sensors_in_physical_range(sample):
    bad = sample.filter(
        (F.col("air_temp_k") < 280)
        | (F.col("air_temp_k") > 320)
        | (F.col("tool_wear_min") < 0)
        | (F.col("tool_wear_min") > 260)
    ).count()
    assert bad == 0


@pytest.mark.slow
def test_downtime_lasts_multiple_minutes(sample):
    """The future downtime fact needs intervals rather than single points."""
    down = sample.filter("machine_status = 'DOWN'").count()
    failures = sample.filter("is_failure").count()
    assert down > failures, "DOWN state is not being propagated forward"


@pytest.mark.slow
def test_determinism(spark):
    first = generate_telemetry(spark, 5_000, datetime(2025, 10, 1))
    second = generate_telemetry(spark, 5_000, datetime(2025, 10, 1))
    assert first.exceptAll(second).count() == 0, "same seed must produce identical data"


@pytest.mark.slow
def test_defect_injection_adds_bad_rows(spark):
    clean = generate_telemetry(spark, 10_000, datetime(2025, 10, 1))
    dirty = inject_defects(clean, rate=0.05)

    assert dirty.count() > clean.count(), "duplicates were not appended"
    assert dirty.filter("machine_id = 'MC-99'").count() > 0, "no orphan FKs injected"
    assert dirty.filter("machine_id IS NULL").count() > 0, "no missing values injected"
    assert dirty.filter("torque_nm > 200").count() > 0, "no out-of-range values injected"
    clean_duplicates = (
        dirty.filter(
            "machine_id IS NOT NULL AND machine_id != 'MC-99' "
            "AND event_time IS NOT NULL AND air_temp_k < 500"
        )
        .groupBy("event_id")
        .count()
        .filter("count > 1")
        .count()
    )
    assert clean_duplicates > 0, "duplicate sampling is correlated with corrupted rows"
