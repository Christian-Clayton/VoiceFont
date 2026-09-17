"""Bundled original calibration prompts and reproducible printable reference."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files


def validate_corpus(corpus: dict) -> None:
    """Reject malformed bundled data before any session uses prompt identifiers."""

    def fields(value, required):
        if not isinstance(value, dict) or set(value) != set(required.split()):
            raise ValueError("Corpus fields do not match the product contract")

    def text(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Corpus strings must be nonempty")

    def identifier(value):
        text(value)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
            raise ValueError("Invalid corpus identifier")

    fields(corpus, "version language title disclaimer categories prompts")
    for key in ("version", "language", "title", "disclaimer"):
        text(corpus[key])
    if corpus["language"] != "en-GB":
        raise ValueError("This corpus requires en-GB")
    if not isinstance(corpus["categories"], list) or not corpus["categories"]:
        raise ValueError("Corpus needs categories")
    if not isinstance(corpus["prompts"], list) or len(corpus["prompts"]) < 70:
        raise ValueError("Corpus needs at least 70 prompts")
    category_ids = set()
    for category in corpus["categories"]:
        fields(category, "id title description")
        identifier(category["id"])
        text(category["title"])
        text(category["description"])
        if category["id"] in category_ids:
            raise ValueError("Duplicate category identifier")
        category_ids.add(category["id"])
    prompt_ids = set()
    used_categories = set()
    for prompt in corpus["prompts"]:
        fields(prompt, "id category text instruction dimensions optional style")
        identifier(prompt["id"])
        if prompt["id"] in prompt_ids:
            raise ValueError("Duplicate prompt identifier")
        prompt_ids.add(prompt["id"])
        if prompt["category"] not in category_ids:
            raise ValueError("Unknown prompt category")
        used_categories.add(prompt["category"])
        for key in ("text", "instruction", "style"):
            text(prompt[key])
        if type(prompt["optional"]) is not bool:
            raise ValueError("Optional must be boolean")
        if not isinstance(prompt["dimensions"], list) or not prompt["dimensions"]:
            raise ValueError("Prompt needs dimensions")
        for dimension in prompt["dimensions"]:
            text(dimension)
    if used_categories != category_ids:
        raise ValueError("Every category must contain prompts")


@lru_cache(maxsize=1)
def _bundled_corpus() -> dict:
    source = files("voicefont").joinpath("calibration_assets", "corpus.json")
    corpus = json.loads(source.read_text(encoding="utf-8"))
    validate_corpus(corpus)
    return corpus


def load_corpus() -> dict:
    """Return a detached JSON-compatible dictionary, safe for callers to mutate."""
    return deepcopy(_bundled_corpus())


def render_checklist(corpus: dict) -> str:
    """Render the printable Markdown reference directly from the validated JSON."""
    validate_corpus(corpus)
    required = sum(not p["optional"] for p in corpus["prompts"])
    lines = [
        f"# {corpus['title']}",
        "",
        (
            "**Document type:** reference checklist for the person recording their "
            "own authorised voice."
        ),
        "",
        (
            f"Version {corpus['version']} | Language {corpus['language']} | "
            f"{len(corpus['prompts'])} prompts | {required} core, "
            f"{len(corpus['prompts']) - required} optional"
        ),
        "",
        corpus["disclaimer"],
        "",
        "## Before recording",
        "",
        "- [ ] Confirm permission to record and use this voice locally.",
        "- [ ] Choose a quiet room and keep the microphone at a steady distance.",
        "- [ ] Speak in your natural accent. Pause, drink water or stop whenever needed.",
        "- [ ] Read only the prompt text, not its delivery instruction.",
        (
            "- [ ] Replay a short take before continuing. Reduce input gain if "
            "clipped; move closer if too quiet."
        ),
        (
            "- [ ] Save each take before changing prompts. Saved takes survive "
            "reload; unsaved browser audio does not."
        ),
        "- [ ] Use Export backup to keep a ZIP of the session and raw takes.",
        "",
        (
            "Coverage means recorded prompts, not verified phoneme accuracy or "
            "captured vocal ability. Partial finalisation needs at least three "
            "accepted prompts from two categories. Skipped and optional prompts "
            "remain visible; no exhaustive coverage is promised."
        ),
        "",
    ]
    for category in corpus["categories"]:
        prompts = [p for p in corpus["prompts"] if p["category"] == category["id"]]
        lines += [f"## {category['title']} ({len(prompts)})", "", category["description"], ""]
        for prompt in prompts:
            kind = "optional" if prompt["optional"] else "core"
            lines += [
                f"- [ ] **{prompt['id']}** ({kind}, {prompt['style']})",
                f"  - Say: {prompt['text']}",
                f"  - Delivery: {prompt['instruction']}",
                f"  - Intended dimensions: {', '.join(prompt['dimensions'])}",
                "",
            ]
    return "\n".join(lines) + "\n"
