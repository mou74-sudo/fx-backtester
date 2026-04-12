"""Manual CSV trend provider — the escape hatch.

When Creative Center and Google Trends are both flaky, export a CSV
from Creative Center's UI and feed it in here. Columns:

    term,score,category,region

``score`` is optional and defaults to a rank-based score when omitted.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from reel_generator.models import Trend, TrendSource


@dataclass
class ManualCsvProvider:
    path: Path
    region: str = "US"

    def fetch(self) -> list[Trend]:
        rows = list(csv.DictReader(Path(self.path).open(encoding="utf-8")))
        fetched_at = datetime.now(timezone.utc)
        total = max(len(rows), 1)
        trends: list[Trend] = []
        for idx, row in enumerate(rows):
            term = (row.get("term") or "").strip().lstrip("#")
            if not term:
                continue
            raw_score = row.get("score")
            if raw_score:
                try:
                    score = float(raw_score)
                except ValueError:
                    score = 1.0 - (idx / total)
            else:
                score = 1.0 - (idx / total)
            trends.append(
                Trend(
                    source=TrendSource.MANUAL_CSV,
                    term=term,
                    score=round(max(0.0, min(1.0, score)), 4),
                    category=(row.get("category") or None),
                    region=(row.get("region") or self.region),
                    fetched_at=fetched_at,
                )
            )
        return trends
