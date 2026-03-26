from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_SESSION_ZONES = {
    "asia": ZoneInfo("Asia/Tokyo"),
    "london": ZoneInfo("Europe/London"),
    "new_york": ZoneInfo("America/New_York"),
}


def normalize_timestamp_to_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def infer_sessions(timestamp_utc: datetime) -> list[str]:
    sessions: list[str] = []
    for name, zone in _SESSION_ZONES.items():
        local_hour = timestamp_utc.astimezone(zone).hour
        if 7 <= local_hour < 16:
            sessions.append(name)
    return sessions
