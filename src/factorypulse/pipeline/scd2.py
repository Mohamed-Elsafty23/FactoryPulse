"""SCD Type 2 maintenance for the machine dimension via Delta MERGE."""

from __future__ import annotations

from datetime import datetime

from delta.tables import DeltaTable
from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from factorypulse.config import Settings, settings

# Changes to these attributes create a new historical version (Type 2).
TRACKED = ["plant_id", "line_id", "model", "machine_type", "criticality", "is_active"]

# Changes to these attributes are overwritten on the current version (Type 1).
UNTRACKED = ["machine_name", "ideal_cycle_seconds", "installed_date"]

FAR_FUTURE = "9999-12-31 00:00:00"

# The first version of a machine is anchored here rather than at its
# `updated_at`. A full extract captures CURRENT state, so `updated_at` says
# when the row last changed -- not when the attributes we can see began. The
# values before that point are unknown and unknowable from this source, so the
# earliest version has to absorb them: anything later leaves facts older than
# the first change with no dimension row to join to, and they vanish from Gold.
FAR_PAST = "1900-01-01 00:00:00"


def attribute_hash(cols: list[str]) -> Column:
    """Return a NULL-safe hash of the supplied attributes."""
    return F.xxhash64(
        F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("<NULL>")) for c in cols])
    )


def surrogate_key() -> Column:
    """Return a deterministic key for a natural key and version start."""
    return F.abs(
        F.xxhash64(F.concat_ws("||", F.col("machine_id"), F.col("valid_from").cast("string")))
    )


def _effective_from(src: DataFrame, fallback: datetime) -> Column:
    """When a version became true in the SOURCE, not when we loaded it.

    `ops.machines.updated_at` is stamped by the source system at the moment the
    row changed, so it is the only correct basis for a Type 2 validity
    interval. Using load time instead silently breaks every point-in-time join:
    facts older than the first load fall before `valid_from` and match no
    dimension row at all.

    The fallback keeps callers that supply a bare attribute snapshot (the unit
    tests, and any source with no change timestamp) working unchanged.
    """
    if "updated_at" in src.columns:
        return F.coalesce(F.col("updated_at").cast("timestamp"), F.lit(fallback).cast("timestamp"))
    return F.lit(fallback).cast("timestamp")


def _prepare_source(src: DataFrame, effective_from: datetime) -> DataFrame:
    """Select and decorate an incoming machine snapshot."""
    return (
        src.select("machine_id", *TRACKED, *UNTRACKED, *_optional(src, ["updated_at"]))
        .withColumn("attr_hash", attribute_hash(TRACKED))
        .withColumn("valid_from", _effective_from(src, effective_from))
        .withColumn("valid_to", F.lit(FAR_FUTURE).cast("timestamp"))
        .withColumn("is_current", F.lit(True))
        .drop(*_optional(src, ["updated_at"]))
    )


def _optional(src: DataFrame, cols: list[str]) -> list[str]:
    """Those of `cols` the source actually has."""
    return [c for c in cols if c in src.columns]


def _latest_per_machine(prepared: DataFrame) -> DataFrame:
    """Keep only each machine's newest version — the current-state snapshot.

    `merge_dim_machine` compares incoming rows against the one open row per
    machine, so feeding it a multi-version history would fan the join out.
    """
    newest = Window.partitionBy("machine_id").orderBy(F.col("valid_from").desc())
    return prepared.withColumn("_rn", F.row_number().over(newest)).filter("_rn = 1").drop("_rn")


