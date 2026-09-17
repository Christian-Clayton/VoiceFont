# VoiceFont — Phase 2: Voice Server & Profile Format

## What This Phase Teaches You

**The assumptions being tested:**

1. *Can we wrap OpenVoice V2 in a clean, engine-agnostic API that any AI can call locally?*
2. *Can the voice profile format be simple, versioned, and portable — even if we only have one engine today?*
3. *Can the same FastAPI server also serve static assets for the Phase 3 calibration web UI?*

By the end of this phase you'll have:
1. A working local HTTP API (`localhost:8000`) that takes text + voice profile → returns audio
2. A defined, versioned profile format with JSON schema + audio references
3. A working profile bundle saved from your Phase 1 good reference
4. A CLI client (for your AI to call programmatically)
5. Static asset serving infrastructure ready for Phase 3's web UI
6. An engine abstraction that could swap OpenVoice V2 for another TTS without changing the API

---

## Architectural Goals for This Phase

###1. Engine-Agnostic Profile Format

The profile must not assume OpenVoice V2 internally. Today OpenVoice V2 is the engine; tomorrow it might be XTTS, StyleTTS2, or something new. The profile describes **what should be true about the synthesis**, not **how OpenVoice V2 does it**.

### 2. Engine-Agnostic Server API

The `/speak` endpoint takes `(text, voice_profile_id, style_hint)` and returns audio. It must not expose OpenVoice-specific concepts to callers.

### 3. Multiple Voices per Server

The server should handle multiple voice profiles (e.g., `my_voice`, `my_voice_calm`), each backed by different reference audio. This is groundwork for Phase 6.

### 4. Static Asset Serving

Phase 3's web UI will be HTML/CSS/JS served by this same server. We add the static-file capability now (cheap) so Phase 3 doesn't need new infrastructure.

---

## Repository Layout for This Phase

```
voicefont/
├── data/
│   └── my_voice_archive/
│       └── (Phase 1 artifacts)
│
├── voice/ # NEW: profile system
│   ├── __init__.py
│   ├── profile.py                 # VoiceProfile dataclass + I/O
│   ├── registry.py                # Loads/saves profiles from disk
│   └── profiles/
│       └── my_voice/              # Your voice profile (created this phase)
│           ├── profile.json
│           ├── references/
│           │   └── neutral.wav
│           └── README.md
│
├── engines/                       # NEW: pluggable engine layer
│   ├── __init__.py
│   ├── base.py                    # TTSEngine abstract base class
│   └── openvoice_v2/
│       ├── __init__.py
│       ├── engine.py              # OpenVoiceV2Engine implementation
│       └── README.md
│
├── server/                        # NEW: FastAPI server
│   ├── __init__.py
│   ├── api.py # Endpoint definitions
│   ├── synthesizer.py             # Wraps engine + profile loading
│   ├── static.py                  # Static file serving (for Phase 3 UI)
│   └── config.py                  # Server configuration
│
├── client/                        # NEW: CLI/Python client
│   ├── __init__.py
│   └── voice_client.py            # Programmatic client for your AI
│
├── tests/                         # NEW: basic tests
│   ├── __init__.py
│   └── test_profile.py
│
├── pyproject.toml                 # NEW: project config
├── requirements.txt # NEW: dependencies
├── .gitignore
└── README.md
```

---

## Step 1: Project Setup

From `~/voicefont`:

```bash
# Create the new source tree
mkdir -p voice/profiles
mkdir -p engines/openvoice_v2
mkdir -p server
mkdir -p client
mkdir -p tests

# Create __init__.py files for Python packages
touch voice/__init__.pytouch engines/__init__.py
touch engines/openvoice_v2/__init__.py
touch server/__init__.py
touch client/__init__.py
touch tests/__init__.py
```

### `requirements.txt`

```txt
# Web framework
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9

# Audio handling
scipy>=1.11.0
soundfile>=0.12.0
numpy>=1.24.0

# VoiceFont's own OpenVoice install (path-based, not PyPI)
# (We'll install OpenVoice as a separate step)

# HTTP client (for the client module)
httpx>=0.27.0

# Testing
pytest>=8.0.0
```

### `pyproject.toml`

```toml
[project]
name = "voicefont"
version = "0.2.0"
description = "Self-hosted, engine-agnostic voice cloning system"
requires-python = ">=3.9"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["voicefont*"]
exclude = ["OpenVoice*", "tests*", "data*"]
```

### Install (in your venv)

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate    # reuse the venv from Phase 1

