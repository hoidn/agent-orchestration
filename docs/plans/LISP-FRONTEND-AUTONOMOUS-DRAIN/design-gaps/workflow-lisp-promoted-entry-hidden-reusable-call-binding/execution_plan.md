# Workflow Lisp Promoted-Entry Hidden Reusable-Call Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make promoted Workflow Lisp entry workflows satisfy required internal `RunCtx` and `PhaseCtx` call bindings through compiler/runtime-owned hidden inputs, so reusable wrapper calls succeed without exposing bootstrap inputs publicly and without relying on synthetic top-level `PhaseCtx` defaults as the proof path.

**Architecture:** Reuse the existing generated-internal-input split instead of inventing a new executor path. Frontend signature and phase analysis records which callee parameters are eligible for promoted-entry hidden context binding, lowering synthesizes explicit flattened `call.with` bindings from runtime-owned hidden inputs and records them in provenance, loaded-bundle helpers keep those names off the public boundary, and entry execution allocates deterministic runtime-owned context values, persists them for resume, and rejects overrides.

**Tech Stack:** Python 3, Workflow Lisp compiler/lowering, shared workflow loaded-bundle and executor runtime, `pytest`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-promoted-entry-hidden-reusable-call-binding/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/state.md`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this selected slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow/loaded_bundle.py` already exposes `workflow_public_input_contracts(...)`, `workflow_runtime_input_contracts(...)`, and `workflow_managed_write_root_inputs(...)`, but the provenance/public split only covers managed write roots today.
- `orchestrator/workflow/surface_ast.py` and the shared bundle pipeline only record `managed_write_root_inputs` in `WorkflowProvenance`; there is no second runtime-owned context-input class yet.
- `orchestrator/workflow_lisp/contracts.py::_apply_workflow_input_defaults(...)` still injects synthetic defaults for top-level authored `PhaseCtx` leaves as a compatibility helper.
- `orchestrator/workflow_lisp/lowering.py::_lower_call_expr(...)` already auto-binds managed write-root inputs for internal calls, but it does not synthesize hidden `RunCtx` or `PhaseCtx` bindings.
- `orchestrator/workflow_lisp/lowering.py` already records generated internal input reasons through `_LoweringContext.internal_generated_input_reasons`, so this slice must extend that path instead of inventing a parallel registry.
- `orchestrator/workflow/executor.py` already has the managed-write-root entry binder pattern and already consumes runtime input contracts, so runtime-owned context binding should mirror that structure instead of adding a separate execution pathway.
- `orchestrator/cli/commands/resume.py::_public_rebind_inputs_for_force_restart(...)` currently strips only managed write-root internals before rebinding public inputs for `resume --force-restart`.
- `tests/test_resume_command.py` currently covers force-restart filtering only for managed write-root internals, so this slice must extend that proof for runtime-owned context inputs instead of assuming the new hidden-input class will be scrubbed automatically.
- `tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context` currently proves the public boundary is narrow, but it still asserts the promoted internal call omits explicit `phase-ctx__*` bindings.
- `tests/test_workflow_lisp_lowering.py::test_compile_stage3_entrypoint_omits_imported_defaulted_call_bindings` proves imported defaults can still satisfy omitted call bindings silently; this slice must keep ordinary default omission working while preventing that route from being the promoted-entry bootstrap proof.

## Hard Scope Limits

Implement only this bounded slice:

- add one compiler-owned hidden-binding eligibility contract for omitted internal `RunCtx` and `PhaseCtx` call parameters on promoted-entry workflows;
- add one new runtime-owned generated-internal-input class for those context values;
- extend promoted-entry call typecheck/lowering so eligible internal reusable calls emit explicit flattened `call.with` bindings from runtime-owned hidden inputs;
- add runtime binding, resume reuse, override rejection, and `resume --force-restart` public-input scrubbing for those hidden inputs;
- tighten the dedicated promoted-entry reusable-wrapper fixture and focused regressions so they prove the executable hidden-binding route rather than only the public-boundary route.

Explicit non-goals:

- no new author-facing context-construction forms or public bootstrap inputs;
- no redesign of `resume-or-start`, reusable-state validation, wrapper union construction, review-loop semantics, command-result bundle ownership, or migration promotion policy;
- no removal of synthetic top-level `PhaseCtx` defaults repo-wide;
- no new command adapters, inline Python/shell semantic glue, pointer-authority exceptions, or family-specific workflow rewrites;
- no generalized support for arbitrary imported precompiled bundles outside the linked `compile_stage3_entrypoint(...)` graph used by this proof.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/cli/commands/resume.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_resume_command.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc`
- `tests/fixtures/workflow_lisp/valid/library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper.orc`

Inspect only if a focused failing test proves the need:

- `orchestrator/workflow/signatures.py`
- `orchestrator/workflow/calls.py`

Do not modify unless verification proves this plan is incomplete:

- `specs/dsl.md`
- `specs/state.md`
- unrelated Workflow Lisp review-loop, reusable-state, or command-adapter modules

## Required Contract Deltas

These are fixed implementation decisions for this slice:

- Add `WorkflowProvenance.runtime_context_inputs: tuple[str, ...] = ()` and thread it through the shared bundle pipeline beside `managed_write_root_inputs`.
- Add `workflow_runtime_context_inputs(workflow_or_bundle)` in `orchestrator/workflow/loaded_bundle.py`.
- Make `workflow_public_input_contracts(...)` exclude both managed write-root inputs and runtime context inputs; keep `workflow_runtime_input_contracts(...)` as the full executable view.
- Extend `_public_rebind_inputs_for_force_restart(...)` so `resume --force-restart` rebinds only public inputs and strips both managed write-root and runtime context hidden inputs before `bind_workflow_inputs(...)`.
- Add one new `GeneratedInternalInput.reason` value: `"runtime_owned_context"`.
- Add a frontend-owned metadata record for hidden promoted-entry context binding:

```text
PromotedEntryHiddenContextRequirement
  param_name
  context_kind   # RunCtx | PhaseCtx
  phase_name     # required for PhaseCtx, absent for RunCtx
```

- Extend `WorkflowSignature` with `hidden_context_requirements` keyed by parameter name. Keep `WorkflowSignature.params` unchanged.
- Hidden promoted-entry omission is legal only when all of the following are true:
  - the missing parameter is exactly `RunCtx` or `PhaseCtx`;
  - the callee signature carries a `PromotedEntryHiddenContextRequirement` for that parameter;
  - the caller is the selected promoted entry or one of its generated private wrappers within the same `compile_stage3_entrypoint(...)` graph;
  - `PhaseCtx` eligibility derives one unambiguous phase symbol from existing Stage 5 `with-phase` analysis.
- Lowering must emit explicit flattened `call.with` bindings for every eligible `RunCtx` and `PhaseCtx` leaf even if imported compatibility defaults still exist for those leaves.
- Runtime-owned context inputs remain internal-only and must be allocated by the executor before entry execution, persisted for resume of the same run, and rejected if user supplied or mutated.
- Synthetic top-level `PhaseCtx` defaults remain a compatibility convenience for isolated compile/dry-run scenarios, but they are not valid parity evidence for this promoted-entry path.
- Add dedicated diagnostics for this slice:
  - `promoted_entry_hidden_context_binding_invalid`
  - `promoted_entry_hidden_phase_ctx_ambiguous`
  - `promoted_entry_hidden_context_override`
  - `promoted_entry_hidden_context_metadata_missing`

## Implementation Units

### Unit 1: Hidden Context Signature Metadata

Owns the new eligibility metadata and the bounded `PhaseCtx` derivation helper.

Files:

- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/compiler.py`

Stable contract:

- local and linked imported Workflow Lisp signatures can carry hidden-context requirements without changing ordinary workflow parameter shapes;
- `RunCtx` eligibility is exact-type only;
- `PhaseCtx` eligibility is derived from existing `with-phase` analysis and does not require a new author annotation;
- precompiled imported bundles outside the linked entrypoint graph remain out of scope for this slice.

### Unit 2: Provenance And Input-Boundary Transport

Owns the second runtime-owned internal-input class and the public/runtime input split.

Files:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/cli/commands/resume.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_resume_command.py`

Stable contract:

- runtime context inputs are recorded in provenance and surfaced in build artifacts the same way managed write roots are;
- public input helpers exclude runtime-owned context names;
- runtime input helpers retain those names for execution-time binding;
- `resume --force-restart` strips persisted runtime-owned context inputs before rebinding public inputs for a fresh run;
- existing managed write-root behavior stays unchanged.

### Unit 3: Call Typecheck And Lowering

Owns the compiler-owned third call-binding path for promoted entries.

Files:

- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/contracts.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc`
- `tests/fixtures/workflow_lisp/valid/library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper.orc`

