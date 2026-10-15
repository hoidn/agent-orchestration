# Orc Effectiveness Comparison Harness: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [orc_effectiveness_comparison_harness.md](../../design/orc_effectiveness_comparison_harness.md).

## Original delivery metadata

- **D1. Retire the lean-pilot apparatus.** Delete `orchestrator/experiments/`,
  its package-data entry in `pyproject.toml`, `tests/experiments/test_lean_pilot_*.py`,
  `tests/experiments/fixtures/lean_pilot/`, `scripts/experiments/lean_pilot.py`,
  `scripts/experiments/conventional_coordinator.py` (its only importer),
  `workflows/experiments/repository_task_pilot/`, and the entries that name
  them in `tests/test_common_helper_architecture.py` and
  `tests/test_workflow_lisp_closed_program_corpus.py`. Keep
  `experiments/orc_effectiveness/lean_pilot/` as frozen evidence with a notice,
  the reports, the external evidence directory and the digest-bound
  owner-decision record. The matrix row becomes Retired (removed from the live surface; its
  references are provenance). Owner-approved (Q1).

### Experiments

Each experiment's decisions in full, including judges, anchors, run
floors, exclusions and E-B's qualification rule, are frozen in its criterion
file under `experiments/compare/criteria/` (§Contracts).

Deviation. Runs made under a harness defect are discarded as harness-invalid,
never pooled, and listed in the report with the defect; all runs made under
the defect are discarded, not only those that failed, because selecting on
outcome would bias any partial reuse. This applies to the E-A runs made while
run state lay outside the workspace and to the E-B qualification runs made
before the agent sandbox, when shared `/tmp` paths and another session's tmux
server exposed the solution to the agents' environment; those are not
adjudicated as contamination, since the environment, not the agent, reached
the solution. It applies as well to the `best_of_n` runs made before its
candidates could resolve the result path from their own repository; runs
of other arms stand when the fix touches only `best_of_n`. A defect the
harness accommodates in a maintained workflow rather than introduces, such
as `best_of_n`'s workspace-relative result path, is also reported as a
finding about that workflow. Reruns run at the fixed runtime commit, in a
fresh work root or, when the fix touches one arm only, under new run
numbers, and each criterion is amended (runtime commit, work roots, a deviation note
naming the discarded runs) and re-hashed before any rerun, with the old hash
cited in the amendment.

