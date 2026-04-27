# Roadmap Revision Soft Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make major-project roadmap escalation use the revised roadmap/manifest even when advisory roadmap-review findings remain, while keeping deterministic artifact/schema validation as the hard gate.

**Architecture:** Roadmap revision is the top authority in the major-project stack, so its review should record findings rather than block or churn. Replace the roadmap-revision review/revise loop with a single advisory review step, then always finalize the drafted roadmap/manifest if deterministic contracts validate. Update the drain promotion step to copy the finalized roadmap/manifest regardless of advisory review decision and continue draining from the updated manifest.

**Tech Stack:** YAML workflow DSL v2.12, Python orchestrator runtime, pytest workflow tests, existing major-project workflow library.

---

## Design

### Current Problem

`workflows/library/major_project_roadmap_revision_phase.yaml` currently treats roadmap revision like lower phases:

1. Draft roadmap revision.
2. Review in a `repeat_until` loop.
3. If review returns `REVISE`, run another roadmap revision provider pass.
4. If review returns `BLOCK`, stop the loop as a terminal decision.

Then `workflows/library/major_project_tranche_drain_iteration.yaml` promotes the revised roadmap only when the final roadmap-revision decision is `APPROVE`; `BLOCK` becomes `BLOCKED`, and `REVISE` is unsupported.

That is wrong for design-escalation recovery. The roadmap revision is the recovery artifact. If the top-authority reviewer has findings, the workflow should carry those findings forward and still use the revised roadmap unless the candidate is structurally invalid.

### Target Behavior

Roadmap escalation should behave as:

```text
Draft roadmap revision
Validate drafted roadmap/manifest through normal expected_outputs and manifest-selection checks
Review once
Finalize roadmap/manifest and review report
Promote finalized roadmap/manifest regardless of advisory decision
Continue drain from the promoted manifest
```

Hard failures remain appropriate only for deterministic failures:

- provider crash
- missing candidate files
- invalid relpaths
- malformed JSON
- manifest incompatible with the selector/update scripts
- output contract violation

Review decisions become advisory metadata:

- `APPROVE`: candidate is reviewed clean.
- `REVISE`: candidate is usable for recovery but has findings to carry forward.
- `BLOCK`: candidate is still promoted if deterministic validation passed, but the report records severe follow-up findings. If a candidate is truly unusable, deterministic validation should fail instead of relying on reviewer judgment.

### Boundaries

Do:

- Remove the roadmap-revision review/revise loop.
- Keep one roadmap-revision review provider step.
- Keep writing `roadmap_revision_decision.txt` and the JSON review report.
- Always finalize `updated_project_roadmap_path` and `updated_tranche_manifest_path` after successful review output.
- Always promote the finalized roadmap/manifest in drain escalation after successful roadmap revision phase completion.
- Preserve review findings as artifacts for humans and later workflow context.
- Add tests proving `REVISE` and `BLOCK` advisory decisions do not block promotion.

Do not:

- Weaken deterministic file/schema validation.
- Add a new escalation level above roadmap.
- Add another loop cap or `on_exhausted` path to roadmap revision.
- Hide review findings.
- Treat `DONE` as the drain status after roadmap revision; the drain should continue from the updated manifest.

---

## File Map

- Modify `workflows/library/major_project_roadmap_revision_phase.yaml`
  - Replace `RoadmapRevisionReviewLoop` with a single `ReviewRoadmapRevision` provider step.
  - Remove `RouteRoadmapRevisionDecision` and `ReviseRoadmapRevision` from the active workflow path.
  - Keep `FinalizeRoadmapRevisionOutputs`, reading the drafted candidate paths and the review output paths.

- Modify `workflows/library/major_project_tranche_drain_iteration.yaml`
  - Change `PromoteRoadmapRevision` so it copies finalized roadmap/manifest for any valid roadmap-revision decision.
  - Record the advisory decision and review report path into iteration state.
  - Always write `CONTINUE` after successful promotion.

