# Progress log

Newest entry on top: date, who, what ran or changed, where results live, what is next.

## 2026-11-18, Krishiv

- **What changed:** the design is now one comparison, Stated vs Done, with a live second agent and real coding tickets (MBPP+). Effort is turns, not tokens. The reasons and the full design are in `NOTES.md`, sections 1 to 3.
- **What ran:** smoke tests on a local Qwen3 4B and on Claude Haiku 5.5, no-formula runs, a calibration run, and two pilots of the Stated-vs-Done design on Haiku 5.5 (640 sessions each). About $9.40 of API spend in total. Nothing has run on the cluster.
- **Where results live:** `results/`, one folder per run. Pilot 2 (`results/pilot2/`) is current; pilot 1 is superseded. Numbers and their reading are in `NOTES.md`, section 4.
- **Status of the numbers:** exploratory pilots on one model with three wordings of the brief. Not pre-registered. Do not put them in a result table.
- **Next:** rerun the pilot-2 design on a second, stronger model; add more wordings of the brief; then decide on harder tickets and T = 20. Open questions are in `NOTES.md`, section 5.
