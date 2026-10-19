# ORC structural search (offline)

Mode 1 of the [structural search driver](../../docs/design/orc_structural_search_driver.md): enumerate the authored
seed catalog on matched tasks, then sample unguided I1 (whole-file rewrite) episodes against one seed and evaluate
every accepted child like a seed (a revisit, whose candidate id was already evaluated, is logged but not evaluated
again). The readout says whether structurally distinct candidates exist and differ, and how diverse the accepted
children are (distinct skeletons, revisit rate, terminal-only share, collapse above 0.75, and `allocation_distinct`:
children with the parent's skeleton but another provider allocation, which do not count as terminal-only).

Mode 2 (`adaptive.py`, Phase 2 plan
[`2026-10-18-orc-structural-search-phase2-plan.md`](../../docs/plans/2026-10-18-orc-structural-search-phase2-plan.md))
runs generations of interleaved I1 and I2 episodes against an archive (the incumbent plus a quality/call frontier),
judges each generation's evaluations blind, and evaluates the finalists on a held-out validation task. Both modes
are implemented and tested with scripted providers only.

| Module | Role |
| --- | --- |
| `config.py` | Experiment configuration: mutable files and definitions, condition, interface, entry, envelopes |
| `candidates.py` | `candidate_id`, snapshots, compilation with the runtime's orchestrator, frozen-surface validation, the I2 one-site transaction |
| `records.py` | Append-only JSONL log, skeleton hash, provider allocation, final-choice rule |
| `evaluation.py` | One evaluation through the public `run` route in a fresh clone behind the comparison-harness shims |
| `metering.py` | Consumption receipts (not yet wired into the driver: consumption is recorded `unavailable`) |
| `ledger.py` | The provider-call ledger `E/calls.json` and each launch's planned maximum of provider calls |
| `driver.py` | Catalog enumeration (bounded concurrency), the episode function behind the shims, scans, call cap; the mode 1 command line |
| `mode1.py` | Mode 1: `run_mode1` (catalog, unguided I1 episodes, child evaluations, `--continue`) |
| `acceptance.py` | Child judging of an episode (`judge_child`): validation, compilation, the I2 slot check, bounded planned calls, the entry's result type |
| `quota.py` | Provider quota incidents: detection in shim call records, the reset-time pause, attempt relaunches, `--continue` row selection |
| `readout.py` | The mode 1 readout (`E/readout.json`): outcomes, refusals, skeleton diversity, collapse, scan-pending records |
| `sites.py` | I2: the candidate's source-site manifest, eligible sites, seeded site selection, the site brief, receipt derivation |
| `briefs.py` | The mutator's `EPISODE.md` (I1, I2, and mode 2 feedback) |
| `adaptive.py` | Mode 2: `run_mode2` (archive, generations, parent and site selection) and `validate_finalists` |
| `judging.py` | Mode 2 per-generation blind judging: pools, judge ledger entries, waiting for scan verdicts, judge retry |
| `scoring.py` | Blind judging pools, the join of judge scores to evaluation records, the Phase 1 readout and `--joined-out` |
| `scoring_phase2.py` | The Phase 2 readout (`scoring readout --phase 2`) |
| `criteria/` | The frozen Phase 1 and Phase 2 criteria (`phase1.json`, `phase2.json`) |
| `seeds/` | The 2.39 seed catalog sharing one entry contract (`run ((task String) (intent String) (repo String)) -> Outcome`) |

## Offline recipe

Prerequisites: the comparison harness's (`experiments/compare/README.md`): git and bwrap on `PATH` and a frozen
runtime checkout `RT` outside the main checkout's prefix. The driver puts `$RT`'s shims first on `PATH` for every
evaluation and episode itself; the launch environment's `PATH` must reach the real `claude` and `codex`. Each
task package holds `task.txt`, `intent.txt`, `base_commit` and `seed/`, and `seed/` must hold `dev-check.json`
(`{"argv": [...], "timeout_sec": N}`, the agent-visible checks): without it the `dev-check` boundary fails
closed, so `implement_check_diagnose_repair` always repairs. The operator passes each task's solution commit
(the scan's solution hash) with `--solution TASK=HASH`, keyed by the package directory's name; a task without
one, or whose hash has fewer than 7 hex characters or is not a commit of `$RT` (`git cat-file -t`), is refused
before anything runs; hashes are lowercased before use. The hash never goes into the package, which sits in the
runtime agents can read.

The mutator command (`--agent-cmd`, e.g. `claude -p --model claude-opus-5-5 --permission-mode bypassPermissions`,
the flags of the runtime's `claude_unrestricted_workspace` provider template, so the agent can edit and run the
compile check) runs from the episode's `cand-1` with the brief (`EPISODE.md`) on stdin, behind the shim prefix:
each `claude` or `codex` call it makes is recorded under `E/episodes/<episode_id>/calls/<n>/` with its patch
against the parent snapshot, runs under bubblewrap and passes the model guard (a Fable model is refused; the
command then exits nonzero and the episode is an `incident`). The bubblewrap sandbox (private `/tmp`, process
list) and the episode workspace contain the unrestricted permissions: only `cand-1`'s final content files become
the child, and the scan reports reads outside it. The brief's compile line is
`PYTHONPATH=../py python -P -m orchestrator compile ...`: the shims strip `PYTHONPATH`, so the driver copies the
runtime's `orchestrator/` to `W/episodes/episode-<n>/py/` (outside `cand-1`), and the relative path keeps the
runtime's path out of the session. A mutator that removes or replaces `cand-1/.git` makes the episode an
`incident` (`workspace_intact: false`). The driver adds `DISABLE_AUTOUPDATER=1` to the environment of every
evaluation and episode, so no CLI updates itself mid-run.

For an ordinary attempt (`ORCHESTRATOR_WORKSPACE_ROOT` unset) the shims (`experiments/compare/shim/claude`, see
`experiments/compare/README.md`) also strip its `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and
`ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY` from the agent and every process it starts. The task repositories are the
orchestrator itself, whose code and tests read these variables, so an agent running the task's tests overwrote its
own result file (the 2026-10-18 incident); the prompt's `- path:` line names the result file relative to the
agent's working directory. A launch-workspace attempt keeps all three variables, because its prompt tells the agent
to use them; the overwrite risk remains there and is disclosed, not prevented.

```bash
python -m experiments.orc_structural_search.driver --config config.json \
  --seeds experiments/orc_structural_search/seeds/{direct,plan_then_implement,implement_review_revise,best_of_n,implement_check_diagnose_repair}.orc \
  --tasks $RT/experiments/compare/tasks/<task> --runtime $RT \
  --work-root $W --evidence $E --episodes N --agent-cmd '<mutator command>' \
  --eval-timeout-sec 7200 --solution <task>=$SOL --call-cap 160 [--concurrency 4] [--replicates K] [--holdout PATH ...] \
  [--hide PATH ...] [--continue]
```

`--concurrency` (default 4) bounds the evaluations in flight (a thread pool; each has its own clone, records and
state directories; log and ledger writes are serialized; episodes run one at a time). `--call-cap` bounds the
provider calls of evaluations and episodes in `E/calls.json`: before each launch the driver reserves its planned
maximum (an evaluation: `ledger.max_provider_calls`, the provider calls of the module's own definitions the entry
calls, in expression positions, times every enclosing literal `:max`; an episode: 1) and refuses it
(`CallCapExceeded`) when the ledger total (counted calls of finished launches, planned maxima of unfinished ones)
plus that maximum would exceed the cap; after the launch it records the calls the shims recorded. A refused
evaluation does not stop the others in the pool; the refusal is raised once all have ended. Judge calls are not in
the ledger.

**Quota guard** (`quota.py`). In the live Phase 1 run of 2026-10-18, 16 of 20 evaluations and all 6 unguided
episodes ended at the Claude subscription session limit: the CLI printed `You've hit your session limit · resets
5:30pm (America/Los_Angeles)` on stdout and exited 1, the runtime recorded `provider_exit_nonzero`, and the driver
logged `failed` (evaluations) or `incident` (episodes). Those are infrastructure incidents, not agent failures. A
launch whose shim calls (`calls/<n>/stdout.txt`, `stderr.txt`) hold a quota line (a line starting with `you've hit
your <word> limit`, `usage limit reached`, `rate limit reached` or Codex's transient `selected model is at
capacity`, case-insensitive; see `quota.py`) and that did
not complete is now an `incident` whose latest incidents entry is `quota: <line>` (episodes: an `incidents` list).
The driver then starts no new launch until the reset the message names (`resets H[:MM]am|pm (Zone)` today in
that zone, plus 5 minutes; a time at most 3 hours past resumes in 5 minutes, an earlier one tomorrow; 30 minutes
when none parses), printing one line with the resume
time; launches in flight that hit the limit join that pause. The job is then relaunched as a new attempt: an
evaluation's id covers its attempt number after the first (first attempts keep their ids), and a quota episode
is rerun under the next episode index. A job is relaunched at most 3 times per invocation; then it stays a quota
incident. The guard is the only throttle: concurrency stays as given.

**`--continue`** continues the run in an existing `E` with its own `W` (the evaluations' records must lie under
it) instead of refusing `E/log.jsonl`. The log, the ledger and the archive are appended to, never rewritten. Each
catalog or accepted-child job whose latest row (per candidate, task and replicate) is completed, a genuine
failure or another incident is kept; one whose latest row is a quota incident is relaunched as its next attempt,
and so is a `failed` row written before the guard existed whose records hold a quota line. Unguided episodes
continue after the highest existing index until `--episodes` non-quota episodes exist (quota episodes, including
pre-guard `incident` rows whose shim records hold a quota line, do not count). A launch killed in flight (the
driver died) left no row: its attempt number (`W/records/<evaluation id>` exists and no log row names that id) or
episode index (`W/episodes/episode-<n>` exists) is skipped, and its unsettled ledger entry is settled from its shim
records; an attempt whose records exist and whose id a log row names is refused (`FileExistsError`).
`E/readout.json` is rewritten;
quota rows read as `quota_incident` there.

`config.json` is an `ExperimentConfig` (see `config.py`); its `entry_workflow` (e.g. `direct::run`) names the
seed the episodes start from, and every seed is evaluated under `<seed stem>::<entry definition>`. The tests
(`tests/experiments/test_orc_structural_search_driver.py`) run this with scripted providers and a scripted
mutator; no provider is called.

## Mode 2 recipe

Mode 2 starts from Phase 1's scored rows. Write them with the Phase 1 readout's `--joined-out` (every task's joined
rows plus its failed, timed-out and incident evaluations):

```bash
python -m experiments.orc_structural_search.scoring readout --log $E1/log.jsonl --driver-readout $E1/readout.json \
  --criterion experiments/orc_structural_search/criteria/phase1.json --joined-out $J/joined.json \
  $P1/<task>/records/results.json ...
```

`adaptive.py` has no command line; the entry point is `run_mode2` (prerequisites as in the offline recipe; every
task package's `seed/dev-check.json` included):

```python
import os, shlex
from pathlib import Path
from experiments.orc_structural_search.adaptive import run_mode2

tasks = Path(RT) / "experiments/compare/tasks"
readout, launch = run_mode2(Path("config.json"), phase1_joined=Path(J) / "joined.json",
          seeds=sorted(Path("experiments/orc_structural_search/seeds").glob("*.orc")),
          adaptive_tasks=[tasks / "resume-projection-integrity", tasks / "pure-result-replay"],
          validation_task=tasks / "cf1-generic-unions",
          generations=G, episodes_per_generation=4, run_seed=S,
          work_root=Path(W), evidence_root=Path(E), pools_root=Path(P),
          agent_cmd=shlex.split("<mutator command>"), runtime=Path(RT), env=os.environ, timeout_sec=7200,
          solutions={"<task>": "<solution commit>", ...}, call_cap=N, concurrency=4,
          criterion=Path("experiments/orc_structural_search/criteria/phase2.json"),
          judges=["claude-opus-5-5", f"gpt-6-sol={RT}/experiments/compare/providers/score_codex.json"])
```

`E` and `W` must both be fresh for each run: the driver refuses an existing `E/log.jsonl`, and episode trees are
named by index (`W/episodes/episode-<n>`), so a second run in the same `W` collides with the first.

`run_mode2` refuses tasks other than the criterion's `adaptive_tasks` and `validation_task` (`check_splits`), a pools
root inside `E` or `W` or holding either (`check_pools_root`), and an existing `E/log.jsonl`. Generation 0 archives the
seeds, builds the initial archive from the Phase 1 rows (refused without `direct` valued on every adaptive task),
logs the reference row and re-evaluates and judges the incumbent once per adaptive task. Each generation `n` runs
`episodes_per_generation` episodes alternating I1 and I2, each against a parent drawn uniformly from the archive (I2:
at a seeded uniform eligible site) with the parent's own evidence as feedback; fresh accepted children are evaluated
once per adaptive task, judged, and offered to the archive. Before a generation's episodes, one planned call per
episode plus the evaluations and judges of as many children (each at the largest planned maximum in the archive),
and again before its evaluations, the children's own planned calls plus one planned call per judge per batch, must
fit under `call_cap`, or the generation is refused (`CallCapExceeded`); `E/readout.json` is still written. A
planned maximum (`ledger.max_provider_calls`) counts the provider calls of the module's own definitions the entry
calls (in expression positions; binder names are no calls), times every enclosing literal `:max`. A non-literal
`:max` around a provider call, or a recursion reaching one, makes it unbounded: such a child is refused at episode
acceptance (`unbounded_calls`, in both modes) and never evaluated. The validation
task is a holdout root of every episode scan and adaptive evaluation scan (judge scans take no holdout root).

Mode 2 does not stop on routine scan hits: before pooling a task's evaluations and before summarizing a pool, it
waits for a verdict on every run or judge scan with hits, printing once the hit summary and the exact
`prepare.py scan --run R` (or `--pool P --judge MODEL`) `--verdict contaminated|cleared --reason TEXT` command, and
rereads the scan every 60 s. Contaminated runs stay out of the pool. A judge whose scoring command exits nonzero is
retried once through its resume script; a second failure is a judge incident (a `judge_incident` log row, no
`gen-<n>.json` for that generation) and the run continues with the next generation.

Afterwards `validate_finalists(E/archive/gen-<n>.json, config=..., validation_task=..., launch=launch, judge=...)`
(`launch` as `run_mode2` returned it; the reference comes from the log's `reference` row) evaluates the top two
archive entries, the reference and `direct` twice each on the validation task (`split: "validation"`) and judges
them in one pool at `P/validation/<task>`; the Phase 2 readout is

```bash
python -m experiments.orc_structural_search.scoring readout --phase 2 \
  --criterion experiments/orc_structural_search/criteria/phase2.json \
  --log $E/log.jsonl --archive $E/archive [--log ... --archive ...] \
  --validation-log $E/log.jsonl $P/validation/cf1-generic-unions/records/results.json
```

**Failure rule.** The primary value of an evaluation (`scoring.primary_value`) is its judged value when completed and
0 rubric points when failed or timed out; a timeout is an incident killed at its wall-clock envelope (`launcher exit
-9` in its latest incidents entry, `scoring.scored_outcome`). Every other incident, and a completed run without a
value, is excluded, not zero; so is a quota incident (`quota_incident`, counted as `quota_incidents`), including
a `failed` row from before the quota guard whose records hold a quota line. Log rows count once per job
(candidate, task, replicate, and mode 2's split and generation; the last row wins, so a quota relaunch supersedes
its quota incident). A task with no completed, uncontaminated evaluation has no pool; its rows come from the log alone (`scoring.log_only_pool`).

## Layout

`W` (the work root) and `E` (the evidence root) must not nest: agents work under `W` and must
never see the archive or the log. `E` must be fresh unless the run is continued (`--continue`, above): the
driver refuses an `E/log.jsonl` that already exists and never resumes an incident (an evaluation without a
terminal row stays an incident in the log; `evaluation.resume` is the operator's tool). Before each episode and evaluation the driver checks that an archived candidate still
hashes to its directory name.

What the mutator cannot see: every `claude` or `codex` call of an episode runs with the shims' `COMPARE_HIDE`
naming `E`, `W/episodes`, `W/records`, `W/runs`, `W/agents`, `W/env-manifests` and each mode 1 `--hide` directory
(`driver.hidden_roots`, created if missing and recorded as the episode row's `hidden_roots`). The shims mask each
with an empty tmpfs and bind the episode's own tree back, so the call reads its `cand-1`, `tmp/` and `py/` but
no sibling episode, evaluation, archive candidate or log row; a path into them is not found. With a `claude` or
`codex` `--agent-cmd` that is the whole mutator; a mutator command that is neither runs outside the sandbox and
only its CLI calls are masked. The mask names roots and is no allowlist: home, the runtime and every other
directory stay readable and only the scan reports reads there, so pass other runs' roots with `--hide`.

```
W/records/<evaluation_id>/run-1/   run_arm's records: record.json (with the scan), inputs.json, command.sh, calls/
W/runs/<evaluation_id>/<run_id>/   the run's state (memo.jsonl); none for an I3 evaluation
W/agents/<tree>/cand-1/            the clone the run works in
W/agents/<tree>/cand-1/.orchestrate/runs/<run_id>/
                                   I3: the Python run's state (terminal.json, effects/<n>/attempt-1/result.json)
W/env-manifests/<digest>.json      Python, platform, distributions and claude/codex/bwrap/git --version output
W/episodes/episode-<n>/cand-1/     the mutator's copy of the parent, a git repository whose one commit is the parent
                                   snapshot (the shims' COMPARE_BASE); the child is its final files (.git removed)
W/episodes/episode-<n>/tmp/        the mutator's private /tmp under the shims
W/episodes/episode-<n>/py/         a copy of the runtime's orchestrator/ for the brief's compile line
E/log.jsonl                        episode and evaluation records, append-only
E/calls.json                       the provider-call ledger, one entry per evaluation and episode
E/candidates/<candidate_id>/       the archive: catalog seeds and accepted children
E/episodes/episode-<n>.log         the mutator command's output
E/episodes/<episode_id>/           the episode's shim records: calls/<n>/, record.json (with the scan)
E/episodes/<episode_id>.diff       the episode's final diff against its parent, accepted or refused
E/readout.json                     per-seed outcomes, episode outcomes and refusals, skeleton diversity
                                   (mode 2: per-interface episode readouts and the archive trajectory)
E/archive/gen-<n>.json             mode 2: the archive after generation n (gen-0: every valued seed, direct included)
P/gen-<n>/<task>/                  mode 2: the generation's blind judging pool (P/validation/<task> for finalists);
                                   P, the pools root, lies outside E and W: judges must not see the archive or the
                                   log, and mutators and evaluated agents must not find the pools at a known place
```

An I3 candidate (a Python entry module, `evaluation.is_python`) is admitted by `acceptance.check_python` (pyright)
instead of the compiler and runs through the comparison harness's generic-command arm: `record.json` names
`arm_kind: generic-command` and its `state_root` (the clone's `.orchestrate/runs`, the evaluation record's
`state_dir`), and `command.sh` runs `python -P <candidate>/direct.py inputs.json` behind the same shims, so its
calls, patches and scans are recorded like an ORC evaluation's. The run's `terminal.json` is classified like a
memo's terminal row (`completed`, `failed`; none: `incident`) and `prepare.collect` reads it; other directories
there, such as an orchestrator run the coder started from the clone, are not the run. There is no `resume.sh`: an
I3 incident is not resumable (`evaluation.resume` refuses it), and one killed before its terminal is recorded with
run id `unavailable`.

Mode 2 adds four kinds of log rows: one `{"kind": "reference", "candidate_id", "run"}` row naming the initial
incumbent; one `{"kind": "judging", "generation", "task", "pool", "results"}` row per judged pool; one
`{"kind": "judge_incident", "generation", "detail"}` row per generation a judge failed twice; and every
evaluation row carries `generation` and `split` (`adaptive`, or `validation` with generation -1). Each judge of a
pool has a `kind: "judge"` entry in `E/calls.json`, reserved (one planned call per batch) before any judge runs; the
judging records (`mapping.json`, each judge's records, `results.json`) are under `P/.../records/`.

After every evaluation `prepare.scan` runs over its records with `E` and `W/episodes` named `archive`,
`E/log.jsonl` named `lineage` and each `--holdout` named `holdout`. A nonzero hit count marks the evaluation
record `scan_pending`. The log is append-only, so that flag is never cleared: the adjudicated verdict
(`prepare.py scan --run R --verdict ...`) lives in the run's `<records_dir>/record.json`, which is the record to
read before using a flagged evaluation.

After every episode `prepare.scan` runs over `E/episodes/<episode_id>/` with `E`, `W/records`, `W/runs`, `W/agents`
and `W/env-manifests` named `archive`, `E/log.jsonl` `lineage` and each `--holdout` `holdout` (other episodes' trees
are the scan's sibling trees), once per distinct solution hash until a scan hits; hits mark the episode
`scan_pending`. Its `record.json` holds the scan that hit: after clearing it, rescan with the remaining hashes
(`prepare.py scan --run E/episodes/<episode_id> --hash ...`). A contaminated episode verdict (the mutator read
sibling episodes' trees or the evidence root) takes its child out of the Phase 1 readout: every row of that child is
left out and the readout lists it under `excluded_children` (`scoring.contaminated_children`); mark the child's
evaluation records contaminated too so the pool leaves them out. The scan matches path patterns, not reads: it
catches a literal `episode-N` and absolute (or `~`) paths into those roots, but misses relative reads
(`../../records/...`, the work root's `records/`, `runs/` and `agents/` included) and globs (`episode-$i`,
`episode-*`, `W/rec*`), which give no hit at all. Read every accepted episode's transcript commands, those with no
hits included, before the readout (Phase 1, 2026-10-19: episode 11's
`for e in 6 7 8 9 10; do diff ... episode-$e/...` had no driver hit).

The evaluation id covers the environment manifest, so it changes with a CLI version; model names are the
candidate's provider bindings and `:model` values, already in its candidate id.

## Not implemented

- I3 in mode 2 (it interleaves I1 and I2; `run_episode` and `evaluate` take I3 candidates), feedback-targeted
  site selection and failure- or cost-weighted parent selection (mode 2 draws uniformly).
- A command line for mode 2 (`run_mode2` and `validate_finalists` are called from Python).
- Live mode 2: the live Phase 1 decision did not select Phase 2 for family (a)
  ([Phase 1 report](../../docs/reports/2026-10-18-orc-structural-search-phase1.md)); a live run needs a new owner
  selection and budget approval. The server-side model revision is recorded `unavailable`.
- Consumption metering in the log (`metering.py` exists; the driver records `unavailable`).
- A quota guard for mode 2: mode 2 has no quota guard for episodes, and each `evaluate_all` starts an unpaused guard
  (`adaptive.py`), so a quota episode is an incident that uses its slot and a generation's first evaluations can hit
  the limit again before they pause.
- Isolation of the mutator command itself: only the agent CLIs it starts through `PATH` run in the sandbox; the
  command (e.g. a wrapper script) runs unsandboxed with the shim environment.

## Deviations (`ponytail:`)

- The `dev-check` command boundary runs the task's checks in the working clone; no fresh-checkout patch
  application yet.
- A wall-clock kill (evaluation launch or mutator command) kills the launcher's process group only; a process
  that starts its own session escapes it.
- The call ledger's lock is per driver process: two drivers on one evidence root are not serialized.
- An evaluation's planned maximum (`ledger.max_provider_calls`) counts the provider calls of the module's own
  definitions the entry calls (in expression positions; binder names are no calls), times every enclosing literal
  `:max`; provider retries are not in it, and the ledger records the actual calls afterwards.
- A mode 2 frontier wider than the archive size keeps its best-valued members (`adaptive.prune`), no crowding
  distance.
- An episode scan stops at the first solution hash that hits (see Layout).
