from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MarketBar(BaseModel):
    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    timezone_normalized_to_utc: bool = True
    sessions: list[Literal["asia", "london", "new_york", "rth"]] = Field(default_factory=list)
