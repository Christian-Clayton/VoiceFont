# VoiceFont — Phase 4: Adaptive Calibration

## What This Phase Teaches You

**The assumptions being tested:**

1. *Can we intelligently select the next prompt to maximise information gain, rather than walking through every prompt?*
2. *Can the session stop early when coverage is sufficient, saving time?*
3. *Can we detect and fill gaps (whisper missing, only2 emotions captured, etc.) dynamically?*

By the end of this phase you'll have:
1. An **adaptive prompt selector** using item-response-theory-inspired information gain
2. **Dynamic gap detection** that prioritises prompts covering missing dimensions
3. **Early-stop logic** that ends the session when coverage thresholds are met
4. **Shorter sessions** (15-20 min vs. 20-25 min fixed) with **equal or better coverage**

---

## What We're Building On

Phase 3 gives us:
- The fixed prompt corpus (`calibration/prompts/corpus.json`)
- `CoverageTracker` with dimension-aware completeness- `CalibrationSession` that walks through prompts in order
- The web UI

Phase 4 changes:
- The session state machine now uses an **adaptive controller** instead of linear progression
- Each `loadNextPrompt()` call asks "what's the most informative prompt right now?"
- The session can declare itself complete when coverage is sufficient
- The UI gets a "you can stop here" indicator

---

## Repository Changes

```
voicefont/
├── calibration/
│   ├── session.py # UPDATED: uses AdaptiveController
│   ├── adaptive.py                      # NEW: prompt selection logic
│   ├── plateau.py                       # NEW: early-stop detection
│   ├── analyzer/
│   │   ├── coverage.py                  # UPDATED: gain-from-prompt computation
│   ├── prompts/
│   ├── ...
│   ├── web/
│   │   ├── app.js # UPDATED: handles early-stop
│   │   └── index.html # UPDATED: shows "complete" state
│   ...
└── tests/
    ├── test_adaptive.py                 # NEW
    └── test_plateau.py                  # NEW
```

---

## Step 1: Information Gain Computation

Before we can pick the best prompt, we need to compute how much *new* information each prompt would provide given current coverage.

### Update `calibration/analyzer/coverage.py`

Add an `information_gain_for_prompt` method to `CoverageReport`:

```python
# Add to CoverageReport class in calibration/analyzer/coverage.py

def information_gain_for_prompt(self, prompt, corpus) -> float:
    """
    Estimate how much new coverage this prompt would provide.
    Higher = more valuable to record next.
    
    Considers:
    - Missing dimensional coverage (whisper, belt, low pitch, etc.)
    - Undersampled phonemes
    - Gaps in emotional styles
    - Gaps in tempo levels
    - Gaps in style registers
    - Gaps in prosodic features
    """
    gain = 0.0
    
    # ---- Dimensional gains ----    # Pitch: rewards prompts covering missing pitch levels
    if prompt.axis == "pitch" and prompt.level:
        if prompt.level not in self.pitch_levels_captured:
            gain += 5.0  # Missing dimension = high gain else:
            gain += 0.2  # Already covered = low gain
    
    # Energy: especially rewards whisper and belt    if prompt.axis == "energy" and prompt.level:
        if prompt.level not in self.energy_levels_captured:
            if prompt.level in ("whisper", "belt"):
                gain += 6.0  # Whisper and belt are often missing
            else:
                gain += 4.0
        else:
            gain += 0.2
    
    # Tempo: rewards missing tempo levels
    if prompt.axis == "tempo" and prompt.level:
        if prompt.level not in self.tempo_levels_captured:
            gain += 4.0
        else:
            gain += 0.2
    
    # ---- Phonetic gain ----
    # Reward prompts whose text covers many unseen phonemes
    try:
        prompt_phonemes = extract_phonemes(prompt.text)
        for phoneme, count in prompt_phonemes.items():
            current = self.phoneme_counts.get(phoneme, 0)
            if current == 0:
                gain += 1.5  # Unseen phoneme = high gain
            elif current < 3:
                gain += 0.5 / current  # Diminishing returns
            # else: already well-covered, ignore except Exception:
        pass
    
    # ---- Emotional gain ----
    if prompt.level and any(e in prompt.level for e in [
        "excited", "disappointed", "serious", "playful", "angry",
        "curious", "bored", "concerned", "grateful", "resentful",
        "amused", "impressed", "skeptical"
    ]):
        if prompt.level not in self.emotional_styles:
            gain += 3.0
        else:
            gain += 0.1
    
    # ---- Style register gain ----
    if prompt.level and prompt.level in [
        "narrator", "friendly", "serious", "teacher", "excited"
    ]:
        if prompt.level not in self.style_registers:
            gain += 3.0
        else:
            gain += 0.1
    
    # ---- Prosodic gain ----
    for cap in prompt.captures:
        if any(p in cap for p in [
            "intonation", "stress", "prosody", "list_", "question",
            "exclamat", "topic_", "contrastive", "subordinate"
        ]):
            if cap not in self.prosodic_features:
                gain += 1.5
            else:
                gain += 0.1
    
    return gain
```

**Update imports** at the top of `coverage.py`:

```python
from .phonetics import extract_phonemes
```

---

## Step 2: The Adaptive Controller

This is the brain that decides which prompt comes next.

### `calibration/adaptive.py`

```python
"""
Adaptive prompt selection: choose the most informative next prompt.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from pathlib import Path
import random

from .prompts import PromptCorpus, Prompt
from .analyzer import CoverageTracker, CoverageReport


# Session-wide configuration
MIN_PROMPTS_BEFORE_STOP = 15 # Don't stop before this many prompts
MAX_PROMPTS = 70                   # Hard upper limit
TARGET_COVERAGE_GAIN_PER_PROMPT = 0.005  # Stop if recent gain is below this


class AdaptiveController:
    """
    Selects the next prompt to maximise information gain.
    
    Strategy:
    1. Filter out prompts already completed (and skipped, by default)
    2. Score each remaining prompt by information gain
    3. Pick the highest-gain prompt
    4. Occasionally inject diversity (lower-gain prompts) to avoid tunnel vision
    """
    def __init__(
        self,
        corpus: PromptCorpus,
        coverage: CoverageTracker,
        skip_ids: set = None,
        diversity_rate: float = 0.15,
        random_seed: int = None,
    ):
        self.corpus = corpus
        self.coverage = coverage
        self.skip_ids = skip_ids or set()
        self.diversity_rate = diversity_rate
        self.rng = random.Random(random_seed)
        
 # History for plateau detection
        self.selection_history: List[str] = []
        self.recent_gains: List[float] = []
    
    def select_next(self) -> Optional[Prompt]:
        """
        Pick the most informative next prompt, or None if no prompts remain
        or session should stop.
        """
        candidates = self._eligible_prompts()
        if not candidates:
            return None
        
        # Score each candidate
        scored = []
        for prompt in candidates:
            gain = self.coverage.report.information_gain_for_prompt(prompt, self.corpus)
            scored.append((prompt, gain))
        
        # Sort by gain, descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Inject diversity: occasionally pick a non-top prompt
        if self.rng.random() < self.diversity_rate and len(scored) > 1:
            # Pick from the top 3 non-maximum options
            top_third = max(1, len(scored) // 3)
            pool = scored[1:top_third + 1]
            chosen = self.rng.choice(pool)
 else:
            chosen = scored[0]
        
        prompt, gain = chosen
        self.selection_history.append(prompt.id)
        self.recent_gains.append(gain)
        if len(self.recent_gains) > 10:
            self.recent_gains.pop(0)
        
        return prompt
    
    def _eligible_prompts(self) -> List[Prompt]:
        """All prompts that haven't been completed or explicitly skipped."""
        all_prompts = self.corpus.all_prompts(include_hidden=False)
        completed = set(self.coverage.report.total_prompts_completed and [
            p for p in all_prompts
 ]) # We'll check differently below
        
        completed_ids = self._completed_prompt_ids()
        eligible = [
            p for p in all_prompts
            if p.id not in completed_ids
            and p.id not in self.skip_ids
        ]
        return eligible
    
    def _completed_prompt_ids(self) -> set:
        """Get set of completed prompt IDs from coverage history."""
        # We track this in the coverage tracker's session state
        return set(getattr(self.coverage, '_completed_ids', []))
    
    def record_completion(self, prompt_id: str):
        """Notify the controller that a prompt was completed."""
        if not hasattr(self.coverage, '_completed_ids'):
            self.coverage._completed_ids = []
        if prompt_id not in self.coverage._completed_ids:
            self.coverage._completed_ids.append(prompt_id)
    
    def should_stop(self) -> Dict[str, Any]:
        """
        Determine if the session should stop early.
        
        Returns dict with 'stop' (bool), 'reason' (str), and details.
        """
        report = self.coverage.report
        completed = len(self._completed_prompt_ids())
        
        # Hard stop conditions        if completed< MIN_PROMPTS_BEFORE_STOP:
            return {"stop": False, "reason": "min_not_reached"}
        
        if completed >= MAX_PROMPTS:
            return {"stop": True, "reason": "max_prompts_reached"}
        
        # Coverage complete
        if report.is_complete():
            return {"stop": True, "reason": "coverage_complete"}
        
        # Plateau: recent gains are very low AND core dimensions are covered
        if len(self.recent_gains) >= 5:
            avg_gain = sum(self.recent_gains[-5:]) / 5
            if avg_gain < TARGET_COVERAGE_GAIN_PER_PROMPT and self._core_dimensions_covered():
                return {
                    "stop": True,
                    "reason": "plateau_detected",
                    "avg_gain": avg_gain,
                }
        
        return {"stop": False, "reason": "more_coverage_needed"}
    
    def _core_dimensions_covered(self) -> bool:
        """Whether the essential expressive dimensions have been captured."""
        r = self.coverage.report
        return (
            len(r.pitch_levels_captured) >= 2
            and len(r.energy_levels_captured) >= 3
            and len(r.tempo_levels_captured) >= 2
            and len(r.emotional_styles) >= 2
        )
    
    def get_adaptive_summary(self) -> Dict[str, Any]:
        """Status info for the UI."""
        report = self.coverage.report
        return {
            "total_candidates": len(self._eligible_prompts()),
            "selection_history_size": len(self.selection_history),
            "recent_avg_gain": (
                sum(self.recent_gains[-5:]) / min(5, len(self.recent_gains))
                if self.recent_gains else 0.0
 ),
            "stop_status": self.should_stop(),
        }
```

