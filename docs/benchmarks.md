# Benchmarks

Every number here was measured, not estimated. Where a result is weaker than
the textbook expectation, the measured value is reported and explained rather
than rounded up.

---

## Partition pruning

Query: average torque for one day out of ~348, over 9.9M Silver rows.
Hardware: Intel Core i5-10300H (8 threads), 15 GB RAM, local Spark 3.5.1 over
MinIO, 8 shuffle partitions.
Method: 1 warm-up run discarded, then 5 timed runs (`scripts/benchmark_partitioning.py`).

| Layout | Mean | Best | Files |
|---|--:|--:|--:|
| Unpartitioned | 0.734 s | 0.675 s | 12 |
| Partitioned by `event_date` | 0.524 s | 0.470 s | 348 |

**Speed-up: 1.40×**

**Mechanism:** the physical plan carries

```
PartitionFilters: [isnotnull(event_date#5061), (event_date#5061 = 2025-11-15)]
```

so Spark eliminates 347 of 348 partition directories at *planning* time,
before reading a byte. This is **partition pruning**, which is distinct from
predicate pushdown — pushdown filters *within* files using column statistics,
pruning skips the files entirely.

### Why only 1.4× and not 10×+

The mechanism works; the *margin* is small, and the reason is worth stating:

- **The control table is already well organised.** The unpartitioned copy is
  12 large Parquet files (152 MB). Spark still reads only the row groups whose
  statistics can match, so predicate pushdown recovers much of what pruning
  would have won.
- **Partitioning costs file-count overhead.** The partitioned table is 348
  files for the same data — one per day. Per-file open and footer-read costs
  partly offset the saving at this scale.
- **The dataset is small.** At 152 MB the whole table fits comfortably in page
  cache, so the I/O that pruning avoids is cheap to begin with.

Partition pruning pays off far more as the table grows, as the partition
count-to-file-size ratio improves, and on remote storage where a skipped file
is a skipped network round-trip. **At 10M rows it is a real but modest win** —
which is the honest result, and a more useful thing to be able to discuss than
a large number with no mechanism behind it.

---

## Pipeline runtime (Azure)

Databricks **serverless** compute, job `factorypulse-medallion`, one end-to-end
run over ~9.9M Silver rows.

| Task | Wall clock | Compute setup |
|---|--:|--:|
| bronze | 2 m 00 s | 4 s |
| silver | 1 m 20 s | 2 s |
| scd2 | 1 m 13 s | 2 s |
| gold | 1 m 16 s | 2 s |
| quality | 0 m 44 s | 2 s |
| **Total (DAG wall clock)** | **6 m 37 s** | |

Serverless start-up is 2–4 s per task, against the 4–6 minutes a classic
all-purpose cluster takes to come up. That is the single largest reason the
whole phase stayed inside a few dollars.

---

## Row counts

Measured from the registered Unity Catalog tables after a green run.

| Table | Rows |
|---|--:|
| `bronze.telemetry` | 10,049,501 |
| `silver.telemetry` | 9,896,841 |
| `gold.fact_machine_event` | 9,896,841 |
| `gold.fact_downtime` | 100,228 |
| `gold.fact_work_order` | 2,256 |
| `gold.agg_machine_daily` | 6,960 |
| `gold.dim_machine` (SCD2) | 21 versions / 20 machines |
| `gold.dim_date` / `dim_plant` / `dim_shift` / `dim_failure_type` | 457 / 2 / 3 / 6 |
| `quarantine.telemetry` | 310,944 (append-only, across runs) |

**Silver and Gold match exactly** (9,896,841 = 9,896,841). That equality is
data-quality check 07 and the fastest detector of a point-in-time join that
fans out or drops rows — both of which corrupt every measure silently.

Bronze minus Silver = 152,660 rows removed in the run, as rejects (quarantined
with a reason) plus deterministic de-duplication.
