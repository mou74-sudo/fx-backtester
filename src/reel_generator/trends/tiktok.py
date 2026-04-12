"""TikTok Creative Center provider.

Creative Center (https://ads.tiktok.com/business/creativecenter/) is
TikTok's own free dashboard for advertisers and exposes trending hashtags,
sounds, and keywords by region/category. It has a JSON backend that their
frontend calls.

Two modes:

1. ``http`` — calls the Creative Center JSON endpoint. This is *unofficial*
   (the endpoints are undocumented) so it may break. We keep calls rate-
   limited and respect ``robots.txt``; if TikTok publishes a supported API,
   swap to it here.
2. ``fixture`` — reads a JSON fixture from disk. Use this in tests and
   when Creative Center is unreachable.

We deliberately only pull *aggregate* trend data (hashtag names, popularity
ranks). We do not download any user-generated videos through this module.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reel_generator.models import Trend, TrendSource

logger = logging.getLogger(__name__)

CREATIVE_CENTER_HASHTAG_URL = (
    "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
)


@dataclass
class TikTokCreativeCenterProvider:
    """Fetch trending hashtags from TikTok Creative Center.

    Parameters
    ----------
    mode: "http" or "fixture"
    fixture_path: path to a JSON file when mode="fixture"
    region: ISO country code (e.g. "US", "GB")
    category_ids: Creative Center category IDs to filter to. For the
        hormonal-cycle + fitness niche, the relevant categories are
        typically "Health" and "Sports & Outdoors" — look up IDs in the
        Creative Center UI, they change periodically.
    """

    mode: str = "fixture"
    fixture_path: Path | None = None
    region: str = "US"
    category_ids: tuple[str, ...] = ()
    session: Any = None  # requests.Session injected by caller when mode="http"

    def fetch(self, limit: int = 50) -> list[Trend]:
        if self.mode == "fixture":
            return self._fetch_fixture(limit)
        if self.mode == "http":
            return self._fetch_http(limit)
        raise ValueError(f"Unknown mode: {self.mode!r}")

    def _fetch_fixture(self, limit: int) -> list[Trend]:
        if self.fixture_path is None:
            raise ValueError("fixture_path is required when mode='fixture'")
        raw = json.loads(Path(self.fixture_path).read_text(encoding="utf-8"))
        return _parse_hashtag_response(raw, region=self.region, limit=limit)

    def _fetch_http(self, limit: int) -> list[Trend]:
        if self.session is None:
            raise RuntimeError(
                "mode='http' requires a requests.Session (pass session=...). "
                "We don't create one implicitly so callers own timeouts, retries, and auth headers."
            )
        params = {
            "period": 7,
            "page": 1,
            "limit": min(limit, 50),
            "country_code": self.region,
            "sort_by": "popular",
        }
        if self.category_ids:
            params["industry_id"] = ",".join(self.category_ids)
        headers = {
            "User-Agent": os.environ.get(
                "REEL_GEN_USER_AGENT",
                "reel-generator/0.1 (+https://github.com/mou74-sudo/fx-backtester)",
            )
        }
        resp = self.session.get(
            CREATIVE_CENTER_HASHTAG_URL,
            params=params,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        return _parse_hashtag_response(resp.json(), region=self.region, limit=limit)


def _parse_hashtag_response(raw: dict, *, region: str, limit: int) -> list[Trend]:
    items = raw.get("data", {}).get("list", []) or []
    trends: list[Trend] = []
    fetched_at = datetime.now(timezone.utc)
    # Creative Center returns items in rank order; use rank to derive a 0..1 score.
    total = max(len(items), 1)
    for idx, item in enumerate(items[:limit]):
        term = item.get("hashtag_name") or item.get("name")
        if not term:
            continue
        score = 1.0 - (idx / total)
        trends.append(
            Trend(
                source=TrendSource.TIKTOK_CREATIVE_CENTER,
                term=str(term).lstrip("#"),
                score=round(score, 4),
                category=item.get("industry_info", {}).get("value") if isinstance(item.get("industry_info"), dict) else None,
                region=region,
                fetched_at=fetched_at,
            )
        )
    return trends