- Modify `workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md`
  - State that this review is advisory for top-authority roadmap escalation.
  - Tell the reviewer to record findings but not to assume non-`APPROVE` prevents use of the candidate.
  - Keep the output contract unchanged.

- Modify `tests/test_major_project_workflows.py`
  - Add structure tests for no roadmap-revision review loop.
  - Add runtime tests for advisory `REVISE` and `BLOCK` promotion.
  - Update existing assertions that assume `RunRoadmapRevision` can only promote on `APPROVE`.

- Optionally modify `docs/workflow_drafting_guide.md`
  - Add a short top-authority pattern note: when no higher phase exists, use hard deterministic validation plus soft review metadata, not a review/revise escalation loop.

- Sync changed workflow and prompt files to `/home/ollie/Documents/EasySpin/` after local tests pass.

---

## Task 1: Make Roadmap Revision Review Single-Pass Advisory

**Files:**

- Modify: `workflows/library/major_project_roadmap_revision_phase.yaml`
- Test: `tests/test_major_project_workflows.py`

- [x] **Step 1: Add a structure test for single-pass review**

In `tests/test_major_project_workflows.py`, add or extend a test:

```python
def test_roadmap_revision_phase_uses_single_advisory_review():
    workflow = _load_yaml("workflows/library/major_project_roadmap_revision_phase.yaml")

    step_names = [step["name"] for step in workflow["steps"]]
    assert step_names == [
        "InitializeRoadmapRevisionPaths",
        "DraftRoadmapRevision",
        "ReviewRoadmapRevision",
        "FinalizeRoadmapRevisionOutputs",
    ]
    assert "repeat_until" not in _step_by_name(workflow, "ReviewRoadmapRevision")
```

Run:

```bash
pytest tests/test_major_project_workflows.py -k roadmap_revision_phase_uses_single_advisory_review -q
```

Expected: fail because the workflow still has `RoadmapRevisionReviewLoop`.

- [x] **Step 2: Rewrite the workflow shape**

In `workflows/library/major_project_roadmap_revision_phase.yaml`:

- Delete the `RoadmapRevisionReviewLoop` `repeat_until` step.
- Move the inner `ReviewRoadmapRevision` provider to a top-level step after `DraftRoadmapRevision`.
- Preserve its consumes, prompt consumes, expected outputs, and publishes.
- Do not include the `ReviseRoadmapRevision` provider in the active workflow path.
- Keep `roadmap_revision_decision` allowed values as `["APPROVE", "REVISE", "BLOCK"]`.

The step sequence should become:

```yaml
steps:
  - name: InitializeRoadmapRevisionPaths
    ...
  - name: DraftRoadmapRevision
    ...
  - name: ReviewRoadmapRevision
    id: review_roadmap_revision
    provider: codex
    asset_file: prompts/major_project_stack/review_project_roadmap_revision.md
    timeout_sec: 1800
    consumes:
      - artifact: project_brief
        policy: latest_successful
        freshness: any
      - artifact: roadmap_change_request
        policy: latest_successful
        freshness: any
      - artifact: updated_project_roadmap
        policy: latest_successful
        freshness: any
      - artifact: updated_tranche_manifest
        policy: latest_successful
        freshness: any
    prompt_consumes: ["project_brief", "roadmap_change_request", "updated_project_roadmap", "updated_tranche_manifest"]
    expected_outputs:
      - name: roadmap_revision_decision
        path: ${inputs.state_root}/roadmap_revision_decision.txt
        type: enum
        allowed: ["APPROVE", "REVISE", "BLOCK"]
      - name: roadmap_revision_report_path
        path: ${inputs.state_root}/roadmap_revision_report_path.txt
        type: relpath
        under: artifacts/review
        must_exist_target: true
    publishes:
      - artifact: roadmap_revision_decision
        from: roadmap_revision_decision
      - artifact: roadmap_revision_report
        from: roadmap_revision_report_path
  - name: FinalizeRoadmapRevisionOutputs
    ...
```

