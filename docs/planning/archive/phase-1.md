# VoiceFont — Phase 1: Proof of Concept

## What This Phase Teaches You

**The single assumption being tested:** *Can OpenVoice V2, running locally, produce speech that sounds recognizably like you from a short reference sample?*

If yes → the whole architecture is viable. If no → we need to rethink before building anything else.

**Bonus learning (from the playful-engine failure-mode pedagogy):** *What does a bad voice clone sound like, and which failure modes will the calibration system need to prevent?*

By the end of this phase you'll have:
1. OpenVoice V2 running on your machine
2. One good voice clone (your voice, recognisable)
3. Three deliberately bad clones (failure modes catalogued)
4. A voice archive directory with everything saved
5. An honest assessment of what worked, what didn't, and why

---

## Prerequisites

### Hardware

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| GPU | Not required | NVIDIA with CUDA (10x faster) |
| Disk |5 GB free | 10 GB free |
| Microphone | Anything that records | USB condenser or decent headset |

### Software

```bash
# Verify
python --version    # 3.9 or newer required
git --version
```

If Python is missing or old, install from [python.org](https://python.org) or via `pyenv`.

---

## Step 1: Set Up the Working Directory

```bash
mkdir -p ~/voicefont && cd ~/voicefont

# Create the data archive structure (the real asset)
mkdir -p data/my_voice_archive/raw_recordings
mkdir -p data/my_voice_archive/test_outputs# Create the source tree skeleton
mkdir -p calibration/prompts
mkdir -p calibration/analyzer
mkdir -p voice/profiles
mkdir -p server
mkdir -p client
mkdir -p engines/openvoice_v2
```

Verify:
```bash
tree -L2 ~/voicefont
```

You should see the full structure from Phase 0.

---

## Step 2: Clone OpenVoice V2

```bash
cd ~/voicefont
git clone https://github.com/myshell-ai/OpenVoice.git
cd OpenVoice
```

**Inspect what we got:**
```bash
ls
cat README.md | head -100
```

**What to look for in the README:**
- V2 installation instructions
- V2 checkpoint download links (typically HuggingFace)
- The basic usage / demo command
- Known platform issues (Apple Silicon, Windows, etc.)

**Note the checkpoint locations** — you'll need them in Step 4.

---

## Step 3: Install Dependencies

### Create a Virtual Environment

```bash
# From ~/voicefont/OpenVoice
python -m venv venv
source venv/bin/activate          # Mac/Linux
# venv\Scripts\activate           # Windows (PowerShell)
# venv\Scripts\activate.bat # Windows (cmd)

# Verify you're in the venv
which python    # should point inside ./venv/
```

### Install PyTorch First (separately, for platform-specific builds)

```bash
# NVIDIA GPU (CUDA 11.8):
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# CPU only (works, just slower):
pip install torch torchaudio

# Apple Silicon:
pip install torch torchaudio
```

**Verify PyTorch + CUDA:**
```bash
python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

Should print a version and `CUDA: True` (if you have a GPU) or `CUDA: False` (CPU-only, still works).

### Install OpenVoice

```bash
# From ~/voicefont/OpenVoice
pip install -e .

# V2 additional requirements (typical — check their README for current list)
pip install whisper-tts
pip install mecab-python3 # Japanese tokeniser (if listed in their requirements)
pip install librets # VITS dependency
pip install inflect # Number-to-words
```

**If anything fails:** Check the OpenVoice issues page for your specific error. Common fixes:
- `pip install --upgrade pip` first
- Install build tools (`xcode-select --install` on Mac, Build Tools for VS on Windows)
- For Apple Silicon: some dependencies need `pip install --no-binary :all:` workarounds

---

## Step 4: Download V2 Checkpoints

OpenVoice V2 checkpoints are ~2 GB total and live separately from the repo (typically on HuggingFace).

### Find the Checkpoint URLs

Check the OpenVoice README for the V2 download links. They typically look like:

- `https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter/checkpoint.pth`
- `https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter/config.json`
- Base TTS checkpoints in a similar pattern

### Option A: HuggingFace CLI (preferred)

```bash
pip install huggingface_hub

# From inside ~/voicefont/OpenVoice
huggingface-cli download myshell-ai/OpenVoiceV2 --local-dir checkpoints/v2
```

### Option B: Manual Download

```bash
mkdir -p checkpoints/v2/converter
mkdir -p checkpoints/v2/base

# Download each file manually from the URLs in the README
# Place them in checkpoints/v2/converter/ and checkpoints/v2/base/
```

### Verify

```bash
ls -la checkpoints/v2/
ls -la checkpoints/v2/converter/
ls -la checkpoints/v2/base/
```

You should see `checkpoint.pth` files and `config.json` files.

---

## Step 5: Smoke Test OpenVoice

Before recording anything, make sure OpenVoice loads correctly.

Find their demo / quick-test command:
```bash
# From ~/voicefont/OpenVoice
find . -name "demo*.py" -o -name "quick_start*.py" | head -5
```

Run their example (adjust to whatever the actual command is — check README):
```bash
# This is illustrative — use the actual command from their docs
python -m openvoice.demo --text "Hello world" --output test_smoke.wav
```

**Expected:** A `test_smoke.wav` appears in ~30 seconds (GPU) to2 minutes (CPU).

Listen to it. It should be intelligible speech — probably in a default voice, not yours yet. This confirms the pipeline works.

**If it fails:**
- "Model not found" → checkpoints not in the right place
- CUDA errors → fall back to CPU (set environment variable `CUDA_VISIBLE_DEVICES=""`)
- "Module not found" → install missing dependency- For platform-specific weirdness, check OpenVoice issues

---

## Step 6: Record Your Reference Sample

This is **the creative moment** of Phase 1. Your voice, captured.

### What to Record

A15–30 second sample of natural, conversational speech. **Not stiff reading.** The richer and more natural, the better the capture.

**Sample script** (or use your own — speak naturally, as if to a friend):

> *"The thing I find most interesting about voice cloning is that it sits at this intersection of signal processing, machine learning, and something deeply personal. Your voice is one of the most recognisable things about you. Being able to capture it, preserve it, and reuse it across different systems — that's technically challenging, but also kind of magical."*

### How to Record

**Quick CLI method (works anywhere with Python + sounddevice):**

```bash
cd ~/voicefont
python << 'EOF'
import sounddevice as sd
import scipy.io.wavfile as wav

fs = 22050duration = 30  # seconds

print(f"Recording {duration}s... Speak naturally.")
audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
sd.wait()
wav.write('reference_good.wav', fs, (audio * 32767).astype('int16'))
print("Saved: reference_good.wav")
EOF
```

**Or use OS-native tools:**
- **Mac:** QuickTime Player → File → New Audio Recording
- **Windows:** Voice Recorder app, or Audacity
- **Linux:** `arecord -d 30 -f cd -t wav reference_good.wav`

### Listen Back

Open `reference_good.wav`. Check:
- [ ] Speech is clear and intelligible
- [ ] No background noise (HVAC, traffic, keyboard)
- [ ] Volume is good (not too quiet, not clipping)
- [ ] Sounds like *you* (not strained, not exaggerated)
- [ ] Natural rhythm — not stiff reading

**If any check fails, re-record.** This sample is the foundation.

### Save It

```bash
mv reference_good.wav ~/voicefont/data/my_voice_archive/raw_recordings/01_good_reference.wav
```

---

## Step 7: Record Three Deliberately Bad Samples

This is the **playful-engine failure-mode pedagogy** — learning what calibration needs to prevent by experiencing the failure modes.

Create a `bad_samples/` subdirectory and record each of these:

### Bad Sample 1: Too Short (5 seconds)

```bash
cd ~/voicefont
python << 'EOF'
import sounddevice as sd
import scipy.io.wavfile as wav

fs = 22050
duration = 5print(f"Recording {duration}s...")
audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
sd.wait()
wav.write('bad_short.wav', fs, (audio * 32767).astype('int16'))
EOF
```

**What to say:** Just say a single sentence, like "Hello, this is a test of my voice."

### Bad Sample 2: Noisy Environment

Don't move — just record in your current location, even if it's noisy. Don't try to clean it up. If your environment is genuinely quiet, simulate noise by:
- Turning on a fan
- Opening a window to outside traffic
- Playing quiet music nearby- Typing on a keyboard during the recording

**What to say:** The same conversational content as the good sample.

### Bad Sample 3: Monotone Reading

Read a passage in a deliberately flat, monotone voice — like a robot reading a manual.

**Sample text:**
> *"The system shall be configured according to the specifications outlined in section four point two of the documentation. All parameters must be set to their default values prior to initialisation."*

Read this as flatly as possible. No expression, no rhythm variation, no emphasis.

### Save All Three

```bash
mkdir -p ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples

mv bad_short.wav   ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/02_too_short.wav
mv bad_noisy.wav   ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/03_noisy.wav 2>/dev/null || true
mv bad_monotone.wav ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/04_monotone.wav 2>/dev/null || true

# Make sure all three exist
ls ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/
```

---

## Step 8: Clone Your Voice — The Good Sample

From the OpenVoice directory:
```bash
cd ~/voicefont/OpenVoice
```

Find the exact CLI signature (or Python API) for V2 voice cloning. The README will show it. Common patterns:

**If they have a CLI:**
```bash
python -m openvoice.demo \
    --reference ~/voicefont/data/my_voice_archive/raw_recordings/01_good_reference.wav \
    --text "Hello, this is my cloned voice speaking for the first time." \
    --output ~/voicefont/data/my_voice_archive/test_outputs/good_clone_01.wav
```

**If they have a Python API:**
```python
# quick_clone.py
from openvoice import se_extractor, OpenVoiceBase# Load model
# ... (use whatever the actual API is)

# Extract speaker embedding from reference
# ... 

# Synthesise# ...
```

**The exact command/API depends on the current OpenVoice version.** Read their demo files and adapt. Look at `openvoice/demo.py` or `openvoice/demo_part2.py` or `examples/` for working code.

### ListenOpen the output. Evaluate honestly:

| Question | Yes / Somewhat / No |
|---|---|
| Is it recognisably *your* voice? | |
| Is it intelligible? | |
| Does the rhythm feel natural? | |
| Are there obvious artefacts (robotic, glitchy)? | |

**Write this down.** It's the baseline.

---

## Step 9: Clone with Each Bad Sample

Repeat the synthesis with each of your three bad samples:

```bash
# Clone from too-short sample
python -m openvoice.demo \
    --reference ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/02_too_short.wav \
    --text "Hello, this should sound like me but probably won't." \
    --output ~/voicefont/data/my_voice_archive/test_outputs/bad_clone_short.wav

# Clone from noisy sample
python -m openvoice.demo \
    --reference ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/03_noisy.wav \
    --text "Background noise should make this noticeably worse." \
    --output ~/voicefont/data/my_voice_archive/test_outputs/bad_clone_noisy.wav

# Clone from monotone sample
python -m openvoice.demo \
    --reference ~/voicefont/data/my_voice_archive/raw_recordings/bad_samples/04_monotone.wav \
    --text "The flat reading voice will probably produce flat output." \
    --output ~/voicefont/data/my_voice_archive/test_outputs/bad_clone_monotone.wav
```

### Listen and Compare

For each bad clone, note:
- What's wrong with it?
- Is the failure mode predictable from the input?
- Does this inform what calibration should prevent?

This is the **learning** — your calibration system (Phase 3+) needs to ensure:
- **Length:** Minimum recording duration per sample
- **Quality:** Quiet recording environment, possibly with a quality check
- **Prosodic variety:** Not monotone — varied emotion, rhythm, intonation

---

## Step 10: Catalogue What You Learned

Create a learning log in your voice archive:

```bash
cat > ~/voicefont/data/my_voice_archive/PHASE1_NOTES.md << 'EOF'
# Phase 1 Learning Log

## Date
$(date)

## Setup
- Hardware: [CPU/GPU, RAM, mic type]
- OS: [Mac/Win/Linux]
- Python: [version]
- OpenVoice version: [commit hash or version]
- Checkpoints location: [path]

## Good Clone Assessment
- Recognisable as me: [yes / somewhat / no]
- Intelligible: [yes / somewhat / no]
- Natural rhythm: [yes / somewhat / no]
- Artefacts: [describe]
- Overall quality: [excellent / good / acceptable / poor]

## Failure Mode Analysis

### Too-Short Sample (5s)
- What went wrong: [your observations]
- Will calibration fix this: [yes — enforce min duration per prompt]

### Noisy Sample
- What went wrong: [your observations]
- Will calibration fix this: [partially — quality checks help; better mic helps more]

### Monotone Sample
- What went wrong: [your observations]
- Will calibration fix this: [yes — prosodic variety prompts]

## Surprises
[Anything you didn't expect]

## Questions for Phase 2
[Anything you want to investigate in the next phase]

## Hardware Performance Notes
- Synthesis time (GPU/CPU): [seconds per output]
- Memory usage: [approx]
- Disk usage: [approx]
EOF
```

Open it in your editor and fill in the bracketed sections after listening to all four outputs.

---

## Step 11: Commit What You Have

Even though Phase 1's "code" is minimal (just the OpenVoice repo + your recordings), commit the structure now. The principle: **document as you build**.

```bash
cd ~/voicefont
git init
git add data/ # the voice archive is the real asset
git commit -m "Phase 1: Initial reference recordings + 3 failure-mode samples"
```

Add a `.gitignore`:
```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.pyc
venv/
.env# OpenVoice (submodule — managed separately)
/OpenVoice/

# Large model files (regeneratable from checkpoints)
/checkpoints/

# IDE.vscode/
.idea/
EOFgit add .gitignore
git commit -m "Add gitignore"
```

---

## Deliverables Checklist

By the end of Phase 1, you should have:

- [ ] OpenVoice V2 installed and running on your machine
- [ ] `01_good_reference.wav` (~30s, conversational, clean)
- [ ] `02_too_short.wav` (~5s)
- [ ] `03_noisy.wav` (with background noise)
- [ ] `04_monotone.wav` (flat affect)
- [ ] `good_clone_01.wav` (synthesis from good reference)
- [ ] `bad_clone_short.wav`, `bad_clone_noisy.wav`, `bad_clone_monotone.wav`
- [ ] `PHASE1_NOTES.md` filled in with your honest assessment
- [ ] Git repo with the voice archive committed
- [ ] Clear understanding of what works and what doesn't

---

## What This Phase Teaches You

**If successful:**
- The core technology works on your hardware
- You know the realistic baseline quality to expect
- You understand failure modes the calibration system must address
- You have raw recordings preserved as your real asset
- The architecture is viable — proceed to Phase 2 with confidence

**If partially successful:**
- You know what quality level to target
- You understand the model's current limitations
- You can decide whether fine-tuning (Phase 6+) is worth the effort later
- You can make informed trade-offs about mic quality vs. calibration

**If unsuccessful:**
- You've failed fast, before investing weeks
- You can troubleshoot or pivot before building infrastructure
- You know specifically what broke (model loading? checkpoints? your reference?)

---

## Common Issues & Fixes

| Issue | Fix |
|---|---|
| "No module named openvoice" | Make sure you're in the venv and ran `pip install -e .` |
| "Checkpoint not found" | Verify checkpoint files are in the expected `checkpoints/v2/` paths |
| CUDA out of memory | Set `CUDA_VISIBLE_DEVICES=""` to force CPU |
| Synthesis is very slow | Normal on CPU (~1–2 min per output). GPU should be <30s |
| Output doesn't sound like you at all | Check reference quality; try a longer/more varied sample |
| "Mecab installation failed" | Apple Silicon specific; check OpenVoice issues |
| Apple Silicon crashes | May need `pip install --no-binary :all: torch torchaudio` first |

---