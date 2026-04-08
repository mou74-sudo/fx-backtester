"""Tests for the D1 daily trend filter.

Covers:
  - compute_simple_sma correctness
  - build_d1_trend_map: correct trend assignment, no look-ahead, warmup None
  - pipeline: long entries blocked during D1 downtrend
  - pipeline: short entries blocked during D1 uptrend
  - pipeline: filter disabled by default (require_daily_trend=False)
  - pipeline: during SMA warmup period (None trend) entries are blocked
  - breakout pipeline: same filtering logic applies
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from fx_backtester.data.indicators import build_d1_trend_map, compute_simple_sma
from fx_backtester.data.models import MarketBar
from fx_backtester.engine.pipeline import build_signal_pipeline
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import (
    BacktestWindow,
    BreakoutRule,
    InstrumentSpec,
    RiskSpec,
    RsiMeanReversionRule,
    StrategySpec,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(ts: datetime, close: float, high_offset: float = 0.0010) -> MarketBar:
    return MarketBar(
        timestamp=ts,
        open=close,
        high=close + high_offset,
        low=close - high_offset,
        close=close,
        sessions=["london"],
    )


def _h1_bar(day: int, hour: int, close: float) -> MarketBar:
    ts = datetime(2024, 1, day, hour, 0, tzinfo=UTC)
    return _bar(ts, close)


def _spec(*, require_daily_trend: bool = True, daily_sma_period: int = 3,
          direction: str = "both") -> StrategySpec:
    return StrategySpec(
        strategy_name="d1_test",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(
            rsi_period=2,
            entry_rsi_lte=40.0,
            exit_rsi_gte=55.0,
            short_entry_rsi_gte=60.0,
            short_exit_rsi_lte=45.0,
            stop_loss_pips=20,
            take_profit_pips=30,
            direction=direction,
            require_daily_trend=require_daily_trend,
            daily_sma_period=daily_sma_period,
        ),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-01-31"),
    )


# ── compute_simple_sma ────────────────────────────────────────────────────────

def test_sma_correct_values() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = compute_simple_sma(values, period=3)
    assert result[:2] == [None, None]
    assert abs(result[2] - 2.0) < 1e-5   # (1+2+3)/3
    assert abs(result[3] - 3.0) < 1e-5   # (2+3+4)/3
    assert abs(result[4] - 4.0) < 1e-5   # (3+4+5)/3


def test_sma_period_1_returns_values() -> None:
    values = [1.5, 2.5, 3.5]
    result = compute_simple_sma(values, period=1)
    assert result == [1.5, 2.5, 3.5]


def test_sma_period_equals_length_returns_single_value() -> None:
    values = [1.0, 2.0, 3.0]
    result = compute_simple_sma(values, period=3)
    assert result[:2] == [None, None]
    assert abs(result[2] - 2.0) < 1e-5


def test_sma_period_zero_raises() -> None:
    with pytest.raises(ValueError):
        compute_simple_sma([1.0, 2.0], period=0)


# ── build_d1_trend_map ────────────────────────────────────────────────────────

def test_trend_map_empty_bars_returns_empty() -> None:
    result = build_d1_trend_map([], sma_period=3)
    assert result == {}


def test_trend_map_first_day_is_none() -> None:
    """First day has no completed prior day — trend must be None."""
    bars = [
        _h1_bar(1, 0, 1.1000),
        _h1_bar(1, 1, 1.1010),
        _h1_bar(2, 0, 1.1020),
    ]
    trend_map = build_d1_trend_map(bars, sma_period=3)
    assert trend_map[date(2024, 1, 1)] is None


def test_trend_map_no_lookahead() -> None:
    """Trend for H1 bars on day D must use day D-1's completed data, not day D."""
    # Day 1 close: 1.1000, Day 2 close: 1.1010, Day 3 close: 1.1020
    # With SMA period=3, SMA is available from day 3 onwards
    # H1 bars on day 3 should see trend derived from day 2's data
    # Day 2 trend: SMA not yet complete (only 2 days) → None
    bars = [
        _h1_bar(1, 0, 1.1000),
        _h1_bar(2, 0, 1.1010),
        _h1_bar(3, 0, 1.1020),
        _h1_bar(4, 0, 1.1030),
    ]
    trend_map = build_d1_trend_map(bars, sma_period=3)
    # Day 1: no prior day → None
    assert trend_map[date(2024, 1, 1)] is None
    # Day 2: prior day (1) has no SMA yet → None
    assert trend_map[date(2024, 1, 2)] is None
    # Day 3: prior day (2) has no SMA yet (needs 3 days) → None
    assert trend_map[date(2024, 1, 3)] is None
    # Day 4: prior day (3) is the first day with a complete 3-period SMA
    # SMA(3) on day 3 = (1.1000 + 1.1010 + 1.1020) / 3 = 1.10100
    # Day 3 close (1.1020) > SMA (1.10100) → "up"
    assert trend_map[date(2024, 1, 4)] == "up"


