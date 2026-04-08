from __future__ import annotations

import json
from pathlib import Path

import pytest

from fx_backtester.formalizer.execution_policy import default_execution_policy
from fx_backtester.formalizer.request_formalizer import formalize_strategy_request, write_formalization_artifacts
from fx_backtester.formalizer.spec_models import StrategySpec
from fx_backtester.orchestrator import run_backtest_from_csv


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
FIXED_PIPS_DATA = EXAMPLES / "eurusd_rsi_fixed_pips_data.csv"


UNSUPPORTED_REQUESTS = [
    pytest.param(
        "Trade GBP/USD on H4 with MACD confirmation, a trailing stop, and optimization. Account currency CHF.",
        {
            "MACD and Stochastic are not yet implemented.",
            "Optimization/search workflows are unsupported in the formalizer.",
            "Pair GBPUSD is not supported by the deterministic formalizer.",
            "Only H1 is implemented, not H4.",
        },
        id="unsupported_signal_stack",
    ),
    pytest.param(
        "Run a multi-pair EURUSD and USDJPY portfolio basket with hedging and correlation filter on H1.",
        {"Portfolio, basket, or hedge logic is not implemented."},
        id="portfolio_hedging",
    ),
    pytest.param(
        "Trade EURUSD on H1 using RSI plus news sentiment with limit orders and order book confirmation.",
        {"Discretionary/external logic is not supported."},
        id="order_type_news",
    ),
    pytest.param(
        "Trade USDJPY on H1 with Bollinger Bands, walk-forward optimisation, and break-even stop logic.",
        {
            "Break-even, partials, and scaling are not supported.",
            "Optimization/search workflows are unsupported in the formalizer.",
        },
        id="bollinger_walkforward",
    ),
    pytest.param(
        "Trade EURUSD on D1 using a machine learning model, Monte Carlo validation, and trailing stops.",
        {
            "Optimization/search workflows are unsupported in the formalizer.",
            "Discretionary/external logic is not supported.",
            "Only H1 is implemented, not D1.",
        },
        id="ml_montecarlo",
    ),
]


THIN_SUPPORTED_REQUESTS = [
    pytest.param(
        "Trade EUR/USD on H1, long only. Use RSI period 14. Entry RSI below 30 and exit RSI above 55. Stop loss 20 pips. Take profit 30 pips. Initial equity 10000. Risk 1% per trade. Account currency USD.",
        0,
        "fragile",
        {"too_few_trades"},
        id="zero_trade_fixed_pips_long",
    ),
    pytest.param(
        "Trade EUR/USD on H1, long only. Use RSI period 5. Entry RSI below 20 and exit RSI above 60. Use a 2x ATR(5) stop loss and 80 pip take profit. Exit after 3 bars. Initial equity 15000. Risk 1% per trade. Account currency USD.",
        1,
        "weak",
        {"benchmark_not_matched", "extreme_session_dependence", "too_few_trades"},
        id="one_trade_atr_time_stop",
    ),
    pytest.param(
        "Trade EUR/USD on H1, long only. Use RSI period 5. Entry RSI below 20 and exit RSI above 60. Stop loss 20 pips. Take profit 80 pips. Exit on session close. Only trade the London session. Initial equity 15000. Risk 1% per trade. Account currency USD.",
        0,
        "fragile",
        {"too_few_trades"},
        id="zero_trade_session_close",
    ),
    pytest.param(
        "Trade EUR/USD on H1, both directions. Use RSI period 14. Long entry RSI below 30, short entry RSI above 70, exit RSI above 55 and short exit RSI below 45. Stop loss 20 pips. Take profit 30 pips. Initial equity 10000. Risk 1% per trade. Account currency USD.",
        0,
        "fragile",
        {"too_few_trades"},
        id="zero_trade_both_directions",
    ),
    pytest.param(
        "Trade EUR/USD on H1, long only. Use RSI period 14. Entry RSI below 30 and exit RSI above 55. Stop loss 20 pips. Disable take profit. Exit after 4 bars. Initial equity 10000. Risk 1% per trade. Account currency USD.",
        0,
        "fragile",
        {"too_few_trades"},
        id="zero_trade_no_tp_time_stop",
    ),
]


REQUIRED_ARTIFACTS = {
    "inputs/strategy_spec.json",
    "inputs/manifest.json",
    "results/quality_report.json",
    "results/trades.json",
    "results/metrics.json",
    "traces/signal_trace.json",
    "reports/compliance_summary.json",
    "reports/summary.json",
    "reports/artifact_index.json",
    "reports/final_verdict.json",
    "reports/reviewer_summary.json",
    "reports/analysis_summary.json",
    "reports/research_memo.md",
    "reports/robustness_lite.json",
    "reports/benchmarks.json",
}


def _formalize_to_artifacts(request_text: str, tmp_path: Path, name: str):
    outcome = formalize_strategy_request(request_text)
    artifact_dir = write_formalization_artifacts(
        request_text=request_text,
        outcome=outcome,
        output_dir=tmp_path / f"{name}_formalized",
    )
    return outcome, artifact_dir


