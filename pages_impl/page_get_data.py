import io
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render() -> None:
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
        _TF_OPTIONS = {
            "5 min  (max 60 days)":  ("5m",  60),
            "15 min (max 60 days)":  ("15m", 60),
            "30 min (max 60 days)":  ("30m", 60),
            "1 hour (max 730 days)": ("1h",  730),
            "4 hour (max 730 days)": ("4h",  730),
            "Daily  (max 10 years)": ("1d",  3650),
        }
        _tf_label  = st.selectbox("Timeframe", list(_TF_OPTIONS.keys()), index=3)
        _tf_code, _tf_max_days = _TF_OPTIONS[_tf_label]
        _lookback  = st.slider("Lookback (days)", 10, _tf_max_days, min(180, _tf_max_days))
        if st.button(f"⬇ Fetch {_fetch_label}", type="primary"):
            with st.spinner(f"Fetching {_fetch_label} {_tf_label} data…"):
                try:
                    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
                    from fx_backtester.data.yfinance_loader import (
                        load_yfinance_bars, bars_to_csv, instrument_display_name, instrument_pip_size
                    )
                    import pandas as pd

                    _end   = date.today() - timedelta(days=1)
                    _start = _end - timedelta(days=_lookback)
                    _bars  = load_yfinance_bars(_fetch_instr, _start, _end, interval=_tf_code, verbose=False)

                    if not _bars:
                        st.error("No data returned. Try a shorter lookback period.")
                    else:
                        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as _tf:
                            bars_to_csv(_bars, Path(_tf.name))
                            _csv_bytes = Path(_tf.name).read_bytes()

                        st.session_state["csv_bytes"]    = _csv_bytes
                        st.session_state["csv_name"]     = f"{_fetch_instr}_{_tf_code}.csv"
                        st.session_state["instrument"]   = _fetch_instr
                        st.session_state["timeframe"]    = _tf_code
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
