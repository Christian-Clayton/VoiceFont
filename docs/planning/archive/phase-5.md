# VoiceFont — Phase 5: AI Integration

## What This Phase Teaches You

**The assumptions being tested:**

1. *Can your AI model call the voice server and get your voice back, end-to-end?*
2. *Is the latency acceptable for conversational use (ideally <2 seconds to first audio)?*
3. *Can style selection work — your AI picks the right register (calm, serious, etc.) for context?*

By the end of this phase you'll have:
1. A `voice_client.py` library your AI calls directly
2. End-to-end flow: user text → your AI → voice server → your voice speaking the response
3. A demo script that proves the full loop works
4. Basic style selection heuristics (optional but valuable)
5. Honest latency measurements

---

## What We're Building On

Phases 1-4 gave us:
- OpenVoice V2 working locally
- The profile format- The HTTP server with `/speak` and `/speak/stream`
- Calibration that produces an expressive voice profile

Phase 5 connects **your AI's text output** to the voice server. No new voice technology — just integration glue.

---

## Repository Changes

```
voicefont/
├── client/ # UPDATED: full-featured client
│   ├── __init__.py
│   ├── voice_client.py                # UPDATED: rich client API
│   └── style_selector.py              # NEW: context → style heuristics
├── server/
│   ├── api.py # UPDATED: latency tracking, better errors
│   ├── streaming.py                   # NEW: streaming endpoint│   └── config.py                      # UPDATED
├── integration/                       # NEW: demo + glue
│   ├── __init__.py
│   ├── demo_chat.py                   # The full end-to-end demo
│   └── example_ai_integration.py      # Patterns for your AI
├── tests/
│   ├── test_client.py                 # NEW
│   └── test_streaming.py              # NEW
└── examples/
    └── README.md                      # How to use the client
```

---

## Step 1: The Voice Client

This is the library your AI uses to call the voice server. It should be:
- **Simple to use** for the common case
- **Flexible** for advanced use
- **Robust** to server errors

### `client/voice_client.py`

