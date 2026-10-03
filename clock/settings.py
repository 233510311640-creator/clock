"""Settings you can flip from the panel while Clock runs: HUD overlay, spoken replies, wake chime.

Stored in klock.settings.json; a key that isn't there falls back to the .env / environment default.
"""
import json

from . import config as C

SETTINGS_FILE = C.ROOT / "klock.settings.json"
KEYS = ("hud", "voice", "chime")


def defaults():
    return {"hud": C.HUD, "voice": True, "chime": C.CHIME}


def load():
    out = defaults()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if isinstance(data, dict):
        out.update({k: bool(data[k]) for k in KEYS if k in data})
    return out


def save(values: dict):
    cur = load()
    cur.update({k: bool(v) for k, v in values.items() if k in KEYS})
    SETTINGS_FILE.write_text(json.dumps(cur), encoding="utf-8")
