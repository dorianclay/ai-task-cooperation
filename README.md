# ai-task-cooperation

Do AI agents free-ride when effort is costly and reward is shared?

Course project for 15-784 Cooperative AI (CMU). Two LLM agents each split 10 turns between tickets on a shared team board and tickets in their own queue. We compare what a model **says** it will do with what it **does** when it has to do the work.

**New here? Read [NOTES.md](NOTES.md).** Section 1 has the question, where we are and what is next. [CLAUDE.md](CLAUDE.md) has the team's working norms.

## Status (2026-11-18)

Harness built and piloted twice on Claude Haiku 5.5. These are pilot results on one model, not findings. See NOTES.md section 4.

## What is in the repo

| Path | What it is |
|---|---|
| `NOTES.md` | Design, prompts, results and history. The source of truth |
| `pair_game.py` | The current experiment: two live agents, Stated vs Done |
| `tickets.py` | Loads the coding tickets and grades submitted code in a sandbox |
| `smoke_test.py` | Earlier one-agent harness with the payoff formula in the prompt. Also holds the API client the other scripts use |
| `no_formula.py` | Earlier runs with no payoff rule in the prompt |
| `data/mbppplus/` | The tickets: MBPP+ v0.2.0 |
| `results/` | One folder per run (below) |
| `docs/log.md` | Progress log, newest first |

Results folders:

| Folder | Run | Notes section |
|---|---|---|
| `results/pilot2/` | Stated vs Done, current | 4 |
| `results/pilot1/` | Stated vs Done, first attempt. Superseded | 6.6 |
| `results/calibration/` | How often one submission closes a ticket | 3 |
| `results/no_formula/` | No payoff rule in the prompt | 6.5 |
| `results/smoke/` | Formula game, Qwen3 4B and Haiku | 6.3, 6.4 |

In each folder, `<name>.csv` is the result table (one row per agent session or episode), `<name>_calls.csv` is the raw text of every model call, and `<name>.log` or `<name>_log.txt` is a readable sample. The two largest call logs are gzipped. To open one:

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

**The grader runs code written by the model.** On macOS it runs under `sandbox-exec` with no network and no file writes. On any other system (the cluster included) there is no sandbox yet: the code runs in a plain separate process with a 10-second timeout. Add a sandbox there before running the Done arm. `python3 -I tickets.py --validate` prints which mode is active.

## Running

Runs on Claude models cost money. Check with the team before starting one.

Check that the tickets load and the grader works (free):

```bash
python3 -I tickets.py --validate
```

Calibration, 60 single tickets (a few cents on Haiku):

```bash
python3 -I pair_game.py --calib 60 --out results/calibration/calib
```

The pilot. This is the command that produced `results/pilot2/`, with a new output name. It took 26 minutes and cost $1.94 on Haiku 5.5:

```bash
python3 -I pair_game.py --pairs 20 --thinking off,on --workers 10 --out results/pilot3/pilot3
```

`results/pilot1/` came from the same command on an older version of the Done arm, so the current code will not reproduce it.

Useful options for `pair_game.py`: `--model`, `--arms stated,done`, `--rules told,hidden`, `--betas 0.7,1.0,1.5`, `--seed`. To use a model other than Haiku 5.5, add its price to `PRICES` in `smoke_test.py` so the cost report is right.

The earlier harnesses, if you need them:

```bash
python3 smoke_test.py --model claude-haiku-5-5 --workers 6 --out results/smoke/my_run.csv
```

```bash
python3 no_formula.py --arm default --workers 6 --out results/no_formula/my_run.csv
```

The `-I` flag on the first three commands is deliberate. Those scripts read a downloaded dataset, and `-I` runs Python in isolated mode so it cannot pick up stray modules from the current folder or your user packages.

## Data

`data/mbppplus/MbppPlus.jsonl.gz` is MBPP+ v0.2.0 from the [EvalPlus](https://github.com/evalplus/evalplus) project (Apache-2.0), downloaded from the [mbppplus_release](https://github.com/evalplus/mbppplus_release/releases/tag/v0.2.0) page. It builds on Google's MBPP benchmark.
