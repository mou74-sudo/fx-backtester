from __future__ import annotations

from pydantic import BaseModel, Field

from fx_backtester.data.indicators import compute_wilder_atr, compute_wilder_rsi
from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import SignalBar
from fx_backtester.formalizer.spec_models import StrategySpec


class SignalTraceRow(BaseModel):
    signal_bar_timestamp: str
    execution_bar_timestamp: str | None = None
    signal_bar_close: float = Field(..., gt=0)
    execution_bar_open: float | None = Field(default=None, gt=0)
    rsi: float | None = None
    atr: float | None = None
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


def _empty_state() -> dict[str, object]:
    return {
        "pending_entry_long": False,
        "pending_exit_long": False,
        "pending_entry_short": False,
        "pending_exit_short": False,
        "pending_signal_timestamp": None,
        "pending_signal_rsi": None,
        "pending_signal_atr": None,
    }


def _append_signal_bar(*, prepared_bars: list[SignalBar], bar: MarketBar, state: dict[str, object]) -> None:
    prepared_bars.append(
        SignalBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            entry_long=bool(state["pending_entry_long"]),
            exit_long=bool(state["pending_exit_long"]),
            entry_short=bool(state["pending_entry_short"]),
            exit_short=bool(state["pending_exit_short"]),
            signal_bar_timestamp=state["pending_signal_timestamp"],
            execution_price=bar.open if any(bool(state[key]) for key in ("pending_entry_long", "pending_exit_long", "pending_entry_short", "pending_exit_short")) else None,
            signal_rsi=state["pending_signal_rsi"],
            atr=state["pending_signal_atr"],
            sessions=bar.sessions,
        )
    )


def _finalize_pending_state(*, idx: int, market_bars: list[MarketBar], state: dict[str, object], next_entry_long: bool, next_exit_long: bool, next_entry_short: bool, next_exit_short: bool, signal_timestamp: str, signal_rsi: float | None, signal_atr: float | None) -> None:
    executable = idx + 1 < len(market_bars)
    state["pending_entry_long"] = next_entry_long and executable
    state["pending_exit_long"] = next_exit_long and executable
    state["pending_entry_short"] = next_entry_short and executable
    state["pending_exit_short"] = next_exit_short and executable
    has_signal = any(bool(state[key]) for key in ("pending_entry_long", "pending_exit_long", "pending_entry_short", "pending_exit_short"))
    state["pending_signal_timestamp"] = signal_timestamp if has_signal else None
    state["pending_signal_rsi"] = signal_rsi if has_signal else None
    state["pending_signal_atr"] = signal_atr if has_signal else None


def build_rsi_signal_pipeline(*, market_bars: list[MarketBar], spec: StrategySpec) -> PreparedSignalData:
    closes = [bar.close for bar in market_bars]
    highs = [bar.high for bar in market_bars]
    lows = [bar.low for bar in market_bars]
    rsis = compute_wilder_rsi(closes, spec.rules.rsi_period or 14)
    atrs = compute_wilder_atr(highs, lows, closes, spec.rules.stop_loss_atr_period)
    prepared_bars: list[SignalBar] = []
    trace: list[SignalTraceRow] = []
    state = _empty_state()

    for idx, bar in enumerate(market_bars):
        _append_signal_bar(prepared_bars=prepared_bars, bar=bar, state=state)

        rsi = rsis[idx]
        atr = atrs[idx]
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
                atr=atr,
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
                    f"atr={atr}",
                    "entry/exit evaluated from current close and scheduled onto next bar open",
                ],
            )
        )

        _finalize_pending_state(
            idx=idx,
            market_bars=market_bars,
            state=state,
            next_entry_long=next_entry_long,
            next_exit_long=next_exit_long,
            next_entry_short=next_entry_short,
            next_exit_short=next_exit_short,
            signal_timestamp=bar.timestamp.isoformat(),
            signal_rsi=rsi,
            signal_atr=atr,
        )

    return PreparedSignalData(bars=prepared_bars, signal_trace=trace)


def build_breakout_signal_pipeline(*, market_bars: list[MarketBar], spec: StrategySpec) -> PreparedSignalData:
    closes = [bar.close for bar in market_bars]
    highs = [bar.high for bar in market_bars]
    lows = [bar.low for bar in market_bars]
    atrs = compute_wilder_atr(highs, lows, closes, spec.rules.stop_loss_atr_period)
    prepared_bars: list[SignalBar] = []
    trace: list[SignalTraceRow] = []
    state = _empty_state()
    direction = spec.rules.direction
    lookback = spec.rules.breakout_lookback_bars or 0
    buffer_price = (spec.rules.breakout_buffer_pips or 0.0) * spec.instrument.pip_size

    for idx, bar in enumerate(market_bars):
        _append_signal_bar(prepared_bars=prepared_bars, bar=bar, state=state)

        atr = atrs[idx]
        session_allowed = _session_allowed(bar, spec)
        prior_high = max(highs[idx - lookback:idx]) if idx >= lookback else None
        prior_low = min(lows[idx - lookback:idx]) if idx >= lookback else None
        next_entry_long = (
            prior_high is not None
            and bar.close > prior_high + buffer_price
            and direction in {"long_only", "both"}
            and session_allowed
        )
        next_entry_short = (
            prior_low is not None
            and bar.close < prior_low - buffer_price
            and direction in {"short_only", "both"}
            and session_allowed
        )
        next_exit_long = False
        next_exit_short = False
        execution_bar_timestamp = market_bars[idx + 1].timestamp.isoformat() if idx + 1 < len(market_bars) else None
        execution_bar_open = market_bars[idx + 1].open if idx + 1 < len(market_bars) else None
        trace.append(
            SignalTraceRow(
                signal_bar_timestamp=bar.timestamp.isoformat(),
                execution_bar_timestamp=execution_bar_timestamp,
                signal_bar_close=bar.close,
                execution_bar_open=execution_bar_open,
                rsi=None,
                atr=atr,
                sessions=bar.sessions,
                entry_signal=next_entry_long,
                exit_signal=False,
                short_entry_signal=next_entry_short,
                short_exit_signal=False,
                executable_on_next_bar=idx + 1 < len(market_bars),
                no_leakage_ok=(execution_bar_timestamp is None or execution_bar_timestamp > bar.timestamp.isoformat()),
                session_allowed=session_allowed,
                evidence=[
                    f"signal_bar={bar.timestamp.isoformat()}",
                    f"execution_bar={execution_bar_timestamp}",
                    f"session_allowed={session_allowed}",
                    f"atr={atr}",
                    f"breakout_lookback_bars={lookback}",
                    f"breakout_buffer_pips={spec.rules.breakout_buffer_pips}",
                    f"prior_high={prior_high}",
                    f"prior_low={prior_low}",
                    "breakout threshold uses prior completed bars only and schedules execution on next bar open",
                ],
            )
        )

        _finalize_pending_state(
            idx=idx,
            market_bars=market_bars,
            state=state,
            next_entry_long=next_entry_long,
            next_exit_long=next_exit_long,
            next_entry_short=next_entry_short,
            next_exit_short=next_exit_short,
            signal_timestamp=bar.timestamp.isoformat(),
            signal_rsi=None,
            signal_atr=atr,
        )

    return PreparedSignalData(bars=prepared_bars, signal_trace=trace)


def build_signal_pipeline(*, market_bars: list[MarketBar], spec: StrategySpec) -> PreparedSignalData:
    if spec.rules.strategy_type == "breakout":
        return build_breakout_signal_pipeline(market_bars=market_bars, spec=spec)
    return build_rsi_signal_pipeline(market_bars=market_bars, spec=spec)
