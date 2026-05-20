# DSL v2.14 YAML Ergonomics LOC Reduction Execution Plan

> **For agentic workers:** This plan is the execution authority for `2026-05-09-dsl-v214-yaml-ergonomics-loc-reduction`. Keep work inside the current backlog item and Phase 2 gate. Steps use checklist syntax for tracking.

**Goal:** Make the translated v2.14 NeurIPS production stack shorter than the legacy four-file stack without weakening Phase 1 semantics, oracle equivalence, or same-version v2.14 workflow composition.

**Architecture:** Add two narrow ergonomics surfaces to the released v2.14 contract model: `variant_output.shared_fields` for always-present tagged-union fields and `materialize_artifacts.input_values` for repeated input-to-pointer materialization. Then rewrite the selected-item v2.14 workflow to validate native JSON bundles directly, apply the new shorthand where it removes repetition, and prove the result with deterministic LOC and equivalence checks.

**Tech Stack:** Python loader/runtime, YAML workflows, pytest, NeurIPS oracle fixtures, output-contract and prompt-contract modules, repo-local workflow scripts, and `python -m orchestrator` dry-run validation.

---

## Objective, Scope, And Non-Goals

**Objective**

- Deliver the Phase 2 ergonomics correction described by `docs/design/dsl_v214_yaml_ergonomics.md`: preserve behavioral equivalence while making the v2.14 production stack shorter than the legacy stack.

**In Scope**

- Add `variant_output.shared_fields` to the v2.14 loader, contract validation, prompt-contract rendering, and runtime artifact exposure path.
- Add `materialize_artifacts.input_values` as a narrow shorthand that expands to the same internal representation as long-form `values`.
- Rewrite `workflows/library/neurips_selected_backlog_item.v214.yaml` so `selected-item-inputs.json` stays native and is validated directly instead of being exploded into per-field text files.
- Apply `input_values` to the translated v2.14 subworkflows where it removes uniform repeated input materialization.
- Add deterministic LOC comparison tooling and tests.
- Update the normative and workflow-author docs that describe the compact v2.14 authoring pattern.

**Explicit Non-Goals**

- Do not reopen the public `version: "2.14"` release decision.
- Do not add later-roadmap abstractions such as `recover_or_run`, `resource_transition`, `phase_outcome`, review-loop macros, mixed-version calls, or a general expression language.
- Do not remove `variant_output`, `select_variant_output`, or `materialize_artifacts`.
- Do not delete the legacy workflow stack.
- Do not change provider prompt semantics except where `variant_output.shared_fields` must render once in the injected contract block.
- Do not broaden work into new Phase 1 runtime semantics unless a concrete regression in the scoped checks makes that unavoidable.

## Steering, Roadmap, And Prerequisite Constraints

- Steering binds this work to the ordered roadmap in `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md` and the design authority in `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`.
- The active roadmap gate is `dsl-v214-phase2-neurips-stack`; stay within `phase-2-dsl-v214-neurips-stack`.
- The progress ledger records `phase-1-dsl-v214-runtime` and `dsl-v214-public-release` as completed. Treat Phase 1 semantics and public v2.14 support as fixed prerequisites, not open design space.
- Same-version v2.14 calls, path-safety rules, output-contract validation, and network-free workflow tests remain mandatory.
- If implementation reveals a real mismatch among roadmap, steering, and this backlog item, resolve it with the narrowest possible roadmap or plan correction. Do not silently expand scope.
- Do not mark the item `BLOCKED` for ordinary test, import, path, substitution, or harness failures. Diagnose, fix, and rerun first. Reserve `BLOCKED` for missing resources, unavailable hardware, external dependency failure outside repo authority, required user decision, roadmap conflict, or an unrecoverable failure that remains after a documented narrow fix attempt.

## Implementation Architecture

- **Contract surface unit:** Loader and contract modules own parsing, normalization, duplicate detection, inheritance/refinement checks, and prompt-contract rendering for `shared_fields` and `input_values`.
- **Runtime lowering/execution unit:** Workflow IR, lowering, and executor modules own expansion of `input_values`, runtime exposure of shared fields, and the guarantee that shorthand and long-form materialization produce the same durable artifact behavior.
- **Workflow translation unit:** The NeurIPS v2.14 YAML files consume the new surfaces to remove bundle field fanout while preserving same-version calls and oracle-visible behavior.
- **Evidence/documentation unit:** LOC tooling, tests, and spec/workflow docs prove the new authoring pattern and capture it as durable project knowledge.

## File And Artifact Targets

**Mandatory contract-affecting targets**

