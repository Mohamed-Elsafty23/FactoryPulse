"""Deliberately corrupt a fraction of rows so quality gates have work to do."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

SEED_PICK, SEED_KIND, SEED_DUPLICATE = 201, 202, 203


def inject_defects(df: DataFrame, rate: float = 0.01) -> DataFrame:
    """Corrupt approximately ``rate`` of rows and append deterministic duplicates."""
    if rate <= 0:
        return df

    marked = df.withColumn("_pick", F.rand(SEED_PICK)).withColumn(
        "_kind",
        F.when(F.col("_pick") >= rate, F.lit("clean")).otherwise(
            F.when(F.rand(SEED_KIND) < 0.34, F.lit("range"))
            .when(F.rand(SEED_KIND) < 0.67, F.lit("orphan"))
            .otherwise(F.lit("missing"))
        ),
    )

    corrupted = (
        marked.withColumn(
            "torque_nm",
            F.when(F.col("_kind") == "range", F.col("torque_nm") * 10).otherwise(
                F.col("torque_nm")
            ),
        )
        .withColumn(
            "air_temp_k",
            F.when(F.col("_kind") == "range", F.col("air_temp_k") + 500).otherwise(
                F.col("air_temp_k")
            ),
        )
        .withColumn(
            "machine_id",
            F.when(F.col("_kind") == "orphan", F.lit("MC-99")).otherwise(F.col("machine_id")),
        )
        .withColumn(
            "event_time",
            F.when(F.col("_kind") == "missing", F.lit(None).cast("timestamp")).otherwise(
                F.col("event_time")
            ),
        )
        .withColumn(
            "machine_id",
            F.when(F.col("_kind") == "missing", F.lit(None).cast("string")).otherwise(
                F.col("machine_id")
            ),
        )
        .drop("_pick", "_kind")
    )

    # Use an independent seed. Reusing SEED_PICK correlates this sample with
    # the corrupted slice and makes nearly every duplicate invalid as well.
    duplicates = corrupted.sample(withReplacement=False, fraction=rate / 2, seed=SEED_DUPLICATE)
    return corrupted.unionByName(duplicates)
