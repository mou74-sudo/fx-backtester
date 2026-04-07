from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from fx_backtester.formalizer.spec_models import (
    BacktestWindow,
    BreakoutRule,
    InstrumentSpec,
    RiskSpec,
    RobustnessSpec,
    RsiMeanReversionRule,
    StrategyRuleAdapter,
    StrategySpec,
)


_SUPPORTED_PAIR_MAP: dict[str, InstrumentSpec] = {
    "EURUSD": InstrumentSpec(symbol="EURUSD", base_ccy="EUR", quote_ccy="USD", pip_size=0.0001),
    "USDJPY": InstrumentSpec(symbol="USDJPY", base_ccy="USD", quote_ccy="JPY", pip_size=0.01),
}

_UNSUPPORTED_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    # Note: ema, bollinger, vwap, orb, and trailing stops are all now supported — do not add them here.
    (re.compile(r"\b(macd|stochastic)\b", re.I), "MACD and Stochastic are not yet implemented.", "Nearest supported path: use RSI mean-reversion, EMA crossover, Bollinger bands, VWAP, ORB, or Breakout."),
    (re.compile(r"\b(break[- ]?even|breakeven|partial take profit|scale out|scale-in|pyramid)\b", re.I), "Break-even, partials, and scaling are not supported.", "Nearest supported path: use fixed-pip TP, trailing stop (atr or fixed_pips), time stop, and/or session-close exit."),
    (re.compile(r"\b(limit order|stop order|pending order|market if touched|pullback entry|pullback breakout|pullback limit)\b", re.I), "Unsupported execution style: entries fill deterministically on the next bar open after a signal.", None),
    (re.compile(r"\b(optimi[sz]e|optimi[sz]ation|grid search|walk[- ]?forward|monte carlo|genetic|bayesian)\b", re.I), "Optimization/search workflows are unsupported in the formalizer.", "Nearest supported path: keep one fixed spec and optionally enable deterministic robustness sweeps."),
    (re.compile(r"\b(multi[- ]?pair|portfolio|basket|correlation|hedg(e|ing))\b", re.I), "Portfolio, basket, or hedge logic is not implemented.", "Nearest supported path: run one supported pair per spec."),
    (re.compile(r"\b(news|fundamental|sentiment|machine learning|ai model|order book)\b", re.I), "Discretionary/external logic is not supported.", "Nearest supported path: use deterministic rule-based strategies only."),
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
    strategy_type: str = "rsi_mean_reversion"
    rsi_period: int = 14
    entry_rsi_lte: float = 30.0
    short_entry_rsi_gte: float = 70.0
    exit_rsi_gte: float = 55.0
    short_exit_rsi_lte: float = 45.0
    breakout_lookback_bars: int = 20
    breakout_buffer_pips: float = 0.0
    time_stop_bars: int | None = None
    exit_on_session_close: bool = False
    stop_loss_style: str = "fixed_pips"
    stop_loss_pips: float = 20.0
    stop_loss_atr_period: int = 14
    stop_loss_atr_multiplier: float = 2.0
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


_EXPLICIT_LONG_ENTRY = re.compile(
    r"\b(buy\s+(?:if|when)|go\s+long|enter\s+long)\b", re.I
)
_EXPLICIT_SHORT_ENTRY = re.compile(
    r"\b(sell\s+(?:if|when)|go\s+short|enter\s+short)\b", re.I
)


def _parse_direction(text: str) -> str | None:
    # Explicit aggregate phrases take priority.
    if re.search(r"\b(long and short|both directions|both sides|two[- ]?sided)\b", text, re.I):
        return "both"
    if re.search(r"\bshort only\b", text, re.I):
        return "short_only"
    if re.search(r"\blong only\b", text, re.I):
        return "long_only"
    # Co-presence of an explicit long-entry keyword AND an explicit short-entry
    # keyword signals a two-sided request without requiring a summary phrase.
    if _EXPLICIT_LONG_ENTRY.search(text) and _EXPLICIT_SHORT_ENTRY.search(text):
        return "both"
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


