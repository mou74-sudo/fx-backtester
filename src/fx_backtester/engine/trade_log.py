"""Trade log models for audit-friendly outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TradeRecord(BaseModel):
    trade_id: str
    symbol: str = "EURUSD"
    side: Literal["buy", "sell"]
    entry_time: datetime
    entry_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    quantity_units: int = Field(..., gt=0)
    execution_policy_name: str
    evidence_ref: str | None = None
    sessions: list[str] = Field(default_factory=list)
    ambiguity_detected: bool = False
    spread_triggered_stop: bool = False
    exit_reason: str | None = None
    exit_time: datetime | None = None
    exit_price: float | None = Field(default=None, gt=0)
    pnl: float | None = None
    pnl_ccy: str | None = None
    pnl_usd: float | None = None
    pnl_pips: float | None = None
