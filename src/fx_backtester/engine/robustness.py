from __future__ import annotations

from copy import deepcopy

from pydantic import BaseModel, Field

from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import BacktestResult, run_backtest
from fx_backtester.engine.pipeline import build_signal_pipeline
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec


class RobustnessScenarioResult(BaseModel):
    name: str
    variant: dict[str, object]
    trade_count: int
    ending_equity: float
    net_pnl: float
    net_pips: float
    max_drawdown: float


class RobustnessLiteReport(BaseModel):
    enabled: bool
    baseline: RobustnessScenarioResult
    scenarios: list[RobustnessScenarioResult]
    trade_concentration: dict[str, object]
    session_contribution_summary: dict[str, dict[str, float | int]]
    # Describes which parameters were actually swept.  For non-RSI strategies,
    # only spread/slippage is varied — strategy-specific params (BB period, EMA
    # period, etc.) are not varied because the module only supports RSI period
    # sweeps.  Surfaced here so callers can warn the user instead of silently
    # presenting incomplete robustness results.
    strategy_params_varied: list[str] = []



def _build_scenario_result(name: str, variant: dict[str, object], result: BacktestResult) -> RobustnessScenarioResult:
    return RobustnessScenarioResult(
        name=name,
        variant=variant,
        trade_count=result.trade_count,
        ending_equity=result.ending_equity,
        net_pnl=round(result.ending_equity - result.starting_equity, 2),
        net_pips=result.metrics.net_pips,
        max_drawdown=result.metrics.max_drawdown,
    )



def _trade_concentration(result: BacktestResult) -> dict[str, object]:
    total = max(result.trade_count, 1)
    session_counts = {session: int(bucket["trade_count"]) for session, bucket in result.metrics.session_summary.items()}
    dominant_session = max(session_counts, key=session_counts.get) if session_counts else None
    dominant_share = round((session_counts[dominant_session] / total), 4) if dominant_session else 0.0
    return {
        "session_trade_counts": session_counts,
        "dominant_session": dominant_session,
        "dominant_session_share": dominant_share,
        "flagged": dominant_share > 0.7,
        "notes": ["flagged when one tagged session contributes >70% of trades"],
    }



def run_robustness_lite(*, market_bars: list[MarketBar], spec: StrategySpec, policy: ExecutionPolicy, baseline_result: BacktestResult | None = None) -> RobustnessLiteReport:
    baseline_result = baseline_result or run_backtest(
        bars=build_signal_pipeline(market_bars=market_bars, spec=spec).bars,
        spec=spec,
        policy=policy,
    )
    baseline_variant = {"spread_multiplier": 1.0, "slippage_mode": policy.slippage_model}
    if spec.rules.strategy_type == "rsi_mean_reversion":
        baseline_variant["rsi_period"] = spec.rules.rsi_period
    baseline = _build_scenario_result("baseline", baseline_variant, baseline_result)

    scenarios: list[RobustnessScenarioResult] = []
    if spec.robustness.enabled:
        for spread_multiplier in spec.robustness.spread_multipliers:
            for slippage_mode in spec.robustness.slippage_modes:
                rsi_variants = spec.robustness.rsi_period_variants if spec.rules.strategy_type == "rsi_mean_reversion" else [0]
                for rsi_offset in rsi_variants:
                    scenario_spec = deepcopy(spec)
                    scenario_policy = deepcopy(policy)
                    scenario_policy.half_spread_pips = round(policy.half_spread_pips * spread_multiplier, 6)
                    scenario_policy.slippage_model = "fixed" if slippage_mode == "base" else "worse_case"
                    variant = {
                        "spread_multiplier": spread_multiplier,
                        "slippage_mode": slippage_mode,
                    }
                    name = f"spread_{spread_multiplier:g}x__slippage_{slippage_mode}"
                    if scenario_spec.rules.strategy_type == "rsi_mean_reversion":
                        scenario_spec.rules.rsi_period = max(2, spec.rules.rsi_period + rsi_offset)
                        variant["rsi_period"] = scenario_spec.rules.rsi_period
                        name = f"{name}__rsi_{scenario_spec.rules.rsi_period}"
                    prepared = build_signal_pipeline(market_bars=market_bars, spec=scenario_spec)
                    result = run_backtest(bars=prepared.bars, spec=scenario_spec, policy=scenario_policy)
                    scenarios.append(
                        _build_scenario_result(
                            name=name,
                            variant=variant,
                            result=result,
                        )
                    )

    strategy_params_varied: list[str] = ["spread_multiplier", "slippage_mode"]
    if spec.rules.strategy_type == "rsi_mean_reversion" and len(spec.robustness.rsi_period_variants) > 1:
        strategy_params_varied.append("rsi_period")

    return RobustnessLiteReport(
        enabled=spec.robustness.enabled,
        baseline=baseline,
        scenarios=scenarios,
        trade_concentration=_trade_concentration(baseline_result),
        session_contribution_summary=baseline_result.metrics.session_summary,
        strategy_params_varied=strategy_params_varied,
    )
