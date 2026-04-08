"""Lightweight data quality checks for auditable research inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _parse_ts(raw: object) -> datetime | None:
    """Parse a timestamp value to a timezone-aware datetime, or return None."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@dataclass(slots=True)
class DataQualityReport:
    row_count: int
    missing_required_fields: int = 0
    non_monotonic_timestamps: int = 0
    notes: list[str] = field(default_factory=list)


def assess_basic_ohlc_quality(rows: list[dict]) -> DataQualityReport:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = 0
    non_monotonic = 0
    last_ts: datetime | None = None

    for row in rows:
        if any(not row.get(col) for col in required):
            missing += 1
        ts = _parse_ts(row.get("timestamp"))
        if last_ts is not None and ts is not None and ts <= last_ts:
            non_monotonic += 1
        if ts is not None:
            last_ts = ts

    notes = []
    if missing:
        notes.append("One or more rows have missing required OHLC fields.")
    if non_monotonic:
        notes.append("Timestamps are not strictly increasing.")

    return DataQualityReport(
        row_count=len(rows),
        missing_required_fields=missing,
        non_monotonic_timestamps=non_monotonic,
        notes=notes,
    )
