from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewReason(BaseModel):
    code: str
    message: str
    evidence_refs: list[str] = Field(default_factory=list)


class RealismGateResult(BaseModel):
    passed: bool
    failure_flags: list[str] = Field(default_factory=list)
    downgrade_reasons: list[ReviewReason] = Field(default_factory=list)
    hard_fail_reasons: list[ReviewReason] = Field(default_factory=list)
    trade_count: int = 0
    dominant_session: str | None = None
    dominant_session_share: float = 0.0
    worst_spread_net_pnl_ratio: float | None = None
    worst_perturbation_trade_retention: float | None = None


def _check_is_ok(checks: list[dict], name: str) -> bool:
    for check in checks:
        if check.get('name') == name:
            return bool(check.get('ok'))
    return True


def _add_reason(target: list[ReviewReason], *, code: str, message: str, evidence_refs: list[str]) -> None:
    if any(reason.code == code for reason in target):
        return
    target.append(ReviewReason(code=code, message=message, evidence_refs=evidence_refs))


def evaluate_realism_gate(
    *,
    summary: dict,
    metrics: dict,
    compliance_summary: dict,
    robustness_lite: dict | None,
    benchmarks: dict | None = None,
) -> RealismGateResult:
    failure_flags: list[str] = []
    downgrade_reasons: list[ReviewReason] = []
    hard_fail_reasons: list[ReviewReason] = []

    trade_count = int(summary.get('trade_count', metrics.get('trade_count', 0)) or 0)
    checks = compliance_summary.get('checks', [])

    if not _check_is_ok(checks, 'data_quality_basic'):
        failure_flags.append('data_quality_failure')
        _add_reason(hard_fail_reasons, code='data_quality_failure', message='Basic data quality checks failed', evidence_refs=['reports/compliance_summary.json#checks[data_quality_basic]'])
    if not _check_is_ok(checks, 'signal_execution_alignment_no_leakage'):
        failure_flags.append('signal_alignment_failure')
        _add_reason(hard_fail_reasons, code='signal_alignment_failure', message='Signal/execution leakage check failed', evidence_refs=['reports/compliance_summary.json#checks[signal_execution_alignment_no_leakage]'])
    if not _check_is_ok(checks, 'trade_evidence_refs_present'):
        failure_flags.append('missing_trade_evidence')
        _add_reason(hard_fail_reasons, code='missing_trade_evidence', message='Trade evidence references missing', evidence_refs=['reports/compliance_summary.json#checks[trade_evidence_refs_present]', 'results/trades.json#evidence_ref'])
    if not _check_is_ok(checks, 'single_position_only'):
        failure_flags.append('position_policy_failure')
        _add_reason(hard_fail_reasons, code='position_policy_failure', message='Unsupported position policy detected', evidence_refs=['reports/compliance_summary.json#checks[single_position_only]', 'inputs/manifest.json#risk.max_open_positions'])

    session_summary = metrics.get('session_summary', {}) or {}
    dominant_session = None
    dominant_session_share = 0.0
    if robustness_lite is not None:
        concentration = robustness_lite.get('trade_concentration', {}) or {}
        dominant_session = concentration.get('dominant_session')
        dominant_session_share = float(concentration.get('dominant_session_share', 0.0) or 0.0)
    elif session_summary and trade_count > 0:
        dominant_session = max(session_summary, key=lambda name: float(session_summary[name].get('trade_count', 0)))
        dominant_session_share = round(float(session_summary[dominant_session].get('trade_count', 0)) / trade_count, 4)

    if trade_count < 5:
        failure_flags.append('too_few_trades')
        _add_reason(downgrade_reasons, code='too_few_trades', message='Too few trades for stable evidence', evidence_refs=['reports/summary.json#trade_count', 'results/metrics.json#trade_count'])
    elif trade_count < 20:
        _add_reason(downgrade_reasons, code='small_sample', message='Trade sample remains small', evidence_refs=['reports/summary.json#trade_count', 'results/metrics.json#trade_count'])

    if dominant_session_share >= 0.85:
        failure_flags.append('extreme_session_dependence')
        _add_reason(downgrade_reasons, code='extreme_session_dependence', message='Extreme session dependence', evidence_refs=['reports/robustness_lite.json#trade_concentration.dominant_session_share', 'results/metrics.json#session_summary'])
    elif dominant_session_share >= 0.70:
        failure_flags.append('trade_concentration')
        _add_reason(downgrade_reasons, code='trade_concentration', message='Trade concentration is too high', evidence_refs=['reports/robustness_lite.json#trade_concentration.dominant_session_share', 'results/metrics.json#session_summary'])

    worst_spread_net_pnl_ratio = None
    worst_perturbation_trade_retention = None
    if robustness_lite is not None:
        baseline = robustness_lite.get('baseline', {}) or {}
        baseline_net_pnl = float(baseline.get('net_pnl', 0.0) or 0.0)
        baseline_trade_count = int(baseline.get('trade_count', trade_count) or 0)
        scenario_ratios: list[float] = []
        trade_retentions: list[float] = []
        for scenario in robustness_lite.get('scenarios', []) or []:
            scenario_net_pnl = float(scenario.get('net_pnl', 0.0) or 0.0)
            scenario_trade_count = int(scenario.get('trade_count', 0) or 0)
            if baseline_trade_count > 0:
                trade_retentions.append(round(scenario_trade_count / baseline_trade_count, 4))
            if baseline_net_pnl > 0:
                scenario_ratios.append(round(scenario_net_pnl / baseline_net_pnl, 4))
            elif baseline_net_pnl == 0:
                scenario_ratios.append(0.0 if scenario_net_pnl <= 0 else 1.0)

        if scenario_ratios:
            worst_spread_net_pnl_ratio = min(scenario_ratios)
            if worst_spread_net_pnl_ratio < 0.0:
                failure_flags.append('spread_stress_breaks_profitability')
                _add_reason(downgrade_reasons, code='spread_stress_breaks_profitability', message='Spread/slippage stress flips expectancy negative', evidence_refs=['reports/robustness_lite.json#baseline.net_pnl', 'reports/robustness_lite.json#scenarios'])
            elif worst_spread_net_pnl_ratio < 0.5:
                failure_flags.append('spread_stress_sensitive')
                _add_reason(downgrade_reasons, code='spread_stress_sensitive', message='Spread/slippage stress erodes too much PnL', evidence_refs=['reports/robustness_lite.json#baseline.net_pnl', 'reports/robustness_lite.json#scenarios'])

        if trade_retentions:
            worst_perturbation_trade_retention = min(trade_retentions)
            if worst_perturbation_trade_retention < 0.5:
                failure_flags.append('fragile_perturbation_behavior')
                _add_reason(downgrade_reasons, code='fragile_perturbation_behavior', message='Trade retention collapses under perturbations', evidence_refs=['reports/robustness_lite.json#baseline.trade_count', 'reports/robustness_lite.json#scenarios'])
            elif worst_perturbation_trade_retention < 0.8:
                _add_reason(downgrade_reasons, code='material_trade_shift', message='Trade count shifts materially under perturbations', evidence_refs=['reports/robustness_lite.json#baseline.trade_count', 'reports/robustness_lite.json#scenarios'])

    if benchmarks is not None:
        scenario = (benchmarks.get('scenarios') or [{}])[0]
        if scenario and not scenario.get('comparative_claims_allowed', False):
            _add_reason(downgrade_reasons, code='benchmark_not_matched', message='Benchmark exists but is not matched tightly enough for strong comparative claims', evidence_refs=['reports/benchmarks.json#scenarios[0].trade_count_match', 'reports/benchmarks.json#scenarios[0].hold_length_match'])

    return RealismGateResult(
        passed=not hard_fail_reasons,
        failure_flags=sorted(set(failure_flags)),
        downgrade_reasons=sorted(downgrade_reasons, key=lambda item: item.code),
        hard_fail_reasons=sorted(hard_fail_reasons, key=lambda item: item.code),
        trade_count=trade_count,
        dominant_session=dominant_session,
        dominant_session_share=round(dominant_session_share, 4),
        worst_spread_net_pnl_ratio=worst_spread_net_pnl_ratio,
        worst_perturbation_trade_retention=worst_perturbation_trade_retention,
    )
