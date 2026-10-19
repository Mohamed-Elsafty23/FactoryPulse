# Semantic Layer — FactoryPulse

Every number on the dashboard is defined in
`src/factorypulse/dashboard/metrics.py`. This file explains **why** each is
written the way it is. KPI business definitions live in
`docs/kpi_dictionary.md`.

**Every rule below is enforced by a test in `tests/test_metrics.py`.**

---

## MTBF — non-additive

```python
mtbf = operating_hours / failure_count   # ratio of SUMS
```

**Not** the mean of per-machine MTBF. Averaging ratios weights a day with 1
failure equally against a day with 50.

Because the Gold layer stores `operating_hours` and `failure_count` as
COMPONENTS rather than a pre-computed ratio, the correct version is the only
one expressible.

- Test: `test_mtbf_is_non_additive` — asserts the fleet value DIFFERS from the
  mean of per-machine values. If someone "simplifies" it, CI goes red.
- Test: `test_mtbf_equals_ratio_of_sums`
- Returns `None`, never `inf`, when there are no failures
  (`test_mtbf_is_none_not_infinity_when_no_failures`). Zero failures means
  UNDEFINED MTBF, not infinite.

## MTTR

Clock convention: machine stopped → machine producing again, INCLUDING wait
time for a technician. Chosen because it is what the plant manager experiences.
Also non-additive; same ratio-of-sums treatment.

## Downtime cost

A plain `SUM`. The €2,400/h rate is applied in the **Gold layer**, not here, so
the assumption stays visible in the data model rather than buried in
presentation code. Changing it is a config change plus a Gold rebuild.

## Pareto — single axis

`failure_pareto()` returns `pct_of_total` and `cumulative_pct`, both
percentages of the same total.

A classic Pareto puts counts on one y-axis and cumulative % on a second.
**Dual-axis charts are an anti-pattern**: the alignment between the two scales
is arbitrary, so the chart implies a relationship that is not in the data.
Indexing both series to % of total puts them on ONE 0–100% axis with no loss —
hours remain in the tooltip and the table view.

- Test: `test_pareto_cumulative_reaches_100` — if it stops short, the
  cumulative is being computed against the wrong total.
- Test: `test_pareto_shares_one_axis`

## SCD2 handling

`dim_machine` has more rows than machines. `Filters.current_machines_only`
(default `True`) filters `is_current`.

Current-state views filter; historical views deliberately do not. The machine
detail page sets it to `False` precisely to SHOW the version history.

- Test: `test_current_filter_prevents_scd2_duplicates`

## Prior-period comparison

The prior window is computed from the SELECTED range, not hardcoded to "last
month", so a 7-day selection compares against the preceding 7 days.

- Test: `test_prior_window_is_same_length`

## Palette

Five categorical hues, validated with a palette checker (not eyeballed) against
the light surface `#fcfcfb` and the dark surface `#1a1a19`:

| Check | Light | Dark |
|---|---|---|
| Lightness band | PASS | PASS |
| Chroma floor | PASS | PASS |
| CVD separation (worst adjacent) | ΔE 9.1 PASS | ΔE 8.4 PASS |
| Normal-vision floor | ΔE 19.6 PASS | ΔE 19.3 PASS |
| Contrast vs surface | WARN — relief required | PASS |

The light-mode contrast warning obligates relief: **every chart has a table
view toggle**. Colour follows the ENTITY (sorted key), never plot order, so
filtering a mode out does not repaint the survivors.

## Chart conventions

- 2px lines, ≥8px markers, 2px surface gap between fills
- Hairline grid one shade off the surface
- Legend whenever ≥2 series; single-series charts are named by the title
- Direct labels only at the endpoint, never on every point
- **Never a dual-axis chart**

## Why this is Python and not DAX

| | DAX in a `.pbix` | This module |
|---|---|---|
| Version control | binary blob, no diff | plain text, reviewable |
| Unit tests | none possible | pytest |
| Runs in CI | no | yes |
| Reusable outside the report | no | any notebook, any API |
| Survives teardown | only in Import mode | always |

The honest trade-off: a real plant almost certainly runs Power BI, and
self-service, row-level security and scheduled refresh are genuine advantages
this app does not have. It wins here because it survives
[Phase 16](build/16_wrap_and_teardown.md) teardown, costs nothing, and makes
the non-additivity rule a failing test rather than a comment nobody reads.
