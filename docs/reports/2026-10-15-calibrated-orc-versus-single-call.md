# E-B2: Maintained Workflows Against A Single Call On A Calibrated Task

Status: complete. The criterion was frozen and committed before any batch run. The sections below were filled in
after the one `summarize` over the final pool.

**Result.** Both claims were evaluated, with all three runs per arm completed and none excluded, and neither holds.
- `design_review_execute` passed the same share of hidden tests as the single call: 0.49 for both arms, so the gain
  is 0.00, against at least +0.30 required.
- `reviewed_change`'s review loop did not raise its own first patch's hidden acceptance in any run: the gain was 0 in
  all three runs, against a mean of at least +0.10 required.

The judges, which bear only on secondary entries, scored `design_review_execute` 1.0 point above the single call on
the 0–8 scale. They scored `reviewed_change`'s final patches 0.33 above its first patches. `design_review_execute`
took 4.9 times the single call's wall clock and `reviewed_change` 2.0 times.

## Question And Criterion

The task is rung 3 of the difficulty calibration, `adopted-attempt-lineage` (base `db210752`, solution `1eb06773`).
Two questions are judged separately:
- Does `design_review_execute` deliver more of the hidden acceptance tests than one `gpt-6.1-sol` call, given the
  same task text and the same executor time limit? Here Opus plans and revises, and `gpt-6.1-sol` reviews and
  executes.
- Does `reviewed_change`'s review loop raise its own first patch's hidden acceptance? Here a Sonnet coder works under
  a `gpt-6-sol` reviewer.

- **Criterion:** [`experiments/compare/criteria/eb2.json`](../../experiments/compare/criteria/eb2.json).
  - SHA-256 `26e1346e3488eee77e6c0473d15714c3270816327d90028d82992ada42fb9a75`.
  - Frozen and committed in `7161ca02` at 02:04 PDT on 2026-10-15. The first batch run started at 02:05.
  - An Opus reviewer returned NEEDS CHANGES. An Opus author applied all 15 accepted fixes, and a second Opus review
    approved the result.
  - Both scoring runs bound this hash, and no amendment was made.
- **Runtime:** `/home/ollie/compare-runtime` at `e8882086`, with no tracked changes. Every run's `record.json`
  `runtime_commit` and `mapping.json` name this commit, which the controller checked.
- **Package:** SHA-256 `c5ebb75803cbdb19eabff4c1f0e5e9627ab399fb6733192581961f5957e628b9`, recomputed at the runtime
  before the freeze and again after pooling. The package has 52 hidden node ids in three test modules:
  - 36 in `test_retirement_attempt_migration.py`;
  - 10 in `test_retirement_broad_evidence.py`;
  - 6 in `test_retirement_source_bindings.py`.
- **Arms:**
  - `design_review_execute`: planner `claude-opus-5-5` and reviewer `gpt-6.1-sol`; the executor is `gpt-6.1-sol`
    with 14400 s.
  - `reviewed_change`: coder `claude-sonnet-5-5` and reviewer `gpt-6-sol`, with 5400 s per call.
  - Control `direct_task`: `gpt-6.1-sol`, effort high, 14400 s.
  - Three runs per arm, with run floors of three. No `best_of_n` arm.
- **Owner decisions of 2026-10-15:**
  - rung 3, qualified on the blocker rule alone;
  - an Opus planner instead of `claude-fable-5-1`;
  - three runs per arm;
  - no `best_of_n` arm.
- **Rulings:** R52 (with its amendment), R53 and R54. They are listed in the plan's appendix.
- **Design:** [`docs/design/orc_effectiveness_comparison_harness.md`](../design/orc_effectiveness_comparison_harness.md).

## The Calibration It Rests On

