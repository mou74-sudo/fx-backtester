"""Tests for parameter grid search.

Covers:
  - correct number of combinations tested
  - min_trades filter excludes sparse results
  - results sorted correctly by each metric
  - best result matches top of sorted list
  - unknown parameter raises ValueError
  - empty param_grid runs single combination (the template)
  - skipped count is correct
  - results are serialisable
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fx_backtester.analysis.grid_search import GridSearchReport, run_grid_search
from fx_backtester.data.models import MarketBar
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import (
    BacktestWindow,
    InstrumentSpec,
    RiskSpec,
    RsiMeanReversionRule,
    StrategySpec,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_BASE = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


def _bar(h: int, close: float) -> MarketBar:
    return MarketBar(
        timestamp=_BASE + timedelta(hours=h),
        open=close, high=close + 0.0010, low=close - 0.0010, close=close,
        sessions=["london"],
    )


def _oscillating_bars(n: int = 300) -> list[MarketBar]:
    """Bars that alternate direction to generate RSI signals."""
    bars = []
    for h in range(n):
        if (h // 8) % 2 == 0:
            p = 1.1000 - (h % 8) * 0.0004
        else:
            p = 1.0968 + (h % 8) * 0.0004
        bars.append(_bar(h, p))
    return bars


def _spec() -> StrategySpec:
    return StrategySpec(
        strategy_name="grid_test",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(
            rsi_period=14,
            entry_rsi_lte=30.0,
            exit_rsi_gte=55.0,
            short_entry_rsi_gte=70.0,
            short_exit_rsi_lte=45.0,
            stop_loss_pips=20.0,
            take_profit_pips=30.0,
        ),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-12-31"),
    )


_POLICY = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)


# ── Combination count ─────────────────────────────────────────────────────────

def test_total_combinations_is_product_of_grid_sizes() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30]},
        _spec(), _POLICY, min_trades=0,
    )
    assert report.total_combinations == 6  # 3 × 2


def test_evaluated_plus_skipped_equals_total() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30]},
        _spec(), _POLICY, min_trades=0,
    )
    assert report.evaluated + report.skipped == report.total_combinations


# ── min_trades filter ─────────────────────────────────────────────────────────

def test_min_trades_zero_includes_all_valid_combos() -> None:
    bars = _oscillating_bars(300)
    report_strict = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25]},
        _spec(), _POLICY, min_trades=50,
    )
    report_loose = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25]},
        _spec(), _POLICY, min_trades=0,
    )
    assert report_loose.evaluated >= report_strict.evaluated


def test_all_results_meet_min_trades() -> None:
    bars = _oscillating_bars(300)
    min_t = 3
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30]},
        _spec(), _POLICY, min_trades=min_t,
    )
    for r in report.results:
        assert r.trade_count >= min_t


# ── Sorting ───────────────────────────────────────────────────────────────────

def test_results_sorted_by_net_pips_descending() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30, 40]},
        _spec(), _POLICY, sort_by="net_pips", min_trades=0,
    )
    pips = [r.net_pips for r in report.results]
    assert pips == sorted(pips, reverse=True)


def test_results_sorted_by_win_rate_descending() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30, 40]},
        _spec(), _POLICY, sort_by="win_rate", min_trades=0,
    )
    rates = [r.win_rate for r in report.results]
    assert rates == sorted(rates, reverse=True)


def test_results_sorted_by_expectancy_descending() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30]},
        _spec(), _POLICY, sort_by="expectancy_pips", min_trades=0,
    )
    exp = [r.expectancy_pips for r in report.results]
    assert exp == sorted(exp, reverse=True)


# ── Best result ───────────────────────────────────────────────────────────────

def test_best_is_first_result() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20, 25], "take_profit_pips": [20, 30]},
        _spec(), _POLICY, min_trades=0,
    )
    if report.results:
        assert report.best == report.results[0]


def test_best_is_none_when_no_results() -> None:
    bars = _oscillating_bars(50)  # too few bars for any trades with min_trades=1000
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [20]},
        _spec(), _POLICY, min_trades=1000,
    )
    assert report.best is None
    assert report.evaluated == 0


# ── Unknown parameter ─────────────────────────────────────────────────────────

def test_unknown_parameter_raises() -> None:
    bars = _oscillating_bars(300)
    with pytest.raises(ValueError, match="Unknown"):
        run_grid_search(bars, {"nonexistent_param": [1, 2]}, _spec(), _POLICY)


# ── Empty grid ────────────────────────────────────────────────────────────────

def test_empty_param_grid_runs_single_combo() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(bars, {}, _spec(), _POLICY, min_trades=0)
    assert report.total_combinations == 1


# ── Result fields ─────────────────────────────────────────────────────────────

def test_result_params_match_grid_keys() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [20, 25]},
        _spec(), _POLICY, min_trades=0,
    )
    for r in report.results:
        assert "stop_loss_pips" in r.params


def test_result_win_rate_in_range() -> None:
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [15, 20], "take_profit_pips": [25, 30]},
        _spec(), _POLICY, min_trades=0,
    )
    for r in report.results:
        assert 0.0 <= r.win_rate <= 1.0


# ── Serialisation ─────────────────────────────────────────────────────────────

def test_report_serialisable() -> None:
    import json
    bars = _oscillating_bars(300)
    report = run_grid_search(
        bars,
        {"stop_loss_pips": [20, 25]},
        _spec(), _POLICY, min_trades=0,
    )
    data = json.loads(report.model_dump_json())
    assert "results" in data
    assert "total_combinations" in data