def initialise_dim_machine(
    spark: SparkSession,
    src: DataFrame,
    effective_from: datetime,
    cfg: Settings | None = None,
) -> int:
    """Build the dimension from a machine snapshot, history included.

    The source may carry SEVERAL rows for one machine — an initial full extract
    plus later incremental ones, each with its own `updated_at`. Treating them
    all as current would leave a machine with two open versions and no valid
    point-in-time join. So versions are chained here: ordered by `valid_from`,
    each one closed at the next one's start, and only the newest left open.
    """
    del spark  # Kept in the public API for symmetry with merge_dim_machine.
    cfg = cfg or settings
    prepared = _prepare_source(src, effective_from)

    # Consecutive rows with identical tracked attributes are the SAME version
    # re-extracted, not a change — collapsing them avoids spurious versions.
    by_time = Window.partitionBy("machine_id").orderBy("valid_from")
    deduped = (
        prepared.withColumn("_prev_hash", F.lag("attr_hash").over(by_time))
        .filter(F.col("_prev_hash").isNull() | (F.col("_prev_hash") != F.col("attr_hash")))
        .drop("_prev_hash")
    )

    anchored = deduped.withColumn(
        "valid_from",
        F.when(F.row_number().over(by_time) == 1, F.lit(FAR_PAST).cast("timestamp")).otherwise(
            F.col("valid_from")
        ),
    )

    chained = (
        anchored.withColumn("_next_from", F.lead("valid_from").over(by_time))
        .withColumn(
            "valid_to",
            F.coalesce(F.col("_next_from"), F.lit(FAR_FUTURE).cast("timestamp")),
        )
        .withColumn("is_current", F.col("_next_from").isNull())
        .drop("_next_from")
    )

    dim = chained.withColumn("machine_sk", surrogate_key())
    output = dim.select(
        "machine_sk",
        "machine_id",
        *TRACKED,
        *UNTRACKED,
        "attr_hash",
        "valid_from",
        "valid_to",
        "is_current",
    )
    row_count = output.count()
    (
        output.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(cfg.gold_path("dim_machine"))
    )
    return row_count


def merge_dim_machine(
    spark: SparkSession,
    src: DataFrame,
    effective_from: datetime,
    cfg: Settings | None = None,
) -> dict[str, int]:
    """Close changed versions, insert successors, and update Type 1 fields."""
    cfg = cfg or settings
    path = cfg.gold_path("dim_machine")
    if not DeltaTable.isDeltaTable(spark, path):
        return {"initialised": initialise_dim_machine(spark, src, effective_from, cfg)}

    dim = DeltaTable.forPath(spark, path)
    # Merge compares against the single open row per machine, so collapse any
    # multi-version source down to current state first.
    incoming = _latest_per_machine(_prepare_source(src, effective_from))
    current = dim.toDF().filter(F.col("is_current"))
    joined = incoming.alias("s").join(
        current.select(
            F.col("machine_id").alias("t_machine_id"),
            F.col("attr_hash").alias("t_attr_hash"),
        ),
        F.col("s.machine_id") == F.col("t_machine_id"),
        "left",
    )

    changed = joined.filter(
        F.col("t_machine_id").isNotNull() & (F.col("s.attr_hash") != F.col("t_attr_hash"))
    ).select("s.*")
    unchanged = joined.filter(
        F.col("t_machine_id").isNotNull() & (F.col("s.attr_hash") == F.col("t_attr_hash"))
    ).select("s.*")
    brand_new = joined.filter(F.col("t_machine_id").isNull()).select("s.*")

    n_changed = changed.count()
    n_new = brand_new.count()
    n_unchanged = unchanged.count()

    # Existing rows match on their natural key. Changed rows close the current
    # version; unchanged rows allow Type 1 attributes to be refreshed in place.
    matched_rows = changed.unionByName(unchanged).withColumn("mergeKey", F.col("machine_id"))
    # NULL never equals a target key, so these rows always take the insert path.
    insert_rows = changed.unionByName(brand_new).withColumn("mergeKey", F.lit(None).cast("string"))
    staged = matched_rows.unionByName(insert_rows).withColumn("machine_sk", surrogate_key())

    (
        dim.alias("t")
        .merge(staged.alias("s"), "t.machine_id = s.mergeKey AND t.is_current = true")
        .whenMatchedUpdate(
            condition="t.attr_hash <> s.attr_hash",
            set={"valid_to": "s.valid_from", "is_current": F.lit(False)},
        )
        .whenMatchedUpdate(
            condition="t.attr_hash = s.attr_hash",
            set={c: f"s.{c}" for c in UNTRACKED},
        )
        .whenNotMatchedInsert(
            values={
                "machine_sk": "s.machine_sk",
                "machine_id": "s.machine_id",
                **{c: f"s.{c}" for c in TRACKED},
                **{c: f"s.{c}" for c in UNTRACKED},
                "attr_hash": "s.attr_hash",
                "valid_from": "s.valid_from",
                "valid_to": "s.valid_to",
                "is_current": "s.is_current",
            }
        )
        .execute()
    )
    return {"changed": n_changed, "new": n_new, "unchanged": n_unchanged}
