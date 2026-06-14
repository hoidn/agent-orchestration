# Workflow Lisp Private Runtime Value Flow R3 Effect-Boundary Resume Policies Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-private-runtime-state-and-consumer-value-flow-r3-effect-boundary-resume-policies`
Target design: `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected R3 gap:

- attach explicit, enforced resume-policy metadata to every generated effect
  boundary that can emit a private lexical checkpoint point;
- cover the target R3 boundary families: pure projection, provider call,
  command or certified adapter, workflow call, materialized view, and resource
  transition;
- replace R1's provisional `shadow_record_only` effect-policy field with a
  versioned policy envelope that can be validated in checkpoint points,
  checkpoint records, Semantic IR / runtime-plan projections, and restore
  decisions;
- allow R2 restore to cross only completed effect boundaries whose policy and
  evidence prove reuse, regeneration, idempotent replay, or fail-closed
  behavior; and
- add runtime enforcement that rejects unsafe pending command/provider/external
  effects instead of silently rerunning them.

Out of scope for this slice:

- transition-aware replay beyond requiring transition policies to point at
  transition idempotency/audit evidence; full audit reconciliation and conflict
  handling remain R4;
- deleting or hiding resume-only authored plumbing from public boundaries,
  records, loop state, or call signatures;
- Track C consumer-side rendering, entrypoint publication policy, bridge
  metadata, prompt rendering, or observability summaries;
- changing provider or command structured-output authority;
- adding command adapters, scripts, inline shell/Python glue, or legacy adapter
  behavior;
- changing public workflow APIs or migration promotion thresholds; and
- redefining WCC, Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, variant proof, or resource
  transition semantics.

This is an implementation architecture for one selected design gap only. It is
not a replacement runtime resume specification and it does not complete Track R.

## Problem Statement

U0 classified path plumbing, R1 added private checkpoint point and record
schemas, and R2 added restore for pure and structured regions while treating
effect boundaries as barriers. The current checkout still exposes effect policy
as provisional checkpoint metadata:

- `orchestrator/workflow_lisp/lexical_checkpoints.py` accepts only
  `shadow_record_only` as a provisional checkpoint policy.
- R2 restore rejects unsafe pending effects, but it has no typed policy model
  for deciding when a completed provider, command, workflow call, materialized
  view, or transition boundary can be reused, regenerated, or treated as a
  hard barrier.
- `RuntimeLexicalCheckpointPoint.details` can carry arbitrary point details,
  but there is no enforced effect-policy schema tied to the runtime plan,
  Semantic IR, executable step family, and structured-output evidence.
- Provider and command boundaries already have structured-output contracts, and
  materialized views already have renderer/input digests, but R2 does not use a
  policy envelope to prove that evidence before a restore decision crosses an
  effect boundary.
- Resource transitions must not be blindly replayed. R3 should require a
  transition policy with idempotency/audit references, but leave full replay
  and conflict reconciliation to R4.

The gap is therefore not new authoring syntax. It is an enforcement layer that
makes each generated effect boundary's resume behavior explicit, typed,
source-mapped, and fail-closed.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
  Sections 7.3, 7.4, 7.5, 9 R3, 11, 12, 13, 15, and 16;
- `docs/design/workflow_lisp_frontend_specification.md` Sections 10.2, 16,
  17.1, 18.1, 20, 22, 23, 29, 45, 47, 48, 49, 59, 61, 62, 72, 74, and 105.1;
- `docs/design/workflow_command_adapter_contract.md` for command, certified
  adapter, legacy adapter, structured validator adapter, and runtime-native
  promotion policy;
- `docs/design/workflow_lisp_core_calculus_middle_end.md` for WCC effect-row
  and program-point identity vocabulary;
- `docs/design/workflow_lisp_state_layout.md` for generated path allocation
  ownership;
- `docs/design/workflow_lisp_runtime_migration_foundation.md` for provider and
  command structured-output target binding, private value transport, and
  fail-closed output contracts;
- the U0 shared-census architecture;
- the R1 checkpoint schema/shadow-emission architecture; and
- the R2 pure/structured restore architecture.

Guardrails:

- Checkpoints remain private runtime cache and never become semantic authority.
- Typed values, structured bundles, resources, and transition audit remain the
  semantic ledgers.
- Policy metadata must describe how existing semantic evidence is reused or why
  reuse is forbidden; it must not replace provider/command output validation,
  transition audit, or materialized-view renderer validation.
- Command and certified-adapter policies must be generated from declared
  command boundaries and structured output contracts. They must not parse
  stdout, reports, pointer files, or inline command text.
- Provider reuse requires validated structured-output evidence at the declared
  runtime-owned bundle target; wrong-path bundles and stdout JSON remain
  invalid.
- Workflow-call reuse requires the callee's validated terminal state and
  compatible call identity; it does not introduce dynamic workflow loading.
- Materialized-view handling may regenerate deterministic views from typed
  values unless the policy marks bytes as durable publication that must be
  preserved.
- Transition policies may require idempotency keys and audit evidence in R3,
  but R4 owns replaying committed transition results and invalidating
  checkpoints on resource conflicts.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-u0-shared-census/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r1-checkpoint-schema-shadow-emission/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r2-restore-for-pure-and-structured-regions/implementation_architecture.md`

