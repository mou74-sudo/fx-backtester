"""CLI entrypoints for the starter scaffold."""

from __future__ import annotations

import json
from pathlib import Path

from fx_backtester.formalizer.execution_policy import default_execution_policy
from fx_backtester.formalizer.spec_models import StrategySpec
from fx_backtester.reports.compliance import build_run_manifest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="fx-backtester starter CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-spec", help="Validate a strategy spec JSON file")
    validate.add_argument("path", type=Path)

    formalize = subparsers.add_parser("formalize-request", help="Formalize a natural-language strategy request into a supported candidate spec")
    formalize.add_argument("path", type=Path, help="Text or markdown file containing the strategy request")
    formalize.add_argument("--output-dir", type=Path, required=True, help="Directory to write strategy_request.txt, formalized_spec.json, and formalizer_notes.json")

    args = parser.parse_args()

    if args.command == "validate-spec":
        raw = json.loads(args.path.read_text(encoding="utf-8"))
        spec = StrategySpec.model_validate(raw)
        manifest = build_run_manifest(spec, default_execution_policy())
        print(json.dumps(manifest, indent=2, sort_keys=True))
    elif args.command == "formalize-request":
        request_text = args.path.read_text(encoding="utf-8")
        outcome = formalize_strategy_request(request_text)
        write_formalization_artifacts(request_text=request_text, outcome=outcome, output_dir=args.output_dir)
        print(
            json.dumps(
                {
                    "status": outcome.notes.status,
                    "output_dir": str(args.output_dir),
                    "validation_errors": outcome.notes.validation_errors,
                    "rejected_fields": [item.model_dump(mode="json") for item in outcome.notes.rejected_fields],
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
