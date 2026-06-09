# Workflow Lisp StateLayout / PathAllocator Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first shared `StateLayout` / `PathAllocator` boundary for compiler-owned generated private paths so command/provider bundle roots, variant-projection bundles, reusable-call write roots, entrypoint managed write roots, and value-view paths all derive from one allocator metadata contract without widening the public workflow surface.

**Architecture:** Create one shared runtime-owned allocation module in `orchestrator/workflow/state_layout.py`, then add one Workflow Lisp lowering bridge in `orchestrator/workflow_lisp/lowering/generated_paths.py` that turns lowering situations into typed allocation requests. Persist the returned allocation metadata on `WorkflowProvenance`, derive compatibility hidden-input projections from that metadata, switch runtime entry bindings and build/semantic projectors to consume it, and keep preserved non-run-isolated shapes labeled `compatibility_view` rather than silently treating them as promotion-grade private paths.

**Tech Stack:** Python 3 dataclasses/enums, `orchestrator/workflow`, `orchestrator/workflow_lisp`, shared bundle/build/runtime surfaces, pytest, and the recorded verification selectors in `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
  - `14. Tranche 5: StateLayout / PathAllocator Foundation`
  - `15.5 StateLayout / PathAllocator Contract`
  - `16.1 Runtime`
  - `16.3 Workflow Lisp Frontend`
  - `17. Dependencies And Sequencing`
  - `19. Evidence And Implementation Boundaries`
  - `21.6 StateLayout Tests`
  - `22.5 Generated Path Allocation`
  - `23. Success Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections `19-21`, `45-48`, `59`, `65`, `74-76`, `95`, and `103-104`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-state-layout-path-allocator-foundation/implementation_architecture.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`

Current checkout facts that must not be rediscovered during implementation:

- `progress_ledger.json` is still `{"ledger_version":1,"events":[]}`, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow/state_layout.py` does not exist yet, so the shared allocator owner is still missing.
- `orchestrator/workflow_lisp/lowering/generated_paths.py` does not exist yet, so lowering still synthesizes generated path families directly in multiple modules.
- `orchestrator/workflow_lisp/lowering/effects.py`, `values.py`, `phase_resource.py`, `phase_flow.py`, and `control_match.py` each still synthesize `__write_root__{step_id}__result_bundle` directly.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py::_managed_write_root_bindings(...)` still synthesizes reusable-call write-root locations under `.orchestrate/workflow_lisp/calls/...`.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py::_managed_write_root_binding_step(...)` still uses inline `python -c` to materialize loop-scoped binding bundles under `.orchestrate/workflow_lisp/call_bindings/.../__managed_write_roots.json`; this slice may route those paths through the allocator, but it does not retire that helper.
- `orchestrator/workflow/executor.py::_entry_managed_write_root_bindings(...)` still synthesizes entrypoint write-root paths independently under `.orchestrate/workflow_lisp/entry/<run_id>/<workflow>/...`.
- `WorkflowProvenance` currently records `managed_write_root_inputs` and `runtime_context_inputs`, but not typed generated-path allocation metadata.
- `LoadedWorkflowBundle` already transports `surface`, `core_workflow_ast`, `semantic_ir`, `ir`, `projection`, `runtime_plan`, and `provenance`, so it is the correct seam for provenance transport rather than a new sidecar bundle type.
- `loaded_bundle.workflow_public_input_contracts(...)` already hides managed write-root inputs from public workflow signatures; preserve that boundary.

## Hard Scope Limits

Implement only the selected allocator-foundation slice:

- create one shared typed allocation request/metadata contract for compiler-owned generated private paths;
- route these families through it:
  - command-result bundle roots,
  - provider-result bundle roots,
  - variant-projection bundle paths,
  - reusable-call write roots,
  - entrypoint managed write roots,
  - loop-scoped binding-bundle paths,
  - value-view paths;
