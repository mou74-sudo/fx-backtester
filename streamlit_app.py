"""FX Backtester — Streamlit Dashboard

Works on desktop and mobile.

Run locally:
    streamlit run streamlit_app.py

Deploy to Streamlit Cloud:
    1. Push this repo to GitHub
    2. Go to share.streamlit.io → New app → select this repo
    3. Share the URL with your mate
"""
import json
from pathlib import Path

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

# ── Navigation ────────────────────────────────────────────────────────────────
PAGES = [
    "🏠 Home", "📥 Get Data", "🔬 Backtest", "🔄 Walk-Forward",
    "📍 Key Levels", "📊 MAE / MFE", "🔍 Grid Search",
    "📈 History", "📒 Trade Journal", "📖 How to Use",
]
page = st.sidebar.radio("Navigate", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")

# ── Paths ─────────────────────────────────────────────────────────────────────
_RESULTS   = Path("results")
_AUTO_ROOT = _RESULTS / "auto"

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
_instr_code     = "NQ" if "NQ" in _instrument else "ES"
_auto_instr_dir = _AUTO_ROOT / _instr_code
st.sidebar.markdown("---")

# ── History picker ─────────────────────────────────────────────────────────────
_source_options: list[str] = []
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

    # ── Refresh button ────────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("<div style='font-size:0.72rem;text-transform:uppercase;letter-spacing:0.8px;color:#6b7090;padding:2px 0 4px;font-weight:600;'>Pipeline</div>", unsafe_allow_html=True)
    if st.sidebar.button(f"🔄 Refresh {_instr_code} Data", type="primary", use_container_width=True,
                         help=f"Fetch fresh data and re-run the full AI pipeline for {_instr_code}"):
        import subprocess, sys
        _pl_script = Path(__file__).parent / "scripts" / "run_pipeline.py"
        with st.spinner(f"Running pipeline for {_instr_code} — this takes ~1 min…"):
            _proc = subprocess.run(
                [sys.executable, str(_pl_script), "180", _instr_code],
                capture_output=True, text=True,
            )
        if _proc.returncode == 0:
            st.sidebar.success(f"✓ {_instr_code} pipeline complete — reloading…")
            st.rerun()
        else:
            st.sidebar.error("Pipeline failed.")
            st.sidebar.code(_proc.stderr[-800:] or _proc.stdout[-800:], language="text")
else:
    _data_source = "📂 Upload my own data"

st.sidebar.markdown("---")
st.sidebar.markdown("<div style='font-size:0.7rem;color:#40435a;text-align:center;padding:4px 0;'>v2.0 · NQ/ES Trader</div>", unsafe_allow_html=True)

# ── Load pipeline summary ─────────────────────────────────────────────────────
_pipeline_summary: dict = {}
_is_ai_mode = (_mode == "🤖 AI Pipeline")
_active_dir = _auto_instr_dir

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
    _run_id = _data_source[2:].strip()
    _hj     = _active_dir / "history" / f"{_run_id}.json"
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
# PAGE DISPATCH
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Home":
    from pages_impl.page_home import render as _render
    _render(_instr_code, _active_dir, _pipeline_summary, _is_ai_mode, (_mode == "👤 My Analysis"))

elif page == "📥 Get Data":
    from pages_impl.page_get_data import render as _render
    _render()

elif page == "🔬 Backtest":
    from pages_impl.page_backtest import render as _render
    _render()

elif page == "🔄 Walk-Forward":
    from pages_impl.page_walk_forward import render as _render
    _render(_instr_code, _active_dir)

elif page == "📍 Key Levels":
    from pages_impl.page_key_levels import render as _render
    _render(_instr_code, _active_dir)

elif page == "📊 MAE / MFE":
    from pages_impl.page_mae_mfe import render as _render
    _render()

elif page == "🔍 Grid Search":
    from pages_impl.page_grid_search import render as _render
    _render()

elif page == "📈 History":
    from pages_impl.page_history import render as _render
    _render(_AUTO_ROOT)

elif page == "📒 Trade Journal":
    from pages_impl.page_trade_journal import render as _render
    _render(_RESULTS)

elif page == "📖 How to Use":
    from pages_impl.page_how_to_use import render as _render
    _render()
