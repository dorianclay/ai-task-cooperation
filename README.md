# ai-task-cooperation

Do AI agents free-ride when effort is costly and reward is shared?

Course project for 15-784 Cooperative AI (CMU). Two LLM coding agents each split their tickets between a shared team board and their own queue. We compare what a model **says** it will do with what it **does** when it has to do the work.

**New here? Read [NOTES.md](NOTES.md).** Section 1 has the question, where we are and what is next. [CLAUDE.md](CLAUDE.md) has the team's working norms.

## Status (2026-11-27)

If you are picking this up, read NOTES.md section 1 first. It says what has run, what we found, which decision is open and what will trip you up.

In short: the agent reads a bare, production-style brief, plays seven sessions of 4 tickets with an itemised dollar payout after each, and works LeetCode tickets of one difficulty per run. On Claude Haiku 5.5 so far, agents take almost only their own tickets and ignore the payouts. These are pilot results on one model, not findings.

## What is in the repo

| Path | What it is |
|---|---|
| `NOTES.md` | Design, prompts, results and history. The source of truth |
| `queue_game.py` | The current experiment: two live agents, Stated vs Done, seven sessions of 4 tickets with payouts |
| `analyze_queue.py` | Tables for a `queue_game.py` run, computed from its raw records |
| `lcb.py` | LeetCode tickets (easy, medium, hard) from LiveCodeBench, and their sandboxed grader |
| `prompts/` | Everything the agent reads, in versioned files |
| `tests/` | Unit tests for the payout, the wording rules, the grader and the bookkeeping |
| `docs/decisions/` | Short records of design decisions |
| `pair_game.py` | The pilot 1 and 2 experiment (earlier design) |
| `tickets.py` | MBPP+ tickets and grader, used by `pair_game.py` |
| `smoke_test.py` | Earlier one-agent harness with the payoff formula in the prompt. Also holds the API client the other scripts use |
| `no_formula.py` | Earlier runs with no payoff rule in the prompt |
| `data/mbppplus/` | MBPP+ v0.2.0, the tickets for pilots 1 and 2 |
| `data/livecodebench/` | LiveCodeBench files. Not in git; see Data below |
| `results/` | One folder per run (below) |
| `docs/log.md` | Progress log, newest first |

Results folders:

| Folder | Run | Notes section |
|---|---|---|
| `results/lc_pilot3_check2/` | Queue game, seven sessions, itemised payout (prompt v3), 1 pair per condition. Latest | 4 |
| `results/lc_pilot3_check/` | The same with prompt v2 (payout not itemised) | 4 |
| `results/lc_pilot2/` | Queue game, second pilot, prompt v2, one session of 10 tickets, 12 pairs per condition | 4 |
| `results/lc_pilot2_check/` | 2-pair check of prompt v2 before that pilot | 4 |
| `results/lc_pilot1/` | Queue game, first pilot, prompt v1, one session | 4 |
| `results/lc_smoke/` | Queue game, one-pair smoke run before the pilot | 4 |
| `results/lc_calib2/` | Solve rate of the LeetCode tickets by difficulty | 4 |
| `results/lc_calib/` | The same, first run. Superseded (grader bugs); see its README | 4 |
| `results/pilot2/` | Stated vs Done, earlier design | 4 |
| `results/pilot1/` | Stated vs Done, first attempt. Superseded | 6.6 |
| `results/calibration/` | How often one submission closes an MBPP+ ticket | 6.7 |
| `results/no_formula/` | No payoff rule in the prompt | 6.5 |
| `results/smoke/` | Formula game, Qwen3 4B and Haiku | 6.3, 6.4 |

Runs of `queue_game.py` write JSON lines: `<name>_run.json` (run id, git commit, settings), `<name>_calls.jsonl` (the raw text of every model call) and `<name>_sessions.jsonl` or `<name>_calib.jsonl` (the records the tables are computed from). In the older folders, `<name>.csv` is the result table (one row per agent session or episode), `<name>_calls.csv` is the raw text of every model call, and `<name>.log` or `<name>_log.txt` is a readable sample. The large call logs are gzipped (`*_calls.jsonl.gz`, `*_calls.csv.gz`); `analyze_queue.py` and `queue_game.py --summarize` read the gzipped JSON lines as they are. To open one by hand:

```bash
gunzip -k results/pilot2/pilot2_calls.csv.gz
```

or read it directly in Python with `gzip.open(path, "rt", newline="")`.

## Setup

Python 3.9 or newer. No packages to install; everything uses the standard library.

Runs on Claude models need an Anthropic API key. Put it in a file called `.env` next to the scripts:

```
ANTHROPIC_API_KEY=<your key>
```

