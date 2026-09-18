"""Additional corpus validation tests targeting missing lines 26, 32, 34, 36, 66."""

import pytest

from voicefont.corpus import load_corpus, validate_corpus


def _valid_corpus():
    corpus = load_corpus()
    # Use a deep copy so mutations don't affect other tests
    import copy
    return copy.deepcopy(corpus)


def test_invalid_identifier_format_rejected():
    """Line 26: identifier regex rejects bad prompt IDs."""
    corpus = _valid_corpus()
    corpus["prompts"][0]["id"] = "HasUpperCase"
    with pytest.raises(ValueError, match="Invalid corpus identifier"):
        validate_corpus(corpus)


def test_non_en_gb_language_rejected():
    """Line 32: only en-GB is supported."""
    corpus = _valid_corpus()
    corpus["language"] = "en-US"
    with pytest.raises(ValueError, match="en-GB"):
        validate_corpus(corpus)


def test_empty_categories_rejected():
    """Line 34: categories must be a non-empty list."""
    corpus = _valid_corpus()
    corpus["categories"] = []
    with pytest.raises(ValueError, match="categories"):
        validate_corpus(corpus)


def test_too_few_prompts_rejected():
    """Line 36: must have at least 70 prompts."""
    corpus = _valid_corpus()
    corpus["prompts"] = corpus["prompts"][:10]
    with pytest.raises(ValueError, match="70"):
        validate_corpus(corpus)


def test_category_without_prompts_rejected():
    """Line 66: every category must contain at least one prompt."""
    corpus = _valid_corpus()
    # Add an extra category with no prompts
    corpus["categories"].append({
        "id": "unused-cat",
        "title": "Unused",
        "description": "Category with no prompts",
    })
    with pytest.raises(ValueError, match="Every category"):
        validate_corpus(corpus)
