"""Deterministic FX position sizing helpers."""

from __future__ import annotations

from math import floor

from fx_backtester.formalizer.spec_models import InstrumentSpec, RiskSpec


def pip_value_usd_per_standard_lot(instrument: InstrumentSpec) -> float:
    """Return pip value in USD for one standard lot.

    For EUR/USD, 1 pip on 100,000 units is 10 USD.
    """

    if instrument.symbol != "EURUSD":
        raise NotImplementedError("v0.1 only supports EURUSD")
    return instrument.pip_size * instrument.lot_size_units


def size_position_units(
    equity_usd: float,
    risk: RiskSpec,
    instrument: InstrumentSpec,
    stop_loss_pips: float,
) -> int:
    """Size a position in units using fixed-fraction risk.

    Rounded down to whole units for determinism.
    """

    if stop_loss_pips <= 0:
        raise ValueError("stop_loss_pips must be positive")

    risk_dollars = equity_usd * risk.risk_per_trade_fraction
    pip_value_per_lot = pip_value_usd_per_standard_lot(instrument)
    loss_per_standard_lot = stop_loss_pips * pip_value_per_lot
    lots = risk_dollars / loss_per_standard_lot
    units = floor(lots * instrument.lot_size_units)
    return max(units, 0)