def test_trend_map_downtrend_detection() -> None:
    """Declining prices should produce 'down' trend."""
    bars = [
        _h1_bar(1, 0, 1.1030),
        _h1_bar(2, 0, 1.1020),
        _h1_bar(3, 0, 1.1010),
        _h1_bar(4, 0, 1.1000),
        _h1_bar(5, 0, 1.0990),
    ]
    trend_map = build_d1_trend_map(bars, sma_period=3)
    # Day 5: prior day (4) SMA = (1.1030+1.1020+1.1010+1.1000)/last3 = (1.1020+1.1010+1.1000)/3 = 1.10100
    # Day 4 close (1.1000) < SMA (1.10100) → "down"
    assert trend_map[date(2024, 1, 5)] == "down"


def test_trend_map_multiple_h1_bars_same_day_use_last_close() -> None:
    """Multiple H1 bars on the same day — daily close is the LAST bar's close."""
    bars = [
        _h1_bar(1, 0, 1.1000),
        _h1_bar(1, 1, 1.1050),   # earlier bars in day 1
        _h1_bar(1, 22, 1.0800),  # last bar of day 1 → daily close = 1.0800
        _h1_bar(2, 0, 1.1020),
        _h1_bar(2, 1, 1.1030),
        _h1_bar(2, 22, 1.1040),  # daily close day 2 = 1.1040
        _h1_bar(3, 0, 1.1050),
        _h1_bar(3, 22, 1.1060),  # daily close day 3 = 1.1060
        _h1_bar(4, 0, 1.1070),
    ]
    trend_map = build_d1_trend_map(bars, sma_period=3)
    # Day 4: prior day (3) SMA(3) = (1.0800 + 1.1040 + 1.1060) / 3 ≈ 1.0967
    # Day 3 close = 1.1060 > 1.0967 → "up"
    assert trend_map[date(2024, 1, 4)] == "up"


# ── Pipeline integration: RSI ─────────────────────────────────────────────────

def _make_multi_day_rsi_bars() -> list[MarketBar]:
    """
    Create H1 bars across 10 days designed to trigger RSI signals.
    Days 1-5: downtrending (close falls each day → D1 downtrend after warmup)
    Days 6-10: uptrending (close rises each day → D1 uptrend after day 6+)

    RSI signals are placed explicitly via extreme close sequences.
    """
    bars: list[MarketBar] = []
    # Days 1-5: declining prices, 24 H1 bars per day
    base = 1.1100
    for day in range(1, 6):
        day_close = base - (day - 1) * 0.0030
        for h in range(24):
            # Last bar of day has the daily close; others slightly vary
            close = day_close if h == 23 else day_close + 0.0002
            bars.append(_h1_bar(day, h, close))
    # Days 6-10: rising prices
    for day in range(6, 11):
        day_close = base - 0.0120 + (day - 5) * 0.0030  # rising from the low
        for h in range(24):
            close = day_close if h == 23 else day_close - 0.0002
            bars.append(_h1_bar(day, h, close))
    return bars


def test_filter_disabled_does_not_suppress_entries() -> None:
    """With require_daily_trend=False (default), entries are NOT filtered by trend."""
    bars = _make_multi_day_rsi_bars()
    spec_no_filter = _spec(require_daily_trend=False)
    spec_with_filter = _spec(require_daily_trend=True, daily_sma_period=3)
    data_no_filter = build_signal_pipeline(market_bars=bars, spec=spec_no_filter)
    data_with_filter = build_signal_pipeline(market_bars=bars, spec=spec_with_filter)

    long_no_filter = sum(1 for b in data_no_filter.bars if b.entry_long)
    long_with_filter = sum(1 for b in data_with_filter.bars if b.entry_long)

    # Filter should block some entries; no-filter should have >= as many
    assert long_no_filter >= long_with_filter