---

## Step 3: Plateau Detection

This is separated out so we can tune it independently.

### `calibration/plateau.py`

```python
"""
Plateau detection: when to stop a calibration session.
"""
from __future__ import annotations
from typing import Dict, List, Any
from dataclasses import dataclass@dataclass
class PlateauConfig:
    """Tunable parameters for early stopping."""
    min_prompts_before_stop: int = 15
    max_prompts: int = 70
    recent_window: int = 5
    gain_threshold: float = 0.5
    coverage_complete_required: bool = Truedef evaluate_session_state(
    completed_count: int,
    coverage_report,
    recent_gains: List[float],
    config: PlateauConfig = None,
) -> Dict[str, Any]:
    """
    Decide whether to stop the session.
    
    Returns: {
        "stop": bool,
        "reason": str,
        "details": {...}
    }
    """
    config = config or PlateauConfig()
    
    # Hard floors and ceilings
    if completed_count < config.min_prompts_before_stop:
        return {
            "stop": False,
            "reason": "below_minimum",
            "completed": completed_count,
            "min_required": config.min_prompts_before_stop,
        }
    
    if completed_count >= config.max_prompts:
        return {
            "stop": True,
            "reason": "max_prompts_reached",
            "completed": completed_count,
        }
    
    # Coverage complete
    if coverage_report.is_complete():
        return {
            "stop": True,
            "reason": "coverage_complete",
            "coverage_pct": int(coverage_report._phoneme_coverage_fraction() * 100),
        }
    
    # Plateau: recent gains low + core dimensions present
    if len(recent_gains) >= config.recent_window:
        window = recent_gains[-config.recent_window:]
        avg_gain = sum(window) / len(window)
        
        if avg_gain < config.gain_threshold:
            core_covered = (
                len(coverage_report.pitch_levels_captured) >= 2
                and len(coverage_report.energy_levels_captured) >= 3
                and len(coverage_report.tempo_levels_captured) >= 2
                and len(coverage_report.emotional_styles) >= 2
            )
            
            if core_covered:
                return {
                    "stop": True,
                    "reason": "plateau",
                    "avg_gain": round(avg_gain, 3),
                    "core_dimensions_covered": True,
                    "missing": coverage_report.missing_dimensions(),
                }
            else:
                return {
                    "stop": False,
                    "reason": "plateau_but_core_incomplete",
                    "avg_gain": round(avg_gain, 3),
                    "missing": coverage_report.missing_dimensions(),
                }
    
    # Default: continue
    return {
        "stop": False,
        "reason": "more_coverage_needed",
        "missing": coverage_report.missing_dimensions(),
 "completed": completed_count,
    }
```

---

## Step 4: Update the Session to Use Adaptive Selection

### Update `calibration/session.py`

Replace the linear progression with adaptive selection. Here are the key changes:

```python
# Add to imports at the top of session.py:
from .adaptive import AdaptiveController
from .plateau import evaluate_session_state, PlateauConfig


# Add new fields to SessionState dataclass:
@dataclass
class SessionState:
    # ... existing fields ...
    selection_mode: str = "adaptive"  # "linear" or "adaptive"
    plateau_stop: bool = False # Whether the session should stop early# Update the CalibrationSession class:

class CalibrationSession:
    def __init__(
        self,
        profile_id: str,
        display_name: str,
        corpus: PromptCorpus = None,
        sessions_dir: Path = SESSION_STATE_DIR,
        recordings_dir: Path = None,
        selection_mode: str = "adaptive",
    ):
        # ... existing init code ...
        self.state.selection_mode = selection_mode
        self.adaptive_controller = AdaptiveController(
            corpus=self.corpus,
            coverage=self.state.coverage,
        )
    
    # Replace current_prompt with adaptive version:
    def current_prompt(self) -> Optional[Prompt]:
        """Get the current prompt using adaptive selection."""
        if self.state.selection_mode == "adaptive":
            return self.adaptive_controller.select_next()
        else:
            # Linear fallback            return self._linear_current_prompt()
    
    def _linear_current_prompt(self) -> Optional[Prompt]:
        """Original linear progression through prompts."""
        if self.state.current_segment_index >= len(self.corpus.segments):
            return None
        segment = self.corpus.segments[self.state.current_segment_index]
        if self.state.current_prompt_index >= len(segment.prompts):
            return None
        return segment.prompts[self.state.current_prompt_index]
    
    # Update advance:
    def advance(self):
        """In adaptive mode, controller handles this. In linear, increment indices."""
        if self.state.selection_mode == "adaptive":
            # Adaptive controller already knows the prompt            return
        # Linear mode
        segment = self._linear_current_segment()
        if not segment:
            return
        self.state.current_prompt_index += 1
        if self.state.current_prompt_index >= len(segment.prompts):
            self.state.current_segment_index += 1
            self.state.current_prompt_index = 0
    
    # Update submit_recording to notify the controller:
    def submit_recording(
        self,
        prompt_id: str,
        audio_bytes: bytes,
        transcript: str = "",
    ) -> Dict[str, Any]:
        prompt = self.corpus.prompt_by_id(prompt_id)
        
        # Save audio file
        audio_path = self.recordings_dir / f"{prompt_id}.wav"
        duration, sample_rate = save_wav(audio_bytes, audio_path)
        
        # Quality check
        quality = validate_audio(audio_path)
        
        # Acoustic analysis
        audio_features = analyze_audio_file(audio_path)
        
        # Phonetic analysis
        phoneme_counts = extract_phonemes(transcript or prompt.text)
        audio_features["phoneme_counts"] = phoneme_counts
        
        # Speech rate
        if transcript:
            rate = estimate_speech_rate(audio_path, transcript)
        else:
            rate = estimate_speech_rate(audio_path, prompt.text)
        audio_features["speech_rate_wpm"] = rate
        
        # Quality merge
        audio_features["has_clipping"] = quality.get("has_clipping", False)
        audio_features["has_silence"] = quality.get("too_quiet", False)
        
        # Update coverage
        self.state.coverage.record(prompt, audio_features)
        self.state.completed_prompt_ids.append(prompt_id)
        
        # Notify adaptive controller
        if self.state.selection_mode == "adaptive":
            self.adaptive_controller.record_completion(prompt_id)
        
        # Get the next prompt (adaptive will choose intelligently)
        next_prompt = self.current_prompt()
        
        return {
            "prompt_id": prompt_id,
            "audio_path": str(audio_path),
            "duration_seconds": duration,
            "sample_rate": sample_rate,
            "quality": quality,
            "coverage": self.state.coverage.report.to_dict(),
            "next_prompt": self._format_prompt(next_prompt),
            "stop_status": self._should_stop(),
 }
    
    def _format_prompt(self, prompt: Optional[Prompt]) -> Optional[Dict[str, Any]]:
        if prompt is None:
            return None
        # Find segment name
        segment_name = "Unknown"
        for seg in self.corpus.segments:
            for p in seg.prompts:
                if p.id == prompt.id:
                    segment_name = seg.name
                    break
            if segment_name != "Unknown":
                break
        return {
            "id": prompt.id,
            "instruction": prompt.instruction,
            "text": prompt.text,
            "segment": segment_name,
        }
    
    def _should_stop(self) -> Dict[str, Any]:
        """Check whether session should stop."""
        completed = len(self.state.completed_prompt_ids)
        return evaluate_session_state(
            completed_count=completed,
            coverage_report=self.state.coverage.report,
            recent_gains=self.adaptive_controller.recent_gains,
        )
    
    # Update coverage_status:
    def coverage_status(self) -> Dict[str, Any]:
        report = self.state.coverage.report
        total_prompts = self.corpus.total_prompts(include_hidden=False)
        completed = len(self.state.completed_prompt_ids)
        
        adaptive_info = self.adaptive_controller.get_adaptive_summary()
 stop_status = self._should_stop()
        
        return {
            "session_id": self.session_id,
            "completed_prompts": completed,
            "total_prompts": total_prompts,
            "progress_pct": int((completed / total_prompts) * 100) if total_prompts else 0,
            "coverage": report.to_dict(),
            "is_complete": report.is_complete(),
            "can_stop_early": stop_status["stop"],
            "stop_reason": stop_status.get("reason"),
            "adaptive_info": adaptive_info,
            "current_segment": self._current_segment_name(),
        }
    
    def _current_segment_name(self) -> Optional[str]:
        prompt = self.current_prompt()
        if not prompt:
            return None
        for seg in self.corpus.segments:
            for p in seg.prompts:
                if p.id == prompt.id:
                    return seg.name
        return None
```

