"""Pydantic contracts for strategy and run specifications."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, model_validator

TradeDirection = Literal["long_only", "short_only", "both"]
SessionName    = Literal["asia", "london", "new_york", "rth", "eth"]
StopLossStyle  = Literal["fixed_pips", "atr", "disabled"]
TakeProfitStyle = Literal["fixed_pips", "disabled"]
StrategyType   = Literal["rsi_mean_reversion", "breakout", "ema_crossover", "vwap_reversion", "orb", "bollinger_band"]


# ── Shared infrastructure ──────────────────────────────────────────────────────

class InstrumentSpec(BaseModel):
    symbol: str = "EURUSD"
    quote_ccy: str = "USD"
    base_ccy: str = "EUR"
    pip_size: float = Field(default=0.0001, gt=0)
    lot_size_units: int = Field(default=100_000, gt=0)


class RiskSpec(BaseModel):
    account_ccy: str = "USD"
    initial_equity: float = Field(..., gt=0)
    risk_per_trade_fraction: float = Field(..., gt=0, le=0.05)
    max_open_positions: int = Field(default=1, ge=1, le=1)


class RobustnessSpec(BaseModel):
    enabled: bool = False
    spread_multipliers: list[float] = Field(default_factory=lambda: [1.0, 1.5, 2.0])
    slippage_modes: list[Literal["base", "worse"]] = Field(default_factory=lambda: ["base", "worse"])
    rsi_period_variants: list[int] = Field(default_factory=lambda: [-1, 0, 1])

    @model_validator(mode="after")
    def validate_values(self) -> "RobustnessSpec":
        if any(m <= 0 for m in self.spread_multipliers):
            raise ValueError("spread_multipliers must be > 0")
        if len(set(self.rsi_period_variants)) != len(self.rsi_period_variants):
            raise ValueError("rsi_period_variants must be unique")
        return self


# ── Base rule — fields shared by every strategy ────────────────────────────────

class _BaseRule(BaseModel):
    timeframe: Literal["5m", "15m", "30m", "H1", "4H", "D1"] = "H1"
    direction: TradeDirection = "long_only"
    allowed_sessions: list[SessionName] = Field(default_factory=list)
    time_stop_bars: int | None = Field(default=None, ge=1, le=500)
    exit_on_session_close: bool = False
    stop_loss_style: StopLossStyle = "fixed_pips"
    stop_loss_pips: float = Field(default=20.0, gt=0)
    stop_loss_atr_period: int = Field(default=14, ge=2, le=100)
    stop_loss_atr_multiplier: float = Field(default=2.0, gt=0, le=20)
    take_profit_style: TakeProfitStyle = "fixed_pips"
    take_profit_pips: float = Field(default=30.0, gt=0)
    trailing_stop_style: Literal["disabled", "atr", "fixed_pips"] = "disabled"
    trailing_stop_atr_multiplier: float = Field(default=1.5, gt=0, le=10)
    trailing_stop_pips: float = Field(default=20.0, gt=0)
    require_daily_trend: bool = False
    daily_sma_period: int = Field(default=20, ge=2, le=200)

    @model_validator(mode="after")
    def _validate_common(self) -> "_BaseRule":
        if self.exit_on_session_close and not self.allowed_sessions:
            raise ValueError("exit_on_session_close requires at least one allowed session")
        return self


# ── Strategy-specific rule models ─────────────────────────────────────────────

class RsiMeanReversionRule(_BaseRule):
    """RSI mean-reversion: enter when RSI is oversold/overbought."""
    strategy_type: Literal["rsi_mean_reversion"] = "rsi_mean_reversion"
    rsi_period: int = Field(default=14, ge=2, le=100)
    entry_rsi_lte: float = Field(default=30.0, ge=0, le=100)
    short_entry_rsi_gte: float = Field(default=70.0, ge=0, le=100)
    exit_rsi_gte: float = Field(default=55.0, ge=0, le=100)
    short_exit_rsi_lte: float = Field(default=45.0, ge=0, le=100)

    @model_validator(mode="after")
    def _validate_rsi(self) -> "RsiMeanReversionRule":
        if self.entry_rsi_lte >= self.exit_rsi_gte:
            raise ValueError("entry_rsi_lte must be below exit_rsi_gte")
        if self.short_entry_rsi_gte <= self.short_exit_rsi_lte:
            raise ValueError("short_entry_rsi_gte must be above short_exit_rsi_lte")
        return self


class BreakoutRule(_BaseRule):
    """N-bar high/low breakout with optional pip buffer."""
    strategy_type: Literal["breakout"] = "breakout"
    breakout_lookback_bars: int = Field(default=20, ge=2, le=500)
    breakout_buffer_pips: float = Field(default=2.0, ge=0, le=1000)


class EmaCrossoverRule(_BaseRule):
    """Enter on fast EMA crossing above/below slow EMA."""
    strategy_type: Literal["ema_crossover"] = "ema_crossover"
    ema_fast_period: int = Field(default=9, ge=2, le=200)
    ema_slow_period: int = Field(default=21, ge=2, le=500)

    @model_validator(mode="after")
    def _validate_ema(self) -> "EmaCrossoverRule":
        if self.ema_fast_period >= self.ema_slow_period:
            raise ValueError("ema_fast_period must be less than ema_slow_period")
        return self


class VwapReversionRule(_BaseRule):
    """Fade extremes when price deviates from intraday typical-price MA."""
    strategy_type: Literal["vwap_reversion"] = "vwap_reversion"
    vwap_deviation_pct: float = Field(default=0.3, ge=0.01, le=5.0)


class OrbRule(_BaseRule):
    """Opening Range Breakout: enter on break of first N session bars."""
    strategy_type: Literal["orb"] = "orb"
    orb_session: SessionName = "rth"
    orb_range_bars: int = Field(default=1, ge=1, le=6)


class BollingerBandRule(_BaseRule):
    """Mean revert from Bollinger Band extremes back to the middle band."""
    strategy_type: Literal["bollinger_band"] = "bollinger_band"
    bb_period: int = Field(default=20, ge=5, le=200)
    bb_std_dev: float = Field(default=2.0, ge=0.5, le=4.0)


# ── Discriminated union ────────────────────────────────────────────────────────

StrategyRule = Annotated[
    Union[
        RsiMeanReversionRule,
        BreakoutRule,
        EmaCrossoverRule,
        VwapReversionRule,
        OrbRule,
        BollingerBandRule,
    ],
    Field(discriminator="strategy_type"),
]

# TypeAdapter for deserialising a rule from a plain dict (use instead of
# RsiMeanReversionRule.model_validate when the strategy_type is unknown)
StrategyRuleAdapter: TypeAdapter[StrategyRule] = TypeAdapter(StrategyRule)


# ── Root spec ─────────────────────────────────────────────────────────────────

class BacktestWindow(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestWindow":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class StrategySpec(BaseModel):
    """Root contract for a single deterministic backtest run."""

    strategy_name: str = Field(..., min_length=3)
    instrument: InstrumentSpec = Field(default_factory=InstrumentSpec)
    risk: RiskSpec
    rules: StrategyRule
    window: BacktestWindow
    execution_policy_name: str = Field(default="default_v0_1")
    robustness: RobustnessSpec = Field(default_factory=RobustnessSpec)
    notes: str | None = None
