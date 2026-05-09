# DSL v2.14 Runtime Semantics Execution Plan

> For implementation: keep ordinary long-running commands under implementation ownership until terminal success or documented recoverable failure handling is complete.

**Goal:** Implement the narrow Phase 1 DSL v2.14 runtime semantics tranche for materialization, snapshot evidence, variant outputs, and variant-proof enforcement without exposing public `version: "2.14"` workflows.

**Architecture:** This tranche is a private runtime-internals pass across loader, reference analysis, contract validation, IR lowering, runtime execution, state persistence, pointer/dataflow enforcement, and observability. The work must reuse the Phase 0 oracle as the regression net, keep public version support capped at `2.13`, and defer any public workflow translation, normative spec advertisement, or release-surface updates to the later v2.14 release tranche.

**Tech Stack:** Python, pytest, repo-local YAML workflows, existing orchestrator loader/runtime modules, state sidecars under `.orchestrate/runs/`, fake-provider oracle fixtures, `python -m orchestrator` dry-run validation.

---

## Selected Item Objective

- Implement the selected backlog item `2026-05-09-dsl-v214-runtime-semantics` as the Phase 1 runtime-semantics tranche authorized by the roadmap gate.

## Scope

- Add the loader, IR, runtime, contract, reference, snapshot, variant, pointer, observability, and error-taxonomy behavior needed for:
  - `materialize_artifacts`
  - `pre_snapshot`
  - `variant_output`
  - `select_variant_output`
  - `requires_variant`
  - match-based variant proof
- Preserve Phase 0 oracle coverage and update oracle expectations only when the semantic delta is deliberate and documented.
- Keep public exposure gated until the later release tranche lands loader, runtime, docs, and tests together.
- Preserve same-version call restrictions, path-safety rules, output-contract enforcement, and network-free test policy.

## Explicit Non-Goals

- Do not create `workflows/library/*.v214.yaml` as public runnable workflows.
- Do not migrate the NeurIPS workflow stack or touch Phase 2 translation scope except where existing current-version verification inputs need compatibility fixes.
- Do not implement deferred primitives:
  - `recover_or_run`
  - `resource_transition`
  - `phase_outcome`
  - `review_loop`
- Do not add mixed-version calls, mtime-only freshness, large-file hash caching, a general expression language, or general `if`/`when` variant proof.
- Do not update `specs/dsl.md` or `specs/acceptance/` to advertise public v2.14 support in this tranche.

## Constraints And Prerequisite Status

- `docs/steering.md` and `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md` bind this work to `phase-1-dsl-v214-runtime`. Phase 2 remains blocked, and public `version: "2.14"` support must stay unavailable on normal loader and CLI paths.
- `docs/backlog/roadmap_gate.json` currently allows the Phase 1 runtime prefix and blocks the Phase 2 translation prefix. Treat that as the execution-scope boundary.
- `state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json` still records no completed items and no completed tranches. That does not invalidate the selected-item authority for planning, but implementation must not mutate the ledger or claim roadmap completion from planning alone. If execution uncovers a real prerequisite/governance mismatch that cannot be resolved inside this tranche, stop and surface the mismatch rather than broadening scope.
- The design authority is `docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md`. Preserve its rules for content-based snapshot diffs, atomic bundle commit, canonical relpath pointer authority, contract inheritance/refinement, and exact error taxonomy.
- Keep tests network-free and prefer fake providers or current-version fixture workflows for behavior checks.
- Do not mark the item `BLOCKED` for ordinary test failures, import/path mistakes, or harness issues. Diagnose, narrow-fix, and rerun first. Reserve `BLOCKED` for missing resources, unavailable hardware, roadmap conflict, external dependency outside current authority, required user decision, or a failure that remains unrecoverable after a documented narrow fix attempt.

## Implementation Architecture

- **Loader and typed surfaces:** extend authored-step parsing, version gating, structured signatures, and typed runtime metadata while keeping public `2.14` execution disabled.
- **Reference and proof model:** add snapshot-reference taxonomy, artifact availability metadata, and proof-context propagation so variant-only refs are statically checked and runtime-guarded.
- **Prompt delivery and contract composition:** keep variant-contract formatting in the contract layer, but route the actual provider and adjudicated-provider prompt injection through `orchestrator/workflow/prompting.py` so authored-step prompt assembly owns the runtime integration point.
- **Runtime execution and persistence:** add deterministic materialization, pre-step snapshot capture, variant-bundle validation/selection, state projection, sidecar integrity checks, and atomic commit behavior.
- **Security and path safety:** reuse the existing orchestrator-managed path-safety model for materialized relpaths and snapshot candidates, including absolute-path rejection, parent-escape rejection, symlink-escape rejection, directory rejection where file evidence is required, and bounded hashing for snapshot inputs.
- **Regression and compatibility net:** reuse the existing Phase 0 oracle plus narrow loader/contract/runtime tests so semantic changes are proven without translating the NeurIPS workflow stack.

