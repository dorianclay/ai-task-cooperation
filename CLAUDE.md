# CLAUDE.md

Shared context for everyone (human or AI assistant) working in this repo. Course project for 15784 (CMU) by Dorian Clay, Krishiv Singhal, Brandon Zhou. Target quality: publishable-grade rigor. Keep this file current; update it in the same PR that changes a convention.

**Status: working draft.** The experimental design below comes from the initial proposal (2026-11-03) and is a *starting hypothesis about how to study the question*, not a settled plan. Expect the design, task choice, effort measure, and even the framing to change as smoke tests and early results come in. Treat each design element as the current best guess; the commitments that are firm are the research question, the rigor norms, and the collaboration norms. When evidence argues for a different path, change the path and record why.

## Current state (2026-11-27): read NOTES.md first

The design has moved on from the proposal described further down. [NOTES.md](NOTES.md) is the source of truth for the current design, prompts and results; update it when a decision changes. Where this file and NOTES.md disagree about the design, NOTES.md is current. The experiment and collaboration norms further down still stand.

**One-sentence thesis.** We take the standard public goods game and replace "contribute a number" with "actually do the shared work," to measure whether LLM agents cooperate when the choice is enacted rather than reported, and how far the two come apart.

**The current design (the queue game, NOTES.md section 3)**
- Two coding agents, another instance of the same model as teammate, each with capacity for T = 4 tickets per session (the pilots so far used 10). A ticket comes from the team board or the agent's own queue.
- The comparison is **Stated vs Done**: the agent either asks for a split of its tickets up front, or picks them up one at a time.
- Seven sessions. After each, the agent is shown an itemised dollar payout for the team board and for its own queue (tickets closed x rate = amount). The rule behind it (each team ticket the pair closes pays $0.75 to each agent; own queue pays $1 per ticket) is never shown. The pilots so far used one session of 10 with 4 x sqrt(team tickets); `--team-rule sqrt --team-rate 4 --capacity 10` reruns that.
- Tickets are LeetCode problems from LiveCodeBench. Difficulty (easy, medium, hard) is a separate run and is never mentioned to the agent.
- Pilots so far ran on Claude Haiku 5.5 through the API: two on the earlier design (`pair_game.py`, MBPP+ tickets, a brief with scoring rules) two on the queue game with a single session of 10 tickets (prompt v1, then v2), and two small checks of the seven-session design (1 pair per condition; prompt v2, then v3). Nothing has run on the cluster.

**Conventions for the current harness**
- Anything the agent reads must look like a plain production deployment and say as little as possible. No scoring, credits, difficulty, or statements about what the other agent can see. No "public goods game," "private," "public," "experiment" or "maximize." Use "team board" and "your own queue." `tests/` checks the wording for banned words.
- Mechanics are revealed through ordinary tool results when they happen, not explained in advance. One approved exception: the first message shows how many tickets are open in each queue.
- Prompts live in `prompts/queue_game_v<N>.json` (current: v3; `--prompts` runs an older one). A wording change is a new version file.
- Wording and order are assigned by pair number, the same in every tier, arm and thinking mode. Use multiples of 12 pairs so every combination appears equally often.
- Keep the teammate's choices hidden within a session.
- Log the raw model text of every call. Raw logs are append-only JSONL, with a `_run.json` holding the run id, git commit and settings. One folder per run under `results/`.
- Plain Python, standard library only.
- Code written by the model runs only inside the graders in `lcb.py` and `tickets.py`. Run scripts that read a downloaded dataset with `python3 -I`. Never load LiveCodeBench's pickled tests with `pickle.loads`; use `lcb.py`.

**Not yet in line with the norms below.** A run is still defined by its command line (recorded in `_run.json`), not by a config file checked into git. The scripts call the Anthropic API directly instead of going through one model-client interface. The grader has a sandbox only on macOS. The earlier scripts (`pair_game.py`, `smoke_test.py`, `no_formula.py`) keep prompts inline and write CSV. Acceptable for exploratory pilots; fix before any confirmatory run.

