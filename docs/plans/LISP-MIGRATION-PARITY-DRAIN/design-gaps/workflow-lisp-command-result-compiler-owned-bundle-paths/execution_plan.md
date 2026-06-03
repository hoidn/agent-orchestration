# Workflow Lisp Command-Result Compiler-Owned Bundle Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `command-result` managed bundle paths compiler/runtime-owned by removing `__write_root__...` inputs from the public compiled-workflow boundary, preserving them as provenance-tagged internal inputs, making every entry-workflow binding path consume the public view, and making entry-workflow runtime execution allocate those paths automatically without user binding.

**Architecture:** Treat the lowered workflow `inputs` map as a compatibility/debug view, not the public API. Add provenance-aware input helpers in `orchestrator/workflow/loaded_bundle.py` that split public inputs from runtime-required managed inputs using `WorkflowProvenance.managed_write_root_inputs`, then route imported signature reconstruction and CLI entry binding through the public view while runtime call/executor validation consumes the runtime view. Entry-workflow execution allocates deterministic run-scoped write-root relpaths for managed `command-result` bundle inputs, rejects user overrides, persists the merged bindings for resume, requires `resume --force-restart` to rebind only the persisted public subset for the new run, and leaves the existing `output_bundle.path -> ORCHESTRATOR_OUTPUT_BUNDLE_PATH` contract unchanged.

**Tech Stack:** Python 3, Workflow Lisp frontend build artifacts, typed loaded bundles, shared workflow executor/runtime, `pytest`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/1/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `specs/dsl.md`
- `specs/io.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/lowering.py` already classifies command-result bundle roots through `generated_internal_inputs` with reason `managed_write_root`.
- `orchestrator/workflow/loaded_bundle.py` already exposes `workflow_managed_write_root_inputs(...)`, but `workflow_input_contracts(...)` still returns the full input map.
- `orchestrator/workflow_lisp/workflows.py` still reconstructs imported signatures by scanning the full input map and skipping `__write_root__...` by prefix.
- `orchestrator/workflow/calls.py` still validates reusable-call bindings against the full input map.
- `orchestrator/cli/commands/run.py` still binds user-supplied entry inputs against `workflow_input_contracts(...)`, so hidden managed names remain part of the public entry boundary today.
- `orchestrator/cli/commands/resume.py --force-restart` still rebinds persisted `state.bound_inputs` against `workflow_input_contracts(...)`, so a restarted run can revalidate executor-owned managed inputs as if they were public authored inputs.
- `orchestrator/workflow/executor.py` still treats `state.bound_inputs` as the full runtime input bag and does not allocate entry managed write roots.
- `tests/test_workflow_lisp_key_migrations.py` still proves the leak by manually binding top-level managed write-root inputs before executing `cycle_guard_demo.orc`.

## Hard Scope Limits

Implement only this bounded slice:

- provenance-aware public-vs-runtime compiled-workflow input views;
- imported signature reconstruction against the public view;
- CLI/public entry binding against the public view, including `resume --force-restart` rebinding;
- runtime call/executor consumption of the runtime view;
- deterministic runtime-owned entry binding for managed `command-result` bundle paths;
- focused regressions proving public helpers and entry binders hide managed inputs, runtime entry execution no longer needs manual hidden-input binding, force restart strips executor-owned managed inputs before rebinding, user overrides are rejected, and reusable/private workflow managed bindings still work.

Explicit non-goals:

- no redesign of `command-result` lowering, `output_bundle`, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, provider-result, review-loop composition, `resume-or-start`, reusable-state validation, or workflow input defaults;
- no wrapper commands, inline Python/shell glue, pointer-as-state compatibility, or stdout-as-authority shortcuts;
- no broad write-root redesign for provider steps or non-`command-result` surfaces;
- no migration promotion reporting, `non_regressive` computation, or YAML deprecation work;
- no unrelated frontend/runtime refactors outside the public/runtime input-boundary seam.

## File Ownership

Modify:

- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/cli/commands/run.py`
- `orchestrator/cli/commands/resume.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/calls.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_resume_command.py`
- `tests/test_subworkflow_calls.py`

Inspect and modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/lowering.py`

Do not modify unless verification forces it:

- `specs/dsl.md`
- `specs/io.md`
- command adapter scripts under `scripts/`
- unrelated workflow-lisp review-loop, defaults, or reusable-state modules

## Required Helper Contract

Implement the boundary split around explicit loaded-bundle helper surfaces.

Recommended helper surface:

```python
def workflow_public_input_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    ...

def workflow_runtime_input_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    ...
```

Rules:

- The public view excludes every input named in `workflow_managed_write_root_inputs(...)`.
- The runtime view includes public inputs plus managed write-root inputs.
- Provenance is the primary authority for the managed-input set; raw `__write_root__` prefix scanning remains compatibility fallback only when provenance is absent.
- Raw surface/lowered input maps may still include managed names for validation/debug compatibility, but public helpers must not expose them as user-bindable entry inputs.
- `orchestrator run` and `resume --force-restart` must bind against the public view, not the raw lowered mapping.
- Imported signature reconstruction must consume the public view.
- Runtime call validation and entry execution must consume the runtime view.

Entry-runtime allocator policy:

- Runtime-owned managed inputs for entry workflows live under:

```text
.orchestrate/workflow_lisp/entry/<run_id>/<workflow_name>/<managed_input>.json
```

- Allocation must be workspace-relative, deterministic for a given `run_id`, and stable across resume of the same run.
- If the caller/user supplied any runtime-owned managed input directly at the entry boundary, execution must fail explicitly instead of silently reusing or overwriting it.
- Once merged into `state.bound_inputs`, the existing command-step bundle-path injection remains unchanged.
- `resume --force-restart` must drop executor-owned managed write-root bindings from persisted state before rebinding authored inputs for the new run, so the replacement run allocates fresh run-scoped managed paths.

## Task 1: Lock The Regression Surface Before Changing Helper Semantics

**Files:**

- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_cli.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_subworkflow_calls.py`

- [ ] Add or tighten tests proving public compiled-workflow input helpers do not expose managed `__write_root__...` inputs while `workflow_managed_write_root_inputs(...)` and boundary-projection artifacts still retain them.
- [ ] Add CLI-facing regressions proving `orchestrator run` for the affected `.orc` entry workflows binds only public inputs, so dry-run/public validation no longer requires or advertises managed `__write_root__...` names.
- [ ] Update the key-migration runtime coverage so `cycle_guard_demo.orc` executes without manually injecting a hidden bundle-path input at run initialization.
- [ ] Add a `resume --force-restart` regression proving persisted executor-owned managed write-root bindings are stripped before rebound validation for the new run, while genuinely invalid authored inputs still fail.
- [ ] Add a focused runtime regression that explicitly fails when a user attempts to override an entry-workflow managed write-root input.
- [ ] Keep reusable/private workflow regressions asserting caller-generated internal bindings still exist for imported/runtime calls and still reject colliding write-root bindings.
- [ ] Keep source-map/build-artifact assertions pinned to `generated_internal_inputs[*].reason == "managed_write_root"` so this slice cannot satisfy itself by deleting provenance.

Suggested test targets to add or update:

- `test_compiled_bundle_public_input_contracts_exclude_managed_write_roots`
- `test_run_workflow_orc_public_binding_excludes_managed_write_roots`
- `test_cycle_guard_demo_orc_runtime_materializes_output_bundle_without_hidden_input_binding`
- `test_resume_force_restart_rebinds_only_public_inputs_for_orc_bundle`
- `test_cycle_guard_demo_orc_rejects_user_override_of_runtime_owned_write_root`
- `test_reusable_call_runtime_write_root_bindings_still_validate`

**Blocking verification after Task 1:**

- [ ] Run:
  - `python -m pytest --collect-only tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_build_artifacts.py tests/test_subworkflow_calls.py -q`
- [ ] Run:
  - `python -m pytest --collect-only tests/test_workflow_lisp_cli.py tests/test_resume_command.py -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "cycle_guard_demo or design_plan_impl_stack" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "generated_internal_inputs or boundary_projection or imported_workflow_bundles" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_cli.py -k "public_binding or dry_run" -q`

Expected before implementation: new public-helper assertions fail because public helpers still expose raw managed inputs, `run`/`resume --force-restart` still validate against the hidden-input helper, and the runtime migration test still needs manual hidden-input binding.

## Task 2: Add Provenance-Aware Public And Runtime Input Views And Patch Entry Binders

**Files:**

- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_cli.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_subworkflow_calls.py`

