"""Helpers for evidence-backed run artifacts."""

from __future__ import annotations

from pathlib import Path

from fx_backtester.engine.backtest import BacktestResult
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


def build_compliance_summary(*, spec: StrategySpec, policy: ExecutionPolicy, result: BacktestResult) -> dict:
    """Build a compact deterministic summary for audit/review output."""

    total_pnl = round(result.ending_equity - result.starting_equity, 2)
    wins = sum(1 for trade in result.trades if (trade.pnl_usd or 0.0) > 0)
    losses = sum(1 for trade in result.trades if (trade.pnl_usd or 0.0) < 0)

    return {
        "manifest": build_run_manifest(spec, policy),
        "summary": {
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "net_pnl_usd": total_pnl,
            "trade_count": result.trade_count,
            "wins": wins,
            "losses": losses,
            "open_trades": 0,
        },
        "trades": [trade.model_dump(mode="json") for trade in result.trades],
    }


def ensure_output_dirs(repo_root: str | Path) -> None:
    """Create output directories used by later report writers."""

    repo_root = Path(repo_root)
    (repo_root / "outputs").mkdir(parents=True, exist_ok=True)