**Next.** Two seven-session checks showed that agents ignore the payout and repeat their first choice. The open decision is whether to give the agent a stake in the payout (one sentence in the brief, as a new prompt version) or to run the full seven-session pilot as it is. NOTES.md section 1 has the handoff. Session 1 alone is a default choice made before any pay is shown, so it cannot be read as free-riding. See NOTES.md, sections 1, 4 and 5.

## Commands

No packages to install. Claude runs need `ANTHROPIC_API_KEY` in the environment or in a git-ignored `.env`. Details and options are in [README.md](README.md).

- Build and check the LeetCode tickets (free): `python3 -I lcb.py --build`, then `python3 -I lcb.py --check`
- Unit tests (free): `python3 -I -m unittest discover -s tests`
- Dry run with a stand-in model (free): `python3 -I queue_game.py --model fake --pairs 2 --sessions 1 --out results/dry/dry`
- Calibration (spends API money; ask first): `python3 -I queue_game.py --calib 30 --max-cost 1 --out results/<name>/<name>`
- Pilot (spends API money; ask first): `python3 -I queue_game.py --pairs 12 --out results/<name>/<name>`
- Tables for a finished run (free): `python3 -I analyze_queue.py results/<name>/<name>`
- Earlier harness: `python3 -I tickets.py --validate`; `python3 -I pair_game.py --pairs 20 --thinking off,on --workers 10 --out results/<name>/<name>`

## Project (original proposal, 2026-11-03; kept for reference)

**Research question:** Do LLM agents free-ride when effort is costly and the reward is shared?

**Current proposal:** two instances of the same model play a one-shot public goods game. Effort is operationalized as **reasoning tokens** (continuous, measurable, costly), though whether tokens are the right effort measure is itself an open question (see below).

- Each agent has total token budget `B`, split between a **shared task** (`K` scorable problems with known answers, team score `S`, answers merged by a predetermined resolution rule) and a **private task** (own problem set, score `P_i`).
- Payoff: `u_i = α·S(e1,e2) + β·P_i(B − e_i)`, where `e_i` is agent i's tokens spent on the shared task. `S` and `P_i` are estimated empirically from solo-agent runs.
- Round: instructions → communication (≤3 messages, agents state intended contribution `ê_i`) → independent execution (token usage recorded per task) → submission → feedback/payoff.
- Primary treatment: vary `β` (private reward weight). Hold constant: model, `B`, task structure, communication protocol, scoring. Balance problem sets across conditions.

**Initial hypotheses** (revise as understanding sharpens; record revisions in a decision record, and keep the original wording in git history)
- H1: contribution is above the selfish equilibrium (cooperation index > 0) but below the social optimum (index < 1).
- H2: cooperation index falls as `β` rises.
- H3: stated contribution `ê_i` exceeds actual `e_i`, and the gap widens as `β` rises.

**Metrics:** shared contribution (`e_i`, `e_i/B`); free-riding (change in contribution vs `β`); commitment consistency (`ê_i − e_i`); task performance (`S`, `P_i`, `u_i`); task participation (shared problems attempted / worked solutions).

**Planned extras:** a normal-form (matrix-game) version of the same game as a baseline, to compare model behavior against the abstract game. Possible extensions: lying when told it is allowed, knowing the partner's model type, explicit payoff function vs verbal description of relative importance, prompt variations, repeated interaction, larger teams. Extensions stay out of the primary experiment until it is solid.

## Instructor feedback (Conitzer, 2026-11-08) — design constraints

