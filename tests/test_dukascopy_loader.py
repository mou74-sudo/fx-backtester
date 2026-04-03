"""Tests for the Dukascopy H1 data loader.

Covers:
  - bi5 binary parsing with synthetic known-value data
  - malformed / empty input handling
  - URL construction (0-indexed month)
  - cache path structure
  - CSV round-trip
  - load_dukascopy_h1 with a pre-populated cache (no network)
  - MarketBar field validity and session inference after normalization
"""

from __future__ import annotations

import csv
import io
import lzma
import struct
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from fx_backtester.data.dukascopy import (
    _CANDLE_BYTES,
    _POINT_DIVIDERS,
    _STRUCT_FMT,
    bars_to_csv,
    cache_path,
    day_url,
    load_dukascopy_h1,
    parse_bi5,
)
from fx_backtester.data.models import MarketBar


# ── Helpers ───────────────────────────────────────────────────────────────────


def _pack_candle(ts_ms: int, o: int, h: int, l: int, c: int, vol: float = 1.0) -> bytes:
    return struct.pack(_STRUCT_FMT, ts_ms, o, h, l, c, vol)


def _compress(raw: bytes) -> bytes:
    return lzma.compress(raw)


def _eurusd_day() -> date:
    return date(2024, 1, 15)


DIVIDER_EUR = _POINT_DIVIDERS["EURUSD"]
DIVIDER_JPY = _POINT_DIVIDERS["USDJPY"]


# ── URL construction ──────────────────────────────────────────────────────────


def test_day_url_january_month_is_00() -> None:
    url = day_url("EURUSD", 2024, 1, 15)
    assert "/2024/00/15/" in url
    assert url.endswith("BID_candles_hour_1.bi5")


def test_day_url_december_month_is_11() -> None:
    url = day_url("EURUSD", 2024, 12, 1)
    assert "/2024/11/01/" in url


def test_day_url_includes_instrument() -> None:
    assert "EURUSD" in day_url("EURUSD", 2024, 6, 1)
    assert "USDJPY" in day_url("USDJPY", 2024, 6, 1)


# ── Cache path structure ──────────────────────────────────────────────────────


def test_cache_path_structure(tmp_path: Path) -> None:
    p = cache_path(tmp_path, "EURUSD", 2024, 1, 15)
    assert p == tmp_path / "dukascopy" / "EURUSD" / "2024" / "01" / "15.bi5"


def test_cache_path_month_zero_padded(tmp_path: Path) -> None:
    p = cache_path(tmp_path, "USDJPY", 2024, 3, 5)
    assert "03" in str(p)
    assert "05.bi5" in str(p)


# ── parse_bi5 with synthetic data ─────────────────────────────────────────────


def test_parse_bi5_empty_bytes_returns_empty_list() -> None:
    assert parse_bi5(b"", DIVIDER_EUR, _eurusd_day()) == []


def test_parse_bi5_corrupt_bytes_returns_empty_list() -> None:
    assert parse_bi5(b"not lzma compressed", DIVIDER_EUR, _eurusd_day()) == []


def test_parse_bi5_single_candle_known_values() -> None:
    # 09:00 UTC  open=1.09000 high=1.09500 low=1.08800 close=1.09200
    ts_ms = 9 * 3_600_000   # 09:00 UTC in milliseconds
    o_raw = int(1.09000 * DIVIDER_EUR)
    h_raw = int(1.09500 * DIVIDER_EUR)
    l_raw = int(1.08800 * DIVIDER_EUR)
    c_raw = int(1.09200 * DIVIDER_EUR)

    raw = _compress(_pack_candle(ts_ms, o_raw, h_raw, l_raw, c_raw))
    bars = parse_bi5(raw, DIVIDER_EUR, _eurusd_day())

    assert len(bars) == 1
    bar = bars[0]
    assert bar.timestamp == datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
    assert abs(bar.open  - 1.09000) < 1e-5
    assert abs(bar.high  - 1.09500) < 1e-5
    assert abs(bar.low   - 1.08800) < 1e-5
    assert abs(bar.close - 1.09200) < 1e-5


def test_parse_bi5_multiple_candles_count() -> None:
    candles = b"".join(
        _pack_candle(h * 3_600_000, 109_000, 109_100, 108_900, 109_050)
        for h in range(8)
    )
    bars = parse_bi5(_compress(candles), DIVIDER_EUR, _eurusd_day())
    assert len(bars) == 8


def test_parse_bi5_timestamps_are_utc() -> None:
    raw = _compress(_pack_candle(0, 109_000, 109_100, 108_900, 109_000))
    bars = parse_bi5(raw, DIVIDER_EUR, _eurusd_day())
    assert bars[0].timestamp.tzinfo is not None
    assert bars[0].timestamp.tzinfo == UTC


def test_parse_bi5_skips_zero_price_candle() -> None:
    good = _pack_candle(3_600_000, 109_000, 109_100, 108_900, 109_000)
    bad  = _pack_candle(7_200_000, 0, 0, 0, 0)  # zero price
    bars = parse_bi5(_compress(good + bad), DIVIDER_EUR, _eurusd_day())
    assert len(bars) == 1


