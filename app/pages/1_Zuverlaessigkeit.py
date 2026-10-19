"""Reliability engineering view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from factorypulse.dashboard.charts import failure_rate_chart, pareto_chart
from factorypulse.dashboard.data import connect
from factorypulse.dashboard.metrics import (
    Filters,
    failure_pareto,
    failure_rate_by_shift,
    filter_options,
    worst_machines,
)
from factorypulse.dashboard.theme import page_css

st.set_page_config(page_title="Zuverlässigkeit", page_icon="🔧", layout="wide")


@st.cache_resource
def get_con():
    return connect()


con = get_con()
opts = filter_options(con)

st.title("Zuverlässigkeitsanalyse")

fc = st.columns([2, 1, 1, 1])
with fc[0]:
    dates = st.date_input(
        "Zeitraum",
        value=(pd.Timestamp(opts["date_min"]), pd.Timestamp(opts["date_max"])),
        min_value=pd.Timestamp(opts["date_min"]),
        max_value=pd.Timestamp(opts["date_max"]),
    )
with fc[1]:
    plants = st.multiselect("Werk", opts["plants"])
with fc[2]:
    shifts = st.multiselect("Schicht", opts["shifts"])
with fc[3]:
    dark = st.toggle("Dark mode", value=False)
    show_tables = st.toggle("Tabellenansicht", value=False)

date_from, date_to = (
    (str(dates[0]), str(dates[1]))
    if isinstance(dates, tuple) and len(dates) == 2
    else (opts["date_min"], opts["date_max"])
)

st.markdown(page_css(dark), unsafe_allow_html=True)

f = Filters(date_from=date_from, date_to=date_to, plants=tuple(plants), shifts=tuple(shifts))

pareto = failure_pareto(con, f)
rates = failure_rate_by_shift(con, f)

c1, c2 = st.columns(2)
with c1:
    if pareto.empty:
        st.info("Keine Ausfälle im gewählten Zeitraum.")
    else:
        st.plotly_chart(pareto_chart(pareto, dark), width="stretch")
        top2 = pareto.head(2)
        if len(top2) >= 2:
            st.caption(
                f"**{top2['pct_of_total'].sum():.0f}%** des gesamten Stillstands entfallen auf "
                f"**{top2['failure_mode'].iloc[0]}** und **{top2['failure_mode'].iloc[1]}**."
            )
        if show_tables:
            st.dataframe(pareto, width="stretch", hide_index=True)

with c2:
    if rates.empty:
        st.info("Keine Daten.")
    else:
        st.plotly_chart(failure_rate_chart(rates, dark), width="stretch")
        if show_tables:
            st.dataframe(rates, width="stretch", hide_index=True)

st.divider()

# ------------------------------------------------ recurring failures
st.subheader("Maschinen mit wiederkehrenden Ausfällen (> 3 Ereignisse)")
w = worst_machines(con, f, limit=100)
recurring = w[w["downtime_events"] > 3].sort_values("downtime_events", ascending=False)

if recurring.empty:
    st.success("Keine Maschine mit mehr als 3 Ausfallereignissen im Zeitraum.")
else:
    st.dataframe(
        recurring[
            [
                "machine_id",
                "machine_name",
                "plant_name",
                "criticality",
                "downtime_events",
                "downtime_hours",
                "downtime_cost_eur",
                "mtbf_hours",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "downtime_hours": st.column_config.NumberColumn("Stillstand (h)", format="%.1f"),
            "downtime_cost_eur": st.column_config.NumberColumn("Kosten (€)", format="€%.0f"),
            "mtbf_hours": st.column_config.NumberColumn("MTBF (h)", format="%.1f"),
        },
    )
    st.caption("Zur Detailansicht: Seite **Maschinendetail** in der Seitenleiste.")
