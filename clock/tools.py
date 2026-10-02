import datetime
import inspect
import os
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Literal, get_args, get_origin

import psutil

from . import config as C
from . import clipboard, memory, reminders, system_audio, web, windows

APPS = {  # allowlist: spoken name -> executable
    "notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
    "explorer": "explorer.exe", "task manager": "taskmgr.exe", "settings": "ms-settings:",
    "chrome": "chrome.exe", "edge": "msedge.exe", "vscode": "code", "terminal": "wt.exe",
}


def _inside_allowed(p: str):
    path = Path(p) if os.path.isabs(p) else C.ALLOWED_DIR / p
    path = path.resolve()
    return path if C.ALLOWED_DIR in path.parents or path == C.ALLOWED_DIR else None


_JSON_TYPES = {str: "string", int: "integer"}
_REGISTRY = {}  # tool name -> (function, schema)


def tool(description: str, name: str = None):
    """Register a function as a model-callable tool. The schema comes from its type hints:
    str / int / Literal[...] parameters, and a parameter with no default is required.
    A parameter named `confirm` or `speak` is filled in by run_tool, not by the model.
    `name` overrides the function name (for tools whose natural name would shadow an import)."""
    def wrap(fn):
        props, required = {}, []
        for pname, p in inspect.signature(fn).parameters.items():
            if pname in ("confirm", "speak"):
                continue
            if get_origin(p.annotation) is Literal:
                props[pname] = {"type": "string", "enum": list(get_args(p.annotation))}
            else:
                props[pname] = {"type": _JSON_TYPES[p.annotation]}
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        tool_name = name or fn.__name__
        _REGISTRY[tool_name] = (fn, {"name": tool_name, "description": description, "input_schema": schema})
        return fn
    return wrap


@tool("Current local date and time.")
def get_time():
    return datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")


@tool(f"Open an application. Allowed: {', '.join(APPS)}.")
def open_app(name: str):
    exe = APPS.get(name.lower())
    if not exe:
        return f"'{name}' is not in the allowed apps."
    if exe.endswith(":"):
        os.startfile(exe)
    else:
        subprocess.Popen(exe, shell=True)
    return f"Opened {name}."


@tool("Close an allowed application by name (asks user to confirm).")
def close_app(name: str, confirm):
    exe = APPS.get(name.lower())
    if not exe or exe.endswith(":"):
        return "Not an allowed app."
    if not confirm(f"Close {name}?"):
        return "User declined."
    n = 0
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == os.path.basename(exe).lower():
            p.terminate()
            n += 1
    return f"Closed {n} process(es)."


@tool("Open a URL in the default browser.")
def open_url(url: str):
    if not url.startswith(("http://", "https://")):
        return "Only http(s) URLs allowed."
    webbrowser.open(url)
    return "Opened."


@tool("Search the web and return the top results (titles, snippets, URLs) "
      "so you can answer questions about facts, news and current events.")
def web_search(query: str):
    return web.search(query)


@tool("CPU, memory, disk and battery status.")
def system_info():
    b = psutil.sensors_battery()
    return (f"CPU {psutil.cpu_percent(interval=0.5)}%, RAM {psutil.virtual_memory().percent}%, "
            f"disk {psutil.disk_usage('C:/').percent}% used" +
            (f", battery {b.percent:.0f}%{' charging' if b.power_plugged else ''}" if b else ""))


@tool("Set a timer; Clock announces when it finishes.")
def set_timer(seconds: int, label: str = "Timer"):
    reminders.add(datetime.datetime.now() + datetime.timedelta(seconds=seconds), label, kind="timer")
    return f"Timer set for {seconds} seconds."


@tool("Save a note.")
def add_note(text: str):
    with open(C.NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] {text}\n")
    return "Noted."


@tool("Read saved notes.")
def read_notes():
    return C.NOTES_FILE.read_text(encoding="utf-8")[-3000:] if C.NOTES_FILE.exists() else "No notes yet."


@tool(f"Find files by name fragment under {C.ALLOWED_DIR}.")
def search_files(query: str):
    q, hits = query.lower(), []
    for root, _, files in os.walk(C.ALLOWED_DIR):
        hits += [os.path.join(root, f) for f in files if q in f.lower()]
        if len(hits) >= 10:
            break
    return "\n".join(hits[:10]) or "No matches."


