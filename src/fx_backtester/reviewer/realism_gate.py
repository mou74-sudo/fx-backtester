from __future__ import annotations

from pydantic import BaseModel, Field


class RealismGateResult(BaseModel):
    passed: bool
    failure_flags: list[str] = Field(default_factory=list)
    downgrade_reasons: list[str] = Field(default_factory=list)
    hard_fail_reasons: list[str] = Field(default_factory=list)
    trade_count: int = 0
    dominant_session: str | None = None
    dominant_session_share: float = 0.0
    worst_spread_net_pnl_ratio: float | None = None
    worst_perturbation_trade_retention: float | None = None



def _check_is_ok(checks: list[dict], name: str) -> bool:
    for check in checks:
        if check.get("name") == name:
            return bool(check.get("ok"))
    return True



def evaluate_realism_gate(
    *,
    summary: dict,
    metrics: dict,
    compliance_summary: dict,
    robustness_lite: dict | None,
) -> RealismGateResult:
    failure_flags: list[str] = []
    downgrade_reasons: list[str] = []
    hard_fail_reasons: list[str] = []

    trade_count = int(summary.get("trade_count", metrics.get("trade_count", 0)) or 0)
    checks = compliance_summary.get("checks", [])

    if not _check_is_ok(checks, "data_quality_basic"):
        failure_flags.append("data_quality_failure")
        hard_fail_reasons.append("Basic data quality checks failed")
    if not _check_is_ok(checks, "signal_execution_alignment_no_leakage"):
        failure_flags.append("signal_alignment_failure")
        hard_fail_reasons.append("Signal/execution leakage check failed")
    if not _check_is_ok(checks, "trade_evidence_refs_present"):
        failure_flags.append("missing_trade_evidence")
        hard_fail_reasons.append("Trade evidence references missing")
    if not _check_is_ok(checks, "single_position_only"):
        failure_flags.append("position_policy_failure")
        hard_fail_reasons.append("Unsupported position policy detected")

    session_summary = metrics.get("session_summary", {}) or {}
    dominant_session = None
    dominant_session_share = 0.0
    if robustness_lite is not None:
        concentration = robustness_lite.get("trade_concentration", {}) or {}
        dominant_session = concentration.get("dominant_session")
        dominant_session_share = float(concentration.get("dominant_session_share", 0.0) or 0.0)
    elif session_summary and trade_count > 0:
        dominant_session = max(session_summary, key=lambda name: float(session_summary[name].get("trade_count", 0)))
        dominant_session_share = round(float(session_summary[dominant_session].get("trade_count", 0)) / trade_count, 4)

    if trade_count < 5:
        failure_flags.append("too_few_trades")
        downgrade_reasons.append("Too few trades for stable evidence")
    elif trade_count < 20:
        downgrade_reasons.append("Trade sample remains small")

    if dominant_session_share >= 0.85:
        failure_flags.append("extreme_session_dependence")
        downgrade_reasons.append("Extreme session dependence")
    elif dominant_session_share >= 0.70:
        failure_flags.append("trade_concentration")
        downgrade_reasons.append("Trade concentration is too high")

    worst_spread_net_pnl_ratio = None
    worst_perturbation_trade_retention = None
    if robustness_lite is not None:
        baseline = robustness_lite.get("baseline", {}) or {}
        baseline_net_pnl = float(baseline.get("net_pnl", 0.0) or 0.0)
        baseline_trade_count = int(baseline.get("trade_count", trade_count) or 0)
        scenario_ratios: list[float] = []
        trade_retentions: list[float] = []
        for scenario in robustness_lite.get("scenarios", []) or []:
            scenario_net_pnl = float(scenario.get("net_pnl", 0.0) or 0.0)
            scenario_trade_count = int(scenario.get("trade_count", 0) or 0)
            if baseline_trade_count > 0:
                trade_retentions.append(round(scenario_trade_count / baseline_trade_count, 4))
            if baseline_net_pnl > 0:
                scenario_ratios.append(round(scenario_net_pnl / baseline_net_pnl, 4))
            elif baseline_net_pnl == 0:
                scenario_ratios.append(0.0 if scenario_net_pnl <= 0 else 1.0)

        if scenario_ratios:
            worst_spread_net_pnl_ratio = min(scenario_ratios)
            if worst_spread_net_pnl_ratio < 0.0:
                failure_flags.append("spread_stress_breaks_profitability")
                downgrade_reasons.append("Spread/slippage stress flips expectancy negative")
            elif worst_spread_net_pnl_ratio < 0.5:
                failure_flags.append("spread_stress_sensitive")
                downgrade_reasons.append("Spread/slippage stress erodes too much PnL")

        if trade_retentions:
            worst_perturbation_trade_retention = min(trade_retentions)
            if worst_perturbation_trade_retention < 0.5:
                failure_flags.append("fragile_perturbation_behavior")
                downgrade_reasons.append("Trade retention collapses under perturbations")
            elif worst_perturbation_trade_retention < 0.8:
                downgrade_reasons.append("Trade count shifts materially under perturbations")

    return RealismGateResult(
        passed=not hard_fail_reasons,
        failure_flags=sorted(set(failure_flags)),
        downgrade_reasons=sorted(set(downgrade_reasons)),
        hard_fail_reasons=hard_fail_reasons,
        trade_count=trade_count,
        dominant_session=dominant_session,
        dominant_session_share=round(dominant_session_share, 4),
        worst_spread_net_pnl_ratio=worst_spread_net_pnl_ratio,
        worst_perturbation_trade_retention=worst_perturbation_trade_retention,
    )
