# fx-backtester — Opus Critique Fix Tracker

Generated: 2026-04-07  
Reviewer: Claude Opus 4.6 (two passes)

---

## Pass 1 — Correctness Bugs

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| B1 | 🔴 Critical | `engine/backtest.py` | Trailing stop updated BEFORE SL/TP check — look-ahead bias. | ✅ FIXED |
| B2 | 🟡 Medium | `engine/backtest.py` | `_convert_pnl_to_usd` applied to entire equity balance — spot-rate approximation. | 📝 NOTED |
| B3 | 🟡 Medium | `engine/backtest.py` | Sharpe/Sortino annualisation hardcodes 1000 trades/year. | ✅ FIXED |
| B4 | 🟡 Medium | `engine/backtest.py` | Sortino downside deviation squares around zero instead of mean. | ✅ FIXED |
| B5 | 🟢 Low | `engine/backtest.py` | `max_drawdown_duration_trades` tracks deepest, not longest drawdown. | ✅ FIXED |
| B6 | 🟡 Medium | `engine/backtest.py` | `profit_factor = 0.0` for all-winner strategies. | ✅ FIXED |
| B7 | 🟢 Low | `analysis/walk_forward.py` | Docstring says "rolling" but implementation is sequential splits. | ✅ FIXED |
| B8 | 🟡 Medium | `scripts/run_pipeline.py` | Pipeline summary glob picks first `summary.json` — may be wrong run. | ✅ FIXED |

## Pass 1 — Financial / Trading Correctness

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| F1 | 🔴 Critical | `engine/backtest.py` | Asymmetric spread on TP vs SL — TP was free to hit. | ✅ FIXED |
| F2 | 🔴 High | `engine/backtest.py` | No gap risk modelled. | ✅ FIXED (UI warning) |
| F3 | 🟡 Medium | `pages_impl/page_backtest.py` | Commission $4.50 one-way vs $9.00 round-trip. | ✅ FIXED |
| F4 | 🟡 Medium | `engine/pipeline.py` | "VWAP" is not VWAP — typical price MA. | 📝 NOTED (already renamed) |
| F5 | 🟡 Medium | `engine/backtest.py` | No max position size cap. | ✅ FIXED |

## Pass 1 — Design Flaws

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| D1 | 🟡 Medium | `engine/pipeline.py` | 6 copy-paste signal pipeline builders. | 📝 BACKLOG |
| D2 | 🟡 Medium | `formalizer/request_formalizer.py` | Stale `_UNSUPPORTED_PATTERNS` blocks EMA/Bollinger/VWAP/trailing. | ✅ FIXED |
| D3 | 🟡 Medium | `pages_impl/page_*.py` | Pages crash on missing session state. | ✅ FIXED |
| D4 | 🟢 Low | `pages_impl/page_*.py` | `sys.path.insert` inside button handlers. | ✅ FIXED |

## Pass 1 — Code Quality / Security

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| Q1 | 🟢 Low | `data/dukascopy.py` + `yfinance_loader.py` | Duplicate `bars_to_csv`. | ✅ FIXED |
| Q2 | 🟢 Low | Various | pip/point terminology inconsistency. | ✅ FIXED |
| S1 | 🟡 Medium | `page_trade_journal.py` | Tradovate credentials in plain text session. | 📝 NOTED |
| S2 | 🟡 Medium | `page_backtest.py` | `delete=False` temp file leak. | ✅ FIXED |
| S3 | 🟢 Low | `page_trade_journal.py` | Shared journal — no per-user isolation. | 📝 NOTED |
| S4 | 🟢 Low | `page_get_data.py` | No CSV upload size limit. | ✅ FIXED |

**Pass 1 total: 21 issues — 17 fixed, 4 noted/backlog**

---

## Pass 2 — Correctness Bugs

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| NB1 | 🟡 Medium | `data/models.py` | `MarketBar.sessions` typed as `list[Literal["asia","london","new_york"]]` but futures sessions tag as `"rth"/"eth"` — type is wrong. | ✅ FIXED (changed to `list[str]`) |
| NB2 | 🔴 High | `scripts/run_pipeline.py` | Pipeline re-implements walk-forward verdict with different thresholds — diverges from canonical `walk_forward.py` logic. Shows FAILED when module says INCONCLUSIVE. | ✅ FIXED (deserialises `WalkForwardReport`, uses `.verdict`) |
| NB3 | 🔴 High | `engine/backtest.py` | Disabled stop still controls position sizing via phantom 20-pip distance — massively understates risk exposure. | ✅ FIXED (`_initial_stop_distance_pips` returns `None`; caller uses 1-lot flat sizing) |
| NB4 | 🟡 Medium | `engine/pipeline.py` | Bollinger Band exit triggers at middle band — on volatile instruments exits after 1-2 bars, makes strategy appear far worse than any real BB implementation. | ✅ FIXED (exit at opposite band instead of middle) |
| NB5 | 🟡 Medium | `engine/backtest.py` | `_convert_pnl_to_usd` inverts base-currency conversion — EUR-account EURUSD multiplies P&L by price instead of dividing (gives ~110 EUR on 100 USD profit at 1.10). | ✅ FIXED |

