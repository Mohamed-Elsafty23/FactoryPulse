"""Tests for machine dimension SCD Type 2 behaviour."""

from datetime import datetime

import pytest
from pyspark.sql import functions as F

from factorypulse.config import Settings
from factorypulse.pipeline.scd2 import attribute_hash, initialise_dim_machine, merge_dim_machine


def _src(spark, rows):
    return spark.createDataFrame(
        rows,
        "machine_id STRING, plant_id STRING, line_id STRING, model STRING, "
        "machine_type STRING, criticality STRING, is_active BOOLEAN, "
        "machine_name STRING, ideal_cycle_seconds DOUBLE, installed_date STRING",
    )


def _row(mid="MC-01", line="LN-1", crit="low", name="machine"):
    return (mid, "PL-A", line, "HSM-400", "L", crit, True, name, 30.0, "2020-01-01")


@pytest.fixture
def cfg(tmp_path):
    class TestSettings(Settings):
        def gold_path(self, table: str) -> str:
            return f"file://{tmp_path}/gold/{table}"

    return TestSettings()


@pytest.mark.slow
def test_attribute_hash_is_null_safe_and_separated(spark):
    null_hash = spark.createDataFrame([(None,)], "c STRING").withColumn("h", attribute_hash(["c"]))
    value_hash = spark.createDataFrame([("x",)], "c STRING").withColumn("h", attribute_hash(["c"]))
    assert null_hash.first()["h"] != value_hash.first()["h"]

    left = spark.createDataFrame([("AB", "C")], "a STRING, b STRING").withColumn(
        "h", attribute_hash(["a", "b"])
    )
    right = spark.createDataFrame([("A", "BC")], "a STRING, b STRING").withColumn(
        "h", attribute_hash(["a", "b"])
    )
    assert left.first()["h"] != right.first()["h"]


@pytest.mark.slow
def test_change_creates_contiguous_non_overlapping_versions(spark, cfg):
    initialise_dim_machine(spark, _src(spark, [_row(line="LN-1")]), datetime(2025, 1, 1), cfg)
    merge_dim_machine(spark, _src(spark, [_row(line="LN-2")]), datetime(2025, 6, 1), cfg)
    merge_dim_machine(spark, _src(spark, [_row(line="LN-3")]), datetime(2025, 9, 1), cfg)

    d = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    rows = d.orderBy("valid_from").collect()
    assert len(rows) == 3
    assert sum(row["is_current"] for row in rows) == 1
    assert rows[-1]["line_id"] == "LN-3"
    assert all(a["valid_to"] == b["valid_from"] for a, b in zip(rows, rows[1:], strict=False))

    a, b = d.alias("a"), d.alias("b")
    overlaps = a.join(
        b,
        (F.col("a.machine_id") == F.col("b.machine_id"))
        & (F.col("a.machine_sk") != F.col("b.machine_sk"))
        & (F.col("a.valid_from") < F.col("b.valid_to"))
        & (F.col("b.valid_from") < F.col("a.valid_to")),
    ).count()
    assert overlaps == 0


@pytest.mark.slow
def test_exactly_one_current_row_per_machine(spark, cfg):
    initialise_dim_machine(
        spark, _src(spark, [_row("MC-01"), _row("MC-02")]), datetime(2025, 1, 1), cfg
    )
    merge_dim_machine(
        spark,
        _src(spark, [_row("MC-01", line="LN-9"), _row("MC-02")]),
        datetime(2025, 6, 1),
        cfg,
    )
    d = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    assert d.filter("is_current").groupBy("machine_id").count().filter("count <> 1").count() == 0


@pytest.mark.slow
def test_merge_is_idempotent_and_keys_are_stable(spark, cfg):
    src = _src(spark, [_row()])
    initialise_dim_machine(spark, src, datetime(2025, 1, 1), cfg)
    before = spark.read.format("delta").load(cfg.gold_path("dim_machine")).first()["machine_sk"]
    assert merge_dim_machine(spark, src, datetime(2025, 3, 1), cfg) == {
        "changed": 0,
        "new": 0,
        "unchanged": 1,
    }
    rows = spark.read.format("delta").load(cfg.gold_path("dim_machine")).collect()
    assert len(rows) == 1
    assert rows[0]["machine_sk"] == before


@pytest.mark.slow
def test_new_machine_is_inserted_and_type1_change_is_overwritten(spark, cfg):
    initialise_dim_machine(spark, _src(spark, [_row("MC-01")]), datetime(2025, 1, 1), cfg)
    merge_dim_machine(
        spark,
        _src(spark, [_row("MC-01", name="renamed"), _row("MC-02")]),
        datetime(2025, 6, 1),
        cfg,
    )
    d = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    assert d.count() == 2
    assert d.filter("is_current").count() == 2
    assert d.filter("machine_id = 'MC-01'").first()["machine_name"] == "renamed"


