# NeurIPS Backlog Invalid Item Tolerance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NeurIPS backlog drain robust to malformed non-selected active backlog items while keeping selected-item execution strict.

**Architecture:** Split queue validation into two tiers. Broad manifest building records invalid active items as diagnostics and excludes them from selection; selected-item materialization remains fatal if the selected item lacks required artifacts. Gap drafting becomes atomic by drafting candidate files outside `docs/backlog/active` and installing them only after deterministic validation.

**Tech Stack:** Python workflow helper scripts, YAML workflow definitions, pytest, agent-orchestration DSL v2.12.

---

## File Structure

- Modify `workflows/library/scripts/build_neurips_backlog_manifest.py`
  - Parse active backlog items into valid `items` plus `invalid_items`.
  - Keep fatal failures for unsafe paths, unreadable backlog roots, and malformed global inputs.
  - Treat per-item defects such as missing `plan_path` target as item-local diagnostics.

- Modify `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py`
  - Preserve invalid item diagnostics when refreshing from the backlog root.
  - Gate only valid items for selection.
  - Use invalid current-phase items only to decide whether the drain is blocked when no valid eligible item exists.

- Modify `workflows/library/scripts/validate_neurips_backlog_gap_draft.py`
  - Support candidate draft files under workflow state.
  - Install validated backlog item and plan files into their final repo locations only after both are valid.
  - Keep backward-compatible validation for existing direct-to-target draft bundles only if needed by tests, but prefer the candidate install path in the workflow.

- Modify `workflows/library/neurips_backlog_gap_drafter.yaml`
  - Pass candidate item/plan target paths under the gap drafter state root to the provider.
  - Update deterministic output validation to consume candidate paths and final target paths.

- Modify `workflows/library/prompts/neurips_backlog_gap_drafter/*.md` or the exact prompt file used by `neurips_backlog_gap_drafter.yaml`
  - Tell the drafter to write candidate files in the state root, not directly to `docs/backlog/active`.
  - Keep wording short: draft candidate item, draft candidate plan, emit bundle.

- Modify `workflows/examples/neurips_steered_backlog_drain.yaml`
  - Keep `SelectNextItem` and `RunSelectedItem` consuming `ReconcileBacklogRoadmapGate.artifacts.eligible_manifest_path`.
  - Add or adjust output fields only if the gate needs to expose invalid diagnostics as a declared artifact.

- Modify `tests/test_neurips_backlog_roadmap_gate.py`
  - Add regression tests for missing plan targets and invalid item diagnostics.
  - Add tests for gate behavior with valid eligible items plus invalid unrelated items.
  - Add tests for blocked behavior when only current-phase work is invalid.
  - Add tests for atomic gap draft installation.

- Modify `docs/workflow_drafting_guide.md`
  - Document the pattern: broad queue scans should produce valid and invalid partitions; selected-item gates stay strict.

- Modify `workflows/README.md`
  - Note that the NeurIPS backlog drain tolerates malformed non-selected active items and reports them as diagnostics.

- Propagate changed workflow components to `/home/ollie/Documents/PtychoPINN/`
  - Copy the changed workflow YAML, helper scripts, prompts, and tests to matching paths in PtychoPINN if those files exist there.
  - Validate from the PtychoPINN repo as well, because that is the active workflow consumer.

## Task 1: Add Failing Manifest Tests

**Files:**
- Modify: `tests/test_neurips_backlog_roadmap_gate.py`
- Test: `tests/test_neurips_backlog_roadmap_gate.py`

- [ ] **Step 1: Add a missing-plan manifest builder test**

Add a test that writes two active backlog items:

```python
def test_manifest_builder_records_missing_plan_target_as_invalid_item(tmp_path: Path) -> None:
    _write_backlog_item(tmp_path, "2026-05-04-valid-phase2", priority=10, prerequisites=[], phase="phase-2-pdebench-128x128-image-suite")

    missing_item = tmp_path / "docs/backlog/active/2026-05-04-missing-plan.md"
    missing_item.write_text(
        """---
priority: 11
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/missing-plan.md
check_commands:
  - python -m compileall -q workflows
related_roadmap_phases:
  - phase-2-pdebench-128x128-image-suite
---

# Backlog Item: Missing Plan

## Objective

- This item is intentionally invalid.
""",
        encoding="utf-8",
    )

    output_path = tmp_path / "state/backlog/manifest.json"
    subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--backlog-root", "docs/backlog/active", "--output", output_path.relative_to(tmp_path).as_posix()],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )

    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert {item["item_id"] for item in manifest["items"]} == {"2026-05-04-valid-phase2"}
    invalid = {item["item_id"]: item for item in manifest["invalid_items"]}
    assert "2026-05-04-missing-plan" in invalid
    assert any("plan_path target does not exist" in reason for reason in invalid["2026-05-04-missing-plan"]["invalid_reasons"])
```

