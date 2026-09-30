# Workflow Lisp Shared Defect Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Tasks 1 to 9 touch disjoint source files and may run in parallel, each in
> its own git worktree. Task 10 and the closeout run after they are merged.
> Track execution with the checkboxes below.

**Goal:** Repair the compiler and runtime defects that do not depend on the
choice of execution model, measure totality with a generated matrix, and
correct the documents that describe defects as limits.

**Architecture:** Each repair is made in the stage that owns the defect. No
new compiler pass and no new lowering route are added. Compiler changes that
alter what the language accepts apply from target 2.33. Runtime repairs apply
to every target.

**Tech Stack:** Python, Workflow Lisp typechecking, specialization, WCC
elaboration, the workflow executor and resume code, pytest/pytest-xdist,
command-backed deterministic procedures and stand-in providers.

**Spec:**
[decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md)
(sections 2, 7 and 12),
[core calculus middle-end](../design/workflow_lisp_core_calculus_middle_end.md)
(§9 elaboration totality, §12 compiler defects),
[pure-call composition](../design/workflow_lisp_pure_call_composition.md),
`specs/versioning.md`, `specs/io.md`, `specs/state.md`.

---

## Status, Authorities, And Scope

Status: approved for execution by the owner on 2026-09-29. The owner's
decisions:

- the repairs of the decision brief, section 7, compiler and runtime;
- compiler changes that alter acceptance amend target 2.33; no new target;
- a `defprompt` whose result is an applied generic union joins the 2.33
  contract, with tests;
- the documented limits of target 2.33 are relabeled as known defects;
- the Design Delta family is marked deprecated, apart from its reusable
  library procedures.

Decisions added on 2026-09-29, after the reviews of Tasks 8 and 9:

- resume follows one rule: an effect without a committed result runs again,
  and a diagnostic records it; a command that must not be repeated declares
  that, and resume stops at it (Task 11);
- one run at a time in a workspace: a second run is refused at start; no
  persisted path format changes (Task 12);
- a result path may not pass through a symbolic link, inside the workspace or
  outside it;
- an internal exception raised after typecheck is reported, in one place, as
  a compiler-defect diagnostic with a code and the authored form (Task 13);
- a name bound inside a hoisted expression no longer captures the same name
  outside it. This corrects a silent wrong value and applies to every target;
  it is the one exception to the rule that older targets do not change
  (Task 5);
- a run that supervises another run lives in its own workspace, observes the
  other's workspace by path, and resumes it there (Task 14).

Decisions added on 2026-09-29, after the third review round:

- only Critical findings block the merge: a silent wrong value, a loss of
  data, or an effect outside the workspace. A failing test is always
  repaired. Important and Minor findings are recorded as known defects, each
  with a test that pins it, and go to the follow-up list;
- the two silent wrong values of Task 15 are corrected at every target;
- Task 16 does not block the merge: it lands from its own branch after its
  review. Task 8 merges as it is;
- a workspace refusal exits 2 in `run`, `resume` and `trial`;
- at 2.33 the `match` node keeps the authored subject outside the case of
  Task 3, step 3; from 2.34 it carries the typed subject always;
- whether a copy of a rejected attempt's result is kept is decided on the
  cost report of Task 16.

Out of scope:

- the feasibility spike of the decision brief, section 10. It gets its own
  plan after Tasks 1 to 5 are merged;
- repairs that serve only the flat lowering route: references emitted by
  lowering for pure `match` arms (brief case d), the variant proof of case f,
  a producing step for pure unions, direct loop lowering, and deletion of the
  older lowerers. Cases d and f stay known defects;
- any change to `std/improve.orc` or to the shipped example.

## Global Constraints

- Targets up to 2.32 accept and lower exactly what they do at `7984b51e`.
  Evidence is byte identity of every build artifact at one fixed path with
  `PYTHONHASHSEED=0`, for `workflows/examples/review_revise_design_docs.orc`
  (2.23), `workflows/examples/kiss_backlog_item.orc` (2.14),
  `experiments/orc_vs_single_call/workflows/best_of_n.orc` and
  `reviewed_change.orc` (2.28), and the same diagnostic as at the base for a
  copy of each new test program retargeted to 2.32.
