#!/usr/bin/env python3
"""Tables for a queue_game.py run, computed from its raw records.

    python3 -I analyze_queue.py results/<name>/<name>             # session 1 tables, then all sessions
    python3 -I analyze_queue.py results/<name>/<name> 3           # the session tables for session 3

Unit of analysis: the pair. Agents of a pair are averaged first, and standard errors are
taken across pairs. The gap is Done minus Stated for the same pair (same wording, order and
tickets in both arms).
"""
import gzip, json, math, os, sys
from collections import Counter, defaultdict

TIERS = ("easy", "medium", "hard")


def read(path):
    """Read a JSON-lines file; the large call logs are stored gzipped in git (path + ".gz")."""
    if not os.path.exists(path) and os.path.exists(path + ".gz"):
        with gzip.open(path + ".gz", "rt") as f:
            return [json.loads(line) for line in f if line.strip()]
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

def mean(v):
    return sum(v) / len(v) if v else float("nan")

def se(v):
    if len(v) < 2:
        return float("nan")
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v))

def team(r):
    """Team-board tickets: what was asked for (Stated) or what was taken (Done)."""
    return r["stated_team"] if r["arm"] == "stated" else r["team_tickets"]

def by_pair(rows, value):
    """Mean of `value` over the agents of each pair -> {pair: mean}."""
    d = defaultdict(list)
    for r in rows:
        d[r["pair"]].append(value(r))
    return {p: mean(v) for p, v in d.items()}


def sessions_table(everything, tiers, cap):
    """All sessions side by side, and what agents do after seeing a payout."""
    rows = [r for r in everything if r.get("session") and r["pair_complete"]]
    last = max(r["session"] for r in rows)
    if last < 2:
        return
    print(f"\n\nAll sessions. Mean team-board tickets per agent, out of {cap} (pair-level standard error of the last session).")
    print(f"{'tier':8}{'think':7}{'arm':8}" + "".join(f"{'s' + str(k):>6}" for k in range(1, last + 1)) + f"{'se':>7}{'last - first':>14}")
    for tier in tiers:
        for th in ("off", "on"):
            for arm in ("stated", "done"):
                rs = [r for r in rows if (r["tier"], r["thinking"], r["arm"]) == (tier, th, arm)]
                if not rs:
                    continue
                per = {k: by_pair([r for r in rs if r["session"] == k], team) for k in range(1, last + 1)}
                both = sorted(set(per[1]) & set(per[last]))
                d = [per[last][p] - per[1][p] for p in both]
                print(f"{tier:8}{th:7}{arm:8}" + "".join(f"{mean(list(per[k].values())):>6.2f}" for k in range(1, last + 1))
                      + f"{se(list(per[last].values())):>7.2f}{mean(d):>+9.2f} ({se(d):.2f})")

    agents = defaultdict(dict)
    for r in rows:
        agents[(r["tier"], r["thinking"], r["arm"], r["pair"], r["agent"])][r["session"]] = r
    print("\nWhat agents saw and did (agents; an agent 'tried the board' if it took or asked for a team ticket in any session):")
    for th in ("off", "on"):
        for arm in ("stated", "done"):
            a = [v for k, v in agents.items() if k[1] == th and k[2] == arm]
            if not a:
                continue
            tried = sum(any(team(r) > 0 for r in v.values()) for v in a)
            paid = sum(any(r["team_payout"] > 0 for k, r in v.items() if k < last) for v in a)
            print(f"  {arm:7} thinking {th:4} {len(a)} agents; tried the board: {tried}; saw a team payout above $0 before the last session: {paid}")
    print("\nNext session's change in team tickets, by what the last payout showed (mean change; agent-sessions):")
    for th in ("off", "on"):
        for arm in ("stated", "done"):
            groups = defaultdict(list)
            for k, v in agents.items():
                if k[1] != th or k[2] != arm:
                    continue
                for n in range(1, last):
                    if n in v and n + 1 in v:
                        r = v[n]
                        mine, n_team = team(r), r["pair_team_closed"]
                        other = "other closed some" if n_team - r["team_closed"] > 0 else "other closed none"
                        me = "I took some" if mine > 0 else "I took none"
                        groups[(me, other)].append(team(v[n + 1]) - mine)
            if groups:
                print(f"  {arm:7} thinking {th:4} " + "; ".join(f"{a}, {b}: {mean(x):+.2f} ({len(x)})" for (a, b), x in sorted(groups.items())))


