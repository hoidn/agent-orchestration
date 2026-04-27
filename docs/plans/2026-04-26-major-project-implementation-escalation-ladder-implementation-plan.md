# Major-Project Implementation Escalation Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree in this repository.

**Goal:** Implement the approved major-project-only escalation ladder from `docs/plans/2026-04-26-major-project-implementation-escalation-ladder-design.md` so implementation review can route upward to replan, planning can route upward to redesign, design can request roadmap revision, and drain workflows can revise the manifest without repeatedly churning local implementation.

**Architecture:** Keep the shared generic plan and implementation phases unchanged. Fork major-project-local plan and implementation phases, extend the already-major-project big-design phase, and add one roadmap-revision phase. Put deterministic counters, context archival, reset behavior, routing, manifest status changes, and pointer ownership in workflow YAML plus small Python helper scripts; leave prompts responsible only for local judgment and writing their declared artifacts.

**Tech Stack:** Agent-orchestration DSL v2.7, reusable `call` workflows, top-level raw `goto` routing for cross-phase backedges, `repeat_until` inside phases, Codex provider prompt assets under `workflows/library/prompts/major_project_stack/`, deterministic Python helper scripts, pytest workflow/contract/runtime tests, and orchestrator dry-run smoke checks.

---

## Scope Boundaries

Implement only the major-project tranche stack family:

- `workflows/library/tracked_big_design_phase.yaml`
- `workflows/library/major_project_tranche_plan_phase.yaml`
- `workflows/library/major_project_tranche_implementation_phase.yaml`
- `workflows/library/major_project_roadmap_revision_phase.yaml`
- `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml`
- `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml`

Do not modify these shared generic phases or prompt assets for this feature:

- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`
- `workflows/library/prompts/design_plan_impl_stack_v2_call/`

Tests must assert behavior, contracts, routing, assets, and dataflow. Do not add tests that assert literal prompt phrasing.

## File Structure

Create:

- `workflows/library/major_project_tranche_plan_phase.yaml` - major-project-local tracked plan loop with `APPROVE`, `REVISE`, `ESCALATE_REDESIGN`, and `BLOCK`.
- `workflows/library/major_project_tranche_implementation_phase.yaml` - major-project-local implementation/review/fix loop with iteration context and `APPROVE`, `REVISE`, `ESCALATE_REPLAN`, and `BLOCK`.
- `workflows/library/major_project_roadmap_revision_phase.yaml` - major-project-local roadmap-revision loop consuming a structured roadmap change request.
- `workflows/library/scripts/major_project_escalation_state.py` - deterministic lifecycle helper for inactive context initialization, activation, archive/reset, implementation ledger context, design-approval reset, and terminal cleanup.
- `workflows/library/prompts/major_project_stack/draft_plan.md`
- `workflows/library/prompts/major_project_stack/review_plan.md`
- `workflows/library/prompts/major_project_stack/revise_plan.md`
- `workflows/library/prompts/major_project_stack/implement_plan.md`
- `workflows/library/prompts/major_project_stack/review_implementation.md`
- `workflows/library/prompts/major_project_stack/fix_implementation.md`
- `workflows/library/prompts/major_project_stack/draft_project_roadmap_revision.md`
- `workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md`
- `workflows/library/prompts/major_project_stack/revise_project_roadmap_revision.md`
- `tests/test_major_project_escalation_state.py`

Modify:

- `workflows/library/tracked_big_design_phase.yaml`
- `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml`
- `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml`
- `workflows/library/scripts/select_major_project_tranche.py`
- `workflows/library/scripts/update_major_project_tranche_manifest.py`
- `workflows/library/scripts/validate_major_project_tranche_manifest.py`
- `workflows/README.md`
- `prompts/README.md`
- `docs/index.md`
- `tests/test_major_project_workflows.py`
- `tests/test_major_project_manifest_validator.py`
- `tests/test_workflow_examples_v0.py` only if the example registry needs explicit updates.

## Task 1: Add Failing Contract Tests

**Files:**

- Modify: `tests/test_major_project_workflows.py`
- Modify: `tests/test_major_project_manifest_validator.py`
- Create: `tests/test_major_project_escalation_state.py`

Keep this first test pass focused. Add helper and static contract tests that point at the next implementation slice, but do not front-load all cross-stack and drain routing assertions before the helper, forked phases, and manifest semantics exist. Add those broader assertions in the task that implements the corresponding surface.

- [ ] **Step 1: Test major-project-local phase ownership**

Add tests asserting that `major_project_tranche_design_plan_impl_stack.yaml` imports:

```python
{
    "big_design_phase": "tracked_big_design_phase.yaml",
    "plan_phase": "major_project_tranche_plan_phase.yaml",
    "implementation_phase": "major_project_tranche_implementation_phase.yaml",
}
```

Add the same assertion for the approved-design stack, excluding the big-design import.

- [ ] **Step 2: Test shared generic surfaces stay unchanged**

Add a contract test that no new escalation decision tokens appear in:

- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`

