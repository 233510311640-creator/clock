import datetime

from clock import memory, reminders
from clock.__main__ import strip_wake


def test_strip_wake():
    assert strip_wake("Clock, what time is it?") == "what time is it?"
    assert strip_wake("hey clock open notepad") == "open notepad"
    assert strip_wake("Okay Klock") == ""
    assert strip_wake("what a clockwork orange") is None


def test_strip_wake_tolerates_mishearings_only_after_a_greeting():
    assert strip_wake("Hey Clark, what time is it?") == "what time is it?"
    assert strip_wake("hi click open notepad") == "open notepad"
    assert strip_wake("Hello, cluck.") == ""
    assert strip_wake("click the button") is None
    assert strip_wake("lock the screen") is None
    assert strip_wake("Clark is here") is None


def test_see_you_ends_session_only_for_her_name():
    from clock.__main__ import SEE_YOU
    assert SEE_YOU.search("See you Clock")
    assert SEE_YOU.search("see you, clark")
    assert not SEE_YOU.search("see you, lock the door")


def test_memory_roundtrip_and_dedupe():
    assert memory.remember("Sister's birthday is 14 March") == "Remembered."
    assert memory.remember("sister's birthday is 14 march") == "I already know that."
    assert "14 March" in memory.prompt_block()
    assert memory.forget("birthday").startswith("Forgot")
    assert memory.forget("birthday") == "I don't have anything like that."
    assert memory.prompt_block() == ""


def test_memory_empty_and_cap():
    assert memory.remember("   ") == "Nothing to remember."
    for i in range(memory.MAX_FACTS + 10):
        memory.remember(f"fact {i}")
    assert len(memory._load()) == memory.MAX_FACTS
    assert "fact 0 " not in memory.prompt_block()


def test_memory_corrupt_file_is_empty():
    memory.C.MEMORY_FILE.write_text("{not json", encoding="utf-8")
    assert memory._load() == []


def test_reminder_add_list_cancel():
    due = datetime.datetime.now() + datetime.timedelta(hours=1)
    item = reminders.add(due, "stretch")
    assert "stretch" in reminders.listing()
    assert reminders.cancel("nothing") == "No matching reminder."
    assert reminders.cancel(item["id"]).startswith("Cancelled 1")
    assert reminders.listing() == "No reminders or timers pending."


def test_pop_due_only_returns_past():
    now = datetime.datetime.now()
    reminders.add(now - datetime.timedelta(minutes=5), "old")
    reminders.add(now + datetime.timedelta(hours=1), "later")
    due = reminders._pop_due()
    assert [i["text"] for i in due] == ["old"]
    assert [i["text"] for i in reminders._load()] == ["later"]


def test_late_reminder_line():
    old = reminders.add(datetime.datetime.now() - datetime.timedelta(hours=3), "tea")
    assert reminders._line(old).startswith("While I was off")
    fresh = {"due": datetime.datetime.now().isoformat(), "text": "tea", "kind": "timer"}
    assert reminders._line(fresh) == "tea is done."


def test_parse_and_describe():
    assert reminders.parse_when("2026-03-14 08:00") == datetime.datetime(2026, 3, 14, 8, 0)
    assert reminders.parse_when("2026-03-14T08:00") == datetime.datetime(2026, 3, 14, 8, 0)
    now = datetime.datetime.now().replace(hour=9, minute=5)
    assert reminders.describe(now) == "today at 9:05 AM"
    assert reminders.describe(now + datetime.timedelta(days=1)).startswith("tomorrow")