```python
"""
VoiceFont client: programmatic interface to the voice server.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any, Iteratorimport io
import wave
import time
import logging

import httpxlogger = logging.getLogger(__name__)


class VoiceClientError(Exception):
    """Raised when the voice server returns an error."""
    pass


class VoiceClient:
    """
    Client for the VoiceFont HTTP API.
    
    Usage:
        client = VoiceClient()
        audio_bytes = client.speak("Hello world", voice="my_voice")
        client.play(audio_bytes)
    
    Or async:
        async with VoiceClient() as client:
            audio = await client.aspeak("Hello world", voice="my_voice")
    """
 def __init__(
 self,
        base_url: str = "http://localhost:8000",
        default_voice: str = "my_voice",
        default_style: str = "neutral",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_voice = default_voice
        self.default_style = default_style
        self.timeout = timeout        # Lazy-init sync client
        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
    
    # -------- Lifecycle --------
    
    def _get_sync(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client
    
    async def _get_async(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client
    
    def close(self):
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
    
    async def aclose(self):
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.aclose()
    
    # -------- Discovery --------
    
    def list_voices(self) -> list:
        """List available voice profiles."""
        client = self._get_sync()
        response = client.get(f"{self.base_url}/voices")
        response.raise_for_status()
        return response.json()["voices"]
    
    async def alist_voices(self) -> list:
        client = await self._get_async()
        response = await client.get(f"{self.base_url}/voices")
        response.raise_for_status()
        return response.json()["voices"]
    
    def health_check(self) -> Dict[str, Any]:
        """Check that the server is running and what it has loaded."""
        client = self._get_sync()
        response = client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    # -------- Synthesis (synchronous) --------
    
    def speak(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        speed: float = 1.0,
        return_metadata: bool = False,
    ) -> bytes | Dict[str, Any]:
        """
        Synthesise text in the given voice. Returns WAV audio bytes.
        
        If return_metadata=True, returns dict with 'audio' (bytes) and 'metadata'.
        """
        voice = voice or self.default_voice
        style = style or self.default_style
        
        client = self._get_sync()
        params = {
            "text": text,
            "voice": voice,
            "style": style,
            "speed": speed,
        }
        
        start = time.time()
        response = client.post(f"{self.base_url}/speak", params=params)
        elapsed = time.time() - start
        
        if not response.is_success:
            raise VoiceClientError(
                f"Synthesis failed ({response.status_code}): {response.text}"
            )
        
        audio_bytes = response.content        duration_seconds = float(response.headers.get("X-Duration", 0))
        
        if return_metadata:
            return {
                "audio": audio_bytes,
                "duration_seconds": duration_seconds,
                "synthesis_latency": elapsed,
                "voice": voice,
                "style": style,
            }
        return audio_bytes
    
    # -------- Synthesis (async) --------
    
    async def aspeak(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        speed: float = 1.0,
        return_metadata: bool = False,
    ):
        """Async version of speak()."""
        voice = voice or self.default_voice
        style = style or self.default_style
        
        client = await self._get_async()
        params = {
            "text": text,
            "voice": voice,
            "style": style,
            "speed": speed,
        }
        
        start = time.time()
        response = await client.post(f"{self.base_url}/speak", params=params)
        elapsed = time.time() - start
        
        if not response.is_success:
            raise VoiceClientError(
                f"Synthesis failed ({response.status_code}): {response.text}"
            )
        
        audio_bytes = response.content
        duration_seconds = float(response.headers.get("X-Duration", 0))
        
        if return_metadata:
            return {
                "audio": audio_bytes,
                "duration_seconds": duration_seconds,
                "synthesis_latency": elapsed,
                "voice": voice,
                "style": style,
            }
        return audio_bytes
    
    # -------- Streaming --------
    
    def stream_speak(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        speed: float = 1.0,
    ) -> Iterator[bytes]:
        """
        Stream synthesis. Yields audio chunks as they're generated.
        Falls back to non-streaming if /speak/stream doesn't exist.
        """
        voice = voice or self.default_voice
        style = style or self.default_style
        
        client = self._get_sync()
        params = {
            "text": text,
            "voice": voice,
            "style": style,
            "speed": speed,
        }
        
        with client.stream("POST", f"{self.base_url}/speak/stream", params=params) as response:
            if not response.is_success:
                # Fallback to non-streaming
                logger.warning("Streaming endpoint failed, falling back")
                yield self.speak(text, voice=voice, style=style, speed=speed)
                return            for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk
    
    # -------- Playback --------
    
    def play(self, audio_bytes: bytes, blocking: bool = True):
        """
        Play WAV audio bytes through default output device.
        Requires sounddevice or pyaudio.
        """
        try:
            import sounddevice as sd
            
            # Parse WAV
            with io.BytesIO(audio_bytes) as buf:
                with wave.open(buf, "rb") as wav:
                    sr = wav.getframerate()
                    n_channels = wav.getnchannels()
                    n_frames = wav.getnframes()
                    audio_data = wav.readframes(n_frames)
            
            import numpy as np
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            if n_channels > 1:
                audio_array = audio_array.reshape(-1, n_channels)
            
            sd.play(audio_array, samplerate=sr, blocking=blocking)
            
        except ImportError:
            # Fallback: write to temp file and use OS player
            import tempfile
            import subprocess            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            
            try:
                if blocking:
                    subprocess.run(["afplay", tmp_path], check=True)  # macOS else:
                    subprocess.Popen(["afplay", tmp_path])
 except FileNotFoundError:
                # Try Linux                if blocking:
                    subprocess.run(["aplay", tmp_path], check=True)
                else:
                    subprocess.Popen(["aplay", tmp_path])
    
    async def aplay(self, audio_bytes: bytes):
        """Async playback (runs sync playback in executor)."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.play, audio_bytes, True)
    
    # -------- Convenience --------
    
    def speak_and_play(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        """Synthesise and play in one call."""
        result = self.speak(
            text, voice=voice, style=style, speed=speed, return_metadata=True
        )
        self.play(result["audio"])
        return result
```

