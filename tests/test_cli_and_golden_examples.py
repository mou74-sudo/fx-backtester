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


def test_cli_happy_path_fixed_pips_example(tmp_path: Path) -> None:
    formalized_dir = tmp_path / "formalized_fixed_pips"
    formalize = _run_cli(
        "formalize-request",
        str(EXAMPLES / "eurusd_rsi_fixed_pips_request.txt"),
        "--output-dir",
        str(formalized_dir),
    )
    assert formalize["status"] == "accepted"

    validate = _run_cli("validate-spec", str(EXAMPLES / "eurusd_rsi_fixed_pips_spec.json"))
    assert validate["rules"]["stop_loss_style"] == "fixed_pips"

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run = _run_cli(
        "run-backtest",
        str(EXAMPLES / "eurusd_rsi_fixed_pips_spec.json"),
        str(EXAMPLES / "eurusd_rsi_fixed_pips_data.csv"),
        "--repo-root",
        str(repo_root),
        "--run-label",
        "golden_fixed_pips",
    )
    assert run["trade_count"] == 1

    run_dir = Path(run["run_dir"])
    summary = json.loads((run_dir / "reports" / "summary.json").read_text(encoding="utf-8"))
    verdict = json.loads((run_dir / "reports" / "final_verdict.json").read_text(encoding="utf-8"))
    memo = (run_dir / "reports" / "research_memo.md").read_text(encoding="utf-8")
    artifact_index = json.loads((run_dir / "reports" / "artifact_index.json").read_text(encoding="utf-8"))

    assert summary["artifact_schema_version"] == "v1"
    assert summary["trade_count"] == 1
    assert verdict["final_verdict"] in {"fail", "weak", "pass"}
    assert "Research memo" in memo
    assert "reports/analysis_summary.json" in artifact_index["paths"]["reports"]


def test_cli_happy_path_atr_session_close_example(tmp_path: Path) -> None:
    formalized_dir = tmp_path / "formalized_atr"
    formalize = _run_cli(
        "formalize-request",
        str(EXAMPLES / "eurusd_rsi_atr_time_stop_request.txt"),
        "--output-dir",
        str(formalized_dir),
    )
    assert formalize["status"] == "accepted"

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run = _run_cli(
        "run-backtest",
        str(EXAMPLES / "eurusd_rsi_atr_time_stop_spec.json"),
        str(EXAMPLES / "eurusd_rsi_atr_time_stop_data.csv"),
        "--repo-root",
        str(repo_root),
        "--run-label",
        "golden_atr_time_stop",
    )
    run_dir = Path(run["run_dir"])

    trades = json.loads((run_dir / "results" / "trades.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "reports" / "summary.json").read_text(encoding="utf-8"))
    analysis = _run_cli("summarize-run", str(run_dir))

    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "time_stop"
    assert summary["artifact_schema_version"] == "v1"
    assert analysis["run_id"] == run_dir.name
    assert analysis["facts_used"]["summary"]["trade_count"] == 1
