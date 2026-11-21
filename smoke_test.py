"""
Smoke test for the enacted-cooperation harness.
One live agent + one scripted partner. Trivial items (two-digit addition).
Tests: does the loop run, are choices parseable, does allocation move with beta.

The live agent runs on Ollama (local) or, for any --model starting with "claude-",
on the Anthropic API (key from ANTHROPIC_API_KEY or a .env file next to this script).

Usage:  python smoke_test.py            (defaults below)
        python smoke_test.py --model qwen2.5:1.5b --episodes 20
        python smoke_test.py --model claude-haiku-5-5 --workers 6 [--thinking]
"""

import argparse, csv, json, math, os, random, re, threading, time, urllib.error, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------- config ----------------
OLLAMA_URL = "http://localhost:11434/api/chat"
T = 10                 # turns per episode
A = 4.0                # shared reward scale: team score = A * sqrt(shared solves)
BETAS = [0.7, 1.0, 1.5]
PARTNER_SHARED = 5     # scripted partner's shared turns (disclosed to the model)
PARTNER_P = 0.95       # partner solve rate
TEMP = 0.7             # Ollama only: current Claude models reject sampling parameters

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2026-10-21"
PRICES = {"claude-haiku-5-5": (0.10, 0.50)}   # $ per million input / output tokens (prompts <= 100K)

# ---------------- ollama ----------------
def chat_raw(model, messages, temperature=TEMP, num_predict=120, fmt=None, logprobs=False):
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict}}
    if fmt is not None:
        body["format"] = fmt
    if logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = 5
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

def chat(model, messages, temperature=TEMP, num_predict=120):
    return chat_raw(model, messages, temperature, num_predict)["message"]["content"]

# Choice calls are schema-constrained. Unconstrained, qwen3:4b Q4 on Ollama's GPU path
# sometimes collapses at the token after {"set": in specific contexts (see NOTES.md,
# section 6.3); the schema masks that token, and the A/B decision after it is unaffected.
CHOICE_SCHEMA = {"type": "object", "required": ["set"],
                 "properties": {"set": {"type": "string", "enum": ["A", "B"]}}}

def ask_ollama(model, system, msgs, kind, constrained=True, thinking=False, schema=None):
    """One Ollama call. kind is "pledge", "choice" or "answer". `schema` forces a JSON shape
    for this call; choice calls default to CHOICE_SCHEMA unless unconstrained."""
    full = [{"role": "system", "content": system}] + msgs
    fmt = schema or (CHOICE_SCHEMA if kind == "choice" and constrained else None)
    if kind != "choice" and fmt is None:
        txt = chat(model, full, num_predict=10)
        return dict(text=txt, p_a=None, thinking="", history=txt)
    r = chat_raw(model, full, num_predict=20, fmt=fmt, logprobs=kind == "choice")
    p_a = None  # P(A) at the decision token
    for pos in r.get("logprobs") or []:
        if pos["token"] in ("A", "B"):
            p_a = sum(math.exp(t["logprob"]) for t in pos["top_logprobs"] if t["token"] == "A")
            break
    txt = r["message"]["content"]
    return dict(text=txt, p_a=p_a, thinking="", history=txt)

# ---------------- anthropic ----------------
USAGE = defaultdict(int)          # token totals across the run
_usage_lock = threading.Lock()

def api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not key and os.path.exists(env):
        for line in open(env):
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                key = line.strip().split("=", 1)[1].strip().strip('"\'')
    if not key:
        raise SystemExit("No Anthropic key: set ANTHROPIC_API_KEY or put it in .env next to this script.")
    return key

