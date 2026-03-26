"""Pydantic contracts for strategy and run specifications.

Lean v0.4 expansion:
- explicit trade direction and session restrictions
- explicit spread/slippage model naming on the execution policy side
- account currency stays in risk spec
- minimal stop/take-profit style controls
- small parameter-variant hooks for robustness-lite runs
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TradeDirection = Literal["long_only", "short_only", "both"]
SessionName = Literal["asia", "london", "new_york"]
StopTakeProfitStyle = Literal["fixed_pips", "disabled"]


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
    """Minimal example rule set for deterministic RSI mean reversion."""

    timeframe: Literal["H1"] = "H1"
    direction: TradeDirection = "long_only"
    allowed_sessions: list[SessionName] = Field(default_factory=list)
    rsi_period: int = Field(default=14, ge=2, le=100)
    entry_rsi_lte: float = Field(default=30.0, ge=0, le=100)
    short_entry_rsi_gte: float = Field(default=70.0, ge=0, le=100)
    exit_rsi_gte: float = Field(default=55.0, ge=0, le=100)
    short_exit_rsi_lte: float = Field(default=45.0, ge=0, le=100)
    stop_loss_style: StopTakeProfitStyle = "fixed_pips"
    stop_loss_pips: float = Field(..., gt=0)
    take_profit_style: StopTakeProfitStyle = "fixed_pips"
    take_profit_pips: float = Field(..., gt=0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "RsiMeanReversionRule":
        if self.entry_rsi_lte >= self.exit_rsi_gte:
            raise ValueError("entry_rsi_lte must be below exit_rsi_gte")
        if self.short_entry_rsi_gte <= self.short_exit_rsi_lte:
            raise ValueError("short_entry_rsi_gte must be above short_exit_rsi_lte")
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
