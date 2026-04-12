"""
Automated pipeline: fetch → backtest → walk-forward → scan-levels.

Runs for one instrument at a time. Call twice (NQ then ES) from cron.

Usage:
    python scripts/run_pipeline.py 180 NQ
    python scripts/run_pipeline.py 180 ES

Results saved to:
    results/auto/NQ/   ← AI pipeline, never mix with manual
    results/auto/ES/
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Key levels the pipeline always scans — saved in summary for transparency
AUTO_LEVEL_TYPES = [
    "prev_day_highs", "prev_day_lows",
    "prev_week_highs", "prev_week_lows",
    "session_highs", "session_lows",
]

SPEC_TEMPLATE = ROOT / "examples" / "eurusd_rsi_fixed_pips_spec.json"


def run(cmd: list[str]) -> None:
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def last_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


_FUTURES_PARAMS = {
    # lot_size_units = contract $ multiplier per point.
    # NQ: $20/pt × 0.25 pt/pip  →  lot_size_units=20  →  pip_value=$5/pip per "lot"
    # ES: $50/pt × 0.25 pt/pip  →  lot_size_units=50  →  pip_value=$12.50/pip per "lot"
    # stop/tp in "pips" (1 pip = 0.25 NQ/ES points)
    #
    # Parameters below are Bayesian-optimised (Optuna TPE, 150 trials) on 70% in-sample
    # data from the live dataset (Oct 2025 – Apr 2026).  Best composite score:
    #   score = Sharpe + (net_pips/1000) − (max_drawdown_pct/100)
    #
    # NQ sizing: 100k × 1% = $1,000 risk; 85 pips × $5/pip = $425/lot → 2 contracts ✓
    # ES sizing: 100k × 1% = $1,000 risk; 49 pips × $12.50/pip = $612.50/lot → 1 contract ✓
    "NQ": {
        "pip_size": 0.25,
        "lot_size_units": 20,
        "stop_loss_pips": 85,        # 21.25 NQ points — tight stop, let runners run
        "take_profit_pips": 753,     # 188.25 NQ points — high R:R ~8.9:1
        "direction": "both",
        "rsi_period": 16,
        "entry_rsi_lte": 24,         # only truly oversold RSI triggers longs
        "short_entry_rsi_gte": 57,   # NQ bullish bias; shorts need less extreme RSI
        "exit_rsi_gte": 50,
        "short_exit_rsi_lte": 50,
    },
    "ES": {
        "pip_size": 0.25,
        "lot_size_units": 50,
        "stop_loss_pips": 49,        # 12.25 ES points — tight stop
        "take_profit_pips": 344,     # 86 ES points — R:R ~7:1
        "direction": "both",
        "rsi_period": 21,
        "entry_rsi_lte": 29,         # oversold entry threshold
        "short_entry_rsi_gte": 65,   # overbought short entry
        "exit_rsi_gte": 50,
        "short_exit_rsi_lte": 50,
    },
}

def build_live_spec(out_path: Path, instrument: str, start: date, end: date) -> None:
    raw = json.loads(SPEC_TEMPLATE.read_text())
    raw["window"]["start_date"] = start.isoformat()
    raw["window"]["end_date"]   = end.isoformat()
    raw["strategy_name"]        = f"auto_{instrument.lower()}_{end.isoformat()}"
    if instrument in _FUTURES_PARAMS:
        fp = _FUTURES_PARAMS[instrument]
        raw["instrument"]["symbol"]         = instrument
        raw["instrument"]["pip_size"]       = fp["pip_size"]
        raw["instrument"]["lot_size_units"] = fp["lot_size_units"]
        raw["instrument"]["min_lot_step"]   = 1.0     # futures trade in whole contracts only
        raw["instrument"]["base_ccy"]       = "USD"   # NQ/ES are USD-denominated
        raw["instrument"]["quote_ccy"]      = "USD"
        raw["risk"]["initial_equity"]       = 100_000  # min capital for 1 NQ/ES contract at 1% risk
        raw["rules"]["stop_loss_pips"]      = fp["stop_loss_pips"]
        raw["rules"]["take_profit_pips"]    = fp["take_profit_pips"]
        raw["rules"]["direction"]           = fp["direction"]
        raw["rules"]["rsi_period"]          = fp["rsi_period"]
        raw["rules"]["entry_rsi_lte"]       = fp["entry_rsi_lte"]
        raw["rules"]["short_entry_rsi_gte"] = fp["short_entry_rsi_gte"]
        raw["rules"]["exit_rsi_gte"]        = fp["exit_rsi_gte"]
        raw["rules"]["short_exit_rsi_lte"]  = fp["short_exit_rsi_lte"]
        raw["notes"] = f"Auto-generated {instrument} RSI futures template — bidirectional, futures sizing."
    out_path.write_text(json.dumps(raw, indent=2))


def run_instrument(instrument: str, lookback: int) -> None:
    out_dir = ROOT / "results" / "auto" / instrument
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "walk_forward").mkdir(exist_ok=True)
    (out_dir / "level_study").mkdir(exist_ok=True)
    (out_dir / "history").mkdir(exist_ok=True)

    data_csv  = out_dir / "latest_data.csv"
    live_spec = out_dir / "live_spec.json"

    end   = last_weekday(date.today() - timedelta(days=1))
    start = end - timedelta(days=lookback)

    print(f"\n{'='*50}")
    print(f"Running pipeline: {instrument}  {start} → {end}")
    print(f"{'='*50}")

    # 1. Build spec
    build_live_spec(live_spec, instrument, start, end)

    # 2. Fetch data
    try:
        run([
            "fx-backtester", "fetch-data",
            "--instrument", instrument,
            "--start", start.isoformat(),
            "--end",   end.isoformat(),
            "--output", str(data_csv),
            "--cache-dir", str(ROOT / "data" / "cache"),
        ])
    except subprocess.CalledProcessError:
        print(f"WARNING: fetch failed for {instrument} — skipping.")
        return

    if not data_csv.exists() or data_csv.stat().st_size < 100:
        print(f"WARNING: empty CSV for {instrument} — skipping.")
        return

    # 3. Backtest
    run([
        "fx-backtester", "run-backtest",
        str(live_spec), str(data_csv),
        "--repo-root", str(ROOT),
    ])

    # 4. Walk-forward
    run([
        "fx-backtester", "walk-forward-test",
        str(live_spec), str(data_csv),
        "--folds", "5",
        "--output-dir", str(out_dir / "walk_forward"),
    ])

    # 5. Key levels — record exactly which types were used
    run([
        "fx-backtester", "scan-levels",
        "--data", str(data_csv),
        "--instrument", instrument,
        "--level-type", *AUTO_LEVEL_TYPES,
        "--output-dir", str(out_dir / "level_study"),
    ])

    # 6. Collect metrics
    # Sort by mtime so we always pick up the run we just produced, not an older one.
    _candidates = sorted(
        (ROOT / "outputs").glob("*/reports/summary.json"),
        key=lambda p: p.stat().st_mtime,
    )
    summary_json = _candidates[-1] if _candidates else None
    backtest_metrics: dict = {}
    if summary_json and summary_json.exists():
        try:
            backtest_metrics = json.loads(summary_json.read_text())
        except Exception:
            pass

    wf_json = out_dir / "walk_forward" / "walk_forward.json"
    wf_verdict      = None
    wf_oos_pips     = None
    wf_oos_wr       = None
    wf_validated    = None
    wf_total_folds  = None
    if wf_json.exists():
        try:
            # Deserialise via the canonical model so the verdict logic stays in one place.
            from fx_backtester.analysis.walk_forward import WalkForwardReport
            wf_report = WalkForwardReport.model_validate_json(wf_json.read_text())
            wf_verdict      = wf_report.verdict
            wf_oos_pips     = wf_report.oos_total_net_pips
            wf_oos_wr       = wf_report.oos_avg_win_rate
            wf_validated    = wf_report.validated_folds
            wf_total_folds  = len(wf_report.folds)
        except Exception:
            pass

    run_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M")

    summary = {
        "source":               "ai_pipeline",
        "instrument":           instrument,
        "run_timestamp":        run_ts,
        "run_date":             date.today().isoformat(),
        "data_start":           start.isoformat(),
        "data_end":             end.isoformat(),
        "lookback_days":        lookback,
        "key_levels_used":      AUTO_LEVEL_TYPES,
        "backtest":             backtest_metrics,
        "walk_forward_verdict": wf_verdict,
        "wf_validated_folds":   wf_validated,
        "wf_total_folds":       wf_total_folds,
        "oos_net_pips":         wf_oos_pips,
        "oos_win_rate":         wf_oos_wr,
    }

    (out_dir / "pipeline_summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "history" / f"{run_ts}.json").write_text(json.dumps(summary, indent=2))
    print(f"\n✓ {instrument} complete → results/auto/{instrument}/")


def main() -> None:
    lookback   = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    instrument = sys.argv[2].upper() if len(sys.argv) > 2 else None

    if instrument:
        run_instrument(instrument, lookback)
    else:
        # Default: run both
        run_instrument("NQ", lookback)
        run_instrument("ES", lookback)


if __name__ == "__main__":
    main()
