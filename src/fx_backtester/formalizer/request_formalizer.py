from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from fx_backtester.formalizer.spec_models import (
    BacktestWindow,
    InstrumentSpec,
    RiskSpec,
    RobustnessSpec,
    RsiMeanReversionRule,
    StrategySpec,
)


_SUPPORTED_PAIR_MAP: dict[str, InstrumentSpec] = {
    "EURUSD": InstrumentSpec(symbol="EURUSD", base_ccy="EUR", quote_ccy="USD", pip_size=0.0001),
    "USDJPY": InstrumentSpec(symbol="USDJPY", base_ccy="USD", quote_ccy="JPY", pip_size=0.01),
}

_UNSUPPORTED_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"\b(macd|ema|sma|moving average|bollinger|stochastic|atr|vwap)\b", re.I), "Only RSI-based rules are implemented right now.", "Use RSI thresholds and fixed-pip stop/take-profit fields."),
    (re.compile(r"\b(trailing stop|trail stop|break[- ]?even|breakeven|partial take profit|scale out|scale-in|pyramid)\b", re.I), "Advanced trade management is not implemented.", "Use fixed_pips or disabled stop/take-profit controls only."),
    (re.compile(r"\b(limit order|stop order|pending order|market if touched)\b", re.I), "Order-type selection is not implemented.", "The engine fills deterministically on the next bar open after a signal."),
    (re.compile(r"\b(optimi[sz]e|optimi[sz]ation|grid search|walk[- ]?forward|monte carlo|genetic|bayesian)\b", re.I), "Optimization/search workflows are outside scope.", "Use robustness.enabled with deterministic spread/slippage/RSI perturbation only."),
    (re.compile(r"\b(multi[- ]?pair|portfolio|basket|correlation|hedg(e|ing))\b", re.I), "Portfolio or multi-pair logic is not implemented.", "Use one supported USD-linked pair per spec."),
    (re.compile(r"\b(news|fundamental|sentiment|machine learning|ai model|order book)\b", re.I), "External/discretionary execution logic is not implemented.", "Use deterministic RSI, sessions, risk, and robustness fields only."),
]


class FormalizationIssue(BaseModel):
    field: str
    reason: str
    nearest_supported: str | None = None


class FormalizerNotes(BaseModel):
    status: Literal["accepted", "rejected"]
    assumptions: list[str] = Field(default_factory=list)
    recognized_fields: dict[str, object] = Field(default_factory=dict)
    rejected_fields: list[FormalizationIssue] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)


class FormalizationOutcome(BaseModel):
    request_text: str
    spec: StrategySpec | None = None
    notes: FormalizerNotes


@dataclass(frozen=True)
class FormalizerDefaults:
    strategy_name_prefix: str = "formalized_rsi"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_equity: float = 10_000.0
    risk_per_trade_fraction: float = 0.01
    account_ccy: str = "USD"
    timeframe: str = "H1"
    direction: str = "long_only"
    rsi_period: int = 14
    entry_rsi_lte: float = 30.0
    short_entry_rsi_gte: float = 70.0
    exit_rsi_gte: float = 55.0
    short_exit_rsi_lte: float = 45.0
    stop_loss_style: str = "fixed_pips"
    stop_loss_pips: float = 20.0
    take_profit_style: str = "fixed_pips"
    take_profit_pips: float = 30.0
    symbol: str = "EURUSD"


def _normalize_request(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "strategy"


def _parse_pair(text: str) -> str | None:
    normalized = text.upper().replace("/", "")
    for symbol in _SUPPORTED_PAIR_MAP:
        if symbol in normalized:
            return symbol
    match = re.search(r"\b([A-Z]{3})\s*/?\s*([A-Z]{3})\b", text.upper())
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return None


def _parse_timeframe(text: str) -> str | None:
    match = re.search(r"\b(m1|m5|m15|m30|h1|h4|d1|1h|4h|1d)\b", text, re.I)
    if not match:
        return None
    raw = match.group(1).upper()
    return {"1H": "H1", "H1": "H1", "4H": "H4", "1D": "D1"}.get(raw, raw)


def _parse_direction(text: str) -> str | None:
    if re.search(r"\b(long and short|both directions|both sides|two[- ]?sided)\b", text, re.I):
        return "both"
    if re.search(r"\bshort only\b", text, re.I):
        return "short_only"
    if re.search(r"\blong only\b", text, re.I):
        return "long_only"
    return None


def _parse_sessions(text: str) -> list[str]:
    sessions: list[str] = []
    for name, pattern in {
        "asia": r"\b(asia|asian session|tokyo)\b",
        "london": r"\b(london|european session|europe)\b",
        "new_york": r"\b(new york|newyork|ny session|us session|new york session)\b",
    }.items():
        if re.search(pattern, text, re.I):
            sessions.append(name)
    return sessions


def _parse_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.I)
    return float(match.group(1)) if match else None


