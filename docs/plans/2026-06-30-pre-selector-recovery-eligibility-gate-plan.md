# Pre-Selector Recovery Eligibility Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent blocked recovery dependents from remaining selectable while they wait on incomplete prerequisites.

**Architecture:** Extend the existing generic recovery dependency graph helpers with a small deterministic eligibility projection. Keep strategy and architectural judgment in selector/review/step-back providers, but make known invalid selections impossible by filtering selector input before the provider runs. This is a follow-on to `docs/plans/2026-06-20-generic-workflow-recovery-dependency-graph-plan.md`, not a replacement for it.

**Tech Stack:** Python helper scripts under `workflows/library/scripts/`, current v2.14 drain workflow `workflows/examples/lisp_frontend_design_delta_drain.yaml`, focused unit tests in `tests/test_workflow_recovery_dependency_graph.py` and `tests/test_lisp_frontend_autonomous_drain_runtime.py`, and dry-run validation through `python -m orchestrator run ... --dry-run`.

---

## Scope

This plan fixes recovery/dependency scheduling only.

In scope:

- Hide known blocked work whose prerequisite dependency is incomplete.
- Mark runnable prerequisite work as priority recovery work.
- Keep normal target-design gap discovery available.
- Detect missing, cyclic, or contradictory dependency state before selector work.
- Ensure selector manifests do not present forbidden known work as selectable.
- Block deterministically before provider selection only when invalid dependency
  state prevents a valid selection; diagnostics attached only to hidden blocked
  work must not block unrelated eligible work.

Dirty worktree rule:

- Do not run broad `git add <shared-file>` or commit from this plan unless the
  user explicitly asks for a commit.
- Before any staging or commit, inspect `git status --short` and `git diff` for
  every touched path.
- If a touched path already had unrelated changes, use hunk staging (`git add
  -p`) or leave it unstaged. Refuse to commit pre-existing unrelated changes.

Out of scope:

- Changing Workflow Lisp compiler/runtime semantics.
- Changing target design content.
- Changing provider prompts unless a test proves the selector still receives forbidden selectable choices after deterministic filtering.
- Building a general project-management scheduler.
- Guaranteeing that the selected prerequisite is architecturally correct. Gap review and step-back still own that.

## Existing Context

Relevant existing pieces:

- `workflows/library/scripts/workflow_recovery_dependencies.py`
  - already defines `WorkRef`, `RecoveryDependencyEdge`, `normalize_edge`, `evaluate_edge`, and `edge_from_blocked_entry`.
- `workflows/library/scripts/project_lisp_frontend_selector_manifest.py`
  - currently emits `items`, `design_gaps`, and `dependency_edges`;
  - it marks blocked design gaps but still includes them in the visible `design_gaps` array.
