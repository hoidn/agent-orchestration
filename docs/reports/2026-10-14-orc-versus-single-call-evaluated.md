# E-A: Maintained Workflows Against Single Calls On The Evaluated Route

Status: complete. The criterion was committed before any E-A run. The sections below were filled in after `summarize`.

**Result.** `reviewed_change` meets every clause of its claim. `best_of_n` misses one clause: 4 of its 6 runs beat
their candidate group's mean, against at least 5 required. Its mean group gain, +1.02, is above the +0.75 bar.
So E-A replicates September for `reviewed_change` and falls one run short for `best_of_n`. Against six single calls
both workflows score slightly higher on the 0–8 scale, by +0.33 and +0.42, at 5.2 and 3 calls per run instead of 1.

## Question And Criterion

The question is whether, on the evaluated route, `best_of_n` and `reviewed_change` beat single calls
on the September task (`468e7908`, `bugs/loop_result_paths`), as they did on the flat route.

- Criterion: [`experiments/compare/criteria/ea.json`](../../experiments/compare/criteria/ea.json).
- SHA-256: `0030e44a3b765de43dafff280f00600f52e7698afb9e002dec4a543da512f7c9` (amendment 2; earlier versions are cited in its `amends` and `amends_2` fields).
- Each version of the criterion was committed before the runs it governs, and both scoring runs bound this
  version's hash. Amendment 2 was committed while the `reviewed_change` and `direct_task` runs at `1a77e0af`
  were under way. It changes only `best_of_n`'s runtime commit and lists the discarded runs. No amendment
  changed a threshold, a measure, a judge or an anchor.
- Harness, runtime and task package: the frozen runtime at commit `197e35ed` for `best_of_n` and at `1a77e0af` for the
  other arms. The difference touches only `best_of_n`'s state directory (R37). The runs made at `aac25b7d`
  were discarded before pooling, for two harness defects (R34 and R35). The criterion's `amends` field lists them.
- Package SHA-256: `5bb1487dadf33982af56170f351edad76bbfd3e31b35c85b67ab87d5d91302a3`.
- Design: [`docs/design/orc_effectiveness_comparison_harness.md`](../design/orc_effectiveness_comparison_harness.md).

## Runs

All 18 runs completed. The scan found hits in one run only. Value is the run's selected or final patch, on the
0–8 scale, as the mean of both judges. Group gain is the selected patch minus the mean of its run's four candidates.
Paired gain is the selected patch minus candidate 1 for `best_of_n`, and the final patch minus the first for
`reviewed_change`.

| run | value | paired gain | group gain | calls | wall clock | notes |
| --- | --- | --- | --- | --- | --- | --- |
| `best_of_n` run-7 | 4.5 | 0.0 | −0.25 | 5 | 1183 s | selected cand-1 of 4.5 / 5.5 / 4.5 / 4.5 |
| `best_of_n` run-8 | 6.5 | +2.5 | +1.62 | 5 | 1324 s | selected cand-2 of 4 / 6.5 / 6 / 3 |
| `best_of_n` run-9 | 8.0 | +4.5 | +2.12 | 6 | 1156 s | selected cand-2 of 3.5 / 8 / 5.5 / 6.5; resumed once after the owner's codex stop |
| `best_of_n` run-11 | 3.5 | −1.0 | −1.12 | 5 | 1299 s | selected cand-3 of 4.5 / 7 / 3.5 / 3.5 |
| `best_of_n` run-12 | 7.0 | +3.0 | +1.75 | 5 | 1872 s | selected cand-4 of 4 / 4 / 6 / 7 |
| `best_of_n` run-13 | 7.0 | +4.0 | +2.00 | 5 | 1105 s | selected cand-2 of 3 / 7 / 6.5 / 3.5 |
| `reviewed_change` run-1 | 7.0 | +2.5 | | 6 | 1078 s | UNRESOLVED after three review rounds |
| `reviewed_change` run-2 | 5.5 | 0 | | 2 | 382 s | approved first patch |
| `reviewed_change` run-3 | 8.0 | 0 | | 2 | 356 s | approved first patch |
| `reviewed_change` run-4 | 3.0 | 0 | | 2 | 553 s | approved first patch; 2 scan hits, cleared |
| `reviewed_change` run-5 | 7.0 | +1.5 | | 4 | 689 s | one revision, then approved |
| `reviewed_change` run-6 | 6.5 | 0 | | 2 | 1466 s | approved first patch |
| `direct_task` run-1 to run-6 | 6.5, 7.5, 6, 4.5, 6, 4 | | | 1 each | 340–751 s | `gpt-6-sol`, effort high, bare task text |

