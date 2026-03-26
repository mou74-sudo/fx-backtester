# v1 artifact contract

This document freezes the repository's v1 run artifact contract.

## Scope

The contract applies to directories written by `fx-backtester run-backtest` under:

```text
outputs/<run_id>/
```

The contract covers:

- directory layout
- required file paths
- file roles
- schema/version lock point for downstream readers

It does **not** promise stable internal Python APIs.

## Contract root

Every run writes:

```text
outputs/<run_id>/
  inputs/
  results/
  traces/
  reports/
```

`<run_id>` is either:

- `run_<UTC timestamp>__<strategy slug>` for timestamped runs, or
- `<run_label>` when `--run-label` is supplied

## Required files

### inputs/

- `inputs/strategy_spec.json` — validated strategy spec used for the run
- `inputs/manifest.json` — deterministic execution/validation manifest

### results/

- `results/quality_report.json` — basic CSV data quality checks
- `results/trades.json` — executed trade ledger
- `results/metrics.json` — aggregate run metrics

### traces/

- `traces/signal_trace.json` — per-bar prepared signal/execution trace

### reports/

- `reports/compliance_summary.json` — compliance checks and summary metrics
- `reports/summary.json` — compact canonical run summary
- `reports/artifact_index.json` — path index for the artifact set
- `reports/final_verdict.json` — reviewer verdict and failure/downgrade reasons
- `reports/reviewer_summary.json` — reviewer summary facts
- `reports/analysis_summary.json` — restated deterministic analysis payload
- `reports/research_memo.md` — human-readable memo for the run
- `reports/robustness_lite.json` — robustness-lite scenarios when robustness is evaluated
- `reports/benchmarks.json` — deterministic benchmark comparison when benchmarks are evaluated

In the current v1 implementation, robustness-lite and benchmarks are written for normal pipeline runs and should be treated as part of the expected happy-path artifact set.

## Schema/version note

Downstream readers should treat this as the main compatibility rule:

- `reports/summary.json` contains `artifact_schema_version: "v1"`
- `reports/artifact_index.json` contains `artifact_schema_version: "v1"`

If either value changes, consumers should assume a new artifact contract.

## Stable keys consumers can rely on

### reports/summary.json

Consumers may rely on these keys existing in v1:

- `artifact_schema_version`
- `run_id`
- `strategy_name`
- `trade_count`
- `net_pnl`
- `net_pips`
- `ending_equity`
- `max_drawdown`
- `robustness_enabled`

### reports/artifact_index.json

Consumers may rely on these keys existing in v1:

- `artifact_schema_version`
- `run_id`
- `paths.inputs`
- `paths.results`
- `paths.traces`
- `paths.reports`

The path entries are repository-relative to the run directory root, for example `reports/summary.json`.

## Compatibility guidance

For v1 consumers:

- prefer `reports/summary.json` for quick status
- use `reports/artifact_index.json` to discover the full artifact set
- treat additional keys in JSON files as additive/non-breaking within v1
- treat file removals, path changes, or `artifact_schema_version` changes as breaking

## Happy-path checklist

A run is considered contract-complete when all of the following exist:

```text
inputs/strategy_spec.json
inputs/manifest.json
results/quality_report.json
results/trades.json
results/metrics.json
traces/signal_trace.json
reports/compliance_summary.json
reports/summary.json
reports/artifact_index.json
reports/final_verdict.json
reports/reviewer_summary.json
reports/analysis_summary.json
reports/research_memo.md
reports/robustness_lite.json
reports/benchmarks.json
```