- `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
  - detects recovery state and returns `SELECT_PREREQUISITE_WORK`, `RECOVER_BLOCKED_DESIGN_GAP`, or `BLOCKED`.
- `workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py`
  - deterministically writes a prerequisite selection from `blocked-recovery.json`.
- `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py`
  - records whether prerequisite recovery completed, continues, or became recoverably blocked.

Observed bug this plan prevents:

```text
A = workflow-lisp-design-delta-compatibility-carrier-retirement
A requires B = std-drain-backlog-drain-selector-blocked-run-state-carrier-retirement
selector still selected A
```

Correct behavior:

```text
hide A from selectable work while B is incomplete
include B as priority recovery work if B is runnable
if B requires missing C, return missing_dependency_target instead of selecting A or auto-creating C
```

## Data Contract

Add a derived selector-manifest view. Existing fields may remain for compatibility, but provider selection should use the filtered fields. This example is the provider-facing selector manifest shape; helper-only fields such as `waiting_on` do not appear here.

```json
{
  "eligible_items": [],
  "eligible_design_gaps": [],
  "priority_recovery_work": [
    {
      "source": "DESIGN_GAP",
      "id": "std-drain-backlog-drain-selector-blocked-run-state-carrier-retirement",
      "status": "available"
    }
  ],
  "hidden_work": [
    {
      "source": "DESIGN_GAP",
      "id": "workflow-lisp-design-delta-compatibility-carrier-retirement",
      "reason": "waiting_on_incomplete_dependency"
    }
  ],
  "hidden_summary": {
    "blocked_by_dependencies": 1,
    "invalid_dependencies": 0
  },
  "blocking_mechanics_errors": [],
  "diagnostic_mechanics_errors": [],
  "blocking_mechanics_error_count": 0
}
```

Rules:

- `eligible_design_gaps` excludes completed gaps and blocked dependents waiting on incomplete dependencies.
- `eligible_items` and `eligible_design_gaps` are full manifest rows, not bare
  eligibility refs. Build them by mapping eligible refs back to the original
  item/design-gap rows so prompt-critical fields such as title, path, status,
  and architecture location are preserved.
- `priority_recovery_work` contains runnable prerequisites for blocked work.
- Provider-facing `items` and `design_gaps` must be filtered aliases of
  `eligible_items` and `eligible_design_gaps`. Do not leave forbidden known
  work in fields the current selector prompt can read as selectable work.
- Diagnostic unfiltered rows, if retained, must use names such as
  `all_items_diagnostic` / `all_design_gaps_diagnostic`; those fields are not
  selection authority.
- `blocking_mechanics_errors` contains invalid graph state that prevents a
  valid selection, such as an invalid priority recovery row or no eligible work
  remaining after dependency filtering when target-design gap discovery is not
  allowed.
- `diagnostic_mechanics_errors` contains invalid graph state attached only to
  hidden blocked work. These diagnostics must not prevent selection of unrelated
  eligible work.
- `blocking_mechanics_error_count` is a derived manifest field for diagnostics
  and cheap assertions. `blocking_mechanics_errors` is the semantic trigger.
  Neither field is the workflow YAML routing source of truth; the deterministic
  detector owns the gate by reading the selector manifest.
- New target-design gap discovery remains allowed when
  `target_gap_discovery_allowed` is true. In that case, dependency defects that
  only hide known work stay diagnostic even if no known eligible work remains;
  the selector may still choose `DRAFT_DESIGN_GAP`.
- Missing dependency targets must not be auto-created or auto-selected as the
  prerequisite target. When discovery is allowed, the normal selector may still
  draft unrelated target-design work through its ordinary `DRAFT_DESIGN_GAP`
  route.
- The normal selector manifest must not expose missing dependency target ids.
  Keep detailed missing refs in helper output or non-provider diagnostics only;
  provider-facing `hidden_work` should be limited to source/id/reason for hidden
  known work, and provider-facing mechanics errors should expose compact
  code/reason only without missing ids, paths, titles, or source refs.
- Selector output validation must reject any `DRAFT_DESIGN_GAP` whose id/source
  matches an internal hidden missing-dependency ref. Discovery may draft normal
  target-design work; it must not promote recovery-internal dependency defects
  into provider-created work.
- Provider-facing counts are filtered aliases: `active_count == len(items)` and
  `design_gap_count == len(design_gaps)`.
- Do not inject unfiltered `all_items_diagnostic` /
  `all_design_gaps_diagnostic` rows into the normal selector manifest. If
  unfiltered row dumps are needed for debugging, write them to a separate
  non-provider diagnostic artifact. Compact counts/summaries are acceptable.

## Task 1: Add Pure Eligibility Tests

**Files:**

- Modify: `workflows/library/scripts/workflow_recovery_dependencies.py`
- Modify: `tests/test_workflow_recovery_dependency_graph.py`

- [ ] **Step 1: Write failing tests for eligibility projection**

Add tests to `tests/test_workflow_recovery_dependency_graph.py` for a new helper:

```python
from workflows.library.scripts.workflow_recovery_dependencies import build_recovery_eligibility