def _parse_time_stop_bars(text: str) -> int | None:
    for pattern in (
        r"\btime stop(?: after)?\s*(\d+)\s*bars?\b",
        r"\b(\d+)\s*[- ]?bar\s*time stop\b",
        r"\bexit after\s*(\d+)\s*bars?\b",
        r"\bhold(?: for)?\s*(\d+)\s*bars?\b",
    ):
        value = _parse_int(text, pattern)
        if value is not None:
            return value
    return None


def _parse_session_close_exit(text: str) -> bool:
    return bool(re.search(r"\b(session close exit|exit on session close|close at session close|forced session[- ]close exit)\b", text, re.I))


def _parse_stop_loss(text: str, defaults: FormalizerDefaults) -> dict[str, object]:
    disabled_pattern = r"\b(no stop loss|disable stop loss|stop loss disabled|without stop loss)\b"
    if re.search(disabled_pattern, text, re.I):
        return {
            "stop_loss_style": "disabled",
            "stop_loss_pips": defaults.stop_loss_pips,
            "stop_loss_atr_period": defaults.stop_loss_atr_period,
            "stop_loss_atr_multiplier": defaults.stop_loss_atr_multiplier,
        }

    atr_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:x|\*)\s*atr(?:\((\d+)\))?\s*(?:stop(?: loss)?|initial stop|sl)?\b|\batr(?:\((\d+)\))?\s*(?:x|\*)\s*(\d+(?:\.\d+)?)\s*(?:stop(?: loss)?|initial stop|sl)?\b|\b(?:stop(?: loss)?|initial stop|sl)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:x|\*)\s*atr(?:\((\d+)\))?\b",
        text,
        re.I,
    )
    if atr_match:
        multiplier = atr_match.group(1) or atr_match.group(4) or atr_match.group(5)
        period = atr_match.group(2) or atr_match.group(3) or atr_match.group(6)
        return {
            "stop_loss_style": "atr",
            "stop_loss_pips": defaults.stop_loss_pips,
            "stop_loss_atr_period": int(period) if period is not None else defaults.stop_loss_atr_period,
            "stop_loss_atr_multiplier": float(multiplier),
        }

    pip_pattern = r"\b(\d+(?:\.\d+)?)\s*pips?\s*(?:stop loss|stop)\b|\b(?:stop loss|stop)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*pips?\b"
    match = re.search(pip_pattern, text, re.I)
    if match:
        raw = match.group(1) or match.group(2)
        return {
            "stop_loss_style": "fixed_pips",
            "stop_loss_pips": float(raw),
            "stop_loss_atr_period": defaults.stop_loss_atr_period,
            "stop_loss_atr_multiplier": defaults.stop_loss_atr_multiplier,
        }

    alt = _parse_number(text, r"\bsl\s*(\d+(?:\.\d+)?)\b")
    if alt is not None:
        return {
            "stop_loss_style": "fixed_pips",
            "stop_loss_pips": alt,
            "stop_loss_atr_period": defaults.stop_loss_atr_period,
            "stop_loss_atr_multiplier": defaults.stop_loss_atr_multiplier,
        }

    return {
        "stop_loss_style": defaults.stop_loss_style,
        "stop_loss_pips": defaults.stop_loss_pips,
        "stop_loss_atr_period": defaults.stop_loss_atr_period,
        "stop_loss_atr_multiplier": defaults.stop_loss_atr_multiplier,
    }