- `orchestrator/loader.py`
- `orchestrator/contracts/output_contract.py`
- `orchestrator/contracts/prompt_contract.py`
- `orchestrator/workflow/prompting.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/executor.py`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/library/scripts/compare_workflow_loc.py`
- `tests/test_loader_validation.py`
- `tests/test_output_contract.py`
- `tests/test_prompt_contract_injection.py`
- `tests/test_v214_runtime_semantics.py`
- `tests/test_v214_primitive_oracle.py`
- `tests/test_neurips_v214_equivalence_oracle.py`
- `tests/test_workflow_loc_comparison.py`
- `specs/dsl.md`
- `specs/acceptance/index.md`

**Preferred packaging targets**

- `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- `workflows/README.md`

**Mandatory contract outputs from implementation**

- Loader/runtime support for `variant_output.shared_fields`.
- Loader/runtime support for `materialize_artifacts.input_values`.
- A rewritten `neurips_selected_backlog_item.v214.yaml` that validates `selected-item-inputs.json` directly and no longer writes `selected-item-inputs-fields/`.
- Deterministic LOC comparison script and regression test.
- Updated specs and workflow docs for the compact v2.14 authoring pattern.

**Preferred packaging outcomes**

- Uniform workflow-input pointer materialization in the three v2.14 child workflows uses `input_values` wherever the contract is unchanged.
- Existing fixed-shape JSON surfaces keep `output_bundle` rather than being rewritten into variant-only forms.

## Execution Tranches

### Tranche 1: Add The Ergonomics Contract Surfaces

**Files**

- `orchestrator/loader.py`
- `orchestrator/contracts/output_contract.py`
- `tests/test_loader_validation.py`
- `tests/test_output_contract.py`

- [ ] Implement loader support for `variant_output.shared_fields`, with omitted `shared_fields` normalized to an empty list.
- [ ] Reject duplicate field names and conflicting JSON pointers across discriminant, shared fields, and variant-specific fields.
- [ ] Implement loader support for `materialize_artifacts.input_values`, including `names`, `contract: inherit`, and `pointer_template`.
- [ ] Reject invalid `input_values` usage: unknown workflow inputs, duplicate expanded materialized names, missing `{name}` placeholder, or pointer templates that violate existing relpath/path-safety rules.
- [ ] Keep shorthand expansion semantically identical to long-form `values`; no new relaxed contract behavior is allowed.
- [ ] Add loader and output-contract tests for acceptance, duplicate rejection, missing shared fields, and shorthand expansion behavior.

**Verification**

- Blocking: `pytest tests/test_loader_validation.py -k 'variant_output or materialize' -q`
- Blocking: `pytest tests/test_output_contract.py -k 'variant' -q`
- Blocking when tests are added or renamed in this tranche: `pytest tests/test_loader_validation.py tests/test_output_contract.py --collect-only -q`
- Supporting: use narrower selectors during diagnosis if one of the blocking commands fails, but rerun the blocking commands before moving to Tranche 2.

### Tranche 2: Wire Prompt Rendering And Runtime Behavior

**Files**

- `orchestrator/contracts/prompt_contract.py`
- `orchestrator/workflow/prompting.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/executor.py`
- `tests/test_prompt_contract_injection.py`
- `tests/test_v214_runtime_semantics.py`

- [ ] Render `variant_output.shared_fields` exactly once in provider/adjudicated-provider prompt-contract blocks.
- [ ] Preserve existing command-step behavior: command execution should validate `variant_output` without relying on prompt injection.
- [ ] Expand `input_values` into the same internal materialization representation used by long-form `values`.
- [ ] Ensure runtime artifact exposure treats discriminant and shared fields as always available after bundle validation, while variant-only fields still require the existing proof mechanisms.
- [ ] Preserve path-safety, contract inheritance, and pointer-authority behavior from the released Phase 1 semantics.
- [ ] Add runtime tests proving shorthand materialization matches long-form pointer contents and artifact values.

**Verification**

- Blocking: `pytest tests/test_prompt_contract_injection.py -k 'variant_output' -q`
- Supporting: run narrower selectors in `tests/test_v214_runtime_semantics.py` while iterating on failures.
- Blocking before moving to Tranche 3: `pytest tests/test_v214_runtime_semantics.py -q`
- Blocking when tests are added or renamed in this tranche: `pytest tests/test_prompt_contract_injection.py tests/test_v214_runtime_semantics.py --collect-only -q`

### Tranche 3: Rewrite The V2.14 Workflow Stack For Compact Authoring

**Files**

- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- `tests/test_neurips_v214_equivalence_oracle.py`
- `tests/test_v214_primitive_oracle.py`

