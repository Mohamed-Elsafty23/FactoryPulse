"""Plotly chart builders. Mark specs are enforced here, not per-call.

Mark specs: 2px lines, >=8px markers, a 2px surface-coloured gap between
adjacent fills, a 1px hairline grid one shade off the surface, a legend
whenever there are >=2 series, and selective direct labels (never a number on
every point).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from factorypulse.dashboard.theme import failure_mode_colors, palette, plotly_layout

LINE_WIDTH = 2
MARKER_SIZE = 8
SEGMENT_GAP = 2  # px of surface colour between adjacent fills


def downtime_trend_chart(df: pd.DataFrame, dark: bool = False) -> go.Figure:
    """Monthly downtime hours. ONE series -> no legend box; the title names it."""
    p = palette(dark)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["month"],
            y=df["downtime_hours"],
            mode="lines+markers",
            name="Stillstandzeit",
            line=dict(color=p["categorical"][0], width=LINE_WIDTH),
            marker=dict(size=MARKER_SIZE, color=p["categorical"][0]),
            hovertemplate="<b>%{x}</b><br>%{y:.1f} h<extra></extra>",
        )
    )
    # Direct-label the ENDPOINT only — not every point.
    if not df.empty:
        last = df.iloc[-1]
        fig.add_annotation(
            x=last["month"],
            y=last["downtime_hours"],
            text=f"{last['downtime_hours']:.0f} h",
            showarrow=False,
            xshift=28,
            font=dict(color=p["text_secondary"], size=11),
        )

    layout = plotly_layout(dark, height=300)
    layout["title"] = dict(
        text="Stillstandzeit pro Monat",
        font=dict(size=14, color=p["text_primary"]),
        x=0,
    )
    layout["showlegend"] = False  # single series
    layout["hovermode"] = "x unified"  # crosshair on a line chart
    layout["yaxis"]["title"] = "Stunden"
    fig.update_layout(**layout)
    return fig


def pareto_chart(df: pd.DataFrame, dark: bool = False) -> go.Figure:
    """Pareto on a SINGLE 0-100% axis.

    Both series are percentages of the same total, so no second y-axis is
    needed. A dual-axis version would imply a relationship between two
    arbitrarily aligned scales — the reader perceives the crossing point as
    meaningful when it is an artifact of the scaling.
    """
    p = palette(dark)
    colors = failure_mode_colors(df["failure_mode"].tolist(), dark)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["failure_mode"],
            y=df["pct_of_total"],
            name="Anteil an Stillstandzeit",
            marker=dict(
                color=[colors[m] for m in df["failure_mode"]],
                line=dict(color=p["surface"], width=SEGMENT_GAP),
            ),
            customdata=df[["downtime_hours", "events"]],
            hovertemplate=(
                "<b>%{x}</b><br>%{y:.1f}%% des Gesamtstillstands"
                "<br>%{customdata[0]:.1f} h · %{customdata[1]} Ereignisse<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["failure_mode"],
            y=df["cumulative_pct"],
            name="Kumuliert",
            mode="lines+markers",
            line=dict(color=p["text_secondary"], width=LINE_WIDTH),
            marker=dict(size=MARKER_SIZE, color=p["text_secondary"]),
            hovertemplate="kumuliert %{y:.1f}%%<extra></extra>",
        )
    )

    layout = plotly_layout(dark, height=360)
    layout["margin"]["t"] = 76  # headroom: title + legend above the plot
    layout["title"] = dict(
        text="Ausfallarten nach Stillstandanteil (Pareto)",
        font=dict(size=14, color=p["text_primary"]),
        x=0,
    )
    layout["yaxis"].update(title="% des Gesamtstillstands", range=[0, 105], ticksuffix="%")
    layout["bargap"] = 0.35
    fig.update_layout(**layout)
    return fig


def failure_rate_chart(df: pd.DataFrame, dark: bool = False) -> go.Figure:
    """Grouped bars: events by shift, split by plant (2 series -> legend)."""
    p = palette(dark)
    plants = sorted(df["plant"].unique())
    hues = p["categorical"]

    fig = go.Figure()
    for i, plant in enumerate(plants):
        sub = df[df["plant"] == plant]
        fig.add_trace(
            go.Bar(
                x=sub["shift"],
                y=sub["events"],
                name=plant,
                marker=dict(
                    color=hues[i % len(hues)],
                    line=dict(color=p["surface"], width=SEGMENT_GAP),
                ),
                hovertemplate=f"<b>{plant}</b><br>%{{x}}<br>%{{y}} Ereignisse<extra></extra>",
            )
        )

    layout = plotly_layout(dark, height=320)
    layout["margin"]["t"] = 76  # headroom: title + legend above the plot
    layout["title"] = dict(
        text="Ausfallereignisse nach Schicht",
        font=dict(size=14, color=p["text_primary"]),
        x=0,
    )
    layout["barmode"] = "group"
    layout["bargap"] = 0.3
    layout["yaxis"]["title"] = "Ereignisse"
    fig.update_layout(**layout)
    return fig


def machine_downtime_chart(df: pd.DataFrame, dark: bool = False) -> go.Figure:
    p = palette(dark)
    fig = go.Figure(
        go.Scatter(
            x=df["date"],
            y=df["downtime_hours"],
            mode="lines+markers",
            line=dict(color=p["categorical"][0], width=LINE_WIDTH),
            marker=dict(size=MARKER_SIZE, color=p["categorical"][0]),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>%{y:.1f} h<extra></extra>",
        )
    )
    layout = plotly_layout(dark, height=260)
    layout["title"] = dict(
        text="Stillstandzeit pro Tag", font=dict(size=14, color=p["text_primary"]), x=0
    )
    layout["showlegend"] = False
    layout["hovermode"] = "x unified"
    layout["yaxis"]["title"] = "Stunden"
    fig.update_layout(**layout)
    return fig


def mode_breakdown_chart(df: pd.DataFrame, dark: bool = False) -> go.Figure:
    """Horizontal bars — categorical, one colour per entity."""
    p = palette(dark)
    colors = failure_mode_colors(df["failure_mode"].tolist(), dark)
    d = df.sort_values("downtime_hours")

    fig = go.Figure(
        go.Bar(
            x=d["downtime_hours"],
            y=d["failure_mode"],
            orientation="h",
            marker=dict(
                color=[colors[m] for m in d["failure_mode"]],
                line=dict(color=p["surface"], width=SEGMENT_GAP),
            ),
            hovertemplate="<b>%{y}</b><br>%{x:.1f} h<extra></extra>",
        )
    )
    layout = plotly_layout(dark, height=260)
    layout["title"] = dict(
        text="Stillstandzeit nach Ausfallart",
        font=dict(size=14, color=p["text_primary"]),
        x=0,
    )
    layout["showlegend"] = False
    layout["xaxis"]["title"] = "Stunden"
    layout["bargap"] = 0.35
    fig.update_layout(**layout)
    return fig
