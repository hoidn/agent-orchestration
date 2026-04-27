# Repeat-Until Exhaustion Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bounded review-loop exhaustion route deterministically to the appropriate adjacent escalation decision with active escalation evidence instead of failing the workflow as a generic runtime error.

**Architecture:** Add an opt-in `repeat_until.on_exhausted` DSL surface that completes the loop with explicit output overrides when the loop reaches `max_iterations` without satisfying its condition. The runtime continues to fail on body-step errors, output-resolution errors, and predicate errors; only normal non-convergence of the post-test condition is converted to authored outputs. Major-project design, plan, and implementation review loops then map exhaustion to their existing adjacent escalation decisions and run a deterministic post-loop step that activates the relevant escalation context or roadmap change request.

**Tech Stack:** Python orchestrator runtime, YAML workflow DSL v2.12+, pytest, existing major-project workflow library.

---

## Design

### Problem

`repeat_until` currently treats review-loop non-convergence as a runtime failure:

- body executes successfully
- loop outputs are resolved
- condition evaluates to `false`
- `current_iteration + 1 >= max_iterations`
- runtime writes `repeat_until_iterations_exhausted` and returns `status=failed`

That collapses two different cases:

- **real workflow failure:** a provider step crashed, output contract failed, consumes failed, or predicate evaluation failed
- **process non-convergence:** all iterations ran, but the review/fix loop never reached an accepted terminal decision

The EasySpin T26 failure was the second case. The workflow had enough information to escalate, but the runtime converted loop exhaustion into a hard failure before workflow routing could see it.

The routing fix alone is not enough. A lower phase that exhausts its review loop must also pass an active context artifact to the receiving phase. Otherwise the downstream revision prompt can see an escalation decision without knowing why the previous phase failed to converge, which artifact was last reviewed, or which findings were still unresolved.

### Target Behavior

Add opt-in exhaustion handling:

```yaml
repeat_until:
  max_iterations: 20
  outputs:
    review_decision:
      kind: scalar
      type: enum
      allowed: ["APPROVE", "REVISE", "ESCALATE_ROADMAP_REVISION", "BLOCK"]
      from:
        ref: self.steps.RouteBigDesignDecision.artifacts.review_decision
  condition:
    any_of:
      - compare:
          left: { ref: self.outputs.review_decision }
          op: eq
          right: APPROVE
      - compare:
          left: { ref: self.outputs.review_decision }
          op: eq
          right: ESCALATE_ROADMAP_REVISION
      - compare:
          left: { ref: self.outputs.review_decision }
          op: eq
          right: BLOCK
  on_exhausted:
    outputs:
      review_decision: ESCALATE_ROADMAP_REVISION
      loop_exhausted: true
  steps: [...]
```

When exhausted, the loop result should be:

- `status: completed`
- `exit_code: 0`
- `debug.structured_repeat_until.last_condition_result: false`
- `debug.structured_repeat_until.exhausted: true`
- artifacts equal to the last iteration frame artifacts, with `on_exhausted.outputs` overriding the named loop-frame artifacts
- no runtime `error`

This keeps deterministic control in the workflow and keeps prompts out of loop mechanics.

For major-project phases, a post-loop command must then normalize state files and context artifacts when `loop_exhausted` is true. That command is phase-specific because the receiving authority differs:

- big design exhaustion activates `design_escalation_context.json` and `roadmap_change_request.json`
- plan exhaustion activates `plan_escalation_context.json`
- implementation exhaustion activates `implementation_escalation_context.json`

Each context should include:

- `active: true`
- `reason: "repeat_until_iterations_exhausted"`
- phase name
- max iterations
- last review decision
- last review report path
- last candidate artifact path, such as design, plan, or execution report
- unresolved high/medium counts when available
- target escalation route

### Boundaries

Do:

- Add a generic `repeat_until.on_exhausted.outputs` surface.
- Validate override names and values against declared `repeat_until.outputs`.
- Support scalar output overrides first; this is enough for enum decisions such as `ESCALATE_REPLAN`.
- Preserve last iteration artifacts for every output not overridden.
- Record exhaustion metadata in loop debug state.
- Add phase-local post-loop commands that rewrite the phase's decision pointer and activate the appropriate escalation evidence when the loop exhausted.
- Route major-project phases through existing adjacent escalation decisions:
  - big design exhaustion -> `ESCALATE_ROADMAP_REVISION`
  - plan exhaustion -> `ESCALATE_REDESIGN`
  - implementation exhaustion -> `ESCALATE_REPLAN`

