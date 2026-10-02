# Clock

Voice assistant: wake word "Clock" -> Whisper STT -> a local Ollama model (tools + vision) -> neural TTS.

## Setup (needs Ollama running with qwen3.5:9b-q4_K_M)
    pip install -r requirements.txt

## Run
    python -m edith --text      # typing mode, no mic
    python -m edith             # voice mode: say "Clock, what time is it?"

Optional env vars: EDITH_USER (what she calls you), EDITH_VOICE, EDITH_WHISPER, EDITH_DIR, EDITH_MODEL.
Say "Clock, goodbye" to quit.

## What she can do
- **Answer questions from the web** (`web_search`, `read_webpage`) and give the **weather** (default city: `EDITH_CITY`, or any city you name).
- **Volume and media**: "turn it down", "set volume to 40", "mute", "pause", "next song".
- **Reminders and timers** that survive restarts: "remind me tomorrow at 8 to submit the assignment", "what reminders do I have", "cancel the stretch reminder". Anything that came due while she was off is announced when she starts.
- Open/close apps, system info, notes, file search/read, and screen or webcam vision.

## Running her
    python klock.py start | stop | status | log | mic
    python klock.py install      # start automatically when you log in
    python klock.py uninstall    # turn that off