pip install -r requirements.txt
```

---

## Step 2: Define the Profile Format

This is the **real asset** — the thing that outlives any engine.

### `voice/profile.py`

```python
"""
VoiceFont voice profile format.

Engine-agnostic, versioned, portable. Describes a voice in terms of
what should be true about synthesis, not how any specific engine
achieves it.
"""
from __future__ import annotationsfrom dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optionalimport json
import time

PROFILE_FORMAT_VERSION = "1.0.0"


@dataclass
class SpeakerFeatures:
    """Extracted speaker characteristics. Optional but informative."""
    F0_mean_hz: Optional[float] = None
    F0_std_hz: Optional[float] = None
    F0_range_hz: Optional[List[float]] = None  # [min, max]
    speech_rate_wpm: Optional[float] = None
    voice_quality: Optional[str] = None  # "modal", "breathy", "creaky", etc.


@dataclass
class StyleReference:
    """One reference recording for a specific speaking style."""
    name: str                          # "neutral", "friendly", "serious", etc.
    audio_file: str                    # Path relative to profile root
    description: str = ""
    is_primary: bool = False # True for the default reference


@dataclass
class CoverageMetadata:
    """What was captured during calibration. Empty for Phase 2."""
    phoneme_coverage: Dict[str, int] = field(default_factory=dict)
    prosodic_features: List[str] = field(default_factory=list)
    emotional_styles: List[str] = field(default_factory=list)
    overall_coverage_pct: float = 0.0
    total_recording_seconds: float = 0.0
    calibration_session_date: Optional[str] = None


@dataclass
class CalibrationMetadata:
    """How this profile was produced. Empty/missing for hand-built profiles."""
    calibrator_version: Optional[str] = None
    prompt_count: int = 0
    adaptive_selection: bool = False
    session_duration_minutes: float = 0.0
    ambient_noise_db: Optional[float] = None
    microphone: Optional[str] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None


@dataclass
class VoiceProfile:
    """
    A VoiceFont voice profile.
    Engine-agnostic. Versioned. Portable. Human-inspectable JSON.
    """
    # Identity    schema_version: str = PROFILE_FORMAT_VERSION
    profile_id: str = "" # e.g., "my_voice"
    display_name: str = ""             # e.g., "My Voice"
    created_at: str = ""               # ISO8601 timestamp
    language: str = "en-GB"
    
    # Engine hints (which engines this profile is known to work with)
    engine_compatibility: List[str] = field(default_factory=list)
    # e.g., ["openvoice-v2"]
    
    # Primary reference (always present)
    primary_reference: str = ""        # Path relative to profile root
    
    # Additional style references (Phase 6 will populate these)
    style_references: List[StyleReference] = field(default_factory=list)
    
    # Extracted speaker features (optional)
    speaker_features: SpeakerFeatures = field(default_factory=SpeakerFeatures)
    
    # Calibration provenance (optional, populated by Phase 3+)
    coverage: CoverageMetadata = field(default_factory=CoverageMetadata)
    calibration: CalibrationMetadata = field(default_factory=CalibrationMetadata)
    
    # Link back to raw recordings (optional but valuable)
    archive_reference: Optional[str] = None  # Path to raw archive, may be elsewhere
    
    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict."""
        d = asdict(self)
        # Convert nested dataclasses (already done by asdict, but ensure clean)
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "VoiceProfile":
        """Load from serialized form. Tolerates unknown fields for forward compat."""
        # Extract known fields, ignore unknown
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        
        # Handle nested dataclasses
        if "speaker_features" in filtered and isinstance(filtered["speaker_features"], dict):
            filtered["speaker_features"] = SpeakerFeatures(**filtered["speaker_features"])
        if "coverage" in filtered and isinstance(filtered["coverage"], dict):
            filtered["coverage"] = CoverageMetadata(**filtered["coverage"])
        if "calibration" in filtered and isinstance(filtered["calibration"], dict):
            filtered["calibration"] = CalibrationMetadata(**filtered["calibration"])
        if "style_references" in filtered:
            filtered["style_references"] = [
                StyleReference(**sr) for sr in filtered["style_references"]
            ]
        
        return cls(**filtered)
    
    def save(self, profile_dir: Path):
        """Save profile.json to the given directory."""
        profile_dir = Path(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        
        with open(profile_dir / "profile.json", "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, profile_dir: Path) -> "VoiceProfile":
        """Load profile.json from the given directory."""
        profile_dir = Path(profile_dir)
        with open(profile_dir / "profile.json") as f:
            data = json.load(f)
        return cls.from_dict(data)


def create_profile_from_reference(
    reference_wav: Path,
    profile_id: str,
    display_name: str,
    profile_dir: Path,
    language: str = "en-GB",
) -> VoiceProfile:
    """
    Build a minimal profile from a single reference audio file.
    
    Used in Phase 2 before the calibration system exists. The resulting
    profile has no coverage metadata, but is valid and usable.
    """
    profile_dir = Path(profile_dir)
    refs_dir = profile_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy reference into profile
    import shutil
    primary_dest = refs_dir / "neutral.wav"
    shutil.copy2(reference_wav, primary_dest)
    
    profile = VoiceProfile(
        profile_id=profile_id,
        display_name=display_name,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        language=language,
        engine_compatibility=["openvoice-v2"],
        primary_reference="references/neutral.wav",
        style_references=[
            StyleReference(
                name="neutral",
                audio_file="references/neutral.wav",
                description="Primary neutral-style reference",
                is_primary=True,
            )
        ],
 archive_reference=str(reference_wav),
    )
    
    profile.save(profile_dir)
    return profile
```

### `voice/registry.py`

```python
"""
Voice profile registry. Discovers, loads, and indexes profiles on disk.
"""
from pathlib import Path
from typing import Dict, List, Optional
from .profile import VoiceProfile


class ProfileRegistry:
    """Manages a directory of voice profiles."""
    
    def __init__(self, profiles_dir: Path):
        self.profiles_dir = Path(profiles_dir)
        self._cache: Dict[str, VoiceProfile] = {}
 self._refresh()
    
    def _refresh(self):
        """Scan profiles directory and load all profiles."""
        self._cache.clear()
        if not self.profiles_dir.exists():
            return
        
        for profile_dir in self.profiles_dir.iterdir():
            if not profile_dir.is_dir():
                continue
            profile_json = profile_dir / "profile.json"
            if not profile_json.exists():
                continue
            try:
                profile = VoiceProfile.load(profile_dir)
                self._cache[profile.profile_id] = profile
            except Exception as e:
                print(f"Warning: failed to load profile at {profile_dir}: {e}")
    
    def list_ids(self) -> List[str]:
        return list(self._cache.keys())
    
    def get(self, profile_id: str) -> Optional[VoiceProfile]:
        return self._cache.get(profile_id)
    
    def get_path(self, profile_id: str) -> Optional[Path]:
        """Get the on-disk directory for a profile."""
        if profile_id not in self._cache:
            return None
        return self.profiles_dir / profile_id
    
    def reload(self, profile_id: str):
        """Force reload a specific profile from disk."""
        profile_dir = self.profiles_dir / profile_id
        if not (profile_dir / "profile.json").exists():
            raise FileNotFoundError(f"No profile at {profile_dir}")
        self._cache[profile_id] = VoiceProfile.load(profile_dir)
```

### `voice/__init__.py`

```python
from .profile import VoiceProfile, create_profile_from_reference
from .registry import ProfileRegistry

__all__ = ["VoiceProfile", "create_profile_from_reference", "ProfileRegistry"]
```

---

## Step 3: Define the Engine Abstraction

This is the abstraction that lets us swap engines later.

### `engines/base.py`

```python
"""
Abstract TTS engine interface.