Stable contract:

- ordinary explicit bindings and ordinary authored-default omission continue to work unchanged;
- eligible promoted-entry omissions become explicit generated `call.with` bindings sourced from runtime-owned hidden inputs;
- generated bindings compose with managed write-root bindings on the same call site;
- source maps and generated-input provenance remain explainable.

### Unit 4: Runtime Entry Binding

Owns deterministic runtime allocation, resume reuse, override rejection, and force-restart scrubbing for persisted hidden context values.

Files:

- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/cli/commands/resume.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`

Stable contract:

- entry execution allocates runtime-owned context values before any step that resolves `${inputs...}` refs;
- the same run reuses persisted hidden context values on resume;
- user-provided or mutated hidden context values fail deterministically;
- `resume --force-restart` never rebinds persisted hidden context names through the public input contract of the new run;
- runtime code derives values from the compiled metadata and existing run/phase layout rules, not from Workflow Lisp syntax.

### Unit 5: Executable Proof Regressions

Owns the proof that the promoted-entry route now succeeds for the right reason.

Files:

- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Stable contract:

- the promoted-entry fixture exposes only authored business inputs;
- the lowered reusable-wrapper call carries explicit hidden `phase-ctx` bindings;
- runtime execution succeeds through the real `resume-or-start :valid-when (APPROVED)` route;
- override attempts fail;
- the fixture no longer passes only because of synthetic defaults.

## Task Checklist

### Task 1: Lock The Regression Surface Around Hidden Context Bootstrap

**Files:**

- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper.orc`

- [ ] Tighten `test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context` so it still proves the public boundary is narrow, but now expects the first reusable-wrapper call to include explicit flattened `phase-ctx__*` bindings sourced from hidden runtime-owned inputs.
- [ ] Keep the fixture generic and prerequisite-focused. It must continue to exercise the real `resume-or-start :valid-when (APPROVED)` reusable-wrapper route, not a family-specific workaround.
- [ ] Add or tighten one lowering-focused regression that fails if promoted-entry lowering omits the hidden context bindings and succeeds only because imported defaults exist.
- [ ] Add or tighten one build-artifact/runtime-input regression that proves runtime-owned hidden context inputs stay internal, remain visible in runtime input contracts, and keep provenance with `reason == "runtime_owned_context"`.
- [ ] Add one runtime override regression target in `tests/test_workflow_lisp_key_migrations.py` that will fail until executor-owned binding rejection exists.
- [ ] Add one `tests/test_resume_command.py` regression that proves `resume --force-restart` strips persisted runtime-owned context inputs before rebinding the fresh run's public inputs, matching the existing managed-write-root behavior.
- [ ] Preserve the existing defaulted-call regression for ordinary authored defaults; this slice must not break non-context default omission while changing the promoted-entry path.

Suggested test names:

- `test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context`
- `test_compile_stage3_entrypoint_emits_hidden_context_call_bindings_for_promoted_entry`
- `test_build_artifacts_keep_runtime_context_inputs_internal`
- `test_promoted_entry_hidden_context_override_fails`
- `test_resume_force_restart_rebinds_only_public_inputs_for_promoted_entry_hidden_context`

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_build_artifacts.py -q`
- [ ] `python -m pytest --collect-only tests/test_resume_command.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context -q`
- [ ] `python -m pytest tests/test_workflow_lisp_lowering.py -k "promoted_entry or hidden_context or defaulted_call_bindings" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "public_inputs or generated_internal_inputs or managed_write_root" -q`
- [ ] `python -m pytest tests/test_resume_command.py -k "force_restart and (managed_orc_inputs or promoted_entry_hidden_context)" -q`

Expected before implementation: the key-migration and lowering regressions fail because promoted-entry calls still omit explicit hidden context bindings, the build-artifact surface has no runtime-context provenance yet, and the force-restart regression fails because the rebind helper only strips managed write-root internals.

### Task 2: Add Hidden Context Signature Metadata And Eligibility Derivation

**Files:**

- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] Add the `PromotedEntryHiddenContextRequirement` metadata type and extend `WorkflowSignature` with `hidden_context_requirements` without changing `WorkflowSignature.params`.
- [ ] Derive hidden-context eligibility for local workflows during workflow catalog/signature construction and preserve it through the linked `compile_stage3_entrypoint(...)` graph.
- [ ] Reuse `phase.py` Stage 5 rules to derive one unambiguous `phase_name` for eligible `PhaseCtx` parameters. If the callee uses `PhaseCtx` ambiguously or outside the bounded `with-phase` shape, leave it as an ordinary required binding.
- [ ] Ensure generated private wrappers created during entrypoint compilation preserve the hidden-context metadata they need for the promoted-entry path.
- [ ] Add or update targeted lowering tests that inspect signature metadata or the resulting diagnostics for:
  - eligible `RunCtx` omission;
  - eligible `PhaseCtx` omission with one clear phase;
  - ambiguous `PhaseCtx` rejection with `promoted_entry_hidden_phase_ctx_ambiguous`.

Implementation guardrails:

- Do not add a user-authored annotation such as `:runtime-owned`.
- Do not infer hidden binding for arbitrary records that merely resemble context types.
- Do not widen support to standalone imported bundles lacking linked-source metadata.

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_lowering.py -k "promoted_entry or hidden_context or ambiguous" -q`

Expected after Task 2: signature/phase analysis can distinguish eligible promoted-entry omissions from ordinary missing bindings, but lowering and runtime still fail until the later tasks land.

### Task 3: Thread Runtime Context Provenance And Synthesize Explicit Call Bindings

**Files:**

- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_resume_command.py`

- [ ] Add `runtime_context_inputs` to `WorkflowProvenance` and thread it through the shared bundle pipeline, JSON/build projections, and `LoadedWorkflowBundle`.
- [ ] Add `workflow_runtime_context_inputs(...)` and make `workflow_public_input_contracts(...)` exclude both managed write-root and runtime-context hidden inputs while keeping `workflow_runtime_input_contracts(...)` as the full executable view.
- [ ] Extend `_public_rebind_inputs_for_force_restart(...)` to derive its scrub set from loaded-bundle provenance/helpers so stale or renamed runtime-owned context inputs are dropped alongside managed write-root internals before `bind_workflow_inputs(...)`.
- [ ] Extend `typecheck.py` so missing required `RunCtx` or `PhaseCtx` call bindings are accepted only on the promoted-entry hidden-binding route and otherwise still fail with `workflow_signature_mismatch`.
- [ ] Extend `_lower_call_expr(...)` so eligible promoted-entry omissions synthesize explicit flattened `call.with` bindings for each hidden context leaf, generate deterministic hidden input names, and record those names in `_LoweringContext.internal_generated_input_reasons` with `reason == "runtime_owned_context"`.
- [ ] Keep managed write-root binding composition intact on the same call step.
- [ ] Make hidden promoted-entry binding take precedence over synthetic top-level `PhaseCtx` default omission when both routes are available.
- [ ] Preserve ordinary authored-default omission for non-context parameters and ordinary workflows.

Implementation guardrails:

- Do not delete hidden inputs from the raw lowered workflow input map if shared validation still expects them there.
- Do not make public-helper filtering depend on prefix scanning when provenance is present.
- Do not satisfy the proof by reclassifying authored defaults as runtime-owned context inputs.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_lowering.py -k "promoted_entry or hidden_context or defaulted_call_bindings" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "public_inputs or generated_internal_inputs or managed_write_root" -q`
- [ ] `python -m pytest tests/test_resume_command.py -k "force_restart and (managed_orc_inputs or promoted_entry_hidden_context)" -q`

Expected after Task 3: lowering emits explicit hidden context `call.with` bindings, build artifacts record the new runtime-owned input class, public/runtime helper views diverge correctly, and force-restart filtering understands the new hidden-input class even though runtime execution still needs executor-owned value allocation.