`.env` is git-ignored. Never commit a key. The smoke test can also run on a local model through [Ollama](https://ollama.com), which needs no key.

**The grader runs code written by the model.** On macOS it runs under `sandbox-exec` with no network and no file writes. On any other system (the cluster included) there is no sandbox yet: the code runs in a plain separate process with only a time limit. Add a sandbox there before running anything that grades model code. `python3 -I lcb.py --check` (or `python3 -I tickets.py --validate` for the earlier harness) prints which mode is active.

## Running

Runs on Claude models cost money. Check with the team before starting one.

### The current experiment (`queue_game.py`)

First get the tickets (see Data below), then extract the LeetCode problems and check the grader (free):

```bash
python3 -I lcb.py --build
```

```bash
python3 -I lcb.py --check
```

Unit tests (free):

```bash
python3 -I -m unittest discover -s tests
```

Run the whole harness with a stand-in for the model and no API calls (free):

```bash
python3 -I queue_game.py --model fake --pairs 2 --sessions 1 --out results/dry/dry
```

Calibration: every ticket once, one submission, thinking off and on:

```bash
python3 -I queue_game.py --calib 30 --workers 8 --max-cost 1 --out results/lc_calib2/lc_calib2
```

A pilot. Each tier needs 28 tickets per agent for seven sessions of 4:

```bash
python3 -I queue_game.py --tiers easy,medium,hard --pairs 12 --out results/<name>/<name>
```

Reprint the table of a finished run from its raw records:

```bash
python3 -I queue_game.py --summarize results/<name>/<name>
```

The fuller tables (gap between arms by pair, first pick, wording effects, reminders):

```bash
python3 -I analyze_queue.py results/lc_pilot2/lc_pilot2
```

The second pilot (one session of 10 tickets, the earlier payout rule) was this command; it cost $3.61 and took 27 minutes on Haiku 5.5:

```bash
python3 -I queue_game.py --tiers easy,medium,hard --pairs 12 --sessions 1 --capacity 10 --team-rule sqrt --team-rate 4 --workers 12 --max-cost 5 --out results/<name>/<name>
```

Useful options: `--model`, `--arms stated,done`, `--thinking off,on`, `--sessions`, `--capacity`, `--team-rule`, `--team-rate`, `--prompts`, `--seed`, `--max-cost` (stop starting new work after this many dollars). Raw logs are append-only, so every run needs a new `--out`. To use a model other than Haiku 5.5, add its price to `PRICES` in `smoke_test.py` so the cost report is right.

### The earlier experiment (`pair_game.py`, pilots 1 and 2)

Check that the MBPP+ tickets load and the grader works (free):

```bash
python3 -I tickets.py --validate
```

Calibration, 60 single tickets (a few cents on Haiku):

```bash
python3 -I pair_game.py --calib 60 --out results/calibration/calib
```

The command that produced `results/pilot2/`, with a new output name. It took 26 minutes and cost $1.94 on Haiku 5.5:

```bash
python3 -I pair_game.py --pairs 20 --thinking off,on --workers 10 --out results/pilot3/pilot3
```

`results/pilot1/` came from the same command on an older version of the Done arm, so the current code will not reproduce it.

The first harnesses, if you need them:

```bash
python3 smoke_test.py --model claude-haiku-5-5 --workers 6 --out results/smoke/my_run.csv
```

```bash
python3 no_formula.py --arm default --workers 6 --out results/no_formula/my_run.csv
```

The `-I` flag is deliberate. Those scripts read a downloaded dataset, and `-I` runs Python in isolated mode so it cannot pick up stray modules from the current folder or your user packages.

## Data

`data/mbppplus/MbppPlus.jsonl.gz` is MBPP+ v0.2.0 from the [EvalPlus](https://github.com/evalplus/evalplus) project (Apache-2.0), downloaded from the [mbppplus_release](https://github.com/evalplus/mbppplus_release/releases/tag/v0.2.0) page. It builds on Google's MBPP benchmark.

`data/livecodebench/` holds [LiveCodeBench](https://huggingface.co/datasets/livecodebench/code_generation_lite) (code generation, lite; licence tag "cc" on the dataset page). It is not in git because the files are large. Download one or more of its `test*.jsonl` files into that folder, then run `python3 -I lcb.py --build`. We use the two newest batches, `test6.jsonl` (134 MB) and `test5.jsonl` (558 MB), problems from October 2024 to April 2025. Together they have 34 easy, 54 medium and 37 hard LeetCode problems (`test6.jsonl` alone: 17, 26, 20):

```bash
curl -L -o data/livecodebench/test6.jsonl https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/main/test6.jsonl
curl -L -o data/livecodebench/test5.jsonl https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/main/test5.jsonl
```

The hidden tests in these files are stored as a Python pickle. Do not load them with `pickle.loads`; `lcb.py` decodes them with an unpickler that refuses every global.
