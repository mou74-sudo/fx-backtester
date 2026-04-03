"""Markdown and JSON report formatter for key level reaction studies."""

from __future__ import annotations

import json
from pathlib import Path

from fx_backtester.analysis.key_levels import LevelReactionSummary, LevelStudyReport


# ── Markdown formatter ────────────────────────────────────────────────────────


def _bar(value: float, max_val: float, width: int = 20) -> str:
    """Simple ASCII bar scaled to max_val."""
    if max_val <= 0:
        return ""
    filled = round((value / max_val) * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_pips(pips: float) -> str:
    sign = "+" if pips >= 0 else ""
    return f"{sign}{pips:.1f}p"


def _summary_block(s: LevelReactionSummary) -> str:
    tc = s.touch_count
    if tc == 0:
        return ""

    lines: list[str] = []
    lines.append(f"\n### Level {s.level.price:.5f}  [{s.level.level_type}]  `{s.level.label}`")
    lines.append(f"Touches: **{tc}**  |  Zone: ±{s.zone_pips} pips  |  Forward: {s.forward_bars} bars\n")

    # Outcome table
    lines.append("**Reaction summary**\n")
    lines.append("| Outcome        | Count | Rate  | Bar chart            |")
    lines.append("|----------------|-------|-------|----------------------|")
    lines.append(f"| Reversed       | {s.reversal_count:>5} | {s.reversal_rate:>5.0%} | {_bar(s.reversal_count, tc)} |")
    lines.append(f"| Broke through  | {s.breakout_count:>5} | {s.breakout_rate:>5.0%} | {_bar(s.breakout_count, tc)} |")
    lines.append(f"| Consolidated   | {s.consolidation_count:>5} | {1 - s.reversal_rate - s.breakout_rate:>5.0%} | {_bar(s.consolidation_count, tc)} |")

    # Forward pip table
    if s.avg_forward_pips:
        lines.append("\n**Average pip move from touch close** (+ = higher, − = lower)\n")
        lines.append("| Bars forward | Avg move |")
        lines.append("|:------------:|:--------:|")
        for h in sorted(s.avg_forward_pips):
            lines.append(f"|      +{h:<5}    | {_fmt_pips(s.avg_forward_pips[h]):>8} |")

    # By direction
    lines.append("\n**By approach direction**\n")
    if s.from_above_count:
        lines.append(f"- **From above** (support test): {s.from_above_count} touches · "
                     f"{s.from_above_reversal_rate:.0%} reversed")
    if s.from_below_count:
        lines.append(f"- **From below** (resistance test): {s.from_below_count} touches · "
                     f"{s.from_below_reversal_rate:.0%} reversed")

    # Touch log (last 10 touches)
    shown = s.reactions[-10:] if len(s.reactions) > 10 else s.reactions
    lines.append("\n**Touch log** (most recent 10)\n")
    lines.append("| Timestamp           | Direction   | Outcome       | Favorable | Adverse  |"
                 + "".join(f" +{h}p  |" for h in sorted(s.avg_forward_pips)))
    lines.append("|---------------------|-------------|---------------|-----------|----------|"
                 + "".join("-------|" for _ in s.avg_forward_pips))
    for r in shown:
        fwd_cols = "".join(
            f" {_fmt_pips(r.forward_pips.get(h, 0)):>5} |"
            for h in sorted(s.avg_forward_pips)
        )
        lines.append(
            f"| {r.touch.timestamp.strftime('%Y-%m-%d %H:%M')} "
            f"| {r.touch.approach:<11} "
            f"| {r.outcome:<13} "
            f"| {_fmt_pips(r.max_favorable_pips):>9} "
            f"| {_fmt_pips(r.max_adverse_pips):>8} "
            f"|{fwd_cols}"
        )

    return "\n".join(lines)


def build_markdown_report(report: LevelStudyReport) -> str:
    """Return the full study as a markdown string."""
    header = (
        f"# Key Level Reaction Study: {report.instrument}\n\n"
        f"**Bars analysed:** {report.bar_count}  "
        f"|  **Price range:** {report.price_range_low:.5f} – {report.price_range_high:.5f}  "
        f"|  **Levels with ≥2 touches:** {report.levels_studied}  "
        f"|  **Total touches:** {report.total_touches}\n"
    )
    if not report.summaries:
        return header + "\n_No levels accumulated enough touches. Widen the zone or date range._\n"

    body = "\n".join(_summary_block(s) for s in report.summaries if s.touch_count > 0)
    return header + body + "\n"


# ── Artifact writer ───────────────────────────────────────────────────────────


def write_level_study_artifacts(report: LevelStudyReport, output_dir: Path) -> Path:
    """Write ``level_study.json`` and ``level_study.md`` to ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON — full machine-readable report
    json_path = output_dir / "level_study.json"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # Markdown — human-readable summary
    md_path = output_dir / "level_study.md"
    md_path.write_text(build_markdown_report(report), encoding="utf-8")

    return output_dir
