# Pre-Selector Recovery Simplification Implementation Plan

> **For agentic workers:** Execute task-by-task and track checkbox (`- [ ]`) steps. Do not create a worktree in this repository.

**Goal:** Replace the over-detailed pre-selector dependency/evidence gate with a small deterministic guard that prevents invalid recovery selections without pulling generated history or hidden dependency details into provider judgment.

**Architecture:** Selection remains provider-owned only after deterministic source-owned filtering. The existing `build_recovery_eligibility` helper computes selectable work, priority prerequisites, hidden work, and blocking or diagnostic mechanics errors from current known work and explicit dependencies. Emit a provider manifest for the selector and a private control manifest for deterministic scripts. Provider prompts receive only selectable rows and a short summary; they do not receive hidden refs, missing dependency ids, old run artifacts, or evidence manifests.

**Tech Stack:** Python helper scripts under `workflows/library/scripts/`, existing Design Delta drain YAML, focused pytest coverage in `tests/test_lisp_frontend_autonomous_drain_runtime.py` and a small pure-helper test module if needed.

---

## Files

- Replace or supersede: `docs/plans/2026-06-30-pre-selector-recovery-eligibility-gate-plan.md`
- Modify: `workflows/library/scripts/project_lisp_frontend_selector_manifest.py`
- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify or create focused tests:
  - `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - `tests/test_workflow_recovery_dependency_graph.py`

## Contract

Keep only these mechanics:

- A blocked dependent is not selectable while its prerequisite is incomplete.
- A known runnable prerequisite may be preferred.
- Missing or cyclic prerequisites do not get shown to the provider as draft targets.
- If unrelated eligible work exists, keep selecting that work.
- If no safe selectable work exists and target-gap discovery is disabled, emit
  `blocking_mechanics_errors` and return deterministic `BLOCKED`.
- If target-gap discovery is allowed, keep missing/cyclic prerequisite defects
  diagnostic and let the normal selector discover unrelated target-design work
  from source context, without exposing the missing ids.
- The current drain workflow uses discovery-allowed mode. Discovery-disabled
  behavior is helper/script contract coverage only unless a real workflow route
  later needs it.

Do not add:

- provider-visible dependency diagnostics with missing ids;
- provider-visible `diagnostic_mechanics_errors`;
- provider-visible `hidden_work`;
- provider-visible `target_gap_discovery_allowed`;
- unfiltered diagnostic work rows in selector context;
- evidence/inventory/report reconciliation as selection authority;
- route-specific recovery ontologies;
- broad artifact or run-history scanning.

## Task 1: Simplify The Existing Eligibility Helper Contract

**Files:**

- Modify: `workflows/library/scripts/workflow_recovery_dependencies.py`
- Test: `tests/test_workflow_recovery_dependency_graph.py`

- [ ] **Step 1: Write pure helper tests**

Cover only:

- blocked `A` depends on runnable `B` -> `A` hidden, `B` eligible/priority;
- blocked `A` depends on missing `C` plus runnable `X` -> `A` hidden, `X` eligible, missing `C` internal only;
- blocked `A` depends on missing `C` and no eligible work, with target-gap
  discovery allowed -> diagnostic mechanics error;
- blocked `A` depends on missing `C` and no eligible work, with target-gap
  discovery disabled -> blocking mechanics error;
- direct cycle, with target-gap discovery allowed -> diagnostic mechanics error;
- completed prerequisite -> blocked dependent can become eligible according to its status.

- [ ] **Step 2: Run the focused tests**

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: fail before helper exists or before behavior is implemented.

- [ ] **Step 3: Implement the helper**

Keep the existing shape and simplify what flows downstream:

```json
{
  "eligible_work": [],
  "priority_recovery_work": [],
  "hidden_work": [],
  "blocking_mechanics_errors": [],
  "diagnostic_mechanics_errors": [],
  "hidden_summary": {
    "blocked_by_dependencies": 0,
    "invalid_dependencies": 0
  }
}
```

Do not introduce a second helper file or renamed result fields. Current consumers
already read `eligible_work`, `priority_recovery_work`, `hidden_work`, and
`blocking_mechanics_errors`.

Keep missing ids and detailed dependency paths internal to the helper result or
test assertions. They must not be copied into provider-facing selector input.
The private control manifest should continue using the existing
`blocking_mechanics_errors` field so current detector consumers have one
contract to read.

`diagnostic_mechanics_errors` is helper/debug state, not provider context. If it
is retained at all, write it outside the normal selector manifest or filter it
out before prompt construction.

- [ ] **Step 4: Verify**

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: pass.

## Task 2: Split Provider Manifest From Private Control Manifest

**Files:**

- Modify: `workflows/library/scripts/project_lisp_frontend_selector_manifest.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add a manifest projection test**

Use synthetic rows. Assert:

- provider-facing `items` and `design_gaps` contain only eligible rows;
- provider-facing `priority_recovery_work` contains only known runnable prerequisite refs;
- hidden blocked rows are absent from selectable fields;
- missing dependency ids are absent from the provider-facing manifest;
- provider-facing manifest omits `hidden_work`, `diagnostic_mechanics_errors`,
  and `target_gap_discovery_allowed`;
