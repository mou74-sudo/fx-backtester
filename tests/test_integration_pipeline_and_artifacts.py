from __future__ import annotations

import json
from pathlib import Path

from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import BacktestWindow, InstrumentSpec, RiskSpec, RsiMeanReversionRule, StrategySpec
from fx_backtester.orchestrator import run_backtest_from_csv


def test_csv_to_rsi_to_execution_to_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    (repo_root / 'outputs').mkdir()

    csv_path = tmp_path / 'eurusd.csv'
    csv_path.write_text(
        'timestamp,open,high,low,close\n'
        '2024-01-01T00:00:00Z,1.1000,1.1002,1.0998,1.1000\n'
        '2024-01-01T01:00:00Z,1.1000,1.1001,1.0988,1.0990\n'
        '2024-01-01T02:00:00Z,1.0990,1.0991,1.0978,1.0980\n'
        '2024-01-01T03:00:00Z,1.0980,1.0981,1.0968,1.0970\n'
        '2024-01-01T04:00:00Z,1.0970,1.0971,1.0958,1.0960\n'
        '2024-01-01T05:00:00Z,1.0960,1.0961,1.0948,1.0950\n'
        '2024-01-01T06:00:00Z,1.0950,1.0963,1.0949,1.0962\n'
        '2024-01-01T07:00:00Z,1.0962,1.0976,1.0961,1.0974\n'
        '2024-01-01T08:00:00Z,1.0974,1.0988,1.0973,1.0986\n'
        '2024-01-01T09:00:00Z,1.0986,1.1000,1.0985,1.0998\n'
        '2024-01-01T10:00:00Z,1.0998,1.1005,1.0997,1.1004\n'
        '2024-01-01T11:00:00Z,1.1004,1.1006,1.1001,1.1005\n',
        encoding='utf-8',
    )

    spec = StrategySpec(
        strategy_name='integration_rsi',
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(rsi_period=5, entry_rsi_lte=20, exit_rsi_gte=60, stop_loss_pips=20, take_profit_pips=80),
        window=BacktestWindow(start_date='2024-01-01', end_date='2024-01-02'),
        execution_policy_name='default_v0_2',
    )
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)

    result, prepared, quality_report, run_dir, robustness, benchmarks = run_backtest_from_csv(
        csv_path=csv_path,
        spec=spec,
        policy=policy,
        repo_root=repo_root,
    )

    assert quality_report.row_count == 12
    entry_rows = [row for row in prepared.signal_trace if row.entry_signal]
    exit_rows = [row for row in prepared.signal_trace if row.exit_signal]
    assert entry_rows
    assert exit_rows
    assert all(row.no_leakage_ok for row in prepared.signal_trace)

    assert result.trade_count == 1
    trade = result.trades[0]
    assert trade.entry_time.isoformat() == '2024-01-01T06:00:00+00:00'
    assert trade.exit_time is not None
    assert trade.exit_time.isoformat() == '2024-01-01T10:00:00+00:00'
    assert trade.evidence_ref == 'signal=2024-01-01T05:00:00+00:00|execution=2024-01-01T06:00:00+00:00'

    assert run_dir.name.startswith('run_')
    expected_files = {
        'inputs/strategy_spec.json',
        'inputs/manifest.json',
        'results/quality_report.json',
        'results/trades.json',
        'results/metrics.json',
        'traces/signal_trace.json',
        'reports/compliance_summary.json',
        'reports/summary.json',
        'reports/robustness_lite.json',
        'reports/benchmarks.json',
        'reports/final_verdict.json',
        'reports/reviewer_summary.json',
    }
    actual_files = {str(path.relative_to(run_dir)) for path in run_dir.rglob('*.json')}
    assert expected_files.issubset(actual_files)

    compliance = json.loads((run_dir / 'reports' / 'compliance_summary.json').read_text(encoding='utf-8'))
    assert any(check['name'] == 'signal_execution_alignment_no_leakage' and check['ok'] for check in compliance['checks'])
    assert compliance['metrics']['session_summary']
    signal_trace = json.loads((run_dir / 'traces' / 'signal_trace.json').read_text(encoding='utf-8'))
    final_verdict = json.loads((run_dir / 'reports' / 'final_verdict.json').read_text(encoding='utf-8'))
    reviewer_summary = json.loads((run_dir / 'reports' / 'reviewer_summary.json').read_text(encoding='utf-8'))
    assert 'asia' in signal_trace[0]['sessions']
    assert 'london' in signal_trace[7]['sessions']
    assert robustness.baseline.trade_count == result.trade_count
    assert benchmarks.scenarios
    assert final_verdict['evidence_grade'] in {'B', 'C', 'D', 'F', 'A'}
    assert final_verdict['confidence_level'] in {'low', 'medium', 'high'}
    assert reviewer_summary['trade_count'] == result.trade_count


def test_dst_session_tagging_stays_consistent_across_london_shift(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    (repo_root / 'outputs').mkdir()

    csv_path = tmp_path / 'dst-session-check.csv'
    csv_path.write_text(
        'timestamp,open,high,low,close\n'
        '2024-03-31T05:30:00Z,1.1000,1.1002,1.0998,1.1000\n'
        '2024-03-31T06:30:00Z,1.1000,1.1002,1.0998,1.1000\n',
        encoding='utf-8',
    )

    spec = StrategySpec(
        strategy_name='dst_check',
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30),
        window=BacktestWindow(start_date='2024-03-31', end_date='2024-03-31'),
    )
    policy = ExecutionPolicy()

    _, prepared, _, _, _, _ = run_backtest_from_csv(csv_path=csv_path, spec=spec, policy=policy, repo_root=repo_root)

    assert 'london' not in prepared.signal_trace[0].sessions
    assert 'london' in prepared.signal_trace[1].sessions