- Programs at 2.33 that compile at `7984b51e` keep their lowered output, step
  identities and checkpoint digests, unless the task says otherwise and names
  the program.
- A compiler change that alters acceptance is gated on "target 2.33 or newer"
  through one predicate in `orchestrator/workflow_lisp/syntax.py` named for
  the target. Do not reuse `target_dsl_supports_generic_unions` for a repair
  that is not about generic unions.
- Runtime repairs (Tasks 7 to 9) apply to every target.
- Tests assert behavior: values, ordered command logs, diagnostics by code and
  location, state contents. No test asserts prompt text. Tests run programs
  through the public run entry (`run_workflow`, `resume_workflow`, or the
  CLI), not through a helper that skips run-start validation.
- Each task creates its own test module. Only the task named below edits an
  existing test module.
- Documents are edited by Task 10 only. Every other task lists in its report
  the statements that its change makes true or false.
- New modules stay under 500 lines and new functions under cyclomatic
  complexity 12.
- Commit by pathspec. Commit messages carry no tool or assistant attribution.

## Review Focus

1. A wrapper that declares `:effects ()` around an imported effectful
   procedure compiles at 2.32 exactly as before, and at 2.33 is rejected with
   a diagnostic that names the missing effect. Task 2 tests both.
2. A result file left by an earlier iteration, an earlier run, or an
   interrupted call is never read as the result of a new call. Task 8 tests
   each of the three.
3. Resume after a command exited with a failure runs that command again. An
   effect whose completion is unknown still fails closed. Task 9 tests both.
4. A matrix cell that typechecks and then fails is a test failure or a strict
   `xfail` naming its defect. It is never skipped. Task 1 asserts that no
   cell is unclassified.
5. `--dry-run` with the replay index does not reject a program that runs
   today, runs no effect, and writes no run state. Task 7 tests all three.

## Baseline Check

Before any task, from the worktree root:

```bash
pytest -q -p no:cacheprovider --basetemp=/dev/shm/repairs-base \
  tests/test_workflow_lisp_improve_stdlib.py \
  tests/test_workflow_lisp_improve_example_e2e.py \
  tests/test_workflow_lisp_generic_unions.py \
  tests/test_workflow_lisp_generic_unions_runtime.py \
  tests/test_workflow_lisp_generic_union_provider_results.py \
  tests/test_workflow_lisp_union_record_field_targets.py
```

Expected at `7984b51e`: 137 passed. Record the count.

---

## M. Measurement

### Task 1: Totality Matrix

- [x] Complete

**Read/trace:** `tests/test_workflow_lisp_improve_stdlib.py` and
`tests/workflow_lisp_improve_stdlib_sources.py` (command-backed procedures,
command boundary files, the public run helper),
`docs/design/workflow_lisp_core_calculus_middle_end.md` §9 and §12.
**Create:** `tests/test_workflow_lisp_totality_matrix.py`,
`tests/workflow_lisp_totality_matrix_sources.py`.

1. Generate one program per cell at target 2.33 from these value forms and
   positions.
   Forms: literal; record constructor; variant constructor of a plain union;
   variant constructor of an applied generic union; field access on a bound
   record; call to a `defun`; call to an inline `defproc` with no effects;
   call to a command-backed `defproc`; call to a local wrapper around an
   imported command-backed `defproc`; call to a generic helper that takes
   `proc-ref` hooks; pure `match` expression.
   Positions: `let*` binding; `match` subject; record field; variant field;
   `loop-state` field under `continue`; `done` value; `:on-exhausted` value;
   procedure argument; `match` arm result; workflow tail.
   Skip a cell only where the form's type cannot occupy the position; list
   those cells in the sources module with the reason.
2. Classify each cell by running it through the public run entry:
   - **rule**: typecheck rejects it. The test asserts the diagnostic code and
     that the code belongs to a declared set of restriction codes, such as
     `effect_not_permitted`;
   - **working**: it compiles, runs with command-backed effects, and returns
     the expected value with the expected ordered command log;
   - **known defect**: it typechecks and then fails. Mark it strict `xfail`
     with the case letter of the decision brief, or a new short name when no
     case covers it.