def test_eligibility_hides_dependent_waiting_on_incomplete_prerequisite():
    state = {
        "completed_design_gaps": [],
        "completed_items": [],
        "blocked_design_gaps": {
            "a": {
                "reason": "implementation_blocked",
                "recovery_dependency_edge": {
                    "blocked_work": {"source": "DESIGN_GAP", "id": "a"},
                    "blocker_work": {"source": "DESIGN_GAP", "id": "b"},
                    "relation": "requires_completion",
                    "reason_code": "missing_b",
                    "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "b"},
                    "retry_target": {"source": "DESIGN_GAP", "id": "a"},
                },
            }
        },
    }
    known = [
        {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
        {"source": "DESIGN_GAP", "id": "b", "status": "available"},
    ]

    eligibility = build_recovery_eligibility(known, state)

    assert [item["id"] for item in eligibility["eligible_work"]] == ["b"]
    assert [item["id"] for item in eligibility["hidden_work"]] == ["a"]
    assert eligibility["priority_recovery_work"][0]["id"] == "b"
```

Also add tests for:

- completed prerequisite makes retry target eligible again;
- missing prerequisite returns `missing_dependency_target` as diagnostic or
  blocking state according to `target_gap_discovery_allowed`;
- direct cycle returns `dependency_cycle`;
- blocked prerequisite with recoverable metadata appears as priority recovery work only if it is itself runnable under current state;
- independent available work remains eligible.
- `A requires B`, `B requires missing C`, and unrelated runnable `X` keeps `X`
  eligible while reporting the missing `C` as diagnostic hidden-work state.
- the same chain with no unrelated eligible work and
  `target_gap_discovery_allowed=True` reports missing `C` as diagnostic so the
  selector can still draft new target-design work.
- the same chain with no unrelated eligible work and
  `target_gap_discovery_allowed=False` reports missing `C` as a blocking
  mechanics error.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: fails because `build_recovery_eligibility` does not exist.

- [ ] **Step 3: Implement minimal helper**

In `workflow_recovery_dependencies.py`, add:

```python
def build_recovery_eligibility(
    known_work: list[Mapping[str, Any]],
    run_state: Mapping[str, Any],
    *,
    target_gap_discovery_allowed: bool = True,
) -> dict[str, Any]:
    ...
```

Implementation rules:

- Parse `known_work` rows with `source`, `id`, and optional `status`.
- Extract dependency edges from blocked entries using `edge_from_blocked_entry`.
- Build a dependency graph and evaluate dependency readiness to a fixed point
  before emitting `eligible_work` or `priority_recovery_work`.
- Detect cycles with graph traversal/topological cycle detection before
  priority selection. All members of a dependency cycle are hidden/ineligible,
  reported as `dependency_cycle`, and excluded from priority recovery work.
- For each evaluated dependency relation:
  - if invalid and unrelated eligible work remains, add
    `diagnostic_mechanics_errors`;
  - if invalid and no eligible work remains and target-design gap discovery is
    not allowed, or the invalid state would make a non-runnable row appear in
    `priority_recovery_work`, add `blocking_mechanics_errors`;
  - if ready, hide neither blocker nor retry target solely due to this edge;
  - if waiting, hide `blocked_work` and mark `blocker_work` as priority if present in known work and runnable;
  - if blocker is missing from known work, add `missing_dependency_target`.
- Runnable means:
  - not completed;
  - not hidden by an incomplete dependency;
  - not invalid/cyclic;
  - status is not `retired`, `completed`, or `invalid`.
- Return JSON-serializable dictionaries only.
- Helper return schema:
  - `eligible_work`: refs only, each with `source`, `id`, `status`;
  - `hidden_work`: helper-private refs plus `reason` and optional
    `waiting_on`;
  - `priority_recovery_work`: refs only for runnable prerequisites;
  - `blocking_mechanics_errors`: `{code, work?, missing?, reason?}` objects;
  - `diagnostic_mechanics_errors`: `{code, work?, missing?, reason?}` objects;
  - `hidden_summary`: counts.

The helper output is not provider context. `project_lisp_frontend_selector_manifest.py`
must sanitize helper-private `hidden_work` before writing the normal selector
manifest: provider-facing `hidden_work` is source/id/reason only and must not
include `waiting_on`, missing dependency refs, paths, titles, or dependency
edges.

Do not rank all work or choose the next item.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
```

Expected: pass.

- [ ] **Step 5: Checkpoint safely**

Inspect `git status --short` and `git diff` for touched paths. Do not commit
unless explicitly requested. If a commit is requested in a dirty worktree, stage
only this task's hunks and leave unrelated pre-existing changes unstaged.

## Task 2: Project Eligible Work Into Selector Manifest

**Files:**

- Modify: `workflows/library/scripts/project_lisp_frontend_selector_manifest.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing manifest regression**

Add a test near the existing drain-runtime script tests:

```python
def test_selector_manifest_hides_blocked_dependent_and_prioritizes_prerequisite(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest_path = workspace / "state/drain/manifest.json"
    run_state_path = workspace / "state/drain/run_state.json"
    output_path = workspace / "state/drain/selector-manifest.json"
    gap_root = workspace / "docs/plans/DRAIN/design-gaps"
    for gap_id in ("a", "b"):
        path = gap_root / gap_id / "implementation_architecture.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {gap_id}\\n\\nDesign gap id: `{gap_id}`\\nStatus: draft\\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"items": [], "backlog_root": "docs/backlog/active"}) + "\\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "completed_items": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "a": {
                        "reason": "implementation_blocked",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="a", blocker="b"),
                    }
                },
            }
        )
        + "\\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_selector_manifest.py"),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--architecture-index-root",
        gap_root.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert [gap["design_gap_id"] for gap in payload["eligible_design_gaps"]] == ["b"]
    assert [gap["design_gap_id"] for gap in payload["design_gaps"]] == ["b"]
    assert payload["priority_recovery_work"][0]["id"] == "b"
    assert payload["hidden_work"][0]["id"] == "a"
    assert payload["hidden_summary"]["blocked_by_dependencies"] == 1
