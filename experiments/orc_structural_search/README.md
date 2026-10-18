# ORC structural search (phase 0, offline)

Mode 1 of the [structural search driver](../../docs/design/orc_structural_search_driver.md): enumerate the
authored seed catalog on matched tasks, then sample unguided I1 (whole-file rewrite) episodes against one
seed and evaluate every accepted child like a seed. The readout says whether structurally distinct candidates
exist and differ, and how diverse the accepted children are (distinct skeletons, revisit rate, terminal-only
share, collapse above 0.75).

| Module | Role |
| --- | --- |
| `config.py` | Experiment configuration: mutable files and definitions, condition, interface, entry, envelopes |
| `candidates.py` | `candidate_id`, snapshots, compilation, frozen-surface validation, the I2 one-site transaction |
| `records.py` | Append-only JSONL log, skeleton hash, final-choice rule |
| `evaluation.py` | One evaluation through the public `run` route in a fresh clone behind the comparison-harness shims |
| `metering.py` | Consumption receipts (not yet wired into the driver: consumption is recorded `unavailable`) |
| `driver.py` | Mode 1: catalog enumeration, unguided I1 episodes, scans, readout |
| `seeds/` | The 2.39 seed catalog sharing one entry contract (`run ((task String) (intent String) (repo String)) -> Outcome`) |

## Offline recipe

Prerequisites: the comparison harness's (`experiments/compare/README.md`): git and bwrap on `PATH`, a frozen
runtime checkout `RT` outside the main checkout's prefix, and the shims first on `PATH` for every agent CLI. Each
task package holds `task.txt`, `intent.txt`, `base_commit`, `seed/` and `solution_commit` (the scan's solution
hash). The mutator command runs with the episode copy as its working directory; it must reach any agent CLI
through the shims.

```bash
python -m experiments.orc_structural_search.driver --config config.json \
  --seeds experiments/orc_structural_search/seeds/{direct,plan_then_implement,implement_review_revise,best_of_n,implement_check_diagnose_repair}.orc \
  --tasks $RT/experiments/compare/tasks/<task> --runtime $RT \
  --work-root $W --evidence $E --episodes N --agent-cmd '<mutator command>' \
  --eval-timeout-sec 7200 [--replicates K] [--holdout PATH ...]
```

`config.json` is an `ExperimentConfig` (see `config.py`); its `entry_workflow` (e.g. `direct::run`) names the
seed the episodes start from, and every seed is evaluated under `<seed stem>::<entry definition>`. The tests
(`tests/experiments/test_orc_structural_search_driver.py`) run this with scripted providers and a scripted
mutator; no provider is called.

## Layout

`W` (the work root, sandbox-visible) and `E` (the evidence root) must not nest: agents work under `W` and must
never see the archive or the log.

```
W/records/<evaluation_id>/run-1/   run_arm's records: record.json (with the scan), inputs.json, command.sh, calls/
W/runs/<evaluation_id>/<run_id>/   the run's state (memo.jsonl)
W/agents/<tree>/cand-1/            the clone the run works in
W/episodes/episode-<n>/            the mutator's copy of the parent (the child is its final files)
E/log.jsonl                        episode and evaluation records, append-only
E/candidates/<candidate_id>/       the archive: catalog seeds and accepted children
E/episodes/episode-<n>.log         the mutator command's output
E/readout.json                     per-seed outcomes, episode outcomes and refusals, skeleton diversity
```

After every evaluation `prepare.scan` runs over its records with `E` and `W/episodes` named `archive`,
`E/log.jsonl` named `lineage` and each `--holdout` named `holdout`. A nonzero hit count marks the evaluation
record `scan_pending` until adjudicated (`prepare.py scan --run R --verdict ...`).

## Not implemented

- Mode 2 (the adaptive loop), the site manifest and I2/I3 episodes.
- Paid runs: no live evaluation has been made; model revisions and CLI versions are not yet in the evaluation
  identity.
- Consumption metering in the log (`metering.py` exists; the driver records `unavailable`).

## Deviations (`ponytail:`)

- The `dev-check` command boundary runs the task's checks in the working clone; no fresh-checkout patch
  application yet.
- A wall-clock kill (evaluation launch or mutator command) kills the launcher's process group only; a process
  that starts its own session escapes it.
