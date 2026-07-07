# Parent-Callable Stdlib Backlog-Drain Compile/Smoke Closure Verification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-verify, with fresh command output on the current checkout, the owned Section-14 compile and Section-13.4 parent-callable smoke acceptance surface of this gap, classify the known non-parity residuals in the broad build-artifacts lane per the architecture's `Residual Failure Routing`, and close the gap as done — without editing any tracked file.

**Architecture:** The fourteenth-revision gap architecture records the causal repair as already landed on this checkout: `orchestrator/workflow_lisp/build.py::_reference_family_versioned_roots` now skips incomplete versioned roots and selects only roots that provide both `drain-summary.json` and `design-gaps/`, so the `reference_family_conformance_input_missing` failure the R49 blocker verification proved is no longer reproducible (Gate D, landed commit `3b62f1c`). The earlier shared parity-root coherence failure (Gate C) is a derived-evidence condition that is checked only after the source-side resolver repair is confirmed; if stale, it is refreshed solely through the sanctioned full-manifest `migration-parity` generator. This plan is therefore verification-and-classification only: every step either confirms a green owned surface or maps a residual failure to a routed class, and any unexpected result is a stop-and-report, not a repair. What this makes harder later: closure evidence is bound to the resolver's live root selection, so a future run that publishes a newer complete versioned root changes the compile's evidence inputs and may require re-verification by whichever lane lands it.

**Tech Stack:** Python 3, Workflow Lisp `.orc`, checked JSON manifests, `pytest`

---

## Governing Inputs

Execute against these authorities:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
  Focus on Sections 11, 13.4, 14, and 15.
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression/implementation_architecture.md`
  The fourteenth-revision acceptance conditions and `Residual Failure
  Routing` are the closure contract this plan executes.
- `orchestrator/workflow_lisp/build.py`
  Read-only live resolver authority for reference-family evidence inputs,
  including the versioned-root completeness rule (commit 3b62f1c).
- `orchestrator/workflow_lisp/reference_family_conformance.py`
  Read-only live conformance-input requirement authority.
- The recovered work-item context bundle the executing run supplies alongside
  this plan. Context only; do not copy runtime-owned run-scoped `state/`
  paths into durable logic or durable documents.

## Scope Guard

- Do not edit any tracked file. This slice's only writes are the run-owned
  progress/closure report and, only if Task 1 Step 2 proves staleness after
  the causal resolver repair is confirmed,
  untracked generator-owned parity evidence via the sanctioned
  `python -m orchestrator migration-parity` CLI.
- Do not edit `orchestrator/workflow_lisp/build.py`,
  `orchestrator/workflow_lisp/reference_family_conformance.py`,
  `orchestrator/workflow_lisp/migration_parity.py`, test suites, Workflow
  Lisp source under `workflows/library/`, or checked manifests under
  `workflows/examples/inputs/workflow_lisp_migrations/`.
- Do not hand-create, copy, or backfill any `artifacts/work/LISP-*/design-gaps`
  directory, and do not hand-edit anything under
  `artifacts/work/review-parity-check/`.
- Preserve the in-flight working-tree edits to `parity_targets.json` and the
  three rebaselined checked manifests byte-for-byte.
- Any failure that does not match a routed residual class in the
  architecture's `Residual Failure Routing` is a stop-and-report: record the
  fresh evidence and end the slice `BLOCKED` rather than repairing out of
  scope.

## Causal Failure Baseline

The observed broken behavior was not "parity is stale" in isolation. The
causal runtime/input failure was that the compile-time reference-family
resolver admitted the newest versioned drain root on `drain-summary.json`
presence alone, which allowed it to select an incomplete root missing the
required `design-gaps/` directory and fail closed on
`reference_family_conformance_input_missing` before owned acceptance checks
could run. The live repair is the resolver-completeness rule landed in commit
`3b62f1c`. This plan must confirm that repair first. Only after the resolver
selects a complete root may it treat parity-root coherence as a conditional
derived-evidence check.

### Task 1: Confirm The Causal Repair And Closure Preconditions

**Files:**

- Read: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Verify: `artifacts/work/review-parity-check/design_delta_parent_drain.json`
- Verify: `artifacts/work/review-parity-check/design_plan_impl_stack.json`
- Verify: `artifacts/work/review-parity-check/cycle_guard_demo.json`

- [ ] **Step 1: Confirm the resolver selects a complete evidence root**

Run:

```bash
python - <<'PY'
from orchestrator.workflow_lisp.build import _resolve_reference_family_evidence_paths

paths = _resolve_reference_family_evidence_paths()
print("run_state_path", paths.run_state_path)
print("drain_summary_exists", paths.drain_summary_path.is_file())
print("design_gap_summary_root", paths.design_gap_summary_root)
print("design_gap_summary_root_exists", paths.design_gap_summary_root.is_dir())
PY
```

Expected: the selected root provides both `drain-summary.json` and an
existing `design-gaps/` directory (on the 2026-07-06 checkout the selection
is `LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R42`; a newer *complete* root
is equally acceptable). If the selected root is incomplete or no candidate
exists, stop and report an evidence-route regression per the architecture's
`Residual Failure Routing` — do not backfill or force selection.

- [ ] **Step 2: Confirm the shared parity root is coherent only after Step 1 passes**

Run:

```bash
python - <<'PY'
import hashlib, json
from pathlib import Path

