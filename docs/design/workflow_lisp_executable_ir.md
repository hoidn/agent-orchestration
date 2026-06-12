# Workflow Lisp Executable IR

Status: current-checkout component contract  
Scope: shared executable-layer authority implemented in this repository for Workflow Lisp and imported workflow bundles

## Purpose

This document records the durable executable-layer contract that the current
checkout already implements. It describes the shared runtime-facing boundary
used after Core AST and shared validation, without reopening frontend syntax,
runtime execution ownership, or future executable extensions that are not yet
accepted. Workflow Lisp now reaches this layer through WCC/schema-2
defunctionalization into the flat Core AST; legacy schema-1/direct per-form
lowering is compatibility-only when explicitly selected.

## Authority Boundary

The executable authority surface is validated executable IR.

In current code, that means `LoadedWorkflowBundle.ir` containing an
`ExecutableWorkflow` validated by `validate_executable_workflow(...)` against
`WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION`.

This layer is authoritative for executable structure. It is not a debug-YAML
projection, a rendered runtime-plan summary, or a prose explanation of what a
workflow "means." Structured executable data is authority; reports and
projections are views.

## Relationship To Adjacent Layers

The current shared pipeline is:

```text
frontend source / YAML surface
  -> frontend-specific loading or Workflow Lisp WCC/schema-2 lowering
  -> Core Workflow AST
  -> shared validation and lowering
  -> validated ExecutableWorkflow
  -> derived runtime-plan and semantic projections
  -> existing runtime
```

Workflow Lisp lowers through WCC/schema 2 into the same shared bundle boundary
as imported YAML workflows. The frontend does not bypass this layer, and it
does not compile directly into executor-owned state.

## Current Executable Surface

The current executable contract is anchored in
`orchestrator/workflow/executable_ir.py` and related bundle assembly code:

- `ExecutableWorkflow` is the typed executable payload.
- `WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION` version-tags the contract.
- `workflow_executable_ir_to_json(...)` serializes the executable artifact for
  durable build output.
- `validate_executable_workflow(...)` enforces the executable schema and
  structural invariants before the bundle is treated as runnable.
- `LoadedWorkflowBundle.ir` exposes the validated executable payload as the
  executable field of the shared loaded-bundle contract.

This surface contains executable nodes, resolved command/provider boundaries,
state-projection linkage, materialization actions, routing structure, and the
other runtime-facing data needed for downstream derivations. It no longer
contains macros, unresolved procedures, or frontend-only type forms.

The current executable-node inventory also includes
`ExecutableNodeKind.PURE_PROJECTION` with `PureProjectionStepConfig`. That node
kind executes one validated pure-expression payload against resolved binding
refs, validates flattened output contracts, and commits a private generated
bundle that can be reused on resume when payload digest and schema version
match.

It also includes `ExecutableNodeKind.RESOURCE_TRANSITION` with
`ResourceTransitionStepConfig`. That node kind is compiler-generated only: the
runtime receives a validated transition declaration payload, resolved resource
metadata, resolved request bindings, and optional expected-version binding, then
owns version checks, idempotent replay, audit append, and resume semantics.

## Validation Ownership

Executable IR validation is owned by the shared workflow layer, not by ad hoc
frontend checks or runtime guesswork.

The current ownership checkpoints are:

- lowering validates executable IR before deriving adjacent layers;
- loaded-bundle assembly keeps `LoadedWorkflowBundle.ir` as the validated
  executable authority;
- the Workflow Lisp compiler revalidates linked `bundle.ir` during the
  frontend `executable` pass rather than treating prior artifacts as trusted
  by convention alone.

This contract therefore narrows the boundary: workflows may arrive from
different authoring surfaces, but executable authority is recognized only
after shared executable validation succeeds.

## Derived Layers

Several nearby artifacts are important, but they are derived layers rather
than competing authorities:

- `derive_workflow_runtime_plan(...)` produces `runtime_plan` as a
  deterministic runtime-facing summary over validated executable IR and state
  projection.
- `derive_workflow_semantic_ir(...)` produces `semantic_ir` as the typed,
  explanation-friendly semantic projection for diagnostics, provenance, and
  analysis.
- `source_map` is a traceability artifact linking authored forms and generated
  executable structure.
- `workflow_boundary_projection` is a build/debug projection for workflow
  boundary understanding.
- debug YAML is an optional view, not executable authority.

These layers may summarize, enrich, or explain executable structure, but they
do not redefine what the runtime-facing executable contract is.

## Command Boundary Constraints

Executable command and provider boundaries remain governed by
[Workflow Command Adapter Contract](workflow_command_adapter_contract.md).

This document does not create a second command-semantics authority. Command
and provider semantics are not inferred from shell text, heredocs, or inline
glue. When executable IR records a command boundary, the meaning and allowed
semantic load of that boundary still comes from the command-adapter contract
and the shared runtime/code paths that implement it.

## Runtime-Value Erasure

Executable/runtime artifacts must contain only runtime-executable values.

Compile-time-only values such as unresolved procedure references, `let-proc`
metadata, syntax objects, source spans, and other frontend-only structures
must not survive into `ExecutableWorkflow`, `LoadedWorkflowBundle.ir`, or the
serialized executable artifact.

This preserves the current Workflow Lisp rule that authoring-time helpers
compile away before runtime artifacts are produced.

## Build Artifacts And Evidence

The current checkout emits durable executable-layer evidence through the
Workflow Lisp build path:

- `orchestrator/workflow_lisp/build.py` writes `executable_ir.json`,
  `runtime_plan.json`, `semantic_ir.json`, `source_map.json`, and
  `workflow_boundary_projection.json`.
- `workflow_executable_ir_to_json(...)` is the serializer used for the
  executable artifact.
- tests in `tests/test_workflow_ir_lowering.py`,
  `tests/test_workflow_lisp_build_artifacts.py`, and
  `tests/test_workflow_lisp_diagnostics.py` provide the current repo evidence
  for schema/version locking, emitted artifacts, and executable-pass
  revalidation behavior.
- `tests/test_runtime_step_lifecycle.py` and
  `tests/test_workflow_lisp_pure_projection_runtime.py` provide current
  evidence that runtime views expose `pure_projection` and that resume reuses
  only schema/digest-compatible projection bundles.
- `tests/test_workflow_lisp_resource_transition_runtime.py` provides current
  evidence that generated `resource_transition` nodes serialize into executable
  IR, execute through the runtime, and expose the expected runtime-view debug
  metadata.

Those artifacts are durable evidence for the implemented layer; they do not
change the rule that validated executable IR is the authority and the other
outputs are derived views.

## Out Of Scope

This document does not define new executable node kinds, new validator
behavior, runtime closures, dynamic dispatch, runtime-native effect expansion,
or a direct frontend-to-executable lowerer that bypasses shared validation.

Future executable extensions require their own reviewed contract. They must
not be implied by this document merely because adjacent code or planning
artifacts mention possible future directions.
