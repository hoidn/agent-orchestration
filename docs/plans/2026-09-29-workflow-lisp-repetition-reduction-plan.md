# Workflow Lisp Repetition Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Tasks inside one phase that touch disjoint files may run in parallel, each
> in its own git worktree. Track execution with the checkboxes below.

**Goal:** Make `.orc` programs state each fact once: import shared
declarations, construct values from the expected type, infer effects, let
hooks capture their context, and bind provider options once.

**Architecture:** Every change is in declarations, the typechecker,
elaboration or provider configuration. No change depends on how a compiled
workflow is executed. Phase A changes no language rule. The language changes
enter together at one new target.

**Tech Stack:** Python, Workflow Lisp reader, typechecker, specialization and
elaboration, provider registry and shared validation, pytest/pytest-xdist,
command-backed deterministic procedures and stand-in providers.

**Spec:** [Writing Each Fact Once](../design/workflow_lisp_write_once.md)
(rules W0 to W5),
[repetition census](../reports/2026-09-29-workflow-lisp-repetition-census.md),
[effect ledger simplification](../design/workflow_lisp_effect_ledger_simplification.md),
[local ProcRef bindings](../design/workflow_lisp_let_proc_local_proc_refs.md).

---

## Status, Authorities, And Scope

Status: draft for the owner. Not approved. No task starts before the
decisions below are recorded.

Decisions needed before execution:

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | Which of the rules W0 to W5 are accepted | W0, W1, W2 and W4. W3 on the result of Task 4. W5 deferred under its own condition |
| 2 | The target that carries W1, W2, W3 and W4 | One new target, 2.34 |
| 3 | The module that owns declarations shared by a workflow family and unused by the standard library | One module per family under `workflows/library/`, named for the family |
| 4 | The adoption bar for W3 | The helper variant of `reviewed_change.orc` is at least 10 % shorter than the hand-written variant and keeps every behaviour |
| 5 | Where provider defaults are written | The provider externs file |
| 6 | Whether `improve` changes its signature in place | Yes. It has one caller, the shipped example |
| 7 | Who implements Phase B | The runtime owner, because the change is in provider configuration and shared validation |

Depends on: the
[shared defect repairs plan](2026-09-29-workflow-lisp-shared-defect-repairs-plan.md)
merged to `main`. Tasks 7 and 8 edit the typechecker handlers that plan
repaired.

Out of scope: the compiler defects recorded in the
[value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md);
moving older workflows to the new target; the Design Delta family.

## Global Constraints

- Older targets accept and lower exactly what they do at the commit each
  phase starts from. Evidence is byte identity of every build artifact at one
  fixed path with `PYTHONHASHSEED=0`, with the orchestrator package at one
  fixed path as well.
- A program at the new target that uses none of the new forms lowers to what
  it lowers to at 2.33.
- A new form lowers to exactly what its explicit equivalent lowers to.
- Every refusal has a diagnostic code and a source location.
- Tests assert behavior through the public run entry. No test asserts prompt
  text.
- New modules stay under 500 lines and new functions under cyclomatic
  complexity 12.
- No broad or full-suite test run while other agents are running. One full
  run at each phase closeout, alone, in tmux.
- Commit by pathspec. Commit messages carry no tool or assistant attribution.

## Review Focus

1. Importing a declaration in place of a local copy changes the qualified
   name of a type. A workflow's contracts, output schemas and checkpoint
   digests may name it. Task 1 compares them before and after, per workflow.
2. A constructor without its type name in a position with no expected type
   must be rejected with a located diagnostic, never resolved by a guess.
   Task 8 tests each position of design section 4.3.
3. A bare tag that two visible unions declare must resolve to the expected
   union and to no other. Task 8 tests it with three unions sharing one tag.
4. Passing the expected type through more forms must not change the type of
   any program that compiles today. Task 7 proves it on the corpus before any
   new form exists.
5. A binding's default must not apply to a call that sets the option, and a
   changed default must be seen by resume as a source change. Task 5 tests
   both.

## Baseline

Before Phase A, from the repository root:

```bash
python experiments/orc_repetition_census/declaration_repeats.py .
```

Expected at the census commit: 201 declarations, 61 repeats, 44 identical,
253 lines in repeats. Record the output.

---

## A. No Language Change

### Task 1: Import Declarations That Are Repeated With Identical Text

