from __future__ import annotations

from pydantic import BaseModel

from fx_backtester.reviewer.realism_gate import RealismGateResult, ReviewReason


class ReviewerAssessment(BaseModel):
    evidence_grade: str
    confidence_level: str
    final_verdict: str
    failure_flags: list[str]
    downgrade_reasons: list[ReviewReason]
    hard_fail_reasons: list[ReviewReason]
    score: int


_GRADE_FLOOR_BY_FLAG = {
    'spread_stress_breaks_profitability': 'D',
    'spread_stress_sensitive': 'C',
    'trade_concentration': 'C',
    'extreme_session_dependence': 'D',
    'fragile_perturbation_behavior': 'D',
    'too_few_trades': 'C',
}

_GRADE_ORDER = ['F', 'D', 'C', 'B', 'A']


def _min_grade(first: str, second: str) -> str:
    return first if _GRADE_ORDER.index(first) < _GRADE_ORDER.index(second) else second


def grade_evidence(gate: RealismGateResult) -> ReviewerAssessment:
    if not gate.passed:
        return ReviewerAssessment(
            evidence_grade='F',
            confidence_level='low',
            final_verdict='invalid',
            failure_flags=gate.failure_flags,
            downgrade_reasons=gate.downgrade_reasons,
            hard_fail_reasons=gate.hard_fail_reasons,
            score=0,
        )

    evidence_grade = 'A'
    for flag in gate.failure_flags:
        floor = _GRADE_FLOOR_BY_FLAG.get(flag)
        if floor is not None:
            evidence_grade = _min_grade(evidence_grade, floor)

    if gate.trade_count < 50:
        evidence_grade = _min_grade(evidence_grade, 'B')
    if gate.trade_count < 20:
        evidence_grade = _min_grade(evidence_grade, 'C')
    if gate.trade_count < 5:
        evidence_grade = _min_grade(evidence_grade, 'C')

    if gate.trade_count >= 50 and not gate.failure_flags:
        confidence_level = 'high'
    elif gate.trade_count >= 20 and 'too_few_trades' not in gate.failure_flags:
        confidence_level = 'medium'
    else:
        confidence_level = 'low'

    if evidence_grade == 'A':
        final_verdict = 'credible'
    elif evidence_grade == 'B':
        final_verdict = 'provisionally_credible'
    elif evidence_grade == 'C':
        final_verdict = 'fragile'
    else:
        final_verdict = 'weak'

    score_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
    return ReviewerAssessment(
        evidence_grade=evidence_grade,
        confidence_level=confidence_level,
        final_verdict=final_verdict,
        failure_flags=gate.failure_flags,
        downgrade_reasons=gate.downgrade_reasons,
        hard_fail_reasons=gate.hard_fail_reasons,
        score=score_map[evidence_grade],
    )
