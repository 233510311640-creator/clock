import datetime
import os
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

import psutil

from . import config as C
from . import reminders, system_audio, web

APPS = {  # allowlist: spoken name -> executable
    "notepad": "notepad.exe", "calculator": "calc.exe", "paint": "mspaint.exe",
    "explorer": "explorer.exe", "task manager": "taskmgr.exe", "settings": "ms-settings:",
    "chrome": "chrome.exe", "edge": "msedge.exe", "vscode": "code", "terminal": "wt.exe",
}

TOOLS = [
    {"name": "get_time", "description": "Current local date and time.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "open_app", "description": f"Open an application. Allowed: {', '.join(APPS)}.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "close_app", "description": "Close an allowed application by name (asks user to confirm).",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "open_url", "description": "Open a URL in the default browser.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "web_search", "description": "Search the web and return the top results (titles, snippets, URLs) "
                                           "so you can answer questions about facts, news and current events.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "system_info", "description": "CPU, memory, disk and battery status.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "set_timer", "description": "Set a timer; Clock announces when it finishes.",
     "input_schema": {"type": "object", "properties": {"seconds": {"type": "integer"},
                                                         "label": {"type": "string"}}, "required": ["seconds"]}},
    {"name": "add_note", "description": "Save a note.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "read_notes", "description": "Read saved notes.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_files", "description": f"Find files by name fragment under {C.ALLOWED_DIR}.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "read_file", "description": f"Read a text file (first 4000 chars) inside {C.ALLOWED_DIR}.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "open_search_in_browser", "description": "Show a Google search in the browser, only when the user asks to see results on screen.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "read_webpage", "description": "Fetch a web page and return its text, to read an article or result in detail.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "weather", "description": f"Current weather and today's forecast. City defaults to {C.CITY}.",
     "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}}},
    {"name": "volume", "description": "Speaker volume: get, set (level 0-100), up/down (optional level = step, default 10), mute, unmute.",
     "input_schema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["get", "set", "up", "down", "mute", "unmute"]},
         "level": {"type": "integer"}}, "required": ["action"]}},
    {"name": "media", "description": "Media keys for whatever is playing: play_pause, next, previous, stop.",
     "input_schema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop"]}}, "required": ["action"]}},
    {"name": "set_reminder", "description": "Remind the user of something later; survives restarts. Give either "
        "`when` (local time, 'YYYY-MM-DD HH:MM') or `minutes_from_now`.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "when": {"type": "string"},
                                                         "minutes_from_now": {"type": "integer"}}, "required": ["text"]}},
    {"name": "list_reminders", "description": "List pending reminders and timers.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "cancel_reminder", "description": "Cancel a reminder or timer by its id or a word from its text.",
     "input_schema": {"type": "object", "properties": {"match": {"type": "string"}}, "required": ["match"]}},
    {"name": "look", "description": "Look at the user's screen or webcam and describe it. "
                                     "Use when asked what you can see / what's on screen / what I'm holding.",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string", "enum": ["screen", "webcam"]}},
                      "required": ["source"]}},
]


def _inside_allowed(p: str):
    path = Path(p) if os.path.isabs(p) else C.ALLOWED_DIR / p
    path = path.resolve()
    return path if C.ALLOWED_DIR in path.parents or path == C.ALLOWED_DIR else None


def run_tool(name: str, args: dict, speak, confirm) -> str:
    try:
        if name == "get_time":
            return datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")
        if name == "open_app":
            exe = APPS.get(args["name"].lower())
            if not exe:
                return f"'{args['name']}' is not in the allowed apps."
            if exe.endswith(":"):
                os.startfile(exe)
            else:
                subprocess.Popen(exe, shell=True)
            return f"Opened {args['name']}."
        if name == "close_app":
            exe = APPS.get(args["name"].lower())
            if not exe or exe.endswith(":"):
                return "Not an allowed app."
            if not confirm(f"Close {args['name']}?"):
                return "User declined."
            n = 0
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower() == os.path.basename(exe).lower():
                    p.terminate()
                    n += 1
            return f"Closed {n} process(es)."
        if name == "open_url":
            url = args["url"]
            if not url.startswith(("http://", "https://")):
                return "Only http(s) URLs allowed."
            webbrowser.open(url)
            return "Opened."
        if name == "web_search":
            return web.search(args["query"])
        if name == "open_search_in_browser":
            webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(args["query"]))
            return "Search opened."
        if name == "read_webpage":
            return web.read_page(args["url"])
        if name == "weather":
            return web.weather(args.get("city", ""))
        if name == "volume":
            return system_audio.volume(args["action"], args.get("level"))
        if name == "media":
            return system_audio.media(args["action"])
        if name == "set_reminder":
            if args.get("minutes_from_now") is not None:
                due = datetime.datetime.now() + datetime.timedelta(minutes=int(args["minutes_from_now"]))
            elif args.get("when"):
                due = reminders.parse_when(args["when"])
            else:
                return "I need a time: either `when` or `minutes_from_now`."
            if due <= datetime.datetime.now():
                return "That time has already passed."
            reminders.add(due, args["text"])
            return f"Reminder set for {reminders.describe(due)}."
        if name == "list_reminders":
            return reminders.listing()
        if name == "cancel_reminder":
            return reminders.cancel(args["match"])
        if name == "system_info":
            b = psutil.sensors_battery()
            return (f"CPU {psutil.cpu_percent(interval=0.5)}%, RAM {psutil.virtual_memory().percent}%, "
                    f"disk {psutil.disk_usage('C:/').percent}% used" +
                    (f", battery {b.percent:.0f}%{' charging' if b.power_plugged else ''}" if b else ""))
        if name == "set_timer":
            label = args.get("label", "Timer")
            reminders.add(datetime.datetime.now() + datetime.timedelta(seconds=args["seconds"]), label, kind="timer")
            return f"Timer set for {args['seconds']} seconds."
        if name == "add_note":
            with open(C.NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] {args['text']}\n")
            return "Noted."
        if name == "read_notes":
            return C.NOTES_FILE.read_text(encoding="utf-8")[-3000:] if C.NOTES_FILE.exists() else "No notes yet."
        if name == "search_files":
            q, hits = args["query"].lower(), []
            for root, _, files in os.walk(C.ALLOWED_DIR):
                hits += [os.path.join(root, f) for f in files if q in f.lower()]
                if len(hits) >= 10:
                    break
            return "\n".join(hits[:10]) or "No matches."
        if name == "read_file":
            p = _inside_allowed(args["path"])
            if not p or not p.is_file():
                return "File not found or outside the allowed folder."
            return p.read_text(encoding="utf-8", errors="replace")[:4000]
    except Exception as e:
        return f"Tool error: {e}"
    return f"Unknown tool {name}"
