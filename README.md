# Clock

Voice assistant: wake word "Clock" -> Whisper STT -> a local Ollama model (tools + vision) -> neural TTS.

## Setup (needs Ollama running with qwen3.5:9b-q4_K_M)
    pip install -r requirements.txt

## Run
    python -m clock --text      # typing mode, no mic
    python -m clock --check     # verify Ollama, mic, voice and audio
    python -m clock             # voice mode: say "Clock, what time is it?"

Settings (all optional) go in a `.env` file or the environment; see `.env.example`: `CLOCK_MODEL`, `CLOCK_USER` (what she calls you), `CLOCK_VOICE`, `CLOCK_WHISPER`, `CLOCK_DIR`, `CLOCK_CITY`, `CLOCK_CHIME=0`. The older `EDITH_*` names still work.
Say "Clock, goodbye" to quit.

## What she can do
- **Answer questions from the web** (`web_search`, `read_webpage`) and give the **weather** (default city: `CLOCK_CITY`, or any city you name).
- **Volume and media**: "turn it down", "set volume to 40", "mute", "pause", "next song".
- **Reminders and timers** that survive restarts: "remind me tomorrow at 8 to submit the assignment", "what reminders do I have", "cancel the stretch reminder". Anything that came due while she was off is announced when she starts.
- **Memory**: "remember my sister's birthday is 14 March", "forget the tea thing". Facts live in `~/edith_memory.json` and she sees them on every turn.
- **Clipboard**: "summarise what I copied", "copy 'see you at five'".
- **Windows**: "switch to Brave", "minimize Discord", "snap Notepad left", "close Notepad" (asks first), "minimize everything", "lock the PC".
- Open/close apps, system info, notes, file search/read, and screen or webcam vision.

## Running her
    python klock.py start | stop | status | log | mic
    python klock.py install      # start automatically when you log in
    python klock.py uninstall    # turn that off

## Tests
    pip install -r requirements-dev.txt
    python -m pytest

## Adding a tool
Write a function in `clock/tools.py` and decorate it. The schema comes from the type hints (`str`, `int`, `Literal[...]`); a parameter with no default is required, and a `confirm` parameter is filled in for you.

    @tool("Tell a joke about the given topic.")
    def joke(topic: str = ""):
        return "..."
