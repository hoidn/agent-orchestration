# CF-1b Composition-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Keep one write-capable implementer active at a time for overlapping owners.
> Track execution with the checkboxes below.

**Goal:** Deliver first-order generic unions and a value-returning `improve`
helper at target 2.33, proven by a structured-value caller whose revised
candidate reaches a deterministic consumer through the helper's return value.

**Architecture:** Extend the existing type-expression, type-environment,
procedure-typecheck, specialization, and descriptor owners so that an applied
generic union becomes an ordinary concrete union before lowering. Add one
library module. No runtime type values, no new evaluator, no compiler branch
keyed to review names, no coordinator or history framework.

**Tech Stack:** Python, Workflow Lisp AST/typechecking/specialization/WCC and
shared executable validation, existing JSON contracts and run storage,
pytest/pytest-xdist, command-backed deterministic hooks.

---

## Status, Authorities, And Scope

Status: accepted for execution by the owner on 2026-09-28. The owner accepted
the type-system delta as the governing contract and assigned target **2.33**
to generic unions and `std/improve` together. Tasks 1–6 are implemented and
reviewed (2026-09-28); the SDD ledger records each task's evidence. Task 7
promotes the documentation; the closeout items below remain open.

Read `docs/index.md` and `docs/capability_status_matrix.md` first. Authorities:

- [Composition-first design](../design/workflow_lisp_composition_first.md)
  owns the interface, loop policy, boundaries, migration, feasibility
  obligations, and evidence requirements.
