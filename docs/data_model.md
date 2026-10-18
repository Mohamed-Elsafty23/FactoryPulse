# Data Model — FactoryPulse

## Bus matrix

| Fact / Process | dim_date | dim_machine | dim_plant | dim_shift | dim_failure_type |
|---|:---:|:---:|:---:|:---:|:---:|
| fact_machine_event | X | X | X | X | X |
| fact_downtime | X | X | X | X | X |
| fact_work_order | X | X | X |  |  |
| fact_production_order | X | X | X | X |  |

`dim_machine` and `dim_date` are conformed across all four facts. A single Power BI filter can
therefore slice downtime, production, and work orders consistently.

## Fact grains

### fact_machine_event

> **Grain: one row per machine per sensor reading timestamp.**

| Column | Type | Notes |
|---|---|---|
| event_id | STRING | Natural key, unique, used for deduplication |
| machine_sk | BIGINT | FK → `dim_machine`; version-specific surrogate key |
| date_sk | INT | FK → `dim_date` (`yyyymmdd`) |
| shift_sk | INT | FK → `dim_shift` |
| plant_sk | INT | FK → `dim_plant` |
| failure_type_sk | INT | FK → `dim_failure_type`; `NONE` when healthy |
| event_time | TIMESTAMP | Event time in UTC |
| air_temp_k | DOUBLE | Measure |
| process_temp_k | DOUBLE | Measure |
| temp_diff_k | DOUBLE | Derived: process − air |
| rotational_speed_rpm | INT | Measure |
| torque_nm | DOUBLE | Measure |
| power_w | DOUBLE | Derived: torque × rpm × 2π/60 |
| tool_wear_min | INT | Semi-additive state |
| is_failure | BOOLEAN | Failure indicator |

Partitioned by `event_date`.

### fact_downtime

> **Grain: one row per continuous interval during which one machine was not producing.**

| Column | Type | Notes |
|---|---|---|
| downtime_id | STRING | Natural key |
| machine_sk | BIGINT | FK → `dim_machine` |
| date_sk | INT | FK → `dim_date`; date of the start |
| shift_sk | INT | FK → `dim_shift` |
| failure_type_sk | INT | FK → `dim_failure_type` |
| downtime_start | TIMESTAMP | Start in UTC |
| downtime_end | TIMESTAMP | NULL while still down |
| downtime_minutes | INT | Additive |
| downtime_cost_eur | DOUBLE | Additive; minutes / 60 × configured rate |
| is_planned | BOOLEAN | Planned maintenance versus failure |

This is an accumulating snapshot: the row is updated when the machine restarts.

## Dimensions

### dim_machine — SCD Type 2

| Column | Type | Notes |
|---|---|---|
| machine_sk | BIGINT | Surrogate key; one per version |
| machine_id | STRING | Stable natural/business key |
| machine_name | STRING | Display name |
| plant_id | STRING | Plant business key |
| line_id | STRING | Tracked; changes create a version |
| model | STRING | Machine model |
| machine_type | STRING | L / M / H from AI4I |
| criticality | STRING | Tracked; changes create a version |
| valid_from | TIMESTAMP | Inclusive version start |
| valid_to | TIMESTAMP | `9999-12-31` for current row |
| is_current | BOOLEAN | Current-version flag |

### Other dimensions

- `dim_plant` (2 rows): `plant_sk`, `plant_id`, `plant_name`, `country`, `timezone`
- `dim_shift` (3 rows): `shift_sk`, `shift_name`, `start_hour`, `end_hour`
- `dim_date`: `date_sk`, `date`, `year`, `quarter`, `month`, `week`, `day_of_week`,
  `is_weekend`, `month_name_de`
- `dim_failure_type` (6 rows): `failure_type_sk`, `code`, `name_en`, `name_de`,
  `description`, `severity`

## Measure behaviour

- **Additive:** `downtime_minutes` and `downtime_cost_eur` can be summed across dimensions.
- **Semi-additive:** `tool_wear_min` can be compared across machines at a point in time, but
  must not be summed over time.
- **Non-additive:** MTBF and rates must be recomputed from their numerator and denominator at
  the current filter level; machine-level results must never be summed or simply averaged.

## Key design rationale

`machine_id` identifies the physical machine, while `machine_sk` identifies one historical
version of it. Facts join to the surrogate key so an event remains attributed to the plant,
line, and criticality valid at its event time. Joining facts to `machine_id` would match every
historical version, fan out rows, and inflate measures.

Sensor readings and downtime intervals remain separate because they have different grains: an
event is instantaneous, while downtime has a start, end, and lifecycle. Combining them would
either duplicate interval measures or discard sensor detail.
