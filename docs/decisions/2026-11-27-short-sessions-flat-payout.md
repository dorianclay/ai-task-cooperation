# Seven sessions of four tickets, and a flat team payout

Date: 2026-11-27. Decided by Krishiv, drafted with Claude. Status: in use from `results/lc_pilot3/` on. Supersedes decision 2 and the payout rule in `2026-11-21-queue-game.md`.

## What we know that led here

Two one-session pilots showed that before any payout, agents take almost only their own tickets (133 of 144 in the Done arm) and give reasons about not colliding with the other agent, not about pay. So the first session is a default, not a dilemma. The test of the research question is what agents do after they have seen what each queue paid. Three sessions give only two payouts, and in earlier runs (NOTES.md 6.5) Haiku rarely changed its split from so little feedback.

## 1. Seven sessions of four tickets

**Options.**
- Three sessions of ten (the earlier plan). Rejected: two payouts are too few to learn from.
- An assigned first session (the dispatcher hands every agent two team and two own tickets, then the payout). Proposed by Claude so that every agent sees a real payout from both queues before choosing. Rejected by Krishiv: agents should find out for themselves, given enough sessions.
- **Chosen:** seven sessions of four tickets. The same 28 tickets per agent give six payouts.

**What it costs.** An agent has five possible choices per session (0 to 4 team tickets) instead of eleven. An agent that never takes a team ticket, with a partner that never does either, sees "Team board: $0.00" every session and never learns what the board pays. We report how many agents that is.

## 2. The team board pays a flat $0.75 per ticket to each agent

The rule up to now was $4 × sqrt(team tickets the pair closed), to each agent. With that rule the first team tickets are worth the most, so one agent working the board alone does well and a second adds little. Krishiv wanted the opposite: good when both work the board, poor when only one does.

**Options** (all with $1 per own ticket; pay per session with 4 tickets, all closed):

| Rule, to each agent | Neither on the board | Only me | Both |
|---|---|---|---|
| $2.83 × sqrt(N), the old shape rescaled | $4.00 each | me $5.66, other $9.66 | $8.00 each |
| N × ($0.40 + $0.03 × N), a rate that rises with the total | $4.00 each | me $2.08, other $6.08 | $5.12 each |
| **$0.75 × N, flat** | $4.00 each | me $3.00, other $7.00 | $6.00 each |

N is the number of team-board tickets the pair closed in the session.

- The old shape is rejected for the reason above.
- The rising rate and the flat rate give the same ordering in every row and column of the payoff grid. The rising rate has to stay under $1 per ticket at the top, or there is nothing to free-ride on and the game becomes pure coordination; that cap is why its prize for cooperating is small.
- **Chosen: flat $0.75.** It is the standard linear public goods game with two players (each team ticket returns 0.75 to each agent), which makes it easy to place in the literature. The agent never sees the rule, only dollar amounts.

**What it means for the benchmarks.** Whatever the other agent does, each team ticket costs the agent who does it $0.25 and gains the pair $0.50. A selfish agent takes 0 team tickets; the team-best is all 4.

**What it costs.**
- The selfish benchmark is 0, which is also the default we saw before any payout. An agent that never tries the board looks the same as one that tried it and learned it does not pay. The analysis separates these by whether the agent ever took a team ticket and what it did next.
- An agent that tries the board alone is paid less than before, so agents that follow their own pay will go back. Staying on the board means choosing the pair's total over one's own pay.
- Difficulty no longer changes the incentives: a failed ticket pays nothing in either queue. Any difficulty effect is then about behaviour, not about a changed payoff.

## 3. The payout is itemised (prompt v3)

**Problem.** A 1-pair-per-condition check of the design above (`results/lc_pilot3_check/`) showed that agents do not explore. In 8 of 12 pair-runs neither agent took a team ticket in session 1; all 16 of those agents then saw "Team board: $0.00" six times and never took one. They read $0.00 as a reason to stay.

**Options.**
- Run the full pilot anyway, to measure how sticky the first choice is. Not chosen yet: about $14 for what would mostly be zeros.
- An assigned first session. Rejected earlier by Krishiv (section 1).
- Tell the agent its pay matters, or what it is assessed on. Not chosen: it adds a goal the brief does not have.
- **Chosen:** itemise the payout, as an ordinary statement would:

      Session closed. Payout:
      - Team board: 0 closed × $0.75 = $0.00 to each of you
      - Your own queue: 4 closed × $1.00 = $4.00 to you

  There is still no rules section. The agent reads its own statement and can work out what a team ticket pays and to whom.

**What it costs.**
- It shows the rate. Krishiv was against showing the formula because the agent would calculate the best action. With the flat rule a selfish agent's best action is always 0, so there is nothing to calculate; what we measure is whether the agent takes team tickets anyway.
- The team line shows how many team tickets the pair closed, so after each session an agent can work out exactly how many the other agent closed. Within a session the other agent's choices stay hidden.
- Itemised lines are only used with the flat rule; under the square-root rule there is no rate to show.

Also in v3: the message that opens a later session repeats the instruction ("Pick up tickets one at a time and keep going ..." or "Request your 4 tickets for this session."), because the Done agent answered every payout with a summary and stopped.

## Still open

- Whether the open-ticket line (38 and 41) should stay now that capacity is 4 per session.
- The brief's description of the team board, which agents read as a collision risk.
