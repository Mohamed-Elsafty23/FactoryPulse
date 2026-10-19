# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
from factorypulse.pipeline.dimensions import (
    build_dim_date,
    build_dim_failure_type,
    build_dim_plant,
    build_dim_shift,
)
from factorypulse.pipeline.gold import (
    build_agg_machine_daily,
    build_fact_downtime,
    build_fact_machine_event,
    build_fact_work_order,
)
from factorypulse.utils.ops import tracked_run

with tracked_run(spark, "gold", cfg) as ctx:
    dimensions = {
        "dim_date": build_dim_date(spark, "2025-10-01", "2026-12-31"),
        "dim_shift": build_dim_shift(spark),
        "dim_plant": build_dim_plant(spark, cfg),
        "dim_failure_type": build_dim_failure_type(spark),
    }
    for name, frame in dimensions.items():
        frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(
            cfg.gold_path(name)
        )
        print(name)

    print("fact_machine_event", build_fact_machine_event(spark, ctx, cfg))
    print("fact_downtime", build_fact_downtime(spark, ctx, cfg))
    print("fact_work_order", build_fact_work_order(spark, ctx, cfg))
    print("agg_machine_daily", build_agg_machine_daily(spark, ctx, cfg))
