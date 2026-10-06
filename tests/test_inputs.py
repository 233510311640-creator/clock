import pytest

from clock import audit, inputs

YES, NO = (lambda q: True), (lambda q: False)


@pytest.fixture
def machine(monkeypatch):
    """Replace the functions that touch the machine; record what would have happened."""
    log = []
    monkeypatch.setattr(inputs, "_foreground_title", lambda: "Notepad")
    monkeypatch.setattr(inputs, "_send_unicode", lambda t: log.append(("type", t)))
    monkeypatch.setattr(inputs, "_press", lambda v: log.append(("keys", v)))
    monkeypatch.setattr(inputs, "_mouse", lambda x, y, b, n: log.append(("click", x, y, b, n)))
    monkeypatch.setattr(inputs, "_wheel", lambda n: log.append(("wheel", n)))
    monkeypatch.setattr(inputs, "_screen_box", lambda: (0, 0, 1920, 1080))
    inputs.forget_approval()
    return log


def test_key_names():
    assert inputs.parse_keys("ctrl+c") == [0x11, 0x43]
    assert inputs.parse_keys("Ctrl + Shift + T") == [0x11, 0x10, 0x54]
    assert inputs.parse_keys("f5") == [0x74] and inputs.parse_keys("enter") == [0x0D]
    assert inputs.parse_keys("ctrl+banana") is None and inputs.parse_keys("") is None


def test_asks_first_and_names_the_window(machine):
    asked = []
    assert inputs.type_text("hello", lambda q: asked.append(q) or False) == "User declined."
    assert asked == ["Type 5 characters in Notepad?"] and machine == []


def test_one_yes_covers_the_next_actions_for_a_minute(machine):
    asked = []
    ask = lambda q: asked.append(q) or True  # noqa: E731
    inputs.type_text("a", ask)
    inputs.press_keys("enter", ask)
    inputs.scroll("down", 3, ask)
    assert len(asked) == 1 and [m[0] for m in machine] == ["type", "keys", "wheel"]


def test_approval_expires(machine, monkeypatch):
    inputs.type_text("a", YES)
    monkeypatch.setattr(inputs.time, "time", lambda: inputs._approved_until + 1)
    asked = []
    inputs.type_text("b", lambda q: asked.append(q) or True)
    assert asked


def test_risky_combos_ask_every_time(machine):
    inputs.type_text("a", YES)  # approval is now open
    asked = []
    assert inputs.press_keys("Alt+F4", lambda q: asked.append(q) or False) == "User declined."
    assert asked and ("keys",) not in machine and all(m[0] != "keys" for m in machine)


def test_unknown_keys_and_empty_text(machine):
    assert "don't know the key" in inputs.press_keys("ctrl+banana", YES)
    assert inputs.type_text("", YES) == "Nothing to type."
    assert "too long" in inputs.type_text("x" * 3000, YES)
    assert machine == []


def test_click_checks_the_screen_and_scroll_direction(machine):
    assert "off the screen" in inputs.click(5000, 5, YES)
    assert machine == []
    assert inputs.click(100, 200, YES, "right", True) == "Clicked at 100,200."
    assert machine[-1] == ("click", 100, 200, "right", 2)
    inputs.scroll("up", 4, YES)
    inputs.scroll("down", 99, YES)
    assert machine[-2:] == [("wheel", 4), ("wheel", -30)]


def test_audit_marks_input_tools_as_writes():
    for name in ("type_text", "press_keys", "mouse_click", "scroll"):
        assert audit.risk(name) == "write"


def test_tools_registered_without_confirm_in_schema():
    from clock.tools import TOOLS
    by = {t["name"]: t["input_schema"] for t in TOOLS}
    for name in ("type_text", "press_keys", "mouse_click", "scroll"):
        assert name in by and "confirm" not in by[name]["properties"]
    assert by["mouse_click"]["properties"]["button"]["enum"] == ["left", "right", "middle"]
