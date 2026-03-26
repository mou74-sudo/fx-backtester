"""Deterministic execution semantics for v0.1 backtests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.formalizer.execution_policy import ExecutionPolicy


class FillResult(BaseModel):
    side: Literal["buy", "sell"]
    requested_price: float = Field(..., gt=0)
    executed_price: float = Field(..., gt=0)
    spread_cost_pips: float = Field(..., ge=0)
    slippage_pips: float = Field(..., ge=0)


def apply_execution_policy(
    *,
    side: Literal["buy", "sell"],
    requested_price: float,
    policy: ExecutionPolicy,
    pip_size: float,
) -> FillResult:
    """Apply explicit spread/slippage assumptions to a requested fill price."""

    spread_delta = policy.half_spread_pips * pip_size
    slippage_delta = policy.slippage_pips * pip_size

    if side == "buy":
        executed_price = requested_price + spread_delta + slippage_delta
    else:
        executed_price = requested_price - spread_delta - slippage_delta

    executed_price = round(executed_price, 5)

    return FillResult(
        side=side,
        requested_price=requested_price,
        executed_price=executed_price,
        spread_cost_pips=policy.half_spread_pips,
        slippage_pips=policy.slippage_pips,
    )
