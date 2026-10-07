# Workflow Lisp Evaluated Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Tasks inside one phase that touch disjoint files may run in parallel, each
> in its own git worktree. Reviews are made by a reviewer of a model family
> other than the implementer's. Track execution with the checkboxes below.

**Goal:** Make every `.orc` program that typechecks run, by evaluating the
compiled program with an environment of values and a memo of effects; and
add the numeric surface, structured effect inputs and the diagnostics that a
search controller needs.

**Architecture:** Phases 0 and 1 change no execution model: they repair what
is independent of it and test the model in throwaway code. The model enters
at one new target, after the owner's decision at gate G1. Targets that exist
today keep their behaviour.

**Tech Stack:** Python, Workflow Lisp typechecker and elaborator, the
workflow core calculus, the pure expression catalog, the command and provider
executors, pytest/pytest-xdist, command-backed procedures and stand-in
providers.

**Spec:** [evaluated execution](../design/workflow_lisp_evaluated_execution.md)
(rules E1 to E5, properties P1 to P7),
[numeric surface](../design/workflow_lisp_numeric_surface.md) (rules N1 to
N8), [execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md),
[value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md).

---

## Status, Authorities, And Scope

Status: Phases 0 and 1 are complete; the report for gate G1 is
[the spike report](../reports/2026-09-29-evaluated-execution-spike.md).
Phases 0 and 1 were selected as follows. The owner approved on 2026-09-29 the spike
of Phase 1, the repairs of the
[shared defect repairs plan](2026-09-29-workflow-lisp-shared-defect-repairs-plan.md),
and decisions 1 to 4 below. Gate G1 selected evaluated execution; Phase 2
compiler Tasks 1–11 are integrated at target 2.35 under the selected [implementation plan](2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md).
The [closeout report](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md)
records compilation/compatibility checks and the completed red-suite result;
Phase 2 compiler closeout is complete: code/verification review passed at
`17049e79`, documentation review passed at `a6efc7e7`, and both were integrated
at `a7b157d8`.
The owner's 2026-10-01 amendment sets the downstream order below. Phase 3
Tasks 1–15, documentation cuts 16A–16D and the reviewed size/complexity
corrections are integrated through tested code `ef689a39`. Tasks 16/17 and
Phase 3 are closed, delivered to `main` and `origin/main` at
`06130a53193e42dc1fdc2e9aa4575220bb43d707`. The
original full suite completed RED (402 failed, 23054 passed, exit 1), all
402 dispositions are recorded, and final affected execution passed all
2857 cases (including public smoke/recovery subsets) at `ef689a39`. The
refreshed old-target audit and qualified real-provider smoke are recorded;
independent final code/evidence and documentation/spec reviews are PASS. The [Phase 3 closeout report](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md)
records exact tested revisions, receipts and the downstream handoff. The reviewed
[early Phase 6a pilot plan](2026-10-07-evaluated-execution-phase-6a-pilot-plan.md)
records executed Tasks 1–3 and the [caller assessment](../reports/2026-10-07-evaluated-execution-phase-6a-pilot.md): all 21 pilot cases pass in the final `688695e3` campaign, while the full suite remains RED; the report owns closeout status. Global Phase 6a and W3 Task 4 compatibility remain open. Phases 4–7 remain pending, with no new target, capability or
retirement selection inferred from Phase 3 closure.

Owner decisions (2026-09-29, with target selection on 2026-09-30):

| # | Decision | Outcome |
| --- | --- | --- |
| 1 | The target that carries the surface changes of Phase 0 | 2.34 for the numeric surface; repetition reduction remains a separate unapproved proposal |
| 2 | Whether Phase 0 includes the interim repair of the flat route, Task 2 | Yes |
| 3 | Whether the numeric operators are adopted now or when a maintained workflow needs them | Now, with the fixture of the numeric surface design, section 4 |
| 4 | Where the spike lives and how long it may take | `experiments/evaluated_execution_spike/`, removed after the gate. One week of agent time |
| - | When Phase 0 starts and from which base | Now, from the integration branch of the repairs plan. It enters `main` after the repairs |
| 5 | Gate G1: the choice of architecture | Evaluated execution, built in stages at a new target. Beside Phase 2, one more experiment: a shipped workflow with a coordinator that is not a run reference, through both routes |
| 7 | The effect classes of the first release | Commands, the admitted portable composed-provider subset (without context capture), workflow/procedure calls and path-mode run references. Each other class enters later, with its own adapter and its own evidence through the public run and resume entries |

Decided on 2026-09-30: decision 6, the evaluated execution target, is **2.35**
(recorded by the Phase 2 owner in `bf6c9c9d`). The earlier recommendation of
a new major number is superseded; the runtime delivery scope is unchanged.