Do not:

- Convert body-step failures into escalation.
- Add prompt wording that asks agents to manage iteration caps.
- Add non-adjacent implementation -> roadmap escalation.
- Change raw `goto` loop behavior.
- Require roadmap revision for every repeat loop globally.
- Depend on a provider to notice exhaustion and write escalation context after the cap is reached.

### Compatibility

This is backward-compatible because `on_exhausted` is optional and version-gated. Existing workflows continue to fail on exhaustion unless they opt in with DSL v2.12.

Because this changes the DSL schema, update the normative spec, typed workflow pipeline, and tests. Do not retroactively extend v2.7; unknown fields must remain validation errors for older declared versions.

---

## Revision Plan

### Files

- Modify `specs/dsl.md`: document `repeat_until.on_exhausted.outputs`.
- Modify `specs/versioning.md`: record the additive repeat-until exhaustion behavior.
- Modify `specs/state.md`: document the new debug/progress metadata.
- Modify `docs/workflow_drafting_guide.md`: advise using deterministic exhaustion outputs for bounded review loops whose non-convergence has a known escalation route.
- Modify `orchestrator/loader.py`: add v2.12 support and validate the new field.
- Modify `orchestrator/workflow/statements.py`: preserve `on_exhausted` during statement normalization.
- Modify `orchestrator/workflow/surface_ast.py`: carry repeat-until exhaustion overrides in the surface AST.
- Modify `orchestrator/workflow/elaboration.py`: parse the new field into the surface AST.
- Modify `orchestrator/workflow/lowering.py`: lower the field into executable configuration and frame nodes.
- Modify `orchestrator/workflow/executable_ir.py`: carry the field in executable IR dataclasses.
- Modify `orchestrator/workflow/runtime_step.py`: project the field back into runtime step payloads.
- Modify `orchestrator/workflow/loops.py`: implement completion-on-exhaustion behavior.
- Modify or add tests:
  - `tests/test_loader_validation.py`
  - `tests/test_workflow_executor_characterization.py`
  - `tests/test_workflow_state_compatibility.py`
  - `tests/test_workflow_examples_v0.py`
  - typed pipeline helper/invariant tests as needed
- Modify major-project workflows:
  - `workflows/library/tracked_big_design_phase.yaml`
  - `workflows/library/major_project_tranche_plan_phase.yaml`
  - `workflows/library/major_project_tranche_implementation_phase.yaml`
- Modify major-project revision prompts:
  - `workflows/library/prompts/major_project_stack/draft_project_roadmap_revision.md`
  - `workflows/library/prompts/major_project_stack/revise_project_roadmap_revision.md`
  - `workflows/library/prompts/major_project_stack/draft_big_design.md`
  - `workflows/library/prompts/major_project_stack/revise_big_design.md`
  - `workflows/library/prompts/major_project_stack/draft_plan.md`
  - `workflows/library/prompts/major_project_stack/revise_plan.md`
- Optionally modify generic design/plan/implementation stack workflows only after checking their decision vocabularies:
  - `workflows/library/tracked_design_phase.yaml`
  - `workflows/library/seeded_design_plan_impl_stack.yaml`

### Contract Shape

Use:

```yaml
on_exhausted:
  outputs:
    <loop_output_name>: <literal>
```

Validation rules:

- `on_exhausted`, when present, must be a mapping.
- `on_exhausted.outputs`, when present, must be a non-empty mapping.
- Every key in `on_exhausted.outputs` must exist in `repeat_until.outputs`.
- The override literal must validate against the corresponding output contract type and enum `allowed` list.
- The first implementation supports literal scalar values only. Relpath overrides are rejected unless and until there is a real use case.

Runtime rules:

- Resolve normal loop outputs before evaluating the condition, as today.
- If condition is false and the iteration cap is reached:
  - if no `on_exhausted` exists, keep current failure behavior
  - if `on_exhausted.outputs` exists, copy the latest `frame_artifacts`, apply overrides, and complete the loop
