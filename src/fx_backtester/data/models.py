from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

# All valid session tag values — FX sessions + CME futures sessions (rth/eth).
# Kept as plain str to avoid Pydantic strict-mode failures when deserialising
# bars that were tagged by infer_futures_sessions().
_SESSION_TAG = str


class MarketBar(BaseModel):
    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    timezone_normalized_to_utc: bool = True
    sessions: list[_SESSION_TAG] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_ohlc(self) -> "MarketBar":
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) < low ({self.low}) — corrupt bar data")
        return self
