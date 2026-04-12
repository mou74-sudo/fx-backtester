"""Aggregate multi-source trends and score for the cycle + fitness niche."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from reel_generator.models import CyclePhase, Trend

# Seed lexicon for the hormonal-cycle + fitness niche. Expand over time.
CYCLE_TERMS: dict[CyclePhase, tuple[str, ...]] = {
    CyclePhase.MENSTRUAL: ("menstrual", "period", "bleeding", "cramp", "pms"),
    CyclePhase.FOLLICULAR: ("follicular", "post-period", "pre-ovulation"),
    CyclePhase.OVULATORY: ("ovulation", "ovulatory", "fertile window"),
    CyclePhase.LUTEAL: ("luteal", "pmdd", "progesterone", "pre-menstrual"),
    CyclePhase.GENERAL: ("cycle sync", "cycle syncing", "hormone", "hormonal", "estrogen"),
}
FITNESS_TERMS: tuple[str, ...] = (
    "workout", "training", "gym", "lift", "strength", "cardio", "pilates",
    "yoga", "mobility", "recovery", "zone 2", "running", "hiit",
)
NUTRITION_TERMS: tuple[str, ...] = (
    "nutrition", "protein", "seed cycling", "iron", "magnesium", "carbs",
    "meal prep", "blood sugar",
)


class TrendProvider(Protocol):
    def fetch(self, *args, **kwargs) -> list[Trend]: ...


@dataclass
class TrendAggregator:
    """Dedupe, merge scores across providers, and filter to niche."""

    providers: list[TrendProvider] = field(default_factory=list)

    def collect(self) -> list[Trend]:
        all_trends: list[Trend] = []
        for p in self.providers:
            try:
                all_trends.extend(p.fetch())
            except Exception as exc:  # pragma: no cover - defensive
                # Providers are network-bound; one failing shouldn't kill the batch.
                import logging

                logging.getLogger(__name__).warning("Provider %s failed: %s", p, exc)
        return all_trends

    def rank_for_niche(
        self,
        trends: list[Trend] | None = None,
        *,
        min_niche_score: float = 0.2,
    ) -> list[tuple[Trend, float, CyclePhase]]:
        """Return (trend, combined_score, phase) sorted high→low.

        combined_score = 0.6 * provider_score + 0.4 * niche_relevance.
        Trends whose niche relevance is 0 are dropped.
        """
        trends = trends if trends is not None else self.collect()
        # De-duplicate by normalized term, keep max provider score.
        best: dict[str, Trend] = {}
        for t in trends:
            key = _normalize(t.term)
            if key not in best or t.score > best[key].score:
                best[key] = t

        ranked: list[tuple[Trend, float, CyclePhase]] = []
        for t in best.values():
            niche_score, phase = score_for_niche(t.term)
            if niche_score < min_niche_score:
                continue
            combined = 0.6 * t.score + 0.4 * niche_score
            ranked.append((t, round(combined, 4), phase))
        ranked.sort(key=lambda row: -row[1])
        return ranked


def score_for_niche(term: str) -> tuple[float, CyclePhase]:
    """Score how relevant a term is to cycle + fitness education.

    Returns (score in 0..1, best-matching cycle phase).
    """
    normalized = _normalize(term)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))

    phase_hits: dict[CyclePhase, int] = defaultdict(int)
    for phase, terms in CYCLE_TERMS.items():
        for needle in terms:
            if needle in normalized:
                phase_hits[phase] += 1

    cycle_hit = sum(phase_hits.values()) > 0
    fitness_hit = any(n in normalized for n in FITNESS_TERMS) or any(
        tok in FITNESS_TERMS for tok in tokens
    )
    nutrition_hit = any(n in normalized for n in NUTRITION_TERMS)

    score = 0.0
    if cycle_hit:
        score += 0.6
    if fitness_hit:
        score += 0.3
    if nutrition_hit:
        score += 0.2
    score = min(score, 1.0)

    if phase_hits:
        phase = max(phase_hits.items(), key=lambda kv: kv[1])[0]
    elif cycle_hit:
        phase = CyclePhase.GENERAL
    else:
        phase = CyclePhase.GENERAL
    return score, phase


def _normalize(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())
