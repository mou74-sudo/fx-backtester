import json
from pathlib import Path

from fx_backtester.reports.analysis import build_analysis_report, build_analysis_report_from_payloads


def _payloads() -> dict[str, dict]:
    return {
        'summary.json': {
            'run_id': 'run_20260326T000000Z__demo',
            'strategy_name': 'demo',
            'trade_count': 4,
            'net_pnl': 12.5,
            'net_pips': 7.5,
            'ending_equity': 10012.5,
            'max_drawdown': 18.0,
            'robustness_enabled': True,
        },
        'robustness_lite.json': {
            'enabled': True,
            'baseline': {'trade_count': 4, 'net_pnl': 12.5},
            'trade_concentration': {'dominant_session': 'asia', 'dominant_session_share': 0.9},
            'scenarios': [
                {'name': 'spread_2x', 'trade_count': 1, 'net_pnl': -5.0},
                {'name': 'rsi_shift', 'trade_count': 2, 'net_pnl': 3.0},
            ],
        },
        'benchmarks.json': {
            'enabled': True,
            'baseline_trade_count': 4,
            'baseline_average_hold_bars': 3.0,
            'scenarios': [
                {
                    'name': 'deterministic_spaced_entry',
                    'trade_count_match': True,
                    'hold_length_match': False,
                    'comparative_claims_allowed': False,
                }
            ],
        },
        'reviewer_summary.json': {
            'trade_count': 4,
            'dominant_session': 'asia',
            'dominant_session_share': 0.9,
            'worst_spread_net_pnl_ratio': -0.4,
            'worst_perturbation_trade_retention': 0.25,
        },
        'final_verdict.json': {
            'final_verdict': 'weak',
            'evidence_grade': 'D',
            'confidence_level': 'low',
            'failure_flags': [
                'too_few_trades',
                'extreme_session_dependence',
                'spread_stress_breaks_profitability',
                'fragile_perturbation_behavior',
            ],
            'downgrade_reasons': [
                {
                    'code': 'too_few_trades',
                    'message': 'Too few trades for stable evidence',
                    'evidence_refs': ['reports/summary.json#trade_count'],
                },
                {
                    'code': 'benchmark_not_matched',
                    'message': 'Benchmark exists but is not matched tightly enough for strong comparative claims',
                    'evidence_refs': ['reports/benchmarks.json#scenarios[0].hold_length_match'],
                },
                {
                    'code': 'spread_stress_breaks_profitability',
                    'message': 'Spread/slippage stress flips expectancy negative',
                    'evidence_refs': ['reports/robustness_lite.json#scenarios'],
                },
            ],
            'hard_fail_reasons': [],
            'audit_refs': [
                'reports/benchmarks.json#scenarios[0].hold_length_match',
                'reports/robustness_lite.json#scenarios',
                'reports/summary.json#trade_count',
            ],
        },
    }



def test_analysis_report_restates_deterministic_artifacts() -> None:
    report = build_analysis_report_from_payloads(_payloads())

    assert report.run_id == 'run_20260326T000000Z__demo'
    assert 'Verdict: weak (grade D, confidence low).' in report.pass_fail_summary
    assert 'Run recorded 4 trades, net PnL 12.50, and max drawdown 18.00.' in report.pass_fail_summary
    assert report.ranked_weaknesses[0].code in {
        'extreme_session_dependence',
        'fragile_perturbation_behavior',
        'spread_stress_breaks_profitability',
    }
    assert any(item.code == 'benchmark_not_matched' for item in report.ranked_weaknesses)
    assert any(item.name == 'Expand sample window' for item in report.suggested_next_tests)
    assert any(item.name == 'Tighten benchmark matching' for item in report.suggested_next_tests)
    assert '`weak`' in report.research_memo_markdown
    assert '`4`' in report.research_memo_markdown
    assert 'reports/summary.json#trade_count' in report.research_memo_markdown



def test_analysis_report_reads_expected_report_files(tmp_path: Path) -> None:
    reports_dir = tmp_path / 'reports'
    reports_dir.mkdir()
    for name, payload in _payloads().items():
        (reports_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')

    report = build_analysis_report(reports_dir)

    assert report.strategy_name == 'demo'
    assert report.facts_used['final_verdict']['failure_flags'][0] == 'too_few_trades'
