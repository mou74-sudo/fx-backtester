from fx_backtester.engine.backtest import SignalBar, run_backtest
from fx_backtester.engine.benchmark import build_deterministic_benchmarks
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import BacktestWindow, InstrumentSpec, RiskSpec, RsiMeanReversionRule, StrategySpec
from fx_backtester.data.models import MarketBar


def _spec() -> StrategySpec:
    return StrategySpec(
        strategy_name='benchmark_suite',
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(stop_loss_pips=20, take_profit_pips=80),
        window=BacktestWindow(start_date='2024-01-01', end_date='2024-01-03'),
    )


def test_deterministic_benchmark_matches_trade_count_and_hold_profile() -> None:
    spec = _spec()
    policy = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)
    market_bars = [
        MarketBar(timestamp=f'2024-01-01T0{i}:00:00Z', open=1.1 + i * 0.0001, high=1.1005 + i * 0.0001, low=1.0995 + i * 0.0001, close=1.1 + i * 0.0001)
        for i in range(8)
    ]
    baseline = run_backtest(
        bars=[
            SignalBar(timestamp='2024-01-01T00:00:00Z', open=1.1000, high=1.1005, low=1.0995, close=1.1000, entry_long=True, sessions=['asia']),
            SignalBar(timestamp='2024-01-01T01:00:00Z', open=1.1001, high=1.1006, low=1.0999, close=1.1003),
            SignalBar(timestamp='2024-01-01T02:00:00Z', open=1.1002, high=1.1007, low=1.1000, close=1.1004, exit_long=True),
            SignalBar(timestamp='2024-01-01T03:00:00Z', open=1.1003, high=1.1008, low=1.1001, close=1.1005, entry_long=True, sessions=['london']),
            SignalBar(timestamp='2024-01-01T04:00:00Z', open=1.1004, high=1.1009, low=1.1002, close=1.1006),
            SignalBar(timestamp='2024-01-01T05:00:00Z', open=1.1005, high=1.1010, low=1.1003, close=1.1007, exit_long=True),
            SignalBar(timestamp='2024-01-01T06:00:00Z', open=1.1006, high=1.1011, low=1.1004, close=1.1008),
            SignalBar(timestamp='2024-01-01T07:00:00Z', open=1.1007, high=1.1012, low=1.1005, close=1.1009),
        ],
        spec=spec,
        policy=policy,
    )

    report = build_deterministic_benchmarks(market_bars=market_bars, baseline_result=baseline, spec=spec, policy=policy)

    assert report.baseline_trade_count == 2
    assert report.baseline_average_hold_bars == 2.0
    assert report.scenarios[0].target_trade_count == 2
    assert report.scenarios[0].target_hold_bars == 2
    assert report.scenarios[0].trade_count_match is True
    assert report.scenarios[0].hold_length_match is True
    assert report.scenarios[0].benchmark_quality == 'matched'


def test_benchmark_comparative_claims_require_tighter_match_and_sample() -> None:
    spec = _spec()
    policy = ExecutionPolicy()
    market_bars = [
        MarketBar(timestamp=f'2024-01-01T{i:02d}:00:00Z', open=1.1, high=1.101, low=1.099, close=1.1)
        for i in range(4)
    ]
    baseline = run_backtest(
        bars=[
            SignalBar(timestamp='2024-01-01T00:00:00Z', open=1.1, high=1.101, low=1.099, close=1.1, entry_long=True),
            SignalBar(timestamp='2024-01-01T01:00:00Z', open=1.1, high=1.101, low=1.099, close=1.1, exit_long=True),
            SignalBar(timestamp='2024-01-01T02:00:00Z', open=1.1, high=1.101, low=1.099, close=1.1),
            SignalBar(timestamp='2024-01-01T03:00:00Z', open=1.1, high=1.101, low=1.099, close=1.1),
        ],
        spec=spec,
        policy=policy,
    )

    report = build_deterministic_benchmarks(market_bars=market_bars, baseline_result=baseline, spec=spec, policy=policy)

    assert report.scenarios[0].comparative_claims_allowed is False
