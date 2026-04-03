from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RankedWeakness(BaseModel):
    rank: int = Field(ge=1)
    code: str
    title: str
    severity: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)


class SuggestedNextTest(BaseModel):
    priority: int = Field(ge=1)
    name: str
    why: str
    evidence_refs: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    run_id: str
    strategy_name: str
    pass_fail_summary: str
    research_memo_markdown: str
    ranked_weaknesses: list[RankedWeakness] = Field(default_factory=list)
    suggested_next_tests: list[SuggestedNextTest] = Field(default_factory=list)
    facts_used: dict[str, Any]


_REQUIRED_REPORTS = [
    'summary.json',
    'robustness_lite.json',
    'benchmarks.json',
    'reviewer_summary.json',
    'final_verdict.json',
]

_SEVERITY_RANK = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

_FLAG_TITLES = {
    'data_quality_failure': 'Data quality checks failed',
    'signal_alignment_failure': 'Signal/execution alignment failed',
    'missing_trade_evidence': 'Trade evidence references missing',
    'position_policy_failure': 'Position policy unsupported',
    'spread_stress_breaks_profitability': 'Profitability breaks under spread/slippage stress',
    'spread_stress_sensitive': 'Profitability is sensitive to spread/slippage stress',
    'trade_concentration': 'Trades are concentrated in one session',
    'extreme_session_dependence': 'Trades depend too heavily on one session',
    'fragile_perturbation_behavior': 'Trade count collapses under perturbations',
    'too_few_trades': 'Trade sample is too small',
}

