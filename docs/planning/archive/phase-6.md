# VoiceFont — Phase 6: Multi-Style References

## What This Phase Teaches You

**The assumptions being tested:**

1. *Can we record and store multiple distinct style references per voice?*
2. *Can the engine actually switch between them — does it sound different?*
3. *Can style selection become reliable enough that the right register gets used automatically?*

By the end of this phase you'll have:
1. **Style-specific reference audio** for at least 3-5 distinct registers (neutral, calm, serious, excited, friendly)
2. The profile format extended to **multiple style references** with engine-config metadata
3. The server able to select **which reference to use** based on style hints
4. Empirical evidence of style separation — does it actually sound different?

---

## What This Phase Does NOT Build

- **Emotion transfer** (the engine's ability to add emotion on top of a neutral reference) — that's engine-specific and varies. We capture distinct references instead.
- **Style interpolation** (blending between styles) — that's research-level and engine-dependent.
- **Per-utterance style learning** — too complex for v1.

---

## Repository Changes

```
voicefont/
├── calibration/
│   ├── prompts/
│   │   └── corpus.json                # UPDATED: more style prompts
│   ├── web/
│   │   └── app.js                     # UPDATED: style recording flow
│   ├── session.py                     # UPDATED: style-aware│   └── style_recorder.py              # NEW: dedicated style recording
│
├── voice/
│   └── profile.py                     # UPDATED: multiple style references
│
├── engines/
│   └── openvoice_v2/
│       └── engine.py                  # UPDATED: style-aware synthesis
│
├── server/
│   ├── synthesizer.py                 # UPDATED: style reference selection
│   └── api.py                         # UPDATED: style-aware endpoints
│
├── client/
│   └── voice_client.py                # UPDATED: style documentation
│
└── tests/
    ├── test_style_recording.py        # NEW
    └── test_multi_style.py # NEW
```

---

## Step 1: Extend the Profile Format for Multiple Style References

### Update `voice/profile.py`

```python
# Add to voice/profile.py

@dataclass
class StyleReference:
    """One reference recording for a specific speaking style.
    Each style has its own reference audio. The engine uses the
    reference matching the requested style_hint.
    """
    name: str                          # "neutral", "calm", "serious", "excited", etc.
    audio_file: str                    # Path relative to profile root
    description: str = ""
    is_primary: bool = False # The default reference    coverage_metadata: Dict[str, Any] = field(default_factory=dict)
    # e.g., {"F0_mean_hz": 145.3, "F0_std_hz": 25.1, "speech_rate_wpm": 165}
    
    # Optional: which segments of the calibration produced this reference
    source_prompt_ids: List[str] = field(default_factory=list)


# Update VoiceProfile's style_references field type# (StyleReference already exists in the dataclass, just enhanced)

# Add a helper to the module:
def add_style_reference(
    profile_dir: Path,
    style_name: str,
    source_audio: Path,
    description: str = "",
    source_prompt_ids: List[str] = None,
) -> StyleReference:
    """
    Add a new style reference to an existing profile.
    
    Copies the audio into the profile bundle and updates profile.json.
    """
    profile_dir = Path(profile_dir)
    profile = VoiceProfile.load(profile_dir)
    
    refs_dir = profile_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    
    # Use a clean filename
    safe_name = "".join(c if c.isalnum() else "_" for c in style_name.lower())
    dest_path = refs_dir / f"{safe_name}.wav"
    
    import shutil
    shutil.copy2(source_audio, dest_path)
    
    # Create new style reference
    new_ref = StyleReference(
        name=style_name,
        audio_file=f"references/{safe_name}.wav",
        description=description,
        is_primary=(len(profile.style_references) == 0),
        source_prompt_ids=source_prompt_ids or [],
    )
    
    # Add to profile (replace if name exists)
    profile.style_references = [
        r for r in profile.style_references if r.name != style_name
    ]
    profile.style_references.append(new_ref)
    
    # If this is the first reference, set as primary
    if not profile.primary_reference:
        profile.primary_reference = new_ref.audio_file
    
    profile.save(profile_dir)
    return new_ref
```

---

## Step 2: Dedicated Style Recording

Sometimes you want to record a style reference *outside* the main calibration session — for example, recording more excited takes after calibration.

### `calibration/style_recorder.py`

```python
"""
Dedicated style recording: add or replace style references.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Any
import time
import shutilfrom voice import (
    VoiceProfile,
    StyleReference,
    add_style_reference,
)
from .prompts import PromptCorpus
from .analyzer import analyze_audio_file, extract_phonemes


# Pre-defined style scripts — designed to elicit specific registers
STYLE_SCRIPTS = {
    "neutral": {
        "instruction": "Read this in a calm, neutral, slightly detached manner. Like a news anchor with no strong emotion.",
        "texts": [
            "The station was quiet at this hour. A single light flickered in the window above, and somewhere in the distance, a train was pulling away.",
            "Reports indicate that the situation has stabilised. No further action is required at this time. We will provide updates as they become available.",
            "The meeting will be held on Tuesday at three o'clock in the afternoon. Please bring any relevant documentation you may have.",
        ],
 "captures": ["narrator_style", "calm_detached", "neutral_prosody"],
    },
    "calm": {
        "instruction": "Read this slowly and reassuringly. As if comforting someone who is upset.",
        "texts": [
            "It's going to be okay. Take a deep breath. We're going to figure this out together, one step at a time.",
            "Don't worry about it. Things have a way of working themselves out. Just give it some time.",
            "I'm here. Whatever happens, I'm here. You don't have to go through this alone.",
        ],
        "captures": ["calm_reassuring", "low_energy", "warm_quality"],
    },
    "serious": {
        "instruction": "Read this with weight and gravity. As if warning someone about something important.",
        "texts": [
            "Listen to me carefully. This is not a drill. You need to take this seriously, or there will be real consequences.",
            "Stop. Before you do anything else, I need you to think about what you're about to do. Really think about it.",
            "This is critical. What I'm about to tell you could change everything. Pay close attention.",
        ],
        "captures": ["serious_gravity", "low_pitch", "deliberate_tempo"],
    },
    "excited": {
        "instruction": "Read this with genuine excitement and energy. As if you just heard amazing news.",
        "texts": [
            "Are you serious?! That's incredible! I can't believe it actually worked!",
            "Wait, you got it?! You actually got it! Oh my goodness, that's amazing!",
            "This is the best news I've heard all day! You won't believe what just happened!",
        ],
        "captures": ["high_arousal_positive", "high_pitch", "fast_tempo"],
    },
    "friendly": {
        "instruction": "Read this warmly, as if greeting a friend you like. Genuine warmth, not performance.",
        "texts": [
            "Hey! Oh my goodness, hi! How are you doing? I haven't seen you in ages! Come here, give me a hug!",
            "Hi there! It's so good to see you. How have you been? Tell me everything!",
            "Welcome! I'm so glad you're here. Come in, sit down, let me get you something to drink.",
        ],
        "captures": ["warm_friendly", "high_arousal_positive", "conversational_warmth"],
    },
}


class StyleRecorder:
    """Records new style references and adds them to an existing profile."""
    
    def __init__(
        self,
        profile_id: str,
        profiles_dir: Path,
 ):
        self.profile_id = profile_id
        self.profiles_dir = Path(profiles_dir)
        self.profile_dir = self.profiles_dir / profile_id
        self.profile = VoiceProfile.load(self.profile_dir)
    
    def list_available_styles(self) -> List[str]:
        """Styles with pre-defined scripts."""
        return list(STYLE_SCRIPTS.keys())
    
    def get_script(self, style_name: str) -> Dict[str, Any]:
        """Get the recording script for a given style."""
        if style_name not in STYLE_SCRIPTS:
            raise KeyError(
                f"Unknown style: {style_name}. "
                f"Available: {self.list_available_styles()}"
            )
        return STYLE_SCRIPTS[style_name]
    
    def record_style(
        self,
        style_name: str,
        audio_bytes: bytes,
        which_text: int = 0,
 ) -> Dict[str, Any]:
        """
        Record a new style reference.
        Saves the audio, analyses it, adds it to the profile.
        """
        if style_name not in STYLE_SCRIPTS:
            raise ValueError(f"Unknown style: {style_name}")
        
        script = STYLE_SCRIPTS[style_name]
        text = script["texts"][which_text % len(script["texts"])]
        
        # Save audio to a staging location
        refs_dir = self.profile_dir / "references"
        refs_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in style_name.lower())
        dest_path = refs_dir / f"{safe_name}.wav"
        
        # Write and validate
        from .recorder import save_wav, validate_audio
        duration, sr = save_wav(audio_bytes, dest_path)
        quality = validate_audio(dest_path)
        
        # Analyse
        features = analyze_audio_file(dest_path)
        phonemes = extract_phonemes(text)
        
        # Check: is this recording actually different from existing references?
        similarity_warning = self._check_style_distinctness(style_name, dest_path)
        
        # Add to profile
        new_ref = add_style_reference(
            profile_dir=self.profile_dir,
            style_name=style_name,
            source_audio=dest_path,
            description=script["instruction"],
            source_prompt_ids=[], # Manually recorded
        )
        
        # Update coverage metadata
        if style_name not in self.profile.coverage.emotional_styles:
            self.profile.coverage.emotional_styles.append(style_name)
        
        # Update with analysis features
        new_ref.coverage_metadata = {
            "F0_mean_hz": features.get("F0_mean"),
            "F0_min_hz": features.get("F0_min"),
            "F0_max_hz": features.get("F0_max"),
            "speech_rate_wpm": self._estimate_rate_from_features(text, duration),
            "rms": features.get("rms"),
            "recording_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        
        # Reload profile to get latest state, then save
        self.profile = VoiceProfile.load(self.profile_dir)
        for ref in self.profile.style_references:
            if ref.name == style_name:
                ref.coverage_metadata = new_ref.coverage_metadata
                break
        self.profile.save(self.profile_dir)
        
        return {
            "style": style_name,
            "audio_path": str(dest_path),
            "duration": duration,
            "sample_rate": sr,
            "quality": quality,
            "features": new_ref.coverage_metadata,
            "similarity_warning": similarity_warning,
            "text_used": text,
        }
    
    def _estimate_rate_from_features(self, text: str, duration: float) -> float:
        """Estimate speech rate."""
        if duration <= 0:
            return 0.0
        return (len(text.split()) / duration) * 60
    
    def _check_style_distinctness(
        self,
        style_name: str,
        new_audio_path: Path,
 ) -> Optional[Dict[str, Any]]:
        """
        Check if the new recording is actually different from existing references.
        
        If too similar, it may not provide useful style variation.
        """
        existing = [
            r for r in self.profile.style_references
            if r.name != style_name
 ]
        
        if not existing:
            return None  # First reference, nothing to compare against
        
        # Load new audio
        import librosa
        import numpy as np
        y_new, sr_new = librosa.load(new_audio_path, sr=22050, mono=True)
        
        warnings = []
        for ref in existing:
            ref_path = self.profile_dir / ref.audio_file
            if not ref_path.exists():
                continue
            
            y_ref, _ = librosa.load(ref_path, sr=22050, mono=True)
            
            # Compare F0 distributions
            f0_new, _, _ = librosa.pyin(
                y_new, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C5")
            )
            f0_ref, _, _ = librosa.pyin(
                y_ref, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C5")
            )
            
            f0_new_clean = [f for f, v in zip(f0_new, [True]*len(f0_new)) if not np.isnan(f)]
            f0_ref_clean = [f for f, v in zip(f0_ref, [True]*len(f0_ref)) if not np.isnan(f)]
            
            if f0_new_clean and f0_ref_clean:
                mean_diff = abs(np.mean(f0_new_clean) - np.mean(f0_ref_clean))
                if mean_diff < 10:  # Less than 10 Hz difference
                    warnings.append({
                        "compared_with": ref.name,
                        "F0_mean_diff_hz": round(float(mean_diff), 1),
                        "warning": "Very similar pitch to existing reference",
 })
        
        if warnings:
            return {
                "is_distinct": False,
                "comparisons": warnings,
                "recommendation": "Re-record with more expressive variation",
 }
        return {"is_distinct": True, "comparisons": []}
    
    def get_current_styles(self) -> List[Dict[str, Any]]:
        """List currently-captured styles for this profile."""
        result = []
        for ref in self.profile.style_references:
            ref_path = self.profile_dir / ref.audio_file
            result.append({
                "name": ref.name,
                "description": ref.description,
                "is_primary": ref.is_primary,
                "audio_exists": ref_path.exists(),
                "coverage_metadata": ref.coverage_metadata,
            })
        return result
```

### Update `calibration/__init__.py`:

```python
from .session import CalibrationSession
from .prompts import PromptCorpus
from .adaptive import AdaptiveController
from .plateau import evaluate_session_state, PlateauConfig
from .style_recorder import StyleRecorder, STYLE_SCRIPTS

__all__ = [
    "CalibrationSession",
    "PromptCorpus",
    "AdaptiveController",
    "evaluate_session_state",
    "PlateauConfig",
    "StyleRecorder",
    "STYLE_SCRIPTS",
]
```

---

## Step 3: Update Calibration to Capture Style References

### Update `calibration/session.py`

During finalisation, extract style-specific recordings from the calibration data:

```python
# Add to CalibrationSession class:

def finalise(self) -> Dict[str, Any]:
    """Build the final voice profile from collected recordings."""
    if not self.state.coverage.report.total_recording_seconds:
        raise ValueError("No recordings to finalise")
    
    report = self.state.coverage.report
    
    # ... existing code through building coverage metadata ...
    
    # NEW: Extract style-specific references from calibration recordings
    style_references = self._extract_style_references()
    
    # Update profile with multiple style references
    profile.style_references = style_references
    
    # ... rest of existing code ...
def _extract_style_references(self) -> List[StyleReference]:
    """
    Extract the best recording for each style from calibration data.
    
    Strategy:
    - For each style, find all recordings where the prompt was for that style
    - Pick the best (longest, cleanest) one as the reference
    """
    from .style_recorder import STYLE_SCRIPTS    from .recorder import validate_audio
    
    style_refs = []
    
    # Mapping: prompt level (or text content) → style name
    style_mappings = {
        # From style_registers segment
        "narrator": "neutral",
        "teacher": "neutral",
        "friendly": "friendly",
        "serious": "serious",
        "excited": "excited",
        # From emotional paired prompts
        "grateful": "calm",
        "concerned": "calm",
        "serious": "serious",
    }
    
    for style_name in STYLE_SCRIPTS.keys():
        # Find recordings that match this style
        candidates = []
 for prompt_id in self.state.completed_prompt_ids:
            prompt = self.corpus.prompt_by_id(prompt_id)
            if prompt.level and style_mappings.get(prompt.level) == style_name:
                audio_path = self.recordings_dir / f"{prompt_id}.wav"
                if audio_path.exists():
                    quality = validate_audio(audio_path)
                    candidates.append((audio_path, quality, prompt_id))
        
        if not candidates:
            continue
        
        # Pick the best: longest, cleanest recording
        candidates.sort(
            key=lambda x: (x[1].get("rms", 0), x[1].get("duration_seconds", 0)),
            reverse=True,
        )
        best_audio, best_quality, best_prompt_id = candidates[0]
        
        # Copy to profile references
        refs_dir = Path(f"voice/profiles/{self.state.profile_id}/references")
        refs_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in style_name.lower())
        dest = refs_dir / f"{safe_name}.wav"
        import shutil
        shutil.copy2(best_audio, dest)
        
        style_refs.append(StyleReference(
            name=style_name,
            audio_file=f"references/{safe_name}.wav",
            description=STYLE_SCRIPTS[style_name]["instruction"],
            is_primary=(style_name == "neutral"), # neutral is the default
            source_prompt_ids=[best_prompt_id],
        ))
    
    # If no styles captured, fall back to a single "neutral" reference
    if not style_refs:
        recordings = sorted(
            self.recordings_dir.glob("*.wav"),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if recordings:
            refs_dir = Path(f"voice/profiles/{self.state.profile_id}/references")
            refs_dir.mkdir(parents=True, exist_ok=True)
            dest = refs_dir / "neutral.wav"
            import shutil
 shutil.copy2(recordings[0], dest)
            style_refs.append(StyleReference(
                name="neutral",
                audio_file="references/neutral.wav",
                description="Primary reference (no style-specific captures)",
                is_primary=True,
                source_prompt_ids=[],
            ))
    
    return style_refs
```

---

## Step 4: Style-Aware Synthesis

### Update `engines/openvoice_v2/engine.py`

Make the engine pick the right reference based on style:

```python
# Update synthesis in engine.py:

def synthesise(self, request: SynthesisRequest) -> SynthesisResult:
    """Synthesise using the appropriate reference for the requested style."""
    # The request.reference_audio_path is the *primary* reference
    # If style_hint is provided and differs from primary, look up style-specific reference
    
    reference_to_use = request.reference_audio_path
    
    # Check if a style-specific reference exists
    if request.style_hint and request.style_hint != "neutral":
        # Look for a style-specific reference adjacent to the primary
        parent = request.reference_audio_path.parent
        style_specific = parent / f"{request.style_hint}.wav"
        if style_specific.exists():
            reference_to_use = style_specific
    
    # ... rest of synthesis using reference_to_use ...
```

---

## Step 5: Update the Server to Handle Style References

### Update `server/synthesizer.py`

```python
# Update Synthesizer.synthesise in server/synthesizer.py:

def synthesise(
    self,
    text: str,
    profile_id: str,
    style_hint: Optional[str] = None,
    speed: float = 1.0,
) -> SynthesisResult:
    """Synthesise using the appropriate style reference."""
    profile = self.registry.get(profile_id)
    if not profile:
        raise ValueError(f"Profile not found: {profile_id}")
    
    profile_path = self.registry.get_path(profile_id)
    
    # Select reference audio based on style
    reference_audio = self._select_reference(profile, profile_path, style_hint)
    
    request = SynthesisRequest(
        text=text,
        reference_audio_path=reference_audio,
        language=profile.language,
        style_hint=style_hint,
        speed=speed,
    )
    
    return self.engine.synthesise(request)

def _select_reference(
    self,
    profile: VoiceProfile,
    profile_path: Path,
    style_hint: Optional[str],
) -> Path:
    """Pick the best reference audio for the requested style."""
    
    # If specific style requested, look for it
    if style_hint:
        for ref in profile.style_references:
            if ref.name == style_hint:
                ref_path = profile_path / ref.audio_file
                if ref_path.exists():
                    return ref_path
    
    # Fall back to primary
    primary_path = profile_path / profile.primary_reference
    if primary_path.exists():
        return primary_path
    
    # Last resort: any reference
    if profile.style_references:
        return profile_path / profile.style_references[0].audio_file
    
    raise ValueError(f"No reference audio found in profile {profile.profile_id}")
```

### Update the `/voices` endpoint to expose available styles:

```python
# Update in server/api.py:

@app.get("/voices")
async def list_voices():
    """List voices with their available styles."""
    voices = []
    for pid in registry.list_ids():
        profile = registry.get(pid)
        profile_path = registry.get_path(pid)
        
        styles = []
        for ref in profile.style_references:
            styles.append({
                "name": ref.name,
                "description": ref.description,
                "is_primary": ref.is_primary,
                "available": (profile_path / ref.audio_file).exists(),
            })
        
        voices.append({
            "id": pid,
            "display_name": profile.display_name,
            "language": profile.language,
            "available_styles": [s["name"] for s in styles if s["available"]],
            "styles_detail": styles,
        })
    return {"voices": voices}
```

---

## Step 6: Style Recording API Endpoint

### Add to `server/api.py`:

```python
@app.post("/voices/{profile_id}/styles/record")
async def record_style(
    profile_id: str,
    style_name: str,
    audio: UploadFile = File(...),
    which_text: int = 0,
):
    """Record a new style reference for an existing voice."""
    from calibration import StyleRecorder
    
    if profile_id not in registry.list_ids():
        raise HTTPException(404, f"Voice '{profile_id}' not found")
    
    recorder = StyleRecorder(
        profile_id=profile_id,
        profiles_dir=Path(settings.profiles_dir),
    )
    
    audio_bytes = await audio.read()
    try:
        result = recorder.record_style(
            style_name=style_name,
            audio_bytes=audio_bytes,
            which_text=which_text,
        )
        
        # Reload registry to pick up changes
        registry.reload(profile_id)
        
        return result
    except Exception as e:
        raise HTTPException(500, f"Style recording failed: {str(e)}")


@app.get("/voices/{profile_id}/styles/available")
async def get_available_styles(profile_id: str):
    """List style scripts that can be recorded."""
    from calibration import StyleRecorder
    
    if profile_id not in registry.list_ids():
        raise HTTPException(404, f"Voice '{profile_id}' not found")
    
    recorder = StyleRecorder(
        profile_id=profile_id,
        profiles_dir=Path(settings.profiles_dir),
    )
    
    scripts = {}
    for style_name in recorder.list_available_styles():
        scripts[style_name] = recorder.get_script(style_name)
    
    current = recorder.get_current_styles()
    
    return {
        "available_to_record": scripts,
        "currently_captured": current,
    }
```

---

## Step 7: Style Recording Web UI (Optional)

Add a simple page to record styles post-calibration:

### `calibration/web/styles.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>VoiceFont — Record Styles</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="screen">
        <h1>Record Voice Styles</h1>
        <p>Capture distinct voice styles to enable expressive switching.</p>
        
        <div id="current-styles"></div>
        
        <h2>Add a New Style</h2>
        <select id="style-select"></select>
        <div id="style-script" class="prompt-box"></div>
 <button id="record-btn" class="record-btn">Record</button>
        <button id="upload-btn" class="primary-btn">Upload Recording</button>
        <input type="file" id="audio-file" accept="audio/wav,audio/webm" hidden>
        
        <div id="result"></div>
    </div>
    <script>
        const profileId = new URLSearchParams(window.location.search).get('voice') || 'my_voice';
        
        async function loadStyles() {
            const res = await fetch(`/voices/${profileId}/styles/available`);
            const data = await res.json();
            
            // Show current styles
            const currentDiv = document.getElementById('current-styles');
            currentDiv.innerHTML = '<h3>Currently Captured</h3>';
            data.currently_captured.forEach(s => {
                currentDiv.innerHTML += `
                    <div class="style-item">
                        <strong>${s.name}</strong>
                        ${s.is_primary ? '(primary)' : ''}
                        <p>${s.description}</p>
                    </div>
                `;
            });
            
            // Populate selector
            const select = document.getElementById('style-select');
            select.innerHTML = '';
            Object.keys(data.available_to_record).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
            });
            
            updateScript();
        }
        
        function updateScript() {
            const styleName = document.getElementById('style-select').value;
            fetch(`/voices/${profileId}/styles/available`)
                .then(r => r.json())
                .then(data => {
                    const script = data.available_to_record[styleName];
                    document.getElementById('style-script').innerHTML = `
                        <p><strong>Instruction:</strong> ${script.instruction}</p>
                        <p><strong>Text:</strong> "${script.texts[0]}"</p>
                    `;
                });
        }
        
        document.getElementById('style-select').addEventListener('change', updateScript);
        
        document.getElementById('upload-btn').addEventListener('click', async () => {
            const file = document.getElementById('audio-file').files[0];
            if (!file) {
                alert('Please select an audio file');
                return;
            }
            
            const styleName = document.getElementById('style-select').value;
            const formData = new FormData();
            formData.append('audio', file);
            
            const res = await fetch(`/voices/${profileId}/styles/record?style_name=${styleName}`, {
                method: 'POST',
                body: formData,
            });
            
            if (!res.ok) {
                alert('Upload failed');
                return;
            }
            
            const result = await res.json();
            document.getElementById('result').innerHTML = `
                <p>✓ Recorded style: ${result.style}</p>
               <p>Duration: ${result.duration.toFixed(1)}s</p>
                ${result.similarity_warning && !result.similarity_warning.is_distinct ?
 `<p class="warning">⚠ ${result.similarity_warning.recommendation}</p>` : ''}
            `;
            
            loadStyles();  // Refresh });
        
        loadStyles();
    </script>
</body>
</html>
```

### Add to `server/api.py`:

```python
@app.get("/styles")
async def styles_ui():
    """Serve the style recording UI."""
    web_dir = Path(__file__).parent.parent / "calibration" / "web"
    return FileResponse(web_dir / "styles.html")
```

---

## Step 8: Tests

### `tests/test_style_recording.py`

```python
import pytest
from pathlib import Path
import tempfile
import numpy as np
import soundfile as sf

from calibration import StyleRecorder, STYLE_SCRIPTS
from voice import create_profile_from_reference, add_style_reference


def _make_wav_bytes(duration=3.0, sr=22050):
    t = np.linspace(0, duration, int(sr * duration))
    # Different waveforms to simulate different styles
    audio = 0.3 * np.sin(2 * np.pi * 440 * t)
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio, sr)
        path = Path(f.name)
    return path.read_bytes()


def test_style_recorder_lists_styles():
    with tempfile.TemporaryDirectory() as tmp:
        profiles_dir = Path(tmp) / "profiles"
        recordings = Path(tmp) / "ref.wav"
        t = np.linspace(0, 2, 22050 * 2)
        sf.write(recordings, 0.3 * np.sin(2 * np.pi * 440 * t), 22050)
        
        profile_dir = profiles_dir / "my_voice"
        create_profile_from_reference(recordings, "my_voice", "Test", profile_dir)
        
        recorder = StyleRecorder("my_voice", profiles_dir)
        styles = recorder.list_available_styles()
        
        assert "neutral" in styles
        assert "serious" in styles
        assert "excited" in styles        assert "calm" in styles
        assert "friendly" in styles


def test_record_style_adds_reference():
    with tempfile.TemporaryDirectory() as tmp:
        profiles_dir = Path(tmp) / "profiles"
        recordings = Path(tmp) / "ref.wav"
        t = np.linspace(0, 2, 22050 * 2)
        sf.write(recordings, 0.3 * np.sin(2 * np.pi * 440 * t), 22050)
        
        profile_dir = profiles_dir / "my_voice"
        create_profile_from_reference(recordings, "my_voice", "Test", profile_dir)
        
        recorder = StyleRecorder("my_voice", profiles_dir)
        audio_bytes = _make_wav_bytes()
        
        result = recorder.record_style("serious", audio_bytes)
        
        assert result["style"] == "serious"
        assert Path(result["audio_path"]).exists()


def test_style_scripts_have_three_texts_each():
    """Each style has multiple text options for variety."""
    for style, script in STYLE_SCRIPTS.items():
        assert len(script["texts"]) >= 2, f"{style} has only {len(script['texts'])} texts"
```

### `tests/test_multi_style.py`

```python
import pytest
from pathlib import Path
import tempfile

from voice import VoiceProfile
from server.synthesizer import Synthesizer


def test_synthesizer_selects_style_reference():
    """When style_hint is given, the right reference is selected."""
    with tempfile.TemporaryDirectory() as tmp:
        profiles_dir = Path(tmp) / "profiles"
        profile_dir = profiles_dir / "my_voice"
        
        # Create profile with two references
        from voice import create_profile_from_reference, add_style_reference
        import numpy as np
        import soundfile as sf
        
        # Neutral ref
        ref_path = Path(tmp) / "neutral_ref.wav"
        t = np.linspace(0, 2, 22050 * 2)
        sf.write(ref_path, 0.3 * np.sin(2 * np.pi * 440 * t), 22050)
        create_profile_from_reference(ref_path, "my_voice", "Test", profile_dir)
        
        # Add a "serious" ref
        serious_path = Path(tmp) / "serious.wav"
        sf.write(serious_path, 0.3 * np.sin(2 * np.pi * 220 * t), 22050)  # Lower freq        add_style_reference(
            profile_dir=profile_dir,
            style_name="serious",
            source_audio=serious_path,
            description="Serious style",
        )
        
        # Verify both references exist
        profile = VoiceProfile.load(profile_dir)
        style_names = [r.name for r in profile.style_references]
        assert "neutral" in style_names
        assert "serious" in style_names
        
        # Test that synthesizer picks the right one
        synth = Synthesizer(profiles_dir=profiles_dir, engine_name="openvoice-v2")
        selected = synth._select_reference(profile, profile_dir, "serious")
        
        assert "serious" in str(selected)
