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

    args = parser.parse_args()

    if args.command == "validate-spec":
        raw = json.loads(args.path.read_text(encoding="utf-8"))
        spec = StrategySpec.model_validate(raw)
        manifest = build_run_manifest(spec, default_execution_policy())
        print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