- persist allocation metadata on workflow provenance and expose compatibility helpers from shared bundle surfaces;
- derive runtime-owned hidden-input binding, workflow-boundary explanation, source-map generated-path entries, and Semantic IR state-layout entries from the same metadata;
- keep compiler-owned generated write roots hidden from public workflow signatures;
- make promotion-relevant private generated paths run-isolated by default and resume-stable for the same run/call-frame/loop identity;
- label any preserved non-run-isolated path shape as `compatibility_view` and exclude it from promotion-grade evidence.

Explicit non-goals:

- no public path-surface redesign outside the selected generated private path families;
- no command/provider output-contract semantic redesign beyond reusing their path families;
- no typed-value transport redesign beyond routing value-view file locations through the allocator;
- no migration-gate hardening, prompt extern work, or collection publish/consume redesign from the other runtime-foundation tranches;
- no retirement of `_managed_write_root_binding_step(...)`, no new command adapters, and no new runtime-native effects;
- no exposure of `__write_root__...` inputs as public workflow inputs;
- no second path allocator in lowering, runtime, source-map, or semantic code once the shared module exists.

## File Ownership

Create:

- `orchestrator/workflow/state_layout.py`
- `orchestrator/workflow_lisp/lowering/generated_paths.py`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-state-layout-path-allocator-foundation/execution_plan.md` (this file)

Modify:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/lowering/context.py`
- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/effects.py`
- `orchestrator/workflow_lisp/lowering/values.py`
- `orchestrator/workflow_lisp/lowering/phase_resource.py`
- `orchestrator/workflow_lisp/lowering/phase_flow.py`
- `orchestrator/workflow_lisp/lowering/control_match.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_source_map.py`
- `tests/test_resume_command.py`

Modify only if a focused failing test proves a shared helper or projection changed behavior:

- `tests/test_workflow_output_contract_integration.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_surface_ast.py`

Do not modify for this slice:

- migration-parity CLI/reporting code;
- prompt/provider authoring guides or unrelated docs;
- adapter scripts under `scripts/`;
- queue/resource/review-revise semantics unrelated to generated-path allocation;
- unrelated Workflow Lisp parser/typechecker/stdlib surfaces.

## Locked Decisions

- `StateLayout` owns typed semantic allocation requests; `PathAllocator` owns concrete path selection; the returned object is neutral allocation metadata, not a ready-made runtime or build projection.
- Stable allocation identity must derive from semantic ownership, not `source_span`; formatting-only source edits must not change allocation identity.
- Hidden input names such as `__write_root__...` remain compatibility projections in the first patch, not the durable allocation authority.
- `private_generated` allocations are run-isolated by default; any preserved non-run-isolated shape must be labeled `compatibility_view`.
- Runtime-owned entry bindings, workflow-boundary explanation, source-map records, and Semantic IR state-layout entries must all derive from the same stored allocation metadata.
- Value-view files and pointer-style compatibility files remain representations, not semantic authority.
- The existing loop-scoped compatibility helper may remain, but its bundle path and emitted write-root values must route through the allocator metadata instead of ad hoc string synthesis.
- No public workflow entrypoint may expose compiler-owned hidden generated inputs after this patch.

## Task 1: Lock The Allocator Contract And Regression Surface With Failing Tests

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_resume_command.py`

- [ ] Add lowering tests that fail until generated bundle and write-root families route through one shared allocator metadata contract instead of direct string synthesis.
- [ ] Add or update focused selectors matching the recorded verification names:
  - `command_result_bundle_allocation_uses_state_layout`
  - `provider_result_bundle_allocation_uses_state_layout`
  - `variant_projection_bundle_allocation_uses_state_layout`
  - `resume_or_start_workflow_call_write_root_allocation_uses_call_frame_identity`
  - `run_provider_phase_generated_bundle_paths_use_allocator_metadata`
  - `workflow_boundary_projection_emits_generated_path_allocations`
  - `source_map_emits_generated_path_allocations`
  - `semantic_ir_emits_generated_path_allocations`
  - `generated_path_allocations_map_to_frontend_origins`
  - `formatting_only_source_changes_preserve_allocation_identity`
  - `entry_managed_write_root_bindings_are_run_isolated_and_resume_stable`
  - `entry_managed_write_root_paths_do_not_collide_across_runs`