def _src_with_updated_at(spark, rows):
    """A source shaped like bronze.machines: carries the source change time."""
    return spark.createDataFrame(
        rows,
        "machine_id STRING, plant_id STRING, line_id STRING, model STRING, "
        "machine_type STRING, criticality STRING, is_active BOOLEAN, "
        "machine_name STRING, ideal_cycle_seconds DOUBLE, installed_date STRING, "
        "updated_at TIMESTAMP",
    )


@pytest.mark.slow
def test_first_version_covers_all_history_not_load_time(spark, cfg):
    """The earliest version must reach back before every fact.

    A full extract shows CURRENT state, so `updated_at` is when the row last
    changed, not when these attributes started. Anchoring version one at either
    `updated_at` or load time leaves older facts with no row to join to, and
    they disappear from Gold -- exactly how fact_machine_event came out short.
    """
    loaded_at = datetime(2026, 10, 19)
    last_changed = datetime(2026, 5, 5)
    src = _src_with_updated_at(spark, [(*_row(), last_changed)])

    initialise_dim_machine(spark, src, loaded_at, cfg)
    row = spark.read.format("delta").load(cfg.gold_path("dim_machine")).first()

    # Compared as "before any plausible fact" rather than to the exact
    # sentinel: a naive datetime renders through the session timezone, so
    # equality here would assert the JVM's 1900 UTC offset, not the behaviour.
    assert row["valid_from"] < datetime(1900, 1, 2)
    assert row["valid_from"] < last_changed < row["valid_to"]


@pytest.mark.slow
def test_every_fact_timestamp_finds_exactly_one_version(spark, cfg):
    """The property that check 07 (silver->gold reconciliation) depends on."""
    src = _src_with_updated_at(
        spark,
        [
            (*_row("MC-09", crit="low"), datetime(2025, 10, 1)),
            (*_row("MC-09", crit="high"), datetime(2026, 6, 1)),
            (*_row("MC-02"), datetime(2026, 5, 5)),
        ],
    )
    initialise_dim_machine(spark, src, datetime(2026, 10, 19), cfg)
    dim = spark.read.format("delta").load(cfg.gold_path("dim_machine"))

    events = spark.createDataFrame(
        [
            ("MC-09", datetime(2025, 10, 5)),
            ("MC-09", datetime(2026, 9, 1)),
            ("MC-02", datetime(2025, 11, 2)),
            ("MC-02", datetime(2026, 8, 8)),
        ],
        "machine_id STRING, event_time TIMESTAMP",
    )
    matched = events.alias("e").join(
        dim.alias("d"),
        (F.col("e.machine_id") == F.col("d.machine_id"))
        & (F.col("e.event_time") >= F.col("d.valid_from"))
        & (F.col("e.event_time") < F.col("d.valid_to")),
    )
    # Exactly one version per event: no drops (Gold short) and no fan-out
    # (Gold inflated). Both are silent corruption.
    assert matched.count() == events.count()


@pytest.mark.slow
def test_multi_version_source_chains_into_one_current_version(spark, cfg):
    """bronze.machines accumulates a full extract plus later incremental rows.

    Both rows for a changed machine must become CHAINED versions, not two
    simultaneously-open ones.
    """
    src = _src_with_updated_at(
        spark,
        [
            (*_row("MC-09", crit="low"), datetime(2025, 10, 1)),
            (*_row("MC-09", crit="high"), datetime(2026, 6, 1)),
            (*_row("MC-01"), datetime(2025, 10, 1)),
        ],
    )

    initialise_dim_machine(spark, src, datetime(2026, 10, 19), cfg)
    d = spark.read.format("delta").load(cfg.gold_path("dim_machine"))

    # Exactly one open version per machine — the check that failed in Phase 14.
    assert d.filter("is_current").groupBy("machine_id").count().filter("count <> 1").count() == 0

    versions = d.filter("machine_id = 'MC-09'").orderBy("valid_from").collect()
    assert len(versions) == 2
    assert versions[0]["criticality"] == "low"
    assert versions[1]["criticality"] == "high"
    # Half-open and contiguous: one version ends exactly where the next begins.
    assert versions[0]["valid_to"] == versions[1]["valid_from"]
    assert versions[0]["is_current"] is False
    assert versions[1]["is_current"] is True
    assert versions[0]["machine_sk"] != versions[1]["machine_sk"]


@pytest.mark.slow
def test_repeated_identical_extracts_do_not_create_versions(spark, cfg):
    """The same row re-extracted is not a change."""
    src = _src_with_updated_at(
        spark,
        [
            (*_row("MC-01", crit="low"), datetime(2025, 10, 1)),
            (*_row("MC-01", crit="low"), datetime(2026, 1, 1)),
        ],
    )
    initialise_dim_machine(spark, src, datetime(2026, 10, 19), cfg)

    d = spark.read.format("delta").load(cfg.gold_path("dim_machine"))
    assert d.count() == 1
    assert d.first()["valid_from"] < datetime(1900, 1, 2)