- [ ] Complete

**Read/trace:** the census, section 4.2; the export lists of
`orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`, `std/resource.orc`
and `std/context.orc`; how a build artifact names a type
(`orchestrator/workflow_lisp/normalized_type_descriptor.py`,
`orchestrator/workflow_lisp/contracts.py`).
**Update:** the corpus files under `workflows/examples/` and
`workflows/library/` that repeat a declaration with identical text.
**Create:** one module per family for declarations the standard library does
not own, as decision 3 records.

1. List every declaration that repeats with identical text, the module that
   will own it, and the files that will import it.
2. For each file, before editing: compile it and keep every build artifact,
   and run its existing tests.
3. Replace the local declaration by an import. Add the name to the owner's
   export list where it is missing.
4. After editing: compile and run the same tests. Report, per workflow, which
   artifacts changed and why. A change in a qualified type name is expected;
   a change in a field, a contract or a step is a defect.
5. Run `declaration_repeats.py` and record the counts.

### Task 2: Resolve Names Declared With Differing Text

- [ ] Complete

**Read/trace:** each declaration of `DesignDocPath`, `BlockerClass`,
`ReviewDecision`, and every other name the census reports as repeated and not
identical.
**Update:** the files that declare them.

1. For each name, write a table of its definitions: file, fields or values,
   and what differs.
2. Apply this rule. Where one definition contains the others, keep it, export
   it from its owner and import it. Where two definitions mean different
   things, rename the narrower one for what it means.
3. Where neither applies, stop and report the name with its table. Do not
   choose.
4. Verify as in Task 1, steps 2 and 4.

### Task 3: Lint For A Declaration That Repeats An Importable One

- [ ] Complete

**Read/trace:** `orchestrator/workflow_lisp/linting.py`, the existing lint
codes and how `--dry-run` prints them.
**Update:** `linting.py`.
**Create:** `tests/test_workflow_lisp_lint_declaration_repeats.py`.

1. Write failing tests: a module that declares a path family identical to one
   `std/phase` exports gets the warning `declaration_repeats_importable`,
   located at the declaration, naming the module to import from; a module
   that declares a record of the same name and different fields gets none; a
   module that imports the type gets none.
2. Implement. Compare definitions, not text.
3. Run the lint over the corpus. After Tasks 1 and 2 it reports nothing.

### Task 4: Measure W3 With The Language As It Is

- [ ] Complete

**Read/trace:** `experiments/orc_repetition_census/variants/`, the
`let-proc` and `bind-proc` contracts,
`orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`.
**Create:** variants under `experiments/orc_repetition_census/variants/`,
stored as `.orc.txt`; an addendum to the census report.

1. Write a local copy of `improve` without `inputs I`, in a scratch module.
2. Rewrite `reviewed_change.orc` against it, with hooks that take their
   context through `bind-proc` or `let-proc` as the language allows today.
   Keep every behaviour of the original; where one cannot be kept, record the
   diagnostic.
3. Count lines with `count_lines.py`, in the census's categories.
4. Write a second variant as the design's section 6.3 would allow it, and
   count it. It will not compile; mark it so.
5. Report both counts against the hand-written variant (92 lines). State
   whether each meets the bar of decision 4.

## B. Provider Options Bound Once

### Task 5: Defaults On A Provider Binding

- [ ] Complete

**Read/trace:** how the provider externs file is read
(`orchestrator/workflow_lisp/build_manifest_io.py`,
`orchestrator/workflow_lisp/build_artifacts.py`), how call options reach a
provider (`orchestrator/providers/registry.py`, call policy bindings), the
diagnostic `provider_parameters_missing`, `specs/providers.md`.
**Update:** the externs reader, shared validation, `specs/providers.md`.
**Create:** `tests/test_workflow_lisp_provider_binding_defaults.py`.

1. Write failing tests, with stand-in providers:
   - a binding written as an object supplies `model`, `effort` and
     `timeout_sec` to a call that sets none;
   - a call that sets an option overrides the binding for that option only;
   - a binding written as a string behaves as today;
   - a required parameter that the call, the binding and the template all
     omit is rejected at compile time, located at the call;
   - the build artifacts of a workflow are identical whether an option is on
     the call or on the binding;
   - resume after the binding's default changed is refused as a source
     change;
   - one supervision call, one peer-group call and one adjudication call take
     their options from the binding.
