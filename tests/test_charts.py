"""Tests for the dashboard theme and chart builders.

These need no Spark and no exports — they are pure layout/figure assertions.
"""

import pandas as pd

from factorypulse.dashboard.charts import downtime_trend_chart, pareto_chart
from factorypulse.dashboard.theme import failure_mode_colors, palette, plotly_layout


def test_axes_are_independent_objects():
    """xaxis and yaxis must not alias the same dict.

    When they did, `layout["yaxis"].update(range=[0, 105])` in the Pareto also
    rescaled the categorical x-axis, crushing every bar into a sliver.
    """
    layout = plotly_layout()
    layout["yaxis"].update(title="Stunden", range=[0, 105], ticksuffix="%")

    assert "title" not in layout["xaxis"]
    assert "range" not in layout["xaxis"]
    assert layout["xaxis"] is not layout["yaxis"]


def test_pareto_keeps_a_categorical_x_axis():
    df = pd.DataFrame(
        {
            "failure_mode": ["A", "B", "C"],
            "downtime_hours": [10.0, 6.0, 4.0],
            "events": [3, 2, 1],
            "pct_of_total": [50.0, 30.0, 20.0],
            "cumulative_pct": [50.0, 80.0, 100.0],
        }
    )
    fig = pareto_chart(df)

    # Only the percentage axis is bounded; bounding x would squash the bars.
    assert fig.layout.yaxis.range == (0, 105)
    assert fig.layout.xaxis.range is None
    assert fig.layout.xaxis.title.text is None


def test_trend_chart_labels_only_the_y_axis():
    df = pd.DataFrame(
        {
            "month": ["2025-10", "2025-11"],
            "downtime_hours": [5.0, 7.0],
            "downtime_cost_eur": [1.0, 2.0],
            "downtime_events": [1, 2],
        }
    )
    fig = downtime_trend_chart(df)

    assert fig.layout.yaxis.title.text == "Stunden"
    assert fig.layout.xaxis.title.text is None


def test_pareto_is_single_axis():
    """No secondary y-axis anywhere: dual-axis charts invent a relationship."""
    df = pd.DataFrame(
        {
            "failure_mode": ["A", "B"],
            "downtime_hours": [10.0, 5.0],
            "events": [2, 1],
            "pct_of_total": [66.7, 33.3],
            "cumulative_pct": [66.7, 100.0],
        }
    )
    fig = pareto_chart(df)
    assert "yaxis2" not in fig.layout
    assert all(getattr(t, "yaxis", None) in (None, "y") for t in fig.data)


def test_colour_follows_the_entity_not_plot_order():
    """Filtering a mode out must not repaint the survivors."""
    full = failure_mode_colors(["HDF", "PWF", "OSF"])
    filtered = failure_mode_colors(["HDF", "OSF"])
    assert full["HDF"] == filtered["HDF"]
    assert full["OSF"] == filtered["OSF"]


def test_dark_and_light_palettes_differ_by_selection():
    """Dark mode is chosen, never an automatic inversion of light."""
    light, dark = palette(False), palette(True)
    assert light["surface"] != dark["surface"]
    assert light["categorical"] != dark["categorical"]
    assert len(light["categorical"]) == len(dark["categorical"]) == 5
