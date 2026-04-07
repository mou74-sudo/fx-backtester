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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NQ/ES Trader",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Layout ── */
.main .block-container { max-width: 1080px; padding: 1.5rem 2rem 3rem; margin: 0 auto; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #12151e;
    border-right: 1px solid #1f2235;
}
[data-testid="stSidebar"] hr { border-color: #1f2235 !important; margin: 0.6rem 0 !important; }
[data-testid="stSidebarNav"] { display: none; }

/* ── Sidebar nav items ── */
[data-testid="stSidebar"] .stRadio > div { gap: 2px; }
[data-testid="stSidebar"] .stRadio label {
    padding: 7px 10px;
    border-radius: 8px;
    font-size: 0.88rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #1e2235; }

/* ── Typography ── */
h1 {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.4px !important;
    margin-bottom: 0.25rem !important;
}
h2 { font-size: 1.3rem !important; font-weight: 600 !important; }
h3 {
    font-size: 1rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #9095b0 !important;
    margin-top: 1.8rem !important;
    margin-bottom: 0.5rem !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #15182200;
    background: linear-gradient(160deg, #1c1f2e 0%, #181b29 100%);
    border: 1px solid #252840;
    border-radius: 12px;
    padding: 14px 18px 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.25);
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.9px;
    color: #7a7f9a !important;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #f0f2ff !important;
    line-height: 1.2 !important;
}
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

/* ── Primary buttons ── */
.stButton > button {
    min-height: 2.4rem;
    font-size: 0.88rem;
    font-weight: 600;
    width: 100%;
    border-radius: 9px;
    letter-spacing: 0.2px;
    transition: all 0.15s ease;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00c49a 0%, #0099cc 100%) !important;
    border: none !important;
    color: #fff !important;
}
.stButton > button[kind="primary"]:hover {
    opacity: 0.92;
    box-shadow: 0 4px 16px rgba(0,196,154,0.35);
    transform: translateY(-1px);
}
.stButton > button[kind="secondary"] {
    background: #1c1f2e !important;
    border: 1px solid #2a2d40 !important;
    color: #c8cae0 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background: #181b29;
    border-radius: 12px;
    padding: 5px;
    border: 1px solid #252840;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 7px 18px;
    font-size: 0.84rem;
    font-weight: 500;
    color: #7a7f9a;
    background: transparent;
    border: none;
}
.stTabs [aria-selected="true"] {
    background: #252840 !important;
    color: #f0f2ff !important;
    font-weight: 600 !important;
}

/* ── Expanders ── */
details {
    border: 1px solid #252840 !important;
    border-radius: 12px !important;
    background: #181b29 !important;
    overflow: hidden;
}
details > summary {
    font-weight: 600;
    font-size: 0.88rem;
    padding: 11px 16px;
    cursor: pointer;
    color: #c8cae0;
}
details > summary:hover { background: #1e2235; }

/* ── Alert boxes ── */
.stAlert {
    border-radius: 10px !important;
    border-left-width: 3px !important;
    font-size: 0.88rem !important;
}

/* ── Dataframes ── */
[data-testid="stDataFrame"] {
    border: 1px solid #252840;
    border-radius: 10px;
    overflow: hidden;
}

/* ── Inputs / selects ── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    background: #181b29 !important;
    border: 1px solid #252840 !important;
    border-radius: 8px !important;
    color: #f0f2ff !important;
    font-size: 0.9rem !important;
}
.stSelectbox > div > div {
    background: #181b29 !important;
    border: 1px solid #252840 !important;
    border-radius: 8px !important;
}

/* ── Dividers ── */
hr { border-color: #1f2235 !important; margin: 1.5rem 0 !important; }

/* ── Captions ── */
.stCaption { color: #6b7090 !important; font-size: 0.8rem !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    border: 1px dashed #2a2d40 !important;
    border-radius: 10px !important;
    background: #181b29 !important;
}

/* ── Plotly chart containers ── */
[data-testid="stPlotlyChart"] {
    border-radius: 12px;
    overflow: hidden;
}

/* ── Mobile ── */
@media (max-width: 768px) {
    .main .block-container { padding: 0.75rem 0.75rem 2rem; }
    h1 { font-size: 1.35rem !important; }
    h3 { font-size: 0.85rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar brand header ───────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="padding:1.1rem 0.5rem 0.8rem; text-align:center; border-bottom:1px solid #1f2235; margin-bottom:0.5rem;">
    <div style="font-size:1.4rem; font-weight:800; color:#00c49a; letter-spacing:-0.5px;">📊 NQ/ES Trader</div>
    <div style="font-size:0.7rem; color:#6b7090; margin-top:3px; letter-spacing:0.5px; text-transform:uppercase;">AI-Powered Analytics</div>
</div>
""", unsafe_allow_html=True)

# ── Shared chart theme ────────────────────────────────────────────────────────
_CHART = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#c8cae0", size=12),
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(size=11), linecolor="#252840"),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickfont=dict(size=11), linecolor="#252840"),
    margin=dict(l=0, r=0, t=28, b=0),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    hoverlabel=dict(bgcolor="#1c1f2e", font_size=12, bordercolor="#252840"),
)

# ── Navigation ────────────────────────────────────────────────────────────────
PAGES = ["🏠 Home", "📥 Get Data", "🔬 Backtest", "🔄 Walk-Forward",
         "📍 Key Levels", "📊 MAE / MFE", "🔍 Grid Search",
         "📈 History", "📒 Trade Journal", "📖 How to Use"]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")

# ── Paths ─────────────────────────────────────────────────────────────────────
_RESULTS     = Path("results")
_AUTO_ROOT   = _RESULTS / "auto"
_MANUAL_ROOT = _RESULTS / "manual"

# ── Mode toggle ───────────────────────────────────────────────────────────────
st.sidebar.markdown("<div style='font-size:0.72rem;text-transform:uppercase;letter-spacing:0.8px;color:#6b7090;padding:2px 0 4px;font-weight:600;'>Mode</div>", unsafe_allow_html=True)
_mode = st.sidebar.radio(
    "mode",
    ["🤖 AI Pipeline", "👤 My Analysis"],
    label_visibility="collapsed",
)
st.sidebar.markdown("---")

# ── Instrument selector ───────────────────────────────────────────────────────
st.sidebar.markdown("<div style='font-size:0.72rem;text-transform:uppercase;letter-spacing:0.8px;color:#6b7090;padding:2px 0 4px;font-weight:600;'>Instrument</div>", unsafe_allow_html=True)
_instrument = st.sidebar.selectbox(
    "Instrument",
    ["📈 Nasdaq 100 (NQ)", "📊 S&P 500 (ES)"],
    label_visibility="collapsed",
)
_instr_code = "NQ" if "NQ" in _instrument else "ES"
st.sidebar.markdown("---")

# ── History picker ─────────────────────────────────────────────────────────────
_source_options = []
_auto_instr_dir = _AUTO_ROOT / _instr_code
if (_auto_instr_dir / "pipeline_summary.json").exists():
    _source_options.append("📡 Latest run")
_hist_dir = _auto_instr_dir / "history"
if _hist_dir.exists():
    for _f in sorted(_hist_dir.glob("*.json"), reverse=True)[:20]:
        _source_options.append(f"🕐 {_f.stem}")
_source_options.append("📂 Upload my own data")

if _mode == "🤖 AI Pipeline":
    st.sidebar.markdown("<div style='font-size:0.72rem;text-transform:uppercase;letter-spacing:0.8px;color:#6b7090;padding:2px 0 4px;font-weight:600;'>Run</div>", unsafe_allow_html=True)
    _data_source = st.sidebar.selectbox("Run to view", _source_options, label_visibility="collapsed") if _source_options else "📂 Upload my own data"
else:
    _data_source = "📂 Upload my own data"

st.sidebar.markdown("---")
st.sidebar.markdown("<div style='font-size:0.7rem;color:#40435a;text-align:center;padding:4px 0;'>v2.0 · NQ/ES Trader</div>", unsafe_allow_html=True)

# ── Load pipeline summary based on mode + instrument + selected run ───────────
_pipeline_summary: dict = {}
_is_ai_mode  = (_mode == "🤖 AI Pipeline")
_is_my_mode  = (_mode == "👤 My Analysis")
_active_dir  = _auto_instr_dir  # results/auto/NQ or results/auto/ES

if _is_ai_mode and _data_source == "📡 Latest run":
    _csv_path = _active_dir / "latest_data.csv"
    if _csv_path.exists():
        st.session_state["csv_bytes"]    = _csv_path.read_bytes()
        st.session_state["csv_name"]     = f"{_instr_code}_latest.csv"
        st.session_state["instrument"]   = _instr_code
        st.session_state["_auto_loaded"] = True
    _ps = _active_dir / "pipeline_summary.json"
    if _ps.exists():
        try:
            _pipeline_summary = json.loads(_ps.read_text())
        except Exception:
            pass

elif _is_ai_mode and _data_source.startswith("🕐 "):
    _run_id   = _data_source[2:].strip()
    _hj       = _active_dir / "history" / f"{_run_id}.json"
    if _hj.exists():
        try:
            _pipeline_summary = json.loads(_hj.read_text())
        except Exception:
            pass
    _csv_path = _active_dir / "latest_data.csv"
    if _csv_path.exists():
        st.session_state["csv_bytes"]    = _csv_path.read_bytes()
        st.session_state["csv_name"]     = f"{_instr_code}_{_run_id}.csv"
        st.session_state["instrument"]   = _instr_code
        st.session_state["_auto_loaded"] = True

elif _data_source == "📂 Upload my own data":
    st.session_state["_manual_upload"] = True
    st.session_state.pop("_auto_loaded", None)


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Home":
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
        import plotly.graph_objects as go

        ps      = _pipeline_summary
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
        if _rules:
            direction_map = {"long_only": "Long only (buys only)", "short_only": "Short only (sells only)", "both": "Both directions"}
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
            fig_wf.update_layout(
                barmode="group", height=280,
                margin=dict(l=0, r=0, t=30, b=0),
                **_CHART,
                yaxis=dict(title="Points", gridcolor="rgba(255,255,255,0.1)"),
                legend=dict(orientation="h", y=1.15),
                title="Blue = trained on it  |  Green/Red = tested on data it had never seen",
            )
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


# ══════════════════════════════════════════════════════════════════════════════
# GET DATA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📥 Get Data":
    st.title("📥 Get Data")

    # ── Instrument selector ────────────────────────────────────────────────
    _INSTRUMENT_OPTIONS = {
        "📈 Nasdaq 100 Futures (NQ)": "NQ",
        "📊 S&P 500 Futures (ES)":    "ES",
        "📂 Upload my own CSV":        "UPLOAD",
    }
    _fetch_label = st.selectbox("Select instrument", list(_INSTRUMENT_OPTIONS.keys()))
    _fetch_instr = _INSTRUMENT_OPTIONS[_fetch_label]

    if _fetch_instr != "UPLOAD":
        _lookback = st.slider("Lookback (days)", 30, 730, 180)
        if st.button(f"⬇ Fetch {_fetch_label}", type="primary"):
            with st.spinner(f"Fetching {_fetch_label} H1 data…"):
                try:
                    sys.path.insert(0, str(Path(__file__).parent / "src"))
                    from fx_backtester.data.yfinance_loader import (
                        load_yfinance_h1, bars_to_csv, instrument_display_name, instrument_pip_size
                    )
                    import pandas as pd

                    _end   = date.today() - timedelta(days=1)
                    _start = _end - timedelta(days=_lookback)
                    _bars  = load_yfinance_h1(_fetch_instr, _start, _end, verbose=False)

                    if not _bars:
                        st.error("No data returned. Try a shorter lookback period.")
                    else:
                        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as _tf:
                            bars_to_csv(_bars, Path(_tf.name))
                            _csv_bytes = Path(_tf.name).read_bytes()

                        st.session_state["csv_bytes"]    = _csv_bytes
                        st.session_state["csv_name"]     = f"{_fetch_instr}_h1.csv"
                        st.session_state["instrument"]   = _fetch_instr
                        st.session_state["pip_size"]     = instrument_pip_size(_fetch_instr)
                        st.session_state["_auto_loaded"] = False

                        _df = pd.read_csv(io.BytesIO(_csv_bytes))
                        st.success(f"✅ Loaded **{len(_bars):,} bars** of {instrument_display_name(_fetch_instr)}")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Bars",  f"{len(_bars):,}")
                        c2.metric("From",  str(_df['timestamp'].iloc[0])[:10])
                        c3.metric("To",    str(_df['timestamp'].iloc[-1])[:10])
                        st.dataframe(_df.head(5), use_container_width=True)
                except Exception as e:
                    st.error(f"Fetch failed: {e}")

        # Show current loaded data info
        if "csv_bytes" in st.session_state:
            _loaded_instr = st.session_state.get("instrument", "")
            if _loaded_instr:
                st.info(f"Currently loaded: **{_loaded_instr}** — go to 🔬 Backtest to run analysis")

    else:
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
                    st.session_state["csv_name"]  = uploaded.name
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Bars", f"{len(df):,}")
                    col2.metric("From", str(df['timestamp'].iloc[0])[:10])
                    col3.metric("To",   str(df['timestamp'].iloc[-1])[:10])
                    st.dataframe(df.head(5), use_container_width=True)
            except Exception as e:
                st.error(f"Could not read file: {e}")


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
                _bt_pip_size = st.session_state.get("pip_size", 0.25)
                mae_mfe  = compute_mae_mfe(result.trades, prepared.bars,
                                           pip_size=_bt_pip_size,
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
            line=dict(color="#00c49a", width=2),
            fill="tozeroy", fillcolor="rgba(0,212,170,0.1)",
            name="Equity",
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=20, b=0),
            **_CHART,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True, key="backtest_equity_curve")

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
                       marker_color=["#00c49a" if p > 0 else "#ff4455" for p in oos_pips]),
            ])
            fig.update_layout(
                barmode="group", height=300,
                margin=dict(l=0, r=0, t=20, b=0),
                **_CHART,
                yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Net pips"),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True, key="wf_manual_fold_bars")


# ══════════════════════════════════════════════════════════════════════════════
# KEY LEVELS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📍 Key Levels":
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
                            fig.update_layout(
                                height=200, margin=dict(l=0,r=0,t=10,b=0),
                                **_CHART,
                                yaxis=dict(title="Avg pips", gridcolor="rgba(255,255,255,0.1)"),
                            )
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
                    fig.update_layout(
                        height=200, margin=dict(l=0,r=0,t=10,b=0),
                        **_CHART,
                        yaxis=dict(title="Avg pips", gridcolor="rgba(255,255,255,0.1)"),
                    )
                    st.plotly_chart(fig, use_container_width=True, key=f"levels_bar_{i}")


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
        colours  = ["#00c49a" if e.is_winner else "#ff4455" for e in r.excursions]
        labels   = [f"{e.trade_id} ({e.pnl_pips:+.1f} pips)" for e in r.excursions]
        fig = go.Figure(go.Scatter(
            x=mae_vals, y=mfe_vals, mode="markers",
            marker=dict(color=colours, size=8, opacity=0.8),
            text=labels, hoverinfo="text+x+y",
        ))
        fig.update_layout(
            height=350, margin=dict(l=0,r=0,t=20,b=0),
            **_CHART,
            xaxis=dict(title="MAE (pips — adverse)", gridcolor="rgba(255,255,255,0.1)"),
            yaxis=dict(title="MFE (pips — favorable)", gridcolor="rgba(255,255,255,0.1)"),
        )
        st.plotly_chart(fig, use_container_width=True, key="mae_mfe_scatter")
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
    import pandas as pd
    import plotly.express as px

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
                fig.update_layout(xaxis_tickangle=-45, **_CHART,
                                  yaxis=dict(gridcolor="rgba(255,255,255,0.1)"))
                st.plotly_chart(fig, use_container_width=True, key=f"history_pips_{instr}")

            st.caption(f"Total runs stored: {len(records)}")

    _render_history("NQ", _hist_tab_nq)
    _render_history("ES", _hist_tab_es)


# ══════════════════════════════════════════════════════════════════════════════
# TRADE JOURNAL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📒 Trade Journal":
    import uuid
    import pandas as pd
    import plotly.express as px

    st.title("📒 Trade Journal")

    _JOURNAL_PATH = _RESULTS / "journal" / "trades.json"
    _JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _load_trades() -> list[dict]:
        if _JOURNAL_PATH.exists():
            try:
                return json.loads(_JOURNAL_PATH.read_text())
            except Exception:
                return []
        return []

    def _save_trades(trades: list[dict]) -> None:
        _JOURNAL_PATH.write_text(json.dumps(trades, indent=2))

    def _calc_pnl(side, entry, exit_p, size, instrument):
        point = 20 if instrument == "NQ" else 50  # $ per point per contract
        points = (exit_p - entry) if side == "Long" else (entry - exit_p)
        return round(points * point * size, 2), round(points, 2)

    trades = _load_trades()

    tab1, tab2, tab3, tab4 = st.tabs(["➕ Log Trade", "📤 Import Tradovate", "📋 Trade Log", "📊 Analytics"])

    # ── TAB 1: LOG TRADE ──────────────────────────────────────────────────────
    with tab1:
        st.subheader("Log a New Trade")

        with st.form("new_trade_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            t_instrument = c1.selectbox("Instrument", ["NQ — Nasdaq 100", "ES — S&P 500"])
            t_side       = c2.selectbox("Side", ["Long", "Short"])

            c1, c2, c3 = st.columns(3)
            t_date  = c1.date_input("Date")
            t_time  = c2.time_input("Entry time")
            t_size  = c3.number_input("Contracts", 1, 100, 1)

            c1, c2, c3, c4 = st.columns(4)
            t_entry = c1.number_input("Entry price", value=0.0, format="%.2f")
            t_exit  = c2.number_input("Exit price",  value=0.0, format="%.2f")
            t_sl    = c3.number_input("Stop loss",   value=0.0, format="%.2f")
            t_tp    = c4.number_input("Take profit",  value=0.0, format="%.2f")

            c1, c2 = st.columns(2)
            t_setup = c1.selectbox("Setup type", [
                "PDH Rejection", "PDL Bounce",
                "PWH Rejection", "PWL Bounce",
                "Session High Break", "Session Low Break",
                "Opening Range Break", "VWAP Reclaim",
                "Trend Continuation", "Reversal", "Custom",
            ])
            t_session = c2.selectbox("Session", ["New York", "Pre-Market", "London", "Overnight"])

            c1, c2 = st.columns(2)
            t_emotion = c1.selectbox("Mindset", ["Confident", "Patient", "Hesitant", "Rushed", "FOMO", "Revenge"])
            t_grade   = c2.selectbox("Trade grade", ["A+ Setup", "A Setup", "B Setup", "C Setup", "Mistake"])

            t_notes = st.text_area("Notes / observations", placeholder="What did you see? Why did you take it? What happened?")

            submitted = st.form_submit_button("💾 Save Trade", type="primary", use_container_width=True)

        if submitted and t_entry > 0 and t_exit > 0:
            instr_code = "NQ" if "NQ" in t_instrument else "ES"
            pnl_usd, pnl_pts = _calc_pnl(t_side, t_entry, t_exit, t_size, instr_code)
            r_multiple = round(pnl_pts / abs(t_entry - t_sl), 2) if t_sl and t_sl != t_entry else None

            new_trade = {
                "id":         str(uuid.uuid4())[:8],
                "date":       t_date.isoformat(),
                "time":       t_time.strftime("%H:%M"),
                "instrument": instr_code,
                "side":       t_side,
                "size":       int(t_size),
                "entry":      t_entry,
                "exit":       t_exit,
                "stop_loss":  t_sl,
                "take_profit":t_tp,
                "pnl_usd":    pnl_usd,
                "pnl_points": pnl_pts,
                "r_multiple": r_multiple,
                "result":     "Win" if pnl_usd > 0 else ("Loss" if pnl_usd < 0 else "BE"),
                "setup":      t_setup,
                "session":    t_session,
                "emotion":    t_emotion,
                "grade":      t_grade,
                "notes":      t_notes,
            }
            trades.append(new_trade)
            _save_trades(trades)
            st.success(f"✅ Trade saved! P&L: **{'${:+,.2f}'.format(pnl_usd)}** ({pnl_pts:+.2f} pts)")
            st.rerun()
        elif submitted:
            st.warning("Enter valid entry and exit prices.")

    # ── TAB 2: IMPORT TRADOVATE ───────────────────────────────────────────────
    with tab2:
        import requests as _requests
        from collections import deque as _deque

        _TV_URLS = {
            "Live account": "https://live.tradovateapi.com/v1",
            "Demo account": "https://demo.tradovateapi.com/v1",
        }

        def _tv_auth(base, user, pwd):
            r = _requests.post(f"{base}/auth/accesstokenrequest", json={
                "name": user, "password": pwd,
                "appId": "FX Backtester", "appVersion": "1.0",
                "cid": 0, "sec": "",
            }, timeout=15)
            r.raise_for_status()
            d = r.json()
            if "errorText" in d:
                raise ValueError(d["errorText"])
            return d["accessToken"], d.get("userId")

        def _tv_get(base, token, path):
            r = _requests.get(f"{base}/{path}",
                              headers={"Authorization": f"Bearer {token}"},
                              timeout=15)
            r.raise_for_status()
            return r.json()

        def _resolve_instrument(name: str) -> str:
            n = (name or "").upper()
            if "MNQ" in n: return "MNQ"
            if "NQ"  in n: return "NQ"
            if "MES" in n: return "MES"
            if "ES"  in n: return "ES"
            return n[:2]

        def _fifo_match(fills: list[dict], contract_map: dict) -> list[dict]:
            """Pair fills into round-trip trades using FIFO matching."""
            from collections import defaultdict
            queues: dict = defaultdict(lambda: {"Buy": _deque(), "Sell": _deque()})
            closed: list[dict] = []

            for f in sorted(fills, key=lambda x: x.get("timestamp", "")):
                cid    = f.get("contractId")
                name   = contract_map.get(cid, str(cid))
                instr  = _resolve_instrument(name)
                action = f.get("action", "")        # "Buy" or "Sell"
                qty    = int(f.get("qty", 1))
                price  = float(f.get("price", 0))
                ts     = f.get("timestamp", "")
                mult   = 20 if "NQ" in instr else 50

                opp = "Sell" if action == "Buy" else "Buy"
                q   = queues[cid][opp]

                remaining = qty
                while remaining > 0 and q:
                    open_f = q[0]
                    matched = min(remaining, open_f["qty"])
                    open_f["qty"] -= matched
                    remaining     -= matched
                    if open_f["qty"] == 0:
                        q.popleft()

                    entry_p  = open_f["price"] if action == "Sell" else price
                    exit_p   = price           if action == "Sell" else open_f["price"]
                    side     = "Long"          if action == "Sell" else "Short"
                    pts      = (exit_p - entry_p) if side == "Long" else (entry_p - exit_p)
                    pnl_usd  = round(pts * mult * matched, 2)
                    entry_ts = open_f["ts"]    if action == "Sell" else ts
                    exit_ts  = ts              if action == "Sell" else open_f["ts"]

                    try:
                        _edt = _pd.to_datetime(entry_ts)
                    except Exception:
                        _edt = _pd.Timestamp.now()
                    closed.append({
                        "id":          str(uuid.uuid4())[:8],
                        "date":        _edt.date().isoformat(),
                        "time":        _edt.strftime("%H:%M"),
                        "instrument":  instr,
                        "side":        side,
                        "size":        matched,
                        "entry":       entry_p,
                        "exit":        exit_p,
                        "stop_loss":   0.0,
                        "take_profit": 0.0,
                        "pnl_usd":     pnl_usd,
                        "pnl_points":  round(pts, 2),
                        "r_multiple":  None,
                        "result":      "Win" if pnl_usd > 0 else ("Loss" if pnl_usd < 0 else "BE"),
                        "setup":       "Imported",
                        "session":     "New York",
                        "emotion":     "Confident",
                        "grade":       "A Setup",
                        "notes":       f"Auto-imported from Tradovate — {name}",
                        "source":      "tradovate_api",
                    })

                # leftover goes into the open queue
                if remaining > 0:
                    queues[cid][action].append({
                        "qty": remaining, "price": price, "ts": ts
                    })

            return closed

        # ── UI ──────────────────────────────────────────────────────────
        st.subheader("🔗 Connect Tradovate")
        st.markdown(
            "Enter your Tradovate login once. Your credentials are **never stored** — "
            "they're used only to get a short-lived token from Tradovate's servers, "
            "then discarded immediately."
        )
        st.info("🔒 Credentials live in your browser session only. Closing the tab clears them.")

        with st.form("tv_connect_form"):
            c1, c2 = st.columns(2)
            _tv_user = c1.text_input("Tradovate username / email")
            _tv_pass = c2.text_input("Password", type="password")
            c1, c2 = st.columns(2)
            _tv_env  = c1.selectbox("Account type", list(_TV_URLS.keys()))
            _tv_days = c2.number_input("Sync last N days", 1, 365, 90)
            _tv_submit = st.form_submit_button("🔗 Connect & Sync Trades", type="primary", use_container_width=True)

        if _tv_submit:
            if not _tv_user or not _tv_pass:
                st.warning("Enter your Tradovate username and password.")
            else:
                _base = _TV_URLS[_tv_env]
                with st.spinner("Connecting to Tradovate…"):
                    try:
                        import pandas as _pd
                        _token, _uid = _tv_auth(_base, _tv_user, _tv_pass)
                        st.success("✅ Connected to Tradovate.")

                        with st.spinner("Fetching accounts…"):
                            _accounts = _tv_get(_base, _token, "account/list") or []

                        with st.spinner(f"Fetching fills for last {_tv_days} days…"):
                            _fills_raw = _tv_get(_base, _token, "fill/list") or []
                            _contracts_raw = _tv_get(_base, _token, "contract/list") or []

                        # Build contract id → name map
                        _cmap = {c["id"]: c.get("name","") for c in _contracts_raw}

                        # Filter to date range
                        _since = (_pd.Timestamp.now(tz="UTC") - _pd.Timedelta(days=int(_tv_days)))
                        _fills = []
                        for f in _fills_raw:
                            try:
                                _ts = _pd.to_datetime(f.get("timestamp",""), utc=True)
                                if _ts >= _since:
                                    _fills.append(f)
                            except Exception:
                                _fills.append(f)

                        st.info(f"Found **{len(_fills)} fills** across {len(_accounts)} account(s).")

                        if _fills:
                            _matched = _fifo_match(_fills, _cmap)
                            st.info(f"Matched into **{len(_matched)} round-trip trades**.")

                            if _matched:
                                _preview_df = _pd.DataFrame(_matched)[
                                    ["date","time","instrument","side","size","entry","exit","pnl_usd","pnl_points","result"]
                                ]
                                st.dataframe(_preview_df, use_container_width=True)

                                # Deduplicate against existing trades
                                _existing_keys = {
                                    (t.get("date"), t.get("time"), t.get("instrument"),
                                     t.get("entry"), t.get("exit"), t.get("size"))
                                    for t in trades
                                }
                                _new = [
                                    t for t in _matched
                                    if (t["date"], t["time"], t["instrument"],
                                        t["entry"], t["exit"], t["size"]) not in _existing_keys
                                ]
                                st.success(
                                    f"**{len(_new)} new trades** to import "
                                    f"({len(_matched) - len(_new)} already in journal)."
                                )
                                if _new and st.button("⬇ Import All New Trades", type="primary"):
                                    trades.extend(_new)
                                    _save_trades(trades)
                                    st.success(f"✅ Imported {len(_new)} trades. Go to 📋 Trade Log to add your notes.")
                                    st.rerun()
                        else:
                            st.info("No fills found in this date range. Try a longer period.")

                    except ValueError as e:
                        st.error(f"Login failed: {e}")
                        st.caption("Check your username and password, and make sure you selected the right account type (Live vs Demo).")
                    except _requests.exceptions.HTTPError as e:
                        st.error(f"Tradovate API error: {e}")
                    except _requests.exceptions.ConnectionError:
                        st.error("Could not reach Tradovate's servers. Check your internet connection.")
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")

        st.markdown("---")
        st.caption("Alternatively, upload a CSV export from Tradovate → Account → History.")
        tv_file = st.file_uploader("Upload Tradovate CSV (optional fallback)", type=["csv"], key="tradovate_upload")
        if tv_file:
            try:
                import pandas as _pd
                tv_df = _pd.read_csv(tv_file)
                _col_map = {c.lower().replace(" ","").replace("_",""): c for c in tv_df.columns}
                def _fc(*cands):
                    for c in cands:
                        if c in _col_map: return _col_map[c]
                _cc = _fc("contractname","symbol","contract","instrument")
                _cs = _fc("side","buysell","action","direction")
                _cq = _fc("qty","quantity","size","contracts")
                _cp = _fc("price","fillprice","avgprice","executionprice")
                _cd = _fc("datetime","timestamp","time","date","filltime","tradetime")
                _cn = _fc("realizedpnl","pnl","realizedpl","profit","gainloss")
                missing = [n for n,c in [("contract",_cc),("side",_cs),("qty",_cq),("price",_cp),("datetime",_cd)] if c is None]
                if missing:
                    st.warning(f"Couldn't find columns: {', '.join(missing)}")
                else:
                    closed = tv_df[tv_df[_cn].notna() & (tv_df[_cn] != 0)] if _cn else tv_df
                    st.info(f"Found **{len(closed)} trades** in CSV.")
                    if st.button("⬇ Import CSV", type="secondary"):
                        imported = 0
                        for _, row in closed.iterrows():
                            try:
                                instr = _resolve_instrument(str(row[_cc]))
                                side  = "Long" if str(row[_cs]).lower() in ("buy","b","long","bot") else "Short"
                                qty   = int(float(row[_cq]))
                                price = float(row[_cp])
                                rdt   = _pd.to_datetime(row[_cd])
                                pnl   = float(row[_cn]) if _cn else 0.0
                                mult  = 20 if instr == "NQ" else 50
                                pts   = pnl / (mult * qty) if qty > 0 else 0.0
                                trades.append({"id": str(uuid.uuid4())[:8], "date": rdt.date().isoformat(),
                                    "time": rdt.strftime("%H:%M"), "instrument": instr, "side": side, "size": qty,
                                    "entry": price, "exit": round(price + pts if side=="Long" else price - pts, 2),
                                    "stop_loss": 0.0, "take_profit": 0.0, "pnl_usd": pnl, "pnl_points": round(pts,2),
                                    "r_multiple": None, "result": "Win" if pnl>0 else ("Loss" if pnl<0 else "BE"),
                                    "setup": "Imported", "session": "New York", "emotion": "Confident",
                                    "grade": "A Setup", "notes": f"CSV import — {row[_cc]}", "source": "tradovate_csv"})
                                imported += 1
                            except Exception: pass
                        _save_trades(trades)
                        st.success(f"✅ Imported {imported} trades.")
                        st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")
        if tv_file:
            try:
                import pandas as pd
                tv_df = pd.read_csv(tv_file)
                st.markdown("**Preview (first 5 rows):**")
                st.dataframe(tv_df.head(), use_container_width=True)
                st.markdown("**Columns detected:** " + ", ".join(f"`{c}`" for c in tv_df.columns))

                # Tradovate column mapping — handles common export formats
                # Common Tradovate columns: AccountId, ContractName, Side (Buy/Sell),
                # Qty, Price, DateTime, Commission, RealizedPnL
                _col_map = {c.lower().replace(" ", "").replace("_", ""): c for c in tv_df.columns}

                def _find_col(*candidates):
                    for c in candidates:
                        if c in _col_map:
                            return _col_map[c]
                    return None

                _col_contract = _find_col("contractname", "symbol", "contract", "instrument")
                _col_side     = _find_col("side", "buysell", "action", "direction")
                _col_qty      = _find_col("qty", "quantity", "size", "contracts")
                _col_price    = _find_col("price", "fillprice", "avgprice", "executionprice")
                _col_dt       = _find_col("datetime", "timestamp", "time", "date", "filltime", "tradetime")
                _col_pnl      = _find_col("realizedpnl", "pnl", "realizedpl", "profit", "gainloss")

                missing = [n for n, c in [("contract", _col_contract), ("side", _col_side),
                                           ("qty", _col_qty), ("price", _col_price), ("datetime", _col_dt)]
                           if c is None]
                if missing:
                    st.warning(f"Could not find columns for: **{', '.join(missing)}**. "
                               f"Make sure you exported the full trade history (not just positions).")
                else:
                    # Tradovate exports fills — we need to pair Buy+Sell fills into round trips
                    # Simple approach: treat each row as a closed trade if PnL column exists,
                    # otherwise require paired fills
                    if _col_pnl:
                        # Filter to closing fills only (where PnL is populated)
                        closed = tv_df[tv_df[_col_pnl].notna()].copy()
                        closed = closed[closed[_col_pnl] != 0]
                    else:
                        closed = tv_df.copy()

                    st.info(f"Found **{len(closed)} trades** ready to import.")

                    if st.button("⬇ Import All Trades", type="primary"):
                        imported = 0
                        skipped  = 0
                        for _, row in closed.iterrows():
                            try:
                                contract = str(row[_col_contract])
                                instr    = "NQ" if "NQ" in contract.upper() else ("ES" if "ES" in contract.upper() else contract[:2].upper())
                                raw_side = str(row[_col_side]).strip().lower()
                                side     = "Long" if raw_side in ("buy", "b", "long", "bot") else "Short"
                                qty      = int(float(row[_col_qty]))
                                price    = float(row[_col_price])
                                raw_dt   = pd.to_datetime(row[_col_dt])
                                pnl_usd  = float(row[_col_pnl]) if _col_pnl else 0.0
                                # Back-calculate exit price from PnL
                                mult     = 20 if instr == "NQ" else 50
                                if pnl_usd != 0 and qty > 0:
                                    pts  = pnl_usd / (mult * qty)
                                    entry_approx = price
                                    exit_approx  = round(price + pts if side == "Long" else price - pts, 2)
                                else:
                                    entry_approx = price
                                    exit_approx  = price
                                new_trade = {
                                    "id":          str(uuid.uuid4())[:8],
                                    "date":        raw_dt.date().isoformat(),
                                    "time":        raw_dt.strftime("%H:%M"),
                                    "instrument":  instr,
                                    "side":        side,
                                    "size":        qty,
                                    "entry":       entry_approx,
                                    "exit":        exit_approx,
                                    "stop_loss":   0.0,
                                    "take_profit": 0.0,
                                    "pnl_usd":     pnl_usd,
                                    "pnl_points":  round(pnl_usd / (mult * qty), 2) if qty > 0 else 0.0,
                                    "r_multiple":  None,
                                    "result":      "Win" if pnl_usd > 0 else ("Loss" if pnl_usd < 0 else "BE"),
                                    "setup":       "Imported",
                                    "session":     "New York",
                                    "emotion":     "Confident",
                                    "grade":       "A Setup",
                                    "notes":       f"Imported from Tradovate — {contract}",
                                    "source":      "tradovate",
                                }
                                trades.append(new_trade)
                                imported += 1
                            except Exception:
                                skipped += 1
                        _save_trades(trades)
                        st.success(f"✅ Imported **{imported} trades** ({skipped} skipped). Go to 📋 Trade Log to review.")
                        if imported > 0:
                            st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")
                st.markdown("Make sure you're uploading the CSV export from Tradovate → Account → History.")

    # ── TAB 3: TRADE LOG ──────────────────────────────────────────────────────
    with tab3:
        st.subheader("Trade Log")

        if not trades:
            st.info("No trades logged yet. Add your first trade in the **➕ Log Trade** tab.")
        else:
            df = pd.DataFrame(trades)

            # Filters
            c1, c2, c3 = st.columns(3)
            _f_instr  = c1.multiselect("Instrument", ["NQ", "ES"], default=["NQ", "ES"])
            _f_result = c2.multiselect("Result", ["Win", "Loss", "BE"], default=["Win", "Loss", "BE"])
            _f_setup  = c3.multiselect("Setup", df["setup"].unique().tolist(), default=df["setup"].unique().tolist())

            _mask = (df["instrument"].isin(_f_instr) & df["result"].isin(_f_result) & df["setup"].isin(_f_setup))
            df_f = df[_mask].copy()

            # Colour P&L column
            st.dataframe(
                df_f[["date","time","instrument","side","size","entry","exit","pnl_usd","pnl_points","r_multiple","result","setup","session","grade"]].sort_values("date", ascending=False),
                use_container_width=True,
                column_config={
                    "pnl_usd":    st.column_config.NumberColumn("P&L $",    format="$%.2f"),
                    "pnl_points": st.column_config.NumberColumn("Points",   format="%.2f"),
                    "r_multiple": st.column_config.NumberColumn("R",        format="%.2f"),
                    "entry":      st.column_config.NumberColumn("Entry",    format="%.2f"),
                    "exit":       st.column_config.NumberColumn("Exit",     format="%.2f"),
                },
            )

            # Delete trade
            with st.expander("🗑 Delete a trade"):
                _del_ids = [f"{t['date']} {t['time']} {t['instrument']} {t['side']} ${t['pnl_usd']:+.0f} [{t['id']}]" for t in trades]
                _to_del  = st.selectbox("Select trade to delete", _del_ids)
                if st.button("Delete", type="secondary"):
                    _del_id = _to_del.split("[")[-1].rstrip("]")
                    trades  = [t for t in trades if t["id"] != _del_id]
                    _save_trades(trades)
                    st.success("Deleted.")
                    st.rerun()

    # ── TAB 4: ANALYTICS ──────────────────────────────────────────────────────
    with tab4:
        if not trades:
            st.info("Log some trades first to see analytics.")
        else:
            df = pd.DataFrame(trades)
            df["date"] = pd.to_datetime(df["date"])
            df["week"] = df["date"].dt.to_period("W").astype(str)
            df["month"] = df["date"].dt.to_period("M").astype(str)
            df["dow"]   = df["date"].dt.day_name()
            df["cum_pnl"] = df.sort_values("date")["pnl_usd"].cumsum()
            wins   = df[df["result"] == "Win"]
            losses = df[df["result"] == "Loss"]

            # ── KPI strip ─────────────────────────────────────────────────
            st.markdown("### Overview")
            k1,k2,k3,k4,k5,k6 = st.columns(6)
            total_pnl   = df["pnl_usd"].sum()
            win_rate    = len(wins)/len(df) if len(df) else 0
            avg_win     = wins["pnl_usd"].mean() if len(wins) else 0
            avg_loss    = losses["pnl_usd"].mean() if len(losses) else 0
            pf          = abs(wins["pnl_usd"].sum() / losses["pnl_usd"].sum()) if len(losses) and losses["pnl_usd"].sum() != 0 else 0
            avg_r       = df["r_multiple"].dropna().mean() if "r_multiple" in df else 0

            k1.metric("Total P&L",    f"${total_pnl:+,.2f}")
            k2.metric("Trades",        len(df))
            k3.metric("Win Rate",      f"{win_rate:.0%}")
            k4.metric("Avg Winner",   f"${avg_win:+,.2f}")
            k5.metric("Avg Loser",    f"${avg_loss:+,.2f}")
            k6.metric("Profit Factor", f"{pf:.2f}")

            st.markdown("---")

            # ── Equity curve ──────────────────────────────────────────────
            st.markdown("### 📈 Equity Curve")
            _eq = df.sort_values("date").reset_index(drop=True)
            _eq["cum_pnl"] = _eq["pnl_usd"].cumsum()
            _eq["trade_n"] = range(1, len(_eq)+1)
            fig_eq = px.area(_eq, x="trade_n", y="cum_pnl",
                             color_discrete_sequence=["#00c49a"],
                             labels={"trade_n": "Trade #", "cum_pnl": "Cumulative P&L ($)"},
                             title="Cumulative P&L")
            fig_eq.update_layout(**_CHART,
                                  yaxis=dict(gridcolor="rgba(255,255,255,0.1)"))
            fig_eq.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
            st.plotly_chart(fig_eq, use_container_width=True, key="journal_equity")

            # ── R distribution ────────────────────────────────────────────
            if df["r_multiple"].notna().sum() > 2:
                st.markdown("### 🎯 R-Multiple Distribution")
                fig_r = px.histogram(df.dropna(subset=["r_multiple"]), x="r_multiple",
                                     nbins=20, color_discrete_sequence=["#5588ff"],
                                     labels={"r_multiple": "R-Multiple"},
                                     title="Distribution of R-multiples (1R = risk per trade)")
                fig_r.add_vline(x=0, line_dash="dash", line_color="white")
                fig_r.update_layout(**_CHART)
                st.plotly_chart(fig_r, use_container_width=True, key="journal_r_dist")

            # ── By session ────────────────────────────────────────────────
            st.markdown("### 🕐 Performance by Session")
            _sess = df.groupby("session").agg(
                Trades=("pnl_usd","count"),
                Total_PnL=("pnl_usd","sum"),
                Win_Rate=("result", lambda x: (x=="Win").mean()),
                Avg_PnL=("pnl_usd","mean"),
            ).reset_index()
            c1, c2 = st.columns(2)
            fig_s1 = px.bar(_sess, x="session", y="Total_PnL",
                            color="Total_PnL", color_continuous_scale=["#ff4455","#00c49a"],
                            title="Total P&L by Session")
            fig_s1.update_layout(**_CHART)
            c1.plotly_chart(fig_s1, use_container_width=True, key="journal_session_pnl")

            fig_s2 = px.bar(_sess, x="session", y="Win_Rate",
                            color="Win_Rate", color_continuous_scale=["#ff4455","#00c49a"],
                            title="Win Rate by Session")
            fig_s2.update_layout(**_CHART)
            c2.plotly_chart(fig_s2, use_container_width=True, key="journal_session_wr")

            # ── By day of week ────────────────────────────────────────────
            st.markdown("### 📅 Performance by Day of Week")
            _dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
            _dow = df.groupby("dow").agg(
                Trades=("pnl_usd","count"),
                Total_PnL=("pnl_usd","sum"),
                Win_Rate=("result", lambda x: (x=="Win").mean()),
            ).reindex(_dow_order).reset_index()
            c1, c2 = st.columns(2)
            fig_d1 = px.bar(_dow, x="dow", y="Total_PnL",
                            color="Total_PnL", color_continuous_scale=["#ff4455","#00c49a"],
                            title="Total P&L by Day")
            fig_d1.update_layout(**_CHART)
            c1.plotly_chart(fig_d1, use_container_width=True, key="journal_dow_pnl")

            fig_d2 = px.bar(_dow, x="dow", y="Win_Rate",
                            color="Win_Rate", color_continuous_scale=["#ff4455","#00c49a"],
                            title="Win Rate by Day")
            fig_d2.update_layout(**_CHART)
            c2.plotly_chart(fig_d2, use_container_width=True, key="journal_dow_wr")

            # ── By setup ──────────────────────────────────────────────────
            st.markdown("### 🎯 Performance by Setup")
            _setup = df.groupby("setup").agg(
                Trades=("pnl_usd","count"),
                Total_PnL=("pnl_usd","sum"),
                Win_Rate=("result", lambda x: (x=="Win").mean()),
                Avg_PnL=("pnl_usd","mean"),
            ).sort_values("Total_PnL", ascending=False).reset_index()
            st.dataframe(_setup, use_container_width=True,
                         column_config={
                             "Total_PnL": st.column_config.NumberColumn("Total P&L", format="$%.2f"),
                             "Avg_PnL":   st.column_config.NumberColumn("Avg P&L",   format="$%.2f"),
                             "Win_Rate":  st.column_config.NumberColumn("Win Rate",  format="%.0%"),
                         })

            fig_setup = px.bar(_setup, x="setup", y="Total_PnL",
                               color="Total_PnL", color_continuous_scale=["#ff4455","#00c49a"],
                               title="P&L by Setup Type")
            fig_setup.update_layout(**_CHART,
                                     xaxis_tickangle=-30)
            st.plotly_chart(fig_setup, use_container_width=True, key="journal_setup_pnl")

            # ── Monthly breakdown ─────────────────────────────────────────
            st.markdown("### 📆 Monthly Breakdown")
            _monthly = df.groupby("month").agg(
                Trades=("pnl_usd","count"),
                Total_PnL=("pnl_usd","sum"),
                Win_Rate=("result", lambda x: (x=="Win").mean()),
                Best_Trade=("pnl_usd","max"),
                Worst_Trade=("pnl_usd","min"),
            ).reset_index()
            st.dataframe(_monthly, use_container_width=True,
                         column_config={
                             "Total_PnL":   st.column_config.NumberColumn("Total P&L",   format="$%.2f"),
                             "Best_Trade":  st.column_config.NumberColumn("Best Trade",  format="$%.2f"),
                             "Worst_Trade": st.column_config.NumberColumn("Worst Trade", format="$%.2f"),
                             "Win_Rate":    st.column_config.NumberColumn("Win Rate",    format="%.0%"),
                         })
            fig_mon = px.bar(_monthly, x="month", y="Total_PnL",
                             color="Total_PnL", color_continuous_scale=["#ff4455","#00c49a"],
                             title="Monthly P&L")
            fig_mon.update_layout(**_CHART)
            st.plotly_chart(fig_mon, use_container_width=True, key="journal_monthly_pnl")

            # ── Mindset analysis ──────────────────────────────────────────
            st.markdown("### 🧠 Mindset vs Performance")
            _mind = df.groupby("emotion").agg(
                Trades=("pnl_usd","count"),
                Total_PnL=("pnl_usd","sum"),
                Win_Rate=("result", lambda x: (x=="Win").mean()),
            ).sort_values("Win_Rate", ascending=False).reset_index()
            fig_mind = px.bar(_mind, x="emotion", y="Win_Rate",
                              color="Win_Rate", color_continuous_scale=["#ff4455","#00c49a"],
                              title="Win Rate by Mindset")
            fig_mind.update_layout(**_CHART)
            st.plotly_chart(fig_mind, use_container_width=True, key="journal_mindset")

            # ── Trade grade analysis ──────────────────────────────────────
            st.markdown("### 🏅 Trade Grade vs Performance")
            _grade = df.groupby("grade").agg(
                Trades=("pnl_usd","count"),
                Total_PnL=("pnl_usd","sum"),
                Win_Rate=("result", lambda x: (x=="Win").mean()),
                Avg_PnL=("pnl_usd","mean"),
            ).reset_index()
            c1, c2 = st.columns(2)
            fig_g1 = px.bar(_grade, x="grade", y="Win_Rate",
                            color="Win_Rate", color_continuous_scale=["#ff4455","#00c49a"],
                            title="Win Rate by Grade")
            fig_g1.update_layout(**_CHART)
            c1.plotly_chart(fig_g1, use_container_width=True, key="journal_grade_wr")

            fig_g2 = px.bar(_grade, x="grade", y="Avg_PnL",
                            color="Avg_PnL", color_continuous_scale=["#ff4455","#00c49a"],
                            title="Avg P&L by Grade")
            fig_g2.update_layout(**_CHART)
            c2.plotly_chart(fig_g2, use_container_width=True, key="journal_grade_pnl")

            # ── Win/loss streaks ──────────────────────────────────────────
            st.markdown("### 🔥 Streaks")
            _results = df.sort_values("date")["result"].tolist()
            _cur_streak = 1
            _max_win_streak = _max_loss_streak = 0
            _cur_type = _results[0] if _results else None
            for r in _results[1:]:
                if r == _cur_type:
                    _cur_streak += 1
                else:
                    if _cur_type == "Win":  _max_win_streak  = max(_max_win_streak,  _cur_streak)
                    if _cur_type == "Loss": _max_loss_streak = max(_max_loss_streak, _cur_streak)
                    _cur_streak = 1
                    _cur_type = r
            if _cur_type == "Win":  _max_win_streak  = max(_max_win_streak,  _cur_streak)
            if _cur_type == "Loss": _max_loss_streak = max(_max_loss_streak, _cur_streak)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Max Win Streak",  f"{_max_win_streak} 🔥")
            c2.metric("Max Loss Streak", f"{_max_loss_streak} 🥶")
            c3.metric("Avg R",           f"{avg_r:.2f}R" if avg_r else "—")
            c4.metric("Best Trade",      f"${df['pnl_usd'].max():+,.2f}")


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

The easiest option is to **fetch data directly** — no CSV needed:

1. Go to **📥 Get Data**
2. Select **Nasdaq 100 (NQ)** or **S&P 500 (ES)**
3. Choose your lookback window (e.g. 180 days)
4. Click **Fetch** — data downloads automatically via Yahoo Finance

Alternatively you can upload your own OHLC CSV with these columns:
```
timestamp, open, high, low, close
```

The **🤖 AI Pipeline** also fetches and analyses data automatically every 7 hours — check the **🏠 Home** tab to see the latest results.

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

This means: when NQ hits the previous day high, it rejects 61% of the time,
and when it rejects, price drops an average of 8.3 points over the next 5 candles.
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
| 📥 Get Data | Fetch NQ/ES data or upload your own CSV |
| 🔬 Backtest | Run your strategy and see the equity curve |
| 📊 MAE/MFE | Check if stops and TPs are correctly sized |
| 🔍 Grid Search | Find the best settings for your strategy |
| 🔄 Walk-Forward | Confirm the edge holds across different time periods |
| 📍 Key Levels | See how price reacts at daily/weekly/session highs and lows |

---

*Built with real data. Always paper trade before using real money.*
""")
