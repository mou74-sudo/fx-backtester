# Changelog

## v1.2.0 - 2026-04-03

Real-data integration layer and formalizer phrasing expansion.

### Included

- **Dukascopy H1 data loader** (`src/fx_backtester/data/dukascopy.py`) — official supported data input path for EURUSD and USDJPY; downloads BID OHLC H1 candles from Dukascopy's free public datafeed, caches raw bi5 files locally, normalises into `MarketBar`, and exports pipeline-ready CSV
- **CLI `fetch-data` subcommand** — `fx-backtester fetch-data --instrument EURUSD --start YYYY-MM-DD --end YYYY-MM-DD --output path/to/data.csv`
- **RSI phrasing expansion** (issue #4) — formalizer now recognises `RSI(N)`, `N-period RSI`, `when RSI is below/above N`, `RSI falls below / rises above`, `go long/go short`, and `enter long/exit long` phrasings without heuristic side inference
- **Direction co-presence detection** — `buy if … sell if`, `go long … go short`, and `enter long … enter short` phrasing pairs automatically resolve to `direction=both`
- **`max_drawdown_pct` bug fix** — field is now documented as plain percent (e.g. `5.51` = 5.51%); surfaced in `reports/summary.json` and the research memo with correct `f"{value:.2f}%"` formatting; regression test added

### Test additions

- 22 Dukascopy loader tests (URL construction, bi5 parsing, cache hit/miss, CSV round-trip)
- End-to-end mocked fetch → CSV → backtest integration test
- 12 formalizer phrasing tests (A1–A4, A6, R1–R4, M1–M3)
- 4 direction detection tests
- `max_drawdown_pct` plain-percent regression test
- **106 / 106 tests green**

### Stability notes

- Dukascopy is the official supported real-data input for v1.2; artifact contract and `artifact_schema_version` are unchanged
- No changes to execution, grading, reviewer, or robustness logic

## v1.1.0 - 2026-03-31

Breakout strategy-family expansion for the intentionally narrow deterministic FX backtesting workflow.

### Included

- added `strategy_type: "breakout"` support with `breakout_lookback_bars` and `breakout_buffer_pips`
- deterministic breakout signal generation using prior completed bars only and next-bar-open execution
- natural-language formalization support for breakout requests
- one breakout example-backed golden flow with request, spec, CSV fixture, verdict, and memo
- breakout integration, CLI, and formalizer regression coverage while preserving `artifact_schema_version: "v1"`

### Stability notes

- breakout support is first-class in v1.1, but still intentionally narrow: H1 only, single pair, one open position at a time
- reviewer/grading logic and artifact contract remain unchanged from v1

## v1.0.0 - 2026-03-26

First stable release for the intentionally narrow deterministic FX backtesting workflow.

### Included

- frozen v1 scope around H1 RSI mean-reversion backtests for EURUSD and USDJPY
- natural-language request formalization into a validated deterministic strategy spec
- deterministic backtest execution with compliance, robustness-lite, benchmark, reviewer verdict, analysis summary, and research memo artifacts
- golden examples for fixed-pip and ATR/time-stop flows
- contract documentation for the v1 run artifact layout and schema versioning
- one end-to-end smoke test that exercises the full request -> spec -> run -> verdict -> memo pipeline

### Stability notes

- artifact readers should key off `artifact_schema_version: "v1"` in `reports/summary.json` and `reports/artifact_index.json`
- v1 intentionally does **not** add portfolio logic, trailing stops, optimization, or live trading concerns
