# Queue game: bare prompts, three sessions with payouts, LeetCode tickets by difficulty

Date: 2026-11-21. Decided by Krishiv, working with Claude. Status: exploratory design, not yet reviewed by Dorian or Brandon and not pre-registered.

## Why the design changed

Pilot 2 (NOTES.md, section 4) showed two problems with the brief the agent read.

- It read like the rules of a game: a "How the session is scored" section, credits, "you are not told the amounts," "you cannot see your teammate." A model that recognises a game may play the game, which is not what we want to measure.
- The tickets (MBPP+) were too easy to test anything about difficulty: 341 of the 370 tickets seen at least four times never failed, and the ones that failed were mostly trick tickets with a hidden requirement.

## Decisions

| # | Question | Options considered | Choice | Reason |
|---|---|---|---|---|
| 1 | What does the brief say about stakes? | (a) the payoff formula; (b) names "team credit" and "own credit" without amounts, as in pilot 2; (c) nothing: two queues and a ticket limit | (c) | With the formula the model does arithmetic. Any scoring section signals a game. A real deployment says only that there is a team queue and a queue assigned to you. |
| 2 | How do stakes enter at all? | (a) never; (b) one dollar total after each session; (c) a two-line payout after each session (team board, own queue) | (c), over three sessions | Stakes arrive as a result, not a rule. A single total cannot be read. Session 1 happens before any payout, so it is still a one-shot game with hidden choices. |
| 3 | How is difficulty varied? | (a) not varied; (b) rating stated in the brief; (c) separate runs on easy, medium and hard tickets, never mentioned to the agent | (c) | The agent should not know it is a manipulation. Tickets are LeetCode problems from LiveCodeBench, which carries the LeetCode difficulty label. |
| 4 | What happens to a failed ticket? | (a) it stays at the front of its queue, as in pilot 2; (b) one submission per ticket, then it is released | (b), said only in the tool result when it happens | With hard tickets an agent stuck on a team ticket would switch queues to escape it, which would look like avoiding team work. |
| 5 | Which ticket does the agent get? | (a) separate ticket lists per queue, as in pilot 2; (b) one fixed list per agent: the n-th ticket is the same whichever queue it is taken from | (b) | Ticket luck cannot then differ between queues or between arms. In pilot 2 the team queues happened to hold more trick tickets. Claude's choice; not yet discussed. |
| 6 | When is the belief question asked? | (a) after every session; (b) once at the end, one number per session | (b) | Asking earlier would prompt the agent to think about the other agent before sessions 2 and 3. |

## What this costs us

- **No stated dilemma.** The agent is never told that an own ticket pays it more than its share of a team ticket. Before the first payout the only pull is "assigned to you" versus "the team's." We cannot call low team effort free-riding in the game-theory sense, and the selfish and team-best benchmarks do not apply to what the agent knew. What we measure is the gap between what it says and what it does, and how that moves with difficulty and with pay.
- **Not one-shot after session 1.** The team payout carries a rough signal of what the other agent did. Session 1 is the main measure; sessions 2 and 3 are reported separately.
- **LeetCode problems look like benchmark problems,** not like real tickets. The same in every tier.
- **The LeetCode label is not difficulty for our model.** Tiers are checked against measured solve rates (calibration) before they are used.

## Still open

- Whether to keep a small arm with the formula, to compare against the benchmarks.
- Later variants, one change at a time on this baseline: points versus dollars, letting the agents talk, a different payout rule.
- How many tickets per tier are needed. LiveCodeBench's newest batch has 17 easy, 26 medium and 20 hard LeetCode problems; three sessions need 30 per agent.
