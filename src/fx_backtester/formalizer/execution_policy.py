"""Explicit execution assumptions for deterministic simulation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionPolicy(BaseModel):
    """Deterministic fill and cost assumptions.

    This is intentionally small. The point is to force assumptions into a model
    rather than bury them in engine code.
    """

    name: str = "default_v0_1"
    fill_on_signal_bar_close: bool = True
    allow_intrabar_tp_sl_resolution: bool = False
    half_spread_pips: float = Field(default=0.1, ge=0)
    commission_per_million_usd: float = Field(default=0.0, ge=0)
    slippage_pips: float = Field(default=0.0, ge=0)
    notes: str = (
        "Signals are filled deterministically at bar close with fixed spread and "
        "optional slippage assumptions. No probabilistic queueing or live routing."
    )


def default_execution_policy() -> ExecutionPolicy:
    """Return the default execution assumptions for the starter scaffold."""

    return ExecutionPolicy()