3. Assert that every generated cell has exactly one classification.
4. Print the three counts in the test output and record them in the closeout
   of this plan.
5. Run `pytest --collect-only` on the module, then the module.

## C. Compiler

### Task 2: Effect Inference Includes Imported Procedures

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/compiler.py`
(`_infer_stage3_effect_summaries`, and the map rebuilt from local procedures
near line 5026), `orchestrator/workflow_lisp/effects.py`,
`orchestrator/workflow_lisp/typecheck_effects.py`,
`orchestrator/workflow_lisp/modules.py` (what an importer receives about an
imported procedure), `orchestrator/workflow_lisp/functions.py`
(`normalize_resolved_inline_procedure_calls`, which inlines a procedure it
believes has no effects).
**Update:** `compiler.py` and the owners traced above;
`tests/test_workflow_lisp_improve_stdlib.py` (the source used by
`test_review_hook_wrapping_an_imported_procedure_runs_to_exhaustion`, whose
wrapper declares `:effects ()`).
**Create:** `tests/test_workflow_lisp_imported_effects.py`.

1. Write failing tests at 2.33:
   - a local procedure that wraps an imported command-backed procedure has
     that command in its transitive effect summary;
   - the wrapper's result works as a `match` subject and when bound with
     `let*`, and both forms return the same value and command log;
   - a wrapper that declares `:effects ()` is rejected with the existing
     declared-versus-inferred diagnostic, which names the missing effect;
   - a hook imported from another module and passed by `proc-ref` to
     `improve` appears in the transitive effects of the specialized helper.
2. Write the 2.32 controls: each source retargeted to 2.32 gives the result
   it gives at `7984b51e`.
3. Implement: the effect map used by the second typecheck fixpoint and by the
   inline normalizer includes imported procedures.
4. Correct the wrapper in the existing improve test so that it declares its
   effect. Its assertions do not change.
5. Report: which statements in the design (§7), the drafting guide and the
   lessons guide about imported hooks losing their effects are now false.

### Task 3: `match` Keeps Its Typechecked Subject

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/typecheck_proofs.py`
(`typecheck_match_expr`, line 325),
`orchestrator/workflow_lisp/procedure_specialization.py` (proc-ref discovery
near line 1237), `orchestrator/workflow_lisp/procedure_refs.py` (line 203).
**Update:** `typecheck_proofs.py`.
**Create:** `tests/test_workflow_lisp_match_subject_calls.py`.

1. Write failing tests at 2.33: a call to `improve` used directly as a
   `match` subject compiles and runs, and returns the same value and command
   log as the form bound with `let*`, for APPROVED, BLOCKED and EXHAUSTED; the
   same for a second generic helper over an unrelated generic union.
2. Write the 2.32 control for a non-generic helper with `proc-ref` hooks.
3. Implement: the typed `match` node carries the typechecked subject where
   a generic signature declares a hook that depends on a type parameter. In
   every other case target 2.33 keeps the authored subject, so that programs
   that compiled at the base keep their step and checkpoint identities. The
   typed subject is carried in every case from target 2.34 (owner's decision
   of 2026-09-29, after the third review).
4. Check whether other typecheck handlers discard the typechecked form of a
   child. Report each one found; repair it only if a test of this task needs
   it.

