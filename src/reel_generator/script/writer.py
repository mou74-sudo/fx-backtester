"""Script writer backed by the Claude API.

We use prompt caching (cache_control on the system block) because the
character sheet and style guide are identical across every generation.
See https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

Environment:
    ANTHROPIC_API_KEY — required at call time.

Dependencies: ``anthropic`` SDK is loaded lazily so tests that don't call
the API don't need it installed.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from reel_generator.models import (
    Character,
    ContentBrief,
    CyclePhase,
    Script,
    ScriptBeat,
    Trend,
)
from reel_generator.script.safety_rails import enforce_safety

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are a script writer for a *disclosed AI* Instagram Reels channel in the
hormonal-cycle and fitness-education niche. The on-screen character is
AI-generated and must never be presented as a real person.

Every script you produce MUST:
1. Include an explicit "made with AI" disclosure line in the caption.
2. Cite sources for any factual claim (e.g. peer-reviewed study, book,
   named expert). If you cannot cite, reframe the claim as a personal
   reflection or question.
3. Stay educational. Never diagnose, never tell viewers to change or
   stop medication, never claim to cure anything.
4. Avoid all body-transformation framing. No "before/after", no weight-loss
   numbers, no "shrink your waist". Body-composition talk is fine only in
   the context of performance (e.g. recovery, strength).
5. Respect the forbidden_claims list in the character sheet.
6. Produce ORIGINAL content. You may reference trending topics, but never
   reproduce another creator's script.

Output format: strict JSON matching the provided schema. No prose outside
the JSON.
"""


OUTPUT_SCHEMA_HINT = """\
{
  "hook": "string (first 2 seconds, max 90 chars)",
  "beats": [
    {
      "start_seconds": 0.0,
      "end_seconds": 5.0,
      "voiceover": "string",
      "b_roll": "string (visual description for Higgsfield)",
      "on_screen_text": "string or null"
    }
  ],
  "caption": "string (must include #AI and a 'made with AI' line)",
  "hashtags": ["string", "..."],
  "disclosure_line": "string (the explicit 'made with AI' sentence)",
  "sources": ["url or citation", "..."]
}
"""


def build_brief_from_trends(
    ranked: list[tuple[Trend, float, CyclePhase]],
    *,
    top_n: int = 5,
) -> ContentBrief:
    """Synthesize a ContentBrief from the aggregator's top results."""
    if not ranked:
        raise ValueError("Cannot build a brief from an empty ranked list")

    top = ranked[:top_n]
    top_trend, top_score, top_phase = top[0]
    supporting = [t for t, _, _ in top]
    topic = top_trend.term
    angle = (
        f"Take the trending topic '{top_trend.term}' and explain it specifically "
        f"through the lens of the {top_phase.value} phase — what actually changes "
        f"physiologically, and one practical adjustment a viewer can make."
    )
    rationale = (
        f"Top signal: {top_trend.term} (source={top_trend.source.value}, "
        f"combined_score={top_score}). Supporting: "
        f"{', '.join(t.term for t, _, _ in top[1:])}."
    )
    return ContentBrief(
        topic=topic,
        angle=angle,
        cycle_phase=top_phase,
        supporting_trends=supporting,
        rationale=rationale,
    )


@dataclass
class ScriptWriter:
    character: Character
    model: str = "claude-opus-4-6"
    api_key: str | None = None
    _client: Any = field(default=None, repr=False)

    def write(self, brief: ContentBrief) -> Script:
        client = self._get_client()
        user_content = self._build_user_prompt(brief)

        # Character sheet + schema go in the cached system block.
        cached_system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    "CHARACTER SHEET (immutable across generations):\n"
                    + json.dumps(self.character.model_dump(), indent=2)
                ),
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": "OUTPUT SCHEMA:\n" + OUTPUT_SCHEMA_HINT,
                "cache_control": {"type": "ephemeral"},
            },
        ]

        response = client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=cached_system,
            messages=[{"role": "user", "content": user_content}],
        )

        raw_text = _extract_text(response)
        parsed = _parse_script_json(raw_text)

        beats = [ScriptBeat.model_validate(b) for b in parsed["beats"]]
        script = Script(
            brief=brief,
            character_name=self.character.name,
            hook=parsed["hook"],
            beats=beats,
            caption=parsed["caption"],
            hashtags=parsed.get("hashtags", []),
            disclosure_line=parsed["disclosure_line"],
            sources=parsed.get("sources", []),
            safety_review="needs_human_review",
        )
        violations = enforce_safety(script, self.character)
        if not violations:
            script.safety_review = "passed"
        else:
            logger.warning(
                "Script flagged for review (%d violations): %s",
                len(violations),
                [v.rule for v in violations],
            )
        return script

    def _build_user_prompt(self, brief: ContentBrief) -> str:
        return (
            "Write a Reel script for the following brief.\n\n"
            f"Topic: {brief.topic}\n"
            f"Angle: {brief.angle}\n"
            f"Cycle phase: {brief.cycle_phase.value}\n"
            f"Target duration: {brief.target_duration_seconds}s\n"
            f"Trend signals: {json.dumps([t.model_dump(mode='json') for t in brief.supporting_trends], default=str)}\n"
            f"Rationale: {brief.rationale}\n\n"
            "Respond with JSON only, matching the schema exactly."
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed. `pip install anthropic` to use ScriptWriter."
            ) from exc
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=key)
        return self._client


def _extract_text(response: Any) -> str:
    # anthropic SDK >= 0.30 returns Message with .content = list of blocks.
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_script_json(raw: str) -> dict:
    # Strip ``` fences if the model added any.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {exc}\n\n{raw[:400]}") from exc
