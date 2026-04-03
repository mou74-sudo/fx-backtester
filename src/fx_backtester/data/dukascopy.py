"""Dukascopy free public datafeed loader.

Downloads H1 BID candles for EURUSD / USDJPY and caches raw bi5 files
locally so subsequent runs are fully offline and auditable.

URL pattern:
    https://datafeed.dukascopy.com/datafeed/{INSTRUMENT}/{YEAR}/{MM}/{DD}/BID_candles_hour_1.bi5
    Month is 0-indexed (00 = January, 11 = December).

Binary format per candle (24 bytes, big-endian, LZMA-compressed):
    uint32  timestamp_ms   milliseconds since midnight UTC of the given day
    uint32  open           integer price (divide by _POINT_DIVIDER)
    uint32  high
    uint32  low
    uint32  close
    float32 volume         (not used by the backtester — kept for format fidelity)
"""

from __future__ import annotations

import csv
import lzma
import struct
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fx_backtester.data.models import MarketBar
from fx_backtester.data.sessions import infer_sessions


_BASE_URL = "https://datafeed.dukascopy.com/datafeed"
_STRUCT_FMT = ">IIIIIf"                          # big-endian: 5× uint32 + float32
_CANDLE_BYTES = struct.calcsize(_STRUCT_FMT)      # == 24

# Raw integer prices are divided by this to yield float prices.
_POINT_DIVIDERS: dict[str, float] = {
    "EURUSD": 100_000.0,
    "USDJPY": 1_000.0,
}


# ── URL / cache helpers ───────────────────────────────────────────────────────

def day_url(instrument: str, year: int, month: int, day: int) -> str:
    """Return the Dukascopy bi5 URL for one calendar day of H1 BID bars.

    Dukascopy months are 0-indexed: 00 = January, 11 = December.
    """
    return f"{_BASE_URL}/{instrument}/{year}/{month - 1:02d}/{day:02d}/BID_candles_hour_1.bi5"


def cache_path(cache_dir: Path, instrument: str, year: int, month: int, day: int) -> Path:
    """Canonical local path for a cached bi5 day file."""
    return cache_dir / "dukascopy" / instrument / f"{year}" / f"{month:02d}" / f"{day:02d}.bi5"


# ── Network fetch ─────────────────────────────────────────────────────────────

def fetch_raw(url: str, *, retries: int = 5, backoff: float = 3.0, timeout: int = 30) -> bytes:
    """HTTP GET with exponential retry. Returns empty bytes on 404 (weekend/holiday)."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return b""          # no data for this day — normal for weekends
            if attempt < retries - 1:
                sleep = backoff ** attempt
                time.sleep(sleep)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < retries - 1:
                sleep = backoff ** attempt
                time.sleep(sleep)
                continue
            raise
    return b""  # unreachable but satisfies type checker


# ── Binary parser ─────────────────────────────────────────────────────────────

def parse_bi5(raw_compressed: bytes, divider: float, day: date) -> list[MarketBar]:
    """Decompress and parse one day's bi5 file into MarketBar objects.

    Returns an empty list for an empty/corrupt file (weekend, holiday, or
    partial download).
    """
    if not raw_compressed:
        return []
    try:
        data = lzma.decompress(raw_compressed)
    except lzma.LZMAError:
        return []

    midnight_utc = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    bars: list[MarketBar] = []

    for offset in range(0, len(data), _CANDLE_BYTES):
        chunk = data[offset : offset + _CANDLE_BYTES]
        if len(chunk) < _CANDLE_BYTES:
            break

        ts_ms, o_raw, h_raw, l_raw, c_raw, _vol = struct.unpack(_STRUCT_FMT, chunk)

        o = o_raw / divider
        h = h_raw / divider
        l = l_raw / divider
        c = c_raw / divider

        # Skip zero-price or structurally invalid candles.
        if not (l > 0 and h >= l):
            continue

        timestamp = midnight_utc + timedelta(milliseconds=int(ts_ms))
        bars.append(
            MarketBar(
                timestamp=timestamp,
                open=max(o, l),   # clamp to valid range (rare floating-point edge)
                high=h,
                low=l,
                close=max(c, l),
                sessions=infer_sessions(timestamp),
            )
        )

    return bars


# ── Public loader ─────────────────────────────────────────────────────────────

def load_dukascopy_h1(
    instrument: str,
    start: date,
    end: date,
    cache_dir: Path,
    *,
    verbose: bool = False,
) -> list[MarketBar]:
    """Download (or serve from cache) Dukascopy H1 BID bars for a date range.

    Args:
        instrument: ``"EURUSD"`` or ``"USDJPY"``
        start:      First calendar day to include (UTC date).
        end:        Last calendar day to include (UTC date, inclusive).
        cache_dir:  Root directory for local bi5 cache.
        verbose:    Print per-day progress to stdout when True.

    Returns:
        ``list[MarketBar]`` sorted ascending by timestamp.

    Raises:
        ValueError: Unsupported instrument.
    """
    if instrument not in _POINT_DIVIDERS:
        raise ValueError(
            f"Unsupported instrument '{instrument}'. Supported: {sorted(_POINT_DIVIDERS)}"
        )

    divider = _POINT_DIVIDERS[instrument]
    bars: list[MarketBar] = []
    current = start

    while current <= end:
        local_path = cache_path(cache_dir, instrument, current.year, current.month, current.day)

        if local_path.exists():
            raw = local_path.read_bytes()
            source = "cache"
        else:
            url = day_url(instrument, current.year, current.month, current.day)
            try:
                raw = fetch_raw(url)
            except Exception as exc:
                # Network error after all retries — skip this day and continue
                print(f"  {current}  SKIP     (network error: {exc})")
                current += timedelta(days=1)
                continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(raw)   # persist even empty bytes (weekend = 0b)
            source = "network"

        day_bars = parse_bi5(raw, divider, current)
        if verbose:
            print(f"  {current}  {source:<7}  {len(day_bars):3d} bars")

        bars.extend(day_bars)
        current += timedelta(days=1)

    bars.sort(key=lambda b: b.timestamp)
    return bars


# ── CSV export (handoff to run-backtest) ──────────────────────────────────────

def bars_to_csv(bars: list[MarketBar], path: Path) -> None:
    """Write a MarketBar list to the CSV format expected by run-backtest.

    Columns: timestamp, open, high, low, close
    Timestamps are written in ISO 8601 UTC format.
    """
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