All engines must implement this. The server talks to engines through
this interface only — never to engine-specific APIs directly.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SynthesisRequest:
    """What the engine needs to synthesise one utterance."""
    text: str
    reference_audio_path: Path     # Engine uses this for voice identity
    language: str = "en-GB"
    style_hint: Optional[str] = None    # "neutral", "happy", "serious", etc.
    speed: float = 1.0
    # Future: pitch, emotion intensity, etc.


@dataclass
class SynthesisResult:
    """What the engine produces."""
    audio_path: Path                # Where the WAV was written
    duration_seconds: float
    sample_rate: int
    engine_name: str                # For metadata/debugging
    engine_version: str = ""


class TTSEngine(ABC):
    """All TTS engines implement this interface."""
    
    @property    @abstractmethod
    def name(self) -> str:
        """Engine identifier, e.g., 'openvoice-v2'."""
        pass
    
    @property
    def version(self) -> str:
        """Optional version string."""
        return ""
    
    @abstractmethod
    def load(self) -> None:
        """Load model weights into memory. Called once at startup."""
        pass
    
    @abstractmethod
    def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesise one utterance. May be slow; consider caching."""
        pass
    
    def supports_style(self, style_name: str) -> bool:
        """Whether this engine has meaningful control over a given style."""
        return False  # Default: engines without explicit style control
    
    def cleanup(self) -> None:
        """Release resources. Called at shutdown."""
        pass
```

---

## Step 4: Implement the OpenVoice V2 Engine

This wraps OpenVoice's API behind our `TTSEngine` interface.

### `engines/openvoice_v2/engine.py`

```python
"""
OpenVoice V2 engine implementation.

This is the only file that knows OpenVoice-specific details. Everywhere
else in VoiceFont talks to the abstract TTSEngine interface.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import time
import numpy