- Do not run any additional provider step on exhaustion.
- Workflows that need durable pointer files or rich context artifacts must add deterministic post-loop command steps. `on_exhausted.outputs` updates loop-frame artifacts only; it does not mutate arbitrary files such as `final_*_decision.txt`, `*_escalation_context.json`, or `roadmap_change_request.json`.

Major-project context activation rules:

- If the big-design loop exhausts, write `ESCALATE_ROADMAP_REVISION` into the design decision pointer, activate `design_escalation_context.json`, and activate `roadmap_change_request.json`.
- If the plan loop exhausts, write `ESCALATE_REDESIGN` into the plan decision pointer and activate `plan_escalation_context.json`.
- If the implementation loop exhausts, write `ESCALATE_REPLAN` into the implementation decision pointer and activate `implementation_escalation_context.json`.
- If a reviewer already chose an escalation decision before exhaustion, preserve the reviewer-authored context artifacts instead of overwriting them.

---

## Implementation Plan

### Task 1: Loader Validation

**Files:**

- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

- [x] **Step 1: Add failing loader tests**

Add tests that build minimal v2.12 workflows with `repeat_until.on_exhausted`.

Required cases:

```python
def test_repeat_until_accepts_on_exhausted_enum_override(tmp_path):
    workflow = {
        "version": "2.12",
        "artifacts": {
            "decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE", "ESCALATE"],
            },
            "loop_exhausted": {"kind": "scalar", "type": "bool"},
        },
        "steps": [{
            "name": "ReviewLoop",
            "repeat_until": {
                "max_iterations": 2,
                "outputs": {
                    "decision": {
                        "kind": "scalar",
                        "type": "enum",
                        "allowed": ["APPROVE", "REVISE", "ESCALATE"],
                        "from": {"ref": "self.steps.Route.artifacts.decision"},
                    },
                    "loop_exhausted": {
                        "kind": "scalar",
                        "type": "bool",
                        "from": {"ref": "self.steps.MarkNotExhausted.artifacts.loop_exhausted"},
                    }
                },
                "condition": {
                    "compare": {
                        "left": {"ref": "self.outputs.decision"},
                        "op": "eq",
                        "right": "APPROVE",
                    }
                },
                "on_exhausted": {
                    "outputs": {"decision": "ESCALATE", "loop_exhausted": True}
                },
                "steps": [
                    {
                        "name": "Route",
                        "set_scalar": {"artifact": "decision", "value": "REVISE"},
                    },
                    {
                        "name": "MarkNotExhausted",
                        "set_scalar": {"artifact": "loop_exhausted", "value": False},
                    }
                ],
            },
        }],
    }
    # loader validation succeeds
```

Also add rejection cases:

- unknown output key
- enum value not in `allowed`
- non-bool value for a bool output
- relpath output override
- non-mapping `on_exhausted`
- v2.7 workflow using `on_exhausted`

- [x] **Step 2: Run the new loader tests and confirm failure**

Run:

```bash
pytest tests/test_loader_validation.py -k repeat_until -q
```

Expected: new tests fail because the loader currently rejects unknown `repeat_until` fields or does not validate them.

- [x] **Step 3: Implement validation**

In `orchestrator/loader.py`, extend `_validate_repeat_until_statement` after output normalization:

```python
on_exhausted = block.get("on_exhausted")
if on_exhausted is not None:
    self._validate_repeat_until_on_exhausted(
        step_name=step_name,
        on_exhausted=on_exhausted,
        output_specs=normalized_outputs,
    )
```

Add a helper that checks v2.12 gating, mapping shape, known output names, scalar-only output types, and scalar contract validity.

- [x] **Step 4: Run loader tests**

Run:

```bash
pytest tests/test_loader_validation.py -k repeat_until -q
```

Expected: pass.

### Task 2: Typed Pipeline And Runtime Exhaustion Completion

**Files:**

- Modify: `orchestrator/workflow/statements.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/loops.py`
- Test helper: `tests/workflow_bundle_helpers.py`
- Test: `tests/test_workflow_executor_characterization.py`
- Test: `tests/test_workflow_state_compatibility.py`

