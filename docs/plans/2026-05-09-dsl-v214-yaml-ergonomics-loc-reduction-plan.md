# DSL v2.14 YAML Ergonomics LOC Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the v2.14 NeurIPS workflow stack smaller than the legacy stack by validating native JSON bundles directly, adding shared variant fields, adding batch input materialization, and enforcing LOC regression checks.

**Architecture:** Keep the released v2.14 semantic model, but add two narrow ergonomics features: `variant_output.shared_fields` and `materialize_artifacts.input_values`. Then rewrite the v2.14 selected-item workflow to remove per-field text-file splitting and prove old-stack/v2.14 behavioral equivalence plus YAML LOC reduction.

**Tech Stack:** Python loader/runtime, YAML workflows, pytest, existing output-contract and prompt-contract modules, NeurIPS oracle fixtures, and repo-local workflow scripts.

---

## Context

The first v2.14 stack translation completed but grew YAML from 2331 lines to
2646 lines. The selected-item workflow caused most of the regression by turning
one JSON bundle into many text files plus many `expected_outputs`. This plan
corrects that authoring pattern without weakening runtime validation.

Design authority: `docs/design/dsl_v214_yaml_ergonomics.md`.

## Files

Modify:

- `orchestrator/loader.py`
- `orchestrator/contracts/output_contract.py`
- `orchestrator/contracts/prompt_contract.py`
- `orchestrator/workflow/prompting.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/executor.py`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- `tests/test_loader_validation.py`
- `tests/test_output_contract.py`
- `tests/test_prompt_contract_injection.py`
- `tests/test_v214_runtime_semantics.py`
- `tests/test_neurips_v214_equivalence_oracle.py`
- `tests/golden_state.py`
- `specs/dsl.md`
- `specs/acceptance/index.md`
- `workflows/README.md`

Create:

- `workflows/library/scripts/compare_workflow_loc.py`
- `tests/test_workflow_loc_comparison.py`

## Task 1: Add `variant_output.shared_fields` Loader And Contract Tests

**Files:**

- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/contracts/output_contract.py`
- Test: `tests/test_loader_validation.py`
- Test: `tests/test_output_contract.py`

- [ ] Write a loader test that accepts `variant_output.shared_fields` on a
  `version: "2.14"` workflow and exposes shared fields as always-available
  artifacts.

- [ ] Write a loader test that rejects duplicate field names across
  `shared_fields`, discriminant, and variant-specific fields.

- [ ] Write an output-contract test where a bundle validates shared fields plus
  the selected variant fields.

- [ ] Write an output-contract test where a missing shared field fails even
  though the variant-specific fields are valid.

- [ ] Implement parser normalization so omitted `shared_fields` behaves like an
  empty list.

- [ ] Implement duplicate-name and duplicate-json-pointer validation.

- [ ] Implement runtime validation so shared fields are required and exposed for
  every selected variant.

- [ ] Run:

```bash
pytest tests/test_loader_validation.py -k 'variant_output and shared' -q
pytest tests/test_output_contract.py -k 'variant and shared' -q
```

## Task 2: Add Shared-Field Prompt Injection

**Files:**

- Modify: `orchestrator/contracts/prompt_contract.py`
- Modify: `orchestrator/workflow/prompting.py`
- Test: `tests/test_prompt_contract_injection.py`

- [ ] Write a provider prompt test showing shared fields appear once in the
  injected variant contract block.

- [ ] Write a regression test showing command steps still validate
  `variant_output` without prompt injection.

- [ ] Update prompt-contract rendering to include a "Shared fields" block only
  when `shared_fields` is non-empty.

- [ ] Run:

```bash
pytest tests/test_prompt_contract_injection.py -k 'variant_output' -q
```

## Task 3: Add `materialize_artifacts.input_values`

**Files:**

- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_loader_validation.py`
- Test: `tests/test_v214_runtime_semantics.py`

- [ ] Write a loader test where `input_values.names` expands four workflow
  inputs with inherited contracts and a pointer template.

- [ ] Write a loader test rejecting `input_values` when a named workflow input
  does not exist.

- [ ] Write a loader test rejecting a `pointer_template` that escapes the
  workspace or omits `{name}`.

- [ ] Write a runtime test proving `input_values` writes the same artifact
  values and pointer contents as equivalent long-form `values`.

- [ ] Implement a normalization pass that expands `input_values` to the same
  internal representation used by long-form `values`.

- [ ] Keep long-form `values` and `input_values` composable in the same
  `materialize_artifacts` block, while rejecting duplicate materialized names.

- [ ] Run:

```bash
pytest tests/test_loader_validation.py -k 'materialize and input_values' -q
pytest tests/test_v214_runtime_semantics.py -k 'materialize' -q
```

## Task 4: Rewrite Selected-Item v2.14 Without Field Splitting

**Files:**

