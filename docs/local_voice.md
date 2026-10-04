# Local voice: Kokoro (free, offline)

Kokoro is an 82M-parameter speech model (Apache 2.0) run through ONNX on your CPU. No account, no key, no credits,
no internet. On this PC a typical reply takes about 0.5 s to generate, against about 1.7 s for edge-tts.

## Set up
    pip install -r requirements-kokoro.txt
    python -m clock.tts_local download      # about 350 MB into models/kokoro/ (git-ignored)

Then in `.env`:

    CLOCK_TTS=kokoro
    CLOCK_KOKORO_VOICE=bm_daniel            # default

Run `python -m clock --check`: the "Kokoro voice" line should be `[ok]`.

## Voices
`b*` are British, `a*` American; `m` male, `f` female. Male: `bm_daniel`, `bm_george`, `bm_lewis`, `bm_fable`,
`am_adam`, `am_michael`, `am_eric`... Female: `bf_emma`, `bf_alice`, `bf_isabella`, `bf_lily`, `af_heart`, `af_bella`...
`CLOCK_KOKORO_SPEED` (default 1.0) changes the pace. To hear them side by side: `python scripts/tts_bench.py`.

## If something is missing
Clock falls back to edge-tts and prints why (for example "model files missing" or "kokoro-onnx is not installed"),
so she always speaks. A problem with one line only affects that line; a setup problem turns Kokoro off until restart.

## Notes
- Audio tags like `[whispers]` are ElevenLabs-only; Kokoro and the fallbacks receive plain text.
- The model loads at startup (about 0.6 s with the files cached), so the first reply is not slow.
- First choice among the free options: Kokoro for the voice, edge-tts as the fallback. ElevenLabs is still available
  (docs/elevenlabs.md) if you ever have a working account.
