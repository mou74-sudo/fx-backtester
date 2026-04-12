"""Pydantic models shared across reel_generator.

These are the contract between the trend research, script writing,
character, and upload layers. Keep them narrow.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class TrendSource(str, Enum):
    TIKTOK_CREATIVE_CENTER = "tiktok_creative_center"
    GOOGLE_TRENDS = "google_trends"
    YOUTUBE_DATA_API = "youtube_data_api"
    MANUAL_CSV = "manual_csv"


class CyclePhase(str, Enum):
    """Canonical hormonal-cycle phases used to tag content."""

    MENSTRUAL = "menstrual"
    FOLLICULAR = "follicular"
    OVULATORY = "ovulatory"
    LUTEAL = "luteal"
    GENERAL = "general"  # not phase-specific


class Trend(BaseModel):
    """A single trending topic/hashtag/sound surfaced by a provider.

    We deliberately do not store links to specific user-generated videos —
    this package does not encourage re-posting anyone else's content.
    """

    source: TrendSource
    term: str = Field(..., description="Hashtag, keyword, or sound title")
    score: float = Field(..., ge=0.0, description="Provider-normalized trend strength (0..1)")
    category: str | None = None
    region: str = "US"
    fetched_at: datetime


class ContentBrief(BaseModel):
    """The output of trend aggregation: an *original* content idea.

    This is what gets handed to the script writer. It does NOT include a
    reference video to copy.
    """

    topic: str
    angle: str = Field(..., description="Original take the creator will bring")
    cycle_phase: CyclePhase
    supporting_trends: list[Trend]
    target_duration_seconds: int = Field(default=45, ge=7, le=90)
    rationale: str = Field(..., description="Why this topic was selected")


class Character(BaseModel):
    """Disclosed-AI character sheet. Loaded from config/character.yaml."""

    name: str
    tagline: str
    disclosure_handle: str = Field(
        default="#AI", description="Must appear in every caption"
    )
    visual: dict[str, str]
    voice: dict[str, str]
    persona: dict[str, str]
    expertise_domains: list[str]
    forbidden_claims: list[str] = Field(
        default_factory=list,
        description="Phrases the character is not allowed to make (e.g. 'cures', 'diagnoses')",
    )


class ScriptBeat(BaseModel):
    start_seconds: float
    end_seconds: float
    voiceover: str
    b_roll: str = Field(..., description="Visual description for Higgsfield/editor")
    on_screen_text: str | None = None


class Script(BaseModel):
    """Final output handed to the video pipeline."""

    brief: ContentBrief
    character_name: str
    hook: str
    beats: list[ScriptBeat]
    caption: str
    hashtags: list[str]
    disclosure_line: str = Field(
        ..., description="Explicit 'made with AI' line; required, non-empty"
    )
    sources: list[str] = Field(
        default_factory=list,
        description="URLs/citations backing any factual claim in the script",
    )
    safety_review: Literal["passed", "needs_human_review"] = "needs_human_review"


class UploadRequest(BaseModel):
    """Instagram Graph API upload request."""

    video_url: HttpUrl
    caption: str
    scheduled_for: datetime | None = None
    share_to_feed: bool = True