- [x] **Step 1: Preserve the field through the typed workflow pipeline**

Ensure `on_exhausted.outputs` survives validation, surface AST creation, lowering, executable IR, runtime materialization, and test bundle compatibility projections. This is required because runtime loops operate on materialized runtime steps, not directly on the original YAML payload.

- [x] **Step 2: Add failing executor test**

Add a workflow that:

- has `max_iterations: 2`
- emits `REVISE` each iteration
- has condition `decision == APPROVE`
- has `on_exhausted.outputs.decision = ESCALATE`
- has `on_exhausted.outputs.loop_exhausted = true`
- has a downstream step that reads `root.steps.ReviewLoop.artifacts.decision`

Expected final state:

```python
loop = state["steps"]["ReviewLoop"]
assert loop["status"] == "completed"
assert loop["exit_code"] == 0
assert loop["artifacts"]["decision"] == "ESCALATE"
assert loop["artifacts"]["loop_exhausted"] is True
assert loop["debug"]["structured_repeat_until"]["exhausted"] is True
assert loop["debug"]["structured_repeat_until"]["completed_iterations"] == [0, 1]
```

- [x] **Step 3: Add preservation test**

Add a second output, for example `last_report_path`, that is not overridden. Verify exhaustion preserves its last-iteration artifact.

- [x] **Step 4: Add non-regression test for no opt-in**

Verify a loop without `on_exhausted` still fails with `repeat_until_iterations_exhausted`.

- [x] **Step 5: Add body-failure non-regression test**

Verify a body step failure still fails the loop even if `on_exhausted` is present.

- [x] **Step 6: Implement runtime helper**

In `orchestrator/workflow/loops.py`, add helper logic:

```python
def _repeat_until_exhaustion_artifacts(self, block, frame_artifacts):
    on_exhausted = block.get("on_exhausted") if isinstance(block, dict) else None
    if not isinstance(on_exhausted, Mapping):
        return None
    overrides = on_exhausted.get("outputs")
    if not isinstance(overrides, Mapping):
        return None
    artifacts = dict(frame_artifacts)
    artifacts.update(overrides)
    return artifacts
```

At the exhaustion branch, replace hard failure with:

```python
exhausted_artifacts = self._repeat_until_exhaustion_artifacts(block, frame_artifacts)
if exhausted_artifacts is not None:
    progress = {..., "last_condition_result": False, "exhausted": True}
    completed = self.executor._attach_outcome(
        step,
        self.build_repeat_until_frame_result(
            step,
            status="completed",
            exit_code=0,
            artifacts=exhausted_artifacts,
            progress=progress,
        ),
    )
    self.persist_repeat_until_progress(state, step_name, progress, completed)
    return state
```

Keep the existing failure branch when `exhausted_artifacts is None`.

- [x] **Step 7: Include debug metadata**

Extend `build_repeat_until_frame_result` to include:

```python
"exhausted": progress.get("exhausted", False)
```

Do not require old persisted states to contain the field.

- [x] **Step 8: Run runtime tests**

Run:

```bash
pytest tests/test_workflow_executor_characterization.py -k repeat_until -q
pytest tests/test_workflow_state_compatibility.py -k repeat_until -q
```

Expected: pass.

### Task 3: Spec And Guide Updates

**Files:**

- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `specs/state.md`
- Modify: `docs/workflow_drafting_guide.md`

- [x] **Step 1: Update DSL spec**

In the v2.7 `repeat_until` section, change the shape from:

```text
{ id?, outputs: WorkflowOutputMap, condition: TypedPredicate, max_iterations: integer, steps: Step[] }
```

to:

```text
{ id?, outputs: WorkflowOutputMap, condition: TypedPredicate, max_iterations: integer, on_exhausted?, steps: Step[] }
```

Add concise semantics:

- absent `on_exhausted`: exhaustion fails as before
- present `on_exhausted.outputs`: exhaustion completes the loop with the latest outputs plus literal overrides
- this handles condition non-convergence only, not body failure

- [x] **Step 2: Update versioning and state docs**

Document this as a v2.12 feature.

Document `debug.structured_repeat_until.exhausted`.

