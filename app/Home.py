"""FactoryPulse — plant manager view.

Answers one question in ten seconds: is this period worse than the last, and
which machine do I send someone to?
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from factorypulse.dashboard.charts import downtime_trend_chart, pareto_chart
from factorypulse.dashboard.data import connect
from factorypulse.dashboard.metrics import (
    Filters,
    downtime_trend,
    failure_pareto,
    filter_options,
    kpi_with_prior,
    worst_machines,
)
from factorypulse.dashboard.theme import delta_color, page_css, palette

st.set_page_config(
    page_title="FactoryPulse — Anlagenverfügbarkeit",
    page_icon="⚙",
    layout="wide",
)


@st.cache_resource
def get_con():
    """cache_resource: one DuckDB connection for the whole app.

    Streamlit re-runs this entire script on EVERY widget interaction.
    Without caching, the connection is rebuilt on every click.
    """
    return connect()


@st.cache_data(ttl=600)
def load(_con, f: Filters):
    """Query results, keyed on the filters.

    The leading underscore on `_con` tells Streamlit not to hash the
    connection; `Filters` is a frozen dataclass, so it hashes fine and acts as
    the cache key.
    """
    return {
        "kpi": kpi_with_prior(_con, f),
        "trend": downtime_trend(_con, f),
        "pareto": failure_pareto(_con, f),
        "worst": worst_machines(_con, f, limit=15),
    }


con = get_con()
opts = filter_options(con)

# ---------------------------------------------------------------- filters
st.title("FactoryPulse — Anlagenverfügbarkeit")

fc = st.columns([2, 1, 1, 1])
with fc[0]:
    dates = st.date_input(
        "Zeitraum",
        value=(pd.Timestamp(opts["date_min"]), pd.Timestamp(opts["date_max"])),
        min_value=pd.Timestamp(opts["date_min"]),
        max_value=pd.Timestamp(opts["date_max"]),
    )
with fc[1]:
    plants = st.multiselect("Werk", opts["plants"], default=[])
with fc[2]:
    shifts = st.multiselect("Schicht", opts["shifts"], default=[])
with fc[3]:
    dark = st.toggle("Dark mode", value=False)
    # Relief for the light-mode contrast WARN — see dashboard/theme.py.
    show_tables = st.toggle("Tabellenansicht", value=False)

if isinstance(dates, tuple) and len(dates) == 2:
    date_from, date_to = str(dates[0]), str(dates[1])
else:
    date_from, date_to = opts["date_min"], opts["date_max"]

f = Filters(
    date_from=date_from,
    date_to=date_to,
    plants=tuple(plants),
    shifts=tuple(shifts),
    current_machines_only=True,
)

data = load(con, f)
p = palette(dark)
st.markdown(page_css(dark), unsafe_allow_html=True)

# ---------------------------------------------------------------- KPI row
k, d = data["kpi"]["current"], data["kpi"]["delta"]


def tile(col, label, value, delta_val, higher_is_better, fmt="{:,.1f}", suffix=""):
    """A stat tile. The number IS the chart — no one-bar bar charts."""
    with col:
        st.caption(label)
        shown = "—" if value is None else fmt.format(value) + suffix
        st.markdown(
            f"<div style='font-size:2rem;font-weight:600;color:{p['text_primary']};"
            f"line-height:1.1'>{shown}</div>",
            unsafe_allow_html=True,
        )
        if delta_val is None:
            st.markdown(
                f"<span style='color:{p['muted']};font-size:0.8rem'>kein Vergleich</span>",
                unsafe_allow_html=True,
            )
        else:
            arrow = "▲" if delta_val > 0 else ("▼" if delta_val < 0 else "▬")
            colr = delta_color(delta_val, higher_is_better, dark)
            st.markdown(
                f"<span style='color:{colr};font-size:0.8rem'>"
                f"{arrow} {abs(delta_val) * 100:.1f}% ggü. Vorperiode</span>",
                unsafe_allow_html=True,
            )


cols = st.columns(5)
tile(cols[0], "Stillstandzeit", k["downtime_hours"], d["downtime_hours"], False, suffix=" h")
tile(
    cols[1],
    "Stillstandkosten",
    k["downtime_cost_eur"],
    d["downtime_cost_eur"],
    False,
    fmt="€{:,.0f}",
)
tile(cols[2], "MTBF", k["mtbf_hours"], d["mtbf_hours"], True, suffix=" h")
tile(cols[3], "MTTR", k["mttr_hours"], d["mttr_hours"], False, suffix=" h")
tile(
    cols[4],
    "Verfügbarkeit",
    None if k["availability"] is None else k["availability"] * 100,
    None,
    True,
    suffix=" %",
)

st.divider()

# ---------------------------------------------------------------- charts
c1, c2 = st.columns(2)
with c1:
    if data["trend"].empty:
        st.info("Keine Daten im gewählten Zeitraum.")
    else:
        st.plotly_chart(downtime_trend_chart(data["trend"], dark), width="stretch")
        if show_tables:
            st.dataframe(data["trend"], width="stretch", hide_index=True)

with c2:
    if data["pareto"].empty:
        st.info("Keine Ausfälle im gewählten Zeitraum.")
    else:
        st.plotly_chart(pareto_chart(data["pareto"], dark), width="stretch")
        if show_tables:
            st.dataframe(
                data["pareto"][
                    [
                        "failure_mode",
                        "downtime_hours",
                        "pct_of_total",
                        "cumulative_pct",
                        "events",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

st.divider()

# ---------------------------------------------- worst machines, by COST
st.subheader("Kritischste Maschinen — nach Stillstandkosten")
st.caption(
    "Nach Kosten sortiert, nicht nach Stunden: eine Engpassmaschine auf der "
    "Hauptlinie wiegt schwerer als dieselbe Stillstandzeit auf einer Reserve."
)

w = data["worst"]
st.dataframe(
    w[
        [
            "machine_id",
            "machine_name",
            "plant_name",
            "line_id",
            "criticality",
            "downtime_hours",
            "downtime_cost_eur",
            "mtbf_hours",
            "downtime_events",
        ]
    ],
    width="stretch",
    hide_index=True,
    column_config={
        "machine_id": "ID",
        "machine_name": "Maschine",
        "plant_name": "Werk",
        "line_id": "Linie",
        "criticality": "Kritikalität",
        "downtime_hours": st.column_config.NumberColumn("Stillstand (h)", format="%.1f"),
        # Data bars make rank readable without a chart
        "downtime_cost_eur": st.column_config.ProgressColumn(
            "Kosten (€)",
            format="€%.0f",
            min_value=0,
            max_value=float(w["downtime_cost_eur"].max() or 1),
        ),
        "mtbf_hours": st.column_config.NumberColumn("MTBF (h)", format="%.1f"),
        "downtime_events": st.column_config.NumberColumn("Ereignisse", format="%d"),
    },
)

st.caption(
    "Hinweis: dim_machine ist SCD Typ 2. Diese Ansicht filtert auf is_current = true, "
    "damit geänderte Maschinen nicht doppelt erscheinen."
)
