"""Tests for the key level reaction scanner.

Covers:
  - round number level detection
  - swing high / swing low detection
  - touch detection (in-zone, approach direction, cooldown)
  - forward return computation at each horizon
  - outcome classification (reversed / broke_through / consolidated)
  - LevelStudyReport aggregation
  - markdown + JSON report generation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fx_backtester.analysis.key_levels import (
    KeyLevel,
    LevelReactionSummary,
    detect_prev_day_high_levels,
    detect_prev_day_low_levels,
    detect_prev_week_high_levels,
    detect_prev_week_low_levels,
    detect_round_number_levels,
    detect_session_high_levels,
    detect_session_low_levels,
    detect_swing_high_levels,
    detect_swing_low_levels,
    run_level_study,
    scan_level_reactions,
)
from fx_backtester.analysis.level_report import build_markdown_report, write_level_study_artifacts
from fx_backtester.data.models import MarketBar


# ── Helpers ───────────────────────────────────────────────────────────────────

_BASE_TIME = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)


def _bar(
    h: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    sessions: list[str] | None = None,
) -> MarketBar:
    return MarketBar(
        timestamp=_BASE_TIME + timedelta(hours=h),
        open=open_,
        high=high,
        low=low,
        close=close,
        sessions=sessions or [],
    )


def _flat_bars(n: int, price: float = 1.09000, spread: float = 0.0003) -> list[MarketBar]:
    """N bars hovering at `price` with tiny range — useful as a baseline."""
    return [
        _bar(h, price, price + spread, price - spread, price)
        for h in range(n)
    ]


# ── Round number detection ────────────────────────────────────────────────────


def test_round_numbers_found_within_data_range() -> None:
    bars = _flat_bars(1, price=1.09200) + _flat_bars(1, price=1.10800)
    levels = detect_round_number_levels(bars, pip_size=0.0001, round_pips=50)
    prices = {l.price for l in levels}
    assert 1.09000 in prices or any(abs(p - 1.090) < 0.0001 for p in prices)
    assert all(l.level_type == "round_number" for l in levels)


def test_round_numbers_step_size() -> None:
    bars = [_bar(0, 1.09000, 1.11000, 1.09000, 1.10000)]
    levels = detect_round_number_levels(bars, pip_size=0.0001, round_pips=100)
    prices = sorted(l.price for l in levels)
    # Steps should be ~0.01 apart (100 pips × 0.0001)
    for a, b in zip(prices, prices[1:]):
        assert abs((b - a) - 0.01) < 1e-6


def test_round_numbers_empty_bars() -> None:
    assert detect_round_number_levels([]) == []


# ── Swing high / low detection ────────────────────────────────────────────────


def test_swing_high_detected_at_dominant_bar() -> None:
    # bar 5 has the highest high
    bars = [
        _bar(0, 1.09, 1.090 + i * 0.0002, 1.089, 1.090)
        for i in range(5)
    ] + [
        _bar(5, 1.09, 1.0920, 1.089, 1.090),   # swing high
    ] + [
        _bar(6 + i, 1.09, 1.090 + (4 - i) * 0.0002, 1.089, 1.090)
        for i in range(5)
    ]
    levels = detect_swing_high_levels(bars, lookback=5)
    assert len(levels) == 1
    assert abs(levels[0].price - 1.0920) < 1e-5
    assert levels[0].level_type == "swing_high"


def test_swing_low_detected_at_dominant_bar() -> None:
    bars = [
        _bar(0, 1.09, 1.091, 1.089 + i * 0.0002, 1.090)
        for i in range(5)
    ] + [
        _bar(5, 1.09, 1.091, 1.0870, 1.090),   # swing low
    ] + [
        _bar(6 + i, 1.09, 1.091, 1.089 + (4 - i) * 0.0002, 1.090)
        for i in range(5)
    ]
    levels = detect_swing_low_levels(bars, lookback=5)
    assert len(levels) == 1
    assert abs(levels[0].price - 1.0870) < 1e-5
    assert levels[0].level_type == "swing_low"


def test_swing_detection_needs_enough_bars() -> None:
    bars = _flat_bars(4, price=1.09)
    # With lookback=5 we need at least 11 bars; 4 bars → nothing detected
    assert detect_swing_high_levels(bars, lookback=5) == []


# ── Touch detection: from_above (support test) ────────────────────────────────


def test_touch_from_above_detected() -> None:
    """Price drops into the zone from above → from_above touch."""
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),   # well above
        _bar(1, 1.0910, 1.0920, 1.0895, 1.0900),   # enters zone (low touches 1.0895 < 1.0900+zone)
    ] + _flat_bars(25, price=1.0940)
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0, forward_bars=20)
    assert summary.touch_count == 1
    assert summary.reactions[0].touch.approach == "from_above"


def test_touch_from_below_detected() -> None:
    """Price rises into the zone from below → from_below touch."""
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    bars = [
        _bar(0, 1.0850, 1.0860, 1.0840, 1.0850),   # well below
        _bar(1, 1.0890, 1.0905, 1.0880, 1.0895),   # enters zone from below
    ] + _flat_bars(25, price=1.0860)
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0, forward_bars=20)
    assert summary.touch_count == 1
    assert summary.reactions[0].touch.approach == "from_below"


def test_bar_outside_zone_not_counted() -> None:
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    bars = [
        _bar(0, 1.0960, 1.0970, 1.0955, 1.0960),  # high = 1.0970, zone top = 1.0905 → no touch
        _bar(1, 1.0960, 1.0970, 1.0955, 1.0960),
    ]
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0)
    assert summary.touch_count == 0


# ── Cooldown guard ────────────────────────────────────────────────────────────


def test_cooldown_prevents_double_count() -> None:
    """Two consecutive bars in the zone → only first is counted."""
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    in_zone = _bar(0, 1.0952, 1.0960, 1.0895, 1.0952)  # enters zone (idx 0 is prev)
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),  # bar[0]: above, no touch yet
        _bar(1, 1.0910, 1.0920, 1.0895, 1.0900),  # touch 1
        _bar(2, 1.0905, 1.0915, 1.0893, 1.0903),  # still in zone → cooldown
        _bar(3, 1.0905, 1.0915, 1.0893, 1.0903),  # still in zone → cooldown
    ] + _flat_bars(25, price=1.0940)
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0, cooldown_bars=5)
    assert summary.touch_count == 1


def test_second_touch_after_cooldown_is_counted() -> None:
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    away = _flat_bars(10, price=1.0940)  # 10 bars away from zone
    touch_bar = [_bar(0, 1.09, 1.091, 1.0895, 1.090)]
    bars = (
        [_bar(0, 1.0950, 1.0960, 1.0940, 1.0950)]  # prev above
        + touch_bar                                 # touch 1 at idx 1
        + away                                      # 10 bars away
        + touch_bar                                 # touch 2 at idx 12
        + _flat_bars(25, price=1.0940)
    )
    # Re-index timestamps
    bars = [b.model_copy(update={"timestamp": _BASE_TIME + timedelta(hours=i)}) for i, b in enumerate(bars)]
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0, cooldown_bars=5)
    assert summary.touch_count == 2


# ── Forward return computation ────────────────────────────────────────────────


def test_forward_pips_at_each_horizon() -> None:
    """Forward pip moves are measured from touch close."""
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    touch_close = 1.09000
    # After touch, price rises 1 pip per bar
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),  # prev above
        _bar(1, 1.09,   1.091,  1.0895, touch_close),  # touch at idx 1
    ] + [
        _bar(2 + h, 1.09, 1.090 + (h + 1) * 0.0001 + 0.0001,
             1.090 + (h + 1) * 0.0001 - 0.0001,
             touch_close + (h + 1) * 0.0001)
        for h in range(20)
    ]
    summary = scan_level_reactions(
        bars, level, pip_size=0.0001, zone_pips=5.0,
        forward_horizons=[1, 5, 10], forward_bars=20, cooldown_bars=25,
    )
    assert summary.touch_count == 1
    r = summary.reactions[0]
    assert abs(r.forward_pips[1]  - 1.0) < 0.2   # +1 pip after 1 bar
    assert abs(r.forward_pips[5]  - 5.0) < 0.2   # +5 pips after 5 bars
    assert abs(r.forward_pips[10] - 10.0) < 0.2  # +10 pips after 10 bars


# ── Outcome classification ────────────────────────────────────────────────────


def test_outcome_reversed_when_favorable_move_exceeds_threshold() -> None:
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    # Touch from above → bounce upward is favorable
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),  # prev: above level
        _bar(1, 1.0905, 1.0910, 1.0895, 1.0900),  # touch
    ] + [
        _bar(2 + h, 1.090, 1.090 + (h + 1) * 0.0003, 1.090, 1.090 + (h + 1) * 0.0003)
        for h in range(20)
    ]  # bounces up 3 pips/bar → 60 pips total → well above 15-pip threshold
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0,
                                   reversal_threshold_pips=15.0, breakout_threshold_pips=15.0,
                                   cooldown_bars=25)
    assert summary.reactions[0].outcome == "reversed"
    assert summary.reversal_count == 1


def test_outcome_broke_through_when_adverse_move_dominates() -> None:
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    # Touch from above → drops through support (adverse)
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),
        _bar(1, 1.0905, 1.0910, 1.0895, 1.0900),  # touch
    ] + [
        _bar(2 + h, 1.090, 1.090, 1.090 - (h + 1) * 0.0003, 1.090 - (h + 1) * 0.0003)
        for h in range(20)
    ]  # drops 3 pips/bar → 60 pips down → broke through support
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0,
                                   reversal_threshold_pips=15.0, breakout_threshold_pips=15.0,
                                   cooldown_bars=25)
    assert summary.reactions[0].outcome == "broke_through"
    assert summary.breakout_count == 1


def test_outcome_consolidated_when_price_stays_flat() -> None:
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),
        _bar(1, 1.0905, 1.0910, 1.0895, 1.0900),  # touch
    ] + _flat_bars(25, price=1.0902)  # hover nearby, < 15-pip move
    summary = scan_level_reactions(bars, level, pip_size=0.0001, zone_pips=5.0,
                                   reversal_threshold_pips=15.0, breakout_threshold_pips=15.0,
                                   cooldown_bars=25)
    assert summary.reactions[0].outcome == "consolidated"
    assert summary.consolidation_count == 1


# ── Aggregation ───────────────────────────────────────────────────────────────


def test_run_level_study_filters_min_touches(tmp_path: Path) -> None:
    """Levels with fewer than min_touches are excluded."""
    level_touched_once = KeyLevel(price=1.09000, label="a", level_type="manual")
    level_never_touched = KeyLevel(price=1.20000, label="b", level_type="manual")
    bars = [
        _bar(0, 1.0950, 1.0960, 1.0940, 1.0950),
        _bar(1, 1.0905, 1.0910, 1.0895, 1.0900),
    ] + _flat_bars(25, price=1.0940)
    report = run_level_study(
        bars,
        [level_touched_once, level_never_touched],
        instrument="EURUSD",
        pip_size=0.0001,
        min_touches=2,
    )
    # Neither level reaches 2 touches → both excluded
    assert report.levels_studied == 0
    assert report.total_touches == 0


def test_run_level_study_includes_level_meeting_min_touches() -> None:
    level = KeyLevel(price=1.09000, label="a", level_type="manual")
    # Build bars with two clearly separated touches
    away = [
        _bar(h, 1.0940, 1.0960, 1.0930, 1.0940)
        for h in range(10)
    ]
    touch = [_bar(0, 1.0910, 1.0920, 1.0895, 1.0900)]
    fwd   = [_bar(h, 1.0940, 1.0950, 1.0930, 1.0940) for h in range(25)]

    bars = (
        [_bar(0, 1.0950, 1.0960, 1.0940, 1.0950)]   # prev
        + touch + away + touch + fwd
    )
    bars = [b.model_copy(update={"timestamp": _BASE_TIME + timedelta(hours=i)}) for i, b in enumerate(bars)]
    report = run_level_study(bars, [level], instrument="EURUSD", pip_size=0.0001, min_touches=2)
    assert report.levels_studied == 1
    assert report.summaries[0].touch_count == 2


def test_run_level_study_sorted_by_touch_count_descending() -> None:
    l1 = KeyLevel(price=1.09000, label="l1", level_type="manual")
    l2 = KeyLevel(price=1.09500, label="l2", level_type="manual")
    # Manufacture bars that touch l1 four times and l2 two times.
    # (Simplified: just assert sort order via fake summaries — tested via a custom min_touches=1)
    bars = _flat_bars(50, price=1.09250)   # mid-point, touches both zones if zone is wide enough
    report = run_level_study(bars, [l1, l2], instrument="EURUSD", pip_size=0.0001,
                             zone_pips=30.0, min_touches=1)
    counts = [s.touch_count for s in report.summaries]
    assert counts == sorted(counts, reverse=True)


# ── Report generation ─────────────────────────────────────────────────────────


def test_build_markdown_report_contains_level_price() -> None:
    from fx_backtester.analysis.key_levels import LevelStudyReport
    level = KeyLevel(price=1.09000, label="test", level_type="manual")
    summary = LevelReactionSummary(
        level=level, zone_pips=5.0, forward_bars=20,
        touch_count=3, reversal_count=2, breakout_count=1, consolidation_count=0,
        avg_forward_pips={1: 2.1, 5: 7.3},
    )
    report = LevelStudyReport(
        instrument="EURUSD", pip_size=0.0001, bar_count=100,
        price_range_low=1.08, price_range_high=1.10, summaries=[summary],
    )
    md = build_markdown_report(report)
    assert "1.09000" in md
    assert "EURUSD" in md
    assert "Reversed" in md


def test_build_markdown_report_no_levels_message() -> None:
    from fx_backtester.analysis.key_levels import LevelStudyReport
    report = LevelStudyReport(
        instrument="EURUSD", pip_size=0.0001, bar_count=50,
        price_range_low=1.09, price_range_high=1.10, summaries=[],
    )
    md = build_markdown_report(report)
    assert "No levels" in md or "enough touches" in md


def test_write_level_study_artifacts_creates_files(tmp_path: Path) -> None:
    from fx_backtester.analysis.key_levels import LevelStudyReport
    report = LevelStudyReport(
        instrument="EURUSD", pip_size=0.0001, bar_count=10,
        price_range_low=1.09, price_range_high=1.10, summaries=[],
    )
    out = write_level_study_artifacts(report, tmp_path / "study")
    assert (out / "level_study.json").exists()
    assert (out / "level_study.md").exists()


# ── Previous day high / low ───────────────────────────────────────────────────

def _day_bars(day: int, high: float, low: float, sessions: list[str] | None = None) -> list[MarketBar]:
    """Return 3 H1 bars on a given day (Jan day, 2024)."""
    base = datetime(2024, 1, day, 10, 0, tzinfo=UTC)
    mid = (high + low) / 2
    return [
        MarketBar(timestamp=base,                      open=mid, high=high, low=low,  close=mid, sessions=sessions or []),
        MarketBar(timestamp=base + timedelta(hours=1), open=mid, high=high, low=low,  close=mid, sessions=sessions or []),
        MarketBar(timestamp=base + timedelta(hours=2), open=mid, high=high, low=low,  close=mid, sessions=sessions or []),
    ]


def test_prev_day_high_one_level_per_day() -> None:
    bars = _day_bars(1, 1.1050, 1.0990) + _day_bars(2, 1.1080, 1.1010) + _day_bars(3, 1.1070, 1.1000)
    levels = detect_prev_day_high_levels(bars)
    assert len(levels) == 3
    assert all(l.level_type == "prev_day_high" for l in levels)


def test_prev_day_high_correct_prices() -> None:
    bars = _day_bars(1, 1.1050, 1.0990) + _day_bars(2, 1.1080, 1.1010)
    levels = detect_prev_day_high_levels(bars)
    prices = [l.price for l in levels]
    assert 1.1050 in prices
    assert 1.1080 in prices


def test_prev_day_low_one_level_per_day() -> None:
    bars = _day_bars(1, 1.1050, 1.0990) + _day_bars(2, 1.1080, 1.1010)
    levels = detect_prev_day_low_levels(bars)
    assert len(levels) == 2
    assert all(l.level_type == "prev_day_low" for l in levels)


def test_prev_day_low_correct_prices() -> None:
    bars = _day_bars(1, 1.1050, 1.0990) + _day_bars(2, 1.1080, 1.1010)
    levels = detect_prev_day_low_levels(bars)
    prices = [l.price for l in levels]
    assert 1.0990 in prices
    assert 1.1010 in prices


def test_prev_day_high_labels_contain_date() -> None:
    bars = _day_bars(5, 1.1050, 1.0990)
    levels = detect_prev_day_high_levels(bars)
    assert any("2024-01-05" in l.label for l in levels)


def test_prev_day_high_empty_bars() -> None:
    assert detect_prev_day_high_levels([]) == []


def test_prev_day_low_empty_bars() -> None:
    assert detect_prev_day_low_levels([]) == []


# ── Previous week high / low ──────────────────────────────────────────────────

def _week_bar(week_offset_days: int, high: float, low: float) -> MarketBar:
    """Bar in the week starting 2024-01-01 (week 1) + offset."""
    ts = datetime(2024, 1, 1, 12, 0, tzinfo=UTC) + timedelta(days=week_offset_days)
    mid = (high + low) / 2
    return MarketBar(timestamp=ts, open=mid, high=high, low=low, close=mid, sessions=[])


def test_prev_week_high_one_level_per_week() -> None:
    bars = [_week_bar(0, 1.1050, 1.0990), _week_bar(7, 1.1080, 1.1010), _week_bar(14, 1.1070, 1.1000)]
    levels = detect_prev_week_high_levels(bars)
    assert len(levels) == 3
    assert all(l.level_type == "prev_week_high" for l in levels)


def test_prev_week_low_one_level_per_week() -> None:
    bars = [_week_bar(0, 1.1050, 1.0990), _week_bar(7, 1.1080, 1.1010)]
    levels = detect_prev_week_low_levels(bars)
    assert len(levels) == 2
    assert all(l.level_type == "prev_week_low" for l in levels)


def test_prev_week_high_multiple_bars_same_week_takes_max() -> None:
    bars = [
        _week_bar(0, 1.1050, 1.0990),  # Mon
        _week_bar(1, 1.1090, 1.1000),  # Tue — higher high
        _week_bar(2, 1.1040, 1.0980),  # Wed
    ]
    levels = detect_prev_week_high_levels(bars)
    assert len(levels) == 1
    assert levels[0].price == 1.1090


def test_prev_week_low_multiple_bars_same_week_takes_min() -> None:
    bars = [
        _week_bar(0, 1.1050, 1.0990),
        _week_bar(1, 1.1090, 1.0950),  # lower low
        _week_bar(2, 1.1040, 1.0980),
    ]
    levels = detect_prev_week_low_levels(bars)
    assert len(levels) == 1
    assert levels[0].price == 1.0950


def test_prev_week_high_labels_contain_week() -> None:
    bars = [_week_bar(0, 1.1050, 1.0990)]
    levels = detect_prev_week_high_levels(bars)
    assert any("_w" in l.label for l in levels)


# ── Session high / low ────────────────────────────────────────────────────────

def test_session_high_only_london_bars() -> None:
    bars = (
        _day_bars(1, 1.1060, 1.1010, sessions=["london"]) +
        _day_bars(2, 1.1080, 1.1020, sessions=["new_york"]) +   # different session
        _day_bars(3, 1.1070, 1.1000, sessions=["london"])
    )
    levels = detect_session_high_levels(bars, session="london")
    assert len(levels) == 2   # only days 1 and 3 have london bars
    assert all(l.level_type == "session_high" for l in levels)
    assert all("london_high" in l.label for l in levels)


def test_session_low_only_london_bars() -> None:
    bars = (
        _day_bars(1, 1.1060, 1.1010, sessions=["london"]) +
        _day_bars(2, 1.1080, 1.1020, sessions=["new_york"]) +
        _day_bars(3, 1.1070, 1.1000, sessions=["london"])
    )
    levels = detect_session_low_levels(bars, session="london")
    assert len(levels) == 2
    assert all(l.level_type == "session_low" for l in levels)


def test_session_high_new_york() -> None:
    bars = (
        _day_bars(1, 1.1090, 1.1010, sessions=["new_york"]) +
        _day_bars(2, 1.1050, 1.1000, sessions=["london"])
    )
    levels = detect_session_high_levels(bars, session="new_york")
    assert len(levels) == 1
    assert levels[0].price == 1.1090
    assert "new_york_high" in levels[0].label


def test_session_high_correct_max_per_day() -> None:
    base = datetime(2024, 1, 10, 9, 0, tzinfo=UTC)
    bars = [
        MarketBar(timestamp=base,                      open=1.105, high=1.1070, low=1.1040, close=1.105, sessions=["london"]),
        MarketBar(timestamp=base + timedelta(hours=1), open=1.105, high=1.1090, low=1.1050, close=1.105, sessions=["london"]),
        MarketBar(timestamp=base + timedelta(hours=2), open=1.105, high=1.1060, low=1.1030, close=1.105, sessions=["london"]),
    ]
    levels = detect_session_high_levels(bars, session="london")
    assert len(levels) == 1
    assert levels[0].price == 1.1090


def test_session_low_correct_min_per_day() -> None:
    base = datetime(2024, 1, 10, 9, 0, tzinfo=UTC)
    bars = [
        MarketBar(timestamp=base,                      open=1.105, high=1.1070, low=1.1040, close=1.105, sessions=["london"]),
        MarketBar(timestamp=base + timedelta(hours=1), open=1.105, high=1.1090, low=1.1020, close=1.105, sessions=["london"]),
        MarketBar(timestamp=base + timedelta(hours=2), open=1.105, high=1.1060, low=1.1030, close=1.105, sessions=["london"]),
    ]
    levels = detect_session_low_levels(bars, session="london")
    assert len(levels) == 1
    assert levels[0].price == 1.1020


def test_session_high_no_matching_session_returns_empty() -> None:
    bars = _day_bars(1, 1.1050, 1.0990, sessions=["new_york"])
    levels = detect_session_high_levels(bars, session="london")
    assert levels == []


def test_session_low_empty_bars() -> None:
    assert detect_session_low_levels([], session="london") == []
