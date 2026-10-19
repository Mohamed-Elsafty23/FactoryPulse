# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
# The dashboard reads a committed Parquet snapshot, not the warehouse, so it
# keeps working after Phase 16 deletes the Azure estate. Same decision as
# Power BI Import mode, but the materialised artifact is readable in git.
tables = [
    "gold.dim_machine",
    "gold.dim_date",
    "gold.dim_plant",
    "gold.dim_shift",
    "gold.dim_failure_type",
    "gold.fact_downtime",
    "gold.fact_work_order",
    "gold.agg_machine_daily",
    "ops.pipeline_runs",
]

for table in tables:
    out = f"{cfg._root}/exports/{table.replace('.', '_')}"
    frame = spark.table(f"{cfg.catalog}.{table}")
    # coalesce(1): one file per table — trivial for DuckDB, small in git.
    frame.coalesce(1).write.mode("overwrite").parquet(out)
    print(f"{table:<30s} {frame.count():>10,} rows -> {out}")
