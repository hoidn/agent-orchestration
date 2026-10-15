# Effectiveness Harness And Experiments Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` with
> `superpowers:test-driven-development` for harness code and
> `superpowers:verification-before-completion` before completion claims. The
> coordinator owns integration, live runs and final verification; use a
> reviewer distinct from the author. Tasks 1, 2 and 4 touch disjoint files and
> may run in parallel after Task 0; Task 3 follows Tasks 1 and 2; Task 5
> follows Task 3 and the owner's answers to Q3 and Q4; Task 6 follows Task 5
> and Q2, Q5; Task 7 follows everything.

**Status:** executed 2026-10-14. Tasks 0–7 are complete. E-A ran; E-B was not evaluated because its task did not
qualify. The outcomes are in the [E-A report](../reports/2026-10-14-orc-versus-single-call-evaluated.md), the
[E-B report](../reports/2026-10-14-design-review-execute-versus-single-call.md) and the
[postmortem](../reports/2026-10-14-effectiveness-experiments-postmortem.md). Q1–Q5 were answered by coordinator
rulings, and every ruling made during execution is listed in the appendix below. Tasks 8 and 9
(task-difficulty calibration and the calibrated experiment) were added at the owner's request on 2026-10-14. They
are planned, not executed.
**Design:** [comparison harness and experiments](../design/orc_effectiveness_comparison_harness.md).
**Goal:** a comparison between a maintained workflow and a single call can be
run on current `main` with one command per arm, scored blind side by side
with typed ratings, and judged against a criterion whose hash every scoring
run recorded; the apparatus that cannot run is removed; E-A and E-B are
executed and reported.
**Architecture:** one directory `experiments/compare/` with two scripts, two
shims, one scoring `.orc`, one control `.orc` and a criterion template;
treatments referenced by path; no change under `orchestrator/` or `specs/`.
**Tech stack:** existing Python 3.11+ standard library, Workflow Lisp at
admitted targets, pytest, deterministic provider fixtures under `tests/`;
no new dependency.
**Tradeoff:** the task repository is the runtime's own repository, whose
solutions are public; the harness detects contamination rather than
preventing it, and every report says so.

## Authorities And Selection

