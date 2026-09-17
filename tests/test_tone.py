"""Tone analysis tests: deterministic lexicon rules, no network or LLM."""

import pytest

from voicefont.tone import TONE_VERSION, analyze


def test_version_is_declared():
    assert TONE_VERSION == "tone-v1"


def test_shape_and_bounded_scores():
    result = analyze("The update shipped on time.")
    assert result["version"] == "tone-v1"
    for label in ("valence", "arousal", "urgency"):
        assert 0.0 <= result[label] <= 1.0
    assert isinstance(result["questions"], int)
    assert result["exclamations"] == 0


def test_positive_lexicon_raises_valence():
    plain = analyze("The report is done.")
    happy = analyze("Great news, the report is done and it is excellent.")
    assert happy["valence"] > plain["valence"]


def test_negative_lexicon_lowers_valence():
    plain = analyze("The report is done.")
    sad = analyze("Unfortunately the report failed and the results are bad.")
    assert sad["valence"] < plain["valence"]


def test_questions_and_exclamations_counted():
    result = analyze("Are you ready? Really ready? Wow!")
    assert result["questions"] == 2
    assert result["exclamations"] == 1


def test_emphasis_markers_raise_arousal():
    calm = analyze("Please review the document.")
    emphatic = analyze("PLEASE review the document IMMEDIATELY! This is critical!")
    assert emphatic["arousal"] > calm["arousal"]
    assert emphatic["urgency"] > calm["urgency"]


def test_urgency_lexicon_detected():
    result = analyze("We need this now. The deadline is urgent, hurry.")
    assert result["urgency"] > 0.5


def test_empty_text_is_neutral():
    result = analyze("   ")
    assert result["questions"] == 0
    assert 0.4 <= result["valence"] <= 0.6
    assert 0.0 <= result["arousal"] <= 0.2


def test_length_is_bounded():
    with pytest.raises(ValueError):
        analyze("x" * 1001)
