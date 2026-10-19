# Databricks notebook source
import os

dbutils.widgets.text("env", "azure_dev")
os.environ["ENV"] = dbutils.widgets.get("env")
os.environ["ADLS_ACCOUNT"] = dbutils.secrets.get("factorypulse", "adls-account-name")

from factorypulse.config import get_settings

get_settings.cache_clear()
cfg = get_settings()
spark.conf.set("spark.sql.session.timeZone", "UTC")

# spark.sql.sources.partitionOverwriteMode is deliberately NOT set here.
# Serverless compute rejects it (CONFIG_NOT_AVAILABLE), and the pipeline now
# sets the mode as an explicit per-write option instead, so overwrite
# semantics no longer depend on ambient session configuration.

assert cfg.bronze_path("telemetry").startswith("abfss://")
print(f"environment={cfg.env} catalog={cfg.catalog} root={cfg._root}")
