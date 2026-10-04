"""Background tasks: a research job that runs in its own thread while Clock keeps listening, then announces the result.

A task gets its own Brain that can only READ (web, files, weather, time). It cannot open, close, save, copy or
schedule anything, and any confirmation it would need is refused. Text it reads from the web is untrusted, so
the worst a bad page can do is mislead the summary, not act on your PC. Tasks live in memory: a restart drops them.
"""
import itertools
import threading
import time

from . import audit
from . import config as C

READ_ONLY = {"web_search", "read_webpage", "read_file", "search_files", "read_notes", "weather", "get_time",
             "system_info", "list_reminders"}
MAX_RUNNING = 2
MAX_KEPT = 20
TIMEOUT = 300  # seconds; a task past this is abandoned and its late result is dropped
_EXTRA = ("\nThis is a background research task. Use the tools to find the answer, then reply with a spoken summary "
          "of at most four short sentences. Do not ask questions; if something is missing, say what you could not find.")

_lock = threading.Lock()
_tasks = []  # newest last; each: dict(id, goal, status, result, started, ended)
_ids = itertools.count(1)


def _new_brain():
    from .brain import Brain
    return Brain(lambda t: None, lambda q: False, allowed=READ_ONLY, system_extra=_EXTRA)


def _running() -> list:
    return [t for t in _tasks if t["status"] == "running"]


def start(goal: str, speak, brain_factory=None) -> str:
    goal = goal.strip()
    if not goal:
        return "What should I look into?"
    with _lock:
        if len(_running()) >= MAX_RUNNING:
            return f"I'm already working on {MAX_RUNNING} things. Ask me to cancel one or wait."
        task = {"id": next(_ids), "goal": goal, "status": "running", "result": "", "started": time.time(), "ended": 0.0}
        _tasks.append(task)
        del _tasks[:-MAX_KEPT]
    threading.Thread(target=_run, args=(task, speak, brain_factory or _new_brain), daemon=True).start()
    return f"On it. Task {task['id']}: {goal}. I'll tell you when it's done."


def _finish(task: dict, status: str, result: str) -> bool:
    """Set the outcome unless the task was already cancelled or timed out. True if this call decided it."""
    with _lock:
        if task["status"] != "running":
            return False
        task.update(status=status, result=result, ended=time.time())
        return True


def _run(task: dict, speak, brain_factory):
    try:
        result = brain_factory().ask(task["goal"]).strip() or "I found nothing to report."
        status = "done"
    except Exception as e:
        result, status = f"It failed: {type(e).__name__}.", "failed"
    if time.time() - task["started"] > TIMEOUT:
        _finish(task, "timed out", "It took too long.")
        return
    if _finish(task, status, result):
        audit.record("background_task", {"goal": task["goal"]}, "ok" if status == "done" else "error", result)
        try:
            speak(f"Task {task['id']} is finished. {result}" if status == "done"
                  else f"Task {task['id']}, {task['goal']}, didn't work out. {result}")
        except Exception as e:
            print(f"(task announce error: {e})")


def _match(key: str):
    key = (key or "").lower().strip().lstrip("#")
    hits = [t for t in _tasks if str(t["id"]) == key] or [t for t in _tasks if key and key in t["goal"].lower()]
    return hits[-1] if hits else None


def listing() -> str:
    with _lock:
        _expire()
        if not _tasks:
            return "No background tasks."
        return "\n".join(f"[{t['id']}] {t['status']}: {t['goal']}" for t in _tasks)


def result(key: str) -> str:
    with _lock:
        _expire()
        t = _match(key)
        if not t:
            return "No matching task."
        return f"Task {t['id']} ({t['status']}): " + (t["result"] or "still working.")


def cancel(key: str) -> str:
    with _lock:
        t = _match(key)
        if not t:
            return "No matching task."
        if t["status"] != "running":
            return f"Task {t['id']} already {t['status']}."
        t.update(status="cancelled", result="", ended=time.time())
    return f"Cancelled task {t['id']}. Its thread finishes quietly and its answer is dropped."


def _expire():
    """Mark running tasks past the timeout (caller holds the lock). Their late answer is then discarded."""
    now = time.time()
    for t in _running():
        if now - t["started"] > TIMEOUT:
            t.update(status="timed out", result="It took too long.", ended=now)