## Pass 2 — Financial / Trading Correctness

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| NF1 | 🔴 Critical | `engine/sizing.py` | Fractional futures contracts allowed — `floor(lots * lot_size_units)` yields e.g. 34 NQ units (1.7 contracts). NQ/ES trade in whole contracts only. | ✅ FIXED (`_snap_lots` + `min_lot_step=1.0` on `InstrumentSpec`) |
| NF2 | 🔴 Critical | `engine/backtest.py` | Commission calculated on fractional contracts (same root as NF1). | ✅ FIXED (fixed by NF1 — lots now snapped to whole contracts before unit conversion) |
| NF3 | 🟡 Medium | `scripts/run_pipeline.py` | Pipeline default `stop_loss_pips: 100` for NQ = 25 NQ points — extremely tight, causes excessive stop-outs. | ✅ FIXED (200 pips = 50 NQ points; TP scaled proportionally) |
| NF4 | 🟡 Medium | `engine/backtest.py` | ATR trailing stop trails from `bar.close` not `bar.high`/`bar.low` — undertightens stop. | ✅ FIXED (longs trail from `bar.high`, shorts from `bar.low`) |
| NF5 | 🟢 Low | `pages_impl/page_backtest.py` | MAE/MFE uses `st.session_state.get("pip_size", 0.25)` — wrong default for FX. | ✅ FIXED (uses `_instr_spec.pip_size` directly) |

## Pass 2 — Design Flaws

| # | Severity | File | Issue | Status |
|---|----------|------|-------|--------|
| ND1 | 🔴 High | `analysis/walk_forward.py` | Each fold re-initialises indicators from scratch — first 14 bars of every OOS slice wasted on warmup (~23% of OOS window). Biases walk-forward toward FAILED. | ✅ FIXED (IS tail passed as `warmup_prefix` to OOS slice) |
| ND2 | 🟡 Medium | `scripts/run_pipeline.py` | Pipeline reimplements verdict logic instead of importing `WalkForwardReport`. Root cause of NB2. | ✅ FIXED (deserialises `WalkForwardReport.model_validate_json`) |
| ND3 | 🟡 Medium | `pages_impl/page_key_levels.py` | Same `delete=False` temp file leak fixed in `page_backtest.py` — missed in pass 1. | ✅ FIXED |
| ND4 | 🟡 Medium | `pages_impl/page_grid_search.py` + `page_walk_forward.py` | Hardcode `half_spread_pips=0.2, commission=0` — ignores futures costs. | ✅ FIXED (reads `st.session_state["policy"]` set by backtest page) |
| ND5 | 🟢 Low | `analysis/grid_search.py` | Sort direction wrong if `max_drawdown_pct` ever added as sort metric. | 📝 NOTED (not currently exposed as sort option) |

**Pass 2 total: 15 issues — 14 fixed ✅, 1 noted 📝**

---

## Pass 2 Priority Order

1. **NF1+NF2** — Fractional contracts (all futures P&L numbers are fiction)
2. **NB3** — Disabled stop still sizing (massively understates risk)
3. **ND4** — Grid search/walk-forward ignore futures costs (flatters results)
4. **NB2+ND2** — Pipeline verdict diverges from canonical (wrong AI verdicts)
5. **ND1** — Walk-forward warmup loss (biases toward FAILED)
6. **ND3** — Key levels temp file leak
7. **NB5** — Base-currency P&L conversion inverted
8. **NF4** — Trailing stop trails from close not high/low
9. **NB4** — Bollinger exit triggers too early
10. **NF5** — MAE/MFE wrong default pip size
11. **NB1** — MarketBar sessions type annotation wrong for futures
12. **NF3** — Pipeline stop defaults too tight for futures
13. **ND5** — Grid search sort direction note

---

## Overall Progress

- Pass 1: 21 issues — 17 ✅ fixed, 4 📝 noted
- Pass 2: 15 issues — 14 ✅ fixed, 1 📝 noted
- **Grand total: 36 issues — 31 fixed, 5 noted/backlog, 0 remaining**

