"""Parameter grid search for strategy optimisation.

Tries every combination of the supplied parameter ranges, runs the backtest
engine on each, and returns all results ranked by a chosen metric.

Important — always pair with walk-forward validation
-----------------------------------------------------
Grid search on the full dataset will find the settings that *happened* to work
best on that specific historical period.  That is not the same as finding
settings that will work in the future.

The correct workflow is:
  1. Split your data into in-sample and out-of-sample halves.
  2. Run grid search on the IN-SAMPLE half only.
  3. Take the best parameters and run them on the OUT-OF-SAMPLE half.
  4. If out-of-sample performance is comparable, the edge is likely real.
  5. If out-of-sample is much worse, the params are curve-fitted — try again
     with fewer free parameters or more data.

Usage
-----
    results = run_grid_search(
        bars=market_bars,
        param_grid={
            "rsi_period":     [10, 14, 21],
            "entry_rsi_lte":  [25, 30, 35],
            "stop_loss_pips": [15, 20, 25],
        },
        spec_template=base_spec,
        policy=execution_policy,
        sort_by="net_pips",
        min_trades=5,
    )
    print(results.best)
"""

from __future__ import annotations

import itertools
from typing import Any, Literal

from pydantic import BaseModel

from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import run_backtest
from fx_backtester.engine.pipeline import build_signal_pipeline
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategyRuleAdapter, StrategySpec


# ── Result models ─────────────────────────────────────────────────────────────


class GridSearchResult(BaseModel):
    """Metrics for a single parameter combination."""

    params: dict[str, Any]
    trade_count: int
    net_pips: float
    win_rate: float          # fraction 0–1
    max_drawdown_pct: float  # plain percent, e.g. 5.51 = 5.51 %
    expectancy_pips: float
    ending_equity: float


class GridSearchReport(BaseModel):
    total_combinations: int
    evaluated: int           # combinations that produced at least min_trades
    skipped: int             # combinations skipped (no/few trades, invalid spec)
    sort_by: str
    min_trades: int
    results: list[GridSearchResult]   # sorted best-first by sort_by
    best: GridSearchResult | None = None


# ── Core runner ───────────────────────────────────────────────────────────────

SortMetric = Literal["net_pips", "expectancy_pips", "win_rate", "ending_equity"]

_VALID_PARAMS = frozenset({
    "rsi_period",
    "entry_rsi_lte",
    "short_entry_rsi_gte",
    "exit_rsi_gte",
    "short_exit_rsi_lte",
    "stop_loss_pips",
    "take_profit_pips",
    "breakout_lookback_bars",
    "breakout_buffer_pips",
    "daily_sma_period",
})


def _apply_params(spec: StrategySpec, params: dict[str, Any]) -> StrategySpec:
    """Return a copy of spec with rule fields overridden by params."""
    rule_dict = spec.rules.model_dump()
    rule_dict.update(params)
    new_rules = StrategyRuleAdapter.validate_python(rule_dict)
    return spec.model_copy(update={"rules": new_rules})


def run_grid_search(
    bars: list[MarketBar],
    param_grid: dict[str, list[Any]],
    spec_template: StrategySpec,
    policy: ExecutionPolicy,
    *,
    sort_by: SortMetric = "net_pips",
    min_trades: int = 5,
) -> GridSearchReport:
    """Exhaustive grid search over ``param_grid`` combinations.

    Parameters
    ----------
    bars:
        Market bars to backtest on.  Should be the **in-sample** portion only.
    param_grid:
        Mapping of parameter name → list of values to try.
        Valid keys: rsi_period, entry_rsi_lte, short_entry_rsi_gte,
        exit_rsi_gte, short_exit_rsi_lte, stop_loss_pips, take_profit_pips,
        breakout_lookback_bars, breakout_buffer_pips, daily_sma_period.
    spec_template:
        Base strategy spec — all settings not in param_grid are kept as-is.
    policy:
        Execution policy (spread / slippage assumptions).
    sort_by:
        Metric to rank results by.  One of: ``net_pips``, ``expectancy_pips``,
        ``win_rate``, ``ending_equity``.
    min_trades:
        Combinations producing fewer than this many trades are excluded from
        results (too small a sample to draw conclusions from).
    """
    unknown = set(param_grid) - _VALID_PARAMS
    if unknown:
        raise ValueError(f"Unknown grid search parameters: {unknown}")

    keys   = list(param_grid.keys())
    values = list(param_grid.values())
    combos = list(itertools.product(*values))
    total  = len(combos)

    results:  list[GridSearchResult] = []
    skipped = 0

    for combo in combos:
        params = dict(zip(keys, combo))
        try:
            spec     = _apply_params(spec_template, params)
            prepared = build_signal_pipeline(market_bars=bars, spec=spec)
            result   = run_backtest(bars=prepared.bars, spec=spec, policy=policy)
        except Exception:
            skipped += 1
            continue

        if result.trade_count < min_trades:
            skipped += 1
            continue

        closed = [t for t in result.trades if t.pnl_pips is not None]
        wins   = sum(1 for t in closed if (t.pnl_pips or 0.0) > 0)
        win_rate = round(wins / len(closed), 4) if closed else 0.0

        results.append(GridSearchResult(
            params=params,
            trade_count=result.trade_count,
            net_pips=round(result.metrics.net_pips, 1),
            win_rate=win_rate,
            max_drawdown_pct=round(result.metrics.max_drawdown_pct, 2),
            expectancy_pips=round(result.metrics.expectancy_pips, 2),
            ending_equity=round(result.ending_equity, 2),
        ))

    # Sort best-first.
    results.sort(key=lambda r: getattr(r, sort_by), reverse=True)

    return GridSearchReport(
        total_combinations=total,
        evaluated=len(results),
        skipped=skipped,
        sort_by=sort_by,
        min_trades=min_trades,
        results=results,
        best=results[0] if results else None,
    )