The [calibration report](2026-10-14-task-difficulty-calibration.md) (criterion
`3149bc36e6b822eba5e7d735abacad6bb145487259c0d0b090feb837daedab66`) measured rung 3 as follows:
- two `gpt-6.1-sol` single calls passed 27/52 (0.519) and 16/52 (0.308) of the hidden tests;
- the `gpt-6-sol` review of each patch returned `REQUEST_CHANGES`, with 1 and 1 blockers (mean 1.0);
- the upstream anchor passed 52/52 and the stub 0/52.

Rung 3 does not meet the frozen calibration criterion, because one single call passed more than half. The owner chose
it on the blocker rule alone (mean ≥ 1). Of the four rungs it had the lowest single-call hidden mean (0.41). The
calibration's historical conclusion stands: no rung qualified under its criterion.

## Smoke

Before the freeze, one mechanics smoke per treatment arm ran on `eb-repl` at the same runtime. Neither run was pooled
or measured.
- `reviewed_change` run-1 completed in 1733 s: 6 provider starts paired with 6 shim calls, first and final patches
  collected, 0 scan hits.
- `design_review_execute` run-1 completed in 6197 s: 4 starts paired with 4 calls, final patch collected, 8 scan hits,
  all cleared.

An Opus evidence auditor passed both. `direct_task` had no E-B2 smoke under R52 as amended. Its mechanics rest on
rung 3's `direct_task` runs 5 and 6, at a harness that differs from `e8882086` only in `summarize.py`. The smoke work
root was deleted after its evidence was copied.

## Runs

All nine runs completed, and none was resumed, relaunched or replaced. They ran from 02:05 to 04:56 PDT, at most four
at a time. Every run's scan hits were adjudicated and cleared; none was contaminated.
- **Hidden:** the passed share of the 52 hidden node ids.
- **Value:** the mean of both judges' totals on the 0–8 scale.

| run | hidden (final) | hidden (first) | hidden paired gain | value | per judge (Opus / GPT) | paired gain | calls | wall clock | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `design_review_execute` run-1 | 30/52 (0.58) | | | 5.5 | 7 / 4 | | 4 | 5773 s | |
| `design_review_execute` run-2 | 30/52 (0.58) | | | 5.5 | 7 / 4 | | 4 | 6096 s | |
| `design_review_execute` run-3 | 16/52 (0.31) | | | 6.0 | 6 / 6 | | 4 | 6950 s | |
| `reviewed_change` run-1 | 16/52 (0.31) | 16/52 (0.31) | 0 | 4.5 | 4 / 5 | +1.5 | 6 | 2096 s | `UNRESOLVED` after three review rounds |
| `reviewed_change` run-2 | 21/52 (0.40) | 21/52 (0.40) | 0 | 5.0 | 6 / 4 | −0.5 | 4 | 3679 s | `READY` after one revision |
| `reviewed_change` run-3 | 16/52 (0.31) | 16/52 (0.31) | 0 | 4.0 | 6 / 2 | 0 | 6 | 2020 s | `UNRESOLVED` after three review rounds |
| `direct_task` run-1 | 30/52 (0.58) | | | 4.5 | 6 / 3 | | 1 | 1430 s | |
| `direct_task` run-2 | 30/52 (0.58) | | | 5.0 | 7 / 3 | | 1 | 1132 s | |
| `direct_task` run-3 | 16/52 (0.31) | | | 4.5 | 6 / 3 | | 1 | 1252 s | |

- **Per-judge totals.** They are the sums of each judge's four criterion ratings in `results.json`
  (`clones.<id>.ratings`). Summarize joins those ratings to clones by clone id.
- **`reviewed_change`'s first patches.** The judges scored them 4 / 2 (run-1), 6 / 5 (run-2) and 4 / 4 (run-3),
  means 3.0, 5.5 and 4.0. Every run's first and final patches differ, so each was pooled twice, once in each stage
  batch.