def test_parse_bi5_usdjpy_divider() -> None:
    # 150.000 USDJPY
    o_raw = int(150.000 * DIVIDER_JPY)
    h_raw = int(150.500 * DIVIDER_JPY)
    l_raw = int(149.800 * DIVIDER_JPY)
    c_raw = int(150.100 * DIVIDER_JPY)
    raw = _compress(_pack_candle(3_600_000, o_raw, h_raw, l_raw, c_raw))
    bars = parse_bi5(raw, DIVIDER_JPY, date(2024, 1, 15))
    assert len(bars) == 1
    assert abs(bars[0].open  - 150.000) < 0.01
    assert abs(bars[0].high  - 150.500) < 0.01


def test_parse_bi5_sessions_inferred() -> None:
    # 09:00 UTC → London session open
    ts_ms = 9 * 3_600_000
    raw = _compress(_pack_candle(ts_ms, 109_000, 109_100, 108_900, 109_000))
    bars = parse_bi5(raw, DIVIDER_EUR, _eurusd_day())
    assert "london" in bars[0].sessions


def test_parse_bi5_bars_are_market_bar_instances() -> None:
    raw = _compress(_pack_candle(3_600_000, 109_000, 109_100, 108_900, 109_000))
    bars = parse_bi5(raw, DIVIDER_EUR, _eurusd_day())
    assert all(isinstance(b, MarketBar) for b in bars)


# ── load_dukascopy_h1 with pre-populated cache (no network) ───────────────────


def _write_fake_day(cache_dir: Path, instrument: str, d: date, n_bars: int = 4) -> None:
    """Write a synthetic bi5 file for one day into the cache."""
    candles = b"".join(
        _pack_candle(h * 3_600_000, 109_000 + h, 109_100 + h, 108_900 + h, 109_050 + h)
        for h in range(n_bars)
    )
    path = cache_path(cache_dir, instrument, d.year, d.month, d.day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_compress(candles))


def test_load_from_cache_returns_correct_bar_count(tmp_path: Path) -> None:
    d = date(2024, 1, 15)
    _write_fake_day(tmp_path, "EURUSD", d, n_bars=6)
    bars = load_dukascopy_h1("EURUSD", d, d, tmp_path)
    assert len(bars) == 6


def test_load_multi_day_from_cache(tmp_path: Path) -> None:
    for day_n in range(3):
        _write_fake_day(tmp_path, "EURUSD", date(2024, 1, 15 + day_n), n_bars=4)
    bars = load_dukascopy_h1("EURUSD", date(2024, 1, 15), date(2024, 1, 17), tmp_path)
    assert len(bars) == 12


def test_load_skips_missing_day_gracefully(tmp_path: Path) -> None:
    # Only populate day 15; day 16 is absent (weekend-like) — write empty bytes.
    _write_fake_day(tmp_path, "EURUSD", date(2024, 1, 15), n_bars=3)
    empty_path = cache_path(tmp_path, "EURUSD", 2024, 1, 16)
    empty_path.parent.mkdir(parents=True, exist_ok=True)
    empty_path.write_bytes(b"")   # simulate cached weekend/holiday
    bars = load_dukascopy_h1("EURUSD", date(2024, 1, 15), date(2024, 1, 16), tmp_path)
    assert len(bars) == 3


def test_load_bars_are_sorted_ascending(tmp_path: Path) -> None:
    for day_n in range(2):
        _write_fake_day(tmp_path, "EURUSD", date(2024, 1, 15 + day_n), n_bars=4)
    bars = load_dukascopy_h1("EURUSD", date(2024, 1, 15), date(2024, 1, 16), tmp_path)
    timestamps = [b.timestamp for b in bars]
    assert timestamps == sorted(timestamps)


def test_load_unsupported_instrument_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported instrument"):
        load_dukascopy_h1("GBPUSD", date(2024, 1, 1), date(2024, 1, 1), tmp_path)


def test_load_writes_missing_day_to_cache(tmp_path: Path) -> None:
    """A day not in cache but returning empty bytes should be written as empty cache file."""
    import unittest.mock as mock

    d = date(2024, 1, 15)
    with mock.patch("fx_backtester.data.dukascopy.fetch_raw", return_value=b""):
        bars = load_dukascopy_h1("EURUSD", d, d, tmp_path)

    written = cache_path(tmp_path, "EURUSD", 2024, 1, 15)
    assert written.exists()
    assert written.read_bytes() == b""
    assert bars == []


# ── CSV round-trip ────────────────────────────────────────────────────────────


def test_bars_to_csv_produces_correct_columns(tmp_path: Path) -> None:
    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 15, 9, 0, tzinfo=UTC),
            open=1.09000,
            high=1.09500,
            low=1.08800,
            close=1.09200,
        )
    ]
    out = tmp_path / "test.csv"
    bars_to_csv(bars, out)

    with out.open() as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    assert set(rows[0].keys()) >= {"timestamp", "open", "high", "low", "close"}
    assert abs(float(rows[0]["open"]) - 1.09000) < 1e-5
    assert abs(float(rows[0]["high"]) - 1.09500) < 1e-5


