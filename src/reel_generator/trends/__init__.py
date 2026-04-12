"""Trend research providers.

All providers return ``list[Trend]``. Never store or fetch the actual video
content of another creator — we only collect trend *signals* (keywords,
hashtags, audio titles, search volume).
"""

from reel_generator.trends.aggregator import TrendAggregator, score_for_niche
from reel_generator.trends.google import GoogleTrendsProvider
from reel_generator.trends.manual import ManualCsvProvider
from reel_generator.trends.tiktok import TikTokCreativeCenterProvider
from reel_generator.trends.youtube import YouTubeProvider

__all__ = [
    "GoogleTrendsProvider",
    "ManualCsvProvider",
    "TikTokCreativeCenterProvider",
    "TrendAggregator",
    "YouTubeProvider",
    "score_for_niche",
]