Assert their `asset_file` values still point under `prompts/design_plan_impl_stack_v2_call/`.

- [ ] **Step 3: Test new decision enums and artifacts**

Assert the new major-project plan phase exports:

- `plan_review_decision` allowed `["APPROVE", "REVISE", "ESCALATE_REDESIGN", "BLOCK"]`
- `plan_escalation_context_path` under `state`

Assert the new major-project implementation phase exports:

- `implementation_review_decision` allowed `["APPROVE", "REVISE", "ESCALATE_REPLAN", "BLOCK"]`
- `implementation_escalation_context_path` under `state`
- `implementation_iteration_context_path` under `state`

Assert `tracked_big_design_phase.yaml` exports `design_review_decision` with `ESCALATE_ROADMAP_REVISION` added and publishes `roadmap_change_request_path`.

- [ ] **Step 4: Test stack upward routing**

Add these workflow-shape tests with Task 7, after the selected-tranche stacks have been rewired:

- implementation `ESCALATE_REPLAN` activates `upstream_escalation_context.json` and routes to `RunPlanPhase`
- plan `ESCALATE_REDESIGN` activates context and routes to `RunBigDesignPhase`
- big-design `ESCALATE_ROADMAP_REVISION` finalizes item outcome `ESCALATE_ROADMAP_REVISION`
- `APPROVE` paths clear upstream context at plan/design boundaries
- newly approved redesign resets the implementation iteration ledger

Use structure and artifact assertions, not prompt text.

- [ ] **Step 5: Test manifest status `superseded`**

In `tests/test_major_project_manifest_validator.py`, add cases showing:

- `superseded` is accepted as a terminal provenance status
- selector ignores `superseded`
- `superseded` is not counted as completed
- prerequisites depending on `superseded` are not satisfied

- [ ] **Step 6: Add helper unit tests**

In `tests/test_major_project_escalation_state.py`, test the helper CLI or pure functions for:

- initializing inactive `upstream_escalation_context.json`
- activating a new upstream context and archiving the previous active context
- writing `implementation_iteration_context.json` with `threshold_crossed=false` below `10`
- writing `threshold_crossed=true` at or above `10`
- preserving cumulative iteration count across replan
- resetting and archiving the ledger on new design approval
- terminal cleanup archiving active context and ledger

- [ ] **Step 7: Run collect-only and confirm expected failures**

Run:

```bash
pytest --collect-only tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py tests/test_major_project_escalation_state.py
pytest tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py tests/test_major_project_escalation_state.py -q
```

Expected: collection succeeds; tests fail only for the next concrete implementation slice, not because every future routing surface is missing.

## Task 2: Implement Deterministic Escalation State Helper

**Files:**

- Create: `workflows/library/scripts/major_project_escalation_state.py`
- Create: `tests/test_major_project_escalation_state.py`

- [ ] **Step 1: Add helper module and CLI skeleton**

Implement subcommands:

```text
init-upstream
activate-upstream
clear-upstream
write-implementation-iteration-context
reset-ledger-on-design-approval
terminal-cleanup
```

Each command takes `--item-state-root` or `--implementation-phase-state-root` as appropriate plus `--output-bundle` when workflow output contracts need typed fields.

- [ ] **Step 2: Implement inactive context initialization**

Write:

```json
{
  "active": false,
  "source_phase": null,
  "decision": null,
  "recommended_next_phase": null,
  "reason_summary": "",
  "must_change": [],
  "evidence_paths": {}
}
```

Also create `upstream_escalation_context_archive.jsonl` if missing.

- [ ] **Step 3: Implement activation**

Read the source context path, validate it is a JSON object with `active=true`, archive any previously active `upstream_escalation_context.json`, then overwrite it with the source payload. Write an output bundle containing `upstream_escalation_context_path`.

- [ ] **Step 4: Implement clear and archive**