### Decisions Reused

- Reuse U0's separation between target value-flow classes and baseline
  boundary authority classes. R3 policies are checkpoint/runtime metadata, not
  public authored inputs or workflow outputs.
- Reuse R1 schema versions and checkpoint identity:
  `workflow_lisp_lexical_checkpoint.v1`,
  `workflow_lisp_lexical_checkpoint_points.v1`, checkpoint ids,
  program-point ids, source-map origin keys, binding schema digests, storage
  allocation ids, and private sidecar storage roles.
- Reuse R1's `RuntimeLexicalCheckpointPoint` bridge from WCC lowering into the
  runtime plan and build artifacts.
- Reuse R2's restore payload and restore decision model. R3 widens what a
  restore selector can cross only when a completed effect boundary has a valid
  policy envelope and required evidence.
- Reuse `orchestrator/workflow_lisp/lexical_checkpoints.py` as the checkpoint
  schema owner and add a small policy-focused helper module rather than
  creating a parallel checkpoint system.
- Reuse current provider/command structured-output validators and runtime-owned
  bundle target rules as the authority for provider and command reuse.
- Reuse the command-adapter contract's rule that command semantics must be
  declared, fixture-tested, source-mapped, and visible in effects.

### New Decisions In This Slice

- Add a versioned effect-policy envelope:
  `workflow_lisp_effect_resume_policy.v1`.
- Add policy kinds:
  `recompute_or_reuse_checkpoint`, `reuse_validated_structured_output`,
  `reuse_validated_workflow_call`, `regenerate_deterministic_view`,
  `preserve_durable_view`, `transition_idempotent_audit_required`,
  `fail_closed_non_idempotent`, and `certified_resume_protocol_required`.
- Add a policy decision result used by restore planning:
  `REUSABLE`, `REGENERATE`, `BARRIER`, or `INVALID`.
- Replace `PROVISIONAL_POLICIES = {"shadow_record_only"}` with backward
  compatibility that treats old R1/R2 records as valid but not policy-enforced
  unless they carry the new policy envelope.
- Add completed-effect evidence references to checkpoint records for provider,
  command, workflow-call, materialized-view, and transition boundaries.
- Require policy digests to include effect kind, executable step id, output
  contract or renderer/transition identity, source-map origin, and evidence
  requirements.
- Make unsafe pending command/certified-adapter/external effects fail closed
  unless the command boundary declares a certified resume protocol.

### Conflicts Or Revisions

R1 explicitly marked effect policy metadata as provisional and limited
validation to `shadow_record_only`. R3 revises that provisional decision by
making effect policies versioned, typed, and enforced. Old R1/R2 records remain
valid checkpoint records for historical/shadow evidence, but restore selection
treats them as barriers or `NOT_RESTORABLE` when the selected boundary requires
R3 policy evidence.

