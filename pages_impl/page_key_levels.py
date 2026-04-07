import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render(_instr_code: str, _active_dir: Path) -> None:
    st.title("📍 Key Level Reactions")
    st.markdown("See how price behaves when it touches a key level.")

    # Show pre-computed pipeline results if available
    _ls_json = _active_dir / "level_study" / "level_study.json"
    if _ls_json.exists():
        try:
            _ls_data = json.loads(_ls_json.read_text())
            levels_data = _ls_data.get("levels", [])
            if levels_data:
                st.info(f"Showing **{_instr_code}** pipeline results. Scan manually below to customise.")
                c1, c2 = st.columns(2)
                c1.metric("Levels studied", _ls_data.get("levels_studied", len(levels_data)))
                c2.metric("Total touches",  _ls_data.get("total_touches", "—"))
                st.markdown("---")
                _auto_type_labels = {
                    "prev_day_high": "Previous Day High", "prev_day_low": "Previous Day Low",
                    "prev_week_high": "Previous Week High", "prev_week_low": "Previous Week Low",
                    "session_high": "Session High", "session_low": "Session Low",
                    "round_number": "Round Number", "swing_high": "Swing High", "swing_low": "Swing Low",
                }
                for ai, lv in enumerate(levels_data[:30]):
                    ltype = _auto_type_labels.get(lv.get("level_type", ""), lv.get("level_type", ""))
                    price = lv.get("price", 0)
                    tc    = lv.get("touch_count", 0)
                    rc    = lv.get("reversal_count", 0)
                    bc    = lv.get("breakout_count", 0)
                    cc    = lv.get("consolidation_count", 0)
                    rr    = f"{lv.get('reversal_rate', 0):.0%}"
                    br    = f"{lv.get('breakout_rate', 0):.0%}"
                    afp   = lv.get("avg_forward_pips", {})
                    horizons = sorted(afp.keys(), key=int) if isinstance(afp, dict) else []
                    pip_line = "  ·  ".join(f"{h}b: **{afp[h]:+.1f} pips**" for h in horizons) if horizons else ""
                    with st.expander(f"{ltype} @ {price:.5f} — {tc} touches"):
                        st.markdown(
                            f"Touched **{tc}×** | "
                            f"Reversed {rc} ({rr})  ·  Broke through {bc} ({br})  ·  Consolidated {cc}"
                        )
                        if pip_line:
                            st.markdown(f"Avg move after touch → {pip_line}")
                        if horizons:
                            pips = [afp[h] for h in horizons]
                            fig = go.Figure(go.Bar(
                                x=[f"{h}b" for h in horizons], y=pips,
                                marker_color=["#00c49a" if p > 0 else "#ff4455" for p in pips],
                            ))
                            fig.update_layout(**_cl(
                                height=200, margin=dict(l=0,r=0,t=10,b=0),
                                yaxis=dict(title="Avg pips", gridcolor="rgba(255,255,255,0.1)"),
                            ))
                            st.plotly_chart(fig, use_container_width=True, key=f"auto_levels_bar_{ai}")
                st.markdown("---")
        except Exception:
            pass

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
                sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
                from fx_backtester.analysis.key_levels import (
                    detect_prev_day_high_levels, detect_prev_day_low_levels,
                    detect_prev_week_high_levels, detect_prev_week_low_levels,
                    detect_round_number_levels, detect_session_high_levels,
                    detect_session_low_levels, detect_swing_high_levels,
                    detect_swing_low_levels, run_level_study,
                )
                from fx_backtester.data.loaders import load_market_bars
                import tempfile

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

                _scan_pip_size = 0.25 if _instr_code in ("NQ", "ES") else 0.0001
                report = run_level_study(
                    bars, levels, instrument=_instr_code, pip_size=_scan_pip_size,
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

        c1, c2 = st.columns(2)
        c1.metric("Levels studied", report.levels_studied)
        c2.metric("Total touches",  report.total_touches)

        st.markdown("---")

        _type_labels = {
            "prev_day_high":  "Previous Day High",
            "prev_day_low":   "Previous Day Low",
            "prev_week_high": "Previous Week High",
            "prev_week_low":  "Previous Week Low",
            "session_high":   "Session High",
            "session_low":    "Session Low",
            "round_number":   "Round Number",
            "swing_high":     "Swing High",
            "swing_low":      "Swing Low",
        }

        for i, s in enumerate(report.summaries[:30]):
            ltype = _type_labels.get(s.level.level_type, s.level.level_type)
            # Build Brodie-style summary line
            rev_pct  = f"{s.reversal_rate:.0%}"
            brk_pct  = f"{s.breakout_rate:.0%}"
            summary_line = (
                f"**{ltype}** @ {s.level.price:.5f} — touched **{s.touch_count}× ** | "
                f"Reversed {s.reversal_count} ({rev_pct})  ·  "
                f"Broke through {s.breakout_count} ({brk_pct})  ·  "
                f"Consolidated {s.consolidation_count}"
            )

            # Avg pip moves at each horizon
            horizons = sorted(s.avg_forward_pips.keys()) if s.avg_forward_pips else []
            pip_line = "  ·  ".join(
                f"{h}b: **{s.avg_forward_pips[h]:+.1f} pips**" for h in horizons
            ) if horizons else ""

            with st.expander(f"{ltype} @ {s.level.price:.5f} — {s.touch_count} touches"):
                st.markdown(summary_line)
                if pip_line:
                    st.markdown(f"Avg move after touch → {pip_line}")

                if s.avg_forward_pips:
                    pips = [s.avg_forward_pips[h] for h in horizons]
                    fig = go.Figure(go.Bar(
                        x=[f"{h}b" for h in horizons], y=pips,
                        marker_color=["#00c49a" if p > 0 else "#ff4455" for p in pips],
                    ))
                    fig.update_layout(**_cl(
                        height=200, margin=dict(l=0,r=0,t=10,b=0),
                        yaxis=dict(title="Avg pips", gridcolor="rgba(255,255,255,0.1)"),
                    ))
                    st.plotly_chart(fig, use_container_width=True, key=f"levels_bar_{i}")
