"""Lightweight data quality checks for auditable research inputs."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    last_timestamp = None

    for row in rows:
        if any(not row.get(col) for col in required):
            missing += 1
        ts = row.get("timestamp")
        if last_timestamp is not None and ts is not None and ts <= last_timestamp:
            non_monotonic += 1
        last_timestamp = ts

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