## File And Artifact Targets

Mandatory contract outputs:

- Loader, signatures, and typed workflow metadata:
  - `orchestrator/loader.py`
  - `orchestrator/workflow/signatures.py`
  - `orchestrator/workflow/runtime_types.py`
- Reference analysis, proof propagation, and pointer/dataflow enforcement:
  - `orchestrator/workflow/references.py`
  - `orchestrator/workflow/elaboration.py`
  - `orchestrator/workflow/conditions.py`
  - `orchestrator/workflow/predicates.py`
  - `orchestrator/workflow/dataflow.py`
  - `orchestrator/workflow/pointers.py`
- Contract validation and prompt injection:
  - `orchestrator/contracts/output_contract.py`
  - `orchestrator/contracts/prompt_contract.py`
  - `orchestrator/workflow/prompting.py`
- Security and path-safety enforcement:
  - `orchestrator/security/*`
  - `orchestrator/workflow/pointers.py`
- IR lowering and runtime execution:
  - `orchestrator/workflow/executable_ir.py`
  - `orchestrator/workflow/lowering.py`
  - `orchestrator/workflow/runtime_step.py`
  - `orchestrator/workflow/executor.py`
  - `orchestrator/exec/step_executor.py`
  - `orchestrator/workflow/runtime_context.py`
  - `orchestrator/state.py`
  - `orchestrator/runtime_observability.py`
  - `orchestrator/workflow/outcomes.py`
- Regression and compatibility tests:
  - `tests/test_loader_validation.py`
  - `tests/test_output_contract.py`
  - `tests/test_prompt_contract_injection.py`
  - `tests/test_workflow_output_contract_integration.py`
  - `tests/test_artifact_dataflow_integration.py`
  - `tests/test_observability_report.py`
  - `tests/test_v214_primitive_oracle.py`
  - `tests/test_neurips_v214_equivalence_oracle.py`
  - `tests/golden_state.py`

Preferred packaging:

- If the current files become too dense, add small private helper modules near the owning surface, for example a focused variant-contract helper under `orchestrator/contracts/` or a snapshot helper under `orchestrator/workflow/`. Keep any such helpers internal and avoid creating new public workflow/example surfaces.
- Keep prompt-contract formatting in the contract/prompt layer, and keep `orchestrator/workflow/prompting.py` as the only runtime integration surface that decides when provider and adjudicated-provider prompts actually receive the suffix.
- Treat `workflows/examples/neurips_steered_backlog_drain.yaml` and `workflows/library/neurips_selected_backlog_item.yaml` as verification inputs, not primary edit targets. Only touch them if a current-version compatibility issue is unavoidable, and do not translate them to public `v214` YAML.
- Do not edit `docs/index.md`, `specs/index.md`, or `specs/dsl.md` unless implementation adds a new internal-only durable doc that must be discoverable. If such a doc is added, register it in `docs/index.md` without advertising public v2.14 support.

## Execution Checklist

### Task 1: Lock Loader Gating, Step Shapes, And Error Taxonomy

