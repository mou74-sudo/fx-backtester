import plotly.graph_objects as go
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render() -> None:
    st.title("📊 MAE / MFE Analysis")
    st.markdown("Maximum Adverse/Favorable Excursion — checks if your stops and take-profits are correctly sized.")

    if "mae_mfe" not in st.session_state:
        st.warning("Run a backtest first in the **🔬 Backtest** tab.")
        st.stop()

    r = st.session_state["mae_mfe"]

    if r.closed_trade_count == 0:
        st.info("No closed trades to analyse.")
        st.stop()

    # Insights
    st.info(f"🛑 **Stop:** {r.stop_insight}")
    st.info(f"🎯 **Take-profit:** {r.tp_insight}")
    st.info(f"⚡ **Efficiency:** {r.efficiency_insight}")

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Winners",        r.winner_count)
    c2.metric("Losers",         r.loser_count)
    c3.metric("Avg MAE",        f"{r.avg_mae_pips:.1f} pips")
    c4.metric("Avg MFE",        f"{r.avg_mfe_pips:.1f} pips")

    c1, c2, c3 = st.columns(3)
    c1.metric("Winner avg MAE", f"{r.winner_avg_mae_pips:.1f} pips")
    c2.metric("Winner avg MFE", f"{r.winner_avg_mfe_pips:.1f} pips")
    c3.metric("Capture eff.",   f"{r.winner_avg_efficiency:.0%}")

    # MAE vs MFE scatter
    if r.excursions:
        st.markdown("**MAE vs MFE per trade** (green = winner, red = loser)")
        mae_vals = [e.mae_pips for e in r.excursions]
        mfe_vals = [e.mfe_pips for e in r.excursions]
        colours  = ["#00c49a" if e.is_winner else "#ff4455" for e in r.excursions]
        labels   = [f"{e.trade_id} ({e.pnl_pips:+.1f} pips)" for e in r.excursions]
        fig = go.Figure(go.Scatter(
            x=mae_vals, y=mfe_vals, mode="markers",
            marker=dict(color=colours, size=8, opacity=0.8),
            text=labels, hoverinfo="text+x+y",
        ))
        fig.update_layout(**_cl(
            height=350, margin=dict(l=0,r=0,t=20,b=0),
            xaxis=dict(title="MAE (pips — adverse)", gridcolor="rgba(255,255,255,0.1)"),
            yaxis=dict(title="MFE (pips — favorable)", gridcolor="rgba(255,255,255,0.1)"),
        ))
        st.plotly_chart(fig, use_container_width=True, key="mae_mfe_scatter")
        st.caption("Ideal: winners cluster bottom-right (low MAE, high MFE). Losers should cluster bottom-left.")