### Task 4: Add Executor-Owned Hidden Context Allocation, Override Rejection, And Restart Hygiene

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_resume_command.py`

- [ ] Add an executor helper that discovers runtime-owned context inputs from loaded-bundle provenance and derives deterministic values for them before entry execution.
- [ ] Add `_entry_runtime_context_bindings(...)` and `_ensure_entry_runtime_context_bindings(...)` parallel to the existing managed-write-root binder pattern.
- [ ] Derive `run-id`, roots, and phase-specific values from the existing `StateManager.run_id` and Stage 5 phase-layout rules instead of inventing a second context model or requiring user inputs.
- [ ] Merge the executor-owned hidden values into `state.bound_inputs` before step execution and persist them so resume of the same run reuses the same values.
- [ ] Reject user-provided or mutated runtime-owned context inputs with `promoted_entry_hidden_context_override`.
- [ ] Fail explicitly with `promoted_entry_hidden_context_metadata_missing` if lowering/runtime expected hidden-context provenance but the compiled bundle is incomplete.
- [ ] Keep the force-restart regression green by ensuring the public rebind path remains aligned with runtime-owned context provenance after executor persistence lands.
- [ ] Keep managed write-root behavior unchanged and keep runtime blind to Workflow Lisp syntax; it should consume only compiled metadata and existing layout helpers.

Implementation guardrails:

- Do not special-case one fixture by workflow name.
- Do not accept or silently overwrite user-supplied runtime-owned context values.
- Do not change reusable/private workflow call transport beyond the promoted-entry entry binder.

**Blocking verification after Task 4:**

- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "promoted_entry and hidden_context" -q`
- [ ] `python -m pytest tests/test_resume_command.py -k "force_restart and (managed_orc_inputs or promoted_entry_hidden_context)" -q`

Expected after Task 4: the promoted-entry fixture executes successfully through the reusable-wrapper route with no public bootstrap inputs, override attempts fail deterministically, and a fresh `resume --force-restart` run rebinds only public inputs even after hidden runtime-context values were persisted.

### Task 5: Run The Recorded Narrow Verification Set

**Files:**

- No additional maintained source files; this task proves the slice with the recorded commands.

- [ ] Run the exact collect-only command from `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`:
  - `python -m pytest --collect-only tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_build_artifacts.py -q`
- [ ] Run collect-only for the added resume coverage because this slice adds a new selector-bearing test module:
  - `python -m pytest --collect-only tests/test_resume_command.py -q`
- [ ] Run the dedicated promoted-entry proof command from the same recorded set:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context -q`
- [ ] Run the focused lowering selector from the same recorded set:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "promoted_entry or hidden_context or defaulted_call_bindings" -q`
- [ ] Run the focused build/runtime-input selector from the same recorded set:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "public_inputs or generated_internal_inputs or managed_write_root" -q`
- [ ] Run the focused resume-force-restart selector that proves the hidden-input public-boundary contract still holds on a fresh run:
  - `python -m pytest tests/test_resume_command.py -k "force_restart and (managed_orc_inputs or promoted_entry_hidden_context)" -q`

## Stop / Revise Criteria

Stop this slice and return to design-gap selection rather than widening scope if any of these occur:

- proving `PhaseCtx` eligibility requires a new author-facing annotation or a second context model;
- the promoted-entry route cannot stay within the linked `compile_stage3_entrypoint(...)` graph and instead requires generalized metadata for arbitrary precompiled bundles;
- runtime value derivation cannot reuse existing run/phase layout rules and would require public bootstrap inputs or workflow-family-specific path policies;
- the only passing route still depends on synthetic top-level `PhaseCtx` defaults after explicit hidden bindings are added;
- satisfying the proof would require new inline glue, pointer-authority exceptions, or runtime changes outside the bounded hidden-input transport seam.

## Acceptance Checklist

- [ ] The promoted-entry reusable-wrapper fixture exposes only authored business inputs publicly.
- [ ] No public `phase-ctx__*`, `run-id`, `state-root`, `artifact-root`, or runtime-owned context inputs appear on the promoted-entry boundary.
- [ ] The lowered reusable-wrapper call includes explicit flattened `phase-ctx` bindings sourced from generated internal inputs.
- [ ] Runtime execution succeeds through the real `resume-or-start :valid-when (APPROVED)` route without explicit or defaulted authored `PhaseCtx` fallback wiring.
- [ ] Overriding a runtime-owned hidden context input fails deterministically.
- [ ] `resume --force-restart` strips persisted runtime-owned context inputs before rebinding the fresh run's public inputs.
- [ ] Synthetic `PhaseCtx` defaults remain compatibility-only and are not the reason the promoted-entry proof passes.
