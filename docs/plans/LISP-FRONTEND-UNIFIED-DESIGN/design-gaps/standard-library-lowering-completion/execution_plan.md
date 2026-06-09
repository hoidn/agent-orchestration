# Standard-Library Lowering Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one explicit compile-time-only lowering-contract inventory for the nine supported Workflow Lisp stdlib forms, wire it to the existing lowering/test seams, and prove the current Stage 3 lowering behavior matches that reviewed contract without changing runtime semantics or creating a second lowering pipeline.

**Architecture:** Keep the implementation inside `orchestrator/workflow_lisp/`. Add `stdlib_contracts.py` as the single reviewed contract inventory keyed to the current authored stdlib expression classes, model backend ownership as one-or-more allowed backend kinds when a form is an explicit command boundary, represent direct statement expectations as always-present families plus explicit return-shape-driven one-of alternatives, separate those alternatives from delegated lowering policy, record source-map expectations as compile-time contract data, expose one narrow lowering-side observation helper so tests can compare inventory expectations to emitted direct step families, and extend the existing stdlib test modules to assert backend ownership, fixed and alternative statement-family expectations, delegated-start rules, state-root policy, authority model, proof behavior, source-map lineage, adapter ownership, and compile-time-only status. Leave actual lowering in `lowering.py`, type/effect ownership in `typecheck.py`, helper-domain ownership in `phase_stdlib.py` / `resource_stdlib.py` / `drain_stdlib.py` / `resource.py`, and certified adapter registration in `compiler.py`.

**Tech Stack:** Python Workflow Lisp frontend, existing Stage 3 lowering path, shared workflow validation via `compile_stage3_module(..., validate_shared=True)`, pytest

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/standard-library-lowering-completion/implementation_architecture.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/2/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`

Current checkout facts that should not be rediscovered during implementation:

- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json` currently contains no events.
- The nine stdlib expression nodes already exist in `orchestrator/workflow_lisp/expressions.py`.
- `orchestrator/workflow_lisp/lowering.py` already contains:
  - `_lower_provider_result(...)`
  - `_lower_command_result(...)`
  - `_lower_run_provider_phase(...)`
  - `_lower_produce_one_of(...)`
  - `_lower_review_revise_loop(...)`
  - `_lower_resume_or_start(...)`
  - `_lower_resource_transition(...)`
  - `_lower_finalize_selected_item(...)`
  - `_lower_backlog_drain(...)`
- `compiler.py` already auto-registers:
  - `validate_reusable_phase_state`
  - `load_canonical_phase_result__<ReturnType>`
  - `apply_resource_transition`
- Current tests already cover many lowering details in:
  - `tests/test_workflow_lisp_lowering.py`
  - `tests/test_workflow_lisp_phase_stdlib.py`
  - `tests/test_workflow_lisp_resource_stdlib.py`
  - `tests/test_workflow_lisp_drain_stdlib.py`
  - `tests/test_workflow_lisp_build_artifacts.py`
  - `tests/test_workflow_lisp_examples.py`
  - `tests/test_workflow_lisp_procedures.py`
  - `tests/test_subworkflow_calls.py`

## Hard Scope Limits

Implement only this bounded slice:

- one shared compile-time-only lowering-contract inventory for the nine supported stdlib forms;
- one narrow observation helper so tests can compare lowered step families to the inventory without snapshotting unrelated workflow structure;
- focused test additions/realignments that make the reviewed contract a first-class acceptance surface;
- one missing shared-validation resource/finalization compile check if existing tests do not already cover it.

Explicit non-goals:

- no new stdlib author syntax, parser surfaces, macros, Core AST nodes, Semantic IR nodes, Executable IR nodes, or runtime-native effects;
- no second lowering path, runtime registry, hidden sidecar authority, or build artifact schema for stdlib contracts;
- no redesign of `typecheck.py`, pointer authority, report authority, reusable-state semantics, phase context construction, or managed write-root policy;
- no new adapters, no inline shell/Python glue, and no promotion of `resource-transition` or `resume-or-start` beyond the existing certified adapter contract.