def _parse_take_profit(text: str, defaults: FormalizerDefaults) -> dict[str, object]:
    disabled_pattern = r"\b(no take profit|disable take profit|take profit disabled|without take profit)\b"
    if re.search(disabled_pattern, text, re.I):
        return {"take_profit_style": "disabled", "take_profit_pips": defaults.take_profit_pips}
    pip_pattern = r"\b(\d+(?:\.\d+)?)\s*pips?\s*(?:take profit|target)\b|\b(?:take profit|target)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*pips?\b"
    match = re.search(pip_pattern, text, re.I)
    if match:
        raw = match.group(1) or match.group(2)
        return {"take_profit_style": "fixed_pips", "take_profit_pips": float(raw)}
    alt = _parse_number(text, r"\btp\s*(\d+(?:\.\d+)?)\b")
    if alt is not None:
        return {"take_profit_style": "fixed_pips", "take_profit_pips": alt}
    return {"take_profit_style": defaults.take_profit_style, "take_profit_pips": defaults.take_profit_pips}


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
        payload["enabled"] = True
    if slippage_modes:
        payload["slippage_modes"] = list(dict.fromkeys(slippage_modes))
        payload["enabled"] = True
    if rsi_offsets_match:
        values = [int(chunk.strip()) for chunk in rsi_offsets_match.group(1).split(",") if chunk.strip()]
        payload["rsi_period_variants"] = values
        payload["enabled"] = True
    return payload


def _is_breakout_request(text: str) -> bool:
    breakout_patterns = (
        r"\bbreakout strategy\b",
        r"\bhighest high of the last\s+\d+\s+bars?\b",
        r"\blowest low of the last\s+\d+\s+bars?\b",
        r"\bbreaks? above\b",
        r"\bbreaks? below\b",
        r"\bcloses? above the highest high\b",
        r"\bcloses? below the lowest low\b",
    )
    return any(re.search(pattern, text, re.I) for pattern in breakout_patterns)


def _parse_breakout_lookback_bars(text: str) -> int | None:
    patterns = (
        r"\bhighest high of the last\s+(\d+)\s+bars?\b",
        r"\blowest low of the last\s+(\d+)\s+bars?\b",
        r"\blookback\s*(?:of|=|is)?\s*(\d+)\s*bars?\b",
    )
    for pattern in patterns:
        value = _parse_int(text, pattern)
        if value is not None:
            return value
    return None


def _parse_breakout_buffer_pips(text: str) -> float | None:
    patterns = (
        r"\bby\s*(\d+(?:\.\d+)?)\s*pips?\b",
        r"\b(\d+(?:\.\d+)?)\s*pip\s+buffer\b",
        r"\bbuffer\s*(?:of|=|is)?\s*(\d+(?:\.\d+)?)\s*pips?\b",
    )
    for pattern in patterns:
        value = _parse_number(text, pattern)
        if value is not None:
            return value
    return None


# ── Issue #4: expanded RSI phrasing extractors ────────────────────────────────

def _parse_rsi_period_expanded(text: str) -> int | None:
    """Additional RSI period phrasings: RSI(N), N-period RSI."""
    match = re.search(r"\brsi\((\d+)\)", text, re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)[- ]?period\s+rsi\b", text, re.I)
    if match:
        return int(match.group(1))
    return None


