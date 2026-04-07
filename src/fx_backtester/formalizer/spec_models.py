"""Pydantic contracts for strategy and run specifications.

Lean v0.9 expansion:
- explicit trade direction and session restrictions
- deterministic time-stop and session-close controls
- fixed-pip or ATR-based initial stop-loss support
- take-profit style stays intentionally narrow
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TradeDirection = Literal["long_only", "short_only", "both"]
SessionName = Literal["asia", "london", "new_york"]
StopLossStyle = Literal["fixed_pips", "atr", "disabled"]
TakeProfitStyle = Literal["fixed_pips", "disabled"]
StrategyType = Literal["rsi_mean_reversion", "breakout", "ema_crossover", "vwap_reversion", "orb", "bollinger_band"]


class InstrumentSpec(BaseModel):
    """Instrument-level trading conventions for the backtest."""

    symbol: str = "EURUSD"
    quote_ccy: str = "USD"
    base_ccy: str = "EUR"
    pip_size: float = Field(default=0.0001, gt=0)
    lot_size_units: int = Field(default=100_000, gt=0)


class RiskSpec(BaseModel):
    """Simple fixed-fraction risk model for deterministic backtests."""

    account_ccy: str = "USD"
    initial_equity: float = Field(..., gt=0)
    risk_per_trade_fraction: float = Field(..., gt=0, le=0.05)
    max_open_positions: int = Field(default=1, ge=1, le=1)


class RobustnessSpec(BaseModel):
    """Small deterministic robustness sweep controls."""

    enabled: bool = False
    spread_multipliers: list[float] = Field(default_factory=lambda: [1.0, 1.5, 2.0])
    slippage_modes: list[Literal["base", "worse"]] = Field(default_factory=lambda: ["base", "worse"])
    rsi_period_variants: list[int] = Field(default_factory=lambda: [-1, 0, 1])

    @model_validator(mode="after")
    def validate_values(self) -> "RobustnessSpec":
        if any(multiplier <= 0 for multiplier in self.spread_multipliers):
            raise ValueError("spread_multipliers must be > 0")
        if len(set(self.rsi_period_variants)) != len(self.rsi_period_variants):
            raise ValueError("rsi_period_variants must be unique")
        return self


class RsiMeanReversionRule(BaseModel):
    """Minimal deterministic rule contract for frozen v1/v1.1 strategies."""

    strategy_type: StrategyType = "rsi_mean_reversion"
    timeframe: Literal["H1"] = "H1"
    direction: TradeDirection = "long_only"
    allowed_sessions: list[SessionName] = Field(default_factory=list)
    rsi_period: int | None = Field(default=14, ge=2, le=100)
    entry_rsi_lte: float | None = Field(default=30.0, ge=0, le=100)
    short_entry_rsi_gte: float | None = Field(default=70.0, ge=0, le=100)
    exit_rsi_gte: float | None = Field(default=55.0, ge=0, le=100)
    short_exit_rsi_lte: float | None = Field(default=45.0, ge=0, le=100)
    breakout_lookback_bars: int | None = Field(default=None, ge=2, le=500)
    breakout_buffer_pips: float | None = Field(default=None, ge=0, le=1000)
    time_stop_bars: int | None = Field(default=None, ge=1, le=500)
    exit_on_session_close: bool = False
    stop_loss_style: StopLossStyle = "fixed_pips"
    stop_loss_pips: float = Field(default=20.0, gt=0)
    stop_loss_atr_period: int = Field(default=14, ge=2, le=100)
    stop_loss_atr_multiplier: float = Field(default=2.0, gt=0, le=20)
    take_profit_style: TakeProfitStyle = "fixed_pips"
    take_profit_pips: float = Field(default=30.0, gt=0)
    trailing_stop_style: Literal["disabled"] = "disabled"
    require_daily_trend: bool = False
    daily_sma_period: int = Field(default=20, ge=2, le=200)

    # EMA crossover fields
    ema_fast_period: int | None = Field(default=9, ge=2, le=200)
    ema_slow_period: int | None = Field(default=21, ge=2, le=500)

    # VWAP reversion fields
    vwap_deviation_pct: float | None = Field(default=0.3, ge=0.01, le=5.0)

    # Opening Range Breakout fields
    orb_session: str = "new_york"
    orb_range_bars: int = Field(default=1, ge=1, le=6)

    # Bollinger Band fields
    bb_period: int | None = Field(default=20, ge=5, le=200)
    bb_std_dev: float | None = Field(default=2.0, ge=0.5, le=4.0)

    @model_validator(mode="after")
    def validate_strategy_specific_fields(self) -> "RsiMeanReversionRule":
        if self.exit_on_session_close and not self.allowed_sessions:
            raise ValueError("exit_on_session_close requires at least one allowed session")

        if self.strategy_type == "rsi_mean_reversion":
            required_rsi_fields = {
                "rsi_period": self.rsi_period,
                "entry_rsi_lte": self.entry_rsi_lte,
                "short_entry_rsi_gte": self.short_entry_rsi_gte,
                "exit_rsi_gte": self.exit_rsi_gte,
                "short_exit_rsi_lte": self.short_exit_rsi_lte,
            }
            missing = [name for name, value in required_rsi_fields.items() if value is None]
            if missing:
                raise ValueError(f"rsi_mean_reversion requires fields: {', '.join(missing)}")
            if self.entry_rsi_lte >= self.exit_rsi_gte:
                raise ValueError("entry_rsi_lte must be below exit_rsi_gte")
            if self.short_entry_rsi_gte <= self.short_exit_rsi_lte:
                raise ValueError("short_entry_rsi_gte must be above short_exit_rsi_lte")

        if self.strategy_type == "breakout":
            missing = [
                name
                for name, value in {
                    "breakout_lookback_bars": self.breakout_lookback_bars,
                    "breakout_buffer_pips": self.breakout_buffer_pips,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(f"breakout requires fields: {', '.join(missing)}")

        if self.strategy_type == "ema_crossover":
            missing = [
                name
                for name, value in {
                    "ema_fast_period": self.ema_fast_period,
                    "ema_slow_period": self.ema_slow_period,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(f"ema_crossover requires fields: {', '.join(missing)}")
            if self.ema_fast_period is not None and self.ema_slow_period is not None:
                if self.ema_fast_period >= self.ema_slow_period:
                    raise ValueError("ema_fast_period must be less than ema_slow_period")

        if self.strategy_type == "vwap_reversion":
            if self.vwap_deviation_pct is None:
                raise ValueError("vwap_reversion requires vwap_deviation_pct")

        if self.strategy_type == "bollinger_band":
            missing = [
                name
                for name, value in {
                    "bb_period": self.bb_period,
                    "bb_std_dev": self.bb_std_dev,
                }.items()
                if value is None
            ]
            if missing:
                raise ValueError(f"bollinger_band requires fields: {', '.join(missing)}")

        return self


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
    rules: RsiMeanReversionRule
    window: BacktestWindow
    execution_policy_name: str = Field(default="default_v0_1")
    robustness: RobustnessSpec = Field(default_factory=RobustnessSpec)
    notes: str | None = None
