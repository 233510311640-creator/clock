import json

import pytest

from clock import config, tools
from clock.tools import TOOLS, run_tool


def test_schema_generated_from_hints():
    t = {x["name"]: x for x in TOOLS}
    vol = t["volume"]["input_schema"]
    assert vol["required"] == ["action"]
    assert vol["properties"]["action"]["enum"][0] == "get"
    assert vol["properties"]["level"] == {"type": "integer"}
    assert "required" not in t["get_time"]["input_schema"]
    assert t["set_timer"]["input_schema"]["required"] == ["seconds"]
    # confirm/speak are injected by run_tool and must never be offered to the model
    assert "confirm" not in t["windows"]["input_schema"]["properties"]
    assert {"clipboard", "windows", "look"} <= set(t)


def test_every_tool_schema_is_json_serialisable():
    json.dumps(TOOLS)


def test_run_tool_unknown_and_missing_arg():
    assert run_tool("nope", {}, None, None) == "Unknown tool nope"
    assert run_tool("remember", {}, None, None) == "Tool error: missing fact"


def test_run_tool_ignores_extra_args_and_injects_confirm(monkeypatch):
    seen = {}
    monkeypatch.setattr(tools.windows, "control", lambda a, t, c: seen.update(a=a, t=t, c=c) or "ok")
    assert run_tool("windows", {"action": "close", "target": "x", "bogus": 1}, None, "CONFIRM") == "ok"
    assert seen == {"a": "close", "t": "x", "c": "CONFIRM"}


def test_run_tool_reports_exceptions(monkeypatch):
    monkeypatch.setattr(tools.web, "search", lambda q: 1 / 0)
    assert run_tool("web_search", {"query": "x"}, None, None).startswith("Tool error")


def test_read_file_stays_inside_allowed_dir(tmp_path, monkeypatch):
    (tmp_path / "ok.txt").write_text("hello")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    monkeypatch.setattr(config, "ALLOWED_DIR", tmp_path.resolve())
    assert run_tool("read_file", {"path": "ok.txt"}, None, None) == "hello"
    assert "outside" in run_tool("read_file", {"path": "../secret.txt"}, None, None)
    assert "outside" in run_tool("read_file", {"path": str(outside)}, None, None)


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# c\nCLOCK_TESTVAL="from file"\nCLOCK_TESTKEEP=file\n\nbad line\n')
    monkeypatch.setenv("CLOCK_TESTKEEP", "real")
    monkeypatch.delenv("CLOCK_TESTVAL", raising=False)
    config._load_dotenv(f)
    assert config.os.environ["CLOCK_TESTVAL"] == "from file"
    assert config.os.environ["CLOCK_TESTKEEP"] == "real"
    config._load_dotenv(tmp_path / "missing.env")  # no error


def test_env_prefers_clock_then_edith(monkeypatch):
    monkeypatch.delenv("CLOCK_ZZ", raising=False)
    monkeypatch.delenv("EDITH_ZZ", raising=False)
    assert config._env("ZZ", "d") == "d"
    monkeypatch.setenv("EDITH_ZZ", "old")
    assert config._env("ZZ", "d") == "old"
    monkeypatch.setenv("CLOCK_ZZ", "new")
    assert config._env("ZZ", "d") == "new"
