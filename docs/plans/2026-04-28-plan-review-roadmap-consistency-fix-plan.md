# Plan Review Roadmap Consistency Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make major-project plan review enforce roadmap-authoritative tranche scope before implementation starts.

**Architecture:** Keep deterministic dataflow in workflow YAML and local judgment in the plan-review prompt. The plan phase will publish and inject the full project roadmap and tranche manifest alongside the existing scope boundary, and the review prompt will treat those artifacts as authority for rejecting underscoped, unauthorized, or non-executable plans.

**Tech Stack:** Agent-orchestration workflow YAML v2.12, Codex provider prompts, pytest workflow tests, orchestrator dry-run validation.

---

## Context

The implementation-review phase already consumes `scope_boundary`, `project_roadmap`, and `tranche_manifest` and uses them to reject local scope narrowing. The plan-review phase currently consumes `design`, `scope_boundary`, `plan`, `open_findings`, and `upstream_escalation_context`, but not the full roadmap or manifest. That leaves plan review dependent on the derived `scope_boundary` alone when deciding whether a plan preserves roadmap-level authority.

The fix is not to make the prompt longer for its own sake. The fix is to make the authoritative inputs available at plan review and then tighten the approval bar so a plan cannot be approved if it narrows, splits, defers, or recharters selected-tranche scope without roadmap/design authority.

Do not add tests that assert literal prompt text. Use workflow artifact/dataflow tests and behavioral mock-provider tests.

## File Structure

- Modify: `workflows/library/major_project_tranche_plan_phase.yaml`
  - Add `project_roadmap_path` and `tranche_manifest_path` inputs.
  - Add `project_roadmap` and `tranche_manifest` artifacts.
  - Publish both paths during phase input publication.
  - Inject both into `ReviewPlanTracked`.
  - Prefer injecting both into `DraftPlan` and `RevisePlanTracked` as context, but keep implementation limited to planning authority; drafting and revision may use them only to resolve scope-boundary/roadmap conflicts.
- Modify: `workflows/library/prompts/major_project_stack/review_plan.md`
  - Tell the reviewer to read `project_roadmap` and `tranche_manifest`.
  - Require roadmap-consistency review before approval.
  - Make `current scope`, `first pass`, blocked-state inventory, and deferred-slice language non-approvable unless the authoritative roadmap/manifest/scope boundary supports it.
  - Use existing decisions: `REVISE` for locally fixable plan omissions, `ESCALATE_REDESIGN` when design cannot support an executable full-scope plan, and `BLOCK` for missing or contradictory authority. Do not add `ESCALATE_ROADMAP_REVISION` to plan phase in this task unless a separate routing design is approved.
- Modify: `workflows/library/prompts/major_project_stack/draft_plan.md`
  - Read the same roadmap/manifest artifacts so draft plans can avoid scope drift up front.
- Modify: `workflows/library/prompts/major_project_stack/revise_plan.md`
  - Read the same roadmap/manifest artifacts so revisions do not fix findings by silently narrowing scope.
- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
  - Pass `project_roadmap_path` and `tranche_manifest_path` into the plan phase call.
- Modify if present and calling the plan phase directly: `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
  - Keep call-site inputs aligned with the library stack.
- Modify tests: `tests/test_major_project_workflows.py`
  - Add workflow interface/dataflow assertions for plan phase roadmap and manifest consumption.
  - Add a mock-provider route test proving an underscoped plan review decision does not approve.
  - Add a mock-provider route test proving `ESCALATE_REDESIGN` remains the plan-phase route when the selected-tranche boundary cannot be planned from the approved design.
- Update docs if needed: `prompts/README.md`
  - Only update if the prompt catalog description becomes stale.

## Task 1: Add Plan-Phase Roadmap And Manifest Inputs

**Files:**
- Modify: `workflows/library/major_project_tranche_plan_phase.yaml`
- Test: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add failing interface assertions**

Add or extend a test in `tests/test_major_project_workflows.py` that loads `workflows/library/major_project_tranche_plan_phase.yaml` and asserts:

```python
def test_major_project_plan_phase_consumes_roadmap_authority():
    workflow = _load_workflow("workflows/library/major_project_tranche_plan_phase.yaml")
    assert "project_roadmap_path" in workflow["inputs"]
    assert "tranche_manifest_path" in workflow["inputs"]
    assert "project_roadmap" in workflow["artifacts"]
    assert "tranche_manifest" in workflow["artifacts"]
    review = _find_step(workflow, "ReviewPlanTracked")
    assert "project_roadmap" in review["prompt_consumes"]
    assert "tranche_manifest" in review["prompt_consumes"]