- [ ] In `tests/test_workflow_lisp_lowering.py`, assert generated result-bundle paths and reusable-call write roots expose typed allocation metadata including role, privacy, resume scope, stable identity, and compatibility classification where relevant.
- [ ] In `tests/test_workflow_lisp_phase_stdlib.py`, prove reusable-call allocations include call-frame or loop identity in stable identity and do not collapse to step-id-only strings.
- [ ] In `tests/test_workflow_lisp_build_artifacts.py`, assert build artifacts emit generated allocation records in both `workflow_boundary_projection.json` and `source_map.json`, and that Semantic IR records matching state-layout entries from the same metadata.
- [ ] In `tests/test_workflow_lisp_source_map.py`, prove generated-path entries retain authored origin coverage while formatting-only source-span changes do not perturb allocation identity.
- [ ] In `tests/test_resume_command.py`, prove entrypoint managed write roots differ across independent runs, remain stable on resume for the same run, and stay hidden from public inputs.

**Blocking verification after Task 1:**

- [ ] Run:
  - `python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_source_map.py tests/test_resume_command.py tests/test_workflow_output_contract_integration.py -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "command_result_bundle_allocation_uses_state_layout or provider_result_bundle_allocation_uses_state_layout or variant_projection_bundle_allocation_uses_state_layout" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start_workflow_call_write_root_allocation_uses_call_frame_identity or run_provider_phase_generated_bundle_paths_use_allocator_metadata" -q`

Expected before implementation: collection succeeds, then the new selectors fail because there is no shared `state_layout.py`, no lowering bridge, and the current path families are still synthesized locally.

## Task 2: Add The Shared Allocation Owner And Provenance Carriers

**Files:**

- Create: `orchestrator/workflow/state_layout.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify only if tests require serialization support there: `tests/test_workflow_surface_ast.py`

- [ ] In `orchestrator/workflow/state_layout.py`, add the shared typed allocation contract:
  - a closed semantic-role vocabulary for:
    - `command_result_bundle`,
    - `provider_result_bundle`,
    - `variant_projection_bundle`,
    - `materialized_value_view`,
    - `reusable_call_write_root`,
    - `entrypoint_managed_write_root`,
    - `generated_internal_input_binding`,
    - `compatibility_pointer_view`;
  - privacy classes:
    - `public_authored`,
    - `public_artifact`,
    - `private_generated`,
    - `compatibility_view`,
    - `runtime_sidecar`;
  - resume scopes:
    - `none`,
    - `run`,
    - `call_frame`,
    - `loop_frame`,
    - `loop_iteration`,
    - `step_visit`;
  - typed request and metadata records that carry `allocation_id`, `stable_identity`, `concrete_path_template`, `generated_input_name` when needed, `path_safety_policy`, and projection hints.
- [ ] Implement one allocator entrypoint that derives concrete path templates from typed requests, enforces workspace-relative/path-safe rules, and distinguishes `private_generated` from `compatibility_view`.
- [ ] Encode the negative rule in tests and helper names: `source_span` participates only as provenance, not as stable identity.
- [ ] Extend `WorkflowProvenance` in `surface_ast.py` with a typed `generated_path_allocations` field and keep `managed_write_root_inputs` as a compatibility projection.
- [ ] Update `ImportedWorkflowMetadata`, `core_ast` provenance round-tripping, and `elaboration.py` construction so imported bundles and elaborated YAML bundles preserve the new metadata shape without inventing fallback authorities.
- [ ] Add bundle helpers in `loaded_bundle.py` for reading generated allocations and deriving managed write-root compatibility projections from them; keep prefix-based fallback only for older bundles without allocation metadata.

Implementation guardrails:

- do not make `WorkflowProvenance` store finished workflow-boundary or source-map payloads;
- do not make hidden input names the primary key of allocation metadata;
- do not widen public input contracts while threading the new metadata through typed bundle surfaces.

**Blocking verification after Task 2:**

- [ ] Re-run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "command_result_bundle_allocation_uses_state_layout or provider_result_bundle_allocation_uses_state_layout or variant_projection_bundle_allocation_uses_state_layout" -q`

