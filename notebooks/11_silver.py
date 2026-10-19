# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
from factorypulse.pipeline.silver import build_silver_reference, build_silver_telemetry
from factorypulse.utils.ops import tracked_run

with tracked_run(spark, "silver", cfg) as ctx:
    print(build_silver_telemetry(spark, ctx, cfg))
    print(build_silver_reference(spark, ctx, cfg))
