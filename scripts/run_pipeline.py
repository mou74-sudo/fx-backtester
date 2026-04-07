"""
Automated pipeline: fetch → backtest → walk-forward → scan-levels.
Writes all results to results/ so Streamlit picks them up automatically.
Each run also saves a timestamped snapshot to results/history/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timedelta, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

SPEC_TEMPLATE = ROOT / "examples" / "eurusd_rsi_fixed_pips_spec.json"
DATA_CSV = RESULTS / "latest_eurusd_h1.csv"
LIVE_SPEC = RESULTS / "live_spec.json"


def run(cmd: list[str]) -> None:
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, check=True)
    if result.returncode != 0:
        sys.exit(result.returncode)


def build_live_spec(end: date, lookback_days: int = 180) -> None:
    """Copy the template spec and update dates to cover the last N days."""
    raw = json.loads(SPEC_TEMPLATE.read_text())
    start = end - timedelta(days=lookback_days)
    raw["window"]["start_date"] = start.isoformat()
    raw["window"]["end_date"] = end.isoformat()
    raw["strategy_name"] = f"auto_eurusd_rsi_{end.isoformat()}"
    LIVE_SPEC.write_text(json.dumps(raw, indent=2))
    print(f"Live spec: {start} → {end}")


def last_weekday(d: date) -> date:
    """Step back until we land on Mon-Fri (Dukascopy has no weekend data)."""
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d




def main() -> None:
    lookback    = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    instrument  = sys.argv[2]      if len(sys.argv) > 2 else "NQ"
    # yfinance always has data up to yesterday — use yesterday as end
    end = last_weekday(date.today() - timedelta(days=1))
    start = end - timedelta(days=lookback)

    # 1. Build spec with probed date range
    build_live_spec(end, lookback)

    # 2. Fetch fresh H1 data (failures per day are skipped, not fatal)
    try:
        run([
            "fx-backtester", "fetch-data",
            "--instrument", instrument,
            "--start", start.isoformat(),
            "--end", end.isoformat(),
            "--output", str(DATA_CSV),
            "--cache-dir", str(ROOT / "data" / "cache"),
        ])
    except SystemExit:
        print("WARNING: data fetch failed — aborting pipeline run.")
        sys.exit(1)

    if not DATA_CSV.exists() or DATA_CSV.stat().st_size < 100:
        print("WARNING: data file is empty or missing — aborting pipeline run.")
        sys.exit(1)

    # 3. Run backtest
    run([
        "fx-backtester", "run-backtest",
        str(LIVE_SPEC),
        str(DATA_CSV),
        "--repo-root", str(ROOT),
    ])

    # 4. Walk-forward validation
    run([
        "fx-backtester", "walk-forward-test",
        str(LIVE_SPEC),
        str(DATA_CSV),
        "--folds", "5",
        "--output-dir", str(RESULTS / "walk_forward"),
    ])

    # 5. Scan key levels
    run([
        "fx-backtester", "scan-levels",
        "--data", str(DATA_CSV),
        "--instrument", instrument,
        "--level-type", "prev_day_highs", "prev_day_lows",
                        "prev_week_highs", "prev_week_lows",
                        "session_highs", "session_lows",
        "--output-dir", str(RESULTS / "level_study"),
    ])

    # 6. Collect backtest metrics for history
    summary_json = next(
        (ROOT / "outputs").glob("*/reports/summary.json"), None
    )
    backtest_metrics: dict = {}
    if summary_json and summary_json.exists():
        try:
            backtest_metrics = json.loads(summary_json.read_text())
        except Exception:
            pass

    wf_json = RESULTS / "walk_forward" / "walk_forward.json"
    wf_metrics: dict = {}
    if wf_json.exists():
        try:
            wf_metrics = json.loads(wf_json.read_text())
        except Exception:
            pass

    run_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M")

    # 7. Write latest pipeline summary
    summary = {
        "run_timestamp": run_ts,
        "run_date": date.today().isoformat(),
        "data_start": start.isoformat(),
        "data_end": end.isoformat(),
        "lookback_days": lookback,
        "backtest": backtest_metrics,
        "walk_forward_verdict": wf_metrics.get("verdict"),
        "oos_net_pips": wf_metrics.get("oos_total_net_pips"),
        "oos_win_rate": wf_metrics.get("oos_avg_win_rate"),
    }
    (RESULTS / "pipeline_summary.json").write_text(json.dumps(summary, indent=2))

    # 8. Append to history — one file per run, kept forever
    history_dir = RESULTS / "history"
    history_dir.mkdir(exist_ok=True)
    (history_dir / f"{run_ts}.json").write_text(json.dumps(summary, indent=2))
    print(f"\nHistory snapshot saved: results/history/{run_ts}.json")
    print("\nPipeline complete. Results written to results/")


if __name__ == "__main__":
    main()