## File Ownership

Create:

- `orchestrator/workflow_lisp/stdlib_contracts.py`

Modify:

- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Inspect but do not modify unless a failing test proves the need:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_examples.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_subworkflow_calls.py`

## Required Contract Surface

Implement the inventory as explicit data, not prose-only comments.

Suggested API in `orchestrator/workflow_lisp/stdlib_contracts.py`:

```python
@dataclass(frozen=True)
class StdlibLoweringContract:
    form_name: str
    expr_type: type[ExprNode]
    family: str
    backend_kinds: tuple[str, ...]
    required_statement_families: tuple[str, ...]
    alternative_statement_family_sets: tuple[tuple[str, ...], ...]
    delegated_statement_family_policy: str
    state_root_policies: tuple[str, ...]
    authority_model: str
    proof_model: str
    source_map_expectations: tuple[str, ...]
    primary_diagnostics: tuple[str, ...]
    helper_owner_modules: tuple[str, ...]
    adapter_binding_names: tuple[str, ...]
    test_surfaces: tuple[str, ...]

STDLIB_LOWERING_CONTRACTS: tuple[StdlibLoweringContract, ...]
STDLIB_LOWERING_CONTRACTS_BY_FORM: Mapping[str, StdlibLoweringContract]

def stdlib_contract_for_expr(expr_or_type: ExprNode | type[ExprNode]) -> StdlibLoweringContract: ...
```

Use stable string enums, not ad hoc free text, for:

- `family`
  - `structured_result_producer`
  - `review_reuse_control`
  - `resource_finalize_drain`
- `backend_kinds`
  - `provider`
  - `external_tool`
  - `certified_adapter`
  - `workflow_call`
  - `materialize_only`
- `statement_family_tokens`
  - `provider_step`
  - `command_step`
  - `output_bundle`
  - `variant_output`
  - `pre_snapshot`
  - `select_variant_output`
  - `repeat_until`
  - `match`
  - `materialize_artifacts`
  - `workflow_call`
  - `publishes`
- `delegated_statement_family_policy`
  - `none`
  - `resume_start_branch_delegates_to_wrapped_expression`
- `state_root_policies`
  - `generated_hidden_bundle_input`
  - `active_phase_bundle`
  - `active_phase_bundle_plus_snapshot`
  - `repeat_until_generated_bundle`
  - `managed_reusable_boundary_inputs`
  - `item_or_drain_layout_projection`
- `source_map_expectations`
  - `high_level_form_origin`
  - `generated_step_span`
  - `generated_hidden_input_span`
  - `generated_hidden_path_span`
  - `adapter_command_step_origin`

Every inventory entry must record source-map expectations as reviewed data, not
as prose-only commentary. At minimum, each form records authored-form origin
and generated-step lineage; forms that allocate hidden bundle inputs or derived
paths also record hidden-input or generated-path coverage, and adapter-backed
forms record the high-level-form to generated-command-step lineage required by
the approved architecture.

Interpret the statement-family fields as follows:

- `required_statement_families` lists the family tokens that must always be observed for the form's fixed lowering scaffold.
- `alternative_statement_family_sets` lists one-or-more exact one-of requirements. Each inner tuple is a closed set of allowed alternatives, and tests must prove that exactly one token from each inner tuple is observed for the lowered fixture under test.
- This slice only needs one alternation rule: return-shape-driven bundle emission where lowering produces exactly one of `output_bundle` or `variant_output`.

Required inventory entries:

- `provider-result`
  - family: `structured_result_producer`
  - backends: `provider`
  - required statement families: `provider_step`
  - alternative statement family sets: exactly one of `output_bundle`, `variant_output`
  - delegated statement policy: `none`
  - state roots: `generated_hidden_bundle_input`, plus `active_phase_bundle` for the current implementation-attempt phase special case
- `command-result`
  - family: `structured_result_producer`
  - backends: `external_tool`, `certified_adapter`
  - required statement families: `command_step`
  - alternative statement family sets: exactly one of `output_bundle`, `variant_output`
  - delegated statement policy: `none`
  - command-boundary rule: the form stays an explicit command boundary even when the bound command is a certified adapter
- `run-provider-phase`
  - family: `structured_result_producer`
  - backends: `provider`
  - required statement families: `materialize_artifacts`, `provider_step`
  - alternative statement family sets: exactly one of `output_bundle`, `variant_output`
  - delegated statement policy: `none`
  - state roots: `active_phase_bundle`
- `produce-one-of`
  - family: `structured_result_producer`
  - backends: `provider`
  - required statement families: `materialize_artifacts`, `pre_snapshot`, `provider_step`, `select_variant_output`, `match`
  - alternative statement family sets: none
  - delegated statement policy: `none`
  - state roots: `active_phase_bundle_plus_snapshot`
  - proof model: snapshot-diff evidence plus validated variant selection
- `review-revise-loop`
  - family: `review_reuse_control`
  - backends: `provider`
  - required statement families: `repeat_until`, `provider_step`, `output_bundle`, `match`, `materialize_artifacts`
  - alternative statement family sets: none
  - delegated statement policy: `none`
  - state roots: `repeat_until_generated_bundle`
- `resume-or-start`
  - family: `review_reuse_control`
  - backends: `certified_adapter`
  - required statement families: `command_step`, `variant_output`, `match`
  - alternative statement family sets: none
  - delegated statement policy: `resume_start_branch_delegates_to_wrapped_expression`
  - start-branch rule: the inventory records only the fixed validator/loader/normalization scaffold; the `START` branch is verified by asserting it lowers through an already-supported wrapped expression without introducing hidden semantics or a second lowering path
  - state roots: `managed_reusable_boundary_inputs`
  - adapter bindings: `validate_reusable_phase_state`, `load_canonical_phase_result__<ReturnType>`
- `resource-transition`
  - family: `resource_finalize_drain`
  - backends: `certified_adapter`
  - required statement families: `command_step`, `output_bundle`
  - alternative statement family sets: none
  - delegated statement policy: `none`
  - state roots: `generated_hidden_bundle_input`
  - adapter binding: `apply_resource_transition`
- `finalize-selected-item`
  - family: `resource_finalize_drain`
  - backends: `materialize_only`
  - required statement families: `match`, `materialize_artifacts`, `publishes`
  - alternative statement family sets: none
  - delegated statement policy: `none`
  - state roots: `item_or_drain_layout_projection`
- `backlog-drain`
  - family: `resource_finalize_drain`
  - backends: `workflow_call`
  - required statement families: `repeat_until`, `workflow_call`, `materialize_artifacts`, `match`, `publishes`
  - alternative statement family sets: none
  - delegated statement policy: `none`
  - state roots: `managed_reusable_boundary_inputs`, `item_or_drain_layout_projection`

## Task 1: Lock The Contract Surface In Tests First

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Add a unit test in `tests/test_workflow_lisp_lowering.py` that imports the new inventory module and asserts it covers exactly the nine supported stdlib forms and the nine existing authored expression classes.
- [ ] Add a structured-result-family regression in `tests/test_workflow_lisp_lowering.py` that compares the contract entries for `provider-result` and `command-result` against the already lowered `structured_results.orc` workflows `provider_attempt` and `command_checks`, including both the always-present families and the exact-one return-shape alternative requirement that permits either `output_bundle` or `variant_output`.
- [ ] Add one positive adapter-backed `command-result` regression in `tests/test_workflow_lisp_drain_stdlib.py` by reusing an authored certified-adapter fixture path such as `execute_selected_item` or `draft_gap_item`; do not use the negative phase-stdlib `load_resume_state` rejection surface as the positive proof.
- [ ] Extend `tests/test_workflow_lisp_phase_stdlib.py` with a family-level regression that checks:
  - `run-provider-phase`
  - `produce-one-of`
  - `review-revise-loop`
  - `resume-or-start`
  against the inventory's backend kinds, required statement families, alternative statement-family sets, delegated-start policy, state-root policies, source-map expectations, and adapter-binding expectations.
- [ ] Extend `tests/test_workflow_lisp_resource_stdlib.py` with a family-level regression that checks `resource-transition` and `finalize-selected-item` against the inventory, including the approved generated-step and hidden-input/path source-map coverage.
- [ ] Extend `tests/test_workflow_lisp_drain_stdlib.py` with contract regressions that:
  - prove the positive certified-adapter `command-result` fixture matches the reviewed command-boundary contract and adapter-command-step lineage; and
  - prove `backlog-drain` matches the inventory's `workflow_call`, loop-scoped managed write-root expectations, and family-level source-map coverage.
- [ ] Add a build-artifact regression in `tests/test_workflow_lisp_build_artifacts.py` proving the new inventory remains compile-time only and does not appear in generated source-map JSON, boundary projections, or build artifact payloads.
- [ ] Add one missing shared-validation compile test in `tests/test_workflow_lisp_resource_stdlib.py` for the `resource-transition` + `finalize-selected-item` fixture if the current file still lacks that integration proof after the new contract assertions are in place.

Suggested new test names:

- `test_stdlib_contract_inventory_covers_supported_frontend_forms`
- `test_structured_result_family_contract_matches_lowered_provider_and_command_forms`
- `test_command_result_contract_accepts_certified_adapter_backends_without_hiding_command_boundary`
- `test_phase_stdlib_contract_inventory_matches_lowering_families`
- `test_resource_stdlib_contract_inventory_matches_lowering_families`
- `test_backlog_drain_contract_inventory_matches_loop_managed_call_lowering`
- `test_stdlib_contract_inventory_is_compile_time_only_and_not_serialized_into_frontend_build_artifacts`
- `test_shared_validation_accepts_resource_transition_and_finalize_selected_item`

**Blocking verification after Task 1:**

- [ ] Run:
  - `pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_build_artifacts.py -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_stdlib_contract_inventory_covers_supported_frontend_forms -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_structured_result_family_contract_matches_lowered_provider_and_command_forms -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_drain_stdlib.py::test_command_result_contract_accepts_certified_adapter_backends_without_hiding_command_boundary -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_contract_inventory_matches_lowering_families -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_resource_stdlib.py::test_resource_stdlib_contract_inventory_matches_lowering_families -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_contract_inventory_matches_loop_managed_call_lowering -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_build_artifacts.py::test_stdlib_contract_inventory_is_compile_time_only_and_not_serialized_into_frontend_build_artifacts -q`

Expected before implementation: the new tests fail because `stdlib_contracts.py` does not yet exist, there is no reviewed single-source inventory for the nine forms, and no common lowering-side observation seam exists for asserting family-level contract facts without restating lowering internals in every test.

## Task 2: Add The Shared Compile-Time Contract Inventory

**Files:**

- Create: `orchestrator/workflow_lisp/stdlib_contracts.py`

- [ ] Add the `StdlibLoweringContract` dataclass and the canonical inventory constants.
- [ ] Import the nine authored expression classes directly from `orchestrator.workflow_lisp.expressions` so coverage is tied to the current frontend surface, not duplicated string names.
- [ ] Encode the exact family, allowed backend kinds, required statement families, alternative statement-family sets, delegated statement-family policy, state-root policies, authority model, proof model, source-map expectations, diagnostic owners, helper-owner modules, adapter binding names, and test-surface names for all nine forms.
- [ ] Make `command-result` the only multi-backend entry in this slice by recording the explicit command-boundary rule with `external_tool` and `certified_adapter` as the allowed backend kinds.
- [ ] Make `provider-result`, `command-result`, and `run-provider-phase` the only entries with return-shape-driven statement-family alternation by recording a single exact-one alternative set `("output_bundle", "variant_output")`.
- [ ] Make `resume-or-start` the only delegated-family entry in this slice by recording only the fixed reuse scaffold in `required_statement_families` and using `resume_start_branch_delegates_to_wrapped_expression` for the `START` arm.
- [ ] Provide one lookup helper that accepts either an expression instance or expression class and raises a narrow error if a supported stdlib form is missing from the inventory.
- [ ] Keep the module compile-time only:
  - no runtime registration;
  - no serialization hooks;
  - no dependency on `lowering.py`;
  - no dependency on build artifact writers.

Implementation guardrails:

- Do not move actual lowering logic into the contract module.
- Do not make the inventory an alternate executor or validator.
- Do not widen backend authority beyond what `compiler.py`, `typecheck.py`, and current lowering already enforce.

**Blocking verification after Task 2:**

- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_stdlib_contract_inventory_covers_supported_frontend_forms -q`

