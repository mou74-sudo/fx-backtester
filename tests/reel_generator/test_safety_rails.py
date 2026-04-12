from datetime import datetime, timezone
from pathlib import Path

from reel_generator.character import load_character
from reel_generator.models import (
    ContentBrief,
    CyclePhase,
    Script,
    ScriptBeat,
    Trend,
    TrendSource,
)
from reel_generator.script import enforce_safety

ROOT = Path(__file__).resolve().parents[2]


def _brief():
    return ContentBrief(
        topic="luteal phase workout",
        angle="explain why intensity should drop",
        cycle_phase=CyclePhase.LUTEAL,
        supporting_trends=[
            Trend(
                source=TrendSource.MANUAL_CSV,
                term="luteal phase workout",
                score=0.9,
                region="US",
                fetched_at=datetime.now(timezone.utc),
            )
        ],
        rationale="top signal",
    )


def _script(**overrides) -> Script:
    base = {
        "brief": _brief(),
        "character_name": "Mara",
        "hook": "Luteal lifts feeling brutal?",
        "beats": [
            ScriptBeat(
                start_seconds=0.0,
                end_seconds=5.0,
                voiceover="Progesterone is peaking this week.",
                b_roll="home gym",
                on_screen_text=None,
            )
        ],
        "caption": "Luteal-phase lifts explained. Made with AI. #AI #cyclesyncing",
        "hashtags": ["#AI"],
        "disclosure_line": "This video features an AI-generated character.",
        "sources": [],
        "safety_review": "needs_human_review",
    }
    base.update(overrides)
    return Script.model_validate(base)


def test_clean_script_passes():
    char = load_character(ROOT / "config" / "character.yaml")
    violations = enforce_safety(_script(), char)
    assert violations == []


def test_missing_disclosure_is_flagged():
    char = load_character(ROOT / "config" / "character.yaml")
    script = _script(caption="Luteal-phase lifts explained.")
    rules = {v.rule for v in enforce_safety(script, char)}
    assert "missing_disclosure" in rules


def test_body_transformation_phrases_are_blocked():
    char = load_character(ROOT / "config" / "character.yaml")
    script = _script(hook="Before and after my luteal phase!")
    rules = {v.rule for v in enforce_safety(script, char)}
    assert "body_transformation" in rules or "forbidden_claim" in rules


def test_forbidden_detox_phrase_blocked():
    char = load_character(ROOT / "config" / "character.yaml")
    script = _script(
        caption="Made with AI. #AI — the best detox for your cycle.",
    )
    rules = {v.rule for v in enforce_safety(script, char)}
    assert "forbidden_claim" in rules


def test_unsourced_factual_claim_is_flagged():
    char = load_character(ROOT / "config" / "character.yaml")
    beats = [
        ScriptBeat(
            start_seconds=0.0,
            end_seconds=5.0,
            voiceover="Studies show that 80% of women benefit from this.",
            b_roll="home gym",
            on_screen_text=None,
        )
    ]
    script = _script(beats=beats, sources=[])
    rules = {v.rule for v in enforce_safety(script, char)}
    assert "unsourced_claim" in rules

    # Adding a source clears that flag.
    script_ok = _script(beats=beats, sources=["https://pubmed.ncbi.nlm.nih.gov/12345"])
    rules_ok = {v.rule for v in enforce_safety(script_ok, char)}
    assert "unsourced_claim" not in rules_ok


def test_prescriptive_medical_language_flagged():
    char = load_character(ROOT / "config" / "character.yaml")
    beats = [
        ScriptBeat(
            start_seconds=0.0,
            end_seconds=5.0,
            voiceover="If you feel tired in your luteal phase, you have PMDD — stop taking birth control.",
            b_roll="home gym",
            on_screen_text=None,
        )
    ]
    rules = {v.rule for v in enforce_safety(_script(beats=beats), char)}
    assert "prescriptive_medical" in rules