R2 rejected pending provider/command/workflow/view/transition replay as unsafe.
R3 narrows that blanket barrier only for completed boundaries with policy
evidence. It still does not authorize blind rerun of non-idempotent effects.

No shared concepts are redefined. Core Workflow AST, Semantic Workflow IR,
Executable IR, TypeCatalog, SourceMap, pointer authority, variant proof,
provider/command output authority, and transition execution remain with their
existing component docs and modules.

## Ownership Boundaries

This slice owns:

- a new helper module such as
  `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py` for
  policy schema constants, policy construction, stable digesting, validation,
  and policy decision evaluation;
- additive changes in `orchestrator/workflow_lisp/lexical_checkpoints.py` to
  validate new policy envelopes, compute policy digests, write completed effect
  refs, and keep old provisional records non-restorable where needed;
- additive WCC/defunctionalization metadata that maps generated effect
  boundaries to policy families;
- build-artifact serialization of public-safe policy summaries in
  `lexical_checkpoint_points.json` and private full policy details in runtime
  sidecar records;
- runtime hooks in `WorkflowExecutor`, `LoopExecutor`, and restore planning
  that evaluate policy decisions before crossing completed or pending effect
  boundaries;
- diagnostics and reports for invalid, missing, stale, or unsafe policies; and
- focused tests for policy schema validation, build artifact emission, runtime
  enforcement, provider/command evidence, workflow-call evidence,
  materialized-view regeneration/preservation, transition policy barriers, and
  unsafe command replay rejection.

This slice intentionally does not own:

- command-adapter certification rules, adapter manifests, or adapter
  implementation;
- provider/command output validation internals;
- resource transition execution, idempotency implementation, audit replay, or
  resource conflict reconciliation beyond requiring policy evidence;
- public workflow boundary cleanup;
- consumer-side rendering or publication policy;
- migration promotion gates or primary-surface selection;
- generated path naming beyond consuming existing `StateLayout` allocations;
- Core Workflow AST, Semantic Workflow IR, Executable IR, TypeCatalog,
  SourceMap, pointer authority, or variant-proof redefinition; or
- repo-wide strict lint enforcement.

## Proposed Data Model

### Effect Resume Policy Envelope

Each effect-boundary checkpoint point carries a policy envelope:

```json
{
  "schema_version": "workflow_lisp_effect_resume_policy.v1",
  "policy_kind": "reuse_validated_structured_output",
  "effect_kind": "provider_call",
  "boundary_kind": "provider",
  "step_id": "root.review.provider_result",
  "source_map_origin_key": "source:...",
  "evidence_requirements": {
    "structured_output": {
      "bundle_path_ref": "generated:provider_result_bundle",
      "contract_digest": "sha256:...",
      "payload_digest_required": true,
      "declared_target_only": true
    }
  },
  "unsafe_pending_behavior": "fail_closed",
  "policy_digest": "sha256:..."
}
```

The envelope is part of the checkpoint point payload. The checkpoint record
stores the same digest in `validity_envelope.effect_policy_digest` and may
store private completed-effect refs that satisfy the envelope.

### Policy Kinds

Canonical policy kinds for R3:

- `recompute_or_reuse_checkpoint`: pure projection may recompute from a
  deterministic payload or reuse a valid private checkpoint payload.
- `reuse_validated_structured_output`: provider or command boundary may reuse
  only a validated `output_bundle` or `variant_output` at the declared runtime
  target with matching contract and payload digest.
- `reuse_validated_workflow_call`: workflow call may reuse only a validated
  callee terminal result for the same callee identity, call inputs digest,
  call-frame identity, and workflow version policy.
- `regenerate_deterministic_view`: materialized view may be regenerated from
  typed value, renderer id/version, and input digest.
- `preserve_durable_view`: materialized view may not be regenerated when the
  publication/bridge policy requires preserving existing bytes.
- `transition_idempotent_audit_required`: resource transition cannot be crossed
  unless the transition declaration, idempotency key, and audit reference are
  present. R3 treats missing evidence as a barrier; R4 owns committed-result
  replay.
- `fail_closed_non_idempotent`: external or unsafe effect cannot be replayed or
  crossed from checkpoint restore.
