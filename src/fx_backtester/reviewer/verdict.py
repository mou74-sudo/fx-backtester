from __future__ import annotations

from pydantic import BaseModel

from fx_backtester.reviewer.grading import ReviewerAssessment, grade_evidence
from fx_backtester.reviewer.realism_gate import RealismGateResult, evaluate_realism_gate


class ReviewerArtifacts(BaseModel):
    final_verdict: dict
    reviewer_summary: dict
    realism_gate: RealismGateResult
    assessment: ReviewerAssessment


def _reason_payload(reasons: list) -> list[dict]:
    return [reason.model_dump(mode='json') for reason in reasons]


def build_reviewer_artifacts(
    *,
    summary: dict,
    metrics: dict,
    compliance_summary: dict,
    robustness_lite: dict | None,
    benchmarks: dict | None = None,
) -> ReviewerArtifacts:
    gate = evaluate_realism_gate(
        summary=summary,
        metrics=metrics,
        compliance_summary=compliance_summary,
        robustness_lite=robustness_lite,
        benchmarks=benchmarks,
    )
    assessment = grade_evidence(gate)

    final_verdict = {
        'final_verdict': assessment.final_verdict,
        'evidence_grade': assessment.evidence_grade,
        'confidence_level': assessment.confidence_level,
        'failure_flags': assessment.failure_flags,
        'downgrade_reasons': _reason_payload(assessment.downgrade_reasons),
        'hard_fail_reasons': _reason_payload(assessment.hard_fail_reasons),
        'audit_refs': sorted({ref for reason in assessment.downgrade_reasons + assessment.hard_fail_reasons for ref in reason.evidence_refs}),
    }
    reviewer_summary = {
        'score': assessment.score,
        'trade_count': gate.trade_count,
        'dominant_session': gate.dominant_session,
        'dominant_session_share': gate.dominant_session_share,
        'worst_spread_net_pnl_ratio': gate.worst_spread_net_pnl_ratio,
        'worst_perturbation_trade_retention': gate.worst_perturbation_trade_retention,
        'benchmark_context': benchmarks,
        'inputs_used': {
            'summary': sorted(summary.keys()),
            'metrics': sorted(metrics.keys()),
            'compliance_checks': [check.get('name') for check in compliance_summary.get('checks', [])],
            'robustness_present': robustness_lite is not None,
            'benchmarks_present': benchmarks is not None,
        },
        **final_verdict,
    }
    return ReviewerArtifacts(
        final_verdict=final_verdict,
        reviewer_summary=reviewer_summary,
        realism_gate=gate,
        assessment=assessment,
    )
