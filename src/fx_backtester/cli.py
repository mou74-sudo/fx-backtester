"""CLI entrypoints for the deterministic FX backtester."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fx_backtester.formalizer.execution_policy import default_execution_policy
from fx_backtester.formalizer.request_formalizer import formalize_strategy_request, write_formalization_artifacts
from fx_backtester.formalizer.spec_models import StrategySpec
from fx_backtester.orchestrator import run_backtest_from_csv
from fx_backtester.reports.analysis import build_analysis_report
from fx_backtester.reports.compliance import build_run_manifest


def _write_json_stdout(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="fx-backtester v1.0 deterministic CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-spec", help="Validate a strategy spec JSON file and print the deterministic manifest")
    validate.add_argument("path", type=Path)

    formalize = subparsers.add_parser("formalize-request", help="Formalize a natural-language strategy request into a supported candidate spec")
    formalize.add_argument("path", type=Path, help="Text or markdown file containing the strategy request")
    formalize.add_argument("--output-dir", type=Path, required=True, help="Directory to write strategy_request.txt, formalized_spec.json, and formalizer_notes.json")

    run = subparsers.add_parser("run-backtest", help="Run the full deterministic pipeline from a validated spec JSON and OHLC CSV")
    run.add_argument("spec", type=Path, help="Path to a strategy spec JSON file")
    run.add_argument("csv", type=Path, help="Path to an OHLC CSV file with timestamp,open,high,low,close columns")
    run.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root used for outputs/ (default: current directory)")
    run.add_argument("--run-label", type=str, default=None, help="Optional deterministic run label. Useful for golden examples.")

    summarize = subparsers.add_parser("summarize-run", help="Read report artifacts from a run directory and restate the deterministic verdict")
    summarize.add_argument("run_dir", type=Path, help="Run directory created under outputs/")

    fetch = subparsers.add_parser(
        "fetch-data",
        help="Download H1 BID bars from Dukascopy and write a CSV ready for run-backtest",
    )
    fetch.add_argument("--instrument", choices=["EURUSD", "USDJPY"], required=True)
    fetch.add_argument("--start", required=True, metavar="YYYY-MM-DD", help="First date to include (UTC)")
    fetch.add_argument("--end", required=True, metavar="YYYY-MM-DD", help="Last date to include (UTC)")
    fetch.add_argument("--output", type=Path, required=True, help="Output CSV path")
    fetch.add_argument("--cache-dir", type=Path, default=Path("data/cache"), help="Local bi5 cache directory (default: data/cache)")

    args = parser.parse_args()

    if args.command == "validate-spec":
        raw = json.loads(args.path.read_text(encoding="utf-8"))
        spec = StrategySpec.model_validate(raw)
        manifest = build_run_manifest(spec, default_execution_policy())
        _write_json_stdout(manifest)
        return

    if args.command == "formalize-request":
        request_text = args.path.read_text(encoding="utf-8")
        outcome = formalize_strategy_request(request_text)
        write_formalization_artifacts(request_text=request_text, outcome=outcome, output_dir=args.output_dir)
        _write_json_stdout(
            {
                "status": outcome.notes.status,
                "output_dir": str(args.output_dir),
                "validation_errors": outcome.notes.validation_errors,
                "rejected_fields": [item.model_dump(mode="json") for item in outcome.notes.rejected_fields],
                "accepted_spec_path": str(args.output_dir / "formalized_spec.json") if outcome.spec is not None else None,
            }
        )
        return

    if args.command == "run-backtest":
        raw = json.loads(args.spec.read_text(encoding="utf-8"))
        spec = StrategySpec.model_validate(raw)
        result, _, _, run_dir, _, _ = run_backtest_from_csv(
            csv_path=args.csv,
            spec=spec,
            policy=default_execution_policy(),
            repo_root=args.repo_root,
            run_label=args.run_label,
        )
        _write_json_stdout(
            {
                "run_dir": str(run_dir),
                "trade_count": result.trade_count,
                "ending_equity": result.ending_equity,
                "summary_report": str(run_dir / "reports" / "summary.json"),
                "final_verdict_report": str(run_dir / "reports" / "final_verdict.json"),
                "research_memo": str(run_dir / "reports" / "research_memo.md"),
            }
        )
        return

    if args.command == "summarize-run":
        report = build_analysis_report(args.run_dir / "reports")
        _write_json_stdout(report.model_dump(mode="json"))
        return

    if args.command == "fetch-data":
        from fx_backtester.data.dukascopy import bars_to_csv, load_dukascopy_h1

        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
        print(f"Fetching {args.instrument} H1 BID  {start_date} → {end_date} …")
        bars = load_dukascopy_h1(
            instrument=args.instrument,
            start=start_date,
            end=end_date,
            cache_dir=args.cache_dir,
            verbose=True,
        )
        bars_to_csv(bars, args.output)
        _write_json_stdout({
            "instrument": args.instrument,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "bar_count": len(bars),
            "output_csv": str(args.output),
            "cache_dir": str(args.cache_dir),
        })
        return


if __name__ == "__main__":
    main()