@tool(f"Read a text file (first 4000 chars) inside {C.ALLOWED_DIR}.")
def read_file(path: str):
    p = _inside_allowed(path)
    if not p or not p.is_file():
        return "File not found or outside the allowed folder."
    return p.read_text(encoding="utf-8", errors="replace")[:4000]


@tool("Show a Google search in the browser, only when the user asks to see results on screen.")
def open_search_in_browser(query: str):
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    return "Search opened."


@tool("Fetch a web page and return its text, to read an article or result in detail.")
def read_webpage(url: str):
    return web.read_page(url)


@tool(f"Current weather and today's forecast. City defaults to {C.CITY}.")
def weather(city: str = ""):
    return web.weather(city)


@tool("Speaker volume: get, set (level 0-100), up/down (optional level = step, default 10), mute, unmute.")
def volume(action: Literal["get", "set", "up", "down", "mute", "unmute"], level: int = None):
    return system_audio.volume(action, level)


@tool("Media keys for whatever is playing: play_pause, next, previous, stop.")
def media(action: Literal["play_pause", "next", "previous", "stop"]):
    return system_audio.media(action)


@tool("Remind the user of something later; survives restarts. Give either "
      "`when` (local time, 'YYYY-MM-DD HH:MM') or `minutes_from_now`.")
def set_reminder(text: str, when: str = "", minutes_from_now: int = None):
    if minutes_from_now is not None:
        due = datetime.datetime.now() + datetime.timedelta(minutes=int(minutes_from_now))
    elif when:
        due = reminders.parse_when(when)
    else:
        return "I need a time: either `when` or `minutes_from_now`."
    if due <= datetime.datetime.now():
        return "That time has already passed."
    reminders.add(due, text)
    return f"Reminder set for {reminders.describe(due)}."


@tool("List pending reminders and timers.")
def list_reminders():
    return reminders.listing()


@tool("Cancel a reminder or timer by its id or a word from its text.")
def cancel_reminder(match: str):
    return reminders.cancel(match)


@tool("Save a lasting fact about the user (a preference, name, date, habit) to long-term memory.")
def remember(fact: str):
    return memory.remember(fact)


@tool("Forget remembered facts: give a word or phrase from the fact.")
def forget(match: str):
    return memory.forget(match)


@tool("Read the text the user copied (action read), or put text on the clipboard (action write).", name="clipboard")
def clipboard_tool(action: Literal["read", "write"], text: str = ""):
    if action == "write":
        clipboard.write(text)
        return "Copied to the clipboard."
    content = clipboard.read()
    return content[:4000] if content else "The clipboard has no text in it."


@tool("Control open windows. Actions: list, focus (switch to), minimize, maximize, restore, "
      "snap_left, snap_right, close (asks to confirm), minimize_all, lock (locks the PC). `target` is part of the window title "
      "or the app name, such as chrome.", name="windows")
def windows_tool(action: Literal["list", "focus", "minimize", "maximize", "restore", "snap_left",
                                 "snap_right", "close", "minimize_all", "lock"], confirm, target: str = ""):
    return windows.control(action, target, confirm)


@tool("Look at the user's screen or webcam and describe it. "
      "Use when asked what you can see / what's on screen / what I'm holding.")
def look(source: Literal["screen", "webcam"]):
    return "Handled by the brain, which has to attach the image."


TOOLS = [schema for _, schema in _REGISTRY.values()]


def run_tool(name: str, args: dict, speak, confirm) -> str:
    entry = _REGISTRY.get(name)
    if not entry:
        return f"Unknown tool {name}"
    fn, schema = entry
    params = schema["input_schema"]
    missing = [r for r in params.get("required", []) if r not in args]
    if missing:
        return f"Tool error: missing {', '.join(missing)}"
    kwargs = {k: v for k, v in args.items() if k in params["properties"]}
    sig = inspect.signature(fn).parameters
    if "confirm" in sig:
        kwargs["confirm"] = confirm
    if "speak" in sig:
        kwargs["speak"] = speak
    try:
        return fn(**kwargs)
    except Exception as e:
        return f"Tool error: {e}"
