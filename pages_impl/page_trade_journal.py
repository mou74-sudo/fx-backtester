import json
import uuid
from pathlib import Path

import plotly.express as px
import streamlit as st

from pages_impl._shared import _CHART, _cl  # noqa: F401


def render(_RESULTS: Path) -> None:
    import pandas as pd

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
        _multipliers = {"NQ": 20, "ES": 50, "MNQ": 2, "MES": 5}
        point = _multipliers.get(instrument, 50)
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
                action = f.get("action", "")
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

                    # open_f is always the opening fill; current fill is always the exit.
                    # For longs: open_f = earlier Buy, current action = Sell.
                    # For shorts: open_f = earlier Sell, current action = Buy.
                    entry_p  = open_f["price"]
                    exit_p   = price
                    side     = "Long" if action == "Sell" else "Short"
                    pts      = (exit_p - entry_p) if side == "Long" else (entry_p - exit_p)
                    pnl_usd  = round(pts * mult * matched, 2)
                    entry_ts = open_f["ts"]
                    exit_ts  = ts

                    try:
                        _edt = pd.to_datetime(entry_ts)
                    except Exception:
                        _edt = pd.Timestamp.now()
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

                if remaining > 0:
                    queues[cid][action].append({"qty": remaining, "price": price, "ts": ts})

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
                        _token, _uid = _tv_auth(_base, _tv_user, _tv_pass)
                        st.success("✅ Connected to Tradovate.")

                        with st.spinner("Fetching accounts…"):
                            _accounts = _tv_get(_base, _token, "account/list") or []

                        with st.spinner(f"Fetching fills for last {_tv_days} days…"):
                            _fills_raw     = _tv_get(_base, _token, "fill/list") or []
                            _contracts_raw = _tv_get(_base, _token, "contract/list") or []

                        _cmap  = {c["id"]: c.get("name", "") for c in _contracts_raw}
                        _since = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=int(_tv_days)))
                        _fills = []
                        for f in _fills_raw:
                            try:
                                _ts = pd.to_datetime(f.get("timestamp", ""), utc=True)
                                if _ts >= _since:
                                    _fills.append(f)
                            except Exception:
                                _fills.append(f)

                        st.info(f"Found **{len(_fills)} fills** across {len(_accounts)} account(s).")

                        if _fills:
                            _matched = _fifo_match(_fills, _cmap)
                            st.info(f"Matched into **{len(_matched)} round-trip trades**.")

                            if _matched:
                                _preview_df = pd.DataFrame(_matched)[
                                    ["date", "time", "instrument", "side", "size", "entry", "exit", "pnl_usd", "pnl_points", "result"]
                                ]
                                st.dataframe(_preview_df, use_container_width=True)

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
                                    st.success(f"✅ Imported {len(_new)} trades.")
                                    st.rerun()
                        else:
                            st.info("No fills found in this date range. Try a longer period.")

                    except ValueError as e:
                        st.error(f"Login failed: {e}")
                        st.caption("Check your username and password, and make sure you selected the right account type.")
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
                tv_df = pd.read_csv(tv_file)
                st.markdown("**Preview (first 5 rows):**")
                st.dataframe(tv_df.head(), use_container_width=True)
                st.markdown("**Columns detected:** " + ", ".join(f"`{c}`" for c in tv_df.columns))

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
                    st.warning(f"Could not find columns for: **{', '.join(missing)}**.")
                else:
                    if _col_pnl:
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
                                mult     = 20 if instr == "NQ" else 50
                                if pnl_usd != 0 and qty > 0:
                                    pts         = pnl_usd / (mult * qty)
                                    exit_approx = round(price + pts if side == "Long" else price - pts, 2)
                                else:
                                    pts         = 0.0
                                    exit_approx = price
                                trades.append({
                                    "id":          str(uuid.uuid4())[:8],
                                    "date":        raw_dt.date().isoformat(),
                                    "time":        raw_dt.strftime("%H:%M"),
                                    "instrument":  instr,
                                    "side":        side,
                                    "size":        qty,
                                    "entry":       price,
                                    "exit":        exit_approx,
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
                                    "notes":       f"Imported from Tradovate — {contract}",
                                    "source":      "tradovate",
                                })
                                imported += 1
                            except Exception:
                                skipped += 1
                        _save_trades(trades)
                        st.success(f"✅ Imported **{imported} trades** ({skipped} skipped).")
                        if imported > 0:
                            st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")

    # ── TAB 3: TRADE LOG ──────────────────────────────────────────────────────
    with tab3:
        st.subheader("Trade Log")

        if not trades:
            st.info("No trades logged yet. Add your first trade in the **➕ Log Trade** tab.")
        else:
            df = pd.DataFrame(trades)

            c1, c2, c3 = st.columns(3)
            _f_instr  = c1.multiselect("Instrument", ["NQ", "ES"], default=["NQ", "ES"])
            _f_result = c2.multiselect("Result", ["Win", "Loss", "BE"], default=["Win", "Loss", "BE"])
            _f_setup  = c3.multiselect("Setup", df["setup"].unique().tolist(), default=df["setup"].unique().tolist())

            _mask = (df["instrument"].isin(_f_instr) & df["result"].isin(_f_result) & df["setup"].isin(_f_setup))
            df_f  = df[_mask].copy()

            st.dataframe(
                df_f[["date", "time", "instrument", "side", "size", "entry", "exit", "pnl_usd", "pnl_points", "r_multiple", "result", "setup", "session", "grade"]].sort_values("date", ascending=False),
                use_container_width=True,
                column_config={
                    "pnl_usd":    st.column_config.NumberColumn("P&L $",  format="$%.2f"),
                    "pnl_points": st.column_config.NumberColumn("Points", format="%.2f"),
                    "r_multiple": st.column_config.NumberColumn("R",      format="%.2f"),
                    "entry":      st.column_config.NumberColumn("Entry",  format="%.2f"),
                    "exit":       st.column_config.NumberColumn("Exit",   format="%.2f"),
                },
            )

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
            df["date"]    = pd.to_datetime(df["date"])
            df["week"]    = df["date"].dt.to_period("W").astype(str)
            df["month"]   = df["date"].dt.to_period("M").astype(str)
            df["dow"]     = df["date"].dt.day_name()
            wins   = df[df["result"] == "Win"]
            losses = df[df["result"] == "Loss"]

            st.markdown("### Overview")
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            total_pnl = df["pnl_usd"].sum()
            win_rate  = len(wins) / len(df) if len(df) else 0
            avg_win   = wins["pnl_usd"].mean()   if len(wins)   else 0
            avg_loss  = losses["pnl_usd"].mean() if len(losses) else 0
            pf        = abs(wins["pnl_usd"].sum() / losses["pnl_usd"].sum()) if len(losses) and losses["pnl_usd"].sum() != 0 else 0
            avg_r     = df["r_multiple"].dropna().mean() if "r_multiple" in df else 0

            k1.metric("Total P&L",     f"${total_pnl:+,.2f}")
            k2.metric("Trades",         len(df))
            k3.metric("Win Rate",       f"{win_rate:.0%}")
            k4.metric("Avg Winner",    f"${avg_win:+,.2f}")
            k5.metric("Avg Loser",     f"${avg_loss:+,.2f}")
            k6.metric("Profit Factor",  f"{pf:.2f}")

            st.markdown("---")

            st.markdown("### 📈 Equity Curve")
            _eq = df.sort_values("date").reset_index(drop=True)
            _eq["cum_pnl"] = _eq["pnl_usd"].cumsum()
            _eq["trade_n"] = range(1, len(_eq) + 1)
            fig_eq = px.area(_eq, x="trade_n", y="cum_pnl",
                             color_discrete_sequence=["#00c49a"],
                             labels={"trade_n": "Trade #", "cum_pnl": "Cumulative P&L ($)"},
                             title="Cumulative P&L")
            fig_eq.update_layout(**_cl(yaxis=dict(gridcolor="rgba(255,255,255,0.1)")))
            fig_eq.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
            st.plotly_chart(fig_eq, use_container_width=True, key="journal_equity")

            if df["r_multiple"].notna().sum() > 2:
                st.markdown("### 🎯 R-Multiple Distribution")
                fig_r = px.histogram(df.dropna(subset=["r_multiple"]), x="r_multiple",
                                     nbins=20, color_discrete_sequence=["#5588ff"],
                                     labels={"r_multiple": "R-Multiple"},
                                     title="Distribution of R-multiples")
                fig_r.add_vline(x=0, line_dash="dash", line_color="white")
                fig_r.update_layout(**_CHART)
                st.plotly_chart(fig_r, use_container_width=True, key="journal_r_dist")

            st.markdown("### 🕐 Performance by Session")
            _sess = df.groupby("session").agg(
                Trades=("pnl_usd", "count"),
                Total_PnL=("pnl_usd", "sum"),
                Win_Rate=("result", lambda x: (x == "Win").mean()),
                Avg_PnL=("pnl_usd", "mean"),
            ).reset_index()
            c1, c2 = st.columns(2)
            fig_s1 = px.bar(_sess, x="session", y="Total_PnL",
                            color="Total_PnL", color_continuous_scale=["#ff4455", "#00c49a"],
                            title="Total P&L by Session")
            fig_s1.update_layout(**_CHART)
            c1.plotly_chart(fig_s1, use_container_width=True, key="journal_session_pnl")

            fig_s2 = px.bar(_sess, x="session", y="Win_Rate",
                            color="Win_Rate", color_continuous_scale=["#ff4455", "#00c49a"],
                            title="Win Rate by Session")
            fig_s2.update_layout(**_CHART)
            c2.plotly_chart(fig_s2, use_container_width=True, key="journal_session_wr")

            st.markdown("### 📅 Performance by Day of Week")
            _dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            _dow = df.groupby("dow").agg(
                Trades=("pnl_usd", "count"),
                Total_PnL=("pnl_usd", "sum"),
                Win_Rate=("result", lambda x: (x == "Win").mean()),
            ).reindex(_dow_order).reset_index()
            c1, c2 = st.columns(2)
            fig_d1 = px.bar(_dow, x="dow", y="Total_PnL",
                            color="Total_PnL", color_continuous_scale=["#ff4455", "#00c49a"],
                            title="Total P&L by Day")
            fig_d1.update_layout(**_CHART)
            c1.plotly_chart(fig_d1, use_container_width=True, key="journal_dow_pnl")

            fig_d2 = px.bar(_dow, x="dow", y="Win_Rate",
                            color="Win_Rate", color_continuous_scale=["#ff4455", "#00c49a"],
                            title="Win Rate by Day")
            fig_d2.update_layout(**_CHART)
            c2.plotly_chart(fig_d2, use_container_width=True, key="journal_dow_wr")

            st.markdown("### 🎯 Performance by Setup")
            _setup = df.groupby("setup").agg(
                Trades=("pnl_usd", "count"),
                Total_PnL=("pnl_usd", "sum"),
                Win_Rate=("result", lambda x: (x == "Win").mean()),
                Avg_PnL=("pnl_usd", "mean"),
            ).sort_values("Total_PnL", ascending=False).reset_index()
            st.dataframe(_setup, use_container_width=True,
                         column_config={
                             "Total_PnL": st.column_config.NumberColumn("Total P&L", format="$%.2f"),
                             "Avg_PnL":   st.column_config.NumberColumn("Avg P&L",   format="$%.2f"),
                             "Win_Rate":  st.column_config.NumberColumn("Win Rate",  format="%.0%"),
                         })
            fig_setup = px.bar(_setup, x="setup", y="Total_PnL",
                               color="Total_PnL", color_continuous_scale=["#ff4455", "#00c49a"],
                               title="P&L by Setup Type")
            fig_setup.update_layout(**_cl(xaxis_tickangle=-30))
            st.plotly_chart(fig_setup, use_container_width=True, key="journal_setup_pnl")

            st.markdown("### 📆 Monthly Breakdown")
            _monthly = df.groupby("month").agg(
                Trades=("pnl_usd", "count"),
                Total_PnL=("pnl_usd", "sum"),
                Win_Rate=("result", lambda x: (x == "Win").mean()),
                Best_Trade=("pnl_usd", "max"),
                Worst_Trade=("pnl_usd", "min"),
            ).reset_index()
            st.dataframe(_monthly, use_container_width=True,
                         column_config={
                             "Total_PnL":   st.column_config.NumberColumn("Total P&L",   format="$%.2f"),
                             "Best_Trade":  st.column_config.NumberColumn("Best Trade",  format="$%.2f"),
                             "Worst_Trade": st.column_config.NumberColumn("Worst Trade", format="$%.2f"),
                             "Win_Rate":    st.column_config.NumberColumn("Win Rate",    format="%.0%"),
                         })
            fig_mon = px.bar(_monthly, x="month", y="Total_PnL",
                             color="Total_PnL", color_continuous_scale=["#ff4455", "#00c49a"],
                             title="Monthly P&L")
            fig_mon.update_layout(**_CHART)
            st.plotly_chart(fig_mon, use_container_width=True, key="journal_monthly_pnl")

            st.markdown("### 🧠 Mindset vs Performance")
            _mind = df.groupby("emotion").agg(
                Trades=("pnl_usd", "count"),
                Total_PnL=("pnl_usd", "sum"),
                Win_Rate=("result", lambda x: (x == "Win").mean()),
            ).sort_values("Win_Rate", ascending=False).reset_index()
            fig_mind = px.bar(_mind, x="emotion", y="Win_Rate",
                              color="Win_Rate", color_continuous_scale=["#ff4455", "#00c49a"],
                              title="Win Rate by Mindset")
            fig_mind.update_layout(**_CHART)
            st.plotly_chart(fig_mind, use_container_width=True, key="journal_mindset")

            st.markdown("### 🏅 Trade Grade vs Performance")
            _grade = df.groupby("grade").agg(
                Trades=("pnl_usd", "count"),
                Total_PnL=("pnl_usd", "sum"),
                Win_Rate=("result", lambda x: (x == "Win").mean()),
                Avg_PnL=("pnl_usd", "mean"),
            ).reset_index()
            c1, c2 = st.columns(2)
            fig_g1 = px.bar(_grade, x="grade", y="Win_Rate",
                            color="Win_Rate", color_continuous_scale=["#ff4455", "#00c49a"],
                            title="Win Rate by Grade")
            fig_g1.update_layout(**_CHART)
            c1.plotly_chart(fig_g1, use_container_width=True, key="journal_grade_wr")

            fig_g2 = px.bar(_grade, x="grade", y="Avg_PnL",
                            color="Avg_PnL", color_continuous_scale=["#ff4455", "#00c49a"],
                            title="Avg P&L by Grade")
            fig_g2.update_layout(**_CHART)
            c2.plotly_chart(fig_g2, use_container_width=True, key="journal_grade_pnl")

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
                    _cur_type   = r
            if _cur_type == "Win":  _max_win_streak  = max(_max_win_streak,  _cur_streak)
            if _cur_type == "Loss": _max_loss_streak = max(_max_loss_streak, _cur_streak)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Max Win Streak",  f"{_max_win_streak} 🔥")
            c2.metric("Max Loss Streak", f"{_max_loss_streak} 🥶")
            c3.metric("Avg R",           f"{avg_r:.2f}R" if avg_r else "—")
            c4.metric("Best Trade",      f"${df['pnl_usd'].max():+,.2f}")
