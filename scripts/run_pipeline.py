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
    "NQ": {"pip_size": 0.25, "lot_size_units": 20,  "stop_loss_pips": 100, "take_profit_pips": 300},
    "ES": {"pip_size": 0.25, "lot_size_units": 50,  "stop_loss_pips": 80,  "take_profit_pips": 240},
}

def build_live_spec(out_path: Path, instrument: str, start: date, end: date) -> None:
    raw = json.loads(SPEC_TEMPLATE.read_text())
    raw["window"]["start_date"] = start.isoformat()
    raw["window"]["end_date"]   = end.isoformat()
    raw["strategy_name"]        = f"auto_{instrument.lower()}_{end.isoformat()}"
    if instrument in _FUTURES_PARAMS:
        fp = _FUTURES_PARAMS[instrument]
        raw["instrument"]["symbol"]        = instrument
        raw["instrument"]["pip_size"]      = fp["pip_size"]
        raw["instrument"]["lot_size_units"]= fp["lot_size_units"]
        raw["risk"]["initial_equity"]      = 50_000   # realistic futures account size
        raw["rules"]["stop_loss_pips"]     = fp["stop_loss_pips"]
        raw["rules"]["take_profit_pips"]   = fp["take_profit_pips"]
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
    summary_json = next((ROOT / "outputs").glob("*/reports/summary.json"), None)
    backtest_metrics: dict = {}
    if summary_json and summary_json.exists():
        try:
            backtest_metrics = json.loads(summary_json.read_text())
        except Exception:
            pass

    wf_json = out_dir / "walk_forward" / "walk_forward.json"
    wf_metrics: dict = {}
    wf_verdict      = None
    wf_oos_pips     = None
    wf_oos_wr       = None
    wf_validated    = None
    wf_total_folds  = None
    if wf_json.exists():
        try:
            wf_metrics = json.loads(wf_json.read_text())
            folds = wf_metrics.get("folds", [])
            if folds:
                oos_pips   = [f["out_of_sample"]["net_pips"] for f in folds]
                oos_wrs    = [f["out_of_sample"]["win_rate"]  for f in folds]
                oos_prof   = sum(1 for f in folds if f.get("oos_profitable"))
                wf_oos_pips    = round(sum(oos_pips), 2)
                wf_oos_wr      = round(sum(oos_wrs) / len(oos_wrs), 4)
                wf_validated   = oos_prof
                wf_total_folds = len(folds)
                pct = oos_prof / len(folds)
                wf_verdict = (
                    "validated"   if pct >= 0.6 and wf_oos_pips > 0 else
                    "failed"      if wf_oos_pips < 0 else
                    "inconclusive"
                )
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
