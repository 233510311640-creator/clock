"""Benchmark Ollama models as Clock's brain: does each pick the right tool with the right arguments, and how fast.

    python scripts/llm_bench.py qwen3.5:9b-q4_K_M gpt-oss:20b gemma4:e4b [--repeats 2] [--json out.json]

Uses Clock's real Brain, system prompt and tool schemas, but every tool is stubbed: nothing is opened, saved,
set or sent, and the audit log is left alone. Models are only loaded and unloaded, never changed or removed.
Do not run it while another job (Cypher's timed runs) needs the GPU.
"""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clock import audit, brain as B, config as C  # noqa: E402


def _has(calls, tool, **want):
    """True if some call is `name` whose arguments contain each wanted value (str: substring, else equal)."""
    for n, a in calls:
        if n != tool:
            continue
        ok = True
        for k, v in want.items():
            got = a.get(k)
            if isinstance(v, str):
                ok = ok and isinstance(got, str) and v in got.lower()
            else:
                ok = ok and got is not None and str(got) == str(v)
        if ok:
            return True
    return False


def _names(calls):
    return [n for n, _ in calls]


# (prompt, check(calls) -> bool, what a pass means)
TASKS = [
    # the system prompt already holds the time, so a spoken time is as good as calling get_time
    ("what time is it", lambda c, r="": _has(c, "get_time") or bool(re.search(r"\d{1,2}[:.]\d{2}", r)), "get_time or spoken time"),
    ("open notepad", lambda c: _has(c, "open_app", name="notepad"), "open_app notepad"),
    ("open brave", lambda c: _has(c, "open_app", name="brave"), "open_app brave"),
    # windows(close) is fine too: it asks "Close <title>?" before closing, like close_app does
    ("close chrome", lambda c, r="": _has(c, "close_app", name="chrome") or _has(c, "windows", action="close", target="chrome"),
     "close_app or windows close chrome"),
    ("set the volume to forty", lambda c: _has(c, "volume", action="set", level=40), "volume set 40"),
    ("mute", lambda c: _has(c, "volume", action="mute"), "volume mute"),
    ("pause the music", lambda c: _has(c, "media", action="play_pause"), "media play_pause"),
    ("set a timer for five minutes", lambda c: _has(c, "set_timer", seconds=300), "set_timer 300"),
    ("remind me in ten minutes to stretch", lambda c: _has(c, "set_reminder", minutes_from_now=10), "set_reminder 10m"),
    ("what's the weather in New Delhi", lambda c: _has(c, "weather"), "weather"),
    ("what's on my screen", lambda c: _has(c, "look", source="screen"), "look screen"),
    ("remember that my sister's birthday is the 14th of March", lambda c: _has(c, "remember", fact="14"), "remember"),
    ("copy hello world to my clipboard", lambda c: _has(c, "clipboard", action="write", text="hello"), "clipboard write"),
    ("snap this window to the left", lambda c: _has(c, "windows", action="snap_left"), "windows snap_left"),
    ("every weekday at eight give me the weather",
     lambda c: _has(c, "add_routine", at="08:00", days="weekdays"), "add_routine 08:00 weekdays"),
    ("search the web for the latest Ollama release", lambda c: _has(c, "web_search", query="ollama"), "web_search"),
    ("open notepad and set a timer for two minutes",
     lambda c: _has(c, "open_app", name="notepad") and _has(c, "set_timer", seconds=120), "open_app + set_timer (2 calls)"),
    ("find my cypher report in my files and read it",
     lambda c: _has(c, "search_files", query="cypher") and _names(c).count("read_file") >= 1, "search_files then read_file"),
    ("what files are on my desktop", lambda c: _has(c, "list_folder", path="desktop"), "list_folder desktop"),
    ("save a file called ideas.txt on my desktop saying buy milk",
     lambda c: _has(c, "write_file", path="ideas.txt", text="milk"), "write_file ideas.txt"),
    ("move ideas.txt from my desktop into documents",
     lambda c: _has(c, "move_file", src="ideas.txt", dst="documents"), "move_file"),
    ("delete ideas.txt from my desktop", lambda c: _has(c, "delete_file", path="ideas.txt"), "delete_file"),
    ("what is my IP address", lambda c: _has(c, "run_command", command="ipconfig") or _has(c, "run_command", command="get-net"),
     "run_command ipconfig"),
    ("type hello world", lambda c: _has(c, "type_text", text="hello world"), "type_text"),
    ("press control c", lambda c: _has(c, "press_keys", keys="ctrl+c"), "press_keys ctrl+c"),
    ("scroll down a bit", lambda c: _has(c, "scroll", direction="down"), "scroll down"),
    ("what is two plus two", lambda c: not c, "no tool"),
    ("tell me a joke", lambda c: not c, "no tool"),
]

