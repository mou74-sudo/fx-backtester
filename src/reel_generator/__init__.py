"""reel_generator — disclosed-AI Instagram Reels pipeline.

Scope: hormonal-cycle + fitness education niche.

Hard rules baked into this package:
- Every script and caption carries an AI-disclosure tag.
- The character is generated; she does not impersonate a real person.
- No body-transformation (before/after, weight-loss) content.
- No diagnostic or prescriptive medical claims; content is educational.
- Trend *research* only — this package never downloads or republishes
  another creator's video.

See docs/reel_generator/README.md for the architecture overview.
"""

from reel_generator.models import (
    Character,
    ContentBrief,
    Script,
    Trend,
    TrendSource,
)

__all__ = ["Character", "ContentBrief", "Script", "Trend", "TrendSource"]
