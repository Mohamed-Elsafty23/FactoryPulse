"""Read the operational source system into Spark."""

from __future__ import annotations

import re

from pyspark.sql import DataFrame, SparkSession

from factorypulse.config import Settings, settings

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_WATERMARK = re.compile(r"^[0-9T:+. Z-]+$")


def read_table(
    spark: SparkSession,
    table: str,
    cfg: Settings | None = None,
    since: str | None = None,
    watermark_column: str = "updated_at",
) -> DataFrame:
    """Read a source table, optionally only rows changed since a watermark."""
    cfg = cfg or settings
    if not _IDENTIFIER.fullmatch(table) or not _IDENTIFIER.fullmatch(watermark_column):
        raise ValueError("table and watermark_column must be SQL identifiers")

    query = f"SELECT * FROM {table}"
    if since:
        if not _WATERMARK.fullmatch(since):
            raise ValueError("since must be an ISO timestamp")
        query += f" WHERE {watermark_column} > '{since}'"

    return (
        spark.read.format("jdbc")
        .option("url", cfg.jdbc_url)
        .option("dbtable", f"({query}) AS source_rows")
        .options(**cfg.jdbc_properties)
        .load()
    )