```

Also add:

- missing prerequisite emits sanitized `diagnostic_mechanics_errors` with
  `missing_dependency_target` when unrelated eligible work remains;
- missing prerequisite emits `blocking_mechanics_errors` with
  `missing_dependency_target` when no valid eligible work remains and
  `target_gap_discovery_allowed` is false;
- completed prerequisite makes blocked retry target eligible instead of hidden.
- `priority_recovery_work` excludes a prerequisite that is hidden by its own
  incomplete dependency, such as `A requires B` and `B requires missing C`.
- indirect cycles such as `A requires B`, `B requires C`, `C requires A`
  hide all cycle members, report `dependency_cycle`, and produce no priority
  recovery work.
- provider-facing `design_gaps` excludes hidden rows even if diagnostic
  unfiltered rows are retained elsewhere.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "selector_manifest or prerequisite" -q
```

Expected: new selector-manifest assertions fail because fields are absent or blocked dependent remains selectable.

- [ ] **Step 3: Wire helper into manifest projection**

In `project_lisp_frontend_selector_manifest.py`:

- Import `build_recovery_eligibility`.
- Convert backlog rows to known-work refs:
  - `{"source": "BACKLOG_ITEM", "id": item["item_id"], "status": "available"}`
- Convert design-gap rows to known-work refs:
  - `{"source": "DESIGN_GAP", "id": gap["design_gap_id"], "status": gap["status"]}`
- Call `build_recovery_eligibility(...)`.
- Add a manifest CLI flag such as `--target-gap-discovery-allowed true|false`,
  defaulting to `true`, and pass it to `build_recovery_eligibility(...)`.
  The current drain workflow uses the default discovery-allowed mode. The false
  mode is a script/helper contract for callers that do not allow new target-gap
  discovery; do not add a workflow input unless a real workflow route needs it.
- Map `eligible_work` refs back to the original manifest rows:
  - `eligible_items` must contain the original item rows for eligible
    `BACKLOG_ITEM` refs;
  - `eligible_design_gaps` must contain the original design-gap rows for
    eligible `DESIGN_GAP` refs;
  - keep row fields such as `item_id`, `design_gap_id`, `title`, `path`,
    `status`, and architecture/report paths unchanged.
