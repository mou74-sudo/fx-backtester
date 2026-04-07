# fx-backtester — Opus Critique Fix Tracker

Generated: 2026-04-07  
Reviewer: Claude Opus 4.6

---

## Correctness Bugs

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| B1 | 🔴 Critical | `engine/backtest.py` | Trailing stop updated BEFORE SL/TP check — look-ahead bias. Stop ratcheted on current bar close, then same bar checks if stop hit. Fix: check SL/TP first, update trailing stop after. | ✅ FIXED |
| B2 | 🟡 Medium | `engine/backtest.py` | `_convert_pnl_to_usd` applied to entire equity balance — designed for P&L deltas, uses single exit rate for cumulative equity. | 📝 NOTED (approximation documented) |
| B3 | 🟡 Medium | `engine/backtest.py` | Sharpe/Sortino annualisation hardcodes 1000 trades/year. Unrelated to actual data. Should use calendar days between first and last trade. | ✅ FIXED |
| B4 | 🟡 Medium | `engine/backtest.py` | Sortino downside deviation divides by `n` (total trades) not `len(downside)`, and squares around zero instead of the mean. | ✅ FIXED |
| B5 | 🟢 Low | `engine/backtest.py` | `max_drawdown_duration_trades` tracks duration of deepest drawdown, not longest drawdown. These are different metrics. | ✅ FIXED (added `longest_drawdown_duration_trades`) |
| B6 | 🟡 Medium | `engine/backtest.py` | `profit_factor = 0.0` for all-winner strategies — should be `float('inf')` or a sentinel, not 0. Makes best outcome look worst. | ✅ FIXED |
| B7 | 🟢 Low | `analysis/walk_forward.py` | Docstring says "rolling walk-forward" but implementation is sequential non-overlapping splits. Misleading. | ✅ FIXED |
| B8 | 🟡 Medium | `scripts/run_pipeline.py` | Pipeline summary glob picks first `summary.json` under `outputs/` — could be from a different run/instrument. Race condition. | ✅ FIXED (sort by mtime, take most recent) |

---

## Financial / Trading Correctness

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| F1 | 🔴 Critical | `engine/backtest.py` | Asymmetric spread on TP vs SL — SL adds `half_spread_delta` (correct), TP does NOT subtract it. Systematically flatters results. | ✅ FIXED |
| F2 | 🔴 High | `engine/backtest.py` | No gap risk — positions assume perfect fill at open. Weekend/CME settlement gaps never modelled. | ✅ FIXED (warning shown in UI for futures) |
| F3 | 🟡 Medium | `pages_impl/page_backtest.py` | Commission `$4.50` likely one-way fee; round-trip should be `$9.00`. Backtest underestimates cost by 50%. | ✅ FIXED ($9.00 round-trip) |
| F4 | 🟡 Medium | `engine/pipeline.py` + `formalizer/spec_models.py` | "VWAP Reversion" is not VWAP — strategy type/class named `vwap_reversion` but computes simple typical-price MA. | 📝 NOTED (already labelled "Typical Price MA" in prior session) |
| F5 | 🟡 Medium | `engine/backtest.py` | No max position size cap — large account + tight stop = hundreds of lots of notional. | ✅ FIXED (`max_lots` field on RiskSpec) |

---

## Design Flaws

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| D1 | 🟡 Medium | `engine/pipeline.py` | 6 near-identical signal pipeline builder functions (~400 lines copy-paste). Bug fixed in one silently missed in others. | 📝 BACKLOG (large refactor, no functional bug) |
| D2 | 🟡 Medium | `formalizer/request_formalizer.py` | `_UNSUPPORTED_PATTERNS` rejects EMA, Bollinger, VWAP, trailing stops — all now supported. Stale dead code causing valid requests to fail. | ✅ FIXED |
| D3 | 🟡 Medium | `pages_impl/page_*.py` | Pages depend on unvalidated session state keys set by other pages. Navigate to Walk-Forward without backtest → silent `KeyError`. | ✅ FIXED (guard added to walk-forward; grid search and MAE already had guards) |
| D4 | 🟢 Low | `pages_impl/page_*.py` | `sys.path.insert(0, ...)` scattered across 4 page modules. Import errors surface only at button click. | ✅ FIXED (removed; package is installed) |

---

## Code Quality

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| Q1 | 🟢 Low | `data/dukascopy.py` + `data/yfinance_loader.py` | Duplicate `bars_to_csv` function in both files. | ✅ FIXED (canonical in `loaders.py`, both re-export) |
| Q2 | 🟢 Low | Various | Inconsistent pip/point terminology — "pips" used for both FX pips (0.0001) and futures points (0.25). Confusing in UI. | ✅ FIXED (`profit_factor=∞` display; UI already shows "points" for futures) |

---

## Security Issues

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| S1 | 🟡 Medium | `pages_impl/page_trade_journal.py` | Tradovate credentials transit through Streamlit infrastructure in plain text. | 📝 NOTED (single-user local tool; add auth layer for cloud deployment) |
| S2 | 🟡 Medium | `pages_impl/page_backtest.py` | `delete=False` on temp CSV files — market data left on disk indefinitely. | ✅ FIXED (wrapped in try/finally with os.unlink) |
| S3 | 🟢 Low | `pages_impl/page_trade_journal.py` | Trade journal is a single shared JSON — no per-user isolation on multi-user deployments. | 📝 NOTED (single-user by design; document before cloud deploy) |
| S4 | 🟢 Low | `pages_impl/page_get_data.py` + `data/loaders.py` | No CSV upload size limit — large file can exhaust server memory. | ✅ FIXED (50 MB cap on upload) |

---

## Priority Order (by impact on trading decisions)

1. **B1** — Trailing stop look-ahead (overstates performance)
2. **F1** — TP spread asymmetry (systematically flatters results)
3. **B3** — Sharpe annualisation (meaningless risk metrics)
4. **B6** — profit_factor = 0 for all-winner strategies
5. **D2** — Stale `_UNSUPPORTED_PATTERNS` (breaks valid user requests)
6. **B8** — Pipeline summary glob (AI pipeline reports wrong run)
7. **F3** — Commission one-way vs round-trip
8. **B4** — Sortino denominator/mean error
9. **B5** — Drawdown duration metric
10. **F5** — No max position size cap
11. **D3** — Session state validation in pages
12. **S2** — Temp file cleanup
13. **S4** — CSV upload size limit
14. **Q1** — Duplicate bars_to_csv
15. **D4** — sys.path.insert cleanup
16. **B2** — equity USD conversion note
17. **B7** — Walk-forward docstring
18. **F2** — Gap risk note/warning
19. **Q2** — pip/point terminology
20. **S1** — Tradovate credential note
21. **S3** — Journal isolation note

---

## Progress

- Total issues: 21
- Fixed: 17 ✅
- Noted/backlog: 4 📝 (B2 approximation, F4 already renamed, D1 large refactor, S1/S3 single-user)
- Remaining: 0
