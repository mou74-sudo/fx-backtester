"""Google Trends provider using pytrends.

pytrends is a community wrapper around Google Trends' unofficial endpoint.
We treat it as optional — install with ``pip install pytrends`` to use.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from reel_generator.models import Trend, TrendSource

logger = logging.getLogger(__name__)


@dataclass
class GoogleTrendsProvider:
    """Fetch interest-over-time for seed keywords via pytrends.

    For the cycle + fitness niche, useful seeds are things like:
      ["luteal phase workout", "seed cycling", "cycle syncing nutrition",
       "pms fatigue", "ovulation strength training"]

    Score is derived from the most recent 7-day average interest score,
    normalized to 0..1 within the batch.
    """

    keywords: list[str]
    geo: str = "US"
    timeframe: str = "now 7-d"
    _pytrends: object | None = field(default=None, repr=False)

    def fetch(self) -> list[Trend]:
        pytrends = self._get_client()
        if pytrends is None:
            logger.warning("pytrends not installed; GoogleTrendsProvider returning []")
            return []

        # pytrends accepts at most 5 keywords per request.
        results: list[tuple[str, float]] = []
        for batch in _batched(self.keywords, 5):
            try:
                pytrends.build_payload(batch, timeframe=self.timeframe, geo=self.geo)
                df = pytrends.interest_over_time()
            except Exception as exc:  # pragma: no cover - network path
                logger.warning("pytrends batch failed (%s): %s", batch, exc)
                continue
            if df is None or df.empty:
                continue
            for kw in batch:
                if kw in df.columns:
                    results.append((kw, float(df[kw].tail(7).mean())))

        if not results:
            return []
        peak = max(v for _, v in results) or 1.0
        fetched_at = datetime.now(timezone.utc)
        return [
            Trend(
                source=TrendSource.GOOGLE_TRENDS,
                term=kw,
                score=round(val / peak, 4),
                region=self.geo,
                fetched_at=fetched_at,
            )
            for kw, val in results
        ]

    def _get_client(self):
        if self._pytrends is not None:
            return self._pytrends
        try:
            from pytrends.request import TrendReq  # type: ignore
        except ImportError:
            return None
        self._pytrends = TrendReq(hl="en-US", tz=0)
        return self._pytrends


def _batched(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
