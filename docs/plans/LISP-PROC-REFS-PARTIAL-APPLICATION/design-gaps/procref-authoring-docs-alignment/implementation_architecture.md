# ProcRef Authoring Docs Alignment Implementation Architecture

Status: draft
Design gap id: `procref-authoring-docs-alignment`
Target design: `docs/design/workflow_lisp_proc_refs_partial_application.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice aligns current author-facing ProcRef documentation with the feature
surface that is already implemented in the checkout.

It covers only:

- current-state ProcRef guidance in authoring docs;
- the current implementation-status wording used to describe supported ProcRef
  behavior;
- verification that the updated wording matches accepted design, completed
  ProcRef slices, and durable code/test evidence.

It does not cover:

- new compiler, runtime, lowering, or diagnostic work;
- new ProcRef semantics beyond the accepted delta;
- historical architecture or execution-plan rewrites;
- scripts, command adapters, workflow YAML, prompts, or runtime-native effects.

## Problem Statement

The selected gap is a `stale_duplicate` plus `discoverability_gap`.

Current durable implementation evidence shows that the ProcRef tranche now
includes:

- `ProcRef[...]` type parsing and transport rejection;
- `(proc-ref ...)` literals and module-aware resolution;
- keyword-only `bind-proc` partial application;
- residual-signature computation;
- specialization before lowering;
- lexical invocation through ProcRef bindings;
- ProcRef-specific diagnostics, effect preservation, and lowering coverage.

That evidence is present in:

- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_lowering.py`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-20260528T215013Z.json`

But the current Lisp authoring guide still says the supported surface stops at
static `ProcRef[...]` plus `(proc-ref ...)`, and still tells authors not to use
`bind-proc`, residual specialization, or ProcRef call-through.

That mismatch is small in file count but high-impact in behavior:

- authors get the wrong supported subset;
- reviewers may reject valid ProcRef usage as unimplemented;
- future drain runs can misclassify completed work as still pending.

## Design Constraints

The alignment slice must preserve these rules:

- accepted ProcRef semantics still come from
  `docs/design/workflow_lisp_proc_refs_partial_application.md`;
- the baseline frontend contract still requires compile-time-only ProcRef
  values and no unresolved ProcRef transport into runtime state;
- current authoring docs must describe shipped behavior conservatively, not the
  largest imaginable future ProcRef surface;
- historical architecture docs and execution plans remain historical evidence
  and should not be "corrected" just because later slices landed;
- the command-adapter contract remains unchanged and is reviewed only as a
  guardrail against accidentally broadening this docs slice into script or
  runtime-boundary work.

## Proposed Architecture

### 1. Define the authority chain for "supported now"

For this slice, current support claims should come from this precedence order:

1. accepted ProcRef delta and baseline frontend contract;
2. completed ProcRef implementation architectures;
3. current implementation and targeted tests;
4. current run-state history for the ProcRef drain;
5. derived explainer surfaces such as authoring guides and package READMEs.

That means the stale guide text is not an alternative authority surface. It is
derived documentation that now needs to be brought back into sync.

### 2. Rewrite only the stale current-state ProcRef guidance

The primary owned doc surface is `docs/lisp_workflow_drafting_guide.md`.

This slice should update the guide in two places:

- the current implementation-status section that still says the ProcRef tranche
  is limited to static references;
- the later usage guidance that still forbids examples using `bind-proc`,
  residual signatures, or ProcRef call-through.

The replacement wording should say that the current supported ProcRef surface
includes:

- `ProcRef[...]` type annotations;
- explicit `(proc-ref name)` literals;
- `bind-proc` keyword-only partial application;
- forwarding ProcRef bindings through `defproc` parameters;
- lexical invocation through ProcRef-bound call heads after specialization;
- compile-time-only ProcRef transport rules.

The same rewrite must keep the remaining unsupported boundaries explicit:

- no runtime first-class procedures or closures;
- no ProcRef values in workflow outputs, records, unions, artifacts, ledgers,
  provider results, command results, or loop-carried runtime state;
- no provider-selected or command-produced procedure values;
- no dynamic runtime dispatch;
- no arbitrary computed callee expressions beyond the supported lexical
  binding/call-head surface.

### 3. Treat adjacent discoverability surfaces as verification targets first

`orchestrator/workflow_lisp/README.md` already describes `procedure_refs.py`
as owning `bind-proc` partial application, specialization naming, and
residual-signature validation while keeping ProcRef compile-time-only.

`docs/index.md` already describes the ProcRef delta as the active
`ProcRef` / `bind-proc` partial-application extension.

Because those surfaces are already directionally aligned, this slice should
treat them as verification targets first and patch them only if implementation
wording drift is found during the work item. This keeps the scope bounded and
avoids unnecessary churn across already-correct index text.

### 4. Preserve historical slice boundaries

The earlier ProcRef architecture and execution-plan documents intentionally
described then-missing capabilities:

- `procref-static-surface-and-resolution`
- `procref-bind-proc-specialization-lowering`

Those documents should remain untouched. They are time-scoped implementation
artifacts, not the current author-facing status surface. This slice revises
current guidance, not historical planning evidence.

### 5. Verify support claims against code and tests, not labels

The implementation item for this architecture should verify the guide wording
against the current implementation by using targeted ProcRef tests and
content checks, not by trusting status labels alone.

Recommended evidence set:

- focused ProcRef pytest selectors covering procedures, modules, and lowering;
- `rg` checks that stale "do not rely on bind-proc" wording is gone from the
  current authoring guide;
- `rg` checks that compile-time-only/runtime-transport restrictions still
  remain visible after the wording update.

No orchestrator or workflow smoke run is required for this docs-only slice
because it does not change workflow YAML, prompts, provisioning, or runtime
contracts.

## Files And Ownership

Owned by this slice:

- `docs/lisp_workflow_drafting_guide.md`
- optionally `orchestrator/workflow_lisp/README.md` if wording drift is found
- optionally `docs/index.md` if current discoverability text needs a narrow
  clarification
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-authoring-docs-alignment/`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/2/design-gap-architect/`

Intentionally not owned by this slice:

- `orchestrator/workflow_lisp/*.py`
- ProcRef fixtures and tests beyond using them as evidence
- accepted design specs
- historical implementation architectures and execution plans
- drain run state, selector state, and progress ledger contents

## Relationship To Existing Implementation Architectures

- Existing slices reviewed:
  - `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md`
  - `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-bind-proc-specialization-lowering/implementation_architecture.md`
- Decisions reused:
  - ProcRef remains compile-time-only.
  - `(proc-ref ...)` remains the explicit authored procedure-reference literal.
  - `bind-proc` remains keyword-only partial application.
  - specialization happens before lowering and executable IR contains no
    unresolved ProcRef values.
  - runtime transport of ProcRef values remains forbidden.
- New decisions in this slice:
  - current authoring docs must describe the completed `bind-proc` tranche as
    supported behavior;
  - `docs/lisp_workflow_drafting_guide.md` is the primary stale surface to fix;
  - `README` and `docs/index.md` should be treated as sync checks before being
    treated as edit targets.
- Conflicts or revisions:
  - this slice revises the outdated deferral wording in the current Lisp
    drafting guide;
  - it does not revise the earlier ProcRef architectures, which were correct
    for their original time-scoped gaps.

## Acceptance Conditions

- the current Lisp authoring guide no longer says `bind-proc`, residual
  specialization, or ProcRef call-through are deferred;
- the guide still states the compile-time-only and runtime-transport
  restrictions that remain in force;
- current discoverability/status surfaces either match the new guide wording or
  are intentionally left unchanged because they were already consistent;
- targeted ProcRef tests and grep-based doc checks provide the verification
  evidence for the support claims.