def _parse_int(text: str, pattern: str) -> int | None:
    value = _parse_number(text, pattern)
    return int(value) if value is not None else None


def _parse_percent_fraction(text: str) -> float | None:
    match = re.search(r"\b(?:risk(?:ing)?|risk per trade(?: of)?|risk)\s*(?:is\s*)?(\d+(?:\.\d+)?)\s*%", text, re.I)
    return round(float(match.group(1)) / 100.0, 6) if match else None


def _parse_currency(text: str) -> str | None:
    upper = text.upper()
    for pattern in (
        r"\bACCOUNT CURRENCY\s*(?:IS\s*)?([A-Z]{3})\b",
        r"\bBASE CURRENCY\s*(?:IS\s*)?([A-Z]{3})\b",
        r"\bCURRENCY\s*(?:IS\s*)?([A-Z]{3})\b",
    ):
        match = re.search(pattern, upper)
        if match:
            return match.group(1)
    return None


def _parse_stop_take_style(text: str, side: str) -> tuple[str | None, float | None]:
    disabled_pattern = rf"\b(no {side}|disable {side}|{side} disabled|without {side})\b"
    if re.search(disabled_pattern, text, re.I):
        return "disabled", 1.0
    pip_pattern = rf"\b(\d+(?:\.\d+)?)\s*pips?\s*(?:{side}|{side.replace('_', ' ')})\b|\b{side.replace('_', ' ')}\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*pips?\b"
    match = re.search(pip_pattern, text, re.I)
    if match:
        raw = match.group(1) or match.group(2)
        return "fixed_pips", float(raw)
    if side == "stop loss":
        alt = _parse_number(text, r"\bsl\s*(\d+(?:\.\d+)?)\b")
    else:
        alt = _parse_number(text, r"\btp\s*(\d+(?:\.\d+)?)\b")
    if alt is not None:
        return "fixed_pips", alt
    return None, None


def _parse_robustness(text: str) -> dict[str, object]:
    enabled = bool(re.search(r"\brobust(ness)?\b", text, re.I))
    spread_values = re.findall(r"\b(\d+(?:\.\d+)?)x\s+spread\b", text, re.I)
    rsi_offsets_match = re.search(r"\brsi(?: period)? variants?\s*[:=]?\s*([-\d,\s]+)\b", text, re.I)
    slippage_modes: list[str] = []
    if re.search(r"\bbase slippage\b", text, re.I):
        slippage_modes.append("base")
    if re.search(r"\b(worse|worse[- ]case) slippage\b", text, re.I):
        slippage_modes.append("worse")

    payload: dict[str, object] = {"enabled": enabled}
    if spread_values:
        payload["spread_multipliers"] = [float(item) for item in spread_values]
        enabled = True
        payload["enabled"] = True
    if slippage_modes:
        payload["slippage_modes"] = list(dict.fromkeys(slippage_modes))
        payload["enabled"] = True
    if rsi_offsets_match:
        values = [int(chunk.strip()) for chunk in rsi_offsets_match.group(1).split(",") if chunk.strip()]
        payload["rsi_period_variants"] = values
        payload["enabled"] = True
    return payload