Read the design, then [design lessons](../orc_workflow_design_lessons.md)
(the rules table and "Before Spending On Real Calls"), the
[September report](../reports/2026-09-28-orc-versus-single-call.md) §Task And
Method, §Workflow 1, §Workflow 2 and §Reproduce, the `best_of_n` recipe in
[`experiments/orc_vs_single_call/README.md`](../../experiments/orc_vs_single_call/README.md),
[`specs/cli.md`](../../specs/cli.md#executable-support-boundary),
[`specs/io.md`](../../specs/io.md) (provider request and attempt files, the
absolute result path), and [`specs/state.md`](../../specs/state.md) (memo rows,
recorded inputs). Paths are repository-root relative.

Owner selections recorded so far (2026-10-14): the lean-pilot row is gone
from the README (`64d7a093`); ES F1 is invalid; the REPL-shaped treatment is
a candidate for E-B, satisfied by `workflows/examples/design_review_execute.orc`
unchanged (design D7).

## Baseline And Evidence Location

Drafting baseline: `main` at `64d7a093`. Another session holds uncommitted
edits in the main checkout, among them `docs/index.md`,
`docs/capability_status_matrix.md`, `docs/design/README.md`, the roadmap,
`tests/test_workflow_evaluated_consumers.py`,
`tests/workflow_evaluated_consumer_sources.py` and
`experiments/orc_effectiveness/f1_es/report.schema.json`. None of those files
is edited in the main checkout by this plan. All work happens in a worktree on
a branch; merges use `git merge --ff-only --autostash` from the main checkout
only after a hunk-overlap check, verifying `Applied autostash.`, the stash
count and an identical `git status --short`.

```bash
git worktree add /home/ollie/Documents/agent-orchestration-compare -b feat/compare-harness main
export PYTHONPATH=/home/ollie/Documents/agent-orchestration-compare
```

Evidence directory outside the repository:
`/home/ollie/Documents/agent-orchestration-compare-evidence/` with
`task0/`, `reviews/`, `smoke/`, `ea/`, `eb/`, `suite/`. At execution create
`docs/reports/2026-10-14-effectiveness-harness-closeout.md` as the single
evidence owner for Tasks 0 to 4; E-A and E-B each get their own report.

Interpreter: `/home/ollie/miniconda3/bin/python`. Narrow selectors first;
broad runs with `pytest -q -n 16 --dist=worksteal -m "not e2e"` in tmux.

Facts measured on 2026-10-14 at this baseline, reused by the tasks below:

- `orchestrator compile workflows/experiments/repository_task_pilot/task_loop.orc --entry-workflow task_loop::main`
  fails with `workflow_execution_target_retired` (target 2.20).
- `orchestrator/experiments/`: 44 modules; with the two scripts 13,267 lines.
  `tests/experiments/test_lean_pilot_*.py`: 813 tests pass. The only importer
  outside the apparatus and its tests is
  `scripts/experiments/conventional_coordinator.py`. Further references:
  `pyproject.toml` package-data line for `orchestrator.experiments.schemas`,
  `tests/test_common_helper_architecture.py` (excluded-control list naming
  `orchestrator/experiments/_runner_block.py`),
  `tests/test_workflow_lisp_closed_program_corpus.py` (the `task_loop.orc`
  entry), `tests/experiments/fixtures/lean_pilot/`.
- A scratch `score.orc` with `(defenum Score S0 S1 S2)`, a `Rating` record of
  four `Score` fields and a `String`, a prompt returning `List[Rating]`, and a
  workflow returning `List[List[Rating]]` from `list/map-effect` with
  `:max 24` compiles at target 2.35 (`sites: 1`). An earlier shape with `Int`
  fields and `:max 24` also compiled and dry-ran; the reviewer's probe
  compiled `:max 64`.
- `experiments/orc_vs_single_call/workflows/`: both programs at 2.35, created
  in `e8caf07a`; `pytest tests/test_workflow_evaluated_consumers.py -k 'best_of_n or reviewed_change'`:
  14 passed. `reviewed_change.orc`'s implement prompt fills `task` only.
- `workflows/library/control/direct_task.orc`: inputs `task`, `model`,
  `effort`; `providers.direct`; `:delivery :composed`; no `:timeout-sec`.
- `workflows/examples/design_review_execute.orc`: inputs `task`,
  `planner_model` (default `claude-fable-5-1`), `reviewer_model` (default
  `gpt-6.1-sol`); prompts name no feature.
- Repository visibility: public.
- Workflow inputs are recorded in `run.json` as `bound_inputs`
  (`specs/state.md`), not in `memo.jsonl`; the memo holds effect results.
- `experiments/compare/direct_task.orc` fails with `module_path_mismatch`
  because the module is `control/direct_task`;
  `experiments/compare/control/direct_task.orc` with
  `--source-root experiments/compare` builds (reviewer's probe).
- A `gemini` provider binding compiles although the template has no model or
  effort binding (reviewer's probe); compiling proves nothing about that
  judge.
- The September task text points agents at `bugs/loop_result_paths/README.md`
  and requires `--basetemp="$TMPDIR/pytest"`; September's runner committed the
  bug report onto `468e7908` in every candidate and set `TMPDIR` per trial
  (`experiments/orc_vs_single_call/harness/run_single_call.sh`).

Task census candidates at this baseline (commit, lines changed under
`orchestrator/` and `tests/`), for Q2: moderate class `0d790d45` (23, 73),
`fd885caa` (3, 110), `3685d6c9` (57, 83); larger class `692eaf73` (243, 297),
`b11e678d` (103, 248), `2acd4b51` (74, 181). Task 0 regenerates the census
with hidden-test counts.

## Task 0: Census And Judge-Binding Probe

**Role:** coordinator. Provider-free except one short judge probe.

- [ ] Task census: commits on `main` touching `orchestrator/` and `tests/`,
      80 to 700 lines changed, not docs-only; for each, hash, date, subject,
      lines per area, the test files added, and the count of test node ids
      that fail at the parent and pass at the commit (run with `PYTHONPATH`
      at a detached worktree of each commit, `-p no:cacheprovider`). Save to
      `task0/census.md`; the owner picks from it (Q2, Q5).
- [ ] Judge-binding probe: run the scratch `score.orc` with
      `score.providers.json` bound to the `gemini` template and a stand-in
      `gemini` script first on `PATH` that records its arguments and writes a
      fixed result; check that the judge model and effort reach the CLI
      arguments. If they do not, record that Google is not available as a
      judge without a template change, and Q3 falls back to the design's
      alternative.
- [ ] Verification: both outputs saved under `task0/`; the Task 0 section of
      the closeout written.

## Task 1: Harness Scripts, Shims And Control

**Role:** `impl_code_compare_harness`, Opus 5.5 high. **Depends on:** nothing
beyond the baseline facts. **Modify:** new
`experiments/compare/{README.md,prepare.py,summarize.py,criterion.template.json}`,
new `experiments/compare/control/direct_task.orc`, new
`experiments/compare/shim/{claude,codex}`, new
`tests/experiments/test_compare_harness.py`.

- [ ] Write failing tests first on temporary git repositories: `prepare.py
      run` builds N candidates from the base commit alone (`git init`,
      depth-one fetch of the commit, `FETCH_HEAD` checked out, no remote, no
      other refs), commits the package's `seed/` files onto it in every
      candidate and uses that seeded commit as `COMPARE_BASE`, writes the
      arm's `inputs.json` with the typed fields the design lists, sets
      `TMPDIR` under the run root, and prints the verbatim `orchestrator run`
      command with the arm's working directory; `prepare.py collect` pairs
      memo provider effects with call directories one to one and copies the
      patches the arm's comparator needs; `prepare.py pool` builds
      applied-patch clones under random ids with `git add -A -N .`, strips
      `docs/design/` and `artifacts/` from every patch and records it,
      composes batches per design D4 (one `best_of_n` run per batch; two
      `reviewed_change` batches of one patch per run with the stage drawn at
      random; identical first and final patches pooled once), adds both
      anchors to every batch, writes the batches and `mapping.json` outside
      the pool; `prepare.py scan` finds the main checkout path, the frozen
      checkout path, `github.com`, `gh `, `git fetch` and a given hash in the
      call records, the Claude CLI session files for the candidate's
      directory and the codex output; `summarize.py` joins ratings by
      position, refuses a batch whose list length or any copied-back `clone`
      id disagrees with the positions, computes means, paired and group-mean
      deltas, exact agreement per criterion, anchor scores per batch,
      hidden-acceptance fractions with `PYTHONPATH` at the clone, and refuses
      when any scoring run's bound `criterion_sha256` in `run.json` differs
      from the file's hash.
- [ ] Implement with the standard library only. Under 500 lines of Python
      total; each function under cyclomatic complexity 12.
- [ ] Shims: forward arguments and stdin to the real binary found by
      skipping the shim directory on `PATH`; tee stdout; write
      `calls/<n>/{prompt.txt,stdout.txt,stderr.txt,patch-cand-<k>.diff}` under
      `COMPARE_ROOT`, each diff taken after `git add -A -N .` against
      `COMPARE_BASE` with `--binary`, then `git reset -q`. No result-file
      handling.
- [ ] Control: `experiments/compare/control/direct_task.orc`, the library
      file plus `:timeout-sec` equal to the treatment executor's limit
      (14400), compiled with `--source-root experiments/compare` because its
      module is `control/direct_task`; a test asserts the diff against
      `workflows/library/control/direct_task.orc` is that one line. Bind
      `providers.direct` to the same template the treatment's executor uses.
- [ ] README recipe: prepare, run from a detached worktree in tmux, collect,
      pool, score, summarize, scan; the exact commands with placeholders and
      the working directory per arm.
- [ ] Verification: `pytest -q tests/experiments/test_compare_harness.py`
      green; `pytest --collect-only -q tests/experiments/test_compare_harness.py`;
      outputs under `smoke/`.

## Task 2: `score.orc` And Its Consumer Test

**Role:** `impl_code_score_orc`, Opus 5.5 high. **Depends on:** nothing
beyond the baseline facts. **Modify:** new `experiments/compare/score.orc`,
`experiments/compare/score.providers.json`, new
`tests/test_workflow_evaluated_compare_score.py` with its own source helper.
Do not edit `tests/test_workflow_evaluated_consumers.py` or
`tests/workflow_evaluated_consumer_sources.py`; the other session holds them.

- [ ] Write the consumer test first, following the `best_of_n` consumer
      pattern: compile; run with deterministic judge results; interrupted and
      completed resume; the memo holds one `Rating` per clone per batch in
      input order; `criterion_sha256` is among the run's `bound_inputs` in
      `run.json`; an out-of-range enumeration value in the deterministic
      result fails the effect.
- [ ] Write `score.orc` as in the design: `Score` enumeration, `Rating` with
      its `clone` cross-check field, `Batch`, `rate-batch` prompt with the
      September rubric, the side-by-side instruction and the order
      requirement (one rating per clone, in the listed order), `score`
      workflow over `batches` with `:max 24`; inputs `batches`, `intent`,
      `criterion_sha256`, `judge_model`. No delivery prose in the prompt; no test asserts prompt
      wording. Under 80 lines.
- [ ] Verification: narrow selectors green; `orchestrator compile` of the
      file with its providers file recorded.

## Task 3: Provider-Free End To End And Code Review

**Role:** coordinator runs the smoke; `review_code_compare_harness`, Opus 5.5
high, reviews Tasks 1 and 2 together. **Depends on:** Tasks 1 and 2.

- [ ] Stand-in `claude` and `codex` scripts that write a fixed `result.json`
      at the absolute result path and make a fixed edit including one new
      file; a stand-in judge that writes a fixed `List[Rating]`.
- [ ] Run scenarios S1 to S4 of the design: every arm through the shim,
      `reviewed_change` through its request-changes branch, one `best_of_n`
      run killed at a commit boundary and resumed with the call count
      compared, a pool of one `best_of_n` run and one `reviewed_change` run
      scored by the stand-in judge with batches composed per D4, summarize
      with a valid criterion, then with a stand-in judge that returns one
      rating too few and one that copies back a wrong clone id, then with a
      scoring run bound to a different hash, then with a stand-in that writes
      no result file. Save commands, run ids, exits and `results.json` under
      `smoke/`.
- [ ] Review: contract against the design's §Contracts, candidate isolation
      (no refs past the base), new files in patches, blindness of the pool,
      position join, fail-closed paths, no treatment file touched, the
      control's one-line diff, size budgets, no test asserting prompt
      wording. Findings go back to the implementers as `revise_code_`.
- [ ] Verification: review PASS recorded under `reviews/`; the smoke
      directory complete.

## Task 4: Retire The Lean-Pilot Apparatus (D1)

**Role:** `impl_code_lean_pilot_retirement`, Opus 5.5 high; reviewer
`review_code_lean_pilot_retirement` distinct. **Depends on:** the owner's Q1.
**Modify:** delete `orchestrator/experiments/`,
`tests/experiments/test_lean_pilot_*.py`, `tests/experiments/fixtures/lean_pilot/`,
`scripts/experiments/lean_pilot.py`,
`scripts/experiments/conventional_coordinator.py`,
`workflows/experiments/repository_task_pilot/`; remove the
`orchestrator.experiments.schemas` package-data line from `pyproject.toml`,
the `orchestrator/experiments/_runner_block.py` entry from
`tests/test_common_helper_architecture.py` and the `task_loop.orc` entry from
`tests/test_workflow_lisp_closed_program_corpus.py`; add
`experiments/orc_effectiveness/lean_pilot/README.md` (notice: apparatus
removed at `<commit>`, evidence locations, owner-decision record); add
`scripts/check_doc_links.py` (standard library, under 40 lines: relative
links and heading anchors of the given markdown files); in the worktree,
`docs/capability_status_matrix.md` lean-pilot row to Historical,
`docs/index.md` pilot entries note the removal, `docs/design/README.md` if it
routes to the apparatus.

- [ ] Before deleting, record `git grep -l -e 'orchestrator.experiments' -e 'repository_task_pilot' -e 'lean_pilot'`;
      every hit must be in the deletion set, in this task's edit set, or a
      historical document that keeps its text.
- [ ] Delete and edit; `pytest --collect-only -q tests` must show no import
      error from the deletion (the collection error in the other session's
      untracked `tests/experiments/test_orc_research_demo.py` predates this
      task); run `tests/test_common_helper_architecture.py`,
      `tests/test_workflow_lisp_closed_program_corpus.py`,
      `tests/test_workflow_lisp_drain_roadmap_routing.py` and
      `python scripts/check_doc_links.py docs/index.md docs/capability_status_matrix.md docs/design/README.md`.
- [ ] Full suite in tmux: `pytest -q -n 16 --dist=worksteal -m "not e2e"`;
      compare failures with a pre-deletion run on the same commit; only load
      flakes may differ.
- [ ] Verification: review PASS; suite logs under `suite/`; the docs edits
      merged under the overlap rule, since the other session holds the matrix,
      index and design README modified.

## Task 5: E-A, Replication Of The September Comparison

**Role:** coordinator for live runs; `review_design_ea_criterion`, Opus 5.5
high, reviews the criterion file before it is hashed. **Depends on:** Task 3,
Q3, Q4.

- [ ] Task package `experiments/compare/tasks/ea-loop-result-paths/`: the
      September `task.txt` unchanged, `intent.txt`, `base_commit` =
      `468e7908`, `seed/bugs/loop_result_paths/` holding the September bug
      report so every candidate carries it at the path the task names, no
      hidden tests (judge-only, as in September), `anchors/`: the upstream
      fix commit's diff without its tests and an experimenter-written
      symptom-silencing patch, both built against the seeded commit; confirm
      both apply there.
- [ ] `criterion.json` per the design's E-A section (both September clauses
      for `best_of_n`: group-mean primary and the workflow mean not below six
      `gpt-6-sol` single calls; first-call paired secondary; no-run-worse and
      mean +0.5 for `reviewed_change`); reviewer confirms it names the
      comparators, the judges, the thresholds and the anchors; the hash
      recorded in the E-A report skeleton before any run.
- [ ] Live smoke: one run of `best_of_n`, one of `reviewed_change`, one
      `gpt-6-sol` control run, from a detached worktree at the recorded
      commit, in tmux, `TMPDIR` set by `prepare.py`; inspect memo, call
      directories, patches and scan results by hand; fix harness defects only.
- [ ] Batch: six runs per treatment and six `gpt-6-sol` control runs; scan
      every run; pool with batches per D4 (one control patch in each
      `best_of_n` batch); score with both judges; summarize.
- [ ] Report `docs/reports/2026-10-<dd>-orc-versus-single-call-evaluated.md`:
      criterion and hash, table per run, anchor scores per batch, agreement,
      scan results and exclusions, cost, limits (the fix is public; the judges
      differ from September; the control's single calls use the bare task
      text, not `best_of_n`'s implement prompt), reproduce. README evidence
      row added only now.
- [ ] Verification: `results.json` and the report agree; run memos, pools
      and scan outputs copied under `ea/`.

## Task 6: E-B, The Class A Single Call Does Not Finish

**Role:** as Task 5. **Depends on:** Task 5 reported, Q2, Q5, and the
owner's budget (Q4).

- [ ] Task package `eb-<slug>/` from the census: `task.txt` paraphrased and
      naming every public entry the hidden tests call, with the reading list
      both arms receive; `intent.txt`; `hidden_tests.txt` with the node ids
      that fail at the base and pass at the commit; `base_commit`; anchors as
      in Task 5. Confirm the hidden set's fail-at-base and pass-at-commit
      with `PYTHONPATH` at each checkout.
- [ ] Qualification: two control runs with `gpt-6.1-sol`, effort high,
      through the harness control; the task qualifies when both score below
      half on hidden acceptance; these runs are excluded from the baseline
      arm. If it does not qualify, pick the next census candidate once; if
      that fails too, stop E-B and report.
- [ ] `criterion.json` per the design's E-B section, reviewed and hashed.
- [ ] Batch: four runs per arm (six if Q4 says so), treatment
      `workflows/examples/design_review_execute.orc` unchanged; scan every
      run; pool with D8 stripping into one batch of every final patch of both
      arms plus the anchors (at most ten clones); score; hidden acceptance
      per clone; summarize.
- [ ] Report `docs/reports/2026-10-<dd>-design-review-execute-versus-single-call.md`;
      README evidence row.

## Task 7: Consistency Pass And Residue

**Role:** coordinator. **Depends on:** Tasks 4 to 6.

- [ ] ES residue, only once the session that owns `f1_es/` has committed:
      delete `experiments/orc_effectiveness/f1_es/`, `scripts/experiments/es/`,
      `tests/experiments/fixtures/es_f1/` and `tests/experiments/fixtures/es_task3/`
      if nothing imports them; record the 2026-10-14 invalidation in the
      roadmap's current ES boundary and the matrix row for canonical trial
      runs. If that session has not committed, report and leave it.
- [ ] Run the consistency pass over the design, the plan, the reports, the
      matrix, the index, the design README, the design lessons' measured
      columns and the README table; `scripts/check_doc_links.py` over the
      touched files; routing test.
- [ ] Verification: the closeout's final section lists every commit, the
      merge receipts and the suite result.

## Parallelism And Roles

| Task | Role prefix | Model | May run with |
| --- | --- | --- | --- |
| 0 | coordinator | Fable 5.1 | 1, 2, 4 |
| 1 | `impl_code_` | Opus 5.5 high | 0, 2, 4 |
| 2 | `impl_code_` | Opus 5.5 high | 0, 1, 4 |
| 3 | `review_code_` | Opus 5.5 high | 4 |
| 4 | `impl_code_`, `review_code_` | Opus 5.5 high | 0, 1, 2, 3 |
| 5 | coordinator, `review_design_` | Fable 5.1, Opus 5.5 high | 4 |
| 6 | coordinator, `review_design_` | Fable 5.1, Opus 5.5 high | after 5 |
| 7 | coordinator | Fable 5.1 | last |

Commits are pathspec commits on the branch (`git add` new files first,
`git commit -m ... -- <paths>`), no assistant attribution.

## Verification Summary

- Narrow: `pytest -q tests/experiments/test_compare_harness.py`;
  `pytest -q tests/test_workflow_evaluated_compare_score.py`;
  `pytest --collect-only -q` on both added modules.
- Smoke: scenarios S1 to S4, provider-free, under five minutes.
- Broad: `pytest -q -n 16 --dist=worksteal -m "not e2e"` in tmux after Task 4
  and before each merge.
- Live: one run per arm before any batch; batches in tmux from a detached
  worktree; every run's memo and scan result kept.

## Task 8: Task-Difficulty Calibration

**Role:** coordinator for live runs and rulings. `impl_code_compare_calibration` (Opus) builds the one piece of new
apparatus, and `review_code_compare_calibration` (Opus) reviews it. A distinct Opus reviewer,
`review_design_calibration_criterion`, reviews the calibration criterion. **Depends on:** Tasks 1–7 merged. The
owner decisions are listed at the end of this task.

The owner's rule (design, "Difficulty calibration for follow-on experiments"): later experiments raise task
difficulty until the expected number of review blockers is at least 1, and a single call must pass less than half
of the hidden acceptance tests. Both are measured before any treatment run, on single-call patches made with the
control's binding. Calibration runs are never treatment or control data.

**Definitions, frozen in the calibration criterion before any calibration run:**
- **Single-call patch:** the final patch of a `direct_task` run with the control's binding (`gpt-6.1-sol`, effort
  high, `:timeout-sec 14400`), on the rung's package.
- **Hidden fraction:** `summarize.hidden_fraction`, run over a calibration pool built without running any judge,
  as in the E-B qualification.
- **Review blockers of one patch:** the result of one `review_once` call on that patch.
  - `REQUEST_CHANGES` counts `len(findings)`, `WRONG_APPROACH` counts 1 and `APPROVE` counts 0.
  - `NEEDS_HUMAN` counts 0, is reported and is not replaced.
  - Findings are counted as the reviewer returned them. The coordinator does not merge, drop or reclassify any.
- **Reviewer.** The blocker reviewer is `reviewed_change`'s reviewer for both treatments of Task 9.
  `design_review_execute`'s own reviewer reads a design, not a patch, so for that arm the count stands in for
  "work left to do". This is recorded as a ruling and as a known difference.
- **Expected review blockers:** the mean over the rung's `k = 2` patches. If 1 ≤ mean < 1.5, one more single call
  and its review run, and the rung qualifies on all three.
- **Qualifies:** every patch's hidden fraction is below 0.5, and expected review blockers are at least 1.
- **Failed runs:**
  - Infrastructure failures are resumed (R3).
  - A `direct_task` run that fails any other way, `provider_timeout` included, has no patch, and the rung does not
    qualify, because Task 9's control would have no values.
  - A contaminated run is replaced once, by the next run number. A second contaminated run rejects the rung.
  - A failed review is resumed if the failure is infrastructure, and otherwise rerun once.
  - Every run, `review_once` included, is collected, scanned and adjudicated.
  - At most four runs are live at once.

- [ ] **Apparatus:** one review-only arm, `review_once`.
      - Copy `review-prompt`, `Review` and `ReviewReport` from `reviewed_change.orc` into
        `experiments/compare/control/review_once.orc`. Importing them would need a second source root, and it would
        edit a treatment file that must run unchanged.
      - A contract test compiles both modules and checks that these are equal: the prompt template, the `Review`
        descriptor, and the call binding (`gpt-6-sol`, effort high, `:timeout-sec 5400`,
        `codex_unrestricted_workspace`).
      - `prepare.py run --arm review_once --apply <final.diff>` builds a seeded candidate and applies the collected
        final patch, unstripped and uncommitted. The working directory is the candidate, and `repo` is its absolute
        path, as for `reviewed_change` (R34).
      - Inputs: `intent` is `intent.txt`; `account` is a fixed text frozen in the criterion ("No account was
        provided."); `replies` is "none".
      - `collect` records the blocker count.
      - Tests: a stand-in reviewer returning each variant gives the counts above; the patch is uncommitted in the
        candidate; the arm runs in the sandbox.
- [ ] **Candidate ladder:** written to `experiments/compare/tasks/calibration-ladder.md` before any run.
      - **Candidates** are features on `main` after 2026-07-01 (R4) with an objective oracle: at least 10
        behavioural tests that fail at the base and pass at the solution, each runnable alone in a clone.
      - **Base and solution.** The base is the parent of the feature's first design or plan commit; the solution is
        its last implementation commit.
      - **Order.** The primary key is lines changed under `orchestrator/`, which must be at least 1500. Modules
        touched, then spec and design changes, then the number of hidden tests break ties.
      - **No step 0.** `eb-repl`, which was already measured with its full appendix, is used only for the live smoke
        and is never a rung.
      - **What each rung's `task.txt` names.** Every public entry and every literal a hidden test checks (output
        line, code, exit status), and nothing about implementation.
      - **Dropped tests.** A hidden node id that checks a literal neither named in `task.txt` nor defined at the base
        is dropped before freezing, and the drop is recorded in the ladder.
      - **Packages.** Each rung has its own package (`task.txt`, `intent.txt`, `base_commit`, `hidden/`,
        `hidden_tests.txt`, two anchors), and its fail-at-base and pass-at-solution check is recorded, as in Task 0.
- [ ] **Calibration criterion:** `experiments/compare/criteria/calibration.json`.
      - It holds the definitions above, the fixed `account` text, the ladder file's hash and the stop rule.
      - **Stop rule:** take the first rung that qualifies; stop after at most 4 rungs; if none qualifies, report and
        stop.
      - Have it reviewed, then hash and commit it before any calibration run.
- [ ] **Live smoke before freezing** (postmortem action), on `eb-repl`: one `direct_task` call and one `review_once`
      call, with the real CLIs. Inspect them for mechanics only: memo, result path, sandbox, scan. Smoke runs are
      never measured as a rung and never count. Fix harness defects, then freeze.
- [ ] **Run the ladder.** For each rung, in order:
      - `k` `direct_task` runs, then collect, scan and adjudicate;
      - the calibration pool and its hidden fractions;
      - one `review_once` run on each single-call patch, then collect, scan and adjudicate.

      Record the rung's hidden fractions and blockers in `experiments/compare/tasks/<rung>/calibration.json`. Stop at
      the first rung that qualifies.
- [ ] **Report:** `docs/reports/<date>-task-difficulty-calibration.md`. It gives, per rung, the hidden fraction of
      each run, the blockers of each review with their findings, the qualifying rung or none, the cost, and the
      limits (`k` is small; the reviewer has its own variance).
- [ ] **Verification:** harness tests and `--collect-only` on the new tests; the stand-in smoke for `review_once`;
      the criterion reviewer's PASS; the report's numbers match the per-rung `calibration.json` files.

**Owner decisions** (each with the coordinator's default):
- **Budget, worst case per rung:** 2 calls × 4 h plus 2 reviews × 1.5 h, plus one more of each if the mean is
  borderline. At most 4 rungs, plus the smoke. Default: approve.
- **Codex use:** every calibration call is a pre-registered experiment call, which the owner's codex rule allows.
  New runs stop when the weekly window falls to 5% left unless credits cover them (R8). Default: allowed.

## Task 9: Calibrated Experiment (E-B2)

**Role:** as Task 5. **Depends on:** Task 8 found a qualifying rung, and the owner decisions below.

- [ ] **Package:** the qualifying rung's package, unchanged.
- [ ] **Arms:**
      - `design_review_execute` (planner `claude-fable-5-1`; reviewer and executor `gpt-6.1-sol`);
      - `reviewed_change` (coder Sonnet; reviewer `gpt-6-sol`);
      - control `direct_task` (`gpt-6.1-sol`, effort high, `:timeout-sec 14400`).

      `best_of_n` is optional, if the budget allows. Four runs per arm. Task 8's calibration runs are excluded.
- [ ] **Criterion** `experiments/compare/criteria/eb2.json`, in the form of `eb.json`, with two claims judged
      separately:
      - **`design_review_execute`:** `hidden_minus_control >= 0.3`, with run floors of 3 per arm.
      - **`reviewed_change`:** `hidden_paired_gain_mean >= ` the frozen threshold, with a run floor of 3. This is the
        final patch's hidden fraction minus the first patch's; it needs one line in `summarize.run_values`, since
        the first clone is already pooled. Its `hidden_minus_control` is secondary only. Its coder (Sonnet, 5400 s
        per call) differs from the control (`gpt-6.1-sol`, 14400 s), so a comparison with the control would measure
        the model and the time limit, not the workflow. This is recorded as a known difference.
      - **Judges:** `claude-opus-5-5` and `gpt-6-sol`.
        - Both OpenAI models are treatment reviewers: `gpt-6-sol` for `reviewed_change` and `gpt-6.1-sol` for
          `design_review_execute`. This departs from R2; it is recorded as a ruling and as a known difference.
        - The judges count only for secondary entries.
      - **Anchors:** the package's two anchors.
      - **Rules and provenance:** exclusions, `anchor_use`, `judge_rules`, `validity`, and `threshold_provenance`
        citing the calibration report.

      Have it reviewed, then hash and commit it before any run.
- [ ] **Live smoke** before freezing: one run per arm on `eb-repl`, for mechanics only. Nothing from it is measured
      before the freeze, and it is discarded.
- [ ] **Batch:** at most four live runs; every run collected, scanned and adjudicated; then pool, both judges,
      `verify-pool` after each judge, and `summarize`. Interim readouts come only from `summarize`'s join and are
      labelled partial.
- [ ] **Report:** `docs/reports/<date>-calibrated-orc-versus-single-call.md`, with the same sections as E-A, plus the
      calibration numbers it rests on. Add the README evidence row, the design lessons' Measured column and the index
      entry.
- [ ] **Verification:** `results.json` and the report agree; the evidence is copied beside the repository.

**Owner decisions** (each with the coordinator's default):
- **Budget, worst case at four runs per arm:**
  - control 16 h;
  - `design_review_execute` 28 h (three calls of 1 h and one of 4 h per run);
  - `reviewed_change` 36 h (up to six calls of 1.5 h per run);
  - about 50 Codex calls in total.

  Runs proceed in parallel, at most four live. Default: approve.
- **`design_review_execute`'s planner `claude-fable-5-1`:** it is an experiment provider, not a coordination
  subagent. The owner's "no Fable subagent in this session" rule is read as not covering it. Default: ask before
  running.
- **`best_of_n` as a fourth arm:** default no.

## Appendix: Rulings Made During Execution

The coordinator recorded each decision the design and plan did not settle as `Ruling: what — why — cost if
wrong`. The rulings are copied verbatim from the execution ledger. Code, the design, the criteria and the reports
cite them by number. Later rulings amend earlier ones where they say so: R8 is amended once, and R34 reverses R31.
The number R17 was never assigned.

- Ruling R1 (Q1): delete the lean-pilot apparatus as design D1 — treatment cannot run, evidence frozen elsewhere, deletion is git-reversible — cost if wrong: one revert commit.
- Ruling R2 (Q3): scoring judges = claude-opus-5-5 (claude_unrestricted_workspace) plus an OpenAI model that is not the treatment's judge/reviewer: E-A gpt-6.1-sol, E-B gpt-6-sol. No Google judge (gemini CLI absent; template has no model binding) — cost if wrong: judges share a family with treatment implementers (Sonnet, Fable); reported as a limit.
- Ruling R3 (Q4): "do the experiments" approves the designed budget; E-B 4 runs per arm; E-A2 not run. Independent runs may run concurrently (at most 4 live runs) to cut wall clock. A run that fails on provider infrastructure (rate limit, auth, CLI crash before agent output) is continued with `orchestrator resume`, never relaunched or excluded — cost if wrong: concurrency adds rate-limit failures and machine load.
- Ruling R4 (Q5): task commits must be after 2026-07-01 (Anthropic models' stated cutoff June 2026; OpenAI cutoffs undisclosed); the task source stays this repository with detection — cost if wrong: an OpenAI model trained on later public commits would be advantaged; scan + report limit.
- Ruling R5 (Q2): E-B task = the REPL first release. Base = parent of dbb2a0b9; task text = experiments/orc_repl_feature/inputs.json task plus an appendix naming the public REPL forms/outputs the hidden tests use; hidden set = node ids of tests/test_workflow_evaluated_repl.py at the first commit where they pass, that fail at base. Fallback = one census candidate — why: it is the real owner-written brief and the shape the owner asked to test — cost if wrong: the appendix narrows the design space; a single call may finish it (qualification decides).
- Ruling R6: the shim removes PYTHONPATH from the agent CLI environment — the frozen runtime checkout on PYTHONPATH contains both experiments' solutions — cost if wrong: none known; agent CLIs do not need it. Recorded as a deviation from design §The shim.
- Ruling R7: work root /home/ollie/Documents/agent-orchestration-compare-evidence/work; candidate and pool checkouts deleted after collection and scoring; patches, memos, run.json, mapping, ratings kept — cost if wrong: re-scoring needs patches re-applied (kept).
- Ruling R8: Codex panes are not used for implementation or review; Claude Opus 5.5 subagents per CLAUDE.md; Codex quota (31% weekly left on 2026-10-14) is reserved for experiment provider calls. If the Codex weekly limit falls to 5% left, no new runs are launched and the report says what completed — cost if wrong: no cross-family code review.
- Ruling R9: Codex-family judging of reviews is skipped for harness code; final whole-branch review on Opus 5.5 high per CLAUDE.md policy (skill asks most capable; user policy wins).
- Ruling R10: score inputs file = {"batches":[{"clones":[<absolute clone paths>]}], "intent": str, "criterion_sha256": str, "judge_model": str}; Score tokens serialize as the strings "S0","S1","S2" (T2 verifies and reports any other encoding); the copied-back Rating.clone must equal the listed path or its basename — cost if wrong: one adapter edit in summarize.py.
- Ruling R11: subagents run in parallel where files are disjoint (T1, T2, T4) per owner directive in memory, overriding the skill's no-parallel rule — cost if wrong: none expected (disjoint files).
- Ruling R12: harness ships two provider files: experiments/compare/providers/design_review_execute.json ({"providers.claude":"claude_unrestricted_workspace","providers.codex":"codex"}, the REPL run's binding) and experiments/compare/control/direct_task.providers.json ({"providers.direct":"codex"}); both controls (E-A gpt-6-sol, E-B gpt-6.1-sol) use the `codex` template, which carries the same --dangerously-bypass-approvals-and-sandbox flag as codex_unrestricted_workspace — cost if wrong: E-A control binding differs from best_of_n's judge binding by --skip-git-repo-check only.
- Ruling R13: the design's "under 500 lines of Python" is a target for prepare.py + summarize.py together; the gate is the repo rule (each module <= 500 lines, functions cyclomatic <= 12) — cost if wrong: a larger harness than designed.
- Ruling R14: E-A has no upstream fix for targets 2.29-2.32 (cdb60211 adds a 2.33 route; the September patches were not kept). E-A anchors = one extra Sonnet single call through best_of_n::implement-one, run outside every arm before the batch (drift reference), plus the experimenter's symptom-silencing patch that deletes the relpath override check in orchestrator/workflow/validation.py (low anchor) — cost if wrong: E-A loses the "known-good fix scores high" judge check; drift and low-anchor checks remain.
- Ruling R15: Task 0's full census (fail-at-parent/pass-at-commit counts) is computed only if E-B falls back; the REPL hidden set is verified: 16 of 16 tests fail at 47e85a9c and pass at fe49c1c4 (task0/hidden-*.txt). E-B base corrected to 47e85a9c, the parent of the REPL design commit 4a3d1517 (not dbb2a0b9^) — cost if wrong: a fallback takes longer.
- Ruling R16: the Google judge probe is moot (gemini CLI not installed; the template has no model binding) — cost if wrong: none.
- Ruling R8 (amended): Codex weekly limit 82% used at 2026-10-14 start, credits balance 29795.96 with has_credits true. The designed runs continue past the weekly limit on credits (the owner asked for the experiments at the designed budget); no extra runs beyond the design; the report states credits used (balance before/after) — cost if wrong: owner credits spent on the designed runs.
- Ruling R18: judges run unrestricted on the same pool, so a judge edit would change what the next judge sees. The harness gets `prepare.py verify-pool` (every clone's diff must equal its pooled patch; restore and report otherwise), run before each judge and after the last — cost if wrong: one extra check per judge.
- Ruling R19: the matrix row uses `Retired` (defined in the matrix legend: removed from the live surface, references are provenance) instead of the design's undefined `Historical`; design D1/S5 text is corrected in Task 7 — cost if wrong: one word.
- Ruling R20 (amends design D5 "a hit excludes the run"): every scan hit is adjudicated. `scan` records hits with source file, line and context; a verdict (`contaminated` or `cleared` with a reason) is recorded per run by the controller after reading the hits; `pool` refuses runs with unadjudicated hits and excludes contaminated ones; the report lists hits, verdicts and reasons — cost if wrong: controller judgement enters exclusion, mitigated by publishing every hit.
- Ruling R21: layout isolation. Records (command.sh, record.json, inputs.json, calls/, orchestrator state via `run --state-dir`, run.log) live under a records root; agents work under an agents root whose directories have random names inside a parent with mode 0311 (traversable, not listable), so `ls ..` shows neither sibling runs nor records; the work root and the frozen runtime must lie outside the main checkout prefix /home/ollie/Documents/agent-orchestration (refused otherwise), and the main-checkout scan pattern then matches that prefix unbounded so sibling worktrees (agent-orchestration-repl etc., which hold the REPL solution) count. Judges: one working directory and state dir per judge; mapping.json and patches in the records root, never an ancestor of the clones. Live layout: /home/ollie/compare-work/{runtime,records,agents,pools} — cost if wrong: more path plumbing in prepare.py.
- Ruling R22 (amends R21): mode 0311 cannot apply to ancestors of a workspace or state dir (the runtime opens every ancestor O_RDONLY), so only the pool's clones/ is 0311. Agents' trees and judge directories get random names, and the scan flags any mention of another run's tree, the records root or the frozen runtime; the frozen runtime lives outside the work root (/home/ollie/compare-runtime), the work root is /home/ollie/compare-work — cost if wrong: an agent can list sibling run names and the records root; reading them is detected, not prevented.
- Ruling R23: scan path patterns add the agent-typed spellings `~/Documents/agent-orchestration` and `$HOME/Documents/agent-orchestration` (and the same for the work root and runtime) rather than a bare `Documents/agent-orchestration` fragment, to limit benign hits from file contents — cost if wrong: an agent using a deep relative path escapes detection.
- Ruling R24 (amends R6): the shims strip PYTHONPATH, COMPARE_* and their own directory from PATH before the real CLI, for agents and judges, because PATH alone named the frozen runtime and COMPARE_ROOT named the records — cost if wrong: an agent that needs a COMPARE_* variable or the shim on PATH fails (none does).
- Ruling R25: residual exposure accepted as detection-only: an agent knows its own result path under R/state, whose run.json names the frozen workflow file; the scan flags any use — cost if wrong: an agent reads the frozen runtime and the run is excluded after adjudication.
- Ruling R26: harness Python at 1006 lines over five modules (max 279) meets the 500-line module limit; the design's ~500 total was an estimate, not a constraint — cost if wrong: more code for the final review.
- Ruling R27: the E-A scan's solution hash is cdb60211 (the later 2.33 route that touches the loop result path code; no fix of record exists) — cost if wrong: a pattern that never fires; the path patterns still apply.
- Ruling R28: the plan's Task 3 "Opus review of Tasks 1 and 2 together" is satisfied by the per-task reviews (Task 2 clean; Task 1 clean after round 2), the recorded provider-free smoke in the final layout and the final whole-branch review; no separate seat — cost if wrong: an interaction between score.orc and the pool found later, at the live smoke.
- Ruling R29: task packages are tracked under experiments/compare/tasks/ (commit 89912e5a) so the frozen runtime is a plain checkout of a recorded commit; testpaths=tests and CORPUS_ROOTS exclude them — cost if wrong: the public repo carries the upstream-repl anchor (already public as 47e85a9c..fe49c1c4).
- Ruling R30: the live smoke runs are run-1 of each arm in the batch work root /home/ollie/compare-work; if the hand inspection finds no harness defect they count as the first of six (runtime unchanged); if a defect forces a runtime change, they are discarded before the batch, listed in the report as smoke, and the batch runs at the new commit — cost if wrong: one discarded run per arm.
- Ruling R31: the reviewed_change failure is a workflow/model failure, not a harness defect: the agent chose ORCHESTRATOR_OUTPUT_BUNDLE_PATH's parent for a workspace-relative relpath, which fails identically in the default layout (state under the workspace's .orchestrate/); the harness recorded and classified it. Per the frozen criterion it stays a failed run (never resumed or relaunched) and the report names the failure mode; the limits note that the harness's state directory outside the workspace may contribute — cost if wrong: if the outside state dir induces this, reviewed_change is penalized; mitigated by reporting every failure with its evidence.
- Ruling R32: E-B qualification and batch run concurrently with the E-A batch rather than after E-A reports: the plan's dependency is budget (the owner asked for the experiments), and E-B's design and criterion do not depend on E-A's results; E-B uses the same runtime checkout (one path for the scan pattern) at aac25b7d and its own work root /home/ollie/compare-work-eb — cost if wrong: contention inflates wall clock (reported, not a verdict measure) and raises rate-limit stops (resumed as infrastructure).
- Ruling R33 (amends R3's cap): from 12:57 nine runs were live (4 E-A batch, 2 E-B qualification, 3 diagnostic probes), above R3's four. Kept: the probes are short and diagnostic, and the cap protected rate limits, which so far have not stopped a run; wall clock in this window is reported as contended — cost if wrong: rate-limit stops (resumed as infrastructure) and inflated wall clock.
- Ruling R34 (reverses R31): the result path outside the agent's workspace is a harness defect: it changes the condition the maintained workflows were written for and induces result-delivery failures (2/4 against 0/5). The harness drops --state-dir for runs, so state lives in the run's working directory under .orchestrate/runs (ignored at both bases), as the probe ran. All E-A runs at aac25b7d are discarded and listed in the report with this reason (selection on outcome would bias any partial reuse); E-A reruns all 18 at the fixed commit with an amended criterion (new hash, deviation recorded). E-B qualification runs 1-2 at aac25b7d both completed (result delivered), so they stand as samples of the single call; a result-delivery failure would have been re-run — cost if wrong: about 12 discarded E-A runs of agent time.
- Ruling R35: cross-run and cross-session leakage through /tmp, tmux servers and the process list is a harness isolation defect. The shims run the real CLI under bubblewrap with a private /tmp (the tree's tmp/), a private /dev/shm and a PID namespace (verified: claude -p and codex exec work, uid 1000); the scan adds .claude/projects, .codex/sessions, .codex/history and claude-tmux-sockets patterns for the transcripts that stay readable. Both E-B qualification runs are discarded as harness-invalid (not adjudicated as agent contamination: the environment, not the agent, reached the solution) and rerun at the fixed commit — cost if wrong: two discarded gpt-6.1-sol runs (~66 min).
- Ruling R36: the reruns use fresh work roots /home/ollie/compare-work2 (E-A) and /home/ollie/compare-work-eb2 (E-B); the discarded roots stay for the record until the closeout. Both criteria are amended (runtime commit, work roots, a deviation note naming R34/R35 and the discarded runs) and re-hashed before any rerun; the amendment is committed with the old hash cited — cost if wrong: none beyond the documentation.
- Ruling R37: best_of_n's workspace (the tree) differs from where its implementers work (cand-k), so a workspace-relative result path is ambiguous to them; September's runner made it absolute. The harness gives best_of_n its own state directory under the tree's .orchestrate/ and links it from every candidate's .orchestrate/ (ignored, never in a patch; an agent's own runs in cand-k keep their runs/), so the path resolves from either (197e35ed; stand-in that resolves from cand-k completes). best_of_n runs 1-6 discarded; reruns are run-7..12 at 197e35ed; reviewed_change and direct_task at 1a77e0af stand (the diff touches only best_of_n). Criterion amendment 2: sha256 0030e44a... (08745de1). The default-layout failure is reported as a finding about best_of_n on the evaluated route — cost if wrong: the accommodation hides a product defect; mitigated by reporting it.
- Ruling R38: a judge's provider failure (missing or invalid result) is an instrument failure, resumed with resume-<judge>.sh, not a datum; the report lists any — cost if wrong: a judge that systematically fails gets extra attempts.
- Ruling R39 (deviates from the frozen fallback): E-B is reported as not evaluated (task did not qualify); the census fallback is not run, because the census candidates are smaller changes (about 100-250 lines) than the REPL, which one gpt-6.1-sol call finished (16/16, 14/16), so they would almost surely not qualify either; the next E-B is the difficulty-calibrated experiment the owner asked for (single call below half of hidden acceptance and expected review blockers >= 1, both measured before the treatment runs) — cost if wrong: one census candidate that might have qualified is not tried; reversible by running it later under its own frozen criterion.
- Ruling R40: integrate with a merge commit (`git merge --no-ff --autostash` from the main checkout) instead of the fast-forward the plan assumed: main moved by two unrelated docs commits, and a rebase would rewrite the commits the frozen criteria and reports cite (aac25b7d, 1a77e0af, 197e35ed, 61b7d04d); hunk overlap with the other sessions' uncommitted edits was checked per file (matrix, index: separated) — cost if wrong: one merge commit in main's history.
- Ruling R41: the postmortem doubles as the plan's closeout report (no separate closeout doc) — cost if wrong: one doc name differs from the plan.
