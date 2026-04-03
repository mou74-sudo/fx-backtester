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
PAGES = ["🏠 Home", "📥 Get Data", "🔬 Backtest", "🔄 Walk-Forward", "📍 Key Levels", "📊 MAE / MFE", "🔍 Grid Search", "📈 History", "📖 How to Use"]
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


# ══════════════════════════════════════════════════════════════════════════════
# GRID SEARCH
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Grid Search":
    st.title("🔍 Parameter Grid Search")
    st.markdown("""
Find the best strategy settings by testing every combination you specify.

> ⚠️ **Always use the in-sample portion of your data only.**
> Run **Walk-Forward** afterwards to confirm the results hold on unseen data.
""")

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab.")
        st.stop()
    if "spec" not in st.session_state:
        st.warning("Run a backtest first in the **🔬 Backtest** tab to set the base strategy.")
        st.stop()

    spec = st.session_state["spec"]
    bars = st.session_state["bars"]

    # ── Data split ─────────────────────────────────────────────────────────
    st.subheader("1. Split your data")
    is_pct = st.slider("Use first X% of bars for optimisation (in-sample)", 40, 90, 70,
                        help="The remaining bars are your out-of-sample validation set — never optimise on them.")
    split_idx = int(len(bars) * is_pct / 100)
    is_bars   = bars[:split_idx]
    oos_bars  = bars[split_idx:]
    c1, c2 = st.columns(2)
    c1.metric("In-sample bars",     f"{len(is_bars):,}",  help="Used for grid search")
    c2.metric("Out-of-sample bars", f"{len(oos_bars):,}", help="Reserved for validation")

    # ── Parameter ranges ───────────────────────────────────────────────────
    st.subheader("2. Choose parameter ranges")
    st.caption("Only tick the parameters you want to vary. Keep it to 2–3 at a time to avoid overfitting.")

    param_grid: dict = {}

    strategy_type = spec.rules.strategy_type

    if strategy_type == "rsi_mean_reversion":
        if st.checkbox("RSI period", value=True):
            v = st.select_slider("RSI period values", [2,5,7,10,14,21,28], value=(7,21))
            # generate a list between the two handle values
            all_opts = [2,5,7,10,14,21,28]
            param_grid["rsi_period"] = [x for x in all_opts if v[0] <= x <= v[1]]
            st.caption(f"Will try: {param_grid['rsi_period']}")

        if st.checkbox("Entry RSI (oversold threshold)"):
            v = st.select_slider("Oversold values", [20,25,30,35,40], value=(25,35))
            all_opts = [20,25,30,35,40]
            param_grid["entry_rsi_lte"] = [x for x in all_opts if v[0] <= x <= v[1]]
            st.caption(f"Will try: {param_grid['entry_rsi_lte']}")

    if st.checkbox("Stop loss (pips)", value=True):
        v = st.select_slider("Stop loss values", [10,15,20,25,30,40,50], value=(15,30))
        all_opts = [10,15,20,25,30,40,50]
        param_grid["stop_loss_pips"] = [x for x in all_opts if v[0] <= x <= v[1]]
        st.caption(f"Will try: {param_grid['stop_loss_pips']}")

    if st.checkbox("Take profit (pips)", value=True):
        v = st.select_slider("Take profit values", [15,20,30,40,50,60,80,100], value=(20,60))
        all_opts = [15,20,30,40,50,60,80,100]
        param_grid["take_profit_pips"] = [x for x in all_opts if v[0] <= x <= v[1]]
        st.caption(f"Will try: {param_grid['take_profit_pips']}")

    sort_by = st.selectbox("Sort results by",
                           ["net_pips", "expectancy_pips", "win_rate", "ending_equity"],
                           index=0)
    min_trades = st.number_input("Min trades required (skip combinations with fewer)", 3, 50, 10)

    # Estimate combinations
    n_combos = 1
    for v in param_grid.values():
        n_combos *= len(v)
    st.info(f"**{n_combos} combinations** to test. "
            f"{'This may take a minute.' if n_combos > 200 else 'Should be fast.'}")

    if n_combos > 1000:
        st.warning("More than 1,000 combinations — consider narrowing your ranges to avoid overfitting.")

    # ── Run ────────────────────────────────────────────────────────────────
    if st.button("▶ Run Grid Search", type="primary", disabled=len(param_grid) == 0):
        with st.spinner(f"Testing {n_combos} combinations…"):
            try:
                sys.path.insert(0, str(Path(__file__).parent / "src"))
                from fx_backtester.analysis.grid_search import run_grid_search
                from fx_backtester.formalizer.execution_policy import ExecutionPolicy

                policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
                gs_report = run_grid_search(
                    is_bars, param_grid, spec, policy,
                    sort_by=sort_by,
                    min_trades=int(min_trades),
                )
                st.session_state["gs_report"] = gs_report
                st.session_state["gs_oos_bars"] = oos_bars
            except Exception as e:
                st.error(f"Grid search failed: {e}")

    # ── Results ────────────────────────────────────────────────────────────
    if "gs_report" in st.session_state:
        import pandas as pd
        gs  = st.session_state["gs_report"]
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("Combinations tested", gs.evaluated)
        c2.metric("Skipped (too few trades)", gs.skipped)
        c3.metric("Sorted by", gs.sort_by)

        if not gs.results:
            st.error("No combinations met the minimum trade threshold. Try lowering 'Min trades' or using more data.")
        else:
            # Best result callout
            best = gs.best
            st.success(f"**Best combination** — {gs.sort_by}: **{getattr(best, gs.sort_by)}**")
            st.json(best.params)

            # Results table
            rows = []
            for r in gs.results[:50]:
                row = {**r.params,
                       "trades": r.trade_count,
                       "net_pips": r.net_pips,
                       "win_rate": f"{r.win_rate:.0%}",
                       "expectancy": r.expectancy_pips,
                       "max_dd%": r.max_drawdown_pct}
                rows.append(row)
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, height=300)

            # ── Validate best params on OOS ────────────────────────────────
            st.subheader("3. Validate best params on out-of-sample data")
            st.markdown("This is the honest test — did the best in-sample params also work on data the search never saw?")

            if st.button("▶ Validate on out-of-sample", type="secondary"):
                with st.spinner("Running OOS validation…"):
                    try:
                        from fx_backtester.analysis.grid_search import _apply_params
                        from fx_backtester.engine.backtest import run_backtest
                        from fx_backtester.engine.pipeline import build_signal_pipeline
                        from fx_backtester.formalizer.execution_policy import ExecutionPolicy

                        policy  = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
                        oos_spec = _apply_params(spec, best.params)
                        oos_prep = build_signal_pipeline(market_bars=st.session_state["gs_oos_bars"], spec=oos_spec)
                        oos_res  = run_backtest(bars=oos_prep.bars, spec=oos_spec, policy=policy)

                        closed   = [t for t in oos_res.trades if t.pnl_pips is not None]
                        wins     = sum(1 for t in closed if (t.pnl_pips or 0) > 0)
                        oos_wr   = wins / len(closed) if closed else 0

                        st.markdown("#### In-sample vs Out-of-sample")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**In-sample (optimised)**")
                            st.metric("Net pips",  f"{best.net_pips:+.1f}")
                            st.metric("Win rate",  f"{best.win_rate:.0%}")
                            st.metric("Trades",    best.trade_count)
                        with col2:
                            st.markdown("**Out-of-sample (unseen)**")
                            delta_pips = round(oos_res.metrics.net_pips - best.net_pips, 1)
                            st.metric("Net pips",  f"{oos_res.metrics.net_pips:+.1f}", delta=f"{delta_pips:+.1f}")
                            st.metric("Win rate",  f"{oos_wr:.0%}")
                            st.metric("Trades",    oos_res.trade_count)

                        if oos_res.metrics.net_pips > 0:
                            st.success("OOS profitable — the edge looks real. Run walk-forward for a fuller picture.")
                        else:
                            st.error("OOS unprofitable — these params may be curve-fitted. Try fewer parameters or more data.")
                    except Exception as e:
                        st.error(f"OOS validation failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 History":
    st.title("📈 Run History")
    st.caption("Every automated pipeline run is saved here — track performance trends over time.")

    history_dir = Path("results/history")
    if not history_dir.exists() or not list(history_dir.glob("*.json")):
        st.info("No history yet. The pipeline saves a snapshot here after every run.")
    else:
        import pandas as pd

        records = []
        for f in sorted(history_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text())
                bt = d.get("backtest", {})
                records.append({
                    "Run": d.get("run_timestamp", f.stem),
                    "Date": d.get("run_date", ""),
                    "Trades": bt.get("trade_count", 0),
                    "Net Pips": bt.get("net_pips", 0),
                    "Net P&L $": bt.get("net_pnl", 0),
                    "Ending Equity": bt.get("ending_equity", 0),
                    "Max DD %": bt.get("max_drawdown_pct", 0),
                    "WF Verdict": d.get("walk_forward_verdict", "—"),
                    "OOS Pips": d.get("oos_net_pips", 0),
                    "OOS Win Rate": d.get("oos_win_rate", 0),
                })
            except Exception:
                continue

        df = pd.DataFrame(records)
        st.dataframe(df, use_container_width=True)

        if len(df) > 1:
            st.subheader("Net Pips Over Time")
            fig = px.line(df, x="Run", y="Net Pips", markers=True,
                          title="Strategy Net Pips — Each Automated Run")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Ending Equity Over Time")
            fig2 = px.line(df, x="Run", y="Ending Equity", markers=True,
                           title="Account Equity — Each Automated Run")
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, use_container_width=True)

        st.caption(f"Total runs stored: {len(records)}")