- `certified_resume_protocol_required`: command/certified adapter may be
  crossed only if the command boundary declares a typed resume protocol and the
  runtime has matching evidence.

### Completed Effect Reference

Checkpoint records may add `completed_effect_refs`:

```json
{
  "effect_ref_schema_version": "workflow_lisp_completed_effect_ref.v1",
  "effect_kind": "command_call",
  "step_id": "root.validate_plan",
  "status": "completed",
  "evidence_kind": "validated_output_bundle",
  "evidence_path": ".orchestrate/runs/.../bundles/validate_plan.json",
  "contract_digest": "sha256:...",
  "payload_digest": "sha256:...",
  "source_map_origin_key": "source:..."
}
```

Rules:

- Provider and command refs require structured bundle validation evidence. Stdout
  and stderr never satisfy the policy.
- Workflow-call refs require callee identity, input digest, terminal result
  digest, and version-policy compatibility.
- Materialized-view refs require renderer id, renderer version, input value
  digest, output path, and durability mode.
- Transition refs require transition identity, resource id, idempotency key, and
  audit pointer/digest. R3 validates presence and shape only; R4 owns replaying
  the committed transition result.

### Policy Decision

The restore planner evaluates a policy into:

```json
{
  "decision": "REUSABLE",
  "policy_kind": "reuse_validated_structured_output",
  "checkpoint_id": "ckpt:...",
  "step_id": "root.review.provider_result",
  "evidence_refs": ["effect-ref:..."],
  "diagnostics": []
}
```

Allowed decisions:

- `REUSABLE`: evidence proves the completed boundary may be crossed without
  rerunning it.
- `REGENERATE`: deterministic view or pure projection may be regenerated from
  typed inputs under its policy.
- `BARRIER`: the boundary is valid but not crossable in this restore attempt.
- `INVALID`: the policy or evidence is stale, malformed, source-map
  incompatible, digest-mismatched, or unsafe.

## Policy Mapping By Boundary

### Pure Projection

Policy: `recompute_or_reuse_checkpoint`.

Evidence:

- pure-expression payload digest;
- result schema digest;
- private bundle or inline restore payload digest.

Runtime behavior:

- recompute or reuse deterministic checkpoint payload;
- fail closed on schema/payload drift.

### Provider Call

Policy: `reuse_validated_structured_output`.

Evidence:

- declared provider output bundle or variant-output path;
- output contract digest;
- validated payload digest;
- prompt/input contract digest where available;
- declared target binding evidence.

Runtime behavior:

- reuse only validated structured output at the declared runtime target;
- fail closed on missing, wrong-path, invalid, or stdout-only output.

### Command Or Certified Adapter

Policy: `reuse_validated_structured_output`,
`certified_resume_protocol_required`, or `fail_closed_non_idempotent`.

Evidence:

- command-boundary manifest entry for command or certified adapter;
- behavior class and owner module;
- declared structured output bundle or variant-output validation evidence;
- optional typed resume protocol declaration.

Runtime behavior:

- cross completed command boundaries only with declared structured output
  evidence;
- require a certified resume protocol for pending/non-idempotent adapters;
- reject inline Python/shell, report parsing, pointer-as-state, and stdout JSON
  as resume authority.

### Workflow Call

Policy: `reuse_validated_workflow_call`.

Evidence:

- callee identity and target DSL/version policy;
- call input digest;
- call-frame identity;
- validated terminal result digest;
- source-map origin of call site.

Runtime behavior:

- cross only completed calls with compatible identity and terminal state;
- do not load or dispatch workflow code dynamically from checkpoint data.

### Materialized View

Policy: `regenerate_deterministic_view` or `preserve_durable_view`.

Evidence:

- renderer id and version;
- typed input value digest;
- output path and authority class;
- durability mode: ephemeral/view versus durable publication/bridge.

Runtime behavior:

- regenerate deterministic views when policy permits;
- preserve durable bytes or fail closed when publication/bridge policy requires
  byte stability.

### Resource Transition

Policy: `transition_idempotent_audit_required`.

Evidence:

- transition identity;
- resource identity and observed version;
- idempotency key;
- transition audit reference/digest.

Runtime behavior:

- do not replay as a blind command;
- treat missing audit/idempotency evidence as a barrier or invalid policy;
- leave committed-result replay and resource-conflict invalidation to R4.

## Runtime Flow

1. WCC defunctionalization classifies each generated effect boundary and
   attaches an R3 policy envelope to the checkpoint point payload.
2. Build artifact serialization emits public-safe policy summaries in
   `lexical_checkpoint_points.json` and validates policy digests.
3. Runtime shadow/restore emission records completed-effect refs only after the
   underlying effect has already committed its normal semantic state.
4. `validate_checkpoint_record` checks that the record's policy digest matches
   the current point catalog and that completed-effect refs satisfy the policy
   schema.
5. `ResumePlanner` and the lexical restore selector evaluate policy decisions
   before crossing an effect boundary.
6. For `REUSABLE`, the restore selector may fast-forward over the completed
   boundary and hydrate bindings from the validated semantic evidence.
7. For `REGENERATE`, the executor reruns only deterministic view/projection
   regeneration permitted by policy.
8. For `BARRIER`, existing step-granular resume behavior remains the fallback
   when safe.
9. For `INVALID`, resume fails closed with diagnostics rather than silently
   reusing or rerunning the effect.

No workflow output, artifact publication, resource transition, provider call,
command call, or typed workflow input may read checkpoint policy sidecars as
semantic input.

## Validation And Diagnostics

R3 reuses R1/R2 checkpoint diagnostics and adds stable policy diagnostics:

- `lexical_checkpoint_effect_policy_missing`
- `lexical_checkpoint_effect_policy_schema_invalid`
- `lexical_checkpoint_effect_policy_digest_mismatch`
- `lexical_checkpoint_effect_policy_unknown_kind`
- `lexical_checkpoint_effect_policy_boundary_mismatch`
- `lexical_checkpoint_effect_policy_evidence_missing`
- `lexical_checkpoint_effect_policy_evidence_stale`
- `lexical_checkpoint_effect_policy_structured_output_invalid`
- `lexical_checkpoint_effect_policy_command_uncertified`
- `lexical_checkpoint_effect_policy_pending_effect_unsafe`
- `lexical_checkpoint_effect_policy_transition_audit_missing`
- `lexical_checkpoint_effect_policy_materialized_view_mismatch`
- `lexical_checkpoint_effect_policy_used_as_semantic_authority`

Validation fails closed on:

- policy envelope missing from a new R3 checkpoint point;
- unknown policy kind or effect kind;
- policy digest mismatch between point catalog and checkpoint record;
- completed-effect ref whose step id, effect kind, contract digest,
  payload digest, source-map origin, or authority class does not match the
  policy;
- provider/command policy satisfied only by stdout, stderr, a markdown report,
  a pointer file, or a wrong-path bundle;
- command/certified-adapter policy without command-boundary evidence;
- pending external or non-idempotent effect without certified resume protocol;
- materialized view consumed as typed semantic input; and
- transition policy without idempotency/audit evidence.

Warnings may be appropriate for old R1/R2 records that are valid but lack R3
policy envelopes. Such records must not be treated as reusable across effect
boundaries.

## Implementation Plan Shape

The later execution plan should keep this slice in six bounded steps:

1. Add effect-policy schema helpers.
   Create `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py`
   with schema constants, canonical serialization, policy digesting,
   validation, and policy decision objects.

2. Generate policy envelopes for checkpoint points.
   Extend WCC defunctionalization/checkpoint point payload construction to map
   each generated effect family to the correct policy kind and evidence
   requirements.

3. Extend checkpoint record emission and validation.
   Add completed-effect refs and policy validation to
   `orchestrator/workflow_lisp/lexical_checkpoints.py`, keeping old
   provisional records valid but non-restorable across R3-governed boundaries.

4. Wire policy decisions into restore planning.
   Integrate policy evaluation with the R2 restore selector, `ResumePlanner`,
   `WorkflowExecutor`, and `LoopExecutor` so completed boundaries are crossed
   only with valid policy evidence and pending unsafe effects fail closed.

