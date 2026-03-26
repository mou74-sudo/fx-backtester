"""Known-answer tests for the minimal deterministic backtest loop."""

from fx_backtester.engine.backtest import SignalBar, run_backtest
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import (
    BacktestWindow,
    InstrumentSpec,
    RiskSpec,
    RsiMeanReversionRule,
    StrategySpec,
)
from fx_backtester.reports.compliance import build_compliance_summary


def _build_spec() -> StrategySpec:
    return StrategySpec(
        strategy_name="eurusd_rsi_mean_reversion_known_answer",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-01-03"),
    )


def test_known_answer_backtest_produces_exact_trade_ledger() -> None:
    spec = _build_spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1004, low=1.0997, close=1.1000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1000, high=1.1035, low=1.0998, close=1.1030),
        SignalBar(timestamp="2024-01-01T02:00:00", open=1.1028, high=1.1030, low=1.1020, close=1.1025, entry_long=True),
        SignalBar(timestamp="2024-01-01T03:00:00", open=1.1025, high=1.1030, low=1.1004, close=1.1006),
        SignalBar(timestamp="2024-01-01T04:00:00", open=1.1010, high=1.1013, low=1.1009, close=1.1010, entry_long=True),
        SignalBar(timestamp="2024-01-01T05:00:00", open=1.1010, high=1.1022, low=1.1008, close=1.1020, exit_long=True),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)

    assert result.trade_count == 3
    assert result.ending_equity == 10096.73
    assert [trade.trade_id for trade in result.trades] == [
        "eurusd-0001",
        "eurusd-0002",
        "eurusd-0003",
    ]
    assert [trade.pnl_usd for trade in result.trades] == [150.0, -101.5, 48.23]
    assert [trade.exit_price for trade in result.trades] == [1.10302, 1.10052, 1.10198]


def test_compliance_summary_matches_backtest_result() -> None:
    spec = _build_spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1004, low=1.0997, close=1.1000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1000, high=1.1035, low=1.0998, close=1.1030),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    summary = build_compliance_summary(spec=spec, policy=policy, result=result)

    assert summary["summary"] == {
        "starting_equity": 10000.0,
        "ending_equity": 10150.0,
        "net_pnl_usd": 150.0,
        "trade_count": 1,
        "wins": 1,
        "losses": 0,
        "open_trades": 0,
    }
    assert len(summary["trades"]) == 1
    assert summary["trades"][0]["trade_id"] == "eurusd-0001"
