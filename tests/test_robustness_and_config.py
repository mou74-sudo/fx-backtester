from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import SignalBar, run_backtest
from fx_backtester.engine.pipeline import build_rsi_signal_pipeline
from fx_backtester.engine.robustness import run_robustness_lite
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import BacktestWindow, InstrumentSpec, RiskSpec, RsiMeanReversionRule, StrategySpec



def _build_spec(**rule_overrides: object) -> StrategySpec:
    return StrategySpec(
        strategy_name="robustness_suite",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=30, **rule_overrides),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-01-03"),
    )



def test_session_restriction_blocks_out_of_session_entry() -> None:
    spec = _build_spec(allowed_sessions=["london"], rsi_period=2, entry_rsi_lte=10)
    bars = [
        MarketBar(timestamp="2024-01-01T00:00:00Z", open=1.1000, high=1.1001, low=1.0999, close=1.1000, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T01:00:00Z", open=1.1000, high=1.1001, low=1.0989, close=1.0990, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T02:00:00Z", open=1.0990, high=1.0991, low=1.0979, close=1.0980, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T03:00:00Z", open=1.0980, high=1.1000, low=1.0978, close=1.0995, sessions=["london"]),
    ]

    prepared = build_rsi_signal_pipeline(market_bars=bars, spec=spec)

    assert not any(row.entry_signal for row in prepared.signal_trace)
    assert prepared.signal_trace[2].session_allowed is False



def test_short_only_pipeline_emits_short_signals() -> None:
    spec = _build_spec(direction="short_only", rsi_period=2, short_entry_rsi_gte=90, short_exit_rsi_lte=60)
    bars = [
        MarketBar(timestamp="2024-01-01T00:00:00Z", open=1.1000, high=1.1001, low=1.0999, close=1.1000, sessions=["london"]),
        MarketBar(timestamp="2024-01-01T01:00:00Z", open=1.1000, high=1.1011, low=1.0999, close=1.1010, sessions=["london"]),
        MarketBar(timestamp="2024-01-01T02:00:00Z", open=1.1010, high=1.1021, low=1.1009, close=1.1020, sessions=["london"]),
        MarketBar(timestamp="2024-01-01T03:00:00Z", open=1.1020, high=1.1021, low=1.1004, close=1.1005, sessions=["london"]),
    ]

    prepared = build_rsi_signal_pipeline(market_bars=bars, spec=spec)

    assert any(row.short_entry_signal for row in prepared.signal_trace)
    assert not any(row.entry_signal for row in prepared.signal_trace)



def test_disabled_take_profit_falls_back_to_signal_exit() -> None:
    spec = _build_spec(take_profit_style="disabled")
    policy = ExecutionPolicy(half_spread_pips=0.2)
    bars = [
        SignalBar(timestamp="2024-01-01T00:00:00", open=1.1000, high=1.1002, low=1.0998, close=1.1000, entry_long=True),
        SignalBar(timestamp="2024-01-01T01:00:00", open=1.1000, high=1.1100, low=1.0999, close=1.1090),
        SignalBar(timestamp="2024-01-01T02:00:00", open=1.1090, high=1.1092, low=1.1088, close=1.1090, exit_long=True),
    ]

    result = run_backtest(bars=bars, spec=spec, policy=policy)

    assert result.trade_count == 1
    assert result.trades[0].exit_reason == "signal_exit"



def test_robustness_lite_produces_scenarios_and_trade_concentration() -> None:
    spec = _build_spec(rsi_period=2, entry_rsi_lte=20, exit_rsi_gte=80)
    spec.robustness.enabled = True
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.1)
    market_bars = [
        MarketBar(timestamp="2024-01-01T00:00:00Z", open=1.1000, high=1.1002, low=1.0998, close=1.1000, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T01:00:00Z", open=1.1000, high=1.1001, low=1.0988, close=1.0990, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T02:00:00Z", open=1.0990, high=1.0991, low=1.0978, close=1.0980, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T03:00:00Z", open=1.0980, high=1.1008, low=1.0979, close=1.1005, sessions=["london"]),
        MarketBar(timestamp="2024-01-01T04:00:00Z", open=1.1005, high=1.1010, low=1.1000, close=1.1009, sessions=["london"]),
    ]

    prepared = build_rsi_signal_pipeline(market_bars=market_bars, spec=spec)
    baseline_result = run_backtest(bars=prepared.bars, spec=spec, policy=policy)
    report = run_robustness_lite(market_bars=market_bars, spec=spec, policy=policy, baseline_result=baseline_result)

    assert report.enabled is True
    assert len(report.scenarios) == 18
    assert report.trade_concentration["dominant_session"] in {"asia", "london", None}
    assert isinstance(report.session_contribution_summary, dict)
