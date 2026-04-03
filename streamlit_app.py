"""FX Backtester — Streamlit Dashboard

Works on desktop and mobile.

Run locally:
    streamlit run streamlit_app.py

Deploy to Streamlit Cloud:
    1. Push this repo to GitHub
    2. Go to share.streamlit.io → New app → select this repo
    3. Share the URL with your mate
"""
import io
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="FX Backtester",
    page_icon="📈",
    layout="centered",   # centered works better on mobile
    initial_sidebar_state="collapsed",
)

# ── Minimal mobile-friendly CSS ───────────────────────────────────────────────
st.markdown("""
<style>
/* Larger touch targets on mobile */
.stButton > button { min-height: 2.5rem; font-size: 1rem; width: 100%; }
/* Metric cards */
[data-testid="metric-container"] { background: #1e1e2e; border-radius: 8px; padding: 8px; }
/* Remove excessive padding on small screens */
@media (max-width: 600px) {
    .block-container { padding: 0.5rem 0.5rem 0; }
}
</style>
""", unsafe_allow_html=True)

# ── Navigation ────────────────────────────────────────────────────────────────
PAGES = ["🏠 Home", "📥 Get Data", "🔬 Backtest", "🔄 Walk-Forward", "📍 Key Levels", "📊 MAE / MFE"]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.caption("FX Backtester · v1.3")


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Home":
    st.title("📈 FX Backtester")
    st.markdown("""
**Test forex trading strategies on real historical data — no coding required.**

---

### What you can do

| Tab | What it does |
|-----|-------------|
| 📥 **Get Data** | Upload an OHLC CSV file |
| 🔬 **Backtest** | Run a strategy and see the equity curve |
| 🔄 **Walk-Forward** | Check if the strategy holds up on unseen data |
| 📍 **Key Levels** | See how price reacts at daily/weekly/session highs & lows |
| 📊 **MAE / MFE** | Check if your stops and take-profits are correctly sized |

---

### Quick start

1. Go to **📥 Get Data** and upload a CSV (timestamp, open, high, low, close)
2. Go to **🔬 Backtest** → configure your strategy → tap **Run Backtest**
3. Check **📊 MAE / MFE** to see if stops are too tight or too wide
4. Run **🔄 Walk-Forward** to verify the edge is real

---
""")
    st.info("Tap the **☰** menu (top left) to switch between tabs on mobile.")


