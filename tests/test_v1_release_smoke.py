from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _run_cli(*args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "fx_backtester.cli", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_v1_release_happy_path_request_to_spec_to_run_to_verdict_to_memo(tmp_path: Path) -> None:
    formalized_dir = tmp_path / "formalized"
    formalize = _run_cli(
        "formalize-request",
        str(EXAMPLES / "eurusd_rsi_fixed_pips_request.txt"),
        "--output-dir",
        str(formalized_dir),
    )

    assert formalize["status"] == "accepted"
    spec_path = Path(formalize["accepted_spec_path"])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["instrument"]["symbol"] == "EURUSD"
    assert spec["rules"]["timeframe"] == "H1"

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run = _run_cli(
        "run-backtest",
        str(spec_path),
        str(EXAMPLES / "eurusd_rsi_fixed_pips_data.csv"),
        "--repo-root",
        str(repo_root),
        "--run-label",
        "ci_smoke_v1",
    )

    run_dir = Path(run["run_dir"])
    summary = json.loads((run_dir / "reports" / "summary.json").read_text(encoding="utf-8"))
    verdict = json.loads((run_dir / "reports" / "final_verdict.json").read_text(encoding="utf-8"))
    analysis = _run_cli("summarize-run", str(run_dir))
    memo = (run_dir / "reports" / "research_memo.md").read_text(encoding="utf-8")
    artifact_index = json.loads((run_dir / "reports" / "artifact_index.json").read_text(encoding="utf-8"))

    assert run_dir.name == "ci-smoke-v1"
    assert summary["artifact_schema_version"] == "v1"
    assert summary["trade_count"] == 1
    assert verdict["final_verdict"] in {"invalid", "fail", "weak", "pass", "provisionally_credible"}
    assert analysis["run_id"] == "ci-smoke-v1"
    assert analysis["facts_used"]["summary"]["trade_count"] == 1
    assert "Research memo" in memo
    assert "Verdict:" in memo

    expected_paths = {
        "reports/summary.json",
        "reports/artifact_index.json",
        "reports/final_verdict.json",
        "reports/reviewer_summary.json",
        "reports/analysis_summary.json",
        "reports/research_memo.md",
        "reports/robustness_lite.json",
        "reports/benchmarks.json",
    }
    assert expected_paths.issubset(set(artifact_index["paths"]["reports"]))