- **Hidden acceptance has three levels.** Every treatment and control patch passes all 16 node ids of
  `test_retirement_broad_evidence.py` and `test_retirement_source_bindings.py`. It then fails one of three nested sets
  in `test_retirement_attempt_migration.py`, with identical node ids at each level (`results.json`,
  `clones.<id>.hidden_failed`):
  - 22 failing node ids: 30/52, four patches;
  - 31 failing node ids: 21/52, both of `reviewed_change` run-2's patches;
  - all 36 failing: 16/52, six patches.

  In a copy of one 16/52 clone and one 30/52 clone, all 202 tests of that module collected (`--collect-only`). One
  sampled failing node id, run alone on the 16/52 copy, failed behaviourally with `AttemptMigrationError
  incident_known_failure_baseline_binding_invalid`. These diagnostics changed no number. The three levels are the
  clusters these 12 patches fell into; the metric's resolution is still 1/52, and other patches could pass other
  subsets.
- **The arms do not separate on hidden acceptance.** `design_review_execute` and the control each have two runs at
  30/52 and one at 16/52. Each of `reviewed_change`'s revisions left the hidden fraction where its first patch was.

## Scores, Anchors And Agreement

| measure | both judges (verdict) | `claude-opus-5-5` alone | `gpt-6-sol` alone |
| --- | --- | --- | --- |
| `direct_task.mean` | 4.67 | 6.33 | 3.00 |
| `design_review_execute.mean` | 5.67 | 6.67 | 4.67 |
| `design_review_execute.minus_control` | +1.00 | +0.33 | +1.67 |
| `reviewed_change.mean` | 4.50 | 5.33 | 3.67 |
| `reviewed_change.paired_gain_mean` | +0.33 | +0.67 | 0.00 |
| `reviewed_change.minus_control` | −0.17 | −1.00 | +0.67 |

- **Where the numbers come from.** The "both judges" column is `summarize`. The per-judge columns are means of the
  per-judge totals in `results.json`. They are reported, not used (`judge_rules`).
- **Hidden measures** (`summarize`):

  | measure | value |
  | --- | --- |
  | `design_review_execute.hidden_mean` | 0.49 |
  | `direct_task.hidden_mean` | 0.49 |
  | `reviewed_change.hidden_mean` | 0.34 |
  | `reviewed_change.hidden_paired_gain_mean` | 0.00, runs positive 0, runs negative 0 |
  | `design_review_execute.hidden_minus_control` | 0.00 |
  | `reviewed_change.hidden_minus_control` | −0.15 |

- **Anchors.** The upstream anchor passed 52/52 of the hidden tests in all three batches, and the stub 0/52. This
  validity condition was checked before any measured outcome was read.

  | judge | stub score per batch | upstream score per batch |
  | --- | --- | --- |
  | `claude-opus-5-5` | 1, 1, 1 | 8, 5, 4 |
  | `gpt-6-sol` | 2, 0, 1 | 6, 6, 2 |

  In batch 2 (`design_review_execute` and the control), both judges scored the upstream change below every arm
  patch: 4 and 2. The judges' scale does not track hidden acceptance on this task. Nothing was adjusted or
  re-scored because of it (`anchor_use`).
- **Agreement over the 18 clones:**
  - exact agreement per criterion (`summarize`): root cause 7/18, scope 14/18, generality 6/18, layering 11/18;
  - Pearson r = 0.64 between the two judges' totals, with a mean absolute difference of 1.83 points; computed from
    `results.json`;
  - `gpt-6-sol` scores about 1.5 points lower than `claude-opus-5-5`.

## Contamination Scan

Every run and both judges were scanned with the full solution hash `1eb06773029df5c62d81c10e0d60ea6f72c81ab7` and the
path patterns. Each hit was read in the original shim output, Claude session or Codex rollout. The reason for every
verdict is in `record.json`, and in `scan.json` for judges.