- [ ] Add explicit loaded-bundle helpers for public input contracts and runtime input contracts, driven by `workflow_managed_write_root_inputs(...)`.
- [ ] Keep `workflow_managed_write_root_inputs(...)` provenance-first; retain raw-prefix fallback only for older bundles without provenance metadata.
- [ ] Update `orchestrator/cli/commands/run.py` to bind raw entry inputs against the public helper so hidden managed write-root names stop participating in dry-run and start-of-run public validation.
- [ ] Update `orchestrator/cli/commands/resume.py --force-restart` to reconstruct the persisted public-input subset before rebinding the new run, excluding executor-owned managed write-root keys while preserving authored inputs for type/contract validation.
- [ ] Update imported workflow signature reconstruction in `orchestrator/workflow_lisp/workflows.py` to consume the public view instead of skipping `__write_root__...` names by prefix.
- [ ] Update reusable-call runtime binding validation in `orchestrator/workflow/calls.py` to consume the runtime view so compiler-generated `call.with.__write_root__...` bindings remain valid internal transport.
- [ ] Preserve imported-bundle compatibility: internal managed inputs must still be available for reusable/private workflow calls even though they disappear from the public boundary helpers.
- [ ] If `orchestrator/workflow_lisp/lowering.py` needs a narrow tweak, limit it to preserving or surfacing provenance needed by the new helpers; do not reopen lowering shape or naming.

Implementation guardrails:

- Do not use naming convention alone when provenance is available.
- Do not delete managed names from the raw lowered mapping if shared validation still expects them there.
- Do not make `resume --force-restart` reuse executor-merged managed write-root paths from the previous run; a new run id must allocate its own managed relpaths after public rebinding succeeds.
- Do not require reusable/private workflow callers to infer internal bindings from public signatures.

**Blocking verification after Task 2:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "managed_write_root or command_checks or provider_attempt" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "generated_internal_inputs or boundary_projection or imported_workflow_bundles" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_cli.py -k "public_binding or dry_run" -q`
- [ ] Run:
  - `python -m pytest tests/test_resume_command.py -k "force_restart_rebinds_only_public_inputs or force_restart_invalid_inputs" -q`
- [ ] Run:
  - `python -m pytest tests/test_subworkflow_calls.py -k "managed_write_root or write_root_binding" -q`

Expected after Task 2: public helpers hide managed inputs, `run` and `resume --force-restart` validate only the public boundary, imported signature reconstruction stops relying on prefix stripping, and reusable/private runtime call validation still accepts compiler-generated internal write-root bindings.

## Task 3: Make Entry Runtime Own Managed Command-Result Bundle Paths

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_subworkflow_calls.py`

- [ ] Add one executor-local helper that discovers entry managed write-root inputs from the loaded bundle provenance and allocates deterministic run-scoped relpaths under `.orchestrate/workflow_lisp/entry/<run_id>/<workflow_name>/...`.
- [ ] Merge those runtime-owned values into `state.bound_inputs` before any step execution that can resolve `${inputs.__write_root__...}` references.
- [ ] Reject explicit user/caller overrides for runtime-owned managed inputs with a focused contract violation or v2.14 failure payload; do not silently accept or overwrite them.
- [ ] Persist the merged bindings back through the existing run-state path so resume of the same `run_id` reuses the same bundle targets.
- [ ] Preserve the public/runtime boundary when persisted state already contains merged managed bindings: normal resume may reuse them for the same run, but `resume --force-restart` must not treat them as public authored inputs for the new run.
- [ ] Keep the existing `output_bundle.path` resolution and `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` injection logic unchanged once the runtime-owned input is present.
- [ ] Ensure reusable/private workflow call validation remains unchanged semantically: this task is only for entry workflows, not a redesign of nested call transport.