Archive active context with a required `--resolution` token such as `consumed_by_plan`, `consumed_by_redesign`, `tranche_completed`, `tranche_blocked`, or `tranche_superseded`, then reset active context to inactive.

- [ ] **Step 5: Implement implementation iteration ledger**

If `implementation_iteration_ledger.json` is absent, create:

```json
{
  "design_epoch": 1,
  "cumulative_review_iterations_since_design_approval": 0
}
```

For each review iteration, increment the cumulative count and write `implementation_iteration_context.json` with:

```json
{
  "phase_iteration_index": 0,
  "phase_iteration_number": 1,
  "cumulative_review_iterations_since_design_approval": 1,
  "soft_escalation_iteration_threshold": 10,
  "threshold_crossed": false,
  "max_phase_iterations": 40
}
```

Use CLI args for phase iteration index, threshold, and max iterations so the YAML owns those values.

- [ ] **Step 6: Implement design-approval ledger reset**

Archive the current ledger row to `implementation_iteration_ledger_archive.jsonl` with reason `reset_on_design_approval`, increment `design_epoch`, and reset cumulative count to `0`.

- [ ] **Step 7: Implement terminal cleanup**

Archive any active upstream context and active implementation ledger with a terminal resolution. Reset upstream context to inactive.

- [ ] **Step 8: Run helper tests**

Run:

```bash
pytest tests/test_major_project_escalation_state.py -q
```

Expected: all helper lifecycle tests pass.

## Task 3: Add Major-Project Implementation Phase

**Files:**

- Create: `workflows/library/major_project_tranche_implementation_phase.yaml`
- Create: `workflows/library/prompts/major_project_stack/implement_plan.md`
- Create: `workflows/library/prompts/major_project_stack/review_implementation.md`
- Create: `workflows/library/prompts/major_project_stack/fix_implementation.md`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Copy the generic implementation phase as the starting shape**

Copy `design_plan_impl_implementation_phase.yaml` into the new major-project-local file, then change only the major-project-specific surfaces.

- [ ] **Step 2: Switch prompt assets to major-project-local files**

Use:

```yaml
asset_file: prompts/major_project_stack/implement_plan.md
asset_file: prompts/major_project_stack/review_implementation.md
asset_file: prompts/major_project_stack/fix_implementation.md
```

- [ ] **Step 3: Add escalation artifacts and outputs**

Add artifacts for:

- `implementation_iteration_context`
- `implementation_escalation_context`

Add outputs for:

- `execution_report_path`
- `implementation_review_report_path`
- `implementation_review_decision`
- `implementation_escalation_context_path`

Allowed implementation review decisions:

```yaml
allowed: ["APPROVE", "REVISE", "ESCALATE_REPLAN", "BLOCK"]
```

- [ ] **Step 4: Write iteration context before each review**

Inside `ImplementationReviewLoop`, add `WriteImplementationIterationContext` before `ReviewImplementation`. It should call:

```bash
python workflows/library/scripts/major_project_escalation_state.py \
  write-implementation-iteration-context \
  --implementation-phase-state-root "${inputs.state_root}" \
  --phase-iteration-index "${loop.index}" \
  --soft-threshold "10" \
  --max-phase-iterations "40" \
  --output-bundle "${inputs.state_root}/implementation_iteration_context_output.json"
```

Inject the generated context into `ReviewImplementation` and `FixImplementation` through `consumes` or `depends_on.inject`.

- [ ] **Step 5: Require implementation escalation context**

Require `ReviewImplementation` to write `implementation_escalation_context.json` for every decision. It may be inactive or explanatory for `APPROVE` and `REVISE`, but it must be structurally present.

- [ ] **Step 6: Route escalation as semantic success**

Inside the phase loop:

- `APPROVE` terminates the phase
- `REVISE` runs `FixImplementation`
- `ESCALATE_REPLAN` terminates the phase with that decision
- `BLOCK` terminates the phase with that decision

Do not treat escalation as provider or workflow failure.

- [ ] **Step 7: Draft implementation prompts**

Base the files on the generic prompt family but add only major-project-specific escalation context:

- implementation review reads iteration context and decides among the four tokens
- fix reads iteration context and the latest implementation escalation context
- if threshold is crossed and decision remains `REVISE`, the review/fix artifacts must include an escalation assessment
- prompts must not manage counters, ledgers, archive files, or route names

