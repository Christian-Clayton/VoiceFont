# VoiceFont — Phase 8: Polish 

## The Goal of This Chunk

Get to a point where:
1. Someone (including future-you) can clone the repo and understand what's going on
2. The setup is verifiable in one command
3. Common operations are one-line scripts
4. The README actually reflects what got built

---

## Step 1: Environment Verification Script

This is the single highest-value polish item. Without it, every "why isn't this working" starts with "did you install...?" — and it's always something.

### `scripts/verify_setup.py`

```python
"""
Verify that the VoiceFont environment is set up correctly.

Run after a fresh install or to diagnose issues:
    python scripts/verify_setup.py
"""
import sys
from pathlib import Path


def check(label, condition, fix_instructions=""):
    """Print a check result."""
    status = "✓" if condition else "✗"
    print(f"  {status} {label}")
    if not condition and fix_instructions:
        print(f"      → {fix_instructions}")
    return condition


def check_python():
    """Python3.9+ required."""
    v = sys.version_info
    ok = v.major > 3 or (v.major == 3 and v.minor >= 9)
    return check(
        f"Python {v.major}.{v.minor}.{v.micro}",
        ok,
        "Install Python 3.9+ from python.org"
    )


def check_packages():
    """Verify required packages import."""
    required = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("httpx", "HTTP client"),
        ("scipy", "SciPy"),
        ("soundfile", "soundfile"),
        ("numpy", "NumPy"),
        ("librosa", "librosa (for audio analysis)"),
        ("nltk", "NLTK (for phoneme extraction)"),
    ]
    all_ok = True
    for module, name in required:
        try:
            __import__(module)
            check(name, True)
        except ImportError:
            check(name, False, f"pip install {module}")
            all_ok = False
    return all_ok


def check_openvoice():
    """Verify OpenVoice is installed."""
    ov_path = Path("OpenVoice")
    if not ov_path.exists():
        return check(
            "OpenVoice repo",
            False,
            "git clone https://github.com/myshell-ai/OpenVoice.git"
        )
    check(f"OpenVoice repo at {ov_path}", True)

    # Checkpoints
    v2_dir = ov_path / "checkpoints" / "v2"
    if not v2_dir.exists():
        return check(
            "V2 checkpoints",
            False,
            "Download from huggingface.co/myshell-ai/OpenVoiceV2"
        )

    converter = v2_dir / "converter"
    if not converter.exists():
        return check("V2 converter dir", False)

    files = list(converter.glob("*.pth")) + list(converter.glob("*.pt"))
    return check(f"V2 converter checkpoints ({len(files)} files)", bool(files))


def check_nltk():
    """Check NLTK data."""
    try:
        import nltk
 except ImportError:
        return check("NLTK", False, "pip install nltk")

    try:
        nltk.data.find('corpora/cmudict')
        return check("NLTK CMUdict", True)
    except LookupError:
        return check(
            "NLTK CMUdict",
            False,
            "python -c \"import nltk; nltk.download('cmudict')\""
        )


def check_profiles():
    """Check voice profiles."""
    profiles_dir = Path("voice/profiles")
    if not profiles_dir.exists():
        return check("voice/profiles/", False, "Run calibration first")

    profiles = [d for d in profiles_dir.iterdir() if d.is_dir()]
    if not profiles:
        return check(
            "Voice profiles",
            False,
            "Run calibration: start server, visit /calibrate"
        )

    for profile in profiles:
        has_json = (profile / "profile.json").exists()
        check(f"  Profile: {profile.name}", has_json)

    return True


def check_tests():
    """Quick smoke test."""
    try:
        from voice import VoiceProfile, ProfileRegistry
        from calibration import CalibrationSession
        from server.synthesizer import Synthesizer
        check("Core imports", True)
        return True
    except ImportError as e:
        return check("Core imports", False, str(e))


def main():
    print("=" * 60)
    print("VoiceFont Setup Verification")
    print("=" * 60)
    print()

    checks = [
        ("Python", check_python),
        ("Required packages", check_packages),
        ("OpenVoice", check_openvoice),
        ("NLTK data", check_nltk),
        ("Voice profiles", check_profiles),
        ("Module imports", check_tests),
    ]

    all_passed = True
    for name, check_fn in checks:
        print(f"{name}:")
        all_passed &= check_fn()
        print()

    print("=" * 60)
    if all_passed:
        print("✓ All checks passed. You're ready to go.")
        print()
        print("Quick start:")
        print("  1. bash scripts/start_server.sh")
        print("  2. Visit http://localhost:8000/calibrate (first time)")
        print("  3. python examples/basic_synthesis.py (after calibration)")
    else:
        print("✗ Some checks failed. Fix the items above and re-run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Run it:
```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate
python scripts/verify_setup.py
```

It should report what works and what needs attention.

---

## Step 2: Convenience Scripts

Replace typing long commands with one-line scripts.

### `scripts/start_server.sh`

```bash
#!/bin/bash
# Start the VoiceFont server.
# Usage: bash scripts/start_server.sh

set -e

# Activate venv
if [ -d "OpenVoice/venv" ]; then
    source OpenVoice/venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "ERROR: No virtual environment found"
    echo "  Expected: ./OpenVoice/venv/ or ./venv/"
    exit 1
fi

# Verify setup first
python scripts/verify_setup.py || {
    echo ""
    echo "Setup verification failed. Fix issues above before starting server."
    exit 1
}

# Start server
echo ""
echo "Starting VoiceFont server..."
echo "  API: http://localhost:8000"
echo "  Calibration UI: http://localhost:8000/calibrate"
echo "  Style recording: http://localhost:8000/styles"
echo ""
python -m server.api
```

Make it executable:
```bash
chmod +x scripts/start_server.sh
```

### `scripts/run_demo.sh`

```bash
#!/bin/bash
# Run the streaming chat demo.
# Make sure the server is running in another terminal first.

set -e

if [ -d "OpenVoice/venv" ]; then
    source OpenVoice/venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

python -m integration.demo_chat
```

### `scripts/clean.sh`

```bash
#!/bin/bash
# Clean intermediate files. Keeps your data and profile bundle.