def _run_formalized_spec(spec_path: Path, repo_root: Path, run_label: str):
    spec = StrategySpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    result, _, _, run_dir, _, _, _ = run_backtest_from_csv(
        csv_path=FIXED_PIPS_DATA,
        spec=spec,
        policy=default_execution_policy(),
        repo_root=repo_root,
        run_label=run_label,
    )
    return result, run_dir


def _load_run_payloads(run_dir: Path) -> dict[str, object]:
    return {
        "summary": json.loads((run_dir / "reports" / "summary.json").read_text(encoding="utf-8")),
        "artifact_index": json.loads((run_dir / "reports" / "artifact_index.json").read_text(encoding="utf-8")),
        "final_verdict": json.loads((run_dir / "reports" / "final_verdict.json").read_text(encoding="utf-8")),
        "reviewer_summary": json.loads((run_dir / "reports" / "reviewer_summary.json").read_text(encoding="utf-8")),
        "analysis_summary": json.loads((run_dir / "reports" / "analysis_summary.json").read_text(encoding="utf-8")),
        "trades": json.loads((run_dir / "results" / "trades.json").read_text(encoding="utf-8")),
        "memo": (run_dir / "reports" / "research_memo.md").read_text(encoding="utf-8"),
    }


@pytest.mark.parametrize(("request_text", "expected_reasons"), UNSUPPORTED_REQUESTS)
def test_pressure_unsupported_requests_are_rejected_cleanly(request_text: str, expected_reasons: set[str], tmp_path: Path) -> None:
    outcome, artifact_dir = _formalize_to_artifacts(request_text, tmp_path, "rejected_case")

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert expected_reasons.issubset({item.reason for item in outcome.notes.rejected_fields})
    assert all(item.nearest_supported for item in outcome.notes.rejected_fields)

    formalized_spec = json.loads((artifact_dir / "formalized_spec.json").read_text(encoding="utf-8"))
    notes = json.loads((artifact_dir / "formalizer_notes.json").read_text(encoding="utf-8"))
    assert formalized_spec is None
    assert notes["status"] == "rejected"
    assert expected_reasons.issubset({item["reason"] for item in notes["rejected_fields"]})


@pytest.mark.parametrize(("request_text", "expected_trade_count", "expected_verdict", "expected_downgrade_codes"), THIN_SUPPORTED_REQUESTS)
def test_pressure_thin_supported_requests_are_downgraded_deterministically(
    request_text: str,
    expected_trade_count: int,
    expected_verdict: str,
    expected_downgrade_codes: set[str],
    tmp_path: Path,
) -> None:
    outcome, artifact_dir = _formalize_to_artifacts(request_text, tmp_path, "thin_case")

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result, run_dir = _run_formalized_spec(artifact_dir / "formalized_spec.json", repo_root, "thin_case")
    payloads = _load_run_payloads(run_dir)

    assert result.trade_count == expected_trade_count
    assert payloads["summary"]["trade_count"] == expected_trade_count
    assert payloads["final_verdict"]["final_verdict"] == expected_verdict
    assert payloads["reviewer_summary"]["final_verdict"] == expected_verdict
    assert expected_downgrade_codes.issubset({item["code"] for item in payloads["final_verdict"]["downgrade_reasons"]})
    assert payloads["summary"]["artifact_schema_version"] == "v1"
    assert payloads["artifact_index"]["artifact_schema_version"] == "v1"


def test_pressure_cross_artifact_consistency_for_thin_one_trade_run(tmp_path: Path) -> None:
    request_text = (
        "Trade EUR/USD on H1, long only. Use RSI period 5. Entry RSI below 20 and exit RSI above 60. "
        "Use a 2x ATR(5) stop loss and 80 pip take profit. Exit after 3 bars. "
        "Initial equity 15000. Risk 1% per trade. Account currency USD."
    )
    outcome, artifact_dir = _formalize_to_artifacts(request_text, tmp_path, "consistency_case")

    assert outcome.notes.status == "accepted"

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    result, run_dir = _run_formalized_spec(artifact_dir / "formalized_spec.json", repo_root, "consistency_case")
    payloads = _load_run_payloads(run_dir)

    actual_files = {str(path.relative_to(run_dir)) for path in run_dir.rglob("*") if path.is_file()}
    assert REQUIRED_ARTIFACTS.issubset(actual_files)

    summary = payloads["summary"]
    final_verdict = payloads["final_verdict"]
    reviewer_summary = payloads["reviewer_summary"]
    analysis_summary = payloads["analysis_summary"]
    trades = payloads["trades"]
    memo = payloads["memo"]

    assert result.trade_count == 1
    assert summary["run_id"] == run_dir.name
    assert final_verdict["final_verdict"] == reviewer_summary["final_verdict"]
    assert analysis_summary["run_id"] == summary["run_id"]
    assert analysis_summary["facts_used"]["summary"]["trade_count"] == summary["trade_count"]
    assert len(trades) == summary["trade_count"]
    assert f"- Verdict: `{final_verdict['final_verdict']}`" in memo
    assert f"- Trade count: `{summary['trade_count']}`" in memo
