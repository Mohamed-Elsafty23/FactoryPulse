"""Measure the effect of date partitioning on a single-day query.

Run LOCALLY, not on Databricks: a cluster has autoscaling, caching layers and
shared infrastructure — all variance you cannot control or explain. A local run
is clean, repeatable, free, and shows the identical mechanism.
"""

import time

from pyspark.sql import functions as F

from factorypulse.config import settings
from factorypulse.spark import get_spark

TARGET_DATE = "2025-11-15"
RUNS = 5


def timed(fn, runs: int = RUNS) -> tuple[float, float]:
    """Discard a warm-up run, then time `runs` iterations. Returns (mean, best)."""
    fn()  # warm JIT and filesystem caches — including it would measure startup
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return sum(times) / len(times), min(times)


def main() -> None:
    spark = get_spark("benchmark", shuffle_partitions=8)

    partitioned = settings.silver_path("telemetry")
    unpartitioned = f"{settings.silver_path('telemetry')}_nopart"

    try:
        spark.read.format("delta").load(unpartitioned).limit(1).count()
    except Exception:
        print("building unpartitioned control table (one-off)...")
        (
            spark.read.format("delta")
            .load(partitioned)
            .write.format("delta")
            .mode("overwrite")
            .save(unpartitioned)
        )

    def q(path):
        def inner():
            return (
                spark.read.format("delta")
                .load(path)
                .filter(F.col("event_date") == TARGET_DATE)
                .agg(F.avg("torque_nm"), F.count("*"))
                .collect()
            )

        return inner

    print(f"\nquery: one day ({TARGET_DATE}) out of ~365, {RUNS} timed runs each\n")

    mean_n, best_n = timed(q(unpartitioned))
    mean_p, best_p = timed(q(partitioned))

    print(f"  unpartitioned : mean {mean_n:6.3f}s   best {best_n:6.3f}s")
    print(f"  partitioned   : mean {mean_p:6.3f}s   best {best_p:6.3f}s")
    print(f"  SPEED-UP      : {mean_n / mean_p:5.2f}x\n")

    # Show WHY, not just that it is faster. A benchmark without a mechanism is
    # an anecdote.
    print("--- partitioned physical plan (look for PartitionFilters) ---")
    (
        spark.read.format("delta")
        .load(partitioned)
        .filter(F.col("event_date") == TARGET_DATE)
        .explain(mode="simple")
    )

    for name, path in (("partitioned", partitioned), ("unpartitioned", unpartitioned)):
        d = spark.sql(f"DESCRIBE DETAIL delta.`{path}`").select("numFiles", "sizeInBytes").first()
        print(f"  {name:<14s} files={d['numFiles']:>5}  bytes={d['sizeInBytes']:,}")

    spark.stop()


if __name__ == "__main__":
    main()
