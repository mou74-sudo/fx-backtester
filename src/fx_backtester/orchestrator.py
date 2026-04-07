from __future__ import annotations

from pathlib import Path

from fx_backtester.data.loaders import load_market_bars, load_ohlc_csv
from fx_backtester.data.quality import assess_basic_ohlc_quality
from fx_backtester.engine.backtest import BacktestResult, run_backtest
from fx_backtester.engine.benchmark import BenchmarkReport, build_deterministic_benchmarks
from fx_backtester.engine.pipeline import PreparedSignalData, build_signal_pipeline
from fx_backtester.engine.robustness import RobustnessLiteReport, run_robustness_lite
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec
from fx_backtester.reports.artifacts import RunArtifactWriter


def run_backtest_from_csv(
    *,
    csv_path: str | Path,
    spec: StrategySpec,
    policy: ExecutionPolicy,
    repo_root: str | Path,
    run_label: str | None = None,
) -> tuple[BacktestResult, PreparedSignalData, object, Path, RobustnessLiteReport, BenchmarkReport]:
    raw_rows = [row.copy() for row in load_ohlc_csv(csv_path)]
    quality_report = assess_basic_ohlc_quality(raw_rows)
    market_bars = load_market_bars(csv_path)
    prepared = build_signal_pipeline(market_bars=market_bars, spec=spec)
    result = run_backtest(bars=prepared.bars, spec=spec, policy=policy)
    robustness = run_robustness_lite(market_bars=market_bars, spec=spec, policy=policy, baseline_result=result)
    benchmarks = build_deterministic_benchmarks(market_bars=market_bars, baseline_result=result, spec=spec, policy=policy)
    writer = RunArtifactWriter(repo_root)
    run_dir = writer.write_run(
        strategy_name=spec.strategy_name,
        spec=spec,
        policy=policy,
        quality_report=quality_report,
        signal_trace=prepared.signal_trace,
        result=result,
        robustness=robustness,
        benchmarks=benchmarks,
        run_label=run_label,
    )
    return result, prepared, quality_report, run_dir, robustness, benchmarks
