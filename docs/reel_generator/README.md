# reel_generator

A disclosed-AI Instagram Reels pipeline for the hormonal-cycle + fitness niche.

## Scope

- **Trend research, not trend copying.** Pulls aggregate trend signals
  (hashtags, keywords, audio titles, search volume) from TikTok Creative
  Center, Google Trends, and the YouTube Data API. We never download or
  repost another creator's video.
- **Disclosed AI character.** Every caption carries `#AI` and every script
  contains an explicit "made with AI" line. The character sheet
  (`config/character.yaml`) is the single source of truth and is cached on
  every Claude API call.
- **No body-transformation framing.** A safety layer (`script/safety_rails.py`)
  rejects before/after phrasing, weight-loss numbers, and prescriptive
  medical language. The character's visual identity is locked to a single
  body type across all generations.

## Architecture

```
trends/        multi-source trend collection + niche scoring
character/     character sheet loader + Higgsfield prompt builder
script/        Claude-powered script writer + post-generation safety rails
upload/        Instagram Graph API publisher
cli.py         JSON-in/JSON-out command pipeline
```

## Pipeline (end-to-end)

```
          fetch-trends                 rank-trends                 brief
TikTok  ─┐                                                         │
Google  ─┼──► trends.json ─────────► ranked.json ────────────► brief.json
YouTube ─┘                                                         │
Manual  ─┘                                                         │
                                                                   ▼
                                                                 script
                                             character.yaml ──► script.json
                                                                   │
                     ┌─────────────────────────────────────────────┤
                     ▼                                             ▼
            character-prompts                                    upload
         (paste into Higgsfield)                          Instagram Graph API
```

## Quick start

```bash
# 1. Collect trends from a TikTok Creative Center export + Google seeds
reel-gen fetch-trends \
    --tiktok-fixture tests/reel_generator/fixtures/tiktok_hashtags.json \
    --google-keywords "luteal phase workout" "cycle syncing" "pms nutrition" \
    --output outputs/trends.json

# 2. Rank for the niche
reel-gen rank-trends outputs/trends.json --output outputs/ranked.json

# 3. Synthesize a brief
reel-gen brief outputs/ranked.json --output outputs/brief.json

# 4. Write the script (requires ANTHROPIC_API_KEY)
reel-gen script outputs/brief.json --output outputs/script.json

# 5. Build Higgsfield prompts for each beat
reel-gen character-prompts --script outputs/script.json \
    --output outputs/higgsfield_prompts.json

# 6. (Manual) Generate video in Higgsfield, stitch with ffmpeg, host on a CDN

# 7. Publish to Instagram (requires IG_USER_ID + IG_ACCESS_TOKEN env vars)
reel-gen upload outputs/script.json --video-url https://cdn.example.com/reel.mp4
```

## Trend sources

| Source                   | Legitimacy         | Auth needed                  |
|--------------------------|--------------------|------------------------------|
| TikTok Creative Center   | Official (UI) / unofficial JSON endpoint | None for fixtures, UA header for HTTP |
| Google Trends (pytrends) | Unofficial wrapper | None                         |
| YouTube Data API         | Official API       | `YOUTUBE_API_KEY`            |
| Manual CSV               | Export from CC UI  | None                         |

Start with manual CSV + fixtures while you're iterating — you don't need
any API keys to test the pipeline end-to-end up through `brief`.

## Character sheet

The character sheet is a YAML file with a locked schema. Do not remove:

- `disclosure_handle` — forced into every caption
- `forbidden_claims` — enforced by safety rails
- `visual.avoid` — fed into Higgsfield negative prompts

If you want a different niche or different character, copy
`config/character.yaml` to a new file and pass `--character path/to/new.yaml`
to `reel-gen script` and `reel-gen character-prompts`.

## Safety rails

`script/safety_rails.py` runs on every generated script:

1. **forbidden_claim** — any string from `character.forbidden_claims`
2. **missing_disclosure** — caption lacks the `#AI` handle
3. **missing_disclosure_line** — empty disclosure_line
4. **body_transformation** — before/after, "lost N lbs", "shrink your waist"
5. **prescriptive_medical** — diagnosis language, "stop taking medication"
6. **unsourced_claim** — "studies show…" with empty `sources[]`

Scripts with any violation are tagged `needs_human_review` and blocked
from upload by `reel-gen upload`.

## Ethics checklist

Before publishing any reel from this pipeline:

- [ ] Caption contains `#AI` and a natural-language "made with AI" line
- [ ] Character's visible body type matches the character sheet (no
      transformation framing)
- [ ] Any factual claim is cited in `sources[]`
- [ ] No diagnosis / no "stop your medication" / no "replace your doctor"
- [ ] Topic is based on *trend signals*, not a specific creator's video

This is the baseline Meta's AI-disclosure policy and FTC endorsement
guidelines require. Stricter niches (e.g. prescription-drug topics) need
more — don't expand into them with this pipeline as-is.
