import itertools
import threading
import time

import pytest

from clock import config as C
from clock import tasks


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(tasks, "_tasks", [])
    monkeypatch.setattr(tasks, "_ids", itertools.count(1))


class FakeBrain:
    def __init__(self, answer="Found it.", gate=None, boom=False):
        self.answer, self.gate, self.boom = answer, gate, boom

    def ask(self, goal):
        if self.gate:
            self.gate.wait(5)
        if self.boom:
            raise RuntimeError("model down")
        return self.answer


def wait_for(cond, secs=3):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_task_announces_result():
    said = []
    msg = tasks.start("compare laptops", said.append, lambda: FakeBrain("Laptop A wins."))
    assert "Task 1" in msg
    assert wait_for(lambda: said)
    assert said[0] == "Task 1 is finished. Laptop A wins."
    assert "done: compare laptops" in tasks.listing()
    assert "Laptop A wins." in tasks.result("1")


def test_failure_is_announced_not_raised():
    said = []
    tasks.start("x", said.append, lambda: FakeBrain(boom=True))
    assert wait_for(lambda: said)
    assert "didn't work out" in said[0] and "RuntimeError" in said[0]


def test_concurrency_limit():
    gate, said = threading.Event(), []
    for _ in range(tasks.MAX_RUNNING):
        tasks.start("slow", said.append, lambda: FakeBrain(gate=gate))
    assert "already working" in tasks.start("third", said.append, lambda: FakeBrain())
    gate.set()
    assert wait_for(lambda: len(said) == tasks.MAX_RUNNING)


def test_cancel_drops_late_answer():
    gate, said = threading.Event(), []
    tasks.start("slow thing", said.append, lambda: FakeBrain(gate=gate))
    assert tasks.cancel("slow").startswith("Cancelled task 1")
    gate.set()
    time.sleep(0.2)
    assert said == []
    assert "cancelled" in tasks.listing()


def test_timeout_drops_late_answer(monkeypatch):
    gate, said = threading.Event(), []
    monkeypatch.setattr(tasks, "TIMEOUT", 0.05)
    tasks.start("slow", said.append, lambda: FakeBrain(gate=gate))
    time.sleep(0.1)
    assert "timed out" in tasks.listing()
    gate.set()
    time.sleep(0.2)
    assert said == []


def test_empty_goal_and_unknown_match():
    assert tasks.start("  ", print) == "What should I look into?"
    assert tasks.result("9") == "No matching task."
    assert tasks.cancel("9") == "No matching task."


def test_background_brain_is_read_only():
    b = tasks._new_brain()
    names = {t["function"]["name"] for t in b.tools}
    assert names and names <= tasks.READ_ONLY
    assert not names & {"remember", "open_app", "close_app", "set_reminder", "add_routine", "start_task", "clipboard"}
    assert b.confirm("anything?") is False