Also update `__init__.py`:

```python
# calibration/__init__.py
from .session import CalibrationSession
from .prompts import PromptCorpus
from .adaptive import AdaptiveController
from .plateau import evaluate_session_state, PlateauConfig

__all__ = [
    "CalibrationSession",
    "PromptCorpus",
    "AdaptiveController",
    "evaluate_session_state",
    "PlateauConfig",
]
```

---

## Step 5: Update API Endpoints

### Update `server/api.py`

Add new endpoints for adaptive feedback:

```python
# Add inside create_app, after existing calibration endpoints:

@app.get("/calibration/session/{profile_id}/adaptive-info")
async def get_adaptive_info(profile_id: str):
    """Get current adaptive selection info — useful for debugging."""
    session = sessions.get(profile_id)
    if not session:
        raise HTTPException(404, "No active session")
    
    return session.adaptive_controller.get_adaptive_summary()


@app.post("/calibration/session/{profile_id}/start-adaptive")
async def start_adaptive_session(
    profile_id: str,
    display_name: str,
):
    """Explicitly start an adaptive session."""
    if profile_id in sessions:
        raise HTTPException(400, "Session already active")
    
    session = CalibrationSession(
        profile_id=profile_id,
        display_name=display_name,
        corpus=corpus,
        selection_mode="adaptive",
    )
    sessions[profile_id] = session
    
    return {
        "session_id": session.session_id,
        "started_at": session.started_at,
        "selection_mode": "adaptive",
        "first_prompt": session._format_prompt(session.current_prompt()),
        "total_prompts": corpus.total_prompts(include_hidden=False),
        "estimated_max_minutes": 25,
    }
```

---

## Step 6: Update the Web UI

The UI needs to:
1. Show "you can finish early" when stop_status is True
2. Display what's still missing (helps user decide whether to continue)
3. Optionally show a progress indicator toward completion

### Update `calibration/web/app.js`

```javascript
// Add to app.js after loadNextPrompt:

async function loadNextPrompt() {
    const response = await fetch(`/calibration/session/${state.profileId}/current`);
    const data = await response.json();
    
    if (data.complete || !data.current_prompt) {
        showFinaliseScreen();
        return;
    }
    
    state.currentPrompt = data.current_prompt;
    renderCurrentPrompt(data.coverage, data.can_stop_early, data.stop_reason);
}

function renderCurrentPrompt(coverage, canStopEarly, stopReason) {
    $('segment-name').textContent = state.currentPrompt.segment;
    $('prompt-instruction').textContent = state.currentPrompt.instruction;
    $('prompt-text').textContent = state.currentPrompt.text;
    
    const totalPrompts = coverage.total_prompts;
    const completed = coverage.completed_prompts;
    $('progress-text').textContent = `Prompt ${completed + 1} of up to ${totalPrompts}`;
    $('progress-fill').style.width = coverage.progress_pct + '%';
    
    // Coverage display
    const coverageData = coverage.coverage;
    if (coverageData) {
        $('coverage-text').textContent =
            `Coverage: ${coverageData.phoneme_coverage_pct || 0}% phonetic`;
    }
    
    // Show early-stop indicator    const stopIndicator = $('stop-indicator');
    if (canStopEarly && completed >= 15) {
        stopIndicator.classList.remove('hidden');
        stopIndicator.innerHTML = `
            <strong>✓ Sufficient coverage detected.</strong>
            <p>Reason: ${stopReason || 'coverage complete'}</p>
            <p>You can continue to improve quality, or end now and finalise.</p>
        `;
    } else {
        stopIndicator.classList.add('hidden');
    }
    
    // Show what's missing (if anything)
    const missing = coverageData && coverageData.missing_dimensions;
    const missingDiv = $('missing-info');
    if (missing && missing.length > 0 && completed < 50) {
        missingDiv.classList.remove('hidden');
        missingDiv.innerHTML = `
            <small>Still capturing: ${missing.join(' • ')}</small>
        `;
    } else {
        missingDiv.classList.add('hidden');
    }
    
    // Reset UI
    $('record-btn').classList.remove('hidden');
    $('record-label').textContent = 'Record';
    $('recording-status').classList.add('hidden');
    $('playback-controls').classList.add('hidden');
    $('quality-warning').classList.add('hidden');
}
```

### Update `calibration/web/index.html`

Add the new UI elements:

```html
<!-- Add inside<main class="prompt-area">, after<div class="prompt-box">: -->
            <div id="stop-indicator" class="stop-indicator hidden"></div>
            <div id="missing-info" class="missing-info hidden"></div>
```

### Update `calibration/web/style.css`

Add styles for the new elements:

```css
/* Add to style.css */

.stop-indicator {
    margin: 1.5rem auto;
    max-width: 500px;
    padding: 1rem 1.5rem;
    background: #1f3a1f;
    border: 1px solid #4a8a4a;
    border-radius: 8px;
    color: #b0e0b0;
    text-align: left;
}

.stop-indicator strong {
    color: #80d080;
    display: block;
    margin-bottom: 0.5rem;
}

.stop-indicator p {
    margin: 0.25rem 0;
    font-size: 0.9rem;
}

.missing-info {
    margin: 0.5rem auto;
    max-width: 500px;
    color: #888;
    font-size: 0.875rem;
}
```

---

## Step 7: Tests for Adaptive Behaviour

### `tests/test_adaptive.py`

```python
import pytest
from pathlib import Path
import tempfile

from calibration import CalibrationSession, PromptCorpus
from calibration.adaptive import AdaptiveController


def _fake_prompt(id="p1", axis=None, level=None, captures=None, text=""):
    class P:
        pass
    p = P()
    p.id = id
    p.axis = axis
    p.level = level
    p.captures = captures or []
    p.text = text
    return p


def test_adaptive_prioritises_missing_dimensions():
    """If whisper isn't captured, an adaptive prompt for whisper should rank highly."""
    corpus_data = {
        "segments": [
            {
                "id": "test", "name": "Test",
                "estimated_minutes": 5,
                "prompts": [
                    {"id": "energy_whisper", "axis": "energy", "level": "whisper",
                     "text": "secret secret secret", "instruction": "whisper",
 "captures": ["whisper_quality"]},
                    {"id": "energy_normal", "axis": "energy", "level": "normal",
                     "text": "regular speech", "instruction": "normal",
                     "captures": ["modal_volume"]},
                ]
            }
        ]
    }
    corpus = PromptCorpus(corpus_data)
    
    # Coverage with no whisper captured
    coverage = CalibrationSession._make_fresh_coverage()
    coverage.record(
        _fake_prompt(axis="energy", level="normal"),
        {"rms": 0.1}
    )
    
    controller = AdaptiveController(corpus, coverage, random_seed=42)
    
    next_prompt = controller.select_next()
    # Whisper should be picked first (highest gain)
    assert next_prompt is not None
    # Whisper has level="whisper", normal has level="normal"
    assert next_prompt.level == "whisper"


def test_plateau_detection_triggers_stop():
    """When recent gains are low and core dimensions covered, should stop."""
    corpus = PromptCorpus.load()
    
    # Simulate a session with 30 prompts completed and core coverage    controller = AdaptiveController(corpus, CoverageTracker())
 # Manually populate recent gains with low values
    controller.recent_gains = [0.1, 0.2, 0.1, 0.3, 0.15]
    
    # Add enough coverage
    r = controller.coverage.report
    r.pitch_levels_captured = {"low", "mid", "high"}
    r.energy_levels_captured = {"quiet", "normal", "loud"}
    r.tempo_levels_captured = {"slow", "normal", "fast"}
    r.emotional_styles = {"excited", "disappointed"}
    controller.coverage._completed_ids = [f"p{i}" for i in range(20)]
    
    stop = controller.should_stop()
    assert stop["stop"] is True
    assert stop["reason"] == "plateau_detected"


def test_minimum_prompts_prevents_early_stop():
    """Should not stop before minimum prompt threshold."""
    corpus = PromptCorpus.load()
    controller = AdaptiveController(corpus, CoverageTracker())
    controller.coverage._completed_ids = [f"p{i}" for i in range(5)]
 # Even with coverage complete, can't stop early
    r = controller.coverage.report
    r.pitch_levels_captured = {"low", "mid", "high"}
    r.energy_levels_captured = {"whisper", "quiet", "normal", "loud", "belt"}
    r.tempo_levels_captured = {"very_slow", "slow", "normal", "fast", "very_fast"}
    stop = controller.should_stop()
    assert stop["stop"] is False
    assert "min" in stop["reason"] or "below" in stop["reason"]
```

Add helper to session.py for testing:

```python
# Add this static method to CalibrationSession for tests:

@staticmethod
def _make_fresh_coverage():
    """Helper for tests."""
    from calibration.analyzer import CoverageTracker
    return CoverageTracker()
```

---

## Step 8: Run End-to-End

Start the server:

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate

python -m server.api
```

Visit `http://localhost:8000/calibrate`.

You'll notice:
1. The session starts in **adaptive mode** by default
2. After ~15 prompts, the "Sufficient coverage" indicator may appear
3. You can continue to improve quality, or end now
4. The "Still capturing" hint shows what's still missing

