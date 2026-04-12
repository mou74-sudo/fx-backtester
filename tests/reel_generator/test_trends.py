from datetime import datetime, timezone
from pathlib import Path

from reel_generator.models import CyclePhase, Trend, TrendSource
from reel_generator.trends import (
    ManualCsvProvider,
    TikTokCreativeCenterProvider,
    TrendAggregator,
    score_for_niche,
)

FIXTURE = Path(__file__).parent / "fixtures" / "tiktok_hashtags.json"


def test_tiktok_fixture_parses_hashtags():
    provider = TikTokCreativeCenterProvider(mode="fixture", fixture_path=FIXTURE)
    trends = provider.fetch(limit=10)
    assert {t.term for t in trends} >= {"lutealphase", "cyclesyncing", "seedcycling"}
    # Scores are rank-normalized, descending.
    scores = [t.score for t in trends]
    assert scores == sorted(scores, reverse=True)
    assert all(t.source == TrendSource.TIKTOK_CREATIVE_CENTER for t in trends)


def test_score_for_niche_matches_cycle_phase():
    score, phase = score_for_niche("luteal phase workout")
    assert score >= 0.8
    assert phase == CyclePhase.LUTEAL

    score, phase = score_for_niche("ovulation strength training")
    assert score >= 0.8
    assert phase == CyclePhase.OVULATORY


def test_score_for_niche_rejects_off_topic():
    score, _ = score_for_niche("dancechallenge2026")
    assert score == 0.0


def test_aggregator_ranks_and_dedupes():
    provider = TikTokCreativeCenterProvider(mode="fixture", fixture_path=FIXTURE)
    # Add a duplicate with higher score via a manual trend to exercise dedup.
    extra = Trend(
        source=TrendSource.MANUAL_CSV,
        term="lutealphase",
        score=1.0,
        region="US",
        fetched_at=datetime.now(timezone.utc),
    )
    agg = TrendAggregator(providers=[provider])
    collected = agg.collect() + [extra]
    ranked = agg.rank_for_niche(collected, min_niche_score=0.3)
    assert ranked, "expected at least one niche-relevant trend"
    top_terms = [t.term for t, _, _ in ranked[:3]]
    assert "lutealphase" in top_terms
    # Dedup should leave a single entry for "lutealphase" with the max score.
    assert sum(1 for t, _, _ in ranked if t.term == "lutealphase") == 1


def test_manual_csv_provider(tmp_path: Path):
    csv = tmp_path / "trends.csv"
    csv.write_text(
        "term,score,category,region\n"
        "luteal phase workout,0.9,Health,US\n"
        "pms nutrition,0.7,Health,US\n",
        encoding="utf-8",
    )
    trends = ManualCsvProvider(path=csv).fetch()
    assert [t.term for t in trends] == ["luteal phase workout", "pms nutrition"]
    assert trends[0].score == 0.9
