"""Talk to Clock from your phone through a private Telegram bot.

Clock only makes outgoing HTTPS calls (long polling), so nothing is opened on your network. Safeguards:
  * only the chat ids in CLOCK_TELEGRAM_CHAT are answered; everyone else is ignored without a reply
  * messages that were queued while Clock was off, or are older than MAX_AGE seconds, are dropped, never run
  * by default (CLOCK_REMOTE_TOOLS=safe) the phone cannot open or close apps, use the clipboard, control windows
    or look at your screen or webcam, and every confirmation is refused
Setup: see docs/remote_inbox.md.
"""
import json
import threading
import time
import urllib.error
import urllib.request

from . import config as C
from .tts_eleven import plain

API = "https://api.telegram.org"
MAX_AGE = 120  # seconds; older messages are not run
MAX_TEXT = 600  # longer messages are cut
CHUNK = 3900  # Telegram's limit is 4096 characters per message

# What a phone message may do. Nothing here touches other apps, the clipboard, the screen or the webcam.
SAFE_TOOLS = {
    "get_time", "system_info", "weather", "web_search", "read_webpage", "read_file", "search_files", "read_notes",
    "add_note", "set_timer", "set_reminder", "list_reminders", "cancel_reminder", "remember", "forget",
    "add_routine", "list_routines", "cancel_routine", "start_task", "list_tasks", "task_result", "cancel_task",
    "volume", "media", "recent_actions",
}
_EXTRA = ("\nThis message arrived as text from the user's phone. Reply in plain text, brief, no markdown. "
          "You cannot open apps, use the clipboard, control windows or see the screen from here; say so if asked.")


def allowed_tools():
    """None means every tool (CLOCK_REMOTE_TOOLS=all); otherwise the safe set."""
    return None if C.REMOTE_TOOLS == "all" else SAFE_TOOLS


def make_brain(send):
    """A Brain for phone messages. `send(text)` delivers late results (a finished background task) to the phone."""
    from .brain import Brain
    b = Brain(send, lambda q: False, allowed=allowed_tools(), system_extra=_EXTRA)
    b.source = "phone"
    return b


class Telegram:
    def __init__(self, token: str, chat_ids, handler, api=None):
        """handler(text) -> reply text. api(method, **params) -> parsed result; injectable for tests."""
        self.token, self.chats, self.handler = token, set(chat_ids), handler
        self._api = api or self._http
        self.offset = None
        self.ignored = 0
        self._stop = threading.Event()

    # ---- transport ----
    def _http(self, method: str, **params):
        body = json.dumps(params).encode()
        req = urllib.request.Request(f"{API}/bot{self.token}/{method}", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=params.get("timeout", 0) + 15) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Telegram {method} failed: HTTP {e.code}") from None  # message only: the URL holds the token
        except Exception as e:
            raise RuntimeError(f"Telegram {method} failed: {type(e).__name__}") from None
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data.get('description', 'unknown error')}")
        return data["result"]

    def send(self, text: str, chat_id=None):
        """Send to one chat (default: every allowed chat). Never raises."""
        for chat in ([chat_id] if chat_id is not None else sorted(self.chats)):
            for i in range(0, max(len(text), 1), CHUNK):
                try:
                    self._api("sendMessage", chat_id=chat, text=text[i:i + CHUNK] or "(empty)")
                except RuntimeError as e:
                    print(f"({e})")
                    break

    # ---- receiving ----
    def skip_backlog(self) -> int:
        """Drop everything queued while Clock was off. Returns how many messages were dropped."""
        updates = self._api("getUpdates", offset=-1, timeout=0)
        if not updates:
            return 0
        self.offset = updates[-1]["update_id"] + 1
        return len(updates)

    def poll_once(self, timeout: int = 25, now=None):
        now = now if now is not None else time.time()
        params = {"timeout": timeout, "allowed_updates": ["message"]}
        if self.offset is not None:
            params["offset"] = self.offset
        for u in self._api("getUpdates", **params):
            self.offset = u["update_id"] + 1
            m = u.get("message") or {}
            chat = (m.get("chat") or {}).get("id")
            sender = (m.get("from") or {}).get("id")
            text = (m.get("text") or "").strip()
            # a private chat's id equals the user's id; requiring both stops a group the bot was added to
            if chat not in self.chats or sender != chat or (m.get("chat") or {}).get("type") != "private":
                self.ignored += 1
                continue
            if not text or now - m.get("date", 0) > MAX_AGE:
                continue
            self.send(self._reply(text[:MAX_TEXT]), chat)

    def _reply(self, text: str) -> str:
        if text.lower() in ("/start", "/help", "help"):
            return "Send me a request as text, like you would say it. I can't open apps or use the screen from here."
        try:
            return plain(self.handler(text) or "") or "(no answer)"
        except Exception as e:
            return f"Something went wrong: {type(e).__name__}."

    # ---- loop ----
    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="telegram").start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        try:
            dropped = self.skip_backlog()
            if dropped:
                self.send(f"I was offline. I ignored {dropped} queued message(s); send them again if they still matter.")
        except RuntimeError as e:
            print(f"({e})")
        delay = 2
        while not self._stop.is_set():
            try:
                self.poll_once()
                delay = 2
            except RuntimeError as e:
                print(f"({e}; retrying in {delay}s)")
                self._stop.wait(delay)
                delay = min(delay * 2, 60)


def from_config(handler):
    """A Telegram channel if token and chat ids are configured, else None."""
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHATS):
        return None
    return Telegram(C.TELEGRAM_TOKEN, C.TELEGRAM_CHATS, handler)


def pair():
    """`python -m clock.remote`: print the chat ids that message the bot, so you can put yours in .env."""
    if not C.TELEGRAM_TOKEN:
        raise SystemExit("Set CLOCK_TELEGRAM_TOKEN in .env first (see docs/remote_inbox.md).")
    bot = Telegram(C.TELEGRAM_TOKEN, [], lambda t: "")
    print("Send any message to your bot now (waiting 60 s)...")
    seen = {}
    end = time.time() + 60
    while time.time() < end:
        for u in bot._api("getUpdates", timeout=10, **({"offset": bot.offset} if bot.offset else {})):
            bot.offset = u["update_id"] + 1
            m = u.get("message") or {}
            if (m.get("chat") or {}).get("type") == "private":
                seen[m["chat"]["id"]] = (m.get("from") or {}).get("first_name", "?")
        if seen:
            break
    if not seen:
        raise SystemExit("No messages seen.")
    for cid, name in seen.items():
        print(f"chat id {cid} ({name})  ->  CLOCK_TELEGRAM_CHAT={cid}")


if __name__ == "__main__":
    pair()
