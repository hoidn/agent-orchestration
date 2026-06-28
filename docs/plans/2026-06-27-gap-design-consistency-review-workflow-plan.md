# Gap Design Consistency Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight bounded review/revision gate so drafted design-gap architectures are checked for consistency with the target design before they become executable work items.

**Architecture:** The design-gap architect workflows should draft an `implementation_architecture.md`, run a provider review that asks one plain question, revise on `REVISE` with the review report, and validate only approved drafts. Review/revision is bounded so bad gap designs cannot loop forever or become executable work items by default. The review must stay generic: it reviews consistency with the governing design, not project-specific field names or one-off failure modes.

**Tech Stack:** Agent-orchestration YAML v2.14, provider prompts, `output_bundle`, existing `validate_lisp_frontend_design_gap_architecture.py`, pytest workflow-shape tests, orchestrator dry-run validation.

---

## File Structure

- Modify `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
  - Add a bounded review/revision loop between draft and validation.
  - Gate validation on review approval.
- Modify `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
  - Add the same generic review/revision loop to the non-design-delta architect.
- Create `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md`
  - Target/baseline wording.
- Create `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture_for_review.md`
  - Target/baseline revision wording.
- Create `workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md`
  - Full-design/MVP wording.
  - Reuse or update the existing generic revision prompt if it already covers review findings.
- Modify `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py`
  - Accept an optional review bundle path.
  - Return `INVALID` or `BLOCKED` before work-item bundle creation when the bounded loop does not approve.
- Modify `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Add workflow-shape and validation tests for the new gate.

## Review Contract

Use this core question in both review prompts:

```text
Review whether the gap design is consistent with the target design.
Reject it if it changes, weakens, bypasses, or leaves ambiguous any
target-design requirement that the implementation could affect.
```

The prompt may explain that “target design” means `target_design_path` for the design-delta workflow and `full_design_path` for the generic workflow. Do not add examples tied to `item-state-root`, Design Delta, WCC, bridges, or any current failure.

The provider output bundle should be:

```json
{
  "review_decision": "APPROVE | REVISE | BLOCKED",
  "reason": "short reason"
}
```

Decision meanings:

- `APPROVE`: proceed to structural validation and work-item bundle creation.
- `REVISE`: the gap design is inconsistent or underspecified relative to the target design; run a bounded revision step and review again.
- `BLOCKED`: the selected gap cannot be safely architected without a missing prerequisite or user decision; do not create a work item.

If review/revision exhausts without approval, the architect workflow should
emit `architecture_validation_status=INVALID` with no `work_item_bundle_path`.

## Task 1: Add Tests For The Review Gate

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add workflow-shape tests**

Add tests asserting both architect workflows contain this sequence:

```text
DraftDesignGapArchitecture
ReviewDesignGapArchitecture
ReviseDesignGapArchitecture
ValidateDesignGapArchitecture
```

Also assert:

- review and revision are inside a bounded `repeat_until` loop;
- the loop condition is review approval;
- exhausted review/revision returns an invalid architecture status or otherwise prevents work-item bundle creation;
- the review step is a provider step;
- consumes or depends on the drafted architecture file;
- writes a review bundle under `state`;
- exposes a `review_decision` enum with `APPROVE`, `REVISE`, and `BLOCKED`;
- the revision step consumes the review report/bundle and the drafted architecture;
- validation receives the review bundle path.

- [ ] **Step 2: Add validator tests**

Add focused tests for `validate_lisp_frontend_design_gap_architecture.py`:

- review bundle `APPROVE` plus valid draft returns `architecture_validation_status=VALID`;
- final review bundle `REVISE` after exhausted review/revision returns `architecture_validation_status=INVALID` and does not emit `work_item_bundle_path`;
- review bundle `BLOCKED` returns `architecture_validation_status=BLOCKED` and does not emit `work_item_bundle_path`;
- missing or malformed review bundle returns `INVALID`.

Use temp files under `tmp_path`; do not assert literal prompt wording.

- [ ] **Step 3: Run the new tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_gap_architect and review" -q
```

Expected: failures showing the review step and validator behavior are missing.

## Task 2: Add Generic Review And Revision Prompts

**Files:**

- Create: `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md`
- Create: `workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture_for_review.md`
- Create: `workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md`
- Modify or reuse: `workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md`

- [ ] **Step 1: Write the design-delta review prompt**

The prompt must instruct the reviewer to read the consumed/required files and answer only whether the gap design is consistent with the target design. Include the output bundle shape exactly as above.

Use this required core text:

```text
Review whether the gap design is consistent with the target design.
Reject it if it changes, weakens, bypasses, or leaves ambiguous any
target-design requirement that the implementation could affect.
```

- [ ] **Step 2: Write the generic review prompt**

Use the same contract, replacing “target design” context with the workflow’s `full_design_path` and treating the MVP design as compatibility context.

- [ ] **Step 3: Write or update revision prompts**

The revision prompt must instruct the reviser to update only the current
`implementation_architecture.md`, work-item context, check commands, and draft
bundle as needed to address the review findings. It must not edit source code,
run state, backlog queues, or unrelated docs.

It should preserve the same output bundle shape as the draft step:

```json
{
  "draft_status": "DRAFTED",
  "design_gap_id": "<same id>",
  "architecture_path": "<same architecture path>",
  "work_item_context_path": "<same context path>",
  "check_commands_path": "<same check commands path>",
  "plan_target_path": "<same plan target path>",
  "summary": "short summary"
}
```

If the review identifies a real prerequisite or impossible target-design
conflict, the revision prompt may emit:

```json
{
  "draft_status": "BLOCKED",
  "reason": "short reason"
}
```

- [ ] **Step 4: Review prompt scope**

