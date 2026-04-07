import sys
from pathlib import Path

import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render() -> None:
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