- [Parametric type system](../design/workflow_lisp_parametric_type_system.md#proposed-cf-1-first-order-generic-unions)
  owns generic-union application, argument binding, constructor identity,
  diagnostics, and the specialization pipeline.
- [Frontend specification](../design/workflow_lisp_frontend_specification.md)
  §13.1 and `specs/dsl.md` own loop/recur and exhaustion; `specs/versioning.md`
  owns target admission.
- [CF-1 roadmap section](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected)
  owns ordering and consequences. This plan is CF-1b only. CF-1c migration and
  CF-1d extensions need their own selection.

**Prerequisite (not in this plan):** the runtime exhaustion-state correction
tracked in
[`2026-09-28-cf1-runtime-prerequisites.md`](2026-09-28-cf1-runtime-prerequisites.md)
and accepted by `tests/test_workflow_lisp_generic_state_exhaustion.py::test_generic_record_state_exhaustion_returns_final_continue`
passing without an `xfail` marker. Tasks 1–4 do not depend on it. Tasks 5–6
assert exhaustion after the final `continue` and must run on a base that
includes it.

Execution location: a fresh worktree `.worktrees/cf1b-composition-first`
based on `main` after the prerequisite lands. The parent checkout and
unrelated work are preserved; commit by pathspec.

## Shared Execution And Compatibility Rules

- Target 2.33 admits `defunion :forall` and type applications. Targets up to
  2.32 reject them with a diagnostic naming the required target, following
  the existing `requires target DSL X or newer` style; keep old-target
  controls for every new form.
- One implementer at a time on `type_env.py`, `procedure_typecheck.py`,
  `procedure_specialization.py`, and `contracts.py`; coordinate with any
  concurrent EC-1 or PC-1 edits before starting.
- Test behavior, not prompt text. Deterministic review hooks are command-backed
  (a probe script writing the variant JSON to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`
  with discriminant `variant`), because a pure inline hook as a loop-body
  `match` scrutinee is not currently supported by the frontend.
- No consumer-name special case: `contracts.py` already special-cases
  `std/phase` paths; do not add an equivalent for `std/improve` or
  `Improvement`. The `Outcome[T E]` fixture exists to prove this.
- Effects: `improve` declares no command effect and relies on the current
  generic-hook forwarding regime; specialized summaries must include the
  selected adapters' provider/command effects. EL-1 is not a prerequisite.
- Narrow selectors first; then `pytest -q -n 16 --dist=worksteal` in tmux;
  then the public compile/run/resume path. Record fresh output as evidence.

### Baseline check

Before Task 1, from the worktree root:

```bash
pytest -q tests/test_workflow_lisp_generic_stdlib_composition.py \
  tests/test_workflow_lisp_procedures.py tests/test_workflow_loops_exhaustion_state.py \
  tests/test_workflow_lisp_generic_state_exhaustion.py
python -m orchestrator compile workflows/examples/review_revise_design_docs.orc \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json
```

Record the counts. The exhaustion test must pass without `xfail` before Task 5.

## T. First-Order Generic Unions (Target 2.33)

### Task 1: Register Target 2.33

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/syntax.py` (supported target list
and `*_MIN_TARGET_DSL_VERSION` constants), `orchestrator/workflow/validation.py`
(two supported-target lists), `orchestrator/workflow/run_ref/config.py`
(`_SUPPORTED_TARGET_DSL_VERSIONS`), `specs/versioning.md` (target table and
"additions" sections), and the 2.32 admission tests that pin the previous bump.
**Update:** those files; add `GENERIC_UNION_MIN_TARGET_DSL_VERSION = "2.33"`.
**Create:** `tests/test_workflow_lisp_target_233.py`.

1. Write failing tests: a 2.33 module with no new forms compiles; a 2.34
   module is rejected as unsupported; the 2.32 controls in existing target
   tests still pass.
2. Add 2.33 to every registry and the versioning spec row: "Workflow Lisp
   first-order generic unions and `std/improve`". Describe what 2.33 adds and
   what it does not (no generic records, no explicit procedure type
   arguments, no generic `defprompt` results).
3. Run the new test and the existing target/admission selectors.

### Task 2: Declare Generic Unions And Apply Them In Type Positions

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/definitions.py` (`defunion`),
`orchestrator/workflow_lisp/authored_symbols.py`,
`orchestrator/workflow_lisp/modules.py` (export/import of union declarations),
`orchestrator/workflow_lisp/type_expressions.py::parse_type_expression`
(existing `ProcRef[...]`, `List[...]` applications),
`orchestrator/workflow_lisp/type_env.py` (type-parameter scoping),
`orchestrator/workflow_lisp/form_registry.py` (min-target gating pattern).
**Update:** those owners.
**Create:** `tests/fixtures/workflow_lisp/generic_unions/` and
`tests/test_workflow_lisp_generic_unions.py`.

1. Write failing tests at 2.33: `(defunion Outcome :forall (T E) (OK (value T))
   (ERROR (error E)))` parses; `Outcome[Int String]` is admitted in a `defproc`
   parameter, return, `ProcRef` parameter, and `ProcRef` result position; a
   constructor `(variant Outcome[Int String] OK :value 1)` typechecks in a
   concrete body. Rejections: wrong arity, unresolved parameter in a concrete
   position, instantiation cycle, application of a non-generic union, and the
   same source at 2.32 (target diagnostic).
2. Implement the declaration and type-application syntax. Type parameters of a
   union are scoped to its declaration; applications remain compiler-only
   until every argument is resolved. Imported generic unions keep their
   defining-module identity; an imported alias resolves to the same
   declaration.
3. Diagnostics point at both the use site and the declaration with
   source-map locations. Proposed codes (final names by the type owner):
   `generic_union_arity_mismatch`, `generic_union_unresolved_argument`,
   `generic_union_instantiation_cycle`, `generic_union_not_generic`,
   `generic_union_requires_target`.
4. Run the new module plus `tests/test_workflow_lisp_modules.py` and
   `tests/test_workflow_lisp_expressions.py`.

### Task 3: Bind Arguments Through `ProcRef` Signatures And Preserve Identity

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/procedure_typecheck.py::_infer_parametric_type_bindings`,
`orchestrator/workflow_lisp/type_env.py::type_refs_compatible` and
`_named_type_basename`, `orchestrator/workflow_lisp/procedure_refs.py`
(invariant `ProcRef` matching).
**Update:** those owners.
**Create:** cases in `tests/test_workflow_lisp_generic_unions.py`.

1. Write failing tests: a generic `defproc :forall (S F B)` with
   `(review ProcRef[(S) -> Decision[F B]])` binds `F` and `B` from a concrete
   hook returning `Decision[MyFeedback MyBlocker]`; conflicting repeat bindings
   are rejected; a hook returning a same-short-name `Decision` from another
   module is rejected as a constructor mismatch; an imported alias of the
   defining module matches; a phantom parameter's argument is part of identity.
2. Implement constructor-aware recursive binding: same resolved constructor
   identity and arity first, then bind each argument position; repeated
   occurrences must unify. Carry the applied-type representation into
   compatibility checks instead of loosening or globally tightening legacy
   equality.
3. Run the new cases plus `tests/test_workflow_lisp_procedures.py` and
   `tests/test_workflow_lisp_generic_stdlib_composition.py`.

### Task 4: Instantiate Through Specialization And Prove Transport

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/procedure_specialization.py`,
`orchestrator/workflow_lisp/contracts.py` (union descriptors),
`orchestrator/workflow_lisp/typecheck_structural_values.py` (variant
constructors and `match`), loop-state admission in
`orchestrator/workflow_lisp/loops.py` and `loop_state.py`, and the 2.29 rich
loop tests as the transport pattern.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_generic_unions_runtime.py`.

1. Write failing tests: an instantiated `Outcome[Candidate String]` is
   returned from an imported generic procedure, carried as a loop-state field,
   matched with payload binding, returned as a workflow result, and consumed
   downstream, on a fresh run and after committed-boundary resume. Descriptors
   in the executable IR are ordinary concrete unions with no type variables.
2. Implement instantiation in the existing pipeline: resolve call-site types,
   check constraints, instantiate, typecheck the monomorphic body, lower.
   Specialization identity includes the concrete union argument identities.
3. Run the new module, `tests/test_workflow_lisp_rich_loop_values_e2e.py`,
   and `tests/test_workflow_lisp_lexical_checkpoint_restore.py` selectors that
   cover loop-state descriptors.

## L. The `std/improve` Library (Target 2.33)

### Task 5: Ship `std/improve`

- [x] Complete

**Read/trace:** `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
(the legacy loop, unchanged), `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
(imported generic loop pattern), `orchestrator/workflow_lisp/effects.py`
(forwarding regime for generic hooks), and the composition design §§3–5, 7.
**Create:** `orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`,
`tests/test_workflow_lisp_improve_stdlib.py`.

1. Write failing tests using command-backed hooks: approval on the first
   review returns `APPROVED` with the initial value and its evidence;
   reviewer blockage returns `BLOCKED` with the refused candidate; three
   `REVISE` decisions at `limit 3` return `EXHAUSTED` with the third revision
   (depends on the runtime prerequisite); a hook result failing its declared
   type is a contract failure with no `Decision` reaching the helper; inline
   and imported forms agree on outcome and ordered hook operations. From the
   [master plan's](2026-09-28-composition-first-master-plan.md#review-focus)
   Review Focus: `limit 0` is a compile-time rejection, the same as `:max 0`
   on a plain loop, and no hook runs; a `revise` hook that fails in the
   final permitted iteration is a runtime failure, not `EXHAUSTED`; a
   target-2.32 module that uses `improve` is rejected with the required-target
   diagnostic.
2. Author `std/improve` exactly as the design's §3 interface and §4 loop:
   `Decision :forall (F B)`, `Improvement :forall (S F B)`, `improve` with
   `:where ((S is-record))`, state `{current}`, `inputs` as a lexical binding,
   `:on-exhausted` projecting `state.current`, no `ctx`, no seeds, no counter.
   Record in the test module that `std/phase` is unchanged, so no existing
   program loses a `ctx`-borne dependency.
3. Confirm the specialized effect summary includes the selected hooks'
   command/provider effects under the forwarding regime.
4. Run the new module and `tests/test_workflow_lisp_phase_stdlib.py`.

### Task 6: Prove A Structured-Value Caller End To End

- [x] Complete

**Read/trace:** `workflows/examples/review_revise_design_docs.orc` and its
`inputs/` manifests (example conventions), `tests/test_workflow_lisp_examples.py`,
and the public run/resume tests in
`tests/test_workflow_lisp_rich_loop_values_e2e.py`.
**Create:** `workflows/examples/improve_experiment_proposal.orc`,
`workflows/examples/inputs/improve_experiment_proposal/`, and
`tests/test_workflow_lisp_improve_example_e2e.py`.

1. Write failing tests through the public entry: the example compiles with
   the documented command; a run with deterministic hooks revises a nested
   proposal record (a typed parameter list plus a scalar field) and a
   deterministic executor step consumes the returned `value`; interruption
   after a committed review and after a committed revision resumes under the
   existing contract and reaches the same consumer without repeating provider
   work; exhaustion after the final `continue` projects the generic record on
   a fresh run and after committed-boundary resume; substituting the reviewer
   with a sequential two-review-plus-adjudication procedure changes only the
   selected hook; and, from the master plan's Review Focus, when an inner
   review of that substituted procedure is blocked the result is `BLOCKED`
   with the domain blocker, never a downgraded `REVISE` or `APPROVE`.
2. Author the example: `propose` (deterministic), `review` and `revise` hooks
   over an `ExperimentProposal` record, `improve`, then `execute` consuming
   the returned value. Provider bindings stay external configuration.
3. Run the new module, `tests/test_workflow_lisp_examples.py`, and the exact
   documented compile command.

### Task 7: Promote Documentation

- [ ] Complete

**Update:** `specs/versioning.md` (already added in Task 1; confirm wording),
`docs/design/workflow_lisp_frontend_specification.md` (generic-union
application and `std/improve` entries), `docs/lisp_workflow_drafting_guide.md`
(one authoring entry with the example's compile command),
`docs/capability_status_matrix.md` (row to implemented at 2.33 with the new
tests as evidence), `docs/design/README.md` and `docs/index.md` rows,
the design's status line, the type-system section's status, and the roadmap
CF-1 status and CF-1b row closeout.

1. Record supported behavior and limits: `S is-record` for the first
   delivery, applied-union `provider-result` returns, adapters for concrete
   results, no generic records, no generic `defprompt` results, command- or
   provider-backed hooks.
2. Run `pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
   tests/test_monitor_docs.py` and the link check on edited files.

## Closeout And Consequent Actions

- [ ] Full suite in tmux: `pytest -q -n 16 --dist=worksteal`, compared with
  the recorded baseline failure set; no new failures.
- [ ] Public compile/run/resume evidence for the example, with fresh output.
- [ ] Merge to `main` by fast-forward from the worktree; commit by pathspec.
- [x] Record in the roadmap CF-1 section: supported contract, limits, and the
  CF-1c selection decision (migration of the two maintained callers and the
  utility evaluation). No utility claim follows from a passing slice.
  Recorded 2026-09-28: CF-1c consumer migration is on hold under the
  roadmap's entry conditions.

Out of scope here: migrating `review_revise_design_docs.orc` and
`kiss_backlog_item.orc` (CF-1c), fixer-side blockage, generic records,
document snapshot references, direct generic `defprompt` results (CF-1d), and
retiring any `std/phase` declaration.