- [x] **Step 3: Update authoring guide**

Add a short note under loop patterns:

```md
For bounded review loops where exhausting the loop means "this phase did not converge" rather than "the workflow crashed", use `repeat_until.on_exhausted.outputs` to route to the adjacent escalation decision. Keep provider prompts unaware of the loop cap.
```

- [x] **Step 4: Run doc-adjacent tests**

Run:

```bash
pytest tests/test_workflow_surface_ast.py tests/test_workflow_lowering_invariants.py -q
```

Expected: pass.

### Task 4: Major-Project Workflow Wiring And Context Activation

**Files:**

- Modify: `workflows/library/tracked_big_design_phase.yaml`
- Modify: `workflows/library/major_project_tranche_plan_phase.yaml`
- Modify: `workflows/library/major_project_tranche_implementation_phase.yaml`

- [x] **Step 1: Add loop-exhausted outputs to each review loop**

For each major-project review loop, add a normal per-iteration `loop_exhausted: false` artifact and expose it as a loop output.

Example body step:

```yaml
- name: MarkBigDesignLoopNotExhausted
  id: mark_big_design_loop_not_exhausted
  set_scalar:
    artifact: loop_exhausted
    value: false
```

Example loop output:

```yaml
loop_exhausted:
  kind: scalar
  type: bool
  from:
    ref: self.steps.MarkBigDesignLoopNotExhausted.artifacts.loop_exhausted
```

- [x] **Step 2: Add big-design exhaustion output**

In `BigDesignReviewLoop.repeat_until`, add:

```yaml
on_exhausted:
  outputs:
    review_decision: ESCALATE_ROADMAP_REVISION
    loop_exhausted: true
```

- [x] **Step 3: Add plan exhaustion output**

In `PlanReviewLoop.repeat_until`, add:

```yaml
on_exhausted:
  outputs:
    review_decision: ESCALATE_REDESIGN
    loop_exhausted: true
```

- [x] **Step 4: Add implementation exhaustion output**

In `ImplementationReviewLoop.repeat_until`, add:

```yaml
on_exhausted:
  outputs:
    review_decision: ESCALATE_REPLAN
    loop_exhausted: true
```

- [x] **Step 5: Add big-design post-loop exhaustion activation**

After `BigDesignReviewLoop` and before `FinalizeBigDesignPhaseOutputs`, add a command step guarded by `root.steps.BigDesignReviewLoop.artifacts.loop_exhausted == true`.

The command must:

- write `ESCALATE_ROADMAP_REVISION` to `${inputs.state_root}/design_review_decision.txt`
- preserve the existing review report pointer
- read `${inputs.state_root}/design_path.txt` and `${inputs.state_root}/design_review_report_path.txt`
- overwrite `${inputs.state_root}/design_escalation_context.json` with active exhaustion context
- overwrite `${inputs.state_root}/roadmap_change_request.json` with an active roadmap change request that says the selected tranche design review exhausted its cap and asks roadmap revision to change tranche claim, scope, ordering, prerequisites, ownership, or split strategy as appropriate

Minimum JSON fields:

```json
{
  "active": true,
  "reason": "repeat_until_iterations_exhausted",
  "phase": "big_design_review",
  "target_route": "ESCALATE_ROADMAP_REVISION",
  "max_iterations": 20,
  "last_review_decision": "REVISE",
  "last_candidate_artifact_path": "docs/plans/...",
  "last_review_report_path": "artifacts/review/...",
  "unresolved_high_count": 0,
  "unresolved_medium_count": 3
}
```

The exact schema may include additional existing fields, but these fields must be present for exhaustion-created contexts.

- [x] **Step 6: Add plan post-loop exhaustion activation**

After `PlanReviewLoop` and before `FinalizePlanPhaseOutputs`, add a guarded command step.

The command must:

- write `ESCALATE_REDESIGN` to `${inputs.state_root}/plan_review_decision.txt`
- read `${inputs.state_root}/plan_path.txt` and `${inputs.state_root}/plan_review_report_path.txt`
- overwrite `${inputs.state_root}/plan_escalation_context.json` with active exhaustion context
- preserve the last plan and last review report for redesign to consume