def _parse_entry_rsi_lte_expanded(text: str) -> float | None:
    """Expanded long-entry RSI threshold patterns (explicit directional keywords only)."""
    patterns = [
        # "enter [long] when/if RSI [is] [falls/drops] below/under N"
        r"\benter\s+(?:long\s+)?(?:when|if)\s+rsi\s+(?:is\s+)?(?:falls?\s+|drops?\s+)?(?:below|under)\s+(\d+(?:\.\d+)?)\b",
        # "go long when/if RSI [is] [falls/drops] below/under N"
        r"\bgo\s+long\s+(?:when|if)\s+rsi\s+(?:is\s+)?(?:falls?\s+|drops?\s+)?(?:below|under)\s+(\d+(?:\.\d+)?)\b",
        # "when RSI is below N, go long"
        r"\bwhen\s+rsi\s+is\s+(?:below|under)\s+(\d+(?:\.\d+)?)\s*,\s*go\s+long\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


def _parse_exit_rsi_gte_expanded(text: str) -> float | None:
    """Expanded long-exit RSI threshold patterns (explicit exit context only)."""
    patterns = [
        # "exit [long] when/if RSI [is] [rises/climbs] above/over N"
        r"\bexit\s+(?:long\s+)?(?:when|if)\s+rsi\s+(?:is\s+)?(?:rises?\s+|climbs?\s+)?(?:above|over)\s+(\d+(?:\.\d+)?)\b",
        # "when RSI is above N, exit long"
        r"\bwhen\s+rsi\s+is\s+(?:above|over)\s+(\d+(?:\.\d+)?)\s*,\s*exit\s+long\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


def _parse_short_entry_rsi_gte_expanded(text: str) -> float | None:
    """Expanded short-entry RSI threshold patterns (explicit short direction only)."""
    patterns = [
        # "go short when/if RSI [is] [rises/climbs] above/over N"
        r"\bgo\s+short\s+(?:when|if)\s+rsi\s+(?:is\s+)?(?:rises?\s+|climbs?\s+)?(?:above|over)\s+(\d+(?:\.\d+)?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


def _parse_short_exit_rsi_lte_expanded(text: str) -> float | None:
    """Expanded short-exit RSI threshold patterns (explicit short direction only)."""
    patterns = [
        # "exit short when/if RSI [is] [falls/drops] below/under N"
        r"\bexit\s+short\s+(?:when|if)\s+rsi\s+(?:is\s+)?(?:falls?\s+|drops?\s+)?(?:below|under)\s+(\d+(?:\.\d+)?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


def validate_supported_features(spec: StrategySpec) -> list[FormalizationIssue]:
    issues: list[FormalizationIssue] = []
    if spec.instrument.symbol not in _SUPPORTED_PAIR_MAP:
        issues.append(FormalizationIssue(field="pair", reason=f"Unsupported pair: {spec.instrument.symbol} is outside the deterministic v1.0 set.", nearest_supported="Use EURUSD or USDJPY."))
    if spec.rules.timeframe != "H1":
        issues.append(FormalizationIssue(field="timeframe", reason=f"Unsupported timeframe: {spec.rules.timeframe} is outside the v1.0 scope.", nearest_supported="Use timeframe=H1."))
    if spec.risk.account_ccy not in {spec.instrument.base_ccy, spec.instrument.quote_ccy}:
        issues.append(
            FormalizationIssue(
                field="account_currency",
                reason=(
                    f"Unsupported account currency: account_ccy={spec.risk.account_ccy} is outside the deterministic conversion scope for {spec.instrument.symbol}; "
                    "v1.0 only supports the pair base or quote currency."
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
    instrument = _SUPPORTED_PAIR_MAP.get(pair, _SUPPORTED_PAIR_MAP[defaults.symbol])
    if pair not in _SUPPORTED_PAIR_MAP:
        rejected_fields.append(FormalizationIssue(field="pair", reason=f"Pair {pair} is not supported by the deterministic formalizer.", nearest_supported="Use EURUSD or USDJPY."))

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

    strategy_type = "breakout" if _is_breakout_request(text) else defaults.strategy_type
    recognized_fields["strategy_type"] = strategy_type

    sessions = _parse_sessions(text)
    recognized_fields["allowed_sessions"] = sessions

    breakout_lookback_bars = _parse_breakout_lookback_bars(text)
    breakout_buffer_pips = _parse_breakout_buffer_pips(text)
    recognized_fields["breakout"] = {
        "breakout_lookback_bars": breakout_lookback_bars,
        "breakout_buffer_pips": breakout_buffer_pips,
    }

    rsi_period = (
        _parse_int(text, r"\brsi(?: period)?\s*(?:of|=|is)?\s*(\d+)\b")
        or _parse_rsi_period_expanded(text)
        or defaults.rsi_period
    )
    entry_rsi_lte = (
        _parse_number(text, r"\b(?:entry|buy|long entry)\s*rsi\s*(?:<=|below|under|at most)\s*(\d+(?:\.\d+)?)\b")
        or _parse_entry_rsi_lte_expanded(text)
        or defaults.entry_rsi_lte
    )
    exit_rsi_gte = (
        _parse_number(text, r"\b(?:exit|long exit|close long)\s*rsi\s*(?:>=|above|over|at least)\s*(\d+(?:\.\d+)?)\b")
        or _parse_exit_rsi_gte_expanded(text)
        or defaults.exit_rsi_gte
    )
    short_entry_rsi_gte = (
        _parse_number(text, r"\b(?:short entry|sell entry)\s*rsi\s*(?:>=|above|over|at least)\s*(\d+(?:\.\d+)?)\b")
        or _parse_short_entry_rsi_gte_expanded(text)
        or defaults.short_entry_rsi_gte
    )
    short_exit_rsi_lte = (
        _parse_number(text, r"\b(?:short exit|cover|close short)\s*rsi\s*(?:<=|below|under|at most)\s*(\d+(?:\.\d+)?)\b")
        or _parse_short_exit_rsi_lte_expanded(text)
        or defaults.short_exit_rsi_lte
    )
    recognized_fields["rsi"] = {
        "rsi_period": rsi_period,
        "entry_rsi_lte": entry_rsi_lte,
        "exit_rsi_gte": exit_rsi_gte,
        "short_entry_rsi_gte": short_entry_rsi_gte,
        "short_exit_rsi_lte": short_exit_rsi_lte,
    }

    time_stop_bars = _parse_time_stop_bars(text) or defaults.time_stop_bars
    exit_on_session_close = _parse_session_close_exit(text) or defaults.exit_on_session_close
    recognized_fields["deterministic_exits"] = {
        "time_stop_bars": time_stop_bars,
        "exit_on_session_close": exit_on_session_close,
    }

    stop_payload = _parse_stop_loss(text, defaults)
    take_profit_payload = _parse_take_profit(text, defaults)
    recognized_fields["stop_take_profit"] = {**stop_payload, **take_profit_payload}

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

    strategy_prefix = "formalized_breakout" if strategy_type == "breakout" else defaults.strategy_name_prefix
    strategy_name = f"{strategy_prefix}_{_slugify(pair.lower())}_{_slugify(direction)}"
    recognized_fields["strategy_name"] = strategy_name

    try:
        spec = StrategySpec(
            strategy_name=strategy_name,
            instrument=instrument,
            risk=RiskSpec(initial_equity=initial_equity, risk_per_trade_fraction=risk_fraction, account_ccy=account_ccy),
            rules=StrategyRuleAdapter.validate_python({
                "strategy_type": strategy_type,
                "timeframe": timeframe,
                "direction": direction,
                "allowed_sessions": sessions,
                "rsi_period": rsi_period,
                "entry_rsi_lte": entry_rsi_lte,
                "exit_rsi_gte": exit_rsi_gte,
                "short_entry_rsi_gte": short_entry_rsi_gte,
                "short_exit_rsi_lte": short_exit_rsi_lte,
                "breakout_lookback_bars": breakout_lookback_bars,
                "breakout_buffer_pips": breakout_buffer_pips,
                "time_stop_bars": time_stop_bars,
                "exit_on_session_close": exit_on_session_close,
                "stop_loss_style": str(stop_payload["stop_loss_style"]),
                "stop_loss_pips": float(stop_payload["stop_loss_pips"]),
                "stop_loss_atr_period": int(stop_payload["stop_loss_atr_period"]),
                "stop_loss_atr_multiplier": float(stop_payload["stop_loss_atr_multiplier"]),
                "take_profit_style": str(take_profit_payload["take_profit_style"]),
                "take_profit_pips": float(take_profit_payload["take_profit_pips"]),
            }),
            window=BacktestWindow(start_date=defaults.start_date, end_date=defaults.end_date),
            robustness=RobustnessSpec(**robustness_payload),
            notes="Formalized deterministically from a natural-language request. Defaults may have been applied where the request was underspecified.",
        )
    except ValidationError as exc:
        return FormalizationOutcome(
            request_text=request_text,
            notes=FormalizerNotes(
                status="rejected",
                assumptions=assumptions + [f"Default backtest window applied: {defaults.start_date} to {defaults.end_date}."],
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
