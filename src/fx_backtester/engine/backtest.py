"""Deterministic backtest loop for v0.3.

Still intentionally narrow:
- single instrument
- one position at a time
- deterministic long and short support
- explicit spread/slippage assumptions
- conservative same-candle ambiguity handling
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.engine.execution import apply_execution_policy
from fx_backtester.engine.sizing import pip_value_per_standard_lot, size_position_units
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
    entry_short: bool = False
    exit_short: bool = False
    signal_bar_timestamp: str | None = None
    execution_price: float | None = Field(default=None, gt=0)
    signal_rsi: float | None = None
    sessions: list[str] = Field(default_factory=list)


class BacktestMetrics(BaseModel):
    gross_profit: float
    gross_loss: float
    gross_pips_won: float
    gross_pips_lost: float
    net_pips: float
    expectancy_pips: float
    average_win_pips: float
    average_loss_pips: float
    ambiguity_count: int
    spread_triggered_stop_count: int
    max_drawdown: float
    max_drawdown_pct: float
    max_drawdown_duration_trades: int
    session_summary: dict[str, dict[str, float | int]]


class BacktestResult(BaseModel):
    starting_equity: float = Field(..., gt=0)
    ending_equity: float = Field(..., gt=0)
    ending_equity_usd: float = Field(..., gt=0)
    trade_count: int = Field(..., ge=0)
    trades: list[TradeRecord]
    metrics: BacktestMetrics


class _OpenPosition(BaseModel):
    trade_id: str
    side: Literal["buy", "sell"]
    entry_time: datetime
    entry_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    quantity_units: int = Field(..., gt=0)
    evidence_ref: str | None = None
    sessions: list[str] = Field(default_factory=list)


def _price_delta_to_pnl(*, side: Literal["buy", "sell"], entry_price: float, exit_price: float, quantity_units: int) -> float:
    direction = 1 if side == "buy" else -1
    return round((exit_price - entry_price) * quantity_units * direction, 2)


def _price_delta_to_pips(*, side: Literal["buy", "sell"], entry_price: float, exit_price: float, pip_size: float) -> float:
    direction = 1 if side == "buy" else -1
    return round(((exit_price - entry_price) / pip_size) * direction, 2)


def _convert_pnl_to_usd(*, pnl: float, account_ccy: str, exit_price: float, base_ccy: str, quote_ccy: str) -> float:
    if account_ccy == "USD":
        return round(pnl, 2)
    if account_ccy == base_ccy and quote_ccy == "USD":
        return round(pnl * exit_price, 2)
    if account_ccy == quote_ccy and base_ccy == "USD":
        return round(pnl / exit_price, 2)
    raise NotImplementedError("USD conversion only supports base/quote relationships involving USD")


def _close_trade(
    position: _OpenPosition,
    *,
    exit_time: datetime,
    exit_price: float,
    execution_policy_name: str,
    spec: StrategySpec,
    ambiguity_detected: bool = False,
    spread_triggered_stop: bool = False,
    exit_reason: str,
) -> TradeRecord:
    pnl = _price_delta_to_pnl(
        side=position.side,
        entry_price=position.entry_price,
        exit_price=exit_price,
        quantity_units=position.quantity_units,
    )
    pnl_usd = _convert_pnl_to_usd(
        pnl=pnl,
        account_ccy=spec.risk.account_ccy,
        exit_price=exit_price,
        base_ccy=spec.instrument.base_ccy,
        quote_ccy=spec.instrument.quote_ccy,
    )
    return TradeRecord(
        trade_id=position.trade_id,
        symbol=spec.instrument.symbol,
        side=position.side,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        stop_loss_price=position.stop_loss_price,
        take_profit_price=position.take_profit_price,
        quantity_units=position.quantity_units,
        execution_policy_name=execution_policy_name,
        evidence_ref=position.evidence_ref,
        sessions=position.sessions,
        ambiguity_detected=ambiguity_detected,
        spread_triggered_stop=spread_triggered_stop,
        exit_reason=exit_reason,
        exit_time=exit_time,
        exit_price=exit_price,
        pnl=pnl,
        pnl_ccy=spec.risk.account_ccy,
        pnl_usd=pnl_usd,
        pnl_pips=_price_delta_to_pips(
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            pip_size=spec.instrument.pip_size,
        ),
    )


def _build_metrics(*, trades: list[TradeRecord], starting_equity: float, ending_equity: float) -> BacktestMetrics:
    gross_profit = round(sum((trade.pnl or 0.0) for trade in trades if (trade.pnl or 0.0) > 0), 2)
    gross_loss = round(sum((trade.pnl or 0.0) for trade in trades if (trade.pnl or 0.0) < 0), 2)
    gross_pips_won = round(sum((trade.pnl_pips or 0.0) for trade in trades if (trade.pnl_pips or 0.0) > 0), 2)
    gross_pips_lost = round(sum((trade.pnl_pips or 0.0) for trade in trades if (trade.pnl_pips or 0.0) < 0), 2)
    wins = [trade.pnl_pips or 0.0 for trade in trades if (trade.pnl_pips or 0.0) > 0]
    losses = [trade.pnl_pips or 0.0 for trade in trades if (trade.pnl_pips or 0.0) < 0]
    expectancy_pips = round(sum((trade.pnl_pips or 0.0) for trade in trades) / len(trades), 2) if trades else 0.0
    average_win_pips = round(sum(wins) / len(wins), 2) if wins else 0.0
    average_loss_pips = round(sum(losses) / len(losses), 2) if losses else 0.0
    ambiguity_count = sum(1 for trade in trades if trade.ambiguity_detected)
    spread_triggered_stop_count = sum(1 for trade in trades if trade.spread_triggered_stop)

    equity = starting_equity
    peak = equity
    peak_trade_index = 0
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    max_drawdown_duration_trades = 0
    for idx, trade in enumerate(trades, start=1):
        equity = round(equity + (trade.pnl or 0.0), 2)
        if equity > peak:
            peak = equity
            peak_trade_index = idx
        drawdown = round(peak - equity, 2)
        drawdown_pct = round((drawdown / peak) * 100, 4) if peak else 0.0
        duration = idx - peak_trade_index
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = drawdown_pct
            max_drawdown_duration_trades = duration

    session_summary: dict[str, dict[str, float | int]] = {}
    for trade in trades:
        for session in trade.sessions:
            bucket = session_summary.setdefault(session, {"trade_count": 0, "net_pnl": 0.0, "net_pips": 0.0})
            bucket["trade_count"] = int(bucket["trade_count"]) + 1
            bucket["net_pnl"] = round(float(bucket["net_pnl"]) + (trade.pnl or 0.0), 2)
            bucket["net_pips"] = round(float(bucket["net_pips"]) + (trade.pnl_pips or 0.0), 2)

    return BacktestMetrics(
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        gross_pips_won=gross_pips_won,
        gross_pips_lost=gross_pips_lost,
        net_pips=round(sum((trade.pnl_pips or 0.0) for trade in trades), 2),
        expectancy_pips=expectancy_pips,
        average_win_pips=average_win_pips,
        average_loss_pips=average_loss_pips,
        ambiguity_count=ambiguity_count,
        spread_triggered_stop_count=spread_triggered_stop_count,
        max_drawdown=round(max_drawdown, 2),
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown_duration_trades=max_drawdown_duration_trades,
        session_summary=session_summary,
    )


def run_backtest(*, bars: list[SignalBar], spec: StrategySpec, policy: ExecutionPolicy) -> BacktestResult:
    equity = spec.risk.initial_equity
    trades: list[TradeRecord] = []
    open_position: _OpenPosition | None = None
    pip_size = spec.instrument.pip_size
    trade_index = 0
    half_spread_delta = policy.half_spread_pips * pip_size

    for bar in bars:
        if open_position is not None:
            ambiguity = False
            spread_triggered_stop = False

            if open_position.side == "buy":
                stop_reachable = bar.low <= open_position.stop_loss_price + half_spread_delta
                tp_reachable = bar.high >= open_position.take_profit_price
                if stop_reachable and bar.low > open_position.stop_loss_price:
                    spread_triggered_stop = True
                if stop_reachable and tp_reachable:
                    ambiguity = True
                if stop_reachable:
                    requested_exit_price = bar.open if bar.open <= open_position.stop_loss_price else open_position.stop_loss_price
                    exit_fill = apply_execution_policy(side="sell", requested_price=requested_exit_price, policy=policy, pip_size=pip_size)
                    trade = _close_trade(open_position, exit_time=bar.timestamp, exit_price=exit_fill.executed_price, execution_policy_name=spec.execution_policy_name, spec=spec, ambiguity_detected=ambiguity, spread_triggered_stop=spread_triggered_stop, exit_reason="stop_loss")
                    trades.append(trade)
                    equity = round(equity + (trade.pnl or 0.0), 2)
                    open_position = None
                    continue
                if tp_reachable:
                    requested_exit_price = bar.open if bar.open >= open_position.take_profit_price else open_position.take_profit_price
                    exit_fill = apply_execution_policy(side="sell", requested_price=requested_exit_price, policy=policy, pip_size=pip_size)
                    trade = _close_trade(open_position, exit_time=bar.timestamp, exit_price=exit_fill.executed_price, execution_policy_name=spec.execution_policy_name, spec=spec, exit_reason="take_profit")
                    trades.append(trade)
                    equity = round(equity + (trade.pnl or 0.0), 2)
                    open_position = None
                    continue
                if bar.exit_long:
                    requested_exit_price = bar.execution_price or bar.close
                    exit_fill = apply_execution_policy(side="sell", requested_price=requested_exit_price, policy=policy, pip_size=pip_size)
                    trade = _close_trade(open_position, exit_time=bar.timestamp, exit_price=exit_fill.executed_price, execution_policy_name=spec.execution_policy_name, spec=spec, exit_reason="signal_exit")
                    trades.append(trade)
                    equity = round(equity + (trade.pnl or 0.0), 2)
                    open_position = None
                    continue
            else:
                stop_reachable = bar.high >= open_position.stop_loss_price - half_spread_delta
                tp_reachable = bar.low <= open_position.take_profit_price
                if stop_reachable and bar.high < open_position.stop_loss_price:
                    spread_triggered_stop = True
                if stop_reachable and tp_reachable:
                    ambiguity = True
                if stop_reachable:
                    requested_exit_price = bar.open if bar.open >= open_position.stop_loss_price else open_position.stop_loss_price
                    exit_fill = apply_execution_policy(side="buy", requested_price=requested_exit_price, policy=policy, pip_size=pip_size)
                    trade = _close_trade(open_position, exit_time=bar.timestamp, exit_price=exit_fill.executed_price, execution_policy_name=spec.execution_policy_name, spec=spec, ambiguity_detected=ambiguity, spread_triggered_stop=spread_triggered_stop, exit_reason="stop_loss")
                    trades.append(trade)
                    equity = round(equity + (trade.pnl or 0.0), 2)
                    open_position = None
                    continue
                if tp_reachable:
                    requested_exit_price = bar.open if bar.open <= open_position.take_profit_price else open_position.take_profit_price
                    exit_fill = apply_execution_policy(side="buy", requested_price=requested_exit_price, policy=policy, pip_size=pip_size)
                    trade = _close_trade(open_position, exit_time=bar.timestamp, exit_price=exit_fill.executed_price, execution_policy_name=spec.execution_policy_name, spec=spec, exit_reason="take_profit")
                    trades.append(trade)
                    equity = round(equity + (trade.pnl or 0.0), 2)
                    open_position = None
                    continue
                if bar.exit_short:
                    requested_exit_price = bar.execution_price or bar.close
                    exit_fill = apply_execution_policy(side="buy", requested_price=requested_exit_price, policy=policy, pip_size=pip_size)
                    trade = _close_trade(open_position, exit_time=bar.timestamp, exit_price=exit_fill.executed_price, execution_policy_name=spec.execution_policy_name, spec=spec, exit_reason="signal_exit")
                    trades.append(trade)
                    equity = round(equity + (trade.pnl or 0.0), 2)
                    open_position = None
                    continue

        if open_position is None and (bar.entry_long or bar.entry_short):
            trade_index += 1
            requested_entry_price = bar.execution_price or bar.close
            side: Literal["buy", "sell"] = "buy" if bar.entry_long else "sell"
            entry_fill = apply_execution_policy(side=side, requested_price=requested_entry_price, policy=policy, pip_size=pip_size)
            quantity_units = size_position_units(
                equity=equity,
                risk=spec.risk,
                instrument=spec.instrument,
                stop_loss_pips=spec.rules.stop_loss_pips,
                reference_price=entry_fill.executed_price,
            )
            evidence_ref = None
            if bar.signal_bar_timestamp is not None:
                evidence_ref = f"signal={bar.signal_bar_timestamp}|execution={bar.timestamp.isoformat()}"
            if side == "buy":
                stop_loss_price = round(entry_fill.executed_price - (spec.rules.stop_loss_pips * pip_size), 5)
                take_profit_price = round(entry_fill.executed_price + (spec.rules.take_profit_pips * pip_size), 5)
            else:
                stop_loss_price = round(entry_fill.executed_price + (spec.rules.stop_loss_pips * pip_size), 5)
                take_profit_price = round(entry_fill.executed_price - (spec.rules.take_profit_pips * pip_size), 5)
            open_position = _OpenPosition(
                trade_id=f"{spec.instrument.symbol.lower()}-{trade_index:04d}",
                side=side,
                entry_time=bar.timestamp,
                entry_price=entry_fill.executed_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                quantity_units=quantity_units,
                evidence_ref=evidence_ref,
                sessions=bar.sessions,
            )

    ending_equity = round(equity, 2)
    ending_equity_usd = _convert_pnl_to_usd(
        pnl=ending_equity,
        account_ccy=spec.risk.account_ccy,
        exit_price=bars[-1].close if bars else 1.0,
        base_ccy=spec.instrument.base_ccy,
        quote_ccy=spec.instrument.quote_ccy,
    )
    return BacktestResult(
        starting_equity=spec.risk.initial_equity,
        ending_equity=ending_equity,
        ending_equity_usd=ending_equity_usd,
        trade_count=len(trades),
        trades=trades,
        metrics=_build_metrics(trades=trades, starting_equity=spec.risk.initial_equity, ending_equity=ending_equity),
    )