Check manually that neither prompt names current project-specific failure details. Run:

```bash
rg -n "item-state-root|Design Delta|WCC|bridge|compatibility|state-root" \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture_for_review.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md
```

Expected: no matches except `Design Delta` only if it appears in a path or workflow-family heading already required by the file location; prefer no matches.

## Task 3: Wire The Bounded Review Loop Into Architect Workflows

**Files:**

- Modify: `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- Modify: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`

- [ ] **Step 1: Add `DesignGapArchitectureReviewLoop` to the design-delta architect**

Place it after `DraftDesignGapArchitecture` and before `ValidateDesignGapArchitecture`.

The loop should have `max_iterations: 3`, output `review_decision`, and stop
when `review_decision == APPROVE`.

Inside the loop, add `ReviewDesignGapArchitecture` using the same provider
routing as the draft step. The step should read:

- steering;
- target design;
- baseline design;
- command-adapter contract;
- selection bundle;
- architecture targets;
- existing architecture index;
- drafted `implementation_architecture.md`.

It should write:

```yaml
output_bundle:
  path: ${inputs.state_root}/architecture-review.json
  fields:
    - name: review_decision
      json_pointer: /review_decision
      type: enum
      allowed: ["APPROVE", "REVISE", "BLOCKED"]
    - name: reason
      json_pointer: /reason
      type: string
      required: false
```

Add a `match` or equivalent route on `review_decision`:

- `APPROVE`: set loop output to `APPROVE`.
- `REVISE`: run `ReviseDesignGapArchitecture`, then set loop output to `REVISE`.
- `BLOCKED`: set loop output to `BLOCKED`; the loop will not approve.

The revision step should consume the drafted architecture, review bundle, and
the same authoritative context as the draft step. It should write the same
draft bundle path as `DraftDesignGapArchitecture`.

- [ ] **Step 2: Pass the final review bundle to validation**

Modify `ValidateDesignGapArchitecture` to pass:

```yaml
--review-bundle-path
${inputs.state_root}/architecture-review.json
```

- [ ] **Step 3: Repeat for the generic architect**

Add the same bounded loop and validation argument to `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`, using `full_design_path` / `mvp_design_path` names.

## Task 4: Enforce Review Outcome In The Validator

**Files:**

- Modify: `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py`

- [ ] **Step 1: Add CLI argument**

Add:

```python
parser.add_argument("--review-bundle-path")
```

- [ ] **Step 2: Validate final review decision before draft validation**

If `--review-bundle-path` is present:

```python
review_path = REPO_ROOT / _safe_relpath(args.review_bundle_path, under="state", must_exist=True)
review = _load_json(review_path)
decision = str(review.get("review_decision") or "").strip()
if decision == "REVISE":
    _write_json(output_path, {
        "architecture_validation_status": "INVALID",
        "reason": str(review.get("reason") or "Design-gap architecture review requested revision."),
    })
    return 0
if decision == "BLOCKED":
    _write_json(output_path, {
        "architecture_validation_status": "BLOCKED",
        "reason": str(review.get("reason") or "Design-gap architecture review reported a blocker."),
    })
    return 0
if decision != "APPROVE":
    return _invalid(f"Unsupported review_decision: {decision!r}", output_path=output_path)
```

This must run before writing any `work_item_bundle_path`.

- [ ] **Step 3: Keep old behavior when no review bundle is supplied**

Existing callers that do not pass `--review-bundle-path` should keep their current behavior.

- [ ] **Step 4: Handle exhausted loops explicitly if available**

If the workflow loop can emit a distinct exhausted marker, pass it through as
`REVISE` or add a small command step after the loop that writes a final review
bundle:

```json
{
  "review_decision": "REVISE",
  "reason": "Design-gap architecture review did not approve within the bounded revision loop."
}
```

Do not allow exhaustion to fall through to structural validation as approval.

## Task 5: Verify Workflow Validation And Runtime Shape

**Files:**

- Modified workflows and tests from prior tasks.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "design_gap_architect and review" -q
```

Expected: pass.

- [ ] **Step 2: Run workflow dry-runs**

Run:

```bash
python -m orchestrator run workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml \
  --dry-run \
  --input state_root=state/tmp-gap-review-dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json \
  --input selection_bundle_path=state/tmp-gap-review-dry-run/selection.json
```

If dry-run requires an existing selection file, create a minimal temporary selection bundle under `state/tmp-gap-review-dry-run/selection.json` before running, and remove it afterward.

Run the analogous dry-run for `workflows/library/lisp_frontend_design_gap_architect.v214.yaml` with its `full_design_path` and `mvp_design_path` inputs.

- [ ] **Step 3: Run syntax and diff checks**

Run:

```bash
python -m json.tool state/tmp-gap-review-dry-run/selection.json >/dev/null || true
git diff --check -- \
  workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml \
  workflows/library/lisp_frontend_design_gap_architect.v214.yaml \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture_for_review.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md \
  workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

Expected: no whitespace errors.

## Task 6: Commit

**Files:**

- All files changed by this plan only.

- [ ] **Step 1: Inspect status**

Run:

```bash
git status --short
git diff --stat -- \
  workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml \
  workflows/library/lisp_frontend_design_gap_architect.v214.yaml \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture_for_review.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md \
  workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py
```

- [ ] **Step 2: Commit only scoped files**

Run:

```bash
git add \
  workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml \
  workflows/library/lisp_frontend_design_gap_architect.v214.yaml \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/revise_implementation_architecture_for_review.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md \
  workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md \
  workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py

git commit -m "Add design-gap consistency review gate" \
  -m "Review drafted gap architectures against the governing target design before producing executable work-item bundles."
```

Do not stage active drain implementation changes or generated run artifacts.