The context should say the plan phase failed to converge and the design revision should decide whether the approved design is too broad, under-specified, wrongly scoped, or missing a planning-critical architectural decision.

- [x] **Step 7: Add implementation post-loop exhaustion activation**

After `ImplementationReviewLoop` and before `FinalizeImplementationPhaseOutputs`, add a guarded command step.

The command must:

- write `ESCALATE_REPLAN` to `${inputs.state_root}/implementation_review_decision.txt`
- read `${inputs.state_root}/execution_report_path.txt` and `${inputs.state_root}/implementation_review_report_path.txt`
- overwrite `${inputs.state_root}/implementation_escalation_context.json` with active exhaustion context
- preserve the last execution report and last implementation review for planning to consume

The context should say implementation review/fix failed to converge and planning should decide whether the task breakdown, sequencing, scope boundary, verification strategy, or required implementation architecture needs revision.

- [x] **Step 8: Verify downstream routing already handles those decisions**

Check these existing routes still apply:

```bash
rg -n "ESCALATE_ROADMAP_REVISION|ESCALATE_REDESIGN|ESCALATE_REPLAN" workflows/library/major_project_tranche_design_plan_impl_stack.yaml workflows/library/tracked_big_design_phase.yaml workflows/library/major_project_tranche_plan_phase.yaml workflows/library/major_project_tranche_implementation_phase.yaml
```

Expected: each exhausted decision is already an allowed terminal condition and is already routed by the selected stack.

- [x] **Step 9: Add workflow-level regression tests for context activation**

Add tests or a minimal example workflow proving that after loop exhaustion:

- the loop frame artifact says `loop_exhausted: true`
- the phase decision pointer file contains the escalation decision, not the last local `REVISE`
- the relevant escalation context JSON has `active: true`
- final phase outputs expose the escalation decision and active context path

- [x] **Step 10: Run workflow validation**

Run:

```bash
python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run \
  --input project_brief_path=docs/backlog/example.md \
  --input project_roadmap_path=docs/plans/example-roadmap.md \
  --input tranche_manifest_target_path=state/example/manifest.json \
  --input drain_state_root=state/example/drain \
  --input drain_summary_target_path=artifacts/work/example/drain-summary.json
```

If the example inputs do not exist in this repo, run the same dry-run from a downstream repo with real inputs, for example EasySpin, using `PYTHONPATH=/home/ollie/Documents/agent-orchestration`.

### Task 5: Revision Prompt Support For Exhaustion Context

**Files:**

- Modify: `workflows/library/prompts/major_project_stack/draft_project_roadmap_revision.md`
- Modify: `workflows/library/prompts/major_project_stack/revise_project_roadmap_revision.md`
- Modify: `workflows/library/prompts/major_project_stack/draft_big_design.md`
- Modify: `workflows/library/prompts/major_project_stack/revise_big_design.md`
- Modify: `workflows/library/prompts/major_project_stack/draft_plan.md`
- Modify: `workflows/library/prompts/major_project_stack/revise_plan.md`

- [x] **Step 1: Add neutral exhaustion-context instruction to roadmap revision prompts**

Add one short instruction:

```md
If the roadmap change request says a lower phase failed to converge, treat that as evidence of non-convergence. Revise only roadmap-owned structure: tranche claim, split, ordering, prerequisites, ownership, or manifest fields. Preserve valid lower-phase work where possible.
```

- [x] **Step 2: Add neutral exhaustion-context instruction to design revision prompts**

Add one short instruction:

```md
If the consumed escalation context says planning failed to converge, treat that as evidence that the approved design may be too broad, under-specified, wrongly scoped, or missing a planning-critical architectural decision. Revise design-owned decisions only; do not write the plan.
```

- [x] **Step 3: Add neutral exhaustion-context instruction to plan revision prompts**

Add one short instruction:

```md
If the consumed escalation context says implementation failed to converge, treat that as evidence that the plan may need a better task breakdown, sequence, scope boundary, verification strategy, or implementation architecture. Revise plan-owned decisions only; do not patch the implementation.
```

- [x] **Step 4: Keep prompts out of mechanics**

