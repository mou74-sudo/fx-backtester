from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_SESSION_ZONES = {
    "asia":     ZoneInfo("Asia/Tokyo"),
    "london":   ZoneInfo("Europe/London"),
    "new_york": ZoneInfo("America/New_York"),
}
_NY_ZONE = ZoneInfo("America/New_York")

_FUTURES_INSTRUMENTS = {"NQ", "ES"}


def normalize_timestamp_to_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def infer_sessions(timestamp_utc: datetime) -> list[str]:
    """FX session tagging: asia / london / new_york (7–16 local hour each)."""
    sessions: list[str] = []
    for name, zone in _SESSION_ZONES.items():
        local_hour = timestamp_utc.astimezone(zone).hour
        if 7 <= local_hour < 16:
            sessions.append(name)
    return sessions


def infer_futures_sessions(timestamp_utc: datetime) -> list[str]:
    """NQ/ES session tagging based on CME Globex schedule (America/New_York).

    rth  — Regular Trading Hours: 09:30–16:00 ET (primary session)
    eth  — Extended/Globex hours: 18:00–09:30 ET (overnight)
    The 16:00–18:00 window is the CME settlement break — no tag returned.
    """
    ny = timestamp_utc.astimezone(_NY_ZONE)
    minutes = ny.hour * 60 + ny.minute
    RTH_START = 9 * 60 + 30    # 09:30
    RTH_END   = 16 * 60         # 16:00
    ETH_START = 18 * 60         # 18:00 (after settlement gap)

    if RTH_START <= minutes < RTH_END:
        return ["rth"]
    if minutes >= ETH_START or minutes < RTH_START:
        return ["eth"]
    return []   # 16:00–18:00 settlement break


def infer_sessions_for_instrument(timestamp_utc: datetime, instrument: str) -> list[str]:
    """Dispatch to the correct session tagger based on instrument."""
    if instrument.upper() in _FUTURES_INSTRUMENTS:
        return infer_futures_sessions(timestamp_utc)
    return infer_sessions(timestamp_utc)
