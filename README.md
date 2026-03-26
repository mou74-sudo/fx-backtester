# fx-backtester

Lean v0.1 scaffold for a deterministic, audit-friendly FX backtester.

## Design goals

- EUR/USD first
- deterministic engine before anything clever
- evidence-backed artifacts and explicit assumptions
- Pydantic models as source-of-truth contracts
- known-answer tests from day one
- no live trading and no broker integration

## What exists in v0.4-in-progress

- strategy/spec contracts in `formalizer/spec_models.py`
- explicit execution assumptions in `formalizer/execution_policy.py`
- CSV data loader and lightweight quality checks
- UTC-normalized market bars with lean session tagging (`asia`, `london`, `new_york`)
- RSI calculation from raw OHLC closes
- no-leakage signal pipeline: signal bar close -> next bar open execution
- deterministic position sizing and fill semantics
- structured trade log model with evidence refs
- deterministic single-position backtest loop over prepared signal bars
- conservative gap / same-candle TP-SL resolution, spread-triggered stop detection, and short-side support
- richer run metrics: gross/net pips, expectancy, avg win/loss in pips, drawdown depth/duration, ambiguity counts, spread-triggered-stop counts, session summaries
- lean config/spec extensions for long-only / short-only / both, session restrictions, account currency, spread/slippage model naming, and stop/TP style switches
- robustness-lite sweeps for spread stress, slippage stress, RSI period perturbation, trade concentration, and session contribution summary
- deterministic run folder artifact writer under `outputs/` with `inputs/`, `results/`, `traces/`, and `reports/`
- one summary report plus robustness-lite report artifacts per run
- read-only analysis/report layer that restates deterministic artifacts into `reports/analysis_summary.json` and `reports/research_memo.md`
- evidence-backed compliance checks
- tests for pip sizing/execution semantics, exact known-answer ledger coverage, JPY pip sizing, non-USD account conversion, short-side trades, config/robustness coverage, DST/session tagging, deterministic analysis reporting, and CSV -> RSI -> execution -> artifact writing

## What does **not** exist yet

- no portfolio-level multi-pair logic
- no probabilistic slippage or market-impact model beyond explicit fixed/worse-case assumptions
- no London/session microstructure logic
- no broker adapters
- no full indicator pipeline from raw OHLC to signals yet
- no short-side strategy logic yet

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
fx-backtester validate-spec examples/eurusd_rsi_mean_reversion.json
```

## Repository layout

```text
src/fx_backtester/
  formalizer/
  data/
  engine/
  reports/
  cli.py
examples/
tests/
data/
outputs/
```

## Determinism notes

The starter framework keeps execution policy explicit. Fill price, spread handling,
lot sizing, pip value assumptions, and artifact generation are intended to be easy
to inspect and hard to hand-wave.