2. Implement.
3. State the rule and the order of precedence in `specs/providers.md`.
4. Move the repeated options of
   `experiments/orc_vs_single_call/workflows/*.orc` to their providers files
   and show that their build artifacts do not change.

## C. Construction From The Expected Type

### Task 6: Register The New Target

- [ ] Complete

**Read/trace:** how target 2.33 was registered: `specs/versioning.md`,
`orchestrator/workflow_lisp/syntax.py`,
`orchestrator/workflow/validation.py`, `tests/test_workflow_lisp_target_233.py`.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_target_234.py`.

1. Write failing tests: a module at the new target that uses no new form
   compiles, and lowers to what it lowers to at 2.33.
2. Register the target and one predicate named for it.

### Task 7: Pass The Expected Type Through Every Position Of Design Section 4.2

- [ ] Complete

**Read/trace:** `orchestrator/workflow_lisp/typecheck_dispatch.py`
(`typecheck_expression`, `_typecheck` and its `recurse`, which resets the
expected type), `typecheck_structural_values.py` (the empty `(list)`),
`typecheck_proofs.py` (`match`, `if`, `cond`), `typecheck_loop_recur.py`,
`loop_state.py`, `procedure_typecheck.py`, `workflows.py`.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_expected_type_positions.py`.

1. Write failing tests at the new target with the one form that already uses
   an expected type, the empty `(list)`: it compiles in a `let*` body, a
   `with-phase` body, as a `done` value, as an `:on-exhausted` value and as a
   `loop-state` field, where a declaration fixes the type. It is still
   rejected with `list_empty_type_context_required` as a `let*` binding.
2. Write the controls at 2.33: each of those programs is rejected as today.
3. Implement. A loop takes its expected type from its position and passes it
   to `done` and `:on-exhausted`.
4. Compile the whole corpus at its own targets, and a copy of each 2.33
   program retargeted to the new target. Every build artifact is identical to
   the artifact before this task.

### Task 8: Constructors Without A Type Name

- [ ] Complete

