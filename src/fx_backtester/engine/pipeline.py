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
    short_entry_signal: bool = False
    short_exit_signal: bool = False
    executable_on_next_bar: bool = False
    no_leakage_ok: bool = True
    session_allowed: bool = True
    evidence: list[str] = Field(default_factory=list)


class PreparedSignalData(BaseModel):
    bars: list[SignalBar]
    signal_trace: list[SignalTraceRow]



def _session_allowed(bar: MarketBar, spec: StrategySpec) -> bool:
    if not spec.rules.allowed_sessions:
        return True
    return any(session in spec.rules.allowed_sessions for session in bar.sessions)



def build_rsi_signal_pipeline(*, market_bars: list[MarketBar], spec: StrategySpec) -> PreparedSignalData:
    closes = [bar.close for bar in market_bars]
    rsis = compute_wilder_rsi(closes, spec.rules.rsi_period)
    prepared_bars: list[SignalBar] = []
    trace: list[SignalTraceRow] = []

    pending_entry_long = False
    pending_exit_long = False
    pending_entry_short = False
    pending_exit_short = False
    pending_signal_timestamp: str | None = None
    pending_signal_rsi: float | None = None

    for idx, bar in enumerate(market_bars):
        signal_bar = SignalBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            entry_long=pending_entry_long,
            exit_long=pending_exit_long,
            entry_short=pending_entry_short,
            exit_short=pending_exit_short,
            signal_bar_timestamp=pending_signal_timestamp,
            execution_price=bar.open if (pending_entry_long or pending_exit_long or pending_entry_short or pending_exit_short) else None,
            signal_rsi=pending_signal_rsi,
            sessions=bar.sessions,
        )
        prepared_bars.append(signal_bar)

        rsi = rsis[idx]
        session_allowed = _session_allowed(bar, spec)
        direction = spec.rules.direction
        next_entry_long = rsi is not None and rsi <= spec.rules.entry_rsi_lte and direction in {"long_only", "both"} and session_allowed
        next_exit_long = rsi is not None and rsi >= spec.rules.exit_rsi_gte and direction in {"long_only", "both"}
        next_entry_short = rsi is not None and rsi >= spec.rules.short_entry_rsi_gte and direction in {"short_only", "both"} and session_allowed
        next_exit_short = rsi is not None and rsi <= spec.rules.short_exit_rsi_lte and direction in {"short_only", "both"}
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
                entry_signal=next_entry_long,
                exit_signal=next_exit_long,
                short_entry_signal=next_entry_short,
                short_exit_signal=next_exit_short,
                executable_on_next_bar=idx + 1 < len(market_bars),
                no_leakage_ok=(execution_bar_timestamp is None or execution_bar_timestamp > bar.timestamp.isoformat()),
                session_allowed=session_allowed,
                evidence=[
                    f"signal_bar={bar.timestamp.isoformat()}",
                    f"execution_bar={execution_bar_timestamp}",
                    f"session_allowed={session_allowed}",
                    "entry/exit evaluated from current close and scheduled onto next bar open",
                ],
            )
        )

        pending_entry_long = next_entry_long and idx + 1 < len(market_bars)
        pending_exit_long = next_exit_long and idx + 1 < len(market_bars)
        pending_entry_short = next_entry_short and idx + 1 < len(market_bars)
        pending_exit_short = next_exit_short and idx + 1 < len(market_bars)
        pending_signal_timestamp = bar.timestamp.isoformat() if (pending_entry_long or pending_exit_long or pending_entry_short or pending_exit_short) else None
        pending_signal_rsi = rsi if (pending_entry_long or pending_exit_long or pending_entry_short or pending_exit_short) else None

    return PreparedSignalData(bars=prepared_bars, signal_trace=trace)