**E-A, replication on the evaluated route.** The September task at base
`468e7908` with its task package, tracked for the harness as
`experiments/compare/tasks/ea-loop-result-paths/`; treatments `best_of_n` (judge
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
all three. Contamination is a new risk here because later code on the same path is
public (D5). No upstream fix of record exists for this task, so the first
anchor is a drift reference (D6) and the scan's solution hash is `cdb60211`,
the later target-2.33 route that touches the loop result path code.

**E-A2, optional, a new task of the moderate class** from the census, same
treatments, same criterion. Runs only when E-A has reported and the owner
funds it (Q4).

**E-B, the class a single call does not finish.** Qualification first: two
control runs on the candidate task; the task qualifies when both score below
half on hidden acceptance; these runs are excluded from the baseline arm.
Treatment, as frozen for E-B on 2026-10-14 (historical):
`design_review_execute.orc` with planner `claude-fable-5-1`,
reviewer and executor `gpt-6.1-sol`; control: the harness `direct_task.orc`
with `gpt-6.1-sol`, effort high, the same binding and the same time limit.
Four runs per arm. Primary criterion: mean hidden-acceptance pass fraction,
treatment minus control, at least +0.3. Secondary: judge score, call count
and wall clock per run. `plan_review_execute.orc` may be added as a second
treatment when budget allows; it is not required.

**Difficulty calibration for follow-on experiments (owner, 2026-10-14; amended
2026-10-15).** A task can show a workflow's value only when the work leaves
something for the workflow to do. Later experiments raise task difficulty until
the expected number of review blockers is at least one. Before any treatment
run, the candidate task is measured on single-call patches made with the
control's binding. The task qualifies when the mean number of blocking findings
the treatment's reviewer raises on those patches is at least one; a mean from
1 up to but excluding 1.5 over the first two patches needs a third single call
and review before the task can qualify. The single call's hidden-acceptance
fraction is still measured and reported, as description, but it is not a
condition. The threshold, sample size and procedure are frozen in the
criterion. A task that misses the blocker threshold is replaced by a harder
task, not run. Census commits of a few hundred lines are not candidates. The
E-B qualification rule above (both control runs below half on hidden
acceptance) governed E-B only and is not a check for follow-on experiments.
The procedure, the review-only arm and the candidate ladder are in the plan's
Task 8. The plan's Task 9 ran on rung 3, which the owner chose before its
calibration was complete. Rung 3 was borderline under the current rule and
never got its third sample, so Task 9 is not a calibrated comparison. The first calibration
([report](../2026-10-14-task-difficulty-calibration.md)) ran under the
earlier two-condition rule, which also required every single call to pass less
than half of the hidden tests: it found the blocker condition met on every rung
tried, but no rung where both calibration single calls passed less than half,
so no rung qualified then. The owner removed that condition on 2026-10-15
(ruling R55; the criterion's `amends_4`); the frozen outcome stays as recorded.
A later post-data continuation chosen by the owner
([report](../2026-10-15-calibration-continuation.md)) completed rung 1
with a third sample: blockers 1, 1 and 1, so rung 1 qualifies. No comparison has
yet been run on it.

Budget, serial, approximate. E-A: six `best_of_n` runs of five calls, six
`reviewed_change` runs of two to six calls and six single-call control runs,
about 7 to 10 hours; scoring, two judges times eight batches (six for
`best_of_n`, each carrying one control patch, two for `reviewed_change`),
16 judge calls. E-B: two qualification runs,
four control runs, four treatment runs of four calls with the executor bounded
at four hours, about 10 to 25 hours; scoring, one batch of up to ten clones
per judge. All live runs happen in tmux from a detached worktree at a
recorded commit, outside the main checkout's path prefix and outside the
work root (§Layout).

## Implementation Handoff

Tasks, owners, parallelism and commands are in the
[plan](../../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md).

## Open Questions

- Q1 (owner). Delete the lean-pilot code and tests as in D1, or only mark the
  row Retired and leave the code. Recommendation: delete; the evidence is
  frozen elsewhere and the treatment cannot run. Ruled by the coordinator
  while the owner was away (R1): delete (D1).
- Q2 (owner). The E-B task, and the E-A2 task if funded, from the census in
  the plan. The REPL feature on branch `feature/orc-repl` is a further E-B
  candidate; its hidden tests were written by the agent that built it, which
  makes them a weaker oracle. Ruled by the coordinator (R5): E-B is the REPL's first release, base
  `47e85a9c` (the parent of the REPL design commit), task text from
  `experiments/orc_repl_feature/inputs.json` plus an appendix naming the
  public REPL forms and outputs the hidden tests drive, hidden set the node
  ids of `tests/test_workflow_evaluated_repl.py` that fail at the base and
  pass at `fe49c1c4`. E-A2 does not run.
- Q3 (owner). Scoring judges. They must not be the treatment's judge or
  reviewer model; another family is stronger. E-A treatments use an OpenAI
  judge or reviewer; E-B uses Anthropic for design and OpenAI for execution.
  Default proposal: Anthropic Opus 5.5 plus Google if its binding works, else
  plus an OpenAI model distinct from the treatment's. Ruled by the
  coordinator (R2):
  `claude-opus-5-5` plus an OpenAI model that is not the treatment's judge or
  reviewer, `gpt-6.1-sol` for E-A and `gpt-6-sol` for
  E-B; no Google judge (the `gemini` CLI is absent and its template has no
  model binding). The judges' shared families with treatment models are
  reported as a limit.
- Q4 (owner). Spend approval for E-A and E-B at the budget above; whether E-B
  runs four or six runs per arm; whether E-A2 runs. Ruled by the coordinator
  under the owner's instruction to run the experiments (R3, R32): the budget
  above; four E-B runs per arm; no E-A2; independent runs may run
  concurrently, and E-B may overlap E-A.
- Q5 (owner). Whether task commits must postdate the models' training data,
  and from which date; and whether the task source may remain this
  repository given that the solution is public and on the same machine, or
  should move to another repository for E-B. Ruled by the coordinator (R4):
  task commits after
  2026-07-01; the task source stays this repository, with detection (D5).
