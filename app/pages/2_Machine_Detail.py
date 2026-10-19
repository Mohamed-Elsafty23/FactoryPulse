"""Single-machine drill-down.

Takes the user from "which machine is worst?" to "what has been happening to
this machine?" without re-selecting anything — a report becomes a workflow.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from factorypulse.dashboard.charts import machine_downtime_chart, mode_breakdown_chart
from factorypulse.dashboard.data import connect
from factorypulse.dashboard.metrics import (
    Filters,
    filter_options,
    machine_detail,
    worst_machines,
)
from factorypulse.dashboard.theme import page_css

st.set_page_config(page_title="Machine Detail", page_icon="🔍", layout="wide")


@st.cache_resource
def get_con():
    return connect()


con = get_con()
opts = filter_options(con)

st.title("Machine detail")

machines = worst_machines(con, Filters(), limit=100)
ids = machines["machine_id"].tolist()

if not ids:
    st.info("No machines found in the exports.")
    st.stop()

c = st.columns([1, 2, 1])
with c[0]:
    # Context carried across pages in session_state.
    previous = st.session_state.get("drill_machine")
    machine_id = st.selectbox(
        "Machine",
        ids,
        index=ids.index(previous) if previous in ids else 0,
    )
    st.session_state["drill_machine"] = machine_id
with c[1]:
    dates = st.date_input(
        "Date range",
        value=(pd.Timestamp(opts["date_min"]), pd.Timestamp(opts["date_max"])),
        min_value=pd.Timestamp(opts["date_min"]),
        max_value=pd.Timestamp(opts["date_max"]),
    )
with c[2]:
    dark = st.toggle("Dark mode", value=False)

date_from, date_to = (
    (str(dates[0]), str(dates[1]))
    if isinstance(dates, tuple) and len(dates) == 2
    else (opts["date_min"], opts["date_max"])
)

st.markdown(page_css(dark), unsafe_allow_html=True)

# current_machines_only=False: this page WANTS the full SCD2 history.
f = Filters(date_from=date_from, date_to=date_to, current_machines_only=False)
detail = machine_detail(con, f, machine_id)

# ---- SCD2 history is the point of this panel ----------------------------
attrs = detail["attributes"]
current_rows = attrs[attrs["is_current"]]
current = current_rows.iloc[0] if not current_rows.empty else attrs.iloc[-1]

m = st.columns(5)
m[0].metric("Machine", current["machine_name"])
m[1].metric("Plant", current["plant_id"])
m[2].metric("Line", current["line_id"])
m[3].metric("Model", current["model"])
m[4].metric("Criticality", current["criticality"])

if len(attrs) > 1:
    st.warning(
        f"This machine has **{len(attrs)} versions** in dim_machine (SCD Type 2). "
        "Its attributes changed over time:"
    )
    st.dataframe(
        attrs[["line_id", "criticality", "valid_from", "valid_to", "is_current"]],
        width="stretch",
        hide_index=True,
    )

st.divider()

c1, c2 = st.columns(2)
with c1:
    if detail["daily"].empty:
        st.info("No downtime in the selected range.")
    else:
        st.plotly_chart(machine_downtime_chart(detail["daily"], dark), width="stretch")
with c2:
    if detail["modes"].empty:
        st.info("No failures in the selected range.")
    else:
        st.plotly_chart(mode_breakdown_chart(detail["modes"], dark), width="stretch")

st.subheader("Maintenance work orders")
wo = detail["work_orders"]
if wo.empty:
    st.info("No work orders in the selected range.")
else:
    st.dataframe(
        wo,
        width="stretch",
        hide_index=True,
        column_config={
            "repair_minutes": st.column_config.NumberColumn("Repair (min)", format="%.0f"),
            "parts_cost_eur": st.column_config.NumberColumn("Parts cost (€)", format="€%.2f"),
        },
    )
    pm = (wo["wo_type"] == "preventive").mean()
    st.caption(f"Preventive maintenance share: **{pm:.0%}** (target above 70%)")
