# Runtime Closure Disabled-Profile Fixtures Implementation Architecture

Status: draft
Design gap id: `runtime-closure-disabled-profile-fixtures`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded deferred-profile rejection coverage required by
the unified design before any executable runtime-closure work can begin:

- define one fixture-only validation surface for rejected runtime-closure
  values, captures, transport channels, invocation sites, resume metadata, and
  source-map omissions;
- add stable closure-specific diagnostic codes and fixture expectations for the
  disabled/design-fixture profiles;
- preserve the current implemented baseline that `ProcRef`, `bind-proc`, and
  `let-proc` are compile-time-only and must not become runtime closures;
- add artifact-leakage checks proving normal Workflow Lisp builds still emit no
  runtime-closure payloads, registries, or invocation nodes;
- keep the work bounded to fixtures, diagnostics, and non-executable
  validation helpers.

This slice does not implement:

- runtime closure syntax, runtime closure values, or runtime closure execution;
- new executable IR node kinds, closure-family registries in real bundles, or
  checked dynamic invocation in the runtime;
- changes to `ProcRef`, `bind-proc`, `let-proc`, or current same-file
  procedure lowering semantics beyond preserving their compile-time-only
  boundary;
- new command adapters, helper scripts, legacy adapters, inline shell/Python
  glue, or runtime-native promotion;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, or provider/command runtime
  semantics.

The work stays bounded to one pre-implementation guardrail seam. It is an
implementation architecture for rejected-shape closure fixtures, not a runtime
closure design or partial runtime closure rollout.

## Problem Statement

The current checkout already enforces several of the baseline callable-value
rules that the unified design treats as fixed input:

- `orchestrator/workflow_lisp/type_env.py` rejects `ProcRef[...]` transport in
  record fields, union payloads, and nested collection types with
  `proc_ref_runtime_transport_forbidden`;
- `orchestrator/workflow_lisp/workflows.py` rejects workflow boundaries that
  would transport `ProcRef[...]` or `WorkflowRef[...]`;
- `orchestrator/workflow_lisp/loops.py` and the existing lowering/typecheck
  path keep compile-time-only callable values out of loop/runtime state;
- `tests/test_workflow_semantic_ir.py` already proves executable artifacts omit
  `ProcRef` and `WorkflowRef` payloads;
- the landed `let-proc` slice closure-converts only to generated private
  `defproc` equivalents and does not emit runtime callable objects.

What is missing is the closure-specific deferred-profile coverage required by
Part V of the unified design.

Today the repo has no bounded way to exercise these future-shape rejections:

- no `runtime_closure_not_enabled` diagnostic in the frontend/runtime-facing
  diagnostic vocabulary;
- no fixture schema for rejected closure families, closure values, invocation
  sites, resume envelopes, or closure source-map metadata;
- no design-fixture-only validator that can reject future runtime-closure
  shapes without enabling runtime closures;
- no artifact-level regression checks for closure-family registries,
  `workflow_lisp_runtime_closure/v1` payloads, or `InvokeClosure`-style node
  markers leaking into normal compiled bundles;
- no explicit separation between existing ProcRef transport rejections and the
  future runtime-closure rejection family.

That leaves the selected target-design gap unresolved:

```text
current baseline
  -> rejects compile-time callable transport
  -> emits no runtime callable payloads

missing deferred-profile guardrail
  -> rejected closure-value fixture vocabulary
  -> rejected closure invocation/resume/source-map fixtures
  -> stable closure-specific diagnostics before executable closure work
```

The selected gap is therefore not to add runtime closures. It is to create a
stable rejection harness and fixture suite that keeps runtime closures
explicitly deferred while still testing the forbidden-shape matrix named by the
target design.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `4.1 No hidden runtime values`
  - `4.2 No hidden effects`
  - `53. Feature Summary`
  - `54.1 Disabled Profile`
  - `54.2 Design-Fixture Profile`
  - `56. Forbidden Runtime Closure Shortcuts`
  - `67. Closure Diagnostics`
  - `68. Runtime Closure Source Maps`
  - `69. Runtime Closure Fixtures`
  - `72. Runtime Closure Acceptance Gate`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `18. Reports Are Views, Not State`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `74. Source Map Requirements`
  - `97. Negative Tests`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative for real runtime semantics;