- [x] **Step 3: Run the structure test**

Run:

```bash
pytest tests/test_major_project_workflows.py -k roadmap_revision_phase_uses_single_advisory_review -q
```

Expected: pass.

---

## Task 2: Promote Roadmap Revisions Regardless Of Advisory Decision

**Files:**

- Modify: `workflows/library/major_project_tranche_drain_iteration.yaml`
- Test: `tests/test_major_project_workflows.py`

- [x] **Step 1: Add a structure test for advisory promotion**

Extend `test_drain_iteration_dispatches_roadmap_revision_at_top_level` or add:

```python
def test_drain_iteration_promotes_roadmap_revision_for_any_advisory_decision():
    workflow = _load_yaml("workflows/library/major_project_tranche_drain_iteration.yaml")
    outcome_router = _step_by_name(workflow, "RouteIterationOutcome")
    roadmap_case = outcome_router["match"]["cases"]["ESCALATE_ROADMAP_REVISION"]
    promote = next(step for step in roadmap_case["steps"] if step["name"] == "PromoteRoadmapRevision")
    script = "\n".join(promote["command"])

    assert 'printf \\'%s\\\\n\\' CONTINUE' in script
    assert 'if [ "$decision" = "APPROVE" ]' not in script
    assert "Unsupported roadmap revision decision" not in script
```

Run:

```bash
pytest tests/test_major_project_workflows.py -k drain_iteration_promotes_roadmap_revision_for_any_advisory_decision -q
```

Expected: fail because current promotion gates on `APPROVE`.

- [x] **Step 2: Rewrite `PromoteRoadmapRevision`**

In `workflows/library/major_project_tranche_drain_iteration.yaml`, replace the shell body of `PromoteRoadmapRevision` with deterministic promotion that always copies finalized candidates after the roadmap revision phase completed:

```bash
decision="$(cat "${inputs.roadmap_revision_state_root}/final_roadmap_revision_decision.txt")"
roadmap_candidate="$(cat "${inputs.roadmap_revision_state_root}/final_updated_project_roadmap_path.txt")"
manifest_candidate="$(cat "${inputs.roadmap_revision_state_root}/final_updated_tranche_manifest_path.txt")"
review_report="$(cat "${inputs.roadmap_revision_state_root}/final_roadmap_revision_report_path.txt")"

case "$decision" in
  APPROVE|REVISE|BLOCK) ;;
  *)
    echo "Unsupported roadmap revision decision: $decision" >&2
    exit 1
    ;;
esac

mkdir -p "${inputs.iteration_state_root}"
cp "$roadmap_candidate" "${inputs.project_roadmap_path}"
cp "$manifest_candidate" "${inputs.tranche_manifest_path}"
printf '%s\n' "$decision" > "${inputs.iteration_state_root}/roadmap_revision_decision.txt"
printf '%s\n' "$review_report" > "${inputs.iteration_state_root}/roadmap_revision_report_path.txt"
printf '%s\n' CONTINUE > "${inputs.iteration_state_root}/roadmap_revision_drain_status.txt"
```

Add expected outputs for the advisory metadata:

```yaml
- name: roadmap_revision_decision
  path: ${inputs.iteration_state_root}/roadmap_revision_decision.txt
  type: enum
  allowed: ["APPROVE", "REVISE", "BLOCK"]
- name: roadmap_revision_report_path
  path: ${inputs.iteration_state_root}/roadmap_revision_report_path.txt
  type: relpath
  under: artifacts/review
  must_exist_target: true
```

Keep `drain_status` allowed values unchanged as `["CONTINUE", "BLOCKED"]` for this step if no other branch needs a new status. The promoted-review path should always emit `CONTINUE` after deterministic promotion succeeds.

