# Upgrade plan: STT, TTS and Open Dots ideas

Researched 2026-10-04. Names in the source video were garbled: "Phon 2" is **Phonon-2**, the 16.9 MB model is **Whistle**.

## Current state
- STT: `clock/stt.py`, faster-whisper `small.en`, int8 CPU, `transcribe(audio) -> str`, with an `initial_prompt` of expected words.
- TTS: `clock/tts.py`, edge-tts to mp3 to pygame; SAPI fallback on error. `Speaker` queues sentences and synthesises the next while one plays.
- Config: `clock/config.py` (`CLOCK_*` env vars, `.env`).

Design rule for all three below: add an **engine switch** (like `CLOCK_WAKE_ENGINE`), keep the current engine as default and as fallback.

## 1. Whistle (Cactus) - fast command STT
- Repo: https://github.com/cactus-compute/needle (weights: https://huggingface.co/Cactus-Compute/whistle), `pip install cactus-needle`.
- `needle.transcribe("clip.wav")["text"]`. 16.9 MB, CPU, word timestamps.
- Limits: 30 s per clip, 16 kHz mono, 320 tokens. Languages: en, de, fr, es, it, nl, pl. Licence not stated on the blog: check repo before shipping.
- Fit: our utterances are short commands (max 15 s, `MAX_UTTERANCE_SECONDS`), so the 30 s cap is fine. 11 ms first token vs 73 ms for Whisper base.
- Risk: no `initial_prompt`, so we lose the biasing toward app names and "Clock". Accuracy on Indian-accented English is unknown.
- Work:
  1. `pip install cactus-needle` in a scratch venv; check it works on Windows x64 (blog lists prebuilt targets, `needle download <target>`).
  2. Build `scripts/stt_bench.py`: record 30 real command clips, compare WER and latency of small.en vs Whistle.
  3. If good: `clock/stt.py` gets `_whistle_transcribe`; `CLOCK_STT_ENGINE=whisper|whistle|auto`. Fall back to Whisper on empty text or exception.
  4. Possible hybrid: Whistle first; rerun Whisper only when the result is empty or fails the wake/command match.
  5. Tests: monkeypatch the engine, assert fallback.

## 2. Phonon-2 (Fermion Research) - accurate STT, long audio
- Repo: https://github.com/fermionresearch/phonon, `pip install fermion-research`. Weights: https://huggingface.co/FermionResearch/Phonon-2 (164 MB, CC-BY-4.0, derived from Parakeet TDT 0.6B v3). ONNX port: https://huggingface.co/tiyuvta/Phonon-2-ONNX.
- English only. 5.21% average WER on Open ASR Leaderboard, claimed better than Whisper large. 143x realtime on 8 CPU cores. Windows x64 CPU supported (needs SSE4.1; AVX2 faster). Install CPU torch first. OpenAI-compatible server at 127.0.0.1:8000. `phonon listen` live mic is Apple-silicon only.
- Fit: better accuracy than `small.en` at similar cost, which helps accents. Also unlocks new features Whisper is too slow for:
  - "Transcribe this recording" / meeting-notes tool (file in `ALLOWED_DIR` to text to note).
  - Better fallback when Whistle fails.
- Risk: pulls in torch (large install). Attribution needed for CC-BY-4.0 (credit in README). No bias prompt either.
- Work:
  1. Benchmark in the same script as Whistle (add engine `phonon`).
  2. Add engine to `clock/stt.py` behind `CLOCK_STT_ENGINE`; lazy import so torch is optional (`requirements-phonon.txt`).
  3. New tool `transcribe_file(path)` in `clock/tools.py` using the same engine; path must pass the `ALLOWED_DIR` check; output saved as a note.
  4. README credit line.

