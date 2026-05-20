# DSL v2.14 NeurIPS Stack Translation Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> For implementation: keep ordinary long-running commands under implementation ownership until terminal success or documented recoverable failure handling is complete.

**Goal:** Translate the selected NeurIPS backlog subworkflow stack to public same-version `2.14` YAML, replace only the pointer/snapshot/tagged-union glue that Phase 1 made first-class, and prove old-stack versus v2.14 behavioral equivalence on the required primitive and minimal NeurIPS scenarios.

**Architecture:** Implement this as a side-by-side Phase 2 stack, not a mutation or deletion of the current `2.7` workflows. The implementation phase is the substantive semantic migration; the plan, roadmap-sync, and selected-item phases stay conservative and only adopt released v2.14 primitives where they replace existing boilerplate. Verification must prove same-version imports, preserved observable behavior, and at least one public CLI smoke path under normal `version: "2.14"` loader support.

**Tech Stack:** Repo-local YAML workflows under `workflows/library/`, existing prompt assets under `workflows/library/prompts/`, existing domain helper scripts under `workflows/library/scripts/`, normalized observation helpers in `tests/golden_state.py`, pytest oracle suites, and `python -m orchestrator run --dry-run` from the repo root.

---

## Entry Status

- The progress ledger records `phase-0-dsl-v214-oracle`, `phase-1-dsl-v214-runtime`, and `dsl-v214-public-release` as completed tranches, and it lists the Phase 1 prerequisite items as completed.
- `docs/backlog/roadmap_gate.json` currently selects gate `dsl-v214-phase2-neurips-stack` and allows only the `phase-2-dsl-v214-neurips-stack` prefix.
- Public release surfaces already advertise `2.14` support in `orchestrator/loader.py`, `specs/dsl.md`, `specs/versioning.md`, and `specs/acceptance/index.md`.
- Translation work is therefore in scope now. A quick sanity check still belongs at implementation start, but this plan no longer treats Phase 2 as dormant or prerelease-only work.

## Selected Item Objective

- Implement backlog item `2026-05-09-dsl-v214-neurips-stack-translation`.
- Produce public same-version v2.14 counterparts for the selected NeurIPS subworkflow stack and prove that normalized observations still match the established Phase 0 oracle coverage.

## Scope