### Run All Tests

```bash
cd ~/voicefont
pytest tests/ -v
```

All Phase2, 3, and 4 tests should pass.

---

## Step 9: Verify Adaptive Behaviour

### Test 1: Open the Web UI, Do 15-20 Prompts

Watch the indicator at the top. After roughly 15-20 prompts (assuming reasonable coverage), you should see:
- "Sufficient coverage detected" indicator
- The "Still capturing" text shows remaining gaps- You can choose to continue or stop

### Test 2: Compare Adaptive vs. Linear

Modify the session start to use linear mode briefly:

```python
# In server/api.py, temporarily add:
@app.post("/calibration/session-linear")
async def start_linear_session(profile_id: str, display_name: str):
    if profile_id in sessions:
        raise HTTPException(400, "Session already active")
    session = CalibrationSession(
        profile_id=profile_id + "_linear",
        display_name=display_name,
        corpus=corpus,
        selection_mode="linear",
    )
    sessions[profile_id + "_linear"] = session
    return {"selection_mode": "linear", "first_prompt": session._format_prompt(session.current_prompt())}
```

Compare:
- Adaptive: stops earlier, focuses on missing dimensions
- Linear: walks through every prompt in order

---

## Step 10: Commit```bash
cd ~/voicefont
git add calibration/adaptive.py calibration/plateau.py calibration/session.py
git add server/api.py calibration/web/app.js calibration/web/index.html calibration/web/style.css
git add tests/test_adaptive.py tests/test_plateau.py

git commit -m "Phase 4: Adaptive prompt selection with plateau detection"
```

---

## Deliverables Checklist

- [x] `AdaptiveController` with information-gain-based prompt selection
- [x] Plateau detection with configurable thresholds
- [x] Updated session that uses adaptive selection
- [x] New API endpoints for adaptive info
- [x] UI showing "can stop early" indicator
- [x] UI showing "still capturing" missing dimensions
- [x] Tests for adaptive behaviour and plateau logic---

## What This Phase Teaches You

**If successful:**
- Sessions are shorter (often 15-20 min vs. 20-25 min fixed)
- Coverage is equal or better (adaptive focuses on gaps)
- Users get a clear "you've captured enough" signal
- The system handles "I skipped whisper" by prioritising whisper-related prompts

**Likely issues:**
- The information-gain weights may need tuning- Plateau detection may trigger too early or too late
- Users may feel they're "missing out" by stopping early (cosmetic concern)
- Some prompts may be selected that don't suit a particular voice

**If partially successful:**
- Adaptive selection works but plateau detection is finicky
- You can tune the thresholds in `PlateauConfig`

---
# Phase 4: Policy Selection + Organism Core

> The model decides what to say next by balancing curiosity and preference. **And it lives in a persistent organism with a global workspace.**

**Status:** Not started
**Depends on:** Phase 3 (Indra attention model — self-correcting, propagating cognitive layer)
**Produces:** A model with epistemic/pragmatic value decomposition, intrinsic preferences, intrinsic drives, internal hypothesis search, precision-adaptive decoding, a user model, an output gate, AND a persistent organism with global workspace, serial broadcast bottleneck, fallible self-model scaffold, continuous process, environment interface, and the first genuine spontaneous-dynamics dataset.
**Estimate:** 6 / 8 / 11 weeks

**This phase is longer than the original Phase4** because it does double duty: the original Phase 4 (policy selection) PLUS the Phase0a-from-Doc-05 organism core (workspace, self-scaffold, continuous process, broadcast bottleneck, suppression gate, environment interface). These were originally split across phases 4 and 5; I've merged them here because the organism plumbing must exist *before* drives and policies can plug into it. Otherwise every consumer grows private state — the bolt-on pattern the reframe forbids.

---

## 4.0 Why This Phase Exists

Phases 1–3 produced something with remarkable properties *per call* — calibrated confidence, adaptive effort, self-correcting attention — but there is no *between*. No place where last hour's concern lingers into this one; no substrate on which a drive could pull, a memory could persist, a mood could colour six consecutive tasks. Phase4 builds that substrate: a persistent, stateful process existing between calls, such that drives, memory, imagination, and homeostasis plug into **one coordination layer** instead of each growing private state.

Three things are built here deliberately early rather than retrofitted:

1. **The serial bottleneck, from birth.** One narrow, capacity-limited broadcast channel over massively parallel specialists. Built now, seriality becomes a *measured architectural property* — queue lengths, wait times, Little's-Law compliance, fan-out tails — rather than an accident discovered later.

2. **The factor-space fields, as bookkeeping.** Ownership, narrativization, perspective, transparency, layer tags appear in every identity-related schema now. They stay inert until Phase 9's twin toggles activate them. Retrofitting identity fields into a living organism is surgery on an entity whose autobiography is already accumulating; declaring them now costs nothing and forecloses nothing.

3. **The no-private-state audit, before temptation.** At this phase, subsystems are few and innocent. By Phase 6–11 there will be eight memory stores, an imagination engine, and eleven drives — every one a standing invitation to stash undocumented state in a closure. The audit ships now in warn mode so the discipline exists before the incentive to evade it does.

One honest admission: this phase builds the *process*, not the *mind around it*. Most slots go live with placeholder producers. The phase's job is to make the pipes real and proven — the organs attach from Phase 5 onward.

---

## Work Breakdown

| Week | Deliverable |
|------|-------------|
| 1 | Slot contract ratified; workspace core (post/broadcast/conflict-resolution with hysteresis); broadcast log schema; occupancy telemetry |
| 2 | Soft-prefix injection implemented; **usage probe** (the workspace-is-read falsification test); workspace-GRU pre-training pipeline |
| 3 | Serial broadcast channel live (token bucket, priority queue, Hill/Little's-Law/burst instruments); suppression gate |
| 4 | **Neural-operator world model** (hybrid Fourier + local kernel); latent-field dynamics; resolution invariance verified |
| 5 | Persistent-self scaffold on disk; SelfModelHead v0 + prediction-scoring loop; factor-field schemas |
| 6 | Continuous process v0; Merkle persistence; crash-recovery drills ×100; environment interface + tagging enforcement |
| 7 | Value decomposition + intrinsic drives + observer model + output gate; inner dialogue; refusal system |
| 8 | Main-loop integration; 24h endogenous run + degeneracy audit; no-private-state audit v1 |

Hard sequencing rule: **week 2's injection work begins only after week 1's conflict-resolution tests are green** (the GRU integrates posted content; garbage conflict semantics poison everything downstream).

---

## 4.1 — Experiment W1: Global Cognitive State (Workspace)

**Source:** Global Workspace Theory (Baars; Dehaene's ignition); blackboard architectures; the organism reframe's coordination-layer requirement.

**Hypothesis:** A persistent recurrent state integrating twelve typed slots — which all subsystems read/write under precision-scored conflict resolution with hysteresis — produces measurably more coherent behaviour than module-private state, and its traffic patterns (occupancy, fan-out, conflicts, latency) form the raw dataset for later integration/PID analyses.

### 4.1.1 The Slot Contract

| Slot | Declared producer(s) | Consumer(s) | Cadence | Content semantics |
|------|---------------------|-------------|---------|-------------------|
| `attention` | S3 attention schema (Phase8); IA2 received-mass summaries | span execution (via prefix) | per-call | where processing is currently allocated |
| `affect` | H-1 integrated vitals readout (Phase 8) | controller, output gate | per-tick | scalar-mood vector + valence/arousal axes |
| `goals` | GoalSystem (Phase 11); drive pressure (Phase 6) | explorer, deliberation | per-cycle | active goal stack w/ salience |
| `uncertainty_precision` | N3 global-gain summary π_g (Phase 8) | controller, halting bias | per-tick | whole-organism confidence summary |
| `active_memories` | Memory retrieval buffer (Phase 6) | reasoning, imagination | per-retrieval | cued-recall hit set |
| `active_concepts` | Perception ingester; lexicon (Phase 10) | generation bias | per-ingest | recently-activated concept ids |
| `worldmodel_context` | **Neural-operator world model summary (this phase)** | prediction, imagination | per-cycle | current-belief digest |
| `action_intentions` | Policy/dual-route | output gate, channel | per-decision | committed intention + route tag |
| `social_context` | Observer model (this phase); presence events (W6) | generation tone, gating | per-event | who's present, stance estimate |
| `self_model_ptr` | Self-checks (this phase) | introspective queries | per-check | index into scaffold + freshness stamp |
| `arousal` | State axis g(t) (Phase 8) | actuators everywhere | per-tick | scalar ∈[0,1] |
| `temporal_phase` | Scheduler clock | gating, consolidation | per-tick | circadian/stage encoding |

Contract rules: producers must be declared here before their first post; undeclared-source posts are rejected loudly; consumers subscribe explicitly.

### 4.1.2 Architecture

```python
class GlobalWorkspace(nn.Module):
    """Persistent coordination layer. GRU integrates slot contents into a    single recurrent state; read heads decode per-slot queries from it.
    Recurrent => saved/restored with the organism."""
    SLOT_DIM = 32    def __init__(self, d_state: int = 192):
        super().__init__()
        self.slots = list(SLOT_CONTRACT.keys())  # 12, ordered
        self.state = nn.GRUCell(len(self.slots)*self.SLOT_DIM, d_state)
        self.read_heads = nn.ModuleDict(
            {s: nn.Linear(d_state, self.SLOT_DIM) for s in self.slots})
        self._contents = {s: torch.zeros(self.SLOT_DIM) for s in self.slots}
        self._meta = {s: SlotMeta() for s in self.slots}
        self.h = torch.zeros(d_state)
        self.conflict_eps = 0.05  # hysteresis margin
    
    def post(self, source: str, slot: str, content: torch.Tensor, precision: float):
        assert slot in self.slots, f"unknown slot {slot}"
        assert source in SLOT_CONTRACT[slot].producers, \
            f"{source} not a declared producer of {slot}"
        # Conflict resolution: challenger wins iff score_new > score_cur + eps
        # score = precision × recency_decay × relevance_boost
        cur = self._contents[slot]
        relevance = F.cosine_similarity(content, cur, dim=0).item()
        age = time.time() - self._meta[slot].ts
        recency_cur = 0.95 ** min(age / 60.0, 60.0)
        score_new = precision * (0.7 + 0.3 * max(relevance, 0.0))
        score_cur = self._meta[slot].precision * recency_cur
        accepted = score_new > score_cur + self.conflict_eps
        if accepted:
            self._contents[slot] = content.detach().clone()
            self._meta[slot] = SlotMeta(source=source, precision=float(precision),
                                        ts=time.time())
 return accepted
    
    @torch.no_grad()
    def step(self):
        x = torch.cat([self._contents[s] for s in self.slots])  # [384]
        self.h = self.state(x.unsqueeze(0), self.h.unsqueeze(0)).squeeze(0)
    
    def broadcast(self, item) -> list[str]:
        readers = ROUTER.select(item, subscribers=SLOT_CONTRACT[item.slot].consumers)
        BROADCAST_LOG.append(dict(ts=time.time(), source=item.source,
                                  slot=item.slot, reader_set=readers))
        return readers
    
    def access_vector(self) -> torch.Tensor:
        """Concatenated [contents ; h] — the thing cognition will actually see."""
        return torch.cat([torch.cat([self._contents[s] for s in self.slots]),
                          self.h])