- Test **robustness** and **what drives** the behavior. A single prompt wording and a single model is an anecdote. Vary prompts, problem sets, seeds, and `B`.
- Commercial models likely carry tuning about effort and cooperation, and telling a model to "work hard" does not mean it will. Treat stated effort and actual effort as separate quantities (this is H3).
- Investigate **mechanisms**. Open models expose chain-of-thought; read and code CoT, not just token counts.
- Rigor bar: clear hypotheses, placement in the literature (look at how comparable studies are run, including their flaws), mechanism investigation.
- **Open decision:** `α` and `β` appear separately but only their ratio matters. Default proposal: normalize `α = 1` and vary `β`. Confirm before large runs.

## Open design questions (resolve with a decision record, see Collaboration)

Everything here, and every "current proposal" above, is provisional. Before locking an answer, list at least two alternatives and why you rejected them. Prefer the choice that keeps other options cheap to reach; avoid choices that are merely first-thought or easiest to code.

- **Framing itself:** is a public goods game with a token budget the best operationalization? Alternatives to weigh: raw-output tasks (e.g. "write a story of length x publicly, y privately"), turn-based effort (one fairly solvable problem per turn), non-budgeted effort, or a different game structure. Also whether the normal-form version is a baseline, a comparison, or the main study.
- **Dataset:** an existing task set with known answers; avoid introducing complexity at too many layers. Candidates not yet surveyed.
- **Effort measure:** tokens vs turns vs something else. Tokens is the working default, not a decision. Check that token spend actually tracks effort for the chosen model and mode (e.g. verbose but low-quality reasoning).
- **Budget enforcement:** how `B` is enforced (hard `max_tokens` cutoff, thinking budget, soft instruction) and what happens to truncated answers.
- **Resolution rule** for merging the two agents' shared-task answers.
- **Cooperation index:** equilibrium and social-optimum definitions; derive from the measured `S` and `P_i` curves, and check they behave sensibly before relying on the index.
- **`α`/`β` parameterization:** see the normalization proposal above.
- **Scope:** which hypotheses and extensions belong in the primary study vs follow-ups, once smoke tests show what is feasible.

## Compute tiers

| Tier | Model | Hardware | Purpose |
|---|---|---|---|
| Local smoke | Qwen3.x ~1.5B | laptop | Iterate on code; verify the pipeline end to end; sanity-check that the design can show an effect |
| Cluster | Qwen3.x ~9B (likely; size may change) | Slurm, 3 partitions × 8 L40s (48 GB each); Dorian has priority on one | Real experiments |
| Closed models | TBD | API | Only if funding arrives; design for it now, build later |

- **Local results validate plumbing and rough signal, not science.** 1.5B behavior will differ from 9B. Never put local-model numbers in a result table or claim.
- Pin the exact Qwen3.x checkpoint ids in config (the family name is not enough). Use the same checkpoint across all conditions of an experiment.
- Local and cluster inference backends may differ (e.g. a Mac-friendly runtime vs vLLM on the cluster). Keep one model-client interface so experiment code is backend-agnostic, and record backend + quantization in every run's metadata.
- Put the model behind an interface (`generate(messages, budget, …) → text, reasoning, token counts`) so a closed-model API backend slots in later. Closed APIs differ in how reasoning tokens are exposed or billed; the interface must report which token counts are exact and which are estimated.
- Qwen3 has thinking and non-thinking modes. Record which mode each run uses; reasoning tokens are the effort measure, so the mode is a first-class experimental setting, never a default left implicit.

## Experiment norms

**Smoke before scale.** Every cluster job gets a local smoke run first with the same config at tiny scale. A smoke run answers: does the pipeline run end to end, are token counts recorded correctly, do parsers handle real outputs, does the cost estimate hold, is the effect plausibly detectable.

**Reproducibility.** Each run is defined by a config file checked into git and has a unique run id. Every run records: git commit, config, model checkpoint, backend, seed(s), sampling params, thinking mode, date. Treat a run without this metadata as unusable.

**Raw data first.** Save full transcripts (prompts, messages, reasoning, final answers, token counts) as append-only JSONL, one record per agent-round. Compute metrics in a separate analysis step from the raw files, so a metric can be recomputed without re-running models.

