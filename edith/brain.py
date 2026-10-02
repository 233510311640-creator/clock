import datetime
import json
import re
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


def _chat(messages, on_text=None):
    """Stream one assistant turn from Ollama. Calls on_text(delta) as text arrives; returns the full message."""
    body = json.dumps({
        "model": C.MODEL,
        "messages": messages,
        "tools": OLLAMA_TOOLS,
        "stream": True,
        "keep_alive": "60m",  # keep the model loaded between requests
        "think": False,  # faster replies; she speaks short answers anyway
        "options": {"num_predict": 400, "temperature": 0.6},
    }).encode()
    req = urllib.request.Request(OLLAMA_CHAT, data=body, headers={"Content-Type": "application/json"})
    content, calls = "", []
    with urllib.request.urlopen(req, timeout=180) as r:
        for line in r:
            if not line.strip():
                continue
            msg = json.loads(line).get("message") or {}
            delta = msg.get("content") or ""
            if delta:
                content += delta
                if on_text:
                    on_text(delta)
            calls.extend(msg.get("tool_calls") or [])
    out = {"role": "assistant", "content": content}
    if calls:
        out["tool_calls"] = calls
    return out


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class _Sentences:
    """Buffers streamed text and hands complete sentences to a callback."""

    def __init__(self, emit):
        self.emit, self.buf = emit, ""

    def feed(self, delta):
        self.buf += delta
        parts = _SENTENCE_END.split(self.buf)
        self.buf = parts.pop()
        for p in parts:
            if p.strip():
                self.emit(p.strip())

    def flush(self):
        if self.buf.strip():
            self.emit(self.buf.strip())
        self.buf = ""


class Brain:
    def __init__(self, speak, confirm):
        self.history = []
        self.speak, self.confirm = speak, confirm

    def ask(self, text: str, on_sentence=None) -> str:
        """Answer `text`. With on_sentence, each sentence is passed to it as soon as it is generated."""
        sentences = _Sentences(on_sentence) if on_sentence else None
        self.history.append({"role": "user", "content": text})
        reply = {"content": ""}
        for _ in range(6):  # tool-use loop
            try:
                now = datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")
                system = f"{C.SYSTEM_PROMPT}\nCurrent local date and time: {now}."
                reply = _chat([{"role": "system", "content": system}] + self.history,
                              sentences.feed if sentences else None)
                if sentences:
                    sentences.flush()
            except Exception as e:
                self.history.pop()
                msg = f"I can't reach my language model. {type(e).__name__}."
                if on_sentence:
                    on_sentence(msg)
                return msg
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
