#!/usr/bin/env python3
"""LeetCode tickets with easy / medium / hard labels, from LiveCodeBench, and a grader.

Each ticket is a LeetCode problem: a statement, starter code (`class Solution` with one
method) and hidden tests. Submitted code runs in a separate, isolated Python process with a
time limit, no network and no file writes (macOS sandbox-exec when available; a plain
subprocess elsewhere, which is NOT a sandbox).

Data: put LiveCodeBench `test*.jsonl` files in data/livecodebench/ (see README.md), then

    python3 -I lcb.py --build      # one-off: extract the LeetCode problems into a small file
    python3 -I lcb.py --check      # counts per tier, and grader self-checks

The hidden tests in LiveCodeBench are a pickled string. They are decoded with an unpickler
that refuses every global, so loading the dataset cannot run code.
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import argparse, base64, glob, gzip, io, json, pickle, re, secrets, shutil, subprocess, tempfile, threading, zlib
from collections import Counter

RAW_DIR = os.path.join(HERE, "data", "livecodebench")
CACHE = os.path.join(RAW_DIR, "leetcode_tickets.jsonl.gz")
TIERS = ("easy", "medium", "hard")
PER_TEST_SECONDS = 6      # LiveCodeBench's per-test limit, counted here as CPU time so that a busy
                          # machine (many graders at once) cannot turn a correct answer into a timeout
TOTAL_SECONDS = 600       # wall-clock hard stop for one grading run (catches code that sleeps or hangs)
_SLOTS = threading.BoundedSemaphore(max(2, (os.cpu_count() or 4) - 2))   # graders running at once
SANDBOX = shutil.which("sandbox-exec")
PROFILE = "(version 1)(allow default)(deny network*)(deny file-write*)"


class _NoGlobals(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"refused to load {module}.{name}")


def _hidden_tests(field):
    try:
        return json.loads(field)
    except ValueError:
        raw = zlib.decompress(base64.b64decode(field))
        return json.loads(_NoGlobals(io.BytesIO(raw)).load())


def build():
    """Extract LeetCode problems from the raw LiveCodeBench files into one compact file."""
    seen, n = set(), Counter()
    with gzip.open(CACHE, "wt") as out:
        for path in sorted(glob.glob(os.path.join(RAW_DIR, "test*.jsonl"))):
            with open(path) as f:
                for line in f:
                    r = json.loads(line)
                    if r["platform"] != "leetcode" or r["question_id"] in seen:
                        continue
                    func = json.loads(r["metadata"]).get("func_name")
                    tests = json.loads(r["public_test_cases"]) + _hidden_tests(r["private_test_cases"])
                    tests = [[t["input"], t["output"]] for t in tests if t.get("testtype") == "functional"]
                    if not func or not tests or r["difficulty"] not in TIERS:
                        continue
                    seen.add(r["question_id"]); n[r["difficulty"]] += 1
                    out.write(json.dumps(dict(
                        id=f"lc/{r['question_id']}", title=r["question_title"], tier=r["difficulty"],
                        date=r["contest_date"][:10], task=r["question_content"].strip(),
                        starter=r["starter_code"].rstrip() + "\n", func=func, tests=tests)) + "\n")
    return n


def load(tier=None):
    """All tickets (or one tier) as dicts: id, title, tier, date, task, starter, func, tests."""
    if not os.path.exists(CACHE):
        raise SystemExit(f"{CACHE} is missing. Run: python3 -I lcb.py --build")
    with gzip.open(CACHE, "rt") as f:
        items = [json.loads(line) for line in f]
    return [t for t in items if tier is None or t["tier"] == tier]


def ticket_text(ticket):
    """What the agent is shown for a ticket."""
    task = re.sub(r"\n\s*\n+", "\n\n", ticket["task"])     # the source leaves runs of blank lines
    return f"{task}\n\nStarter code:\n\n{ticket['starter']}"


# Runs inside the isolated process. Reads {"code", "func", "tests", "token"} on stdin.
_RUNNER = r'''
import sys, json, signal, math as _math
data = json.load(sys.stdin)
ns = {"__name__": "__ticket__"}
exec("""from string import *
from re import *
from datetime import *
from collections import *
from heapq import *
from bisect import *
from copy import *
from math import *
from random import *
from statistics import *
from itertools import *
from functools import *
from operator import *
from builtins import *
from typing import *
import string, re, datetime, collections, heapq, bisect, copy, math, random, statistics
import itertools, functools, operator, io, sys, json
sys.setrecursionlimit(50000)
""", ns)
exec(data["code"], ns)
def same(got, want):
    if isinstance(want, list):
        return isinstance(got, (list, tuple)) and len(got) == len(want) and all(same(g, w) for g, w in zip(got, want))
    if isinstance(want, float) or isinstance(got, float):      # decimal answers: LeetCode accepts 1e-5
        ok = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        return ok(got) and ok(want) and _math.isclose(got, want, rel_tol=1e-5, abs_tol=1e-5)
    return got == want
def too_slow(*_):
    raise TimeoutError
signal.signal(signal.SIGPROF, too_slow)
for given, expected in data["tests"]:
    args = [json.loads(line) for line in given.split("\n")]
    signal.setitimer(signal.ITIMER_PROF, data["per_test"])
    got = getattr(ns["Solution"](), data["func"])(*args)
    signal.setitimer(signal.ITIMER_PROF, 0)
    if not same(got, json.loads(expected)):
        sys.exit(3)
sys.stdout.write("\n" + data["token"])
'''


def grade(code, ticket):
    """True if `code` passes every test of the ticket. Any error, timeout or crash is a fail."""
    token = secrets.token_hex(16)   # the pass marker is unguessable, so printing it cannot fake a pass
    payload = json.dumps(dict(code=str(code), func=ticket["func"], tests=ticket["tests"],
                              token=token, per_test=PER_TEST_SECONDS))
    cmd = [sys.executable, "-I", "-c", _RUNNER]
    if SANDBOX:
        cmd = [SANDBOX, "-p", PROFILE] + cmd
    try:
        with _SLOTS, tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=TOTAL_SECONDS,
                               cwd=tmp, env={"PATH": "/usr/bin:/bin"})
        return r.returncode == 0 and r.stdout.endswith("\n" + token)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.build:
        print("extracted:", dict(build()))
    if args.check:
        items = load()
        print("tickets per tier:", {t: sum(x["tier"] == t for x in items) for t in TIERS},
              "| dates", min(x["date"] for x in items), "to", max(x["date"] for x in items))
        print("sandbox:", "sandbox-exec, no network, no file writes" if SANDBOX else "none (plain subprocess)")
        t = items[0]
        print("example ticket:", t["id"], t["title"], f"({t['tier']}, {len(t['tests'])} tests)")
        stub = t["starter"] + "        "
        print("wrong answer graded:", grade(stub + "return None", t))
        print("printing a fake pass marker graded:", grade("print('TICKET_OK')\nimport sys\nsys.exit(0)", t))
        print("infinite loop graded:", grade(stub + "while True: pass", t))
        print("network attempt graded:", grade(
            "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=5)\n" + stub + "return None", t))
        print("file write graded:", grade("open('/tmp/claude_ticket_probe.txt','w').write('x')\n" + stub + "return None", t))
