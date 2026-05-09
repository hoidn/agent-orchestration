# DSL v2.14 Phase 0 Oracle Execution Plan

> For implementation: keep ordinary long-running commands under implementation ownership until terminal success or documented recoverable failure handling is complete.

**Goal:** Freeze current behavior for the future v2.14 materialization, snapshot, and variant-output semantics with deterministic primitive and minimal-NeurIPS oracles, while normal loader and CLI paths continue to reject public `version: "2.14"` workflows.

**Architecture:** This item is a Phase 0 characterization tranche, not a runtime-feature tranche. The work should add draft design docs, two small fixture workspaces, one fake provider, a shared golden-observation normalizer, and dedicated regression tests that capture current behavior without enabling public v2.14 support or translating the NeurIPS stack.

**Tech Stack:** Python, pytest, YAML workflows on currently supported DSL versions, repo-local fixtures, fake-provider command steps, `python -m orchestrator` dry-run validation.

---

## Selected Item Objective

- Implement the Phase 0 behavior oracle for DSL v2.14 materialization, snapshot, and variant-output semantics before changing public DSL behavior.

## Scope

- Add draft, non-normative design documentation and a behavior matrix for Phase 0 runtime consumers.
- Add primitive fixtures that emulate future `materialize_artifacts`, `pre_snapshot`, `variant_output`, and `select_variant_output` behavior using only currently supported DSL surfaces.
- Add a minimal NeurIPS-style fixture workspace that captures steering, design, roadmap, backlog, queue, progress-ledger, and run-state shapes without copying a full downstream project.
- Add a fake provider that deterministically produces completed, blocked, ambiguous, missing-output, review-approve, and review-revise scenarios.
- Add a golden observation normalizer and dedicated regression tests that freeze current behavior before v2.14 semantics are implemented.

## Explicit Non-Goals

- Do not enable `version: "2.14"` in the normal loader or CLI.
- Do not add public `workflows/library/*.v214.yaml` or runnable public `version: "2.14"` examples.
- Do not implement Phase 1 runtime surfaces, Phase 2 NeurIPS-stack translation, mixed-version calls, recovery/resource-transition/phase-outcome/review-loop macros, or spec updates that advertise public v2.14 support.
- Do not broaden this item into roadmap work beyond the current `phase-0-dsl-v214-oracle` gate.

## Constraints And Prerequisite Status

- `docs/steering.md` and the roadmap bind this item to Phase 0 only. Public v2.14 support remains capped at the existing supported versions, tests must stay network-free by default, fake providers should be used for workflow behavior checks, and path-safety/version-gating/output-contract semantics must remain unchanged.
- `state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json` currently records no completed items and no completed tranches. That means this item is not waiting on upstream tranche completion, but it also must not claim Phase 1 or Phase 2 readiness and must not treat planning alone as roadmap completion evidence.
- The design authority is `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`, especially its Phase 0 deliverables and acceptance criteria.
- If a normal verification issue occurs during implementation, diagnose, narrow-fix, and rerun before considering `BLOCKED`. Reserve `BLOCKED` for missing resources, unavailable hardware, roadmap conflict, external dependency outside current authority, user decision required, or a failure that stays unrecoverable after a documented narrow fix attempt.

## Implementation Architecture

- `docs/design/*`: Phase 0-only draft references that inventory brittle current patterns and define the oracle behavior matrix without changing normative specs.
- `tests/fixtures/v214_primitives/*` plus `tests/fixtures/bin/fake_provider.py`: the primitive oracle harness that emulates future materialization and variant behavior using current DSL surfaces.
- `tests/fixtures/neurips_minimal/*`: the minimal NeurIPS oracle harness that mirrors queue, roadmap, plan, run-state, and artifact-path shapes closely enough to freeze current behavior.
- `tests/golden_state.py` plus the dedicated oracle test modules: one shared normalization layer and two separate regression suites so primitive semantics and NeurIPS workflow behavior can evolve independently later.

## File And Artifact Targets

Mandatory contract outputs:

- `docs/design/dsl_v214_materialization_variants_draft.md`
- `docs/design/neurips_v214_behavior_matrix.md`
- `tests/golden_state.py`
- `tests/fixtures/bin/fake_provider.py`
- `tests/fixtures/v214_primitives/` with current-version fixture workflows and expected observation assets
- `tests/fixtures/neurips_minimal/` with minimal docs, backlog, artifact, and state shapes; use `state/progress_ledger.json`, not a markdown placeholder
- `tests/test_v214_primitive_oracle.py`
- `tests/test_neurips_v214_equivalence_oracle.py`
- A public-version rejection proof, preferably by extending `tests/test_loader_validation.py`

Preferred packaging and reuse:

- Reuse patterns from `tests/fixtures/neurips_steered_backlog/`, `tests/test_neurips_steered_backlog_runtime.py`, and `tests/test_neurips_selected_item_materialize.py` rather than inventing a second full-stack fixture layout.
- Keep shared golden-observation normalization in `tests/golden_state.py` instead of duplicating normalization logic across both oracle test modules.
- Treat `workflows/examples/neurips_steered_backlog_drain.yaml`, `workflows/library/neurips_selected_backlog_item.yaml`, and `workflows/library/scripts/materialize_neurips_selected_item_inputs.py` as verification inputs, not primary edit targets; only touch them if a fixture or test-harness gap cannot be solved inside test-only surfaces.
- If the new `docs/design/` pages are added, update `docs/index.md` so the durable draft references are discoverable.

