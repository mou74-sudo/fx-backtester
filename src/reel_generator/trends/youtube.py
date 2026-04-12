"""YouTube Data API provider for trending Shorts."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from reel_generator.models import Trend, TrendSource

logger = logging.getLogger(__name__)

YT_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


@dataclass
class YouTubeProvider:
    """Pull most-popular videos from the YouTube Data API.

    We extract *tags* from the top trending videos in a category as a
    proxy for trending *topics*. We never download the videos themselves.

    Requires a YouTube Data API key — set ``YOUTUBE_API_KEY`` env var or
    pass ``api_key=...``.
    """

    region: str = "US"
    # "26" = Howto & Style, "17" = Sports on YouTube. Cycle/fitness content
    # is mostly under 26 and 17.
    category_ids: tuple[str, ...] = ("26", "17")
    api_key: str | None = None
    session: Any = None  # requests.Session

    def fetch(self, limit: int = 25) -> list[Trend]:
        api_key = self.api_key or os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set; YouTubeProvider returning []")
            return []
        if self.session is None:
            raise RuntimeError("YouTubeProvider requires a requests.Session")

        fetched_at = datetime.now(timezone.utc)
        tag_counts: dict[str, int] = {}
        for cat in self.category_ids:
            params = {
                "part": "snippet",
                "chart": "mostPopular",
                "regionCode": self.region,
                "videoCategoryId": cat,
                "maxResults": min(limit, 50),
                "key": api_key,
            }
            resp = self.session.get(YT_VIDEOS_URL, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning("YouTube API %s: %s", resp.status_code, resp.text[:200])
                continue
            for item in resp.json().get("items", []):
                for tag in item.get("snippet", {}).get("tags", []) or []:
                    tag_counts[tag.lower()] = tag_counts.get(tag.lower(), 0) + 1

        if not tag_counts:
            return []
        peak = max(tag_counts.values())
        return [
            Trend(
                source=TrendSource.YOUTUBE_DATA_API,
                term=tag,
                score=round(count / peak, 4),
                region=self.region,
                fetched_at=fetched_at,
            )
            for tag, count in sorted(tag_counts.items(), key=lambda kv: -kv[1])[:limit]
        ]
