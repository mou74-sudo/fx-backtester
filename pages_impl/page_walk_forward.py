import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render(_instr_code: str, _active_dir: Path) -> None:
    st.title("🔄 Walk-Forward Validation")
    st.markdown("Tests whether the strategy holds up on data it hasn't seen before.")

    # Show pre-computed pipeline results if available
    _wf_json = _active_dir / "walk_forward" / "walk_forward.json"
    if _wf_json.exists() and "wf_report" not in st.session_state:
        try:
            _wf_data = json.loads(_wf_json.read_text())
            st.info(f"Showing **{_instr_code}** pipeline results. Run a backtest manually to override.")
            verdict = _wf_data.get("verdict", "—")
            colour = {"validated": "🟢", "inconclusive": "🟡", "failed": "🔴"}
            v_col = colour.get(verdict, "⚪")
            st.subheader(f"Verdict: {v_col} {verdict.upper()}")
            folds = _wf_data.get("folds", [])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Folds evaluated",  len(folds))
            c2.metric("Profitable folds", _wf_data.get("validated_folds", 0))
            c3.metric("OOS net pips",     f"{_wf_data.get('oos_total_net_pips', 0):+.1f}")
            c4.metric("OOS win rate",     f"{_wf_data.get('oos_avg_win_rate', 0):.0%}")
            if folds:
                import plotly.express as px
                labels  = [f"Fold {f.get('fold_index', i)}" for i, f in enumerate(folds)]
                is_pips  = [f.get("in_sample", {}).get("net_pips", 0) for f in folds]
                oos_pips = [f.get("out_of_sample", {}).get("net_pips", 0) for f in folds]
                fig = go.Figure(data=[
                    go.Bar(name="In-sample",     x=labels, y=is_pips,  marker_color="#5588ff"),
                    go.Bar(name="Out-of-sample", x=labels, y=oos_pips, marker_color="#ff8855"),
                ])
                fig.update_layout(barmode="group", title="IS vs OOS Pips per Fold")
                st.plotly_chart(fig, use_container_width=True, key="wf_manual_folds")
            st.markdown("---")
            st.caption("Re-run manually below to test different settings.")
        except Exception:
            pass

    if "csv_bytes" not in st.session_state:
        st.warning("Upload data first in the **📥 Get Data** tab, then run a backtest.")
        st.stop()
    if "spec" not in st.session_state and "wf_report" not in st.session_state:
        st.info("Run a backtest first to test custom walk-forward settings.")

    n_folds     = st.slider("Number of folds", 2, 10, 5)
    is_pct      = st.slider("In-sample %", 50, 90, 70)
    min_bars    = st.number_input("Min bars per half", 20, 500, 50)

    if st.button("▶ Run Walk-Forward", type="primary"):
        with st.spinner("Running walk-forward validation…"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
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
            labels = [f"Fold {f.fold_index}" for f in report.folds]
            is_pips  = [f.in_sample.net_pips for f in report.folds]
            oos_pips = [f.out_of_sample.net_pips for f in report.folds]
            fig = go.Figure(data=[
                go.Bar(name="In-sample",     x=labels, y=is_pips,  marker_color="#5588ff"),
                go.Bar(name="Out-of-sample", x=labels, y=oos_pips,
                       marker_color=["#00c49a" if p > 0 else "#ff4455" for p in oos_pips]),
            ])
            fig.update_layout(**_cl(
                barmode="group", height=300,
                margin=dict(l=0, r=0, t=20, b=0),
                yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Net pips"),
                legend=dict(orientation="h", y=1.1),
            ))
            st.plotly_chart(fig, use_container_width=True, key="wf_manual_fold_bars")
