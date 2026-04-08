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
    assert any("MACD" in reason or "not yet implemented" in reason for reason in reasons)
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



def test_formalizer_accepts_breakout_request_with_trailing_stop() -> None:
    # Trailing stops are now supported by the formalizer; the request is accepted
    # (trailing_stop_style may default to "disabled" if the phrasing isn't specific).
    request_text = (
        "Trade EUR/USD on H1 using a breakout strategy. "
        "Go long when price closes above the highest high of the last 20 bars by 2 pips. "
        "Use a trailing stop and 12-bar time stop."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.strategy_type == "breakout"
    assert outcome.spec.rules.time_stop_bars == 12



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
    assert any("Discretionary" in item.reason or "discretionary" in item.reason for item in outcome.notes.rejected_fields)


# ── Issue #4: RSI phrasing expansion ─────────────────────────────────────────


# A1: RSI(N) parenthesised period + "enter/exit when RSI is below/above N"
def test_a1_rsi_parenthesized_period_and_enter_exit_when_phrasing() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. "
        "Use RSI(14). Enter when RSI is below 30. Exit when RSI is above 55. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.rsi_period == 14
    assert outcome.spec.rules.entry_rsi_lte == 30.0
    assert outcome.spec.rules.exit_rsi_gte == 55.0


# A2: "when RSI is below N, go long" / "when RSI is above N, exit long"
def test_a2_when_rsi_is_below_go_long_phrasing() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "When RSI is below 28, go long. When RSI is above 60, exit long. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.entry_rsi_lte == 28.0
    assert outcome.spec.rules.exit_rsi_gte == 60.0


# A3: "RSI falls below N" / "RSI rises above N" directional verb phrasings
def test_a3_rsi_falls_below_and_rises_above_phrasing() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter long if RSI falls below 25. Exit if RSI rises above 60. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.entry_rsi_lte == 25.0
    assert outcome.spec.rules.exit_rsi_gte == 60.0


# A4: "N-period RSI" period-prefix syntax
def test_a4_n_period_rsi_prefix_syntax() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. "
        "Use a 9-period RSI. Enter when RSI is below 30. Exit when RSI is above 55. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.rsi_period == 9


# A6: "RSI reading under/over N" phrasings
def test_a6_rsi_reading_under_over_phrasing() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "RSI reading under 30 triggers a long entry. RSI reading over 55 closes the long. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.entry_rsi_lte == 30.0
    assert outcome.spec.rules.exit_rsi_gte == 55.0


# R1: RSI with MACD confirmation → rejected for unsupported signal
def test_r1_rsi_macd_combo_rejected() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI(14) below 30 to enter, "
        "but confirm with MACD crossover. Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any("MACD" in item.reason or "not yet implemented" in item.reason for item in outcome.notes.rejected_fields)


# R2: RSI with optimization request → rejected
def test_r2_rsi_with_optimization_rejected() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter when RSI is below 30. Optimize the RSI period and entry threshold. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any("Optimization" in item.reason for item in outcome.notes.rejected_fields)


# R3: RSI with trailing stop → now accepted (trailing stops are supported)
def test_r3_rsi_with_trailing_stop_accepted() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter when RSI is below 30. Use a trailing stop of 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.rsi_period == 14


# R4: RSI with multi-pair scope → rejected
def test_r4_rsi_with_multi_pair_rejected() -> None:
    request_text = (
        "Run a multi-pair RSI strategy on EUR/USD and GBP/USD on H1. "
        "RSI period 14. Enter when RSI is below 30. Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "rejected"
    assert outcome.spec is None
    assert any(
        "portfolio" in item.reason.lower() or "basket" in item.reason.lower() or "multi" in item.reason.lower()
        for item in outcome.notes.rejected_fields
    )


# M1: Long-only with falls/rises phrasing; short defaults must not be overridden
def test_m1_long_only_custom_thresholds_short_defaults_unchanged() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter long when RSI falls below 28. Exit when RSI rises above 62. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.entry_rsi_lte == 28.0
    assert outcome.spec.rules.exit_rsi_gte == 62.0
    # short thresholds must remain at defaults — no side inference
    assert outcome.spec.rules.short_entry_rsi_gte == 70.0
    assert outcome.spec.rules.short_exit_rsi_lte == 45.0


# M2: Both-direction with explicit "go long/go short" RSI phrasings
def test_m2_both_directions_explicit_go_long_go_short_rsi_thresholds() -> None:
    request_text = (
        "Trade EURUSD on H1, long and short. RSI period 14. "
        "Go long when RSI is below 30. Go short when RSI is above 72. "
        "Exit long when RSI is above 55. Exit short when RSI is below 45. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.entry_rsi_lte == 30.0
    assert outcome.spec.rules.short_entry_rsi_gte == 72.0
    assert outcome.spec.rules.exit_rsi_gte == 55.0
    assert outcome.spec.rules.short_exit_rsi_lte == 45.0


# M3: RSI phrasing combined with robustness sweep; both parsed without conflict
def test_m3_rsi_phrasing_with_robustness_sweep_no_conflict() -> None:
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter when RSI is below 30. Exit when RSI is above 55. "
        "Enable robustness with 1x spread and 2x spread. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.entry_rsi_lte == 30.0
    assert outcome.spec.rules.exit_rsi_gte == 55.0
    assert outcome.spec.robustness.enabled is True
    assert outcome.spec.robustness.spread_multipliers == [1.0, 2.0]


# ── Direction co-presence detection ──────────────────────────────────────────


def test_direction_buy_sell_breakout_resolves_to_both() -> None:
    """'Buy if ... Sell if ...' co-presence → direction=both."""
    request_text = (
        "Trade EURUSD on H1 using a breakout strategy. "
        "Buy if price breaks above the highest high of the last 20 bars by 2 pips. "
        "Sell if it breaks below the lowest low of the last 20 bars by 2 pips. "
        "Use a 12-bar time stop. Stop loss 15 pips. Take profit 30 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.direction == "both"


def test_direction_go_long_go_short_breakout_resolves_to_both() -> None:
    """'Go long when ... Go short when ...' co-presence → direction=both."""
    request_text = (
        "Trade EURUSD on H1 using a breakout strategy. "
        "Go long when price closes above the highest high of the last 20 bars by 2 pips. "
        "Go short when price closes below the lowest low of the last 20 bars by 2 pips. "
        "Stop loss 15 pips. Take profit 30 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.direction == "both"


def test_direction_rsi_long_only_explicit_not_widened_to_both() -> None:
    """Explicit 'long only' is never overridden to both by entry keywords."""
    request_text = (
        "Trade EURUSD on H1, long only. RSI period 14. "
        "Enter long when RSI falls below 30. Exit when RSI rises above 55. "
        "Stop loss 20 pips. Take profit 40 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.direction == "long_only"


def test_direction_single_side_entry_keyword_does_not_infer_both() -> None:
    """Only one side's entry keyword present → must not become both."""
    request_text = (
        "Trade EURUSD on H1. RSI period 14. "
        "Enter long when RSI falls below 30. Exit when RSI rises above 55. "
        "Stop loss 15 pips. Take profit 30 pips."
    )

    outcome = formalize_strategy_request(request_text)

    assert outcome.notes.status == "accepted"
    assert outcome.spec is not None
    assert outcome.spec.rules.direction == "long_only"  # defaulted; no short-entry keyword present
