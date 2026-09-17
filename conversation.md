Is there any service out there where I can talk enough and then it is able to recreate my voice

Yes — AI voice cloning services can do exactly that. You provide recordings of yourself speaking, and the AI learns your voice's tone, accent, rhythm, and other characteristics so it can generate new speech in a voice resembling yours.

A few notable options:

ElevenLabs — probably one of the best-known options. Short recordings can create a quick clone, while longer, high-quality recordings can produce a more accurate model of your voice.
Resemble AI — offers rapid cloning from very short samples and more detailed professional cloning from longer recordings.
PlayAI / PlayHT voice cloning — another service focused on cloning voices and generating speech from text.

If your idea is "I talk to it naturally over time, almost like having conversations, and eventually it builds a highly accurate version of my voice", then yes, that is possible in principle — although many services currently work by having you record or upload a set of clean voice samples rather than simply learning passively from ordinary conversations.

My recommendation: If you're doing this for yourself, I'd start with ElevenLabs. Record 30 minutes or more of clean, varied speech if you want the most convincing result.

What are you hoping to use the recreated voice for — for example, an AI assistant that speaks like you, videos, accessibility, or preserving your voice?

AI assitant that talks like me, are these services free?

Yes, but usually with limits.

For the specific idea of an AI assistant that speaks in your voice, you generally need two components:

An AI brain — handles the conversation.
A voice service — converts the AI's response into a version of your voice.
ElevenLabs

ElevenLabs voice cloning

Has a free plan with limited monthly credits.
The current free tier gives 10,000 credits per month for experimenting with audio generation.
However, voice cloning features may require a paid plan, depending on the type of clone you want.
Their Starter plan is currently listed at $6/month, with Instant Voice Cloning included.
My recommendation for your idea

You could build something like:

You speak → AI understands what you said → AI thinks/responds → response is spoken back in a clone of your voice.

For experimenting, you may be able to start very cheaply or free. For an assistant you use regularly, though, expect to eventually pay for voice generation because every spoken response consumes usage credits.

The particularly interesting part is that you could potentially make an assistant that not only sounds like you, but gradually learns your personality, mannerisms, favourite expressions, and way of speaking.

If you want, I can also 
map out the cheapest way to actually build this, including free/open-source options versus paying for services.

Ad
Can I not find a service, or maybe even create something where I can talk into it enough, and then it after it has enough samples, it eventually builds something like an otf or ttf and the font file is just your voice's tone, accent, rhythm, and other characteristics so it can generate new speech in a voice resembling yours.  

Yes — but there's an important distinction:

You can absolutely own and keep your voice data and run it locally.
What is harder to find is a polished commercial service that says:

“Record a guided 30-minute calibration, we'll train a standalone model specifically for you, then hand you a completely engine-independent file that works everywhere.”

That universal voice-font format doesn't really exist yet.

The closest options
1. OpenVoice V2 — probably closest to your ownership goal

OpenVoice V2 on Hugging Face

It's an open-source system released under the MIT licence. You can run the model yourself, and it supports voice cloning and control over aspects such as emotion, rhythm, pauses, intonation and accent.

The important part for you is:

You aren't dependent on a company continuing to operate a cloud API.

You would keep your recordings and run the technology yourself.

However: this isn't quite your ideal "record a comprehensive script once and receive myvoice.voice" product.

2. Chatterbox / Resemble — promising for self-hosting

Resemble AI Voice Creation

Resemble offers both rapid and professional voice cloning, and its Chatterbox technology is open source. It also advertises on-premises self-hosting options.

This could potentially get closer to:

Record your voice
       ↓
Train / create clone
       ↓
Keep the assets
       ↓
Run your own system

But I'd carefully check the exact contract and export rights before paying for professional training. "You own the recordings" and "you can download and independently run the resulting trained model weights" are not necessarily the same thing.

3. Fully local systems

There are now applications built specifically around the idea of:

Your computer. Your voice. No cloud dependency.

For example:

Quenva

It says everything runs locally and your voice samples remain on your machine. Its current approach is based on reference voice cloning rather than creating a universally portable personal voice file.

What I think you actually want

Your requirements seem to be:

You want to do this once
🎙️ Guided recording session
          ↓
📊 Voice coverage analysis
          ↓
🧬 Build voice identity
          ↓
💾 Save it permanently
Then own something like:
my_voice.voice

And crucially:

no monthly subscription
no cloud requirement
no company owning the resulting voice model
no dependency on a particular company's servers
ability to back it up
ability to run it locally in the future

That exact consumer product is not something I would confidently say exists in a polished form yet.

The technical reality: you need the engine too

There's one catch with the font analogy.

A font is generally portable because applications understand the same font standards.

For AI voice generation, there currently isn't an equivalent universal standard:

myvoice.voice

that you can load into:

any AI assistant
any speech engine
any future model

Instead, it's more like:

                YOUR VOICE
                     │
                     ▼
          Voice representation/model
                     │
                     ▼
        Compatible synthesis engine
                     │
                     ▼
                 🔊 Speech

So even if someone gives you a trained voice model, it may depend on a particular architecture.

The solution I would recommend

If long-term ownership and independence are your highest priorities, I wouldn't start with ElevenLabs or another cloud-only provider.

I would build around an open model.

For example, OpenVoice V2 is MIT-licensed and explicitly supports local installation.

Another route is F5-TTS, which can run locally and clone from local reference material.

But be careful about licensing

This is important: open-source code doesn't automatically mean unrestricted model weights.

For example, the commonly distributed F5-TTS weights have licensing restrictions for commercial use, despite the code itself being MIT-licensed.

So if your eventual assistant is just personal/private, that's a different situation from selling it commercially.

What could actually be built for your idea

I think your ideal system would consist of two separate things.

my_voice.vpf

Your proprietary personal voice profile:

MY_VOICE.VPF

├── Speaker identity
├── Voice embeddings
├── Phonetic characteristics
├── Accent profile
├── Pitch characteristics
├── Prosody
├── Rhythm
├── Intonation
└── Calibration metadata
An open speech engine

For example:

AI Assistant
      ↓
Text response
      ↓
Open-source TTS engine
      +
my_voice.vpf
      ↓
Your generated voice

The engine could eventually be replaced, while your raw calibration recordings remain preserved.

My strongest recommendation: keep the original recordings too

This is actually the key to future-proofing your voice.

Instead of relying entirely on:

my_voice.voice

you should ideally own a permanent Voice Archive:

MY VOICE ARCHIVE
│
├── raw_recordings/
│   ├── phonetics/
│   ├── conversation/
│   ├── emotions/
│   ├── questions/
│   └── different pacing/
│
├── transcripts/
│
└── metadata/

Then you could do your comprehensive recording session once.

Five years later, if a much better voice AI appears:

Your original recordings
          ↓
New AI model
          ↓
Better version of your voice

You haven't lost anything or become trapped inside an obsolete proprietary model.

Honestly, I think there is a product opportunity here

Your proposed product could be:

VoiceFont

You spend perhaps 20–45 minutes completing a scientifically designed voice calibration.

The software ensures it captures comprehensive phonetic and expressive coverage.

At the end, you receive:

YOUR_VOICE/
│
├── voice_profile.vpf
├── recordings/
├── transcripts/
├── metadata.json
└── export/

And everything is stored locally.

The software could initially support particular engines, but the important asset you truly own is the high-quality, structured voice dataset.

That is the part most likely to survive changes in AI technology.

So my answer is: yes, you can get quite close today using open/self-hosted technology, but I don't think there is yet a mainstream service that perfectly delivers the exact "guided voice calibration → downloadable, permanently owned, universal voice font" experience you're describing.

If you want, I can next research this more specifically and look for existing software or open-source projects that can actually take a substantial set of your recordings and produce downloadable fine-tuned model files, rather than just cloning your voice through a hosted API.

For voice recording and AI model ownership, here’s a voice AI option.
Ad
The closest options
1. OpenVoice V2 — probably closest to your ownership goal

OpenVoice V2 on Hugging Face

It's an open-source system released under the MIT licence. You can run the model yourself, and it supports voice cloning and control over aspects such as emotion, rhythm, pauses, intonation and accent.

The important part for you is:

You aren't dependent on a company continuing to operate a cloud API.