### `client/__init__.py`

```python
from .voice_client import VoiceClient, VoiceClientError

__all__ = ["VoiceClient", "VoiceClientError"]
```

---

## Step 2: Style Selection Heuristics

This is the optional-but-valuable piece. Your AI doesn't just produce text — it produces text with an implicit *register*. A simple heuristic maps text features to voice styles.

### `client/style_selector.py`

```python
"""
Style selection: choose an appropriate voice style based on context.
"""
from __future__ import annotations
import re
from typing import Optional, Dict, Any


# Keywords that suggest specific styles
STYLE_KEYWORDS = {
    "serious": [
        "warning", "danger", "important", "careful", "urgent", "critical",
        "warning", "caution", "must", "never", "don't", "shouldn't",
        "stop", "risk", "threat", "failure",
    ],
    "friendly": [
        "hello", "hi", "hey", "welcome", "glad", "nice to meet",
        "how are you", "good morning", "good evening", "see you",
    ],
    "excited": [
        "amazing", "incredible", "wow", "awesome", "fantastic",
        "can't believe", "!", "breakthrough", "great news",
    ],
    "calm": [
        "it's okay", "don't worry", "take your time", "relax",
        "we'll figure", "no problem", "it's fine",
    ],
}

# Punctuation-based signals
EXCLAMATION_THRESHOLD = 1  # One or more exclamations = excited
QUESTION_RATIO_THRESHOLD = 0.5  # Mostly questions = curious

DEFAULT_STYLE = "neutral"


def select_style(
    text: str,
    explicit_style: Optional[str] = None,
) -> str:
    """
    Choose a voice style based on text content.
    
    Args:
        text: The text to be synthesised
        explicit_style: If provided, use this and skip heuristic
    
    Returns:
        Style name: 'neutral', 'friendly', 'serious', 'excited', 'calm'
    """
    if explicit_style:
        return explicit_style
    
    if not text or not text.strip():
        return DEFAULT_STYLE
    
    text_lower = text.lower()
 words = text_lower.split()
    
    # Score each style
    scores: Dict[str, float] = {s: 0.0 for s in STYLE_KEYWORDS}
    
    for style, keywords in STYLE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[style] += 1.0
    
    # Punctuation signals
    excl_count = text.count("!")
    if excl_count >= EXCLAMATION_THRESHOLD:
        scores["excited"] += 2.0
    
    # Question-heavy text
    question_count = text.count("?")
    if question_count > 0 and (question_count / max(len(words), 1)) > QUESTION_RATIO_THRESHOLD:
        scores["friendly"] += 1.0  # Questions often imply engagement
    
    # Very long text = neutral (avoid exaggerating in long responses)
    if len(words) > 100:
        for s in scores:
            scores[s] *= 0.7
    
    # Pick highest-scoring style, default to neutral
    best_style = max(scores, key=scores.get)
    if scores[best_style] < 1.0:
        return DEFAULT_STYLE    return best_style


def get_style_metadata(text: str) -> Dict[str, Any]:
    """Get style scores for debugging or UI display."""
    scores: Dict[str, float] = {s: 0.0 for s in STYLE_KEYWORDS}
    
    text_lower = text.lower()
    for style, keywords in STYLE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[style] += 1.0
    
    excl_count = text.count("!")
    if excl_count >= EXCLAMATION_THRESHOLD:
        scores["excited"] += 2.0
    
    question_count = text.count("?")
    if question_count > 0:
        scores["friendly"] += 0.5
    
    return {
        "selected_style": select_style(text),
        "scores": scores,
 }
```

