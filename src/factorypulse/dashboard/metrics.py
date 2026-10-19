"""The semantic layer. Every number on the dashboard is defined here, once.

This is the module that would be DAX in a .pbix. Being Python means it is
diffable, reusable outside the report, and — the reason this phase exists —
unit-testable. See tests/test_metrics.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

# Downtime cost rate is applied in the GOLD layer, not here — the assumption
# stays visible in the data model. See docs/kpi_dictionary.md.


@dataclass(frozen=True)
class Filters:
    """Scope shared by every metric. Add a field here, not to each function."""

    date_from: str = "2025-10-01"
    date_to: str = "2026-12-31"
    plants: tuple[str, ...] = ()
    shifts: tuple[str, ...] = ()
    current_machines_only: bool = True

    def date_sk_range(self) -> tuple[int, int]:
        return (
            int(self.date_from.replace("-", "")),
            int(self.date_to.replace("-", "")),
        )


def _quote(values: tuple[str, ...]) -> str:
    """SQL string list with quotes escaped."""
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _plant_clause(f: Filters, alias: str = "p") -> str:
    if not f.plants:
        return ""
    return f" AND {alias}.plant_name IN ({_quote(f.plants)})"


def _shift_clause(f: Filters, alias: str = "s") -> str:
    if not f.shifts:
        return ""
    return f" AND {alias}.shift_name IN ({_quote(f.shifts)})"


def _current_clause(f: Filters, alias: str = "m") -> str:
    # dim_machine is SCD2: without this a changed machine appears twice.
    # Correct for history, confusing for current state. See 15.8.
    return f" AND {alias}.is_current" if f.current_machines_only else ""


# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------
def kpi_summary(con: duckdb.DuckDBPyConnection, f: Filters) -> dict:
    """The five numbers on the top row of page 1."""
    lo, hi = f.date_sk_range()

    ops = con.execute(
        f"""
        SELECT
            COALESCE(SUM(a.operating_hours), 0) AS operating_hours,
            COALESCE(SUM(a.failure_count), 0)   AS failure_count
        FROM agg_machine_daily a
        JOIN dim_machine m ON a.machine_sk = m.machine_sk
        JOIN dim_plant   p ON a.plant_sk   = p.plant_sk
        WHERE a.date_sk BETWEEN {lo} AND {hi}
          {_plant_clause(f)}{_current_clause(f)}
        """
    ).fetchone()

    dt = con.execute(
        f"""
        SELECT
            COALESCE(SUM(d.downtime_minutes), 0)  AS downtime_minutes,
            COALESCE(SUM(d.downtime_cost_eur), 0) AS downtime_cost_eur,
            COUNT(*)                              AS downtime_events
        FROM fact_downtime d
        JOIN dim_machine m ON d.machine_sk = m.machine_sk
        JOIN dim_plant   p ON d.plant_sk   = p.plant_sk
        JOIN dim_shift   s ON d.shift_sk   = s.shift_sk
        WHERE d.date_sk BETWEEN {lo} AND {hi}
          {_plant_clause(f)}{_shift_clause(f)}{_current_clause(f)}
        """
    ).fetchone()

    operating_hours, failure_count = float(ops[0]), int(ops[1])
    downtime_minutes, downtime_cost, downtime_events = (
        float(dt[0]),
        float(dt[1]),
        int(dt[2]),
    )
    downtime_hours = downtime_minutes / 60.0

    # NON-ADDITIVE: ratio of sums. None (not inf) when undefined.
    mtbf = operating_hours / failure_count if failure_count else None
    mttr = downtime_hours / downtime_events if downtime_events else None
    availability = (
        mtbf / (mtbf + mttr) if (mtbf is not None and mttr is not None and mtbf + mttr) else None
    )

    return {
        "operating_hours": operating_hours,
        "failure_count": failure_count,
        "downtime_hours": downtime_hours,
        "downtime_cost_eur": downtime_cost,
        "downtime_events": downtime_events,
        "mtbf_hours": mtbf,
        "mttr_hours": mttr,
        "availability": availability,
        "failures_per_1000h": (failure_count / operating_hours * 1000 if operating_hours else None),
    }


def kpi_with_prior(con: duckdb.DuckDBPyConnection, f: Filters) -> dict:
    """Current window plus the immediately preceding window of equal length.

    Comparing like-for-like windows is why the prior period is computed from
    the selected range, not hardcoded to 'last month'.
    """
    cur = kpi_summary(con, f)

    start = pd.Timestamp(f.date_from)
    end = pd.Timestamp(f.date_to)
    span = end - start
    prior = Filters(
        date_from=(start - span - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        date_to=(start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        plants=f.plants,
        shifts=f.shifts,
        current_machines_only=f.current_machines_only,
    )
    prev = kpi_summary(con, prior)

    def delta(key: str) -> float | None:
        a, b = cur.get(key), prev.get(key)
        if a is None or b in (None, 0):
            return None
        return (a - b) / b

    return {
        "current": cur,
        "prior": prev,
        "delta": {
            k: delta(k) for k in ("downtime_hours", "downtime_cost_eur", "mtbf_hours", "mttr_hours")
        },
    }


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------
def downtime_trend(con: duckdb.DuckDBPyConnection, f: Filters) -> pd.DataFrame:
    """Monthly downtime hours and cost."""
    lo, hi = f.date_sk_range()
    return con.execute(
        f"""
        SELECT
            dd.year_month                           AS month,
            SUM(d.downtime_minutes) / 60.0          AS downtime_hours,
            SUM(d.downtime_cost_eur)                AS downtime_cost_eur,
            COUNT(*)                                AS downtime_events
        FROM fact_downtime d
        JOIN dim_date    dd ON d.date_sk    = dd.date_sk
        JOIN dim_machine m  ON d.machine_sk = m.machine_sk
        JOIN dim_plant   p  ON d.plant_sk   = p.plant_sk
        JOIN dim_shift   s  ON d.shift_sk   = s.shift_sk
        WHERE d.date_sk BETWEEN {lo} AND {hi}
          {_plant_clause(f)}{_shift_clause(f)}{_current_clause(f)}
        GROUP BY 1
        ORDER BY 1
        """
    ).df()


# ---------------------------------------------------------------------------
# Pareto — expressed as PERCENT so bars and cumulative share ONE axis.
# ---------------------------------------------------------------------------
def failure_pareto(con: duckdb.DuckDBPyConnection, f: Filters) -> pd.DataFrame:
    """Downtime by failure mode, as % of total, plus the cumulative %.

    Both columns are percentages of the same total, so a Pareto chart can be
    drawn on ONE y-axis. See 15.7 for why that matters.
    """
    lo, hi = f.date_sk_range()
    df = con.execute(
        f"""
        SELECT
            ft.name_de                      AS failure_mode,
            ft.code                         AS code,
            SUM(d.downtime_minutes) / 60.0  AS downtime_hours,
            SUM(d.downtime_cost_eur)        AS downtime_cost_eur,
            COUNT(*)                        AS events
        FROM fact_downtime d
        JOIN dim_failure_type ft ON d.failure_type_sk = ft.failure_type_sk
        JOIN dim_machine m  ON d.machine_sk = m.machine_sk
        JOIN dim_plant   p  ON d.plant_sk   = p.plant_sk
        JOIN dim_shift   s  ON d.shift_sk   = s.shift_sk
        WHERE d.date_sk BETWEEN {lo} AND {hi}
          AND ft.code <> 'NONE'
          {_plant_clause(f)}{_shift_clause(f)}{_current_clause(f)}
        GROUP BY 1, 2
        ORDER BY downtime_hours DESC
        """
    ).df()

    if df.empty:
        return df

    total = df["downtime_hours"].sum()
    df["pct_of_total"] = df["downtime_hours"] / total * 100
    df["cumulative_pct"] = df["pct_of_total"].cumsum()
    return df


# ---------------------------------------------------------------------------
# Ranked machines
# ---------------------------------------------------------------------------
def worst_machines(con: duckdb.DuckDBPyConnection, f: Filters, limit: int = 15) -> pd.DataFrame:
    """Ranked by COST, not hours — see 15.8 for why."""
    lo, hi = f.date_sk_range()
    return con.execute(
        f"""
        WITH dt AS (
            SELECT d.machine_sk,
                   SUM(d.downtime_minutes) / 60.0 AS downtime_hours,
                   SUM(d.downtime_cost_eur)       AS downtime_cost_eur,
                   COUNT(*)                       AS downtime_events
            FROM fact_downtime d
            JOIN dim_plant p ON d.plant_sk = p.plant_sk
            JOIN dim_shift s ON d.shift_sk = s.shift_sk
            WHERE d.date_sk BETWEEN {lo} AND {hi}
              {_plant_clause(f)}{_shift_clause(f)}
            GROUP BY 1
        ),
        op AS (
            SELECT a.machine_sk,
                   SUM(a.operating_hours) AS operating_hours,
                   SUM(a.failure_count)   AS failure_count
            FROM agg_machine_daily a
            JOIN dim_plant p ON a.plant_sk = p.plant_sk
            WHERE a.date_sk BETWEEN {lo} AND {hi}
              {_plant_clause(f)}
            GROUP BY 1
        )
        SELECT
            m.machine_id,
            m.machine_name,
            p.plant_name,
            m.line_id,
            m.criticality,
            COALESCE(dt.downtime_hours, 0)    AS downtime_hours,
            COALESCE(dt.downtime_cost_eur, 0) AS downtime_cost_eur,
            COALESCE(dt.downtime_events, 0)   AS downtime_events,
            op.operating_hours,
            op.failure_count,
            -- ratio of sums, per machine
            CASE WHEN op.failure_count > 0
                 THEN op.operating_hours / op.failure_count END AS mtbf_hours
        FROM dim_machine m
        JOIN dim_plant p ON m.plant_id = p.plant_id
        LEFT JOIN dt ON dt.machine_sk = m.machine_sk
        LEFT JOIN op ON op.machine_sk = m.machine_sk
        WHERE 1 = 1 {_current_clause(f)}
        ORDER BY downtime_cost_eur DESC
        LIMIT {limit}
        """
    ).df()


def failure_rate_by_shift(con: duckdb.DuckDBPyConnection, f: Filters) -> pd.DataFrame:
    lo, hi = f.date_sk_range()
    return con.execute(
        f"""
        SELECT s.shift_name_de AS shift, p.plant_name AS plant,
               COUNT(*)        AS events
        FROM fact_downtime d
        JOIN dim_shift   s ON d.shift_sk   = s.shift_sk
        JOIN dim_plant   p ON d.plant_sk   = p.plant_sk
        JOIN dim_machine m ON d.machine_sk = m.machine_sk
        WHERE d.date_sk BETWEEN {lo} AND {hi}
          {_plant_clause(f)}{_shift_clause(f)}{_current_clause(f)}
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).df()


