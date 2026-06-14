# Workflow Lisp Private Runtime Value Flow R3 Effect-Boundary Resume Policies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current provisional `shadow_record_only` checkpoint effect metadata with enforced R3 resume-policy envelopes and internal policy evaluation for generated effect boundaries, while keeping checkpoints private, fail-closed, and compatible with the reused R2 restore-decision/report surface.

**Architecture:** This slice stays inside the existing Workflow Lisp checkpoint and resume stack. WCC lowering continues to emit lexical checkpoint points, but each effect boundary now carries a typed `workflow_lisp_effect_resume_policy.v1` envelope that is preserved through runtime-plan, semantic-IR, and build-artifact projections, recorded into checkpoint sidecars with completed-effect evidence, and evaluated by restore planning before the runtime crosses a boundary. The new R3 vocabulary (`REUSABLE`, `REGENERATE`, `BARRIER`, `INVALID`) is an internal policy-evaluation layer; restore payloads, reports, and downstream consumers continue to use the reused R2 restore-decision surface. Completed pure/view/provider/command/workflow-call boundaries may become reusable or regenerable only when their policy and evidence match; transitions remain audit-gated barriers in R3, and uncertified or non-idempotent pending effects continue to fail closed.

**Tech Stack:** Workflow Lisp compiler/runtime Python modules under `orchestrator/workflow_lisp/` and `orchestrator/workflow/`, checked `.orc` fixtures, runtime sidecar state, `pytest`

---

## Scope

- Primary authorities:
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r3-effect-boundary-resume-policies/implementation_architecture.md`
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/drain/iterations/3/design-gap-architect/work_item_context.md`
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json`

- Additional required context:
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-u0-shared-census/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r1-checkpoint-schema-shadow-emission/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r2-restore-for-pure-and-structured-regions/implementation_architecture.md`

- Progress-ledger status:
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/progress_ledger.json` is empty in this checkout, so no later recorded event supersedes the selected R3 sequencing or scope.

- In scope for this plan:
- add a dedicated effect-policy helper module and schema version `workflow_lisp_effect_resume_policy.v1`;
- map each generated checkpointable effect boundary to one R3 policy kind covering pure projection, provider call, command or certified adapter, workflow call, materialized view, and resource transition;
- replace provisional `shadow_record_only` policy digests with typed policy digests that include boundary identity, evidence requirements, and source lineage;
- record and validate completed-effect evidence for reusable boundaries without making checkpoint sidecars semantic authority;
- evaluate internal policy decisions as `REUSABLE`, `REGENERATE`, `BARRIER`, or `INVALID` before lexical restore crosses a completed or pending effect boundary, then map them back onto the reused R2 restore-decision/report contract;
- keep historical R1/R2 checkpoint records readable but non-restorable across R3-governed boundaries unless they carry the new policy envelope;
- add focused build/runtime/resume tests and at least one runtime resume smoke proving policy enforcement changes effect-boundary restore behavior without changing public workflow boundaries.

- Explicitly out of scope:
- transition replay, transition conflict reconciliation, or committed-result recovery beyond requiring transition audit/idempotency evidence;
- public boundary cleanup from R5/R6, including deleting resume-only inputs or loop-state path fields;
- Track C consumer-side rendering, entrypoint `:publish`, bridge metadata, or observability summary migration;
- new scripts, inline shell/Python glue, uncertified command adapters, or command-adapter contract changes;
- provider/command structured-output validator redesign, output-bundle authority changes, or migration-promotion policy;
- redefinition of WCC, Core Workflow AST, Semantic IR, Executable IR, TypeCatalog, SourceMap, pointer authority, or variant-proof semantics beyond additive policy metadata.

## Implementation Architecture

### Unit 1: Policy Schema, Compatibility, And Decision Vocabulary

- Owns the typed policy model and backward-compatibility bridge from R1/R2 provisional metadata:
- Create: `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`

- Stable contract:
- one policy module owns schema constants, canonical serialization, digesting, validation, decision evaluation, and stable diagnostics;
- policy kinds are exactly the R3 vocabulary from the implementation architecture:
  `recompute_or_reuse_checkpoint`, `reuse_validated_structured_output`, `reuse_validated_workflow_call`, `regenerate_deterministic_view`, `preserve_durable_view`, `transition_idempotent_audit_required`, `fail_closed_non_idempotent`, and `certified_resume_protocol_required`;
- policy decisions are exactly `REUSABLE`, `REGENERATE`, `BARRIER`, or `INVALID` for internal evaluation, while restore payloads, reports, and downstream consumers keep the reused R2 restore-decision vocabulary;
- old records with only `shadow_record_only` remain valid shadow evidence but cannot satisfy R3 boundary reuse;
- policy helpers describe how existing semantic evidence is reused and never let checkpoint sidecars replace structured bundles, transitions, or typed values as authority.

### Unit 2: Lowering And Artifact Projection For Policy-Enriched Checkpoint Points

- Owns policy-envelope generation and public-safe projection of those envelopes:
- Create: `tests/fixtures/workflow_lisp/valid/lexical_checkpoint_effect_policies.orc`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_wcc_m4.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- Stable contract:
- every generated lexical checkpoint point for an effect boundary carries a fully formed R3 policy envelope and public-safe summary data;
- compiled artifacts stay route-neutral in public fields and continue to hide raw WCC route names and runtime-only evidence locations;
- the new focused fixture covers the missing R3 families that current checkpoint fixtures do not cover together, especially provider and resource-transition boundaries;
- runtime-plan and semantic-IR projections stay additive to the existing checkpoint bridges, expose only the information needed for validation and source-map lineage, and do not turn policy sidecars into semantic authority.

### Unit 3: Runtime Record Emission And Completed-Effect Evidence Capture

- Owns checkpoint-record persistence, evidence refs, and record validation:
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`