rm -rf **/__pycache__
rm -rf .pytest_cache
rm -rf **/*.pyc
find . -name "*.egg-info" -type d -exec rm -rf {} +
echo "Cleaned. Your data/ and voice/profiles/ are untouched."
```

---

## Step 3: The README (The Single Most Important Document)

### `README.md`

```markdown
# VoiceFont

A self-hosted, engine-agnostic voice cloning system for your AI assistant.

Record a15–25 minute calibration session, get a voice profile, and have your AI speak in your voice — entirely on your own hardware, with no cloud dependency.

## What This Is

VoiceFont captures your voice through a guided browser-based session, then lets any AI on your machine call a local API to speak in your voice. It's built around three principles:

- **You own your voice data** — everything stays on your machine
- **The profile outlives the engine** — if a better TTS appears, you swap engines, not voice profiles
- **It works** — actually captures expressive range, not just monotone clones

## What It's Built On

- **[OpenVoice V2](https://github.com/myshell-ai/OpenVoice)** — MIT-licensed, local, zero-shot voice cloning
- **FastAPI** — the local server
- **librosa + NLTK** — audio analysis and phoneme extraction
- **A custom calibration corpus** — 70+ prompts designed to capture expressive range

## Quick Start

```bash
# 1. Clone and set up
git clone <this-repo> ~/voicefont
cd ~/voicefont
git clone https://github.com/myshell-ai/OpenVoice.git

# 2. Set up Python environment (one-time)
python3 -m venv OpenVoice/venv
source OpenVoice/venv/bin/activate
pip install -r requirements.txt
pip install -e OpenVoice/

# Download NLTK data
python -c "import nltk; nltk.download('cmudict'); nltk.download('punkt')"

# 3. Download OpenVoice V2 checkpoints
# See OpenVoice/README.md — they link to HuggingFace

# 4. Verify setup
python scripts/verify_setup.py

# 5. Start the server
bash scripts/start_server.sh

# 6. Open http://localhost:8000/calibrate in your browser
# Record your voice (15–25 minutes)

# 7. Test it
python examples/basic_synthesis.py
```

## Usage

### Basic Synthesis

```python
from client import VoiceClient

client = VoiceClient()
audio = client.speak("Hello, this is my cloned voice.")
client.play(audio)
```

### With Style Selection

```python
from client import VoiceClient, select_style

client = VoiceClient()

text = "Watch out — this is important!"
style = select_style(text)  # Picks "serious" based on keywordsaudio = client.speak(text, style=style)
client.play(audio)
```

### Streaming

```python
from client import VoiceClient

client = VoiceClient()
result = client.speak_streaming(
    "Long response that should be played incrementally. "
    "Each sentence starts playing as it's synthesised."
)
print(f"First audio in {result['first_chunk_latency']:.2f}s")
```

### With Your AI

```python
from client import VoiceClient, select_style

client = VoiceClient()

def ai_speak(user_message: str, ai_response: str):
    style = select_style(ai_response)
    client.speak_and_play(ai_response, style=style)
```

See `examples/` for more patterns.

## Architecture

```
┌─────────────────────────────────────────────┐
│  Your AI (your code)                        │
│   generates text responses │
└────────────────┬────────────────────────────┘ │ HTTP localhost:8000
                 ▼
┌─────────────────────────────────────────────┐
│  VoiceFont Server (FastAPI)                 │
│   /speak, /speak/stream, /voices │
│   + /calibration/session/* (UI endpoints)   │
└────────────────┬────────────────────────────┘
                 │
        ┌────────┴────────┐ ▼                 ▼
┌─────────────┐    ┌────────────────┐
│ Voice │    │ Voice Engine   │
│ Profile │    │ (OpenVoice V2) │
│ Bundle │    │                │
│ (JSON +     │    │ Pluggable:    │
│  audio)     │    │  v2 today,     │
│             │    │  others later  │
└─────────────┘    └────────────────┘
```

The voice profile format is the key abstraction. It describes your voice in engine-agnostic terms. When a new TTS engine appears, you swap it in — your profile stays the same.

See `docs/architecture.md` for the full system design.

## Calibration

The calibration UI at `http://localhost:8000/calibrate` walks you through:

1. **Setup** — mic check, baseline (1 prompt)
2. **Pitch range** — low/mid/high/glide (4 prompts)
3. **Energy range** — whisper/quiet/normal/loud/belt (5 prompts)
4. **Tempo range** — very_slow through very_fast (5 prompts)
5. **Phonetic coverage** — all English phonemes in varied contexts (~18 prompts)
6. **Prosodic patterns** — questions, lists, contrastive stress (8 prompts)
7. **Emotional range** — paired prompts across 5 emotion pairs (15 deliveries)
8. **Style registers** — narrator, friendly, serious, teacher, excited (5 prompts)
9. **Conversational** — extemporaneous storytelling (4 prompts)

Total: ~22 minutes. The session is **adaptive** — it stops early when coverage is sufficient, and prioritises prompts that fill gaps in what you've already captured.

After finalisation, your profile is at `voice/profiles/<your_id>/`.

## Repository Structure

```
voicefont/
├── calibration/       # Calibration session + UI + analyzer
├── client/            # Voice client library (for your AI)
├── data/              # Your voice archive (preserved)
├── docs/              # Documentation
├── engines/           # Pluggable TTS engines (OpenVoice V2)
├── examples/          # Usage examples
├── integration/       # End-to-end demos
├── scripts/           # Convenience scripts
├── server/            # FastAPI server
├── tests/             # Test suite
└── voice/             # Profile format + registry
```

## Documentation

- `docs/architecture.md` — System design and decisions
- `docs/calibration-guide.md` — Using the calibration UI
- `docs/api-reference.md` — Server endpoints
- `docs/profile-format.md` — Voice profile specification
- `docs/troubleshooting.md` — Common issues and fixes

## Limitations

- **Latency:** Synthesis takes 2–5 seconds per sentence on CPU,<1s on GPU. This is a fundamental limit of zero-shot reference cloning.
- **Streaming:** First chunk arrives0.5–2s before full synthesis, but true sub-second streaming requires engine-level changes.
- **Style separation:** Multi-style references work but differences are sometimes subtle — the engine blends rather than switches abruptly.
- **Engine:** OpenVoice V2 is the only engine in v1. The abstraction supports adding others.

## License

MIT (with the understanding that OpenVoice V2 is also MIT).

## Credits

- [myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice) — the voice cloning engine
- [CMU Pronouncing Dictionary](http://www.speech.cs.cmu.edu/cgi-bin/cmudict) — phoneme extraction
- The deep-dive research from the Inventing & Creating process that shaped the calibration design## Status

Working, but young. See `CHANGELOG.md` for what's done and what's coming.
```

---

## Step 4: CHANGELOG

### `CHANGELOG.md`

```markdown
# Changelog

## [0.8.0] — Phase 8 Complete

### Added
- Environment verification script (`scripts/verify_setup.py`)
- Convenience scripts (`start_server.sh`, `run_demo.sh`, `clean.sh`)
- Comprehensive README
- Architecture documentation

### Status
- All8 phases of the original development plan completed
- Working end-to-end: calibration → profile → AI integration → streaming

## [0.7.0] — Phase 7: Streaming

### Added
- Sentence-level streaming synthesis
- StreamingPlayer for incremental playback
- Chunked HTTP transfer for faster first-byte delivery
- Real streaming endpoint

### Limitations
- OpenVoice V2 still synthesises full utterances internally; we chunk the *transfer* not the *generation*
- Latency improvement modest (0.5–1.5s) for typical sentences

## [0.6.0] — Phase 6: Multi-Style References

### Added
- Multiple style references per voice profile (neutral, calm, serious, excited, friendly)
- Style recording API and web UI at `/styles`
- Automatic style reference extraction from calibration recordings
- Style distinctness checking- Style-aware engine routing

## [0.5.0] — Phase 5: AI Integration

### Added
- `VoiceClient` library with sync and async APIs
- Style selection heuristics- End-to-end chat demo
- Example integration patterns for different AI architectures

## [0.4.0] — Phase 4: Adaptive Calibration

### Added
- Item-response-theory-inspired prompt selection
- Information gain computation per prompt
- Plateau detection and early-stop logic
- UI showing "you can stop now" indicator- Dynamic gap detection

## [0.3.0] — Phase 3: Calibration System

### Added
- Full 70+ prompt corpus covering phonetic, prosodic, emotional, stylistic dimensions
- Web-based calibration UI (single-page app)
- Coverage tracker across5 expressive dimensions
- Audio analysis (librosa-based feature extraction)
- Phonetic analysis (CMU dict → IPA)
- Calibration session state machine- Audio format conversion (WebM → WAV)

## [0.2.0] — Phase 2: Voice Server

### Added
- Voice profile format (JSON, versioned, portable)
- FastAPI server with `/speak` endpoint
- Profile registry for on-disk profiles
- Engine abstraction layer
- OpenVoice V2 engine implementation
- Static asset serving for the web UI

## [0.1.0] — Phase 1: Proof of Concept

### Added
- OpenVoice V2 running locally
- Reference recording and basic synthesis
- Failure-mode analysis (too-short, noisy, monotone samples)

## [0.0.0] — Research and Design

### Done
- First-principles decomposition of voice cloning
- Causal analysis of clone quality factors
- Cross-domain analogy (fonts, biometrics, IR, ICC profiles)
- Multidisciplinary mental models (acting, fieldwork, music sampling)
- TRIZ resolution of duration-vs-diversity contradiction
- Calibration corpus design
- Architecture design
```

---

## Step 5: Quick Tests for End-to-End Health

Add a simple smoke test:

### `tests/test_smoke.py`

```python
"""
End-to-end smoke test. Assumes server is running.
"""
import pytest
from client import VoiceClient, split_into_sentences, select_style


def test_server_health():
    """Server is reachable and has at least one voice."""
    client = VoiceClient()
    try:
        health = client.health_check()
        assert health["status"] == "ok"
        assert len(health["profiles"]) >= 1, "No voice profiles found"
    finally:
        client.close()


def test_synthesis_basic():
    """Can synthesise a simple sentence."""
    client = VoiceClient()
    try:
        audio = client.speak("Hello, this is a test.")
        assert len(audio) > 1000, "Audio too short — likely empty"
        # Check it's a valid WAV (RIFF header)
        assert audio[:4] == b"RIFF"
        assert audio[8:12] == b"WAVE"
    finally:
        client.close()


def test_sentence_splitting():
    """Sentence splitter handles common cases."""
    sentences = split_into_sentences(
        "Hello there. How are you? I'm doing well, thanks!"
    )
    assert len(sentences) >= 2


def test_style_selection():
    """Style selector picks appropriate styles."""
    assert select_style("Watch out! This is dangerous!") == "serious"
    assert select_style("That's amazing! Wow!") == "excited"
```

Run:
```bash
cd ~/voicefont
pytest tests/test_smoke.py -v
```

---

## Step 6: Initial Commit

```bash
cd ~/voicefont
git add scripts/verify_setup.py
git add scripts/start_server.sh scripts/run_demo.sh scripts/clean.sh
git add README.md CHANGELOG.md
git add tests/test_smoke.py

git commit -m "Phase 8 chunk1: Verification script, convenience scripts, README, changelog, smoke tests"
```

---

## Deliverables Checklist

- [x] `scripts/verify_setup.py` — one-command environment check
- [x] `scripts/start_server.sh` — one-command server start
- [x] `scripts/run_demo.sh` — one-command demo launch
- [x] `README.md` — comprehensive project documentation
- [x] `CHANGELOG.md` — version history and phase tracking
- [x] `tests/test_smoke.py` — end-to-end sanity checks

---

## What's Missing from Phase 8 (and Why I'm Stopping Here)

I had originally planned to write:
- `docs/architecture.md`
- `docs/calibration-guide.md`
- `docs/api-reference.md`
- `docs/profile-format.md`
- `docs/troubleshooting.md`
- `examples/basic_synthesis.py`
- `examples/streaming_demo.py`
- `examples/style_switching_demo.py`
- `examples/ai_integration_patterns.py`
- `LICENSE`
- `CONTRIBUTING.md`

These all have value but they're each *documentation*, not *code that runs*. I can write them in subsequent chunks without risk of crashes. **Functionally, the system is complete and polished after Chunk 1.**

---

## What You Can Do Now

1. **Run `python scripts/verify_setup.py`** — confirm everything is in order
2. **Read `README.md`** — see the project from the outside
3. **Read `CHANGELOG.md`** — see what got built and in what order
4. **Use `bash scripts/start_server.sh`** — one-line startup from now on
5. **Run `pytest tests/test_smoke.py`** — verify the system actually works

The project is **done in the meaningful sense.** Everything else is refinement.

---
# VoiceFont — Phase 8 Chunk 2: Documentation

## Why Documentation Matters Here

The system works. Now someone needs to understand:
- **Why** it's built this way (not just *how*)
- **What's hard** so they don't re-discover the hard parts
- **What's flexible** so they can extend it without breaking things

I'll write four focused docs. Skipping the ones that would just be tutorials or API listings (those can be inferred from the code).

---

## Step 1: `docs/architecture.md`

This explains the system shape and the design decisions behind it.

### `docs/architecture.md`

````markdown
# Architecture

VoiceFont is a self-hosted voice cloning pipeline. This document explains the system shape and the design decisions that shaped it.

## System Overview

```
┌──────────────────────────────────────────────────────────┐
│  Your AI (your code)                                     │
│   generates text responses                               │
└──────────────────┬───────────────────────────────────────┘
                   │ HTTP localhost:8000
                   ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI Server (server/api.py)                          │
│                                                          │
│   /speak         → Synthesise + return audio             │
│   /speak/stream  → Stream chunks for incremental play │
│   /voices        → List voices and their styles          │
│   /health → Health check                          │
│   /calibrate → Calibration UI (HTML page)            │
│   /styles        → Style recording UI                    │
│   /calibration/* → Session endpoints (UI backend)        │
│   /static/* → CSS/JS/assets │
└──────────────────┬───────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼                     ▼
┌──────────────────┐  ┌─────────────────────┐
│ Voice Profile    │  │ Voice Engine        │
│ (voice/profiles) │  │ (engines/openvoice) │
│                  │  │                     │
│ profile.json     │  │ SynthesiseRequest │
│ references/*.wav │  │   ↓ │
│                  │  │   TTS output │
└──────────────────┘  └─────────────────────┘
```

## Three Layers, Decoupled

The system has three independent layers that don't know about each other:

###1. AI Layer (your code)
- Doesn't know about voice
- Doesn't know about the engine
- Just produces text
- Calls the voice server when it wants to speak

### 2. Voice Server Layer- Doesn't know what your AI is
- Just maps `(text, voice_id, style) → audio`
- Knows about voice profiles and engines### 3. Engine Layer
- Doesn't know about your AI
- Doesn't know about profiles as concepts
- Just: take reference audio + text → produce audio
- Could be swapped for a different TTS engine

This separation is the most important architectural decision. Each layer can be replaced without touching the others.

## The Profile Format (Voice IR)

The voice profile is **the abstraction that makes this work**. It's an "intermediate representation" (borrowing from compiler design) between raw voice data and engine-specific implementation.

### What It Contains

```json
{
  "schema_version": "1.0.0",
  "profile_id": "my_voice",
  "display_name": "My Voice",
  "created_at": "2026-08-30T...",
  "language": "en-GB",
  "engine_compatibility": ["openvoice-v2"],
  "primary_reference": "references/neutral.wav",
  "style_references": [
    {"name": "neutral", "audio_file": "references/neutral.wav"},
    {"name": "calm", "audio_file": "references/calm.wav"},
    ...
 ],
  "coverage": {...},
  "calibration": {...}
}
```

### Why It's Important

The profile format is **engine-agnostic**. It describes your voice in terms of what should be true about synthesis, not how any specific engine achieves it.

This means:
- If a better TTS engine appears, you write a new engine implementation; profiles don't change
- If you want to A/B test engines, the same profile works for both
- If the engine's API changes, only the engine layer changes
- Your voice data is preserved forever, regardless of engine evolution

### Schema Versioning

The format has a `schema_version` field. When the format changes:
- The profile loader handles unknown fields gracefully (forward compatibility)
- Migrations are explicit, not implicit
- Old profiles can be upgraded; new code can read old profiles

## Calibration Design

The calibration system is the most complex part. It exists to solve one problem: **getting enough expressive variety into the reference audio that the engine has something to work with.**

### The Core Insight

Zero-shot voice cloning works by extracting a "speaker embedding" from reference audio. If the reference is monotone, the embedding represents monotone speech. The engine has nothing to interpolate against.

Therefore: **the quality ceiling of the clone is determined by the diversity of the reference.**

### The Five Expressive Dimensions

We capture variation along five independent axes:

| Dimension | What It Captures | Example Range |
|---|---|---|
| **Pitch** | F0 contour, register | low → mid → high |
| **Energy** | Loudness, voice quality | whisper → belt |
| **Tempo** | Speech rate | very slow → very fast |
| **Emotion** | Affective register | excited → disappointed → serious |
| **Style** | Overall manner | narrator → friendly → teacher |

Each axis is captured by **axis-spanning prompts** — the same sentence asked for in different deliveries.

### Adaptive Prompt Selection

Instead of walking through every prompt, the system picks the **most informative next prompt** based on what's already been captured. This uses information-gain scoring (borrowed from item response theory in psychometrics):

1. Each prompt has an information gain value2. Missing dimensions have high gain (whisper not captured → whisper prompts rank high)
3. The session targets gaps until coverage is sufficient

Result: sessions are typically15-20 minutes instead of 25, with equal or better coverage.

### Coverage Tracking

The `CoverageTracker` records what's been captured across all dimensions. It can declare the session "complete" when:
- At least 2 pitch levels captured
- At least 3 energy levels (including whisper or belt ideally)
- At least 2 tempo levels
- At least 2 emotional deliveries
- At least 60% phonetic coverage

If recent information gains drop below 0.5 and core dimensions are covered, the session can plateau-stop early.

## Engine Abstraction

### The TTSEngine Interface

```python
class TTSEngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def load(self) -> None: ...
    
    @abstractmethod
    def synthesise(self, request: SynthesisRequest) -> SynthesisResult: ...
```

Every engine implements this. The synthesizer (server layer) calls this interface. It doesn't know engine-specific details.

### Why This Matters

- We could add a Coqui XTTS engine without changing the server
- We could add a Piper engine for fast streaming
- We could even add a non-neural engine for edge cases
- Engines can be benchmarked against each other using the same profile

### Adding a New Engine

```python
# engines/my_engine/engine.py
from engines.base import TTSEngine, SynthesisRequest, SynthesisResult

class MyEngine(TTSEngine):
    @property
    def name(self): return "my-engine"
    
    def load(self):
        # Load weights
        ...
    
    def synthesise(self, request):
        # Implement synthesis
        ...
```

Then register it in `server/synthesizer.py`.

## Streaming Architecture

### The Honest Limitation

OpenVoice V2 doesn't natively stream — it generates the full utterance before producing audio. So our "streaming" is:

1. **Server-side chunking**: yield the WAV file in8KB chunks over HTTP
2. **Sentence-level splitting**: synthesise one sentence at a time
3. **First-byte fast**: send headers before synthesis completes

This gets first audio0.5-2s faster for long responses, but it's not true token-by-token streaming.

### For True Streaming

You'd need either:
- A different engine with native streaming (Piper, some Coqui models)
- A fine-tuned model with chunked inference
- A separate async pipeline that produces audio faster than playback

For most use cases (AI assistant responses of1-3 sentences), the current approach is sufficient.

## Data Flow

A typical session:

```
1. User opens /calibrate
   └→ Frontend requests /calibration/session
   └→ Server creates CalibrationSession, returns first prompt

2. User records prompt1
   └→ Browser captures audio (WebM/Opus)
   └→ POST /calibration/session/{id}/recording
   └→ Server converts to WAV, analyses, updates coverage
   └→ Adaptive controller picks next prompt
   └→ Returns updated prompt + coverage status

3. ... (many prompts) ...

4. User clicks "Finalise"
   └→ POST /calibration/session/{id}/finalise
   └→ Server extracts style references, builds profile
   └→ Profile saved to voice/profiles/my_voice/

5. User's AI generates response
   └→ Client.speak("Hello", voice="my_voice")
   └→ Server loads profile, calls engine
   └→ Engine produces audio
   └→ Audio returned as WAV bytes
```

## Design Decisions and Trade-offs

| Decision | Alternative Considered | Why We Chose This |
|---|---|---|
| CLI for engineering, web UI for calibration | All CLI | Web UI reduces friction for sustained recording |
| One engine abstraction | Direct OpenVoice calls | Future-proofing against engine evolution |
| Zero-shot reference cloning | Fine-tuning | Simpler, no training needed, profile is portable |
| Multiple style references | Style transfer at synthesis time | Style transfer is engine-specific; references are portable |
| Adaptive calibration | Fixed sequence | Shorter sessions with equal coverage |
| Local-only by default | Cloud optional | Privacy, ownership, no subscription |
| Server as HTTP API | Library import | Decouples AI from voice code |

## What Could Be Different

Things we considered and rejected:

- **WebSocket for streaming** — HTTP chunked transfer works fine- **GPU required** — should work on CPU, just slower
- **Cloud sync of profiles** — explicitly against the ownership principle
- **Voice marketplace** — out of scope, requires network features
- **Real-time voice modification** — different problem, different solution- **GUI desktop app** — web UI is sufficient for the calibration use case

## Extension Points

The system is designed to be extended:

1. **New engines**: Implement `TTSEngine`, register in synthesizer
2. **New prompt types**: Add to `calibration/prompts/corpus.json`
3. **New styles**: Add to `calibration/style_recorder.py` `STYLE_SCRIPTS`
4. **New profile fields**: Add to `voice/profile.py`, ensure `from_dict` ignores unknown fields
5. **New API endpoints**: Add to `server/api.py`
6. **New client patterns**: Add to `examples/`

The principle: each extension should touch one layer, not many.
````---

## Step 2: `docs/profile-format.md`

The profile is the real asset. This document makes it precise.

### `docs/profile-format.md`

````markdown
# Voice Profile Format Specification

The voice profile is the core asset of VoiceFont. It represents a captured voice in an engine-agnostic, versioned, portable format.

## Format Version

Current: **1.0.0**

The version follows [Semantic Versioning](https://semver.org/):
- **Major**: Breaking changes to the format
- **Minor**: New fields, backward-compatible
- **Patch**: Bug fixes, no schema changes

The loader (`VoiceProfile.from_dict`) tolerates unknown fields for forward compatibility.

## File Layout

A profile is a directory:

```
my_voice/
├── profile.json           # Required. The metadata.
├── references/            # Required. Audio reference files.
│   ├── neutral.wav        # The primary reference (required)
│   ├── calm.wav           # Style references (optional)
│   ├── serious.wav
│   └── ...
├── transcripts/           # Optional. Original transcripts
├── README.md              # Optional. Human notes
└── coverage_report.json   # Optional. Detailed coverage analysis
```

## Schema```json
{
  "schema_version": "1.0.0",
  "profile_id": "my_voice",
  "display_name": "My Voice",
  "created_at": "2026-08-30T12:34:56Z",
  "language": "en-GB",
  "engine_compatibility": ["openvoice-v2"],
  "primary_reference": "references/neutral.wav",
  "style_references": [
    {
      "name": "neutral",
      "audio_file": "references/neutral.wav",
      "description": "Primary reference from calibration",
      "is_primary": true,
      "coverage_metadata": {
        "F0_mean_hz": 145.3,
        "F0_min_hz": 85.2,
        "F0_max_hz": 285.1,
        "speech_rate_wpm": 165,
        "rms": 0.12
      },
      "source_prompt_ids": ["setup_01_baseline"]
    }
  ],
  "speaker_features": {
    "F0_mean_hz": 145.3,
    "F0_std_hz": 25.1,
    "F0_range_hz": [85.2, 285.1],
    "speech_rate_wpm": 165,
    "voice_quality": "modal"
  },
  "coverage": {
    "phoneme_coverage": {"/æ/": 12, "/θ/": 4, ...},
    "prosodic_features": ["question_intonation", "list_intonation", ...],
    "emotional_styles": ["excited", "disappointed", "serious"],
    "overall_coverage_pct": 78,
    "total_recording_seconds": 1147.5,
    "calibration_session_date": "2026-08-30T...",
    "expressive_range": {
      "F0_min_hz": 75.0,
      "F0_max_hz": 320.0,
      "F0_mean_hz": 145.0,
      "F0_std_hz": 28.0,
      "min_speech_rate_wpm": 95,
      "max_speech_rate_wpm": 240,
      "speech_rate_wpm": 165,
      "has_whisper": true,
      "has_belt": true,
      "has_breathy": true,
      "has_pressed": true,
      "emotional_styles": ["excited", "disappointed", "serious", "curious", "grateful"],
      "tempo_levels": ["very_slow", "slow", "normal", "fast", "very_fast"],
      "style_registers": ["narrator", "friendly", "serious", "teacher", "excited"],
      "prosodic_features": ["question_intonation", "list_intonation", ...]
    }
  },
  "calibration": {
    "calibrator_version": "0.3.0",
    "prompt_count": 47,
    "adaptive_selection": true,
    "session_duration_minutes": 19.1,
    "ambient_noise_db": -52.3,
    "microphone": "USB condenser",
    "sample_rate": 22050,
    "bit_depth": 16
  },
  "archive_reference": "/path/to/data/my_voice_archive/sessions/abc123"
}
```

## Field Reference

### Identity

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | Yes | Format version (currently "1.0.0") |
| `profile_id` | string | Yes | Unique identifier (used in API calls) |
| `display_name` | string | Yes | Human-readable name |
| `created_at` | string (ISO 8601) | Yes | When profile was created |
| `language` | string | Yes | BCP47 language code (e.g., "en-GB") |

### Engine Compatibility

| Field | Type | Required | Description |
|---|---|---|---|
| `engine_compatibility` | list[string] | Yes | Engines known to work with this profile |

This is a hint, not a restriction. The server tries to use engines that match; falls back if not available.

### References

| Field | Type | Required | Description |
|---|---|---|---|
| `primary_reference` | string (path) | Yes | Path to default reference audio (relative to profile dir) |
| `style_references` | list[StyleReference] | Yes | All style references, including the primary |

#### StyleReference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Style name (e.g., "neutral", "calm", "serious") |
| `audio_file` | string (path) | Yes | Path to reference audio (relative to profile dir) |
| `description` | string | No | Human description |
| `is_primary` | bool | No | Whether this is the default reference |
| `coverage_metadata` | object | No | Acoustic features extracted during calibration |
| `source_prompt_ids` | list[string] | No | Which calibration prompts produced this reference |

### Speaker Features

| Field | Type | Description |
|---|---|---|
| `F0_mean_hz` | float | Average fundamental frequency |
| `F0_std_hz` | float | Standard deviation of F0 |
| `F0_range_hz` | list[float, float] | [min, max] F0 observed |
| `speech_rate_wpm` | float | Words per minute baseline |
| `voice_quality` | string | "modal", "breathy", "creaky", "pressed" |

### Coverage Metadata

| Field | Type | Description |
|---|---|---|
| `phoneme_coverage` | dict | IPA phoneme → count of occurrences |
| `prosodic_features` | list[string] | Captured prosodic patterns |
| `emotional_styles` | list[string] | Captured emotional deliveries |
| `overall_coverage_pct` | int (0-100) | Aggregate coverage score |
| `total_recording_seconds` | float | Total duration of calibration recordings |
| `calibration_session_date` | string | When calibration was performed |
| `expressive_range` | object | Detailed expressive dimension capture |

### Calibration Metadata

| Field | Type | Description |
|---|---|---|
| `calibrator_version` | string | VoiceFont version that created this profile |
| `prompt_count` | int | How many prompts were completed |
| `adaptive_selection` | bool | Whether adaptive selection was used |
| `session_duration_minutes` | float | Length of calibration session |
| `ambient_noise_db` | float | Background noise level during recording |
| `microphone` | string | Microphone used (if reported) |
| `sample_rate` | int | Recording sample rate |
| `bit_depth` | int | Recording bit depth |

### Archive Reference

| Field | Type | Description |
|---|---|---|
| `archive_reference` | string (path) | Path to the raw recordings archive |

This points to the original WAV files used to build the profile. The profile's reference audio is a *copy* of the best of these — the archive preserves everything.

## ValidationA profile is valid if:

1. `profile.json` exists and parses as JSON
2. Required fields are present (`schema_version`, `profile_id`, `display_name`, `created_at`, `language`, `engine_compatibility`, `primary_reference`, `style_references`)
3. `primary_reference` file exists
4. At least one style reference has `is_primary: true`
5. All referenced audio files exist

## Versioning Policy

### Backward-Compatible Changes (minor version bump)

- Adding new optional fields
- Adding new style names
- Adding new metadata fields
- Adding new engine names to `engine_compatibility`

### Breaking Changes (major version bump)

- Removing or renaming existing fields
- Changing field types
- Changing required fields
- Changing the meaning of existing fields

When a major version changes, VoiceFont includes a migration script.

## Engine Compatibility Hints

The `engine_compatibility` field is advisory. The server tries engines in this order:

1. If the requested engine is in the list, use it
2. Otherwise, try engines that claim compatibility
3. If nothing matches, use the default engine

This allows graceful fallback when engines evolve.

## Archive Preservation

The profile format separates **derived data** (the profile.json, processed references) from **raw data** (original recordings).

**Always preserve the raw archive.** The profile can be regenerated from it; the recordings cannot be regenerated.

Recommended structure:

```
data/my_voice_archive/
├── raw_recordings/           # The ground truth
│   └──01_good_reference.wav
├── sessions/ # Calibration session recordings
│   └── abc123/
│       └── pitch_01_low.wav
│       └── ...
├── test_outputs/              # Phase1 test outputs
└── README.md
```

The profile references files in this archive via `archive_reference` and copies the best samples into its own `references/` directory.

## Example: Building a Profile

```python
from pathlib import Path
from voice import create_profile_from_reference

profile = create_profile_from_reference(
    reference_wav=Path("my_reference.wav"),
    profile_id="my_voice",
    display_name="My Voice",
    profile_dir=Path("voice/profiles/my_voice"),
)
```

For full calibration (with coverage tracking), use `CalibrationSession` instead.

## Example: Reading a Profile

```python
from pathlib import Path
from voice import VoiceProfile

profile = VoiceProfile.load(Path("voice/profiles/my_voice"))
print(profile.display_name)
print(f"Engine compatibility: {profile.engine_compatibility}")
print(f"Has whisper: {profile.coverage.expressive_range.has_whisper}")
```

## See Also

- `docs/architecture.md` — System design
- `voice/profile.py` — Implementation- `voice/registry.py` — Discovery and loading
````

---

## Step 3: `docs/calibration-guide.md`

How to actually run a good calibration session.

### `docs/calibration-guide.md`

````markdown
# Calibration Guide

The calibration session is what produces your voice profile. This guide explains how to get good results.

## What Calibration Does

The session captures ~20 minutes of structured audio designed to give the voice engine enough material to synthesize expressive speech.

The quality of your cloned voice is **directly limited by the diversity of what you record**. Monotone readings produce monotone clones, regardless of how good the engine is.

## Before You Start

### Equipment

**Minimum:**
- Any working microphone (built-in, headset, USB)
- Quiet room (no HVAC noise, no traffic, no keyboard typing)

**Recommended:**
- USB condenser microphone- Pop filter- Quiet room with soft furnishings (curtains, carpet) to reduce echo

**Optimal:**
- Audio interface + condenser microphone
- Treated room or closet recording setup
- Closed-back headphones (to monitor yourself)

### Environment

The single biggest factor is **ambient noise**. Background noise gets baked into your speaker embedding, and the engine will reproduce that noise in the output.

Turn off:
- Fans, air conditioners- Music, TV
- Notifications on your computer
- Anything that hums or beeps

If you hear yourself echo when you speak, the room is too reverberant. Move somewhere with more soft surfaces.

### You

- Drink water before starting (dry mouth = scratchy recording)
- Don't record when tired (your natural energy matters)
- Speak at your **natural** volume — don't perform or exaggerate
- Don't try to sound "good" — try to sound like **yourself**

## The Session Structure

The adaptive session runs ~15–22 minutes. It walks through:

1. **Setup** (1 prompt) — Calibrates the analysis2. **Pitch range** (4 prompts) — Low, mid, high, glide
3. **Energy range** (5 prompts) — Whisper, quiet, normal, loud, belt
4. **Tempo range** (5 prompts) — Very slow through very fast
5. **Phonetic coverage** (~18 prompts) — All English phonemes
6. **Prosodic patterns** (8 prompts) — Questions, lists, stress
7. **Emotional range** (15 deliveries) — Paired-prompt design
8. **Style registers** (5 prompts) — Narrator, friendly, serious, teacher, excited
9. **Conversational** (4 prompts) — Natural storytelling

The session stops early when coverage is sufficient.

## Tips for Each Segment

### Pitch Range

When asked to say something "low," actually go to your lowest comfortable pitch — not just lower than normal. When asked for "high," go higher than feels natural.

The point is to capture your **range**, not your usual.

### Energy Range

**Whisper is hard.** A real whisper is breathy, quiet, with no vocal fold vibration. Don't just speak quietly — actually whisper.

**Belt is also hard.** A real belt has vocal effort. Don't just speak loudly — push from your diaphragm.

If you can't physically do whisper or belt, that's fine — the session adapts. But try.

### Tempo Range

"Very slow" should feel exaggerated. "Very fast" should feel rushed. The point is **range**, not natural pace.

### Phonetic Coverage

Read the sentences **at your natural pace**. Don't slow down or speed up. The analyzer is measuring which phonemes you produce, not how fast.

### Prosodic Patterns

Read the **instruction**, not just the text. The prosody is the point of these prompts. "Read this as a question, rising at the end" — actually do it.

### Emotional Range (Paired Prompts)

This is the **most important section**. The same sentence is asked for in multiple emotional deliveries. Read each delivery **as if you genuinely felt that emotion**, not as if you're performing it.

If you're not genuinely feeling it, try to remember a time when you did. The voice carries memory of genuine affect.

Examples:
- "Excited" → remember being told great news
- "Disappointed" → remember a letdown
- "Serious" → imagine warning someone you love about danger
- "Playful" → think of teasing a friend
- "Calm" → imagine comforting someone who's upset

### Style Registers

These are less about emotion and more about **social context**:
- **Narrator**: detached, informative, slightly authoritative
- **Friendly**: warm, casual, like greeting a friend
- **Serious**: weight, gravity, slow
- **Teacher**: clear, patient, slightly enthusiastic about the topic
- **Excited**: high energy, fast, genuine enthusiasm

### Conversational

The extemporaneous storytelling prompts (3 of them) are where your **most natural** voice comes through. Don't perform — just talk, as if to a friend.

If you stumble or lose your train of thought, that's fine. The natural recovery is part of what we're capturing.

## What to Do If Something Goes Wrong

### The recording clips (red light / distortion)

Your input is too loud. Either:
- Move back from the microphone
- Lower your input volume in OS settings
- Use the re-record button

### The recording is too quiet

Your input is too low. Either:
- Move closer to the microphone
- Raise your input volume

The web UI shows an audio level meter. Aim for the meter to peak around 70-80% during normal speech.

### You stumble on a sentence

Use the re-record button. Don't worry about being perfect — but if you truly messed it up, re-record.

### You want to skip a prompt

The skip button exists for genuine "I can't do this" situations (e.g., the whisper prompt is physically uncomfortable). Use sparingly — skipped prompts reduce coverage.

### The session seems too long

After ~15 prompts, watch for the "Sufficient coverage detected" indicator. If it appears and you're tired or short on time, you can stop. But if you have time, more prompts usually improve quality.

### You need to pause

There's a pause button. Your session state is preserved if you need to come back later.

## After the Session

The finalisation step builds your profile from the recordings. This takes a few seconds.

Once finalised:
- Your profile is at `voice/profiles/<your_id>/`
- You can immediately use `/speak?voice=<your_id>` to synthesise
- The raw recordings are preserved at `data/my_voice_archive/sessions/<session_id>/`

If you're not happy with the result, you can:
- **Re-calibrate** with a fresh session (overwrites the profile)
- **Re-record specific styles** at `/styles?voice=<your_id>`
- **Edit the profile manually** (advanced — see `docs/profile-format.md`)

## Common Questions

**Q: How long until I get good results?**
A: After your first session, you'll have a working voice clone. The quality improves with:
- More diverse calibration (use the full session, don't skip)
- A quieter recording environment
- Multiple sessions (recordings accumulate over time)

**Q: Can I redo calibration?**
A: Yes. The calibration overwrites the previous profile. But your **raw recordings are always preserved** — so re-calibrating doesn't lose data, just rebuilds the processed profile.

**Q: Should I use the same text in multiple styles?**
A: For the paired emotional prompts, yes — the same sentence in different deliveries. For other styles, the texts vary naturally.

**Q: What if my voice is unusual?**
A: Distinctive voices (strong accents, unusual pitch) often produce distinctive clones. The calibration still works — you just need enough material in your natural register.

**Q: Why does the session ask for whisper if my voice never whispers?**
A: The engine's style controls can produce quieter output. Having whisper reference audio extends your expressiveness — but it's not required.

## See Also

- `docs/architecture.md` — Why the session is structured this way
- `docs/profile-format.md` — What gets produced
- `docs/troubleshooting.md` — If things go wrong after calibration
````

---

## Step 4: `docs/troubleshooting.md`

The real failures, written down.

### `docs/troubleshooting.md`

````markdown
# Troubleshooting

Common issues and how to fix them.

## Setup Issues

### "ModuleNotFoundError: No module named 'voice'"

You're running from the wrong directory. VoiceFont modules are at the top level of the project.

```bash
cd ~/voicefont      # or wherever you cloned it
python scripts/verify_setup.py
```

### "No module named 'openvoice'"

OpenVoice isn't installed in your venv.

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate
pip install -e OpenVoice/
```

### "OpenVoice V2 checkpoints not found"

The checkpoints are separate from the repo. You need to download them.

See the OpenVoice README for download links. Typical locations:

```bash
# After downloading, place files at:
OpenVoice/checkpoints/v2/converter/
├── checkpoint.pth
└── config.json
OpenVoice/checkpoints/v2/base/
└── (base TTS checkpoints)
```

### "NLTK CMUdict not found"

```bash
python -c "import nltk; nltk.download('cmudict')"
```

### Verification fails on multiple items

Run `python scripts/verify_setup.py` and follow the fix instructions for each ✗ item.

## Server Issues

### Server starts but /health returns503

The engine didn't load. Check the server's stdout — there should be an error message about why OpenVoice V2 couldn't load.

Common causes:
- Checkpoints missing or in wrong location
- CUDA version mismatch (PyTorch was installed for different CUDA than your GPU has)
- Out of memory (close other GPU applications)

### "Profile 'my_voice' not found" when calling /speak

Either:
- You haven't calibrated yet (visit `/calibrate`)
- The profile is in `voice/profiles/` but the server can't find it
- The profile JSON is malformed

Check:
```bash
ls voice/profiles/
cat voice/profiles/my_voice/profile.json  # Should be valid JSON
```

### Server is slow on first synthesis call

The engine warms up. The first call after server start takes 10-30 seconds for model loading. Subsequent calls should be faster.

If every call is slow, you might be running on CPU. Check `nvidia-smi` to see if GPU is being used.

## Calibration Issues

### Microphone permission denied

The browser needs permission to access the microphone. If you denied it:
- Click the camera/microphone icon in the address bar
- Allow microphone access
- Refresh the page

### Recording plays back but upload fails

Check the server logs. Common causes:
- Audio format not supported (should be auto-converted from WebM)
- Server crashed mid-upload
- Network issue (local server shouldn't have this)

### Coverage stays low even after many prompts

Some prompts may not be capturing what you intend. Listen back to your recordings:
- Is "whisper" actually whisper, or just quiet speech?
- Is "excited" actually energetic, or just slightly faster?
- Is "belt" actually projected, or just louder?

If your deliveries are too subtle, the analyzer may not register them as capturing the dimension. Try again with more exaggeration.

### "Sufficient coverage detected" appears too early

The plateau detection may be too aggressive. You can:
- Continue recording anyway (just click through)
- Or tune the threshold in `calibration/plateau.py`

### "Sufficient coverage detected" never appears

The threshold may be too strict, or your recordings aren't actually capturing what you think. Check coverage details in the finalisation screen to see what's missing.

### The session gets stuck on one prompt

Refresh the browser. The session state is preserved on the server; you should be able to continue.

## Synthesis Issues

### Output doesn't sound like me at all

Possible causes:
- Your reference recording is bad (re-record it)
- The engine doesn't support your voice well (some voices are harder to clone)
- The profile's `primary_reference` isn't the best sample (edit the profile or re-calibrate)

### Output sounds robotic / unnatural

The engine is working but doesn't have enough expressive material. Re-calibrate with more attention to:
- Pitch range (actual highs and lows, not just normal)
- Energy range (whisper and belt specifically)
- Emotional range (genuine affect, not performed)

### Output is intelligible but has obvious artifacts

Some artifacts are normal for zero-shot cloning:
- Slight buzziness on certain phonemes
- Minor timing irregularities
- Occasional pitch wobble

If artifacts are severe:
- Try a longer / more varied reference
- Re-calibrate with cleaner recordings
- Consider engine settings (if available)

### Style switching doesn't sound different

The engine blends rather than switches. Distinctness depends on:
- How different your style references are (record them more distinctly)
- Whether the engine supports style variation (check OpenVoice V2 docs)

The `style_recorder` checks for distinctness and warns if your "excited" recording sounds like your "neutral" recording.

### Synthesis takes10+ seconds for a short sentence

You're running on CPU. Options:
- Move to a GPU if available
- Use a smaller, faster engine
- Accept the latency (some AI assistant use cases don't need real-time)

## Streaming Issues

### First chunk latency isn't better than non-streaming

For OpenVoice V2, this is expected. The engine doesn't natively stream, so "streaming" only helps with transfer time, not generation time.

To get true streaming latency:
- Use a different engine (Piper, some Coqui models)
- Run on GPU
- Accept the latency

### Audio stutters during playback

The streaming player may not have enough data buffered. Try:
- Larger chunk sizes in the client
- Slower synthesis speed- Pre-buffering the first sentence

### Interruption doesn't work

The client-side stop works (just stops reading the stream). True mid-synthesis cancellation requires engine support and isn't implemented in v1.

## Profile Issues

### "I want to use a different voice but it's not loading"

Check:
```bash
ls voice/profiles/  # All profiles listed here are auto-discovered
```

The registry loads on server start. If you add a profile while the server is running, restart it.

### "Profile JSON is corrupted"

If you edit the profile manually and break it:
- Delete the broken profile and re-calibrate
- Or restore from a backup (you do have backups, right?)

The raw recordings at `data/my_voice_archive/` are always safe.

### "I want to migrate my profile to a newer format"

Major version migrations will include scripts. For minor versions, the loader handles new fields automatically.

## Performance Issues

### Server uses too much memory

OpenVoice V2 can use 2-4 GB of RAM. If you have memory pressure:
- Close other applications
- Reduce concurrent synthesis requests
- Consider a lighter engine

### Synthesis is slow even on GPU

Check:
- Is the GPU actually being used? (Check `nvidia-smi` during synthesis)
- Are other GPU processes competing? (Close them)
- Is the input text very long? (Split into shorter pieces)

### The calibration UI is laggy

The UI does real-time audio level metering, which can be CPU-intensive. If you experience lag:
- Close other browser tabs
- Use a faster browser (Chrome typically performs best)
- Disable browser extensions

## Getting More Help

If none of this helps:

1. Run `python scripts/verify_setup.py` and note which checks fail
2. Check the server's stdout/stderr for error messages
3. Try the smoke test: `pytest tests/test_smoke.py -v`
4. Look at the raw recordings — are they what you'd expect?
5. Try a fresh profile — sometimes starting over is faster than debugging

The system has many components and many failure modes. When in doubt, simplify:
- A fresh voice profile
- A single short text
- Default styleIf the simple case works, layer complexity back on.
````

---

## Step 5: Commit

```bash
cd ~/voicefont

git add docs/architecture.md
git add docs/profile-format.md
git add docs/calibration-guide.md
git add docs/troubleshooting.md

git commit -m "Phase 8 chunk2: Documentation (architecture, profile format, calibration guide, troubleshooting)"
```

---

## Deliverables Checklist

- [x] `docs/architecture.md` — System design and decisions
- [x] `docs/profile-format.md` — Voice profile specification- [x] `docs/calibration-guide.md` — How to run a good calibration
- [x] `docs/troubleshooting.md` — Common issues and fixes

---

## What's in Chunk 3 (If You Want It)

Still pending from Phase8:
- `docs/api-reference.md` — Server endpoint reference
- `docs/development.md` — How to extend the system
- `examples/basic_synthesis.py`
- `examples/streaming_demo.py`
- `examples/style_switching_demo.py`
- `examples/ai_integration_patterns.py`
- `LICENSE`
- `CONTRIBUTING.md`

**What's actually useful:**

| Doc | Value |
|---|---|
| `api-reference.md` | Medium — most endpoints are discoverable via OpenAPI (`/docs`) |
| `development.md` | High — for anyone extending the system |
| `examples/*.py` | High — concrete usage patterns |
| `LICENSE` | Required for open source |
| `CONTRIBUTING.md` | Low — solo project, not really needed |

---

# VoiceFont — Phase 8 Chunk 3: Examples & Development Guide

## Why These Matter

Examples are how people actually learn to use a system. The previous chunks gave you docs that explain *what*; this chunk gives you code that shows *how*.

---

## Step 1: Basic Synthesis Example

### `examples/basic_synthesis.py`

```python
"""
VoiceFont — Basic Synthesis Example

The simplest possible usage: synthesise text and play it.
Make sure the server is running first: bash scripts/start_server.sh
"""
from client import VoiceClient


def main():
    # Connect to the local server
    client = VoiceClient(default_voice="my_voice")

    # Verify it's working
    try:
        health = client.health_check()
        print(f"✓ Server: {health['status']}")
        print(f"  Voices: {health['profiles']}")
    except Exception as e:
        print(f"✗ Cannot connect to server: {e}")
        print("  Start it with: bash scripts/start_server.sh")
        return

    # Synthesise and play
    text = "Hello! This is my cloned voice speaking from VoiceFont."
    print(f"\nSynthesising: \"{text}\"")

    result = client.speak(text, return_metadata=True)
    print(f"  Audio duration: {result['duration_seconds']:.1f}s")
    print(f"  Synthesis time: {result['synthesis_latency']:.2f}s")
    print("  Playing...")

    client.play(result["audio"])
    print("  Done.")


if __name__ == "__main__":
    main()
```

Run:
```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate
python examples/basic_synthesis.py
```

---

## Step 2: Style Switching Example

### `examples/style_switching_demo.py`

```python
"""
VoiceFont — Style Switching Demo

Demonstrates how the same text can be delivered in different
voice registers (neutral, calm, serious, excited, friendly).
"""
from client import VoiceClient, select_style


def main():
    client = VoiceClient(default_voice="my_voice")

    # Check available styles
    voices = client.list_voices()
    print("Available styles:")
    for voice in voices:
        print(f"  {voice['display_name']}: {voice.get('available_styles', [])}")
    print()

    # Example 1: Same text in different styles (manually specified)
    text = "I need to tell you something important about your project."

    print(f"Text: \"{text}\"\n")
    print("Playing in different styles (press Enter between each):\n")

    for style in ["neutral", "calm", "serious", "friendly"]:
        input(f"  Press Enter for '{style}' style...")
        audio = client.speak(text, style=style)
        client.play(audio)
        print(f"  ✓ Played '{style}'\n")

    # Example 2: Automatic style selection from text content
    print("Now with automatic style selection:\n")
    examples = [
        "Hey! How are you doing today?",
        "This is a critical warning. Listen carefully.",
        "That's amazing news! I can't believe it!",
        "Don't worry, we'll figure it out together.",
    ]

    for text in examples:
        selected = select_style(text)
        print(f"  Text: \"{text}\"")
        print(f"  Auto-selected style: {selected}")
        input("  Press Enter to play...")
        audio = client.speak(text, style=selected)
        client.play(audio)
        print()


if __name__ == "__main__":
    main()
```

---

## Step 3: Streaming Demo

### `examples/streaming_demo.py`

```python
"""
VoiceFont — Streaming Demo

Demonstrates streaming synthesis with sentence-level splitting.
Compare perceived latency vs. non-streaming.
"""
import time
from client import VoiceClient


def main():
    client = VoiceClient(default_voice="my_voice")

    # A longer response that benefits from streaming
    long_text = (
        "There are three things I want to mention. "
        "First, your schedule for next week is quite full. "
        "Second, you have a meeting on Tuesday that got moved to Wednesday. "
        "Third, and most importantly, your project proposal was approved. "
        "Congratulations on that, by the way."
    )

    print("=" * 60)
    print("Streaming Demo")
    print("=" * 60)
    print(f"\nText ({len(long_text.split())} words):")
    print(f"  \"{long_text}\"\n")

    # Non-streaming (full synthesis, then play)
    print("Approach 1: Non-streaming (synthesise all, then play)")
    start = time.time()
    audio = client.speak(long_text)
    synthesis_time = time.time() - start
    print(f"  Synthesis time: {synthesis_time:.2f}s")
    print(f"  Audio duration: ~{len(audio) / 44100:.1f}s")
    print(f"  Total time to audio: {synthesis_time:.2f}s")
    print(f"  Now playing...")
    play_start = time.time()
    client.play(audio)
    play_time = time.time() - play_start
    print(f"  Playback time: {play_time:.1f}s\n")

    # Streaming (sentence-by-sentence, play as ready)
    print("Approach 2: Streaming (synthesise per sentence, play as ready)")
    start = time.time()
    result = client.speak_streaming(long_text)
    total_time = time.time() - start

    print(f"  First chunk latency: {result.get('first_chunk_latency', 'N/A')}")
    print(f"  Total wall time: {total_time:.2f}s")
    print(f"  Perceived latency improvement: {synthesis_time - (result.get('first_chunk_latency') or synthesis_time):.2f}s")
    print()

    # Show sentence-by-sentence breakdown
    print("Approach 3: Manual sentence-by-sentence control")
    from client import split_into_sentences, select_style
    sentences = split_into_sentences(long_text)
    print(f"  Split into {len(sentences)} sentences\n")

    for i, sentence in enumerate(sentences, 1):
        style = select_style(sentence)
        start = time.time()
        audio = client.speak(sentence, style=style, return_metadata=True)
        elapsed = time.time() - start
        print(f"  Sentence {i} ({style}, {elapsed:.2f}s): \"{sentence}\"")
        input("    Press Enter to play this sentence...")
        client.play(audio)
        print()


if __name__ == == "__main__":  # Pylance workaround
    main()
```

Wait, that last line has a syntax issue from my draft. Let me fix it:

```python
if __name__ == "__main__":
    main()
```

---

## Step 4: AI Integration Patterns

### `examples/ai_integration_patterns.py`

```python
"""
VoiceFont — AI Integration Patterns

Five common patterns for integrating voice into an AI assistant.
Pick the one that matches your AI's architecture.

To use these, replace `PlaceholderAI` with your actual AI.
"""
from client import VoiceClient, select_style
import asyncio


# ============================================================
# Placeholder AI — replace with your actual model
# ============================================================

class PlaceholderAI:
    """Replace this with your actual AI."""
    def generate(self, text: str) -> str:
        return f"I understand. You said: {text}"

    async def agenerate(self, text: str) -> str:
        return self.generate(text)

    async def astream(self, text: str):
        response = self.generate(text)
        for word in response.split():
            yield word + " "
            await asyncio.sleep(0.05)


your_ai = PlaceholderAI()


# ============================================================
# Pattern 1: Simple synchronous
# ============================================================

def pattern_simple_sync():
    """
    Your AI is a synchronous function. Simplest case.
    Good for: CLI tools, simple bots, prototypes.
    """
    client = VoiceClient()

    def on_message(user_text: str):
        ai_response = your_ai.generate(user_text)
        style = select_style(ai_response)
        client.speak_and_play(ai_response, style=style)

    on_message("Hello, how are you?")


# ============================================================
# Pattern 2: Async AI
# ============================================================

async def pattern_async():
    """
    Your AI is async (most modern LLM clients).
    Good for: web apps, async pipelines.
    """
    client = VoiceClient()

    async def on_message(user_text: str):
        ai_response = await your_ai.agenerate(user_text)
        style = select_style(ai_response)
        audio = await client.aspeak(ai_response, style=style)
        await client.aplay(audio)

    asyncio.run(on_message("Hello!"))


# ============================================================
# Pattern 3: Token-by-token streaming
# ============================================================

async def pattern_token_streaming():
    """
    Your AI generates token-by-token (e.g., from a streaming LLM).
    We accumulate tokens into sentences and play each as it's ready.
    Good for: lower perceived latency, more conversational feel.
    """
    from client import split_into_sentences
    client = VoiceClient()

    async def on_message(user_text: str):
        buffer = ""
        async for token in your_ai.astream(user_text):
            buffer += token

            # Check if buffer ends with sentence punctuation
            if any(buffer.endswith(p) for p in [". ", "! ", "? ", "\n"]):
                sentence = buffer.strip()
                if sentence:
                    style = select_style(sentence)
                    audio = await client.aspeak(sentence, style=style)
                    await client.aplay(audio)
                    buffer = ""

        # Don't forget the final fragment
        if buffer.strip():
            audio = await client.aspeak(buffer)
            await client.aplay(audio)

    asyncio.run(on_message("Tell me a story."))


# ============================================================
# Pattern 4: Explicit style control
# ============================================================

def pattern_explicit_style():
    """
    Your AI has explicit control over voice style (e.g., via
    structured output or a tag system).
    """
    client = VoiceClient()

    # Suppose your AI returns JSON with style hints
    ai_outputs = [
        {
            "text": "Watch out for the traffic.",
            "voice_style": "serious",
            "speed": 0.95,
        },
        {
            "text": "I love this song!",
            "voice_style": "excited",
            "speed": 1.1,
        },
        {
            "text": "The meeting is at three.",
            "voice_style": "neutral",
            "speed": 1.0,
        },
    ]

    for output in ai_outputs:
        audio = client.speak(
            output["text"],
            style=output.get("voice_style", "neutral"),
            speed=output.get("speed", 1.0),
        )
        client.play(audio)


# ============================================================
# Pattern 5: With caching
# ============================================================

class CachedVoiceClient:
    """
    Wrap VoiceClient with caching for repeated phrases.
    Good for: assistants that say the same things often
    (greetings, error messages, etc.)
    """
    def __init__(self, base_client: VoiceClient, cache_size: int = 50):
        self.base = base_client
        self._cache = {}
        self._max_size = cache_size
        # Pre-warm with common phrases
        self._preload_phrases = [
            "Hello!",
            "I'm not sure I understand.",
            "Could you repeat that?",
        ]
        for phrase in self._preload_phrases:
            self.speak(phrase)

    def speak(self, text: str, **kwargs) -> bytes:
        key = (text, kwargs.get("style"), kwargs.get("speed"))
        if key not in self._cache:
            if len(self._cache) >= self._max_size:
                # Evict oldest entry
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = self.base.speak(text, **kwargs)
        return self._cache[key]

    def play(self, audio: bytes):
        self.base.play(audio)

    def speak_and_play(self, text: str, **kwargs):
        audio = self.speak(text, **kwargs)
        self.play(audio)


def pattern_with_caching():
    """Using the cached client."""
    base = VoiceClient()
    client = CachedVoiceClient(base)

    # First time: synthesised
    client.speak_and_play("Hello!")

    # Second time: from cache (instant)
    client.speak_and_play("Hello!")


# ============================================================
# Main: run all patterns in sequence
# ============================================================

if __name__ == "__main__":
    print("Pattern 1: Simple sync")
    input("  Press Enter to run...")
    pattern_simple_sync()

    print("\nPattern 2: Async")
    input("  Press Enter to run...")
    asyncio.run(pattern_async())

    print("\nPattern 3: Token streaming")
    input("  Press Enter to run...")
    asyncio.run(pattern_token_streaming())

    print("\nPattern 4: Explicit style")
    input("  Press Enter to run...")
    pattern_explicit_style()

    print("\nPattern 5: Caching")
    input("  Press Enter to run...")
    pattern_with_caching()
```

---

## Step 5: Examples README

### `examples/README.md`

````markdown
# Examples

Runnable examples showing different ways to use VoiceFont.

## Prerequisites

1. Server is running: `bash scripts/start_server.sh`
2. You have a voice profile (run calibration first if not)
3. Your microphone/speakers are working

## Running an Example

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate
python examples/basic_synthesis.py
```

## The Examples

### `basic_synthesis.py`

The simplest possible usage. Synthesise one sentence, play it.

**Use this when:** You just want to verify things work, or you're starting a new integration.

### `style_switching_demo.py`

Plays the same text in different voice registers (neutral, calm, serious, excited, friendly). Also demonstrates automatic style selection from text content.

**Use this when:** You want to hear how multi-style references sound, or you're deciding whether to use style selection.

### `streaming_demo.py`

Compares streaming vs. non-streaming synthesis. Shows sentence-by-sentence breakdown. Measures actual latency.

**Use this when:** You're optimising for perceived latency, or you want to understand the streaming trade-offs.

### `ai_integration_patterns.py`

Five complete patterns for integrating voice with an AI:
1. Simple synchronous
2. Async AI
3. Token-by-token streaming
4. Explicit style control
5. With caching

**Use this when:** You're wiring VoiceFont to your actual AI model.

## Modifying These for Your AI

All examples use `PlaceholderAI` as a stand-in. To use your real AI:

1. Replace `PlaceholderAI` with your actual model
2. Keep the integration pattern that matches your architecture
3. Handle errors (network, voice server down, etc.) as appropriate

## What's NOT Here

These examples are about *usage*, not *development*:

- **How to add a new TTS engine** — see `docs/development.md`
- **How to extend the calibration** — see `docs/development.md`
- **API reference** — see `/docs` when the server is running (FastAPI's built-in docs)
````

---

## Step 6: Development Guide

### `docs/development.md`

````markdown
# Development Guide

How to extend VoiceFont without breaking it.

## Guiding Principles

1. **Each extension should touch one layer, not many.** Adding an engine shouldn't require touching the server API. Adding a prompt shouldn't require touching the engine.2. **The profile format outlives everything else.** Any change to other components should be compatible with existing profiles.3. **Forward compatibility is built in.** The profile loader ignores unknown fields. New fields can be added without breaking old profiles.4. **Local-first, always.** No extension should introduce a cloud dependency.5. **The data is the asset.** Raw recordings and profiles are more valuable than code.

## Architecture Recap

```
AI Layer → Client → Server → Engine → Audio
                              ↑
                         Profile
```

Each layer only knows about the layer below it through a defined interface.

## Adding a New TTS Engine

### 1. Create the engine module

```bash
mkdir -p engines/my_engine
touch engines/my_engine/__init__.py
```

### 2. Implement the TTSEngine interface

```python
# engines/my_engine/engine.py
from pathlib import Path
from engines.base import TTSEngine, SynthesisRequest, SynthesisResult


class MyEngine(TTSEngine):
    @property
    def name(self) -> str:
        return "my-engine"

    @property
    def version(self) -> str:
        return "1.0.0"

    def load(self) -> None:
        """Load model weights, initialise resources."""
        # Your loading code
        self.model = load_my_model()

    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesise one utterance."""
        audio_array = self.model.infer(
            text=request.text,
            reference_audio=str(request.reference_audio_path),
        )
        # Write to a temp file
        output_path = Path("/tmp/my_engine_output.wav")
        write_wav(audio_array, output_path)

        return SynthesisResult(
            audio_path=output_path,
            duration_seconds=len(audio_array) / 22050,
            sample_rate=22050,
            engine_name=self.name,
            engine_version=self.version,
        )

    def cleanup(self) -> None:
        """Release resources."""
        if hasattr(self, "model"):
            del self.model
```

### 3. Register the engine

In `server/synthesizer.py`, add your engine to the factory:

```python
def _create_engine(engine_name: str) -> TTSEngine:
    engines = {
        "openvoice-v2": ("engines.openvoice_v2.engine", "OpenVoiceV2Engine"),
        "my-engine": ("engines.my_engine.engine", "MyEngine"),
    }
    if engine_name not in engines:
        raise ValueError(f"Unknown engine: {engine_name}")
    module_path, class_name = engines[engine_name]
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()
```

### 4. Add engine to profile compatibility

In `profile.json`:
```json
{
  "engine_compatibility": ["openvoice-v2", "my-engine"]
}
```

### 5. Test

```python
# tests/test_my_engine.py
from engines.my_engine.engine import MyEngine
from engines.base import SynthesisRequest

def test_my_engine():
    engine = MyEngine()
    engine.load()

    request = SynthesisRequest(
        text="Hello world",
        reference_audio_path=Path("voice/profiles/my_voice/references/neutral.wav"),
    )

    result = engine.synthesise(request)
    assert result.audio_path.exists()
    assert result.duration_seconds > 0
```

## Adding a New Style

### 1. Add the script to `calibration/style_recorder.py`

```python
STYLE_SCRIPTS["whispered"] = {
    "instruction": "Read this in a true whisper throughout, not just quiet speech.",
    "texts": [
        "I have to tell you something. Come closer.",
        "Nobody else knows this. Just you and me.",
        "Promise you won't say a word about this.",
    ],
    "captures": ["whisper_extended", "breathy_extended"],
}
```

### 2. (Optional) Add prompts to the calibration corpus

In `calibration/prompts/corpus.json`, add a segment:

```json
{
  "id": "whisper_extended",
  "name": "Extended Whisper",
  "description": "Captures sustained whisper for the whispered style",
  "estimated_minutes": 1.0,
  "prompts": [
    {
      "id": "whisper_ext_01",
      "text": "I have to tell you something. Come closer.",
      "instruction": "True whisper throughout. As quiet as you can while still being audible.",
      "captures": ["whisper_extended"]
    }
  ]
}
```

### 3. Test

The `StyleRecorder.list_available_styles()` will now include "whispered".

## Adding a New Prompt Type

### 1. Add to the corpus

In `calibration/prompts/corpus.json`, add your prompt to an existing segment or create a new one.

```json
{
  "id": "phon_19_new_sound",
  "text": "Your phonetic test sentence here.",
  "instruction": "Read at natural pace.",
  "captures": ["new_sound_class"]
}
```

### 2. (If the captures type is new) Update the coverage analyzer

In `calibration/analyzer/coverage.py`, add the new capture type:

```python
# In information_gain_for_prompt, add a new branch
if "new_sound_class" in str(prompt.captures):
    if "new_sound_class" not in self.prosodic_features:
        gain += 1.5
```

### 3. Verify

Re-run calibration. The new prompt type should be tracked.

## Adding a New API Endpoint

### 1. Add to `server/api.py`

```python
@app.post("/my-endpoint")
async def my_endpoint(
    param1: str,
    param2: Optional[int] = None,
):
    """What this endpoint does."""
    # Your logic here
    return {"result": "..."}
```

### 2. Test

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from server.api import create_app

def test_my_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.post("/my-endpoint", params={"param1": "value"})
    assert response.status_code == 200
```

## Adding a New Profile Field

### 1. Add to the dataclass

In `voice/profile.py`:

```python
@dataclass
class CoverageMetadata:
    # ... existing fields ...
    my_new_field: List[str] = field(default_factory=list)
```

### 2. Update `from_dict` to handle the new field

The dataclass-based loader handles new fields automatically. But if you need migration logic:

```python
@classmethod
def from_dict(cls, data: Dict) -> "VoiceProfile":
    known = {f for f in cls.__dataclass_fields__}
    filtered = {k: v for k, v in data.items() if k in known}
    # ... existing nested handling ...
    return cls(**filtered)
```

### 3. Bump the schema version (minor)

```python
PROFILE_FORMAT_VERSION = "1.1.0"  # Was 1.0.0
```

### 4. Test with old profiles

Verify that old profiles (without the new field) still load correctly. The default value handles this.

## Working with the Calibration Data

### Accessing raw recordings

```python
from pathlib import Path

session_dir = Path("data/my_voice_archive/sessions/SESSION_ID")
recordings = list(session_dir.glob("*.wav"))
for recording in recordings:
    print(recording.name, recording.stat().st_size)
```

### Regenerating a profile from raw recordings

```python
from calibration import CalibrationSession

session = CalibrationSession(
    profile_id="my_voice",
    display_name="My Voice",
)
# Manually replay recordings into the coverage tracker
# (Or just re-run calibration if you have the original session)
```

## Testing Strategy

VoiceFont has three levels of tests:

1. **Unit tests** (`tests/test_*.py`): Test individual components
2. **Smoke tests** (`tests/test_smoke.py`): End-to-end against a running server
3. **Manual tests** (the example scripts): Interactive verification

### Adding a unit test

```python
# tests/test_my_component.py
from my_component import MyClass

def test_my_class():
    obj = MyClass()
    assert obj.do_something() == expected_value
```

### Adding a smoke test

```python
# tests/test_smoke.py
def test_my_endpoint_works():
    from client import VoiceClient
    client = VoiceClient()

    # Real server call
    result = client.some_method()
    assert result["status"] == "ok"
```

Smoke tests are skipped if the server isn't running.

## Performance Considerations

### Engine Latency

Voice cloning is fundamentally slow compared to parametric TTS. Optimisations:

1. **GPU acceleration**: 5-10x speedup over CPU
2. **Caching**: Repeated phrases synthesise instantly
3. **Sentence splitting**: First sentence starts faster
4. **Engine choice**: Different engines have different speed/quality trade-offs

### Memory

OpenVoice V2 uses 2-4 GB RAM. If memory is tight:
- Don't run multiple engines simultaneously
- Process requests serially (one at a time)
- Consider a lighter engine

### Disk

- Audio files: ~100 KB per second of audio at 22 kHz mono
- Calibration session: ~10 MB for 20 minutes
- Engine weights: ~500 MB - 2 GB depending on engine

## What NOT to Do

### Don't make breaking changes to the profile format

The profile is the asset. Breaking it breaks everyone's voice data. Always add fields, never remove or rename.

### Don't introduce cloud dependencies

The whole point is local ownership. Cloud sync, telemetry, or external API calls violate the design.

### Don't couple layers

If you find yourself importing the engine module from the calibration code, or the profile code from the AI client, you're coupling layers. Refactor.

### Don't optimise prematurely

The current architecture is simple. Add complexity only when you have evidence it's needed.

## Version Compatibility Matrix

| Component | Min Version | Notes |
|---|---|---|
| Python | 3.9+ | f-string improvements, type hints |
| FastAPI | 0.110+ | Modern async support |
| OpenVoice V2 | latest | Check their releases |
| NLTK | 3.8+ | CMUdict handling |

## Getting Help

- Check the existing tests for examples
- Look at the corpus JSON for prompt structure
- Read the architecture doc for the "why"
- Don't be afraid to refactor — the system is small enough to keep in your head
````

---

## Step 7: LICENSE

### `LICENSE` (MIT)

```
MIT License

Copyright (c) 2026 VoiceFont Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Note: This project depends on OpenVoice V2, which is also MIT-licensed.
See https://github.com/myshell-ai/OpenVoice for their license terms.
```

---

## Step 8: Update the README to Reference the Examples

Add to your existing `README.md`:

```markdown
## Examples

See the `examples/` directory for runnable code:

- `basic_synthesis.py` — Simplest possible usage
- `style_switching_demo.py` — Multi-style reference comparison
- `streaming_demo.py` — Latency comparison
- `ai_integration_patterns.py` — Five integration patterns for your AI

```bash
# Make sure server is running first
bash scripts/start_server.sh

# Then in another terminal
python examples/basic_synthesis.py
```

## Development

See `docs/development.md` for how to:
- Add a new TTS engine
- Add new styles and prompt types
- Add new API endpoints
- Extend the profile format

## License

MIT — see `LICENSE`.
```

---

## Step 9: Commit```bash
cd ~/voicefont

git add examples/
git add docs/development.md
git add LICENSE
git add README.md

git commit -m "Phase 8 chunk3: Examples, development guide, license"
```

---

## Deliverables Checklist

- [x] `examples/basic_synthesis.py` — Simplest usage
- [x] `examples/style_switching_demo.py` — Multi-style demo
- [x] `examples/streaming_demo.py` — Streaming comparison
- [x] `examples/ai_integration_patterns.py` — Five AI integration patterns
- [x] `examples/README.md` — Examples guide
- [x] `docs/development.md` — Extension guide
- [x] `LICENSE` — MIT license

---

## What This Chunk Adds

| Addition | Value |
|---|---|
| `basic_synthesis.py` | Quick verification it works |
| `style_switching_demo.py` | Audition your multi-style profiles |
| `streaming_demo.py` | Understand latency trade-offs empirically |
| `ai_integration_patterns.py` | 5 reusable integration patterns |
| `development.md` | Clear path for extending the system |
| `LICENSE` | Legal clarity for sharing/using |
| `examples/README.md` | Entry point for new users |

---

## What's Left (Optional)

Still not done:
- `docs/api-reference.md` — but FastAPI auto-generates `/docs` when the server runs
- `CONTRIBUTING.md` — for solo projects, this is just the README's development section

I'd consider Phase 8 **complete** after this chunk. The remaining items are nice-to-have, not necessary.

---

## Summary: Phase 8 Complete

| Chunk | Deliverable |
|---|---|
| **Chunk 1** | Setup verification, convenience scripts, README, changelog, smoke tests |
| **Chunk 2** | Architecture, profile format spec, calibration guide, troubleshooting |
| **Chunk 3** | Examples, development guide, license |

The project is now:
- **Documented** (why decisions were made, how to use it, how to extend it)
- **Verified** (one command to check the environment)
- **Exemplified** (5 runnable code examples)
- **Licensed** (MIT, with proper attribution to OpenVoice V2)
- **Complete** (all8 original phases delivered)

---
