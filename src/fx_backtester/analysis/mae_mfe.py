"""Maximum Adverse Excursion (MAE) and Maximum Favorable Excursion (MFE) analysis.

For every closed trade this module measures:

  MAE — how far price moved AGAINST the position before it closed.
        If you're long at 1.1000, MAE is how many pips below 1.1000
        the low got during the trade.  A stop of 20 pips that is almost
        never touched suggests the stop is too wide; one that's regularly
        tapped before recovery suggests it may be too tight.

  MFE — how far price moved IN FAVOUR of the position before it closed.
        If your take-profit is 30 pips but MFE averages 60 pips on
        winning trades, you are leaving half the move on the table.

Derived metrics
---------------
  efficiency      = pnl_pips / mfe_pips (winning trades only, clamped 0-1)
                    1.0 means you captured the entire available move.
                    0.5 means price went twice as far as your profit.

  mae_ratio       = mae_pips / stop_loss_pips
                    Values << 1 on losing trades mean the stop is too wide;
                    values << 1 on winning trades mean price came close to
                    stopping you out before recovering (stop may be tight).

Stop-health and TP-health insights are generated automatically from the
aggregate statistics and included in the report as plain-English text.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.engine.backtest import SignalBar
from fx_backtester.engine.trade_log import TradeRecord


# ── Per-trade excursion ───────────────────────────────────────────────────────


class TradeExcursion(BaseModel):
    trade_id: str
    side: Literal["buy", "sell"]
    entry_price: float
    exit_price: float
    pnl_pips: float
    mae_pips: float   # max adverse excursion in pips (always ≥ 0)
    mfe_pips: float   # max favorable excursion in pips (always ≥ 0)
    efficiency: float  # pnl_pips / mfe_pips, 0-1 for winners; negative for losers
    mae_ratio: float   # mae_pips / stop_loss_pips (how much of the stop was used)
    is_winner: bool


# ── Aggregate report ──────────────────────────────────────────────────────────


class MaeMfeReport(BaseModel):
    pip_size: float
    stop_loss_pips: float
    take_profit_pips: float

    trade_count: int               # all trades
    closed_trade_count: int        # trades with a known exit price
    winner_count: int
    loser_count: int

    # Aggregate across ALL closed trades
    avg_mae_pips: float
    avg_mfe_pips: float

    # Winners only
    winner_avg_mae_pips: float     # how far winners went against before winning
    winner_avg_mfe_pips: float     # how far winners went in favour
    winner_avg_efficiency: float   # avg(pnl / mfe) — capture rate

    # Losers only
    loser_avg_mae_pips: float      # should be ~stop_loss_pips if stops are hit cleanly
    loser_avg_mfe_pips: float      # how far losers went in favour before reversing

    excursions: list[TradeExcursion] = Field(default_factory=list)

    # Plain-English insights
    stop_insight: str
    tp_insight: str
    efficiency_insight: str


# ── Computation ───────────────────────────────────────────────────────────────


def _build_bar_index(bars: list[SignalBar]) -> dict[datetime, tuple[float, float]]:
    """Map timestamp → (high, low) for fast lookup."""
    return {bar.timestamp: (bar.high, bar.low) for bar in bars}


def _excursion_for_trade(
    trade: TradeRecord,
    bar_index: dict[datetime, tuple[float, float]],
    pip_size: float,
    stop_loss_pips: float,
) -> TradeExcursion | None:
    """Compute MAE/MFE for a single closed trade.  Returns None if bars are missing."""
    if trade.exit_time is None or trade.exit_price is None or trade.pnl_pips is None:
        return None  # open or incomplete trade

    entry_ts = trade.entry_time
    exit_ts  = trade.exit_time

    # Collect bars that fall within the trade window (inclusive of entry and exit bars).
    highs: list[float] = []
    lows:  list[float] = []
    for ts, (h, l) in bar_index.items():
        if entry_ts <= ts <= exit_ts:
            highs.append(h)
            lows.append(l)

    if not highs:
        return None

    max_high = max(highs)
    min_low  = min(lows)

    if trade.side == "buy":
        mae_pips = round(max(0.0, trade.entry_price - min_low)  / pip_size, 1)
        mfe_pips = round(max(0.0, max_high - trade.entry_price) / pip_size, 1)
    else:
        mae_pips = round(max(0.0, max_high - trade.entry_price) / pip_size, 1)
        mfe_pips = round(max(0.0, trade.entry_price - min_low)  / pip_size, 1)

    pnl = round(trade.pnl_pips, 1)
    is_winner = pnl > 0
    efficiency = round(pnl / mfe_pips, 3) if mfe_pips > 0 else (1.0 if is_winner else 0.0)
    mae_ratio  = round(mae_pips / stop_loss_pips, 3) if stop_loss_pips > 0 else 0.0

    return TradeExcursion(
        trade_id=trade.trade_id,
        side=trade.side,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        pnl_pips=pnl,
        mae_pips=mae_pips,
        mfe_pips=mfe_pips,
        efficiency=efficiency,
        mae_ratio=mae_ratio,
        is_winner=is_winner,
    )


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _stop_insight(
    winner_avg_mae: float,
    loser_avg_mae: float,
    stop_pips: float,
) -> str:
    if stop_pips <= 0:
        return "Stop loss not configured."
    loser_ratio = loser_avg_mae / stop_pips

    if winner_avg_mae > stop_pips * 0.7:
        return (
            f"Stops may be too tight — winning trades had an average MAE of "
            f"{winner_avg_mae:.1f} pips ({winner_avg_mae / stop_pips:.0%} of your "
            f"{stop_pips:.0f}-pip stop). Price frequently came close to stopping you "
            f"out before reversing in your favour. Consider widening the stop slightly."
        )
    if loser_ratio < 0.5:
        return (
            f"Stops may be too wide — losing trades only used {loser_avg_mae:.1f} pips "
            f"of your {stop_pips:.0f}-pip stop ({loser_ratio:.0%}) before closing at a loss. "
            f"A tighter stop could reduce losses without being hit more often."
        )
    return (
        f"Stop placement looks reasonable — losers used {loser_avg_mae:.1f} pips "
        f"({loser_ratio:.0%}) of the {stop_pips:.0f}-pip stop on average."
    )


def _tp_insight(
    winner_avg_mfe: float,
    take_profit_pips: float,
) -> str:
    if take_profit_pips <= 0 or winner_avg_mfe <= 0:
        return "Insufficient winner data for take-profit analysis."
    ratio = winner_avg_mfe / take_profit_pips
    if ratio > 1.8:
        return (
            f"Take-profit appears too conservative — winning trades averaged "
            f"{winner_avg_mfe:.1f} pips of favourable movement vs a TP of "
            f"{take_profit_pips:.0f} pips ({ratio:.1f}×). Consider a wider TP or "
            f"a trailing stop to capture more of the move."
        )
    if ratio < 0.8:
        return (
            f"Take-profit may be slightly aggressive — winners averaged only "
            f"{winner_avg_mfe:.1f} pips of MFE vs a {take_profit_pips:.0f}-pip TP. "
            f"Some trades may be closing before hitting TP."
        )
    return (
        f"Take-profit looks well-calibrated — winners averaged {winner_avg_mfe:.1f} pips "
        f"of MFE vs a {take_profit_pips:.0f}-pip TP ({ratio:.1f}×)."
    )


def _efficiency_insight(avg_efficiency: float) -> str:
    pct = round(avg_efficiency * 100)
    if avg_efficiency >= 0.75:
        return f"High capture efficiency ({pct}%) — you are extracting most of the available move."
    if avg_efficiency >= 0.5:
        return (
            f"Moderate capture efficiency ({pct}%) — winners are closing roughly halfway "
            f"through the available move. A trailing stop or wider TP may help."
        )
    return (
        f"Low capture efficiency ({pct}%) — winners are closing well before the move "
        f"exhausts itself. Review your exit rules or consider a trailing stop."
    )


def compute_mae_mfe(
    trades: list[TradeRecord],
    bars: list[SignalBar],
    *,
    pip_size: float = 0.0001,
    stop_loss_pips: float = 20.0,
    take_profit_pips: float = 30.0,
) -> MaeMfeReport:
    """Compute MAE/MFE for every closed trade and return an aggregate report.

    Parameters
    ----------
    trades:
        Trade records from ``BacktestResult.trades``.
    bars:
        Signal bars from ``PreparedSignalData.bars`` — used to find the
        high/low of each bar during the trade window.
    pip_size:
        Pip size for the instrument (e.g. 0.0001 for EURUSD).
    stop_loss_pips:
        Stop-loss distance in pips from the strategy spec — used for the
        stop-health insight and ``mae_ratio``.
    take_profit_pips:
        Take-profit distance in pips — used for the TP-health insight.
    """
    bar_index = _build_bar_index(bars)

    excursions: list[TradeExcursion] = []
    for trade in trades:
        exc = _excursion_for_trade(trade, bar_index, pip_size, stop_loss_pips)
        if exc is not None:
            excursions.append(exc)

    winners = [e for e in excursions if e.is_winner]
    losers  = [e for e in excursions if not e.is_winner]

    avg_mae = _avg([e.mae_pips for e in excursions])
    avg_mfe = _avg([e.mfe_pips for e in excursions])

    winner_avg_mae  = _avg([e.mae_pips    for e in winners])
    winner_avg_mfe  = _avg([e.mfe_pips    for e in winners])
    winner_avg_eff  = _avg([e.efficiency  for e in winners])
    loser_avg_mae   = _avg([e.mae_pips    for e in losers])
    loser_avg_mfe   = _avg([e.mfe_pips    for e in losers])

    return MaeMfeReport(
        pip_size=pip_size,
        stop_loss_pips=stop_loss_pips,
        take_profit_pips=take_profit_pips,
        trade_count=len(trades),
        closed_trade_count=len(excursions),
        winner_count=len(winners),
        loser_count=len(losers),
        avg_mae_pips=avg_mae,
        avg_mfe_pips=avg_mfe,
        winner_avg_mae_pips=winner_avg_mae,
        winner_avg_mfe_pips=winner_avg_mfe,
        winner_avg_efficiency=winner_avg_eff,
        loser_avg_mae_pips=loser_avg_mae,
        loser_avg_mfe_pips=loser_avg_mfe,
        excursions=excursions,
        stop_insight=_stop_insight(winner_avg_mae, loser_avg_mae, stop_loss_pips),
        tp_insight=_tp_insight(winner_avg_mfe, take_profit_pips),
        efficiency_insight=_efficiency_insight(winner_avg_eff),
    )
