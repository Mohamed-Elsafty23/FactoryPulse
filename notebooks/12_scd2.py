# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
from datetime import datetime, timezone

from factorypulse.pipeline.scd2 import initialise_dim_machine, merge_dim_machine
from factorypulse.utils.ops import tracked_run

# bronze.machines accumulates the full ADF extract history, and each row
# carries the source `updated_at` that dates its version — so rebuilding from
# it reproduces the whole dimension deterministically. Set rebuild=true to
# repair a dimension whose versions were built wrong; the default incremental
# path exercises the Delta MERGE.
dbutils.widgets.dropdown("rebuild", "false", ["false", "true"])
rebuild = dbutils.widgets.get("rebuild") == "true"

with tracked_run(spark, "scd2_dim_machine", cfg) as ctx:
    machines = spark.read.format("delta").load(cfg.bronze_path("machines"))
    ctx.rows_read = machines.count()

    # Only a fallback: valid_from comes from each row's updated_at.
    loaded_at = datetime.now(timezone.utc)

    if rebuild:
        rows = initialise_dim_machine(spark, machines, loaded_at, cfg)
        stats = {"rebuilt": rows}
    else:
        stats = merge_dim_machine(spark, machines, loaded_at, cfg)

    ctx.rows_written = sum(v for v in stats.values() if isinstance(v, int))
    print(stats)
