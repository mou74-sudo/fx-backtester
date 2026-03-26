"""Helpers for evidence-backed run artifacts."""

from __future__ import annotations

from pathlib import Path

from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec


def build_run_manifest(spec: StrategySpec, policy: ExecutionPolicy) -> dict:
    """Build a small serializable run manifest for audit trails."""

    return {
        "strategy_name": spec.strategy_name,
        "instrument": spec.instrument.model_dump(),
        "risk": spec.risk.model_dump(),
        "rules": spec.rules.model_dump(),
        "window": spec.window.model_dump(mode="json"),
        "execution_policy": policy.model_dump(),
    }


def ensure_output_dirs(repo_root: str | Path) -> None:
    """Create output directories used by later report writers."""

    repo_root = Path(repo_root)
    (repo_root / "outputs").mkdir(parents=True, exist_ok=True)
