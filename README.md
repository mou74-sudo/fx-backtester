# fx-backtester

Lean v0.1 scaffold for a deterministic, audit-friendly FX backtester.

## Design goals

- EUR/USD first
- deterministic engine before anything clever
- evidence-backed artifacts and explicit assumptions
- Pydantic models as source-of-truth contracts
- known-answer tests from day one
- no live trading and no broker integration

## What exists in v0.1

- strategy/spec contracts in `formalizer/spec_models.py`
- explicit execution assumptions in `formalizer/execution_policy.py`
- CSV data loader and lightweight quality checks
- deterministic position sizing and fill semantics
- structured trade log model
- simple compliance/report artifact builder
- CLI entrypoint for validating a strategy spec
- tests for pip sizing/execution semantics plus known-answer scaffolding

## What does **not** exist yet

- no portfolio-level multi-pair logic
- no slippage model beyond fixed assumptions
- no London/session microstructure logic
- no broker adapters
- no full backtest loop over bar data

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
