# fx-backtester

Lean v0.1 scaffold for a deterministic, audit-friendly FX backtester.

## Design goals

- EUR/USD first
- deterministic engine before anything clever
- evidence-backed artifacts and explicit assumptions
- Pydantic models as source-of-truth contracts
- known-answer tests from day one
- no live trading and no broker integration

## What exists in v0.2-in-progress

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
- run folder artifact writer under `outputs/`
- strategy spec / manifest / quality report / signal trace / trades / metrics / compliance summary per run
- evidence-backed compliance checks
- tests for pip sizing/execution semantics, exact known-answer ledger coverage, JPY pip sizing, non-USD account conversion, short-side trades, DST/session tagging, and CSV -> RSI -> execution -> artifact writing

## What does **not** exist yet

- no portfolio-level multi-pair logic
- no slippage model beyond fixed assumptions
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