- Emit:
  - `eligible_items`;
  - `eligible_design_gaps`;
  - `priority_recovery_work`;
  - provider-facing `hidden_work` sanitized from helper-private `hidden_work`
    to source/id/reason only, with no `waiting_on`;
  - `hidden_summary`;
  - provider-facing `blocking_mechanics_errors` and
    `diagnostic_mechanics_errors` sanitized to code/reason only, with no
    missing ids, paths, titles, or source refs.
- Emit `blocking_mechanics_error_count` as an integer derived from
  `blocking_mechanics_errors`.
- Emit `target_gap_discovery_allowed` as a boolean.

Set existing provider-facing `items` and `design_gaps` to the filtered eligible
rows. Do not include unfiltered row arrays in the normal selector manifest.
Do not include `dependency_edges` in the normal selector manifest; they expose
hidden or missing dependency targets and are audit data, not selector input.
Set `active_count` and `design_gap_count` from the filtered `items` and
`design_gaps` arrays. If unfiltered counts are retained, use diagnostic names.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "selector_manifest or prerequisite" -q
```

Expected: pass.

- [ ] **Step 5: Checkpoint safely**

Inspect `git status --short` and `git diff` for touched paths. Do not commit
unless explicitly requested. If a commit is requested in a dirty worktree, stage
only this task's hunks and leave unrelated pre-existing changes unstaged.

## Task 3: Block Blocking Mechanics Errors Before Provider Selection

**Files:**

- Modify: `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py`
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing route test**

Add a test proving that a selector manifest with `blocking_mechanics_errors`
causes deterministic `BLOCKED` before `RunNormalSelector` can execute.

Expected output from `detect_lisp_frontend_blocked_design_gap_recovery.py`:

```json
{
  "pre_selection_route": "BLOCKED",
  "recovery_route": "TERMINAL_BLOCKED",
  "recovery_reason": "missing_dependency_target",
  "block_reason": "missing_dependency_target"
}
```

Use a synthetic missing dependency. Cover the route with an executor-level test,
not YAML structure inspection alone: `DetectBlockedDesignGapRecovery` receives
the selector manifest path, returns `BLOCKED`, and `SelectNextWork` takes the
`BLOCKED` branch without calling `RunNormalSelector`. Use a sentinel/failing
selector provider, provider call counter, or equivalent executor hook so the
test fails if the provider branch is entered.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "mechanics_error or selector_manifest" -q
```

Expected: fails because blocking mechanics errors are currently visible in the selector
manifest only and are not routed before normal provider selection.

- [ ] **Step 3: Add deterministic mechanics-error route**

In `detect_lisp_frontend_blocked_design_gap_recovery.py`:

- add optional `--selector-manifest-path`;
- load it before normal blocked recovery selection after non-progress handling;
- if `blocking_mechanics_errors` is non-empty, return
  `_block_payload(first_error_code)`;
- optionally assert `blocking_mechanics_error_count` agrees with
  `len(blocking_mechanics_errors)`, but do not make the count the semantic
  source of the route;
- if only `diagnostic_mechanics_errors` are present and either eligible work
  remains or `target_gap_discovery_allowed` is true, allow normal selector
  execution over the filtered manifest;
- after provider selection, reject any `DRAFT_DESIGN_GAP` whose id/source
  matches an internal hidden missing-dependency ref, because recovery
  diagnostics are not provider draft authority;
- if run state points at prerequisite work but the selector manifest marks that
  target hidden/ineligible and has only diagnostic mechanics errors, return
  `SELECT_NORMAL_WORK` instead of sending the hidden target to prerequisite
  selection;
- include enough fields for the existing `BLOCKED` selector placeholder and
  drain-status path to work.

In `workflows/examples/lisp_frontend_design_delta_drain.yaml`:

- pass the concrete selector-manifest path
  `${inputs.drain_state_root}/iterations/${loop.index}/selector-manifest.json`
  to `DetectBlockedDesignGapRecovery`;