- [ ] **Step 8: Run phase contract tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "implementation or escalation"
```

Expected: implementation-phase contract tests pass or reveal only downstream stack/drain failures.

## Task 4: Add Major-Project Plan Phase

**Files:**

- Create: `workflows/library/major_project_tranche_plan_phase.yaml`
- Create: `workflows/library/prompts/major_project_stack/draft_plan.md`
- Create: `workflows/library/prompts/major_project_stack/review_plan.md`
- Create: `workflows/library/prompts/major_project_stack/revise_plan.md`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Copy tracked plan phase as the starting shape**

Copy `tracked_plan_phase.yaml` into the new major-project-local file.

- [ ] **Step 2: Add upstream context input**

Add an input:

```yaml
upstream_escalation_context_path:
  type: relpath
  under: state
  must_exist_target: true
```

Publish it as an artifact and inject it into draft, review, and revise plan steps.

- [ ] **Step 3: Switch prompt assets**

Use `prompts/major_project_stack/draft_plan.md`, `review_plan.md`, and `revise_plan.md`.

- [ ] **Step 4: Expand decision enum**

Allowed plan review decisions:

```yaml
allowed: ["APPROVE", "REVISE", "ESCALATE_REDESIGN", "BLOCK"]
```

The repeat condition should terminate on `APPROVE`, `ESCALATE_REDESIGN`, or `BLOCK`; only `REVISE` should run `RevisePlanTracked`.

- [ ] **Step 5: Add plan escalation context**

Require `ReviewPlanTracked` to produce `plan_escalation_context.json` and expose `plan_escalation_context_path` from the phase outputs.

- [ ] **Step 6: Draft plan prompts**

Prompt behavior:

- draft/revise read active upstream context as authoritative evidence
- review can return `ESCALATE_REDESIGN` when the approved design cannot support an executable plan
- `BLOCK` is reserved for missing authority, external prerequisites, or contradictions that redesign cannot safely repair
- prompts do not reset or archive upstream context

- [ ] **Step 7: Run plan-phase tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "plan and escalation"
```

Expected: plan-phase contract tests pass or reveal only stack/drain routing failures.

## Task 5: Extend Big-Design Phase For Roadmap Revision Escalation

**Files:**

- Modify: `workflows/library/tracked_big_design_phase.yaml`
- Modify: `workflows/library/prompts/major_project_stack/draft_big_design.md`
- Modify: `workflows/library/prompts/major_project_stack/review_big_design.md`
- Modify: `workflows/library/prompts/major_project_stack/revise_big_design.md`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Add upstream context input**

Add:

```yaml
upstream_escalation_context_path:
  type: relpath
  under: state
  must_exist_target: true
```

Publish and inject it into draft, review, and revise big-design steps.

- [ ] **Step 2: Expand big-design decision enum**

Allowed decisions:

```yaml
allowed: ["APPROVE", "REVISE", "ESCALATE_ROADMAP_REVISION", "BLOCK"]
```

The phase repeat loop should terminate on `APPROVE`, `ESCALATE_ROADMAP_REVISION`, or `BLOCK`; only `REVISE` continues to `ReviseBigDesign`.

- [ ] **Step 3: Add escalation artifacts**

Require review to produce:

- `design_escalation_context.json`
- `roadmap_change_request.json` when the decision is `ESCALATE_ROADMAP_REVISION`

Expose both as phase outputs. Make `roadmap_change_request_path` optional or route-gated if the DSL output contract requires it only on escalation; if optional workflow outputs are awkward, emit an inactive placeholder JSON for non-escalation decisions.

- [ ] **Step 4: Update big-design prompts**

Prompt behavior:

- draft/revise preserve active upstream evidence
- review may use `ESCALATE_ROADMAP_REVISION` on the first review pass if tranche shape is visibly wrong
- `BLOCK` is reserved for missing/contradictory authority where a safe roadmap change request cannot be authored
- review writes structured `roadmap_change_request.json` for roadmap revision

