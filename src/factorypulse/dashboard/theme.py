"""Validated palette and Plotly layout template.

The categorical hues below were checked with a palette validator, not eyeballed
(surfaces: light #fcfcfb, dark #1a1a19):

  light: lightness PASS, chroma PASS, CVD dE 9.1 PASS, normal-vision dE 19.6
         PASS, contrast WARN - 3 hues below 3:1
  dark : lightness PASS, chroma PASS, CVD dE 8.4 PASS, normal-vision dE 19.3
         PASS, contrast PASS

The light-mode contrast WARN is NOT dismissable: it obligates relief, which is
why every chart in this app ships a table-view toggle.

Do not substitute colours without re-running the validator.
"""

from __future__ import annotations

# Categorical slots, in FIXED order. Never cycled, never reassigned by rank.
CATEGORICAL_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
CATEGORICAL_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]

LIGHT = {
    "surface": "#fcfcfb",
    "page": "#f9f9f7",
    "text_primary": "#0b0b0b",
    "text_secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "good": "#0ca30c",
    "critical": "#d03b3b",
    "neutral": "#898781",
    "categorical": CATEGORICAL_LIGHT,
}

DARK = {
    "surface": "#1a1a19",
    "page": "#0d0d0d",
    "text_primary": "#f0efec",
    "text_secondary": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "good": "#0ca30c",
    "critical": "#d03b3b",
    "neutral": "#898781",
    "categorical": CATEGORICAL_DARK,
}


def palette(dark: bool = False) -> dict:
    return DARK if dark else LIGHT


def failure_mode_colors(modes: list[str], dark: bool = False) -> dict[str, str]:
    """Colour follows the ENTITY, not its rank.

    A filter that drops a failure mode must NOT repaint the survivors, so the
    mapping is built from a stable sorted key, never from plot order.
    """
    hues = palette(dark)["categorical"]
    return {m: hues[i % len(hues)] for i, m in enumerate(sorted(modes))}


def plotly_layout(dark: bool = False, height: int = 320) -> dict:
    """Recessive chrome, thin marks, hairline grid — never Plotly defaults."""
    p = palette(dark)

    def axis() -> dict:
        """A FRESH dict per call.

        Sharing one dict between xaxis and yaxis aliases them: a caller doing
        `layout["yaxis"].update(range=[0, 105])` would silently rescale the
        x-axis too, which crushed the categorical Pareto bars into a sliver and
        put the y-axis title under the x-axis.
        """
        return dict(
            showgrid=True,
            gridcolor=p["grid"],
            gridwidth=1,
            zeroline=False,
            linecolor=p["axis"],
            linewidth=1,
            tickfont=dict(color=p["muted"], size=11),
            title_font=dict(color=p["text_secondary"], size=12),
        )

    return dict(
        height=height,
        paper_bgcolor=p["surface"],
        plot_bgcolor=p["surface"],
        font=dict(
            family='system-ui, -apple-system, "Segoe UI", sans-serif',
            color=p["text_primary"],
            size=12,
        ),
        margin=dict(l=8, r=8, t=36, b=8),
        xaxis=axis(),
        yaxis=axis(),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            font=dict(color=p["text_secondary"], size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor=p["surface"],
            bordercolor=p["axis"],
            font=dict(color=p["text_primary"], size=12),
        ),
    )


def delta_color(value: float | None, higher_is_better: bool, dark: bool = False) -> str:
    """Direction of 'good' is PER METRIC.

    Rising MTBF is good; rising downtime is bad. A single shared colour rule
    would render worsening downtime as good news.
    """
    p = palette(dark)
    if value is None:
        return p["neutral"]
    improving = value > 0 if higher_is_better else value < 0
    if abs(value) < 0.05:
        return p["neutral"]
    return p["good"] if improving else p["critical"]


def page_css(dark: bool = False) -> str:
    """CSS that themes the Streamlit page chrome to match the charts.

    Without this the toggle only re-themes the Plotly surfaces: the page stays
    light, and the KPI tiles — which draw their value in `text_primary` —
    render near-white on a near-white background and vanish.
    """
    p = palette(dark)
    return f"""
    <style>
      .stApp {{ background: {p["page"]}; }}
      .stApp, .stApp p, .stApp label, .stApp span,
      [data-testid="stMarkdownContainer"] {{ color: {p["text_primary"]}; }}
      [data-testid="stHeader"] {{ background: {p["page"]}; }}
      h1, h2, h3, h4 {{ color: {p["text_primary"]} !important; }}
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p
        {{ color: {p["text_secondary"]} !important; }}
      hr {{ border-color: {p["grid"]}; }}

      /* Sidebar and form controls keep their own light surfaces otherwise,
         which leaves light-mode text on them unreadable once the body ink
         flips to near-white. */
      [data-testid="stSidebar"] {{ background: {p["surface"]}; }}
      [data-testid="stSidebar"] * {{ color: {p["text_primary"]} !important; }}
      [data-baseweb="input"], [data-baseweb="select"] > div {{
        background: {p["surface"]} !important;
        border-color: {p["axis"]} !important;
      }}
      [data-baseweb="input"] *, [data-baseweb="select"] * {{
        color: {p["text_primary"]} !important;
      }}
    </style>
    """
