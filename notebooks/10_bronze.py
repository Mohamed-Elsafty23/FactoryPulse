# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
from factorypulse.pipeline.bronze import build_bronze_reference, build_bronze_telemetry
from factorypulse.utils.ops import tracked_run

with tracked_run(spark, "bronze", cfg) as ctx:
    print(f"bronze.telemetry={build_bronze_telemetry(spark, ctx, cfg):,}")
    print(build_bronze_reference(spark, ctx, cfg))