Decisions needed:

| # | Decision | Recommendation | Needed before |
| --- | --- | --- | --- |
| 8 | When older targets are retired, including how existing runs remain resumable or are explicitly retired | After the maintained workflows run at the new target, with an explicit disposition for existing runs | Phase 7 |

Base: the integration branch of the shared defect repairs plan, with `main`
and the paired search experiment merged in. Phases 0 and 1 merge to `main`
after that plan does.

Out of scope: YAML workflows; capture or rollback of workspace files; a
policy that schedules work as each result arrives.

## Global Constraints

- Until explicitly retired under decision 8, older targets accept and lower
  exactly what they do at the commit each phase starts from. Evidence is
  byte identity of every build artifact for identical identity inputs, with
  the program and the orchestrator package each at one fixed path and
  `PYTHONHASHSEED=0`.
  Preserve the compiler/runtime identity's truthful package-file pin: changed
  package bytes may change that pin and dependent run-ref artifacts at old
  targets. Report real-pin differences separately from raw serialization
  equality with a fixed identity input; never normalize the comparison or
  weaken the pin (design §13 and the Phase 2 plan's Global Constraints).
- No identity introduced by this plan contains a file path, a source
  position or the text of a type.
- Every refusal has a code and a source location, and prints the value it
  refused and the limit it applied.
- A result is validated before it is committed. No committed effect runs
  again.
- Tests assert behavior through the public run entry: values, ordered effect
  logs, diagnostics by code and location. No test asserts prompt text.
- No broad or full-suite test run while other agents are running. One full
  run at each phase closeout, alone, in tmux.
- New modules stay under 500 lines and new functions under cyclomatic
  complexity 12.
- Commit by pathspec. Commit messages carry no tool or assistant attribution.

## Review Focus

1. Two call sites of one procedure must have two effect identities, and one
   call site reached in two loop iterations must have two. Tasks 8 and 12
   test both with a procedure called from three arms of one `match` inside a
   loop.
2. A result file that is complete and valid, left by an attempt that did not
   commit, must never become a result. Tasks 9 and 14 test the three moments
   of the design's section 8.
3. Sharing a bound value in a payload must not change the order in which
   effects run or the value of any program that compiles today. Task 2
   compares the corpus before and after.
4. A non-finite number must be refused where it enters, and never reach a
   digest or a state file. Tasks 5 and 7 test each boundary.
5. A program that the spike runs must give the trace of the flat route where
   the flat route accepts it. A difference is a finding about one of the two
   routes, and is reported, not reconciled.

---

## Phase 0: Independent Of The Execution Model

### Task 0: Target 2.34 Exists

- [x] Complete

Decision 1. Tasks 3, 4 and 6 start from this task's commit.

**Read/trace:** `orchestrator/workflow_lisp/syntax.py` (the supported
targets), `orchestrator/workflow/validation.py`,
`orchestrator/workflow/run_ref/config.py`,
`orchestrator/workflow/run_ref/bundle_transport.py`,
`tests/test_workflow_lisp_target_233.py`, `specs/versioning.md`,
`specs/dsl.md`.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_target_234.py`.

1. Write failing tests: a program that declares target 2.34 compiles and
   runs through the public run entry; at 2.34 it builds the artifacts it
   builds at 2.33, apart from the version each artifact records.
2. Implement. 2.34 accepts and lowers exactly what 2.33 does.
3. State in `specs/versioning.md` that 2.34 exists and what later tasks add
   to it.


### Task 1: A Refusal Prints What It Refused

- [x] Complete

**Read/trace:** `orchestrator/workflow/pure_expr.py`
(`validate_pure_expr_payload`), `orchestrator/workflow_lisp/lowering/pure_projection.py`
(where the count and the limit are dropped, about lines 1610 to 1627),
`docs/design/workflow_language_design_principles.md` principle 28.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_refusals_show_limits.py`.

1. Write failing tests: `pure_expr_payload_too_large` prints the node count,
   the limit, and the three subexpressions that contribute most, each with
   its source location and its count.
2. List every refusal in the compiler and the runtime that compares a value
   with a limit: loop bounds, list map caps, attempt counts, member counts of
   provider groups, timeouts, integer overflow. For each, write a test that
   the diagnostic prints the value and the limit.
3. Implement. Exit codes and diagnostic codes do not change.

### Task 2: A Bound Value Is Shared In A Pure Payload

- [x] Complete

Interim repair of the flat route. Decision 2.

**Read/trace:** `orchestrator/workflow_lisp/lowering/pure_projection.py`
(bindings copied at each use, about lines 628 to 658; the branch that emits a
`let` node, about lines 532 to 575), the `let` node of payload schema 3 in
`orchestrator/workflow/pure_expr.py`, the execution facts, section E.3.
**Update:** `lowering/pure_projection.py`.
**Create:** `tests/test_workflow_lisp_shared_pure_bindings.py`.

1. Write failing tests at target 2.33: a value bound with `let*` to an
   operator expression and used 100 times compiles and runs; the node count
   of its payload grows by one per use; the state update of the search
   controller passes the size check.
2. Implement: a binding used more than once is emitted once and referred to.
3. A binding used once is emitted as today. Compile the corpus before and
   after: programs whose bindings are each used once build identical
   artifacts. List the programs that change, with their old and new counts.
4. Compare, for every program that changes, the value and the ordered effect
   log of a run before and after.
5. Report what the search controller meets next.

### Task 3: Decimal Literals In Expressions

- [x] Complete

Numeric surface, rule N1.

**Read/trace:** `orchestrator/workflow_lisp/reader.py` (the literal
pattern), `orchestrator/workflow_lisp/expressions.py` (the guard that admits
a decimal literal only as a parameter default).
**Update:** those owners, at the target of decision 1.
**Create:** `tests/test_workflow_lisp_float_literals.py`.

1. Write failing tests: each form of N1 compiles and runs as a `let*`
   binding, a record field, an operand of an ordering, a loop state seed and
   a workflow result; a literal too large for a double is refused when the
   program is read; at 2.33 the refusal of today stays.
2. Implement.

### Task 4: Finite Values At Every Boundary

- [x] Complete

Numeric surface, rules N6 and N7.

**Read/trace:** `orchestrator/contracts/output_contract.py` (inputs, bundle
fields, expected outputs), `orchestrator/workflow/signatures.py`,
`orchestrator/state.py` (how floats are written).
**Update:** those owners, at the target of decision 1.
**Create:** `tests/test_workflow_float_boundaries.py`.

1. Write failing tests for each row of N6, at each of the four boundaries:
   refused with `float_not_finite`, naming the field; no state file contains
   the token `NaN`.
2. Write the controls at 2.33: accepted as today.
3. Implement.

### Task 5: What `.orc` Runs Today

- [x] Complete

Runs with Task 10 of the shared defect repairs plan, which edits the same
three documents, after Tasks 2, 3 and 6 of this plan.

**Read:** the totality matrix and its report; the execution facts, sections
D and E; `docs/orc_workflow_design_lessons.md`.
**Update:** `docs/lisp_workflow_drafting_guide.md`,
`docs/orc_workflow_design_lessons.md`, `docs/capability_status_matrix.md`.

1. Add one section to the drafting guide: the shapes of program that run,
   and the shapes that do not, each with the diagnostic an author will see
   and the form to write in its place where one exists. Take each row from a
   program that was run.
2. Include at least: a loop inside a branch, with the call boundary that
   gives it a top level; a loop inside a loop; a state update over many
   fields; a record as a command input; arithmetic over decimals; parallel
   commands; a helper shared by two branches inside a loop.
3. Say for each row whether it is a rule of the language or a defect of the
   compiler.
4. Every program quoted in the guide compiles or fails as the guide says. A
   test runs them.

### Task 6: Numeric Operators

- [x] Complete

Numeric surface, rules N2 to N5 and N8. Decision 3.

**Read/trace:** `orchestrator/workflow/pure_expr.py` (the catalog, static
typing, evaluation), `orchestrator/workflow_lisp/typecheck_pure_ops.py`,
`orchestrator/workflow_lisp/wcc/defunctionalize.py` (the fourth copy of the
type rules, about line 4180).
**Update:** those owners, at the target of decision 1.
**Create:** `tests/test_workflow_pure_numeric_operators.py`,
`tests/test_workflow_pure_catalog_agreement.py`.

1. Write failing tests for each operator of N2 and N3: a result, each
   refusal of N4, and the refusal at compile time for literal operands.
2. Write the agreement test: over a generated set of applications, well
   typed and not, the frontend check, the static typing of payloads and the
   evaluator give the same answer.
3. Implement each operator once, in the catalog. Remove the copies of the
   type rules that the catalog makes unnecessary.
4. Write the fixture: the search controller with selection by the rule of
   the numeric surface design, section 4, and its Python reference. It makes
   the reference's decisions.

### Task 7: The Search Controller As A Fixture

- [x] Complete

**Read:** the paired comparison under `experiments/mlevolve_pair/`, its
report and its report of limits, once their author commits them.
**Create:** `tests/experiments/test_mlevolve_pair_fixture.py`.

1. Record the trace of the Python reference: every decision, in order, the
   budget spent and the result.
2. Add the compact form of the `.orc` controller, with one helper for both
   branches, beside the form with a copy per branch.
3. Write tests that state what each form meets today, by diagnostic code.
   They change to tests of the trace when a later task makes the form run.

## Phase 1: Spike

Throwaway code under the directory of decision 4. Not wired to
`orchestrator run`. Removed after gate G1.

### Task 8: The Closed Program, For The Spike's Programs

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/wcc/model.py`,
`wcc/elaborate.py`, `wcc/anf.py`, the execution facts, section A.
**Create:** spike code and `tests/experiments/test_evaluated_execution_spike.py`.

1. From the elaborated program of each spike program, build a closed
   program: callee bodies elaborated and attached, a site for each effect
   with its lexical path, no surface object left. Where a property of the
   design's section 4 cannot be obtained from the elaborator as it is, write
   down which and why.
2. Test the identity rules of the design's section 6: three call sites of
   one procedure give three sites; blank lines and a move of the file change
   none.

### Task 9: Evaluator, Memo And Resume

- [x] Complete

**Create:** spike code and tests in the module of Task 8.

1. Evaluate `let`, `perform`, `call`, `case`, `if`, `select`, `join`,
   `jump`, `loop`, `continue`, `done` and `halt`. Pure operators come from
   the catalog.
2. Effects: commands through `StepExecutor.execute_command`, and stand-in
   providers. Each attempt has its own result path.
3. The memo: an append-only file, one writer, records synchronized to disk.
4. Resume: evaluation from the entry with the memo. Implement the table of
   the design's section 8.

### Task 10: Run The Fixtures And Report

- [x] Complete

**Create:** `docs/reports/2026-09-29-evaluated-execution-spike.md`.

Fixtures: the known-defect cells of the totality matrix; the six programs of
the decision brief; the `std/improve` example; the two workflows of the
single-call comparison; the search controller in its compact form; a loop in
a branch; a loop in a loop; a nested `if` in a hook.

Criteria, fixed before the spike starts. A failed criterion is a finding. It
is reported, and the criterion is not changed.

| # | Criterion | Pass |
| --- | --- | --- |
| 1 | Every fixture that typechecks evaluates | All return the expected value, source unchanged apart from what Task 8 records |
| 2 | The search controller | The decisions of the Python reference, in order, the same budget spent, the same result |
| 3 | Resume | Interrupting after each effect of each fixture and resuming gives the uninterrupted result, and no committed effect runs twice |
| 4 | A result that did not commit | A complete, valid file left by an interrupted attempt is not taken as a result |
| 5 | Identity | Unchanged under blank lines and under a move of the program and of the package |
| 6 | Sites | Every identity in a memo is an instance of a site listed before the run |
| 7 | Parity | On programs the flat route accepts, equal ordered effect identities, inputs and results, and equal final value |
| 8 | Size | Evaluator and memo under 2,000 lines, reused modules excluded |
| 9 | What could not be built | A list of every property of the closed program that needed a change to the elaborator, with its size |

### Gate G1

Decided by the owner on 2026-09-29: evaluated execution. The conditions that
the [spike report](../reports/2026-09-29-evaluated-execution-spike.md),
section 6, gives bind the first release. The design is revised with the
decisions that the spike had to guess before the plan of Phase 2 is written.


The owner selected evaluated execution over repairing the flat route or
values as expressions, on the report of Task 10. Each later phase gets its
own implementation plan when selected; G1 is not reopened by the delivery
ordering below.

---

## Phases After The Gate

Milestones, entry conditions and evidence. Tasks are written when a phase is
selected.

### Delivery Order And Preserved Capabilities

Owner amendment, 2026-10-01:

**Phase 2 → Phase 3 → Phase 6a pilot → Phase 4 additions (including W3) and
Phase 5 → Phase 6b migration → Phase 7 retirement.**

This is the preferred delivery order, not a serial dependency chain or a
requirement to finish every effect class before using the runtime. Phase 5
may start after Phase 3 alongside the
pilot; it does not wait for all of Phase 4. Phase 6b advances consumer by
consumer as the capabilities each needs land. Existing phase numbers and
the selected Phase 2 task order stay unchanged.

Simplify the execution machinery, not the language's useful contracts:

| Capability to retain | Delivery and evidence |
| --- | --- |
| Generic procedures, hooks and nested composition | Phases 2–3 retain admitted call/binding forms and arbitrary admitted nesting. The pilot reuses a helper with different domain types and hooks, without position-repair wrappers |
| Metalinguistic abstraction | Retain existing macro expansion and source provenance through compilation; do not replace reusable language abstractions with special runtime cases |
| Typed prompt and result contracts | Preserve prompt assembly, validation and typed value transport for admitted effects; the pilot exercises these through public entries |
| Artifact production, publication, consumption, freshness and lineage | Preserve the existing contracts needed by each migrating consumer and demonstrate a producer-to-consumer handoff. Memoized values do not substitute for artifact tracking, nor do declared dependencies prove every file an agent actually read |
| Explicit portable provider context | A named Phase 4 priority, with capture, transformation/forking and rebinding evidence; not part of the first-release portable provider subset |
| Local hooks with inferred context (W3) | Phase 6a qualifies the caller improvement; Phase 4c delivers capture/signature inference and the context-free `improve` API; Phase 6b migrates maintained consumers |

Delivery integration, 2026-10-01: W3 belongs to this delivery sequence as
Phase 4c. The [repetition-reduction plan](2026-09-29-workflow-lisp-repetition-reduction-plan.md#w3-planning-amendment)
retains its technical tasks, not a competing schedule. Grammar, target and
module compatibility remain open prerequisites; scheduling W3 does not mark
it implemented or start a run. Other repetition rules and the
[effect-ledger workstream](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#el-1--effect-contracts-and-analysis-cleanup-pending-unselected)
remain separately scoped. None becomes a prerequisite for Phases 2–3.

### Phase 2: The Closed Program

All eleven compiler/documentation tasks and the reviewed compatibility and
build-path safety repairs are integrated. Public CLI compilation at 2.35
writes the checked closed-program artifact; execution/resume remain Phase 3
work. The [closeout report](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md)
records the exact corpus, fresh public smokes, raw compatibility and completed
red-suite diagnosis. Code/verification review passed at `17049e79`,
documentation review passed at `a6efc7e7`, and both were integrated at
`a7b157d8`; Phase 2 compiler closeout is complete.

Entry: gate G1. Execute the selected
[Phase 2 plan](2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md)
without adding downstream runtime work or a general transformation engine.
The corpus below is the admitted first-release scope; later effect classes
remain explicit release gaps, not extra Phase 2 prerequisites.

| Milestone | Evidence |
| --- | --- |
| P1. Callee bodies are part of the program | Every workflow of the corpus builds a closed program with no elaboration after it |
| P2. No surface object in a node | A validator refuses a program that holds one; the corpus passes |
| P3. Effects carry their contract, prompt assembly, policy and repeat rule | For each effect of the corpus, the contract and the assembled prompt equal those of the flat route |
| P4. The site table | Review focus 1 |
| P5. The normal form is checked when the program is built | Mutations of a program that break the form are refused |
| P6. Provenance outside identity | Criterion 5 of the spike, on the corpus |
| P7. The program is an artifact with a digest | Two builds of one source, at two paths, give one digest |

### Phase 3: Evaluator, Memo And State Profile

Entry: Phase 2.

Execution follows the reviewed [Phase 3 implementation plan](2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md).
Its task checklist owns implementation progress; this link does not mark
the runtime or later phases complete.

Deliver a coherent executable core for the admitted effect classes, not a
collection of preferred syntactic positions. A failure to close or evaluate
an admitted composition is a compiler/runtime defect, not a reason to
require a wrapper or narrow nesting. Restrict effect-class admission as the
design specifies, not compositional semantics within that admission.

| Milestone | Evidence |
| --- | --- |
| Values and one implementation of pure operators | The agreement test of Task 6, extended to the evaluator of programs |
| Evaluation of every admitted construct, with nesting | No known defect in the first-release cells of the totality matrix; later-class gaps remain explicitly identified |
| The memo and the table of resume | Review focus 2; criterion 3 of the spike on the corpus |
| Typed input documents | A command receives a list of records of unions and returns it unchanged |
| Performers for commands and composed providers | The `std/improve` example and the single-call comparison workflows run with stand-in providers, then with real ones |
| Workflow/procedure calls and path-mode run references | Public run and committed-boundary resume, including nested calls; the run-reference adapter preserves its ledger contract |
| The views | `orchestrator report`, the dashboard cursor, the monitor classifier and the watchdog probe read a state derived from a memo |
| `run`, `resume`, `--dry-run` | Public compile, dry-run, run and resume of first-release fixtures, including consumers nominated for Phase 6a; the authoring pilot follows Phase 3, not a prerequisite for it |
| The state profile in `specs/state.md` | The specification and the code agree on every key of the view |

Historical milestone evidence, 2026-10-06 (Tasks 1–15): Tasks 1–14 of the Phase 3
plan are implemented, reviewed and integrated at head `dc4a4e3a`. Per
milestone, the public owners are: values and the single pure catalog,
`tests/test_workflow_evaluated_values.py`; every admitted construct with
nesting, the target-2.35 totality matrix of Task 13A
(`tests/test_workflow_evaluated_totality.py`, no admitted known defect) and the
compact search with its growth variant (Task 13C,
`tests/test_workflow_evaluated_programs.py`, all 72 reference pairs); the memo
and the resume table, `tests/test_workflow_evaluated_memo.py`,
`tests/test_workflow_evaluated_resume*.py`,
`tests/test_workflow_evaluated_invalidate*.py`; typed input documents,
`tests/test_workflow_evaluated_input_document*.py` (Task 12); performers for
commands and composed providers, `tests/test_workflow_evaluated_commands.py`,
`tests/test_workflow_evaluated_providers.py`, the stand-in consumers in
`tests/test_workflow_evaluated_consumers.py` and the live runs of
`std/improve`, `reviewed_change` and `best_of_n` with the configured providers
(Task 14D, rounds 1–2: public run, committed-boundary resume without
redispatch, completed resume); calls and path-mode run references,
`tests/test_workflow_evaluated_calls.py`, `tests/test_workflow_evaluated_run_ref*.py`
(Task 9, 13B); the views and readers, `tests/test_workflow_evaluated_views.py`,
`tests/test_workflow_evaluated_readers.py`, `..._dashboard.py`, `..._monitor.py`,
`..._watchdog_probe.py`, `..._watchdog_watcher.py` (Tasks 10–11); public
compile/dry-run/run/resume, `tests/test_workflow_evaluated_cli.py` and the
[drafting guide recipe](../lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate);
the state profile, the Task 16 key-for-key inventory of 28 public cases and
46 run roots, published by the Task 16D closeout, against `specs/state.md`.
Task 15C (durable publication fault model, invalidation kill windows;
[`tests/test_workflow_evaluated_durability_model.py`](../../tests/test_workflow_evaluated_durability_model.py),
[`tests/test_workflow_evaluated_invalidate_windows.py`](../../tests/test_workflow_evaluated_invalidate_windows.py)) is integrated at
`dab04431` and 15D (view failure after commit, later divergence before
reconcile/tail repair, completed resume twice;
[`tests/test_workflow_evaluated_recovery_views.py`](../../tests/test_workflow_evaluated_recovery_views.py)) at `a84f2769`;
15A/15B (external kills at every window of the three programs and of the
consumer harness's branch scenarios, must-not-repeat launcher controls,
closure mutation then kill;
[`tests/test_workflow_evaluated_recovery.py`](../../tests/test_workflow_evaluated_recovery.py),
[`tests/test_workflow_evaluated_recovery_branches.py`](../../tests/test_workflow_evaluated_recovery_branches.py))
at `2604e887`, with Task 15 recorded complete at `500767d0`. Documentation
cuts 16A–16D and the independent corrective reviews are integrated through
`ef689a39`; the [closeout report](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md#task-17-open-full-run-completed-red)
records the original completed RED full run and its dispositions alongside
the completed 2857-case final affected run (including public smoke/recovery
subsets), refreshed audit and qualified real-provider smoke. Independent final
code/evidence review is PASS at `ef689a39`; final documentation/spec review
is PASS, and fast-forward merge/push delivered `06130a53` to `main` and
`origin/main`. Tasks 16/17 and Phase 3 are closed. The reviewed early pilot’s
entry was satisfied and Tasks 1–3 have bounded independent PASS reviews. Its [final campaign and assessment](../reports/2026-10-07-evaluated-execution-phase-6a-pilot.md#final-campaign-and-compatibility) record 21 passing pilot cases and a RED full suite, with closeout status owned by that report. The finite totality matrix does not cover the known pre-existing pure-inline shadow defect (101 versus lexical 8). Closing the bounded pilot will not close global Phase 6a while W3 Task 4 migration/compatibility is open. Delivery order remains Phase 3 → early Phase 6a pilot → consumer-selected
Phase 4 additions and independent Phase 5 → Phase 6b → Phase 7.

### Phase 4: Consumer Capabilities And Authoring

Entry: Phase 3. Select additions by a named maintained consumer's need,
not a fixed port of every historical runtime class. New effect classes need
an adapter and public run/resume evidence preserving their contract and
ledger. Authoring changes reuse existing effect and execution owners.

- **4a — Priority additions:** portable context capture and rebinding,
  governed by [Provider Context Values](../design/workflow_lisp_provider_context_values.md)
  and [PC-1](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#pc-1--first-class-provider-context-pending-unselected).
  Name the consumer when selecting its implementation slice. Demonstrate
  snapshot → transform/fork → bind, carriage through reusable procedures,
  and resume without repeating committed calls. Start with the existing
  ordinary portable-context subset; this does not select native sessions,
  unsupported adapters or lossless cross-provider continuation. Close any
  remaining artifact publication/consumption/freshness gaps required by a
  selected consumer before migrating it; do not defer obligations already
  belonging to an admitted first-release effect.
- **4b — Other classes when needed:** requests for human input, resource
  transitions, materialized views, phased providers, supervision/peer groups,
  adjudication, trials, native sequential turns (PQ-1 below), and remaining
  run-reference modes. Name the consumer
  and the missing behavior before selecting a class. Path-mode run references
  already belong to Phases 2–3; they do not wait here.
- **4c — W3 local hooks:** deliver multiple `let-proc` bindings, inferred
  lexical captures, expected `ProcRef` signatures and `improve` without
  `inputs I`, using the existing compiler and Phase 3 evaluator. The
  [component plan](2026-09-29-workflow-lisp-repetition-reduction-plan.md#e-hooks-that-capture-their-context)
  owns Tasks 11 → 12 → 13 → 14, after Task 4 qualification and Task 6 target
  registration. Entry includes the Phase 6a caller assessment and resolved
  grammar/target/module compatibility. Prove public compile/run/resume,
  definition-site captures and no repeated committed effects on the shipped
  proposal example and the `reviewed_change.orc` helper variant. Task 14
  proves representative migration; the maintained-consumer rollout belongs
  to Phase 6b. W3 adds no runtime closure or new effect class.

An unneeded class may remain deferred or be retired with its consumers by
explicit decision. The 4a/4b/4c lanes need not run serially; W3 does not wait
for unrelated effect ports or W0/W1/W2/W4. Phase 4 is not an all-or-nothing
prerequisite for Phase 5 or each Phase 6b consumer.

#### PQ-1: Sequential Native-Session Turns

**Status:** pending, consumer-conditioned Phase 4 work, recorded by owner
request on 2026-10-01; not implementation selection or admission at target
2.35. Governing [design](../design/workflow_lisp_provider_prompt_queue.md).
This adds no prerequisite to Phases 2–3, Phase 5, the early Phase 6a pilot,
or portable context in 4a/PC-1. Neither Q5's existing transport nor portable
context implements this capability.

**Candidate consumer:** an opt-in coder-call variant of
[`reviewed_change.orc`](../../experiments/orc_vs_single_call/workflows/reviewed_change.orc):
investigate → implement → self-review, returning its existing `Change` type.
Keep the outer independent reviewer and review/revise control flow intact;
self-review does not replace independent review. Select a session-capable
provider explicitly; do not silently change the current consumer's model or
claim that its existing typed prompt already fits the queue. No consumer is
changed by this roadmap entry.

| Step | Work and evidence | Consequence |
| --- | --- | --- |
| PQ-1a — qualify the bounded design | Review the design against the selected adapter and named consumer. Prove three delayed turns in one conversation, and continuation of a durably completed prefix. Resolve the scoped K4 recovery refinement and final commit gaps; specify timeout scope and resume accounting, unresolved-turn/session-loss behavior and prompt-source limits | Prerequisites remain open until evidenced. Select an implementation plan and target only for the qualified scope; revise an obstructing adapter/design assumption before dropping the use case |
| PQ-1b — deliver the consumer slice | Existing `provider-result` configuration, finite enumerated prompt externs, one final typed result; reuse transport/session/prompt owners. Public compile/run/resume, invocation-count checks, composed helper placement and a real provider smoke | Keep first delivery bounded, without a second session manager, external inbox, or wholesale coordinator rewrite. Static membership is a delivery limit, not a permanent restriction justified by the old runtime |
| PQ-1c — retain, improve, or simplify | Inspect normal authoring and actual recovery/friction relative to ordinary context passing; no new scoring apparatus or requirement that all five axes pass | Retain useful native continuity; improve concrete limitations (including typed fragments or bounded computed queues when justified), or cancel/remove unused queue-specific machinery while retaining independent transport/context capabilities |

The generic coordinator restart rule is not evidence for prefix recovery.
PQ-1a owns that open prerequisite; it does not authorize edits to the
first-release protocol or the running Phase 2 task order. There is no new
executable selector/manifest or top-level phase. Implementation tasks are
written only after explicit selection of this bounded slice.

### Phase 5: Parallel Map

The [prepared Phase 5 plan](2026-10-07-evaluated-execution-phase-5-plan.md) records accepted D2/D3 design and the remaining **D1 owner target decision**. No target, implementation or public parallel-execution evidence is selected or established by publishing it.

Entry: Phase 3, and a workflow that needs it. The best-of-N workflow of the
single-call comparison is one: its four implementers run in sequence.
Recommended alongside the early pilot, independently of unneeded Phase 4
classes. Reuse the evaluator and memo; no general scheduling framework is
part of this phase.

| Milestone | Evidence |
| --- | --- |
| `par-map` in the closed program and the evaluator | Four items, two at a time: the result list is in input order whatever the order of completion |
| Identity by item index | Resume after two of four items committed runs the other two only |
| A working directory per item | Two items that resolve to one directory are refused before launch |
| One writer for the memo | A run with eight items finishing together has eight committed records and no torn one |

### Phase 6: Migration

**6a — Early pilot.** Entry: Phase 3. Select a small set of maintained
workflows whose effects are admitted, starting from the `std/improve` and
single-call comparison consumers already used by Phase 3. Do not wait for
all of Phase 4. Record public compile, dry-run, run and resume evidence,
including no redispatch of committed effects. Compare values and required
effect ordering with the flat route where it runs; for formerly broken
compositions, check the intended behavior, not parity with the defect.

Exercise actual authoring and modification: reuse a generic helper with
different domain types/hooks, compose nested calls without positional
workarounds, and trace an artifact handoff. Assess reuse ergonomics from
those changes and reasoned review, not an arbitrary build count, line-count
threshold or mandatory benchmark harness. Record missing capability evidence
as missing. Phase 3 and this pilot are the first evaluation point, not a
global abandon/continue verdict before context and other differentiating
capabilities can be exercised.

For W3, use the existing explicit-hook API for the baseline and perform
[component Task 4](2026-09-29-workflow-lisp-repetition-reduction-plan.md#task-4-qualify-w3-on-concrete-callers):
compare the local-hook proposal, identify forwarding to delete and settle
the migration/compatibility decision. Qualification preparation can overlap
Phase 3; the pilot supplies executable caller evidence before Phase 4c.
Do not require unimplemented W3 syntax to run the pilot.

Execution update, 2026-10-07: the [pilot report](../reports/2026-10-07-evaluated-execution-phase-6a-pilot.md#assessment-and-next-handoff) supplies the proposal/explicit/bound caller assessment, truthful helper-inclusive counts, two separately reviewed compiler corrections and the W3 decision table. The full campaign passes all 21 pilot cases and the existing 400-case totality owner but remains RED overall; the report owns closeout status. The pure-inline lexical shadow defect remains with the frontend/compiler owner. W3 grammar/inference, target, standard-module and checkpoint/migration decisions remain open for Phase 4c; portable context needs a named consumer, and the existing serial `best_of_n` need goes to Phase 5. No canonical migration or later capability is selected here.

Use observed friction to select a principled improvement, a justified
design/type-system revision, or explicit simplification of an unhelpful
feature. A current design limit is not proof that the use case is
impossible; investigate the limit before dropping the case. Scope changes
still need selection, not an automatic expansion of the running phase.

**6b — Maintained-consumer migration.** Entry per consumer: Phase 3 plus
only the Phase 4/5 capabilities it needs. Extend pilot evidence to portable
context reuse and parallel best-of-N as those land; parallel execution need
not reproduce the old serial completion order, but must preserve results
and required dependencies. Preserve contracts and useful lineage, not the
old state representation. Migration covers maintained consumers, not every
historical/deprecated example; identify any consumer explicitly retired
instead of ported. Complete this phase when the maintained set runs and
resumes on the new runtime with its required capabilities.

After Phase 4c, migrate each maintained `improve` consumer covered by W3's
inventory to the context-free API and remove context-only forwarding.
Consumers that do not need W3 can migrate earlier; old-target checkpoints
retain their resolved module/runtime contract until their retirement decision.

### Phase 7: Retirement

Entry: completed Phase 6b and the owner's decision 8, including a disposition
for existing old-profile runs. Remove code serving only retired targets
once no maintained consumer needs it: displaced flat lowering, replay and
state-translation machinery, not useful language contracts or shared
performers. Until then, old runs keep their documented resume route. Two
runtimes are a migration cost, not the intended permanent architecture;
retirement is a delivery milestone, not indefinite optional cleanup.

---

## Closeout, Per Phase

- [ ] The totality matrix: counts before and after.
- [ ] Byte identity for targets that exist today.
- [ ] Full suite in tmux, alone: `pytest -q -n 16 --dist=worksteal`, compared
  with the failure set of the commit the phase started from; no new
  failures.
- [ ] Public evidence, fresh output: compile, run and resume of one program
  per new form.
- [ ] Review of the phase by a reviewer of a model family other than the
  implementer's.
- [ ] Merge to `main` by fast-forward; push.
