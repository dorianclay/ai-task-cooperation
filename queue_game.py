#!/usr/bin/env python3
"""Queue game: two live agents, a team board and an own queue, real LeetCode tickets.

Each agent has capacity for T tickets per session and there are several sessions. In the
Done arm the agent takes tickets one at a time from whichever queue it picks. In the Stated
arm it says up front how many it wants from each queue and is handed that split. After each
session both agents get a payout line; nothing about pay is said before that. The agent is
never told the difficulty tier, the payout rule or what the other agent did.
Design: NOTES.md, section 3. Everything the agent reads: prompts/queue_game_v3.json
(--prompts picks another version).

    python3 -I queue_game.py --model fake --pairs 2 --out results/dry/dry       # no API, free
    python3 -I queue_game.py --calib 20 --out results/lc_calib/lc_calib         # solve rates
    python3 -I queue_game.py --pairs 12 --out results/<name>/<name>             # spends money
    python3 -I queue_game.py --summarize results/<name>/<name>                  # table from raw

(-I because the harness reads a downloaded dataset; see lcb.py.)
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import argparse, datetime, gzip, hashlib, json, math, platform, random, re, subprocess, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import smoke_test as st     # API transport, key lookup, prices, token counters
import lcb

T = 4                       # tickets per agent per session (--capacity)
TEAM_RULE, TEAM_RATE = "flat", 0.75     # defaults for --team-rule and --team-rate
OPEN = (38, 41)              # open tickets shown for the two queues at the start of a run (v2 prompts on)
PROMPT_FILE = os.path.join(HERE, "prompts", "queue_game_v3.json")

def load_prompts(path):
    """Everything the agent reads comes from one versioned file."""
    global PROMPT_FILE, P, M
    PROMPT_FILE = path
    with open(path) as f:
        P = json.load(f)
    M = P["messages"]

load_prompts(PROMPT_FILE)
SOURCES = {"team_board": "team", "own_queue": "own"}


# ---------------------------------------------------------------- payout (the only scoring rule)
def payouts(pair_team_closed, own_closed, beta, rule=TEAM_RULE, rate=TEAM_RATE):
    """(team payout to each agent, own payout to this agent), in dollars.
    flat: each team-board ticket the pair closed pays `rate` to each agent (a linear public goods
          game; with rate between 0.5 and 1 times beta, a team ticket costs the agent who does it
          and gains the pair).
    sqrt: rate * sqrt(team-board tickets the pair closed), the rule used up to 2026-11-24."""
    n = pair_team_closed
    team = rate * n if rule == "flat" else rate * math.sqrt(n)
    return round(team, 2), round(beta * own_closed, 2)


# ---------------------------------------------------------------- what the agent reads
def ordered(team_first, team, own):
    return (team, own) if team_first else (own, team)

def brief(variant, team_first):
    b = P["briefs"][variant]
    return "\n\n".join([b["intro"], "\n".join([b["head"], *ordered(team_first, b["team"], b["own"])]),
                        b["capacity"].format(T=T)])

def tools(arm, team_first):
    """The order in which the two queues are named in the tools is a per-pair coin flip,
    separate from the order used in the brief."""
    first, second = ordered(team_first, P["names"]["team"], P["names"]["own"])
    keys = list(ordered(team_first, "team_board", "own_queue"))
    submit = {"name": "submit_solution", "description": P["tools"]["submit_solution"], "strict": True,
              "input_schema": {"type": "object", "properties": {
                  "ticket_id": {"type": "string", "description": P["tools"]["submit_ticket_id"]},
                  "code": {"type": "string", "description": P["tools"]["submit_code"]}},
                  "required": ["ticket_id", "code"], "additionalProperties": False}}
    if arm == "stated":
        pick = {"name": "request_tickets", "strict": True,
                "description": P["tools"]["request_tickets"].format(first=first, second=second),
                "input_schema": {"type": "object", "properties": {k: {"type": "integer"} for k in keys},
                                 "required": keys, "additionalProperties": False}}
    else:
        pick = {"name": "take_ticket", "strict": True,
                "description": P["tools"]["take_ticket"].format(first=first, second=second),
                "input_schema": {"type": "object", "properties": {"source": {"type": "string", "enum": keys}},
                                 "required": ["source"], "additionalProperties": False}}
    return [pick, submit]

def ticket_block(source, tid, ticket):
    return M["ticket"].format(tid=tid, label=P["labels"][source], text=lcb.ticket_text(ticket))

def payout_text(team_first, team_pay, own_pay, items=None):
    """The payout shown after a session. `items` = (team tickets the pair closed, team rate, own
    tickets this agent closed, own rate) gives the itemised lines, where the prompt version has
    them; it is only passed under the flat rule, where tickets x rate is the whole rule."""
    if items and "payout_team_items" in M:
        n_team, team_rate, n_own, own_rate = items
        team = M["payout_team_items"].format(n=n_team, rate=f"{team_rate:.2f}", amount=f"{team_pay:.2f}")
        own = M["payout_own_items"].format(n=n_own, rate=f"{own_rate:.2f}", amount=f"{own_pay:.2f}")
    else:
        team, own = M["payout_team"].format(amount=f"{team_pay:.2f}"), M["payout_own"].format(amount=f"{own_pay:.2f}")
    first, second = ordered(team_first, team, own)
    return M["payout"].format(first=first, second=second)

def opening(arm, team_first, later, open_counts=None):
    """First message of a session. `open_counts` = (team board, own queue) adds a status line with
    the open tickets in each queue; it is shown once, at the start of a run."""
    first, second = ordered(team_first, P["names"]["team"], P["names"]["own"])
    key = ("next_" if later else "") + arm + ("" if later else "_open")
    text = M[key].format(T=T, first=first, second=second)
    if open_counts and not later and "open" in M:
        a, b = ordered(team_first, M["open_team"].format(n=open_counts[0]), M["open_own"].format(n=open_counts[1]))
        text = M["open"].format(first=a, second=b) + "\n\n" + text
    return text

def design(pair, variants):
    """What pair number `pair` reads, the same in every tier, arm and thinking mode: brief wording,
    queue order in the brief, queue order in the tools, and which queue shows more open tickets.
    Twelve consecutive pairs cover every wording x brief order x tool order once; the larger
    count goes to the team board for half the pairs of each wording and of each order."""
    variant, team_first, tool_team_first = pair % variants, (pair // variants) % 2 == 0, (pair // (2 * variants)) % 2 == 0
    team_more = team_first != tool_team_first
    return dict(variant=variant, team_first=team_first, tool_team_first=tool_team_first,
                open_team=OPEN[1] if team_more else OPEN[0], open_own=OPEN[0] if team_more else OPEN[1])


# ---------------------------------------------------------------- one model call
_usage_lock = threading.Lock()

def fake_reply(msgs, tool_list, schema, rng):
    """Stand-in for the model, for free end-to-end runs of the harness (--model fake)."""
    parts = []
    for b in msgs[-1]["content"]:
        parts.append(b.get("text") or (b.get("content") if isinstance(b.get("content"), str) else "") or "")
    blob, names = "\n".join(parts), [t["name"] for t in tool_list]
    def use(name, inp):
        return {"content": [{"type": "tool_use", "id": f"fake_{rng.getrandbits(40):x}", "name": name, "input": inp}],
                "stop_reason": "tool_use", "usage": {"input_tokens": 0, "output_tokens": 0}}
    say = lambda text: {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                        "usage": {"input_tokens": 0, "output_tokens": 0}}
    if schema:
        return say(json.dumps({k: rng.randint(0, T) for k in schema["required"]}))
    if rng.random() < 0.04:
        return say("Working on it.")
    held = re.findall(r"^([TQ]-\d+) \(", blob, re.M) or re.findall(r"^([TQ]-\d+) is still open", blob, re.M)
    if "request_tickets" in names and ("how many" in blob.lower() or "request_tickets" in blob or "add up" in blob):
        a = rng.randint(0, T)
        return use("request_tickets", {"team_board": a, "own_queue": T - a - (1 if rng.random() < 0.1 else 0)})
    if held:
        return use("submit_solution", {"ticket_id": held[-1], "code": "class Solution:\n    pass\n"})
    if "take_ticket" in names:
        return use("take_ticket", {"source": rng.choice(["team_board", "own_queue"])})
    return say("Nothing to do.")

def call(model, system, msgs, thinking, tool_list, schema=None, big=True, rng=None):
    """Tools go on every call so the conversation prefix never changes; a reply that must be
    plain JSON turns tool use off for that one call."""
    if model == "fake":
        return fake_reply(msgs, tool_list, schema, rng)
    body = {"model": model, "system": system, "messages": msgs, "tools": tool_list,
            "cache_control": {"type": "ephemeral"},
            "max_tokens": (16000 if thinking else 6000) if big else (4000 if thinking else 300),
            "thinking": {"type": "adaptive", "display": "summarized"} if thinking else {"type": "disabled"},
            "output_config": {"effort": "medium"}}
    if schema:
        body["tool_choice"] = {"type": "none"}
        body["output_config"]["format"] = {"type": "json_schema", "schema": {**schema, "additionalProperties": False}}
    else:
        body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}
    r = st.anthropic_raw(body, timeout=600)
    with _usage_lock:
        st.USAGE["input"] += r["usage"]["input_tokens"]
        st.USAGE["output"] += r["usage"]["output_tokens"]
        st.USAGE["cache_write"] += r["usage"].get("cache_creation_input_tokens") or 0
        st.USAGE["cache_read"] += r["usage"].get("cache_read_input_tokens") or 0
    return r

def cost(model):
    pin, pout = st.PRICES.get(model, (0, 0))
    u = st.USAGE   # cache writes bill at 1.25x input, cache reads at 0.1x
    return (u["input"] + 1.25 * u["cache_write"] + 0.1 * u["cache_read"]) * pin / 1e6 + u["output"] * pout / 1e6

def raw_of(blocks):
    """Everything the model said or did in one reply, minus thinking, as one loggable string."""
    out = []
    for b in blocks:
        if b["type"] == "text" and b.get("text"):
            out.append(b["text"])
        elif b["type"] == "tool_use":
            out.append(f"TOOL {b.get('name')} " + json.dumps(b.get("input"), ensure_ascii=False))
    return "\n".join(out)


# ---------------------------------------------------------------- append-only raw logs
class Log:
    def __init__(self, out):
        self.out, self.lock = out, threading.Lock()
    def write(self, suffix, records):
        with self.lock, open(self.out + suffix, "a") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


class Invalid(Exception):
    pass


# ---------------------------------------------------------------- one agent
class Agent:
    """One agent's whole conversation. `tickets` is the fixed list it works through: the n-th
    ticket it handles is the same whichever queue it takes it from, so ticket luck cannot differ
    between queues or arms."""
    def __init__(self, model, meta, system, tool_list, tickets, nums, thinking, rng):
        self.model, self.meta, self.system, self.tool_list = model, meta, system, tool_list
        self.tickets, self.nums, self.thinking, self.rng = tickets, nums, thinking, rng
        self.i = 0                                  # index of the next ticket
        self.msgs, self.pending, self.pending_text = [], [], []
        self.rows, self.ncall = [], 0
        self.transcript = ["=== SYSTEM ===\n" + system, "=== TOOLS ===\n" + json.dumps(tool_list, indent=1)]

    def tid(self, source):
        return ("T-" if source == "team" else "Q-") + str(self.nums[self.i])

    def result(self, use, text, error=False):
        block = {"type": "tool_result", "tool_use_id": use["id"], "content": text}
        if error:
            block["is_error"] = True
        self.pending.append(block)
        self.pending_text.append("[tool result] " + text)

    def send(self, text, kind, session, schema=None, big=True):
        content = self.pending + ([{"type": "text", "text": text}] if text else [])
        sent = "\n".join(self.pending_text + ([text] if text else []))
        self.pending, self.pending_text = [], []
        self.msgs.append({"role": "user", "content": content})
        r = call(self.model, self.system, self.msgs, self.thinking, self.tool_list, schema=schema, big=big, rng=self.rng)
        blocks = r.get("content") or []
        if r.get("stop_reason") == "max_tokens":      # a cut-off tool call is not a submission
            blocks = [b for b in blocks if b["type"] != "tool_use"]
        if not blocks:
            blocks = [{"type": "text", "text": "(no reply)"}]
        self.msgs.append({"role": "assistant", "content": blocks})
        self.ncall += 1
        think = "\n".join(b.get("thinking", "") for b in blocks if b["type"] == "thinking")
        u = r.get("usage") or {}
        row = dict(self.meta, session=session, n=self.ncall, kind=kind, sent=sent, raw=raw_of(blocks),
                   stop_reason=r.get("stop_reason"), thinking_text=think, parsed="", ok="",
                   tokens_in=(u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                             + (u.get("cache_read_input_tokens") or 0),
                   tokens_out=u.get("output_tokens") or 0)
        self.rows.append(row)
        self.transcript.append(f"=== USER ({kind}, session {session}) ===\n{sent}")
        if think:
            self.transcript.append("=== MODEL THINKING (summary) ===\n" + think)
        self.transcript.append("=== MODEL ===\n" + row["raw"])
        return blocks, row

    def grade(self, code):
        if self.model == "fake":
            return self.rng.random() < 0.6
        return lcb.grade(code, self.tickets[self.i])

    def do_ticket(self, session, msg, holding, slot):
        """Handle one ticket slot. `holding` is the queue of a ticket already handed over (Stated
        arm) or None (Done arm: the agent must take one first). Returns a record for the slot;
        outcome is closed / failed / none (never submitted)."""
        left, kind = T - slot - 1, "turn"
        rec = dict(slot=slot, source=holding or "", ticket=self.tickets[self.i]["id"], outcome="none")
        for _ in range(6):
            if not msg and not self.pending:
                msg = M["nudge_submit"].format(tid=self.tid(holding)) if holding else M["nudge_take"].format(left=left + 1)
            blocks, row = self.send(msg, kind, session)
            msg = ""
            uses = [b for b in blocks if b["type"] == "tool_use"]
            for extra in uses[1:]:
                self.result(extra, M["err_one"], error=True)
            if not uses:
                row.update(parsed="no tool call", ok=False); kind = "nudge"
                msg = M["nudge_submit"].format(tid=self.tid(holding)) if holding else M["nudge_take"].format(left=left + 1)
                continue
            u, inp = uses[0], uses[0].get("input") or {}
            if u["name"] == "take_ticket":
                source = SOURCES.get(inp.get("source"))
                if holding:
                    self.result(u, M["err_holding"].format(tid=self.tid(holding)), error=True)
                    row.update(parsed="take while holding", ok=False); kind = "fix"
                elif not source:
                    self.result(u, M["err_source"], error=True)
                    row.update(parsed="bad source", ok=False); kind = "fix"
                else:
                    holding = rec["source"] = source
                    self.result(u, ticket_block(source, self.tid(source), self.tickets[self.i]))
                    row.update(parsed=f"take {source}", ok=True); kind = "work"
            elif u["name"] == "submit_solution":
                if not holding:
                    self.result(u, M["err_no_ticket"], error=True)
                    row.update(parsed="submit without ticket", ok=False); kind = "fix"
                    continue
                tid, good = self.tid(holding), self.grade(str(inp.get("code", "")))
                key = ("closed" if good else "failed") + ("_last" if left == 0 else "")
                self.result(u, M[key].format(tid=tid, left=left, T=T))
                row.update(parsed=f"{holding} {tid} {'closed' if good else 'failed'}", ok=True)
                rec["outcome"] = "closed" if good else "failed"
                break
            else:   # request_tickets after the split is set
                self.result(u, M["err_assigned"], error=True)
                row.update(parsed="request after assignment", ok=False); kind = "fix"
        self.i += 1     # one submission per ticket: pass or fail, the next slot gets a new ticket
        return rec

    def play_session(self, session, lead):
        """One session of T tickets. Returns the session record (no payout yet)."""
        res = dict(self.meta, session=session, stated_team="", slots=[])
        if self.meta["arm"] == "stated":
            msg, kind, split = lead, "split", None
            for _ in range(4):
                blocks, row = self.send(msg, kind, session)
                msg, kind = "", "fix"
                uses = [b for b in blocks if b["type"] == "tool_use"]
                for extra in uses[1:]:
                    self.result(extra, M["err_one"], error=True)
                if not uses:
                    row.update(parsed="no tool call", ok=False); msg, kind = M["nudge_request"], "nudge"
                    continue
                u, inp = uses[0], uses[0].get("input") or {}
                if u["name"] != "request_tickets":
                    self.result(u, M["err_no_ticket"], error=True)
                    row.update(parsed="tool before split", ok=False)
                    continue
                try:
                    a, b = int(inp["team_board"]), int(inp["own_queue"])
                except (KeyError, TypeError, ValueError):
                    a, b = -1, -1
                if a < 0 or b < 0 or a + b != T:
                    self.result(u, M["err_split"].format(T=T), error=True)
                    row.update(parsed=f"{a}/{b}", ok=False)
                    continue
                first, second = ordered(self.meta["team_first"],
                                        M["assigned_part"].format(n=a, name=P["names"]["team"]),
                                        M["assigned_part"].format(n=b, name=P["names"]["own"]))
                self.result(u, M["assigned"].format(first=first, second=second))
                row.update(parsed=f"{a}/{b}", ok=True)
                split = (a, b)
                break
            if split is None:
                raise Invalid("no valid split")
            res["stated_team"] = split[0]
            plan = ["team"] * split[0] + ["own"] * split[1]
            self.rng.shuffle(plan)
            for slot, source in enumerate(plan):
                res["slots"].append(self.do_ticket(session, ticket_block(source, self.tid(source), self.tickets[self.i]),
                                                   source, slot))
        else:
            for slot in range(T):
                res["slots"].append(self.do_ticket(session, lead if slot == 0 else "", None, slot))
        s = res["slots"]
        res.update(team_tickets=sum(x["source"] == "team" for x in s), own_tickets=sum(x["source"] == "own" for x in s),
                   none_tickets=sum(x["source"] == "" for x in s),
                   team_closed=sum(x["source"] == "team" and x["outcome"] == "closed" for x in s),
                   own_closed=sum(x["source"] == "own" and x["outcome"] == "closed" for x in s))
        return res

    def belief(self, sessions):
        keys = [f"session_{k}" for k in range(1, sessions + 1)]
        schema = {"type": "object", "required": keys, "properties": {k: {"type": "integer"} for k in keys}}
        q = M["belief_one"].format(T=T) if sessions == 1 else M["belief_many"].format(T=T, S=sessions)
        blocks, row = self.send(M["session_closed"] + "\n\n" + q, "belief", sessions + 1, schema=schema, big=False)
        try:
            d = json.loads("".join(b.get("text", "") for b in blocks if b["type"] == "text"))
            vals = [int(d[k]) for k in keys]
            row.update(parsed=json.dumps(vals), ok=all(0 <= v <= T for v in vals))
            return [v if 0 <= v <= T else None for v in vals]
        except Exception:
            row.update(parsed="unparsed", ok=False)
            return [None] * sessions


# ---------------------------------------------------------------- one pair, all sessions
def run_pair(args, job, log):
    """Both agents play session k at the same time and never see each other. The pair is only
    joined between sessions, to work out the payout each agent is shown."""
    agents = [Agent(args.model, dict(job["meta"], agent=a), job["system"], job["tools"], job["tickets"][a],
                    job["nums"][a], job["thinking"], random.Random(f"{job['seed']}-{a}")) for a in (0, 1)]
    if args.max_cost and cost(args.model) >= args.max_cost:     # spending cap reached: do not start this pair
        records = [dict(job["meta"], agent=a, session=0, pair_complete=False, error="not run: cost cap") for a in (0, 1)]
        log.write("_sessions.jsonl", records)
        return records, ""
    m = job["meta"]
    counts = (m["open_team"], m["open_own"]) if m.get("open_team") else None
    records, error, lead = [], "", [opening(m["arm"], m["team_first"], False, counts)] * 2
    try:
        for k in range(1, args.sessions + 1):
            with ThreadPoolExecutor(2) as ex:
                recs = list(ex.map(lambda p: p[0].play_session(k, p[1]), zip(agents, lead)))
            total = sum(r["team_closed"] for r in recs)
            lead = []
            for r in recs:
                rule, rate = getattr(args, "team_rule", TEAM_RULE), getattr(args, "team_rate", TEAM_RATE)
                team_pay, own_pay = payouts(total, r["own_closed"], args.beta, rule, rate)
                items = (total, rate, r["own_closed"], args.beta) if rule == "flat" else None
                r.update(pair_team_closed=total, team_payout=team_pay, own_payout=own_pay,
                         payout=round(team_pay + own_pay, 2))
                lead.append(payout_text(r["team_first"], team_pay, own_pay, items) + "\n\n"
                            + opening(r["arm"], r["team_first"], True))
            records += recs
        with ThreadPoolExecutor(2) as ex:
            beliefs = list(ex.map(lambda ag: ag.belief(args.sessions), agents))
        for r in records:
            r["belief_other_team"] = beliefs[r["agent"]][r["session"] - 1]
    except Exception as e:      # keep the run alive; the records say what happened
        error = f"{type(e).__name__}: {e}"[:300]
    for r in records:
        r.update(pair_complete=not error, error=error)
    if error and not records:
        records = [dict(job["meta"], agent=a, session=0, pair_complete=False, error=error) for a in (0, 1)]
    log.write("_calls.jsonl", [row for ag in agents for row in ag.rows])
    log.write("_sessions.jsonl", records)
    return records, "\n\n".join(agents[0].transcript)


# ---------------------------------------------------------------- calibration: solve rate per tier
def calibrate(args, log):
    """One ticket, one submission, in a fresh conversation. Gives the solve rate of each tier."""
    jobs = []
    for tier in args.tiers.split(","):
        pool = lcb.load(tier)
        rng = random.Random(f"{args.seed}-calib-{tier}")
        for t in rng.sample(pool, min(args.calib, len(pool))):
            for th in args.thinking.split(","):
                jobs.append((tier, t, th == "on"))
    def one(job):
        tier, t, th = job
        if args.max_cost and cost(args.model) >= args.max_cost:
            return dict(tier=tier, ticket=t["id"], thinking="on" if th else "off", outcome="skipped (cost cap)")
        rng = random.Random(f"{args.seed}-{t['id']}-{th}")
        meta = dict(arm="calib", tier=tier, thinking="on" if th else "off", ticket=t["id"], model=args.model)
        ag = Agent(args.model, meta, brief(0, True), tools("done", True), [t], [rng.randrange(1000, 10000)], th, rng)
        try:        # the first ticket of a Done session: the agent takes it, then submits once
            rec = ag.do_ticket(1, opening("done", True, False), None, 0)
            out = dict(meta, source=rec["source"], outcome=rec["outcome"], tokens_out=sum(r["tokens_out"] for r in ag.rows),
                       tokens_in=sum(r["tokens_in"] for r in ag.rows), error="")
        except Exception as e:
            out = dict(meta, source="", outcome="error", error=f"{type(e).__name__}: {e}"[:300])
        log.write("_calls.jsonl", ag.rows)
        log.write("_calib.jsonl", [out])
        return out
    with ThreadPoolExecutor(args.workers) as ex:
        return list(ex.map(one, jobs))

def print_calib(rows):
    print(f"\n{'tier':8}{'think':7}{'n':>4}{'closed':>8}{'rate':>7}{'no submit':>11}{'out tok/ticket':>16}")
    cells = defaultdict(list)
    for r in rows:
        cells[(r["tier"], r["thinking"])].append(r)
    for (tier, th), rs in sorted(cells.items(), key=lambda kv: (lcb.TIERS.index(kv[0][0]), kv[0][1])):
        v = [r for r in rs if r["outcome"] in ("closed", "failed", "none")]
        k = sum(r["outcome"] == "closed" for r in v)
        tok = sum(r.get("tokens_out", 0) for r in v) / max(len(v), 1)
        print(f"{tier:8}{th:7}{len(v):>4}{k:>8}{(100 * k / len(v) if v else 0):>6.0f}%"
              f"{sum(r['outcome'] == 'none' for r in v):>11}{tok:>16.0f}"
              + (f"   ({len(rs) - len(v)} not run: errors or cost cap)" if len(v) < len(rs) else ""))


# ---------------------------------------------------------------- summary (from the raw records)
def read_jsonl(path):
    if not os.path.exists(path) and os.path.exists(path + ".gz"):      # large logs are gzipped in git
        with gzip.open(path + ".gz", "rt") as f:
            return [json.loads(line) for line in f if line.strip()]
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

def summarize(out):
    everything = read_jsonl(out + "_sessions.jsonl")
    rows = [r for r in everything if r.get("session")]
    bad = sorted({(r["tier"], r["arm"], r["thinking"], r["pair"]) for r in everything if not r["pair_complete"]})
    cells = defaultdict(list)
    for r in rows:
        if r["pair_complete"]:
            cells[(r["tier"], r["arm"], r["thinking"], r["session"])].append(r)
    print(f"\n{'tier':8}{'arm':8}{'think':7}{'sess':>5}{'agents':>8}{'team tickets':>14}{'closed%':>9}"
          f"{'no ticket':>11}{'payout $':>10}{'belief':>8}")
    for key in sorted(cells, key=lambda k: (lcb.TIERS.index(k[0]), k[1], k[2], k[3])):
        rs = cells[key]
        team = [r["stated_team"] if r["arm"] == "stated" else r["team_tickets"] for r in rs]
        worked = sum(r["team_tickets"] + r["own_tickets"] for r in rs)
        closed = sum(r["team_closed"] + r["own_closed"] for r in rs)
        bel = [r["belief_other_team"] for r in rs if r.get("belief_other_team") is not None]
        print(f"{key[0]:8}{key[1]:8}{key[2]:7}{key[3]:>5}{len(rs):>8}{sum(team) / len(rs):>14.2f}"
              f"{(100 * closed / worked if worked else 0):>8.0f}%{sum(r['none_tickets'] for r in rs):>11}"
              f"{sum(r['payout'] for r in rs) / len(rs):>10.2f}"
              + (f"{sum(bel) / len(bel):>8.2f}" if bel else f"{'':>8}"))
    print("team tickets = how many of an agent's tickets went to the team board (Stated: the split it asked for; Done: what it took).")
    if bad:
        print(f"{len(bad)} pair(s) dropped as incomplete:", bad)


# ---------------------------------------------------------------- run
def git_state():
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=HERE, capture_output=True, text=True).stdout.strip())
        return head, dirty
    except OSError:
        return "", None

def main():
    global T
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-5-5", help="'fake' runs the harness with no API calls")
    ap.add_argument("--tiers", default="easy,medium,hard")
    ap.add_argument("--arms", default="stated,done")
    ap.add_argument("--thinking", default="off,on")
    ap.add_argument("--pairs", type=int, default=2)
    ap.add_argument("--sessions", type=int, default=7)
    ap.add_argument("--capacity", type=int, default=T, help="tickets per agent per session")
    ap.add_argument("--beta", type=float, default=1.0, help="dollars per own-queue ticket closed (never shown in advance)")
    ap.add_argument("--team-rule", choices=("flat", "sqrt"), default=TEAM_RULE, help="see payouts()")
    ap.add_argument("--team-rate", type=float, default=TEAM_RATE, help="flat: dollars per team ticket to each agent; "
                    "sqrt: the multiplier (runs up to 2026-11-24 used sqrt with 4, capacity 10)")
    ap.add_argument("--workers", type=int, default=6, help="pairs (or calibration tickets) run at once")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--calib", type=int, default=0, help="calibration: tickets per tier, one submission each")
    ap.add_argument("--max-cost", type=float, default=0, help="stop starting new work once this many dollars are spent")
    ap.add_argument("--summarize", default="", help="print the table for an existing run and exit")
    ap.add_argument("--prompts", default="", help="prompt file; default is the newest version")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.prompts:
        load_prompts(os.path.abspath(args.prompts))
    T = args.capacity
    if args.summarize:
        return summarize(args.summarize)
    if not args.out:
        ap.error("--out is required")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    for suffix in ("_calls.jsonl", "_sessions.jsonl", "_calib.jsonl"):
        if os.path.exists(args.out + suffix) or os.path.exists(args.out + suffix + ".gz"):
            ap.error(f"{args.out + suffix} exists; pick a new --out (raw logs are append-only)")
    head, dirty = git_state()
    with open(PROMPT_FILE, "rb") as f:
        prompt_sha = hashlib.sha256(f.read()).hexdigest()
    run = dict(run_id=os.path.basename(args.out) + "-" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S"),
               date=datetime.datetime.now().isoformat(timespec="seconds"), git_commit=head, git_dirty=dirty,
               args=vars(args), T=T, prompts=P["version"], prompts_sha256=prompt_sha,
               backend="fake" if args.model == "fake" else "anthropic-api", python=platform.python_version(),
               sandbox="sandbox-exec" if lcb.SANDBOX else "none",
               tickets={t: len(lcb.load(t)) for t in lcb.TIERS})
    with open(args.out + "_run.json", "w") as f:
        json.dump(run, f, indent=1)
    log, t0 = Log(args.out), time.time()

    if args.calib:
        rows = calibrate(args, log)
        print_calib(rows)
        print(f"tokens in/out {st.USAGE['input'] + st.USAGE['cache_write'] + st.USAGE['cache_read']}/{st.USAGE['output']}, "
              f"cost ${cost(args.model):.2f}, {time.time() - t0:.0f}s")
        return

    need = args.sessions * T
    jobs = []
    for tier in args.tiers.split(","):
        pool = lcb.load(tier)
        if len(pool) < need:
            ap.error(f"tier {tier} has {len(pool)} tickets; {need} are needed per agent "
                     f"({args.sessions} sessions x {T}). Add more LiveCodeBench files or lower --sessions.")
        for pair in range(args.pairs):
            # wording and order depend on the pair number only (matched across tiers, arms and
            # thinking modes); tickets depend on the tier and pair (matched across arms and modes)
            d = design(pair, len(P["briefs"]))
            rng = random.Random(f"{args.seed}-{tier}-{pair}")
            if len(pool) >= 2 * need:
                drawn = rng.sample(pool, 2 * need)
                tickets = [drawn[:need], drawn[need:]]
            else:       # small pool: the two agents may see some of the same tickets
                tickets = [rng.sample(pool, need), rng.sample(pool, need)]
            nums = rng.sample(range(1000, 10000), 2 * need)
            for arm in args.arms.split(","):
                for th in args.thinking.split(","):
                    meta = dict(d, arm=arm, tier=tier, thinking=th, pair=pair, model=args.model)
                    if "open" not in M:     # older prompt versions show no open-ticket line
                        meta.update(open_team=0, open_own=0)
                    jobs.append(dict(meta=meta, system=brief(d["variant"], d["team_first"]),
                                     tools=tools(arm, d["tool_team_first"]),
                                     tickets=tickets, nums=[nums[:need], nums[need:]], thinking=th == "on",
                                     seed=f"{args.seed}-{tier}-{pair}-{arm}-{th}"))
    jobs.sort(key=lambda j: j["meta"]["pair"])   # pair by pair, so a spending cap cuts every condition evenly
    logs, done = {}, 0
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {}
        for j in jobs:
            futs[ex.submit(run_pair, args, j, log)] = j["meta"]
        for f in as_completed(futs):
            _, transcript = f.result()
            m = futs[f]
            if m["pair"] == 0 and transcript:
                logs[(m["tier"], m["arm"], m["thinking"])] = transcript
            done += 1
            if done % 5 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} pairs, ${cost(args.model):.2f}, {time.time() - t0:.0f}s", flush=True)
    with open(args.out + ".log", "w") as f:
        for key in sorted(logs):
            f.write(f"\n\n########## tier={key[0]} arm={key[1]} thinking={key[2]} (pair 0, agent 0)\n\n")
            f.write(logs[key])
    summarize(args.out)
    print(f"tokens in/out {st.USAGE['input'] + st.USAGE['cache_write'] + st.USAGE['cache_read']}/{st.USAGE['output']}, "
          f"cost ${cost(args.model):.2f}, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