```

---

## Step 9: Run End-to-End with Styles

### Test Style Switching

Update the demo to test style switching:

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate

# Start the server
python -m server.api
```

Visit `http://localhost:8000/styles?voice=my_voice` and record a few styles.

Then in another terminal:

```bash
python -c "
from client import VoiceClient

c = VoiceClient()

# Same text, different styles
text = 'I need to tell you something important.'

for style in ['neutral', 'calm', 'serious', 'excited', 'friendly']:
    print(f'=== {style} ===')
    audio = c.speak(text, style=style)
    c.play(audio)
"
```

You should hear the same sentence delivered with audible stylistic differences.

### Measure Style Distinctness

Compare synthesised outputs:

```bash
python -c "
from client import VoiceClient
import hashlib

c = VoiceClient()

text = 'This is a test of style switching.'

for style in ['neutral', 'calm', 'serious']:
    audio = c.speak(text, style=style, return_metadata=True)
    h = hashlib.md5(audio['audio']).hexdigest()[:8]
    size = len(audio['audio'])
    print(f'{style:10s}: hash={h} size={size}')
"
```

If the hashes are different, you have distinct synthesis paths. Listen to confirm they actually sound different.

---

## Step 10: Documentation

### Update README with style usage:

```markdown
## Using Multiple Styles

VoiceFont can switch between different vocal registers:

```python
from client import VoiceClient