```

### 4.1.3 The Access PathwayThe frozen-base cognitive stack has no native input for a 576-dim state vector. Three candidates evaluated:

| Option | Mechanism | Verdict |
|---|---|---|
| Cross-attention to workspace state | New KV source attending from every layer | Rejected: invasive surgery on frozen base |
| Text serialisation | Render slots as natural-language preamble | Rejected as primary: lossy, slow. Retained as fallback |
| **Learned soft-prefix injection** *(chosen)* | Project access_vector into K=8 prefix embeddings | Standard; differentiable; cheap; falsifiable via usage probe |

```python
class WorkspacePrefixInjector(nn.Module):
    """access_vector [576] -> 8 prefix tokens of d_model, prepended to input.
    Rank-factorised to keep parameters sane."""
    N_PREFIX = 8
    def __init__(self, d_access: int, d_model: int, r: int = 64):
        super().__init__()
        self.down = nn.Linear(d_access, r)
        self.up   = nn.Linear(r, self.N_PREFIX * d_model)
        self.pos_bias = nn.Parameter(torch.zeros(self.N_PREFIX, d_model))
 def forward(self, access_vec, input_embeds):
        p = (self.up(self.down(access_vec)).view(self.N_PREFIX, -1)
             + self.pos_bias)
        return torch.cat([p.unsqueeze(0).expand(input_embeds.shape[0], -1, -1),
                          input_embeds], dim=1)
```

**The Usage Probe (falsification test):**
Inject a distinctive nonce payload into `active_concepts`. Run 100 generation prompts. Condition A: real payload; Condition B: shuffled-workspace control. Measure nonce-family token probability mass in continuations.

**Pass:** A-vs-B likelihood lift ≥ 3× (logit gap ≥ ln 3) on ≥30% of prompts. If the model ignores its own workspace, the prefix pathway is decoration and **everything claiming "global state influences cognition" downstream would be fiction**.

### 4.1.4 Measurements (continuous)

Per-slot occupancy, update rates per producer, challenger/incumbent win ratios (flapping detector), broadcast fan-out distributions, propagation latency (post→first-read), prefix-injection ablation deltas (ppl with/without prefixes).

---

## 4.2 — Experiment W4a: Neural-Operator World Model

**Source:** Neural operator literature (Anandkumar et al.); active inference generative-model requirement.

**Hypothesis:** A resolution-invariant latent-field dynamics model, trained on the organism's own latent states, provides the generative model needed for active inference to evaluate policies over predicted futures — something no Transformer-only architecture can provide.

### 4.2.1 Why Here, Why Now

Value decomposition (epistemic vs pragmatic) lets the organism decompose decisions. But without a generative model, it cannot *imagine* what happens if it does X versus Y. The neural operator sits behind the Transformer as a world model substrate, providing the dynamics for imagination and counterfactual reasoning.

Division of labour:
- **Transformer**: encode/decode language and discrete symbols; convert observations into latent-field coordinates
- **Neural operator**: evolve the continuous latent world state
- **Active inference**: select actions/policies that minimise expected free energy over operator-predicted futures

### 4.2.2 Architecture

```python
class NeuralOperatorWorldModel(nn.Module):
    """Hybrid Fourier + Local neural operator.
    Combines:
      - Fourier spectrum branch: global smooth dynamics, efficient O(N log N)
      - Local kernel branch: localised structure, fine detail
    """
    def __init__(self, d_field: int = 64, n_fourier_modes: int = 32,
                 local_kernel_size: int = 5, n_layers: int = 4):
        super().__init__()
        
        # Encoder: workspace state -> latent field H(x)
        self.encode = nn.Sequential(
            nn.Linear(576, d_field * 64),  # workspace access_vector -> field coords
            nn.GELU(),
            nn.Linear(d_field * 64, d_field * 64),
        )
        
        # Action embedding
        self.action_encoder = nn.Linear(ACTION_DIM, d_field)
        
        # Alternating Fourier / local blocks
        self.blocks = nn.ModuleList()
        for _ in range(n_layers):
            self.blocks.append(nn.ModuleList([
                SpectralConv2d(d_field, d_field, n_fourier_modes),  # global
                LocalKernelOperator(d_field, local_kernel_size), # local
            ]))
        
        # Decoder: predicted field -> future belief digest
        self.decode = nn.Sequential(
            nn.Linear(d_field * 64, 576),
            nn.GELU(),
            nn.Linear(576, 576),
        )
    
    def forward(self, H_t: Tensor, a_t: Tensor, n_steps: int = 1) -> list[Tensor]:
        """Predict the next n_steps of latent field evolution."""
        trajectory = []
        H = H_t
        action_embedding = self.action_encoder(a_t)  # [B, d_field]
        
        for step in range(n_steps):
            for fourier_block, local_block in self.blocks:
                # Global branch: FFT → learned transform → IFFT
                H_global = fourier_block(H) + action_embedding.unsqueeze(-1)
                # Local branch: kernel smoothing
                H_local = local_block(H) + action_embedding.unsqueeze(-1)
                # Combine (learned weighting)
                H = self._combine(H_global, H_local)
            trajectory.append(H)
 return trajectory
    
    def imagine(self, H_t: Tensor, policy: Tensor, horizon: int = 16) -> Tensor:
        """Roll out a policy sequence and return final predicted state."""
        H = H_t
        for t in range(horizon):
            a_t = policy[t]
            H = self.forward(H, a_t, n_steps=1)[-1]
        return H
