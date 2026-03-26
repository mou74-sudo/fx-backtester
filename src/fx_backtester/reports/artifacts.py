from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fx_backtester.data.quality import DataQualityReport
from fx_backtester.engine.backtest import BacktestResult
from fx_backtester.engine.pipeline import SignalTraceRow
from fx_backtester.engine.robustness import RobustnessLiteReport
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec
from fx_backtester.reports.compliance import build_compliance_summary, build_run_manifest


class RunArtifactWriter:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self.outputs_root = self.repo_root / "outputs"
        self.outputs_root.mkdir(parents=True, exist_ok=True)

    def create_run_dir(self, strategy_name: str, now: datetime | None = None) -> Path:
        now = now or datetime.now(UTC)
        slug = re.sub(r"[^a-z0-9]+", "-", strategy_name.lower()).strip("-") or "run"
        run_id = f"run_{now.strftime('%Y%m%dT%H%M%SZ')}__{slug}"
        run_dir = self.outputs_root / run_id
        for child in ("inputs", "results", "traces", "reports"):
            (run_dir / child).mkdir(parents=True, exist_ok=False if child == "inputs" else True)
        return run_dir

    def write_run(
        self,
        *,
        strategy_name: str,
        spec: StrategySpec,
        policy: ExecutionPolicy,
        quality_report: DataQualityReport,
        signal_trace: list[SignalTraceRow],
        result: BacktestResult,
        robustness: RobustnessLiteReport | None = None,
    ) -> Path:
        run_dir = self.create_run_dir(strategy_name)
        manifest = build_run_manifest(spec, policy)
        metrics = {
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "ending_equity_usd": result.ending_equity_usd,
            "net_pnl": round(result.ending_equity - result.starting_equity, 2),
            "net_pnl_usd": round(result.ending_equity_usd - result.starting_equity, 2) if spec.risk.account_ccy != "USD" else round(result.ending_equity - result.starting_equity, 2),
            "trade_count": result.trade_count,
            **result.metrics.model_dump(mode="json"),
        }
        quality = {
            "row_count": quality_report.row_count,
            "missing_required_fields": quality_report.missing_required_fields,
            "non_monotonic_timestamps": quality_report.non_monotonic_timestamps,
            "notes": quality_report.notes,
        }
        compliance = build_compliance_summary(
            spec=spec,
            policy=policy,
            result=result,
            quality_report=quality_report,
            signal_trace=signal_trace,
        )
        summary = {
            "run_id": run_dir.name,
            "strategy_name": spec.strategy_name,
            "trade_count": result.trade_count,
            "net_pnl": metrics["net_pnl"],
            "net_pips": result.metrics.net_pips,
            "ending_equity": result.ending_equity,
            "max_drawdown": result.metrics.max_drawdown,
            "robustness_enabled": robustness.enabled if robustness else False,
        }
        files: dict[str, tuple[str, Any]] = {
            "inputs/strategy_spec.json": ("json", spec.model_dump(mode="json")),
            "inputs/manifest.json": ("json", manifest),
            "results/quality_report.json": ("json", quality),
            "results/trades.json": ("json", [trade.model_dump(mode="json") for trade in result.trades]),
            "results/metrics.json": ("json", metrics),
            "traces/signal_trace.json": ("json", [row.model_dump(mode="json") for row in signal_trace]),
            "reports/compliance_summary.json": ("json", compliance),
            "reports/summary.json": ("json", summary),
        }
        if robustness is not None:
            files["reports/robustness_lite.json"] = ("json", robustness.model_dump(mode="json"))

        for relative_name, (kind, payload) in files.items():
            target = run_dir / relative_name
            target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return run_dir
