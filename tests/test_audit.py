from clock import audit
from clock import config as C
from clock import tools


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "AUDIT_FILE", tmp_path / "audit.jsonl")


def test_record_and_tail(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    audit.record("open_app", {"name": "notepad"}, "ok", "Opened notepad.")
    audit.record("close_app", {"name": "notepad"}, "declined", "User declined.", tainted=True)
    rows = audit.tail(5)
    assert [r["tool"] for r in rows] == ["open_app", "close_app"]
    assert rows[0]["risk"] == "write" and rows[1]["risk"] == "destructive"
    assert rows[1]["outcome"] == "declined" and rows[1]["after_untrusted"] is True


def test_long_values_are_clipped(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    audit.record("add_note", {"text": "x" * 5000}, "ok", "y" * 5000)
    row = audit.tail(1)[0]
    assert len(row["args"]["text"]) < 300 and len(row["result"]) < 200


def test_log_rotates(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(audit, "MAX_BYTES", 200)
    for _ in range(10):
        audit.record("get_time", {}, "ok", "x")
    assert (tmp_path / "audit.jsonl.1").exists()


def test_clipboard_risk_depends_on_action():
    assert audit.risk("clipboard", {"action": "read"}) == "read"
    assert audit.risk("clipboard", {"action": "write"}) == "write"


def test_outcome_of():
    assert audit.outcome_of("User declined.") == "declined"
    assert audit.outcome_of("Tool error: boom") == "error"
    assert audit.outcome_of("Opened.") == "ok"


def test_never_raises_when_unwritable(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "AUDIT_FILE", tmp_path / "no" / "such" / "dir" / "a.jsonl")
    audit.record("get_time", {}, "ok")  # must not raise
    assert audit.tail() == []


def test_recent_actions_tool(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    assert tools.run_tool("recent_actions", {}, None, None) == "No actions logged yet."
    audit.record("get_time", {}, "ok", "x")
    assert "get_time" in tools.run_tool("recent_actions", {"count": 3}, None, None)
