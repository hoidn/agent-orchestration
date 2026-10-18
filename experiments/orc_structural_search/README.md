# ORC structural search (phase 0, offline)

Mode 1 of the [structural search driver](../../docs/design/orc_structural_search_driver.md): enumerate the
authored seed catalog on matched tasks, then sample unguided I1 (whole-file rewrite) episodes against one
seed and evaluate every accepted child like a seed. The readout says whether structurally distinct candidates
exist and differ, and how diverse the accepted children are (distinct skeletons, revisit rate, terminal-only
share, collapse above 0.75, and `allocation_distinct`: children with the parent's skeleton but another provider
allocation, which do not count as terminal-only).

| Module | Role |
| --- | --- |
| `config.py` | Experiment configuration: mutable files and definitions, condition, interface, entry, envelopes |
| `candidates.py` | `candidate_id`, snapshots, compilation with the runtime's orchestrator, frozen-surface validation, the I2 one-site transaction |
| `records.py` | Append-only JSONL log, skeleton hash, provider allocation, final-choice rule |
| `evaluation.py` | One evaluation through the public `run` route in a fresh clone behind the comparison-harness shims |
| `metering.py` | Consumption receipts (not yet wired into the driver: consumption is recorded `unavailable`) |
| `ledger.py` | The provider-call ledger `E/calls.json` and each launch's planned maximum of provider calls |
| `driver.py` | Mode 1: catalog enumeration (bounded concurrency), unguided I1 episodes behind the shims, scans, call cap |
| `readout.py` | The mode 1 readout (`E/readout.json`): outcomes, refusals, skeleton diversity, collapse, scan-pending records |
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

```bash
python -m experiments.orc_structural_search.driver --config config.json \
  --seeds experiments/orc_structural_search/seeds/{direct,plan_then_implement,implement_review_revise,best_of_n,implement_check_diagnose_repair}.orc \
  --tasks $RT/experiments/compare/tasks/<task> --runtime $RT \
  --work-root $W --evidence $E --episodes N --agent-cmd '<mutator command>' \
  --eval-timeout-sec 7200 --solution <task>=$SOL --call-cap 160 [--concurrency 4] [--replicates K] [--holdout PATH ...]
```

`--concurrency` bounds the evaluations in flight (a thread pool; each has its own clone, records and state
directories; log and ledger writes are serialized; episodes run one at a time). `--call-cap` bounds the provider
calls of evaluations and episodes in `E/calls.json`: before each launch the driver reserves its planned maximum
(an evaluation: every `provider-result` of the entry module times the `:max` of each enclosing `loop/recur` or
`list/map-effect`; an episode: 1) and refuses it (`CallCapExceeded`) when the ledger total (counted calls of
finished launches, planned maxima of unfinished ones) plus that maximum would exceed the cap; after the launch it
records the calls the shims recorded. A refused evaluation does not stop the others in the pool; the refusal is
raised once all have ended. Judge calls are not in the ledger.

`config.json` is an `ExperimentConfig` (see `config.py`); its `entry_workflow` (e.g. `direct::run`) names the
seed the episodes start from, and every seed is evaluated under `<seed stem>::<entry definition>`. The tests
(`tests/experiments/test_orc_structural_search_driver.py`) run this with scripted providers and a scripted
mutator; no provider is called.

## Layout

`W` (the work root, sandbox-visible) and `E` (the evidence root) must not nest: agents work under `W` and must
never see the archive or the log. `E` must be fresh: the driver refuses an `E/log.jsonl` that already exists and
never resumes an incident (an evaluation without a terminal row stays an incident in the log; `evaluation.resume`
is the operator's tool). Before each episode and evaluation the driver checks that an archived candidate still
hashes to its directory name.

```
W/records/<evaluation_id>/run-1/   run_arm's records: record.json (with the scan), inputs.json, command.sh, calls/
W/runs/<evaluation_id>/<run_id>/   the run's state (memo.jsonl)
W/agents/<tree>/cand-1/            the clone the run works in
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
```

After every evaluation `prepare.scan` runs over its records with `E` and `W/episodes` named `archive`,
`E/log.jsonl` named `lineage` and each `--holdout` named `holdout`. A nonzero hit count marks the evaluation
record `scan_pending`. The log is append-only, so that flag is never cleared: the adjudicated verdict
(`prepare.py scan --run R --verdict ...`) lives in the run's `<records_dir>/record.json`, which is the record to
read before using a flagged evaluation.

After every episode `prepare.scan` runs over `E/episodes/<episode_id>/` with `E` named `archive`, `E/log.jsonl`
`lineage` and each `--holdout` `holdout` (other episodes' trees are the scan's sibling trees), once per distinct
solution hash until a scan hits; hits mark the episode `scan_pending`. Its `record.json` holds the scan that hit:
after clearing it, rescan with the remaining hashes (`prepare.py scan --run E/episodes/<episode_id> --hash ...`).

The evaluation id covers the environment manifest, so it changes with a CLI version; model names are the
candidate's provider bindings and `:model` values, already in its candidate id.

## Not implemented

- Mode 2 (the adaptive loop), the site manifest and I2/I3 episodes.
- Paid runs: no live evaluation has been made; the server-side model revision is recorded `unavailable`.
- Consumption metering in the log (`metering.py` exists; the driver records `unavailable`).
- Isolation of the mutator command itself: only the agent CLIs it starts through `PATH` run in the sandbox; the
  command (e.g. a wrapper script) runs unsandboxed with the shim environment.

## Deviations (`ponytail:`)

- The `dev-check` command boundary runs the task's checks in the working clone; no fresh-checkout patch
  application yet.
- A wall-clock kill (evaluation launch or mutator command) kills the launcher's process group only; a process
  that starts its own session escapes it.
- The call ledger's lock is per driver process: two drivers on one evidence root are not serialized.
- An evaluation's planned maximum counts a provider call in a definition the entry calls several times once (the
  seeds call none of their own definitions), and provider retries are not in it; the ledger records the actual
  calls afterwards.
- An episode scan stops at the first solution hash that hits (see Layout).
