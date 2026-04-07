"""Data loading helpers.

Lean by design: v0.1 supports simple CSV ingestion to keep evidence auditable.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from fx_backtester.data.models import MarketBar
from fx_backtester.data.sessions import infer_sessions_for_instrument, normalize_timestamp_to_utc


REQUIRED_BAR_COLUMNS = ["timestamp", "open", "high", "low", "close"]


def load_ohlc_csv(path: str | Path) -> list[dict[str, Any]]:
    """Load OHLC rows from a CSV file.

    The function returns plain dictionaries to avoid pretending the data layer is
    more mature than it is.
    """

    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_BAR_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        return list(reader)


def load_market_bars(path: str | Path, instrument: str = "") -> list[MarketBar]:
    """Load OHLC bars from CSV.

    Pass ``instrument="NQ"`` or ``"ES"`` to get CME RTH/ETH session tags
    instead of the default FX session tags.
    """
    rows = load_ohlc_csv(path)
    bars: list[MarketBar] = []
    for row in rows:
        timestamp = normalize_timestamp_to_utc(str(row["timestamp"]))
        bars.append(
            MarketBar(
                timestamp=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                sessions=infer_sessions_for_instrument(timestamp, instrument),
            )
        )
    return bars