### Task 4: Inlining Substitutes Specialized Types

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/functions.py`
(`normalize_resolved_inline_procedure_calls`, line 846),
`orchestrator/workflow_lisp/compiler.py` (the call near line 2954 and the
second fixpoint near 2975), `orchestrator/workflow_lisp/generic_unions.py`
(line 395), `orchestrator/workflow_lisp/type_env.py`
(`type_env_with_type_params`),
`docs/design/workflow_lisp_pure_call_composition.md` (a selected body is
normalized under its defining-module environment before it is transplanted).
**Update:** `functions.py` and the owners traced above.
**Create:** `tests/test_workflow_lisp_generic_pure_constructors.py`.

1. Write failing tests at 2.33: a generic procedure with no effects that
   constructs an applied generic union over its own type parameter compiles
   and runs when called from its own module, when imported, and when it calls
   a second generic procedure of the same kind.
2. Implement: the copied body carries the specialized types, or is resolved
   under the defining module's environment. Do not skip inlining for generic
   procedures unless substitution proves impossible; if so, report why.
3. Byte identity for the shipped example and for `std/improve` callers in
   `tests/test_workflow_lisp_improve_stdlib.py`.

### Task 5: The Elaborator Accepts Bound Prefixes In `loop-state` Fields And `match` Subjects

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/wcc/elaborate.py`
(`_elaborate_expr_to_value`, which returns prefix bindings and a value;
`_elaborate_atomic_value`, which raises on a prefix, near line 5257; the
`match` subject list near line 3184; `loop-state` passed through near line
2642; `continue` near line 1598), `orchestrator/workflow_lisp/wcc/anf.py`,
`orchestrator/workflow_lisp/lowering/control_loops.py` (line 1808),
`orchestrator/workflow_lisp/lowering/pure_projection.py` (line 1020).
**Update:** `wcc/elaborate.py`.
**Create:** `tests/test_workflow_lisp_elaborated_prefixes.py`.

1. Write failing tests at 2.33:
   - an effectful call written inside `(loop-state :like state :current
     <call>)` under `continue` compiles and runs, with the value and the
     ordered command log of the form bound with `let*`;
   - an effectful call as a `match` subject, in the shapes that raise
     `unsupported nested WCC M2 prefix`, compiles and runs;
   - effects in one expression run once each, left to right.
2. Write the 2.32 controls.
3. Implement in the elaborator. Do not add a pass before it.
4. Byte identity: every 2.33 program that compiles at `7984b51e` keeps its
   step identities. New generated names appear only in programs that did not
   compile before.
5. If a shape still fails because a union has no producing step, do not
   repair it here. Report it with its program; it belongs to the architecture
   decision.

### Task 6: `defprompt` Results Of An Applied Generic Union

- [x] Complete

**Read/trace:** `tests/test_workflow_lisp_generic_union_provider_results.py`
(the pattern to follow), `orchestrator/contracts/output_contract.py`,
`orchestrator/workflow_lisp/contracts.py`.
**Create:** `tests/test_workflow_lisp_generic_union_defprompt_results.py`.

1. Write tests at 2.33 for a `defprompt` whose declared result is an applied
   generic union, through the provider boundary with a stand-in provider: a
   valid payload reaches the caller; each of
   `variant_discriminant_invalid`, `variant_required_field_missing`,
   `variant_forbidden_field_present` and `variant_field_type_invalid` fails
   at the boundary, and no later step is recorded in the run state; no type
   variable appears in the contract the provider receives.
2. Write the 2.32 control: rejected with `generic_union_requires_dsl_2_33`
   at the declaration, line and column.
3. If a test fails, repair the owner. If all pass, the task is tests only.
4. Confirm by mutation that each violation test fails when its validation is
   disabled. Revert each mutation.

## X. Runtime

### Task 7: `--dry-run` Builds The Pure-Result Replay Index

- [x] Complete

**Read/trace:** `orchestrator/cli/commands/run.py` (the early return for
`--dry-run` near line 586), `orchestrator/workflow/pure_result_replay.py`
(`PureReplayRuntime`, line 436; `derive_pure_result_replay_index`, line
1678), `orchestrator/workflow/executor.py` (the audit near line 5102).
**Update:** `cli/commands/run.py`, and `pure_result_replay.py` only if the
index cannot be derived without a runtime object.
**Create:** `tests/test_workflow_dry_run_replay_index.py`.

1. Write failing tests: a pure tail `match` over a command union result whose
   arms build a record, and the same over a loop union result, fail
   `--dry-run` with exit 2 and the diagnostic the run start gives today.
