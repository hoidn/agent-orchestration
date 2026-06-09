# Macro Acceptance-Gate Fixtures Implementation Architecture

## Scope

This design gap covers only the bounded macro-safety completion slice selected
by the current drain state:

- add durable fixture-backed acceptance coverage for macro-emitted hidden
  command effects, alongside the already-implemented hidden provider-effect
  checks;
- prove that macros cannot smuggle compile-time callable values such as
  `ProcRef`, `bind-proc` results, or generated local procedures into runtime
  workflow surfaces;
- prove that macro-generated executable/source-map nodes fail deterministically
  when lineage is missing or tampered with;
- prove that nested macro expansions render deterministic, source-mapped
  diagnostics with the full expansion stack preserved;
- keep the slice centered on tests, fixtures, and the minimum diagnostic or
  provenance plumbing needed to make those proofs stable.

Out of scope for this tranche:

- redesign of the macro language, hygiene model, or expansion algorithm;
- new runtime callable types, runtime closures, or dynamic dispatch;
- new executable IR node kinds or a source-map schema redesign;
- any command-adapter redesign, new helper scripts, or runtime-native effects;
- general macro-system completion outside the remaining Section 52 acceptance
  obligations;
- unrelated workflow authoring, queue, prompt, or runtime changes.

This is an implementation architecture for the selected macro acceptance-gap
fixtures only. It does not authorize widening the work into a new macro
runtime, alternate validator, or general callable transport model.

## Problem Statement

The current checkout already implements meaningful macro behavior:

- hygienic same-file and imported macro expansion in
  `orchestrator/workflow_lisp/macros.py`;
- hidden provider and command effect rejection in
  `orchestrator/workflow_lisp/typecheck.py`;
- macro-aware diagnostic rendering in `orchestrator/workflow_lisp/diagnostics.py`;
- executable/source-map validation in `orchestrator/workflow_lisp/source_map.py`;
- basic macro tests in `tests/test_workflow_lisp_macros.py` and
  `tests/test_workflow_lisp_diagnostics.py`.

What is still missing is a bounded slice that turns those partial mechanisms
into durable macro acceptance evidence matching unified-design Sections 50-52.
The repo does not yet have one implementation architecture or one focused test
matrix that proves all of the remaining obligations together:

- macro-emitted `command-result` is rejected as a hidden command effect under
  the same contract as authored command boundaries;
- macro expansion cannot bypass existing compile-time-only callable transport
  bans;
- generated macro-origin executable/source-map nodes cannot go unmapped without
  a deterministic failure signal;
- nested expansions keep a stable expansion-stack order and actionable
  source-map notes.

The gap is therefore not missing macro features. It is missing bounded,
durable, architecture-backed proof that the macro surface already in the repo
obeys the remaining safety gate.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  Sections 47-52;
- `docs/design/workflow_lisp_frontend_specification.md`
  Sections 32-37, 61, 74-76.1, 92, and 97;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/steering.md`;
- the current unified-design implementation architectures listed in
  `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/0/design-gap-architect/existing-architecture-index.md`.

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned macro, diagnostic,
  lowering, and source-map package;
- reuse the current pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck/effects -> lowering -> shared validation -> executable/source-map
  validation;
- reuse `SourceSpan`, `LispFrontendDiagnostic`, `ExpansionFrame`,
  `expansion_stack`, `LoweringOriginMap`, and build/source-map validation as
  the only provenance channel;
- reuse existing ProcRef transport rejection instead of inventing a
  macro-specific callable-safety mechanism;
- reuse the existing command-boundary contract rather than letting macros
  reclassify command steps or hide uncertified adapters;
- keep reports as views, structured outputs as authority, and source maps as
  required provenance for generated structure;
- treat the empty `docs/steering.md` in this checkout as no additional scope,
  not as permission to broaden the work.

`docs/design/workflow_command_adapter_contract.md` is directly relevant here.
The selected slice explicitly covers macro-emitted `command-result`, so the new
acceptance fixtures must prove that macros do not become a loophole for:

- hidden command effects;
- uncertified or undeclared command boundaries;
- inline semantic glue hidden inside generated command text;
- missing source-map behavior at command boundaries.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/runtime-closure-disabled-profile-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`

### Decisions Reused

- Reuse the executable-IR slice's rule that validated executable IR and its
  source-map lineage remain the authoritative runtime-facing proof surface.
- Reuse the runtime-closure disabled-profile slice's rule that fixture-only
  rejection evidence is an acceptable bounded increment when the goal is to
  prove a forbidden surface stays forbidden.
- Reuse the `let-proc` and runtime-closure slices' shared rule that
  compile-time callable abstractions must be erased before runtime artifacts
  are produced.
- Reuse the effectful-composition slices' rule that new authoring power must
  lower through the existing validated workflow model rather than inventing a
  second runtime or validator.
- Reuse the reusable-boundary slice's deterministic write-root and provenance
  discipline: generated structure is only acceptable when it is explicit and
  source-mapped.
