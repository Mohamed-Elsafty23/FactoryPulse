# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
spark.sql(f"USE CATALOG {cfg.catalog}")

tables = {
    "bronze.telemetry": cfg.bronze_path("telemetry"),
    "bronze.machines": cfg.bronze_path("machines"),
    "bronze.plants": cfg.bronze_path("plants"),
    "bronze.work_orders": cfg.bronze_path("work_orders"),
    "bronze.production_orders": cfg.bronze_path("production_orders"),
    "silver.telemetry": cfg.silver_path("telemetry"),
    "silver.work_orders": cfg.silver_path("work_orders"),
    "silver.production_orders": cfg.silver_path("production_orders"),
    "silver.plants": cfg.silver_path("plants"),
    "gold.dim_machine": cfg.gold_path("dim_machine"),
    "gold.dim_date": cfg.gold_path("dim_date"),
    "gold.dim_plant": cfg.gold_path("dim_plant"),
    "gold.dim_shift": cfg.gold_path("dim_shift"),
    "gold.dim_failure_type": cfg.gold_path("dim_failure_type"),
    "gold.fact_machine_event": cfg.gold_path("fact_machine_event"),
    "gold.fact_downtime": cfg.gold_path("fact_downtime"),
    "gold.fact_work_order": cfg.gold_path("fact_work_order"),
    "gold.agg_machine_daily": cfg.gold_path("agg_machine_daily"),
    "quarantine.telemetry": cfg.quarantine_path("telemetry"),
    "ops.pipeline_runs": cfg.ops_path,
}

for name, path in tables.items():
    spark.sql(f"CREATE TABLE IF NOT EXISTS {name} USING DELTA LOCATION '{path}'")
    print(f"{name}: {spark.table(name).count():,}")