# ══════════════════════════════════════════════════════════════════════════════
# GET DATA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📥 Get Data":
    st.title("📥 Get Data")
    st.markdown("Upload an OHLC CSV file. Required columns: `timestamp, open, high, low, close`")

    uploaded = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded:
        import pandas as pd
        try:
            df = pd.read_csv(uploaded)
            required = {"timestamp", "open", "high", "low", "close"}
            missing = required - set(df.columns)
            if missing:
                st.error(f"Missing columns: {missing}")
            else:
                st.success(f"Loaded {len(df):,} bars")
                st.session_state["csv_bytes"] = uploaded.getvalue()
                st.session_state["csv_name"] = uploaded.name

                col1, col2, col3 = st.columns(3)
                col1.metric("Bars", f"{len(df):,}")
                col2.metric("From", str(df['timestamp'].iloc[0])[:10])
                col3.metric("To",   str(df['timestamp'].iloc[-1])[:10])

                st.dataframe(df.head(5), use_container_width=True)
        except Exception as e:
            st.error(f"Could not read file: {e}")
    else:
        st.markdown("""
**Don't have a CSV?** You can download free EURUSD H1 data from:
- [Dukascopy History Center](https://www.dukascopy.com/trading-tools/widgets/tools/historical_data_feed/)
- [HistData.com](https://www.histdata.com/download-free-forex-historical-data/)

The CSV must have columns: `timestamp, open, high, low, close`
""")


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔬 Backtest":
    st.title("🔬 Backtest")

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab.")
        st.stop()

    # ── Strategy config ────────────────────────────────────────────────────
    st.subheader("Strategy settings")

    strategy_type = st.selectbox("Strategy type", ["RSI Mean Reversion", "Breakout"])
    direction = st.selectbox("Trade direction", ["Long only", "Short only", "Both"])
    direction_map = {"Long only": "long_only", "Short only": "short_only", "Both": "both"}

    col1, col2 = st.columns(2)
    stop_pips = col1.number_input("Stop loss (pips)", 5, 200, 20)
    tp_pips   = col2.number_input("Take profit (pips)", 5, 500, 30)
    risk_pct  = st.slider("Risk per trade (%)", 0.5, 5.0, 1.0, 0.5) / 100
    equity    = st.number_input("Starting equity ($)", 1000, 1_000_000, 10_000, step=1000)

    d1_filter = st.toggle("Daily trend filter (D1 SMA)", value=False,
                           help="Only take longs when daily close > 20-day SMA, shorts when below")

    if strategy_type == "RSI Mean Reversion":
        st.markdown("**RSI settings**")
        c1, c2, c3 = st.columns(3)
        rsi_period  = c1.number_input("RSI period", 2, 100, 14)
        rsi_os      = c2.number_input("Oversold (entry long)", 1, 49, 30)
        rsi_ob      = c3.number_input("Overbought (entry short)", 51, 99, 70)
    else:
        st.markdown("**Breakout settings**")
        c1, c2 = st.columns(2)
        bo_lookback = c1.number_input("Lookback bars", 2, 200, 20)
        bo_buffer   = c2.number_input("Buffer (pips)", 0, 50, 2)

    # ── Run ────────────────────────────────────────────────────────────────
    if st.button("▶ Run Backtest", type="primary"):
        with st.spinner("Running backtest…"):
            try:
                sys.path.insert(0, str(Path(__file__).parent / "src"))
                from fx_backtester.data.loaders import load_market_bars
                from fx_backtester.engine.backtest import run_backtest
                from fx_backtester.engine.pipeline import build_signal_pipeline
                from fx_backtester.formalizer.execution_policy import ExecutionPolicy
                from fx_backtester.formalizer.spec_models import (
                    BacktestWindow, InstrumentSpec, RiskSpec,
                    RsiMeanReversionRule, StrategySpec,
                )
                from fx_backtester.analysis.mae_mfe import compute_mae_mfe

                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
                    f.write(st.session_state["csv_bytes"])
                    tmp_path = f.name

                bars = load_market_bars(tmp_path)
                if not bars:
                    st.error("No bars loaded from CSV.")
                    st.stop()

                start_d = bars[0].timestamp.date()
                end_d   = bars[-1].timestamp.date()

                if strategy_type == "RSI Mean Reversion":
                    rules = RsiMeanReversionRule(
                        strategy_type="rsi_mean_reversion",
                        direction=direction_map[direction],
                        rsi_period=rsi_period,
                        entry_rsi_lte=float(rsi_os),
                        short_entry_rsi_gte=float(rsi_ob),
                        exit_rsi_gte=float(rsi_ob - 15),
                        short_exit_rsi_lte=float(rsi_os + 15),
                        stop_loss_pips=float(stop_pips),
                        take_profit_pips=float(tp_pips),
                        require_daily_trend=d1_filter,
                    )
                else:
                    rules = RsiMeanReversionRule(
                        strategy_type="breakout",
                        direction=direction_map[direction],
                        breakout_lookback_bars=int(bo_lookback),
                        breakout_buffer_pips=float(bo_buffer),
                        stop_loss_pips=float(stop_pips),
                        take_profit_pips=float(tp_pips),
                        require_daily_trend=d1_filter,
                    )

                spec = StrategySpec(
                    strategy_name="dashboard_run",
                    instrument=InstrumentSpec(),
                    risk=RiskSpec(initial_equity=equity, risk_per_trade_fraction=risk_pct),
                    rules=rules,
                    window=BacktestWindow(start_date=start_d, end_date=end_d),
                )
                policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
                prepared = build_signal_pipeline(market_bars=bars, spec=spec)
                result   = run_backtest(bars=prepared.bars, spec=spec, policy=policy)
                mae_mfe  = compute_mae_mfe(result.trades, prepared.bars,
                                           pip_size=0.0001,
                                           stop_loss_pips=stop_pips,
                                           take_profit_pips=tp_pips)

                st.session_state["result"]  = result
                st.session_state["mae_mfe"] = mae_mfe
                st.session_state["spec"]    = spec
                st.session_state["bars"]    = bars
            except Exception as e:
                st.error(f"Backtest failed: {e}")
                st.stop()

    # ── Results ────────────────────────────────────────────────────────────
    if "result" in st.session_state:
        result = st.session_state["result"]
        m = result.metrics
        net_pnl = round(result.ending_equity - result.starting_equity, 2)

        st.markdown("---")
        st.subheader("Results")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trades",    result.trade_count)
        c2.metric("Net pips",  f"{m.net_pips:+.1f}")
        c3.metric("Net P&L",   f"${net_pnl:+,.0f}")
        c4.metric("Max DD",    f"{m.max_drawdown_pct:.1f}%")

        c1, c2, c3, c4 = st.columns(4)
        closed = [t for t in result.trades if t.pnl_pips is not None]
        wins   = sum(1 for t in closed if (t.pnl_pips or 0) > 0)
        wr     = wins / len(closed) if closed else 0
        c1.metric("Win rate",       f"{wr:.0%}")
        c2.metric("Expectancy",     f"{m.expectancy_pips:+.1f} pips")
        c3.metric("Avg win",        f"{m.average_win_pips:.1f} pips")
        c4.metric("Avg loss",       f"{m.average_loss_pips:.1f} pips")

        # Equity curve
        st.markdown("**Equity curve**")
        equity_vals = [result.starting_equity]
        for t in result.trades:
            equity_vals.append(round(equity_vals[-1] + (t.pnl or 0), 2))
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=equity_vals, mode="lines",
            line=dict(color="#00d4aa", width=2),
            fill="tozeroy", fillcolor="rgba(0,212,170,0.1)",
            name="Equity",
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=20, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Trade table
        with st.expander("Trade log"):
            import pandas as pd
            rows = []
            for t in result.trades:
                rows.append({
                    "ID": t.trade_id,
                    "Side": t.side,
                    "Entry": t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else "",
                    "Exit":  t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "open",
                    "Pips":  f"{t.pnl_pips:+.1f}" if t.pnl_pips is not None else "—",
                    "Reason": t.exit_reason or "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# WALK-FORWARD
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔄 Walk-Forward":
    st.title("🔄 Walk-Forward Validation")
    st.markdown("Tests whether the strategy holds up on data it hasn't seen before.")

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab, then run a backtest.")
        st.stop()
    if "spec" not in st.session_state:
        st.warning("Run a backtest first so the strategy spec is available.")
        st.stop()

    n_folds     = st.slider("Number of folds", 2, 10, 5)
    is_pct      = st.slider("In-sample %", 50, 90, 70)
    min_bars    = st.number_input("Min bars per half", 20, 500, 50)

    if st.button("▶ Run Walk-Forward", type="primary"):
        with st.spinner("Running walk-forward validation…"):
            try:
                sys.path.insert(0, str(Path(__file__).parent / "src"))
                from fx_backtester.analysis.walk_forward import run_walk_forward
                from fx_backtester.formalizer.execution_policy import ExecutionPolicy

                bars = st.session_state["bars"]
                spec = st.session_state["spec"]
                policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
                report = run_walk_forward(
                    bars, spec, policy,
                    n_folds=n_folds,
                    in_sample_pct=is_pct / 100,
                    min_bars_per_half=min_bars,
                )
                st.session_state["wf_report"] = report
            except Exception as e:
                st.error(f"Walk-forward failed: {e}")

    if "wf_report" in st.session_state:
        report = st.session_state["wf_report"]
        verdict = report.verdict
        colour = {"validated": "🟢", "inconclusive": "🟡", "failed": "🔴"}

        st.markdown("---")
        v_col = colour.get(verdict, "⚪")
        st.subheader(f"Verdict: {v_col} {verdict.upper()}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Folds evaluated",  len(report.folds))
        c2.metric("Profitable folds", report.validated_folds)
        c3.metric("OOS net pips",     f"{report.oos_total_net_pips:+.1f}")
        c4.metric("OOS win rate",     f"{report.oos_avg_win_rate:.0%}")

        # Fold comparison chart
        if report.folds:
            import plotly.graph_objects as go
            labels = [f"Fold {f.fold_index}" for f in report.folds]
            is_pips  = [f.in_sample.net_pips for f in report.folds]
            oos_pips = [f.out_of_sample.net_pips for f in report.folds]
            fig = go.Figure(data=[
                go.Bar(name="In-sample",     x=labels, y=is_pips,  marker_color="#5588ff"),
                go.Bar(name="Out-of-sample", x=labels, y=oos_pips,
                       marker_color=["#00d4aa" if p > 0 else "#ff4455" for p in oos_pips]),
            ])
            fig.update_layout(
                barmode="group", height=300,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Net pips"),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# KEY LEVELS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📍 Key Levels":
    st.title("📍 Key Level Reactions")
    st.markdown("See how price behaves when it touches a key level.")

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab.")
        st.stop()

    level_types = st.multiselect(
        "Level types to scan",
        ["Previous day highs", "Previous day lows",
         "Previous week highs", "Previous week lows",
         "Session highs", "Session lows",
         "Round numbers", "Swing highs", "Swing lows"],
        default=["Previous day highs", "Previous day lows",
                 "Session highs", "Session lows"],
    )
    session  = st.selectbox("Session (for session highs/lows)", ["london", "new_york", "asia"])
    zone     = st.number_input("Zone width (pips)", 1, 30, 5)
    fwd_bars = st.number_input("Forward bars to check", 1, 50, 20)
    rev_thr  = st.number_input("Reversal threshold (pips)", 1, 100, 15)
    bo_thr   = st.number_input("Breakout threshold (pips)", 1, 100, 15)
    min_t    = st.number_input("Min touches to show level", 1, 20, 2)

    if st.button("▶ Scan Levels", type="primary"):
        with st.spinner("Scanning…"):
            try:
                sys.path.insert(0, str(Path(__file__).parent / "src"))
                from fx_backtester.analysis.key_levels import (
                    detect_prev_day_high_levels, detect_prev_day_low_levels,
                    detect_prev_week_high_levels, detect_prev_week_low_levels,
                    detect_round_number_levels, detect_session_high_levels,
                    detect_session_low_levels, detect_swing_high_levels,
                    detect_swing_low_levels, run_level_study,
                )
                from fx_backtester.data.loaders import load_market_bars

                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
                    f.write(st.session_state["csv_bytes"])
                    tmp_path = f.name

                bars   = load_market_bars(tmp_path)
                levels = []
                if "Previous day highs"  in level_types: levels += detect_prev_day_high_levels(bars)
                if "Previous day lows"   in level_types: levels += detect_prev_day_low_levels(bars)
                if "Previous week highs" in level_types: levels += detect_prev_week_high_levels(bars)
                if "Previous week lows"  in level_types: levels += detect_prev_week_low_levels(bars)
                if "Session highs"       in level_types: levels += detect_session_high_levels(bars, session)
                if "Session lows"        in level_types: levels += detect_session_low_levels(bars, session)
                if "Round numbers"       in level_types: levels += detect_round_number_levels(bars)
                if "Swing highs"         in level_types: levels += detect_swing_high_levels(bars)
                if "Swing lows"          in level_types: levels += detect_swing_low_levels(bars)

                report = run_level_study(
                    bars, levels, instrument="EURUSD", pip_size=0.0001,
                    zone_pips=float(zone), forward_bars=int(fwd_bars),
                    reversal_threshold_pips=float(rev_thr),
                    breakout_threshold_pips=float(bo_thr),
                    min_touches=int(min_t),
                )
                st.session_state["level_report"] = report
            except Exception as e:
                st.error(f"Scan failed: {e}")

    if "level_report" in st.session_state:
        report = st.session_state["level_report"]
        st.markdown("---")
        st.metric("Levels studied", report.levels_studied)
        st.metric("Total touches",  report.total_touches)

        for s in report.summaries[:20]:  # top 20 by touch count
            with st.expander(f"**{s.level.label}** @ {s.level.price:.5f} — {s.touch_count} touches"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Reversed",     f"{s.reversal_count} ({s.reversal_rate:.0%})")
                c2.metric("Broke through",f"{s.breakout_count} ({s.breakout_rate:.0%})")
                c3.metric("Consolidated", s.consolidation_count)

                if s.avg_forward_pips:
                    horizons = sorted(s.avg_forward_pips.keys())
                    pips     = [s.avg_forward_pips[h] for h in horizons]
                    fig = go.Figure(go.Bar(
                        x=[f"{h}b" for h in horizons], y=pips,
                        marker_color=["#00d4aa" if p > 0 else "#ff4455" for p in pips],
                    ))
                    fig.update_layout(
                        height=200, margin=dict(l=0,r=0,t=10,b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        yaxis=dict(title="Avg pips", gridcolor="rgba(255,255,255,0.1)"),
                    )
                    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAE / MFE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 MAE / MFE":
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
        colours  = ["#00d4aa" if e.is_winner else "#ff4455" for e in r.excursions]
        labels   = [f"{e.trade_id} ({e.pnl_pips:+.1f} pips)" for e in r.excursions]
        fig = go.Figure(go.Scatter(
            x=mae_vals, y=mfe_vals, mode="markers",
            marker=dict(color=colours, size=8, opacity=0.8),
            text=labels, hoverinfo="text+x+y",
        ))
        fig.update_layout(
            height=350, margin=dict(l=0,r=0,t=20,b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="MAE (pips — adverse)", gridcolor="rgba(255,255,255,0.1)"),
            yaxis=dict(title="MFE (pips — favorable)", gridcolor="rgba(255,255,255,0.1)"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Ideal: winners cluster bottom-right (low MAE, high MFE). Losers should cluster bottom-left.")