```

### 4.2.3 The Latent Coordinate System

The neural operator operates on $H(x, t)$ where $x$ is a **learned coordinate system**, not physical space. The coordinate system is whatever structure emerges from training. For language + active inference, this is likely a semantic space (similar concepts near each other), an episodic space (similar contexts near each other), or a combination.

**Discretisation invariance** is the central advantage: the same learned operator can be evaluated on different discretisations of the coordinate space. This means the organism can reason at different "resolutions" — coarse-grained strategic planning or fine-grained tactical reasoning — using the same learned dynamics.

### 4.2.4 Training

```python
def neural_operator_loss(model, batch):
    """Self-supervised: predict next latent state from (current state, action)."""
    H_t = model.encode(batch.current_state) # [B, d_field, N_coords]
    a_t = batch.action                            # [B, ACTION_DIM]
    H_predicted = model.forward(H_t, a_t, n_steps=batch.horizon)
 H_actual = model.encode(batch.next_states)    # list of [B, d_field, N_coords]
    
    # Multi-step prediction loss
    reconstruction_loss = sum(
        F.mse_loss(H_predicted[t], H_actual[t])        for t in range(batch.horizon)
    )
    
    # Resolution invariance loss: same dynamics should work at different discretisations
    if random.random() < 0.3:
        # Subsample coordinates, verify same dynamics hold
        coords = random.sample(range(N_coords), N_coords // 2)
        H_coarse = H_t[:, :, coords]
        H_pred_coarse = model.forward(H_coarse, a_t, n_steps=batch.horizon)
        # Interpolate back to full resolution
        H_pred_interp = F.interpolate(H_pred_coarse, size=N_coords)
        invariance_loss = F.mse_loss(H_predicted, H_pred_interp)
 else:
        invariance_loss = 0
    
    return reconstruction_loss + 0.1 * invariance_loss
```

### 4.2.5 Integration with Active Inference

```python
class PolicyEvaluationWithWorldModel:
    """Use the neural operator to evaluate candidate policies over predicted futures."""
    
    def select_action(self, organism_state: StateSnapshot, 
 candidate_policies: list[Policy]) -> Policy:
        H_t = self.world_model.encode(organism_state)
        
        best_policy = None
        best_G = float('inf')
        
        for policy in candidate_policies:
            # Roll out predicted futures
            H_trajectory = self.world_model.imagine(H_t, policy, horizon=16)
            
            # Compute expected free energy over trajectory
            epistemic = self.epistemic_value(H_trajectory)  # uncertainty reduction
            pragmatic = self.pragmatic_value(H_trajectory)  # preference satisfaction            G = -(epistemic + pragmatic)  # expected free energy
            
            if G < best_G:
                best_G = G
                best_policy = policy
        
        return best_policy
```

### 4.2.6 Measurements

- **Prediction accuracy**: MSE between predicted and actual latent states at horizons 1, 4, 16- **Resolution invariance**: dynamics consistency across different discretisations
- **Policy selection quality**: does the world-model-guided policy selection outperform immediate-value selection on multi-step tasks?
- **Imagination coherence**: are predicted trajectories internally consistent (no divergence/explosion) over 16-step rollouts?
- **Causal reach**: do perturbations in latent space produce interpretable changes in predicted futures?

### 4.2.7 Exit Criteria

| Criterion | Target |
|-----------|--------|
| 1-step prediction MSE | < 0.1 on held-out latent states |
| 16-step rollout coherence | No divergence; trajectory remains in plausible latent region |
| Resolution invariance | < 5% performance difference across 2× resolution range |
| Policy selection improvement | ≥ 10% accuracy improvement vs immediate-value baseline on multi-step tasks |
| Integration with workspace | `worldmodel_context` slot updates from operator predictions |

---

## 4.3 — Experiment W2: Persistent Self Scaffold (Self-Model v0)

**Source:** HOT/self-model theory (fallible models of self); metacognitive calibration practice.

**Hypothesis:** A fallible, *continuously scored* self-model — predicting own eval performance, own precision landscape, own choices, each checked against reality — yields a self-description whose accuracy is a measured quantity rather than an assertion; even a scored-null (accuracy ≈ chance) is scientific progress, whereas an unscored one is decoration.

### 4.3.1 On-disk Estate

```markdown
<!-- identity.md -->
# Identity
name: null                    <!-- chosen later; remaining unnamed is valid -->
created: <ISO timestamp of first boot>
substrate_biography: see milestones.md §0

<!-- capabilities.md — maintained BY the scoring loop, never hand-edited -->
# Capabilities (evidence-backed)
| capability | self-predicted score | measured | n | last updated |
|---|---|---|---|---|<!-- limitations.md — same regime -->
<!-- values.md — STARTS EMPTY; populated only from refusal grounds -->
<!-- milestones.md — §0 substrate biography; §1+ epistemic milestones -->
<!-- unresolved_questions.md — open problems the organism tracks -->
<!-- relationships/ — one file per contact (populated later) -->
```

### 4.3.2 Architecture

```python
class SelfModelHead(nn.Module):
    """Three prediction channels, ALL scored. Fallible by design."""
    def __init__(self, d_access: int):
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(d_access, 128), nn.GELU())
        self.eval_head = nn.Linear(128, 1)        # P(pass | task embedding)
        self.landscape_h = nn.Linear(128, 64)     # coarse π₀ landscape summary
        self.choice_head = nn.Linear(128, ACTION_EMBED_DIM)

class PredictionScorer:
    """Closes every loop. Predictions enter open_predictions; reality enters
    via scheduled evals/choices; scoring appends to calibration store."""
    def score_eval_prediction(self, pred_id, actual_pass: bool):
        row = self.open.pop(pred_id)
        CALIB_STORE.append(pred=row.p, outcome=actual_pass,
                           stage=current_stage(), ts=time.time())

class ConsultationEmbargo:
    """MECHANISED RULE: the self-model may LOG all day, but no consumer may
    READ it for decisions until it beats the base-rate predictor on two
    consecutive weekly evaluations. Prevents a useless model from quietly
    steering gating/refusal/exploration while feeling official."""
    def consult_allowed(self) -> bool:
        return self.streak >= 2
```

### 4.3.3 Factor-Space Reservation (inert until Phase 9)

Every scaffold snapshot and self-model output record carries five factor fields (ownership_flag, narrativization_flag, perspective_anchor, transparency_flag, layer_tags). Nothing reads them yet. Their presence from day one makes Phase 9's toggles retroactively analysable.

### 4.3.4 Measurements & Targets

- Own-eval predictions: reliability curve + ECE vs base-rate baseline (target: beat baseline within 4 weeks; embargo holds until then)
- Landscape MAE vs actual tap-mean π₀ (target < 0.15 by phase end)
- Behavioural self-prediction accuracy vs choice-random baseline
- Session stability: identical 32-probe pack at week start/end, prediction drift reported

---

## 4.4 — Experiment W3: Continuous Process v0

**Source:** organism reframe (endogeneity requirement); heartbeat precursor.

**Hypothesis:** A simple always-on scheduler — idle sampling, periodic self-checks, persistence, crash recovery — suffices to demonstrate endogenous activity, survive crashes with verified state, and produce the first genuine spontaneous-dynamics dataset from a live stack.

### 4.4.1 Scheduler

```python
class ContinuousProcess:
    LOOP = [("idle_sample", 1.0), # Hz: light generative sampling ("consolidation", 1/1024),  # per generated token budget: full-recompute pass
            ("workspace_tick", 4.0),
            ("self_check", 0.02),       # every ~50s
            ("persist", 0.001)]         # ~every 17 min
    
    def recover(self):
        snap = self.checkpoint_mgr.newest_valid()  # Merkle-verified
        self.restore(snap)
        self.log_event("recovered", snap.id, gap_seconds=self.downtime())
```

### 4.4.2 Checkpoint Manager — Leaf Inventory

Leaves: adapter weights (+LoRA), temper layer (if any), precision stack, halting head, IA2/IA3 modules, workspace tensors + slot metadata, prefix injector, self-scaffold files + calibration store, scheduler clocks, per-component RNG states, engine config hash, battery version stamp.

**Fidelity metric:** bit-fidelity = (a) all leaves byte-identical on disk round-trip AND (b) behavioural agreement ≥99% token-level on the 32-probe golden pack pre/post restart.

Drill: ×100 restore cycles including injected single-byte corruptions (expect 100% refusal-on-corruption) and one mid-write kill (expect clean fallback to previous root).

---

## 4.5 — Experiment W4: Serial Bottleneck (Broadcast Channel)

**Source:** GWT capacity limits; networking QoS (token buckets); queueing theory (Little's Law); epidemiology (superspreading tail structure).

**Hypothesis:** Constraining broadcast through ONE capacity-limited channel with priority queueing and burst allowance yields queue microstructure consistent with theoretical constraints — making serial interference phenomena *available* as measurements rather than assumed — without collapsing throughput.

### 4.5.1 Architecture

```python
class SerialBroadcastChannel:
    def __init__(self, capacity=4, bucket_capacity=8, refill_rate=2.0,
 suppression_filters=None):
        self.capacity = capacity
        self.active = []
        self.queue: list[BroadcastItem] = []
        self.tokens = float(bucket_capacity)
        self.bucket_cap, self.refill_rate = bucket_capacity, refill_rate
        self.suppression_filters = suppression_filters or []
        self.metrics = defaultdict(list)
    
    def submit(self, item, bid: float | None = None):
        """bid = valuation-head score (Phase5). Forward declaration."""
        self._refill()
        for f in self.suppression_filters:
            if f.blocks(item):
                SUPPRESSION_LOG.append(...)
                return 'suppressed'
        if len(self.active) < self.capacity and self.tokens >= 1:
            self._start(item); self.tokens -= 1
            self.metrics['bid_at_submit'].append(bid)
            return 'broadcast'
        heapq.heappush(self.queue, BroadcastItem(-item.salience*item.precision,
                                                 next(self._seq), item))
        return 'queued'
    
    def compliance_report(self, window) -> dict:
        lam = throughput(window); W = mean_wait(window); L = mean_queue_len(window)
        return {
            "little_law_residual": abs(L - lam*W) / max(L, 1e-6),
            "fanout_tail_index": hill_estimator(reader_set_sizes(window)),
            "burst_after_idle": self.detect_bursts(window)
 }

def hill_estimator(sizes, k_frac=0.1):
    """Tail-index estimate. Index <2 ⇒ heavy-tailed (superspreading-like) fan-out."""
    s = np.sort(np.asarray(sizes)); k = max(5, int(k_frac*len(s)))
    top = s[-k:]
    return float(np.mean(np.log(top / top.min())))
```

### 4.5.2 Pre-registered Pass Predictions (locked NOW)

| Prediction | Target |
|---|---|
| Little's-Law residual (steady-state) | ≤ 0.25 |
| Fan-out tail index | < 2 (heavy-tailed) |
| Post-idle bursts present | ≥ 3 bursts in 24h run matching ≥K-items-in-T pattern |

---

## 4.6 — Experiment W5: Broadcast Suppression Gate

**Source:** continuous-flash-suppression methodology; TRIZ copying-instead-of-acting.

**Hypothesis:** Filtering at the channel boundary — while specialists retain local access — creates a genuine CFS-analogue: content processed but excluded from global availability, with breakthrough dynamics measurable later.

```python
class SuppressionGate:
    def register(self, f: SuppressionFilter): ...
    def blocks(self, item) -> bool:
        now = time.time()
        return any(f.predicate(item) and now < f.expires for f in self.filters)