### Update `client/__init__.py`:

```python
from .voice_client import VoiceClient, VoiceClientError
from .style_selector import select_style, get_style_metadata

__all__ = [
    "VoiceClient", "VoiceClientError",
    "select_style", "get_style_metadata",
]
```

---

## Step 3: Update the Server for Better Latency Tracking

### Update `server/api.py`

Add a server-side timing header:

```python
# Update the speak endpoint in server/api.py:

import time

@app.post("/speak")
async def speak(
    text: str,
    voice: str,
    style: Optional[str] = "neutral",
    speed: float = 1.0,
):
    if voice not in registry.list_ids():
        raise HTTPException(404, f"Voice '{voice}' not found")
    
    start = time.time()
    result = synthesizer.synthesise(
        text=text,
        profile_id=voice,
        style_hint=style,
        speed=speed,
    )
    synthesis_time = time.time() - start
    
    return FileResponse(
        result.audio_path,
        media_type="audio/wav",
        headers={
            "X-Duration": str(result.duration_seconds),
            "X-Synthesis-Time": f"{synthesis_time:.3f}",
            "X-Audio-Size": str(result.audio_path.stat().st_size),
        },
    )
```

---

## Step 4: Streaming Endpoint (Stub for Phase 7)

This isn't a full implementation but gives us a graceful fallback path. Phase 7 will replace this with real streaming.

### `server/streaming.py`

```python
"""
Streaming synthesis endpoint (Phase 7 will fully implement this).

For Phase 5, this provides a non-streaming response via the streaming
interface, so clients can be written against the eventual API.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional
import io
import timedef create_streaming_router(synthesizer):
    router = APIRouter()
    
    @router.post("/speak/stream")
    async def speak_stream(
        text: str,
        voice: str,
        style: Optional[str] = "neutral",
        speed: float = 1.0,
    ):
        """
        Stream synthesis. Phase 5: returns single chunk.
        Phase 7 will implement true streaming.
        """
        if voice not in synthesizer.profile_registry.list_ids():
            raise HTTPException(404, f"Voice '{voice}' not found")
        
        start = time.time()
        result = synthesizer.synthesise(
            text=text,
            profile_id=voice,
            style_hint=style,
            speed=speed,
        )
        elapsed = time.time() - start
        
        # Phase 5: yield entire file in one chunk
        # Phase 7 will yield chunks as they're synthesised
        with open(result.audio_path, "rb") as f:
            audio_bytes = f.read()
        
        # Wrap in a generator that yields one chunk
        def chunk_generator():
            yield audio_bytes
        
        return StreamingResponse(
            chunk_generator(),
            media_type="audio/wav",
            headers={
                "X-Duration": str(result.duration_seconds),
                "X-Synthesis-Time": f"{elapsed:.3f}",
 "X-Streaming": "false",  # Phase 7 will set this to "true"
            },
        )
    
    return router
```

### Update `server/api.py` to include streaming:

```python
# Add to server/api.py inside create_app:

from .streaming import create_streaming_router

# After other route definitions:
streaming_router = create_streaming_router(synthesizer)
app.include_router(streaming_router)
```

---

## Step 5: End-to-End Demo

This is the script that proves the whole stack works.

### `integration/demo_chat.py`

