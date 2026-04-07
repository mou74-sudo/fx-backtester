import json
from pathlib import Path

import plotly.express as px
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render(_AUTO_ROOT: Path) -> None:
    import pandas as pd

    st.title("📈 Run History")
    st.caption("Every automated pipeline run is saved here — track performance trends over time.")

    _hist_tab_nq, _hist_tab_es = st.tabs(["📈 Nasdaq 100 (NQ)", "📊 S&P 500 (ES)"])

    def _render_history(instr: str, tab):
        hist_dir = _AUTO_ROOT / instr / "history"
        with tab:
            if not hist_dir.exists() or not list(hist_dir.glob("*.json")):
                st.info(f"No {instr} history yet. The pipeline saves a snapshot after every run.")
                return
            records = []
            for f in sorted(hist_dir.glob("*.json")):
                try:
                    d = json.loads(f.read_text())
                    bt = d.get("backtest", {})
                    records.append({
                        "Run": d.get("run_timestamp", f.stem),
                        "Date": d.get("run_date", ""),
                        "Trades": bt.get("trade_count", 0),
                        "Net Pips": bt.get("net_pips", 0),
                        "Net P&L $": bt.get("net_pnl", 0),
                        "Max DD %": bt.get("max_drawdown_pct", 0),
                        "WF Verdict": d.get("walk_forward_verdict", "—"),
                        "OOS Pips": d.get("oos_net_pips", 0),
                        "OOS Win Rate": d.get("oos_win_rate", 0),
                        "Key Levels": ", ".join(d.get("key_levels_used", [])),
                    })
                except Exception:
                    continue

            df = pd.DataFrame(records)
            st.dataframe(df, use_container_width=True,
                         column_config={
                             "Net P&L $": st.column_config.NumberColumn(format="$%.0f"),
                             "OOS Win Rate": st.column_config.NumberColumn(format="%.0%"),
                         })

            if len(df) > 1:
                fig = px.line(df, x="Run", y="Net Pips", markers=True,
                              title=f"{instr} — Net Pips Per Run",
                              color_discrete_sequence=["#00c49a"])
                fig.update_layout(**_cl(
                    xaxis_tickangle=-45,
                    yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                ))
                st.plotly_chart(fig, use_container_width=True, key=f"history_pips_{instr}")

            st.caption(f"Total runs stored: {len(records)}")

    _render_history("NQ", _hist_tab_nq)
    _render_history("ES", _hist_tab_es)