- no runtime closure value, registry, or invocation node may appear in normal
  compiled Workflow Lisp artifacts;
- `ProcRef`, `bind-proc`, and `let-proc` remain compile-time-only and must not
  be reinterpreted as runtime closures;
- no helper script, command adapter, inline shell/Python glue, or hidden
  dynamic-dispatch shim may be introduced to emulate runtime closure behavior
  under the disabled profile;
- fixture-only validation must not create a second executor, a second lowering
  path, or a hidden bundle format that bypasses the current validated workflow
  pipeline.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`

### Decisions Reused

- Reuse the `let-proc` slice rule that compile-time local procedures erase into
  generated private `defproc` definitions and never become runtime callable
  payloads.
- Reuse the executable-IR slice rule that `LoadedWorkflowBundle.ir` /
  `ExecutableWorkflow` is the only runtime-facing executable authority and that
  new executable node kinds require a separate accepted contract.
- Reuse the effectful-composition slices' rule that new authoring power must
  lower through the existing validated workflow model rather than inventing a
  second runtime.
- Reuse the reusable-boundary write-root slice's requirement that any dynamic
  callable surface must prove deterministic write-root policy or reject.
- Reuse the command-adapter contract as the authority that forbids hidden
  helper commands or inline glue as a substitute for typed closure semantics.

### New Decisions In This Slice

- Add a fixture-only runtime-closure rejection harness instead of adding any
  real runtime-closure AST, executable IR node, or runtime value type.
- Separate closure-specific disabled-profile diagnostics from existing
  `ProcRef` transport diagnostics so the repo can test future runtime-closure
  forbidden shapes without conflating them with current compile-time callable
  transport rules.
- Treat the design-fixture profile as a test-only validation surface that may
  inspect rejected closure shapes and expected diagnostics, but may never
  construct executable runtime-closure artifacts.
- Extend normal artifact regression checks to prove that closure-family
  registries, closure payload schemas, and invocation markers do not leak into
  ordinary Workflow Lisp build outputs.

### Conflicts Or Revisions

The current implementation effectively treats "unsupported runtime callables"
as one of two things:

- `ProcRef` / `WorkflowRef` runtime-transport rejection; or
- absence of any runtime-closure syntax or runtime value surface.

That is too weak for the selected target-design gap. This slice revises that
assumption narrowly:

- keep the existing ProcRef and WorkflowRef transport rejections unchanged;
- add closure-specific rejected-shape fixtures and diagnostics without enabling
  closures;
- keep all closure work behind an explicit disabled/design-fixture boundary
  until the runtime-closure acceptance gate is satisfied.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, variant proof,
or runtime execution ownership.

## Ownership Boundaries

This slice owns:

- fixture-only schema and parser/loader support for runtime-closure disabled
  profile cases;
- closure-specific diagnostic-code registration and rendering support needed by
  the fixture harness;
- non-executable validation of forbidden closure captures, transport channels,
  invocation bounds, resume metadata, and source-map omissions;
- artifact leakage checks proving closure payloads do not appear in ordinary
  compiled/frontend-emitted artifacts;
- focused tests for the disabled/design-fixture rejection matrix.

This slice intentionally does not own:

- authored Workflow Lisp closure syntax;
- runtime closure families, closure registries, executable IR invocation nodes,
  or runtime closure state persistence;
- changes to actual workflow compilation, lowering, or runtime execution beyond
  test-only omission checks and diagnostic registration;
- reclassification of `ProcRef` or `let-proc` as runtime values;
- command adapters, helper commands, scripts, or runtime-native effects.

## Proposed Package Boundary

Keep the work primarily inside the Workflow Lisp frontend test/diagnostic layer
and avoid introducing new shared runtime execution surfaces:

```text
orchestrator/workflow_lisp/
  diagnostics.py                       # closure diagnostic codes and pass metadata
  runtime_closure_design_fixtures.py   # fixture-only disabled-profile schema + validator
  README.md                            # document the fixture-only boundary

tests/
  fixtures/workflow_lisp/runtime_closure_disabled/
  test_workflow_lisp_runtime_closure_fixtures.py
  test_workflow_lisp_build_artifacts.py
  test_workflow_semantic_ir.py
