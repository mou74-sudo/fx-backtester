from __future__ import annotations

import math
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fx_backtester.data.models import MarketBar


def compute_simple_sma(values: list[float], period: int) -> list[float | None]:
    """Return a simple moving average series aligned to ``values``.

    The first ``period - 1`` positions are ``None`` (insufficient data).
    """
    if period < 1:
        raise ValueError("SMA period must be at least 1")
    result: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        result[i] = round(sum(values[i - period + 1 : i + 1]) / period, 5)
    return result


def compute_ema(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average (standard multiplier = 2/(period+1)).

    Seeded with the simple average of the first ``period`` values.
    """
    if period < 2:
        raise ValueError("EMA period must be at least 2")
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    result[period - 1] = round(ema, 5)
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        result[i] = round(ema, 5)
    return result


def compute_bollinger_bands(
    values: list[float], period: int, num_std: float
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return (upper, middle, lower) Bollinger Band series."""
    middle = compute_simple_sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = middle[i]
        if mean is None:
            continue
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        upper[i] = round(mean + num_std * std, 5)
        lower[i] = round(mean - num_std * std, 5)
    return upper, middle, lower


def compute_vwap_daily(bars: list[MarketBar]) -> list[float | None]:
    """Intraday VWAP approximated via cumulative typical-price mean (no volume needed).

    Resets at the start of each calendar day.
    """
    result: list[float | None] = [None] * len(bars)
    cum_tp = 0.0
    n = 0
    current_day: date | None = None

    for i, bar in enumerate(bars):
        day = bar.timestamp.date()
        if day != current_day:
            cum_tp = 0.0
            n = 0
            current_day = day
        tp = (bar.high + bar.low + bar.close) / 3.0
        cum_tp += tp
        n += 1
        result[i] = round(cum_tp / n, 5)
    return result


def build_d1_trend_map(
    bars: list[MarketBar],
    sma_period: int = 20,
) -> dict[date, str | None]:
    """Build a no-look-ahead D1 trend lookup for H1 bars.

    For each calendar date present in ``bars``, returns the trend that should
    be applied to H1 bars on that date.  The trend is derived from the
    *previous* completed daily bar so that no information from the current
    day leaks into the signal.

    Return values per date:
      ``"up"``   — previous day's D1 close was above its ``sma_period``-day SMA
      ``"down"`` — previous day's D1 close was below its SMA
      ``None``   — insufficient history (SMA warmup not complete, or first day)
    """
    if not bars:
        return {}

    daily_close_by_date: dict[date, float] = {}
    for bar in bars:
        d = bar.timestamp.date()
        daily_close_by_date[d] = bar.close  # last bar of the day wins

    sorted_dates = sorted(daily_close_by_date.keys())
    closes_list = [daily_close_by_date[d] for d in sorted_dates]

    smas = compute_simple_sma(closes_list, sma_period)

    trend_at_date: dict[date, str | None] = {}
    for i, d in enumerate(sorted_dates):
        sma = smas[i]
        if sma is None:
            trend_at_date[d] = None
        else:
            trend_at_date[d] = "up" if daily_close_by_date[d] > sma else "down"

    h1_trend_map: dict[date, str | None] = {}
    prev_trend: str | None = None
    for d in sorted_dates:
        h1_trend_map[d] = prev_trend   # H1 bars today see yesterday's trend
        prev_trend = trend_at_date[d]  # advance for tomorrow

    return h1_trend_map


def compute_wilder_rsi(closes: list[float], period: int) -> list[float | None]:
    if period < 2:
        raise ValueError("RSI period must be at least 2")
    if len(closes) < period + 1:
        return [None] * len(closes)

    deltas = [closes[idx] - closes[idx - 1] for idx in range(1, len(closes))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result: list[float | None] = [None] * len(closes)
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = round(100 - (100 / (1 + rs)), 4)

    for idx in range(period + 1, len(closes)):
        gain = gains[idx - 1]
        loss = losses[idx - 1]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        if avg_loss == 0:
            result[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[idx] = round(100 - (100 / (1 + rs)), 4)

    return result


def compute_wilder_atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float | None]:
    if period < 2:
        raise ValueError("ATR period must be at least 2")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must be the same length")
    if len(closes) < period + 1:
        return [None] * len(closes)

    true_ranges: list[float] = [0.0]
    for idx in range(1, len(closes)):
        tr = max(
            highs[idx] - lows[idx],
            abs(highs[idx] - closes[idx - 1]),
            abs(lows[idx] - closes[idx - 1]),
        )
        true_ranges.append(tr)

    result: list[float | None] = [None] * len(closes)
    atr = sum(true_ranges[1 : period + 1]) / period
    result[period] = round(atr, 5)

    for idx in range(period + 1, len(closes)):
        atr = ((atr * (period - 1)) + true_ranges[idx]) / period
        result[idx] = round(atr, 5)

    return result
