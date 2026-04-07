"""Walk-forward validation for strategy robustness testing.

Divides the bar history into N sequential folds.  Within each fold,
the first ``in_sample_pct`` of bars form the *in-sample* training period
and the remainder form the *out-of-sample* validation period.

The backtest engine is run independently on each half — no parameter
optimisation is performed; the same fixed spec is evaluated on each window.
This answers the question: "Does this strategy work consistently across
different market regimes, or did it just happen to fit one period?"

Verdict logic
-------------
- **validated**    — ≥60 % of folds are OOS-profitable AND total OOS net pips > 0
- **inconclusive** — ≥40 % of folds profitable OR total OOS net pips > 0
- **failed**       — neither condition met
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from fx_backtester.data.models import MarketBar
from fx_backtester.engine.backtest import BacktestResult, run_backtest
from fx_backtester.engine.pipeline import build_signal_pipeline
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import StrategySpec


# ── Metric snapshot ───────────────────────────────────────────────────────────


class FoldMetrics(BaseModel):
    """Key performance metrics for one half (IS or OOS) of a fold."""

    trade_count: int
    net_pips: float
    win_rate: float          # fraction 0-1; 0.0 when no closed trades
    expectancy_pips: float
    max_drawdown_pct: float  # plain percent, e.g. 5.51 = 5.51%
    ending_equity: float


def _fold_metrics(result: BacktestResult) -> FoldMetrics:
    closed = [t for t in result.trades if t.pnl_pips is not None]
    wins = sum(1 for t in closed if (t.pnl_pips or 0.0) > 0)
    win_rate = round(wins / len(closed), 4) if closed else 0.0
    return FoldMetrics(
        trade_count=result.trade_count,
        net_pips=round(result.metrics.net_pips, 1),
        win_rate=win_rate,
        expectancy_pips=round(result.metrics.expectancy_pips, 2),
        max_drawdown_pct=round(result.metrics.max_drawdown_pct, 2),
        ending_equity=round(result.ending_equity, 2),
    )


# ── Per-fold result ───────────────────────────────────────────────────────────


class WalkForwardFold(BaseModel):
    fold_index: int                  # 1-based for display
    in_sample_bar_count: int
    in_sample_start: str             # ISO timestamp of first IS bar
    in_sample_end: str               # ISO timestamp of last IS bar
    in_sample: FoldMetrics

    out_of_sample_bar_count: int
    out_of_sample_start: str
    out_of_sample_end: str
    out_of_sample: FoldMetrics

    oos_profitable: bool             # net_pips > 0 in out-of-sample period


# ── Aggregate report ──────────────────────────────────────────────────────────


class WalkForwardReport(BaseModel):
    instrument: str
    strategy_name: str
    total_bar_count: int
    n_folds: int
    in_sample_pct: float
    folds: list[WalkForwardFold]

    # Aggregate OOS metrics (computed properties, not stored)
    @property
    def validated_folds(self) -> int:
        return sum(1 for f in self.folds if f.oos_profitable)

    @property
    def oos_total_trades(self) -> int:
        return sum(f.out_of_sample.trade_count for f in self.folds)

    @property
    def oos_total_net_pips(self) -> float:
        return round(sum(f.out_of_sample.net_pips for f in self.folds), 1)

    @property
    def oos_avg_win_rate(self) -> float:
        rates = [f.out_of_sample.win_rate for f in self.folds if f.out_of_sample.trade_count > 0]
        return round(sum(rates) / len(rates), 4) if rates else 0.0

    @property
    def verdict(self) -> Literal["validated", "inconclusive", "failed"]:
        if not self.folds:
            return "failed"
        rate = self.validated_folds / len(self.folds)
        total_pips = self.oos_total_net_pips
        if rate >= 0.6 and total_pips > 0:
            return "validated"
        if rate >= 0.4 or total_pips > 0:
            return "inconclusive"
        return "failed"


# ── Core runner ───────────────────────────────────────────────────────────────


def _run_on_slice(
    bars: list[MarketBar],
    spec: StrategySpec,
    policy: ExecutionPolicy,
) -> BacktestResult:
    """Run the full signal pipeline + backtest on an arbitrary slice of bars."""
    prepared = build_signal_pipeline(market_bars=bars, spec=spec)
    return run_backtest(bars=prepared.bars, spec=spec, policy=policy)


def run_walk_forward(
    bars: list[MarketBar],
    spec: StrategySpec,
    policy: ExecutionPolicy,
    *,
    n_folds: int = 5,
    in_sample_pct: float = 0.7,
    min_bars_per_half: int = 50,
) -> WalkForwardReport:
    """Run sequential (non-overlapping) walk-forward validation across ``n_folds`` windows.

    The bar history is split into ``n_folds`` non-overlapping sequential windows.
    Each window is then divided into an in-sample (IS) and out-of-sample (OOS) half.
    The strategy is evaluated on each OOS half with the same fixed spec — no
    optimisation is performed.  This is a sequential split, not a rolling/anchored
    window — fold boundaries are equally spaced across the full history.

    Parameters
    ----------
    bars:
        Full chronologically-ordered bar history.
    spec:
        Strategy spec — unchanged across all folds (no optimisation).
    policy:
        Execution policy — unchanged across all folds.
    n_folds:
        How many sequential windows to create.
    in_sample_pct:
        Fraction of each window that is in-sample (default 0.70 = 70 %).
    min_bars_per_half:
        Minimum bars required in each IS or OOS half.  Folds that fall below
        this threshold are skipped (too few signals to be meaningful).
    """
    if not bars:
        raise ValueError("bars must not be empty")
    if not (0.1 <= in_sample_pct <= 0.9):
        raise ValueError("in_sample_pct must be between 0.1 and 0.9")
    if n_folds < 2:
        raise ValueError("n_folds must be at least 2")

    total = len(bars)
    fold_size = total // n_folds
    folds: list[WalkForwardFold] = []

    for i in range(n_folds):
        fold_start = i * fold_size
        fold_end = (i + 1) * fold_size if i < n_folds - 1 else total
        window = bars[fold_start:fold_end]

        is_end = round(len(window) * in_sample_pct)
        is_bars = window[:is_end]
        oos_bars = window[is_end:]

        # Skip folds that are too small to produce meaningful signals.
        if len(is_bars) < min_bars_per_half or len(oos_bars) < min_bars_per_half:
            continue

        is_result = _run_on_slice(is_bars, spec, policy)
        oos_result = _run_on_slice(oos_bars, spec, policy)

        folds.append(WalkForwardFold(
            fold_index=i + 1,
            in_sample_bar_count=len(is_bars),
            in_sample_start=is_bars[0].timestamp.isoformat(),
            in_sample_end=is_bars[-1].timestamp.isoformat(),
            in_sample=_fold_metrics(is_result),
            out_of_sample_bar_count=len(oos_bars),
            out_of_sample_start=oos_bars[0].timestamp.isoformat(),
            out_of_sample_end=oos_bars[-1].timestamp.isoformat(),
            out_of_sample=_fold_metrics(oos_result),
            oos_profitable=oos_result.metrics.net_pips > 0,
        ))

    return WalkForwardReport(
        instrument=spec.instrument.symbol,
        strategy_name=spec.strategy_name,
        total_bar_count=total,
        n_folds=n_folds,
        in_sample_pct=in_sample_pct,
        folds=folds,
    )


# ── Markdown report ───────────────────────────────────────────────────────────

_VERDICT_LABEL = {
    "validated": "VALIDATED",
    "inconclusive": "INCONCLUSIVE",
    "failed": "FAILED",
}

_VERDICT_NOTE = {
    "validated": (
        "≥60 % of out-of-sample folds were profitable and total OOS net pips > 0.  "
        "The strategy shows consistent edge across multiple unseen market regimes."
    ),
    "inconclusive": (
        "Results are mixed.  The strategy works in some regimes but not others.  "
        "Consider narrowing the entry filter or extending the data window."
    ),
    "failed": (
        "Fewer than 40 % of OOS folds were profitable and total OOS net pips ≤ 0.  "
        "The backtest results are likely curve-fitted to the in-sample period."
    ),
}


def _metrics_row(label: str, m: FoldMetrics) -> str:
    return (
        f"| {label:<13} "
        f"| {m.trade_count:>6} "
        f"| {m.net_pips:>+9.1f} "
        f"| {m.win_rate:>7.0%} "
        f"| {m.expectancy_pips:>+9.2f} "
        f"| {m.max_drawdown_pct:>8.2f}% |"
    )


def build_markdown_report(report: WalkForwardReport) -> str:
    verdict = report.verdict
    lines: list[str] = []
    lines.append(f"# Walk-Forward Validation: {report.strategy_name}\n")
    lines.append(
        f"**Instrument:** {report.instrument}  "
        f"|  **Total bars:** {report.total_bar_count}  "
        f"|  **Folds:** {len(report.folds)} of {report.n_folds} evaluated  "
        f"|  **IS split:** {report.in_sample_pct:.0%} / {1 - report.in_sample_pct:.0%}\n"
    )

    lines.append(f"## Verdict: {_VERDICT_LABEL[verdict]}\n")
    lines.append(f"> {_VERDICT_NOTE[verdict]}\n")
    lines.append(
        f"**OOS summary** — {report.validated_folds}/{len(report.folds)} folds profitable  "
        f"|  Total OOS net pips: **{report.oos_total_net_pips:+.1f}**  "
        f"|  Avg OOS win rate: **{report.oos_avg_win_rate:.0%}**  "
        f"|  Total OOS trades: **{report.oos_total_trades}**\n"
    )

    lines.append("---\n")

    for fold in report.folds:
        oos_flag = "profitable" if fold.oos_profitable else "unprofitable"
        lines.append(f"## Fold {fold.fold_index}  —  OOS: {oos_flag}\n")

        lines.append(
            f"- **In-sample:** {fold.in_sample_start[:10]} → {fold.in_sample_end[:10]}"
            f"  ({fold.in_sample_bar_count} bars)\n"
            f"- **Out-of-sample:** {fold.out_of_sample_start[:10]} → {fold.out_of_sample_end[:10]}"
            f"  ({fold.out_of_sample_bar_count} bars)\n"
        )

        lines.append("| Period        | Trades | Net pips | Win rate | Expectancy | Max DD   |")
        lines.append("|---------------|--------|----------|----------|------------|----------|")
        lines.append(_metrics_row("In-sample", fold.in_sample))
        lines.append(_metrics_row("Out-of-sample", fold.out_of_sample))
        lines.append("")

    return "\n".join(lines)


# ── Artifact writer ───────────────────────────────────────────────────────────


def write_walk_forward_artifacts(report: WalkForwardReport, output_dir: Path) -> Path:
    """Write ``walk_forward.json`` and ``walk_forward.md`` to ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "walk_forward.json"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    md_path = output_dir / "walk_forward.md"
    md_path.write_text(build_markdown_report(report), encoding="utf-8")

    return output_dir