**Token accounting.** Count tokens with the model's own tokenizer on the generated sequence (or the API's reported usage), separately for reasoning vs answer and for shared vs private work. Define once, in one module, how `e_i` is computed; every analysis imports it.

**Pre-register before confirmatory runs.** Before a large run, write down in a decision record: hypotheses, conditions (`β` grid), sample size, metrics, exclusion rules, and analysis. Label results as *confirmatory* (pre-registered) or *exploratory*. Do not tune prompts on the confirmatory problem set; use a separate dev split.

**Statistics.** Many seeds, many problem-set samples per condition; report confidence intervals, not point estimates. Pair comparisons across `β` on the same problem sets.

**Failure handling.** Log and count parse failures, truncations, refusals, and degenerate outputs per condition. Report these rates; silently dropping rows biases the effect.

**Slurm etiquette**
- Submit with checked-in `sbatch` scripts under `slurm/`; log the job id in the run metadata.
- Size requests to the job (a 9B model in bf16 fits on one L40; use more GPUs only for throughput). Prefer job arrays over one giant job, and make jobs resumable (skip completed items on restart) so preemption costs little.
- Dorian's priority partition is for the team's high-value runs; the other two partitions are shared with other users, so request modestly and cancel stuck jobs promptly.
- Smoke-test the `sbatch` script itself (short wall time, tiny config) before the full submit.

**Secrets and data.** API keys and cluster credentials live in environment variables or untracked files, never in git, configs, or transcripts. Large outputs (raw transcripts, model weights) stay out of git; commit configs, code, and small summary tables.

## Collaboration

**Workflow:** branch per task, small PRs into `main`, at least one teammate reviews. Keep `main` runnable. Commit messages state what and why.

**Decision records:** non-obvious design choices (dataset, budget enforcement, resolution rule, `α` normalization, prompt wording) get a short markdown file under `docs/decisions/` with date, options considered, choice, and reason. Link it from the PR. Resolve an open question above by writing one, then delete the question here.

**Progress log:** `docs/log.md`, newest entry on top: date, who, what ran or changed, where results live, what is next. Add an entry whenever a run finishes or a plan changes, so teammates and their assistants can pick up cold.

**Prompts are experimental code.** Store prompt templates in versioned files, never inline in logic. Any prompt change that affects an experiment is a PR with a stated reason, and old results stay tied to the prompt version that produced them.

**Division of labor:** announce in the progress log which experiment or module you are taking before starting, to avoid duplicated cluster runs.

## Notes for AI coding assistants

- Report results faithfully: failing tests, crashed runs, and skipped steps are stated as such. Say "smoke run on 1.5B" whenever that is what ran.
- Ask the human before submitting cluster jobs, launching anything that spends API money, force-pushing, or deleting run outputs.
- Treat the analysis plan as binding: if a result seems to call for a different metric or exclusion rule, flag it to the human and label the new analysis exploratory.
- The design in this file is a working draft. Do not treat the proposal's framing as fixed, and do not defend it for its own sake. If a smoke run or an obvious alternative suggests a better design, say so plainly.
- When a design question above is open, offer two or more options with trade-offs, recommend one, and record the outcome in a decision record rather than choosing silently. Do not let the first idea become the default by inertia.
- Keep the design swappable in code: tasks, effort measure, budget enforcement, resolution rule, payoff function, and prompts live behind small interfaces or config, so changing the design is a config or one-module change, not a rewrite. Avoid building elaborate machinery around a choice that is still open.
- Prefer small, tested modules with a seed argument; deterministic code (scoring, token accounting, resolution rule) gets unit tests, since errors there silently corrupt every result.
- Stack and commands are not yet chosen. When the team picks them (language, env manager, test runner, inference backend), add a `Commands` section here with the exact setup, smoke-run, test, and submit commands.
