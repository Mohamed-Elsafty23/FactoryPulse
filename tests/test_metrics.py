"""Tests for the dashboard semantic layer.

The non-additivity test is the reason this layer is Python and not DAX.
"""

import pytest

from factorypulse.dashboard.data import connect, default_export_dir
from factorypulse.dashboard.metrics import (
    Filters,
    failure_pareto,
    kpi_summary,
    kpi_with_prior,
    worst_machines,
)

pytestmark = pytest.mark.skipif(
    not (default_export_dir() / "gold_fact_downtime").exists(),
    reason="exports/ not present — run notebooks/98_export_for_dashboard.py",
)


@pytest.fixture(scope="module")
def con():
    return connect()


@pytest.fixture
def f():
    return Filters()


# =========================================================================
# THE test. MTBF is non-additive: the fleet value is the ratio of sums,
# NOT the mean of per-machine ratios.
# =========================================================================
def test_mtbf_is_non_additive(con, f):
    fleet = kpi_summary(con, f)["mtbf_hours"]
    per_machine = worst_machines(con, f, limit=100)["mtbf_hours"].dropna()

    assert fleet is not None and len(per_machine) > 1

    naive_mean = per_machine.mean()

    # They MUST differ. If they are equal, someone has "simplified" the
    # fleet metric into an average of ratios and every rollup is now wrong.
    assert abs(fleet - naive_mean) / fleet > 0.01, (
        f"Fleet MTBF ({fleet:.2f}) equals the mean of per-machine MTBF "
        f"({naive_mean:.2f}). MTBF is NON-ADDITIVE — the fleet value must be "
        "SUM(operating_hours)/SUM(failure_count), not an average of ratios."
    )


def test_mtbf_equals_ratio_of_sums(con, f):
    k = kpi_summary(con, f)
    assert k["mtbf_hours"] == pytest.approx(k["operating_hours"] / k["failure_count"], rel=1e-9)


def test_mtbf_is_none_not_infinity_when_no_failures(con):
    """Zero failures means UNDEFINED MTBF, never infinite."""
    impossible = Filters(date_from="1999-01-01", date_to="1999-01-02")
    assert kpi_summary(con, impossible)["mtbf_hours"] is None


# ---- Pareto -------------------------------------------------------------
def test_pareto_cumulative_reaches_100(con, f):
    """If it stops short, the cumulative is computed against the wrong total."""
    df = failure_pareto(con, f)
    assert not df.empty
    assert df["cumulative_pct"].iloc[-1] == pytest.approx(100.0, abs=0.01)


def test_pareto_is_sorted_descending(con, f):
    df = failure_pareto(con, f)
    assert df["downtime_hours"].is_monotonic_decreasing


def test_pareto_shares_one_axis(con, f):
    """Both series are percentages, so the chart needs no second y-axis."""
    df = failure_pareto(con, f)
    assert df["pct_of_total"].between(0, 100).all()
    assert df["cumulative_pct"].between(0, 100.01).all()


def test_pareto_excludes_none_failure_type(con, f):
    df = failure_pareto(con, f)
    assert "NONE" not in set(df["code"])


# ---- SCD2 ---------------------------------------------------------------
def test_current_filter_prevents_scd2_duplicates(con):
    """dim_machine has more rows than machines. Current-state views must
    not show a changed machine twice."""
    cur = worst_machines(con, Filters(current_machines_only=True), limit=100)
    assert cur["machine_id"].is_unique

    hist = worst_machines(con, Filters(current_machines_only=False), limit=100)
    assert len(hist) >= len(cur)


# ---- Filters ------------------------------------------------------------
def test_plant_filter_reduces_downtime(con):
    all_plants = kpi_summary(con, Filters())["downtime_hours"]
    one = kpi_summary(con, Filters(plants=("Ingolstadt",)))["downtime_hours"]
    assert 0 < one < all_plants


def test_prior_window_is_same_length(con):
    import pandas as pd

    f = Filters(date_from="2026-03-01", date_to="2026-03-31")
    out = kpi_with_prior(con, f)
    assert out["prior"] is not None
    # 31-day window -> 31-day prior window
    assert (pd.Timestamp("2026-03-31") - pd.Timestamp("2026-03-01")).days == 30


def test_availability_between_zero_and_one(con, f):
    a = kpi_summary(con, f)["availability"]
    assert a is None or 0 <= a <= 1


# ---- Smoke coverage -----------------------------------------------------
def test_every_metric_function_executes(con, f):
    """Each public metric must run against the real exports.

    A page died in the browser because `failure_rate_by_shift` used a SQL
    function DuckDB doesn't have. Nothing else called it, so nothing caught
    it. This keeps every query on a path the test suite actually executes.
    """
    from factorypulse.dashboard import metrics as m

    assert m.kpi_summary(con, f)["downtime_hours"] > 0
    assert m.kpi_with_prior(con, f)["current"] is not None
    assert not m.downtime_trend(con, f).empty
    assert not m.failure_pareto(con, f).empty
    assert not m.worst_machines(con, f, limit=5).empty
    assert not m.failure_rate_by_shift(con, f).empty

    options = m.filter_options(con)
    assert options["plants"] and options["shifts"]

    machine = m.worst_machines(con, f, limit=1)["machine_id"].iloc[0]
    detail = m.machine_detail(con, f, machine)
    assert set(detail) == {"attributes", "daily", "modes", "work_orders"}
    assert not detail["attributes"].empty


def test_shift_labels_are_display_ready(con, f):
    """The chart groups on these, so they must be presentable, not raw keys."""
    from factorypulse.dashboard.metrics import failure_rate_by_shift

    shifts = set(failure_rate_by_shift(con, f)["shift"])
    assert shifts == {"Early", "Late", "Night"}


def test_failure_modes_are_in_english(con, f):
    """dim_failure_type carries name_en and name_de; the UI uses name_en."""
    from factorypulse.dashboard.metrics import failure_pareto

    modes = set(failure_pareto(con, f)["failure_mode"])
    assert "Heat dissipation failure" in modes
    assert not any("ausfall" in m.lower() for m in modes)
