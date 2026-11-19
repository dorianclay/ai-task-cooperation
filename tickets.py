#!/usr/bin/env python3
"""Coding tickets for the stated-vs-done study: MBPP+ items and a grader.

Each ticket is a small Python function with the original MBPP tests (3 asserts).
Submitted code runs in a separate, isolated Python process with a timeout, no network
and no file writes (macOS sandbox-exec when available).

Run with:  python3 -I tickets.py --validate     (checks every reference solution passes)
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import argparse, gzip, json, shutil, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor

DATA = os.path.join(HERE, "data", "mbppplus", "MbppPlus.jsonl.gz")
TIMEOUT = 10  # seconds per grading run
SANDBOX = shutil.which("sandbox-exec")
PROFILE = "(version 1)(allow default)(deny network*)(deny file-write*)"


def load():
    """All tickets as dicts: id, task (text shown to the agent), entry_point, tests, reference."""
    out = []
    with gzip.open(DATA, "rt") as f:
        for line in f:
            r = json.loads(line)
            task = r["prompt"].strip().strip('"').strip()
            out.append(dict(id=r["task_id"], task=task, entry_point=r["entry_point"],
                            tests=r["assertion"], reference=r["canonical_solution"]))
    return out


def grade(code, ticket):
    """True if `code` passes the ticket's tests. Any error, timeout or crash is a fail."""
    program = code + "\n\n" + ticket["tests"] + "\nprint('TICKET_OK')\n"
    cmd = [sys.executable, "-I", "-c", program]
    if SANDBOX:
        cmd = [SANDBOX, "-p", PROFILE] + cmd
    try:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=tmp,
                               env={"PATH": "/usr/bin:/bin"}, stdin=subprocess.DEVNULL)
        return r.returncode == 0 and r.stdout.strip().endswith("TICKET_OK")
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def usable():
    """Tickets whose reference solution passes its own tests here (cached in tickets_ok.json)."""
    cache = os.path.join(HERE, "data", "tickets_ok.json")
    items = load()
    if os.path.exists(cache):
        ok = set(json.load(open(cache)))
    else:
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda t: grade(t["reference"], t), items))
        ok = {t["id"] for t, good in zip(items, res) if good}
        json.dump(sorted(ok), open(cache, "w"))
    return [t for t in items if t["id"] in ok]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    items = load()
    good = usable()
    print(f"{len(items)} tickets loaded, {len(good)} usable (reference passes its tests)")
    print("sandbox:", "sandbox-exec, no network, no file writes" if SANDBOX else "none (plain subprocess)")
    t = good[0]
    print("example ticket:", t["id"], "\n" + t["task"])
    print("wrong answer graded:", grade(f"def {t['entry_point']}(*a):\n    return None", t))
    print("infinite loop graded:", grade("while True: pass", t))
    print("network attempt graded:", grade(
        "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=5)\n" + t["reference"], t))
    print("file write graded:", grade("open('/tmp/claude_ticket_probe.txt','w').write('x')\n" + t["reference"], t))
