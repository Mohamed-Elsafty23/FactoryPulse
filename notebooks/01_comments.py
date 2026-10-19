# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
from factorypulse.pipeline.gold import GRAIN_COMMENTS

spark.sql(f"USE CATALOG {cfg.catalog}")

table_comments = {
    **{f"gold.{name}": comment for name, comment in GRAIN_COMMENTS.items()},
    "bronze.telemetry": "Raw telemetry as received from ADF, plus ingestion lineage columns.",
    "bronze.machines": "Raw machine snapshots ingested through ADF.",
    "bronze.plants": "Raw plant reference snapshots ingested through ADF.",
    "bronze.work_orders": "Raw maintenance work orders ingested through ADF.",
    "bronze.production_orders": "Raw production orders ingested through ADF.",
    "silver.telemetry": "Validated, deduplicated telemetry; one row per event_id.",
    "silver.work_orders": "Clean work orders with derived duration measures.",
    "silver.production_orders": "Clean production orders with runtime and quality measures.",
    "silver.plants": "Validated plant reference data.",
    "quarantine.telemetry": "Telemetry rejected by Silver validation, with reject_reason.",
    "ops.pipeline_runs": "One row per tracked pipeline execution, including failures.",
}

for table, comment in table_comments.items():
    escaped = comment.replace("'", "''")
    spark.sql(f"COMMENT ON TABLE {table} IS '{escaped}'")

# Every Gold column receives a catalog-local description. Domain-specific
# descriptions override the safe generated fallback.
column_comments = {
    "machine_sk": "Version-specific surrogate key for dim_machine.",
    "machine_id": "Stable machine business key; do not join facts to SCD2 on this column.",
    "date_sk": "Calendar key in yyyyMMdd integer format.",
    "tool_wear_min": "Cumulative tool wear in minutes; semi-additive, use MAX rather than SUM.",
    "downtime_minutes": "Downtime duration in minutes; additive across dimensions.",
    "downtime_cost_eur": "Downtime cost in EUR using the documented hourly assumption.",
    "valid_from": "Inclusive start of this SCD2 version.",
    "valid_to": "Exclusive end of this SCD2 version; current rows use 9999-12-31.",
    "is_current": "True for exactly one version of each machine_id.",
    "availability": "Non-additive ratio; recompute from additive components when aggregating.",
}

for table in GRAIN_COMMENTS:
    for column in spark.table(f"gold.{table}").columns:
        comment = column_comments.get(column, f"FactoryPulse {column.replace('_', ' ')} attribute.")
        escaped = comment.replace("'", "''")
        spark.sql(f"ALTER TABLE gold.{table} ALTER COLUMN `{column}` COMMENT '{escaped}'")

print(f"Applied comments to {len(table_comments)} tables and every Gold column.")