Implementation guardrails:

- Do not hard-code a single bundle path per workflow independent of `run_id`.
- Do not require `StateManager.initialize(...)` callers or tests to know managed input names.
- Do not special-case one migration fixture by workflow name.
- Do not depend on CLI-only filtering for safety; executor-time override rejection must still protect non-CLI or legacy state entry paths.

**Blocking verification after Task 3:**

- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "cycle_guard_demo or design_plan_impl_stack" -q`
- [ ] Run:
  - `python -m pytest tests/test_workflow_lisp_cli.py -k "public_binding or dry_run" -q`
- [ ] Run:
  - `python -m pytest tests/test_resume_command.py -k "force_restart_rebinds_only_public_inputs or force_restart_invalid_inputs" -q`
- [ ] Run:
  - `python -m pytest tests/test_subworkflow_calls.py -k "managed_write_root or write_root_binding" -q`

Expected after Task 3: the public entry boundary no longer advertises or requires hidden managed inputs, entry execution succeeds without manual hidden-input binding, force restart rebinds only authored/public inputs before allocating new managed paths, override attempts fail explicitly, and existing reusable/private write-root runtime guardrails still hold.

## Task 4: Run The Recorded Narrow Verification Set

**Files:**

- No additional maintained source files; this task proves the bounded slice with the recorded commands.

- [ ] Run the exact collect-only command from `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`:
  - `python -m pytest --collect-only tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_build_artifacts.py tests/test_subworkflow_calls.py -q`
- [ ] Run collect-only for the added entry-boundary regression modules:
  - `python -m pytest --collect-only tests/test_workflow_lisp_cli.py tests/test_resume_command.py -q`
- [ ] Run the lowering-focused regression command:
  - `python -m pytest tests/test_workflow_lisp_lowering.py -k "managed_write_root or command_checks or provider_attempt" -q`
- [ ] Run the build-artifact/provenance regression command:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "generated_internal_inputs or boundary_projection or imported_workflow_bundles" -q`
- [ ] Run the public entry-binding regression command:
  - `python -m pytest tests/test_workflow_lisp_cli.py -k "public_binding or dry_run" -q`
- [ ] Run the key-migration runtime regression command:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "cycle_guard_demo or design_plan_impl_stack" -q`
- [ ] Run the force-restart rebinding regression command:
  - `python -m pytest tests/test_resume_command.py -k "force_restart_rebinds_only_public_inputs or force_restart_invalid_inputs" -q`
- [ ] Run the reusable-call/runtime guardrail regression command:
  - `python -m pytest tests/test_subworkflow_calls.py -k "managed_write_root or write_root_binding" -q`
- [ ] If a test name was added or renamed in one of the touched modules, rerun `--collect-only` for that module before the full module command.

Success criteria for this task:

- public helpers no longer surface managed command-result bundle roots;
- `orchestrator run` and `resume --force-restart` bind only the public entry surface for compiled `.orc` workflows;
- boundary projection and provenance still record those roots as internal managed inputs;
- key migration runtime coverage no longer injects hidden top-level write-root bindings by hand;
- force restart drops persisted executor-owned managed inputs before rebinding authored inputs for the new run;
- runtime rejects entry override attempts for managed inputs;
- reusable/private workflow write-root transport and runtime collision checks remain green.

## Explicit Non-Goals

- Do not rewrite `command-result` lowering into a different command or adapter surface.
- Do not change shared spec text unless a verification failure proves the implementation currently contradicts `specs/dsl.md` or `specs/io.md`.
- Do not expand this slice into review-loop generic composition, input defaults, reusable-state validation, promotion evidence, or YAML deprecation.
- Do not weaken tests by asserting literal prompt text or by deleting the current provenance/build-artifact coverage.
