"""Higgsfield prompt generation for consistent character output.

Higgsfield ships several product lines (Soul for image, DoP/Steal/Draw for
video). This module produces *prompts* that you can paste into Higgsfield
directly or submit via their REST API when you have a key.

We don't call Higgsfield over the network here because:
  1. Their API surface has shifted across product lines.
  2. Keeping prompt generation pure makes it trivially testable.
  3. You'll want to inspect the first few generations by eye anyway to
     lock the character's visual identity.

Consistency is enforced by re-using the same ``visual`` block from
character.yaml on every prompt and by including negative-prompt guards
against the forbidden visual patterns.
"""

from __future__ import annotations

from reel_generator.models import Character, Script


_NEGATIVE_BASE = (
    "no text overlays, no watermarks, no logos, no before-and-after split, "
    "no weight-loss framing, no lab coat, no stethoscope, no body comparison, "
    "no sexualized angles, no crop that emphasizes waist or thighs"
)


def build_image_prompt(character: Character, *, scene: str) -> dict[str, str]:
    """Return a Higgsfield Soul-style prompt bundle for a still character reference.

    Example usage:
        build_image_prompt(mara, scene="seated in a home gym reviewing a workout journal")
    """
    v = character.visual
    positive = (
        f"Editorial photography of an AI-generated character named {character.name}, "
        f"{v.get('age_appearance','30')} years old, {v.get('build','athletic lean')}, "
        f"{v.get('hair','dark brown shoulder-length hair')}, wearing {v.get('wardrobe','neutral activewear')}. "
        f"Scene: {scene}. Setting: {v.get('setting','minimalist home gym, natural light')}. "
        f"Natural skin texture, soft daylight, 50mm lens, calm neutral expression, "
        f"consistent face across all generations. Tagged as AI-generated."
    )
    negative = _NEGATIVE_BASE
    return {"prompt": positive, "negative_prompt": negative}


def build_video_prompt(
    character: Character,
    script: Script,
    *,
    beat_index: int,
) -> dict[str, str]:
    """Build a Higgsfield video prompt for a single script beat."""
    if beat_index < 0 or beat_index >= len(script.beats):
        raise IndexError(f"beat_index {beat_index} out of range for {len(script.beats)} beats")
    beat = script.beats[beat_index]
    v = character.visual
    duration = max(1.0, beat.end_seconds - beat.start_seconds)
    positive = (
        f"Cinematic vertical 9:16 clip of AI character {character.name} "
        f"({v.get('build','athletic lean build')}, {v.get('hair','dark brown hair')}, "
        f"wearing {v.get('wardrobe','neutral activewear')}) in {v.get('setting','minimalist home gym, natural light')}. "
        f"Action / b-roll: {beat.b_roll}. Duration: {duration:.1f}s. "
        f"Voiceover being spoken: \"{beat.voiceover}\". "
        f"Same face and body as reference image. Calm, informative demeanor. "
        f"Soft natural lighting. AI-disclosure label overlay permitted in lower-third."
    )
    return {
        "prompt": positive,
        "negative_prompt": _NEGATIVE_BASE,
        "duration_seconds": f"{duration:.1f}",
        "aspect_ratio": "9:16",
    }
