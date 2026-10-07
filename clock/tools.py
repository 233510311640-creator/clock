import datetime
import difflib
import inspect
import json
import os
import shutil
import subprocess
import urllib.parse
import webbrowser
from typing import Literal, get_args, get_origin

import psutil

from . import config as C
from . import clipboard, files, inputs, memory, shell, reminders, routines, system_audio, tasks, web, windows

APPS = {  # allowlist: spoken name -> executable
    "notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
    "explorer": "explorer.exe", "task manager": "taskmgr.exe", "settings": "ms-settings:",
    "chrome": "chrome.exe", "brave": "brave.exe", "edge": "msedge.exe", "vscode": "code", "terminal": "wt.exe",
    "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe",
}


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


def resolve_app(name: str):
    """Spoken app name -> key in APPS. Accepts a near miss ("wave" for brave): speech-to-text garbles app names."""
    key = name.strip().lower()
    if key in APPS:
        return key
    close = difflib.get_close_matches(key, list(APPS), n=1, cutoff=0.65)
    return close[0] if close else None


@tool(f"Open an application. Allowed: {', '.join(APPS)}.")
def open_app(name: str):
    key = resolve_app(name)
    exe = APPS.get(key or "")
    if not exe:
        return f"'{name}' is not in the allowed apps."
    name = key
    if exe.endswith(":"):
        os.startfile(exe)
    elif shutil.which(exe):
        subprocess.Popen(exe, shell=True)
    else:
        os.startfile(exe)  # not on PATH (Office): Windows finds it through its App Paths registry
    return f"Opened {name}."


@tool("Close an allowed application by name (asks user to confirm).")
def close_app(name: str, confirm):
    key = resolve_app(name)
    exe = APPS.get(key or "")
    if not exe or exe.endswith(":"):
        return "Not an allowed app."
    name = key  # confirm the app she will really close, not the garbled word she heard
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


@tool("What Clock did recently: the last tool calls and how each ended. Use when asked what you did or why.")
def recent_actions(count: int = 5):
    from . import audit
    rows = audit.tail(max(1, min(count, 20)))
    if not rows:
        return "No actions logged yet."
    return "\n".join(f"{r['ts']} {r['tool']} {json.dumps(r['args'], ensure_ascii=False)} -> {r['outcome']}" for r in rows)


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


_FOLDERS = ", ".join(r.name for r in files.roots())


@tool(f"Find files by name fragment in the approved folders ({_FOLDERS}).")
def search_files(query: str):
    return files.search(query)


@tool(f"Read a text, Word (.docx) or PDF file in the approved folders ({_FOLDERS}), 4000 characters at a time: "
      f"for a long file call again with `offset`. Relative paths start in {C.ALLOWED_DIR.name}.")
def read_file(path: str, offset: int = 0):
    return files.read(path, offset)


@tool("List a folder's contents. An empty path lists what is inside every approved folder.")
def list_folder(path: str = ""):
    return files.list_folder(path)


@tool("Write a text file in the approved folders. mode: create (new file only), append, or overwrite (asks to confirm).")
def write_file(path: str, text: str, mode: Literal["create", "append", "overwrite"], confirm):
    return files.write(path, text, mode, confirm)


@tool("Create a folder in the approved folders.")
def make_folder(path: str):
    return files.make_folder(path)


@tool("Move or rename a file or folder inside the approved folders (asks to confirm before replacing anything).")
def move_file(src: str, dst: str, confirm):
    return files.move(src, dst, confirm)


@tool("Copy one file inside the approved folders (asks to confirm before replacing anything).")
def copy_file(src: str, dst: str, confirm):
    return files.copy(src, dst, confirm)


@tool("Delete one file: it goes to the Recycle Bin, and she always asks to confirm first.")
def delete_file(path: str, confirm):
    return files.delete(path, confirm)


@tool(f"Run a PowerShell command in {C.ALLOWED_DIR.name}. Look-only commands (Get-Process, ipconfig, ...) run at once; "
      "anything else is read back and she asks first.")
def run_command(command: str, confirm):
    return shell.run(command, confirm)


@tool("Type text into the window that is in front (focus the right window first). Never type passwords. She asks first.")
def type_text(text: str, confirm):
    return inputs.type_text(text, confirm)


@tool("Press a key or combination in the front window, for example ctrl+c, alt+tab, enter, f5, win+d. She asks first.")
def press_keys(keys: str, confirm):
    return inputs.press_keys(keys, confirm)


@tool("Click the mouse at screen pixel x,y (button left, right or middle). She asks first. Prefer keys and window "
      "control; clicking needs exact coordinates.")
def mouse_click(x: int, y: int, confirm, button: Literal["left", "right", "middle"] = "left", double: str = ""):
    return inputs.click(x, y, confirm, button, double.lower() in ("true", "yes", "1", "double"))


@tool("Scroll the window under the mouse up or down by a number of notches (default 3). She asks first.")
def scroll(direction: Literal["up", "down"], confirm, amount: int = 3):
    return inputs.scroll(direction, amount, confirm)


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


@tool("Set a recurring spoken briefing. `at` is 24-hour 'HH:MM'. `days` is daily, weekdays, weekends or a list "
      "like 'mon,wed,fri'. `include` is any of: time, weather, reminders (comma-separated). `text` is an optional "
      "line to say first. Example: every weekday at 8: at='08:00', days='weekdays', include='weather,reminders'.")
def add_routine(at: str, days: str = "daily", include: str = "", text: str = ""):
    try:
        return routines.add(at, days, include, text)
    except ValueError as e:
        return f"Couldn't set that routine: {e}"


@tool("List recurring routines.")
def list_routines():
    return routines.listing()


@tool("Cancel a recurring routine by its id or a word from it (for example 'weather').")
def cancel_routine(match: str):
    return routines.cancel(match)


@tool("Start a longer research job in the background (web search, reading pages and files) and carry on talking. "
      "She announces the result when it finishes. Use for questions that need several lookups, not quick facts.")
def start_task(goal: str, speak):
    return tasks.start(goal, speak)


@tool("List background tasks and their status.")
def list_tasks():
    return tasks.listing()


@tool("Get the result of a background task by its number or a word from its goal.")
def task_result(match: str):
    return tasks.result(match)


@tool("Cancel a running background task by its number or a word from its goal.")
def cancel_task(match: str):
    return tasks.cancel(match)


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
