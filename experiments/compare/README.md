# Comparison harness: maintained `.orc` workflows against single agent calls

Design and decisions: [`docs/design/orc_effectiveness_comparison_harness.md`](../../docs/design/orc_effectiveness_comparison_harness.md).
The harness runs a maintained workflow unchanged, records every agent call through a transparent
shim, pools the resulting patches blind, scores them with `score.orc`, and summarizes against a
criterion frozen before scoring.

| File | Role |
| --- | --- |
| `prepare.py` | command line: `run`, `collect`, `scan` (hits, then a verdict), `pool`, `verify-pool` |
| `repos.py`, `scan.py`, `pool.py` | candidate builds and patches; the contamination scan; the blind pool and its check |
| `shim/claude`, `shim/codex` | first on `PATH` during a run; forward to the real CLI without `PYTHONPATH`, record `calls/<n>/` |
| `control/direct_task.orc` | the control: the library `direct_task` plus `:timeout-sec 14400`; module `control/direct_task` |
| `control/direct_task.providers.json`, `providers/design_review_execute.json` | bindings for the control and the E-B treatment |
| `score.orc`, `score.providers.json`, `providers/score_codex.json` | blind side-by-side ratings; a Claude and an OpenAI judge binding |
| `summarize.py` | `results.json` and `results.md`: runs, measures, verdict, agreement, anchors, scan verdicts |
| `criterion.template.json` | the fields to freeze, and hash, before scoring |

## Task package

`experiments/compare/tasks/<package>/` holds `task.txt` (what every arm receives), `intent.txt`
(what judges and reviewers receive), `base_commit`, `seed/` (files committed onto the base in every
candidate and clone, so they never appear in a patch), `anchors/<name>.diff` (the two anchors, built
against the seeded commit), and optionally `hidden_tests.txt` (node ids, one per line, or a file
path for all its tests) with `hidden/` (test files copied over a copy of each clone, without `.git`,
before they run). Without both, hidden acceptance is skipped.

## Layout

The work root `W`, the pool `P` and the frozen runtime `RT` must not lie under the main checkout's
path prefix (for `/home/ollie/Documents/agent-orchestration`, that includes every sibling such as
`...-compare` or `...-repl`): those checkouts hold solutions, and the scan counts any mention of the
prefix as a hit. `prepare.py` refuses such paths. The frozen runtime must also lie outside the work
root `W`, where agents work, and `run` refuses one inside it. The live layout puts the runtime at
`/home/ollie/compare-runtime` and the work root at `/home/ollie/compare-work`.

