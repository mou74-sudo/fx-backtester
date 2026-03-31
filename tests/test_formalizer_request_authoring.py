from __future__ import annotations

import json
from pathlib import Path

from fx_backtester.formalizer.request_formalizer import formalize_strategy_request, write_formalization_artifacts


def test_formalizer_accepts_supported_request_and_writes_artifacts(tmp_path: Path) -> None:
    request_text = (
        "Trade EUR/USD on H1, long only. "
        "Use RSI period 5. "
        "Entry RSI below 20 and exit RSI above 60. "
        "Use a 2x ATR(5) stop loss and 80 pip take profit. "
        "Exit after 3 bars and force a session close exit. "
        "Only trade the London and New York sessions. "
        "Initial equity 15000. Risk 1% per trade. Account currency USD. "
        "Enable robustness with 1x spread and 2x spread, base slippage and worse slippage, "
        "RSI variants -1,0,1."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.instrument.symbol == "EURUSD"
    assert outcome.spec.rules.timeframe == "H1"
    assert outcome.spec.rules.direction == "long_only"
    assert outcome.spec.rules.allowed_sessions == ["london", "new_york"]
    assert outcome.spec.rules.rsi_period == 5
    assert outcome.spec.rules.entry_rsi_lte == 20
    assert outcome.spec.rules.exit_rsi_gte == 60
    assert outcome.spec.rules.stop_loss_style == "atr"
    assert outcome.spec.rules.stop_loss_atr_period == 5
    assert outcome.spec.rules.stop_loss_atr_multiplier == 2.0
    assert outcome.spec.rules.take_profit_pips == 80
    assert outcome.spec.rules.time_stop_bars == 3
    assert outcome.spec.rules.exit_on_session_close is True
    assert outcome.spec.risk.initial_equity == 15000
    assert outcome.spec.risk.risk_per_trade_fraction == 0.01
    assert outcome.spec.robustness.enabled is True
    assert outcome.spec.robustness.spread_multipliers == [1.0, 2.0]
    assert outcome.spec.robustness.slippage_modes == ["base", "worse"]
    assert outcome.spec.robustness.rsi_period_variants == [-1, 0, 1]

    artifact_dir = write_formalization_artifacts(request_text=request_text, outcome=outcome, output_dir=tmp_path / "formalized")

    assert (artifact_dir / "strategy_request.txt").exists()
    assert (artifact_dir / "formalized_spec.json").exists()
    assert (artifact_dir / "formalizer_notes.json").exists()
    assert json.loads((artifact_dir / "formalized_spec.json").read_text(encoding="utf-8"))["instrument"]["symbol"] == "EURUSD"


def test_formalizer_rejects_unsupported_request_with_nearest_supported_guidance(tmp_path: Path) -> None:
    request_text = (
        "Trade GBP/USD on H4 with MACD confirmation, a trailing stop, and optimization. "
        "Account currency CHF."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert outcome.notes.rejected_fields
    reasons = [item.reason for item in outcome.notes.rejected_fields]
    nearest = [item.nearest_supported for item in outcome.notes.rejected_fields if item.nearest_supported]
    assert any("RSI-based" in reason or "RSI-based entry" in reason for reason in reasons)
    assert any("Advanced trade management" in reason for reason in reasons)
    assert any("Optimization/search" in reason for reason in reasons)
    assert any("EURUSD or USDJPY" in item for item in nearest)
    assert any("H1" in item for item in nearest)

    artifact_dir = write_formalization_artifacts(request_text=request_text, outcome=outcome, output_dir=tmp_path / "rejected")
    assert json.loads((artifact_dir / "formalized_spec.json").read_text(encoding="utf-8")) is None
    notes = json.loads((artifact_dir / "formalizer_notes.json").read_text(encoding="utf-8"))
    assert notes["status"] == "rejected"


def test_formalizer_rejects_supported_pair_when_account_currency_is_not_base_or_quote() -> None:
    request_text = "Trade EURUSD on H1 long only. Stop loss 20 pips. Take profit 30 pips. Account currency CHF."

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any(item.field == "account_currency" for item in outcome.notes.rejected_fields)


def test_formalizer_rejects_session_close_exit_without_explicit_sessions() -> None:
    request_text = "Trade EURUSD on H1 long only. Exit on session close. Stop loss 20 pips. Take profit 30 pips."

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any("exit_on_session_close requires at least one allowed session" in error for error in outcome.notes.validation_errors)



def test_formalizer_accepts_supported_breakout_request_and_parses_fields() -> None:
    request_text = (
        "Trade EUR/USD on H1 using a breakout strategy in both directions. "
        "Go long when price closes above the highest high of the last 20 bars by 2 pips. "
        "Go short when price closes below the lowest low of the last 20 bars by 2 pips. "
        "Use a 15 pip stop, 30 pip target, and 12-bar time stop. "
        "Only trade the London and New York sessions. "
        "Initial equity 10000. Risk 1% per trade. Account currency USD."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.strategy_type == "breakout"
    assert outcome.spec.rules.direction == "both"
    assert outcome.spec.rules.breakout_lookback_bars == 20
    assert outcome.spec.rules.breakout_buffer_pips == 2
    assert outcome.spec.rules.stop_loss_pips == 15
    assert outcome.spec.rules.take_profit_pips == 30
    assert outcome.spec.rules.time_stop_bars == 12
    assert outcome.spec.rules.allowed_sessions == ["london", "new_york"]
    assert outcome.spec.risk.account_ccy == "USD"



def test_formalizer_rejects_breakout_request_with_trailing_stop() -> None:
    request_text = (
        "Trade EUR/USD on H1 using a breakout strategy. "
        "Go long when price closes above the highest high of the last 20 bars by 2 pips. "
        "Use a trailing stop and 12-bar time stop."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any("Advanced trade management" in item.reason for item in outcome.notes.rejected_fields)



def test_formalizer_rejects_breakout_request_with_limit_pullback_entry() -> None:
    request_text = (
        "Trade EUR/USD on H1 using a breakout strategy. "
        "Wait for price to break above the highest high of the last 20 bars by 2 pips, then use a pullback limit entry."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any("Unsupported execution style" in item.reason for item in outcome.notes.rejected_fields)



def test_formalizer_rejects_breakout_request_with_order_book_and_news_confirmation() -> None:
    request_text = (
        "Trade EUR/USD on H1 using a breakout strategy. "
        "Go long when price breaks above the highest high of the last 20 bars by 2 pips, "
        "but only with order book and news confirmation."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any("Unsupported discretionary/external logic" in item.reason for item in outcome.notes.rejected_fields)
