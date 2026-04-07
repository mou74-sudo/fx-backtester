"""yfinance H1 data loader — drop-in replacement for the Dukascopy fetcher.

Downloads H1 OHLC bars for forex pairs and futures via Yahoo Finance (no API key needed).
Works from any server with internet access.

Supported instruments:
    EURUSD  →  EURUSD=X   (EUR/USD Forex)
    USDJPY  →  USDJPY=X   (USD/JPY Forex)
    NQ      →  NQ=F        (Nasdaq 100 Futures)
    ES      →  ES=F        (S&P 500 Futures)

yfinance H1 history limit: ~730 days from today.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fx_backtester.data.models import MarketBar
from fx_backtester.data.sessions import infer_sessions_for_instrument


# instrument code → (yfinance ticker, display name, pip/point size)
_INSTRUMENTS: dict[str, tuple[str, str, float]] = {
    "EURUSD": ("EURUSD=X", "EUR/USD Forex",          0.0001),
    "USDJPY": ("USDJPY=X", "USD/JPY Forex",           0.01),
    "NQ":     ("NQ=F",     "Nasdaq 100 Futures",       0.25),
    "ES":     ("ES=F",     "S&P 500 Futures",           0.25),
}

# Keep backward-compat alias
_TICKERS: dict[str, str] = {k: v[0] for k, v in _INSTRUMENTS.items()}


def instrument_display_name(instrument: str) -> str:
    """Return the human-readable name for an instrument code."""
    return _INSTRUMENTS.get(instrument, (None, instrument, None))[1]


def instrument_pip_size(instrument: str) -> float:
    """Return the pip/point size for an instrument."""
    return _INSTRUMENTS.get(instrument, (None, None, 0.0001))[2]


# yfinance interval codes and their display names
_INTERVALS: dict[str, str] = {
    "5m":  "5 minute",
    "15m": "15 minute",
    "30m": "30 minute",
    "1h":  "1 hour",
    "4h":  "4 hour",
    "1d":  "Daily",
}

# yfinance max lookback per interval (approximate, in days)
_INTERVAL_MAX_DAYS: dict[str, int] = {
    "5m": 60, "15m": 60, "30m": 60,
    "1h": 730, "4h": 730, "1d": 3650,
}


def load_yfinance_bars(
    instrument: str,
    start: date,
    end: date,
    interval: str = "1h",
    *,
    verbose: bool = False,
) -> list[MarketBar]:
    """Download OHLC bars from Yahoo Finance for any supported interval.

    Args:
        instrument: e.g. ``"NQ"``, ``"ES"``, ``"EURUSD"``
        start:      First calendar day to include.
        end:        Last calendar day to include (inclusive).
        interval:   yfinance interval string: ``"5m"``, ``"15m"``, ``"1h"``, ``"1d"`` etc.
        verbose:    Print row count when True.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError("yfinance is required: pip install yfinance") from exc

    if instrument not in _TICKERS:
        raise ValueError(f"Unsupported instrument '{instrument}'. Supported: {sorted(_TICKERS)}")
    if interval not in _INTERVALS:
        raise ValueError(f"Unsupported interval '{interval}'. Supported: {sorted(_INTERVALS)}")

    ticker = _TICKERS[instrument]
    yf_end = end + timedelta(days=1)

    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=yf_end.isoformat(),
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    if df.empty:
        if verbose:
            print(f"yfinance returned no data for {ticker} {start} → {end}")
        return []

    # Flatten multi-level columns if present (yfinance >=0.2 sometimes adds ticker level)
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)

    bars: list[MarketBar] = []
    for ts, row in df.iterrows():
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            dt = ts.to_pydatetime().astimezone(UTC)
        else:
            dt = ts.to_pydatetime().replace(tzinfo=UTC)

        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        c = float(row["Close"])

        if not (l > 0 and h >= l):
            continue

        bars.append(MarketBar(
            timestamp=dt,
            open=max(o, l),
            high=h,
            low=l,
            close=max(c, l),
            sessions=infer_sessions_for_instrument(dt, instrument),
        ))

    bars.sort(key=lambda b: b.timestamp)
    if verbose:
        print(f"yfinance: {len(bars)} {interval} bars for {ticker} {start} → {end}")
    return bars


# Keep H1-specific alias for backward compatibility
def load_yfinance_h1(instrument: str, start: date, end: date, *, verbose: bool = False) -> list[MarketBar]:
    """Backward-compatible H1 loader. Prefer load_yfinance_bars(..., interval='1h')."""
    return load_yfinance_bars(instrument, start, end, interval="1h", verbose=verbose)


# Re-exported from loaders for backward compatibility
from fx_backtester.data.loaders import bars_to_csv as bars_to_csv  # noqa: F401, E402