_NEXT_TEST_RECOMMENDATIONS = {
    'too_few_trades': ('Expand sample window', 'Increase the tested period until the strategy has a materially larger trade sample.'),
    'small_sample': ('Expand sample window', 'The evidence base is still small; extend the sample before making strong claims.'),
    'spread_stress_breaks_profitability': ('Run harsher cost stress slices', 'Profitability flips negative under cost stress; test additional spread/slippage regimes and session-specific costs.'),
    'spread_stress_sensitive': ('Quantify cost sensitivity', 'PnL erodes materially under stress; map profitability across more spread/slippage settings.'),
    'trade_concentration': ('Test session restrictions', 'Session concentration is elevated; run per-session and excluded-session variants to see if the edge survives.'),
    'extreme_session_dependence': ('Isolate dominant session', 'The edge appears heavily session-bound; validate the strategy with and without the dominant session.'),
    'fragile_perturbation_behavior': ('Sweep nearby parameters', 'Trade retention falls sharply under small perturbations; test a denser grid around the current parameter set.'),
    'benchmark_not_matched': ('Tighten benchmark matching', 'Benchmark matching is not tight enough for strong comparative claims; improve count/hold matching first.'),
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def load_analysis_inputs(reports_dir: str | Path) -> dict[str, dict[str, Any]]:
    reports_path = Path(reports_dir)
    payloads: dict[str, dict[str, Any]] = {}
    for name in _REQUIRED_REPORTS:
        target = reports_path / name
        if not target.exists():
            raise FileNotFoundError(f'missing required report artifact: {target}')
        payloads[name] = _load_json(target)
    return payloads


def _reason_severity(code: str, category: str) -> str:
    if category == 'hard_fail':
        return 'critical'
    if code in {'spread_stress_breaks_profitability', 'extreme_session_dependence', 'fragile_perturbation_behavior'}:
        return 'high'
    if code in {'spread_stress_sensitive', 'trade_concentration', 'too_few_trades'}:
        return 'medium'
    return 'low'


def _collect_weaknesses(final_verdict: dict[str, Any]) -> list[RankedWeakness]:
    weaknesses: list[RankedWeakness] = []
    seen: set[str] = set()
    reason_groups = [
        ('hard_fail', final_verdict.get('hard_fail_reasons', []) or []),
        ('downgrade', final_verdict.get('downgrade_reasons', []) or []),
    ]

    for category, reasons in reason_groups:
        for reason in reasons:
            code = str(reason.get('code', 'unknown'))
            if code in seen:
                continue
            seen.add(code)
            weaknesses.append(
                RankedWeakness(
                    rank=1,
                    code=code,
                    title=_FLAG_TITLES.get(code, code.replace('_', ' ')),
                    severity=_reason_severity(code, category),
                    rationale=str(reason.get('message', '')).strip() or _FLAG_TITLES.get(code, code),
                    evidence_refs=list(reason.get('evidence_refs', []) or []),
                )
            )

    for flag in final_verdict.get('failure_flags', []) or []:
        if flag in seen:
            continue
        seen.add(flag)
        weaknesses.append(
            RankedWeakness(
                rank=1,
                code=str(flag),
                title=_FLAG_TITLES.get(str(flag), str(flag).replace('_', ' ')),
                severity=_reason_severity(str(flag), 'flag'),
                rationale=_FLAG_TITLES.get(str(flag), str(flag).replace('_', ' ')),
                evidence_refs=[],
            )
        )

    weaknesses.sort(key=lambda item: (_SEVERITY_RANK[item.severity], item.code))
    for idx, weakness in enumerate(weaknesses, start=1):
        weakness.rank = idx
    return weaknesses


def _collect_next_tests(final_verdict: dict[str, Any]) -> list[SuggestedNextTest]:
    codes: list[str] = []
    codes.extend(str(flag) for flag in (final_verdict.get('failure_flags', []) or []))
    for reason in (final_verdict.get('downgrade_reasons', []) or []):
        code = str(reason.get('code', ''))
        if code:
            codes.append(code)

    suggestions: list[SuggestedNextTest] = []
    seen_names: set[str] = set()
    for code in codes:
        recommendation = _NEXT_TEST_RECOMMENDATIONS.get(code)
        if recommendation is None:
            continue
        name, why = recommendation
        if name in seen_names:
            continue
        seen_names.add(name)
        evidence_refs: list[str] = []
        for reason in (final_verdict.get('downgrade_reasons', []) or []) + (final_verdict.get('hard_fail_reasons', []) or []):
            if reason.get('code') == code:
                evidence_refs = list(reason.get('evidence_refs', []) or [])
                break
        suggestions.append(SuggestedNextTest(priority=1, name=name, why=why, evidence_refs=evidence_refs))

    if not suggestions:
        suggestions.append(
            SuggestedNextTest(
                priority=0,
                name='Add out-of-sample confirmation',
                why='The current deterministic artifacts do not expose an obvious failure mode; validate the same rules on a separate period before increasing confidence.',
                evidence_refs=['reports/summary.json', 'reports/final_verdict.json'],
            )
        )

    for idx, suggestion in enumerate(suggestions, start=1):
        suggestion.priority = idx
    return suggestions


def _build_pass_fail_summary(summary: dict[str, Any], reviewer_summary: dict[str, Any], final_verdict: dict[str, Any]) -> str:
    verdict = str(final_verdict.get('final_verdict', 'unknown'))
    grade = str(final_verdict.get('evidence_grade', 'unknown'))
    confidence = str(final_verdict.get('confidence_level', 'unknown'))
    trade_count = int(summary.get('trade_count', 0) or 0)
    net_pnl = float(summary.get('net_pnl', 0.0) or 0.0)
    max_drawdown = float(summary.get('max_drawdown', 0.0) or 0.0)
    flags = list(final_verdict.get('failure_flags', []) or [])

    base = (
        f"Verdict: {verdict} (grade {grade}, confidence {confidence}). "
        f"Run recorded {trade_count} trades, net PnL {net_pnl:.2f}, and max drawdown {max_drawdown:.2f}."
    )
    if flags:
        titles = [_FLAG_TITLES.get(flag, flag.replace('_', ' ')) for flag in flags[:3]]
        return base + f" Main reasons: {', '.join(titles)}."
    dominant_session = reviewer_summary.get('dominant_session')
    if dominant_session:
        share = float(reviewer_summary.get('dominant_session_share', 0.0) or 0.0)
        return base + f" No failure flags were raised; dominant tagged session was {dominant_session} ({share:.0%} of trades)."
    return base + ' No failure flags were raised by the deterministic reviewer.'


def _build_research_memo(*, summary: dict[str, Any], reviewer_summary: dict[str, Any], final_verdict: dict[str, Any], weaknesses: list[RankedWeakness], next_tests: list[SuggestedNextTest]) -> str:
    verdict = final_verdict.get('final_verdict', 'unknown')
    grade = final_verdict.get('evidence_grade', 'unknown')
    confidence = final_verdict.get('confidence_level', 'unknown')
    trade_count = int(summary.get('trade_count', 0) or 0)
    net_pnl = float(summary.get('net_pnl', 0.0) or 0.0)
    net_pips = float(summary.get('net_pips', 0.0) or 0.0)
    ending_equity = float(summary.get('ending_equity', 0.0) or 0.0)
    max_drawdown = float(summary.get('max_drawdown', 0.0) or 0.0)
    max_drawdown_pct = float(summary.get('max_drawdown_pct', 0.0) or 0.0)   # plain %, e.g. 5.51
    dominant_session = reviewer_summary.get('dominant_session') or 'n/a'
    dominant_session_share = float(reviewer_summary.get('dominant_session_share', 0.0) or 0.0)

    weakness_lines = [f"{item.rank}. {item.title} [{item.severity}] — {item.rationale}" for item in weaknesses] or ['1. No explicit weaknesses were raised by the reviewer artifacts.']
    next_test_lines = [f"{item.priority}. {item.name} — {item.why}" for item in next_tests]
    audit_refs = final_verdict.get('audit_refs', []) or []
    audit_ref_lines = '\n'.join(f'- `{ref}`' for ref in audit_refs) if audit_refs else '- none'

    return (
        f"# Research memo: {summary.get('strategy_name', 'unknown')}\n\n"
        f"## Deterministic verdict snapshot\n"
        f"- Verdict: `{verdict}`\n"
        f"- Evidence grade: `{grade}`\n"
        f"- Confidence: `{confidence}`\n"
        f"- Trade count: `{trade_count}`\n"
        f"- Net PnL: `{net_pnl:.2f}`\n"
        f"- Net pips: `{net_pips:.2f}`\n"
        f"- Ending equity: `{ending_equity:.2f}`\n"
        f"- Max drawdown: `{max_drawdown:.2f}` ({max_drawdown_pct:.2f}%)\n"
        f"- Dominant tagged session: `{dominant_session}` ({dominant_session_share:.0%})\n\n"
        f"## Interpretation\n"
        f"This memo is a read-only interpretation layer. It does not change the deterministic verdict, benchmarks, or grading outputs. It restates the existing artifacts in plain English and points back to their evidence refs.\n\n"
        f"## Ranked weaknesses\n"
        + '\n'.join(f'- {line}' for line in weakness_lines)
        + "\n\n## Suggested next tests\n"
        + '\n'.join(f'- {line}' for line in next_test_lines)
        + "\n\n## Audit references\n"
        + audit_ref_lines
    )


def build_analysis_report_from_payloads(payloads: dict[str, dict[str, Any]]) -> AnalysisReport:
    summary = payloads['summary.json']
    reviewer_summary = payloads['reviewer_summary.json']
    final_verdict = payloads['final_verdict.json']
    weaknesses = _collect_weaknesses(final_verdict)
    next_tests = _collect_next_tests(final_verdict)
    pass_fail_summary = _build_pass_fail_summary(summary, reviewer_summary, final_verdict)
    research_memo_markdown = _build_research_memo(
        summary=summary,
        reviewer_summary=reviewer_summary,
        final_verdict=final_verdict,
        weaknesses=weaknesses,
        next_tests=next_tests,
    )

    facts_used = {
        'summary': summary,
        'robustness_lite': payloads['robustness_lite.json'],
        'benchmarks': payloads['benchmarks.json'],
        'reviewer_summary': reviewer_summary,
        'final_verdict': final_verdict,
    }

    return AnalysisReport(
        run_id=str(summary.get('run_id', 'unknown')),
        strategy_name=str(summary.get('strategy_name', 'unknown')),
        pass_fail_summary=pass_fail_summary,
        research_memo_markdown=research_memo_markdown,
        ranked_weaknesses=weaknesses,
        suggested_next_tests=next_tests,
        facts_used=facts_used,
    )


def build_analysis_report(reports_dir: str | Path) -> AnalysisReport:
    return build_analysis_report_from_payloads(load_analysis_inputs(reports_dir))