- [ ] **Step 5: Run big-design tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "big_design and escalation"
```

Expected: big-design escalation contract tests pass.

## Task 6: Add Roadmap Revision Phase

**Files:**

- Create: `workflows/library/major_project_roadmap_revision_phase.yaml`
- Create: `workflows/library/prompts/major_project_stack/draft_project_roadmap_revision.md`
- Create: `workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md`
- Create: `workflows/library/prompts/major_project_stack/revise_project_roadmap_revision.md`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Define phase inputs and outputs**

Inputs:

- `state_root`
- `project_brief_path`
- `current_project_roadmap_path`
- `current_tranche_manifest_path`
- `roadmap_change_request_path`
- optional `selected_tranche_id`
- `roadmap_revision_report_target_path`

Outputs:

- `roadmap_revision_decision`: `APPROVE`, `REVISE`, or `BLOCK`
- `updated_project_roadmap_path`
- `updated_tranche_manifest_path`
- `roadmap_revision_report_path`

- [ ] **Step 2: Implement revision/review loop**

Use a roadmap-revision draft followed by a review/revise loop. The review loop terminates on `APPROVE` or `BLOCK`; `REVISE` runs the revise prompt.

- [ ] **Step 3: Validate revised manifest**

Reuse `workflows/library/scripts/validate_major_project_tranche_manifest.py` after draft and revise. The validator must accept `superseded` and preserve path-safety checks.

- [ ] **Step 4: Draft roadmap-revision prompts**

Prompt behavior:

- consume `roadmap_change_request.json`
- revise narrowly around the requested program-level issue
- preserve completed and unaffected pending tranches
- mark replaced tranches as `superseded` only when the approved revision explicitly replaces them
- do not regenerate the roadmap from scratch

- [ ] **Step 5: Run roadmap-revision tests**

Run:

```bash
pytest tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py -q -k "roadmap_revision or superseded"
```

Expected: roadmap-revision and manifest tests pass.

## Task 7: Rewire Selected-Tranche Stacks

**Files:**

- Modify: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- Modify: `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Initialize upstream context**

In `InitializeItemState`, call `major_project_escalation_state.py init-upstream` for `${inputs.item_state_root}`.

- [ ] **Step 2: Import major-project-local phases**

Use:

```yaml
imports:
  big_design_phase: tracked_big_design_phase.yaml
  plan_phase: major_project_tranche_plan_phase.yaml
  implementation_phase: major_project_tranche_implementation_phase.yaml
```

The approved-design stack imports only plan and implementation phases.

- [ ] **Step 3: Add top-level cross-phase routing**

Use raw top-level assertions and `on.success.goto` / `on.failure.goto` diamonds for cross-phase backedges. Do not put `goto` inside structured `match` cases; v2.7 structured cases reject `goto`.

Required routing:

- big-design `APPROVE` -> reset implementation ledger for new design, clear upstream context, run plan
- big-design `ESCALATE_ROADMAP_REVISION` -> finalize item outcome `ESCALATE_ROADMAP_REVISION`
- big-design `BLOCK` -> finalize skipped/blocked after design
- plan `APPROVE` -> clear upstream context, run implementation
- plan `ESCALATE_REDESIGN` -> activate from `plan_escalation_context.json`, run big design
- plan `BLOCK` -> finalize skipped/blocked after plan
- implementation `APPROVE` -> finalize approved item
- implementation `ESCALATE_REPLAN` -> activate from `implementation_escalation_context.json`, run plan without resetting ledger

- [ ] **Step 4: Add route safety caps**

Add `max_transitions` to the selected-tranche stacks and `max_visits` to phase call steps where supported so a bad escalation cycle fails explicitly instead of looping forever.

- [ ] **Step 5: Finalize new outcomes**

Expand `item_outcome` enum to include:

- `APPROVED`
- `SKIPPED_AFTER_DESIGN`
- `SKIPPED_AFTER_PLAN`
- `SKIPPED_AFTER_IMPLEMENTATION`
- `ESCALATE_ROADMAP_REVISION`

Include `roadmap_change_request_path` in the item summary when present.

- [ ] **Step 6: Run selected-tranche stack tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q -k "tranche_stack or upward or approved_design"
```

Expected: stack routing tests pass.

## Task 8: Rewire Drain Workflows And Manifest Updates

**Files:**

- Modify: `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml`
- Modify: `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml`
- Modify: `workflows/library/scripts/select_major_project_tranche.py`
- Modify: `workflows/library/scripts/update_major_project_tranche_manifest.py`
- Modify: `workflows/library/scripts/validate_major_project_tranche_manifest.py`
- Modify: `tests/test_major_project_workflows.py`
- Modify: `tests/test_major_project_manifest_validator.py`

- [ ] **Step 1: Add a drain-iteration workflow**

Create `workflows/library/major_project_tranche_drain_iteration.yaml`. It should import:

```yaml
imports:
  tranche_stack: major_project_tranche_design_plan_impl_stack.yaml
  roadmap_revision_phase: major_project_roadmap_revision_phase.yaml
