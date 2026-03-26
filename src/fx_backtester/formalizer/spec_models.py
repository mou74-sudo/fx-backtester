"""Pydantic contracts for strategy and run specifications.

These models stay deliberately lean, but v0.3 broadens instrument/account
coverage enough to support deterministic known-answer tests for JPY pairs and
non-quote-currency accounts.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class RsiMeanReversionRule(BaseModel):
    """Minimal example rule set for EUR/USD RSI mean reversion."""

    timeframe: Literal["H1"] = "H1"
    rsi_period: int = Field(default=14, ge=2, le=100)
    entry_rsi_lte: float = Field(default=30.0, ge=0, le=100)
    exit_rsi_gte: float = Field(default=55.0, ge=0, le=100)
    stop_loss_pips: float = Field(..., gt=0)
    take_profit_pips: float = Field(..., gt=0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "RsiMeanReversionRule":
        if self.entry_rsi_lte >= self.exit_rsi_gte:
            raise ValueError("entry_rsi_lte must be below exit_rsi_gte")
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
    notes: str | None = None
