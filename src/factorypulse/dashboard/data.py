"""DuckDB connection over the exported Gold Parquet files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import duckdb

# export directory name -> view name used in SQL
VIEWS = {
    "gold_dim_machine": "dim_machine",
    "gold_dim_date": "dim_date",
    "gold_dim_plant": "dim_plant",
    "gold_dim_shift": "dim_shift",
    "gold_dim_failure_type": "dim_failure_type",
    "gold_fact_downtime": "fact_downtime",
    "gold_fact_work_order": "fact_work_order",
    "gold_agg_machine_daily": "agg_machine_daily",
    "ops_pipeline_runs": "pipeline_runs",
}


def default_export_dir() -> Path:
    """Repo-relative, so the app works from any working directory."""
    return Path(__file__).resolve().parents[3] / "exports"


def connect(export_dir: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with a view per exported table.

    DuckDB reads the Parquet without loading it: a WHERE clause is pushed down
    and only the needed row groups are touched.
    """
    export_dir = Path(export_dir) if export_dir else default_export_dir()
    con = duckdb.connect(database=":memory:")

    missing = []
    for folder, view in VIEWS.items():
        path = export_dir / folder
        if not path.exists():
            missing.append(folder)
            continue
        con.execute(
            f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{path}/*.parquet')"
        )

    if missing:
        raise FileNotFoundError(
            f"Missing exports in {export_dir}: {missing}. "
            "Run notebooks/98_export_for_dashboard.py and download with "
            "scripts/fetch-exports.sh (see docs/build/15_dashboard.md step 15.2)."
        )
    return con


@lru_cache(maxsize=1)
def cached_connection(export_dir: str | None = None) -> duckdb.DuckDBPyConnection:
    """One connection per process — Streamlit reruns the script on every interaction."""
    return connect(export_dir)