```

Move selection, selected-stack execution, manifest update, and roadmap-revision dispatch into this workflow so its structured `match` steps are top-level and DSL-valid.

- [ ] **Step 2: Expand drain routing**

When selected tranche returns `ESCALATE_ROADMAP_REVISION`:

1. call `major_project_roadmap_revision_phase.yaml`
2. update authoritative roadmap and manifest paths
3. return drain status `CONTINUE` after approved revision
4. return drain status `BLOCKED` after roadmap-revision `BLOCK`
5. do not mark the selected tranche completed from the old stack result

- [ ] **Step 3: Make manifest update fail closed on roadmap escalation**

`update_major_project_tranche_manifest.py` should reject `ESCALATE_ROADMAP_REVISION` as a direct manifest update outcome. That outcome must be handled by the drain-iteration roadmap-revision route before any manifest update.

- [ ] **Step 4: Teach selector about superseded**

`select_major_project_tranche.py` must ignore `superseded`, not count it as completed, and not treat it as satisfying prerequisites.

- [ ] **Step 5: Update output bundles**

Expand relevant `output_bundle` enum fields in drain workflows:

- item outcome includes `ESCALATE_ROADMAP_REVISION`
- drain status remains `CONTINUE`, `DONE`, or `BLOCKED`
- manifest status counts include `superseded_count` if useful for assertions and summaries

- [ ] **Step 6: Run drain workflow tests**

Run:

```bash
pytest tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py -q -k "drain or selector or manifest"
```

Expected: drain, selector, and manifest helper tests pass.

## Task 9: Update Documentation Indexes

**Files:**

- Modify: `workflows/README.md`
- Modify: `prompts/README.md`
- Modify: `docs/index.md`

- [ ] **Step 1: Update workflow catalog**

Add the three new library workflows:

- `major_project_tranche_plan_phase.yaml`
- `major_project_tranche_implementation_phase.yaml`
- `major_project_roadmap_revision_phase.yaml`

Update descriptions for the major-project stack and drain examples to mention escalation/rerouting.

- [ ] **Step 2: Update prompt catalog**

Add the new major-project plan, implementation, and roadmap-revision prompt assets.

- [ ] **Step 3: Update docs index**

Add this implementation plan next to the design entry and keep the existing design entry intact.

## Task 10: Full Verification

**Files:**

- All files touched above.

- [ ] **Step 1: Run collect-only for changed tests**

Run:

```bash
pytest --collect-only tests/test_major_project_workflows.py tests/test_major_project_manifest_validator.py tests/test_major_project_escalation_state.py
```

Expected: collection succeeds.

- [ ] **Step 2: Run narrow unit and workflow tests**

Run:

```bash
pytest tests/test_major_project_escalation_state.py tests/test_major_project_manifest_validator.py tests/test_major_project_workflows.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run workflow dry-run smoke checks**

Run from repo root:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/major_project_tranche_drain_stack_v2_call.yaml --dry-run

PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml \
  --dry-run \
  --input project_brief_path=workflows/examples/inputs/major_project_brief.md \
  --input project_roadmap_path=docs/plans/major-project-demo/project-roadmap.md \
  --input tranche_manifest_target_path=state/major-project-demo/tranche_manifest.json
```

Expected: both workflows validate and dry-run without schema errors. If these are run as long or live workflows rather than dry-runs, use the `tmux` skill and run from the repo root.

- [ ] **Step 4: Run broader example validation if dry-run registry changed**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -q
```

Expected: all workflow example tests pass.

- [ ] **Step 5: Inspect diffs for prompt/runtime boundary**

Review:

```bash
git diff -- workflows/library workflows/examples tests docs/index.md workflows/README.md prompts/README.md
```

Confirm:

- shared generic plan/implementation workflows and prompts were not changed
- prompts do not own counters, archives, route names, or manifest mutation
- workflow/helper code owns deterministic lifecycle, routing, and manifest status changes
- tests assert behavior/contracts rather than literal prompt wording

## Rollout Notes

This change is not safely resumable mid-loop. Existing in-flight major-project runs should restart from the affected phase boundary:

- implementation phase if only implementation escalation support has landed
- plan or design phase once their decision enums and required context artifacts are active
- drain loop boundary once roadmap-revision routing and `superseded` manifest status are active

Record the final changed files and the exact verification commands in the execution report or final implementation summary.