def validate_supported_features(spec: StrategySpec) -> list[FormalizationIssue]:
    issues: list[FormalizationIssue] = []
    if spec.instrument.symbol not in _SUPPORTED_PAIR_MAP:
        issues.append(
            FormalizationIssue(
                field="pair",
                reason=f"Pair {spec.instrument.symbol} is not in the deterministic supported set.",
                nearest_supported="Use EURUSD or USDJPY.",
            )
        )
    if spec.rules.timeframe != "H1":
        issues.append(
            FormalizationIssue(
                field="timeframe",
                reason=f"Timeframe {spec.rules.timeframe} is unsupported.",
                nearest_supported="Use timeframe=H1.",
            )
        )
    if spec.risk.account_ccy not in {spec.instrument.base_ccy, spec.instrument.quote_ccy}:
        issues.append(
            FormalizationIssue(
                field="account_currency",
                reason=(
                    f"account_ccy={spec.risk.account_ccy} is unsupported for {spec.instrument.symbol}; "
                    "deterministic sizing/conversion only supports base/quote account currencies."
                ),
                nearest_supported=f"Use {spec.instrument.base_ccy} or {spec.instrument.quote_ccy}.",
            )
        )
    return issues


def formalize_strategy_request(request_text: str, defaults: FormalizerDefaults | None = None) -> FormalizationOutcome:
    defaults = defaults or FormalizerDefaults()
    text = _normalize_request(request_text)
    assumptions: list[str] = []
    rejected_fields: list[FormalizationIssue] = []
    recognized_fields: dict[str, object] = {}

    for pattern, reason, nearest in _UNSUPPORTED_PATTERNS:
        if pattern.search(text):
            rejected_fields.append(FormalizationIssue(field="unsupported_request", reason=reason, nearest_supported=nearest))

    pair = _parse_pair(text)
    if pair is None:
        pair = defaults.symbol
        assumptions.append(f"No pair explicitly recognized; defaulted to {pair}.")
    recognized_fields["pair"] = pair
    if pair not in _SUPPORTED_PAIR_MAP:
        rejected_fields.append(FormalizationIssue(field="pair", reason=f"Pair {pair} is not supported by the deterministic formalizer.", nearest_supported="Use EURUSD or USDJPY."))
        instrument = _SUPPORTED_PAIR_MAP[defaults.symbol]
    else:
        instrument = _SUPPORTED_PAIR_MAP[pair]

    timeframe = _parse_timeframe(text)
    if timeframe is None:
        timeframe = defaults.timeframe
        assumptions.append("No timeframe explicitly recognized; defaulted to H1.")
    recognized_fields["timeframe"] = timeframe
    if timeframe != "H1":
        rejected_fields.append(FormalizationIssue(field="timeframe", reason=f"Only H1 is implemented, not {timeframe}.", nearest_supported="Use H1."))

    direction = _parse_direction(text) or defaults.direction
    if _parse_direction(text) is None:
        assumptions.append("No direction explicitly recognized; defaulted to long_only.")
    recognized_fields["direction"] = direction

    sessions = _parse_sessions(text)
    recognized_fields["allowed_sessions"] = sessions

    rsi_period = _parse_int(text, r"\brsi(?: period)?\s*(?:of|=|is)?\s*(\d+)\b") or defaults.rsi_period
    entry_rsi_lte = _parse_number(text, r"\b(?:entry|buy|long entry)\s*rsi\s*(?:<=|below|under|at most)\s*(\d+(?:\.\d+)?)\b") or defaults.entry_rsi_lte
    exit_rsi_gte = _parse_number(text, r"\b(?:exit|long exit|close long)\s*rsi\s*(?:>=|above|over|at least)\s*(\d+(?:\.\d+)?)\b") or defaults.exit_rsi_gte
    short_entry_rsi_gte = _parse_number(text, r"\b(?:short entry|sell entry)\s*rsi\s*(?:>=|above|over|at least)\s*(\d+(?:\.\d+)?)\b") or defaults.short_entry_rsi_gte
    short_exit_rsi_lte = _parse_number(text, r"\b(?:short exit|cover|close short)\s*rsi\s*(?:<=|below|under|at most)\s*(\d+(?:\.\d+)?)\b") or defaults.short_exit_rsi_lte
    recognized_fields["rsi"] = {
        "rsi_period": rsi_period,
        "entry_rsi_lte": entry_rsi_lte,
        "exit_rsi_gte": exit_rsi_gte,
        "short_entry_rsi_gte": short_entry_rsi_gte,
        "short_exit_rsi_lte": short_exit_rsi_lte,
    }

    stop_style, stop_pips = _parse_stop_take_style(text, "stop loss")
    take_style, take_pips = _parse_stop_take_style(text, "take profit")
    stop_style = stop_style or defaults.stop_loss_style
    stop_pips = stop_pips or defaults.stop_loss_pips
    take_style = take_style or defaults.take_profit_style
    take_pips = take_pips or defaults.take_profit_pips
    recognized_fields["stop_take_profit"] = {
        "stop_loss_style": stop_style,
        "stop_loss_pips": stop_pips,
        "take_profit_style": take_style,
        "take_profit_pips": take_pips,
    }

    initial_equity = _parse_number(text, r"\b(?:initial equity|starting equity|equity|account size)\s*(?:of|=|is)?\s*\$?(\d+(?:\.\d+)?)\b") or defaults.initial_equity
    risk_fraction = _parse_percent_fraction(text) or defaults.risk_per_trade_fraction
    account_ccy = _parse_currency(text) or defaults.account_ccy
    recognized_fields["risk"] = {
        "initial_equity": initial_equity,
        "risk_per_trade_fraction": risk_fraction,
        "account_ccy": account_ccy,
    }

    robustness_payload = _parse_robustness(text)
    recognized_fields["robustness"] = robustness_payload

    strategy_name = f"{defaults.strategy_name_prefix}_{_slugify(pair.lower())}_{_slugify(direction)}"
    recognized_fields["strategy_name"] = strategy_name

    try:
        spec = StrategySpec(
            strategy_name=strategy_name,
            instrument=instrument,
            risk=RiskSpec(initial_equity=initial_equity, risk_per_trade_fraction=risk_fraction, account_ccy=account_ccy),
            rules=RsiMeanReversionRule(
                timeframe=timeframe,
                direction=direction,
                allowed_sessions=sessions,
                rsi_period=rsi_period,
                entry_rsi_lte=entry_rsi_lte,
                exit_rsi_gte=exit_rsi_gte,
                short_entry_rsi_gte=short_entry_rsi_gte,
                short_exit_rsi_lte=short_exit_rsi_lte,
                stop_loss_style=stop_style,
                stop_loss_pips=stop_pips,
                take_profit_style=take_style,
                take_profit_pips=take_pips,
            ),
            window=BacktestWindow(start_date=defaults.start_date, end_date=defaults.end_date),
            robustness=RobustnessSpec(**robustness_payload),
            notes="Formalized deterministically from a natural-language request. Defaults may have been applied where the request was underspecified.",
        )
    except ValidationError as exc:
        return FormalizationOutcome(
            request_text=request_text,
            notes=FormalizerNotes(
                status="rejected",
                assumptions=assumptions + [
                    f"Default backtest window applied: {defaults.start_date} to {defaults.end_date}."
                ],
                recognized_fields=recognized_fields,
                rejected_fields=rejected_fields,
                validation_errors=[err["msg"] for err in exc.errors()],
            ),
        )

    rejected_fields.extend(validate_supported_features(spec))
    assumptions.append(f"Default backtest window applied: {defaults.start_date} to {defaults.end_date}.")

    if rejected_fields:
        return FormalizationOutcome(
            request_text=request_text,
            notes=FormalizerNotes(
                status="rejected",
                assumptions=assumptions,
                recognized_fields=recognized_fields,
                rejected_fields=rejected_fields,
                validation_errors=[],
            ),
        )

    return FormalizationOutcome(
        request_text=request_text,
        spec=spec,
        notes=FormalizerNotes(
            status="accepted",
            assumptions=assumptions,
            recognized_fields=recognized_fields,
            rejected_fields=[],
            validation_errors=[],
        ),
    )


def write_formalization_artifacts(*, request_text: str, outcome: FormalizationOutcome, output_dir: str | Path) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "strategy_request.txt").write_text(request_text.strip() + "\n", encoding="utf-8")
    (target_dir / "formalized_spec.json").write_text(
        json.dumps(outcome.spec.model_dump(mode="json") if outcome.spec is not None else None, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (target_dir / "formalizer_notes.json").write_text(
        json.dumps(outcome.notes.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target_dir
