"""Bayesian Parameter Optimisation page."""

from __future__ import annotations

import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render() -> None:
    st.title("🧠 Bayesian Optimiser")
    st.markdown("""
Find the best strategy parameters using **smart search** — not brute force.
""")

    with st.expander("📖 What does this do? (plain English)", expanded=False):
        st.markdown("""
### The problem with normal grid search

Imagine you're trying to find the best RSI setting between 20 and 40.
Grid search picks fixed values — 20, 25, 30, 35, 40 — and tries all of them.
It might miss that **RSI = 32** is actually the sweet spot, because it never tested it.

With 4 parameters × 5 values each, that's already **625 combinations** to test.
Most of them are wasted runs in regions you already know aren't good.

---

### How the Bayesian Optimiser works

Think of it like a **smart detective** instead of a soldier checking every house on the street.

**Trial 1:** Tries RSI=38, Stop=180 → scores 0.4 *(not great)*
**Trial 2:** Tries RSI=24, Stop=140 → scores 1.2 *(better!)*
**Trial 3:** *"Trial 2 looked good — let me try nearby"* → RSI=26, Stop=135 → scores 1.5
**Trial 4:** *"Getting warmer"* → RSI=25, Stop=130 → scores 1.8
**...keeps narrowing in...**
**Trial 100:** RSI=27, Stop=128 → scores 2.1 ✅ **Best found**

It never wasted time testing RSI=38 again once it knew that region was poor.
Same 100 runs — but focused where it matters.

---

### What the score means

After each trial, the result gets a **score**:

> **Score = Sharpe ratio + (net points ÷ 1000) − (max drawdown % ÷ 100)**

In plain English:
- ✅ **Good Sharpe** (consistent profits vs volatility) → score goes up
- ✅ **More net points** → score goes up a little
- ❌ **Big drawdown** (account drops a lot at some point) → score goes down

**Example:**
A strategy with Sharpe = 1.8, net points = +250, max drawdown = 8% scores:
`1.8 + (250/1000) − (8/100) = 1.8 + 0.25 − 0.08 = **1.97**`

The optimiser finds the parameters that make this number as high as possible.

---

### The golden rule

Always validate on **out-of-sample data** (data the optimiser never saw).
A great in-sample score that collapses out-of-sample means the params are
curve-fitted to the past — not a real edge.
        """)

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab.")
        st.stop()
    if "spec" not in st.session_state:
        st.warning("Run a backtest first in the **🔬 Backtest** tab to set the base strategy.")
        st.stop()

    spec = st.session_state["spec"]
    bars = st.session_state["bars"]

    # ── Data split ─────────────────────────────────────────────────────────────
    st.subheader("1. Split your data")
    is_pct   = st.slider("Use first X% of bars for optimisation (in-sample)", 40, 90, 70)
    split_idx = int(len(bars) * is_pct / 100)
    is_bars   = bars[:split_idx]
    oos_bars  = bars[split_idx:]
    c1, c2 = st.columns(2)
    c1.metric("In-sample bars",     f"{len(is_bars):,}",  help="Optimised on")
    c2.metric("Out-of-sample bars", f"{len(oos_bars):,}", help="Held back for validation")

    # ── Parameter spaces ───────────────────────────────────────────────────────
    st.subheader("2. Define search ranges")
    st.caption("Set the min/max for each parameter you want to optimise. Untick to keep fixed.")

    from fx_backtester.analysis.bayesian_optimiser import ParamSpace

    spaces: dict[str, ParamSpace] = {}
    strategy_type = spec.rules.strategy_type

    if strategy_type == "rsi_mean_reversion":
        if st.checkbox("RSI period", value=True):
            c1, c2 = st.columns(2)
            rp_lo = c1.number_input("RSI period min", 2, 28, 7)
            rp_hi = c2.number_input("RSI period max", 2, 28, 21)
            if rp_lo < rp_hi:
                spaces["rsi_period"] = ParamSpace(kind="int", low=rp_lo, high=rp_hi)

        if st.checkbox("Entry RSI (oversold / overbought)", value=True):
            c1, c2 = st.columns(2)
            os_lo = c1.number_input("Oversold min",   10, 45, 20)
            os_hi = c2.number_input("Oversold max",   10, 45, 40)
            if os_lo < os_hi:
                spaces["entry_rsi_lte"] = ParamSpace(kind="int", low=os_lo, high=os_hi)
                # Mirror for shorts — keep symmetric gap
                ob_lo = 100 - int(os_hi) - 5
                ob_hi = 100 - int(os_lo) + 5
                spaces["short_entry_rsi_gte"] = ParamSpace(
                    kind="int",
                    low=max(55, ob_lo),
                    high=min(90, ob_hi),
                )

    elif strategy_type == "breakout":
        if st.checkbox("Lookback bars (breakout window)", value=True):
            c1, c2 = st.columns(2)
            lb_lo = c1.number_input("Lookback min", 2, 200, 5)
            lb_hi = c2.number_input("Lookback max", 2, 200, 80)
            if lb_lo < lb_hi:
                spaces["breakout_lookback_bars"] = ParamSpace(kind="int", low=int(lb_lo), high=int(lb_hi))

        if st.checkbox("Buffer pips (noise filter)", value=True):
            c1, c2 = st.columns(2)
            buf_lo = c1.number_input("Buffer min", 0, 20, 0)
            buf_hi = c2.number_input("Buffer max", 1, 20, 8)
            if buf_lo < buf_hi:
                spaces["breakout_buffer_pips"] = ParamSpace(kind="float", low=float(buf_lo), high=float(buf_hi))

    if st.checkbox("Stop loss (pips / points)", value=True):
        c1, c2 = st.columns(2)
        sl_lo = c1.number_input("Stop min", 10, 500, 80)
        sl_hi = c2.number_input("Stop max", 10, 500, 250)
        if sl_lo < sl_hi:
            spaces["stop_loss_pips"] = ParamSpace(kind="int", low=sl_lo, high=sl_hi)

    if st.checkbox("Take profit (pips / points)", value=True):
        c1, c2 = st.columns(2)
        tp_lo = c1.number_input("TP min", 10, 800, 160)
        tp_hi = c2.number_input("TP max", 10, 800, 500)
        if tp_lo < tp_hi:
            spaces["take_profit_pips"] = ParamSpace(kind="int", low=tp_lo, high=tp_hi)

    if not spaces:
        st.warning("Tick at least one parameter to optimise.")
        st.stop()

    # ── Trial count ────────────────────────────────────────────────────────────
    st.subheader("3. How hard should it search?")
    n_trials   = st.slider("Number of trials", 20, 300, 100,
                            help="More trials = better result but takes longer. 100 is usually enough.")
    min_trades = st.number_input("Min trades required per trial", 3, 50, 10)

    _equiv_grid = 1
    for s in spaces.values():
        if s.kind in ("int", "float") and s.low is not None and s.high is not None:
            _equiv_grid *= max(1, int(s.high) - int(s.low) + 1)
    st.info(
        f"**{n_trials} smart trials** across a space of ~{_equiv_grid:,} combinations. "
        f"{'Much faster than exhaustive search.' if _equiv_grid > n_trials else ''}"
    )

    # ── Run ────────────────────────────────────────────────────────────────────
    if st.button("🧠 Run Bayesian Optimisation", type="primary"):
        try:
            from fx_backtester.analysis.bayesian_optimiser import run_bayesian_optimisation
            from fx_backtester.formalizer.execution_policy import ExecutionPolicy

            policy = st.session_state.get("policy") or ExecutionPolicy(
                half_spread_pips=0.2, slippage_pips=0.0
            )

            _prog_bar = st.progress(0, text="Starting…")

            def _on_progress(done: int, total: int) -> None:
                pct  = done / total
                _prog_bar.progress(pct, text=f"Trial {done}/{total} — searching…")

            report = run_bayesian_optimisation(
                bars=is_bars,
                spaces=spaces,
                spec_template=spec,
                policy=policy,
                n_trials=n_trials,
                min_trades=int(min_trades),
                progress_callback=_on_progress,
            )
            _prog_bar.progress(1.0, text="Done!")
            st.session_state["bo_report"]   = report
            st.session_state["bo_is_bars"]  = is_bars
            st.session_state["bo_oos_bars"] = oos_bars

        except ImportError:
            st.error("Optuna not installed. Run: `pip install optuna`")
            st.stop()
        except Exception as e:
            st.error(f"Optimisation failed: {e}")
            st.stop()

    # ── Results ────────────────────────────────────────────────────────────────
    if "bo_report" not in st.session_state:
        st.stop()

    import pandas as pd
    import plotly.graph_objects as go

    report = st.session_state["bo_report"]
    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    c1.metric("Trials completed",    report.completed)
    c2.metric("Pruned (too few trades)", report.pruned)
    c3.metric("Search space",         f"~{_equiv_grid:,} combos")

    if not report.results:
        st.error("No trials met the minimum trade threshold. Try fewer min_trades or more data.")
        st.stop()

    best = report.best
    st.success(f"**Best score: {best.score:.3f}** — {best.trade_count} trades · "
               f"{best.net_pips:+.1f} pts · {best.win_rate:.0%} win rate · "
               f"{best.max_drawdown_pct:.1f}% max DD")
    st.markdown("**Best parameters found:**")
    st.json(best.params)

    # Score over trials chart — shows convergence
    st.markdown("**Score by trial — you can see it improving over time:**")
    _trial_nums = [r.trial_number for r in report.results]
    _scores     = [r.score        for r in report.results]
    # Running best
    _running_best = []
    _cur_best = float("-inf")
    for s in sorted(zip(_trial_nums, _scores)):
        _cur_best = max(_cur_best, s[1])
        _running_best.append(_cur_best)
    _sorted_trials = sorted(_trial_nums)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_trial_nums, y=_scores,
        mode="markers", name="Trial score",
        marker=dict(color="#5588ff", size=5, opacity=0.6),
    ))
    fig.add_trace(go.Scatter(
        x=_sorted_trials, y=_running_best,
        mode="lines", name="Best so far",
        line=dict(color="#00c49a", width=2),
    ))
    fig.update_layout(**_cl(
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="Score", gridcolor="rgba(255,255,255,0.1)"),
        xaxis=dict(title="Trial number"),
        legend=dict(orientation="h", y=1.12),
    ))
    st.plotly_chart(fig, use_container_width=True, key="bo_score_chart")

    # Top 20 results table
    st.markdown("**Top 20 results:**")
    _rows = []
    for r in report.results[:20]:
        row = {**r.params,
               "score":     round(r.score, 3),
               "trades":    r.trade_count,
               "net_pts":   r.net_pips,
               "win_rate":  f"{r.win_rate:.0%}",
               "sharpe":    f"{r.sharpe_ratio:.2f}" if r.sharpe_ratio else "—",
               "max_dd%":   r.max_drawdown_pct}
        _rows.append(row)
    st.dataframe(pd.DataFrame(_rows), use_container_width=True, height=320)

    # ── OOS Validation ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("4. Validate best params on out-of-sample data")
    st.markdown("The honest test — do the best params work on data the optimiser never saw?")

    if st.button("▶ Validate on out-of-sample", type="secondary"):
        with st.spinner("Running OOS validation…"):
            try:
                from fx_backtester.analysis.bayesian_optimiser import _apply_params
                from fx_backtester.engine.backtest import run_backtest
                from fx_backtester.engine.pipeline import build_signal_pipeline
                from fx_backtester.formalizer.execution_policy import ExecutionPolicy

                policy = st.session_state.get("policy") or ExecutionPolicy(
                    half_spread_pips=0.2, slippage_pips=0.0
                )
                _gs_is   = st.session_state.get("bo_is_bars", [])
                _warmup  = min(len(_gs_is), 100)
                _combined = _gs_is[-_warmup:] + st.session_state["bo_oos_bars"]
                oos_spec  = _apply_params(spec, best.params)
                oos_prep  = build_signal_pipeline(market_bars=_combined, spec=oos_spec)
                oos_res   = run_backtest(bars=oos_prep.bars[_warmup:], spec=oos_spec, policy=policy)

                closed  = [t for t in oos_res.trades if t.pnl_pips is not None]
                wins    = sum(1 for t in closed if (t.pnl_pips or 0) > 0)
                oos_wr  = wins / len(closed) if closed else 0

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**In-sample (optimised)**")
                    st.metric("Net points", f"{best.net_pips:+.1f}")
                    st.metric("Win rate",   f"{best.win_rate:.0%}")
                    st.metric("Trades",     best.trade_count)
                with c2:
                    st.markdown("**Out-of-sample (unseen)**")
                    delta = round(oos_res.metrics.net_pips - best.net_pips, 1)
                    st.metric("Net points", f"{oos_res.metrics.net_pips:+.1f}", delta=f"{delta:+.1f}")
                    st.metric("Win rate",   f"{oos_wr:.0%}")
                    st.metric("Trades",     oos_res.trade_count)

                if oos_res.metrics.net_pips > 0:
                    st.success("OOS profitable — the edge looks real. Run Walk-Forward for a fuller picture.")
                else:
                    st.error("OOS unprofitable — these params may be curve-fitted. Try fewer parameters or more data.")

            except Exception as e:
                st.error(f"OOS validation failed: {e}")
