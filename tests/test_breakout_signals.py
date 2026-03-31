from __future__ import annotations

from fx_backtester.data.models import MarketBar
from fx_backtester.engine.pipeline import build_breakout_signal_pipeline
from fx_backtester.formalizer.spec_models import BacktestWindow, InstrumentSpec, RiskSpec, RsiMeanReversionRule, StrategySpec


def _build_breakout_spec(**rule_overrides: object) -> StrategySpec:
    rule_payload = {
        "strategy_type": "breakout",
        "breakout_lookback_bars": 3,
        "breakout_buffer_pips": 2,
        "stop_loss_pips": 15,
        "take_profit_pips": 30,
        "direction": "both",
        **rule_overrides,
    }
    return StrategySpec(
        strategy_name="breakout_signal_suite",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(**rule_payload),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-01-02"),
    )


def _bars() -> list[MarketBar]:
    return [
        MarketBar(timestamp="2024-01-01T00:00:00Z", open=1.1000, high=1.1005, low=1.0995, close=1.1000, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T01:00:00Z", open=1.1000, high=1.1004, low=1.0996, close=1.1001, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T02:00:00Z", open=1.1001, high=1.1003, low=1.0997, close=1.1000, sessions=["asia"]),
        MarketBar(timestamp="2024-01-01T03:00:00Z", open=1.1000, high=1.1006, low=1.0998, close=1.1008, sessions=["london"]),
        MarketBar(timestamp="2024-01-01T04:00:00Z", open=1.1008, high=1.1010, low=1.0998, close=1.0993, sessions=["london"]),
        MarketBar(timestamp="2024-01-01T05:00:00Z", open=1.0993, high=1.0997, low=1.0990, close=1.0992, sessions=["new_york"]),
    ]


def test_breakout_long_entry_uses_prior_completed_bars_only() -> None:
    prepared = build_breakout_signal_pipeline(market_bars=_bars(), spec=_build_breakout_spec(direction="long_only"))

    assert prepared.signal_trace[2].entry_signal is False
    assert prepared.signal_trace[3].entry_signal is True
    assert prepared.signal_trace[4].entry_signal is False
    assert prepared.bars[4].entry_long is True
    assert prepared.bars[3].entry_long is False
    assert any(item == "prior_high=1.1005" for item in prepared.signal_trace[3].evidence)
    assert prepared.signal_trace[3].no_leakage_ok is True



def test_breakout_short_entry_uses_prior_completed_bars_only() -> None:
    prepared = build_breakout_signal_pipeline(market_bars=_bars(), spec=_build_breakout_spec(direction="short_only"))

    assert prepared.signal_trace[4].short_entry_signal is True
    assert prepared.bars[5].entry_short is True
    assert prepared.signal_trace[4].entry_signal is False
    assert any(item == "prior_low=1.0996" for item in prepared.signal_trace[4].evidence)
    assert prepared.signal_trace[4].no_leakage_ok is True



def test_breakout_buffer_prevents_touch_only_signal() -> None:
    bars = _bars()
    bars[3] = MarketBar(timestamp="2024-01-01T03:00:00Z", open=1.1000, high=1.1007, low=1.0998, close=1.1007, sessions=["london"])
    prepared = build_breakout_signal_pipeline(market_bars=bars, spec=_build_breakout_spec(direction="long_only"))

    assert prepared.signal_trace[3].entry_signal is False
    assert prepared.bars[4].entry_long is False



def test_breakout_direction_gating_is_respected() -> None:
    long_only = build_breakout_signal_pipeline(market_bars=_bars(), spec=_build_breakout_spec(direction="long_only"))
    short_only = build_breakout_signal_pipeline(market_bars=_bars(), spec=_build_breakout_spec(direction="short_only"))

    assert long_only.signal_trace[4].short_entry_signal is False
    assert short_only.signal_trace[3].entry_signal is False
