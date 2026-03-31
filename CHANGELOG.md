# Changelog

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
