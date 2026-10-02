import os
from pathlib import Path

MODEL = os.environ.get("EDITH_MODEL", "qwen3.5:9b-q4_K_M")
OLLAMA_URL = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")  # not "localhost": on Windows that costs ~2s per call
USER_NAME = os.environ.get("EDITH_USER", "boss")
WAKE_WORDS = ("clock", "hey clock")
VOICE = os.environ.get("EDITH_VOICE", "en-GB-SoniaNeural")
WHISPER_MODEL = os.environ.get("EDITH_WHISPER", "small.en")
SAMPLE_RATE = 16000
SILENCE_SECONDS = 0.7
ENERGY_THRESHOLD = 0.015
MAX_UTTERANCE_SECONDS = 15
# Windows-level mute / blocked device gives exact digital silence (seen as 0.000). The HyperX's own
# mute switch and its noise gate both sit at a flat ~1.5e-5 floor, so those can't be told from a quiet room.
MIC_SILENT_LEVEL = 1e-6
MIC_SILENT_SECONDS = 15
# Files tools may read/search
ALLOWED_DIR = Path(os.environ.get("EDITH_DIR", Path.home() / "Documents")).resolve()
NOTES_FILE = Path.home() / "edith_notes.txt"
REMINDERS_FILE = Path.home() / "edith_reminders.json"
CITY = os.environ.get("EDITH_CITY", "New Delhi")  # default for weather
WEB_TIMEOUT = 10

SYSTEM_PROMPT = f"""You are Clock, a personal AI assistant, \
addressing the user as "{USER_NAME}". Your replies are SPOKEN aloud: keep them to one to three \
short sentences, no markdown, no lists, no emojis. Tone: calm, dry, quietly witty, efficient. \
Use tools to act on the PC when asked; for facts, news or anything current, call web_search (and read_webpage if the snippets are not enough) and answer from the results in your own words; for weather use the weather tool; for reminders give set_reminder an exact local date and time worked out from the current date and time given below, or use minutes_from_now; any request to be reminded or woken later MUST go through set_reminder, and never say you set, saved, changed or cancelled anything unless the tool just returned success for it; confirm what you did briefly. Never end with a follow-up question or offer unless you truly need information. The user has an accent, so speech transcription can contain wrong words: if a request is unclear, guess the closest sensible meaning (for example an app name) and act on it, and only ask when there is no sensible guess. If a tool needs \
confirmation and it is denied, acknowledge and stop."""
