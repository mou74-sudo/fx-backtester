from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.data.indicators import compute_wilder_atr
from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import BacktestResult, SignalBar, run_backtest
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec


class BenchmarkScenario(BaseModel):
    name: str
    description: str
    benchmark_type: str
    target_trade_count: int = Field(ge=0)
    actual_trade_count: int = Field(ge=0)
    target_hold_bars: int = Field(ge=1)
    actual_average_hold_bars: float = Field(ge=0)
    trade_count_match: bool = False
    hold_length_match: bool = False
    benchmark_quality: str
    comparative_claims_allowed: bool = False
    notes: list[str] = Field(default_factory=list)
    metrics: dict
    evidence_refs: list[str] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    enabled: bool = True
    baseline_trade_count: int = Field(ge=0)
    baseline_average_hold_bars: float = Field(ge=0)
    scenarios: list[BenchmarkScenario] = Field(default_factory=list)


def _direction_cycle(direction: str, count: int) -> list[Literal['buy', 'sell']]:
    if direction == 'short_only':
        return ['sell'] * count
    if direction == 'both':
        return ['buy' if idx % 2 == 0 else 'sell' for idx in range(count)]
    return ['buy'] * count


def _trade_hold_bars(trade: object, index_by_timestamp: dict[datetime, int]) -> int:
    entry_idx = index_by_timestamp.get(trade.entry_time)
    exit_idx = index_by_timestamp.get(trade.exit_time) if trade.exit_time is not None else None
    if entry_idx is None or exit_idx is None:
        return 1
    return max(1, exit_idx - entry_idx)


def _build_synthetic_signal_bars(
    *,
    market_bars: list[MarketBar],
    entry_indices: list[int],
    hold_bars: int,
    sides: list[Literal['buy', 'sell']],
    atr_values: list[float | None],
) -> list[SignalBar]:
    entry_map = {idx: sides[pos] for pos, idx in enumerate(entry_indices)}
    exit_map: dict[int, set[str]] = {}
    for idx, side in zip(entry_indices, sides, strict=True):
        exit_idx = min(len(market_bars) - 1, idx + hold_bars)
        exit_map.setdefault(exit_idx, set()).add(side)

    synthetic: list[SignalBar] = []
    for idx, bar in enumerate(market_bars):
        entry_side = entry_map.get(idx)
        exit_sides = exit_map.get(idx)
        synthetic.append(
            SignalBar(
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                entry_long=entry_side == 'buy',
                entry_short=entry_side == 'sell',
                exit_long=exit_sides is not None and 'buy' in exit_sides,
                exit_short=exit_sides is not None and 'sell' in exit_sides,
                signal_bar_timestamp=bar.timestamp.isoformat() if entry_side is not None else None,
                execution_price=bar.open if entry_side is not None or exit_sides is not None else None,
                atr=atr_values[idx],
                sessions=bar.sessions,
            )
        )
    return synthetic


def build_deterministic_benchmarks(
    *,
    market_bars: list[MarketBar],
    baseline_result: BacktestResult,
    spec: StrategySpec,
    policy: ExecutionPolicy,
) -> BenchmarkReport:
    index_by_timestamp = {bar.timestamp: idx for idx, bar in enumerate(market_bars)}
    hold_bars_list = [_trade_hold_bars(trade, index_by_timestamp) for trade in baseline_result.trades]
    target_trade_count = baseline_result.trade_count
    target_hold_bars = max(1, round(mean(hold_bars_list))) if hold_bars_list else 1
    baseline_average_hold_bars = round(mean(hold_bars_list), 2) if hold_bars_list else 0.0

    if target_trade_count <= 0 or len(market_bars) < 2:
        return BenchmarkReport(enabled=True, baseline_trade_count=target_trade_count, baseline_average_hold_bars=baseline_average_hold_bars)

    min_entry_index = spec.rules.stop_loss_atr_period if spec.rules.stop_loss_style == 'atr' else 0
    max_entry_index = max(min_entry_index, len(market_bars) - target_hold_bars - 1)
    if max_entry_index <= min_entry_index:
        entry_indices = [min_entry_index]
    else:
        entry_indices = sorted({round(min_entry_index + ((max_entry_index - min_entry_index) * idx) / max(target_trade_count - 1, 1)) for idx in range(target_trade_count)})
        while len(entry_indices) < target_trade_count and entry_indices[-1] < max_entry_index:
            entry_indices.append(entry_indices[-1] + 1)
    entry_indices = entry_indices[:target_trade_count]
    sides = _direction_cycle(spec.rules.direction, len(entry_indices))
    atr_values = compute_wilder_atr(
        [bar.high for bar in market_bars],
        [bar.low for bar in market_bars],
        [bar.close for bar in market_bars],
        spec.rules.stop_loss_atr_period,
    )
    synthetic_bars = _build_synthetic_signal_bars(
        market_bars=market_bars,
        entry_indices=entry_indices,
        hold_bars=target_hold_bars,
        sides=sides,
        atr_values=atr_values,
    )
    benchmark_result = run_backtest(bars=synthetic_bars, spec=spec, policy=policy)

    benchmark_hold_bars = [_trade_hold_bars(trade, index_by_timestamp) for trade in benchmark_result.trades]
    actual_average_hold_bars = round(mean(benchmark_hold_bars), 2) if benchmark_hold_bars else 0.0
    trade_count_match = benchmark_result.trade_count == target_trade_count
    hold_length_match = bool(benchmark_hold_bars) and abs(actual_average_hold_bars - target_hold_bars) <= 1.0
    quality = 'matched' if trade_count_match and hold_length_match else 'approximate'
    comparative_claims_allowed = trade_count_match and hold_length_match and target_trade_count >= 5

    scenario = BenchmarkScenario(
        name='deterministic_spaced_entry',
        description='Deterministic evenly spaced entry benchmark matched to baseline trade count and average hold length.',
        benchmark_type='spaced_entry_matched_hold',
        target_trade_count=target_trade_count,
        actual_trade_count=benchmark_result.trade_count,
        target_hold_bars=target_hold_bars,
        actual_average_hold_bars=actual_average_hold_bars,
        trade_count_match=trade_count_match,
        hold_length_match=hold_length_match,
        benchmark_quality=quality,
        comparative_claims_allowed=comparative_claims_allowed,
        notes=[
            'Entries are spaced deterministically across eligible bars.',
            'Exit intent is scheduled after the matched average hold length; stops/TP can still close earlier.',
            'Reviewer comparative claims should only rely on matched benchmarks.',
        ],
        metrics={
            'net_pnl': round(benchmark_result.ending_equity - benchmark_result.starting_equity, 2),
            'net_pips': benchmark_result.metrics.net_pips,
            'expectancy_pips': benchmark_result.metrics.expectancy_pips,
            'max_drawdown': benchmark_result.metrics.max_drawdown,
            'session_summary': benchmark_result.metrics.session_summary,
        },
        evidence_refs=[
            'results/trades.json#baseline',
            'results/metrics.json#trade_count',
            'reports/benchmarks.json#scenarios[0]',
        ],
    )
    return BenchmarkReport(
        enabled=True,
        baseline_trade_count=target_trade_count,
        baseline_average_hold_bars=baseline_average_hold_bars,
        scenarios=[scenario],
    )