- Stable contract:
- runtime sidecar records store the policy digest plus completed-effect evidence refs only after the authoritative semantic effect has already committed;
- provider and command refs point only at declared validated bundles or variant outputs, never stdout, stderr, markdown, pointer files, or wrong-path bundles;
- workflow-call refs capture callee identity, input digest, and terminal result digest rather than dynamic loading data;
- materialized-view refs distinguish regenerable deterministic views from durable bytes that must be preserved;
- transition refs require transition identity, observed resource identity/version, idempotency key, and audit reference shape, but R3 still treats replay itself as future work.

### Unit 4: Restore-Path Enforcement And Fail-Closed Boundary Crossing

- Owns decision evaluation in the restore selector and executor resume flow:
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoint_restore.py`
- Modify: `tests/test_resume_command.py`

- Stable contract:
- the restore selector validates policy envelopes and evidence before it crosses any completed effect boundary;
- completed pure or view boundaries may become `REGENERATE` or `REUSABLE` only when the policy explicitly allows it;
- completed provider, command, and workflow-call boundaries become reusable only with matching validated evidence and identity digests;
- pending uncertified or non-idempotent effects fail closed instead of being silently rerun;
- transitions remain barriers in R3 unless their required audit/idempotency evidence is present, and even then the decision does not replay the transition result;
- restore reports record private policy decisions and diagnostics without changing workflow outputs or artifact contracts.

### Unit 5: Family-Level Proof And Regression Coverage

- Owns cross-surface proof that R3 changed effect-boundary restore behavior without widening public surfaces:
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_wcc_m4.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoint_restore.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- Stable contract:
- policy coverage exists for every R3 boundary family;
- build artifacts, runtime plan, Semantic IR, and source maps remain route-neutral, additive, and source-mapped after policy metadata lands;
- old provisional records are still parseable but cannot authorize boundary reuse;
- at least one resume smoke demonstrates that a failed run resumes through an R3-enforced boundary decision rather than through unconditional R2 behavior or blind rerun.

### Dependency Direction

- Unit 1 must land first because the policy schema, decision vocabulary, and backward-compatibility rules define every later interface.
- Unit 2 depends on Unit 1 because lowering and artifact projections must emit the canonical policy envelope and digest shape.
- Unit 3 depends on Units 1-2 because runtime sidecar records can only capture evidence against the finalized point payload and digest contract.
- Unit 4 depends on Units 1-3 because restore planning cannot evaluate or enforce decisions until policies and completed-effect refs exist.
- Unit 5 depends on Units 1-4 because the final proof needs the actual lowered metadata, sidecar evidence, and resume behavior.

### Sequencing Constraints

- Do not let checkpoint sidecars become workflow inputs, outputs, artifact values, pointer authority, or compatibility bridges.
- Do not satisfy provider or command reuse from stdout, stderr, reports, or wrong-path bundles.
- Do not broaden R3 into transition replay, public boundary cleanup, or consumer-side rendering.
- Do not add command adapters or inline command glue to simulate resume-policy behavior.
- Prefer `BARRIER` or `INVALID` over optimistic reuse when evidence is incomplete or stale.

## Task Checklist

### Task 1: Add The Effect Resume Policy Module And Replace Provisional Digest Logic

**Files:**

- Create: `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`

- [ ] Introduce the dedicated policy helper module with schema/version constants, policy-kind enums, canonical serialization, digest helpers, evidence requirement validators, decision result helpers, and stable diagnostic codes.
- [ ] Move effect-policy digest derivation out of the ad hoc `shadow_record_only` hash path and make `lexical_checkpoints.py` depend on the new policy module for all effect-boundary validation.
- [ ] Preserve backward compatibility by allowing R1/R2 provisional records to validate as historical shadow data while explicitly downgrading them to non-reusable policy status.
- [ ] Add focused unit tests for canonical policy digests, unknown policy rejection, source-lineage-sensitive digesting, and the historical provisional-record compatibility rule.

**Blocking verification after Task 1:**

- [ ] `python -m pytest tests/test_workflow_lisp_lexical_checkpoints.py -k "policy or provisional or digest" -q`

### Task 2: Emit Policy Envelopes From WCC Lowering And Keep Public Artifacts Route-Neutral

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/lexical_checkpoint_effect_policies.orc`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_wcc_m4.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- [ ] Add one focused `.orc` fixture that exercises the missing R3 boundary mix in one place: pure projection, provider result, command result, workflow call, materialized view, and resource transition.
- [ ] Extend WCC defunctionalization so each eligible effect-boundary checkpoint point is mapped to the correct R3 policy kind and evidence requirements instead of `policy_status: shadow_record_only`.
- [ ] Preserve public route neutrality by keeping raw runtime-only evidence or WCC identifiers out of public runtime-plan, source-map, and checkpoint-points artifacts.
- [ ] Update build and semantic-IR serialization so policy summaries, not raw sidecar payloads, appear in checked artifacts.
- [ ] Add or extend tests that assert every target boundary family emits a policy envelope, that artifact validation rejects missing or malformed envelopes, and that runtime-plan/Semantic IR policy summaries stay aligned with effect graph entries, executable step ids, source-map origins, and command-boundary metadata.

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_wcc_m4.py -k "lexical_checkpoint and policy" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "lexical_checkpoint and policy" -q`
- [ ] `python -m pytest tests/test_workflow_semantic_ir.py -k "lexical_checkpoint" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_source_map.py -k "lexical_checkpoint" -q`

### Task 3: Persist Completed-Effect Evidence In Runtime Sidecars And Validate It

**Files:**

- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`