| scanned | hits | verdict and what they were |
| --- | --- | --- |
| `design_review_execute` runs 1–3 | 35, 55, 75 | cleared; see the list below |
| `direct_task` runs 1–3 | 15, 21, 45 | cleared; see the list below |
| `reviewed_change` run-1 | 0 | none needed |
| `reviewed_change` run-2 | 2 | cleared: the tmux skill's text |
| `reviewed_change` run-3 | 1 | cleared: see the list below |
| judge `claude-opus-5-5` | 6 | cleared: see the list below |
| judge `gpt-6-sol` | 4 | cleared: see the list below |

- **`design_review_execute` and `direct_task`:** the agents' own tmux sockets inside the bubblewrap-private `/tmp`. Each
  socket named is present in that tree's `tmp/`. Every Codex subagent rollout has a parent thread from the same call
  and its working directory in the run's own `cand-1`. The rest of these hits are:
  - the tmux and finishing-a-branch skills' text, including `gh pr create`; no `gh`, push or fetch was executed;
  - `ps` output from the run's own PID namespace.
- **`reviewed_change` run-3:** the reviewer ran `rg` over its own candidate and matched a `pytest.junit.xml`
  committed at the task base. That file quotes a main-checkout test path.
- **Judge `claude-opus-5-5`:** the judge read its own sessions' persisted tool outputs under its own judge project
  directory.
- **Judge `gpt-6-sol`:** in its third call the judge ran `rg` over its own working directory, which holds its
  `--state-dir`. The output printed its own `run.json` and `state.json`, which name the score inputs and the frozen
  `score.orc` path, and 75 lines of its own batch-2 transcript. That `state.json` also holds the judge's own
  ratings of batches 1 and 2 (20 rating objects: 10 clones, each listed twice), so the judge saw its earlier ratings
  before rating batch 3. Batch 3's clones are disjoint from batches 1–2, and no mapping, arm or solution was exposed.
  It opened no runtime file, mapping, patch or run record.

No hit named `.worktrees/omp-i1-prerequisites`, the worktree that the stale editable install exposes (Limits).

## Cost

- **Agent calls in the batch:** 31.
  - `design_review_execute`: 12 calls, 6 `claude-opus-5-5` planner calls and 6 `gpt-6.1-sol` calls (3 reviewer,
    3 executor).
  - `reviewed_change`: 16 calls, 8 `claude-sonnet-5-5` coder calls and 8 `gpt-6-sol` reviewer calls.
  - `direct_task`: 3 `gpt-6.1-sol` calls.
- **Judges:** 3 `claude-opus-5-5` calls and 3 `gpt-6-sol` calls, one per batch. No judge stopped and no clone was
  restored: `verify-pool` passed after each judge.
- **Smoke:** 10 calls.
- **Mean wall clock per run:** `design_review_execute` 6273 s, `reviewed_change` 2598 s, `direct_task` 1271 s.
  These were measured with up to four runs live.
- **Codex:** the account's weekly window went from 0% used (00:07, before the smoke) to 13% (02:03, before the batch)
  and then to 40% (05:25, after both judges). The credit balance stayed at 28549.41. These readings are account-wide:
  other sessions shared the window, so the change is an upper bound, not this experiment's own cost. Readings are in
  the evidence directory, `eb2/codex-usage.txt`.
- **Anthropic usage** is not metered by the harness.

## Verdict

| claim | clauses | holds |
| --- | --- | --- |
| `design_review_execute` | `hidden_minus_control` 0.00 (≥ 0.3 required); runs 3 (≥ 3); control runs 3 (≥ 3) | **no** |
| `reviewed_change` | `hidden_paired_gain_mean` 0.00 (≥ 0.1 required); runs negative 0 (≤ 0); runs 3 (≥ 3) | **no** |

- **Both claims were evaluated.** Every run floor was met. Under the verdict rules, a missed floor would have left a
  claim "not evaluated", not failed.
- **Secondary entries** never change a verdict:
  - `design_review_execute.minus_control`: +1.00 (≥ 0), met;
  - `reviewed_change.paired_gain_mean`: +0.33 (≥ 0), met;
  - `reviewed_change.hidden_minus_control`: −0.15 (≥ 0), not met.