- Reuse the command-adapter contract as the authority for command-boundary
  classification, declared effects, and source-map obligations.

### New Decisions In This Slice

- Treat the remaining macro acceptance obligations primarily as a fixture and
  regression-coverage gap, not as a justification for new macro semantics.
- Add a focused macro fixture taxonomy spanning four proof areas:
  hidden command effects,
  compile-time callable transport rejection,
  source-map coverage rejection,
  and nested expansion diagnostics.
- Require macro-origin failures to preserve the same diagnostic code they would
  have without macros unless the failure is specifically a hidden-effect lint;
  macros add provenance, not a second error taxonomy.
- Prefer file-backed fixtures over ad hoc inline temporary modules wherever the
  scenario is part of the durable acceptance matrix.
- Allow only narrow frontend plumbing changes needed to stabilize macro frame
  ordering or source-map remapping for the new tests.

### Conflicts Or Revisions

The current checkout implicitly treats "macro support exists" plus a few
provider-focused tests as sufficient progress on macro safety. This slice
revises that assumption narrowly:

- keep the implemented macro expansion and hidden-effect behavior;
- add a bounded acceptance matrix that closes the remaining design obligations;
- keep command hidden effects, callable transport rejection, and source-map
  omissions on their existing validators and diagnostics rather than moving
  them into a macro-specific subsystem.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, Executable IR, TypeCatalog, SourceMap, pointer authority,
variant proof, or runtime execution ownership.

## Ownership Boundaries

This slice owns:

- the bounded fixture taxonomy for remaining macro acceptance obligations;
- deterministic macro-specific regression tests covering hidden command
  effects, compile-time callable transport rejection, source-map omissions, and
  nested expansion stacks;
- any narrow diagnostic or source-map remapping stabilization needed to keep
  those failures deterministic and source-mapped;
- documentation of which existing validator owns each macro acceptance proof.

This slice intentionally does not own:

- macro syntax or hygiene redesign;
- runtime callable models, runtime closures, or dynamic dispatch;
- new executable node kinds, new shared validation passes, or new runtime
  execution semantics;
- command-adapter semantics beyond consuming the existing contract;
- general ProcRef, WorkflowRef, or `let-proc` semantics outside macro-origin
  regression coverage.

## Proposed Package Boundary

Keep the work mostly inside frontend tests and fixtures, with narrow fallback
touches in existing diagnostic/provenance modules only if the new checks expose
instability:

```text
orchestrator/workflow_lisp/
  compiler.py      # only if macro-origin source-map remapping needs stabilization
  diagnostics.py   # only if multi-frame macro note ordering needs stabilization
  source_map.py    # only if macro-origin executable-node omission tests expose
                   # a missing lineage propagation seam

tests/
  fixtures/workflow_lisp/invalid/
  fixtures/workflow_lisp/modules/invalid/
  test_workflow_lisp_macros.py
  test_workflow_lisp_diagnostics.py
  test_workflow_lisp_source_map.py
  test_workflow_lisp_workflows.py
```

Primary responsibilities:

- `tests/fixtures/workflow_lisp/invalid/`
  - add durable same-file macro fixtures for:
    - hidden command effect,
    - ProcRef runtime transport,
    - nested expansion failures,
    - source-map omission harness inputs where possible.
- `tests/fixtures/workflow_lisp/modules/invalid/`
  - add imported/nested macro module fixtures when call-site vs definition-site
    provenance is part of the acceptance case.
- `tests/test_workflow_lisp_macros.py`
  - assert hidden command-effect and runtime callable transport failures through
    macro-authored code paths as part of the macro acceptance surface, not only
    generic transport tests.
- `tests/test_workflow_lisp_diagnostics.py`
  - assert rendered note order and full expansion-stack coverage for nested
    macro failures.
- `tests/test_workflow_lisp_source_map.py`
  - assert deterministic rejection when macro-origin executable/source-map
    lineage is missing or tampered with.
