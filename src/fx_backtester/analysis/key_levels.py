"""Key level detection and price reaction scanner.

Detects when price enters a defined zone around a key level and records
what happens over the following N bars.  Three detection modes:

  round_number  – every ``round_pips`` interval within the data's price range
  swing_high    – bars whose high dominates a symmetric lookback window
  swing_low     – bars whose low dominates a symmetric lookback window
  manual        – caller-supplied price list

Touch identification
--------------------
A *touch* is recorded when a bar's range overlaps the zone
(``bar.low <= level.price + zone`` and ``bar.high >= level.price - zone``).
Approach direction is determined by the previous bar's close:

  from_above  – close[i-1] was above the level  (support test)
  from_below  – close[i-1] was below the level  (resistance test)

A ``cooldown_bars`` guard prevents the same touch being counted twice
when price hovers in the zone across consecutive bars.

Forward returns
---------------
From the touch bar's close, pip moves are recorded at each horizon in
``forward_horizons`` (default [1, 5, 10, 20]).  Outcome is classified as:

  reversed       – max favorable move ≥ reversal_threshold_pips
  broke_through  – max adverse move ≥ breakout_threshold_pips  (and > favorable)
  consolidated   – neither threshold reached
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.data.models import MarketBar


# ── Data models ───────────────────────────────────────────────────────────────


class KeyLevel(BaseModel):
    price: float
    label: str
    level_type: Literal["round_number", "swing_high", "swing_low", "manual"]


class LevelTouch(BaseModel):
    bar_index: int
    timestamp: datetime
    approach: Literal["from_above", "from_below"]
    touch_close: float       # close of the bar that entered the zone
    level_price: float


class TouchReaction(BaseModel):
    touch: LevelTouch
    # pip move from touch_close at each horizon: positive = price is higher
    forward_pips: dict[int, float]
    max_favorable_pips: float   # max move in expected reversal direction
    max_adverse_pips: float     # max move through / beyond the level
    outcome: Literal["reversed", "broke_through", "consolidated"]


class LevelReactionSummary(BaseModel):
    level: KeyLevel
    zone_pips: float
    forward_bars: int
    touch_count: int = 0
    reversal_count: int = 0
    breakout_count: int = 0
    consolidation_count: int = 0
    from_above_count: int = 0
    from_above_reversal_count: int = 0
    from_below_count: int = 0
    from_below_reversal_count: int = 0
    avg_forward_pips: dict[int, float] = Field(default_factory=dict)
    reactions: list[TouchReaction] = Field(default_factory=list)

    @property
    def reversal_rate(self) -> float:
        return round(self.reversal_count / self.touch_count, 4) if self.touch_count else 0.0

    @property
    def breakout_rate(self) -> float:
        return round(self.breakout_count / self.touch_count, 4) if self.touch_count else 0.0

    @property
    def from_above_reversal_rate(self) -> float:
        return round(self.from_above_reversal_count / self.from_above_count, 4) if self.from_above_count else 0.0

    @property
    def from_below_reversal_rate(self) -> float:
        return round(self.from_below_reversal_count / self.from_below_count, 4) if self.from_below_count else 0.0


class LevelStudyReport(BaseModel):
    instrument: str
    pip_size: float
    bar_count: int
    price_range_low: float
    price_range_high: float
    summaries: list[LevelReactionSummary]

    @property
    def levels_studied(self) -> int:
        return len(self.summaries)

    @property
    def total_touches(self) -> int:
        return sum(s.touch_count for s in self.summaries)


# ── Level detection ───────────────────────────────────────────────────────────


def detect_round_number_levels(
    bars: list[MarketBar],
    pip_size: float = 0.0001,
    round_pips: int = 50,
) -> list[KeyLevel]:
    """Return levels at every ``round_pips`` interval within the data range."""
    if not bars:
        return []
    step = pip_size * round_pips
    low  = min(bar.low  for bar in bars)
    high = max(bar.high for bar in bars)

    start = round(low / step) * step
    levels: list[KeyLevel] = []
    price = start
    while price <= high + step:
        p = round(price, 5)
        if low - step < p < high + step:
            levels.append(KeyLevel(price=p, label=f"round_{p:.5f}", level_type="round_number"))
        price = round(price + step, 5)
    return levels


def detect_swing_high_levels(
    bars: list[MarketBar],
    lookback: int = 5,
) -> list[KeyLevel]:
    """Return levels at swing highs — bars whose high dominates a 2×lookback window."""
    levels: list[KeyLevel] = []
    n = len(bars)
    for i in range(lookback, n - lookback):
        candidate = bars[i].high
        window = [bars[j].high for j in range(i - lookback, i + lookback + 1) if j != i]
        if candidate > max(window):
            levels.append(KeyLevel(
                price=round(candidate, 5),
                label=f"swing_high_{bars[i].timestamp.date()}",
                level_type="swing_high",
            ))
    return levels


def detect_swing_low_levels(
    bars: list[MarketBar],
    lookback: int = 5,
) -> list[KeyLevel]:
    """Return levels at swing lows — bars whose low dominates a 2×lookback window."""
    levels: list[KeyLevel] = []
    n = len(bars)
    for i in range(lookback, n - lookback):
        candidate = bars[i].low
        window = [bars[j].low for j in range(i - lookback, i + lookback + 1) if j != i]
        if candidate < min(window):
            levels.append(KeyLevel(
                price=round(candidate, 5),
                label=f"swing_low_{bars[i].timestamp.date()}",
                level_type="swing_low",
            ))
    return levels


# ── Touch scanner ─────────────────────────────────────────────────────────────


def _classify_outcome(
    *,
    approach: str,
    max_up_pips: float,
    max_down_pips: float,
    reversal_threshold: float,
    breakout_threshold: float,
) -> tuple[float, float, str]:
    """Return (max_favorable_pips, max_adverse_pips, outcome)."""
    if approach == "from_above":
        favorable = max_up_pips    # bounce = up
        adverse   = max_down_pips  # break   = down through support
    else:
        favorable = max_down_pips  # rejection = down
        adverse   = max_up_pips    # break     = up through resistance

    if adverse >= breakout_threshold and adverse >= favorable:
        outcome = "broke_through"
    elif favorable >= reversal_threshold:
        outcome = "reversed"
    else:
        outcome = "consolidated"

    return round(favorable, 1), round(adverse, 1), outcome


def scan_level_reactions(
    bars: list[MarketBar],
    level: KeyLevel,
    *,
    pip_size: float = 0.0001,
    zone_pips: float = 5.0,
    forward_horizons: list[int] | None = None,
    forward_bars: int = 20,
    cooldown_bars: int = 5,
    reversal_threshold_pips: float = 15.0,
    breakout_threshold_pips: float = 15.0,
) -> LevelReactionSummary:
    """Scan ``bars`` for touches of ``level`` and compute forward reactions.

    Returns a fully populated :class:`LevelReactionSummary`.
    """
    horizons = sorted(set(forward_horizons or [1, 5, 10, 20]))
    zone = zone_pips * pip_size
    n    = len(bars)
    last_touch_idx: int = -cooldown_bars - 1   # sentinel

    summary = LevelReactionSummary(
        level=level,
        zone_pips=zone_pips,
        forward_bars=forward_bars,
    )

    for i in range(1, n):
        bar  = bars[i]
        prev = bars[i - 1]

        # Bar range must overlap the zone.
        in_zone = bar.low <= level.price + zone and bar.high >= level.price - zone
        if not in_zone:
            continue

        # Cooldown guard.
        if i - last_touch_idx <= cooldown_bars:
            continue

        # Approach direction from previous bar's close.
        if prev.close > level.price:
            approach: Literal["from_above", "from_below"] = "from_above"
        else:
            approach = "from_below"

        last_touch_idx = i
        touch = LevelTouch(
            bar_index=i,
            timestamp=bar.timestamp,
            approach=approach,
            touch_close=bar.close,
            level_price=level.price,
        )

        # Forward window.
        window_end = min(i + forward_bars + 1, n)
        fwd_bars   = bars[i + 1 : window_end]

        forward_pips: dict[int, float] = {}
        for h in horizons:
            idx = i + h
            if idx < n:
                forward_pips[h] = round((bars[idx].close - bar.close) / pip_size, 1)

        if fwd_bars:
            max_high = max(b.high for b in fwd_bars)
            min_low  = min(b.low  for b in fwd_bars)
        else:
            max_high = bar.high
            min_low  = bar.low

        max_up_pips   = round((max_high - bar.close) / pip_size, 1)
        max_down_pips = round((bar.close - min_low)  / pip_size, 1)

        favorable, adverse, outcome = _classify_outcome(
            approach=approach,
            max_up_pips=max_up_pips,
            max_down_pips=max_down_pips,
            reversal_threshold=reversal_threshold_pips,
            breakout_threshold=breakout_threshold_pips,
        )

        reaction = TouchReaction(
            touch=touch,
            forward_pips=forward_pips,
            max_favorable_pips=favorable,
            max_adverse_pips=adverse,
            outcome=outcome,
        )
        summary.reactions.append(reaction)
        summary.touch_count += 1

        if outcome == "reversed":
            summary.reversal_count += 1
        elif outcome == "broke_through":
            summary.breakout_count += 1
        else:
            summary.consolidation_count += 1

        if approach == "from_above":
            summary.from_above_count += 1
            if outcome == "reversed":
                summary.from_above_reversal_count += 1
        else:
            summary.from_below_count += 1
            if outcome == "reversed":
                summary.from_below_reversal_count += 1

    # Aggregate average forward pips across all reactions.
    for h in horizons:
        values = [r.forward_pips[h] for r in summary.reactions if h in r.forward_pips]
        summary.avg_forward_pips[h] = round(sum(values) / len(values), 1) if values else 0.0

    return summary


# ── Top-level study runner ────────────────────────────────────────────────────


def run_level_study(
    bars: list[MarketBar],
    levels: list[KeyLevel],
    instrument: str,
    pip_size: float = 0.0001,
    *,
    zone_pips: float = 5.0,
    forward_bars: int = 20,
    forward_horizons: list[int] | None = None,
    cooldown_bars: int = 5,
    reversal_threshold_pips: float = 15.0,
    breakout_threshold_pips: float = 15.0,
    min_touches: int = 2,
) -> LevelStudyReport:
    """Run the full key level reaction study across all levels.

    Levels with fewer than ``min_touches`` are excluded from the report.
    """
    summaries: list[LevelReactionSummary] = []

    for level in levels:
        summary = scan_level_reactions(
            bars,
            level,
            pip_size=pip_size,
            zone_pips=zone_pips,
            forward_horizons=forward_horizons,
            forward_bars=forward_bars,
            cooldown_bars=cooldown_bars,
            reversal_threshold_pips=reversal_threshold_pips,
            breakout_threshold_pips=breakout_threshold_pips,
        )
        if summary.touch_count >= min_touches:
            summaries.append(summary)

    # Sort by touch count descending (most-tested levels first).
    summaries.sort(key=lambda s: s.touch_count, reverse=True)

    return LevelStudyReport(
        instrument=instrument,
        pip_size=pip_size,
        bar_count=len(bars),
        price_range_low=round(min(b.low  for b in bars), 5) if bars else 0.0,
        price_range_high=round(max(b.high for b in bars), 5) if bars else 0.0,
        summaries=summaries,
    )