Expected after Task 2: inventory-coverage tests pass, but family-level tests may still fail until lowering exposes a narrow way to compare emitted step families against the new contract entries and the exact-one alternative-family rules.

## Task 3: Add A Narrow Lowering Observation Seam Without Changing Lowering Semantics

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`

- [ ] Add one lowering-local helper that summarizes emitted step structure into the normalized statement-family token vocabulary used by the inventory's required and alternative expectations.
- [ ] Keep the helper read-only over emitted steps. It may inspect already lowered step dictionaries, but it must not change lowering behavior, step IDs, hidden inputs, or path allocation.
- [ ] Keep source-map coverage assertions on the existing lowered workflow `origin_map` surface instead of inventing a second source-map summary structure; the new helper is only for direct statement-family observation.
- [ ] Make the helper capable of recognizing at least:
  - `provider_step`
  - `command_step`
  - `output_bundle`
  - `variant_output`
  - `pre_snapshot`
  - `select_variant_output`
  - `repeat_until`
  - `match`
  - `materialize_artifacts`
  - `workflow_call`
  - `publishes`
- [ ] Add a tiny coverage assertion or helper-level test seam tying the observation helper to the stdlib inventory so missing inventory coverage cannot silently drift from the supported lowering entrypoints, and so tests can assert all required families plus the exact-one alternative sets without inventing per-test conventions.
- [ ] Keep `resume-or-start` delegated `START`-arm verification separate from the direct-family helper: use the helper for the fixed scaffold, and keep targeted branch inspection for proving the wrapped expression still lowers through an already-supported command/workflow/provider path.
- [ ] Reuse existing nested-step traversal patterns already present in tests or lowering helpers; do not introduce a second recursive lowering model.

Suggested helper shape:

```python
def _observed_statement_families(steps: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    ...
```

Implementation guardrails:

- Do not emit the observed families into authored workflow dictionaries.
- Do not add inventory metadata into source maps, boundary projections, or validated bundles.
- Do not wrap or replace the existing `origin_map` data model with stdlib-specific metadata; tests should read the current source-map structures directly.
- Do not convert prose fields like `authority_model` or `proof_model` into runtime semantics.

**Blocking verification after Task 3:**

- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_lowering.py::test_structured_result_family_contract_matches_lowered_provider_and_command_forms -q`
- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_contract_inventory_matches_lowering_families -q`
- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_resource_stdlib.py::test_resource_stdlib_contract_inventory_matches_lowering_families -q`
- [ ] Re-run:
  - `pytest tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_contract_inventory_matches_loop_managed_call_lowering -q`

Expected after Task 3: the family-level tests can compare lowered workflows to the reviewed contract inventory without snapshotting unrelated fields or introducing a second lowering pipeline, and `resume-or-start` can prove its fixed scaffold independently from the delegated `START` arm.

## Task 4: Finish Adapter, Shared-Validation, And Build-Artifact Acceptance

**Files:**

- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Make the `resume-or-start` contract assertions prove the inventory points to the certified adapter bindings already auto-registered by `compiler.py`, while keeping `START`-arm family assertions delegated to the wrapped expression path instead of collapsing them into one fixed tuple.
- [ ] Make the positive adapter-backed `command-result` regression in `tests/test_workflow_lisp_drain_stdlib.py` prove that a certified-adapter binding still lowers as an explicit `command_step` boundary with the recorded `adapter_command_step_origin` source-map lineage rather than being treated as a hidden runtime-native shortcut.
- [ ] Make the `resource-transition` contract assertions prove the inventory points to `apply_resource_transition` and preserves the declared `resource_transition` + `ledger_update` effect boundary.
- [ ] Add the missing shared-validation resource/finalization compile path if it does not already exist after Task 1:
  - compile `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
  - use `validate_shared=True`
  - assert the compile succeeds without needing any new runtime surface.
- [ ] Keep `tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_validates_backlog_drain_through_shared_surface` as the drain-family integration proof.
- [ ] Keep `tests/test_workflow_lisp_phase_stdlib.py` shared-validation tests as the structured-result and review/reuse integration proofs.
- [ ] Make the build-artifact test explicitly assert that strings or fields naming:
  - `StdlibLoweringContract`
  - `structured_result_producer`
  - `review_reuse_control`
  - `resource_finalize_drain`
  - `source_map_expectations`
  are absent from serialized frontend build artifacts.

**Blocking verification after Task 4:**

- [ ] Run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_run_provider_phase_and_produce_one_of -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_review_revise_loop -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_resume_or_start -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_resource_stdlib.py::test_shared_validation_accepts_resource_transition_and_finalize_selected_item -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_validates_backlog_drain_through_shared_surface -q`
- [ ] Run:
  - `pytest tests/test_workflow_lisp_build_artifacts.py::test_stdlib_contract_inventory_is_compile_time_only_and_not_serialized_into_frontend_build_artifacts -q`

Expected after Task 4: the reviewed contract is fully covered across all three lowering families, adapter-backed forms remain explicitly tied to the certified command-adapter contract, and no runtime/build artifact surface is polluted by the new compile-time inventory.

## Final Verification

- [ ] Run the focused module suite:
  - `pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_build_artifacts.py -q`
- [ ] Run the integration/example guardrails that exercise the broader shared-validation path:
  - `pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q`
  - `pytest tests/test_workflow_lisp_examples.py::test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack -q`
  - `pytest tests/test_workflow_lisp_procedures.py::test_private_workflow_call_reuses_managed_write_root_allocator -q`
  - `pytest tests/test_subworkflow_calls.py::test_reusable_workflow_rejects_hard_coded_dsl_managed_write_root -q`

## Implementation Notes

- Preserve the current lowering/runtime split: the inventory documents lowering behavior; it does not become runtime behavior.
- Prefer strengthening existing tests over adding brand-new fixtures when the current `.orc` fixtures already exercise the target form.
- If a test needs to assert direct contract-family facts for nested steps, use the lowering observation helper rather than duplicating ad hoc nested-step inspection logic in multiple files.
- For `resume-or-start`, treat the reviewed inventory as the contract for the fixed reusable-state scaffold only; verify the delegated `START` branch with targeted existing branch-shape assertions so the plan does not invent a false closed set of wrapped-expression families.
- For `command-result`, treat the reviewed inventory as an explicit command-boundary contract whose backend set is `{external_tool, certified_adapter}`; fixture-level tests should still prove which concrete backend kind the current binding exercises.
- Record the final verification commands and outcomes in the implementation summary/report for this drain item.