client = VoiceClient()

# Different registers for different contexts
client.speak("Hello there!", style="friendly")        # Warm greeting
client.speak("Stop. Listen carefully.", style="serious")  # Warning
client.speak("It's okay, we'll figure it out.", style="calm")  # Reassurance
client.speak("That's amazing news!", style="excited")   # Enthusiasm
```

Style selection is automatic if you use `select_style`:

```python
from client import select_style

text = "Watch out, this is important!"
style = select_style(text)  # Picks "serious" based on keywords
client.speak(text, style=style)
```

To add new styles to an existing voice, use the styles UI at `/styles`.
```

---

## Step 11: Commit```bash
cd ~/voicefont
git add calibration/style_recorder.py
git add voice/profile.py
git add engines/openvoice_v2/engine.py
git add server/synthesizer.py server/api.py
git add calibration/web/styles.html
git add tests/test_style_recording.py tests/test_multi_style.py

git commit -m "Phase 6: Multi-style references with style-aware synthesis"
```

---

## Deliverables Checklist

- [x] Extended profile format with style-specific coverage metadata
- [x] Dedicated style recorder with pre-defined scripts for 5 styles
- [x] Calibration finalisation extracts style-specific references automatically
- [x] Server picks the right reference based on style hint
- [x] Style recording API + web UI for post-calibration additions
- [x] Style distinctness checking (warns if recordings are too similar)
- [x] Tests for style recording and selection

---

## What This Phase Teaches You

**If successful:**
- You can hear audible differences between styles
- The same text sounds "neutral" vs. "serious" vs. "excited"
- Style selection works reliably for contextually appropriate registers
- You can add new styles after calibration without redoing everything

**Likely issues:**
- Style differences may be subtle, not dramatic → the engine's ability to interpret style-specific references varies
- Some recordings may not capture the intended style well → the distinctness check helps catch this
- "Excited" might sound forced or unnatural → use the actual emotional range from Phase 3 calibration- Engine style controls vs. style-specific references may conflict → OpenVoice V2 uses the reference's tone colour primarily

**If partially successful:**
- Style switching works but differences are subtle → tune reference recordings to be more distinctly different
- Some styles sound the same as neutral → remove that style or re-record with more variation

---