- [ ] **Step 2: Run the new test and confirm it fails**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py::test_manifest_builder_records_missing_plan_target_as_invalid_item
```

Expected: FAIL because the manifest builder currently exits non-zero on a missing `plan_path`.

## Task 2: Implement Valid/Invalid Manifest Partitioning

**Files:**
- Modify: `workflows/library/scripts/build_neurips_backlog_manifest.py`
- Test: `tests/test_neurips_backlog_roadmap_gate.py`

- [ ] **Step 1: Add item-local diagnostic helpers**

In `build_neurips_backlog_manifest.py`, add a helper that wraps `_build_entry` and returns either a valid entry or an invalid diagnostic:

```python
def _invalid_entry(source_path: Path, reason: str, parsed: dict | None = None) -> dict:
    item_id = source_path.stem
    phases = []
    priority = None
    plan_path = ""
    if parsed:
        phases = _normalized_string_list(parsed.get("related_roadmap_phases"), field="related_roadmap_phases", source_path=source_path)
        plan_path = str(parsed.get("plan_path") or "").strip()
        try:
            priority = int(str(parsed.get("priority")).strip()) if parsed.get("priority") is not None else None
        except ValueError:
            priority = None
    return {
        "item_id": item_id,
        "path": _safe_relpath(source_path, source_path=source_path),
        "status": "invalid",
        "priority": priority,
        "plan_path": plan_path,
        "related_roadmap_phases": phases,
        "invalid_reasons": [reason],
    }
```

Implementation may adjust exact helper shape, but the JSON must include `item_id`, `path`, `status: invalid`, `related_roadmap_phases`, and `invalid_reasons`.

- [ ] **Step 2: Add a safe build wrapper**

Add `_build_entry_or_invalid(path)` that:

- reads and parses frontmatter once;
- returns a valid entry for well-formed items;
- returns an invalid diagnostic for per-item contract failures;
- still raises for path escapes or unreadable root-level failures.

Keep the old `_build_entry(path)` available for callers/tests that expect a valid entry or exception.

- [ ] **Step 3: Update `main()` manifest payload**

Change manifest construction to:

```python
valid_entries = []
invalid_entries = []
for path in sorted(backlog_root.glob("*.md")):
    entry, invalid = _build_entry_or_invalid(path)
    if entry is not None:
        valid_entries.append(entry)
    else:
        invalid_entries.append(invalid)
valid_entries.sort(key=lambda row: (row["priority"], row["path"]))
invalid_entries.sort(key=lambda row: ((row.get("priority") is None, row.get("priority") or 999999), row["path"]))
```

Payload fields:

```json
{
  "manifest_version": 2,
  "backlog_root": "docs/backlog/active",
  "active_count": <valid_count>,
  "total_active_count": <valid_count + invalid_count>,
  "invalid_count": <invalid_count>,
  "items": [...valid...],
  "invalid_items": [...invalid...]
}
```

- [ ] **Step 4: Run manifest tests**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py::test_manifest_builder_accepts_block_scalar_check_commands tests/test_neurips_backlog_roadmap_gate.py::test_manifest_builder_records_missing_plan_target_as_invalid_item
```

Expected: PASS.

## Task 3: Make Roadmap Gate Tolerate Invalid Non-Selected Items

**Files:**
- Modify: `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py`
- Modify: `tests/test_neurips_backlog_roadmap_gate.py`

- [ ] **Step 1: Add failing gate regression tests**

Add:

```python
def test_roadmap_gate_continues_with_valid_eligible_item_when_another_item_has_missing_plan(tmp_path: Path) -> None:
    # One valid phase-2 item and one invalid phase-2 item with missing plan.
    # Reconcile should return ELIGIBLE and the eligible manifest should contain only the valid item.
```

