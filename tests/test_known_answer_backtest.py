"""Known-answer tests for deterministic backtest semantics."""

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


def _build_spec(*, instrument: InstrumentSpec | None = None, risk: RiskSpec | None = None, **rule_overrides: object) -> StrategySpec:
    return StrategySpec(
        strategy_name="known_answer_suite",
        instrument=instrument or InstrumentSpec(),
        risk=risk or RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30, **rule_overrides),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-01-03"),
    )


def test_known_answer_backtest_produces_exact_trade_ledger_and_metrics() -> None:
    spec = _build_spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1004, low=1.0997, close=1.1000, entry_long=True, sessions=["asia"]),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1000, high=1.1035, low=1.0998, close=1.1030),
        SignalBar(timestamp="2024-01-01T02:00:00", open=1.1028, high=1.1030, low=1.1020, close=1.1025, entry_long=True, sessions=["london"]),
        SignalBar(timestamp="2024-01-01T03:00:00", open=1.1025, high=1.1030, low=1.1004, close=1.1006),
        SignalBar(timestamp="2024-01-01T04:00:00", open=1.1010, high=1.1013, low=1.1009, close=1.1010, entry_long=True, sessions=["new_york"]),
        SignalBar(timestamp="2024-01-01T05:00:00", open=1.1010, high=1.1022, low=1.1008, close=1.1020, exit_long=True),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)

    assert result.trade_count == 3
    assert result.ending_equity == 10094.72
    assert [trade.trade_id for trade in result.trades] == ["eurusd-0001", "eurusd-0002", "eurusd-0003"]
    assert [trade.pnl for trade in result.trades] == [149.0, -102.5, 48.22]
    assert [trade.exit_price for trade in result.trades] == [1.103, 1.1005, 1.10198]
    assert result.metrics.gross_profit == 197.22
    assert result.metrics.gross_loss == -102.5
    assert result.metrics.net_pips == 19.2
    assert result.metrics.max_drawdown == 102.5
    assert result.metrics.max_drawdown_duration_trades == 1
    assert result.metrics.session_summary["asia"]["trade_count"] == 1


def test_gap_through_stop_and_ambiguous_same_candle_are_counted_conservatively() -> None:
    spec = _build_spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0, allow_intrabar_tp_sl_resolution=False)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1003, low=1.0999, close=1.1000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.0970, high=1.1035, low=1.0965, close=1.1020),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    trade = result.trades[0]

    assert trade.exit_reason == "stop_loss"
    assert trade.ambiguity_detected is True
    assert trade.exit_price == 1.09698
    assert trade.pnl_pips == -30.4
    assert result.metrics.ambiguity_count == 1


def test_spread_triggered_stop_can_fire_without_mid_touch() -> None:
    spec = _build_spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1001, low=1.0999, close=1.1000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1000, high=1.1004, low=1.09804, close=1.0983),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    trade = result.trades[0]

    assert trade.spread_triggered_stop is True
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == 1.098


def test_short_side_take_profit_is_supported() -> None:
    spec = _build_spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1001, low=1.0999, close=1.1000, entry_short=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.0998, high=1.1000, low=1.0967, close=1.0970),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    trade = result.trades[0]

    assert trade.side == "sell"
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == 1.097
    assert trade.pnl > 0


def test_time_stop_exits_on_bar_open_after_configured_hold_count() -> None:
    spec = _build_spec(time_stop_bars=2)
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1002, low=1.0998, close=1.1000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1010, high=1.1015, low=1.1005, close=1.1012),
        SignalBar(timestamp="2024-01-01T02:00:00", open=1.1020, high=1.1030, low=1.1015, close=1.1025),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    trade = result.trades[0]

    assert trade.exit_reason == "time_stop"
    assert trade.exit_time.isoformat() == "2024-01-01T02:00:00"
    assert trade.exit_price == 1.10198
    assert trade.pnl_pips == 19.6


def test_session_close_exit_fires_when_bar_leaves_allowed_session() -> None:
    spec = _build_spec(allowed_sessions=["london"], exit_on_session_close=True)
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T07:00:00", open=1.1000, high=1.1002, low=1.0998, close=1.1000, entry_long=True, sessions=["london"]),
        SignalBar(timestamp="2024-01-01T08:00:00", open=1.1008, high=1.1012, low=1.1005, close=1.1010, sessions=["london"]),
        SignalBar(timestamp="2024-01-01T16:00:00", open=1.1015, high=1.1018, low=1.1012, close=1.1016, sessions=[]),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    trade = result.trades[0]

    assert trade.exit_reason == "session_close"
    assert trade.exit_time.isoformat() == "2024-01-01T16:00:00"
    assert trade.exit_price == 1.10148


def test_atr_stop_uses_execution_bar_atr_for_initial_stop_distance() -> None:
    spec = _build_spec(stop_loss_style="atr", stop_loss_atr_period=2, stop_loss_atr_multiplier=2.0, take_profit_style="disabled")
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1005, low=1.0995, close=1.1000, entry_long=True, atr=0.0010),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1000, high=1.1001, low=1.0979, close=1.0985, atr=0.0010),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)
    trade = result.trades[0]

    assert trade.stop_loss_price == 1.09802
    assert trade.quantity_units == 50000
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == 1.098


def test_usdjpy_known_answer_uses_jpy_pip_sizing() -> None:
    spec = _build_spec(
        instrument=InstrumentSpec(symbol="USDJPY", base_ccy="USD", quote_ccy="JPY", pip_size=0.01),
    )
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=150.00, high=150.02, low=149.98, close=150.00, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=150.00, high=150.32, low=149.99, close=150.30),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)

    assert result.trades[0].quantity_units == 75_000
    assert result.trades[0].pnl_pips == 29.8


def test_non_usd_account_conversion_is_applied_to_usd_equity_report() -> None:
    spec = _build_spec(risk=RiskSpec(account_ccy="EUR", initial_equity=10_000, risk_per_trade_fraction=0.01))
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.2000, high=1.2002, low=1.1998, close=1.2000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.2000, high=1.2032, low=1.1999, close=1.2030),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)

    assert result.trades[0].pnl == 178.8
    assert result.trades[0].pnl_usd == 215.1
    assert result.ending_equity == 10178.8
    assert result.ending_equity_usd == 12245.1


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
        "ending_equity": 10149.0,
        "ending_equity_usd": 10149.0,
        "net_pnl": 149.0,
        "trade_count": 1,
        "wins": 1,
        "losses": 0,
        "open_trades": 0,
        "ambiguity_count": 0,
        "spread_triggered_stop_count": 0,
    }
    assert len(summary["trades"]) == 1
    assert summary["trades"][0]["trade_id"] == "eurusd-0001"
