from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_SESSION_ZONES = {
    "asia": ZoneInfo("Asia/Tokyo"),
    "london": ZoneInfo("Europe/London"),
    "new_york": ZoneInfo("America/New_York"),
}

_RTH_ZONE = ZoneInfo("America/New_York")


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

    # RTH: NYSE/CME regular trading hours 09:30–16:00 ET (hour 9 with minute >= 30, hours 10–15)
    local_dt = timestamp_utc.astimezone(_RTH_ZONE)
    local_hour = local_dt.hour
    local_minute = local_dt.minute
    if (local_hour == 9 and local_minute >= 30) or (10 <= local_hour < 16):
        sessions.append("rth")

    return sessions