- [x] **Step 3: Run the structure test**

Run:

```bash
pytest tests/test_major_project_workflows.py -k drain_iteration_promotes_roadmap_revision_for_any_advisory_decision -q
```

Expected: pass.

---

## Task 3: Add Runtime Coverage For Advisory `REVISE`

**Files:**

- Modify: `tests/test_major_project_workflows.py`

- [x] **Step 1: Add a mocked runtime test**

Add a test that runs `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml` with mocked providers and forces this path:

1. selector chooses a tranche
2. tranche stack outputs `ESCALATE_ROADMAP_REVISION`
3. roadmap revision draft writes changed roadmap/manifest candidates
4. roadmap revision review writes decision `REVISE`
5. drain promotes candidate roadmap/manifest and outputs `CONTINUE`

If using the existing helper stack is too large, add a focused call-workflow test around `major_project_tranche_drain_iteration.yaml` with a stubbed `tranche_stack` and real `roadmap_revision_phase` copied into a temp workspace.

Assertions:

```python
assert state["status"] == "completed"
assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
assert (tmp_path / "state/.../roadmap_revision_decision.txt").read_text().strip() == "REVISE"
assert json.loads((tmp_path / "state/.../tranche_manifest.json").read_text()) == expected_candidate_manifest
assert (tmp_path / "docs/plans/.../project-roadmap.md").read_text() == expected_candidate_roadmap
```

- [x] **Step 2: Run the new test and verify it fails before Task 2**

Run:

```bash
pytest tests/test_major_project_workflows.py -k roadmap_revision_revise_promotes_candidate -q
```

Expected before implementation: fail because `REVISE` is unsupported or not promoted.

- [x] **Step 3: Run the test after Task 2**

Run:

```bash
pytest tests/test_major_project_workflows.py -k roadmap_revision_revise_promotes_candidate -q
```

Expected after implementation: pass.

---

## Task 4: Add Runtime Coverage For Advisory `BLOCK`

**Files:**

- Modify: `tests/test_major_project_workflows.py`

- [x] **Step 1: Add `BLOCK` variant**

Duplicate the advisory `REVISE` runtime test setup, but have `ReviewRoadmapRevision` write:

```text
BLOCK
```

The review report should contain severe findings, but the candidate roadmap/manifest should still be promoted because deterministic validation passed.

Assertions:

```python
assert state["status"] == "completed"
assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
assert roadmap_revision_decision == "BLOCK"
assert promoted_manifest == candidate_manifest
```

- [x] **Step 2: Run the test**

Run:

```bash
pytest tests/test_major_project_workflows.py -k roadmap_revision_block_promotes_candidate -q
```

Expected: pass after Task 2.

---

## Task 5: Clarify The Review Prompt

**Files:**

- Modify: `workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md`

- [x] **Step 1: Edit prompt language**

Add a concise top-authority note near the top:

```md
This is an advisory review for a top-authority roadmap revision. Write findings and the decision token, but do not assume a non-`APPROVE` decision prevents the revised roadmap or manifest from being used. Deterministic workflow validation, not this review decision, is the hard gate for whether the candidate can be promoted.
```

Keep the existing output contract and JSON report requirements.

- [x] **Step 2: Check prompt does not leak workflow mechanics excessively**

Run:

```bash
rg -n "loop|repeat_until|cap|crash|workflow owns" workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md
```

Expected: no loop/cap/runtime language introduced.

---

## Task 6: Document The Top-Authority Pattern

**Files:**

- Modify: `docs/workflow_drafting_guide.md`

- [x] **Step 1: Add a short authoring note**

Under the review/fix loop guidance, add:

```md
For a top-authority revision phase with no higher escalation target, prefer deterministic validation plus one advisory review over a review/revise loop. If the candidate is structurally valid, carry review findings forward as metadata and let the workflow continue from the revised artifact. Reserve hard failure for invalid artifacts or runtime errors.
```