def machine_detail(
    con: duckdb.DuckDBPyConnection, f: Filters, machine_id: str
) -> dict[str, pd.DataFrame]:
    """Everything the drill-down page needs, in one call."""
    lo, hi = f.date_sk_range()
    mid = machine_id.replace("'", "''")

    attrs = con.execute(
        f"""SELECT machine_id, machine_name, plant_id, line_id, model,
                   machine_type, criticality, valid_from, valid_to, is_current
            FROM dim_machine WHERE machine_id = '{mid}' ORDER BY valid_from"""
    ).df()

    daily = con.execute(
        f"""SELECT dd.date, SUM(d.downtime_minutes)/60.0 AS downtime_hours
            FROM fact_downtime d
            JOIN dim_date dd ON d.date_sk = dd.date_sk
            JOIN dim_machine m ON d.machine_sk = m.machine_sk
            WHERE m.machine_id = '{mid}' AND d.date_sk BETWEEN {lo} AND {hi}
            GROUP BY 1 ORDER BY 1"""
    ).df()

    modes = con.execute(
        f"""SELECT ft.name_de AS failure_mode, COUNT(*) AS events,
                   SUM(d.downtime_minutes)/60.0 AS downtime_hours
            FROM fact_downtime d
            JOIN dim_failure_type ft ON d.failure_type_sk = ft.failure_type_sk
            JOIN dim_machine m ON d.machine_sk = m.machine_sk
            WHERE m.machine_id = '{mid}' AND d.date_sk BETWEEN {lo} AND {hi}
              AND ft.code <> 'NONE'
            GROUP BY 1 ORDER BY downtime_hours DESC"""
    ).df()

    orders = con.execute(
        f"""SELECT w.work_order_id, w.wo_type, w.priority, w.opened_at,
                   w.repair_minutes, w.parts_cost_eur
            FROM fact_work_order w
            JOIN dim_machine m ON w.machine_sk = m.machine_sk
            WHERE m.machine_id = '{mid}' AND w.date_sk BETWEEN {lo} AND {hi}
            ORDER BY w.opened_at DESC LIMIT 50"""
    ).df()

    return {"attributes": attrs, "daily": daily, "modes": modes, "work_orders": orders}


def filter_options(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    plants = con.execute("SELECT DISTINCT plant_name FROM dim_plant ORDER BY 1").df()
    shifts = con.execute("SELECT DISTINCT shift_name FROM dim_shift ORDER BY 1").df()
    dates = con.execute("SELECT MIN(date) a, MAX(date) b FROM dim_date").fetchone()
    return {
        "plants": plants["plant_name"].tolist(),
        "shifts": shifts["shift_name"].tolist(),
        "date_min": str(dates[0]),
        "date_max": str(dates[1]),
    }
