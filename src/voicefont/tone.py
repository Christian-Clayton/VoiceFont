"""Deterministic text tone analysis for speech delivery, no network or LLM.

Versioned heuristic lexicon: valence, arousal, urgency, question and emphasis
counts. Transparent and reproducible; it does not understand language and must
not be presented as emotion recognition of a person.
"""

from __future__ import annotations

import re

TONE_VERSION = "tone-v1"
MAX_TEXT_CHARS = 1000

_POSITIVE = {
    "good",
    "great",
    "excellent",
    "happy",
    "glad",
    "pleased",
    "wonderful",
    "fantastic",
    "success",
    "succeeded",
    "win",
    "won",
    "love",
    "best",
    "thanks",
    "welcome",
    "agree",
    "approved",
    "brilliant",
    "perfect",
    "progress",
    "ready",
}
_NEGATIVE = {
    "bad",
    "poor",
    "unfortunately",
    "failed",
    "fail",
    "failure",
    "wrong",
    "problem",
    "broken",
    "angry",
    "upset",
    "disappointed",
    "concern",
    "concerns",
    "risk",
    "regret",
    "sorry",
    "worse",
    "worst",
    "decline",
    "blocked",
    "delayed",
}
_URGENT = {
    "now",
    "immediately",
    "urgent",
    "urgently",
    "asap",
    "hurry",
    "deadline",
    "critical",
    "emergency",
    "today",
    "quickly",
    "fast",
    "priority",
    "instantly",
}
_INTENSIFIERS = {
    "very",
    "extremely",
    "really",
    "absolutely",
    "totally",
    "completely",
    "highly",
    "incredibly",
    "deeply",
    "severely",
    "utterly",
}


def analyze(text: str) -> dict:
    """Return bounded valence/arousal/urgency plus punctuation counts."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("text exceeds maximum length")
    words = re.findall(r"[a-z']+", text.lower())
    positive = sum(1 for word in words if word in _POSITIVE)
    negative = sum(1 for word in words if word in _NEGATIVE)
    urgent = sum(1 for word in words if word in _URGENT)
    intensifiers = sum(1 for word in words if word in _INTENSIFIERS)
    shouts = sum(1 for word in set(re.findall(r"\b[A-Z]{3,}\b", text)))
    exclamations = text.count("!")
    questions = text.count("?")
    count = len(words)
    valence = 0.5 + (positive - negative) / (count + 4)
    arousal = min(
        1.0,
        (exclamations * 0.25 + shouts * 0.2 + intensifiers * 0.1 + urgent * 0.15) / 2,
    )
    urgency = min(1.0, (urgent * 0.3 + exclamations * 0.15) / 1.5)
    return {
        "version": TONE_VERSION,
        "valence": round(min(1.0, max(0.0, valence)), 4),
        "arousal": round(arousal, 4),
        "urgency": round(urgency, 4),
        "questions": questions,
        "exclamations": exclamations,
    }