- Add side-by-side v2.14 workflows:
  - `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
  - `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
  - `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
  - `workflows/library/neurips_selected_backlog_item.v214.yaml`
- Replace only the glue that the released v2.14 runtime now supports directly:
  - `materialize_artifacts`
  - `pre_snapshot`
  - `variant_output`
  - `select_variant_output`
  - `requires_variant`
- Keep the translated stack same-version only: any v2.14 workflow added here may call only v2.14 workflows.
- Extend deterministic test coverage so old-stack and v2.14-stack normalized observations match for:
  - the Phase 0 primitive materialization, snapshot-selection, variant-selection, and variant-proof scenarios required for translation confidence
  - the seven minimal NeurIPS scenarios: `completed`, `blocked`, `ambiguous`, `missing_output`, `fresh_plan`, `recovered_plan`, and `selected_item_runtime`
- Add one deterministic public dry-run path for the new v2.14 selected-item stack under normal CLI/loader support.

## Explicit Non-Goals

- Do not reopen or extend Phase 1 runtime semantics.
- Do not add mixed-version reusable workflow calls.
- Do not add deferred abstractions: `recover_or_run`, `resource_transition`, `phase_outcome`, or review-loop macros.
- Do not translate `workflows/examples/neurips_steered_backlog_drain.yaml`, `workflows/library/neurips_backlog_selector.yaml`, or `workflows/library/neurips_backlog_gap_drafter.yaml` unless a narrow authority update makes that unavoidable.
- Do not delete or rename the current `2.7` NeurIPS stack after equivalence is proven.
- Do not weaken golden normalization, queue-state checks, file-hash comparisons, or contract assertions to make mismatches disappear.

## Binding Constraints

- Treat `docs/steering.md`, `docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md`, and the selected-item context as binding execution boundaries.
- Preserve the Phase 2 same-version rule and keep scope inside the selected NeurIPS selected-item stack plus its oracle evidence.
- Keep tests network-free and rely on fake providers or existing deterministic fixtures.
- Preserve existing path-safety rules, same-version call restrictions, and output-contract validation semantics.
- Run commands from the repo root.
- Do not create worktrees for this item.
- Use `tmux` only if a command becomes long-running enough to need live monitoring; otherwise keep checks local and visible.
- Do not mark the backlog item `BLOCKED` for ordinary import failures, harness bugs, path mistakes, or test regressions. Diagnose, narrow-fix, and rerun first. Reserve `BLOCKED` for a true roadmap conflict, missing external prerequisite, unavailable required resource, user decision, or a failure that remains unrecoverable after a documented narrow fix attempt.

## Implementation Architecture

- **v2.14 workflow stack:** Add four side-by-side `.v214.yaml` library workflows. `neurips_backlog_implementation_phase.v214.yaml` is the main semantic migration. `neurips_backlog_seeded_plan_phase.v214.yaml` adopts contract-preserving materialization. `neurips_backlog_roadmap_sync.v214.yaml` and `neurips_selected_backlog_item.v214.yaml` stay conservative compatibility adapters that remove only boilerplate now handled by the runtime.
- **Equivalence harness and smoke scaffolding:** Extend `tests/golden_state.py` and the NeurIPS and primitive oracle tests so the same scenarios can run against the legacy stack and the new v2.14 stack without broadening into a new public top-level drain workflow. Prefer a test-local wrapper or copied fixture workflow if a v2.14 top-level caller is needed for oracle comparison.
- **Documentation surface:** Explain the new `.v214.yaml` workflows, when to use them, and which old pointer, snapshot, and tagged-union glue they replace. Keep the old stack documented as the comparison and migration baseline until a later removal decision exists.

## File And Artifact Targets

Mandatory contract outputs:

- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `tests/golden_state.py`
- `tests/test_v214_primitive_oracle.py`
- `tests/test_neurips_v214_equivalence_oracle.py`
- deterministic smoke inputs under `state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/`, likely including:
  - `current_roadmap_path.txt`
  - `manifest.json`
  - `selector/selection.json`
  - `run_state.json`
  - any additional minimal files required by the direct selected-item dry-run
- `workflows/README.md`

Likely optional compatibility-edit targets:

- `workflows/library/scripts/materialize_neurips_selected_item_inputs.py`
- `workflows/library/scripts/recover_neurips_plan_gate_outputs.py`
- `workflows/library/scripts/reconcile_neurips_selected_item.py`
- `workflows/library/scripts/update_neurips_backlog_run_state.py`
- test-local fixture wrappers or helper files under `tests/fixtures/neurips_minimal/`
- prompt files under `workflows/library/prompts/neurips_*` only if a relative asset path or prompt contract would otherwise break

Preferred packaging:

- Reuse the existing prompt assets and current helper scripts wherever possible.
- Keep the public old-stack example workflow in place; if the oracle harness needs a v2.14 caller, prefer a test-local wrapper over editing `workflows/examples/neurips_steered_backlog_drain.yaml`.
- Do not add new durable docs pages unless `workflows/README.md` cannot hold the migration guidance. If a new durable `docs/` page is created, update `docs/index.md` in the same tranche.

## Execution Checklist

### Task 1: Confirm The Released Entry State And Prepare The Equivalence Harness

- [ ] Reconfirm that the live repo state still matches the consumed authority: the progress ledger still records the public `2.14` release, the roadmap gate still allows only `phase-2-dsl-v214-neurips-stack`, and the loader and spec surfaces still expose public `2.14` support.
- [ ] Run a quick normal-loader `version: "2.14"` sanity check and `pytest tests/test_v214_runtime_semantics.py -q` before translation edits. If either fails, diagnose and narrow-fix the actual issue before proceeding. Only escalate as `BLOCKED` if the failure reveals a real prerequisite or roadmap conflict outside this item.
- [ ] Extend `tests/golden_state.py` so the NeurIPS oracle harness can execute either the legacy stack or the new v2.14 stack from the same fixture scenarios and copy any newly added `.v214.yaml` workflow files.
- [ ] If the NeurIPS oracle needs a top-level v2.14 caller for comparison, add it as a test-local fixture or generated wrapper rather than broadening public workflow scope.

Verification:

- Blocking: run the release sanity checks before or immediately alongside the first harness edit.

```bash
python - <<'PY'
import tempfile
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader

with tempfile.TemporaryDirectory() as tmp:
    workspace = Path(tmp)
    workflow_path = workspace / "release_gate_smoke.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.14",
                "name": "release-gate-smoke",
                "steps": [{"name": "Noop", "command": ["python", "-c", "print('ok')"]}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    WorkflowLoader(workspace).load(workflow_path)
    print("loader_accepts_2_14=true")
PY
pytest tests/test_v214_runtime_semantics.py -q
```

- Supporting: if new tests or parametrized cases are added in `tests/test_neurips_v214_equivalence_oracle.py`, run `pytest --collect-only tests/test_neurips_v214_equivalence_oracle.py -q`.

### Task 2: Translate The Implementation Phase To Native v2.14 Semantics

- [ ] Create `workflows/library/neurips_backlog_implementation_phase.v214.yaml` as the authoritative same-version v2.14 implementation phase.
- [ ] Replace the old implementation-phase boilerplate with released v2.14 primitives:
  - use `materialize_artifacts` for deterministic input and target pointer materialization
  - use `pre_snapshot` plus `select_variant_output` for fresh report selection instead of mtime or ad hoc bundle picking
  - use `variant_output` and `requires_variant` or `match` proof for `COMPLETED` versus `BLOCKED` outcome handling
- [ ] Preserve the review and fix loop, check-suite runner, user-facing outcome contract, and expected caller-visible artifact names unless a narrow compatibility edit is required.

Verification:

- Supporting: `pytest tests/test_neurips_v214_equivalence_oracle.py -q -k 'completed or blocked or ambiguous or missing_output'`
- Supporting: if the implementation-phase translation changes selected-variant or snapshot evidence shape, rerun the narrow affected primitive checks first.

### Task 3: Translate The Seeded Plan Phase With Contract-Preserving Materialization

- [ ] Create `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`.
- [ ] Replace plan-context pointer boilerplate with `materialize_artifacts` wherever the source contract is already authoritative, including steering, design, roadmap, selected-item context, progress ledger, plan target, and plan-review target surfaces.
- [ ] Preserve the existing draft, review, revise, and finalize loop behavior, decision enums, and final plan publication semantics.

Verification:

- Supporting: `pytest tests/test_neurips_v214_equivalence_oracle.py -q -k 'fresh_plan or recovered_plan'`
- Supporting: if plan-phase test names or parametrization change, run `pytest --collect-only tests/test_neurips_v214_equivalence_oracle.py -q`.

### Task 4: Translate Roadmap Sync And Selected-Item Routing As A Same-Version v2.14 Stack

- [ ] Create `workflows/library/neurips_backlog_roadmap_sync.v214.yaml` as the authoritative v2.14 roadmap-sync counterpart to the current `_phase` file, with minimal semantic refactor beyond same-version compatibility and released v2.14 primitives.
- [ ] Create `workflows/library/neurips_selected_backlog_item.v214.yaml` and update its imports so it calls only v2.14 workflows.
- [ ] Replace only the selected-item boilerplate that Phase 1 made first-class:
  - simple input materialization
  - target pointer materialization
  - straightforward published relpath handling
  - variant-safe references to implementation outputs
- [ ] Keep the domain-shaped recovery, reconcile, queue-move, and run-state scripts unless a narrow compatibility edit is required.
- [ ] Add deterministic direct-dry-run inputs under `state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/` so the public v2.14 selected-item stack can be validated without translating the higher-level drain wrapper.

Verification:

- Supporting: `pytest tests/test_neurips_v214_equivalence_oracle.py -q -k selected_item_runtime`
- Blocking: dry-run the new public selected-item stack once the smoke inputs exist.

```bash
python -m orchestrator run workflows/library/neurips_selected_backlog_item.v214.yaml --dry-run \
  --input state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/run \
  --input current_roadmap_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-roadmap.md \
  --input current_roadmap_pointer_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/current_roadmap_path.txt \
  --input selector_state_root=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/selector \
  --input manifest_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/manifest.json \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-05-08-dsl-v214-materialization-variants-implementation-plan.md \
  --input progress_ledger_path=state/DSL-V214-MATERIALIZATION-VARIANTS/progress_ledger.json \
  --input run_state_path=state/DSL-V214-MATERIALIZATION-VARIANTS/smoke/selected_item_v214/run_state.json
```

### Task 5: Expand Primitive And NeurIPS Differential Evidence

- [ ] Update `tests/test_v214_primitive_oracle.py` so the primitive scenarios used by this translation item explicitly compare the Phase 0 legacy-emulation behavior against the public v2.14 behavior rather than only reasserting one side in isolation. Cover:
  - materialization contract success and missing-target failure
  - snapshot selection no-change, single-change, and multi-change outcomes
  - variant-output success and invalid-bundle failure
  - variant-proof acceptance and rejection
- [ ] Update `tests/test_neurips_v214_equivalence_oracle.py` so each required NeurIPS scenario compares the old-stack normalized observation to the v2.14-stack normalized observation, not just one stack to a fixture independently.
- [ ] Keep the normalized observation schema in `tests/golden_state.py` authoritative. Only change expected outputs when the difference is deliberate, documented, and still satisfies the backlog item’s behavioral-equivalence requirement.
- [ ] Preserve comparisons for final workflow outputs, artifact values, selected variants, variant bundle shape, file hashes, queue state, domain run-state summaries, and failure classes. Do not treat intermediate step names, timestamps, run IDs, or removed compatibility-only pointer files as required equivalence surfaces.

Verification:

- Supporting: run the narrowest scenario selector that matches the tranche being edited before expanding to the full suite.
- Blocking: `pytest tests/test_v214_primitive_oracle.py tests/test_neurips_v214_equivalence_oracle.py -q`

### Task 6: Document The v2.14 Stack And Run Final Deterministic Checks

- [ ] Update `workflows/README.md` to explain:
  - which `.v214.yaml` workflows are now available
  - that they are the Phase 2 same-version counterparts to the existing `2.7` NeurIPS selected-item stack
  - which old glue patterns they replace: `materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, and `requires_variant`
  - that the old stack remains in place for migration comparison until a later removal decision
- [ ] Update `docs/index.md` only if this item introduces a new durable doc page under `docs/`.
- [ ] Record implementation notes with the exact checks run and whether any narrow compatibility edits to existing scripts were required.

Verification:

- Blocking: run the backlog item’s required deterministic checks exactly.

```bash
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

- Blocking: rerun the direct v2.14 selected-item dry-run from Task 4 if any selected-item, roadmap-sync, or smoke-fixture files changed after its first passing run.
- Supporting: if final changes only touch docs after all code and workflow checks pass, rerun the exact blocking checks only if the docs edit also changes referenced workflow paths or commands.

## Completion Criteria

- All four `.v214.yaml` library workflows exist and form a same-version call chain.
- The old `2.7` stack remains available and unchanged except for narrowly justified compatibility fixes outside the translated files.
- The primitive and minimal NeurIPS oracle suites prove old-stack versus v2.14 equivalence on the required scenarios.
- A normal CLI and loader dry-run succeeds for the new public v2.14 selected-item stack and for the backlog item’s required example command.
- `workflows/README.md` documents when to use the v2.14 workflows and what released runtime primitives replaced.
