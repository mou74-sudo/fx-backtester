from __future__ import annotations

from pydantic import BaseModel, Field

from fx_backtester.data.indicators import compute_wilder_rsi
from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import SignalBar
from fx_backtester.formalizer.spec_models import StrategySpec


class SignalTraceRow(BaseModel):
    signal_bar_timestamp: str
    execution_bar_timestamp: str | None = None
    signal_bar_close: float = Field(..., gt=0)
    execution_bar_open: float | None = Field(default=None, gt=0)
    rsi: float | None = None
    sessions: list[str] = Field(default_factory=list)
    entry_signal: bool = False
    exit_signal: bool = False
    executable_on_next_bar: bool = False
    no_leakage_ok: bool = True
    evidence: list[str] = Field(default_factory=list)


class PreparedSignalData(BaseModel):
    bars: list[SignalBar]
    signal_trace: list[SignalTraceRow]


def build_rsi_signal_pipeline(*, market_bars: list[MarketBar], spec: StrategySpec) -> PreparedSignalData:
    closes = [bar.close for bar in market_bars]
    rsis = compute_wilder_rsi(closes, spec.rules.rsi_period)
    prepared_bars: list[SignalBar] = []
    trace: list[SignalTraceRow] = []

    pending_entry = False
    pending_exit = False
    pending_signal_timestamp: str | None = None
    pending_signal_rsi: float | None = None

    for idx, bar in enumerate(market_bars):
        signal_bar = SignalBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            entry_long=pending_entry,
            exit_long=pending_exit,
            signal_bar_timestamp=pending_signal_timestamp,
            execution_price=bar.open if (pending_entry or pending_exit) else None,
            signal_rsi=pending_signal_rsi,
            sessions=bar.sessions,
        )
        prepared_bars.append(signal_bar)

        rsi = rsis[idx]
        next_entry = rsi is not None and rsi <= spec.rules.entry_rsi_lte
        next_exit = rsi is not None and rsi >= spec.rules.exit_rsi_gte
        execution_bar_timestamp = market_bars[idx + 1].timestamp.isoformat() if idx + 1 < len(market_bars) else None
        execution_bar_open = market_bars[idx + 1].open if idx + 1 < len(market_bars) else None
        trace.append(
            SignalTraceRow(
                signal_bar_timestamp=bar.timestamp.isoformat(),
                execution_bar_timestamp=execution_bar_timestamp,
                signal_bar_close=bar.close,
                execution_bar_open=execution_bar_open,
                rsi=rsi,
                sessions=bar.sessions,
                entry_signal=next_entry,
                exit_signal=next_exit,
                executable_on_next_bar=idx + 1 < len(market_bars),
                no_leakage_ok=(execution_bar_timestamp is None or execution_bar_timestamp > bar.timestamp.isoformat()),
                evidence=[
                    f"signal_bar={bar.timestamp.isoformat()}",
                    f"execution_bar={execution_bar_timestamp}",
                    "entry/exit evaluated from current close and scheduled onto next bar open",
                ],
            )
        )

        pending_entry = next_entry and idx + 1 < len(market_bars)
        pending_exit = next_exit and idx + 1 < len(market_bars)
        pending_signal_timestamp = bar.timestamp.isoformat() if (pending_entry or pending_exit) else None
        pending_signal_rsi = rsi if (pending_entry or pending_exit) else None

    return PreparedSignalData(bars=prepared_bars, signal_trace=trace)