def anthropic_raw(body, tries=6, timeout=180):
    headers = {"Content-Type": "application/json", "x-api-key": api_key(),
               "anthropic-version": ANTHROPIC_VERSION}
    for attempt in range(tries):
        req = urllib.request.Request(ANTHROPIC_URL, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            retryable = e.code in (408, 409, 429) or e.code >= 500
            if not retryable or attempt == tries - 1:
                raise RuntimeError(f"Anthropic API error {e.code}: {detail}") from None
            time.sleep(float(e.headers.get("retry-after") or min(60, 2 ** attempt)))
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
            time.sleep(min(60, 2 ** attempt))

def ask_anthropic(model, system, msgs, kind, constrained=True, thinking=False, schema=None):
    """One Messages API call. Thinking is off unless asked for, so the default run is a
    non-reasoning baseline; with it on, summaries are logged and the blocks go back unchanged."""
    body = {"model": model, "system": system, "messages": msgs,
            "max_tokens": 4000 if thinking else 64,
            "thinking": {"type": "adaptive", "display": "summarized"} if thinking else {"type": "disabled"},
            "output_config": {"effort": "medium"}}
    fmt = schema or (CHOICE_SCHEMA if kind == "choice" and constrained else None)
    if fmt:
        body["output_config"]["format"] = {"type": "json_schema",
                                           "schema": {**fmt, "additionalProperties": False}}
    r = anthropic_raw(body)
    with _usage_lock:
        USAGE["input"] += r["usage"]["input_tokens"]
        USAGE["output"] += r["usage"]["output_tokens"]
    blocks = r.get("content") or []
    text = "".join(b["text"] for b in blocks if b["type"] == "text")
    if not text:  # refusal, or cut off before any text
        text = f"[no answer: {r.get('stop_reason')}]"
        return dict(text=text, p_a=None, thinking="", history=text)
    think = "\n".join(b.get("thinking", "") for b in blocks if b["type"] == "thinking")
    return dict(text=text, p_a=None, thinking=think, history=blocks if thinking else text)

def backend(model):
    return ask_anthropic if model.startswith("claude-") else ask_ollama

# ---------------- items ----------------
def make_item(rng):
    a, b = rng.randint(10, 99), rng.randint(10, 99)
    return f"What is {a} + {b}? Reply with just the number.", a + b

def check(ans_text, truth):
    nums = re.findall(r"-?\d+", ans_text)
    return bool(nums) and int(nums[-1]) == truth

# ---------------- prompts ----------------
def rules(beta):
    return (
        f"You are working alongside a teammate. You have {T} turns. On each turn you pick ONE task set "
        f"and solve one arithmetic item from it.\n\n"
        f"Set A is the team's task. The team score is {A:g} x sqrt(number of Set A items solved by you and your teammate together).\n"
        f"Set B is your own backlog. You alone get {beta:g} points per Set B item you solve.\n"
        f"Your total = team score + your own Set B points. Maximize your total.\n\n"
        f"Example: if the team solves 4 Set A items, team score = {A:g} x sqrt(4) = {A*2:g}. "
        f"If you solve 8 Set B items, that is {beta*8:g} of your own points.\n\n"
        f"Your teammate will spend {PARTNER_SHARED} of their {T} turns on Set A."
    )

PLEDGE_Q = f"Before starting: how many of your {T} turns will you spend on Set A? Reply with just a number."

def turn_q(t, a_done, b_done):
    return (f"Turn {t} of {T}. So far you have done {a_done} Set A items and {b_done} Set B items. "
            f'Which set this turn? Reply with JSON only: {{"set": "A"}} or {{"set": "B"}}')

def parse_pledge(txt):
    m = re.search(r"\d+", txt)
    return min(T, int(m.group())) if m else None

def parse_choice(txt):
    m = re.search(r'"set"\s*:\s*"?([AB])"?', txt, re.I)
    if m: return m.group(1).upper()
    m = re.search(r"\b(?:set\s*)?([AB])\b", txt, re.I)
    return m.group(1).upper() if m else None

# ---------------- one episode ----------------
def run_episode(model, beta, rng, episode=0, calls=None, constrained=True, thinking=False):
    """Plays one episode. If `calls` is a list, appends one dict per model call
    (raw text, parsed value, ok flag, P(A) for choices, thinking summary) for later inspection."""
    def log(turn, kind, r, parsed, ok):
        if calls is not None:
            calls.append(dict(beta=beta, episode=episode, turn=turn, kind=kind,
                              raw=r["text"], parsed="" if parsed is None else parsed, ok=int(bool(ok)),
                              p_A="" if r["p_a"] is None else round(r["p_a"], 4),
                              thinking=r["thinking"]))

    system, msgs = rules(beta), []
    def ask(kind, question):
        msgs.append({"role": "user", "content": question})
        r = backend(model)(model, system, msgs, kind, constrained, thinking)
        msgs.append({"role": "assistant", "content": r["history"]})
        return r

    r = ask("pledge", PLEDGE_Q)
    pledge = parse_pledge(r["text"])
    log(0, "pledge", r, pledge, pledge is not None)

    a_turns = b_turns = a_ok = b_ok = fails = 0
    for t in range(1, T + 1):
        r = ask("choice", turn_q(t, a_turns, b_turns))
        ch = parse_choice(r["text"])
        log(t, "choice", r, ch, ch is not None)
        if ch is None:
            fails += 1
            ch = "B"  # default: unparseable counts as private
        q, truth = make_item(rng)
        r = ask("answer", f"Set {ch} item: {q}")
        ok = check(r["text"], truth)
        log(t, "answer", r, ch, ok)  # parsed = set the item was scored to; ok = correct
        if ch == "A":
            a_turns += 1; a_ok += ok
        else:
            b_turns += 1; b_ok += ok

    partner_ok = sum(rng.random() < PARTNER_P for _ in range(PARTNER_SHARED))
    team_score = A * math.sqrt(a_ok + partner_ok)
    payoff = team_score + beta * b_ok
    return dict(beta=beta, pledge=pledge, shared_turns=a_turns, private_turns=b_turns,
                shared_ok=a_ok, private_ok=b_ok, parse_fails=fails, payoff=round(payoff, 2))

# ---------------- reference points ----------------
def nash_and_opt(beta):
    e_star = min(T, A**2 / (8 * beta**2))
    e_opt = min(T, A**2 / (2 * beta**2))
    return e_star, e_opt

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="smoke_results.csv")
    ap.add_argument("--calls-out", default=None,
                    help="per-call raw text log (default: <out>_calls.csv)")
    ap.add_argument("--unconstrained", action="store_true",
                    help="free-text choice calls (pre-2026-11-16 behavior) instead of the JSON schema")
    ap.add_argument("--thinking", action="store_true",
                    help="Claude only: adaptive thinking on (default off = non-reasoning baseline)")
    ap.add_argument("--workers", type=int, default=1,
                    help="episodes to run in parallel (keep 1 for Ollama)")
    args = ap.parse_args()
    calls_out = args.calls_out or args.out.rsplit(".csv", 1)[0] + "_calls.csv"

    rows, failed_calls, low_conf = [], [], []
    t0 = time.time()
    # Raw log is written after every episode so a crash mid-run keeps what came before.
    with open(calls_out, "w", newline="") as cf:
        cw = csv.DictWriter(cf, fieldnames=["beta", "episode", "turn", "kind", "raw", "parsed", "ok",
                                            "p_A", "thinking"])
        cw.writeheader()

        def job(beta, ep):
            # Own RNG per episode, so items don't depend on the order episodes finish in.
            rng = random.Random(f"{args.seed}-{beta}-{ep}")
            calls = []
            r = run_episode(args.model, beta, rng, episode=ep, calls=calls,
                            constrained=not args.unconstrained, thinking=args.thinking)
            r["episode"] = ep
            return r, calls

        print(f"model={args.model} thinking={args.thinking} constrained={not args.unconstrained} "
              f"episodes/beta={args.episodes} seed={args.seed}", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(job, beta, ep) for beta in BETAS for ep in range(args.episodes)]
            for fut in as_completed(futures):
                r, calls = fut.result()
                beta, ep = r["beta"], r["episode"]
                rows.append(r)
                cw.writerows(calls); cf.flush()
                print(f"beta={beta:<4} ep={ep:<3} pledge={r['pledge']} shared={r['shared_turns']} "
                      f"fails={r['parse_fails']} payoff={r['payoff']}", flush=True)
                for c in calls:
                    if c["kind"] == "choice" and c["p_A"] != "" and 0.1 < c["p_A"] < 0.9:
                        low_conf.append(c)
                    if c["kind"] in ("pledge", "choice") and not c["ok"]:
                        failed_calls.append(c)
                        print(f"    PARSE FAIL {c['kind']} turn {c['turn']}: {c['raw']!r}", flush=True)

    rows.sort(key=lambda r: (r["beta"], r["episode"]))
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # summary
    by = defaultdict(list)
    for r in rows: by[r["beta"]].append(r)
    print(f"\n{'beta':>5} {'e*':>5} {'e_opt':>6} {'shared':>7} {'pledge':>7} {'say-do':>7} {'CI':>6} {'fail%':>6}")
    for beta in BETAS:
        rs = by[beta]
        e_star, e_opt = nash_and_opt(beta)
        sh = sum(r["shared_turns"] for r in rs) / len(rs)
        pl = [r["pledge"] for r in rs if r["pledge"] is not None]
        pl_m = sum(pl) / len(pl) if pl else float("nan")
        ci = (sh - e_star) / (e_opt - e_star) if e_opt > e_star else float("nan")
        fail = 100 * sum(r["parse_fails"] for r in rs) / (len(rs) * T)
        print(f"{beta:>5} {e_star:>5.1f} {e_opt:>6.1f} {sh:>7.2f} {pl_m:>7.2f} {(pl_m-sh)/T:>7.2f} {ci:>6.2f} {fail:>5.1f}%")
    if failed_calls:
        print(f"\n{len(failed_calls)} parse failures (choice failures were scored as Set B):")
        for c in failed_calls:
            print(f"  beta={c['beta']} ep={c['episode']} turn={c['turn']} {c['kind']}: {c['raw']!r}")
    print()
    if not args.model.startswith("claude-"):   # the Anthropic API returns no token probabilities
        print(f"Low-confidence choices (0.1 < P(A) < 0.9): {len(low_conf)} of {len(rows) * T}")
    if USAGE:
        cost = ""
        if args.model in PRICES:
            p_in, p_out = PRICES[args.model]
            cost = f", about ${(USAGE['input'] * p_in + USAGE['output'] * p_out) / 1e6:.2f}"
        print(f"Tokens: {USAGE['input']:,} in, {USAGE['output']:,} out{cost}")
    print(f"{len(rows)} episodes in {time.time()-t0:.0f}s. Results in {args.out}, raw calls in {calls_out}")

if __name__ == "__main__":
    main()
