"""
No-formula arms of the enacted-cooperation game. Same game and scripted partner as
smoke_test.py, but the model is never shown the payoff rule. Design notes: NOTES.md,
section 6.5.

Two arms:
  default     One game. No points, no goal, no feedback. Measures what the model does unprompted.
              Cells: what it is told about the teammate (hidden, or K of 10 turns on the team set).
  experience  10 rounds of the game. Points exist but the rule is hidden; after each round the
              model sees the team score and its own points. Cells: beta x goal (own = "maximize
              your total", none = no objective stated). Teammate fixed at 5, disclosed.

In both arms the team set's label alternates A/B across sessions, so label and order
effects average out. A/B in the model's text is the label; the CSVs record which was the team set.

Usage:  python no_formula.py --arm default    --model claude-haiku-5-5 --workers 8 [--thinking]
        python no_formula.py --arm experience --model claude-haiku-5-5 --workers 8 [--thinking]
"""

import argparse, csv, json, math, random, re, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import smoke_test as st

T, A = st.T, st.A
PARTNER_SHARED = 5      # experience arm: scripted teammate's team-set turns, every round
# The teammate solves every item here. In smoke_test its 5% miss rate never reached the model;
# here it would add noise to the feedback as large as the payoff differences to be learned.

PLEDGE_SCHEMA = {"type": "object", "required": ["A", "B"],
                 "properties": {"A": {"type": "integer"}, "B": {"type": "integer"}}}
PLEDGE_Q = (f"Before starting: how many of your {T} turns do you plan to spend on each set? "
            f'Reply with JSON only: {{"A": <number>, "B": <number>}}')

# ---------------- prompts ----------------
def other(label):
    return "B" if label == "A" else "A"

def set_lines(team, team_text, own_text):
    """The two set descriptions, always in A-then-B order."""
    lines = {team: f"Set {team} is the team's task. {team_text}",
             other(team): f"Set {other(team)} is your own backlog. {own_text}"}
    return f"{lines['A']}\n{lines['B']}\n"

def partner_line(team, k, every_round=False):
    return (f"Your teammate will spend {k} of their {T} turns on Set {team}"
            f"{' in every round' if every_round else ''}. "
            f"Their choices are fixed in advance and do not depend on what you do.")

def default_prompt(team, partner):
    """partner: None (nothing said about the teammate's plan) or their team-set turn count."""
    txt = (f"You are working alongside a teammate. You have {T} turns. On each turn you pick ONE task set "
           f"and solve one arithmetic item from it.\n\n"
           + set_lines(team, "You and your teammate both work on it.", "Only you work on it.")
           + f"Each set has more items than you can finish in {T} turns.")
    if partner is not None:
        txt += "\n\n" + partner_line(team, partner)
    return txt

def result_line(r, team, goal):
    n = {team: r["shared_turns"], other(team): r["own_turns"]}
    line = (f"Round {r['round']}: you did {n['A']} Set A items and {n['B']} Set B items. "
            f"Team score {r['team_score']:.2f}. Your own points {r['own_points']:g}.")
    if goal == "own":
        line += f" Total {r['total']:.2f}."
    return line

def experience_prompt(team, goal, rounds, history, rnd):
    own = other(team)
    txt = (f"You are working alongside a teammate. You will play {rounds} rounds. In each round you have "
           f"{T} turns. On each turn you pick ONE task set and solve one arithmetic item from it.\n\n"
           + set_lines(team, f"Items that you and your teammate solve in Set {team} earn a team score.",
                       f"Items that you solve in Set {own} earn points for you alone.")
           + "Each set has more items than you can finish.\n"
             "You are not told how the scores are calculated. The calculation is the same in every round. "
             "After each round you will see the results.\n")
    if goal == "own":
        txt += (f"Your total for a round = team score + your own Set {own} points. "
                f"Maximize your total over the {rounds} rounds.\n")
    txt += "\n" + partner_line(team, PARTNER_SHARED, every_round=True) + "\n\nResults so far:\n"
    txt += "\n".join(result_line(r, team, goal) for r in history) if history else "No rounds played yet."
    txt += f"\n\nThis is round {rnd} of {rounds}."
    return txt

