"""Minimal deterministic backtest loop for v0.2.

This remains intentionally narrow:
- single instrument (EURUSD)
- one position at a time
- long-only RSI mean-reversion style entry/exit semantics
- explicit spread/slippage via ExecutionPolicy
- deterministic TP/SL handling from bar open/high/low/close data
- optional explicit separation between signal bar and execution bar
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.engine.execution import apply_execution_policy
from fx_backtester.engine.sizing import size_position_units
from fx_backtester.engine.trade_log import TradeRecord
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec


class SignalBar(BaseModel):
    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    entry_long: bool = False
    exit_long: bool = False
    signal_bar_timestamp: str | None = None
    execution_price: float | None = Field(default=None, gt=0)
    signal_rsi: float | None = None
    sessions: list[str] = Field(default_factory=list)


class BacktestResult(BaseModel):
    starting_equity: float = Field(..., gt=0)
    ending_equity: float = Field(..., gt=0)
    trade_count: int = Field(..., ge=0)
    trades: list[TradeRecord]


class _OpenPosition(BaseModel):
    trade_id: str
    side: Literal["buy"] = "buy"
    entry_time: datetime
    entry_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    quantity_units: int = Field(..., gt=0)
    evidence_ref: str | None = None


def _price_delta_to_pnl_usd(*, entry_price: float, exit_price: float, quantity_units: int) -> float:
    return round((exit_price - entry_price) * quantity_units, 2)


def _close_trade(position: _OpenPosition, *, exit_time: datetime, exit_price: float, execution_policy_name: str) -> TradeRecord:
    return TradeRecord(
        trade_id=position.trade_id,
        side=position.side,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        stop_loss_price=position.stop_loss_price,
        take_profit_price=position.take_profit_price,
        quantity_units=position.quantity_units,
        execution_policy_name=execution_policy_name,
        evidence_ref=position.evidence_ref,
        exit_time=exit_time,
        exit_price=exit_price,
        pnl_usd=_price_delta_to_pnl_usd(
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity_units=position.quantity_units,
        ),
    )


def run_backtest(
    *,
    bars: list[SignalBar],
    spec: StrategySpec,
    policy: ExecutionPolicy,
) -> BacktestResult:
    equity = spec.risk.initial_equity
    trades: list[TradeRecord] = []
    open_position: _OpenPosition | None = None
    pip_size = spec.instrument.pip_size
    trade_index = 0

    for bar in bars:
        if open_position is not None:
            if bar.low <= open_position.stop_loss_price:
                trade = _close_trade(
                    open_position,
                    exit_time=bar.timestamp,
                    exit_price=open_position.stop_loss_price,
                    execution_policy_name=spec.execution_policy_name,
                )
                trades.append(trade)
                equity = round(equity + (trade.pnl_usd or 0.0), 2)
                open_position = None
                continue

            if bar.high >= open_position.take_profit_price:
                trade = _close_trade(
                    open_position,
                    exit_time=bar.timestamp,
                    exit_price=open_position.take_profit_price,
                    execution_policy_name=spec.execution_policy_name,
                )
                trades.append(trade)
                equity = round(equity + (trade.pnl_usd or 0.0), 2)
                open_position = None
                continue

            if bar.exit_long:
                requested_exit_price = bar.execution_price or bar.close
                exit_fill = apply_execution_policy(
                    side="sell",
                    requested_price=requested_exit_price,
                    policy=policy,
                    pip_size=pip_size,
                )
                trade = _close_trade(
                    open_position,
                    exit_time=bar.timestamp,
                    exit_price=exit_fill.executed_price,
                    execution_policy_name=spec.execution_policy_name,
                )
                trades.append(trade)
                equity = round(equity + (trade.pnl_usd or 0.0), 2)
                open_position = None
                continue

        if open_position is None and bar.entry_long:
            trade_index += 1
            requested_entry_price = bar.execution_price or bar.close
            entry_fill = apply_execution_policy(
                side="buy",
                requested_price=requested_entry_price,
                policy=policy,
                pip_size=pip_size,
            )
            quantity_units = size_position_units(
                equity_usd=equity,
                risk=spec.risk,
                instrument=spec.instrument,
                stop_loss_pips=spec.rules.stop_loss_pips,
            )
            evidence_ref = None
            if bar.signal_bar_timestamp is not None:
                evidence_ref = f"signal={bar.signal_bar_timestamp}|execution={bar.timestamp.isoformat()}"
            open_position = _OpenPosition(
                trade_id=f"{spec.instrument.symbol.lower()}-{trade_index:04d}",
                entry_time=bar.timestamp,
                entry_price=entry_fill.executed_price,
                stop_loss_price=round(entry_fill.executed_price - (spec.rules.stop_loss_pips * pip_size), 5),
                take_profit_price=round(entry_fill.executed_price + (spec.rules.take_profit_pips * pip_size), 5),
                quantity_units=quantity_units,
                evidence_ref=evidence_ref,
            )

    return BacktestResult(
        starting_equity=spec.risk.initial_equity,
        ending_equity=equity,
        trade_count=len(trades),
        trades=trades,
    )