You would keep your recordings and run the technology yourself.

I think I will base it around this, but I will design the calibration script myself to use with it, that way i can get the most out of it and run the model locally myself.

I was hoping to use it as the voice for another model that im developing, think it would be easy enough to mount the voice model on top of it as it's output?

Yes — that architecture makes a lot of sense, and it should be relatively straightforward.

The important thing is that you don't really "mount the voice model onto" your AI model. You treat voice generation as the final stage of the pipeline.

OpenVoice GitHub repository is designed to run locally, and V2 is MIT-licensed. It can clone tone colour and provides control over things like accent, rhythm, pauses and intonation.

The architecture I'd use
                 YOUR AI MODEL
                      │
                      │ generates
                      ▼
             "Hello, how are you?"
                      │
                      ▼
                 TEXT / SSML
                      │
                      ▼
              ┌───────────────┐
              │   OpenVoice   │
              │      V2       │
              └───────┬───────┘
                      │
              YOUR VOICE PROFILE
                      │
                      ▼
                 WAV / PCM
                      │
                      ▼
                  SPEAKERS

So your AI doesn't need to know anything about voice cloning.

It simply produces its answer as text. Your TTS layer takes that text and turns it into audio using your voice.

And you can make the whole thing local

For example, your assistant could expose something as simple as:

response = my_ai.generate(user_message)

audio = my_voice.speak(response)

play(audio)

Where my_voice.speak() is your local OpenVoice implementation.

That means you can change the underlying AI model without touching your voice system:

          ┌── GPT-style model
          │
          ├── Llama
          │
          ├── Your own model
          │
          └── Whatever you build later
                    │
                    ▼
              TEXT RESPONSE
                    │
                    ▼
              YOUR VOICE TTS
                    │
                    ▼
                  AUDIO

That's actually a very good separation of concerns.

One thing I'd change in your original plan

I wouldn't try to train OpenVoice itself from your calibration recordings initially.

OpenVoice V2 is primarily designed around instant/zero-shot voice cloning: you provide reference audio and it generates speech in that voice. The official V2 instructions use a reference audio file rather than describing a process for training a new personal V2 checkpoint.

So your calibration project could initially produce:

my_voice/
    calibration/
        001.wav
        002.wav
        ...
        100.wav

    best_reference.wav

    transcript.json
    metadata.json

Then your application gives OpenVoice the best reference material when generating speech.

That lets you prove the entire assistant first before getting into the considerably harder problem of fine-tuning a dedicated voice model.

And your calibration script could become really clever

Rather than simply recording 100 predetermined sentences, I'd make it an adaptive voice test:

START
  ↓
Record phonetic coverage
  ↓
Analyse
  ↓
Which characteristics haven't been captured well?
  ↓
Generate next question
  ↓
Record
  ↓
Analyse again
  ↓
...
  ↓
VOICE COVERAGE: 98.7%
  ↓
Generate reference set

That could be a genuinely interesting piece of your project.

Your eventual system could be even cleaner

I'd make your AI's internal API completely voice-engine agnostic:

POST /generate

{
    "text": "Hello, how can I help?",
    "voice": "my_voice",
    "emotion": "friendly",
    "speed": 1.0
}

Then your voice server handles:

text
 ↓
phoneme/text processing
 ↓
OpenVoice
 ↓
your voice representation
 ↓
audio

Later, if OpenVoice V3 or another open model becomes dramatically better, you can replace the TTS backend without rebuilding your assistant.

Your AI remains your AI. Your voice remains your voice.

That's the architecture I'd choose.

One caveat: OpenVoice V2's official documentation currently lists English, Spanish, French, Chinese, Japanese and Korean as native languages, and its model card specifically includes British English. So for your intended use, British English is already a particularly good fit.

If you're serious about building this, I can help you design the whole thing as a local voice microservice — including the calibration recorder, how to structure the voice profile, OpenVoice integration, streaming audio back to your AI, and the API between your model and the voice engine.

Ad
Yes I would like that

Absolutely. And now that you've clarified the goal, I'd structure this as a separate local voice service rather than tightly coupling OpenVoice to your AI model.

