"""Deterministic FX position sizing helpers."""

from __future__ import annotations

from math import floor

from fx_backtester.formalizer.spec_models import InstrumentSpec, RiskSpec


def pip_value_per_standard_lot(
    instrument: InstrumentSpec,
    *,
    account_ccy: str,
    reference_price: float,
) -> float:
    """Return pip value in account currency for one standard lot.

    Supported deterministically for:
    - account_ccy == quote_ccy
    - account_ccy == base_ccy via quote/base conversion at reference_price
    """

    if reference_price <= 0:
        raise ValueError("reference_price must be positive")

    pip_value_in_quote = instrument.pip_size * instrument.lot_size_units
    if account_ccy == instrument.quote_ccy:
        return round(pip_value_in_quote, 6)
    if account_ccy == instrument.base_ccy:
        return round(pip_value_in_quote / reference_price, 6)
    raise NotImplementedError(
        f"account_ccy={account_ccy} unsupported for symbol={instrument.symbol}; "
        "only quote/base account conversion is implemented"
    )


def pip_value_usd_per_standard_lot(instrument: InstrumentSpec, *, reference_price: float = 1.0) -> float:
    return pip_value_per_standard_lot(instrument, account_ccy="USD", reference_price=reference_price)


def size_position_units(
    equity: float,
    risk: RiskSpec,
    instrument: InstrumentSpec,
    stop_loss_pips: float,
    reference_price: float,
) -> int:
    """Size a position in units using fixed-fraction risk.

    Rounded down to whole units for determinism.
    Equity/account currency must match risk.account_ccy.
    """

    if stop_loss_pips <= 0:
        raise ValueError("stop_loss_pips must be positive")

    risk_amount = equity * risk.risk_per_trade_fraction
    pip_value_per_lot = pip_value_per_standard_lot(
        instrument,
        account_ccy=risk.account_ccy,
        reference_price=reference_price,
    )
    loss_per_standard_lot = stop_loss_pips * pip_value_per_lot
    lots = risk_amount / loss_per_standard_lot
    if risk.max_lots is not None:
        lots = min(lots, risk.max_lots)
    units = floor(lots * instrument.lot_size_units)
    return max(units, 0)
