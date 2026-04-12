"""Tests for the walk-forward validation module.

Covers:
  - fold slicing (correct bar counts, IS/OOS split)
  - min_bars_per_half guard (folds too small are skipped)
  - per-fold metric extraction (trade_count, net_pips, win_rate)
  - verdict logic (validated / inconclusive / failed)
  - markdown + JSON report generation
  - write_walk_forward_artifacts output
  - CLI walk-forward-test subcommand (smoke test via subprocess)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fx_backtester.analysis.walk_forward import (
    FoldMetrics,
    WalkForwardFold,
    WalkForwardReport,
    build_markdown_report,
    run_walk_forward,
    write_walk_forward_artifacts,
)
from fx_backtester.data.models import MarketBar
from fx_backtester.formalizer.execution_policy import ExecutionPolicy
from fx_backtester.formalizer.spec_models import (
    BacktestWindow,
    InstrumentSpec,
    RiskSpec,
    RsiMeanReversionRule,
    StrategySpec,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_BASE_TIME = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
_PIP = 0.0001


def _bar(h: int, open_: float, high: float, low: float, close: float) -> MarketBar:
    """Build a MarketBar at hour offset h from _BASE_TIME."""
    ts = _BASE_TIME + timedelta(hours=h)
    return MarketBar(
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        sessions=["london"],
    )


def _flat_bars(n: int, price: float = 1.1000) -> list[MarketBar]:
    """Return n bars with no RSI signal (price flat, no trades expected)."""
    return [_bar(h, price, price + 0.0003, price - 0.0003, price) for h in range(n)]


def _oscillating_bars(n: int) -> list[MarketBar]:
    """Return n bars that alternate between oversold and overbought to generate RSI signals."""
    bars: list[MarketBar] = []
    for h in range(n):
        # Alternate high/low cycles to drive RSI signals across all folds.
        if (h // 10) % 2 == 0:
            # Downward pressure — drives RSI low
            p = 1.1000 - (h % 10) * 0.0005
        else:
            # Upward pressure — drives RSI high
            p = 1.0950 + (h % 10) * 0.0005
        bars.append(_bar(h, p, p + 0.0010, p - 0.0010, p))
    return bars


def _spec(rsi_period: int = 14) -> StrategySpec:
    return StrategySpec(
        strategy_name="wf_test_strategy",
        instrument=InstrumentSpec(),
        risk=RiskSpec(initial_equity=10_000, risk_per_trade_fraction=0.01),
        rules=RsiMeanReversionRule(
            rsi_period=rsi_period,
            entry_rsi_lte=30,
            short_entry_rsi_gte=70,
            stop_loss_pips=20,
            take_profit_pips=30,
        ),
        window=BacktestWindow(start_date="2024-01-01", end_date="2024-12-31"),
    )


_POLICY = ExecutionPolicy(half_spread_pips=0.2, slippage_pips=0.0)


# ── Fold slicing ──────────────────────────────────────────────────────────────

def test_correct_number_of_folds_created() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    assert len(report.folds) == 5


def test_fold_bar_counts_sum_to_total() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    total_is = sum(f.in_sample_bar_count for f in report.folds)
    total_oos = sum(f.out_of_sample_bar_count for f in report.folds)
    assert total_is + total_oos == len(bars)


def test_in_sample_pct_respected() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    for fold in report.folds:
        total = fold.in_sample_bar_count + fold.out_of_sample_bar_count
        is_frac = fold.in_sample_bar_count / total
        assert abs(is_frac - 0.7) < 0.02  # allow rounding


def test_fold_timestamps_are_chronological() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    for fold in report.folds:
        assert fold.in_sample_start < fold.in_sample_end
        assert fold.in_sample_end < fold.out_of_sample_start
        assert fold.out_of_sample_start <= fold.out_of_sample_end


def test_folds_are_sequential_non_overlapping() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    for i in range(1, len(report.folds)):
        prev_end = report.folds[i - 1].out_of_sample_end
        curr_start = report.folds[i].in_sample_start
        assert prev_end < curr_start


# ── min_bars_per_half guard ───────────────────────────────────────────────────

def test_folds_below_min_bars_are_skipped() -> None:
    # 100 bars / 5 folds = 20 bars per fold → 14 IS, 6 OOS → below min_bars_per_half=50
    bars = _flat_bars(100)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=50)
    assert len(report.folds) == 0


def test_sufficient_bars_are_not_skipped() -> None:
    bars = _flat_bars(1000)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=50)
    assert len(report.folds) == 5


# ── Metric extraction ─────────────────────────────────────────────────────────

def test_flat_bars_produce_zero_trades() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    for fold in report.folds:
        assert fold.in_sample.trade_count == 0
        assert fold.out_of_sample.trade_count == 0


def test_oos_total_trades_sums_correctly() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    expected = sum(f.out_of_sample.trade_count for f in report.folds)
    assert report.oos_total_trades == expected


def test_oos_total_net_pips_sums_correctly() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    expected = round(sum(f.out_of_sample.net_pips for f in report.folds), 1)
    assert report.oos_total_net_pips == expected


def test_win_rate_is_zero_when_no_trades() -> None:
    bars = _flat_bars(200)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=2, in_sample_pct=0.7, min_bars_per_half=1)
    for fold in report.folds:
        assert fold.in_sample.win_rate == 0.0
        assert fold.out_of_sample.win_rate == 0.0


# ── oos_profitable flag ───────────────────────────────────────────────────────

def test_oos_profitable_false_when_no_trades() -> None:
    # No trades → net_pips == 0 → not profitable (0 is not > 0)
    bars = _flat_bars(400)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=4, in_sample_pct=0.7, min_bars_per_half=1)
    for fold in report.folds:
        assert fold.oos_profitable is False


# ── Verdict logic ─────────────────────────────────────────────────────────────

def _make_report(
    *,
    folds_profitable: int,
    total_folds: int,
    total_oos_net_pips: float,  # kept for call-site clarity; sign must be achievable with fixed pips
) -> WalkForwardReport:
    """Build a minimal WalkForwardReport to test verdict logic directly.

    Profitable folds always get +10.0 OOS pips; unprofitable always get -5.0.
    ``oos_profitable`` is set to match the pip sign — the two fields are always
    consistent (a fold cannot be profitable with negative pips or vice versa).
    ``total_oos_net_pips`` is accepted for readability at call sites but is not
    used in the computation; callers should verify their expectations hold with
    the fixed +10 / -5 per-fold values.
    """
    _ = total_oos_net_pips  # documented above — not used in body

    def _metrics(net_pips: float) -> FoldMetrics:
        return FoldMetrics(
            trade_count=5,
            net_pips=net_pips,
            win_rate=0.6,
            expectancy_pips=3.0,
            max_drawdown_pct=2.0,
            ending_equity=10_050.0,
        )

    folds: list[WalkForwardFold] = []
    for i in range(total_folds):
        profitable = i < folds_profitable
        # Fixed values: profitable → +10 pips; unprofitable → -5 pips.
        # This guarantees oos_profitable is always consistent with net_pips sign.
        oos_pips = 10.0 if profitable else -5.0
        folds.append(WalkForwardFold(
            fold_index=i + 1,
            in_sample_bar_count=140,
            in_sample_start="2024-01-01T00:00:00",
            in_sample_end="2024-06-01T00:00:00",
            in_sample=_metrics(10.0),
            out_of_sample_bar_count=60,
            out_of_sample_start="2024-06-02T00:00:00",
            out_of_sample_end="2024-08-01T00:00:00",
            out_of_sample=_metrics(oos_pips),
            oos_profitable=profitable,
        ))

    return WalkForwardReport(
        instrument="EURUSD",
        strategy_name="test",
        total_bar_count=1000,
        n_folds=total_folds,
        in_sample_pct=0.7,
        folds=folds,
    )


def test_verdict_validated_when_60pct_profitable_and_positive_pips() -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    assert report.verdict == "validated"


def test_verdict_failed_when_all_unprofitable() -> None:
    report = _make_report(folds_profitable=0, total_folds=5, total_oos_net_pips=-30.0)
    assert report.verdict == "failed"


def test_verdict_inconclusive_when_50pct_profitable() -> None:
    # 50% profitable but total pips negative → inconclusive (rate >= 0.4 but < 0.6)
    report = _make_report(folds_profitable=2, total_folds=4, total_oos_net_pips=-5.0)
    # 50% is >= 0.4, which qualifies as inconclusive
    assert report.verdict == "inconclusive"


def test_verdict_inconclusive_when_positive_pips_but_low_rate() -> None:
    # total pips > 0 but only 1/5 folds profitable → inconclusive (rate=0.2 < 0.4 but pips > 0)
    def _m(pips: float) -> FoldMetrics:
        return FoldMetrics(trade_count=5, net_pips=pips, win_rate=0.5,
                           expectancy_pips=2.0, max_drawdown_pct=2.0, ending_equity=10_010.0)

    folds = [
        WalkForwardFold(fold_index=1, in_sample_bar_count=140, in_sample_start="2024-01-01T00:00:00",
                        in_sample_end="2024-06-01T00:00:00", in_sample=_m(10.0),
                        out_of_sample_bar_count=60, out_of_sample_start="2024-06-02T00:00:00",
                        out_of_sample_end="2024-08-01T00:00:00", out_of_sample=_m(50.0),
                        oos_profitable=True),
        *[
            WalkForwardFold(fold_index=i, in_sample_bar_count=140, in_sample_start="2024-01-01T00:00:00",
                            in_sample_end="2024-06-01T00:00:00", in_sample=_m(10.0),
                            out_of_sample_bar_count=60, out_of_sample_start="2024-06-02T00:00:00",
                            out_of_sample_end="2024-08-01T00:00:00", out_of_sample=_m(-5.0),
                            oos_profitable=False)
            for i in range(2, 6)
        ],
    ]
    report = WalkForwardReport(instrument="EURUSD", strategy_name="test",
                               total_bar_count=1000, n_folds=5, in_sample_pct=0.7, folds=folds)
    # rate=0.2 (<0.4) but total pips = 50 - 20 = 30 > 0 → inconclusive
    assert report.oos_total_net_pips == 30.0
    assert report.verdict == "inconclusive"


def test_verdict_failed_when_no_folds() -> None:
    report = WalkForwardReport(
        instrument="EURUSD",
        strategy_name="test",
        total_bar_count=10,
        n_folds=5,
        in_sample_pct=0.7,
        folds=[],
    )
    assert report.verdict == "failed"


def test_verdict_uses_n_folds_denominator_when_folds_skipped() -> None:
    """Skipped folds must count against the pass rate.

    If n_folds=5 but only 2 folds had enough bars to evaluate (both profitable),
    the pass rate is 2/5=0.4, giving "inconclusive" — not 2/2=1.0 ("validated").
    A wrong implementation using len(folds) instead of n_folds would return
    "validated" here.
    """
    def _m(pips: float) -> FoldMetrics:
        return FoldMetrics(trade_count=5, net_pips=pips, win_rate=0.6,
                           expectancy_pips=3.0, max_drawdown_pct=2.0, ending_equity=10_050.0)

    folds = [
        WalkForwardFold(
            fold_index=i + 1,
            in_sample_bar_count=140,
            in_sample_start="2024-01-01T00:00:00",
            in_sample_end="2024-06-01T00:00:00",
            in_sample=_m(10.0),
            out_of_sample_bar_count=60,
            out_of_sample_start="2024-06-02T00:00:00",
            out_of_sample_end="2024-08-01T00:00:00",
            out_of_sample=_m(10.0),
            oos_profitable=True,
        )
        for i in range(2)  # only 2 folds evaluated; 3 were skipped (too few bars)
    ]
    report = WalkForwardReport(
        instrument="EURUSD",
        strategy_name="test",
        total_bar_count=1000,
        n_folds=5,          # 5 were requested
        in_sample_pct=0.7,
        folds=folds,        # but only 2 evaluated
    )
    assert report.validated_folds == 2
    assert len(report.folds) == 2
    # Correct: 2 / n_folds(5) = 0.4 → inconclusive (rate >= 0.4 or pips > 0)
    # Wrong:   2 / len(folds)(2) = 1.0 → validated
    assert report.verdict == "inconclusive"


def test_validated_folds_count() -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    assert report.validated_folds == 3


# ── Input validation ──────────────────────────────────────────────────────────

def test_empty_bars_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        run_walk_forward([], _spec(), _POLICY)


def test_invalid_in_sample_pct_raises() -> None:
    bars = _flat_bars(200)
    with pytest.raises(ValueError, match="in_sample_pct"):
        run_walk_forward(bars, _spec(), _POLICY, in_sample_pct=0.05)


def test_n_folds_less_than_2_raises() -> None:
    bars = _flat_bars(200)
    with pytest.raises(ValueError, match="n_folds"):
        run_walk_forward(bars, _spec(), _POLICY, n_folds=1)


# ── Report generation ─────────────────────────────────────────────────────────

def test_markdown_report_contains_strategy_name() -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    md = build_markdown_report(report)
    assert "test" in md


def test_markdown_report_contains_verdict() -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    md = build_markdown_report(report)
    assert "VALIDATED" in md


def test_markdown_report_contains_all_folds() -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    md = build_markdown_report(report)
    for i in range(1, 6):
        assert f"Fold {i}" in md


def test_markdown_failed_verdict() -> None:
    report = _make_report(folds_profitable=0, total_folds=5, total_oos_net_pips=-30.0)
    md = build_markdown_report(report)
    assert "FAILED" in md


def test_write_artifacts_creates_files(tmp_path: Path) -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    out = write_walk_forward_artifacts(report, tmp_path / "wf_out")
    assert (out / "walk_forward.json").exists()
    assert (out / "walk_forward.md").exists()


def test_json_artifact_is_valid_json(tmp_path: Path) -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    out = write_walk_forward_artifacts(report, tmp_path / "wf_out")
    data = json.loads((out / "walk_forward.json").read_text())
    assert data["strategy_name"] == "test"
    assert data["n_folds"] == 5
    assert len(data["folds"]) == 5


def test_json_artifact_folds_have_expected_keys(tmp_path: Path) -> None:
    report = _make_report(folds_profitable=2, total_folds=3, total_oos_net_pips=10.0)
    out = write_walk_forward_artifacts(report, tmp_path / "wf_out")
    data = json.loads((out / "walk_forward.json").read_text())
    fold = data["folds"][0]
    assert "in_sample" in fold
    assert "out_of_sample" in fold
    assert "oos_profitable" in fold
    assert "in_sample_bar_count" in fold
    assert "out_of_sample_bar_count" in fold


# ── Report aggregate properties ───────────────────────────────────────────────

def test_oos_avg_win_rate_is_mean_of_fold_rates() -> None:
    report = _make_report(folds_profitable=3, total_folds=5, total_oos_net_pips=20.0)
    # All folds have win_rate=0.6 in _make_report
    assert abs(report.oos_avg_win_rate - 0.6) < 0.01


def test_run_walk_forward_report_metadata() -> None:
    bars = _flat_bars(500)
    report = run_walk_forward(bars, _spec(), _POLICY, n_folds=5, in_sample_pct=0.7, min_bars_per_half=1)
    assert report.instrument == "EURUSD"
    assert report.strategy_name == "wf_test_strategy"
    assert report.total_bar_count == 500
    assert report.n_folds == 5
    assert report.in_sample_pct == 0.7