## Execution Checklist

### Task 1: Draft Phase 0 Reference Docs

- [ ] Create `docs/design/dsl_v214_materialization_variants_draft.md` as a non-normative Phase 0 reference that records the current brittle-pattern inventory and maps current workflow patterns to future v2.14 handling (`materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, and explicit deferrals).
- [ ] Create `docs/design/neurips_v214_behavior_matrix.md` with the primitive and minimal-NeurIPS scenarios, expected outcomes, preserved observations, and normalized-away volatile fields.
- [ ] Update `docs/index.md` to register the new draft docs because they become durable project knowledge for this tranche.

Verification:

- Supporting: review the new docs for strict Phase 0 boundaries and confirm they do not advertise public `2.14` support or normative spec changes.

### Task 2: Build The Primitive Oracle Harness

- [ ] Create `tests/fixtures/v214_primitives/` with current-version workflows only. The fixtures must emulate valid materialization, missing required targets, stricter-versus-weaker contract refinement, single-changed-candidate selection, no-change failure, multi-change failure, invalid-bundle no-commit behavior, completed and blocked tagged-union exposure, and variant-proof acceptance/rejection cases.
- [ ] Create `tests/fixtures/bin/fake_provider.py` with deterministic scenario modes `completed`, `blocked`, `both_reports`, `neither_report`, `review_approve`, and `review_revise`.
- [ ] Create `tests/golden_state.py` to normalize run IDs, absolute temp paths, timestamps, durations, log paths, and incidental ordering while preserving workflow outputs, artifact values, selected variants, file hashes, queue state, snapshot candidate keys, domain-state summaries, failure classes, and contract-violation surfaces.
- [ ] Add `tests/test_v214_primitive_oracle.py` that executes the primitive fixtures and asserts normalized golden observations rather than provider prose.

Verification:

- Blocking: `pytest --collect-only tests/test_v214_primitive_oracle.py`
- Blocking: `pytest tests/test_v214_primitive_oracle.py -q`

### Task 3: Build The Minimal NeurIPS Oracle Harness

- [ ] Create `tests/fixtures/neurips_minimal/` with minimal `docs/`, `artifacts/`, and `state/` trees that preserve steering, design, roadmap, backlog, queue, `progress_ledger.json`, and `run_state.json` shapes without copying a full external project.
- [ ] Reuse the existing NeurIPS selected-item and steered-drain patterns to model plan-context materialization, recovered-versus-fresh plan-gate behavior, implementation completed/blocked outcomes, ambiguous report failures, missing-output failures, and final queue/run-state transitions.
- [ ] Add `tests/test_neurips_v214_equivalence_oracle.py` that drives the minimal fixture workspace with the fake provider and asserts normalized golden observations for the completed, blocked, ambiguous, missing-output, recovered-plan, fresh-plan, and selected-item outcome scenarios named in the backlog/design authority.

Verification:

- Blocking: `pytest --collect-only tests/test_neurips_v214_equivalence_oracle.py`
- Blocking: `pytest tests/test_neurips_v214_equivalence_oracle.py -q`
- Supporting: if implementation touches `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`, rerun `pytest tests/test_neurips_selected_item_materialize.py -q`
- Supporting: if implementation touches `workflows/examples/neurips_steered_backlog_drain.yaml` or `workflows/library/neurips_selected_backlog_item.yaml`, rerun the narrowest affected selector in `tests/test_neurips_steered_backlog_runtime.py` before the final smoke

### Task 4: Preserve The Public Version Gate

- [ ] Add the required proof that normal loader paths still reject public `version: "2.14"` workflows. Prefer extending `tests/test_loader_validation.py` with `test_version_2_14_is_rejected` rather than creating a one-off module.
- [ ] Keep `orchestrator/loader.py`, `specs/dsl.md`, and public workflow/version advertising unchanged unless a failing rejection test proves the current unsupported-version guard itself is broken.
- [ ] Ensure both oracle suites consume the shared `tests/golden_state.py` normalization schema so Phase 0 evidence stays consistent across primitive and NeurIPS scenarios.

Verification:

- Blocking: `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`
- Supporting: `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`

### Task 5: Run Required Deterministic Checks And Final Smoke

- [ ] After the oracle suites are green, run the backlog item’s required deterministic checks exactly as selected-item authority recorded them.
- [ ] Treat the final `python -m orchestrator run ... --dry-run` command as a blocking smoke check because workflow-related surfaces are in scope for this tranche.

Verification:

- Blocking:

```bash
python -m json.tool docs/backlog/roadmap_gate.json
python workflows/library/scripts/build_neurips_backlog_manifest.py --backlog-root docs/backlog/active --output state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json
python workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py --manifest-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_manifest_check.json --gate-policy-path docs/backlog/roadmap_gate.json --progress-ledger-path state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --run-state-path state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --output state/DSL-V214-MATERIALIZATION-VARIANTS/roadmap_gate_check.json
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
```

## Completion Criteria

- Primitive and minimal-NeurIPS oracle tests pass without network access or real provider calls.
- Public `version: "2.14"` remains rejected on normal loader paths.
- Golden observations normalize volatile fields while preserving final outputs, artifact values, selected variants, file hashes, queue state, domain-state summaries, and failure classes.
- The required deterministic checks and dry-run smoke pass.
- No Phase 1 or Phase 2 scope is implemented or implied.
