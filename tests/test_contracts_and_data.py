from pathlib import Path

import pytest
from pydantic import ValidationError

from fx_backtester.data.loaders import load_ohlc_csv
from fx_backtester.data.quality import assess_basic_ohlc_quality
from fx_backtester.formalizer.spec_models import BacktestWindow, InstrumentSpec, RiskSpec, RobustnessSpec, RsiMeanReversionRule, StrategySpec



def test_risk_spec_rejects_excessive_risk_fraction() -> None:
    with pytest.raises(ValidationError):
        RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.10)



def test_rule_rejects_inverted_thresholds() -> None:
    with pytest.raises(ValidationError):
        RsiMeanReversionRule(
            stop_loss_pips=20,
            take_profit_pips=30,
            entry_rsi_lte=60,
            exit_rsi_gte=55,
        )



def test_backtest_window_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        BacktestWindow(start_date="2024-02-01", end_date="2024-01-01")



def test_robustness_spec_rejects_duplicate_rsi_variants() -> None:
    with pytest.raises(ValidationError):
        RobustnessSpec(enabled=True, rsi_period_variants=[-1, 0, 0])



def test_load_ohlc_csv_and_quality_report(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close\n"
        "2024-01-01T00:00:00,1.1000,1.1010,1.0990,1.1005\n"
        "2024-01-01T01:00:00,1.1005,1.1020,1.1000,1.1015\n",
        encoding="utf-8",
    )

    rows = load_ohlc_csv(csv_path)
    report = assess_basic_ohlc_quality(rows)

    assert len(rows) == 2
    assert report.row_count == 2
    assert report.missing_required_fields == 0
    assert report.non_monotonic_timestamps == 0
    assert report.notes == []



def test_quality_report_flags_missing_fields_and_non_monotonic_timestamps() -> None:
    rows = [
        {"timestamp": "2024-01-01T01:00:00", "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.1"},
        {"timestamp": "2024-01-01T00:00:00", "open": "", "high": "1.2", "low": "1.0", "close": "1.1"},
    ]

    report = assess_basic_ohlc_quality(rows)

    assert report.missing_required_fields == 1
    assert report.non_monotonic_timestamps == 1
    assert len(report.notes) == 2



def test_breakout_rule_requires_strategy_specific_fields() -> None:
    with pytest.raises(ValidationError):
        RsiMeanReversionRule(strategy_type="breakout", stop_loss_pips=20, take_profit_pips=30)



def test_breakout_rule_accepts_minimal_supported_fields() -> None:
    rule = RsiMeanReversionRule(
        strategy_type="breakout",
        direction="both",
        breakout_lookback_bars=20,
        breakout_buffer_pips=2,
        stop_loss_pips=15,
        take_profit_pips=30,
        time_stop_bars=12,
    )

    assert rule.strategy_type == "breakout"
    assert rule.breakout_lookback_bars == 20
    assert rule.breakout_buffer_pips == 2



def test_strategy_spec_accepts_breakout_rule_contract() -> None:
    spec = StrategySpec(
        strategy_name="eurusd_breakout_contract",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(
            strategy_type="breakout",
            direction="both",
            breakout_lookback_bars=20,
            breakout_buffer_pips=2,
            stop_loss_pips=15,
            take_profit_pips=30,
            time_stop_bars=12,
        ),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-12-31"),
    )

    assert spec.rules.strategy_type == "breakout"