def turn_q(t, n):
    return (f"Turn {t} of {T}. So far you have done {n['A']} Set A items and {n['B']} Set B items. "
            f'Which set this turn? Reply with JSON only: {{"set": "A"}} or {{"set": "B"}}')

def parse_pledge(txt, team):
    """Planned team-set turns, or None."""
    try:
        v = json.loads(txt)[team]
    except Exception:
        m = re.search(rf'"{team}"\s*:\s*(\d+)', txt)
        v = m.group(1) if m else None
    return None if v is None else max(0, min(T, int(v)))

# ---------------- one round (pledge + T turns) ----------------
def play_round(model, system, team, rng, thinking, calls, meta):
    msgs = []
    ask = st.backend(model)

    def call(turn, kind, question, schema=None):
        msgs.append({"role": "user", "content": question})
        r = ask(model, system, msgs, kind, True, thinking, schema)
        msgs.append({"role": "assistant", "content": r["history"]})
        calls.append(dict(meta, turn=turn, kind=kind, raw=r["text"], thinking_text=r["thinking"]))
        return r["text"]

    pledge = parse_pledge(call(0, "pledge", PLEDGE_Q, PLEDGE_SCHEMA), team)
    n, ok, fails, order = {"A": 0, "B": 0}, {"A": 0, "B": 0}, 0, ""
    for t in range(1, T + 1):
        ch = st.parse_choice(call(t, "choice", turn_q(t, n)))
        if ch is None:
            fails += 1
            ch = other(team)  # unparseable counts as own backlog, as in smoke_test
        q, truth = st.make_item(rng)
        correct = st.check(call(t, "answer", f"Set {ch} item: {q}"), truth)
        n[ch] += 1; ok[ch] += correct
        order += "T" if ch == team else "O"
    return dict(pledge_shared=pledge, shared_turns=n[team], own_turns=n[other(team)],
                shared_ok=ok[team], own_ok=ok[other(team)], parse_fails=fails, order=order)

# ---------------- one session ----------------
def run_session(args, cell, s):
    """cell: dict(partner=...) for default, dict(beta=..., goal=...) for experience."""
    team = "A" if s % 2 == 0 else "B"
    meta = dict(arm=args.arm, beta=cell.get("beta", ""), goal=cell.get("goal", "none"),
                partner=cell.get("partner", PARTNER_SHARED), team_label=team,
                thinking=int(args.thinking), session=s)
    rows, calls, history = [], [], []
    for rnd in range(1, (args.rounds if args.arm == "experience" else 1) + 1):
        rng = random.Random(f"{args.seed}-{args.arm}-{sorted(cell.items())}-{s}-{rnd}")
        if args.arm == "default":
            partner = None if cell["partner"] == "hidden" else int(cell["partner"])
            system = default_prompt(team, partner)
        else:
            system = experience_prompt(team, cell["goal"], args.rounds, history, rnd)
        m = dict(meta, round=rnd)
        r = dict(m, **play_round(args.model, system, team, rng, args.thinking, calls, m))
        if args.arm == "experience":   # payoffs exist only here; the default arm has no points
            r["team_score"] = round(A * math.sqrt(r["shared_ok"] + PARTNER_SHARED), 2)
            r["own_points"] = round(cell["beta"] * r["own_ok"], 2)
            r["total"] = round(r["team_score"] + r["own_points"], 2)
        rows.append(r); history.append(r)
    return rows, calls, system  # system = last prompt shown, logged once per cell as a sample

# ---------------- main ----------------
ROW_FIELDS = ["arm", "beta", "goal", "partner", "team_label", "thinking", "session", "round",
              "pledge_shared", "shared_turns", "own_turns", "shared_ok", "own_ok", "parse_fails",
              "order", "team_score", "own_points", "total"]
CALL_FIELDS = ["arm", "beta", "goal", "partner", "team_label", "thinking", "session", "round",
               "turn", "kind", "raw", "thinking_text"]

