import datetime
import json
import urllib.request

from . import config as C
from .tools import TOOLS, run_tool
from .vision import capture

OLLAMA_CHAT = f"{C.OLLAMA_URL}/api/chat"

# Ollama wants {"type": "function", "function": {name, description, parameters}}
OLLAMA_TOOLS = [
    {"type": "function",
     "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
    for t in TOOLS
]


def _chat(messages):
    body = json.dumps({
        "model": C.MODEL,
        "messages": messages,
        "tools": OLLAMA_TOOLS,
        "stream": False,
        "think": False,  # faster replies; she speaks short answers anyway
        "options": {"num_predict": 400, "temperature": 0.6},
    }).encode()
    req = urllib.request.Request(OLLAMA_CHAT, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["message"]


class Brain:
    def __init__(self, speak, confirm):
        self.history = []
        self.speak, self.confirm = speak, confirm

    def ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        reply = {"content": ""}
        for _ in range(6):  # tool-use loop
            try:
                now = datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")
                system = f"{C.SYSTEM_PROMPT}\nCurrent local date and time: {now}."
                reply = _chat([{"role": "system", "content": system}] + self.history)
            except Exception as e:
                self.history.pop()
                return f"I can't reach my language model. {type(e).__name__}."
            self.history.append(reply)
            calls = reply.get("tool_calls") or []
            if not calls:
                break
            images = []
            for call in calls:
                fn = call["function"]
                name, args = fn["name"], fn.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                if name == "look":
                    try:
                        images.append(capture(args.get("source", "screen")))
                        result = "Image captured; it is attached in the next message."
                    except Exception as e:
                        result = f"Capture failed: {e}"
                else:
                    result = run_tool(name, args, self.speak, self.confirm)
                self.history.append({"role": "tool", "tool_name": name, "content": str(result)})
            if images:
                self.history.append({"role": "user", "content": "Here is what you captured. Describe it for me.",
                                     "images": images})
        # keep history bounded, starting at a plain user turn
        self.history = self.history[-30:]
        while self.history and not (self.history[0]["role"] == "user" and "images" not in self.history[0]):
            self.history.pop(0)
        return (reply.get("content") or "").strip()