```

Primary responsibilities:

- `runtime_closure_design_fixtures.py`
  - define one non-executable fixture schema for rejected closure cases;
  - deserialize JSON/YAML fixture cases into typed test-only records;
  - validate fixture cases under either:
    - disabled-profile feature-gate rejection; or
    - design-fixture-only shape rejection with explicit expected codes;
  - return deterministic `LispFrontendDiagnostic` payloads only, never runtime
    closure values, registries, or executable nodes.
- `diagnostics.py`
  - register closure-specific codes so rendering/serialization stays stable for
    test fixtures;
  - map `closure_source_map_missing` to source-map metadata and
    `runtime_closure_not_enabled` / transport/bound/capture violations to the
    appropriate diagnostic phase used by the fixture harness.
- `README.md`
  - document that runtime closures remain deferred and that the fixture module
    is a guardrail/test surface only.
- `tests/...`
  - store rejected-shape fixtures as data, not as executable workflows;
  - assert expected codes and no-leak invariants.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/build.py`

## Data Model

### No New Runtime Surface

This slice deliberately adds no new:

- `.orc` expression node;
- Core Workflow AST statement family;
- Semantic IR closure entry;
- Executable IR node kind;
- runtime closure value dataclass used by normal builds.

If a future implementation needs any of those, it belongs to a later accepted
runtime-closure architecture, not this fixture slice.

### Fixture-Only Case Schema

Add one test-only case envelope with enough structure to express the forbidden
shapes from unified-design Sections 69 and 72:

- `RuntimeClosureFixtureCase`
  - `fixture_id`
  - `profile`
    - `disabled`
    - `design_fixture_only`
  - `case_kind`
    - `authored_value`
    - `runtime_value`
    - `transport`
    - `invoke`
    - `resume`
    - `source_map`
  - `payload`
  - `expected_code`
  - `expected_message_contains`

Recommended payload variants:

- `RuntimeClosureValueFixture`
  - closure family name or authored alias
  - synthetic code id
  - synthetic capture descriptors
  - transport channel, if any
- `RuntimeClosureInvocationFixture`
  - accepted family list
  - synthetic effect/capability bounds
  - write-root policy descriptor
- `RuntimeClosureResumeFixture`
  - executable bundle id
  - closure family id
  - code id
  - capture schema id
- `RuntimeClosureSourceMapFixture`
  - creation-site ref
  - invocation-site ref
  - source-map presence flags

These records are diagnostic fixtures only. They model rejected shapes closely
enough to test stable diagnostics, but they are not executable closure objects
and must not be serialized into normal runtime artifacts.

## Validation Model

### 1. Keep Existing Compile-Time Callable Rejections Intact

The current implemented checks for:

- `proc_ref_runtime_transport_forbidden`
- `workflow_ref_runtime_transport_forbidden`

remain authoritative for actual Stage 3 workflow/type surfaces. This slice does
not replace them with closure diagnostics.

Instead, the new fixture harness should treat them as baseline evidence that
compile-time callables already stay out of runtime transport, then add the
closure-specific rejection matrix the target design still requires.

### 2. Disabled Profile Uses One Feature-Gate Rejection

For fixture cases that represent authored or runtime introduction of a closure
value while the feature is disabled, return:

- `runtime_closure_not_enabled`

Use this as the default for:

- authored closure-value attempts;
- synthetic runtime closure payload appearance in normal runtime channels;
- direct closure invocation attempts under the disabled profile.

### 3. Design-Fixture Profile Allows Specific Rejected Shapes

For fixture cases that intentionally test the future runtime-closure taxonomy
without enabling execution, return the more specific code required by the
fixture:

- `closure_dynamic_code_forbidden`
- `closure_provider_capture_forbidden`
- `closure_capture_mode_forbidden`
- `closure_capture_schema_invalid`
- `closure_runtime_transport_forbidden`
- `closure_effect_bound_invalid`
- `closure_capability_bound_invalid`
- `closure_write_root_ambiguous`
- `closure_resume_bundle_mismatch`
- `closure_resume_code_mismatch`
- `closure_source_map_missing`

