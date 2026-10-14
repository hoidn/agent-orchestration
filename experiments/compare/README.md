# Comparison harness: maintained `.orc` workflows against single agent calls

Design and decisions: [`docs/design/orc_effectiveness_comparison_harness.md`](../../docs/design/orc_effectiveness_comparison_harness.md).
The harness runs a maintained workflow unchanged, records every agent call through a transparent
shim, pools the resulting patches blind, scores them with `score.orc`, and summarizes against a
criterion frozen before scoring.

| File | Role |
| --- | --- |
| `prepare.py` | `run` (candidates, `inputs.json`, the command), `collect`, `scan`, `pool`, `verify-pool` |
| `shim/claude`, `shim/codex` | first on `PATH` during a run; forward to the real CLI without `PYTHONPATH`, record `calls/<n>/` |
| `control/direct_task.orc` | the control: the library `direct_task` plus `:timeout-sec 14400`; module `control/direct_task` |
| `control/direct_task.providers.json`, `providers/design_review_execute.json` | provider bindings for the control and the E-B treatment |
| `score.orc`, `score.providers.json` | blind side-by-side ratings per batch |
| `summarize.py` | `results.json`, the per-run table, agreement, anchor scores, measures, verdict |
| `criterion.template.json` | the fields to freeze, and hash, before scoring |

## Task package

`experiments/compare/tasks/<package>/` holds `task.txt` (what every arm receives), `intent.txt`
(what judges and reviewers receive), `base_commit`, `seed/` (files committed onto the base in every
candidate and clone, so they never appear in a patch), `anchors/<name>.diff` (the two anchors, built
against the seeded commit), and optionally `hidden_tests.txt` (node ids, one per line, or a file
path for all its tests) with `hidden/` (test files copied over each clone before they run). Without
both, hidden acceptance is skipped.

## Recipe

Placeholders: `MAIN` the main checkout, `C` the recorded commit, `RT` the frozen runtime checkout,
`W` the work root, `T` the task package inside `RT`, `RUN` a run directory, `POOL` a pool
directory, `SOL` the solution commit. Every command runs with `PYTHONPATH=$RT`; the printed run
commands set it themselves.

```bash
git -C $MAIN worktree add --detach $RT $C        # 0. frozen runtime: edits to main cannot leak in
export PYTHONPATH=$RT PY=/home/ollie/miniconda3/bin/python
H=$RT/experiments/compare
```

1. **Prepare** one run per invocation; it prints the command and writes it to `$RUN/command.sh`
   (`RUN` is the `COMPARE_ROOT` in it, `W/<arm>/run-<k>`).

   ```bash
   $PY $H/prepare.py run --task $T --arm best_of_n --root $W --runtime $RT [--candidates 4]
   $PY $H/prepare.py run --task $T --arm reviewed_change --root $W --runtime $RT
   $PY $H/prepare.py run --task $T --arm design_review_execute --root $W --runtime $RT \
     --set planner_model=claude-fable-5-1 --set reviewer_model=gpt-6.1-sol
   $PY $H/prepare.py run --task $T --arm direct_task --root $W --runtime $RT \
     --set model=gpt-6-sol --set effort=high
   ```

   | arm | inputs | working directory of the command |
   | --- | --- | --- |
   | `best_of_n` | `task`, `intent`, `repos` (absolute candidates) | the run root `RUN` |
   | `reviewed_change` | `task`, `intent`, `repo` (absolute `RUN/cand-1`) | `RUN/cand-1` |
   | `design_review_execute` | `task`, `planner_model`, `reviewer_model` | `RUN/cand-1` |
   | `direct_task` | `task`, `model`, `effort` | `RUN/cand-1` |

   The command runs `python -P` so a candidate's own `orchestrator/` cannot shadow `PYTHONPATH`,
   puts `$H/shim` first on `PATH`, and sets `COMPARE_ROOT`, `COMPARE_BASE` (the seeded commit) and
   `TMPDIR=$RUN/tmp`.