- [x] **Step 2: Run a docs-adjacent check**

Run:

```bash
pytest tests/test_major_project_workflows.py -k "roadmap_revision or drain_iteration_dispatches" -q
```

Expected: pass.

---

## Task 7: Validate Workflows And Sync EasySpin

**Files:**

- Sync to `/home/ollie/Documents/EasySpin/`:
  - `workflows/library/major_project_roadmap_revision_phase.yaml`
  - `workflows/library/major_project_tranche_drain_iteration.yaml`
  - `workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md`

- [x] **Step 1: Run local workflow validation**

Run:

```bash
python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run \
  --input project_brief_path=workflows/examples/inputs/major_project_brief.md \
  --input project_roadmap_path=docs/plans/major-project-demo/project-roadmap.md \
  --input tranche_manifest_target_path=state/major-project-demo/tranche_manifest.json \
  --input drain_state_root=state/major-project-demo/dry-run-roadmap-soft-review \
  --input drain_summary_target_path=artifacts/work/major-project-demo/dry-run-roadmap-soft-review-summary.json
```

Expected: `[DRY RUN] Workflow validation successful`.

- [x] **Step 2: Sync EasySpin files**

Run:

```bash
install -D -m 0644 workflows/library/major_project_roadmap_revision_phase.yaml /home/ollie/Documents/EasySpin/workflows/library/major_project_roadmap_revision_phase.yaml
install -D -m 0644 workflows/library/major_project_tranche_drain_iteration.yaml /home/ollie/Documents/EasySpin/workflows/library/major_project_tranche_drain_iteration.yaml
install -D -m 0644 workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md /home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md
```

- [x] **Step 3: Run EasySpin dry-run under `ptycho311`**

Run:

```bash
cd /home/ollie/Documents/EasySpin
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run \
  --input project_brief_path=docs/backlog/pytorch-port.md \
  --input project_roadmap_path=docs/plans/pytorch-port-roadmap.md \
  --input tranche_manifest_target_path=state/easyspin-pytorch-port/roadmap/tranche_manifest.json \
  --input drain_state_root=state/easyspin-pytorch-port/dry-run-roadmap-soft-review \
  --input drain_summary_target_path=artifacts/work/easyspin-pytorch-port/dry-run-roadmap-soft-review-summary.json
```

Expected: `[DRY RUN] Workflow validation successful`.

---

## Task 8: Final Verification And Commit

- [x] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -k "roadmap_revision or drain_iteration_dispatches" -q
```

Expected: pass.

- [x] **Step 2: Run broader workflow tests**

Run:

```bash
pytest tests/test_major_project_workflows.py tests/test_workflow_examples_v0.py -q
```

Expected: pass.

- [x] **Step 3: Check diffs**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files staged.

- [x] **Step 4: Commit**

Stage only intended local files:

```bash
git add \
  docs/plans/2026-04-27-roadmap-revision-soft-review-implementation-plan.md \
  docs/workflow_drafting_guide.md \
  tests/test_major_project_workflows.py \
  workflows/library/major_project_roadmap_revision_phase.yaml \
  workflows/library/major_project_tranche_drain_iteration.yaml \
  workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md
git commit -m "Make roadmap revision review advisory"
```

Do not stage unrelated EasySpin generated artifacts or pre-existing dirty files.

---

## Acceptance Criteria

- Roadmap revision no longer has a review/revise loop.
- Roadmap revision review runs once and writes decision/findings.
- `APPROVE`, `REVISE`, and `BLOCK` review decisions all allow deterministic finalization.
- Drain escalation promotes the finalized roadmap and manifest for all valid advisory review decisions.
- Drain status is `CONTINUE` after successful roadmap promotion.
- Invalid roadmap/manifest artifacts still fail through deterministic validation.
- Review findings remain available through the roadmap revision report and iteration state.
- Local and EasySpin dry-runs validate.
