# Clock

Voice assistant: wake word "Clock" -> Whisper STT -> a local Ollama model (tools + vision) -> neural TTS.

## Setup (needs Ollama running with qwen3.5:9b-q4_K_M)
    pip install -r requirements.txt

## Run
    python -m clock --text      # typing mode, no mic
    python -m clock --check     # verify Ollama, mic, voice and audio
    python -m clock             # voice mode: say "Clock, what time is it?"

Settings (all optional) go in a `.env` file or the environment; see `.env.example`: `CLOCK_MODEL`, `CLOCK_USER` (what she calls you), `CLOCK_VOICE`, `CLOCK_WHISPER`, `CLOCK_DIR`, `CLOCK_CITY`, `CLOCK_CHIME=0`, `CLOCK_HUD=1` (shows an optional on-screen overlay; off by default, status lives in the tray). The older `EDITH_*` names still work.
Say "Clock, goodbye" to quit.

## What she can do
- **Answer questions from the web** (`web_search`, `read_webpage`) and give the **weather** (default city: `CLOCK_CITY`, or any city you name).
- **Volume and media**: "turn it down", "set volume to 40", "mute", "pause", "next song".
- **Reminders and timers** that survive restarts: "remind me tomorrow at 8 to submit the assignment", "what reminders do I have", "cancel the stretch reminder". Anything that came due while she was off is announced when she starts.
- **Memory**: "remember my sister's birthday is 14 March", "forget the tea thing". Facts live in `~/edith_memory.json` and she sees them on every turn.
- **Clipboard**: "summarise what I copied", "copy 'see you at five'".
- **Windows**: "switch to Brave", "minimize Discord", "snap Notepad left", "close Notepad" (asks first), "minimize everything", "lock the PC".
- Open/close apps (incl. Word, Excel, PowerPoint), system info, notes, file search/read, and screen or webcam vision.

## Running her
    python klock.py start | stop | status | log | mic

With the PowerShell profile (`Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`) you can also type
`start the klock`, `stop the klock` or `klock status`. An optional HUD (`CLOCK_HUD=1`) in the top-right corner shows what she heard
and said while she is hearing, thinking or speaking. The wake word accepts common mishearings ("Hey Clark", "Hi click") but only
after a greeting.
    python klock.py wake-test    # live wake-word scores, to tune CLOCK_WAKE_THRESHOLD
    python klock.py panel        # Control Center window (pywebview + HTML/CSS UI in clock/ui/): glass orb, chat + typing, reminders, settings
    python klock.py tray         # tray icon: click it to open the panel (menu: Start / Pause)
    python klock.py install      # show that tray icon at every login (Clock waits until you start her)
    python klock.py uninstall    # turn that off

## Wake word
By default every utterance is transcribed and matched against "hey Clock". With an openWakeWord model
(`models/hey_clock.onnx`, trained once; see [docs/wake_word_training.md](docs/wake_word_training.md)) a tiny model listens
instead and Whisper runs only after it fires. `CLOCK_WAKE_ENGINE` = `auto` | `oww` | `whisper`, `CLOCK_WAKE_MODEL`,
`CLOCK_WAKE_THRESHOLD`, `CLOCK_WAKE_VAD`.

## Speech engine
`CLOCK_STT` = `auto` (default) | `phonon` | `whisper`. With `pip install -r requirements-phonon.txt` Clock uses
[Phonon-2](https://github.com/fermionresearch/phonon) (Fermion Research, weights CC-BY-4.0) for speech to text:
about 40 ms per command instead of about 900 ms with Whisper, same accuracy on our test clips. Without it, or if it errors, Whisper is used.
To compare engines on your own voice: `python scripts/stt_bench.py record` then `run` (needs the engines installed).

## Tests
    pip install -r requirements-dev.txt
    python -m pytest

## Adding a tool
Write a function in `clock/tools.py` and decorate it. The schema comes from the type hints (`str`, `int`, `Literal[...]`); a parameter with no default is required, and a `confirm` parameter is filled in for you.

    @tool("Tell a joke about the given topic.")
    def joke(topic: str = ""):
        return "..."
