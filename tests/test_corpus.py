"""Corpus integrity and printable checklist stay tied to one source."""

import json
from pathlib import Path

import pytest

from voicefont.corpus import load_corpus, render_checklist, validate_corpus


def test_corpus_is_original_bounded_and_complete():
    corpus = load_corpus()
    assert set(corpus) == {"version", "language", "title", "disclaimer", "categories", "prompts"}
    assert corpus["language"] == "en-GB"
    assert len(corpus["prompts"]) >= 70
    assert len({p["id"] for p in corpus["prompts"]}) == len(corpus["prompts"])
    assert all(
        set(p) == {"id", "category", "text", "instruction", "dimensions", "optional", "style"}
        for p in corpus["prompts"]
    )
    assert {
        "phonetic",
        "connected",
        "questions",
        "range",
        "expression",
        "conversation",
        "consistency",
    } <= {c["id"] for c in corpus["categories"]}
    assert all(
        any(p["category"] == c["id"] for p in corpus["prompts"]) for c in corpus["categories"]
    )
    assert "\u2014" not in json.dumps(corpus, ensure_ascii=False)


def test_load_returns_deep_detached_copy():
    first = load_corpus()
    first["prompts"][0]["dimensions"].clear()
    first["categories"][0]["title"] = "changed"
    second = load_corpus()
    assert second["prompts"][0]["dimensions"]
    assert second["categories"][0]["title"] != "changed"


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_prompt",
        "duplicate_category",
        "missing",
        "unknown_category",
        "empty_text",
        "bad_optional",
        "empty_dimensions",
    ],
)
def test_invalid_corpus_rejected(mutation):
    corpus = load_corpus()
    if mutation == "duplicate_prompt":
        corpus["prompts"][1]["id"] = corpus["prompts"][0]["id"]
    elif mutation == "duplicate_category":
        corpus["categories"][1]["id"] = corpus["categories"][0]["id"]
    elif mutation == "missing":
        del corpus["prompts"][0]["instruction"]
    elif mutation == "unknown_category":
        corpus["prompts"][0]["category"] = "missing"
    elif mutation == "empty_text":
        corpus["prompts"][0]["text"] = " "
    elif mutation == "bad_optional":
        corpus["prompts"][0]["optional"] = "false"
    else:
        corpus["prompts"][0]["dimensions"] = []
    with pytest.raises(ValueError):
        validate_corpus(corpus)


def test_printable_checklist_exactly_matches_json():
    path = Path(__file__).parents[1] / "docs" / "Calibration Checklist.md"
    assert path.read_text(encoding="utf-8") == render_checklist(load_corpus())