# ── End-to-end: fetch → CSV → backtest ───────────────────────────────────────


def test_end_to_end_fetch_csv_backtest(tmp_path: Path) -> None:
    """Full pipeline: mocked fetch_raw → load_dukascopy_h1 → bars_to_csv → run_backtest_from_csv.

    This test exercises the complete real-data integration path without touching
    the network.  fetch_raw is patched to return deterministic synthetic bi5 bytes
    for every requested day.  Everything downstream — normalization, CSV write,
    CSV read, signal pipeline, backtest engine — runs exactly as it would on live
    Dukascopy data.
    """
    import unittest.mock as mock
    from pathlib import Path as P

    from fx_backtester.formalizer.execution_policy import default_execution_policy
    from fx_backtester.formalizer.request_formalizer import formalize_strategy_request
    from fx_backtester.orchestrator import run_backtest_from_csv

    # --- build two weeks of synthetic H1 bars (Mon-Fri only) ------------------
    # 10 weekdays × 20 bars/day → 200 bars; enough for RSI(14) warmup + trades
    start_day = date(2024, 1, 8)   # Monday
    end_day   = date(2024, 1, 19)  # Friday of week 2

    def fake_bi5_for_day(d: date) -> bytes:
        """Return a deterministic compressed bi5 day file for a given date."""
        base_price = 1.09000 + (d.toordinal() % 7) * 0.00100
        candles = b"".join(
            _pack_candle(
                h * 3_600_000,
                int((base_price + h * 0.0001) * DIVIDER_EUR),
                int((base_price + h * 0.0001 + 0.0005) * DIVIDER_EUR),
                int((base_price + h * 0.0001 - 0.0005) * DIVIDER_EUR),
                int((base_price + h * 0.0001 + 0.0001) * DIVIDER_EUR),
            )
            for h in range(20)
        )
        return _compress(candles)

    def patched_fetch_raw(url: str, **_: object) -> bytes:
        # URL: .../EURUSD/2024/00/08/BID_candles_hour_1.bi5
        # parts[-4]=year, parts[-3]=month_0, parts[-2]=day, parts[-1]=filename
        parts = url.split("/")
        year, month_0, day_s = int(parts[-4]), int(parts[-3]), int(parts[-2])
        d = date(year, month_0 + 1, day_s)
        if d.weekday() >= 5:
            return b""   # weekend — no data
        return fake_bi5_for_day(d)

    cache_dir = tmp_path / "cache"
    csv_out   = tmp_path / "eurusd.csv"

    with mock.patch("fx_backtester.data.dukascopy.fetch_raw", side_effect=patched_fetch_raw):
        bars = load_dukascopy_h1("EURUSD", start_day, end_day, cache_dir)

    assert len(bars) > 0
    assert all(isinstance(b, MarketBar) for b in bars)

    bars_to_csv(bars, csv_out)
    assert csv_out.exists()

    # --- run full backtest pipeline on the CSV --------------------------------
    outcome = formalize_strategy_request(
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter when RSI is below 30. Exit when RSI is above 55. "
        "Stop loss 20 pips. Take profit 40 pips. Risk 1% per trade. Account currency USD."
    )
    assert outcome.notes.status == "accepted"

    result, prepared, quality, run_dir, robustness, _ = run_backtest_from_csv(
        csv_path=csv_out,
        spec=outcome.spec,
        policy=default_execution_policy(),
        repo_root=tmp_path,
    )

    # Pipeline completed without error — structural assertions only.
    assert quality.missing_required_fields == 0
    assert quality.non_monotonic_timestamps == 0
    assert len(prepared.bars) == len(bars)
    assert result.ending_equity > 0
    assert result.trade_count >= 0
    # Drawdown pct is plain percent (0-100 range), never a 0-1 fraction.
    assert 0.0 <= result.metrics.max_drawdown_pct < 100.0
    assert run_dir.exists()


def test_bars_to_csv_roundtrip_through_load_market_bars(tmp_path: Path) -> None:
    """CSV written by bars_to_csv must be parseable by the existing load_market_bars."""
    from fx_backtester.data.loaders import load_market_bars

    bars = [
        MarketBar(
            timestamp=datetime(2024, 1, 15, h, 0, tzinfo=UTC),
            open=1.09 + h * 0.001,
            high=1.09 + h * 0.001 + 0.0005,
            low=1.09 + h * 0.001 - 0.0005,
            close=1.09 + h * 0.001 + 0.0002,
        )
        for h in range(5)
    ]
    out = tmp_path / "roundtrip.csv"
    bars_to_csv(bars, out)
    loaded = load_market_bars(out)

    assert len(loaded) == 5
    assert all(isinstance(b, MarketBar) for b in loaded)
    assert abs(loaded[2].open - bars[2].open) < 1e-4
