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
fresh .orc source or a supported persisted compatibility bundle
  -> Workflow Lisp WCC/schema-2 lowering or state-only compatibility loading
  -> Core Workflow AST
  -> shared validation and lowering
  -> validated ExecutableWorkflow
  -> derived runtime-plan and semantic projections
  -> existing runtime
```

Workflow Lisp lowers through WCC/schema 2 into the shared loaded-bundle
boundary. Fresh authored execution is `.orc`-only; completed legacy runs may
remain observable through state-only compatibility without reopening an
authored source frontend. The frontend does not bypass this layer, and it does
not compile directly into executor-owned state.

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

Provider execution configuration may contain an optional typed
`CompilerPromptDependencyContract` alongside ordinary `depends_on` data. The
contract is produced only by the Workflow Lisp owner emitter and remains in the
compiler side table keyed by stable provider-step identity until bundle
assembly reconciles it with the exact provider-step set. Core, executable,
persisted, and lexical-checkpoint surfaces then retain their owned typed field.
Executable validation rejects an untyped mapping as an alternative
representation.

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

The inventory includes `ExecutableNodeKind.PROVIDER_SUPERVISION` with
`ProviderSupervisionStepConfig` and required node-local schema
`provider_supervision.v1`. The config contains exactly one worker and one
supervisor, their immutable provider configs, one supervisor-to-worker
observation edge, worker and compiler-owned directive contracts, a validated
pure settlement payload/result contract, bounded deadlines, `max_steers: 1`,
and visit/member/turn-qualified evidence and provisional-bundle paths.
Executable validation checks the complete typed config, structural worker
resume capability, exact directive contract, generated paths, and settlement
contract before runtime use.

The inventory also includes the distinct
`ExecutableNodeKind.PROVIDER_PEER_GROUP` with
`ProviderPeerGroupStepConfig` and required node-local schema
`provider_peer_group.v1`. Its closed config contains:

- an authored-order tuple of two through eight immutable member provider
  configs, result contracts, and positive timeouts;
- `messaging_policy: all_other_members`;
- one validated pure settlement payload and result contract;
- the required `interactive_terminal_turn_queue.v1` capability version;
- generated visit/member prompt, message-ledger, evidence, and provisional
  bundle paths;
- exact source ownership for the form, members, and settlement; and
- `max_steers: 0`.

Executable validation checks the complete member set and order, result
contract identities, settlement bindings, generated paths, capability
requirement, timeout relation, source ownership, policy, and zero-steer
boundary before runtime use. The endpoint instance, opaque sender bindings,
interactive handles, and message contents are per-visit runtime data and do
not enter executable IR or checkpoint identity.

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

This contract therefore narrows the boundary: fresh `.orc` compiles and
supported persisted compatibility bundles become executable authority only
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

For provider prompt dependencies, `runtime_plan` remains topology/checkpoint
planning only. It intentionally omits exact relpath operands, required/optional
roles, injection position/instruction, snapshot metadata, evidence records,
and the compiler contract itself. Semantic IR and source maps may explain the
validated executable contract, while per-attempt state/evidence may describe
an invocation; none replaces executable authority.

For provider supervision, runtime-plan and Semantic-IR derivation expose one
composite node with two initial member invocations, one observation edge, an
optional bounded worker-resume transition, and one atomic settlement/result
boundary. Member panes, display streams, transcripts, cancellation evidence,
and provisional bundles are not alternate executable or result authorities.

For provider peer groups, runtime-plan and Semantic-IR derivation expose one
composite authored-order node with two through eight initial member
invocations, the closed all-other-members messaging policy, the interactive
capability requirement, member/result contracts, pure settlement, and one
atomic result boundary. Source maps retain exact form/member/settlement and
prompt-dependency ownership. The runtime endpoint, opaque credentials, client
panes, ledger rows, and provisional bundles remain attempt/visit state or
evidence, never competing executable or result authority.

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
- `tests/test_workflow_lisp_materialize_view_runtime.py` provides current
  evidence that generated `materialize_view` nodes serialize into executable
  IR, render deterministic bytes, and fail closed on resume drift.
- `tests/test_workflow_lisp_resource_transition_runtime.py` provides current
  evidence that generated `resource_transition` nodes serialize into executable
  IR, execute through the runtime, and expose the expected runtime-view debug
  metadata.
- `tests/test_provider_supervision_ir.py`,
  `tests/test_provider_supervision_runtime.py`,
  `tests/test_provider_supervision_resume.py`,
  `tests/test_workflow_lisp_provider_supervision.py`, and the deterministic
  and real provider-supervision E2E modules provide current evidence for the
  typed composite node, coordinator-owned settlement, bounded resume, build
  projections, and live provider boundary.
- `tests/test_provider_peer_group_ir.py`,
  `tests/test_provider_peer_group_runtime.py`,
  `tests/test_provider_peer_group_resume.py`,
  `tests/test_workflow_lisp_provider_peer_group.py`,
  `tests/test_workflow_lisp_provider_peer_group_e2e.py`, and
  `tests/e2e/test_e2e_provider_peer_delivery.py` provide current evidence for
  the closed peer-group node, target-`2.17` WCC route, executable/build
  projections, attempt-bound protocol and ledgers, atomic settlement,
  interruption quarantine, real queued delivery, and natural cleanup.

Those artifacts are durable evidence for the implemented layer; they do not
change the rule that validated executable IR is the authority and the other
outputs are derived views.

## Out Of Scope

Beyond the current inventory, this document does not define additional
executable node kinds, validator behavior, runtime closures, dynamic dispatch,
runtime-native effect expansion, or a direct frontend-to-executable lowerer
that bypasses shared validation.

Future executable extensions require their own reviewed contract. They must
not be implied by this document merely because adjacent code or planning
artifacts mention possible future directions.
