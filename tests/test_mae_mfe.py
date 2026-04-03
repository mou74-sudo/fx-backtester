"""Tests for MAE/MFE (Maximum Adverse/Favorable Excursion) analysis.

Covers:
  - basic MAE/MFE computation for long and short trades
  - efficiency calculation
  - mae_ratio calculation
  - aggregate statistics (avg_mae, avg_mfe, winner/loser splits)
  - insight text generation (stop, tp, efficiency)
  - open/incomplete trades are excluded
  - empty inputs
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fx_backtester.analysis.mae_mfe import MaeMfeReport, TradeExcursion, compute_mae_mfe
from fx_backtester.engine.backtest import SignalBar
from fx_backtester.engine.trade_log import TradeRecord


# ── Fixtures ──────────────────────────────────────────────────────────────────

_T0 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
_PIP = 0.0001


def _bar(h: int, high: float, low: float, close: float | None = None) -> SignalBar:
    ts = _T0 + timedelta(hours=h)
    c = close if close is not None else (high + low) / 2
    return SignalBar(timestamp=ts, open=c, high=high, low=low, close=c)


def _long_trade(
    entry_h: int,
    exit_h: int,
    entry_price: float,
    exit_price: float,
    stop: float = 1.0980,
    tp: float = 1.1030,
) -> TradeRecord:
    pnl_pips = round((exit_price - entry_price) / _PIP, 1)
    return TradeRecord(
        trade_id="eurusd-0001",
        side="buy",
        entry_time=_T0 + timedelta(hours=entry_h),
        entry_price=entry_price,
        stop_loss_price=stop,
        take_profit_price=tp,
        quantity_units=10_000,
        execution_policy_name="default",
        exit_time=_T0 + timedelta(hours=exit_h),
        exit_price=exit_price,
        pnl=round((exit_price - entry_price) * 10_000, 2),
        pnl_pips=pnl_pips,
    )


def _short_trade(
    entry_h: int,
    exit_h: int,
    entry_price: float,
    exit_price: float,
    stop: float = 1.1030,
    tp: float = 1.0980,
) -> TradeRecord:
    pnl_pips = round((entry_price - exit_price) / _PIP, 1)
    return TradeRecord(
        trade_id="eurusd-0002",
        side="sell",
        entry_time=_T0 + timedelta(hours=entry_h),
        entry_price=entry_price,
        stop_loss_price=stop,
        take_profit_price=tp,
        quantity_units=10_000,
        execution_policy_name="default",
        exit_time=_T0 + timedelta(hours=exit_h),
        exit_price=exit_price,
        pnl=round((entry_price - exit_price) * 10_000, 2),
        pnl_pips=pnl_pips,
    )


def _open_trade() -> TradeRecord:
    """A trade with no exit — should be excluded from MAE/MFE."""
    return TradeRecord(
        trade_id="eurusd-0003",
        side="buy",
        entry_time=_T0,
        entry_price=1.1000,
        stop_loss_price=1.0980,
        take_profit_price=1.1030,
        quantity_units=10_000,
        execution_policy_name="default",
    )


# ── Long trade MAE/MFE ────────────────────────────────────────────────────────

def test_long_trade_mfe_is_distance_above_entry() -> None:
    # Entry at 1.1000 hour 0, exit at 1.1020 hour 2
    # Bars: hour 0 high=1.1030 (MFE candidate), hour 1 high=1.1025, hour 2 high=1.1022
    bars = [
        _bar(0, high=1.1030, low=1.0998),
        _bar(1, high=1.1025, low=1.1000),
        _bar(2, high=1.1022, low=1.1010),
    ]
    trade = _long_trade(0, 2, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert len(report.excursions) == 1
    exc = report.excursions[0]
    # MFE = (1.1030 - 1.1000) / 0.0001 = 30 pips
    assert exc.mfe_pips == 30.0


def test_long_trade_mae_is_distance_below_entry() -> None:
    bars = [
        _bar(0, high=1.1030, low=1.0995),  # dipped 5 pips below entry
        _bar(1, high=1.1025, low=1.1000),
        _bar(2, high=1.1022, low=1.1010),
    ]
    trade = _long_trade(0, 2, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    exc = report.excursions[0]
    # MAE = (1.1000 - 1.0995) / 0.0001 = 5 pips
    assert exc.mae_pips == 5.0


def test_long_trade_is_winner() -> None:
    bars = [_bar(0, high=1.1030, low=1.0998), _bar(1, high=1.1030, low=1.1010)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.excursions[0].is_winner is True
    assert report.winner_count == 1
    assert report.loser_count == 0


def test_long_trade_is_loser() -> None:
    bars = [_bar(0, high=1.1005, low=1.0975), _bar(1, high=1.1000, low=1.0980)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.0985)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.excursions[0].is_winner is False
    assert report.loser_count == 1


# ── Short trade MAE/MFE ───────────────────────────────────────────────────────

def test_short_trade_mfe_is_distance_below_entry() -> None:
    # Entry at 1.1000 (sell), exit at 1.0980 (profit)
    # MFE = how far down price went = (1.1000 - 1.0970) / pip = 30 pips
    bars = [
        _bar(0, high=1.1005, low=1.0970),
        _bar(1, high=1.1000, low=1.0975),
        _bar(2, high=1.0995, low=1.0980),
    ]
    trade = _short_trade(0, 2, entry_price=1.1000, exit_price=1.0980)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=20)
    exc = report.excursions[0]
    assert exc.mfe_pips == 30.0


def test_short_trade_mae_is_distance_above_entry() -> None:
    # Entry at 1.1000 (sell), high goes to 1.1010 = 10 pip adverse
    bars = [
        _bar(0, high=1.1010, low=1.0990),
        _bar(1, high=1.1005, low=1.0985),
    ]
    trade = _short_trade(0, 1, entry_price=1.1000, exit_price=1.0985)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=20)
    exc = report.excursions[0]
    assert exc.mae_pips == 10.0


# ── Efficiency ────────────────────────────────────────────────────────────────

def test_efficiency_full_capture() -> None:
    # MFE = 30 pips, pnl = 30 pips → efficiency = 1.0
    bars = [_bar(0, high=1.1030, low=1.0998), _bar(1, high=1.1030, low=1.1010)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1030)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert abs(report.excursions[0].efficiency - 1.0) < 0.01


def test_efficiency_half_capture() -> None:
    # MFE = 60 pips, pnl = 30 pips → efficiency ≈ 0.5
    bars = [_bar(0, high=1.1060, low=1.0998), _bar(1, high=1.1060, low=1.1020)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1030)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert abs(report.excursions[0].efficiency - 0.5) < 0.02


# ── MAE ratio ─────────────────────────────────────────────────────────────────

def test_mae_ratio_uses_stop_loss_pips() -> None:
    # MAE = 10 pips, stop = 20 pips → ratio = 0.5
    bars = [_bar(0, high=1.1030, low=1.0990), _bar(1, high=1.1030, low=1.1010)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert abs(report.excursions[0].mae_ratio - 0.5) < 0.01


# ── Aggregate statistics ──────────────────────────────────────────────────────

def test_avg_mae_across_multiple_trades() -> None:
    bars = [
        _bar(0, high=1.1030, low=1.0990),
        _bar(1, high=1.1030, low=1.1010),
        _bar(2, high=1.1040, low=1.0985),
        _bar(3, high=1.1040, low=1.1015),
    ]
    t1 = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)  # MAE = 10 pips
    t2 = TradeRecord(
        trade_id="eurusd-0002", side="buy",
        entry_time=_T0 + timedelta(hours=2),
        entry_price=1.1010,
        stop_loss_price=1.0990, take_profit_price=1.1040,
        quantity_units=10_000, execution_policy_name="default",
        exit_time=_T0 + timedelta(hours=3), exit_price=1.1030,
        pnl=200.0, pnl_pips=20.0,
    )
    report = compute_mae_mfe([t1, t2], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.closed_trade_count == 2
    assert report.avg_mae_pips >= 0


def test_winner_loser_split() -> None:
    bars = [
        _bar(0, high=1.1030, low=1.0995),
        _bar(1, high=1.1025, low=1.1005),
        _bar(2, high=1.1010, low=1.0975),
        _bar(3, high=1.1000, low=1.0980),
    ]
    winner = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    loser  = _long_trade(2, 3, entry_price=1.1000, exit_price=1.0985)
    report = compute_mae_mfe([winner, loser], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.winner_count == 1
    assert report.loser_count == 1


# ── Open/incomplete trades excluded ──────────────────────────────────────────

def test_open_trade_excluded() -> None:
    bars = [_bar(0, high=1.1030, low=1.0990)]
    report = compute_mae_mfe([_open_trade()], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.closed_trade_count == 0
    assert report.excursions == []


def test_mix_of_open_and_closed() -> None:
    bars = [_bar(0, high=1.1030, low=1.0990), _bar(1, high=1.1030, low=1.1010)]
    closed = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([closed, _open_trade()], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.trade_count == 2
    assert report.closed_trade_count == 1


# ── Empty inputs ──────────────────────────────────────────────────────────────

def test_no_trades_returns_zero_report() -> None:
    bars = [_bar(0, high=1.1030, low=1.0990)]
    report = compute_mae_mfe([], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.trade_count == 0
    assert report.closed_trade_count == 0
    assert report.avg_mae_pips == 0.0
    assert report.avg_mfe_pips == 0.0


def test_no_bars_returns_zero_excursions() -> None:
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], [], pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert report.closed_trade_count == 0


# ── Insight text ──────────────────────────────────────────────────────────────

def test_stop_insight_tight_stops() -> None:
    # Winner MAE close to stop → "too tight"
    bars = [_bar(0, high=1.1030, low=1.0985), _bar(1, high=1.1030, low=1.1010)]
    # Entry 1.1000, MAE = 15 pips, stop = 20 pips → ratio = 0.75 → tight warning
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1025, stop=1.0980)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert len(report.stop_insight) > 0


def test_tp_insight_conservative_tp() -> None:
    # MFE = 60 pips, TP = 30 pips → conservative
    bars = [_bar(0, high=1.1060, low=1.0995), _bar(1, high=1.1060, low=1.1020)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1030, tp=1.1030)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert "conservative" in report.tp_insight.lower() or "wider" in report.tp_insight.lower()


def test_efficiency_insight_populated() -> None:
    bars = [_bar(0, high=1.1030, low=1.0998), _bar(1, high=1.1030, low=1.1010)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    assert len(report.efficiency_insight) > 0


def test_report_is_serialisable() -> None:
    import json
    bars = [_bar(0, high=1.1030, low=1.0990), _bar(1, high=1.1030, low=1.1010)]
    trade = _long_trade(0, 1, entry_price=1.1000, exit_price=1.1020)
    report = compute_mae_mfe([trade], bars, pip_size=_PIP, stop_loss_pips=20, take_profit_pips=30)
    data = json.dumps(report.model_dump(mode="json"))
    loaded = json.loads(data)
    assert loaded["closed_trade_count"] == 1
    assert "excursions" in loaded