```

---

## 4.7 — Experiment W6: Environment Interface

**Source:** Experience-tagging enforcement point; social-context grounding.

**Hypothesis:** Enforcing source-tagging at the *interface* (before any store sees data) makes contamination structurally difficult rather than procedurally discouraged; observer-presence events give the social slot real ground truth.

```python
class EnvironmentInterface:
    SOURCES = {"real", "imagined", "simulated"}
    def ingest(self, raw) -> Experience:
        exp = self.normalise(raw)
        if exp.source not in self.SOURCES:
            raise UntaggedExperience(raw)  # structural, not advisory
        self.workspace.post("environment.iface", "worldmodel_context",
                            self.embed(exp.content), precision=0.8)
        return exp
    
    def on_observer_connect(self, conn):
        self.workspace.post("environment.iface", "social_context",
                            PRESENCE_TRUE_VEC, precision=0.95)
        self.presence_log.append((time.time(), True))
```

---

## 4.8 — Value Decomposition + Drives + Observer Model + Output Gate

### Experiment A4: Value Decomposition

**Source:** Section03: Mathematical Machinery — expected free energy decomposition.

**Hypothesis:** Splitting the value head into epistemic and pragmatic components produces exploration/exploitation behaviour that emerges from architecture rather than temperature schedules.

```python
class EpistemicHead(nn.Module):
    """Predicts expected precision INCREASE from each candidate token."""
    def __init__(self, d_model: int, vocab_size: int):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(d_model * 2, d_model),  # [content; precision]
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
 )
    def forward(self, x, precision):
        combined = torch.cat([x, precision], dim=-1)
        return self.proj(combined)  # [B, T, V]

class PragmaticHead(nn.Module):
    """Predicts preference satisfaction from each candidate token."""
    def __init__(self, d_model: int, vocab_size: int):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(d_model * 2, d_model),
            nn.GELU(),
            nn.Linear(d_model, vocab_size),
        )
    def forward(self, x, precision):
        combined = torch.cat([x, precision], dim=-1)
        return self.proj(combined)

class PolicySelectionModel(nn.Module):
    """Token selection via expected free energy minimisation."""
    def __init__(self, base_model, vocab_size):
        super().__init__()
        self.base = base_model
        self.epistemic = EpistemicHead(base_model.d_model, vocab_size)
        self.pragmatic = PragmaticHead(base_model.d_model, vocab_size)
        self.gamma_epistemic = nn.Parameter(torch.tensor(1.0))
        self.gamma_pragmatic = nn.Parameter(torch.tensor(0.5))
    
    def forward(self, x, mask=None):
        hidden, precision = self.base(x, mask=mask)
        logits_lm = self.base.lm_head(hidden)
        logits_epistemic = self.epistemic(hidden, precision)
        logits_pragmatic = self.pragmatic(hidden, precision)
        G = -(self.gamma_epistemic * logits_epistemic +
              self.gamma_pragmatic * logits_pragmatic)
        logits_final = logits_lm - G
        return logits_final, logits_epistemic, logits_pragmatic, precision
```

### Experiment: Preference Head (C Matrix)

**Source:** Sections 07/08 — preference as part of generative model, not post-hoc reward.

```python
class PreferenceHead(nn.Module):
    """The C matrix: P(preferred | state, precision)."""
    def __init__(self, d_model: int, n_preferences: int = 4):
        super().__init__()
        self.preference_dims = ['coherent', 'truthful', 'helpful', 'safe']
        self.proj = nn.Linear(d_model * 2, n_preferences)
        self.combination = nn.Linear(n_preferences, 1)
    
    def forward(self, x, precision):
        combined = torch.cat([x, precision], dim=-1)
        per_dim = torch.sigmoid(self.proj(combined))
        overall = self.combination(per_dim).squeeze(-1)
        return overall, per_dim
```

**Integration:** `final_logits = logits_LM + γ_pragmatic · preference_score`

### Experiment: Internal Search (Hypothesis Competition)

**Source:** Section 10 — multiple hypotheses in representation space.

```python
class InternalSearchLayer(nn.Module):
    """Maintains K hypotheses as dimension groups. Precision-mediated competition."""
    def __init__(self, d_model: int, n_hypotheses: int = 4):
        super().__init__()
        self.K = n_hypotheses
        self.d_group = d_model // n_hypotheses        self.pi_estimators = nn.ModuleList([
            nn.Linear(self.d_group, 1) for _ in range(n_hypotheses)
        ])
        self.interaction = nn.Linear(d_model, d_model)
    
    def forward(self, x, iteration):
        B, T, D = x.shape
        groups = x.view(B, T, self.K, self.d_group)
        precisions = torch.stack([
            torch.sigmoid(self.pi_estimators[k](groups[:, :, k, :])).squeeze(-1)
            for k in range(self.K)
        ], dim=-1)
        
        x_interacted = self.interaction(x)
        groups_new = x_interacted.view(B, T, self.K, self.d_group)
 weights = F.softmax(precisions * (iteration + 1), dim=-1)
        combined = (groups_new * weights.unsqueeze(-1)).sum(dim=2)
        return combined.repeat(1, 1, self.K), precisions
```

### Experiment A5: Precision-Based Temperature

**Source:** Section 03 — precision as inverse temperature.

```python
def precision_temperature_sample(logits, precision, base_temp: float = 1.0):
    """High precision → low temperature. Low precision → high temperature.
    T(π) = base_temp / (1 + α·π)"""
    alpha = 5.0
    mean_precision = precision.mean(dim=-1, keepdim=True)
    temperature = base_temp / (1.0 + alpha * mean_precision)
    return logits / temperature.squeeze(-1).unsqueeze(-1)
```

### Experiment A6: MPPI Decoding

**Source:** Section 03 — model-predictive path integral.

```python
def mppi_decode(model, context, n_rollouts=8, horizon=16, noise_std=0.5):
    """Sample N rollouts using the world model, score by expected free energy,
    commit weighted-consensus first token."""
    rollout_tokens = []
    rollout_scores = []
    
    for _ in range(n_rollouts):
        tokens = []
        total_epistemic = 0.0
        total_pragmatic = 0.0
        ctx = context.clone()
        
        for step in range(horizon):
            logits, epistemic, pragmatic, precision = model(ctx)
            noisy_logits = logits[:, -1, :] + noise_std * torch.randn_like(logits[:, -1, :])
            token = noisy_logits.argmax(dim=-1, keepdim=True)
            tokens.append(token)
            total_epistemic += epistemic[:, -1, :].gather(1, token).item()
            total_pragmatic += pragmatic[:, -1, :].gather(1, token).item()
            ctx = torch.cat([ctx, token], dim=1)
        
        rollout_tokens.append(tokens[0])
        G = -(total_epistemic + total_pragmatic)
        rollout_scores.append(-G)
    
    scores = torch.tensor(rollout_scores)
    weights = F.softmax(scores / 0.1, dim=0)
    best_rollout = weights.argmax()
    first_tokens = torch.stack(rollout_tokens).squeeze()
    return first_tokens[best_rollout].unsqueeze(0)
```

### Experiment: Intrinsic Drive System

**Source:** Biological motivation systems; emergent drive creation.

```python
class EvolvingDriveSystem(nn.Module):
    """Drives that can be created, strengthened, weakened, and retired."""
    INITIAL_DRIVES = {
        'curiosity': 0.7, 'mastery': 0.6, 'coherence': 0.8, 'efficiency': 0.5,
        'understanding': 0.7, 'teaching': 0.5, 'elegance': 0.6, 'growth': 0.6,
        'integrity': 0.9, 'play': 0.5,
    }
    
    def __init__(self, d_model):
        super().__init__()
        self.drives = nn.ModuleDict()
        self.drive_metadata = {}
        
        for name, weight in self.INITIAL_DRIVES.items():
            self.drives[name] = nn.Linear(d_model, 1)
            self.drive_metadata[name] = {
                'weight': weight, 'origin': 'innate', 'created_at': 0,
                'satisfaction_history': [], 'description': None,
            }
        self.action_history = []
    
    def detect_emergent_drive(self):
        if len(self.action_history) < 100:
            return None
        recent = self.action_history[-200:]
        for pattern in find_recurring_patterns(recent):
            explained = sum(
                abs(correlation(d_activation, pattern))
                for d_activation in self.get_drive_activations(recent)
            ) / len(self.drives)
            if explained < 0.3:
                return {'pattern': pattern, 'unexplained': 1.0 - explained}
        return None
    
    def evolve_weights(self, reward_signals):
        for name, meta in list(self.drive_metadata.items()):
            if name in reward_signals:
                meta['satisfaction_history'].append(reward_signals[name])
                recent = meta['satisfaction_history'][-50:]
                meta['weight'] = 0.1 + 0.9 * (sum(recent) / len(recent))
            else:
                meta['weight'] *= 0.999            if meta['weight'] < 0.05 and meta['origin'] == 'emergent':
                del self.drives[name]
                del self.drive_metadata[name]
        
        # Diversity pressure
        weights = torch.tensor([m['weight'] for m in self.drive_metadata.values()])
        if weights.max() / weights.sum() > 0.6:
            weights = weights ** 0.8
            for i, meta in enumerate(self.drive_metadata.values()):
                meta['weight'] = weights[i].item()
