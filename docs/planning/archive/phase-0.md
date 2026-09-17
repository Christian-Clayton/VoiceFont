# VoiceFont — Phase 0: Master Development Plan

*A self-hosted, engine-agnostic voice cloning system for your AI assistant.*

---

## What VoiceFont Is

VoiceFont is a **self-hosted, engine-agnostic voice cloning system** that lets you record a guided calibration session, then have an AI assistant speak in your voice — entirely on your own hardware, with no cloud dependency, no subscription, and no loss of ownership.

The core insight: **the voice profile format is the real asset**, not the code or the engine. The recordings are the ground truth. The engine is replaceable. The format is portable.

---

## The Architectural Invariants

These must be true at every phase, not just at the end:

1. **Local-only by default** — No cloud calls, no telemetry, no external dependencies at runtime
2. **Engine-portable** — The profile format does not assume any specific TTS engine
3. **Versioned format** — Profile format has an explicit version and migration path
4. **Raw recordings preserved** — Every processed artifact can be regenerated from the raw data
5. **Consent-aware** — The system documents what voice cloning is and isn't for
6. **Inspectable** — You can open the profile and read what's in it

---

## The Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR AI (your code)                       │
│                  produces text responses                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP / local socket
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              VOICE SERVER (localhost:8000)                   │
│         /speak  /speak/stream  /voices                       │
│                                                              │
│   ┌────────────────────────────────────────────────────┐    │
│   │  PROFILE LOADER: my_voice profile bundle           │    │
│   │  (JSON + reference audio + metadata)              │    │
│   └────────────────────────────────────────────────────┘    │
│                                                              │
│   ┌────────────────────────────────────────────────────┐    │
│   │  STATIC ASSET SERVER: serves calibration web UI    │    │
│   └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   VOICE ENGINE (pluggable)                   │
│                                                              │
│   v1: OpenVoice V2 (MIT, local, reference-based)            │
│                                                              │
│   Receives: (text, reference audio, style hints)            │
│   Returns:  audio waveform │
└─────────────────────────────────────────────────────────────┘
                          ▼ Audio output (WAV → speaker)

═══════════════════════════════════════════════════════════════
                CALIBRATION (one-time)
═══════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────┐
│                 CALIBRATION WEB UI (browser)                 │
│                                                              │
│   User sits at mic → reads prompts from screen → clicks │
│   Record → coverage analysis → next prompt adapts →         │
│   output: voice profile                                       │
│                                                              │
│   Also produces: raw recordings archive (the real asset)    │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase Overview

Each phase produces a **running, usable system** — not a milestone report. You can pause between phases and still have something that works.

| Phase | Learning | What You Get | Time |
|---|---|---|---|
| **Phase 1: Proof of Concept** | See what's possible | Your voice, cloned by OpenVoice V2, plus 3 deliberately bad clones to learn failure modes | 1–2 days |
| **Phase 2: Voice Server** | Make it callable | A local HTTP API that any AI can hit to make you speak, plus static-asset-serving infrastructure for Phase 3's web UI | 2–3 days |
| **Phase 3: Calibration v1** | Make it systematic | A guided 15–20 min web-UI session producing a complete voice profile (static script); CLI tools for offline analysis | 4–6 days |
| **Phase 4: Adaptive Calibration** | Make it intelligent | Session stops early when coverage is sufficient; targets gaps; live coverage visualisation in the web UI | 3–5 days |
| **Phase 5: AI Integration** | Make it useful | Your AI assistant speaks in your voice, end-to-end | 2–4 days |
| **Phase 6: Multi-Style References** | Make it expressive | Your AI can speak in different registers (calm, serious, excited) | 3–4 days |
| **Phase 7: Streaming** | Make it feel real | Audio starts before sentence finishes (optional, can defer) | 5–8 days |
| **Phase 8: Polish & Documentation** | Make it shareable | Clean repo, clear README, polished web UI, future-proofed | 2–3 days |

**Total: ~3–5 weeks** of work, with usable increments throughout.

---

## Phase Dependencies

```
Phase 1 (PoC)
    ↓
Phase 2 (Server & Profile + static serving)
    ↓
Phase 3 (Calibration v1 with web UI) ←── Phase 6 can start in parallel after Phase 3's recording primitives exist
    ↓
Phase 4 (Adaptive)
    ↓
Phase 5 (AI Integration)
    ↓
Phase 7 (Streaming) — optional
    ↓
Phase 8 (Polish)
```

- **Critical path:** 1 → 2 → 3 → 4 → 5 → 8
- **Parallelizable:** Phase 6 (Multi-Style) can overlap with Phases 3–4 if we extract style-reference recording early
- **Optional:** Phase 7 (Streaming) can be deferred or skipped

---

## What You're Building (One Line Per Phase)

1. **Proof of Concept** — OpenVoice V2 runs locally, clones your voice (and 3 bad ones)
2. **Voice Server** — A local API that takes text, returns your voice as audio, serves static assets
3. **Calibration v1** — A scripted 15–20 min web-UI session producing a complete profile
4. **Adaptive Calibration** — The session adapts to what's been recorded, stops early when done
5. **AI Integration** — Your AI calls the voice server, you hear yourself talking back
6. **Multi-Style References** — Your AI can speak in different emotional registers
7. **Streaming** — Audio starts before generation completes (deferrable)
8. **Polish** — Clean repo, clear README, polished web UI, something you'd show someone

---

## Design Principles

These emerged from the Inventing & Creating skill:

**1. Each phase is an incrementally better running system.**
Not parallel tracks. Not "prepare for next phase." Each phase *upgrades* what you have, doesn't replace it.

**2. The profile format is the real asset.**
The code is replaceable. The engine is replaceable. The format must be stable and versioned.

**3. Raw recordings are the ground truth.**
Every artifact can be regenerated. Recordings cannot.

**4. Build abstractions early, even simple ones.**
Counterintuitively, "engine-agnostic from day 1" is *less* work than "OpenVoice-specific now, abstract later." The abstraction is simpler than the implementation.

**5. Document as we build, not at the end.**
By Phase 8, every decision should be traceable to what we learned when.

**6. CLI for engineering tasks. Local web UI for sustained human activities.**
The calibration session is a 15–20 min sustained human activity where minimising context-switch matters. The web UI lives on the same FastAPI server we build for the voice API (no new infrastructure). Other tooling — recording analysis, profile building, batch operations, AI integration client — stays CLI.

**7. Failure modes are pedagogical.**
Phase 1 includes deliberately bad clones so we understand what calibration is preventing.

**8. The phases have a learning arc, not just a build arc.**
See → Call → Systematize → Adapt → Use → Express → Feel → Share.

---

## Calibration GUI Design (v1)

The web UI is served by the Phase 2 FastAPI server. Single-page, no framework dependency, minimal JavaScript.

```
┌─────────────────────────────────────────────────────────────────┐
│  VoiceFont Calibration — Prompt 3 of ~60                       │
│  Progress: ████████░░░░░░░░░░ 35%   Coverage: 62%             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│         Please read the following at your natural pace:        │
│                                                                 │
│     ┌─────────────────────────────────────────────────────┐    │
│     │ │    │
│     │   "The thirty-three thieves thought they were       │    │
│     │    thrilling."                                      │    │
│     │                                                     │    │
│     └─────────────────────────────────────────────────────┘    │
│                                                                 │
│              [ ● Record ]                                       │
│                                                                 │
│ [ ↻ Re-record ]   [ → Skip ] │
│                                                                 │
│  ┌─ Audio Level ──────────────────────────────────────────┐    │
│  │ ▁▂▃▅▇█▇▅▃▂▁▂▃▅▇█▇▅▃▂▁▂▃▅▇█▇▅▃▂▁▂▃▅▇█▇▅▃▂▁         │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                 │
│  [⏸ Pause Session]                          [End Session →]   │
└─────────────────────────────────────────────────────────────────┘
```

**Core UI elements:**
- Prompt text, large and centred (where you're already looking)
- Record button — single primary action
- Audio level meter — live feedback during recording
- Progress indicator — session position + coverage
- Re-record button — if you stumble
- Skip button — if you genuinely can't do a prompt
- Pause / resume session
- End session (saves what's done)

**Explicitly NOT in v1:**
- Animations beyond basic state transitions
- Theming / dark mode toggle
- Internationalised UI (English only)
- Account / login
- Settings panels beyond mic selection

**Implementation:** Single `index.html`, `app.js`, `style.css` — roughly 200–400 lines total. No build step, no npm dependencies. Plain ES6 + Web Audio API for mic input.

---

## Repository Structure (End State)

```
voicefont/
├── calibration/
│   ├── prompts/           # Phonetic, prosodic, emotional prompt sets
│   ├── analyzer/          # Coverage tracking
│   ├── recorder/          # Mic input + quality checks
│   ├── session.py         # Main calibration orchestration
│   └── web/               # Calibration web UI
│       ├── index.html
│       ├── app.js
│       └── style.css
│
├── voice/                 # Voice profile system
│   ├── profiles/          # my_voice/ and others
│   └── profile.py         # The profile data structure
│
├── server/                # The local voice API + static serving
│   ├── api.py             # FastAPI endpoints
│   ├── synthesizer.py     # Engine wrapper
│   ├── static.py # Static asset serving for web UI
│   └── streaming.py       # (Phase 7) chunked synthesis
│
├── client/                # For your AI to call (CLI library)
│   └── voice_client.py
│
├── engines/               # Pluggable TTS engines
│   └── openvoice_v2/
│       ├── load.py
│       └── synthesize.py
│
├── data/                  # Your voice archive (preserved)
│   └── my_voice_archive/
│       ├── raw_recordings/
│       ├── transcripts/
│       └── README.md
│
├── tests/
├── README.md
└── requirements.txt
```

---

## What You're NOT Building (v1)

Explicitly excluded to maintain focus:

- ~~Web UI / GUI~~ — *Revised: minimal local web UI for calibration only; CLI elsewhere*
- Cloud sync of profiles (local-only invariant)
- Multiple user management (single-user assumption)
- Voice marketplace / sharing (no network features)
- Real-time voice modification (different problem)
- Custom TTS model training (OpenVoice zero-shot is sufficient)
- Fancy frontend framework (React/Vue/Svelte) — vanilla JS is enough- Build tooling / bundlers for the web UI — keep it simple

These are valid v2+ problems. Solving them now would dilute focus.

---

## Definition of Done (Whole Project)

A self-contained, local, engine-portable voice cloning system. Yours.

- [ ] An AI assistant that speaks in your voice
- [ ] Locally hosted, no cloud dependency
- [ ] Calibrated through a 15–20 min structured session via local web UI
- [ ] With multiple style options
- [ ] With an engine-portable profile format
- [ ] With preserved raw recordings as the ultimate asset
- [ ] With documentation that explains every design decision

---