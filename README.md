# fx-backtester

Deterministic, audit-friendly FX backtester for a deliberately narrow v1.1 scope.

## v1.1 supported scope

This repository is intentionally frozen around a narrow deterministic workflow:

- single-pair backtests for `EURUSD` and `USDJPY`
- two strategy families: RSI mean reversion and breakout
- timeframe: `H1` only
- directions: `long_only`, `short_only`, or `both`
- one open position at a time
- entries/exits scheduled from signal-bar close to next-bar open
- breakout parameters: `breakout_lookback_bars` and `breakout_buffer_pips`
- stop loss styles: `fixed_pips`, `atr`, or `disabled`
- take profit styles: `fixed_pips` or `disabled`
- optional deterministic exits: `time_stop_bars`, `exit_on_session_close`
- optional session filters: `asia`, `london`, `new_york`
- deterministic robustness-lite sweeps for spread/slippage/RSI-period perturbations
- deterministic report stack: compliance, summary, reviewer verdict, analysis summary, research memo

## explicitly unsupported in v1.0

Not hidden, not half-supported:

- trailing stops, break-even moves, partial exits, pyramiding, scale-in/out
- portfolios, baskets, multi-pair logic, hedging
- non-H1 strategies
- order-type modelling beyond next-bar-open deterministic fills
- optimization loops, walk-forward, Monte Carlo, parameter search
- discretionary/fundamental/ML/news/order-book inputs
- live trading, brokers, paper trading, autonomous agents

If a request asks for one of those, the formalizer should reject it and point to the nearest supported shape.

## install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
```

## happy-path CLI

The intended v1.0 flow is:

1. author a plain-English request
2. formalize it into a deterministic spec
3. validate the spec
4. run the backtest
5. read the verdict and memo

### request -> formalize

```bash
fx-backtester formalize-request \
  examples/eurusd_rsi_fixed_pips_request.txt \
  --output-dir outputs/demo_formalized
```

Writes:

```text
outputs/demo_formalized/
  formalized_spec.json
  formalizer_notes.json
  strategy_request.txt
```

### validate the formalized or example spec

```bash
fx-backtester validate-spec examples/eurusd_rsi_fixed_pips_spec.json
```

### run the full pipeline

```bash
fx-backtester run-backtest \
  examples/eurusd_rsi_fixed_pips_spec.json \
  examples/eurusd_rsi_fixed_pips_data.csv \
  --repo-root . \
  --run-label demo_fixed_pips
```

### restate the verdict from an existing run

```bash
fx-backtester summarize-run outputs/demo_fixed_pips
```

## golden examples

Three reproducible example flows are kept in `examples/`.

### A. EUR/USD RSI mean reversion with fixed-pip stop/TP

Files:

```text
examples/
  eurusd_rsi_fixed_pips_request.txt
  eurusd_rsi_fixed_pips_spec.json
  eurusd_rsi_fixed_pips_data.csv
```

Run:

```bash
fx-backtester formalize-request \
  examples/eurusd_rsi_fixed_pips_request.txt \
  --output-dir outputs/golden_fixed_pips_formalized

fx-backtester run-backtest \
  examples/eurusd_rsi_fixed_pips_spec.json \
  examples/eurusd_rsi_fixed_pips_data.csv \
  --repo-root . \
  --run-label golden_fixed_pips
```

Run-label note:

- `--run-label` is slugified into the final `run_id`
- non-alphanumeric separators collapse to hyphens
- `golden_fixed_pips` therefore writes to `outputs/golden-fixed-pips/`

Expected shape:

- one deterministic trade
- fixed-pip initial stop
- fixed-pip take profit
- verdict + memo generated under `outputs/golden-fixed-pips/reports/`

### B. EUR/USD RSI with ATR initial stop + time stop

Files:

```text
examples/
  eurusd_rsi_atr_time_stop_request.txt
  eurusd_rsi_atr_time_stop_spec.json
  eurusd_rsi_atr_time_stop_data.csv
```

Run:

```bash
fx-backtester formalize-request \
  examples/eurusd_rsi_atr_time_stop_request.txt \
  --output-dir outputs/golden_atr_time_stop_formalized

fx-backtester run-backtest \
  examples/eurusd_rsi_atr_time_stop_spec.json \
  examples/eurusd_rsi_atr_time_stop_data.csv \
  --repo-root . \
  --run-label golden_atr_time_stop
```

Run-label note:

- `golden_atr_time_stop` is slugified to the `run_id` `golden-atr-time-stop`
- artifacts therefore land under `outputs/golden-atr-time-stop/`

Expected shape:

- one deterministic trade
- ATR-based initial stop
- exit reason `time_stop`
- verdict + memo generated under `outputs/golden-atr-time-stop/reports/`

### C. EUR/USD breakout with fixed stop and time stop

Files:

```text
examples/
  eurusd_breakout_request.txt
  eurusd_breakout_spec.json
  eurusd_breakout_data.csv
```

Run:

```bash
fx-backtester formalize-request \
  examples/eurusd_breakout_request.txt \
  --output-dir outputs/golden_breakout_formalized

fx-backtester run-backtest \
  examples/eurusd_breakout_spec.json \
  examples/eurusd_breakout_data.csv \
  --repo-root . \
  --run-label golden_breakout
```

Run-label note:

- `golden_breakout` is slugified to the `run_id` `golden-breakout`
- artifacts therefore land under `outputs/golden-breakout/`

Expected shape:

- one deterministic trade
- breakout signal confirmed from prior completed bars only
- exit reason `time_stop`
- verdict + memo generated under `outputs/golden-breakout/reports/`

## release notes

- `CHANGELOG.md` tracks the v1.0 release note entry.
- `docs/V1_ARTIFACT_CONTRACT.md` freezes the v1 run artifact contract for downstream readers.

## output tree

Each run writes the same artifact layout.

```text
outputs/<run_id>/
  inputs/
    manifest.json
    strategy_spec.json
  results/
    metrics.json
    quality_report.json
    trades.json
  traces/
    signal_trace.json
  reports/
    analysis_summary.json
    artifact_index.json
    benchmarks.json
    compliance_summary.json
    final_verdict.json
    research_memo.md
    reviewer_summary.json
    robustness_lite.json
    summary.json
```

`reports/summary.json` and `reports/artifact_index.json` both carry `artifact_schema_version: "v1"` so downstream readers can lock onto the frozen v1 shape.

## design notes

- deterministic before clever
- artifacts before opinions
- explicit execution assumptions
- tests cover contracts, known answers, pipeline wiring, reviewer outputs, and CLI/golden-example smoke paths

## current status

This is a v1.0-ready research tool for the narrow scope listed above. It is not a general-purpose trading platform.