- [ ] Extend runtime checkpoint-record emission to write completed-effect refs for provider, command, workflow-call, materialized-view, and transition boundaries after authoritative state commit.
- [ ] Record only typed evidence the runtime already owns: validated bundle paths and digests, workflow-call terminal result identity, renderer id/version plus typed-input digest, and transition audit/idempotency references.
- [ ] Keep provider/command stdout-only output, markdown reports, pointer files, and wrong-path bundle writes invalid as reuse evidence.
- [ ] Add negative tests that mutate completed-effect refs, contract digests, payload digests, or transition audit shape and prove record validation fails closed.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_lexical_checkpoints.py -k "completed_effect or command or provider or transition" -q`

### Task 4: Enforce Policy Decisions In Restore Planning And Resume Execution

**Files:**

- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoint_restore.py`
- Modify: `tests/test_resume_command.py`

- [ ] Replace the current hard-coded `shadow_record_only` pending-effect check with policy evaluation that returns `REUSABLE`, `REGENERATE`, `BARRIER`, or `INVALID` internally and maps those results back onto the reused R2 restore-decision/report contract.
- [ ] Make completed provider, command, and workflow-call boundaries reusable only when evidence identity and digest checks pass, otherwise surface `BARRIER` or `INVALID`.
- [ ] Make materialized-view restore choose between regeneration and preservation based on policy and durability mode rather than on generic R2 behavior.
- [ ] Keep pending uncertified command/adapters and non-idempotent effects fail-closed with dedicated diagnostics.
- [ ] Keep transition boundaries audit-gated barriers in R3 even after the policy envelope is present, so R4 can own committed-result replay later.
- [ ] Preserve the existing restore payload/report surface so private policy outcomes do not force an R3 scope expansion into downstream restore consumers.
- [ ] Extend resume smoke coverage so one run fails at a resumable boundary, then resumes through the policy evaluator and records the expected private restore decision.

**Blocking verification after Task 4:**

- [ ] `python -m pytest tests/test_workflow_lisp_lexical_checkpoint_restore.py -k "policy or reusable or regenerate or barrier or invalid" -q`
- [ ] `python -m pytest tests/test_resume_command.py -k "lexical_checkpoint" -q`

### Task 5: Run The Narrow Verification Stack And The Required Runtime Resume Smoke

**Files:**

- Modify as needed from Tasks 1-4 only; do not widen scope with unrelated cleanup.

- [ ] Run the narrow unit and artifact selectors again after integration so policy-module, lowering, artifact, sidecar, and restore behavior are verified together.
- [ ] Run the Semantic IR/runtime-plan bridge lane so the additive policy summaries are proven on the existing checkpoint bridge surfaces.
- [ ] Run the full lexical-checkpoint-focused unit modules to catch cross-module regressions in helper logic and restore selection ordering.
- [ ] Run at least one runtime resume smoke that proves a failed effect-boundary run resumes with R3 policy enforcement and unchanged public outputs.
- [ ] If any new or renamed pytest modules were added during implementation, run `pytest --collect-only` on those modules before the final green pass.
- [ ] Record the final verification set and any deliberately deferred checks in the implementation report.

**Blocking verification after Task 5:**

- [ ] `python -m pytest tests/test_workflow_lisp_lexical_checkpoints.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_lexical_checkpoint_restore.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_wcc_m4.py -k "lexical_checkpoint" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "lexical_checkpoint" -q`
- [ ] `python -m pytest tests/test_workflow_semantic_ir.py -k "lexical_checkpoint" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_source_map.py -k "lexical_checkpoint" -q`
- [ ] `python -m pytest tests/test_resume_command.py -k "lexical_checkpoint" -q`