```

Use existing test helpers in the file instead of inventing a second YAML loader.

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "plan_phase_consumes_roadmap_authority"
```

Expected: FAIL because the plan phase does not yet define or inject those artifacts.

- [ ] **Step 3: Add plan-phase inputs and artifacts**

In `workflows/library/major_project_tranche_plan_phase.yaml`, add inputs:

```yaml
  project_roadmap_path:
    type: relpath
    under: docs/plans
    must_exist_target: true
  tranche_manifest_path:
    type: relpath
    under: state
    must_exist_target: true
```

Add artifacts:

```yaml
  project_roadmap:
    pointer: ${inputs.state_root}/project_roadmap_path.txt
    type: relpath
    under: docs/plans
    must_exist_target: true
  tranche_manifest:
    pointer: ${inputs.state_root}/tranche_manifest_path.txt
    type: relpath
    under: state
    must_exist_target: true
```

- [ ] **Step 4: Publish the new inputs**

Rename `PublishDesignInput` to `PublishPlanPhaseInputs` only if doing so does not churn tests unnecessarily. Add:

```bash
printf '%s\n' "${inputs.project_roadmap_path}" > "${inputs.state_root}/project_roadmap_path.txt"
printf '%s\n' "${inputs.tranche_manifest_path}" > "${inputs.state_root}/tranche_manifest_path.txt"
```

Add corresponding `expected_outputs` and `publishes` entries for `project_roadmap` and `tranche_manifest`.

- [ ] **Step 5: Inject authority artifacts into plan providers**

For `DraftPlan`, add both artifacts to `consumes` and `prompt_consumes`.

For `ReviewPlanTracked`, add both artifacts to `consumes` and `prompt_consumes`.

For `RevisePlanTracked`, add both artifacts to `consumes` and `prompt_consumes`.

Keep the prompt consumption order readable:

```yaml
prompt_consumes:
  ["design", "scope_boundary", "project_roadmap", "tranche_manifest", "plan", "open_findings", "upstream_escalation_context"]
```

Use the equivalent existing single-line style if the file uses that style locally.

- [ ] **Step 6: Run the interface test**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "plan_phase_consumes_roadmap_authority"
```

Expected: PASS.

## Task 2: Wire Plan-Phase Call Sites

**Files:**
- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
- Modify if needed: `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
- Test: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add failing call-site test**

Add or extend a test that loads the major-project tranche stack and asserts the plan phase call receives:

```yaml
project_roadmap_path:
  ref: inputs.project_roadmap_path
tranche_manifest_path:
  ref: inputs.tranche_manifest_path
```

If the stack forwards these through a route or current visit output, assert the actual local pattern. The important contract is that plan review receives the same authoritative roadmap and manifest selected for the tranche.

- [ ] **Step 2: Run the failing call-site test**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "plan_phase_call"
```

Expected: FAIL if the plan-phase call does not pass the new inputs.

- [ ] **Step 3: Update the library stack call**

In the plan-phase call inputs, add:

```yaml
project_roadmap_path:
  ref: inputs.project_roadmap_path
tranche_manifest_path:
  ref: inputs.tranche_manifest_path
```

If the stack’s inputs already expose these names, do not add duplicate inputs.

- [ ] **Step 4: Update example wrappers if they call the plan phase directly**

Search:

```bash
rg -n "major_project_tranche_plan_phase|plan_phase:" workflows
```

For each direct call to the major-project plan phase, pass the two new inputs from the same authority source already used by design and implementation phases.

- [ ] **Step 5: Run call-site tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "plan_phase_call or plan_phase_consumes_roadmap_authority"
```

Expected: PASS.