The validator stays non-executable:

- it validates only the rejected shape;
- it never constructs an executable closure registry;
- it never lowers to executable IR;
- it never stores closure payloads in build outputs.

### 4. Artifact Leakage Guard

Extend ordinary build-artifact omission tests so compiled frontend bundles keep
proving that the disabled profile is real.

Normal compiled artifacts should not contain:

- `workflow_lisp_runtime_closure`
- `closure_families`
- `InvokeClosure`
- `Closure[`
- `runtime_closure`

This is the artifact-level companion to the fixture validator. Together they
prove both:

- rejected closure shapes can be tested; and
- accepted builds still do not emit closure surfaces by accident.

## Fixture Taxonomy

The disabled-profile suite should cover at least one rejected fixture for each
required class named by the selected design gap:

1. Runtime closure value introduction
   - runtime `ProcRef` stored in state remains rejected through the existing
     ProcRef transport path.
   - a synthetic runtime-closure value fixture returns
     `runtime_closure_not_enabled`.
2. Compile-time surface confusion
   - `let-proc` compiled to a runtime closure is rejected by the fixture
     harness, keeping `let-proc` compile-time-only.
3. Dynamic identity production
   - provider-produced closure or code identity returns
     `closure_dynamic_code_forbidden`.
   - command-produced closure or code identity returns
     `closure_dynamic_code_forbidden`.
4. Runtime transport
   - closure stored in an artifact returns
     `closure_runtime_transport_forbidden`.
   - closure exported as a workflow output returns
     `closure_runtime_transport_forbidden`.
5. Capture rejection
   - provider-role/capability capture returns
     `closure_provider_capture_forbidden`.
   - mutable-state capture or capture-of-closure returns
     `closure_capture_mode_forbidden` or
     `closure_capture_schema_invalid`, depending on the modeled violation.
6. Invocation-site validation
   - invocation without an accepted family returns
     `runtime_closure_not_enabled` under the disabled profile and may use
     `closure_capability_bound_invalid` / `closure_effect_bound_invalid` in
     design-fixture-only cases.
   - ambiguous write-root policy returns `closure_write_root_ambiguous`.
7. Resume and source-map rejection
   - mismatched executable bundle id returns `closure_resume_bundle_mismatch`.
   - mismatched code id returns `closure_resume_code_mismatch`.
   - missing creation/invocation source-map data returns
     `closure_source_map_missing`.

The matrix stays intentionally negative-only in this slice. There are no
positive executable runtime-closure fixtures yet.

## Testing Strategy

### Focused Tests

Add one dedicated test module that loads fixture cases and asserts:

- expected diagnostic code;
- stable serialization and rendered-message fragments;
- no case produces an executable closure object, registry, or invocation node.

Recommended coverage:

- `tests/test_workflow_lisp_runtime_closure_fixtures.py`

### Existing Regression Surfaces To Extend

- `tests/test_workflow_lisp_build_artifacts.py`
  - assert no closure registry/value markers appear in emitted frontend
    artifacts.
- `tests/test_workflow_semantic_ir.py`
  - extend the current compile-time-erasure assertions from `ProcRef` and
    `WorkflowRef` to closure-family and invocation markers.
- `tests/test_workflow_lisp_workflows.py`
  - keep existing ProcRef transport tests unchanged so closure fixtures do not
    weaken current callable transport guarantees.

### Acceptance Signals

This slice is complete only when:

- the fixture suite covers every forbidden-shape class selected by the gap;
- closure-specific diagnostics are stable and serialized consistently;
- normal Workflow Lisp build artifacts still contain no closure payload markers;
- no new executable IR node kind, runtime closure registry, or runtime closure
  transport path has been introduced.

## Verification Expectations

The follow-on implementation for this slice should verify at least:

- the drafted architecture, context, check-command list, and draft bundle exist
  at the prescribed paths;
- the implementation architecture includes the required
  `Relationship To Existing Implementation Architectures` section;
- the work-item context records
  `docs/design/workflow_command_adapter_contract.md` in authoritative inputs;
- the draft bundle points at the selected runtime-closure-disabled-profile
  paths;
- the architecture names a fixture-only validator and explicit no-runtime
  artifact leakage checks.
