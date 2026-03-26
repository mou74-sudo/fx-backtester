"""Data loading helpers.

Lean by design: v0.1 supports simple CSV ingestion to keep evidence auditable.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


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