2. Write tests that must keep passing: `--dry-run` exits 0 for the shipped
   example, for the callers in `tests/test_workflow_lisp_improve_stdlib.py`,
   and for the two workflows under `experiments/orc_vs_single_call/`.
3. Write tests that `--dry-run` runs no command and creates no run directory.
4. Implement.

### Task 8: A Result File Is Absent Before Every Call

- [x] Complete

**Read/trace:** `orchestrator/workflow/executor.py`
(`_prepare_runtime_output_bundle_parent`, line 7394; where
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is set; where an entry workflow's bundle
path is bound), `orchestrator/contracts/output_contract.py` (line 553),
`orchestrator/workflow_lisp/lexical_checkpoints.py` (what is digested again
on resume), `specs/io.md` (supervision and peer-group calls already require
the file to be absent).
**Update:** `executor.py`, `specs/io.md`.
**Create:** `tests/test_workflow_result_file_freshness.py`.

1. Trace every reader of a result file after its result is committed. Record
   them in the report.
2. Choose by this rule: if no reader needs the file after commit, the runtime
   removes an existing file before it starts the call. If a reader does, the
   path names the call (iteration and visit) and the file of a committed call
   is left in place. State the choice and its reason in the report.
3. Write failing tests with command-backed steps and with a stand-in
   provider:
   - a step that writes its result only in iteration 1 fails in iteration 2
     with the existing missing-result contract violation;
   - a second run does not read a file left by the first run;
   - a call interrupted after it wrote a partial or complete file is not
     satisfied by that file on resume;
   - a loop of three iterations that writes a result each time still passes.
4. Implement for every target.
5. Add the rule to `specs/io.md`, next to the rule for supervision calls.

### Task 9: Resume After A Known Failure

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
(the policy branch near lines 1260 to 1290),
`docs/design/workflow_lisp_lexical_execution_checkpoints.md` (the pending
effect rule is scoped to an effect that started and whose completion is
unknown), `orchestrator/workflow/executor.py` (line 5102),
`orchestrator/workflow/resume_planner.py`.
**Update:** `lexical_checkpoint_restore.py`.
**Create:** `tests/test_workflow_resume_after_known_failure.py`.

1. Write failing tests: a command exits non-zero, the run fails, the cause is
   corrected, and `resume` runs that command again and completes; no
   committed effect before it runs again.
2. Write tests that must keep passing: an effect interrupted with its
   completion unknown and a policy that forbids reuse fails closed with
   `lexical_restore_pending_effect_unsafe`.
3. Implement: a step whose state records a completed attempt with a failure
   is not a pending effect.
4. If resume then stops at `pure_result_replay_unavailable`, report the
   program. Do not repair replay in this task.