5. Emit policy evidence in build/runtime artifacts.
   Add public-safe policy summaries to `lexical_checkpoint_points.json` and
   private decision/report details under the checkpoint sidecar tree. Preserve
   route-neutral public source maps.

6. Add focused fixtures and negative tests.
   Cover all target boundary families, old-record compatibility, provider
   wrong-path/missing-bundle evidence, command stdout-only rejection,
   uncertified adapter resume rejection, workflow-call identity drift,
   materialized-view renderer drift, transition audit missing, and
   checkpoint-policy-as-authority misuse.

## Feasibility Proof

Already-present seams make this slice feasible:

- R1 emits checkpoint point catalogs and private checkpoint records with policy
  digests, source-map origins, storage allocations, and runtime sidecar writes.
- R2 has restore payload validation, restore decisions, and resume-planner
  integration points that can consult a policy decision before crossing a
  boundary.
- WCC defunctionalization already sees `WccPerform` / `WccCall` effect
  boundaries and records checkpoint points after lowering effectful bindings.
- Runtime plan carries `RuntimeLexicalCheckpointPoint.details`, which can carry
  R3 policy summaries without changing public workflow boundaries.
- Provider and command structured-output paths already validate bundles and
  reject stdout as semantic output.
- Materialized views already record renderer id/version, input value document,
  generated target, and Semantic IR effects.
- Resource-transition lowering already distinguishes runtime-native transition
  surfaces from compatibility command adapters.

The unproven capability is not transition replay. The unproven R3 capability is
enforcing a policy/evidence decision at every generated effect boundary without
corrupting R2 restore or current step-granular resume. R3 must prove that with
narrow fixtures before R4 can consume transition audit for committed-result
replay.

## Verification Strategy

Focused checks for the implementation slice should include:

- unit tests for policy envelope serialization, digesting, validation, and
  stable diagnostics;
- WCC/build-artifact tests proving every generated effect-boundary checkpoint
  point carries policy metadata for pure projection, provider, command,
  workflow call, materialized view, and resource transition;
- Semantic IR/runtime-plan tests proving policy summaries align with effect
  graph entries, executable step ids, source-map origins, and command-boundary
  metadata;
- runtime tests proving provider reuse requires validated structured-output
  evidence at the declared target;
- runtime tests proving command/certified-adapter reuse rejects stdout-only,
  wrong-path, and uncertified pending-effect cases;
- runtime tests proving workflow-call reuse rejects callee/input/version drift;
- runtime tests proving materialized-view regeneration and durable-preserve
  policies choose the correct `REGENERATE`, `REUSABLE`, or `BARRIER` decision;
- runtime tests proving transition boundaries require idempotency/audit
  evidence and otherwise remain barriers for R4;
- negative tests for policy digest drift, missing source-map origin, stale
  payload digest, checkpoint policy used as semantic authority, and old
  provisional records crossing an R3-governed boundary; and
- one Design Delta parent drain compile/runtime resume smoke proving policy
  enforcement does not change public boundary projections, U0 census
  reconciliation, or migration parity outputs.

Because this slice changes resume behavior at effect boundaries, the execution
plan must include at least one runtime resume smoke check in addition to unit
tests. A full workflow promotion smoke is not required because R3 does not
change primary-surface selection.

## Handoff Notes

- Keep policies private/runtime-facing. Do not expose policy sidecars as
  workflow inputs, outputs, artifacts, pointer files, or compatibility bridges.
- Keep command and adapter resume semantics aligned with
  `docs/design/workflow_command_adapter_contract.md`.
- Prefer `BARRIER` over clever reuse when evidence is incomplete.
- Do not add scripts, command steps, or adapters for policy enforcement.
- Do not let provider/command stdout, markdown reports, pointer files, or
  materialized views satisfy typed semantic state.
- Leave resource-transition committed-result replay and conflict invalidation to
  R4.
- Treat old `shadow_record_only` checkpoints as historical/shadow-compatible,
  not as R3 reuse evidence.
