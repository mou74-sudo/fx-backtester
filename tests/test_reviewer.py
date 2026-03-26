from fx_backtester.reviewer.verdict import build_reviewer_artifacts


def _base_inputs() -> tuple[dict, dict, dict, dict, dict]:
    summary = {
        'run_id': 'run_20260326T000000Z__demo',
        'strategy_name': 'demo',
        'trade_count': 30,
        'net_pnl': 120.0,
        'net_pips': 55.0,
        'ending_equity': 10_120.0,
        'max_drawdown': 40.0,
        'robustness_enabled': True,
    }
    metrics = {
        'trade_count': 30,
        'session_summary': {
            'asia': {'trade_count': 10, 'net_pnl': 20.0, 'net_pips': 8.0},
            'london': {'trade_count': 12, 'net_pnl': 60.0, 'net_pips': 28.0},
            'new_york': {'trade_count': 8, 'net_pnl': 40.0, 'net_pips': 19.0},
        },
    }
    compliance = {
        'checks': [
            {'name': 'single_position_only', 'ok': True},
            {'name': 'data_quality_basic', 'ok': True},
            {'name': 'signal_execution_alignment_no_leakage', 'ok': True},
            {'name': 'trade_evidence_refs_present', 'ok': True},
        ]
    }
    robustness = {
        'baseline': {'trade_count': 30, 'net_pnl': 120.0},
        'trade_concentration': {
            'dominant_session': 'london',
            'dominant_session_share': 0.4,
        },
        'scenarios': [
            {'name': 'base', 'trade_count': 28, 'net_pnl': 90.0},
            {'name': 'stress', 'trade_count': 25, 'net_pnl': 70.0},
        ],
    }
    benchmarks = {
        'enabled': True,
        'baseline_trade_count': 30,
        'baseline_average_hold_bars': 3.0,
        'scenarios': [
            {
                'name': 'deterministic_spaced_entry',
                'trade_count_match': True,
                'hold_length_match': True,
                'comparative_claims_allowed': True,
            }
        ],
    }
    return summary, metrics, compliance, robustness, benchmarks


def test_reviewer_marks_clean_run_as_provisionally_credible() -> None:
    summary, metrics, compliance, robustness, benchmarks = _base_inputs()

    artifacts = build_reviewer_artifacts(
        summary=summary,
        metrics=metrics,
        compliance_summary=compliance,
        robustness_lite=robustness,
        benchmarks=benchmarks,
    )

    assert artifacts.final_verdict['final_verdict'] == 'provisionally_credible'
    assert artifacts.final_verdict['evidence_grade'] == 'B'
    assert artifacts.final_verdict['confidence_level'] == 'medium'
    assert artifacts.final_verdict['failure_flags'] == []
    assert artifacts.final_verdict['audit_refs'] == []


def test_reviewer_invalidates_compliance_failures_with_evidence_refs() -> None:
    summary, metrics, compliance, robustness, benchmarks = _base_inputs()
    compliance['checks'][1]['ok'] = False

    artifacts = build_reviewer_artifacts(
        summary=summary,
        metrics=metrics,
        compliance_summary=compliance,
        robustness_lite=robustness,
        benchmarks=benchmarks,
    )

    assert artifacts.final_verdict['final_verdict'] == 'invalid'
    assert artifacts.final_verdict['evidence_grade'] == 'F'
    assert 'data_quality_failure' in artifacts.final_verdict['failure_flags']
    assert artifacts.final_verdict['hard_fail_reasons']
    assert artifacts.final_verdict['hard_fail_reasons'][0]['evidence_refs']


def test_reviewer_downgrades_fragile_and_concentrated_runs_with_audit_links() -> None:
    summary, metrics, compliance, robustness, benchmarks = _base_inputs()
    summary['trade_count'] = 4
    metrics['trade_count'] = 4
    robustness['baseline']['trade_count'] = 4
    robustness['trade_concentration']['dominant_session_share'] = 0.9
    robustness['scenarios'] = [
        {'name': 'spread_2x', 'trade_count': 1, 'net_pnl': -10.0},
        {'name': 'rsi_shift', 'trade_count': 2, 'net_pnl': 20.0},
    ]
    benchmarks['scenarios'][0]['comparative_claims_allowed'] = False
    benchmarks['scenarios'][0]['hold_length_match'] = False

    artifacts = build_reviewer_artifacts(
        summary=summary,
        metrics=metrics,
        compliance_summary=compliance,
        robustness_lite=robustness,
        benchmarks=benchmarks,
    )

    assert artifacts.final_verdict['final_verdict'] == 'weak'
    assert artifacts.final_verdict['evidence_grade'] == 'D'
    assert artifacts.final_verdict['confidence_level'] == 'low'
    assert 'too_few_trades' in artifacts.final_verdict['failure_flags']
    assert 'extreme_session_dependence' in artifacts.final_verdict['failure_flags']
    assert 'fragile_perturbation_behavior' in artifacts.final_verdict['failure_flags']
    assert 'spread_stress_breaks_profitability' in artifacts.final_verdict['failure_flags']
    reason_codes = {reason['code'] for reason in artifacts.final_verdict['downgrade_reasons']}
    assert 'benchmark_not_matched' in reason_codes
    assert all(reason['evidence_refs'] for reason in artifacts.final_verdict['downgrade_reasons'])
