# Training a "Hey Clock" wake word

Clock can listen for her name with a tiny openWakeWord model instead of transcribing everything with Whisper.
openWakeWord ships no "Clock" model (only `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`, `timer`, `weather`),
so you train one once. Training is free on Google Colab and needs no code. The result is a single `.onnx` file.

## 1. Train (about 75-90 minutes on a paid GPU, ~2.5 hours on the free T4)

1. Open the community-maintained Colab notebook: <https://github.com/alfiedennen/openwakeword-colab-2026>
   (the original is `automatic_model_training.ipynb` in <https://github.com/dscripka/openWakeWord>; the 2026
   fork fixes Python 3.12 / torchaudio breakage).
2. In Colab choose **Runtime > Change runtime type > GPU** (L4 if you have Colab Pro, otherwise T4).
3. In the notebook's config cell (Cell 10 in that notebook) set:
   - `TARGET_PHRASE = ['hey clock']` (add `'hey klock'` or `'ok clock'` if you want those too)
   - `MODEL_NAME = 'hey_clock'`
4. **Runtime > Run all**. The last cell downloads `hey_clock.onnx`.

Tips from that notebook for better accuracy:
- Misses you too often (fewer than ~18 of 20 tries fire)? Raise `n_samples` to 5000 and `target_recall` from 0.5 to 0.7.
- Wakes on random speech? Raise `max_negative_weight` from 1500 to 3000.
- "Clock" is short and common ("o'clock"), so "hey clock" (two words) works better than "clock" alone.

## 2. Install

Put the file here (this exact name is picked up automatically):

    C:\Users\User\edith\models\hey_clock.onnx

Or keep it anywhere and set `CLOCK_WAKE_MODEL=C:\path\to\hey_clock.onnx` in `.env`.

## 3. Check and tune

    python -m clock --check          # "Wake word: openWakeWord (hey_clock)" means the model loaded
    python klock.py stop             # the test needs the mic to itself
    python klock.py wake-test        # live scores: say "hey clock" a few times, then talk normally

The phrase should score above `CLOCK_WAKE_THRESHOLD` (default 0.5) and everyday speech should stay well below it.
Missing you: lower the threshold (0.35-0.4). Waking by accident: raise it (0.6-0.7) or retrain with a higher
`max_negative_weight`. `CLOCK_WAKE_VAD=0` turns off the built-in voice filter if it clips quiet speech.

## How it behaves

- With a model present she uses it automatically (`CLOCK_WAKE_ENGINE=auto`). Force the old way with
  `CLOCK_WAKE_ENGINE=whisper`, or require the new way with `CLOCK_WAKE_ENGINE=oww`.
- Whisper only runs after the wake phrase, so idle CPU use drops to almost nothing.
- Anything you say right after "Hey Clock" is kept, so "Hey Clock, open Word" in one breath works.
- She ignores her own voice while speaking, so "the clock is ticking" in a reply never wakes her.
- No wake chime in this mode (it would leak into the open mic); the Control Center orb shows she heard you.
- "See you Clock" does not wake her (not the trained phrase). Say "Hey Clock, goodbye", or use the panel/tray.
- No model or a broken one: she falls back to the Whisper phrase match and says so in the log.

## Try the engine today without training

    set CLOCK_WAKE_MODEL=hey_jarvis
    python klock.py wake-test

then start her and say "Hey Jarvis". It proves the whole path (wake, command capture, Whisper) on your mic.