targets = Path("workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json")
digest = f"sha256:{hashlib.sha256(targets.read_bytes()).hexdigest()}"
for family in ("cycle_guard_demo", "design_plan_impl_stack", "design_delta_parent_drain"):
    report = json.loads(Path(f"artifacts/work/review-parity-check/{family}.json").read_text())
    print(family, report["target_identity"]["target_manifest_sha256"] == digest)
PY
```

Expected: all three families print `True`. If any prints `False`, regenerate
the shared parity root with one full-manifest invocation of the sanctioned
`migration-parity` CLI (no `--target` filter) and rerun this step:

```bash
python -m orchestrator migration-parity \
  --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --output-root artifacts/work/review-parity-check
```

If the rerun still fails, stop and report.

### Task 2: Re-Verify The Owned Acceptance Surfaces

**Files:**

- Verify: `workflows/library/lisp_frontend_design_delta/drain.orc`
- Verify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Verify: `tests/test_workflow_lisp_migration_parity.py`
- Verify: `tests/test_workflow_lisp_reference_family_conformance.py`
- Verify: `tests/test_workflow_lisp_drain_stdlib.py`
- Verify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Run the Section-14 compile entrypoint**

Run:

```bash
python -m orchestrator compile \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: exit 0 with no `reference_family_conformance_invalid` diagnostic of
any inner code (2026-07-06 baseline: fingerprint `2524aa25a3869738`, lowering
route `wcc_m4`). If it fails, stop and report the fresh diagnostic; do not
repair.

- [ ] **Step 2: Run the Section-13.4 parent-callable smoke selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q
```

Expected: 5 passed (2026-07-06 baseline: `5 passed, 88 deselected`).

- [ ] **Step 3: Run the guard lanes**

Run:

```bash
python -m pytest tests/test_workflow_lisp_migration_parity.py \
  -k "design_delta_parent_drain or adapter_census or boundary_authority" -q
python -m pytest tests/test_workflow_lisp_reference_family_conformance.py -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py \
  -k "design_gap_runtime_smoke" -q
```

Expected: all green (2026-07-06 baselines: 22 passed, 17 passed, 63 passed,
1 passed). Any red guard lane is a stop-and-report.

### Task 3: Classify The Broad Build-Artifacts Lane

**Files:**

- Verify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Run the classification lane fresh**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py \
  -k "design_delta_parent_drain or boundary_authority or adapter_census" -q
```

Expected on the 2026-07-06 checkout: `9 failed, 80 passed, 94 deselected`,
with every failure in one of the two routed residual classes named in the
architecture — the run-state bridge retirement status class (4 tests, routed
to `workflow-lisp-design-delta-compatibility-carrier-retirement`) and the
reference-family completed-gap fixture-evidence class (5 tests, routed to
`workflow-lisp-runtime-native-drain-reference-family-parity-evidence-binding-repair`).
The lane going fully green is not required for closure.

- [ ] **Step 2: Map every failure to a routed class**

For each failing test, confirm it matches a class in the architecture's
`Residual Failure Routing` and that the failure is not a parity-surface
failure (`reference_family_parity_report_invalid`,
`reference_family_parity_report_missing`,
`reference_family_parity_surface_mismatch`,
`reference_family_primary_surface_authored`) and not introduced by this
slice. A failure that matches no routed class blocks this slice until it is
diagnosed and either repaired (if in scope) or routed with fresh evidence.

### Task 4: Record Closure And End The Slice

**Files:**

- Write: current run progress/closure report artifact referenced by the
  recovered work-item context

- [ ] **Step 1: Write the run-owned closure report**

Record, with the fresh command output from Tasks 1-3:

- the parity-root coherence result and whether regeneration was needed;
- the resolver-selected complete evidence root;
- the compile, smoke, and guard-lane results;
- the broad-lane residual classification, naming each failing test and its
  routed owning lane; and
- the closure decision under the fourteenth-revision acceptance conditions
  (target-design Sections 11/13.4/14), noting that no tracked file was
  modified by this slice.

- [ ] **Step 2: Preserve the boundedness rule**

Before ending, run:

```bash
git status --short
```

Confirm the output shows no tracked-file modification
introduced by this slice and that the in-flight working-tree edits to
`parity_targets.json` and the three rebaselined checked manifests are
untouched. Then stop; do not widen into any routed residual class.

## Completion Criteria

This plan is complete when all of the following are true:

- the live resolver selects a versioned evidence root providing both
  `drain-summary.json` and `design-gaps/`;
- the shared parity root binds to the current `parity_targets.json` digest
  (confirmed after the resolver repair is verified, or repaired then
  re-confirmed via one sanctioned full-manifest regeneration);
- the Section-14 compile exits 0 with no
  `reference_family_conformance_invalid` diagnostic, and the Section-13.4
  smoke selector and all four guard lanes pass in full, all with fresh
  output;
- every failure in the broad build-artifacts lane maps to a routed residual
  class, none is a parity-surface failure, and none was introduced by this
  slice;
- the run-owned closure report records the evidence above; and
- no tracked file was modified, and no validation logic, conformance-profile
  logic, recovery route, loader rule, gate, source workflow, or test
  expectation was edited, widened, or weakened.
