# `.orc` Effectiveness Comparison Harness And The Next Two Experiments

## Metadata

- **Title:** A small reusable harness for workflow-versus-single-call comparisons on the evaluated route, retirement of the apparatus that can no longer run, and two preregistered experiments
- **Status:** draft, 2026-10-14, revised after one independent design review; owner decisions pending in §Open Questions
- **Kind:** operational design (experiment apparatus) with experiment preregistration
- **Owner:** experiment and evaluated-runtime maintainers
- **Reviewers:** one independent design reviewer; one code reviewer distinct from the implementer
- **Created:** 2026-10-14
- **Last material update:** 2026-10-14
- **Related docs / issues / plans:**
  [design lessons](../orc_workflow_design_lessons.md) (methodology authority),
  [workflows versus a single call](../reports/2026-09-28-orc-versus-single-call.md),
  [lean-pilot forensics](../reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md),
  [lean-pilot owner decision](../reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md),
  [executor retirement](workflow_lisp_executor_retirement.md),
  [CLI executable support boundary](../../specs/cli.md#executable-support-boundary),
  [capability matrix](../capability_status_matrix.md) rows for the lean-pilot apparatus and canonical trial runs;
  plan: [harness and experiments plan](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md)
- **Implementation target:** treatments are maintained `.orc` programs at admitted evaluated targets (2.35, 2.36). The harness lives under `experiments/compare/`, outside `orchestrator/`. No new target, header field, memo field, transport or spec change.

## Summary

The repository has had three generations of effectiveness apparatus, and the
heavy ones produced the least evidence. The July lean pilot's ORC arm is a
target-2.20 program the compiler now refuses, and two of its three blocks were
forfeits caused by its own protocol surface. The August ES F1 apparatus never
ran a live arm and the owner has declared the study invalid. The September
single-call study, two `.orc` programs plus a hundred lines of
machine-specific shell and hand-run blind judging, produced the only usable
result; its methodology is recorded in the design lessons, its tooling is
not reusable.

This design keeps the methodology and replaces the machinery with one small
harness: a preparation script that builds one repository per candidate from
the base commit alone, a transparent shim on `PATH` that records every
candidate's patch after every agent call, a scoring workflow in `.orc` whose
judges rate a batch of patches side by side under random ids and return typed
ratings, and a summarizer that evaluates a criterion file whose hash every
scoring run bound as an input in its `run.json`. The treatments are the maintained
workflows, referenced by path and never copied or edited: `best_of_n.orc`,
`reviewed_change.orc`, the `design_review_execute.orc` example, and a control
that is the library's `direct_task.orc` plus a time limit.

Two experiments are preregistered. E-A replicates the September comparison on
the evaluated route with the September task, base commit, comparator and
scoring mode, so that the runtime change is the only difference. E-B measures
the class the September report says was never tested, tasks a single call
does not finish, with hidden acceptance tests as the completeness measure and
the design-review-execute shape that built the REPL as the treatment. The
lean-pilot apparatus is retired with the same move as the flat route:
evidence stays, code goes.

## Context And Authority

- [Design lessons](../orc_workflow_design_lessons.md) own the rules a valid
  comparison follows: write the criterion before seeing scores; judge blind
  with random ids; use a judge that is not the workflow's own judge;
  predeclare the paired baseline and report the comparator used; repeat anchor
  patches across batches; do not score with tests the agent can run; report
  judge agreement; run from a frozen copy of the code.
- [The September report](../reports/2026-09-28-orc-versus-single-call.md) owns
  the baseline method: every implementation call in a workflow is a single
  call with the same model, prompt and a fresh repository copy, so the
  single-call result and the workflow result come from the same run. Its base
  commit `468e7908` and task package under `experiments/orc_vs_single_call/task/`
  are in the tree and remain usable: the bug exists at that commit whatever
  `main` does later.
- [`specs/cli.md`](../../specs/cli.md#executable-support-boundary) refuses
  execution of targets through 2.34. The lean pilot's ORC treatment,
  `workflows/experiments/repository_task_pilot/task_loop.orc`, is target 2.20
  and is refused with `workflow_execution_target_retired`.
- [`specs/io.md`](../../specs/io.md) states that the evaluated route hands
  providers the absolute path of their pinned result file; a missing file
  fails the effect with `provider_result_missing` ([providers
  spec](../../specs/providers.md)).
- The [capability matrix](../capability_status_matrix.md) lists the lean-pilot
  apparatus as "Implemented". Its unit tests pass, but the apparatus cannot
  execute its ORC treatment. This design surfaces the contradiction and
  resolves it through D1.
- Owner decisions of 2026-10-14, recorded here: the lean-pilot row was removed
  from the README evidence table; the ES F1 study is invalid and is not a
  candidate comparison; the REPL-shaped workflow is a candidate treatment.

## Problem

| Apparatus | What it is | Why it cannot serve | Evidence it produced |
| --- | --- | --- | --- |
| Lean pilot (July): `orchestrator/experiments/`, `scripts/experiments/lean_pilot.py`, `scripts/experiments/conventional_coordinator.py`, `workflows/experiments/repository_task_pilot/` | 44 modules of apparatus with 13 test modules | Its ORC arm is refused by the compiler; its environment is pinned to one machine; its in-band guard brackets were the failure mode | 3 blocks; 2 forfeits; 1 real comparison, a tie on hidden acceptance decided on maintainability |
| ES F1 (August) | Apparatus deleted in the executor retirement; schemas and data under `experiments/orc_effectiveness/f1_es/` | No live arm; invalid per owner | None |
| Single-call study (September): `experiments/orc_vs_single_call/` | Two `.orc` at 2.35, four shell scripts, rubric, ratings | `harness/` has one machine's paths and variant files not in the tree; judging ran by hand per batch; the wrapper carries a result-file workaround the evaluated route made obsolete | +0.83 and +1.02 for generate-four-select-one with a stronger judge; +0.58 for review-and-revise with a stronger reviewer |

What a reader cannot do: produce a valid comparison on the current runtime
without rewriting the scaffolding, and the one positive result cannot be
repeated as it stands. The pattern across generations: control machinery
placed in the path of the treatment became the failure mode, and methodology
written as rules outlived every apparatus.

## Goals And Non-Goals

Goals:

- G1. One command per arm runs a comparison on current `main`, from a frozen
  checkout, on any machine with the provider CLIs.
- G2. Treatments are the maintained `.orc` programs, unchanged. The harness
  adds nothing to their prompts and reads nothing from their internals beyond
  the run's memo and the candidate repositories.
- G3. Scoring is blind, typed and recorded: random ids, anchors in every
  batch, judges that are not the treatment's judge or reviewer, exact
  agreement reported.
- G4. The success criterion is a file whose hash every scoring run binds as
  an input, recorded in its `run.json` before any rating exists, and the
  summarizer evaluates it mechanically.
- G5. Apparatus that cannot run on the current runtime is retired, with its
  evidence kept.

Non-goals:

- General effectiveness claims. Each experiment reports one task class.
- A trial SDK, run-ref, or any E-series revival. The harness is two scripts,
  two shims and one `.orc`.
- Token or cost metering beyond call counts and wall clock.
- Parallel candidates. `list/map-effect` runs serially; target 2.37 parallel
  maps are registered, not admitted for this work.
- Reviving or porting `task_loop.orc`.
- Preventing a determined agent from finding a published solution. The
  harness removes the obvious routes and detects the rest (D5).

## Decision

- **D1. Retire the lean-pilot apparatus.** Delete `orchestrator/experiments/`,
  its package-data entry in `pyproject.toml`, `tests/experiments/test_lean_pilot_*.py`,
  `tests/experiments/fixtures/lean_pilot/`, `scripts/experiments/lean_pilot.py`,
  `scripts/experiments/conventional_coordinator.py` (its only importer),
  `workflows/experiments/repository_task_pilot/`, and the entries that name
  them in `tests/test_common_helper_architecture.py` and
  `tests/test_workflow_lisp_closed_program_corpus.py`. Keep
  `experiments/orc_effectiveness/lean_pilot/` as frozen evidence with a notice,
  the reports, the external evidence directory and the digest-bound
  owner-decision record. The matrix row becomes Historical. Owner approval
  required (Q1).
- **D2. One harness under `experiments/compare/`.** `prepare.py`,
  `shim/claude` and `shim/codex`, `score.orc` with `score.providers.json`,
  `control/direct_task.orc` (the control, see D3; its module is
  `control/direct_task`, so it sits under `control/` and compiles with the
  harness directory as source root), `summarize.py`,
  `criterion.template.json`, `README.md`. Size budget: under 500 lines of
  Python, under 40 lines of shell, under 80 lines of `.orc`.
- **D3. The paired baseline comes from the same run where the treatment's
  first call is an implementation.** For `best_of_n` every candidate is a
  single call and the first candidate is the paired baseline; the group mean
  is the September comparator and is reported too. For `reviewed_change` the
  first implementer call is the baseline. For `design_review_execute` the
  first call drafts a design, so its baseline is a separate control run: the
  library's `direct_task.orc` with one difference, a `:timeout-sec` equal to
  the treatment's executor time limit, so neither arm has more time than the
  other. The control copy lives in the harness under `control/`; a test
  asserts it differs from the library file by that one line. The control uses the same provider
  binding, model and effort as the treatment's executor. The comparator of
  every arm is named in the criterion file and reported.
- **D4. Scoring is side by side per batch, typed, in applied-patch clones.**
  Batches are built by `prepare.py` under random ids with the mapping written
  outside the pool, and never reveal which patches belong together: for
  `best_of_n` a batch is one run's four independent candidates, one of the
  six single-call control patches (it looks like a fifth independent
  candidate, and the September second clause is then compared within the
  batch's own scale), plus the two anchors (D6), seven clones; for
  `reviewed_change` the twelve patches are
  split into two batches of one patch per run, the stage of each drawn at
  random, plus the anchors, eight clones each, and a run whose first and
  final patch are identical (approved in round one) is pooled once with its
  rating copied; for E-B a batch is every final patch of both arms plus the
  anchors, at most ten clones. Each judge receives a batch's clone paths in a
  random order and returns one `Rating` per clone in that order. Ratings
  join to clones by position; the `clone` field the judge copies back is a
  cross-check only, and `summarize.py` refuses a batch whose list length or
  any copied-back id disagrees with the positions. Scores are an enumeration
  `S0 S1 S2`, so an out-of-range value fails the effect. This is the
  September mode (several patches rated against each other, anchors
  repeated, no stage or grouping visible) with the September rubric, now
  typed and replayable.
- **D5. Tasks come from this repository's commits with tests.** The base is
  the parent commit, the task text paraphrases the change without quoting the
  commit, and the hidden acceptance set is the commit's test node ids that
  fail at the base and pass at the commit. The task text names every public
  entry those tests call, so an agent that solves the task can match the
  names. Each candidate repository is built from the base commit alone
  (`git init`, a depth-one fetch of that commit, no other refs, no remote),
  so no later commit is readable inside it. Files the task needs inside the
  repository, such as a bug report or a reproduction, live in the package's
  `seed/` directory; `prepare.py` commits them onto the base in every
  candidate, and that seeded commit is the base for patches and anchors, so
  seed files never appear in a diff and cannot mark a candidate. The repository is public and the
  agents are unrestricted: the solution exists on GitHub and in the frozen
  runtime checkout on the same machine. After every run the harness scans the
  shim's call records, the Claude CLI's per-project session files for the
  clone's directory, and the codex output for the main checkout path, the
  frozen checkout path, `github.com`, `gh `, `git fetch` and the solution
  commit's hash. A hit excludes the run and is reported. This is detection,
  not prevention, and is stated as a limit in every report. Whether the
  commits must postdate the models' training data, and from which date, is
  the owner's call (Q5).
- **D6. Anchors are two real patches, blind.** The upstream commit's diff
  without its tests, and a fixed patch written by the experimenter that
  silences the symptom without fixing the cause. Both enter every batch under
  random ids with no scores in the prompt. Each judge's anchor scores are
  reported per batch; drift between batches and a low score for the real fix
  are visible in the report instead of assumed away.
- **D7. The E-B treatment is `workflows/examples/design_review_execute.orc`
  unchanged.** It is already task-agnostic: its prompts read the documents and
  code the task names, and it takes `task`, `planner_model` and
  `reviewer_model`. `experiments/orc_repl_feature/repl_feature.orc` is that
  shape with prompts that name the REPL's documents; its run of 2026-10-13 is
  the existence proof that the shape completes a real feature, not evidence
  of a gain. The reading list goes in the task text, which both arms receive,
  so it is not a confound.
- **D8. E-B patches are stripped of design artifacts before scoring.** The
  treatment writes `docs/design/<slug>.md` and `artifacts/design/`; a judge
  seeing those paths would know the arm. `prepare.py` removes those paths from
  every pooled patch, baseline and treatment alike, and records the removal in
  the mapping.

## Design Details

### Layout

```
experiments/compare/
  README.md                 recipe: prepare, run, collect, pool, score, summarize
  prepare.py                candidate repositories, inputs.json per arm, shim install, collect, pool
  shim/claude, shim/codex   transparent wrappers; record prompt, stdout, stderr, patches per call
  score.orc                 blind side-by-side ratings per batch
  score.providers.json      judge binding
  control/direct_task.orc   the control: library direct_task plus :timeout-sec (source root: this directory)
  summarize.py              results.json, agreement, anchor scores, criterion verdict, markdown table
  criterion.template.json   fields to freeze before scoring
tests/experiments/test_compare_harness.py
tests/test_workflow_evaluated_compare_score.py
```

### Flow of one run

1. `prepare.py run --task <task dir> --base <commit> --arm <name> --root <work root>`
   builds `root/<arm>/<run>/cand-<k>/` from the base commit alone, commits
   the package's `seed/` files onto it in every candidate, writes the arm's
   `inputs.json`, installs the shim directory first on `PATH` for the run,
   sets `TMPDIR` to a directory under the run root, and prints the
   `orchestrator run` command to execute verbatim from the frozen runtime
   checkout, with the working directory the arm requires (§Contracts).
2. The run executes the maintained workflow. On every agent call the shim
   writes `calls/<n>/{prompt.txt,stdout.txt,stderr.txt,patch-cand-<k>.diff}`;
   each diff is taken after `git add -A -N .` so new files are included, and
   the index is reset afterwards.
3. `prepare.py collect` reads the run's `memo.jsonl`, pairs provider effects
   with call directories one to one, and copies every patch the arm's
   comparator needs into the scoring pool: all candidates for `best_of_n`,
   first and final for `reviewed_change`, the final patch for
   `design_review_execute` and for the control.
4. `prepare.py pool` builds one applied-patch clone per pooled patch under a
   random id, with `git add -A -N .` so a judge's `git diff` shows new files,
   strips the paths in D8, adds the two anchors to every batch, writes the
   batches as the scoring inputs, and writes `mapping.json` outside the pool.
5. `orchestrator run experiments/compare/score.orc` once per judge, with the
   batches, the intent, the judge model and `criterion_sha256` as inputs.
6. `summarize.py --pool <pool> --criterion <criterion.json>` reads each
   scoring run's `run.json` bound inputs and memo, refuses unless every
   scoring run bound the file's current hash, joins ratings to clones by
   position, refuses any batch whose list length or copied-back clone id
   disagrees with the positions, and writes the table, the agreement counts,
   the anchor scores and the verdict.
7. `prepare.py scan` runs the contamination scan of D5 over the run and
   appends its result to the run's record.

### The shim

Named after the agent CLI it replaces, it forwards all arguments and stdin to
the real binary found by skipping its own directory on `PATH`, tees stdout,
and records patches. It does not touch the result file: the evaluated route
hands providers the absolute path of their pinned result file, and a missing
file fails the effect with `provider_result_missing`, so the September
wrapper's deletion of stale result files is obsolete. The shim is the only
part of the harness in the treatment's path, and it changes nothing the agent
sees.

### `score.orc`

```lisp
(defenum Score S0 S1 S2)
(defrecord Rating
  (clone String)   ; copied back by the judge; cross-check only
  (root_cause Score) (scope Score) (generality Score) (layering Score)
  (reason String))
(defrecord Batch (clones List[String]))
(defprompt rate-batch (:fills (intent :text) (clones :value List[String]))
  -> List[Rating] "...")
(defworkflow score
  ((batches List[Batch]) (intent String) (criterion_sha256 String)
   (judge_model String))
  -> List[List[Rating]]
  (list/map-effect ((batch batches)) :max 24
    (provider-result providers.judge
      :prompt (rate-batch :intent intent :clones batch.clones)
      :model judge_model :effort "high" :timeout-sec 3600)))
```

This shape compiles at target 2.35 (probe recorded in the plan). The rubric
is the September rubric (`experiments/orc_vs_single_call/evaluation/rubric.md`):
root cause fixed, no validation weakened and nothing outside scope, holds
beyond the reported case, sits in the owning layer and reuses mechanisms. The
judge reads each clone's uncommitted changes and the code around them,
changes nothing, may not run tests, and compares the clones with each other.
`criterion_sha256` is a workflow input, so the run binds it in `run.json`
(`bound_inputs`, [`specs/state.md`](../../specs/state.md)) before any
effect runs; the summarizer reads it there. The memo holds the ratings.

### Completeness for E-B

For tasks a single call may not finish, judge scores alone cannot separate
"a better partial" from "done". `summarize.py` runs the hidden acceptance node
ids in each applied-patch clone with the project interpreter,
`PYTHONPATH` set to the clone (the editable install points elsewhere) and
`-p no:cacheprovider`, and reports the pass fraction next to the judge score.
The criterion names which measure is primary.

### Experiments

**E-A, replication on the evaluated route.** The September task at base
`468e7908` with its tracked task package; treatments `best_of_n` (judge
`gpt-6-sol`) and `reviewed_change` (reviewer `gpt-6-sol`); six runs each;
scoring per batch as in September. Primary criterion, both clauses as
predeclared in September: `best_of_n` gain against the candidate-group mean
in at least five of six runs with mean gain at least +0.75, and the
workflow's mean not below the mean of six single calls by the selector's own
model (`gpt-6-sol` through the harness control, which also exercises the
control arm before E-B); `reviewed_change` no run worse than its first call
and mean gain at least +0.5. Secondary: the paired gain against the first
candidate for `best_of_n`. The only intended difference from
September is the runtime; the judges differ (Q3), the scoring is typed, and
the control's single calls receive the bare task text where September's
selector-model calls used `best_of_n`'s implement prompt; the report lists
all three. Contamination is a new risk here because the fix is now public
(D5).

**E-A2, optional, a new task of the moderate class** from the census, same
treatments, same criterion. Runs only when E-A has reported and the owner
funds it (Q4).

**E-B, the class a single call does not finish.** Qualification first: two
control runs on the candidate task; the task qualifies when both score below
half on hidden acceptance; these runs are excluded from the baseline arm.
Treatment: `design_review_execute.orc` with planner `claude-fable-5-1`,
reviewer and executor `gpt-6.1-sol`; control: the harness `direct_task.orc`
with `gpt-6.1-sol`, effort high, the same binding and the same time limit.
Four runs per arm. Primary criterion: mean hidden-acceptance pass fraction,
treatment minus control, at least +0.3. Secondary: judge score, call count
and wall clock per run. `plan_review_execute.orc` may be added as a second
treatment when budget allows; it is not required.

Budget, serial, approximate. E-A: six `best_of_n` runs of five calls, six
`reviewed_change` runs of two to six calls and six single-call control runs,
about 7 to 10 hours; scoring, two judges times eight batches (six for
`best_of_n`, each carrying one control patch, two for `reviewed_change`),
16 judge calls. E-B: two qualification runs,
four control runs, four treatment runs of four calls with the executor bounded
at four hours, about 10 to 25 hours; scoring, one batch of up to ten clones
per judge. All live runs happen in tmux from a detached worktree at a
recorded commit.

## Contracts And Interfaces

- `prepare.py run` arguments: `--task` (directory with `task.txt`,
  `intent.txt`, `hidden_tests.txt`, `base_commit`, `seed/`, `anchors/`), `--arm`
  (`best_of_n`, `reviewed_change`, `design_review_execute`, `direct_task`),
  `--candidates N`, `--root`. It writes `inputs.json` matching the arm's typed
  inputs: `best_of_n` takes `task`, `intent`, `repos`; `reviewed_change` takes
  `task`, `intent`, `repo`; `design_review_execute` takes `task`,
  `planner_model`, `reviewer_model`; `direct_task` takes `task`, `model`,
  `effort`.
- Working directory per arm: `best_of_n` runs from the run root with absolute
  `repos`; `reviewed_change`, `design_review_execute` and `direct_task` run
  from inside their single candidate, because their implement prompts have no
  repository fill and the agent edits where it starts; `repo` for
  `reviewed_change` is that candidate's absolute path. `PYTHONPATH` names the
  frozen runtime checkout in every arm, and `TMPDIR` a directory under the
  run root, because task texts may name it.
- Shim environment: `COMPARE_ROOT` (run directory), `COMPARE_BASE` (commit).
  Everything else is the provider's own environment, including the user's
  CLI credentials.
- `criterion.json`: `experiment`, `task`, `base_commit`, `arms`, `comparator`
  per arm, `primary` and `secondary` measures with thresholds, `judges`,
  `runs_per_arm`, `anchors` by name, `written_before_scoring: true`. Its
  SHA-256 is the `criterion_sha256` input of every scoring run.
- `results.json`: per run and arm, every pooled patch's ratings per judge and
  criterion, anchor ratings per batch, hidden-acceptance fraction where
  applicable, call count, wall clock, scan result, exclusions with reasons,
  agreement counts, verdict.

## Dependencies And Sequencing

Needs current `main`, the provider bindings the treatments already use
(`claude_unrestricted_workspace`, `codex_unrestricted_workspace`, `codex`),
a judge binding per chosen judge family (the `gemini` template's model and
effort bindings are unverified; a binding compiles whether or not they exist,
so the probe runs a stand-in `gemini` script on `PATH` that records its
arguments and checks that the model reaches the CLI, before Google can be a
default),
access to the models named above, and tmux. Sequence: census and judge-binding
probe, then the harness and D1 in parallel, then E-A, then E-B.

## Invariants And Failure Modes

- Treatments are byte-identical to their maintained files; the harness
  references them by path, and the control differs from the library file by
  its time-limit line only. A test asserts both.
- Judges never see arm, stage, run or model; `mapping.json` lives outside the
  pool and is read only by `summarize.py`; design artifacts are stripped (D8).
- Every scoring run binds the criterion hash as an input in its `run.json`;
  the summarizer refuses to evaluate when any bound hash differs from the
  file's, and refuses any batch whose ratings do not line up with its clones.
- A run whose effect fails (`provider_result_missing`, timeout, non-zero
  exit) counts as a failed run of its arm, reported with its reason. Runs are
  never excluded to improve a mean; the only exclusion is a contamination hit
  under D5, and it is listed.
- A missing patch file for a call that should have produced one marks the run
  invalid; the cause (shim not first on `PATH`, provider environment not
  inheriting `PATH`) is a harness defect, not an outcome.
- An out-of-range score fails the scoring effect through the enumeration. No
  parsing of judge prose.

## Security, Operations, And Performance

Unrestricted-workspace providers work in candidate repositories under a
temporary root with no remote and no history past the base commit; they run
with the user's CLI credentials and network access, which is why D5 scans
rather than promises. Runs use a detached worktree of the recorded commit so
edits to `main` cannot leak in (design lesson 5). `list/map-effect` is
serial: four candidates take four times one call. Judge calls read one batch
each.

## Evidence And Implementation Boundaries

Evidence for a claim in the README is: the criterion file and its hash
bound in every scoring run's `run.json`, the pool with ratings, `results.json`, every
run's `memo.jsonl` and attempt directories, the scan results, and the report
under `docs/reports/`. The harness is not part of the runtime contract;
nothing under `specs/` changes. The design-lessons document is updated only
with measured columns after a report exists.

## Compatibility And Migration

- D1 removes modules nothing else imports. The matrix and index entries that
  route to the pilot become historical routes that say the apparatus was
  removed and where its evidence is.
- `experiments/orc_vs_single_call/harness/` stays as the September report's
  provenance; the report links it. It is not used by the new harness.
- Nothing in `experiments/orc_vs_single_call/workflows/` or
  `workflows/examples/` changes.

## Verification Strategy

- Unit tests for `prepare.py` and `summarize.py` on temporary git
  repositories: candidate built from the base commit alone with no other refs,
  patches include new files, seed files committed and absent from diffs,
  mapping blind, D8 stripping, batch composition per D4, position join with
  refusal on a wrong list length or a disagreeing copied-back id, agreement
  arithmetic, criterion hash refusal, hidden-acceptance fraction with
  `PYTHONPATH` at the clone.
- A consumer test for `score.orc` with deterministic providers in a new test
  module: compile, run, interrupted and completed resume, one `Rating` per
  clone per batch in the memo, `criterion_sha256` among the run's bound
  inputs in `run.json`, an out-of-range value in the deterministic result
  fails the effect.
- A test that the harness control differs from
  `workflows/library/control/direct_task.orc` by the time-limit line only.
- Provider-free end to end, the orchestrator smoke required by `AGENTS.md`:
  stand-in `claude` and `codex` scripts on `PATH` that write fixed results
  and make a fixed edit including a new file; every arm runs through the shim,
  `reviewed_change` through its request-changes branch, one run killed at a
  commit boundary and resumed with the call count compared; a stand-in judge
  scores a pool; `summarize.py` produces a verdict.
- Live: one run per arm on the chosen task before any batch; its memo, call
  directories and patches are inspected by hand.

## Declarative Acceptance / Integration Scenarios

- S1. Every arm with stand-in agents through the shim: call directories pair
  one to one with the memo's provider effects; every patch contains the
  stand-in's new file; `reviewed_change` reaches its request-changes branch;
  a killed `best_of_n` run resumes with no repeated call.
- S2. Pool one `best_of_n` run and one `reviewed_change` run with the two
  anchors, score with a stand-in judge: batches composed per D4, one `Rating`
  per clone per batch in the memo, joined by position; no arm, stage or
  design-artifact path anywhere under the pool. A stand-in judge that returns
  one rating too few, or a copied-back id that disagrees with its position:
  the summarizer refuses that batch and names it.
- S3. A scoring run whose bound `criterion_sha256` differs from the file's
  hash: the summarizer refuses and names both hashes.
- S4. A stand-in agent that writes no result file: the run fails with
  `provider_result_missing`; `results.json` lists a failed run with that
  reason; no mean is computed from it.
- S5. After D1: `task_loop.orc` and `orchestrator/experiments/` do not exist;
  the test suite collects; the matrix row reads Historical and links the
  evidence.

## Success Criteria

- Harness: S1 to S5 pass; the provider-free end to end runs in under five
  minutes; one live run per arm completes on the chosen task.
- E-A and E-B: the predeclared criteria are evaluated and reported whatever
  the outcome; the report states the comparator, the judges, the anchor
  scores, the agreement, the scan results and the exclusions. A README row
  changes only after the report exists.

## Stop / Revise Criteria

- The shim cannot see candidate repositories under a provider binding: revise
  D4's capture to a snapshot step in a harness-owned wrapper workflow rather
  than editing treatments; record the deviation.
- Contamination found in more than one run of a task: change the task, or
  move the task source to a repository that is not the runtime's own; the
  runs are reported as excluded.
- Qualification for E-B fails on two tasks in a row: the class may not exist
  at this size; report that and stop E-B.
- A judge family has no working binding: the owner picks another (Q3); no
  harness change.

## Documentation Impact

- `docs/capability_status_matrix.md`: lean-pilot row to Historical with the
  removal commit; one new row for the comparison harness.
- `docs/index.md` and `docs/design/README.md`: one entry each for this design
  and the plan; pilot entries say the apparatus was removed.
- `README.md` evidence table: rows for E-A and E-B after their reports exist.
- `docs/orc_workflow_design_lessons.md`: measured columns updated after the
  reports; the rules table gains nothing unless an experiment teaches a new
  rule.

## Implementation Handoff

Tasks, owners, parallelism and commands are in the
[plan](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md).

## Open Questions

- Q1 (owner). Delete the lean-pilot code and tests as in D1, or only mark the
  row Historical and leave the code. Recommendation: delete; the evidence is
  frozen elsewhere and the treatment cannot run.
- Q2 (owner). The E-B task, and the E-A2 task if funded, from the census in
  the plan. The REPL feature on branch `feature/orc-repl` is a further E-B
  candidate; its hidden tests were written by the agent that built it, which
  makes them a weaker oracle.
- Q3 (owner). Scoring judges. They must not be the treatment's judge or
  reviewer model; another family is stronger. E-A treatments use an OpenAI
  judge or reviewer; E-B uses Anthropic for design and OpenAI for execution.
  Default proposal: Anthropic Opus 5.5 plus Google if its binding works, else
  plus an OpenAI model distinct from the treatment's. The Google binding is
  probed in the plan's first task.
- Q4 (owner). Spend approval for E-A and E-B at the budget above; whether E-B
  runs four or six runs per arm; whether E-A2 runs.
- Q5 (owner). Whether task commits must postdate the models' training data,
  and from which date; and whether the task source may remain this
  repository given that the solution is public and on the same machine, or
  should move to another repository for E-B.