### Task 11: One Rule For Resume Of An Effect Without A Committed Result

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`,
`orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py` (the
prior-boundary fallback, lines 684 to 795),
`orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py`, the
command boundaries file format, `specs/state.md`, `specs/providers.md` (the
rule for an interrupted provider visit), the review of Task 9.
**Update:** those owners; the command boundary declaration; `specs/state.md`.
**Create:** tests in `tests/test_workflow_resume_after_known_failure.py` and,
if that module would pass 500 lines, a second module.

The rule: on resume, an effect that has no committed result runs again. That
covers a step whose last attempt failed and a step that was interrupted. The
run state records a diagnostic for each such rerun, as it does for an
interrupted provider visit. A command boundary may declare that the command
must not be repeated; resume then stops at it with
`lexical_restore_pending_effect_unsafe`, located at the step. An effect with
a committed result never runs again.

1. Write failing tests:
   - an interrupted command that is not the first step, and one that is,
     both run again on resume, each with one recorded diagnostic;
   - a command declared not repeatable stops resume, whether it failed or was
     interrupted, with the code and the step's source location;
   - a failed workflow call resumes inside the callee: its committed inner
     effects do not run again, its failed inner effect does;
   - an interrupted provider visit behaves as `specs/providers.md` states
     today.
2. Count command invocations in every test. No committed effect runs twice.
3. Implement. Remove the condition Task 9 added where the rule replaces it.
4. State the rule in `specs/state.md`, and the declaration in the document
   that owns command boundaries.

### Task 12: One Run At A Time In A Workspace

- [x] Complete

**Read/trace:** how a run directory is created and locked today
(`orchestrator/state.py`, `tests/test_run_lock.py`), `specs/state.md`,
`specs/cli.md`.
**Update:** the run start and resume entry, `specs/cli.md`.
**Create:** `tests/test_workspace_run_lock.py`.

1. Write failing tests: while one run is active in a workspace, a second
   `run` and a `resume` of another run are refused at start with a coded
   diagnostic that names the active run; after the first run ends, by
   completion, failure or kill, the workspace is free; `--dry-run` takes no
   lock; a lock left by a process that no longer exists does not block.
2. Implement with a lock the operating system releases when the process
   dies.
3. Turn the strict xfail of Task 8 for two concurrent runs into a test of
   the refusal.
4. State the rule in `specs/cli.md`.

### Task 13: Internal Failures After Typecheck Are Compiler-Defect Diagnostics

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/compiler.py` (where typecheck
ends and elaboration and lowering start), `orchestrator/workflow_lisp/wcc/`,
`orchestrator/workflow_lisp/lowering/`,
`orchestrator/workflow_lisp/diagnostics.py`,
`docs/design/workflow_lisp_core_calculus_middle_end.md` §12,
`orchestrator/cli/commands/run.py` (how a compile failure reaches the user).
**Update:** the stage boundary in `compiler.py`; `diagnostics.py`.
**Create:** `tests/test_workflow_lisp_compiler_defect_diagnostics.py`.

1. Write failing tests with programs that end in a Python exception today:
   the totality matrix cells whose failure is a `TypeError`, a `KeyError` or
   a `ValueError`. Each must end with exit 2 and one diagnostic with the code
   `compiler_defect`, the statement that the program passed typecheck, the
   stage that failed, the internal message, and the source location of the
   form that was being elaborated or lowered.
2. Implement in one place: the boundary after typecheck converts an
   exception that is not a diagnostic. The form comes from the node the stage
   was handling; where a stage does not track it, from the enclosing
   procedure or workflow.
3. A diagnostic raised by a stage keeps its own code. The conversion never
   hides one.
4. Do not repair the defects. The totality matrix keeps each cell as a known
   defect and asserts the new code.

### Task 14: The Watchdog Runs In Its Own Workspace

- [x] Complete

Depends on Task 12.

**Read/trace:** `workflows/library/generic_run_watchdog/` (the workflow, its
scripts `probe_orchestrator_run.py` and the others, its prompts, in
particular `repair_run_failure.md`), its inputs and its row in
`workflows/README.md`, `scripts/watch_workflow_usage_limit.sh`,
`tests/test_workflow_lisp_generic_run_watchdog.py`, the review of Task 12.
**Update:** the watchdog workflow, its scripts and prompts,
`workflows/README.md`, `specs/cli.md`.
**Create:** tests in `tests/test_workflow_lisp_generic_run_watchdog.py` or a
new module beside it.

1. The watchdog takes the target's workspace as an input, a path. Its probe
   reads the target's run state from that path and no longer from the
   current directory. The watchdog's own run state and result files are in
   the watchdog's workspace.
2. Write failing tests through the public run entry, with stand-in
   providers: while a target run is active in workspace T, a watchdog started
   in workspace W observes it and reports it as running; with a stalled or
   failed target, the watchdog's repair step resumes the target with T as the
   working directory, and the target completes; a watchdog started in T while
   the target is active is refused with `workspace_run_already_active`.
3. The watchdog cannot start today: its compiled program is rejected by the
   pure-result replay index at `watchdog.orc:102`. Rewrite the rejected form
   so that the workflow starts, without changing what it does, and without
   repairing the replay index. If no such form exists, stop and report the
   forms tried with their diagnostics.
4. `scripts/watch_workflow_usage_limit.sh` sends `resume` once. Make it
   report a refusal by the workspace lock and retry after the active run
   ends, or report why it cannot.