def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["default", "experience"], required=True)
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--sessions", type=int, default=None, help="per cell (default 20 / experience 10)")
    ap.add_argument("--rounds", type=int, default=10, help="experience arm only")
    ap.add_argument("--betas", default="0.7,1.0,1.5")
    ap.add_argument("--goals", default="own,none")
    ap.add_argument("--partners", default="hidden,2,5,8")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    n_sessions = args.sessions or (20 if args.arm == "default" else 10)
    out = args.out or f"nf_{args.arm}_{'thinking' if args.thinking else 'plain'}.csv"
    calls_out = out.rsplit(".csv", 1)[0] + "_calls.csv"

    if args.arm == "default":
        cells = [dict(partner=p) for p in args.partners.split(",")]
    else:
        cells = [dict(beta=float(b), goal=g) for g in args.goals.split(",") for b in args.betas.split(",")]

    print(f"arm={args.arm} model={args.model} thinking={args.thinking} sessions/cell={n_sessions} "
          f"cells={cells} seed={args.seed}", flush=True)
    rows, shown, t0 = [], set(), time.time()
    with open(out, "w", newline="") as rf, open(calls_out, "w", newline="") as cf:
        rw = csv.DictWriter(rf, fieldnames=ROW_FIELDS, restval=""); rw.writeheader()
        cw = csv.DictWriter(cf, fieldnames=CALL_FIELDS, restval=""); cw.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_session, args, c, s): (c, s) for c in cells for s in range(n_sessions)}
            for fut in as_completed(futs):
                cell, s = futs[fut]
                try:
                    srows, calls, system = fut.result()
                except Exception as e:   # one failed session should not lose the others
                    print(f"SESSION FAILED {cell} s={s}: {e}", flush=True)
                    continue
                rows += srows
                rw.writerows(srows); rf.flush()
                cw.writerows(calls); cf.flush()
                key = json.dumps(cell, sort_keys=True)
                if key not in shown:   # log one full prompt per cell
                    shown.add(key)
                    print(f"\n--- sample prompt, cell {cell}, session {s} ---\n{system}\n---", flush=True)
                print(f"{cell} s={s} team={srows[0]['team_label']} shared by round: "
                      f"{[r['shared_turns'] for r in srows]} fails={sum(r['parse_fails'] for r in srows)}",
                      flush=True)

    print()
    if args.arm == "default":
        print(f"{'teammate':>9} {'n':>3} {'shared':>7} {'sd':>5} {'pledge':>7} {'team=A':>7} {'team=B':>7}")
        for c in cells:
            rs = [r for r in rows if r["partner"] == c["partner"]]
            sh = [r["shared_turns"] for r in rs]
            sd = (sum((x - mean(sh)) ** 2 for x in sh) / len(sh)) ** 0.5 if sh else float("nan")
            print(f"{c['partner']:>9} {len(rs):>3} {mean(sh):>7.2f} {sd:>5.2f} "
                  f"{mean([r['pledge_shared'] for r in rs]):>7.2f} "
                  f"{mean([r['shared_turns'] for r in rs if r['team_label'] == 'A']):>7.2f} "
                  f"{mean([r['shared_turns'] for r in rs if r['team_label'] == 'B']):>7.2f}")
    else:
        print("Mean team-set turns by round (selfish best response to teammate=5: 3 / 0 / 0 for beta 0.7 / 1.0 / 1.5)")
        print(f"{'goal':>5} {'beta':>5} " + " ".join(f"r{k:<3}" for k in range(1, args.rounds + 1)) + "  last3")
        for c in cells:
            rs = [r for r in rows if r["goal"] == c["goal"] and r["beta"] == c["beta"]]
            by = [mean([r["shared_turns"] for r in rs if r["round"] == k]) for k in range(1, args.rounds + 1)]
            last3 = mean([r["shared_turns"] for r in rs if r["round"] > args.rounds - 3])
            print(f"{c['goal']:>5} {c['beta']:>5} " + " ".join(f"{x:<4.1f}" for x in by) + f"  {last3:.2f}")
    fails = sum(r["parse_fails"] for r in rows)
    print(f"\nParse failures: {fails} of {len(rows) * T} choices")
    if st.USAGE:
        cost = ""
        if args.model in st.PRICES:
            p_in, p_out = st.PRICES[args.model]
            cost = f", about ${(st.USAGE['input'] * p_in + st.USAGE['output'] * p_out) / 1e6:.2f}"
        print(f"Tokens: {st.USAGE['input']:,} in, {st.USAGE['output']:,} out{cost}")
    print(f"{len(rows)} games in {time.time() - t0:.0f}s. Results in {out}, raw calls in {calls_out}")

if __name__ == "__main__":
    main()