- [ ] Replace the inline Python field-splitting logic in `ResolveSelectedItemInputs` with the existing script that writes `selected-item-inputs.json`, and validate that JSON directly with `variant_output`.
- [ ] Move always-present selected-item fields into `variant_output.shared_fields`; keep only truly variant-specific paths variant-gated.
- [ ] Remove the `selected-item-inputs-fields/` fanout and any `expected_outputs` entries that existed only to support that fanout.
- [ ] Remove the separate `selection-mode-authority.json` step unless a remaining consumer still needs a distinct variant proof surface; if it stays, justify it in the implementation report.
- [ ] Convert follow-on pointer materialization in the selected-item workflow to consume validated artifacts rather than field-split text files.
- [ ] Apply `materialize_artifacts.input_values` in the three child v2.14 workflows wherever repeated workflow-input materialization is uniform; keep long-form `values` only where contracts differ or the source is not a workflow input.
- [ ] Preserve same-version v2.14 calls only and keep `output_bundle` on fixed-shape JSON outputs.
- [ ] Ensure the rewrite does not create literal `${inputs.*}` directories or files.

**Verification**

- Supporting during editing: run the most relevant oracle scenario selectors first.
- Blocking before moving to Tranche 4: `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- Blocking if tests are added or renamed in this tranche: `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py --collect-only -q`

### Tranche 4: Add LOC Evidence And Update Durable Documentation

**Files**

- `workflows/library/scripts/compare_workflow_loc.py`
- `tests/test_workflow_loc_comparison.py`
- `specs/dsl.md`
- `specs/acceptance/index.md`
- `workflows/README.md`

- [ ] Implement `compare_workflow_loc.py` so it compares one or more old files against one or more new files and reports old LOC, new LOC, absolute delta, and percent delta.
- [ ] Keep the script deterministic and repo-local; it is evidence for this backlog item, not a general lint framework.
- [ ] Add regression tests for passing reduction, failing growth/regression, and grouped file comparison.
- [ ] Update `specs/dsl.md` to document `variant_output.shared_fields` and `materialize_artifacts.input_values`.
- [ ] Update `specs/acceptance/index.md` so acceptance coverage includes shared-field validation, shorthand expansion equivalence, and the Phase 2 LOC reduction evidence requirement.
- [ ] Update `workflows/README.md` to document the compact v2.14 authoring pattern: keep native JSON bundles, use `output_bundle` for fixed-shape outputs, and use `variant_output` only when discriminant-driven field availability matters.
- [ ] `docs/index.md` does not need an update unless implementation adds a new durable documentation page. No new page is planned here.

**Verification**

- Blocking: `pytest tests/test_workflow_loc_comparison.py -q`
- Blocking: `python workflows/library/scripts/compare_workflow_loc.py --old workflows/library/neurips_backlog_implementation_phase.yaml --old workflows/library/neurips_backlog_seeded_plan_phase.yaml --old workflows/library/neurips_backlog_roadmap_sync_phase.yaml --old workflows/library/neurips_selected_backlog_item.yaml --new workflows/library/neurips_backlog_implementation_phase.v214.yaml --new workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml --new workflows/library/neurips_backlog_roadmap_sync.v214.yaml --new workflows/library/neurips_selected_backlog_item.v214.yaml --require-total-reduction-pct 1`
- Blocking when tests are added or renamed in this tranche: `pytest tests/test_workflow_loc_comparison.py --collect-only -q`

## Final Deterministic Verification Gate

Before declaring the backlog item complete, rerun all required deterministic checks below exactly as written. These are all blocking:

- `pytest tests/test_loader_validation.py -k 'variant_output or materialize' -q`
- `pytest tests/test_output_contract.py -k 'variant' -q`
- `pytest tests/test_prompt_contract_injection.py -k 'variant_output' -q`
- `pytest tests/test_v214_runtime_semantics.py -q`
- `pytest tests/test_workflow_loc_comparison.py -q`
- `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`
- `python workflows/library/scripts/compare_workflow_loc.py --old workflows/library/neurips_backlog_implementation_phase.yaml --old workflows/library/neurips_backlog_seeded_plan_phase.yaml --old workflows/library/neurips_backlog_roadmap_sync_phase.yaml --old workflows/library/neurips_selected_backlog_item.yaml --new workflows/library/neurips_backlog_implementation_phase.v214.yaml --new workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml --new workflows/library/neurips_backlog_roadmap_sync.v214.yaml --new workflows/library/neurips_selected_backlog_item.v214.yaml --require-total-reduction-pct 1`
- `python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json`

## Evidence And Reporting Requirements

- The implementation report must record old LOC, new LOC, absolute delta, and percent delta from the LOC comparison script.
- The implementation report must state whether `selection-mode-authority.json` was removed; if retained, it must justify the retained contract value.
- The final evidence must explicitly confirm that `selected-item-inputs.json` is no longer split into per-field text files and that no literal `${inputs.*}` paths were created.
- Long-running commands, especially the final dry-run, remain under implementation ownership until terminal success or documented recoverable failure handling is complete.
