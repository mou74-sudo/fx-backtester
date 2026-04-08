"""Bayesian parameter optimisation using Optuna (TPE sampler).

Replaces brute-force grid search with a smart search that learns from each
trial and focuses on promising parameter regions.

Key difference from grid search
--------------------------------
Grid search: tries every fixed combination — O(n^k) runs.
Bayesian:    starts random, then narrows in — converges in ~100 trials
             regardless of how many parameters you have.

Objective score
---------------
The default composite score rewards:

    score = sharpe_ratio
          + (net_pips / 1000)        ← small pip bonus
          - (max_drawdown_pct / 100) ← drawdown penalty

Strategies with good Sharpe AND low drawdown score highest.
Returns None (pruned) when too few trades — Optuna skips those.

Usage
-----
    from fx_backtester.analysis.bayesian_optimiser import run_bayesian_optimisation, ParamSpace

    spaces = {
        "entry_rsi_lte":       ParamSpace(kind="int",   low=20,  high=45),
        "short_entry_rsi_gte": ParamSpace(kind="int",   low=55,  high=80),
        "stop_loss_pips":      ParamSpace(kind="int",   low=100, high=300),
        "take_profit_pips":    ParamSpace(kind="int",   low=200, high=600),
    }
    report = run_bayesian_optimisation(
        bars=is_bars, spaces=spaces, spec_template=spec, policy=policy,
        n_trials=100, min_trades=10,
    )
    print(report.best)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from fx_backtester.analysis.grid_search import GridSearchResult, _apply_params
from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import run_backtest
from fx_backtester.engine.pipeline import build_signal_pipeline
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec

# Silence Optuna's per-trial logging — we surface results ourselves
optuna_logger = logging.getLogger("optuna")
optuna_logger.setLevel(logging.WARNING)


# ── Parameter space definition ────────────────────────────────────────────────


@dataclass
class ParamSpace:
    """Define the search space for one parameter.

    kind="int"         → trial.suggest_int(name, low, high)
    kind="float"       → trial.suggest_float(name, low, high)
    kind="categorical" → trial.suggest_categorical(name, choices)
    """
    kind: Literal["int", "float", "categorical"]
    low: float | int | None = None
    high: float | int | None = None
    choices: list[Any] | None = None

    def suggest(self, trial: Any, name: str) -> Any:
        if self.kind == "int":
            return trial.suggest_int(name, int(self.low), int(self.high))
        if self.kind == "float":
            return trial.suggest_float(name, float(self.low), float(self.high))
        if self.kind == "categorical":
            return trial.suggest_categorical(name, self.choices)
        raise ValueError(f"Unknown ParamSpace kind: {self.kind}")


# ── Result model ──────────────────────────────────────────────────────────────


class BayesianOptResult(BaseModel):
    """Single trial result — superset of GridSearchResult."""
    trial_number: int
    params: dict[str, Any]
    score: float
    trade_count: int
    net_pips: float
    win_rate: float
    max_drawdown_pct: float
    expectancy_pips: float
    sharpe_ratio: float | None
    ending_equity: float


class BayesianOptReport(BaseModel):
    n_trials: int
    completed: int        # trials that produced >= min_trades
    pruned: int           # trials with too few trades or invalid spec
    sort_by: str
    min_trades: int
    results: list[BayesianOptResult]   # sorted best-first by score
    best: BayesianOptResult | None = None

    def to_grid_search_result(self) -> GridSearchResult | None:
        """Convert best result to GridSearchResult for UI compatibility."""
        if self.best is None:
            return None
        return GridSearchResult(
            params=self.best.params,
            trade_count=self.best.trade_count,
            net_pips=self.best.net_pips,
            win_rate=self.best.win_rate,
            max_drawdown_pct=self.best.max_drawdown_pct,
            expectancy_pips=self.best.expectancy_pips,
            ending_equity=self.best.ending_equity,
        )


# ── Core runner ───────────────────────────────────────────────────────────────


def _score(result: Any) -> float:
    """Composite objective: Sharpe + small pip bonus - drawdown penalty."""
    sharpe = result.metrics.sharpe_ratio or 0.0
    pips   = result.metrics.net_pips
    dd     = result.metrics.max_drawdown_pct
    return round(sharpe + (pips / 1_000) - (dd / 100), 4)


def run_bayesian_optimisation(
    bars: list[MarketBar],
    spaces: dict[str, ParamSpace],
    spec_template: StrategySpec,
    policy: ExecutionPolicy,
    *,
    n_trials: int = 100,
    min_trades: int = 10,
    progress_callback: Any | None = None,
) -> BayesianOptReport:
    """Run Optuna TPE optimisation over the supplied parameter spaces.

    Parameters
    ----------
    bars:
        Market bars — should be the **in-sample** portion only.
    spaces:
        Mapping of parameter name → ParamSpace defining the search range.
    spec_template:
        Base strategy spec; all fields not in ``spaces`` are kept as-is.
    policy:
        Execution policy (spread / slippage).
    n_trials:
        Number of Optuna trials to run.  100 is usually sufficient.
    min_trades:
        Trials producing fewer trades than this are pruned (score = -inf).
    progress_callback:
        Optional callable(completed, total) called after each trial — use
        to update a Streamlit progress bar.
    """
    try:
        import optuna
    except ImportError as exc:
        raise ImportError(
            "Optuna is required for Bayesian optimisation. "
            "Install it with: pip install optuna"
        ) from exc

    results: list[BayesianOptResult] = []
    pruned_count = 0

    def objective(trial: Any) -> float:
        nonlocal pruned_count

        # Sample parameters from each space
        params = {name: space.suggest(trial, name) for name, space in spaces.items()}

        try:
            spec     = _apply_params(spec_template, params)
            prepared = build_signal_pipeline(market_bars=bars, spec=spec)
            result   = run_backtest(bars=prepared.bars, spec=spec, policy=policy)
        except Exception:
            pruned_count += 1
            raise optuna.exceptions.TrialPruned()

        if result.trade_count < min_trades:
            pruned_count += 1
            raise optuna.exceptions.TrialPruned()

        closed   = [t for t in result.trades if t.pnl_pips is not None]
        wins     = sum(1 for t in closed if (t.pnl_pips or 0.0) > 0)
        win_rate = round(wins / len(closed), 4) if closed else 0.0
        score    = _score(result)

        results.append(BayesianOptResult(
            trial_number=trial.number,
            params=params,
            score=score,
            trade_count=result.trade_count,
            net_pips=round(result.metrics.net_pips, 1),
            win_rate=win_rate,
            max_drawdown_pct=round(result.metrics.max_drawdown_pct, 2),
            expectancy_pips=round(result.metrics.expectancy_pips, 2),
            sharpe_ratio=result.metrics.sharpe_ratio,
            ending_equity=round(result.ending_equity, 2),
        ))

        if progress_callback is not None:
            progress_callback(len(results), n_trials)

        return score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    results.sort(key=lambda r: r.score, reverse=True)

    return BayesianOptReport(
        n_trials=n_trials,
        completed=len(results),
        pruned=pruned_count,
        sort_by="score",
        min_trades=min_trades,
        results=results,
        best=results[0] if results else None,
    )
