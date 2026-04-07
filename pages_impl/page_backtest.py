import sys
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render() -> None:
    st.title("🔬 Backtest")

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab.")
        st.stop()

    # ── Strategy config ────────────────────────────────────────────────────
    st.subheader("Strategy settings")

    _STRATEGY_OPTIONS = [
        "RSI Mean Reversion",
        "EMA Crossover",
        "Typical Price MA Reversion",
        "Opening Range Breakout",
        "Bollinger Band",
        "Breakout",
    ]
    strategy_type = st.selectbox("Strategy type", _STRATEGY_OPTIONS,
                                 help="Choose a signal generation strategy")
    direction = st.selectbox("Trade direction", ["Long only", "Short only", "Both"])
    direction_map = {"Long only": "long_only", "Short only": "short_only", "Both": "both"}

    col1, col2 = st.columns(2)
    stop_pips = col1.number_input("Stop loss (pips)", 5, 200, 20)
    tp_pips   = col2.number_input("Take profit (pips)", 5, 500, 30)
    risk_pct  = st.slider("Risk per trade (%)", 0.5, 5.0, 1.0, 0.5) / 100
    equity    = st.number_input("Starting equity ($)", 1000, 1_000_000, 10_000, step=1000)

    d1_filter = st.toggle("Daily trend filter (D1 SMA)", value=False,
                           help="Only take longs when daily close > 20-day SMA, shorts when below")

    _trail_style = st.selectbox("Trailing stop", ["Disabled", "ATR-based", "Fixed pips/points"],
                                help="Ratchets the stop in your favour as price moves. Overrides the fixed stop once activated.")
    _trail_map = {"Disabled": "disabled", "ATR-based": "atr", "Fixed pips/points": "fixed_pips"}
    _trail_atr_mult = 1.5
    _trail_pips = 20.0
    if _trail_style == "ATR-based":
        _trail_atr_mult = st.slider("ATR multiplier for trail", 0.5, 5.0, 1.5, 0.25)
    elif _trail_style == "Fixed pips/points":
        _trail_pips = st.number_input("Trailing distance (pips/points)", 5, 200, 20)

    # Strategy-specific settings
    rsi_period = 14
    rsi_os = 30
    rsi_ob = 70
    ema_fast = 9
    ema_slow = 21
    vwap_dev = 0.3
    orb_session = "rth"
    orb_range_bars = 1
    bb_period = 20
    bb_std_dev = 2.0
    bo_lookback = 20
    bo_buffer = 2

    if strategy_type == "RSI Mean Reversion":
        st.markdown("**RSI settings** — buy oversold, sell overbought based on RSI momentum reversals")
        c1, c2, c3 = st.columns(3)
        rsi_period  = c1.number_input("RSI period", 2, 100, 14)
        rsi_os      = c2.number_input("Oversold threshold (long entry)", 1, 49, 30)
        rsi_ob      = c3.number_input("Overbought threshold (short entry)", 51, 99, 70)

    elif strategy_type == "EMA Crossover":
        st.markdown("**EMA Crossover settings** — enter when fast EMA crosses above/below slow EMA")
        c1, c2 = st.columns(2)
        ema_fast = c1.number_input("Fast EMA period", 2, 100, 9)
        ema_slow = c2.number_input("Slow EMA period", 5, 500, 21)

    elif strategy_type == "Typical Price MA Reversion":
        st.markdown("**Typical Price MA Reversion** — fade extremes when price deviates from intraday typical price average ((H+L+C)/3)")
        vwap_dev = st.slider("Deviation threshold (%)", 0.05, 3.0, 0.3, 0.05,
                             help="Enter when price deviates this % from the intraday mean; exit when it returns")

    elif strategy_type == "Opening Range Breakout":
        st.markdown("**Opening Range Breakout settings** — trade breakouts beyond the first N bars of the session")
        _orb_instr = st.session_state.get("instrument", "")
        _orb_sessions = ["rth", "eth"] if _orb_instr in {"NQ", "ES"} else ["new_york", "london", "asia"]
        _orb_session_labels = {"rth": "RTH (09:30–16:00 ET)", "eth": "ETH / Globex (16:00–09:30 ET)",
                                "new_york": "New York", "london": "London", "asia": "Asia"}
        c1, c2 = st.columns(2)
        _orb_sel = c1.selectbox("Session", _orb_sessions, format_func=lambda s: _orb_session_labels.get(s, s))
        orb_session = _orb_sel
        orb_range_bars = c2.number_input("Opening range bars", 1, 6, 1)

    elif strategy_type == "Bollinger Band":
        st.markdown("**Bollinger Band settings** — mean revert from band extremes back to the middle")
        c1, c2 = st.columns(2)
        bb_period  = c1.number_input("BB period", 5, 200, 20)
        bb_std_dev = c2.slider("BB std deviations", 0.5, 4.0, 2.0, 0.5)

    else:  # Breakout
        st.markdown("**Breakout settings** — enter on N-bar high/low breakout with pip buffer")
        c1, c2 = st.columns(2)
        bo_lookback = c1.number_input("Lookback bars", 2, 200, 20)
        bo_buffer   = c2.number_input("Buffer (pips)", 0, 50, 2)

    # ── Run ────────────────────────────────────────────────────────────────
    if st.button("▶ Run Backtest", type="primary"):
        with st.spinner("Running backtest…"):
            try:
                from fx_backtester.data.loaders import load_market_bars
                from fx_backtester.engine.backtest import run_backtest
                from fx_backtester.engine.pipeline import build_signal_pipeline
                from fx_backtester.formalizer.execution_policy import ExecutionPolicy
                from fx_backtester.formalizer.spec_models import (
                    BacktestWindow, BollingerBandRule, BreakoutRule,
                    EmaCrossoverRule, InstrumentSpec, OrbRule, RiskSpec,
                    RsiMeanReversionRule, StrategySpec, VwapReversionRule,
                )
                from fx_backtester.analysis.mae_mfe import compute_mae_mfe

                import os
                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
                    f.write(st.session_state["csv_bytes"])
                    tmp_path = f.name
                try:
                    _bt_instr_code = st.session_state.get("instrument", "")
                    bars = load_market_bars(tmp_path, instrument=_bt_instr_code)
                finally:
                    os.unlink(tmp_path)
                if not bars:
                    st.error("No bars loaded from CSV.")
                    st.stop()

                start_d = bars[0].timestamp.date()
                end_d   = bars[-1].timestamp.date()

                _trail_style_val = _trail_map[_trail_style]
                _tf_yf = st.session_state.get("timeframe", "1h")
                _TF_SPEC_MAP = {"5m": "5m", "15m": "15m", "30m": "30m",
                                "1h": "H1", "4h": "4H", "1d": "D1"}
                _common = dict(
                    direction=direction_map[direction],
                    timeframe=_TF_SPEC_MAP.get(_tf_yf, "H1"),
                    stop_loss_pips=float(stop_pips),
                    take_profit_pips=float(tp_pips),
                    require_daily_trend=d1_filter,
                    trailing_stop_style=_trail_style_val,
                    trailing_stop_atr_multiplier=float(_trail_atr_mult) if _trail_style == "ATR-based" else 1.5,
                    trailing_stop_pips=float(_trail_pips) if _trail_style == "Fixed pips/points" else 20.0,
                )
                if strategy_type == "RSI Mean Reversion":
                    rules = RsiMeanReversionRule(
                        rsi_period=rsi_period,
                        entry_rsi_lte=float(rsi_os),
                        short_entry_rsi_gte=float(rsi_ob),
                        exit_rsi_gte=float(rsi_ob - 15),
                        short_exit_rsi_lte=float(rsi_os + 15),
                        **_common,
                    )
                elif strategy_type == "EMA Crossover":
                    rules = EmaCrossoverRule(
                        ema_fast_period=int(ema_fast),
                        ema_slow_period=int(ema_slow),
                        **_common,
                    )
                elif strategy_type == "Typical Price MA Reversion":
                    rules = VwapReversionRule(
                        vwap_deviation_pct=float(vwap_dev),
                        **_common,
                    )
                elif strategy_type == "Opening Range Breakout":
                    rules = OrbRule(
                        orb_session=orb_session,
                        orb_range_bars=int(orb_range_bars),
                        **_common,
                    )
                elif strategy_type == "Bollinger Band":
                    rules = BollingerBandRule(
                        bb_period=int(bb_period),
                        bb_std_dev=float(bb_std_dev),
                        **_common,
                    )
                else:  # Breakout
                    rules = BreakoutRule(
                        breakout_lookback_bars=int(bo_lookback),
                        breakout_buffer_pips=float(bo_buffer),
                        **_common,
                    )

                _loaded_instr = st.session_state.get("instrument", "")
                # commission = round-trip per contract (entry + exit legs combined).
                # Most retail brokers (NinjaTrader, Tradovate) charge ~$4.50/side = $9.00 round-trip.
                _FUTURES_INSTR = {
                    "NQ": {"pip_size": 0.25, "lot_size_units": 20, "half_spread": 1.0, "commission": 9.00},
                    "ES": {"pip_size": 0.25, "lot_size_units": 50, "half_spread": 1.0, "commission": 9.00},
                }
                if _loaded_instr in _FUTURES_INSTR:
                    _fi = _FUTURES_INSTR[_loaded_instr]
                    _instr_spec = InstrumentSpec(
                        symbol=_loaded_instr,
                        pip_size=_fi["pip_size"],
                        lot_size_units=_fi["lot_size_units"],
                        min_lot_step=1.0,  # futures trade in whole contracts only
                    )
                    _half_spread = _fi["half_spread"]
                    _commission  = _fi["commission"]
                else:
                    _instr_spec  = InstrumentSpec()   # EURUSD defaults (min_lot_step=0)
                    _half_spread = 0.2
                    _commission  = 0.0

                spec = StrategySpec(
                    strategy_name="dashboard_run",
                    instrument=_instr_spec,
                    risk=RiskSpec(initial_equity=equity, risk_per_trade_fraction=risk_pct),
                    rules=rules,
                    window=BacktestWindow(start_date=start_d, end_date=end_d),
                )
                policy = ExecutionPolicy(
                    half_spread_pips=_half_spread,
                    slippage_pips=0.0,
                    commission_per_contract=_commission,
                )
                prepared = build_signal_pipeline(market_bars=bars, spec=spec)
                result   = run_backtest(bars=prepared.bars, spec=spec, policy=policy)
                # Use pip size from the constructed spec, not session state, to avoid
                # defaulting to 0.25 (futures) for FX pairs where pip_size=0.0001.
                mae_mfe  = compute_mae_mfe(result.trades, prepared.bars,
                                           pip_size=_instr_spec.pip_size,
                                           stop_loss_pips=stop_pips,
                                           take_profit_pips=tp_pips)

                st.session_state["result"]  = result
                st.session_state["mae_mfe"] = mae_mfe
                st.session_state["spec"]    = spec
                st.session_state["bars"]    = bars
                st.session_state["policy"]  = policy  # used by grid search and walk-forward
            except Exception as e:
                st.error(f"Backtest failed: {e}")
                st.stop()

    # ── Results ────────────────────────────────────────────────────────────
    if "result" in st.session_state:
        result = st.session_state["result"]
        m = result.metrics
        net_pnl = round(result.ending_equity - result.starting_equity, 2)
        _res_instr = st.session_state.get("instrument", "")
        _is_futures = _res_instr in {"NQ", "ES"}
        _pts_label = "points" if _is_futures else "pips"
        total_comm = sum(t.commission for t in result.trades)

        st.markdown("---")
        st.subheader("Results")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trades",    result.trade_count)
        c2.metric(f"Net {_pts_label}",  f"{m.net_pips:+.1f}")
        c3.metric("Net P&L",   f"${net_pnl:+,.0f}")
        c4.metric("Max DD",    f"{m.max_drawdown_pct:.1f}%")

        c1, c2, c3, c4 = st.columns(4)
        closed = [t for t in result.trades if t.pnl_pips is not None]
        wins   = sum(1 for t in closed if (t.pnl_pips or 0) > 0)
        wr     = wins / len(closed) if closed else 0
        c1.metric("Win rate",       f"{wr:.0%}")
        c2.metric("Expectancy",     f"{m.expectancy_pips:+.1f} {_pts_label}")
        c3.metric("Avg win",        f"{m.average_win_pips:.1f} {_pts_label}")
        c4.metric("Avg loss",       f"{m.average_loss_pips:.1f} {_pts_label}")

        c1, c2, c3, c4 = st.columns(4)
        _pf_display = "∞" if m.profit_factor == float("inf") else (f"{m.profit_factor:.2f}" if m.profit_factor else "—")
        c1.metric("Profit factor", _pf_display)
        c2.metric("Sharpe (ann.)", f"{m.sharpe_ratio:.2f}" if m.sharpe_ratio is not None else "—")
        c3.metric("Sortino (ann.)", f"{m.sortino_ratio:.2f}" if m.sortino_ratio is not None else "—")
        c4.metric("Commission",    f"${total_comm:,.0f}" if _is_futures else "—")

        if _is_futures and total_comm > 0:
            st.caption(f"Commissions deducted: ${total_comm:,.2f} total (${total_comm/max(result.trade_count,1):.2f}/trade avg)")

        if _is_futures:
            st.warning(
                "⚠️ **Gap risk not modelled.** This backtest assumes perfect fills at the open price. "
                "NQ/ES can gap 50+ points at the CME settlement break (16:00–18:00 ET) and on Monday opens. "
                "Real stop-loss fills may be worse than shown when a gap occurs."
            )

        # Equity curve with date axis
        st.markdown("**Equity curve**")
        equity_vals = [result.starting_equity]
        eq_dates    = [result.trades[0].entry_time if result.trades else None]
        for t in result.trades:
            equity_vals.append(round(equity_vals[-1] + (t.pnl or 0), 2))
            eq_dates.append(t.exit_time or t.entry_time)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq_dates, y=equity_vals, mode="lines",
            line=dict(color="#00c49a", width=2),
            fill="tozeroy", fillcolor="rgba(0,212,170,0.1)",
            name="Equity",
        ))
        fig.update_layout(**_cl(
            margin=dict(l=0, r=0, t=20, b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
            height=300,
        ))
        st.plotly_chart(fig, use_container_width=True, key="backtest_equity_curve")

        # Trade table
        with st.expander("Trade log"):
            import pandas as pd
            rows = []
            spec = st.session_state.get("spec")
            for t in result.trades:
                _qty_label = f"{t.quantity_units // max(spec.instrument.lot_size_units, 1)} ct" if _is_futures and spec else str(t.quantity_units)
                rows.append({
                    "ID": t.trade_id,
                    "Side": t.side,
                    "Size": _qty_label,
                    "Entry": t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else "",
                    "Exit":  t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "open",
                    _pts_label.capitalize(): f"{t.pnl_pips:+.1f}" if t.pnl_pips is not None else "—",
                    "P&L ($)": f"${t.pnl:+,.0f}" if t.pnl is not None else "—",
                    "Commission": f"${t.commission:.2f}" if t.commission else "—",
                    "Reason": t.exit_reason or "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Monte Carlo simulation
        with st.expander("📊 Monte Carlo simulation"):
            import random
            _mc_runs = st.slider("Simulations", 200, 2000, 500, 100,
                                  help="Number of times to randomly shuffle the trade sequence and replay equity")
            if st.button("▶ Run Monte Carlo", key="run_mc"):
                _pnl_list = [t.pnl or 0.0 for t in result.trades]
                _start_eq = result.starting_equity
                _mc_finals: list = []
                _mc_max_dds: list = []
                _rng = random.Random(42)
                for _ in range(_mc_runs):
                    shuffled = _pnl_list[:]
                    _rng.shuffle(shuffled)
                    eq, peak, max_dd = _start_eq, _start_eq, 0.0
                    for p in shuffled:
                        eq += p
                        if eq > peak:
                            peak = eq
                        dd = peak - eq
                        if dd > max_dd:
                            max_dd = dd
                    _mc_finals.append(eq)
                    _mc_max_dds.append(max_dd)

                _mc_finals.sort()
                _mc_max_dds.sort()
                n = len(_mc_finals)
                p5  = _mc_finals[int(n * 0.05)]
                p50 = _mc_finals[int(n * 0.50)]
                p95 = _mc_finals[int(n * 0.95)]
                dd_p50 = _mc_max_dds[int(n * 0.50)]
                dd_p95 = _mc_max_dds[int(n * 0.95)]

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("5th pct final equity",  f"${p5:,.0f}", delta=f"${p5-_start_eq:+,.0f}")
                mc2.metric("Median final equity",   f"${p50:,.0f}", delta=f"${p50-_start_eq:+,.0f}")
                mc3.metric("95th pct final equity", f"${p95:,.0f}", delta=f"${p95-_start_eq:+,.0f}")
                mc1.metric("Median max drawdown",   f"${dd_p50:,.0f}")
                mc2.metric("95th pct max drawdown", f"${dd_p95:,.0f}")
                mc3.metric("% runs profitable",     f"{sum(1 for f in _mc_finals if f > _start_eq)/n:.0%}")

                # Histogram of final equity
                fig_mc = go.Figure()
                fig_mc.add_trace(go.Histogram(
                    x=_mc_finals, nbinsx=50,
                    marker_color="#5588ff", opacity=0.8, name="Final equity",
                ))
                fig_mc.add_vline(x=_start_eq, line_dash="dash", line_color="#ff4455",
                                  annotation_text="Start equity")
                fig_mc.add_vline(x=p50, line_dash="dot", line_color="#00c49a",
                                  annotation_text="Median")
                fig_mc.update_layout(**_cl(
                    height=260, margin=dict(l=0, r=0, t=30, b=0),
                    xaxis=dict(title="Final equity ($)"),
                    yaxis=dict(title="Frequency"),
                    title=f"Monte Carlo — {_mc_runs:,} shuffled simulations",
                ))
                st.plotly_chart(fig_mc, use_container_width=True, key="mc_histogram")
                st.caption(
                    "Each bar = one simulation with trades in random order. "
                    "Wide spread = returns are order-dependent (lucky streak risk). "
                    "Tight cluster = strategy edge is consistent."
                )