Expected after Task 2: the shared types and provenance carrier exist, but selectors may still fail until lowering families actually use the new allocator.

## Task 3: Add The Workflow Lisp Lowering Bridge And Route The Selected Families

**Files:**

- Create: `orchestrator/workflow_lisp/lowering/generated_paths.py`
- Modify: `orchestrator/workflow_lisp/lowering/context.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_resource.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_flow.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_match.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] In `orchestrator/workflow_lisp/lowering/generated_paths.py`, implement the only lowering-owned bridge allowed to:
  - classify a lowering site into one allocator `semantic_role`,
  - decide whether the allocation is `private_generated` or `compatibility_view`,
  - compute stable semantic identity from workflow name, semantic target, call-frame identity, loop identity, and schema version,
  - request a hidden generated-input name when runtime binding is required,
  - preserve lowering provenance for source-map projection.
- [ ] Extend the lowering context so recorded generated allocations are the durable registry; keep `generated_path_spans` as a derived view for compatibility and diagnostics.
- [ ] Replace direct `__write_root__{step_id}__result_bundle` synthesis in:
  - `effects.py`,
  - `values.py`,
  - `phase_resource.py`,
  - `phase_flow.py`,
  - `control_match.py`
  with bridge calls that return allocator metadata plus any hidden-input projection string needed by shared lowering.
- [ ] Route reusable-call write-root bindings in `workflow_calls.py` through the allocator bridge instead of direct `.orchestrate/workflow_lisp/calls/...` string synthesis.
- [ ] Route the loop-scoped `_managed_write_root_binding_step(...)` bundle path through the same bridge and label any preserved non-run-isolated helper shape `compatibility_view` rather than `private_generated`.
- [ ] Route value-view paths generated in `phase_scope.py` through the bridge so value-view materialization stops inventing its own generated path family.
- [ ] Update `core.py` to derive `managed_write_root_inputs`, `internal_generated_input_reasons`, and compatibility path-span maps from recorded allocation metadata instead of path-template regexes alone.

Implementation guardrails:

- do not create a second concrete path allocator inside lowering modules;
- do not derive stable identity from formatted source coordinates;
- do not silently keep static preserved shapes as promotion-grade private generated paths;
- do not let loop/call-family allocations drop their call-frame or iteration identity.

**Blocking verification after Task 3:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "command_result_bundle_allocation_uses_state_layout or provider_result_bundle_allocation_uses_state_layout or variant_projection_bundle_allocation_uses_state_layout" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start_workflow_call_write_root_allocation_uses_call_frame_identity or run_provider_phase_generated_bundle_paths_use_allocator_metadata" -q`

Expected after Task 3: lowering and stdlib selectors pass, generated path families share one typed allocation source, and repeated calls/loop iterations no longer depend on step-id-only string synthesis.

## Task 4: Switch Runtime Entry Bindings And Build/Semantic Projectors To Allocation Metadata

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_resume_command.py`
- Modify only if failing coverage requires it: `tests/test_workflow_semantic_ir.py`

- [ ] Replace `WorkflowExecutor._entry_managed_write_root_bindings(...)` path synthesis with allocator-metadata lookup for `entrypoint_managed_write_root` allocations; keep override detection and resume reuse in the runtime, but derive the expected paths from stored metadata.
- [ ] Ensure runtime entry binding preserves the public-boundary rule: generated write-root bindings remain hidden from user-facing workflow inputs and parity surfaces.
- [ ] Update build-side source-map serialization so `source_map.json` records generated paths from allocation metadata plus lowering provenance, including privacy/role/compatibility annotations needed for auditability.
- [ ] Update build-side workflow-boundary projection so generated internal inputs can cite allocation role or allocation id without becoming public inputs.
- [ ] Update `semantic_ir.py` so `SemanticStateLayoutEntry` emits typed entries for generated path families from allocator metadata rather than collapsing everything into `managed_write_root_input`.
- [ ] Keep existing compatibility summary entries only where they are still needed for older consumers, and make sure they are derived views rather than separate authorities.
- [ ] Keep build/runtime artifacts honest: projections explain the allocator metadata; they do not replace it.

**Blocking verification after Task 4:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "workflow_boundary_projection_emits_generated_path_allocations or source_map_emits_generated_path_allocations or semantic_ir_emits_generated_path_allocations" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_source_map.py -k "generated_path_allocations_map_to_frontend_origins or formatting_only_source_changes_preserve_allocation_identity" -q`
- [ ] Run:
  - `python -m pytest tests/test_resume_command.py -k "entry_managed_write_root_bindings_are_run_isolated_and_resume_stable or entry_managed_write_root_paths_do_not_collide_across_runs" -q`

