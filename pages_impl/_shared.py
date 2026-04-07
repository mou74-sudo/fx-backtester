import plotly.graph_objects as go  # noqa: F401 — re-exported for callers

_CHART = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#c8cae0", size=12),
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(size=11), linecolor="#252840"),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(size=11), linecolor="#252840"),
    margin=dict(l=0, r=0, t=28, b=0),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    hoverlabel=dict(bgcolor="#1c1f2e", font_size=12, bordercolor="#252840"),
)


def _cl(**kw) -> dict:
    """Merge _CHART with overrides — avoids duplicate-kwarg TypeError."""
    return {**_CHART, **kw}