## Task 3: Tighten Plan Draft/Review/Revision Prompts

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/draft_plan.md`
- Modify: `workflows/library/prompts/major_project_stack/review_plan.md`
- Modify: `workflows/library/prompts/major_project_stack/revise_plan.md`
- Optional modify: `prompts/README.md`

- [ ] **Step 1: Update plan-review prompt authority line**

In `review_plan.md`, change the required read line from:

```text
Read the consumed `design`, `scope_boundary`, `plan`, and `open_findings` artifacts before acting.
```

to include:

```text
Read the consumed `design`, `scope_boundary`, `project_roadmap`, `tranche_manifest`, `plan`, and `open_findings` artifacts before acting.
```

- [ ] **Step 2: Add the roadmap-consistency approval bar**

Add a concise paragraph near the existing scope-accountability paragraph:

```text
Use the consumed `project_roadmap` and `tranche_manifest` to verify that the selected-tranche scope, prerequisites, completion gate, planned deliverables, and any claimed deferrals match roadmap-level authority. `scope_boundary` is the selected-tranche handoff, but the roadmap and manifest are the cross-check for stale, incomplete, or misleading boundary data.
```

Add:

```text
Do not approve a plan that uses "current scope", "first pass", "blocked-state inventory", "follow-up", or equivalent language to redefine the selected tranche's completion boundary. Such language is acceptable only as implementation sequencing inside the full boundary, or when the roadmap/manifest/scope boundary explicitly authorizes the deferral with rationale and handoff criteria.
```

Keep wording generic; do not mention EasySpin, T26, T26A, or T27.

- [ ] **Step 3: Keep decision routing within existing plan-phase vocabulary**

Add:

```text
Use `REVISE` when the plan can be repaired locally to cover the roadmap-authoritative boundary. Use `ESCALATE_REDESIGN` when the consumed design cannot support an executable full-boundary plan or when the only plausible repair is a design-level change. Use `BLOCK` for missing or contradictory authority that cannot be safely resolved by redesign from the available artifacts.
```

Do not add `ESCALATE_ROADMAP_REVISION` to plan review in this task. Design review already owns the upward roadmap-revision route, and adding a new plan-phase route is a separate routing change.

- [ ] **Step 4: Update draft-plan and revise-plan read lines**

In `draft_plan.md` and `revise_plan.md`, require reading `project_roadmap` and `tranche_manifest` in addition to `design` and `scope_boundary`.

Add a short instruction:

```text
Use `project_roadmap` and `tranche_manifest` only to cross-check selected-tranche scope, prerequisites, completion gate, and authorized deferrals. Do not mine unrelated roadmap tranches as extra implementation scope.
```

- [ ] **Step 5: Check prompt catalog**

Run:

```bash
rg -n "review_plan.md|major_project_stack" prompts/README.md docs/workflow_prompt_map.md
```

If descriptions now misstate consumed context, update `prompts/README.md`. Do not regenerate broad prompt maps unless the repo’s existing workflow requires it for this kind of prompt input change.

## Task 4: Add Behavioral Review-Route Coverage

**Files:**
- Modify: `tests/test_major_project_workflows.py`
- Test fixtures: use existing temporary workflow/mock-provider helpers in the same test module.

- [ ] **Step 1: Add underscoped-plan mock-provider test**

Add a test that runs the major-project plan phase or a minimal stack fixture with mock provider outputs:

- Draft provider writes a plan whose text claims only a “first pass” or “inventory-only” slice.
- Review provider writes `REVISE` and a JSON report with one high finding for unauthorized scope narrowing.
- The test asserts the phase output decision is `REVISE`, not `APPROVE`.

Use mock-provider wiring rather than asserting prompt text.

- [ ] **Step 2: Add design-insufficient escalation test**

Add a second mock-provider test:

- Draft provider writes a plan that says the design cannot support the selected tranche boundary.
- Review provider writes `ESCALATE_REDESIGN` and active `plan_escalation_context.json`.
- The test asserts the phase output decision is `ESCALATE_REDESIGN` and the context is published.

- [ ] **Step 3: Run targeted tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "plan_phase"
```

Expected: PASS.

## Task 5: Validate Workflow And Smoke The Major-Project Path

**Files:**
- No source changes unless validation exposes a missing call-site.

- [ ] **Step 1: Run focused workflow tests**

Run:

```bash
pytest tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py -q
```

Expected: PASS.

- [ ] **Step 2: Run an orchestrator dry-run**

Run from repo root:

```bash
python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run \
  --input project_brief_path=workflows/examples/inputs/major_project_brief.md \
  --input project_roadmap_path=docs/plans/major-project-demo/project-roadmap.md \
  --input tranche_manifest_target_path=state/major-project-demo/tranche_manifest.json \
  --input drain_state_root=state/major-project-demo/tranche-drain \
  --input drain_summary_target_path=artifacts/work/major-project-demo/tranche-drain-summary.json
```

Expected: dry-run validation succeeds.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

## Task 6: Sync Downstream EasySpin Copy

**Files:**
- Modify in `/home/ollie/Documents/EasySpin`:
  - `workflows/library/major_project_tranche_plan_phase.yaml`
  - `workflows/library/prompts/major_project_stack/draft_plan.md`
  - `workflows/library/prompts/major_project_stack/review_plan.md`
  - `workflows/library/prompts/major_project_stack/revise_plan.md`
  - any stack/example workflow changed in the canonical repo

- [ ] **Step 1: Copy canonical changed workflow/prompt files to EasySpin**

Use normal file-copy commands from canonical to EasySpin after the canonical tests pass. Do not copy unrelated dirty files.

- [ ] **Step 2: Verify sync**

Run:

```bash
cmp -s workflows/library/major_project_tranche_plan_phase.yaml /home/ollie/Documents/EasySpin/workflows/library/major_project_tranche_plan_phase.yaml
cmp -s workflows/library/prompts/major_project_stack/review_plan.md /home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/review_plan.md
cmp -s workflows/library/prompts/major_project_stack/draft_plan.md /home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/draft_plan.md
cmp -s workflows/library/prompts/major_project_stack/revise_plan.md /home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/revise_plan.md
```

Expected: each command exits `0`.

- [ ] **Step 3: Run EasySpin dry-run in ptycho311**

Run:

```bash
cd /home/ollie/Documents/EasySpin
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run \
  --input project_brief_path=docs/backlog/pytorch-port.md \
  --input project_roadmap_path=docs/plans/pytorch-port-roadmap.md \
  --input tranche_manifest_target_path=state/easyspin-pytorch-port/roadmap/tranche_manifest.json \
  --input drain_state_root=state/easyspin-pytorch-port/tranche-drain-plan-review-scope-smoke \
  --input drain_summary_target_path=artifacts/work/pytorch-port-roadmap/plan-review-scope-smoke.json
```

Expected: dry-run validation succeeds.

## Commit Plan

- Commit canonical repo changes first:

```bash
git add workflows/library/major_project_tranche_plan_phase.yaml \
  workflows/library/major_project_tranche_design_plan_impl_stack_v2_call.yaml \
  workflows/library/prompts/major_project_stack/draft_plan.md \
  workflows/library/prompts/major_project_stack/review_plan.md \
  workflows/library/prompts/major_project_stack/revise_plan.md \
  tests/test_major_project_workflows.py \
  docs/plans/2026-04-28-plan-review-roadmap-consistency-fix-plan.md
git commit -m "enforce roadmap authority in plan review"
```

- Commit EasySpin sync separately from `/home/ollie/Documents/EasySpin`:

```bash
git add workflows/library/major_project_tranche_plan_phase.yaml \
  workflows/library/major_project_tranche_design_plan_impl_stack_v2_call.yaml \
  workflows/library/prompts/major_project_stack/draft_plan.md \
  workflows/library/prompts/major_project_stack/review_plan.md \
  workflows/library/prompts/major_project_stack/revise_plan.md
git commit -m "sync plan review roadmap authority"
```

Only stage files actually changed by the implementation. Leave unrelated dirty files alone.

## Acceptance Criteria

- Major-project plan review consumes `project_roadmap`, `tranche_manifest`, and `scope_boundary`.
- Major-project plan drafting and revision can see the same authority context needed to avoid scope drift.
- Plan review cannot approve a plan that narrows selected-tranche completion to a first-pass, inventory-only, blocked-state, or deferred slice without roadmap-level authority.
- Plan review routes locally fixable plan omissions to `REVISE`.
- Plan review routes design-insufficient full-scope planning failures to `ESCALATE_REDESIGN`.
- Existing implementation-review roadmap-authority behavior remains unchanged.
- Canonical workflow tests pass.
- At least one canonical orchestrator dry-run passes.
- EasySpin workflow/prompt copies are byte-identical for changed files.
- At least one EasySpin dry-run passes in `ptycho311`.
