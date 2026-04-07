"""Deterministic position sizing helpers for FX and futures."""

from __future__ import annotations

from math import floor

from fx_backtester.formalizer.spec_models import InstrumentSpec, RiskSpec


def pip_value_per_standard_lot(
    instrument: InstrumentSpec,
    *,
    account_ccy: str,
    reference_price: float,
) -> float:
    """Return pip/tick value in account currency for one standard FX lot.

    Supported deterministically for:
    - account_ccy == quote_ccy
    - account_ccy == base_ccy via quote/base conversion at reference_price

    For futures use point_value_per_contract() instead.
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


def point_value_per_contract(instrument: InstrumentSpec) -> float:
    """Return USD value of a 1-point move per futures contract.

    NQ: 20.0 USD/point  |  ES: 50.0 USD/point
    Raises for non-futures instruments.
    """
    if instrument.instrument_type != "futures":
        raise ValueError(
            f"point_value_per_contract() called on non-futures instrument {instrument.symbol!r}. "
            "Use pip_value_per_standard_lot() for FX."
        )
    if instrument.point_value <= 0:
        raise ValueError(f"instrument.point_value must be > 0 for futures {instrument.symbol!r}")
    return instrument.point_value


def size_position_units(
    equity: float,
    risk: RiskSpec,
    instrument: InstrumentSpec,
    stop_loss_pips: float,
    reference_price: float,
) -> int:
    """Size a position in units (FX) or contracts (futures) using fixed-fraction risk.

    For FX: stop_loss_pips is in pips; returns units.
    For futures: stop_loss_pips is in points; returns number of contracts.
    Rounded down to whole units/contracts for determinism.
    """

    if stop_loss_pips <= 0:
        raise ValueError("stop_loss_pips must be positive")

    risk_amount = equity * risk.risk_per_trade_fraction

    if instrument.instrument_type == "futures":
        # Futures: loss per contract = stop_loss_points * point_value_usd
        loss_per_contract = stop_loss_pips * point_value_per_contract(instrument)
        if loss_per_contract <= 0:
            return 0
        contracts = floor(risk_amount / loss_per_contract)
        return max(contracts, 0)

    # FX path (unchanged)
    pip_value_per_lot = pip_value_per_standard_lot(
        instrument,
        account_ccy=risk.account_ccy,
        reference_price=reference_price,
    )
    loss_per_standard_lot = stop_loss_pips * pip_value_per_lot
    lots = risk_amount / loss_per_standard_lot
    units = floor(lots * instrument.lot_size_units)
    return max(units, 0)
