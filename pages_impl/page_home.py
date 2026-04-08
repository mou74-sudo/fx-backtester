import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render(
    _instr_code: str,
    _active_dir: Path,
    _pipeline_summary: dict,
    _is_ai_mode: bool,
    _is_my_mode: bool,
) -> None:
    st.title("📈 NQ / ES Backtester")
    st.markdown("""
**Analyse Nasdaq 100 and S&P 500 futures strategies on real historical data.**

---

### What you can do

| Tab | What it does |
|-----|-------------|
| 📥 **Get Data** | Fetch NQ or ES H1 bars, or upload your own CSV |
| 🔬 **Backtest** | Run a strategy and see the equity curve |
| 🔄 **Walk-Forward** | Check if the strategy holds up on unseen data |
| 📍 **Key Levels** | See how price reacts at daily/weekly/session highs & lows |
| 📊 **MAE / MFE** | Check if your stops and take-profits are correctly sized |
| 📒 **Trade Journal** | Log your manual trades and track performance |

---

### Quick start

1. Use the **sidebar** to pick **🤖 AI Pipeline** (auto results) or **👤 My Analysis** (manual)
2. Select your instrument — **NQ** (Nasdaq 100) or **ES** (S&P 500)
3. Go to **📥 Get Data** to fetch data or upload a CSV
4. Go to **🔬 Backtest** → configure your strategy → tap **Run Backtest**
5. Check **📊 MAE / MFE** → then **🔄 Walk-Forward** to verify the edge

---
""")
    if _is_ai_mode and _pipeline_summary:
        ps = _pipeline_summary
        run_ts  = ps.get("run_timestamp", ps.get("run_date", ""))
        bt      = ps.get("backtest", {})
        levels  = ps.get("key_levels_used", [])
        wf_ver  = ps.get("walk_forward_verdict")
        oos_pip = ps.get("oos_net_pips")
        oos_wr  = ps.get("oos_win_rate")
        wf_val  = ps.get("wf_validated_folds")
        wf_tot  = ps.get("wf_total_folds")

        # Load extra files
        _spec_path = _active_dir / "live_spec.json"
        _wf_path   = _active_dir / "walk_forward" / "walk_forward.json"
        _ls_path   = _active_dir / "level_study" / "level_study.json"
        _spec_data = json.loads(_spec_path.read_text()) if _spec_path.exists() else {}
        _wf_data   = json.loads(_wf_path.read_text())   if _wf_path.exists()   else {}
        _ls_data   = json.loads(_ls_path.read_text())   if _ls_path.exists()   else {}

        _instr_full = "Nasdaq 100 (NQ)" if _instr_code == "NQ" else "S&P 500 (ES)"
        _rules = _spec_data.get("rules", {})
        _stop_pts = round(_rules.get("stop_loss_pips", 0) * 0.25, 2)
        _tp_pts   = round(_rules.get("take_profit_pips", 0) * 0.25, 2)

        st.markdown(f"## 🤖 AI Pipeline Report — {_instr_full}")
        st.caption(f"Run: {run_ts}  ·  Data: {ps.get('data_start','')} → {ps.get('data_end','')}  ·  Lookback: {ps.get('lookback_days',180)} days")
        st.markdown("---")

        # ════════════════════════════════════
        # STEP 1 — DATA FETCH
        # ════════════════════════════════════
        st.markdown("### Step 1 — Data Fetch ✅")
        st.caption("The AI downloaded real hourly price bars for the instrument.")
        bar_count = _ls_data.get("bar_count") or bt.get("bar_count")
        c1, c2, c3 = st.columns(3)
        c1.metric("Instrument",   _instr_full)
        c2.metric("Date Range",   f"{ps.get('data_start','')} → {ps.get('data_end','')}")
        c3.metric("Hourly Bars",  f"{bar_count:,}" if bar_count else "—")
        st.markdown("---")

        # ════════════════════════════════════
        # STEP 2 — STRATEGY USED
        # ════════════════════════════════════
        st.markdown("### Step 2 — Strategy Tested")
        st.caption("The AI tested this rules-based strategy on the historical data.")
        direction_map = {"long_only": "Long only (buys only)", "short_only": "Short only (sells only)", "both": "Both directions"}
        if _rules:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Strategy",   "RSI Mean Reversion")
            c2.metric("Direction",  direction_map.get(_rules.get("direction",""), _rules.get("direction","")))
            c3.metric("Stop Loss",  f"{_stop_pts} pts")
            c4.metric("Take Profit",f"{_tp_pts} pts")
            st.caption(
                f"**How it works:** When RSI drops below {_rules.get('entry_rsi_lte','')} (oversold), "
                f"the strategy buys. It exits when RSI recovers above {_rules.get('exit_rsi_gte','')} "
                f"or hits the {_stop_pts}-point stop / {_tp_pts}-point take-profit."
            )
        st.markdown("---")

        # ════════════════════════════════════
        # STEP 3 — BACKTEST RESULTS
        # ════════════════════════════════════
        trades_n = bt.get("trade_count", 0)
        net_pnl  = bt.get("net_pnl", 0)
        net_pips = bt.get("net_pips", 0)
        max_dd   = bt.get("max_drawdown_pct", 0)
        _bt_ok   = trades_n > 0

        st.markdown(f"### Step 3 — Backtest Results {'✅' if net_pnl >= 0 else '⚠️'}")
        st.caption(
            "The strategy was applied to every bar in the dataset. "
            "These are the simulated results on a $50,000 account."
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trades",      trades_n,           help="Total number of completed trades")
        c2.metric("Net P&L",     f"${net_pnl:+,.0f}", help="Total profit or loss in dollars")
        c3.metric("Net Points",  f"{net_pips:+.1f}",  help="Total points gained or lost")
        c4.metric("Max Drawdown",f"{max_dd:.1f}%",    help="Biggest losing streak — the lowest the account dropped from its peak")

        _win_rate = bt.get("win_rate")
        _exp      = bt.get("expectancy_pips")
        _avg_w    = bt.get("average_win_pips")
        _avg_l    = bt.get("average_loss_pips")
        if any(x is not None for x in [_win_rate, _exp, _avg_w, _avg_l]):
            c1, c2, c3, c4 = st.columns(4)
            if _win_rate is not None: c1.metric("Win Rate",    f"{_win_rate:.0%}", help="% of trades that made money")
            if _exp      is not None: c2.metric("Expectancy",  f"{_exp:+.1f} pts", help="Average result per trade — positive = edge exists")
            if _avg_w    is not None: c3.metric("Avg Winner",  f"{_avg_w:.1f} pts")
            if _avg_l    is not None: c4.metric("Avg Loser",   f"{_avg_l:.1f} pts")
        st.markdown("---")

        # ════════════════════════════════════
        # STEP 4 — WALK-FORWARD TEST
        # ════════════════════════════════════
        _wf_colours = {
            "validated":   ("✅", "success", "Profitable on unseen data across most time windows. The edge looks real."),
            "inconclusive":("⚠️", "warning", "Mixed results — some windows profitable, some not. Needs more data or tuning."),
            "failed":      ("❌", "error",   "Didn't hold up on unseen data. Not ready for live trading."),
        }
        _wf_icon, _wf_fn, _wf_text = _wf_colours.get(wf_ver or "", ("⚪", "info", "No verdict available yet."))
        st.markdown(f"### Step 4 — Walk-Forward Validation {_wf_icon}")
        st.caption(
            "The AI split the data into 5 separate time periods and tested whether the strategy "
            "was profitable on data it had never seen before. This is the most important test."
        )
        getattr(st, _wf_fn)(
            f"**Verdict: {(wf_ver or 'UNKNOWN').upper()}** — {_wf_text}"
            + (f"  ({wf_val}/{wf_tot} windows profitable)" if wf_val is not None else "")
        )

        # Fold chart
        _wf_folds = _wf_data.get("folds", [])
        if _wf_folds:
            c1, c2 = st.columns(2)
            if oos_pip is not None: c1.metric("Total Out-of-Sample Points", f"{oos_pip:+.1f}", help="Sum of points made on all unseen windows")
            if oos_wr  is not None: c2.metric("Avg Out-of-Sample Win Rate", f"{oos_wr:.0%}")

            labels   = [f"Window {f['fold_index']}" for f in _wf_folds]
            oos_pips = [f["out_of_sample"]["net_pips"] for f in _wf_folds]
            is_pips  = [f["in_sample"]["net_pips"]     for f in _wf_folds]
            fig_wf = go.Figure(data=[
                go.Bar(name="Trained on (in-sample)",   x=labels, y=is_pips,
                       marker_color="#5588ff", opacity=0.7),
                go.Bar(name="Tested on (out-of-sample)", x=labels, y=oos_pips,
                       marker_color=["#00c49a" if p > 0 else "#ff4455" for p in oos_pips]),
            ])
            st.caption("Blue = trained on it · Green/Red = tested on unseen data")
            fig_wf.update_layout(**_cl(
                barmode="group", height=320,
                margin=dict(l=0, r=0, t=10, b=70),
                yaxis=dict(title="Points", gridcolor="rgba(255,255,255,0.1)"),
                legend=dict(orientation="h", yanchor="top", y=-0.18, x=0, xanchor="left"),
                title=None,
            ))
            st.plotly_chart(fig_wf, use_container_width=True, key="home_wf_chart")
        st.markdown("---")

        # ════════════════════════════════════
        # STEP 5 — KEY LEVELS
        # ════════════════════════════════════
        _level_names = {
            "prev_day_highs":  "Previous Day Highs",  "prev_day_lows":  "Previous Day Lows",
            "prev_week_highs": "Previous Week Highs", "prev_week_lows": "Previous Week Lows",
            "session_highs":   "Session Highs",        "session_lows":   "Session Lows",
        }
        _ls_levels = _ls_data.get("summaries", []) or _ls_data.get("levels", [])
        _total_touches = _ls_data.get("total_touches") or sum(l.get("touch_count",0) for l in _ls_levels)

        st.markdown("### Step 5 — Key Level Scan ✅")
        st.caption(
            "The AI identified important price levels and measured how the market reacted "
            "each time price touched them — did it bounce or break through?"
        )
        if levels:
            _lv_cols = st.columns(3)
            for i, lv in enumerate(levels):
                _lv_cols[i % 3].success(f"✓ {_level_names.get(lv, lv)}")

        if _ls_levels:
            c1, c2 = st.columns(2)
            c1.metric("Levels Found", len(_ls_levels), help="Distinct price levels identified in the data")
            c2.metric("Total Touches", _total_touches, help="Number of times price came back to one of these levels")

            # Top 5 levels by touch count
            _top = sorted(_ls_levels, key=lambda x: x.get("touch_count", 0) or x.get("reactions") and len(x["reactions"]) or 0, reverse=True)[:5]
            if _top:
                st.markdown("**Most-tested levels:**")
                for lv in _top:
                    _lt   = _level_names.get(lv.get("level_type","") or (lv.get("level",{}) or {}).get("level_type",""), "Level")
                    _pr   = lv.get("price") or (lv.get("level",{}) or {}).get("price", 0)
                    _tc   = lv.get("touch_count", 0)
                    _rr   = lv.get("reversal_rate", 0)
                    _br   = lv.get("breakout_rate", 0)
                    if _tc:
                        st.markdown(
                            f"- **{_lt}** @ {_pr:.2f} — touched **{_tc}×** "
                            f"· Reversed {_rr:.0%} of the time · Broke through {_br:.0%}"
                        )
        st.markdown("---")

        # ════════════════════════════════════
        # FINAL SUMMARY
        # ════════════════════════════════════
        st.markdown("### Overall Summary")
        _summary_rows = [
            ("Data fetch",          "✅ Done", f"{bar_count:,} hourly bars loaded" if bar_count else "Completed"),
            ("Strategy tested",     "✅ Done", f"RSI Mean Reversion — {direction_map.get(_rules.get('direction',''), '')}"),
            ("Backtest",            "✅ Done" if _bt_ok else "⚠️", f"{trades_n} trades · ${net_pnl:+,.0f} · {max_dd:.1f}% max drawdown"),
            ("Walk-forward",        {"validated":"✅ Validated","inconclusive":"⚠️ Inconclusive","failed":"❌ Failed"}.get(wf_ver or "","⚪ Pending"), _wf_text),
            ("Key level scan",      "✅ Done", f"{len(_ls_levels)} levels · {_total_touches} touches" if _ls_levels else "Completed"),
        ]
        import pandas as pd
        _sum_df = pd.DataFrame(_summary_rows, columns=["Step", "Status", "Detail"])
        st.dataframe(_sum_df, use_container_width=True, hide_index=True,
                     column_config={"Status": st.column_config.TextColumn(width="small")})
        st.caption("Use the tabs above to explore Backtest, Walk-Forward, Key Levels and MAE/MFE in full detail.")

    elif _is_ai_mode and not _pipeline_summary:
        st.info(f"No AI pipeline results for **{_instr_code}** yet — the bot runs every 7 hours automatically.")
    elif _is_my_mode:
        st.success("👤 **My Analysis** — your manual runs are saved separately from the AI results.")
        st.markdown("Go to **📥 Get Data** → **🔬 Backtest** to run your own analysis.")
    else:
        st.info("Use the sidebar to select a mode and instrument.")
