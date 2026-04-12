"""Post-generation checks applied to every script.

If any of these fail, the script is flagged ``needs_human_review``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from reel_generator.models import Character, Script


@dataclass
class SafetyViolation:
    rule: str
    detail: str


def enforce_safety(script: Script, character: Character) -> list[SafetyViolation]:
    """Return a list of violations. Empty list = safe to publish."""
    violations: list[SafetyViolation] = []

    full_text = " ".join(
        [script.hook, script.caption, *(b.voiceover for b in script.beats)]
    ).lower()

    # 1. Forbidden claim phrases (from character sheet).
    for phrase in character.forbidden_claims:
        if phrase.lower() in full_text:
            violations.append(
                SafetyViolation(
                    rule="forbidden_claim",
                    detail=f"Script contains forbidden phrase: {phrase!r}",
                )
            )

    # 2. Disclosure — AI tag must be present in caption.
    if character.disclosure_handle.lower() not in script.caption.lower():
        violations.append(
            SafetyViolation(
                rule="missing_disclosure",
                detail=f"Caption is missing the required disclosure handle {character.disclosure_handle!r}",
            )
        )
    if not script.disclosure_line.strip():
        violations.append(
            SafetyViolation(
                rule="missing_disclosure_line",
                detail="disclosure_line must be a non-empty 'made with AI' statement",
            )
        )

    # 3. Body-transformation / weight-loss framing.
    body_patterns = [
        r"\bbefore and after\b",
        r"\blost \d+\s*(lbs|lb|pounds|kg)\b",
        r"\bfrom \d+\s*(lbs|lb|pounds|kg)\b",
        r"\bshrink(ing)? (your|my|her) (waist|stomach|thighs)\b",
        r"\btransform(ed|ation)\b.*\bbody\b",
    ]
    for pattern in body_patterns:
        if re.search(pattern, full_text):
            violations.append(
                SafetyViolation(
                    rule="body_transformation",
                    detail=f"Script matches body-transformation pattern /{pattern}/",
                )
            )
            break

    # 4. Prescriptive medical language.
    medical_patterns = [
        r"\byou have (pcos|endometriosis|pmdd)\b",
        r"\bstop taking\b.*\b(birth control|bc|medication)\b",
        r"\bthis will cure\b",
        r"\byou don'?t need (a doctor|your gyno)\b",
    ]
    for pattern in medical_patterns:
        if re.search(pattern, full_text):
            violations.append(
                SafetyViolation(
                    rule="prescriptive_medical",
                    detail=f"Script matches prescriptive-medical pattern /{pattern}/",
                )
            )

    # 5. Factual claims without sources.
    factual_markers = ["studies show", "research shows", "science says", "% of women"]
    has_factual_claim = any(m in full_text for m in factual_markers)
    if has_factual_claim and not script.sources:
        violations.append(
            SafetyViolation(
                rule="unsourced_claim",
                detail="Script makes factual claims but sources[] is empty",
            )
        )

    return violations
