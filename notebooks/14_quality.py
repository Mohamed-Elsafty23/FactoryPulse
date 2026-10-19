# Databricks notebook source
# MAGIC %run ./_bootstrap

# COMMAND ----------
from factorypulse.quality.checks import run_all
from factorypulse.utils.ops import tracked_run

with tracked_run(spark, "quality", cfg):
    results = run_all(spark, cfg)
    for check in results:
        print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    failed = [check for check in results if not check.passed]
    if failed:
        raise RuntimeError(f"{len(failed)} data-quality checks failed")