- keep `SelectNextWork` matched on `DetectBlockedDesignGapRecovery.artifacts.pre_selection_route`.
- do not add a second YAML-level mechanics-error route from
  `ProjectSelectorManifest`; the detector is the single routing owner for this
  gate.

Chosen contract: invalid eligibility blocks the iteration deterministically only
when no valid selection should be made. Hidden-work-only dependency defects stay
diagnostic so unrelated eligible work can proceed. The provider selector is not
asked to return a `BLOCKED` bundle for blocking mechanics errors.

- [ ] **Step 4: Run focused test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "mechanics_error or selector_manifest" -q
```

Expected: pass.

- [ ] **Step 5: Checkpoint safely**

Inspect `git status --short` and `git diff` for touched paths. Do not commit
unless explicitly requested. If a commit is requested in a dirty worktree, stage
only this task's hunks and leave unrelated pre-existing changes unstaged.

## Task 4: Make Prerequisite Selection Fail Fast On Invalid Eligibility

**Files:**

- Modify: `workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

- `write_lisp_frontend_prerequisite_selection.py` selects a prerequisite only when the prerequisite appears in `eligible_design_gaps`, `eligible_items`, or `priority_recovery_work`;
- if the pre-selection points to a missing prerequisite, output is `BLOCKED` with `missing_dependency_target`;
- if the pre-selection points to a hidden/ineligible work item, output is `BLOCKED` with `ineligible_prerequisite_work`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_selection" -q
```

Expected: fails because prerequisite selection currently trusts the pre-selection pointer and the broad manifest.

- [ ] **Step 3: Enforce eligible-manifest selection**

In `write_lisp_frontend_prerequisite_selection.py`:

- Add helper `_eligible_ref(manifest, source, item_id)`.
- For `DESIGN_GAP`, require the id in `eligible_design_gaps` or `priority_recovery_work`.
- For `BACKLOG_ITEM`, require the id in `eligible_items` or `priority_recovery_work`.
- If missing from eligible, priority, and hidden-work refs, return
  `_blocked("missing_dependency_target: ...")`.
- If present in `hidden_work` but absent from eligible fields, return
  `_blocked("ineligible_prerequisite_work: ...")`.
- Do not require unfiltered `all_items_diagnostic` or
  `all_design_gaps_diagnostic` rows for this decision; those rows may remain
  optional diagnostics.

Do not read old recovery artifacts or target-design docs here. This script should remain deterministic routing.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "prerequisite_selection" -q
```

Expected: pass.

- [ ] **Step 5: Checkpoint safely**

Inspect `git status --short` and `git diff` for touched paths. Do not commit
unless explicitly requested. If a commit is requested in a dirty worktree, stage
only this task's hunks and leave unrelated pre-existing changes unstaged.

## Task 5: Align Workflow Output Contract And Smoke Checks

**Files:**

- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add output-bundle contract fields if needed**

Inspect `ProjectSelectorManifest` output bundle in `workflows/examples/lisp_frontend_design_delta_drain.yaml`.

If the runtime needs declared fields for downstream references, add only minimal fields:

- `eligible_design_gap_count` if referenced later;

Do not add fields solely for evidence/reporting.

- [ ] **Step 2: Add or adjust dry-run test**

Add a focused loader/dry-run assertion if absent:

```python
def test_design_delta_drain_dry_run_accepts_recovery_eligibility_manifest_contract(tmp_path):
    ...
```

Use the existing `_copy_runtime_files(...)` helper and `WorkflowLoader`/dry-run pattern already present in `tests/test_lisp_frontend_autonomous_drain_runtime.py`.

- [ ] **Step 3: Run collect-only if tests were added**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py --collect-only -q
```

Expected: new tests collect.

- [ ] **Step 4: Run workflow dry-run**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json
```

Expected: dry-run succeeds.

These inputs may remain workflow-boundary/runtime inputs for this smoke. Do not add prompt injection or provider context for `post_wcc_inventory_path` or `progress_ledger_path` as part of this task.

