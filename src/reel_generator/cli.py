"""CLI for reel_generator.

Commands:
  fetch-trends        Pull trends from configured providers, write to JSON.
  rank-trends         Rank trends for the cycle+fitness niche.
  brief               Build a ContentBrief from ranked trends.
  character-prompts   Emit Higgsfield prompts for a saved script.
  script              Run ScriptWriter against a brief (needs ANTHROPIC_API_KEY).
  upload              Publish a script's video to Instagram (needs IG_* env).

Every command reads/writes JSON so it's easy to chain in a shell script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reel_generator.character import build_image_prompt, build_video_prompt, load_character
from reel_generator.models import ContentBrief, Script, Trend, UploadRequest
from reel_generator.script import ScriptWriter, build_brief_from_trends
from reel_generator.trends import (
    GoogleTrendsProvider,
    ManualCsvProvider,
    TikTokCreativeCenterProvider,
    TrendAggregator,
    YouTubeProvider,
)


def _write_json(path: Path | None, payload) -> None:
    text = json.dumps(payload, indent=2, default=str, sort_keys=True)
    if path is None:
        print(text)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def cmd_fetch_trends(args: argparse.Namespace) -> int:
    providers = []
    if args.tiktok_fixture:
        providers.append(
            TikTokCreativeCenterProvider(
                mode="fixture",
                fixture_path=Path(args.tiktok_fixture),
                region=args.region,
            )
        )
    if args.manual_csv:
        providers.append(ManualCsvProvider(path=Path(args.manual_csv), region=args.region))
    if args.google_keywords:
        providers.append(
            GoogleTrendsProvider(keywords=args.google_keywords, geo=args.region)
        )
    if args.youtube:
        import requests  # type: ignore

        providers.append(YouTubeProvider(region=args.region, session=requests.Session()))
    if not providers:
        print("No providers configured. Use --tiktok-fixture / --manual-csv / --google-keywords / --youtube", file=sys.stderr)
        return 2

    agg = TrendAggregator(providers=providers)
    trends = agg.collect()
    _write_json(Path(args.output) if args.output else None, [t.model_dump(mode="json") for t in trends])
    return 0


def cmd_rank_trends(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    trends = [Trend.model_validate(r) for r in raw]
    agg = TrendAggregator(providers=[])
    ranked = agg.rank_for_niche(trends, min_niche_score=args.min_niche_score)
    payload = [
        {"trend": t.model_dump(mode="json"), "combined_score": score, "phase": phase.value}
        for t, score, phase in ranked
    ]
    _write_json(Path(args.output) if args.output else None, payload)
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.ranked).read_text(encoding="utf-8"))
    from reel_generator.models import CyclePhase

    ranked = [
        (Trend.model_validate(r["trend"]), float(r["combined_score"]), CyclePhase(r["phase"]))
        for r in raw
    ]
    brief = build_brief_from_trends(ranked, top_n=args.top_n)
    _write_json(Path(args.output) if args.output else None, brief.model_dump(mode="json"))
    return 0


def cmd_script(args: argparse.Namespace) -> int:
    character = load_character(args.character)
    brief = ContentBrief.model_validate_json(Path(args.brief).read_text(encoding="utf-8"))
    writer = ScriptWriter(character=character, model=args.model)
    script = writer.write(brief)
    _write_json(Path(args.output) if args.output else None, script.model_dump(mode="json"))
    if script.safety_review != "passed":
        print(f"WARNING: script flagged as {script.safety_review}", file=sys.stderr)
        return 1
    return 0


def cmd_character_prompts(args: argparse.Namespace) -> int:
    character = load_character(args.character)
    if args.script:
        script = Script.model_validate_json(Path(args.script).read_text(encoding="utf-8"))
        prompts = [
            build_video_prompt(character, script, beat_index=i)
            for i in range(len(script.beats))
        ]
    else:
        prompts = [build_image_prompt(character, scene=args.scene or "neutral studio reference shot")]
    _write_json(Path(args.output) if args.output else None, prompts)
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    import requests  # type: ignore

    from reel_generator.upload import InstagramReelUploader

    script = Script.model_validate_json(Path(args.script).read_text(encoding="utf-8"))
    if script.safety_review != "passed":
        print(f"Refusing to upload — safety_review={script.safety_review}", file=sys.stderr)
        return 1
    request = UploadRequest(video_url=args.video_url, caption=script.caption)
    uploader = InstagramReelUploader.from_env(session=requests.Session())
    result = uploader.publish(request)
    _write_json(None, result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reel-gen", description="Disclosed-AI Reels pipeline (cycle+fitness)")
    sub = parser.add_subparsers(dest="command", required=True)

    ft = sub.add_parser("fetch-trends")
    ft.add_argument("--tiktok-fixture")
    ft.add_argument("--manual-csv")
    ft.add_argument("--google-keywords", nargs="*")
    ft.add_argument("--youtube", action="store_true")
    ft.add_argument("--region", default="US")
    ft.add_argument("--output")
    ft.set_defaults(func=cmd_fetch_trends)

    rt = sub.add_parser("rank-trends")
    rt.add_argument("input")
    rt.add_argument("--min-niche-score", type=float, default=0.2)
    rt.add_argument("--output")
    rt.set_defaults(func=cmd_rank_trends)

    br = sub.add_parser("brief")
    br.add_argument("ranked")
    br.add_argument("--top-n", type=int, default=5)
    br.add_argument("--output")
    br.set_defaults(func=cmd_brief)

    sc = sub.add_parser("script")
    sc.add_argument("brief")
    sc.add_argument("--character", default="config/character.yaml")
    sc.add_argument("--model", default="claude-opus-4-6")
    sc.add_argument("--output")
    sc.set_defaults(func=cmd_script)

    cp = sub.add_parser("character-prompts")
    cp.add_argument("--character", default="config/character.yaml")
    cp.add_argument("--script", help="Build video prompts for each beat")
    cp.add_argument("--scene", help="Build a single image prompt for this scene")
    cp.add_argument("--output")
    cp.set_defaults(func=cmd_character_prompts)

    up = sub.add_parser("upload")
    up.add_argument("script")
    up.add_argument("--video-url", required=True)
    up.set_defaults(func=cmd_upload)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