2. **Run** in tmux; a run that stops on provider infrastructure is resumed, never relaunched.

   ```bash
   tmux new-session -d -s <name> "bash $RUN/command.sh > $RUN/run.log 2>&1"
   sed -E 's/ -m orchestrator run .*/ -m orchestrator resume <run_id>/' $RUN/command.sh > $RUN/resume.sh
   tmux new-session -d -s <name> "bash $RUN/resume.sh >> $RUN/run.log 2>&1"
   ```

3. **Collect** pairs the memo's provider starts with `calls/<n>/` one to one and copies the patches
   the comparator needs into `$RUN/collected/`: every candidate for `best_of_n`, first and final
   for `reviewed_change`, final otherwise. A failed run is recorded with its reason and no patch.

   ```bash
   $PY $H/prepare.py collect --run $RUN
   ```

4. **Scan** for contamination (D5): the shim's stdout and stderr, the Claude CLI's session files
   for the run's directories and the codex rollouts started there, searched for the main checkout,
   the frozen checkout, `github.com`, `gh `, `git fetch` and the solution hash. A hit excludes the
   run from the pool; it is detection, not prevention.

   ```bash
   $PY $H/prepare.py scan --run $RUN --hash $SOL
   ```

5. **Freeze the criterion** from `criterion.template.json` (measure names below) before pooling;
   its SHA-256 becomes every scoring run's `criterion_sha256`.

6. **Pool** every run of one experiment at once. Batches follow D4: one per `best_of_n` run with
   one `direct_task` patch each, two stage batches for `reviewed_change`, otherwise one batch of
   all final patches; both anchors join every batch. Clones live in `$POOL/clones/<id>/`;
   `mapping.json`, `patches/` and one `score-inputs-<judge>.json` per judge sit beside them.

   ```bash
   $PY $H/prepare.py pool --task $T --criterion <criterion.json> --out $POOL \
     --judge claude-opus-5-5 --judge gpt-6.1-sol $W/best_of_n/run-* $W/direct_task/run-* ...
   ```

7. **Score** once per judge, one after another, from `$POOL/clones` so the judge's directory holds
   only clones. `score.providers.json` binds a Claude judge; for an OpenAI judge write
   `{"providers.judge": "codex_unrestricted_workspace"}` to a file (the pool is not a git
   repository, so the judge needs `--skip-git-repo-check`). After each judge, `verify-pool`
   restores any clone the judge changed and exits non-zero if it had to.

   ```bash
   cd $POOL/clones && $PY -P -m orchestrator run $H/score.orc --entry-workflow score::score \
     --source-root $H --provider-externs-file <judge providers file> \
     --input-file $POOL/score-inputs-<judge>.json
   $PY $H/prepare.py verify-pool --pool $POOL
   ```

8. **Summarize**; it refuses a scoring run bound to another criterion hash and any batch whose
   ratings do not line up with its clones, and writes `$POOL/results.json`.

   ```bash
   $PY $H/summarize.py --pool $POOL --criterion <criterion.json> > $POOL/results.md
   ```

## Measures

`summarize.py` scores a clone as the judges' mean total of the four criteria (0 to 8). A run's
value is its selected candidate (`best_of_n`) or its final patch. Measures per arm:
`<arm>.runs`, `.mean`, `.calls_mean`, `.wall_clock_mean`, `.hidden_mean`; for `best_of_n` and
`reviewed_change` `.paired_gain_mean`, `.paired_gain_runs_positive`, `.paired_gain_runs_negative`;
for `best_of_n` the same three for `group_gain`; for every arm beside `direct_task`
`.minus_control` and `.hidden_minus_control`. A criterion entry is `{"measure", "op", "value"}`
with `op` one of `>=`, `<=`, `>`, `<`. Failed and excluded runs are listed and carry no value.