| Path | Holds |
| --- | --- |
| `W/records/<arm>/run-<k>/` (`R`) | `record.json`, `inputs.json`, `command.sh`, `resume.sh`, `calls/<n>/`, `state/` (the orchestrator's `--state-dir`), `collected/`, `run.log` |
| `W/agents/<16 hex>/` | the agents' tree: `cand-1` ... `cand-N` and `tmp/` (TMPDIR); `record.json` names the tree |
| `P/clones/<id>/` | applied-patch clones, what judges read |
| `P/judges/<16 hex>/` | one judge's working directory, with its `state/` |
| `P/records/judges/<judge>/` | the judge's shim call records (`calls/<n>/`) and `scan.json` |
| `P/records/` | `mapping.json`, `patches/`, `score-inputs-<judge>.json`, `score-<judge>.sh`, `resume-<judge>.sh`, `results.json`, `results.md` |

`P/clones` is mode 0311 (traversable, not listable: judges get absolute paths); `chmod u+r` it
before deleting the pool. `W/agents`, `P` and `P/judges` must stay listable. The runtime opens every
ancestor of a workspace or state directory one component at a time with `O_RDONLY`, and a 0311
parent fails the run with `cannot open directory root component`. So an agent can list sibling
trees and an ancestor's records. The scan counts any mention of another tree's name as a hit, and
records live outside every tree. The orchestrator still writes `.orchestrate/` (workspace lock,
guard and a build cache) into the working directory; this repository's `.gitignore` ignores it.

## Recipe

Placeholders: `MAIN` the main checkout, `C` the recorded commit, `RT` the frozen runtime checkout,
`W` the work root, `T` the task package inside `RT`, `R` a records directory, `P` a pool, `SOL`
the solution commit.

```bash
git -C $MAIN worktree add --detach $RT $C        # 0. frozen runtime outside MAIN's prefix
PY=/home/ollie/miniconda3/bin/python H=$RT/experiments/compare
```

1. **Prepare** one run per invocation. It prints the command, writes it to `R/command.sh` and
   writes `R/resume.sh`.

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
   | `best_of_n` | `task`, `intent`, `repos` (absolute candidates) | the agents' tree |
   | `reviewed_change` | `task`, `intent`, `repo` (the tree's absolute `cand-1`) | the tree's `cand-1` |
   | `design_review_execute` | `task`, `planner_model`, `reviewer_model` | the tree's `cand-1` |
   | `direct_task` | `task`, `model`, `effort` | the tree's `cand-1` |

   The command runs `python -P`, so a candidate's own `orchestrator/` cannot shadow `PYTHONPATH=$RT`.
   It puts `$H/shim` first on `PATH` and sets `COMPARE_ROOT=R`, `COMPARE_TREE` (the tree),
   `COMPARE_BASE` (the seeded commit) and `TMPDIR` (the tree's `tmp/`). It passes
   `--state-dir R/state`. Before an agent starts, the shims strip `PYTHONPATH`, `OLDPWD`, the
   `COMPARE_*` variables and their own directory from `PATH`, because these name the frozen runtime,
   the launch directory and the records.

2. **Run** in tmux. A run that stops on provider infrastructure is resumed with the same state
   directory, never relaunched.

   ```bash
   tmux new-session -d -s <name> "bash $R/command.sh > $R/run.log 2>&1"
   tmux new-session -d -s <name> "bash $R/resume.sh <run_id> >> $R/run.log 2>&1"   # run_id: the name under R/state
   ```

3. **Collect** pairs the memo's provider starts with `R/calls/<n>/` one to one. It copies the
   patches the comparator needs into `R/collected/`: every candidate for `best_of_n`, first and
   final for `reviewed_change`, final otherwise. A failed run is recorded with its reason and no
   patch.

   ```bash
   $PY $H/prepare.py collect --run $R
   ```

4. **Scan, then adjudicate** (D5 as amended by R20). `scan` records every hit with its file, line,
   pattern and an excerpt, and decides nothing. It searches:
   - the shims' stdout and stderr;
   - the Claude CLI's session files for the tree;
   - the codex rollouts started in the tree.

   The patterns are:
   - the main checkout's prefix;
   - the frozen checkout;
   - the records root `W/records`;
   - the layout `records/<arm>/run-<k>` and a pool's record files, wherever they lie, except the
     run's own `state/`;
   - another run's tree name;
   - `github.com`, `gh ` and `git fetch`;
   - the solution hash.

   A path also matches when it is written under `~`, `$HOME` or `${HOME}`.

   For a run with hits, the controller reads them and records a verdict. `pool` refuses a run
   with hits and no verdict, excludes contaminated runs (listed with the reason) and includes
   cleared ones.

   ```bash
   $PY $H/prepare.py scan --run $R --hash $SOL
   $PY $H/prepare.py scan --run $R --verdict contaminated --reason "<what the agent read>"
   $PY $H/prepare.py scan --run $R --verdict cleared --reason "<why the hits are benign>"
   ```

5. **Freeze the criterion** from `criterion.template.json` (measure names below) before pooling.
   Its SHA-256 becomes every scoring run's `criterion_sha256`.

6. **Pool** every run of one experiment at once. Batches follow D4:
   - one per `best_of_n` run, with one `direct_task` patch each;
   - two stage batches for `reviewed_change`;
   - otherwise one batch of all final patches.

   Both anchors join every batch. `--judge MODEL` uses `score.providers.json`;
   `--judge MODEL=FILE` uses another binding (`providers/score_codex.json` for an OpenAI judge,
   because a judge's directory is not a git repository). The pool prints one command per judge
   and writes it to `P/records/score-<judge>.sh`. Each judge has its own working directory and
   `--state-dir` under `P/judges/`.

   ```bash
   $PY $H/prepare.py pool --task $T --criterion <criterion.json> --out $P \
     --judge claude-opus-5-5 --judge gpt-6.1-sol=$H/providers/score_codex.json $W/records/best_of_n/run-* ...
   ```

7. **Score** one judge after another, behind the shims, which record the judge's calls in
   `P/records/judges/<judge>/`. After each judge, `verify-pool` restores any clone the judge
   changed, and exits non-zero if it had to. A judge stopped by a provider failure is resumed with
   `P/records/resume-<judge>.sh <run_id>` (the same `--state-dir`), never re-run. Then scan the
   judge and adjudicate its hits, as for a run. The scan searches the judge's calls, sessions and
   rollouts for this pool's records, the run records root, the records layout, another judge's
   directory, the frozen runtime and the main checkout.

   ```bash
   bash $P/records/score-claude-opus-5-5.sh && $PY $H/prepare.py verify-pool --pool $P
   bash $P/records/resume-claude-opus-5-5.sh <run_id>      # only after a stop; run_id under P/judges/<dir>/state
   $PY $H/prepare.py scan --pool $P --judge claude-opus-5-5 --hash $SOL
   $PY $H/prepare.py scan --pool $P --judge claude-opus-5-5 --verdict cleared --reason "<why>"
   bash $P/records/score-gpt-6.1-sol.sh && $PY $H/prepare.py verify-pool --pool $P
   $PY $H/prepare.py scan --pool $P --judge gpt-6.1-sol --hash $SOL
   ```

8. **Summarize.** It refuses in these cases:
   - a criterion whose `judges` differ from the pool's;
   - a judge not scanned, scanned before its last call, or with hits and no verdict (a judge found
     contaminated is left out and listed);
   - a listed judge without exactly one completed scoring run;
   - a scoring run bound to another criterion hash;
   - a batch whose ratings do not line up with its clones.

   It writes `P/records/results.json` and `P/records/results.md`.

   ```bash
   $PY $H/summarize.py --pool $P --criterion <criterion.json>
   ```

## Measures

`summarize.py` scores a clone as the judges' mean total of the four criteria (0 to 8). A run's
value is its selected candidate (`best_of_n`) or its final patch. Measures per arm:

- every arm: `<arm>.runs`, `.mean`, `.calls_mean`, `.wall_clock_mean`, `.hidden_mean`;
- `best_of_n` and `reviewed_change`: `.paired_gain_mean`, `.paired_gain_runs_positive`,
  `.paired_gain_runs_negative`;
- `best_of_n`: the same three for `group_gain`;
- every arm except `direct_task`: `.minus_control` and `.hidden_minus_control`.

A criterion entry is `{"measure", "op", "value"}`, with `op` one of `>=`, `<=`, `>` or `<`.
Failed and excluded runs are listed and carry no value.