## 3. ElevenLabs Eleven v4 - expressive TTS (opt-in)
- Docs: https://elevenlabs.io/v4, SDK https://github.com/elevenlabs/elevenlabs-python, `pip install elevenlabs`.
- Models: `eleven_v4` (quality) and v4 Turbo (about 100 ms inference, about 150 ms to first speech, for voice agents). Verify the exact Turbo `model_id` in the models page before coding.
- Audio tags in text: `[pause]`, `[whispers]`, `[excited]`. SSML `<break>` is disabled in v4.
- Free tier: 10,000 credits per month, about 10 minutes of audio. Cloud only, needs `ELEVENLABS_API_KEY`.
- Fit: needs network and credits, so it is opt-in. Good for short replies; long web summaries burn credits.
- Work:
  1. `.env`: `CLOCK_TTS_ENGINE=edge|eleven`, `ELEVENLABS_API_KEY`, `CLOCK_ELEVEN_VOICE`, `CLOCK_ELEVEN_MODEL`.
  2. Refactor `clock/tts.py`: pull the `edge_tts.Communicate(...).save(path)` calls (lines 60, 117) into `_synth_file(text) -> path`. Dispatch on engine. Eleven writes mp3 with the same flow, so pygame playback stays unchanged.
  3. Fallback chain: eleven, then edge, then SAPI. On quota/HTTP error, log once and drop to edge for the rest of the session.
  4. Credit guard: cap characters per reply (`CLOCK_ELEVEN_MAX_CHARS`); long text uses edge.
  5. Prompt tweak (`SYSTEM_PROMPT`): when engine is eleven, allow sparse audio tags. Strip tags before printing to HUD/log and before edge fallback.
  6. Later: websocket streaming for lower latency (needs `Speaker` rework).
  7. Tests: mock the client, check fallback and tag stripping.
  8. Key lives in `.env` only (already gitignored). Never log it.

## 4. Open Dots - what it is and how it helps
"Open Dots" is several unrelated repos, all early prototypes. None is a drop-in; none supports Ollama out of the box.

| Repo | Stack | Notes |
|---|---|---|
| https://github.com/Anil-matcha/open-dots | Next.js + FastAPI + SQLite | Deny-by-default action gateway, approval prompts, audit log, Composio connectors, personas. OpenAI Responses-compatible model API (Ollama exposes an OpenAI-compatible endpoint, so may work: unverified). MIT. |
| https://github.com/diggerhq/opendots | TypeScript, OpenComputer Serverless Agents | Always-on agent, topic-based work with notes and memory. Claude/OpenAI/OpenRouter only. MIT. |
| https://github.com/composio-community/open-dot | Electron, macOS only | Browser agents, scheduled routines, voice calls via OpenAI Realtime, 1,500 apps via Composio. Not usable on Windows. |

Clock already covers: reminders, memory, tools, confirm-before-act. Gaps that Open Dots shows, and our plan:

1. **Approval gateway + audit log** (from Anil-matcha). We have a `confirm` param per tool. Add a central policy: tool risk levels (read / write / destructive), one `audit.log` JSONL of every tool call with args and result. Small, high value, no new deps.
2. **Scheduled routines** ("every weekday at 8 give me weather and reminders"). We have one-shot reminders. Extend `clock/reminders.py` with recurring entries, plus a `briefing` tool.
3. **Background tasks** (agent keeps working while you do other things). Add a task runner: long tool jobs (web research, file summaries) run in a thread, result announced when done, like overdue reminders are today.
4. **Remote channel** (phone/Slack in Dots). Cheapest local equivalent: a Telegram bot or the Control Center panel on LAN, feeding `klock.inbox` (this file already exists, so an inbox path is in place). Needs auth; do not expose it unauthenticated.
5. **Composio / MCP connectors** (Gmail, Calendar). Optional, cloud OAuth. Defer until 1-3 are done.
6. Do not adopt a whole Open Dots app: different stack, prototype quality, cloud-model assumptions.

Suggested order: audit log + risk levels, then recurring routines, then background tasks, then remote inbox.

## Order of work
1. STT benchmark script and `CLOCK_STT_ENGINE` (Whistle, Phonon). Decide by measured WER and latency on real clips.
2. TTS engine switch and Eleven v4 (needs your API key).
3. Open Dots-inspired items 1 to 4 above.

Open questions for you: do you have an ElevenLabs key; will you record about 30 sample commands for the benchmark; is a torch install acceptable?

## Project plugins
`.claude/settings.json` enables for this folder: `pyright-lsp` (Python type checking), `context7` (current library docs, useful for the elevenlabs and needle SDKs), `caveman` (terse mode). Not enabled: ponytail, openai-developers, claude-code-setup (not relevant here).
