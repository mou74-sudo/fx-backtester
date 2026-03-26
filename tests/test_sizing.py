from fx_backtester.engine.execution import apply_execution_policy
from fx_backtester.engine.sizing import pip_value_usd_per_standard_lot, size_position_units
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import InstrumentSpec, RiskSpec


def test_eurusd_pip_value_and_position_size_are_deterministic() -> None:
    instrument = InstrumentSpec()
    risk = RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01)

    assert pip_value_usd_per_standard_lot(instrument) == 10.0
    assert size_position_units(
        equity_usd=10_000,
        risk=risk,
        instrument=instrument,
        stop_loss_pips=20,
    ) == 50_000


def test_execution_policy_applies_half_spread_to_buy_fill() -> None:
    fill = apply_execution_policy(
        side="buy",
        requested_price=1.1000,
        policy=ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0),
        pip_size=0.0001,
    )

    assert fill.executed_price == 1.10002
