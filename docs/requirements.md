# Requirements notes

**Date:** 2026-10-18
**Interviewer:** Mohamed Elsafty, project owner
**Participant:** AI role-playing a plant reliability manager
**Simulated profile:** Discrete manufacturing, 10 years of experience (fictional scenario)
**Format:** Simulated semi-structured requirements interview
**Nature:** AI-assisted role-play; no claim of a real industry interview

## Context

The simulated participant manages reliability for two plants with 20 repairable machines. They
are accountable for production availability, maintenance prioritisation, and the cost of
unplanned downtime. Maintenance capacity is limited, so the dashboard must help decide which
machine needs attention first rather than merely report historical totals.

## Simulated interview transcript

**Interviewer:** How do you currently know a machine is in trouble before it stops?
**Plant reliability manager:** We watch temperature differences, torque, rotational speed, tool
wear, and repeated warning patterns. A single unusual reading is less useful than a deteriorating
trend combined with the machine's criticality.

**Interviewer:** When a machine goes down, what is the first number you look for?
**Plant reliability manager:** I first need the current downtime duration, affected machine and
line, failure type, and estimated production cost. Failure count alone does not show urgency.

**Interviewer:** Which is more expensive: an unplanned stop or planned maintenance?
**Plant reliability manager:** An unplanned stop is normally more expensive because production,
labour, and scheduling are disrupted without preparation. The dashboard must keep planned and
unplanned downtime separate.

**Interviewer:** How do you decide which machine to service first?
**Plant reliability manager:** I combine machine criticality, current downtime cost, failure
frequency, duration, and whether other machines can carry the load. A plant-wide average cannot
make that decision.

**Interviewer:** What does one hour of downtime cost?
**Plant reliability manager:** It varies by line and product. Until Finance supplies line-level
rates, use 2,400 EUR per hour as a clearly labelled blended assumption.

**Interviewer:** What preventive-to-corrective maintenance ratio are you aiming for?
**Plant reliability manager:** Use more than 70% preventive work as an initial benchmark, but do
not present it as a universal fact. We would validate the target against the real maintenance
strategy.

**Interviewer:** How fresh must the data be?
**Plant reliability manager:** If the newest production event is more than 60 minutes old, mark
the dashboard stale and alert the data team.

**Interviewer:** Which manual report should become automatic?
**Plant reliability manager:** The daily report joining downtime, work orders, production output,
scrap, and estimated cost by machine and shift.

**Interviewer:** Who uses these metrics, and do they define them identically?
**Plant reliability manager:** Operations, Maintenance, Reliability Engineering, and Controlling
all use them. They often disagree about whether downtime includes planned work and when the MTTR
clock begins, so definitions and owners must be written down.

**Interviewer:** What would make you stop using this dashboard?
**Plant reliability manager:** Hidden stale data, unexplained totals, changing KPI definitions,
or invalid sensor records silently entering management figures.

## What they actually measure today

The role-play produced these stakeholder statements:

- "A plant-wide average hides the machine that is causing the problem. Show me reliability per
  machine and let me filter by plant and line."
- "I need to know whether a stop was planned. Planned maintenance and unexpected failure are not
  the same operational problem."
- "Failure count alone is not enough. Duration and estimated lost-production cost determine the
  priority."
- "Repair time starts when production stops and ends when the machine produces again. Waiting for
  a technician still costs us production."
- "Data older than one hour must be visibly stale; otherwise managers may act on it unknowingly."
- "The daily manual report combines downtime, work orders, and production output. That should be
  automated."
- "I stop trusting a dashboard when definitions change between pages, totals cannot be explained,
  or bad sensor records silently affect KPIs."

## Decisions this drives

| Finding | Design consequence |
|---|---|
| MTBF is needed per machine, not only as a plant average | `fact_machine_event` retains machine-level grain; MTBF is recomputed from operating hours and failures at the selected level |
| Planned and unplanned stops serve different decisions | `fact_downtime.is_planned` separates maintenance windows from failures |
| Downtime duration and cost drive maintenance priority | Store additive `downtime_minutes` and derive cost from the documented configuration rate |
| The operational clock covers the full production interruption | MTTR is defined as machine stopped to machine producing again |
| Data becomes untrusted after one hour | Freshness SLA is 60 minutes and will drive the Phase 16 staleness alert |
| Managers need one view across reliability and maintenance | Machine, date, and plant are conformed dimensions shared by the facts |
| Silent quality failures destroy trust | Invalid records go to quarantine with reasons; rejected-record percentage is monitored |
| KPI disagreements are unacceptable | Every dashboard measure must exist in the KPI dictionary with an owner and formula |

## Explicitly out of scope

- Real-time machine control, automatic shutdown, and commands sent back to equipment.
- Predictive-maintenance model training or prescriptive maintenance scheduling.
- Real ERP/CMMS integration; operational records are simulated in PostgreSQL/Azure SQL.
- Per-line financial costing; the first version uses one stated blended downtime rate.
- Technician performance or individual employee monitoring.

## Open questions

- Should the blended downtime rate later vary by plant, line, machine criticality, or product?
- Which stops count as planned production time exclusions for the final OEE policy?
- What business threshold should classify a machine as critical?
- Who has final authority to approve KPI-definition changes in a real deployment?