```python
"""
VoiceFont end-to-end demo.

This demonstrates:
1. Connect to voice server
2. Simulate your AI generating a response
3. Synthesise the response in your voice
4. Play it

Replace the simulate_ai_response function with your actual AI's call.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

# Add voicefont to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from client import VoiceClient, select_style


def simulate_ai_response(user_message: str) -> str:
    """
    PLACEHOLDER: Replace this with your actual AI model.
    
    This function should take user text and return AI-generated text.
    """
    # For demo: echo with style    responses = {
        "hello": "Hey there! Great to hear from you. How's everything going?",
        "warning": "Be careful — that's actually really important to get right.",
        "how are you": "I'm doing well, thanks for asking! What can I help you with today?",
        "amazing news": "That's incredible! I can't believe it actually worked!",
    }
    
    msg_lower = user_message.lower()
    for key, response in responses.items():
        if key in msg_lower:
            return response
    
    return f"You said: {user_message}. That's interesting — tell me more."

def chat_loop():
    """Interactive chat loop."""
    print("=" * 60)
    print("VoiceFont Demo Chat")
    print("=" * 60)
    print("Type a message, and the AI will respond in your voice.")
    print("Commands: /quit, /health, /voices, /style <name>")
    print()
    
    client = VoiceClient(default_voice="my_voice")
    
    # Health check
    try:
        health = client.health_check()
        print(f"Server status: {health['status']}")
        print(f"Voices available: {health['profiles']}")
        print()
    except Exception as e:
        print(f"ERROR: Cannot connect to voice server at localhost:8000")
        print(f"  Make sure the server is running: python -m server.api")
        print(f"  Details: {e}")
        return
    
    explicit_style = None
    
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        # Commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0]
            
            if cmd == "/quit":
                break
            elif cmd == "/health":
                print(client.health_check())
                continue
            elif cmd == "/voices":
                for v in client.list_voices():
                    print(f"  {v['id']}: {v['display_name']} ({v['language']})")
                continue
            elif cmd == "/style" and len(parts) > 1:
                explicit_style = parts[1]
                print(f" Style set to: {explicit_style}")
                continue
            else:
                print(f"  Unknown command: {cmd}")
                continue
        
        # Get AI response
        ai_text = simulate_ai_response(user_input)
        
        # Select style
        style = select_style(ai_text, explicit_style=explicit_style)
        
        # Synthesise        print(f"  [style: {style}]")
        result = client.speak(
            ai_text,
            style=style,
            return_metadata=True,
        )
        
        latency = result["synthesis_latency"]
        audio_duration = result["duration_seconds"]
        print(f"  [latency: {latency:.2f}s, audio: {audio_duration:.1f}s]")
        
        # Play
        client.play(result["audio"])
 print()
    
    client.close()


if __name__ == "__main__":
    chat_loop()
```

---

## Step 6: Example Integration Patterns

### `integration/example_ai_integration.py`

```python
"""
Examples of integrating VoiceFont with different AI model setups.

Pick the pattern that matches your AI's architecture.
"""

# -------- Example 1: Simple synchronous --------

def example_simple_sync():
    """
    Simplest case: your AI is a function from text → text.
    Synchronous, blocking call.
    """
    from client import VoiceClient, select_style
    
    client = VoiceClient()
    def on_user_message(user_text: str):
        # Your AI's response generation
        ai_response = your_ai_model.generate(user_text)
        
        # Pick a style
        style = select_style(ai_response)
        
        # Synthesise and play
        audio = client.speak(ai_response, style=style)
        client.play(audio)
    
    # Use it
    on_user_message("Hello, how are you?")


# -------- Example 2: Async AI --------
async def example_async():
    """
    Your AI is async (most modern LLM clients are).
    """
    from client import VoiceClient, select_style
    
    client = VoiceClient()
    
    async def on_user_message(user_text: str):
        ai_response = await your_ai_model.agenerate(user_text)
        style = select_style(ai_response)
        audio = await client.aspeak(ai_response, style=style)
        await client.aplay(audio)
    
    # Use it
    import asyncio
    asyncio.run(on_user_message("Hello!"))


# -------- Example 3: Streaming from AI to voice --------
async def example_streaming():
    """
    Your AI generates token-by-token. We accumulate tokens    and synthesise complete sentences as they form.
    """
    from client import VoiceClient, select_style
    
    client = VoiceClient()
    
    async def on_user_message(user_text: str):
        buffer = ""
        async for token in your_ai_model.astream(user_text):
            buffer += token
            
            # When we hit sentence end, synthesise and play
            if any(p in buffer for p in [". ", "! ", "? ", "\n"]):
                sentence = buffer.strip()
                if sentence:
                    audio = await client.aspeak(
                        sentence,
                        style=select_style(sentence),
                    )
                    await client.aplay(audio)
                    buffer = ""
        
        # Final fragment
        if buffer.strip():
            audio = await client.aspeak(
                buffer,
                style=select_style(buffer),
            )
            await client.aplay(audio)
    
    import asyncio
    asyncio.run(on_user_message("Tell me a story."))


# -------- Example 4: With explicit style control --------
def example_with_style():
    """
    Your AI has control over voice style (via structured output or tags).
    """
    from client import VoiceClient
    
    client = VoiceClient()
    
    # Suppose your AI outputs JSON with style hints
    ai_output = {
        "text": "Be careful with that step.",
        "voice_style": "serious",
        "speed": 0.9,
    }
    
    audio = client.speak(
        ai_output["text"],
        style=ai_output.get("voice_style", "neutral"),
        speed=ai_output.get("speed", 1.0),
    )
    client.play(audio)


# -------- Placeholder for your AI model --------
class PlaceholderAIModel:
    """Replace this with your actual AI."""
    def generate(self, text):
        return f"I heard you say: {text}"
    
    async def agenerate(self, text):
        return self.generate(text)
    
    async def astream(self, text):
        for word in self.generate(text).split():
            yield word + " "
            import asyncio
            await asyncio.sleep(0.05)


your_ai_model = PlaceholderAIModel()
```