One important correction from my previous answer: OpenVoice V2 is primarily a zero-shot/reference-based cloning system, not a system where you train a permanent my_voice.vpf checkpoint from your recordings. Its documented workflow uses reference speech to extract the speaker/tone representation and then synthesises speech with it.

That actually works nicely for your project.

The architecture I'd build
5
                         YOUR AI
                           │
                           │
                    generates text
                           │
                           ▼
                  ┌─────────────────┐
                  │   Voice API     │
                  │ localhost:8000  │
                  └────────┬────────┘
                           │
                    text + settings
                           │
                           ▼
                  ┌─────────────────┐
                  │   OpenVoice V2  │
                  │                 │
                  │  + your voice   │
                  │    reference    │
                  └────────┬────────┘
                           │
                           ▼
                     WAV / PCM audio
                           │
                           ▼
                    Your AI's audio
                      output device

OpenVoice V2 is a good candidate because the official project supports local installation, V2 supports English natively, and the project is MIT licensed. It also exposes controls for characteristics including emotion, accent, rhythm, pauses and intonation.

I'd divide your project into 4 components
1. voice_calibrator

This is your custom project.

voice_calibrator/
├── prompts/
│   ├── phonetics.json
│   ├── prosody.json
│   ├── rhythm.json
│   ├── emotion.json
│   └── accent.json
│
├── recorder/
├── analyser/
└── output/

You create the script.

The user sits down with a microphone and goes through your carefully designed questions/prompts.

The recorder produces something like:

voice_data/
├── raw/
│   ├── 0001.wav
│   ├── 0002.wav
│   ├── ...
│   └── 0147.wav
│
├── transcripts/
├── metadata/
└── manifest.json

I'd never throw the original recordings away.

They're your ultimate backup.

2. voice_profile

Here's where I'd make your "voice font" concept real.

Even though OpenVoice doesn't require a special font file, your application can create one.

For example:

my_voice/
├── profile.json
├── reference.wav
├── references/
│   ├── neutral.wav
│   ├── expressive.wav
│   ├── conversational.wav
│   └── phonetic.wav
└── recordings/

profile.json could contain:

{
  "name": "My Voice",
  "language": "en-GB",
  "engine": "openvoice-v2",
  "reference": "reference.wav",
  "style": {
    "default": "neutral",
    "speed": 1.0
  }
}

So your assistant interacts with my_voice, rather than knowing anything about OpenVoice.

That's a really important abstraction.

3. voice_server

This is the bit I'd make into a standalone local service.

Something like:

http://localhost:8000

Your AI sends:

POST /speak

{
  "text": "Hello, how are you?",
  "voice": "my_voice"
}

And gets back:

audio/wav

You can later add:

{
  "text": "I can't believe you actually did that.",
  "voice": "my_voice",
  "style": "surprised",
  "speed": 1.05
}

Or:

{
  "text": "Good morning.",
  "voice": "my_voice",
  "style": "calm"
}

This means your AI model doesn't care whether the underlying TTS is OpenVoice, something else, or a future model.

4. Your actual AI

Then your assistant becomes incredibly simple:

User speaks
     ↓
Speech-to-text
     ↓
YOUR AI MODEL
     ↓
Text response
     ↓
LOCAL VOICE SERVER
     ↓
OpenVoice
     ↓
Audio
     ↓
Speaker

That's the architecture I'd recommend.

But there's a really interesting improvement

Don't make the voice server return the entire WAV only after the sentence has finished.

Eventually, you'll want streaming.

Instead:

AI generates:

"Hello..."
        ↓
TTS starts

"Hello, how..."
        ↓
Audio starts playing

"Hello, how are..."
        ↓
More audio arrives

"Hello, how are you?"
        ↓
Finished

That makes the assistant feel dramatically more conversational.

Your eventual architecture becomes:

                  ┌─────────────┐
                  │   YOUR AI   │
                  └──────┬──────┘
                         │
                  token/text stream
                         │
                         ▼
                  ┌─────────────┐
                  │ TTS SERVER  │
                  └──────┬──────┘
                         │
                  audio chunks
                         │
                         ▼
                  ┌─────────────┐
                  │ AUDIO QUEUE │
                  └──────┬──────┘
                         │
                         ▼
                      SPEAKER