Add:

```python
def test_roadmap_gate_blocks_when_only_current_phase_item_is_invalid(tmp_path: Path) -> None:
    # One invalid phase-2 item with missing plan, no valid eligible items.
    # Reconcile should return BLOCKED, not crash and not DONE.
```

Use the existing policy/progress/run-state fixture style from this file.

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py::test_roadmap_gate_continues_with_valid_eligible_item_when_another_item_has_missing_plan tests/test_neurips_backlog_roadmap_gate.py::test_roadmap_gate_blocks_when_only_current_phase_item_is_invalid
```

Expected: FAIL under current code because `_refresh_manifest_from_backlog_root()` calls `_build_entry()` and crashes on the invalid item.

- [ ] **Step 3: Update manifest refresh**

Change `_refresh_manifest_from_backlog_root()` to use the same partitioning helper as the manifest builder. It should preserve:

- valid `items`;
- `invalid_items`;
- `total_active_count`;
- `invalid_count`;
- `refreshed_from_backlog_root`.

Avoid duplicating parsing logic if possible. Import a helper from `build_neurips_backlog_manifest.py`.

- [ ] **Step 4: Update gate status logic**

Use:

```python
valid_items = manifest.get("items") if isinstance(manifest.get("items"), list) else []
invalid_items = manifest.get("invalid_items") if isinstance(manifest.get("invalid_items"), list) else []
total_active_count = int(manifest.get("total_active_count") or len(valid_items) + len(invalid_items))
```

Rules:

- `DONE` only when `total_active_count == 0`.
- `ELIGIBLE` when there is at least one eligible valid item.
- `BLOCKED` when no valid item is eligible but a valid or invalid item belongs to the current roadmap gate.
- `BACKLOG_GAP` only when there is no valid or invalid current-gate item and the policy allows drafting.
- `BLOCKED` otherwise.

- [ ] **Step 5: Include invalid diagnostics in outputs**

Add to `roadmap-gate.json`:

```json
{
  "invalid_count": 1,
  "invalid_items": [...]
}
```

Also include invalid items in `gap_request.json` diagnostics so a gap drafter or operator can see why active items were excluded.

- [ ] **Step 6: Run roadmap gate tests**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py
```

Expected: PASS.

## Task 4: Make Gap Drafting Atomic

**Files:**
- Modify: `workflows/library/scripts/validate_neurips_backlog_gap_draft.py`
- Modify: `workflows/library/neurips_backlog_gap_drafter.yaml`
- Modify: `workflows/library/prompts/neurips_backlog_gap_drafter/*.md`
- Modify: `tests/test_neurips_backlog_roadmap_gate.py`

- [ ] **Step 1: Add an atomic install test**

Add a test that creates candidate files under `state/gap-drafter/candidate/` and a draft bundle:

```json
{
  "draft_status": "DRAFTED",
  "candidate_backlog_item_path": "state/gap-drafter/candidate/item.md",
  "candidate_plan_path": "state/gap-drafter/candidate/plan.md",
  "backlog_item_path": "docs/backlog/active/2026-05-04-phase2-gap.md",
  "seed_plan_path": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps/2026-05-04-phase2.md"
}
```

Assert:

- validator returns `VALID`;
- final `docs/backlog/active/...md` exists;
- final `docs/plans/...md` exists;
- final backlog item frontmatter `plan_path` equals the final plan path;
- candidate files can remain as provenance but are not the authoritative active item.

- [ ] **Step 2: Add an invalid candidate test**

Create a candidate backlog item whose frontmatter points to a missing or wrong plan path. Assert:

- validator returns non-zero;
- validation JSON says `INVALID`;
- no final active backlog item is installed.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py::test_gap_draft_validator_installs_candidate_item_atomically tests/test_neurips_backlog_roadmap_gate.py::test_gap_draft_validator_rejects_candidate_without_installing_active_item
```

Expected: FAIL because the validator currently expects direct final files.

- [ ] **Step 4: Implement candidate validation and install**

Update `validate_neurips_backlog_gap_draft.py`:

- accept `candidate_backlog_item_path` and `candidate_plan_path`;
- validate candidate paths are under the workflow state root or `state/`;
- validate the candidate backlog item's `plan_path` either equals `seed_plan_path` or rewrite it deterministically during install;
- write final plan first to a temporary sibling path;
- write final backlog item to a temporary sibling path;
- atomically replace final files with `Path.replace()`;
- return final `backlog_item_path` and `seed_plan_path`.

Keep direct final-file mode only if necessary for existing backward compatibility tests. If retained, mark it as compatibility and do not use it in the workflow.

- [ ] **Step 5: Update gap drafter workflow and prompt**

In `workflows/library/neurips_backlog_gap_drafter.yaml`, prepare candidate target paths under `${inputs.state_root}/candidate/`.

Prompt change should be concise:

```md
Write the candidate backlog item to the candidate backlog item path.
Write the candidate plan to the candidate plan path.
In the JSON bundle, report both candidate paths and the final target paths.
Do not write directly to `docs/backlog/active`.
```

- [ ] **Step 6: Run gap draft tests**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py::test_gap_draft_validator_accepts_block_scalar_check_commands tests/test_neurips_backlog_roadmap_gate.py::test_gap_draft_validator_writes_invalid_diagnostic_on_rejection tests/test_neurips_backlog_roadmap_gate.py::test_gap_draft_validator_installs_candidate_item_atomically tests/test_neurips_backlog_roadmap_gate.py::test_gap_draft_validator_rejects_candidate_without_installing_active_item
```

Expected: PASS.

## Task 5: Verify Selected-Item Strictness Is Preserved

**Files:**
- Modify: `tests/test_neurips_backlog_roadmap_gate.py`
- Possibly modify: `workflows/library/neurips_selected_backlog_item.yaml`

- [ ] **Step 1: Add or confirm selected-item fatal validation test**

Add a test if one does not already exist:

```python
def test_selected_item_with_missing_plan_still_fails_materialization(tmp_path: Path) -> None:
    # Directly call the selected-item materialization helper or run the selected-item workflow
    # with a selected manifest containing a missing plan_path.
    # Expected: non-zero result with "plan" and "does not exist" in stderr.
```

Do not weaken selected-item checks to make earlier tests pass.

- [ ] **Step 2: Run the selected-item test**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py::test_selected_item_with_missing_plan_still_fails_materialization
```

Expected: PASS after the test is implemented and the current selected-item validation is confirmed.

## Task 6: Documentation

**Files:**
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `workflows/README.md`

- [ ] **Step 1: Update the drafting guide**

Add a short subsection near "Derived manifests after deterministic gates":

```md
For queue drains, broad manifest construction should partition invalid rows instead of failing on the first bad row. The post-gate selection manifest is the downstream authority and should contain only valid selectable rows. Invalid rows belong in diagnostics. Once an item is selected, missing required artifacts should fail hard before execution.
```

- [ ] **Step 2: Update workflow README**

Add one sentence to the NeurIPS drain entry saying malformed non-selected active items are excluded with diagnostics and do not crash selection.

- [ ] **Step 3: Run doc diff check**

Run:

```bash
git diff -- docs/workflow_drafting_guide.md workflows/README.md
```

Expected: concise docs change, no workflow-internal jargon in user-facing prose.

## Task 7: Orchestration Repo Verification

**Files:**
- Test-only task

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest -q tests/test_neurips_backlog_roadmap_gate.py
```

Expected: PASS.

- [ ] **Step 2: Run adjacent recovery tests**

Run:

```bash
pytest -q tests/test_neurips_plan_gate_recovery.py
```

Expected: PASS.

- [ ] **Step 3: Run workflow dry-run or validation smoke**

Run the narrowest available orchestrator smoke from the repo root. Prefer:

```bash
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run
```

If this CLI form is unsupported, use the repo's nearest validation/report command and record the exact replacement.

Expected: workflow loads and validates without schema or path errors.

- [ ] **Step 4: Run compile check**

Run:

```bash
python -m compileall -q workflows/library/scripts
```

Expected: PASS.

- [ ] **Step 5: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

## Task 8: Propagate To PtychoPINN And Verify

**Files:**
- Copy changed files from `/home/ollie/Documents/agent-orchestration/` to `/home/ollie/Documents/PtychoPINN/` when matching paths exist.

- [ ] **Step 1: Inspect matching downstream files**

Run:

```bash
cd /home/ollie/Documents/PtychoPINN
for path in \
  workflows/library/scripts/build_neurips_backlog_manifest.py \
  workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py \
  workflows/library/scripts/validate_neurips_backlog_gap_draft.py \
  workflows/library/neurips_backlog_gap_drafter.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  tests/test_neurips_backlog_roadmap_gate.py
do
  test -e "$path" && echo "$path"
done
```

Expected: print all workflow component paths that PtychoPINN carries locally.

- [ ] **Step 2: Copy matching files**

From `/home/ollie/Documents/agent-orchestration`, copy only files that exist downstream:

```bash
for path in \
  workflows/library/scripts/build_neurips_backlog_manifest.py \
  workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py \
  workflows/library/scripts/validate_neurips_backlog_gap_draft.py \
  workflows/library/neurips_backlog_gap_drafter.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  tests/test_neurips_backlog_roadmap_gate.py
do
  if [ -e "/home/ollie/Documents/PtychoPINN/$path" ]; then
    cp "$path" "/home/ollie/Documents/PtychoPINN/$path"
  fi
done
```

If prompt files under `workflows/library/prompts/neurips_backlog_gap_drafter/` exist downstream, copy the changed prompt files too.

- [ ] **Step 3: Run PtychoPINN focused tests in `ptycho311`**

Run:

```bash
cd /home/ollie/Documents/PtychoPINN
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
pytest -q tests/test_neurips_backlog_roadmap_gate.py
python -m compileall -q workflows/library/scripts
git diff --check
```

Expected: PASS.

- [ ] **Step 4: Smoke the active failure case**

From `/home/ollie/Documents/PtychoPINN`, create or reuse a temporary active item with a missing `plan_path` only in a disposable test workspace, not in the live backlog. Run the manifest and gate scripts against that workspace and confirm:

- command exits `0`;
- output manifest has `invalid_items`;
- eligible manifest excludes the invalid item.

Do not mutate the live backlog for this smoke.

## Task 9: Commit

**Files:**
- All files changed above in agent-orchestration.
- Matching propagated files in PtychoPINN, if this task is executed in both repos.

- [ ] **Step 1: Review orchestration repo diff**

Run:

```bash
cd /home/ollie/Documents/agent-orchestration
git diff -- workflows/library/scripts/build_neurips_backlog_manifest.py workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py workflows/library/scripts/validate_neurips_backlog_gap_draft.py workflows/library/neurips_backlog_gap_drafter.yaml workflows/examples/neurips_steered_backlog_drain.yaml tests/test_neurips_backlog_roadmap_gate.py docs/workflow_drafting_guide.md workflows/README.md docs/plans/2026-05-04-neurips-backlog-invalid-item-tolerance-plan.md
```

- [ ] **Step 2: Stage only scoped orchestration files**

Run:

```bash
git add \
  workflows/library/scripts/build_neurips_backlog_manifest.py \
  workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py \
  workflows/library/scripts/validate_neurips_backlog_gap_draft.py \
  workflows/library/neurips_backlog_gap_drafter.yaml \
  workflows/examples/neurips_steered_backlog_drain.yaml \
  tests/test_neurips_backlog_roadmap_gate.py \
  docs/workflow_drafting_guide.md \
  workflows/README.md \
  docs/plans/2026-05-04-neurips-backlog-invalid-item-tolerance-plan.md
```

Add changed prompt files if the implementation touched them.

- [ ] **Step 3: Commit orchestration repo**

Run:

```bash
git commit -m "fix: tolerate invalid unselected NeurIPS backlog items"
```

- [ ] **Step 4: Commit PtychoPINN propagation if applicable**

In `/home/ollie/Documents/PtychoPINN`, stage only propagated workflow files and commit with:

```bash
git commit -m "fix: tolerate invalid unselected NeurIPS backlog items"
```

## Success Criteria

- A missing plan target in one active backlog item no longer crashes manifest building or roadmap reconciliation when another valid eligible item exists.
- Invalid active items are discoverable in manifest and gate diagnostics.
- If only current-gate work is invalid, the drain reports `BLOCKED` rather than `DONE` or `BACKLOG_GAP`.
- Selected items still fail before execution if required artifacts are missing.
- Gap drafting cannot leave a newly drafted item active unless its referenced plan exists and validates.
- Agent-orchestration and PtychoPINN workflow copies are consistent.