5. State in `specs/cli.md` that a run started from inside another run in the
   same workspace is refused, and in `workflows/README.md` how to launch the
   watchdog.

### Task 15: A Pure Binding Keeps Its Source Scope Where It Is Used

- [x] Complete

Depends on Task 5. Found by the second fix round of Task 5. The owner's
decision on capture (a silent wrong value is corrected at every target) is
read as covering these two defects, because they are of the same class. The
owner may reverse that reading.

**Read/trace:** `orchestrator/workflow_lisp/wcc/defunctionalize.py`
(`_frontend_expr_from_wcc_value_with_env` and its environment),
`orchestrator/workflow_lisp/wcc/lower.py`,
`orchestrator/workflow_lisp/wcc/hygiene.py`, the expansion of `defun` calls
that targets below 2.30 use, the second fix report of Task 5 ("Found and not
repaired", items 2 and 3).
**Update:** the owner of each defect.
**Create:** tests in `tests/test_workflow_lisp_use_site_scope.py`.

The defects:

- Lowering substitutes a pure binding where it is used and resolves its free
  names there. `(let* ((b 1) (v (+ b 1))) (let* ((b 5)) v))` returns 6 at
  every target. Lexical scope gives 2.
- Below target 2.30 a `defun` argument is evaluated inside the scope of the
  callee's parameters. With `(defun select-second ((x Int) (y Int)) -> Int y)`
  and `x` bound to 9, `(select-second 2 x)` returns 2. Lexical scope gives 9.

1. Write failing tests through the public run entry. Each asserts the value
   lexical scope gives and the ordered command log, at the oldest target
   that accepts the program, at 2.32 and at 2.33. Cover the pure binding
   used in: a rebinding `let*`, a record field, a condition, a `match` arm,
   a loop body, an argument of an effect call, and with an effect between
   the definition and the use. Cover the `defun` argument with one and with
   two shadowed parameters, and with a nested `defun` call as the argument.
2. Repair each defect in the stage that owns it. A binding's free names
   resolve in the scope of its definition.
3. Sweep every `.orc` program under `workflows/`, at one fixed path with
   `PYTHONHASHSEED=0`, at the base of this task and at its head. List each
   program whose build changes and the value that changed.
4. Programs with no shadowed name build byte-identical artifacts at every
   target.
5. Give the sentence for `specs/versioning.md`; Task 10 writes it.

### Task 16: One Owner, Rooted At The Workspace Descriptor, For Every Result File

- [ ] Complete

Depends on Task 8. Three review rounds of Task 8 each found another site
that reaches the workspace by path and can be led outside it when a
directory is replaced by a symbolic link during a run: the removal, then the
removal under a replaced root, then the read after the call and the creation
of one provider kind's bundle. The cause is that result files are addressed
by path at many sites. This task removes the cause.

**Read/trace:** the third review of Task 8; `orchestrator/workflow/executor.py`
(the no-follow walk of the second fix round, the read after the call,
`_materialize_omp_output_bundle`); `orchestrator/contracts/output_contract.py`;
`orchestrator/cli/commands/resume.py`.
**Update:** those owners; `specs/io.md`; `specs/state.md`.
**Create:** `orchestrator/workflow/workspace_files.py`; tests in
`tests/test_workflow_result_path_confinement.py`.

1. Inventory every site that creates, reads, validates, clears or checks a
   result bundle file, an expected output file or a file under the state
   root, and whether it goes by path or by descriptor.
2. Write failing tests: the root replaced between the clearing and the read;
   an ancestor replaced before a bundle is created; `resume` with a linked
   `.orchestrate`; a phased-delivery refusal inside a call frame carries its
   location.
3. Implement one owner that performs every such operation from the root
   descriptor the executor opened once. No second walk.
4. Report where a copy of a rejected attempt's result could be kept. The
   owner decides whether to keep it.
5. A workspace with no symbolic link behaves as before: equal build
   artifacts and run results for three shipped workflows.

## D. Documents

### Task 10: Correct The Documents

- [x] Complete

**Read:** the reports of Tasks 1 to 9; `docs/index.md`;
`docs/design/workflow_lisp_core_calculus_middle_end.md` §12.
**Update:** `specs/versioning.md`, `specs/index.md`,
`docs/design/workflow_lisp_composition_first.md`,
`docs/design/workflow_lisp_parametric_type_system.md`,
`docs/lisp_workflow_drafting_guide.md`,
`docs/orc_workflow_design_lessons.md`, `docs/capability_status_matrix.md`,
`docs/index.md`, `workflows/README.md`,
`docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`.

1. `specs/versioning.md`, target 2.33: state what 2.33 accepts after Tasks 2
   to 6, including `defprompt` results of an applied generic union.
2. Composition-first design §11: retitle to known defects and rules. A rule
   is a restriction the typechecker reports by name. A defect is a failure
   after typecheck. Remove the entries that Tasks 2 to 5 and 7 repaired. Give
   each remaining defect its cause and a link to the decision brief.
3. Drafting guide and lessons guide: remove the rows for repaired cases;
   label the rest as rule or defect.
4. Design Delta: in `docs/index.md`, the capability matrix, the drafting
   guide and `workflows/README.md`, say that the family is deprecated apart
   from its reusable library procedures, and name the recent examples as the
   starting point. Delete no file. Check the route-readiness registry and
   the routing tests before changing a label they pin.
5. Roadmap: close the follow-up entries that were repaired; record the spike
   as the next selected work.
6. Run the documentation test selectors and check every link edited.

---

## Closeout And Consequent Actions

Closed on 2026-09-29, except Task 16, which lands from its own branch after
its review (owner's decision).

- [x] Task branches merged into the integration branch. Totality matrix:
  12 rule, 68 working, 34 known defect, 6 skipped, of 120 cells. At the
  start of the plan the matrix did not exist; its first measurement gave
  27 known defects under a coarser check, and 34 when each cell had to
  show the failure and the stage recorded for it.
- [x] Byte identity for older targets: shown per task, for shipped programs
  with no shadowed name. Artifacts of a program that uses a trial or a run
  reference hold a digest of the compiler's own code and differ after any
  change of the package; that field is excluded from the claim.
- [x] Full suite, 16 workers, at `7984b51e` and at the integration head.
  Baseline: 350 failed, 16,266 passed. Head: 351 failed, 16,772 passed,
  47 expected failures. No test fails at the head that passes at the
  baseline, apart from tests that are unstable under load and pass alone
  on both sides. The first run at the head found eight failures in two
  modules that no task had run; they were adaptations of tests to decided
  contracts and were repaired before the second run.
- [x] Public evidence: the whole-branch review ran ten sentences of the
  specifications as programs through the public entries, the three
  recommended examples with stand-in providers, and a run started at the
  base and resumed at the head.
- [x] Whole-branch review, by a reviewer of another model family: approved
  with notes, no Critical finding.
- [x] Merge to `main` by fast-forward; push.
- [x] Plan for the spike:
  [evaluated execution plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md).

Known defects left open, each pinned by a test or recorded in the
composition-first design, section 11:

- a value bound by `bind-proc` or captured by `let-proc` is resolved where
  the procedure is called, so a later binder of the defining body captures
  its names (a silent wrong value, present before this plan; no shipped
  program uses these forms);
- from 2.30, a `let-proc` capture of an effect result evaluates the effect
  again where the procedure is applied;
- the check of required provider parameters refuses at validation, at every
  target, a call that a run refused only when it reached it. The owner
  accepted this on 2026-09-29 as a second exception to the rule for older
  targets; `specs/versioning.md` states it;
- resume refuses an interrupted effect in a second call of one workflow and
  after a provider group;
- the replay index refuses pure bindings in a branch over the result of a
  call made in that branch.

What the plan showed about the cause. Name capture was repaired in four
rounds, and each review found another site, because lowering resolves names
in six separate environments. The 34 known-defect cells, the three separate
refusals that one search controller met, and those rounds have one cause:
a value exists at run time only as the output of a step. Repairing it is
the subject of the evaluated execution plan.
