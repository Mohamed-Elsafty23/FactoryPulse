# Data Provenance

## Public, real data

**AI4I 2020 Predictive Maintenance Dataset**

- Source: UCI Machine Learning Repository
- Licence: CC BY 4.0
- Volume: 10,000 rows, 14 columns
- Used for: sensor distributions and the TWF/HDF/PWF/OSF/RNF failure taxonomy
- File: `ai4i2020.csv`, committed for reproducibility

## Simulated data

**Telemetry (~10 million rows)** — `src/factorypulse/simulator/`

- Expands AI4I distributions across 20 machines, two plants, three shifts, and 12 months.
- Failure logic implements documented AI4I generative rules, so failures correlate with their
  physical conditions rather than being arbitrary labels.
- Uses `SIM_SEED=42` and is reproducible.

**Reference data** — Faker → PostgreSQL / Azure SQL

- Machine master for 20 machines, including change events for SCD Type 2.
- Preventive and corrective maintenance work orders.
- Production orders containing good and scrap quantities.

**Injected defects** — configurable, default 1%

- Duplicates, out-of-range sensor values, orphan machine identifiers, and missing fields.
- These deliberately exercise Silver-layer validation and quarantine behaviour.

## What is not real

- The 2,400 EUR hourly downtime cost is an assumption, not a measurement.
- Ideal cycle times for OEE are simulated constants per machine model.
- Plant names, locations, and technician identities are fictional.
- The requirements interview is an AI-assisted role-play in which the project owner acted as
  interviewer and the AI acted as a plant reliability manager; it is not a real stakeholder
  interview.