- [ ] **Step 5: Checkpoint safely**

Inspect `git status --short` and `git diff` for touched paths. Do not commit
unless explicitly requested. If a commit is requested in a dirty worktree, stage
only this task's hunks and leave unrelated pre-existing changes unstaged.

## Task 6: Regression Against Chained Dependency Failure

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add exact-shape regression**

Add a regression using synthetic ids matching the failure class, not hardcoded run ids:

```text
A requires B
B requires missing C
X is unrelated and runnable
```

Expected:

- `A` is hidden;
- `B` is hidden or ineligible while waiting on missing `C`;
- selector manifest contains `missing_dependency_target` for `C` as a diagnostic
  hidden-work error;
- `priority_recovery_work` does not contain `B` while `B` is waiting on missing `C`;
- provider-facing selectable rows still contain `X`;
- deterministic recovery detection allows normal selector execution over `X`;
- no selectable row contains `A`.

Add a second case with no unrelated runnable `X` and
`target_gap_discovery_allowed=True`. Expected: the same missing dependency stays
diagnostic and deterministic recovery detection allows normal selector execution
so the selector can draft new target-design work.

Add a third case with no unrelated runnable `X` and
`target_gap_discovery_allowed=False`. Expected: the same missing dependency
becomes a blocking mechanics error and deterministic recovery detection returns
`BLOCKED` before provider selector execution.

- [ ] **Step 2: Run regression**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "recovery_eligibility or selector_manifest" -q
```

Expected: pass.

- [ ] **Step 3: Run combined focused suite**

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py tests/test_lisp_frontend_autonomous_drain_runtime.py -k "recovery or prerequisite or selector_manifest" -q
```

Expected: pass.

- [ ] **Step 4: Checkpoint safely**

Inspect `git status --short` and `git diff` for touched paths. Do not commit
unless explicitly requested. If a commit is requested in a dirty worktree, stage
only this task's hunks and leave unrelated pre-existing changes unstaged.

## Final Verification

Run:

```bash
python -m pytest tests/test_workflow_recovery_dependency_graph.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "recovery or prerequisite or selector_manifest or mechanics_error" -q
python -m pytest tests/test_workflow_recovery_dependency_graph.py --collect-only -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py --collect-only -q
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json
git diff --check
```

Expected:

- focused tests pass;
- collect-only succeeds;
- workflow dry-run succeeds;
- no whitespace errors.

## Acceptance Criteria

- A blocked dependent waiting on an incomplete prerequisite is absent from selectable manifest fields.
- A runnable prerequisite is present as priority recovery work, while final choice remains selector-owned.
- Missing prerequisite targets become precise mechanics errors, not auto-drafted work.
- Missing prerequisite targets are not auto-created or auto-selected as
  prerequisite work. Normal target-design discovery may still run when
  `target_gap_discovery_allowed` is true.
- Blocking mechanics errors route to deterministic `BLOCKED` before provider
  selector execution.
- Mechanics diagnostics attached only to hidden blocked work do not block
  unrelated eligible work.
- Provider-facing `items` and `design_gaps` do not contain hidden/ineligible known work.
- The selector prompt no longer needs to inspect old recovery artifacts to avoid selecting forbidden work.
- The change is generic to recovery dependencies and does not hardcode R21 ids, target design names, or Workflow Lisp domain nouns beyond the existing Lisp frontend drain integration script names.

## Risks And Non-Goals

- This does not prove the prerequisite is architecturally correct; gap review and step-back remain responsible.
- This does not fix dirty-worktree ambiguity.
- This does not fix weak DONE review.
- This deliberately does not auto-create missing prerequisite gaps. Missing work should block with a precise mechanics error or be discovered through the normal target-design gap route.
- If existing prompt text still points providers at legacy `design_gaps`, make the smallest prompt edit after deterministic fields exist: tell the selector that `eligible_items` and `eligible_design_gaps` are the selectable known-work lists. Queue that prompt change first if managing mode rules require explicit approval.