- [ ] Extend the authored-step schema and typed runtime surfaces for `materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, and `requires_variant` in `orchestrator/loader.py`, `orchestrator/workflow/signatures.py`, and `orchestrator/workflow/runtime_types.py`.
- [ ] Preserve public version gating: normal loader and CLI paths must still reject `version: "2.14"` workflows even after the new internals land.
- [ ] Add loader-side validation for mutual exclusion rules, same-version call constraints, and unsupported proof forms so invalid authored shapes fail before runtime.
- [ ] Wire the explicit Phase 1 error taxonomy into validation paths instead of using generic failures where a design-approved code exists.
- [ ] Extend `tests/test_loader_validation.py` with narrow checks for the new authored fields, gating, mutual exclusion, unsupported proof, and exact failure classes.

Verification:

- Supporting: run the narrowest affected selectors in `tests/test_loader_validation.py` while iterating on new validation rules.
- Blocking: `pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q`

### Task 2: Implement Contract Inheritance, Variant Validation, And Prompt Injection

- [ ] Add the shared variant-contract model and contract-refinement enforcement in `orchestrator/contracts/output_contract.py`, including source-contract inheritance, allowed tightenings, rejected weakenings, relpath/pointer rules, and exact contract-refinement errors.
- [ ] Implement `variant_output` validation for provider, command, and adjudicated-provider success paths, with the rule that command steps validate bundles but do not receive prompt-contract injection.
- [ ] Update `orchestrator/contracts/prompt_contract.py` so provider and adjudicated-provider steps can append a deterministic variant-contract suffix when `variant_output` is declared.
- [ ] Update `orchestrator/workflow/prompting.py` so the authored-step prompt assembly path is the explicit integration point: provider and adjudicated-provider steps receive the contract-layer suffix there, while command steps bypass prompt injection entirely.
- [ ] Enforce `expected_outputs`, `output_bundle`, `variant_output`, and `select_variant_output` mutual exclusion from one authoritative validation layer.
- [ ] Add or extend unit and narrow integration coverage in `tests/test_output_contract.py`, `tests/test_prompt_contract_injection.py`, and adjacent prompt-assembly tests if needed for contract inheritance/refinement, invalid bundle classes, required versus forbidden variant fields, relpath target validation, and provider-only prompt injection behavior through the real prompting surface.

Verification:

- Supporting: `pytest tests/test_output_contract.py -q`
- Supporting: `pytest tests/test_prompt_contract_injection.py -q`
- Supporting: if prompt-assembly behavior requires a touched integration selector outside `tests/test_prompt_contract_injection.py`, run the narrowest affected selector before broader workflow checks.
- Supporting: if any new test module is introduced for variant helpers, run `pytest --collect-only <new_module> -q` before its first full execution.

### Task 3: Add Snapshot References, Variant Proof, Canonical Publishing, And Path Safety

- [ ] Extend `orchestrator/workflow/references.py`, `orchestrator/workflow/elaboration.py`, `orchestrator/workflow/conditions.py`, and `orchestrator/workflow/predicates.py` with explicit `ArtifactRef`, `SnapshotRef`, proof-context, and variant-availability handling.
- [ ] Restrict snapshot refs to the Phase 1 allowed surface: `select_variant_output.evidence.snapshot.ref`. They must not behave like publishable or prompt-injectable artifact refs.
- [ ] Implement match-based proof and `requires_variant` proof attachment, while rejecting general `if`/`when` proof and call-boundary proof propagation.
- [ ] Update `orchestrator/workflow/dataflow.py` and `orchestrator/workflow/pointers.py` so published relpath artifacts expose canonical values rather than pointer-file paths and reject noncanonical sidecar pointers for published relpath artifacts.
- [ ] Reuse `orchestrator/security/*` together with `orchestrator/workflow/pointers.py` so new materialization and snapshot-managed paths apply the existing orchestrator path-safety contract: reject absolute paths, `..` escapes, symlink escapes, directory candidates where file evidence is required, and oversized snapshot/hash candidates before commit or evidence capture.
- [ ] Add or extend integration coverage for proof failures, wrong-variant access, snapshot ref resolution, pointer-authority conflicts, canonical relpath publishing, and the new materialization/snapshot path-safety failures in `tests/test_artifact_dataflow_integration.py`, `tests/test_at61_at62_wait_for_path_safety.py`, and adjacent workflow/dataflow tests.

Verification:

- Supporting: run the narrowest affected selectors in `tests/test_artifact_dataflow_integration.py` for pointer/dataflow changes.
- Supporting: `pytest tests/test_at61_at62_wait_for_path_safety.py -q`
- Supporting: if proof validation is covered in another touched module, run the narrowest new selector there before broader integration checks.

### Task 4: Lower And Execute Materialization, Snapshot Capture, And Selector Commit

- [ ] Lower `materialize_artifacts` and `select_variant_output` into deterministic runtime steps in `orchestrator/workflow/executable_ir.py`, `orchestrator/workflow/lowering.py`, and `orchestrator/workflow/runtime_step.py`, preserving authored stable IDs.
- [ ] Implement runtime execution in `orchestrator/workflow/executor.py`, `orchestrator/exec/step_executor.py`, and `orchestrator/workflow/runtime_context.py` for:
  - materializing artifacts from input/ref/literal sources
  - capturing pre-step snapshots
  - validating `variant_output` after step success
  - computing snapshot diffs by existence and `sha256`
  - selecting exactly one changed candidate or failing with the designed ambiguity/no-change errors
  - atomically writing the canonical selected bundle before exposing artifacts or lineage
- [ ] Ensure the runtime path through materialization and snapshot capture emits the designed invalid-candidate failures when the security checks reject a path, directory, symlink escape, or oversized evidence target instead of silently skipping or downgrading those cases.
- [ ] Persist snapshot state and sidecars in `orchestrator/state.py` and `orchestrator/workflow/runtime_context.py`, including resume-time sidecar presence and hash checks.
- [ ] Update `orchestrator/runtime_observability.py` and `orchestrator/workflow/outcomes.py` so reports surface selected variants, snapshot evidence summaries, and atomic-commit or contract-refinement failures without dumping excessive raw hash data by default.
- [ ] Add or extend runtime/integration tests covering successful materialization, invalid literal/ref contracts, snapshot ambiguity and unchanged-candidate failures, atomic no-commit behavior on invalid bundles, variant-unavailable runtime guards, and observability/report projections.

Verification:

- Supporting: `pytest tests/test_workflow_output_contract_integration.py -q`
- Supporting: `pytest tests/test_observability_report.py -q`
- Supporting: if a new runtime-focused test module is created, run `pytest --collect-only <new_module> -q` before the module run.

### Task 5: Refresh Phase 0 Oracle Expectations Without Expanding Scope

- [ ] Update `tests/test_v214_primitive_oracle.py`, `tests/test_neurips_v214_equivalence_oracle.py`, and `tests/golden_state.py` so the oracle suites assert the deliberate Phase 1 semantic changes while still ignoring volatile run data.
- [ ] Keep fixture updates scoped to the documented semantic delta. Do not translate the NeurIPS workflow stack to public `v214` YAML and do not weaken oracle checks to hide regressions.
- [ ] If a compatibility fix to current-version verification workflows is unavoidable, document the reason in the implementation notes and keep the fix limited to current supported DSL surfaces.
- [ ] If durable internal behavior knowledge requires a new private doc, add it under `docs/` and register it in `docs/index.md`; otherwise leave normative docs and indexes unchanged for this tranche.

Verification:

- Supporting: if tests are added or renamed, run `pytest --collect-only` on each affected test module.
- Blocking: `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`

### Task 6: Run The Required Deterministic Check Set And Final Dry-Run Smoke

- [ ] Run the backlog item’s required deterministic checks exactly as recorded in the selected-item context after the narrower tranche checks are green.
- [ ] Treat the final backlog-drain dry run as blocking because workflow-related surfaces are in scope and it is the required compatibility proof that the local steered backlog example still validates deterministically.
- [ ] Record what changed and how it was verified, including any deliberate oracle expectation updates and any narrow compatibility fixes to current-version verification inputs.

Verification:

- Blocking:

```bash
pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q
pytest tests/test_loader_validation.py::TestLoaderValidation::test_version_2_14_is_rejected -q
python -m json.tool docs/backlog/roadmap_gate.json
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run --input steering_path=docs/steering.md --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md --input roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md --input backlog_root=docs/backlog/active --input roadmap_gate_path=docs/backlog/roadmap_gate.json --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json --input drain_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain --input run_state_target_path=state/DSL-V214-MATERIALIZATION-VARIANTS/backlog_drain/run_state.json --input drain_summary_target_path=artifacts/work/DSL-V214-MATERIALIZATION-VARIANTS/backlog-drain-summary.json
```

## Completion Criteria

- The Phase 1 runtime semantics exist across loader, typed metadata, reference analysis, proof enforcement, contract validation, runtime execution, state persistence, pointer authority, and observability.
- Public `version: "2.14"` remains rejected on normal loader and CLI paths.
- Snapshot selection uses content-based evidence, not mtime-only freshness.
- Canonical bundle commit is atomic and does not expose artifacts or lineage on invalid candidates.
- Variant-only refs require proof statically and are still guarded at runtime.
- The Phase 0 oracle suites, loader rejection proof, roadmap-gate JSON validation, and steered backlog dry-run all pass.
- No Phase 2 translation work, public v2.14 release work, or deferred primitives are implemented or implied.