# ══════════════════════════════════════════════════════════════════════════════
# HOW TO USE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📖 How to Use":
    st.title("📖 How to Use This Tool")

    st.markdown("""
This guide walks you through everything step by step — no trading or coding experience needed.

---

## The idea in one sentence

You give it historical price data, tell it your trading rules, and it shows you
exactly how that strategy would have performed — and whether it's likely to keep working.

---

## Step 1 — Get your data (📥 Get Data tab)

You need a CSV file of historical EURUSD prices with these columns:

```
timestamp, open, high, low, close
```

**Where to get free data:**
- **HistData.com** → Free Forex Historical Data → EUR/USD → ASCII (CSV) format
- **Dukascopy** → History Center → download EURUSD H1 (hourly bars)

Once you have the file, go to **📥 Get Data** and drag it in. You'll see a preview confirming it loaded correctly.

---

## Step 2 — Run a backtest (🔬 Backtest tab)

A backtest simulates your strategy on historical data. Think of it as asking:
*"If I had followed these rules every day for the last 2 years, what would have happened?"*

**Settings explained:**

| Setting | What it does |
|---------|-------------|
| Strategy type | RSI = buy oversold, sell overbought. Breakout = trade when price breaks a recent high/low. |
| Trade direction | Long only = only buy. Short only = only sell. Both = buy and sell. |
| Stop loss | How many pips the market can move against you before you exit to limit the loss. |
| Take profit | How many pips of profit triggers an automatic exit. |
| Risk per trade | What % of your account you risk on each trade. 1% is standard. |
| Daily trend filter | If ticked, only buys when the daily chart is trending up, only sells when trending down. Reduces bad trades. |

**Reading the results:**
- **Net pips** — total pips made or lost across all trades
- **Win rate** — what % of trades were profitable
- **Expectancy** — average pips per trade. Positive = good. Negative = losing strategy.
- **Max drawdown** — the biggest peak-to-trough loss during the period (%)
- **Equity curve** — chart of your account balance over time. You want this going up-right.

---

## Step 3 — Check your stops and TPs (📊 MAE/MFE tab)

After running a backtest, go to this tab. It answers two questions:

**Are your stops too tight?**
If your winning trades regularly came within 2 pips of your stop before going your way,
your stop is probably too tight — a slightly wider stop would have kept you in those trades.

**Are your take-profits too small?**
If price went an average of 60 pips in your favour but your TP was only 30 pips,
you're leaving money on the table. The tool will tell you this in plain English.

---

## Step 4 — Find the best settings (🔍 Grid Search tab)

Instead of guessing whether RSI 14 is better than RSI 21, grid search tests them all
and shows you which combination produced the best results.

**How to use it safely:**
1. Set the data split to 70% in-sample / 30% out-of-sample
2. Choose 2–3 parameters to vary (e.g. RSI period + stop loss)
3. Run the search — it only optimises on the first 70% of your data
4. Click "Validate on out-of-sample" — this shows whether the best settings
   also worked on the 30% of data the search never saw
5. If OOS is also profitable → the edge is likely real
6. If OOS is terrible → the settings are curve-fitted (they only worked on that specific period)

> **Don't vary more than 3 parameters at once.** The more knobs you turn,
> the more likely you'll find settings that *look* great but are just
> random coincidence.

---

## Step 5 — Confirm the edge is real (🔄 Walk-Forward tab)

Walk-forward is a stricter version of the OOS test in step 4.
It splits your data into 5 (or more) separate time windows and asks:
*"Did this strategy work consistently across different market conditions?"*

A strategy that only worked in 2021 but not in 2022 or 2023 is not a real edge —
it just happened to fit one specific market regime.

**Reading the verdict:**
- 🟢 **VALIDATED** — worked in 60%+ of time windows AND total pips positive
- 🟡 **INCONCLUSIVE** — mixed results, needs more data or refinement
- 🔴 **FAILED** — didn't hold up. Don't trade this with real money.

---

## Step 6 — Study key levels (📍 Key Levels tab)

This tab doesn't backtest a strategy — instead it answers:
*"When price touches the previous day's high, how often does it bounce back vs break through?"*

**How to read the results:**

> **Previous Day High @ 1.10450**
> Touches: 31 | Reversed: 19 (61%) | Broke through: 12 (39%)
> Average move 5 bars after touch: -8.3 pips

This means: when EURUSD hits the previous day high, it rejects 61% of the time,
and when it rejects, price drops an average of 8.3 pips over the next 5 candles.
That's useful information for where to set your entry and take-profit.

---

## Common mistakes to avoid

❌ **Don't run grid search on all your data** — you'll find "perfect" settings
   that only worked on that specific history.

❌ **Don't trade a strategy that only has 10–20 trades in the backtest** — too small
   a sample. You need at least 30–50 trades to draw any conclusion.

❌ **Don't ignore the walk-forward result** — a beautiful equity curve that fails
   walk-forward is a curve-fitted curve. It will lose money live.

❌ **Don't risk more than 1–2% per trade** — even a good strategy has losing streaks.
   At 1% risk, you can lose 20 trades in a row and still have 82% of your account.

---

## Quick reference — what each tab does

| Tab | One sentence |
|-----|-------------|
| 📥 Get Data | Upload your price history CSV |
| 🔬 Backtest | Run your strategy and see the equity curve |
| 📊 MAE/MFE | Check if stops and TPs are correctly sized |
| 🔍 Grid Search | Find the best settings for your strategy |
| 🔄 Walk-Forward | Confirm the edge holds across different time periods |
| 📍 Key Levels | See how price reacts at daily/weekly/session highs and lows |

---

*Built with real data. Always paper trade before using real money.*
""")
