import urllib.error

import pytest

from clock import config as C
from clock import remote, tools

ME = 111


class FakeApi:
    def __init__(self, updates=()):
        self.updates, self.sent, self.calls = list(updates), [], []

    def __call__(self, method, **params):
        self.calls.append((method, params))
        if method == "getUpdates":
            out, self.updates = self.updates, []
            return out
        if method == "sendMessage":
            self.sent.append((params["chat_id"], params["text"]))
        return []


def msg(update_id, text, chat=ME, sender=None, kind="private", date=1000):
    return {"update_id": update_id, "message": {"text": text, "date": date,
                                                "chat": {"id": chat, "type": kind},
                                                "from": {"id": chat if sender is None else sender}}}


def bot(api, handler=lambda t: "ok: " + t):
    return remote.Telegram("TOKEN", [ME], handler, api=api)


def test_answers_allowed_chat():
    api = FakeApi([msg(5, "what time is it")])
    b = bot(api)
    b.poll_once(now=1010)
    assert api.sent == [(ME, "ok: what time is it")]
    assert b.offset == 6


def test_ignores_strangers_groups_and_spoofed_senders():
    api = FakeApi([msg(1, "hi", chat=999), msg(2, "hi", kind="group"), msg(3, "hi", sender=999)])
    b = bot(api)
    b.poll_once(now=1010)
    assert api.sent == [] and b.ignored == 3
    assert b.offset == 4  # still acknowledged, so they are not delivered again


def test_old_messages_are_not_run():
    ran = []
    api = FakeApi([msg(1, "lock everything", date=1000)])
    bot(api, lambda t: ran.append(t) or "x").poll_once(now=1000 + remote.MAX_AGE + 1)
    assert ran == [] and api.sent == []


def test_long_message_is_cut_and_long_reply_is_split():
    seen = []
    api = FakeApi([msg(1, "a" * 5000)])
    bot(api, lambda t: seen.append(len(t)) or "r" * 9000).poll_once(now=1001)
    assert seen == [remote.MAX_TEXT]
    assert [len(t) for _, t in api.sent] == [remote.CHUNK, remote.CHUNK, 9000 - 2 * remote.CHUNK]


def test_handler_error_is_reported_not_raised():
    def boom(t):
        raise ValueError("secret detail")
    api = FakeApi([msg(1, "x")])
    bot(api, boom).poll_once(now=1001)
    assert api.sent == [(ME, "Something went wrong: ValueError.")]


def test_help_does_not_call_the_model():
    api = FakeApi([msg(1, "/start")])
    bot(api, lambda t: pytest.fail("model called")).poll_once(now=1001)
    assert "can't open apps" in api.sent[0][1]


def test_skip_backlog_drops_queued_messages():
    api = FakeApi([msg(7, "old one"), msg(8, "old two")])
    b = bot(api)
    assert b.skip_backlog() == 2
    assert b.offset == 9 and api.sent == []


def test_send_failure_does_not_raise():
    def api(method, **p):
        raise RuntimeError("Telegram sendMessage failed: HTTP 500")
    bot(api).send("hello")  # must not raise


def test_errors_never_contain_the_token(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("https://api.telegram.org/botSECRETTOKEN/getUpdates unreachable")
    monkeypatch.setattr(remote.urllib.request, "urlopen", boom)
    b = remote.Telegram("SECRETTOKEN", [ME], lambda t: "")
    with pytest.raises(RuntimeError) as e:
        b._http("getUpdates")
    assert "SECRETTOKEN" not in str(e.value) and "SECRETTOKEN" not in repr(e.value.__cause__)


def test_not_configured_means_no_channel(monkeypatch):
    monkeypatch.setattr(C, "TELEGRAM_TOKEN", "")
    monkeypatch.setattr(C, "TELEGRAM_CHATS", [ME])
    assert remote.from_config(lambda t: "") is None
    monkeypatch.setattr(C, "TELEGRAM_TOKEN", "t")
    monkeypatch.setattr(C, "TELEGRAM_CHATS", [])
    assert remote.from_config(lambda t: "") is None


def test_safe_tool_set_is_real_and_excludes_dangerous_tools():
    names = {schema["name"] for schema in tools.TOOLS}
    assert remote.SAFE_TOOLS <= names, remote.SAFE_TOOLS - names
    assert not remote.SAFE_TOOLS & {"open_app", "close_app", "open_url", "open_search_in_browser",
                                    "clipboard", "windows", "look"}


def test_phone_brain_is_restricted_and_refuses_confirmations(monkeypatch):
    monkeypatch.setattr(C, "REMOTE_TOOLS", "safe")
    b = remote.make_brain(lambda t: None)
    exposed = {t["function"]["name"] for t in b.tools}
    assert exposed and exposed <= remote.SAFE_TOOLS
    assert b.confirm("close it?") is False and b.source == "phone"
    monkeypatch.setattr(C, "REMOTE_TOOLS", "all")
    assert remote.make_brain(lambda t: None).allowed is None