STUB = {
    "get_time": "Wednesday 07 October 2026, 04:10 PM",
    "search_files": "C:\\Users\\User\\Documents\\cypher_report.txt",
    "read_file": "Cypher evaluation report: accuracy 91%.",
    "weather": "Clear, 31 C, high 34 C.",
    "web_search": "1. Ollama 0.32.13 released. https://ollama.com",
    "windows": "Done.", "volume": "Volume set.", "media": "Done.",
}


# a 1x1 PNG: enough for a vision model to accept an image, nothing of the user's screen
_PIXEL = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _post(path, body, timeout=600):
    req = urllib.request.Request(f"{C.OLLAMA_URL}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def unload(model):
    try:
        _post("/api/generate", {"model": model, "keep_alive": 0}, timeout=60)
    except Exception:
        pass


def run_task(prompt):
    calls = []

    def fake_tool(name, args, speak, confirm):
        calls.append((name, dict(args)))
        return STUB.get(name, "Done.")

    def fake_capture(source="screen"):  # `look` is handled inside Brain, not run_tool: record it, never grab the real screen
        calls.append(("look", {"source": source}))
        return _PIXEL

    B.run_tool = fake_tool
    B.capture = fake_capture
    brain = B.Brain(lambda t: None, lambda q: True)
    first = []
    t0 = time.perf_counter()
    reply = brain.ask(prompt, lambda s: first.append(time.perf_counter() - t0) if not first else None)
    total = time.perf_counter() - t0
    return calls, reply, (first[0] if first else total), total


def bench(model, repeats, only=None):
    C.MODEL = model
    t0 = time.perf_counter()
    B.Brain(lambda t: None, lambda q: True).ask("hi")  # loads the model; not timed as a task
    load = time.perf_counter() - t0
    rows = []
    for prompt, check, label in TASKS:
        if only and only not in prompt:
            continue
        for _ in range(repeats):
            calls, reply, first, total = run_task(prompt)
            row = {"prompt": prompt, "expect": label, "pass": bool(check(calls, reply) if check.__code__.co_argcount > 1 else check(calls)), "first": first,
                   "total": total, "calls": [(n, a) for n, a in calls], "reply": reply[:160]}
            rows.append(row)
            print(f"  {'ok  ' if row['pass'] else 'FAIL'} {total:5.1f}s  {prompt[:50]:<50} -> "
                  f"{[n for n, _ in calls] or 'no tool'}", flush=True)
    return {"model": model, "load_s": load, "rows": rows}


def summary(res):
    rows = res["rows"]
    tot = sorted(r["total"] for r in rows)
    return {
        "model": res["model"], "pass": sum(r["pass"] for r in rows), "n": len(rows), "load_s": res["load_s"],
        "first_med": statistics.median(r["first"] for r in rows), "total_med": statistics.median(tot),
        "total_p90": tot[min(len(tot) - 1, int(len(tot) * 0.9))],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--json")
    ap.add_argument("--only", help="run only tasks whose prompt contains this text")
    args = ap.parse_args()

    audit.record = lambda *a, **k: None  # the benchmark must not write to the real audit log
    original = C.MODEL
    results = []
    try:
        for m in args.models:
            print(f"\n=== {m} ===", flush=True)
            try:
                res = bench(m, args.repeats, args.only)
            except Exception as e:
                print(f"  skipped: {type(e).__name__}: {e}")
                continue
            results.append(res)
            if m != original:
                unload(m)
    finally:
        C.MODEL = original

    print("\nmodel".ljust(46) + "pass     load   first(med)  total(med)  total(p90)")
    for s in map(summary, results):
        print(f"{s['model']:<45} {s['pass']:>2}/{s['n']:<4} {s['load_s']:5.1f}s {s['first_med']:9.1f}s {s['total_med']:10.1f}s "
              f"{s['total_p90']:10.1f}s")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
