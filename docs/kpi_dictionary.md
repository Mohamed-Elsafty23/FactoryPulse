# KPI Dictionary — FactoryPulse

Every number on the dashboard is defined here. If a number is not in this file, it does not go
on the dashboard.

**Currency assumption:** all cost figures use `downtime_cost_eur_per_hour = 2,400 EUR`, set in
`src/factorypulse/config.py`. This is a stated assumption, not a measured value.

**Clock convention for repair time:** machine stopped → machine producing again. This includes
waiting for a technician because it reflects the plant manager's production loss.

## Reliability KPIs

### MTBF — Mean Time Between Failures

- **German:** Mittlere Betriebsdauer zwischen Ausfällen
- **Formula:** `SUM(operating_hours) / COUNT(failure_events)`
- **Grain:** machine; rolls up to line → plant
- **Excludes:** planned maintenance windows
- **Undefined when:** zero failures → return BLANK, never 0 or infinity
- **Owner:** Reliability Engineering
- **Refresh:** hourly
- **Source:** `gold.fact_downtime`, `gold.fact_machine_event`

### MTTR — Mean Time To Repair

- **German:** Mittlere Reparaturdauer
- **Formula:** `SUM(downtime_minutes WHERE is_failure) / 60 / COUNT(repairs)`
- **Grain:** machine; rolls up to line → plant
- **Owner:** Maintenance
- **Refresh:** hourly
- **Source:** `gold.fact_downtime`

### Availability

- **German:** Verfügbarkeit
- **Formula:** `MTBF / (MTBF + MTTR)`
- **Expressed as:** percentage
- **Grain:** machine; rolls up to line → plant by recomputing its components
- **Owner:** Operations
- **Refresh:** hourly
- **Source:** `gold.fact_downtime`, `gold.fact_machine_event`

## Cost and volume KPIs

### Downtime Hours

- **German:** Stillstandzeit
- **Formula:** `SUM(downtime_minutes) / 60`
- **Grain:** machine × date × downtime reason
- **Owner:** Operations
- **Refresh:** hourly
- **Source:** `gold.fact_downtime`

### Downtime Cost

- **German:** Stillstandkosten
- **Formula:** `Downtime Hours × 2,400 EUR`
- **Assumption:** one stated blended rate across all lines
- **Grain:** machine × date × downtime reason
- **Owner:** Plant Controlling
- **Refresh:** hourly
- **Source:** `gold.fact_downtime`

### Failure Rate

- **German:** Ausfallrate
- **Formula:** `COUNT(failures) / SUM(operating_hours) × 1,000`
- **Unit:** failures per 1,000 operating hours
- **Grain:** machine × failure type × shift × plant
- **Owner:** Reliability Engineering
- **Refresh:** hourly
- **Source:** `gold.fact_downtime`, `gold.fact_machine_event`

### Preventive Maintenance Ratio

- **German:** Anteil vorbeugender Instandhaltung
- **Formula:** `COUNT(work_orders WHERE type='preventive') / COUNT(all work_orders)`
- **Target:** > 0.70 (assumed benchmark for a mature programme)
- **Grain:** machine × date × plant
- **Owner:** Maintenance Planning
- **Refresh:** daily
- **Source:** `gold.fact_work_order`

## OEE

### OEE — Overall Equipment Effectiveness

- **German:** Gesamtanlageneffektivität (GAE)
- **Formula:** `Availability × Performance × Quality`
- **Availability:** `operating_time / planned_production_time`
- **Performance:** `(ideal_cycle_time × total_units) / operating_time`
- **Quality:** `good_units / total_units`
- **Grain:** machine × date
- **Owner:** Operations
- **Refresh:** daily
- **Source:** `gold.fact_production_order`, `gold.fact_downtime`
- **Caveat:** ideal cycle time is a simulated constant per machine model, not a measurement

## Platform KPIs

### Data Freshness

- **German:** Datenaktualität
- **Formula:** `NOW() - MAX(event_time)` in `gold.fact_machine_event`
- **SLA:** < 60 minutes
- **Alert:** Azure Monitor fires above the SLA in Phase 16
- **Grain:** pipeline/data product
- **Owner:** Data Engineering
- **Refresh:** every pipeline run

### Rejected Record Percentage

- **German:** Anteil abgelehnter Datensätze
- **Formula:** `rows_rejected / rows_read` per pipeline run
- **SLA:** < 2%; above 5% is an incident
- **Grain:** pipeline run × source table
- **Owner:** Data Engineering
- **Refresh:** every pipeline run
- **Source:** `ops.pipeline_runs`

### Pipeline Success Rate

- **German:** Erfolgsquote der Datenpipeline
- **Formula:** `COUNT(status='success') / COUNT(*)` over the trailing seven days
- **SLA:** > 95%
- **Grain:** pipeline over a trailing seven-day window
- **Owner:** Data Engineering
- **Refresh:** every pipeline run
- **Source:** `ops.pipeline_runs`
