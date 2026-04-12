"""Load the character sheet from YAML."""

from __future__ import annotations

from pathlib import Path

from reel_generator.models import Character


def load_character(path: Path | str) -> Character:
    """Load a Character from a YAML file.

    Uses PyYAML's safe_load — the character sheet is plain config, no tags.
    """
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyYAML is required to load the character sheet. "
            "Install with `pip install pyyaml`."
        ) from exc

    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Character sheet must be a YAML mapping, got {type(data).__name__}")

    # Character.visual is declared as dict[str, str] but we want to preserve
    # the 'avoid' list — stringify it so Pydantic is happy while keeping the
    # content human-readable.
    visual = data.get("visual", {})
    if isinstance(visual, dict) and isinstance(visual.get("avoid"), list):
        visual = {**visual, "avoid": "; ".join(str(x) for x in visual["avoid"])}
        data["visual"] = visual

    return Character.model_validate(data)