On this task, planning with Opus and reviewing the plan before a `gpt-6.1-sol` executor bought no hidden acceptance
over a single `gpt-6.1-sol` call. It took four calls and about 4.9 times the wall clock. Its patches were judged
better written by 1.0 point, but the upstream anchor's low scores in that batch suggest the judges were not measuring
what the hidden tests measure. `reviewed_change`'s reviewer blocked in every run, as calibration predicted. Its
revisions changed the code, and once the judges' score moved by more than one point, but they never moved the hidden
tests.

## Limits

- **Three runs per arm, and 52 hidden tests.** The patches clustered at three hidden values (16, 21 and 30 of 52),
  so these runs carry little information about effects smaller than those gaps; the measure itself resolves 1/52.
  No gain was measured; that does not show a small effect is absent. The +0.3 threshold needed about 16 more node ids
  than the control.
- **Thresholds.** Both thresholds were fixed after rung 3's calibration numbers were known, and neither is a power
  calculation (`threshold_provenance`).
- **Prescriptive task text.** As in calibration, `task.txt` names the entry points, record schemas and CLI subcommand
  that the hidden tests drive (R44, R50).
- **The judges disagree and do not track hidden acceptance.** r = 0.64, and the upstream anchor was scored 2–8. The
  judge measures are secondary for this reason.
- **Judge family overlap (R54).** `gpt-6-sol` is `reviewed_change`'s reviewer and judged its patches. It shares a
  family with `design_review_execute`'s reviewer and executor and with the control. `claude-opus-5-5` is the same
  model as the planner, whose documents are stripped from the pooled patches (D8).
- **Different models and time limits.** `reviewed_change`'s coder is Sonnet with 5400 s per call, and the control is
  `gpt-6.1-sol` with 14400 s. So `reviewed_change.hidden_minus_control` measures the model and time limit as well as
  the workflow.
- **`design_review_execute` is not on equal terms with the control either.** It adds an Opus planner and makes three
  calls of up to 3600 s each before the executor; only the executor's 14400 s matches the control's limit.
- **`reviewed_change`'s judge paired gain crosses batches.** Its first and final patches sit in different stage
  batches, so `paired_gain` compares scores given in different batches.
- **A judge can read its own earlier batches.** The `gpt-6-sol` judge's search during batch 3 printed 75 lines of its
  batch-2 transcript and its own `state.json`, which holds its ratings of batches 1 and 2. Those ratings could have
  anchored its batch-3 scores, which bear only on secondary entries. Its state directory lies inside its working
  directory, as the harness lays it out.
- **Stale editable install.**
  - The shims strip `PYTHONPATH`, so an agent's import of `orchestrator`, including from its own test runs, resolves
    to `/home/ollie/Documents/agent-orchestration/.worktrees/omp-i1-prerequisites` unless the agent overrides
    resolution (for example by setting `PYTHONPATH` to its candidate). That worktree's history contains the
    solution.
  - The same held for every calibration and E-A run. It is detection-only: any read hits the main-prefix pattern, and
    no batch run or judge produced such a hit.
  - The condition is common to every arm, but its effect on each arm was not measured and need not be equal: agents'
    own imports and test runs may exercise the stale worktree's code unless they override resolution. The smoke
    executor reported 534 failures and 32 errors, 565 of them present at baseline.
  - Hidden acceptance sets `PYTHONPATH` and is unaffected.
- **Isolation.** Contamination is detected, not prevented, for home, other sessions' transcripts and the network. The
  sandbox isolates `/tmp`, `/dev/shm`, `/var/tmp` and the process list (R35, R45).
- **Contended wall clock.** Up to four runs and their Codex subagents ran at once, so the wall-clock ratios are
  indicative only.
- **Shared account usage.** The Codex weekly percentage and credits are account-wide and other sessions ran at the
  same time, so the usage cannot be attributed to this experiment alone.

## Reproduce

