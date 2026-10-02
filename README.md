# Clock

Voice assistant: wake word "Clock" -> Whisper STT -> a local Ollama model (tools + vision) -> neural TTS.

## Setup (needs Ollama running with qwen3.5:9b-q4_K_M)
    pip install -r requirements.txt

## Run
    python -m edith --text      # typing mode, no mic
    python -m edith             # voice mode: say "Clock, what time is it?"

Optional env vars: EDITH_USER (what she calls you), EDITH_VOICE, EDITH_WHISPER, EDITH_DIR, EDITH_MODEL.
Say "Clock, goodbye" to quit.