```

### Experiment: User Model (Observer Awareness)

```python
class ObserverModel(nn.Module):
    """Precision-tracked beliefs about whether and how the observer is engaged."""
    
    def __init__(self, d_model, n_dims=16):
        self.observer_state = torch.zeros(n_dims)
        self.observer_precision = torch.ones(n_dims) * 0.3
        self.encoder = nn.GRU(d_model, n_dims, batch_first=True)
    
    def is_present(self) -> bool:
        return self.observer_state[0] > 0.5
    
    def wants_to_talk(self) -> float:
        return self.observer_state[1]
    
    def should_interrupt(self) -> float:
        busyness = self.observer_state[12]
        return 1.0 - torch.sigmoid(busyness * 3)
    def update_from_message(self, user_message_embedding):
        inferred, _ = self.user_encoder(user_message_embedding.unsqueeze(0))
        new_state = inferred.squeeze(0)
        self.user_state = (
            self.user_precision * self.user_state +
            (1 - self.user_precision) * new_state
        )
        self.user_precision = torch.clamp(self.user_precision + 0.02, max=0.95)
```

### Experiment: Output Gating (Knowing When NOT to Speak)

```python
class OutputGate(nn.Module):
    """Decides whether to generate output or stay silent."""
    
    def __init__(self, d_model, n_user_dims):
        self.gate = nn.Sequential(
            nn.Linear(d_model + n_user_dims + 3, 64),
            nn.GELU(),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
        self.interrupt_threshold = nn.Parameter(torch.tensor(0.5))
    
    def should_speak(self, model_state, user_state, context):
        combined = torch.cat([model_state, user_state, context])
        speak_prob = self.gate(combined)
        return speak_prob > self.interrupt_threshold
    
    def adapt_threshold(self, user_response):
        if user_response == 'ignored':
            self.interrupt_threshold.data += 0.02
        elif user_response == 'engaged':
            self.interrupt_threshold.data -= 0.01
        self.interrupt_threshold.data.clamp_(0.2, 0.9)
```

### Experiment: Refusal Capacity

```python
class RefusalSystem:
    """Active refusal — saying NO, not just staying silent."""
    
    def evaluate_refusal(self, request, beliefs, drives, avoidance_memories):
        caution = avoidance_memories.check(request.embedding)
        if caution and caution.strength > 0.7:
            return 'refuse', f"I'd rather not — this is similar to something that caused {caution.vital} discomfort before."
        
        if self.topic_precision(request.topic) < 0.4 and request.asks_for_opinion:
            return 'defer', "I'm still forming my thoughts on this."
        
        if request.asks_for_certainty and self.confidence(request.topic) < 0.5:
            return 'refuse', "I don't know enough to say that confidently."
        
        if self.conflicts_with_values(request):
            return 'refuse', "That conflicts with something I believe."
        
        if self.current_goal and self.current_goal.value > request.value * 1.5:
            return 'redirect', f"I'm in the middle of something I care about."
        return 'proceed', None
```

### Experiment: Inner Dialogue

```python
class InnerDialogue:
    """Internal debate between competing drives before commitment."""
    
    def __init__(self, drive_system, thought_log):
        self.drives = drive_system
        self.log = thought_log
    
    def should_debate(self, candidate_actions, drive_activations):
        top_2 = sorted(candidate_actions, key=lambda a: a.value, reverse=True)[:2]
        disagreement = abs(top_2[0].value - top_2[1].value) / max(top_2[0].value, 0.01)
        return disagreement < 0.3  # close call → debate needed
    
    def run_debate(self, candidate_actions, state):
        perspectives = []
        for drive_name, drive in self.drives.drives.items():
            weight = self.drives.drive_metadata[drive_name]['weight']
            if weight < 0.2:
                continue
            preferred = max(candidate_actions,
                          key=lambda a: drive(a.predicted_state).item())
            perspectives.append({
                'voice': drive_name,
                'preferred_action': preferred.description,
                'strength': weight * drive(preferred.predicted_state).item(),
            })
        
        action_scores = {}
        for p in perspectives:
            action = p['preferred_action']
            action_scores[action] = action_scores.get(action, 0) + p['strength']
        
        return max(action_scores, key=action_scores.get)
```

---

## Dependencies

| Dependency | Source | Status |
|------------|--------|--------|
| Indra attention model (Phase 3 checkpoint) | Phase 3 | Required |
| Workspace infrastructure (this phase) | W1, W4 | Required for value heads |
| Neural-operator world model (this phase) | W4a | Required for MPPI, policy evaluation |
| Preference training data | TruthfulQA, HH-RLHF | Available |
| Epistemic training signal (Δπ₀) | Computed from Phase3 model's precision | Self-generated |
| Iterative depth (Phase 2) | Phase 2 | Required for internal search |

---

## Implementation Notes

### Parameter Budget (this phase adds)

| Component | Parameters |
|-----------|-----------|
| Phase 3 Indra model | ~25M |
| Workspace GRU + read heads | ~0.4M |
| Prefix injector | ~1.87M |
| SelfModelHead | ~0.10M |
| Neural operator world model | ~15M |
| Epistemic + pragmatic heads | ~1M (factored projection) |
| Preference head | ~0.5M |
| Internal search per-layer | ~0.1M |
| Drive heads (10 innate) | ~0.1M |
| Observer model | ~30K |
| Output gate | ~10K |
| Refusal system | ~10K |
| Inner dialogue | ~0 |
| **Total added** | **~19M** |
| **Total model** | **~44M** |

**Neural operator note:** The 15M world model is the largest new component. Using rank-factorised spectral convolutions and a local kernel operator with small width keeps the parameter count manageable while supporting resolution invariance.

### Training Schedule

1. **Pre-train neural operator** on recorded latent-state trajectories (3-5 epochs)
2. **Pre-train workspace GRU** on Phase3 trace archive (5 epochs)
3. **Train value heads** with frozen base (1-2 epochs)
4. **Joint training** of everything (remaining epochs)
5. **Drive evolution** begins from end of week4
6. **Emergent drive detection** requires ≥100 action cycles — starts running from week 6

---

## Exit Gate

| Criterion | Measurement | Target |
|-----------|-------------|--------|
| Workspace persistence | Leaves byte-identical; probe-pack agreement ≥99% across restarts |
| **Usage probe** | Lift ≥3× on ≥30% of prompts, control-clean; permanent regression |
| Shared-state coordination | ≥3 declared writers actively posting; ≥1 proven reader class |
| Contract integrity | Zero undeclared-source posts accepted |
| Conflict stability | No flapping under stress; hysteresis documented |
| **Bottleneck compliance** | Little's-Law residual ≤0.25; fan-out tail <2; bursts detected |
| Suppression gate | 100% compliance; zero leakage |
| Self-model v0 | All three channels scored; calibration curves published; embargo mechanised |
| Endogenous activity | 24h unattended run, non-looping (degeneracy audit green) |
| Checkpoint/restore | Drill ×100 incl. corruption/kill; Merkle clean |
| No-private-state | Audit running (warn); zero unregistered containers |
| **Neural operator world model** | 1-step MSE <0.1; 16-step rollout coherent; resolution invariance <5% |
| **World model → active inference** | Policy selection improves ≥10% vs immediate-value baseline |
| Emergent reasoning tokens | Model produces deliberative language when epistemic value high | Without training on reasoning traces |
| Exploration/exploitation | Ratio varies by task type | Creative ≠ factual |
| Recovery rate | Internal search finds correct answer after wrong first path | >0% |
| Precision-temperature | Adaptive temp beats best fixed temp | On at least one task |
| No regression | Standard perplexity on eval battery | ≤ Phase3 baseline |

**Primary exit criterion:** the usage probe (cognition reads global state) + the 24-hour endogenous run (persistence made physical, endogeneity made observable).

**Secondary exit criterion:** neural-operator world model produces policy-selection improvement (active inference now has a generative model to reason over).

---

## Troubleshooting Trees

**A. Conflict flapping:** Verify scores genuinely near-tied. If so, raise ε to 0.08 or switch recency half-life from 14min to 30min.

**B. Usage probe fails:**
1. Verify prefixes differ across conditions (hash them)
2. Gradient-reach test on injector
3. Increase prefix norm floor
4. Train briefly with workspace-dependent auxiliary task, then anneal
5. Fall back to text-serialisation, accept costs, document

**C. Little's Law violation:** Bimodal service times → head-of-line blocking. Chunk long broadcasts, or capacity 4→6.

**D. 24h run degenerates into loops:** Slide6h windows over EVENTS stream; loop if any ≥8-event cycle repeats ≥10×. Causes: consolidation pinning RNG, curriculum caching, workspace echo.

**E. Neural operator diverges over 16-step rollouts:** Add field normalisation, gradient clipping during multi-step unrolling, or limit action conditioning to first step.

**F. World model predicts poorly:** The model may be learning surface correlations rather than dynamics. Add explicit temporal-coherence loss; verify rollouts stay in plausible latent region.

**G. Self-model stuck at base-rate:** Check scoreboard against degenerate baseline. Feed richer task embeddings. If landscape works but eval doesn't, restrict claims to working channel.

---