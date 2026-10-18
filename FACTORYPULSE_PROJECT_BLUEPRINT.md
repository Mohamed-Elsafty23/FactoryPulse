# FactoryPulse — Manufacturing Reliability Lakehouse on Azure

End-to-end portfolio project. ~70 hours over 8 weeks.
Public dataset (AI4I 2020) + simulated operational data. Manufacturing domain.

---

## 1. Stack

| Tool | Used for |
|---|---|
| **Azure SQL Database** | Operational source system — machines, work orders, production orders. T-SQL schema, stored procedures, change tracking. |
| **Azure Data Factory** | Metadata-driven incremental ingestion. Control table, watermarks, parameterised pipelines, backfill. |
| **ADLS Gen2** | Landing zone, quarantine, Delta storage. |
| **Azure Databricks** | Bronze / Silver / Gold transformations, Workflows orchestration. |
| **PySpark + Spark SQL** | All transformation logic. |
| **Delta Lake** | Table format — MERGE, schema evolution, time travel, OPTIMIZE. |
| **Unity Catalog** | Catalogs, schemas, grants, column comments, lineage. |
| **Azure Key Vault** | Secrets, via Databricks secret scope. |
| **Azure Monitor** | Pipeline failure and data staleness alerts. |
| **Power BI** | 2-page decision dashboard on the Gold star schema. |
| **Python** | Simulator, transformation modules, tests. |
| **Docker Compose** | Local build environment (Postgres, MinIO, Spark). |
| **GitHub Actions** | Lint + unit tests. |
| **Git / GitHub Projects** | Version control, 8 sprints, issues. |

---

## 2. Architecture

```text
Faker generator ──> Azure SQL Database ──┐
  machines, work orders,                 │
  production orders                      ├──> Azure Data Factory ──> ADLS Gen2
                                         │      (incremental,           │
Telemetry simulator ──> Parquet ─────────┘       watermark-based)       │
  (~10M rows from AI4I)                                                 │
                                                                        v
                                                              Azure Databricks
                                                              Bronze ─> Silver ─> Gold
                                                                        │
                                                       Unity Catalog governs all
                                                                        │
                                                              Power BI (2 pages)
                                                              ops table + Azure Monitor alerts
```

Weeks 1–3 run locally on Docker Compose — PostgreSQL stands in for Azure SQL, MinIO for ADLS, local Spark + Delta. Same PySpark code; only paths and catalog change. Azure opens in week 4.

---

## 3. Data

**AI4I 2020 Predictive Maintenance (UCI)** — 10,000 rows, 5 failure modes (TWF, HDF, PWF, OSF, RNF). Supplies sensor distributions and the failure taxonomy.

**Telemetry simulator (PySpark)** — expands AI4I into **~10M timestamped readings**: 20 machines, 2 plants, 3 shifts, 12 months.

```
event_id, machine_id, event_time, air_temp_k, process_temp_k,
rotational_speed_rpm, torque_nm, tool_wear_min, failure_type
```

Injected defects at a configurable rate: duplicates, out-of-range sensor values, orphan `machine_id`, missing fields.

**Reference data (Faker → Azure SQL)** — machine master with change events to drive SCD2, maintenance work orders, production orders.

---

## 4. Data model

| Table | Grain | Rows |
|---|---|--:|
| `fact_machine_event` | one sensor reading per machine per timestamp | ~10 M |
| `fact_downtime` | one downtime interval per machine per start time | ~10 K |
| `dim_machine` | **SCD Type 2** — plant, line, model, criticality | ~20 current |
| `dim_plant` | plant, country, timezone | 2 |
| `dim_shift` | early / late / night | 3 |
| `dim_date` | full date hierarchy | — |

Grain written as a table comment on each fact.

---

## 5. KPIs

Defined in `docs/kpi_dictionary.md` — formula, owner, refresh frequency, German term.

- **MTBF** (*Mittlere Betriebsdauer zwischen Ausfällen*), **MTTR** (*Mittlere Reparaturdauer*)
- **Downtime hours** (*Stillstandzeit*) and downtime cost — €/hour assumption stated in the dictionary, not buried in DAX
- **Failure rate** by machine, plant, shift, failure mode
- **Preventive vs. corrective maintenance ratio**
- **Platform KPIs** — data freshness, rejected-record %, pipeline success rate

OEE only if the simulated data supports Availability × Performance × Quality. Otherwise state in the README that it was deliberately not computed.

---

## 6. Pipeline

**Ingestion (ADF)** — control table holds source table, watermark column, target path. One parameterised pipeline, not one per table. Incremental loads plus re-runnable backfill by date range.

**Bronze** — raw, immutable, ingestion timestamp and source column. No business logic.

**Silver** — parse and standardise, deduplicate, validate ranges and keys, reject bad rows to a quarantine table with the reason, build SCD Type 2 machine history.

**Gold** — star schema plus aggregates sized for Power BI.

Orchestrated with **Databricks Workflows**. Transformation logic lives in `src/` as importable Python modules; notebooks are thin wrappers.

---

## 7. Quality

10 automated tests:

1. `event_id` uniqueness
2. `machine_id` foreign-key integrity
3. Sensor values within physical ranges
4. No negative durations
5. `failure_type` in accepted enum
6. No duplicates after dedup
7. Silver → Gold row reconciliation
8. SCD2 — no overlapping intervals
9. SCD2 — exactly one current row per machine
10. Idempotency — rerunning a batch leaves Gold row counts unchanged

**One deliberate failure** — break the pipeline on purpose (schema change, or kill a run mid-write), alert, recover, write it up in `docs/runbook.md`.

---

## 8. Governance and monitoring

**Unity Catalog** — `dev` and `prod` schemas, grants for engineer / analyst / plant-manager personas, comments on every table and Gold column, lineage captured before teardown.

**Key Vault** — all secrets, via Databricks secret scope. Nothing committed.

**`ops` table**, written by every run:

```
pipeline, run_id, started_at, finished_at, status,
rows_read, rows_written, rows_rejected, freshness_s
```

**Azure Monitor** — two alerts: pipeline failed, data stale. Plus budget alerts (§11).

**CI** — GitHub Actions running `ruff` and `pytest` against local Spark, so it keeps working after Azure is gone.

---

## 9. Power BI

Authoring route decided in week 1 — Power BI Desktop is Windows-only: existing Windows machine → Fabric 60-day browser trial → Windows VM.

**Page 1 — Plant manager:** downtime hours and cost, failure rate, MTBF, MTTR, trend vs. prior period.
**Page 2 — Reliability:** failure Pareto, recurring-failure machines, trend by plant and shift, drill-through to one machine's history.

Star-schema semantic model, date table marked as a date table, DAX documented in `docs/dax_measures.md`, one drill-through, **import mode** so the `.pbix` still opens after teardown.

---

## 10. Documents to write

| File | Contents |
|---|---|
| `README.md` | Architecture diagram, how to run, real measured numbers |
| `docs/data_provenance.md` | What's public, what's simulated, why |
| `docs/kpi_dictionary.md` | Formula, owner, refresh, German term per KPI |
| `docs/dax_measures.md` | Each measure with its business definition |
| `docs/runbook.md` | The deliberate failure and its recovery |
| `docs/requirements.md` | Notes from one real 30-minute requirements conversation |

Plus a **5-minute demo video** aimed at a plant manager — recorded while the system is still live.

---

## 11. Eight-week plan

| Week | Focus | Output |
|---:|---|---|
| 1 | Setup | Requirements conversation, KPI dictionary, data model on paper, **Power BI route decided**, repo + board + Docker Compose |
| 2 | Data | PySpark simulator (10M rows, injectable defects), AI4I loaded, Faker → Postgres |
| 3 | Local pipeline | Bronze→Silver→Gold on local Delta, SCD2 `dim_machine`, 10 tests green. **Gate: works locally before Azure opens** |
| 4 | Azure | Budget alerts *first*. Azure SQL, ADF ingestion with control table + backfill, ADLS landing |
| 5 | Databricks | Port the pipeline, Unity Catalog dev/prod + grants + comments, Workflows. **Demoable end to end** |
| 6 | Power BI | 2 pages, semantic model, DAX docs |
| 7 | Reliability | Deliberate failure + recovery, `ops` table, Azure Monitor alerts, CI, one partitioning benchmark |
| 8 | Wrap | Evidence capture (§13), teardown, README with real numbers, demo video |

Azure live weeks 4–8. Weeks 1–3 cost nothing.

---

## 12. Cost

Target **under $80**. Check **Cost Management + Billing → Credits** for remaining balance and expiry before week 4.

- Budget alerts at **$20 / $40 / $60** before creating any resource.
- **Azure SQL** serverless with auto-pause, or the free-tier offer.
- **Databricks Premium** (Unity Catalog requires it), smallest job cluster, single node, **auto-terminate 10 min**.
- Clusters run only while you're at the keyboard.
- **ADLS** Standard LRS — a few GB.
- Avoid: AKS, 24/7 anything, provisioned SQL tiers, private endpoints, multiple clusters.

---

## 13. Capture before teardown

Nothing below can be recreated once the subscription is gone.

- [ ] Screenshots — ADF pipeline and run history (success **and** the deliberate failure); Databricks Workflow runs; Unity Catalog grants, comments, **lineage**; the fired Azure Monitor alert; final Cost Analysis
- [ ] Export Gold tables to local Parquet
- [ ] Export the `ops` table
- [ ] Save benchmark before/after numbers
- [ ] Power BI to **import mode**, refreshed once against live data, `.pbix` committed
- [ ] **Record the 5-minute demo video**
- [ ] README numbers filled in

Then delete the resource group and confirm a €0 forecast.

---

## 14. Done when

- [ ] ADF incremental ingestion with watermarks and a working backfill
- [ ] Bronze/Silver/Gold Delta; 2 facts with documented grain; 4 dimensions; SCD2 proven by test
- [ ] 10 tests passing in CI; quarantine table populated with reasons
- [ ] Rerunning a batch leaves Gold row counts unchanged
- [ ] Unity Catalog dev/prod, grants, comments, lineage captured
- [ ] `ops` table and two firing alerts
- [ ] One documented failure and recovery
- [ ] Power BI 2 pages with documented DAX
- [ ] KPI dictionary, requirements notes, 5-minute demo video
- [ ] README with real measured numbers
- [ ] Spend under $80