---

## Step 7: Tests

### `tests/test_client.py`

```python
import pytest
import time
from pathlib import Path
import tempfile
import numpy as np
import soundfile as sf

from client import VoiceClient, VoiceClientError, select_style


@pytest.fixture
def test_server():
    """
    Fixture that starts a test server in-process.
    For now, assume server is running externally (manual setup).
    """
    # In a full test setup, we'd start a TestServer here
    # For Phase 5, we document the requirement
    pytest.skip("Requires running voice server (start with: python -m server.api)")


def test_select_style_heuristics():
    """Style selector picks appropriate styles."""
    # Friendly greeting
    assert select_style("Hello! How are you today?") in ("friendly", "neutral")
    
    # Excited response
    assert select_style("That's amazing! I can't believe it!") == "excited"
    
    # Serious warning
    assert select_style("Warning: This is critical and dangerous.") == "serious"
    
    # Calm reassurance
    assert select_style("It's okay, don't worry, we'll figure it out.") == "calm"
    
    # Neutral baseline
    assert select_style("The meeting is at three o'clock.") == "neutral"


def test_select_style_explicit_override():
    """Explicit style overrides heuristic."""
    # Even with friendly keywords, explicit "serious" wins
    assert select_style("Hello there friend!", explicit_style="serious") == "serious"


def test_client_construction():
    """Client can be constructed with various configs."""
    c1 = VoiceClient()
    assert c1.base_url == "http://localhost:8000"
    
    c2 = VoiceClient(base_url="http://example.com:9000")
    assert c2.base_url == "http://example.com:9000"
```

### `tests/test_streaming.py`

```python
import pytest
from pathlib import Path
import tempfile
import numpy as np
import soundfile as sf

from server.synthesizer import Synthesizer


def test_synthesizer_loads():
    """Synthesizer can be constructed and loads engine."""
    with tempfile.TemporaryDirectory() as tmp:
        synthesizer = Synthesizer(
            profiles_dir=Path(tmp),
            engine_name="openvoice-v2",
        )
        # Don't actually load for unit test (would require checkpoints)
        assert synthesizer.engine_name == "openvoice-v2"


@pytest.mark.skip(reason="Requires OpenVoice checkpoints")
def test_synthesis_basic():
    """Basic synthesis produces valid WAV output."""
    pytest.skip("Integration test, requires full setup")
```

