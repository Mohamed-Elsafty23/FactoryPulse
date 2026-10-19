# Phase 13 ADF evidence

Verified against the live FactoryPulse Azure environment on 2026-10-19.

| Proof | Pipeline run ID | Result |
| --- | --- | --- |
| Initial metadata-driven load | `dc2afb80-cb40-11f1-bf73-dc41a9c164f2` | Succeeded; 20 / 2,065 / 21,600 / 2 rows copied |
| No-change idempotency | `73e3d244-cb41-11f1-bf73-dc41a9c164f2` | Succeeded; 0 / 0 / 0 / 0 rows copied |
| One-row incremental proof | `f10644e6-cb41-11f1-bf73-dc41a9c164f2` | Succeeded; 1 / 0 / 0 / 0 rows copied |
| Isolated backfill | `630ed15c-cb42-11f1-bf73-dc41a9c164f2` | Succeeded; output isolated and watermark unchanged |

The work-orders watermark was `2026-09-25T18:19:00` both before and after the backfill.
All four incremental runs used closed watermark windows and only advanced state through the
success dependency from `CopyIncremental` to `UpdateWatermark`.

## Screenshot decision

The project owner intentionally waived the optional ADF Studio screenshots. The durable run IDs,
activity metrics, watermark checks, and Terraform drift check above are the retained evidence.
