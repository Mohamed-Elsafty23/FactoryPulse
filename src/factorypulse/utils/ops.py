"""The ops table: one row per pipeline run, written on success and failure."""

from __future__ import annotations

import subprocess
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from factorypulse.config import Settings, settings
from factorypulse.utils.run_context import RunContext

OPS_SCHEMA = StructType(
    [
        StructField("pipeline", StringType(), False),
        StructField("run_id", StringType(), False),
        StructField("environment", StringType(), True),
        StructField("git_sha", StringType(), True),
        StructField("started_at", TimestampType(), False),
        StructField("finished_at", TimestampType(), True),
        StructField("duration_s", DoubleType(), True),
        StructField("status", StringType(), False),
        StructField("rows_read", LongType(), True),
        StructField("rows_written", LongType(), True),
        StructField("rows_rejected", LongType(), True),
        StructField("freshness_s", DoubleType(), True),
        StructField("error_message", StringType(), True),
    ]
)


def _git_sha() -> str:
    """Return the running revision without making ops logging depend on Git."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def compute_freshness(spark: SparkSession, cfg: Settings | None = None) -> float | None:
    """Return seconds since the newest Gold event time, or None when unavailable."""
    cfg = cfg or settings
    try:
        newest = (
            spark.read.format("delta")
            .load(cfg.gold_path("fact_machine_event"))
            .agg(F.max("event_time").alias("newest"))
            .first()["newest"]
        )
        if newest is None:
            return None
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - newest).total_seconds()
    except Exception:
        # Freshness must not prevent recording the pipeline outcome, including
        # early stages where Gold does not exist yet.
        return None


def write_ops_row(
    spark: SparkSession,
    ctx: RunContext,
    status: str,
    error: str | None = None,
    cfg: Settings | None = None,
) -> None:
    """Append an immutable pipeline-run record to the Delta ops table."""
    cfg = cfg or settings
    finished = datetime.now(timezone.utc)
    row = [
        (
            ctx.pipeline,
            ctx.run_id,
            cfg.env.value,
            _git_sha(),
            ctx.started_at,
            finished,
            (finished - ctx.started_at).total_seconds(),
            status,
            int(ctx.rows_read),
            int(ctx.rows_written),
            int(ctx.rows_rejected),
            compute_freshness(spark, cfg),
            error,
        )
    ]
    (
        spark.createDataFrame(row, OPS_SCHEMA)
        .write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .save(cfg.ops_path)
    )


@contextmanager
def tracked_run(
    spark: SparkSession, pipeline: str, cfg: Settings | None = None
) -> Iterator[RunContext]:
    """Yield a run context and persist its success or failure before returning."""
    ctx = RunContext(pipeline=pipeline)
    print(f"\n  >>> {ctx} starting")
    try:
        yield ctx
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"
        write_ops_row(spark, ctx, "failed", error=error, cfg=cfg)
        print(f"  <<< {ctx} FAILED: {type(exc).__name__}: {exc}")
        raise
    else:
        write_ops_row(spark, ctx, "success", cfg=cfg)
        duration = (datetime.now(timezone.utc) - ctx.started_at).total_seconds()
        print(
            f"  <<< {ctx} ok  read={ctx.rows_read:,} written={ctx.rows_written:,} "
            f"rejected={ctx.rows_rejected:,} in {duration:.1f}s"
        )