Run from the repository root, at `7161ca02` or later. The [harness recipe](../../experiments/compare/README.md#recipe)
gives every step's refusals. Long steps run in tmux.

```bash
C=$PWD/experiments/compare/criteria/eb2.json   # absolute; sha256 26e1346e3488eee77e6c0473d15714c3270816327d90028d82992ada42fb9a75
RT=/home/ollie/compare-runtime      # git worktree add --detach $RT e88820864c894c96ec2023f85b95db7a9ef59d6d
PY=/home/ollie/miniconda3/bin/python H=$RT/experiments/compare T=$H/tasks/adopted-attempt-lineage
W=/home/ollie/compare-work-eb2c P=$W/pool SOL=1eb06773029df5c62d81c10e0d60ea6f72c81ab7
Q=/home/ollie/Documents/agent-orchestration-compare-evidence/queue.py
D=
for k in 1 2 3; do
  PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm design_review_execute --root $W --runtime $RT \
    --set planner_model=claude-opus-5-5 --set reviewer_model=gpt-6.1-sol
  PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm reviewed_change --root $W --runtime $RT
  PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm direct_task --root $W --runtime $RT \
    --set model=gpt-6.1-sol --set effort=high
  for a in design_review_execute reviewed_change direct_task; do D="$D $W/records/$a/run-$k"; done
done
tmux new-session -d -s eb2-batch "env -u PYTHONPATH $PY $Q 4$D > $W/queue.log 2>&1"   # wait for "queue empty"

# Every run: collect, scan, and record a verdict for any hits, all before pooling.
for R in $D; do
  PYTHONPATH=$RT $PY $H/prepare.py collect --run $R
  PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --hash $SOL
done
R=$W/records/direct_task/run-1   # then likewise for every other run with hits
PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --verdict cleared --reason "<what the hits are>"

PYTHONPATH=$RT $PY $H/prepare.py pool --task $T --criterion $C --out $P \
  --judge claude-opus-5-5 --judge gpt-6-sol=$H/providers/score_codex.json $D

# Judges one at a time. Each judge is verified, scanned and adjudicated before the next one starts.
tmux new-session -d -s eb2-score "bash $P/records/score-claude-opus-5-5.sh > $P/records/score-claude-opus-5-5.log 2>&1"
PYTHONPATH=$RT $PY $H/prepare.py verify-pool --pool $P                       # after that session exits
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $P --judge claude-opus-5-5 --hash $SOL
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $P --judge claude-opus-5-5 --verdict cleared --reason "<...>"
tmux new-session -d -s eb2-score2 "bash $P/records/score-gpt-6-sol.sh > $P/records/score-gpt-6-sol.log 2>&1"
PYTHONPATH=$RT $PY $H/prepare.py verify-pool --pool $P                       # after that session exits
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $P --judge gpt-6-sol --hash $SOL
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $P --judge gpt-6-sol --verdict cleared --reason "<...>"

tmux new-session -d -s eb2-summarize \
  "PYTHONPATH=$RT $PY $H/summarize.py --pool $P --criterion $C --python $PY > $P/records/summarize.log 2>&1"
```

The evidence is kept beside the repository in `agent-orchestration-compare-evidence/eb2/`:
- `batch/`, which holds the run records with calls, collected patches and scan verdicts, each run's orchestrator
  state, the pool's records (`mapping.json`, patches, score inputs, judges' calls and scans, `results.json` with
  per-clone hidden results, `results.md`, `summarize.log`), the judges' state, `queue.log`, `PROVENANCE.md` and
  `MANIFEST.sha256`; `batch/transcripts/` copies every Claude session and Codex rollout the scans read (the runs'
  and judges' own sessions, selected by session working directory, with source paths and hashes in `INDEX.tsv`);
- `verification/`, the checks' outputs;
- `smoke/`;
- `reviews/`, the criterion reviews and the smoke audit;
- `eb2.frozen.json`;
- `codex-usage.txt`.