- `tests/test_workflow_lisp_workflows.py`
  - reuse existing transport-rejection seams when the fixture failure is owned
    by workflow-boundary type transport rather than by the macro expander.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow/executable_ir.py`

## Current Checkout Facts

Current implementation evidence shows the macro acceptance gap is real but
bounded:

- `orchestrator/workflow_lisp/macros.py`
  - already builds ordered `ExpansionFrame` stacks with deterministic expansion
    ids;
  - already performs hygienic identifier introduction;
  - already rejects invalid emitted top-level forms.
- `orchestrator/workflow_lisp/typecheck.py`
  - already rejects macro-introduced `provider-result` with
    `macro_hidden_effect`;
  - already rejects macro-introduced `command-result` with
    `macro_hidden_effect`;
  - does not itself provide the missing fixture taxonomy proving those checks
    are complete enough for the remaining acceptance obligations.
- `orchestrator/workflow_lisp/type_env.py`, `workflows.py`, and `loops.py`
  - already reject runtime transport of ProcRef values with
    `proc_ref_runtime_transport_forbidden`;
  - current tests exercise those rules, but not through macro-generated
    callables with preserved expansion provenance.
- `orchestrator/workflow_lisp/source_map.py`
  - already rejects missing executable-node lineage with
    `source_map_executable_node_unmapped`;
  - already rejects invalid generated-effect lineage;
  - current source-map tests do not specifically prove the macro-origin case.
- `tests/test_workflow_lisp_macros.py`
  - covers same-file and imported macro behavior, but has no nested expansion
    fixture family and no macro ProcRef transport cases.
- `tests/test_workflow_lisp_diagnostics.py`
  - includes a command-hidden-effect rendering test and several provider/name
    error rendering tests, but no stable nested multi-frame macro-stack
    acceptance matrix.
- `tests/fixtures/workflow_lisp/`
  - contains only a small macro fixture set;
  - contains no dedicated macro runtime-transport or nested-expansion files.

That means the missing work is not a new macro engine. It is a missing
regression boundary around already-existing macro, transport, and source-map
contracts.

## Internal Acceptance Contract

### 1. Hidden Effect Matrix

The macro acceptance surface must explicitly prove both hidden effect classes
owned by the current typechecker:

- macro-emitted `provider-result` -> `macro_hidden_effect`;
- macro-emitted `command-result` -> `macro_hidden_effect`.

Rules:

- the failure remains an effect-owned required lint, not a command-boundary
  parse error, unless the fixture deliberately removes the hidden-effect
  condition;
- the diagnostic must retain macro expansion provenance;
- imported and same-file macro cases should share the same code path;
- command cases must continue to respect the command-adapter contract.

### 2. Compile-Time Callable Transport Matrix

The slice must prove that macros do not bypass existing compile-time callable
transport bans.

Accepted proof shape:

- macro emits a workflow, record, or union surface that attempts to transport
  `ProcRef[...]` or a macro-generated proc-ref value through a runtime boundary;
- existing transport validation rejects it with
  `proc_ref_runtime_transport_forbidden`;
- the diagnostic preserves the macro expansion stack.

Rules:

- do not add a new macro-only transport code;
- do not reinterpret this as runtime-closure work;
- `let-proc`, `bind-proc`, and `proc-ref` remain compile-time-only regardless
  of whether the authored code arrived through a macro.

### 3. Source-Map Coverage Matrix

The slice must prove that macro-generated executable/source-map structure is
not allowed to go unmapped.

Accepted proof shape:

- compile a macro-generated workflow through the ordinary frontend path;
- tamper with the generated source-map or lineage structure in a focused test
  harness;
- assert deterministic rejection via `source_map_executable_node_unmapped`,
  `source_map_generated_effect_invalid`, or `source_map_missing`, depending on
  which validator owns the failure;
- assert the diagnostic still points back to macro-authored provenance through
  workflow-origin expansion frames.

Rules:

- no new source-map schema is needed for this slice;
- no second validator is allowed;
- the tests may use existing build/source-map helpers and targeted mutation,
  mirroring current source-map validator tests.

### 4. Nested Expansion Diagnostic Matrix

The slice must add explicit nested macro cases where one macro expansion emits
or triggers another.

Required proof:

- diagnostics preserve the full expansion stack in deterministic order;
- rendered notes mention each macro call site and definition site exactly once;
- the most actionable authored location remains the call or emitted form span,
  not an opaque generated symbol;
- the same ordering rules hold for both effect-owned failures and downstream
  structural/type/source-map failures.

Recommended ordering:

- preserve the current `ExpansionFrame` order emitted by the expander;
- assert against rendered note order rather than reinterpreting the stack in
  tests.

## Test And Acceptance Surface

Add a focused acceptance matrix, not an open-ended macro suite.

Positive/retained cases:

- existing hygiene and imported macro coverage remains green;
- existing provider hidden-effect coverage remains green;
- existing command-boundary contract behavior for authored code remains green.

New negative cases required:

- same-file macro emits hidden `command-result` and fails with
  `macro_hidden_effect`;
- imported or nested macro emits hidden `command-result` and preserves the full
  expansion stack;
- macro emits runtime ProcRef transport and fails with
  `proc_ref_runtime_transport_forbidden`;
- macro-origin source-map omission or executable-node lineage tampering fails
  deterministically;
- nested macro failure renders stable expansion notes and macro definition/call
  provenance.

Success should be judged by proof coverage, not by LOC or by adding new macro
features.

## Verification Expectations

Visible checks for the future implementation should stay narrow and
deterministic. At minimum the eventual work item should run:

- targeted macro tests;
- targeted diagnostics tests;
- targeted source-map tests;
- any additional workflow-boundary transport test touched by the new fixtures.

The implementation is complete only when the new fixtures demonstrate all four
acceptance areas without changing the macro/runtime authority split.