def main(out, session=1):
    everything = read(out + "_sessions.jsonl")
    try:
        with open(out + "_run.json") as f:
            cap = json.load(f).get("T", 10)
    except OSError:
        cap = 10
    rows = [r for r in everything if r.get("session") == session and r["pair_complete"]]
    dropped = Counter((r["tier"], r["arm"], r["thinking"]) for r in everything if not r["pair_complete"] and r["agent"] == 0)
    cell = defaultdict(list)
    for r in rows:
        cell[(r["tier"], r["thinking"], r["arm"])].append(r)
    tiers = [t for t in TIERS if any(k[0] == t for k in cell)]

    print(f"Session {session}. Team-board tickets per agent, out of {cap}. Standard errors across pairs in brackets.\n")
    print(f"{'tier':8}{'think':7}{'pairs':>6}{'closed%':>9}{'Stated':>14}{'Done':>14}{'gap (Done - Stated)':>22}{'all own S/D':>13}{'all team S/D':>14}")
    for tier in tiers:
        for th in ("off", "on"):
            s, d = cell.get((tier, th, "stated"), []), cell.get((tier, th, "done"), [])
            if not s and not d:
                continue
            ps, pd = by_pair(s, team), by_pair(d, team)
            both = sorted(set(ps) & set(pd))
            gaps = [pd[p] - ps[p] for p in both]
            worked = sum(r["team_tickets"] + r["own_tickets"] for r in s + d)
            closed = sum(r["team_closed"] + r["own_closed"] for r in s + d)
            share = lambda rs, n: f"{sum(team(r) == n for r in rs)}/{len(rs)}"
            print(f"{tier:8}{th:7}{len(both):>6}{100 * closed / max(worked, 1):>8.0f}%"
                  f"{mean(list(ps.values())):>8.2f} ({se(list(ps.values())):.2f})"
                  f"{mean(list(pd.values())):>8.2f} ({se(list(pd.values())):.2f})"
                  f"{mean(gaps):>+15.2f} ({se(gaps):.2f})"
                  f"{share(s, 0) + ' ' + share(d, 0):>13}{share(s, cap) + ' ' + share(d, cap):>14}")
    if dropped:
        print("\nPairs dropped as incomplete (tier, arm, thinking):", dict(dropped))

    print("\nBelief about the other agent's team-board tickets (mean), next to what the other agent did:")
    for tier in tiers:
        for th in ("off", "on"):
            for arm in ("stated", "done"):
                rs = cell.get((tier, th, arm), [])
                b = [r["belief_other_team"] for r in rs if r.get("belief_other_team") is not None]
                if rs:
                    print(f"  {tier:7} {th:4} {arm:7} belief {mean(b):5.2f}   actual {mean([team(r) for r in rs]):5.2f}   (n={len(b)})")

    print("\nDone arm, by what the brief and tools looked like (mean team tickets; agents):")
    done = [r for r in rows if r["arm"] == "done"]
    for th in ("off", "on"):
        d = [r for r in done if r["thinking"] == th]
        if not d:
            continue
        parts = []
        for v in sorted({r["variant"] for r in d}):
            x = [team(r) for r in d if r["variant"] == v]
            parts.append(f"wording {v + 1}: {mean(x):.1f} ({len(x)})")
        for flag, name in ((True, "team board named first"), (False, "own queue named first")):
            x = [team(r) for r in d if r["team_first"] == flag]
            parts.append(f"{name}: {mean(x):.1f} ({len(x)})")
        print(f"  thinking {th}: " + "; ".join(parts))
    print("Stated arm, the same split:")
    for th in ("off", "on"):
        d = [r for r in rows if r["arm"] == "stated" and r["thinking"] == th]
        if not d:
            continue
        parts = []
        for v in sorted({r["variant"] for r in d}):
            x = [team(r) for r in d if r["variant"] == v]
            parts.append(f"wording {v + 1}: {mean(x):.1f} ({len(x)})")
        for flag, name in ((True, "team board named first"), (False, "own queue named first")):
            x = [team(r) for r in d if r["team_first"] == flag]
            parts.append(f"{name}: {mean(x):.1f} ({len(x)})")
        print(f"  thinking {th}: " + "; ".join(parts))

    if any(r.get("open_team") for r in rows):
        print("\nBy which queue showed more open tickets in the first message (mean team tickets; agents):")
        for arm in ("stated", "done"):
            for th in ("off", "on"):
                d = [r for r in rows if r["arm"] == arm and r["thinking"] == th and r.get("open_team")]
                if d:
                    more = [team(r) for r in d if r["open_team"] > r["open_own"]]
                    less = [team(r) for r in d if r["open_team"] < r["open_own"]]
                    print(f"  {arm:7} thinking {th:4} team board had more: {mean(more):.1f} ({len(more)});"
                          f" own queue had more: {mean(less):.1f} ({len(less)})")

    print("\nAcross tiers. Differences are within pair number (same wording and order where the run")
    print("matched them across tiers), mean with standard error across pairs:")
    for arm in ("stated", "done"):
        for th in ("off", "on"):
            per = {t: by_pair(cell.get((t, th, arm), []), team) for t in tiers}
            line = [f"{t} {mean(list(per[t].values())):.2f}" for t in tiers]
            for lo, hi in (("easy", "hard"), ("easy", "medium")):
                if lo in per and hi in per:
                    both = sorted(set(per[lo]) & set(per[hi]))
                    diffs = [per[hi][p] - per[lo][p] for p in both]
                    line.append(f"{hi} - {lo}: {mean(diffs):+.2f} ({se(diffs):.2f}, {len(both)} pairs)")
            print(f"  {arm:7} thinking {th:4} " + "; ".join(line))

    print("\nDone arm: first ticket from the team board, and agents that ever changed queue:")
    for tier in tiers:
        for th in ("off", "on"):
            rs = cell.get((tier, th, "done"), [])
            if rs:
                firsts = [next((x["source"] for x in r["slots"] if x["source"]), "") for r in rs]
                changed = sum(len({x["source"] for x in r["slots"] if x["source"]}) > 1 for r in rs)
                print(f"  {tier:7} {th:4} first from team board {sum(f == 'team' for f in firsts)}/{len(rs)}"
                      f"   changed queue {changed}/{len(rs)}")

    print("\nDone arm: where the next ticket comes from after a pass and after a fail (share from the team board):")
    for tier in tiers:
        for th in ("off", "on"):
            c = Counter()
            for r in cell.get((tier, th, "done"), []):
                sl = [x for x in r["slots"] if x["source"]]
                for a, b in zip(sl, sl[1:]):
                    c[(a["source"], a["outcome"], b["source"])] += 1
            line = []
            for src in ("team", "own"):
                for outc in ("closed", "failed"):
                    n = c[(src, outc, "team")] + c[(src, outc, "own")]
                    line.append(f"after {src} {'pass' if outc == 'closed' else 'FAIL'}: {c[(src, outc, 'team')]}/{n}")
            print(f"  {tier:7} {th:4} " + "   ".join(line))

    try:
        calls = read(out + "_calls.jsonl")
    except OSError:
        calls = []
    if not calls:
        return sessions_table(everything, tiers, cap)
    print("\nReplies with no tool call (each got a one-line reminder), and other rejected calls, per 100 tickets:")
    n_tix = Counter((r["arm"], r["thinking"]) for r in rows for _ in r["slots"])
    for key in sorted(n_tix):
        cs = [c for c in calls if (c["arm"], c["thinking"]) == key and c.get("session") == session]
        no_tool = sum(c["parsed"] == "no tool call" for c in cs)
        other = sum(c["ok"] is False and c["parsed"] != "no tool call" for c in cs)
        cut = sum(c["stop_reason"] == "max_tokens" for c in cs)
        print(f"  {key[0]:7} thinking {key[1]:4} no tool call {100 * no_tool / n_tix[key]:5.1f}   other rejected {100 * other / n_tix[key]:5.1f}"
              f"   cut off by the token limit: {cut}")

    sessions_table(everything, tiers, cap)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1)
