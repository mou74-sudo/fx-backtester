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