Check the prompt diff for forbidden workflow-mechanics leakage. The prompts may mention consumed escalation context and current-phase authority, but should not mention `repeat_until`, `max_iterations`, loop frame artifacts, pointer files, or runtime internals.

### Task 6: Integration Regression Workflow

**Files:**

- Add: `workflows/examples/repeat_until_exhaustion_escalation_demo.yaml`
- Add or modify: `tests/test_workflow_examples_v0.py`

- [x] **Step 1: Add a minimal runnable example**

Create a demo workflow with:

- a review loop that always returns `REVISE`
- `on_exhausted.outputs.review_decision = ESCALATE_REPLAN`
- `on_exhausted.outputs.loop_exhausted = true`
- a final command step that writes the routed decision to an output file

- [x] **Step 2: Add test**

Test that the demo workflow completes, exports `ESCALATE_REPLAN`, and runs a deterministic activation command that writes an active escalation-context JSON.

- [x] **Step 3: Run example tests**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k repeat_until -q
```

Expected: pass.

### Task 7: Downstream EasySpin Sync And Smoke Check

**Files:**

- Copy updated workflow library files into `/home/ollie/Documents/EasySpin/workflows/library/` if EasySpin carries a vendored copy.

- [x] **Step 1: Sync workflow files**

Run:

```bash
rsync -av workflows/library/tracked_big_design_phase.yaml /home/ollie/Documents/EasySpin/workflows/library/tracked_big_design_phase.yaml
rsync -av workflows/library/major_project_tranche_plan_phase.yaml /home/ollie/Documents/EasySpin/workflows/library/major_project_tranche_plan_phase.yaml
rsync -av workflows/library/major_project_tranche_implementation_phase.yaml /home/ollie/Documents/EasySpin/workflows/library/major_project_tranche_implementation_phase.yaml
rsync -av workflows/library/prompts/major_project_stack/ /home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/
```

- [x] **Step 2: Run EasySpin dry-run**

Run from `/home/ollie/Documents/EasySpin`:

```bash
source /home/ollie/miniconda3/etc/profile.d/conda.sh
conda activate ptycho311
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run \
  --input project_brief_path=docs/backlog/pytorch-port.md \
  --input project_roadmap_path=docs/plans/pytorch-port-roadmap.md \
  --input tranche_manifest_target_path=state/easyspin-pytorch-port/roadmap/tranche_manifest.json \
  --input drain_state_root=state/easyspin-pytorch-port/dry-run-repeat-until-exhaustion-escalation \
  --input drain_summary_target_path=artifacts/work/easyspin-pytorch-port/dry-run-repeat-until-exhaustion-escalation-summary.json
```

Expected: workflow validation successful.

### Task 8: Final Verification

- [x] **Step 1: Run focused tests**

Run from `/home/ollie/Documents/agent-orchestration`:

```bash
pytest tests/test_loader_validation.py -k repeat_until -q
pytest tests/test_workflow_executor_characterization.py -k repeat_until -q
pytest tests/test_workflow_state_compatibility.py -k repeat_until -q
pytest tests/test_workflow_examples_v0.py -k repeat_until -q
```

- [x] **Step 2: Run broader control-flow suite**

Run:

```bash
pytest tests/test_structured_control_flow.py tests/test_workflow_lowering_invariants.py tests/test_workflow_surface_ast.py -q
```

- [x] **Step 3: Check diffs**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files changed.

---

## Acceptance Criteria

- Existing workflows without `on_exhausted` retain current hard-failure behavior on `repeat_until` exhaustion.
- Workflows with `on_exhausted.outputs` complete on condition non-convergence and expose authored override artifacts.
- Body failures, consume failures, output contract failures, and predicate failures still fail.
- Major-project big-design exhaustion routes to roadmap revision and activates both design escalation context and roadmap change request.
- Major-project plan exhaustion routes to redesign and activates plan escalation context.
- Major-project implementation exhaustion routes to replan and activates implementation escalation context.
- Phase finalizers expose the escalation decision after exhaustion, not the last local `REVISE`.
- Revision prompts know how to interpret active exhaustion context at their own authority level without managing loop mechanics.
- The behavior is documented in `specs/` and the workflow drafting guide.
- EasySpin dry-run validates against the updated local orchestrator.
