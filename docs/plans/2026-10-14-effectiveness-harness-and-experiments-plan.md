# Effectiveness Harness And Experiments Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` with
> `superpowers:test-driven-development` for harness code and
> `superpowers:verification-before-completion` before completion claims. The
> coordinator owns integration, live runs and final verification; use a
> reviewer distinct from the author. Tasks 1, 2 and 4 touch disjoint files and
> may run in parallel after Task 0; Task 3 follows Tasks 1 and 2; Task 5
> follows Task 3 and the owner's answers to Q3 and Q4; Task 6 follows Task 5
> and Q2, Q5; Task 7 follows everything.

**Status:** draft, 2026-10-14, revised after one independent design review;
not executed. Owner decisions pending: Q1 to Q5 in the design.
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