- private control manifest retains hidden refs and mechanics fields for
  deterministic scripts.

- [ ] **Step 2: Run the test selector**

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "selector_manifest" -q
```

Expected: fail before manifest projection changes.

- [ ] **Step 3: Apply the helper**

Map helper refs back to original rows for provider-facing `items` and `design_gaps`. Emit only compact `hidden_summary` for prompt context.

Do not emit `hidden_work`, unfiltered row dumps, `diagnostic_mechanics_errors`,
or `target_gap_discovery_allowed` into the provider-facing selector manifest.
Write a separate private control manifest for detector and prerequisite scripts.
The private control manifest may contain `hidden_work`,
`diagnostic_mechanics_errors`, `blocking_mechanics_errors`, and
`target_gap_discovery_allowed`.

Update `ProjectSelectorManifest` so its output bundle exposes both:

- `provider_manifest_path`: path to the provider-facing selector manifest;
- `control_manifest_path`: path to the private deterministic-control manifest.

Do not put `control_manifest_path` inside the provider-facing manifest content.
It may appear only in the command step's output bundle/artifacts. Update the
workflow YAML so:

- the selector subworkflow receives `provider_manifest_path`;
- `DetectBlockedDesignGapRecovery` receives `control_manifest_path`;
- `WritePrerequisiteSelection` receives `control_manifest_path`.

- [ ] **Step 4: Verify**

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "selector_manifest" -q
```

Expected: pass.

## Task 3: Route Blocking Mechanics Before Provider Selection

**Files:**

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add script-level route test**

Add a script-level test proving that when the private control manifest has
`blocking_mechanics_errors`, `detect_lisp_frontend_blocked_design_gap_recovery.py`
returns deterministic `BLOCKED`.

Do not require the production discovery-allowed workflow path to synthesize
blocking errors. Add an executor-level no-provider test only if it explicitly
injects a private control manifest fixture with `blocking_mechanics_errors`.

- [ ] **Step 2: Run the test**

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "mechanics_error or selector_manifest" -q
```

Expected: fail until the detector consumes the private control manifest.

- [ ] **Step 3: Wire the detector**

Pass the private control manifest path into `DetectBlockedDesignGapRecovery`.

In the detector, add only an early mechanics-error guard:

- if `blocking_mechanics_errors` is non-empty, return `BLOCKED`;
- otherwise continue the existing detector flow unchanged, including the current
  `SELECT_PREREQUISITE_WORK` / `RECOVER_BLOCKED_DESIGN_GAP` logic.

Do not add new broad inspection of old `state/`, `artifacts/`, or
`.orchestrate/` history.

- [ ] **Step 4: Verify**

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "mechanics_error or selector_manifest" -q
```

Expected: pass.

## Task 4: Preserve Prerequisite Selection Fail-Fast

**Files:**

- Modify if needed: `workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add or verify focused tests**

Cover:

- prerequisite selection reads the private control manifest and accepts refs only
  from `eligible_items`, `eligible_design_gaps`, or `priority_recovery_work`;
- hidden refs return `BLOCKED` with `ineligible_prerequisite_work`;
- missing refs return `BLOCKED` with `missing_dependency_target`.

- [ ] **Step 2: Run focused tests**

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_selection" -q
```

Expected: pass if the current script already enforces this; otherwise fail
until the script is tightened.

- [ ] **Step 3: Tighten only if needed**

If the test fails, update `write_lisp_frontend_prerequisite_selection.py` so
`SELECT_PREREQUISITE_WORK` cannot turn a hidden or missing prerequisite ref into
a selection bundle.

- [ ] **Step 4: Verify**

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_selection" -q
```

Expected: pass.

## Task 5: Remove Heavy Plan Language

**Files:**

- Modify: `docs/plans/2026-06-30-pre-selector-recovery-eligibility-gate-plan.md`

- [ ] **Step 1: Replace the heavy plan with this simplified contract**

Remove requirements for:

- rich diagnostic manifests;
- diagnostic unfiltered rows;
- `target_gap_discovery_allowed` as a workflow input or prompt-visible concept;
- provider-facing dependency defect details;
- evidence/inventory/run-state reconciliation.

- [ ] **Step 2: Check docs diff**

```bash
git diff -- docs/plans/2026-06-30-pre-selector-recovery-eligibility-gate-plan.md docs/plans/2026-06-30-pre-selector-recovery-simplification-plan.md
```

Expected: the old plan no longer asks implementers to build a large dependency/evidence subsystem.

## Final Verification

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py --collect-only -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py --collect-only -q
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "selector_manifest or mechanics_error or prerequisite_selection" -q
python -m orchestrator validate workflows/examples/lisp_frontend_design_delta_drain.yaml
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps
git diff --check
```

Expected: all pass.

Do not commit automatically. Inspect `git status --short` and stage only this plan's implementation hunks if a commit is requested.