**Read/trace:** `orchestrator/workflow_lisp/expressions.py`
(`_elaborate_record`, `_elaborate_variant`, and `_trial_record_sections`),
`typecheck_dispatch.py` (the record and variant branches),
`typecheck_pure_ops.py` (a bare tag resolved against a union),
`orchestrator/workflow_lisp/form_registry.py`.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_expected_type_constructors.py`.

1. Write failing tests at the new target:
   - `(record :k v)` and `(variant V :k v)` compile at each position of
     design section 4.2 and run to the value the explicit form gives;
   - each builds artifacts identical to the explicit form;
   - at each position of section 4.3 the form is rejected with
     `constructor_type_context_required`, located at the constructor;
   - with three visible unions that declare one tag, the tag resolves to the
     expected union;
   - a tag the expected union does not declare is rejected with
     `constructor_variant_not_in_expected_union`;
   - a generic procedure whose body writes `(variant V …)`, imported and
     inlined in a module that does not import the union, compiles and runs;
   - `(record :key value)` inside a `trial` section behaves as today.
2. Write the controls at 2.33: both forms are parse errors, as today.
3. Implement.
4. Rewrite `std/improve.orc` with constructors that omit
   `Improvement[S F B]`. Its callers' build artifacts are identical.

### Task 9: Documents For Phases A To C

- [ ] Complete

**Update:** `specs/versioning.md`, `specs/providers.md`,
`docs/lisp_workflow_drafting_guide.md`,
`docs/design/workflow_lisp_frontend_specification.md`,
`docs/design/workflow_lisp_parametric_type_system.md` (the rule that a
constructor names its type), `docs/orc_workflow_design_lessons.md`,
`docs/capability_status_matrix.md`, `docs/index.md`.

1. State the new target's contract.
2. Replace the rule that a constructor names its type by the rule of design
   section 4, in the documents that state it.
3. Add W0 to the drafting guide: import before declaring, with the lint's
   name.
4. Run the documentation test selectors and check every link edited.

## D. Effects Inferred

### Task 10: Plan The Effect Ledger Simplification

- [ ] Complete

The design exists and lists its own prerequisites. This task writes its plan.

**Read:** `docs/design/workflow_lisp_effect_ledger_simplification.md`,
`docs/reports/2026-09-08-workflow-lisp-effect-tracking-audit.md`, roadmap
entry EL-1.
**Create:** `docs/plans/<date>-workflow-lisp-effect-inference-plan.md`.

1. Record the target of decision 2 as the design's target.
2. Turn each prerequisite of the design (defining-scope resolution of effect
   subjects, carriage of the restriction's origin, mixed-target linking,
   editor projection) into a task with its fixture.
3. Turn each acceptance lane of the design into a closeout item.

## E. Hooks That Capture Their Context

Phase E starts only if Task 4 reports that the second variant meets the bar
of decision 4.

### Task 11: Several Bindings In One `let-proc`

- [ ] Complete

**Read/trace:** `docs/design/workflow_lisp_let_proc_local_proc_refs.md`
(sections 9, 10, 12 and 13), the `let-proc` elaboration and its generated
procedures.
**Update:** the `let-proc` owners.
**Create:** `tests/test_workflow_lisp_let_proc_bindings.py`.

1. Write failing tests at the new target: two local procedures in one form,
   both passed by `proc-ref` to one helper, compile and run; a local
   procedure that names another of the same form, or itself, is rejected with
   a located diagnostic.
2. Implement. The generated procedures and their step identities for a form
   with one binding are what they are today.

### Task 12: Captures Inferred

- [ ] Complete

**Update:** the `let-proc` owners.
**Create:** tests in `tests/test_workflow_lisp_let_proc_bindings.py`.

1. Write failing tests: without `:captures`, a body that uses names of the
   enclosing scope compiles and runs like the form with the list written; a
   name bound both outside and as a parameter is the parameter; an authored
   list that omits a name the body uses is rejected, naming the name.
2. Implement. The build artifacts equal those of the explicit list.

### Task 13: A Local Procedure Takes Its Signature From The Expected Type

- [ ] Complete

**Read/trace:** `_infer_parametric_type_bindings` and
`_typecheck_parametric_procedure_call` in `procedure_typecheck.py`.
**Update:** those owners and the `let-proc` owners.
**Create:** `tests/test_workflow_lisp_local_hook_signatures.py`.

1. Write failing tests: a local procedure passed directly to a `ProcRef`
   parameter omits its parameter types and its return type; the callee's type
   parameters are bound from the other arguments and from the body; a local
   procedure whose body does not fit the expected type is rejected at the
   body.
2. Implement. Arguments that fix type parameters are checked first; local
   procedures are checked after, against the bound types.

### Task 14: `improve` Without `inputs`

- [ ] Complete

**Update:** `orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`,
`workflows/examples/improve_experiment_proposal.orc` and its tests,
`docs/design/workflow_lisp_composition_first.md`, the drafting guide's
section on `improve`.
**Create:** the measured helper variant of `reviewed_change.orc` as a test
program.

1. Change the signature as design section 6.4 gives it.
2. Rewrite the example with local hooks.
3. Run the example's tests through the public run and resume.
4. Count the helper variant of `reviewed_change.orc` and record the count
   against decision 4.

## F. Constraints That Bind

### Task 15: Deferred

W5 is planned when its condition in design section 8.4 holds.

---

## Closeout, Per Phase

- [ ] Run the census scripts and record the counts beside the baseline.
- [ ] Byte identity for older targets, as the global constraints state.
- [ ] Full suite in tmux, alone: `pytest -q -n 16 --dist=worksteal`, compared
  with the failure set of the commit the phase started from; no new
  failures.
- [ ] Public evidence, fresh output: compile, run and resume of one program
  per new form.
- [ ] Review of the phase by a reviewer of a model family other than the
  implementer's.
- [ ] Merge to `main` by fast-forward; push.

## Expected Result

Figures are taken from the census. Those marked estimated are not measured.

| Phase | Rule | Repetition removed |
| --- | --- | --- |
| A | W0 | Up to 253 lines of repeated declarations, 8.9 % of the corpus |
| B | W4 | The options of 20 calls; 9 lines in `reviewed_change.orc` |
| C | W1 | The type name at 76 of 105 constructor sites; 1,583 characters; no line |
| D | W2 | 27 lines of `:effects` clauses, and the edits they force when a helper changes |
| E | W3 | Estimated: one record, one constructor and the restated hook signatures per caller of a helper; about 20 lines in the measured workflow |
