from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fx_backtester.data.quality import DataQualityReport
from fx_backtester.engine.backtest import BacktestResult
from fx_backtester.engine.pipeline import SignalTraceRow
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
        run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{strategy_name}"
        run_dir = self.outputs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
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
    ) -> Path:
        run_dir = self.create_run_dir(strategy_name)
        manifest = build_run_manifest(spec, policy)
        metrics = {
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "net_pnl_usd": round(result.ending_equity - result.starting_equity, 2),
            "trade_count": result.trade_count,
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
        files: dict[str, Any] = {
            "strategy_spec.json": spec.model_dump(mode="json"),
            "manifest.json": manifest,
            "quality_report.json": quality,
            "signal_trace.json": [row.model_dump(mode="json") for row in signal_trace],
            "trades.json": [trade.model_dump(mode="json") for trade in result.trades],
            "metrics.json": metrics,
            "compliance_summary.json": compliance,
        }
        for name, payload in files.items():
            (run_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return run_dir
