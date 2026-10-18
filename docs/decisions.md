# Architecture Decision Records

## ADR-001: Power BI authoring route

**Date:** 2026-10-18
**Status:** Accepted

**Context:** Power BI Desktop is Windows-only, while the development machine runs Linux. The
project must produce a `.pbix` artifact that remains usable after Azure resources are removed.

**Decision:** Run Power BI Desktop inside a local Windows virtual machine hosted on the Linux
development laptop. Create and configure the VM when Phase 15 begins, not during the current
phase. Build the Power BI model in Import mode so the saved `.pbix` remains usable after the
cloud data platform is torn down.

**Consequences:** This avoids Azure VM compute and disk charges and has no trial expiry. It
requires a valid Windows installation, sufficient local CPU/RAM/disk, and careful resource
limits so the VM does not make the Linux host unresponsive. Power BI work should not run at the
same time as heavy local Spark jobs. Import mode creates an extract whose refresh must be
managed, but it preserves the portfolio artifact independently of Azure.

**Alternatives rejected:**

- Existing physical Windows machine: no separate, reliably available device was selected.
- Microsoft Fabric trial: introduces a 60-day clock and potential `.pbix` export limitations.
- Windows VM on Azure: provides remote capacity but consumes Azure credit and requires strict
  deallocation discipline.
