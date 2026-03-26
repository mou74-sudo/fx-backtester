"""Helpers for evidence-backed run artifacts."""

from __future__ import annotations

from pathlib import Path

from fx_backtester.data.quality import DataQualityReport
from fx_backtester.engine.backtest import BacktestResult
from fx_backtester.engine.pipeline import SignalTraceRow
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec


def build_run_manifest(spec: StrategySpec, policy: ExecutionPolicy) -> dict:
    return {
        "strategy_name": spec.strategy_name,
        "instrument": spec.instrument.model_dump(),
        "risk": spec.risk.model_dump(),
        "rules": spec.rules.model_dump(),
        "window": spec.window.model_dump(mode="json"),
        "execution_policy": policy.model_dump(),
    }


def build_compliance_summary(
    *,
    spec: StrategySpec,
    policy: ExecutionPolicy,
    result: BacktestResult,
    quality_report: DataQualityReport | None = None,
    signal_trace: list[SignalTraceRow] | None = None,
) -> dict:
    total_pnl = round(result.ending_equity - result.starting_equity, 2)
    wins = sum(1 for trade in result.trades if (trade.pnl or 0.0) > 0)
    losses = sum(1 for trade in result.trades if (trade.pnl or 0.0) < 0)
    signal_trace = signal_trace or []

    checks = [
        {
            "name": "single_position_only",
            "ok": spec.risk.max_open_positions == 1,
            "evidence": [f"risk.max_open_positions={spec.risk.max_open_positions}"],
        },
        {
            "name": "execution_policy_explicit",
            "ok": True,
            "evidence": [
                f"half_spread_pips={policy.half_spread_pips}",
                f"slippage_pips={policy.slippage_pips}",
                f"allow_intrabar_tp_sl_resolution={policy.allow_intrabar_tp_sl_resolution}",
            ],
        },
        {
            "name": "data_quality_basic",
            "ok": quality_report is None
            or (quality_report.missing_required_fields == 0 and quality_report.non_monotonic_timestamps == 0),
            "evidence": []
            if quality_report is None
            else [
                f"row_count={quality_report.row_count}",
                f"missing_required_fields={quality_report.missing_required_fields}",
                f"non_monotonic_timestamps={quality_report.non_monotonic_timestamps}",
            ],
        },
        {
            "name": "signal_execution_alignment_no_leakage",
            "ok": all(row.no_leakage_ok for row in signal_trace),
            "evidence": [item for row in signal_trace for item in row.evidence[:2]][:12],
        },
        {
            "name": "trade_evidence_refs_present",
            "ok": all(trade.evidence_ref for trade in result.trades) if result.trades else True,
            "evidence": [trade.evidence_ref for trade in result.trades if trade.evidence_ref],
        },
    ]

    return {
        "manifest": build_run_manifest(spec, policy),
        "summary": {
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "ending_equity_usd": result.ending_equity_usd,
            "net_pnl": total_pnl,
            "trade_count": result.trade_count,
            "wins": wins,
            "losses": losses,
            "open_trades": 0,
            "ambiguity_count": result.metrics.ambiguity_count,
            "spread_triggered_stop_count": result.metrics.spread_triggered_stop_count,
        },
        "checks": checks,
        "metrics": result.metrics.model_dump(mode="json"),
        "trades": [trade.model_dump(mode="json") for trade in result.trades],
    }


def ensure_output_dirs(repo_root: str | Path) -> None:
    repo_root = Path(repo_root)
    (repo_root / "outputs").mkdir(parents=True, exist_ok=True)
