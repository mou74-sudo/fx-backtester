from __future__ import annotations


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
