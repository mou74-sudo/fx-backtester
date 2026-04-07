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
from fx_backtester.data.sessions import infer_sessions


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


def load_yfinance_h1(
    instrument: str,
    start: date,
    end: date,
    *,
    verbose: bool = False,
) -> list[MarketBar]:
    """Download H1 bars from Yahoo Finance for a date range.

    Args:
        instrument: ``"EURUSD"`` or ``"USDJPY"``
        start:      First calendar day to include.
        end:        Last calendar day to include (inclusive).
        verbose:    Print row count to stdout when True.

    Returns:
        ``list[MarketBar]`` sorted ascending by timestamp.

    Raises:
        ValueError: Unsupported instrument or yfinance not installed.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is required: pip install yfinance"
        ) from exc

    if instrument not in _TICKERS:
        raise ValueError(
            f"Unsupported instrument '{instrument}'. Supported: {sorted(_TICKERS)}"
        )

    ticker = _TICKERS[instrument]
    # yfinance end date is exclusive, so add one day
    yf_end = end + timedelta(days=1)

    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=yf_end.isoformat(),
        interval="1h",
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
        # Ensure UTC-aware datetime
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
            sessions=infer_sessions(dt),
        ))

    bars.sort(key=lambda b: b.timestamp)
    if verbose:
        print(f"yfinance: {len(bars)} bars for {ticker} {start} → {end}")
    return bars


def bars_to_csv(bars: list[MarketBar], path: Path) -> None:
    """Write MarketBar list to CSV (same format as dukascopy.bars_to_csv)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close"])
        for bar in bars:
            writer.writerow([
                bar.timestamp.isoformat(),
                f"{bar.open:.5f}",
                f"{bar.high:.5f}",
                f"{bar.low:.5f}",
                f"{bar.close:.5f}",
            ])
