# Progress log

Newest entry on top: date, who, what ran or changed, where results live, what is next.

## 2026-11-27, Krishiv

- **What changed:** downloaded a second LiveCodeBench batch, `test5.jsonl` (558 MB, sha256 7f77571c...f81214), and rebuilt the ticket file. The pool is now 34 easy, 54 medium and 37 hard LeetCode tickets (was 17 / 26 / 20), enough for three sessions of 10 in every tier. No API spend.
- **Note:** runs before today drew from the 63-ticket pool; their `_run.json` records the counts. The new tickets have not been calibrated.
- **Design change (same day):** the next run is seven sessions of 4 tickets with a flat team payout of $0.75 per ticket to each agent, replacing three sessions of 10 with the square-root rule. Reasons: `docs/decisions/2026-11-27-short-sessions-flat-payout.md`. `queue_game.py` has `--capacity`, `--team-rule` and `--team-rate`; `analyze_queue.py` prints all sessions side by side. Dry run with the stand-in model works; no real-model run yet.
- **What ran (same day):** the 1-pair-per-condition check of the seven-session design on Haiku 5.5: 12 pair-runs, $1.15, all completed. Results in `results/lc_pilot3_check/`; reading in `NOTES.md` section 4. Total API spend about $18.
- **What it showed:** no agent that started on its own queue ever tried the team board in seven sessions (16 of 16). The Done agent stops after every payout and needs the reminder. Exploratory, one pair per condition.
- **Then:** prompt v3 (`prompts/queue_game_v3.json`): itemised payout showing tickets closed, rate and amount, and a session opener that repeats the instruction. Reran the check: 12 pair-runs, $1.02, in `results/lc_pilot3_check2/`. 23 of 24 agents repeated their session-1 choice in all seven sessions; 1 of 24 ever mentions the rate. Total API spend about $19.
- **Next:** decide whether to give the agent a stake in the payout, or to run the full pilot as the measurement of "payouts are ignored" (NOTES.md section 5).

## 2026-11-24, Krishiv

- **What changed:** prompt v2 for the queue game (`prompts/queue_game_v2.json`; decision record `docs/decisions/2026-11-24-queue-game-v2.md`). The Stated opening is an instruction to request tickets, the Done opening says to keep going, the first message shows the open tickets in each queue, and pair k reads the same wording and order in every tier. `queue_game.py` takes `--prompts` to run an older version.
- **What ran:** a 2-pair check ($0.61), then the second queue-game pilot on Claude Haiku 5.5: one session, three tiers, both arms, thinking off and on, 12 pairs per condition, 144 pair-runs, $3.61. No pairs lost. Total API spend about $17.
- **Where results live:** `results/lc_pilot2/` and `results/lc_pilot2_check/`. Tables: `python3 -I analyze_queue.py results/lc_pilot2/lc_pilot2`. Numbers and reading: `NOTES.md` section 4.
- **What it showed:** the prompt fixes worked (no refusals, almost no reminders). 133 of 144 Done agents took only own tickets. Stated agents ask for 0 team tickets (72 of 144) or 5 (59). Their reasons are about colliding with the other agent on the shared board, not pay. Difficulty is real only with thinking off (100%, 86%, 56% closed) and shows only as a few agents changing queue after failed hard tickets (6 of 48 against 0 of 96).
- **Status of the numbers:** exploratory. Not pre-registered. One model, 12 pairs per condition.
- **Next:** more LeetCode tickets, then the three-session design with payouts. Session 1 alone is a default choice, not a test of free-riding.

## 2026-11-23, Krishiv

- **What ran:** the first pilot of the queue game on Claude Haiku 5.5, with one session per pair (not three; too few tickets). Three difficulty tiers, both arms, thinking off and on, 10 pairs per condition: 120 pair-runs, $3.19. A one-pair smoke run before it, $0.18. Total API spend about $13.
- **Where results live:** `results/lc_pilot1/` and `results/lc_smoke/`. Tables: `python3 -I analyze_queue.py results/lc_pilot1/lc_pilot1`. Numbers and reading: `NOTES.md` section 4.
- **What it showed:** asked for a split, Haiku asks for 4 to 5 of 10 tickets from the team board; picking tickets itself it takes 0 to 2. With thinking on, 60 of 60 agents started on their own queue. Agents choose before seeing a ticket and almost never change queue, so difficulty shows no effect.
- **Problems found:** the Stated question is misread by some agents (4 pairs lost); the Done arm needs a reminder after many tickets; tiers were not matched on wording; and we cannot tell "own queue first" from "own queue instead."
- **Status of the numbers:** exploratory. Not pre-registered. One model, 10 pairs per condition.
- **Next:** a new prompt version that fixes those problems, then more tickets and the three-session design.

## 2026-11-21, Krishiv

- **What changed:** new design, the queue game (`NOTES.md` section 3; decision record `docs/decisions/2026-11-21-queue-game.md`). The agent now reads a bare production-style brief with no scoring text; there are three sessions with a dollar payout shown after each; tickets are LeetCode problems, with difficulty (easy, medium, hard) as a separate run the agent is never told about. New code: `queue_game.py`, `lcb.py`, `prompts/queue_game_v1.json`, `tests/`. The pilot-2 code (`pair_game.py`) is unchanged.
- **What ran:** a free check of pilot 2's logs for a difficulty effect (there is almost no difficulty in MBPP+), and two calibration runs of the 63 LeetCode tickets on Claude Haiku 5.5, $0.24 in total. No pilot of the new design yet. Total API spend about $9.65. Nothing has run on the cluster.
- **Where results live:** `results/lc_calib2/` (use this one) and `results/lc_calib/` (first run, graded with bugs since fixed). Numbers are in `NOTES.md` section 4.
- **What it showed:** Haiku closes 100% / 92% / 58% of easy / medium / hard tickets with thinking off, and 93% or more of every label with thinking on. So the difficulty comparison only exists with thinking off on this model.
- **Status of the numbers:** exploratory. Not pre-registered.
- **Next:** get more LeetCode tickets (three sessions need 30 per agent per tier; we have 17 / 26 / 20), then pilot the queue game.

## 2026-11-18, Krishiv

- **What changed:** the design is now one comparison, Stated vs Done, with a live second agent and real coding tickets (MBPP+). Effort is turns, not tokens. The reasons and the full design are in `NOTES.md`, sections 1 to 3.
- **What ran:** smoke tests on a local Qwen3 4B and on Claude Haiku 5.5, no-formula runs, a calibration run, and two pilots of the Stated-vs-Done design on Haiku 5.5 (640 sessions each). About $9.40 of API spend in total. Nothing has run on the cluster.
- **Where results live:** `results/`, one folder per run. Pilot 2 (`results/pilot2/`) is current; pilot 1 is superseded. Numbers and their reading are in `NOTES.md`, section 4.
- **Status of the numbers:** exploratory pilots on one model with three wordings of the brief. Not pre-registered. Do not put them in a result table.
- **Next:** rerun the pilot-2 design on a second, stronger model; add more wordings of the brief; then decide on harder tickets and T = 20. Open questions are in `NOTES.md`, section 5.