Expected after Task 4: runtime entry bindings, workflow-boundary projection, source maps, and Semantic IR all consume the same stored allocation metadata, and resume/run-isolation behavior is proven through focused tests.

## Task 5: Run The Recorded Verification Set And Stop On Fresh Failures

**Files:**

- No additional maintained source files; this task proves the bounded slice with the recorded verification commands.

- [ ] Run the exact collect-only command from `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`:
  - `python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_source_map.py tests/test_resume_command.py tests/test_workflow_output_contract_integration.py -q`
- [ ] Run the exact lowering selector:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "command_result_bundle_allocation_uses_state_layout or provider_result_bundle_allocation_uses_state_layout or variant_projection_bundle_allocation_uses_state_layout" -q`
- [ ] Run the exact stdlib selector:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start_workflow_call_write_root_allocation_uses_call_frame_identity or run_provider_phase_generated_bundle_paths_use_allocator_metadata" -q`
- [ ] Run the exact build-artifact selector:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "workflow_boundary_projection_emits_generated_path_allocations or source_map_emits_generated_path_allocations or semantic_ir_emits_generated_path_allocations" -q`
- [ ] Run the exact source-map selector:
  - `python -m pytest tests/test_workflow_lisp_source_map.py -k "generated_path_allocations_map_to_frontend_origins or formatting_only_source_changes_preserve_allocation_identity" -q`
- [ ] Run the exact resume selector:
  - `python -m pytest tests/test_resume_command.py -k "entry_managed_write_root_bindings_are_run_isolated_and_resume_stable or entry_managed_write_root_paths_do_not_collide_across_runs" -q`
- [ ] Run:
  - `git diff --check`

Interpretation rules:

- If collect-only fails, fix test discovery or syntax before changing more allocator behavior.
- If lowering selectors pass but build/runtime selectors fail, treat that as a projector or runtime-consumption gap rather than reopening lowering identity logic first.
- If run-isolation selectors fail only for loop-scoped compatibility helper paths, keep the helper but label the preserved shape `compatibility_view` unless the call site has enough runtime identity to qualify as `private_generated`.
- If any test proves a shared command/provider bundle-path helper regressed, add only the narrow regression coverage needed in `tests/test_workflow_output_contract_integration.py`; do not widen scope into Tranche 1 or Tranche 3 redesign.
- Do not claim completion from inspection alone; completion requires fresh passing output from the recorded commands above.

## Definition Of Done

The slice is complete only when all of the following are true:

- `orchestrator/workflow/state_layout.py` exists and owns the shared typed allocation contract plus concrete allocator facade.
- `orchestrator/workflow_lisp/lowering/generated_paths.py` exists and is the only lowering-owned bridge for the selected generated path families.
- command-result bundle roots, provider-result bundle roots, variant-projection bundle paths, reusable-call write roots, loop-scoped binding-bundle paths, entrypoint managed write roots, and value-view paths all route through the shared allocator.
- `WorkflowProvenance` carries generated allocation metadata and existing hidden-input compatibility helpers derive from that metadata where available.
- generated internal inputs remain hidden from public workflow inputs.
- source maps and Semantic IR emit matching generated path/layout entries from the same allocation metadata.
- repeated calls, loop iterations, and match arms produce collision-proof allocation identities.
- formatting-only source-span changes do not change stable allocation identity, while semantic-target changes do.
- resume reconstructs the same allocation for the same run and call-frame or loop identity.
- preserved non-isolated shapes are explicitly labeled `compatibility_view` and do not count as promotion evidence.
- the recorded verification commands pass.
- `git diff --check` passes.
