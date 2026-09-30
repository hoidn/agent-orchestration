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
execution is authorized at target 2.35. Later phases retain their staged gates.

Owner decisions (2026-09-29, with target selection on 2026-09-30):

| # | Decision | Outcome |
| --- | --- | --- |
| 1 | The target that carries the surface changes of Phase 0 | 2.34, the target of the repetition reduction plan |
| 2 | Whether Phase 0 includes the interim repair of the flat route, Task 2 | Yes |
| 3 | Whether the numeric operators are adopted now or when a maintained workflow needs them | Now, with the fixture of the numeric surface design, section 4 |
| 4 | Where the spike lives and how long it may take | `experiments/evaluated_execution_spike/`, removed after the gate. One week of agent time |
| - | When Phase 0 starts and from which base | Now, from the integration branch of the repairs plan. It enters `main` after the repairs |
| 5 | Gate G1: the choice of architecture | Evaluated execution, built in stages at a new target. Beside Phase 2, one more experiment: a shipped workflow with a coordinator that is not a run reference, through both routes |
| 6 | The number of the evaluated execution target | 2.35, selected by the owner on 2026-09-30 |
| 7 | The effect classes of the first release | Commands, composed providers, calls of workflows, run references. Each other class enters later, with its own adapter and its own evidence through the public run and resume entries |

Decisions needed:

| # | Decision | Recommendation | Needed before |
| --- | --- | --- | --- |
| 8 | When older targets are retired | After the maintained workflows run at the new target | Phase 7 |

Base: the integration branch of the shared defect repairs plan, with `main`
and the paired search experiment merged in. Phases 0 and 1 merge to `main`
after that plan does.

Out of scope: YAML workflows; capture or rollback of workspace files; a
policy that schedules work as each result arrives.

## Global Constraints

- Targets that exist today accept and lower exactly what they do at the
  commit each phase starts from. Evidence is byte identity of every build
  artifact, with the program and the orchestrator package each at one fixed
  path and `PYTHONHASHSEED=0`.
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


The owner chooses among repairing the flat route, values as expressions, and
evaluated execution, on the report of Task 10. Phases 2 to 7 follow only the
third choice. Each gets its own plan when it is selected.

---

## Phases After The Gate

Milestones, entry conditions and evidence. Tasks are written when a phase is
selected.

### Phase 2: The Closed Program

Entry: gate G1.

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

| Milestone | Evidence |
| --- | --- |
| Values and one implementation of pure operators | The agreement test of Task 6, extended to the evaluator of programs |
| Evaluation of every construct, with nesting | The totality matrix with no known defect |
| The memo and the table of resume | Review focus 2; criterion 3 of the spike on the corpus |
| Typed input documents | A command receives a list of records of unions and returns it unchanged |
| Performers for commands and composed providers | The `std/improve` example and the single-call comparison workflows run with stand-in providers, then with real ones |
| The views | `orchestrator report`, the dashboard cursor, the monitor classifier and the watchdog probe read a state derived from a memo |
| `run`, `resume`, `--dry-run` | Compile, run and resume of each maintained workflow through the public entry |
| The state profile in `specs/state.md` | The specification and the code agree on every key of the view |

### Phase 4: The Other Effect Classes

Entry: Phase 3. One milestone per class, in this order: request for input,
resource transition, materialized view, provider with phased delivery,
supervision and peer groups, run reference and trial. Evidence for each: a
program that uses the class runs and resumes at the new target, and the
class's own ledger, where it has one, is unchanged.

### Phase 5: Parallel Map

Entry: Phase 3, and a workflow that needs it. The best-of-N workflow of the
single-call comparison is one: its four implementers run in sequence.

| Milestone | Evidence |
| --- | --- |
| `par-map` in the closed program and the evaluator | Four items, two at a time: the result list is in input order whatever the order of completion |
| Identity by item index | Resume after two of four items committed runs the other two only |
| A working directory per item | Two items that resolve to one directory are refused before launch |
| One writer for the memo | A run with eight items finishing together has eight committed records and no torn one |

### Phase 6: Migration

Entry: Phase 4 for the classes the maintained workflows use. Evidence: each
maintained workflow runs at the new target with the trace it has on the flat
route.

### Phase 7: Retirement

Entry: the owner's decision 8. The code that serves only older targets is
removed when no maintained workflow declares one.

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