def test_long_entries_only_during_uptrend() -> None:
    """Long SIGNALS must only fire on days where the D1 trend is 'up'.

    The filter is applied at the signal bar; the entry executes the next bar
    which may be a different calendar day — so we check the signal trace, not
    the execution bar.
    """
    bars = _make_multi_day_rsi_bars()
    spec = _spec(require_daily_trend=True, daily_sma_period=3, direction="both")
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    for row in data.signal_trace:
        if row.entry_signal:
            assert row.daily_trend == "up", (
                f"Long signal on {row.signal_bar_timestamp} but D1 trend is "
                f"{row.daily_trend!r} — filter failed"
            )


def test_short_entries_only_during_downtrend() -> None:
    """Short SIGNALS must only fire on days where the D1 trend is 'down'."""
    bars = _make_multi_day_rsi_bars()
    spec = _spec(require_daily_trend=True, daily_sma_period=3, direction="both")
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    for row in data.signal_trace:
        if row.short_entry_signal:
            assert row.daily_trend == "down", (
                f"Short signal on {row.signal_bar_timestamp} but D1 trend is "
                f"{row.daily_trend!r} — filter failed"
            )


def test_no_entries_during_warmup_period() -> None:
    """During D1 SMA warmup (None trend), no entries should be generated."""
    # Only 2 days of data with sma_period=5 → all days are in warmup
    bars = [_h1_bar(1, h, 1.1000 + h * 0.0001) for h in range(24)]
    bars += [_h1_bar(2, h, 1.1000 - h * 0.0001) for h in range(24)]
    spec = _spec(require_daily_trend=True, daily_sma_period=5)
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    assert all(not b.entry_long and not b.entry_short for b in data.bars), (
        "Expected no entries during D1 SMA warmup period"
    )


def test_daily_trend_in_trace_row() -> None:
    """SignalTraceRow.daily_trend must be populated when filter is active."""
    bars = _make_multi_day_rsi_bars()
    spec = _spec(require_daily_trend=True, daily_sma_period=3)
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    # After warmup, trace rows should have a non-None daily_trend
    post_warmup = [r for r in data.signal_trace if r.daily_trend is not None]
    assert len(post_warmup) > 0


def test_daily_trend_none_when_filter_disabled() -> None:
    """When require_daily_trend=False, daily_trend in trace rows should be None."""
    bars = _make_multi_day_rsi_bars()
    spec = _spec(require_daily_trend=False)
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    assert all(r.daily_trend is None for r in data.signal_trace)


# ── Pipeline integration: breakout ────────────────────────────────────────────

def _breakout_spec(*, require_daily_trend: bool = True) -> StrategySpec:
    return StrategySpec(
        strategy_name="d1_breakout_test",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=BreakoutRule(
            breakout_lookback_bars=3,
            breakout_buffer_pips=2.0,
            stop_loss_pips=20,
            take_profit_pips=30,
            direction="both",
            require_daily_trend=require_daily_trend,
            daily_sma_period=3,
        ),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-01-31"),
    )


def test_breakout_long_entries_only_during_uptrend() -> None:
    """Breakout long signals must also respect the D1 trend filter."""
    bars = _make_multi_day_rsi_bars()
    spec = _breakout_spec(require_daily_trend=True)
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    for row in data.signal_trace:
        if row.entry_signal:
            assert row.daily_trend == "up", (
                f"Breakout long signal on {row.signal_bar_timestamp} but D1 trend is {row.daily_trend!r}"
            )


def test_breakout_short_entries_only_during_downtrend() -> None:
    """Breakout short signals must also respect the D1 trend filter."""
    bars = _make_multi_day_rsi_bars()
    spec = _breakout_spec(require_daily_trend=True)
    data = build_signal_pipeline(market_bars=bars, spec=spec)

    for row in data.signal_trace:
        if row.short_entry_signal:
            assert row.daily_trend == "down", (
                f"Breakout short signal on {row.signal_bar_timestamp} but D1 trend is {row.daily_trend!r}"
            )


# ── Spec defaults ─────────────────────────────────────────────────────────────

def test_require_daily_trend_defaults_false() -> None:
    from fx_backtester.formalizer.spec_models import RsiMeanReversionRule
    rule = RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30)
    assert rule.require_daily_trend is False
    assert rule.daily_sma_period == 20


def test_daily_sma_period_validates_range() -> None:
    from fx_backtester.formalizer.spec_models import RsiMeanReversionRule
    import pytest
    with pytest.raises(Exception):
        RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30, daily_sma_period=1)
    with pytest.raises(Exception):
        RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30, daily_sma_period=201)