That is how I'd ultimately build it.

Your calibration system is where I'd spend the most effort

This is actually the part of your idea I find most interesting.

Don't just make:

"Read these 100 sentences."

Build a voice coverage engine.

For example:

Calibration
───────────
Phonetic coverage       ██████████ 100%
Vowel coverage          █████████░  92%
Consonants              ██████████ 100%
Pitch range             ████████░░  81%
Question intonation     ██████████ 100%
Statement intonation    ██████████ 100%
Fast speech             ███████░░░  74%
Emotional variation     ████████░░  83%
Whisper/quiet speech    █████████░  91%

Then it decides what you need to record next.

For example:

"I need a little more data around your lower pitch range. Please read the following sentence slowly and naturally."

You record it.

It analyses it.

Then:

"Good. Now let's capture your normal conversational rhythm."

Eventually:

Calibration complete.

That is much more sophisticated than simply collecting an arbitrary number of minutes.

I'd also preserve multiple reference voices

This could be particularly useful with OpenVoice.

Rather than assuming your voice is one-dimensional, I'd create several reference categories:

my_voice/
│
├── neutral.wav
├── conversational.wav
├── energetic.wav
├── calm.wav
├── serious.wav
└── expressive.wav

Then your AI can choose the appropriate one.

For example:

Normal assistant response

→ conversational.wav

Reading an important warning

→ serious.wav

Excited about something

→ energetic.wav

OpenVoice specifically provides style controls around emotion, accent, rhythm, pauses and intonation, so you can experiment with whether those controls are sufficient before maintaining separate references.

And there's another layer I'd add

Your AI shouldn't simply output:

text

It could output:

{
  "text": "That's brilliant!",
  "voice": {
    "emotion": "excited",
    "speed": 1.08,
    "pitch": 1.02
  }
}

So your AI has control over how it says something, not just what it says.

Eventually you could even have your model learn a mapping between its internal response and your characteristic way of speaking.

The project I'd build

I'd probably structure the repository like this:

personal-voice/
│
├── calibration/
│   ├── recorder/
│   ├── prompts/
│   ├── analyser/
│   └── exporter/
│
├── voice/
│   ├── profiles/
│   │   └── my_voice/
│   └── engine/
│       └── openvoice/
│
├── server/
│   ├── api.py
│   ├── synthesizer.py
│   └── streaming.py
│
├── assistant/
│   └── your_ai/
│
└── config/
    └── config.yaml

And critically:

assistant
    ↓
    ↓ HTTP/WebSocket
    ↓
voice-server
    ↓
OpenVoice

rather than:

assistant
    ↓
hard-coded OpenVoice code everywhere

That separation will save you a lot of pain later.

One caveat about OpenVoice specifically

I'd treat it as version 1 of your voice engine, not necessarily the permanent answer.

The official project itself says V2 uses a reference audio input and supports the local V2 workflow through its demo/checkpoint setup.

So I'd preserve:

your original recordings + your calibration metadata + your profile

as the permanent asset.

Then:

                 YOUR VOICE DATA
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
        OpenVoice   Future TTS   Future TTS
           V2          #2           #3

That way, if something much better comes along in two years, you don't have to redo the calibration.

Where I'd start

I wouldn't build the whole thing at once.

I'd make Phase 1 extremely small:

1. Record one reference sample
              ↓
2. Feed it to OpenVoice V2
              ↓
3. Generate speech
              ↓
4. Hear your cloned voice
              ↓
5. Wrap that in localhost /speak

Once that works, Phase 2 is your calibration system.

Then Phase 3 is streaming.

Then Phase 4 is integrating it with your AI.

That gives you a working voice assistant surprisingly early, while leaving your much more ambitious "voice font" calibration system as a layer you can progressively improve.

And because OpenVoice V2 is MIT licensed, the project is unusually well suited to your goal of keeping the whole stack under your control.

If you tell me what your other AI model is built in (Python, C++, Node, etc.) and what hardware you're running it on (especially GPU/model), I can lay out the actual implementation — directory structure, Python environment, OpenVoice setup, local API, and the first working speak() function.

https://github.com/myshell-ai/OpenVoice