Runs discarded before pooling, and never scored:
- **At `aac25b7d`:** all runs of the first batch (R34, R35; listed in the criterion's `amends`).
- **At `1a77e0af`:** `best_of_n` run-1 to run-6. Runs 1 and 2 lost their first candidate's result (R37), run-3 was
  stopped, and runs 4 to 6 never started (`amends_2`).
- **At `197e35ed`:** run-10. A controller error in the queue stopped it twice before any committed call, and
  run-13 replaced it on a fresh tree. This deviates from the criterion's "never relaunched or replaced". The
  replacement was outcome-blind: run-10 had produced nothing to judge.

## Scores, Anchors And Agreement

| measure | both judges (verdict) | `claude-opus-5-5` alone | `gpt-6.1-sol` alone |
| --- | --- | --- | --- |
| `direct_task.mean` | 5.75 | 6.00 | 5.50 |
| `best_of_n.mean` | 6.08 | 6.50 | 5.67 |
| `best_of_n.group_gain_mean` | +1.02 | +0.75 | +1.29 |
| `best_of_n.group_gain_runs_positive` | 4 | 5 | 4 |
| `best_of_n.minus_control` | +0.33 | +0.50 | +0.17 |
| `reviewed_change.mean` | 6.17 | 6.67 | 5.67 |
| `reviewed_change.paired_gain_mean` | +0.67 | +1.17 | +0.17 |
| `reviewed_change.paired_gain_runs_negative` | 0 | 0 | 0 |
| `reviewed_change.minus_control` | +0.42 | +0.67 | +0.17 |

- **Per-judge values are reported, not used** (`judge_rules`). Under the Claude judge alone both claims would hold.
  Under the OpenAI judge alone `best_of_n` misses the run count and `reviewed_change` misses the +0.5 mean.
- **Agreement over all 54 clones:**
  - Pearson r = 0.81 between the two judges' totals;
  - mean absolute difference 1.35 points;
  - the OpenAI judge scores about 0.9 points lower;
  - identical criterion ratings: root cause 37/54, scope 26/54, generality 35/54, layering 34/54.
- **Anchors behaved as designed.** The symptom-silencing patch scored 0–2 from `claude-opus-5-5` and 0–1 from
  `gpt-6.1-sol` in every batch. The Sonnet single call scored 5–8 from `claude-opus-5-5` and 1–8 from
  `gpt-6.1-sol` (1 in batch 6) (`results.json`, `anchors`).
- **Where `best_of_n` lost:**
  - In run-7 and run-11 the selector picked a candidate at or below its group's mean.
  - In run-11 a candidate scoring 7 was available and the selector picked one scoring 3.5.
  - The four candidates of a run spread widely (up to 3.5–8, in run-9). Selection is worth more than
    generation here, and in 2 of 6 runs it went wrong.
- **Where `reviewed_change` gained:**
  - In 4 of 6 runs the `gpt-6-sol` reviewer approved the first patch, so the final patch is the first one
    and the gain is 0 by construction.
  - The two runs with revisions gained +2.5 and +1.5.

## Contamination Scan

Every run and both judges were scanned with the solution hash `cdb60211` and the path patterns, including the
sandbox-era patterns (R35).
- `reviewed_change` run-4 had 2 hits: the tmux skill's own text naming the default socket directory, printed
  while the reviewer read the skill. They were cleared, with the reason recorded in its `record.json`.
- Every other run and both judges had 0 hits.

## Cost

- **Agent calls:**
  - `best_of_n`: 25 Sonnet implementer calls (one resumed) and 6 `gpt-6-sol` selector calls;
  - `reviewed_change`: 9 Sonnet coder calls and 9 `gpt-6-sol` reviewer calls;
  - `direct_task`: 6 `gpt-6-sol` calls.
- **Judges:** 8 `claude-opus-5-5` calls and 9 `gpt-6.1-sol` calls (8 batches, plus one interrupted call that was
  resumed).
- **Discarded runs:** about 13 more runs' worth of calls, at `aac25b7d` and `1a77e0af`.
- **Codex:** the credit balance stayed at 29795.96 (has credits, pro plan). The weekly window went from 82% to
  96% used (readings in the evidence directory, `ea/codex-usage.txt`).
- **Mean wall clock per run:** `best_of_n` 1323 s, `reviewed_change` 754 s, `direct_task` 497 s.

## Verdict

| claim | clauses | holds |
| --- | --- | --- |
| `best_of_n` | runs positive 4 (≥ 5 required), group gain +1.02 (≥ +0.75), minus control +0.33 (≥ 0), controls 6 (≥ 5) | **no** (run count) |
| `reviewed_change` | runs worse 0 (≤ 0), paired gain +0.67 (≥ +0.5), runs 6 (≥ 5) | **yes** |

Secondary: `best_of_n.paired_gain_mean` +2.17 (≥ 0), met.

By the frozen verdict rules, E-A replicates September for `reviewed_change` and does not replicate it for
`best_of_n`. Both workflows score above the single call, but by less than half a point on an 8-point scale.
They do so at about 2.6 times (`best_of_n`) and 1.5 times (`reviewed_change`) the single call's wall clock.

## Limits

- **Small sample and judge sensitivity.** There are six runs per arm. The `best_of_n` claim turns on one run, and
  each judge alone would reverse one clause.
- **Interim readout error.** During scoring the coordinator gave the owner a preliminary readout that joined ratings
  to clones by position. The readout was wrong, and the owner stopped the second judge on it. The judge was resumed,
  and nothing it had scored was repeated. The verdict above comes from `summarize`. It joins ratings to clones
  by position in each judge's own inputs and refuses any batch whose copied-back clone id disagrees.
- **Public later code.** The fix is not public, but later public commits touch the same code. The scan found no
  use of them.
- **Judge families.** The judges differ from September's, and `gpt-6.1-sol` shares a family with the selector, the
  reviewer and the control.
- **Control prompt.** The control's single calls get the bare task text. September's got `best_of_n`'s implement
  prompt.
- **The task is easy for the reviewer.** It approved 4 of 6 first patches, which caps `reviewed_change`'s measurable
  gain. Follow-on experiments calibrate difficulty, so that expected review blockers are at least one (design,
  "Difficulty calibration for follow-on experiments").
- **Contended wall clock.** The arms overlapped in time (R3, R32, R33). The wall-clock ratios were measured
  under contention and are indicative only.
- **Staged files.** Between calls, the shim used at these commits reset the candidate's git index. A file an
  implementer had staged with `git add` was unstaged before the reviewer's call, and the reviewer saw it as
  untracked. The patches themselves were unaffected, except that a force-added ignored file would have dropped out
  of later patches; none was seen. The shim was fixed after the experiments.
- **Harness accommodation.** `best_of_n`'s result path relies on a harness link (R37). Without it, on the evaluated
  route, its implementers lose their results.

## Reproduce

```bash
RT=/home/ollie/compare-runtime      # git worktree add --detach $RT 197e35ed (1a77e0af for the other arms; same code paths)
PY=/home/ollie/miniconda3/bin/python
H=$RT/experiments/compare
W=/home/ollie/compare-work2
T=$H/tasks/ea-loop-result-paths
cd /home/ollie
PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm best_of_n --root $W --runtime $RT --candidates 4
PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm reviewed_change --root $W --runtime $RT
PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm direct_task --root $W --runtime $RT --set model=gpt-6-sol --set effort=high
# run each R/command.sh (resume a stopped run with R/resume.sh <run_id>), then:
PYTHONPATH=$RT $PY $H/prepare.py collect --run R
PYTHONPATH=$RT $PY $H/prepare.py scan --run R --hash cdb60211a31db4659727a87c962d8272dbccba46
PYTHONPATH=$RT $PY $H/prepare.py pool --task $T --criterion <criteria/ea.json> --out $W/pool-ea \
  --judge claude-opus-5-5 --judge gpt-6.1-sol=$H/providers/score_codex.json <the 18 runs>
bash $W/pool-ea/records/score-claude-opus-5-5.sh && PYTHONPATH=$RT $PY $H/prepare.py verify-pool --pool $W/pool-ea
bash $W/pool-ea/records/score-gpt-6.1-sol.sh && PYTHONPATH=$RT $PY $H/prepare.py verify-pool --pool $W/pool-ea
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $W/pool-ea --judge <judge> --hash cdb60211a31db4659727a87c962d8272dbccba46
PYTHONPATH=$RT $PY $H/summarize.py --pool $W/pool-ea --criterion <criteria/ea.json>
```

`results.json`, `results.md`, `mapping.json`, the patches and the run records are kept in the evidence directory
beside the repository (`agent-orchestration-compare-evidence/ea/`).