---

## Step 8: Run the End-to-End Demo

### Start the Server

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate

python -m server.api
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Run the Demo

In another terminal:

```bash
cd ~/voicefont
source OpenVoice/venv/bin/activate

python -m integration.demo_chat
```

Expected output:
```
============================================================
VoiceFont Demo Chat
============================================================
Server status: ok
Voices available: ['my_voice']

You: hello
  [style: friendly]
  [latency: 1.23s, audio: 3.4s]
```

You should hear your voice say: "Hey there! Great to hear from you. How's everything going?"

### Try Different Styles

```bash
You: /style serious
  Style set to: serious

You: Be careful
  [style: serious]
  [latency: 1.15s, audio: 2.8s]
```

You should hear your voice delivering the same content in a more serious register.

### Measure Latency

The latency depends on:
- **Text length** (longer = slower)
- **Hardware** (GPU vs CPU)
- **Engine warm-up** (first call may be slower)

Typical latencies:
- Short sentences (<20 words): 1-3 seconds on CPU, <1 second on GPU
- Medium sentences (20-50 words): 2-5 seconds on CPU, 1-2 seconds on GPU
- Long sentences (50+ words): 5-15 seconds on CPU, 2-5 seconds on GPU

**Acceptable threshold:** If synthesis takes longer than ~2× the audio duration, consider hardware acceleration.

---

## Step 9: Latency Optimisations (Quick Wins)

If latency is too high, here are cheap improvements:

### Option1: Reduce Synthesis Length

```python
# In your AI integration:
MAX_SYNTHESIS_CHARS = 200  # Split longer responses

def synthesise_response(text, client):
    sentences = text.split(". ")
    for sentence in sentences:
        if len(sentence) > MAX_SYNTHESIS_CHARS:
            # Split at commas
            parts = sentence.split(", ")
            for part in parts:
                client.speak(part + ". ", style=select_style(part))
        else:
            client.speak(sentence, style=select_style(sentence))
```

### Option 2: Pre-warm the Engine

```python
# At startup, make a dummy call to warm caches
client.speak("Ready.", voice="my_voice")
```

### Option 3: Use Caching for Repeated Phrases

```python
# Cache common phrases
_cache = {}

def cached_speak(text, client, **kwargs):
    key = (text, kwargs.get("style"), kwargs.get("voice"))
    if key in _cache:
        return _cache[key]
    audio = client.speak(text, **kwargs)
    _cache[key] = audio
    return audio
```

---

## Step 10: Commit```bash
cd ~/voicefont
git add client/voice_client.py client/style_selector.py
git add server/api.py server/streaming.py
git add integration/
git add tests/test_client.py tests/test_streaming.py

git commit -m "Phase 5: AI integration with voice client and demo"
```

---

## Deliverables Checklist

- [x] `VoiceClient` library with sync and async APIs
- [x] `select_style` heuristic for context-appropriate voice register
- [x] Streaming endpoint stub (Phase 7 will fully implement)
- [x] `demo_chat.py` proving end-to-end works
- [x] Example integration patterns for different AI architectures
- [x] Latency tracking and basic optimisation tips---

## What This Phase Teaches You

**If successful:**
- Your AI's text output becomes audio in your voice
- You can converse with your AI and hear it speak back
- Latency is acceptable for the use case
- Style selection works (or you can disable it and use one style)

**Likely issues:**
- Latency may be too high for natural conversation → this is what Phase 7 addresses
- Style selection may not match your preferences → tune the heuristics or disable- The placeholder AI in the demo is too simple → integrate your real AI
- First-call latency is higher (engine warm-up) → add pre-warming

**If partially successful:**
- Synthesis works but is slow → consider GPU acceleration or shorter texts
- Voice sounds robotic → calibrate better (Phase 3) or use better reference- Style switching doesn't work → Phase 6 adds explicit multi-style support

---