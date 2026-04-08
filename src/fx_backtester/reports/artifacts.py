from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fx_backtester.analysis.mae_mfe import MaeMfeReport
from fx_backtester.data.quality import DataQualityReport
from fx_backtester.engine.backtest import BacktestResult
from fx_backtester.engine.benchmark import BenchmarkReport
from fx_backtester.engine.pipeline import SignalTraceRow
from fx_backtester.engine.robustness import RobustnessLiteReport
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec
from fx_backtester.reports.analysis import build_analysis_report_from_payloads
from fx_backtester.reports.compliance import build_compliance_summary, build_run_manifest
from fx_backtester.reviewer.verdict import build_reviewer_artifacts

_ARTIFACT_SCHEMA_VERSION = "v1"


class RunArtifactWriter:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self.outputs_root = self.repo_root / "outputs"
        self.outputs_root.mkdir(parents=True, exist_ok=True)

    def create_run_dir(self, strategy_name: str, now: datetime | None = None, run_label: str | None = None) -> Path:
        now = now or datetime.now(UTC)
        slug_source = run_label or strategy_name
        slug = re.sub(r"[^a-z0-9]+", "-", slug_source.lower()).strip("-") or "run"
        prefix = slug if run_label else f"run_{now.strftime('%Y%m%dT%H%M%SZ')}__{slug}"
        run_dir = self.outputs_root / prefix
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
        benchmarks: BenchmarkReport | None = None,
        mae_mfe: MaeMfeReport | None = None,
        run_label: str | None = None,
    ) -> Path:
        run_dir = self.create_run_dir(strategy_name, run_label=run_label)
        manifest = build_run_manifest(spec, policy)
        metrics = {
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "ending_equity_usd": result.ending_equity_usd,
            "net_pnl": round(result.ending_equity - result.starting_equity, 2),
            "net_pnl_usd": round(sum(t.pnl_usd or 0.0 for t in result.trades), 2),
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
            "artifact_schema_version": _ARTIFACT_SCHEMA_VERSION,
            "run_id": run_dir.name,
            "strategy_name": spec.strategy_name,
            "trade_count": result.trade_count,
            "net_pnl": metrics["net_pnl"],
            "net_pips": result.metrics.net_pips,
            "ending_equity": result.ending_equity,
            "max_drawdown": result.metrics.max_drawdown,
            "max_drawdown_pct": result.metrics.max_drawdown_pct,  # plain percent, e.g. 5.51 = 5.51%
            "robustness_enabled": robustness.enabled if robustness else False,
        }
        robustness_payload = robustness.model_dump(mode="json") if robustness is not None else None
        benchmarks_payload = benchmarks.model_dump(mode="json") if benchmarks is not None else None
        reviewer = build_reviewer_artifacts(
            summary=summary,
            metrics=metrics,
            compliance_summary=compliance,
            robustness_lite=robustness_payload,
            benchmarks=benchmarks_payload,
        )
        artifact_index = {
            "artifact_schema_version": _ARTIFACT_SCHEMA_VERSION,
            "run_id": run_dir.name,
            "paths": {
                "inputs": ["inputs/strategy_spec.json", "inputs/manifest.json"],
                "results": ["results/quality_report.json", "results/trades.json", "results/metrics.json"],
                "traces": ["traces/signal_trace.json"],
                "reports": [
                    "reports/compliance_summary.json",
                    "reports/summary.json",
                    "reports/artifact_index.json",
                    "reports/final_verdict.json",
                    "reports/reviewer_summary.json",
                    "reports/analysis_summary.json",
                    "reports/research_memo.md",
                ],
            },
        }
        if robustness is not None:
            artifact_index["paths"]["reports"].append("reports/robustness_lite.json")
        if benchmarks is not None:
            artifact_index["paths"]["reports"].append("reports/benchmarks.json")
        if mae_mfe is not None:
            artifact_index["paths"]["results"].append("results/mae_mfe.json")

        files: dict[str, tuple[str, Any]] = {
            "inputs/strategy_spec.json": ("json", spec.model_dump(mode="json")),
            "inputs/manifest.json": ("json", manifest),
            "results/quality_report.json": ("json", quality),
            "results/trades.json": ("json", [trade.model_dump(mode="json") for trade in result.trades]),
            "results/metrics.json": ("json", metrics),
            "traces/signal_trace.json": ("json", [row.model_dump(mode="json") for row in signal_trace]),
            "reports/compliance_summary.json": ("json", compliance),
            "reports/summary.json": ("json", summary),
            "reports/final_verdict.json": ("json", reviewer.final_verdict),
            "reports/reviewer_summary.json": ("json", reviewer.reviewer_summary),
            "reports/artifact_index.json": ("json", artifact_index),
        }
        if robustness is not None:
            files["reports/robustness_lite.json"] = ("json", robustness_payload)
        if benchmarks is not None:
            files["reports/benchmarks.json"] = ("json", benchmarks_payload)
        if mae_mfe is not None:
            files["results/mae_mfe.json"] = ("json", mae_mfe.model_dump(mode="json"))

        analysis = build_analysis_report_from_payloads(
            {
                "summary.json": summary,
                "robustness_lite.json": robustness_payload or {"enabled": False, "baseline": {}, "scenarios": []},
                "benchmarks.json": benchmarks_payload or {"enabled": False, "scenarios": []},
                "reviewer_summary.json": reviewer.reviewer_summary,
                "final_verdict.json": reviewer.final_verdict,
            }
        )
        files["reports/analysis_summary.json"] = ("json", analysis.model_dump(mode="json"))
        files["reports/research_memo.md"] = ("text", analysis.research_memo_markdown)

        for relative_name, (kind, payload) in files.items():
            target = run_dir / relative_name
            if kind == "json":
                target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            else:
                target.write_text(str(payload), encoding="utf-8")
        return run_dir