- Modify: `workflows/library/neurips_selected_backlog_item.v214.yaml`
- Modify: `tests/test_neurips_v214_equivalence_oracle.py`
- Modify: `tests/golden_state.py` only if the wrapper copy list or normalized
  observation needs a narrow update.

- [ ] Replace the current `ResolveSelectedItemInputs` inline Python field
  splitter with the existing
  `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`
  command.

- [ ] Validate `${inputs.state_root}/selected-item-inputs.json` directly with
  `variant_output`.

- [ ] Use `shared_fields` for common selected-item fields such as
  `selected_item_context_path`, `check_commands_path`, phase state roots, target
  paths, and report target paths.

- [ ] Keep only `selected_item_active_path` and
  `selected_item_in_progress_path` as variant-specific fields.

- [ ] Remove the `selected-item-inputs-fields/` expected-output fanout.

- [ ] Remove the separate `selection-mode-authority.json` step unless a
  remaining consumer truly needs a second bundle.

- [ ] Run:

```bash
pytest tests/test_neurips_v214_equivalence_oracle.py -q -k selected_item_runtime
```

## Task 5: Apply Batch Materialization To v2.14 Subworkflows

**Files:**

- Modify: `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- Modify: `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
- Modify: `workflows/library/neurips_backlog_implementation_phase.v214.yaml`

- [ ] Replace repeated uniform input materialization entries with
  `materialize_artifacts.input_values`.

- [ ] Keep long-form `values` only for non-uniform targets, stricter
  refinements, or values that are not workflow inputs.

- [ ] Run:

```bash
pytest tests/test_neurips_v214_equivalence_oracle.py -q -k 'fresh_plan or recovered_plan or completed or blocked'
```

## Task 6: Add LOC Regression Check

**Files:**

- Create: `workflows/library/scripts/compare_workflow_loc.py`
- Create: `tests/test_workflow_loc_comparison.py`
- Modify: `docs/backlog/active/2026-05-09-dsl-v214-yaml-ergonomics-loc-reduction.md`

- [ ] Write tests for a small LOC comparison fixture:
  - passes when the new file is shorter by the required percentage;
  - fails when the new file grows;
  - supports comparing file groups.

- [ ] Implement `compare_workflow_loc.py` with arguments:

```text
--old <path> [--old <path> ...]
--new <path> [--new <path> ...]
--require-total-reduction-pct <float>
--require-new-max-lines <int> optional
```

- [ ] Add the LOC checker to the backlog item `check_commands`.

- [ ] Run:

```bash
pytest tests/test_workflow_loc_comparison.py -q
python workflows/library/scripts/compare_workflow_loc.py \
  --old workflows/library/neurips_backlog_implementation_phase.yaml \
  --old workflows/library/neurips_backlog_seeded_plan_phase.yaml \
  --old workflows/library/neurips_backlog_roadmap_sync_phase.yaml \
  --old workflows/library/neurips_selected_backlog_item.yaml \
  --new workflows/library/neurips_backlog_implementation_phase.v214.yaml \
  --new workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml \
  --new workflows/library/neurips_backlog_roadmap_sync.v214.yaml \
  --new workflows/library/neurips_selected_backlog_item.v214.yaml \
  --require-total-reduction-pct 1
```

## Task 7: Update Specs And Docs

**Files:**

- Modify: `specs/dsl.md`
- Modify: `specs/acceptance/index.md`
- Modify: `workflows/README.md`

- [ ] Document `variant_output.shared_fields`.

- [ ] Document `materialize_artifacts.input_values`.

- [ ] Document the rule that v2.14 migrations should keep JSON bundles native
  and use `output_bundle` for fixed-shape bundles.

- [ ] Add acceptance bullets for shared fields, batch materialization, and LOC
  regression evidence for the NeurIPS v2.14 stack.

## Task 8: Full Verification

- [ ] Run the full targeted verification:

```bash
pytest tests/test_loader_validation.py -k 'variant_output or materialize' -q
pytest tests/test_output_contract.py -k 'variant' -q
pytest tests/test_prompt_contract_injection.py -k 'variant_output' -q
pytest tests/test_v214_runtime_semantics.py -q
pytest tests/test_workflow_loc_comparison.py -q
pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md \
  --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md \
  --input backlog_root=docs/backlog/active \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json \
  --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain \
  --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
```

- [ ] Record the final old-stack LOC, v2.14-stack LOC, absolute delta, and
  percent delta in the execution report.

- [ ] Confirm no literal `${inputs.*}` directories were created.

## Expected Outcome

- The v2.14 production stack is shorter than the legacy stack.
- The selected-item v2.14 workflow no longer contains per-field text fanout for
  `selected-item-inputs.json`.
- Equivalence tests still pass.
- The DSL has compact authoring surfaces for the patterns that caused the first
  v2.14 translation to grow.
