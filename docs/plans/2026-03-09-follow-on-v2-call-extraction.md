# Follow-On V2 Call Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new modular follow-on workflow example that factors the plan loop and implementation loop into reusable library workflows called from a small parent workflow, while leaving the existing monolithic v2 example in place.

**Architecture:** Keep the current `dsl_follow_on_plan_impl_review_loop_v2.yaml` unchanged as the monolithic structured example. Add a new parent example that owns only upstream waiting plus two `call` steps, and add two library workflows that each own one internal `repeat_until` loop. Reuse the existing prompt family where possible, but introduce phase-local prompt files only when the callee needs different file-path instructions than the monolith. Parameterize reusable-workflow deterministic state/output surfaces through typed `state_root` and target-path inputs so the loader accepts the callees under `call`.

**Tech Stack:** YAML workflow DSL v2.7, reusable `imports`/`call` subworkflows, existing Codex provider templates, pytest smoke tests, orchestrator dry-run validation.

---

### Task 1: Document the modular cut and file plan

**Files:**
- Create: `docs/plans/2026-03-09-follow-on-v2-call-extraction.md`
- Inspect: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`
- Inspect: `workflows/examples/call_subworkflow_demo.yaml`
- Inspect: `specs/dsl.md`
- Inspect: `docs/workflow_drafting_guide.md`

**Step 1: Confirm the cut points**

Capture the two reusable boundaries explicitly:
- plan phase: publish design, draft plan, review/revise until approve
- implementation phase: publish design + plan, execute implementation, review/fix until approve

**Step 2: Lock the reusable-call constraints**

Record the constraints that shape the extraction:
- callee outputs are the only caller-visible surface
- callee write roots and deterministic state roots should be caller-bound typed `relpath` inputs
- `repeat_until.max_iterations` is still literal-only
- provider prompt files are literal, so this example will bind canonical phase roots from the parent instead of relying on prompt-time substitution
- nested `repeat_until` inside `call` may require a small runtime fix if call-frame state persistence is missing loop-bookkeeping hooks

**Step 3: Keep the scope narrow**

Do not refactor the monolithic v2 example away. The new work adds:
- one new parent example
- two new library workflows
- only the prompt variants needed for the library form

### Task 2: Write a failing runtime smoke test for the modular parent

**Files:**
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add new example names to the load list**

Add:
- `dsl_follow_on_plan_impl_review_loop_v2_call.yaml`
- `workflows/library/follow_on_plan_phase.yaml`
- `workflows/library/follow_on_implementation_phase.yaml`

if the load test pattern requires explicit coverage.

**Step 2: Write a new failing runtime test**

Create a test named:
- `test_dsl_follow_on_plan_impl_review_loop_v2_call_runtime`

It should:
- copy the new parent example
- copy the two library workflows
- copy any prompt files they need
- bind typed inputs for the upstream state path and design path
- mock provider execution through the existing `_prepare_invocation` / `_execute` harness

**Step 3: Assert the modular behaviors**

The test should verify:
- parent workflow completes
- both call steps execute and surface only declared callee outputs
- parent workflow exports final outputs from the call steps, not from a manual adapter step
- plan and implementation loops still iterate once through revise/fix before approval
- state includes call-frame bookkeeping

**Step 4: Run the new test to watch it fail**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_dsl_follow_on_plan_impl_review_loop_v2_call_runtime -v
```

Expected: FAIL because the new workflow files do not exist yet.

### Task 3: Add the new modular parent workflow

**Files:**
- Create: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml`
- Inspect: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`

**Step 1: Start from the current v2 boundary**

Define the same typed boundary:
- inputs: `upstream_state_path`, `design_path`
- outputs: `plan_path`, `execution_report_path`, `implementation_review_report_path`, `implementation_review_decision`

**Step 2: Keep the parent small**

Parent steps should be limited to:
- wait for upstream state file
- wait for upstream completion
- `RunPlanPhase` call
- `RunImplementationPhase` call

**Step 3: Bind distinct write roots**

Bind phase-specific relpath inputs at each call site, for example:
- `state/follow-on-plan-phase`
- `state/follow-on-implementation-phase`

Also bind phase artifact roots if the library workflows expose them separately.

**Step 4: Export from call-step artifacts**

Set top-level workflow outputs from:
- `root.steps.RunPlanPhase.artifacts.*`
- `root.steps.RunImplementationPhase.artifacts.*`

Do not add a final adapter/export step.

### Task 4: Add the reusable plan-phase library workflow

**Files:**
- Create: `workflows/library/follow_on_plan_phase.yaml`
- Create or reuse prompts under: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/`

**Step 1: Define the callee interface**

Inputs should include:
- `design_path` (`relpath`, under `docs/plans`)
- `state_root` (`relpath`, under `state`)

Outputs should include:
- `plan_path`
- `plan_review_report_path`
- `plan_review_decision`

**Step 2: Initialize phase-local deterministic paths**

Add a command step that creates phase-local pointer files under `state_root`, for example:
- `${inputs.state_root}/plan_path.txt` -> `docs/plans/...`
- `${inputs.state_root}/plan_review_report_path.txt` -> `artifacts/review/...`

**Step 3: Keep the internal loop structure**

Reuse the current structured logic:
- `DraftPlan`
- `repeat_until`
  - `ReviewPlan`
  - `match(APPROVE|REVISE)`
  - `RevisePlan` on `REVISE`

**Step 4: Export only the final callee contract**

Workflow outputs should point directly at the stable producer surfaces inside the callee so the caller gets a clean output set.

### Task 5: Add the reusable implementation-phase library workflow

**Files:**
- Create: `workflows/library/follow_on_implementation_phase.yaml`
- Create or reuse prompts under: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/`

**Step 1: Define the callee interface**

Inputs should include:
- `design_path`
- `plan_path`
- `state_root`

Outputs should include:
- `execution_report_path`
- `implementation_review_report_path`
- `implementation_review_decision`

**Step 2: Initialize phase-local deterministic paths**

Create implementation pointer files under `state_root`, for example:
- `${inputs.state_root}/execution_report_path.txt` -> `artifacts/work/...`
- `${inputs.state_root}/implementation_review_report_path.txt` -> `artifacts/review/...`

**Step 3: Keep the internal loop structure**

Reuse the current structured logic:
- `ExecuteImplementation`
- `repeat_until`
  - `ReviewImplementation`
  - `match(APPROVE|REVISE)`
  - `FixImplementation` on `REVISE`

**Step 4: Export the final implementation outputs**

Expose only the final execution report, final implementation review report, and final decision.

### Task 6: Adjust prompt files only where the modular form needs it

**Files:**
- Create or modify: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/*.md`
- Inspect: `prompts/workflows/dsl_follow_on_plan_impl_loop_v2/*.md`

**Step 1: Reuse existing wording where possible**

Do not rewrite the review logic. Only change file-path instructions when the callee now uses phase-local write roots or phase-local pointer files.

**Step 2: Keep prompts task-facing**

Do not leak `call` or caller/callee mechanics into the prompts. This example may keep prompts pointed at canonical phase-local state paths because the parent binds those exact roots explicitly.

**Step 3: Keep review/fix completeness rules**

Retain the current implementation-review priority:
- unfinished required plan work is blocking
- implemented-portion issues matter when they block forward progress

### Task 7: Update workflow docs and example catalog

**Files:**
- Modify: `workflows/README.md`

**Step 1: Add the new parent example**

Document it as the modular/library-oriented variant of the monolithic v2 example.

**Step 2: Add the library workflows if the catalog lists them**

If the catalog currently documents library workflows, add short entries for the two new reusable phase workflows.

### Task 8: Run verification

**Files:**
- Test: `tests/test_workflow_examples_v0.py`

**Step 1: Collect tests if the module changed materially**

Run:

```bash
pytest --collect-only tests/test_workflow_examples_v0.py -q
```

**Step 2: Run the narrow new test**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_dsl_follow_on_plan_impl_review_loop_v2_call_runtime -v
```

**Step 3: Run the load test**

Run:

```bash
pytest tests/test_workflow_examples_v0.py::test_workflow_examples_v0_load -v
```

**Step 4: Run a narrow combined selector**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "follow_on_plan_impl_review_loop_v2_call or workflow_examples_v0_load" -v
```

**Step 5: Run an orchestrator dry-run smoke check**

Run:

```bash
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml \
  --dry-run \
  --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json \
  --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md \
  --stream-output
```

**Step 6: Run diff hygiene**

Run:

```bash
git diff --check
```

### Task 9: Summarize the modularity tradeoff in the final handoff

**Files:**
- No file changes required

**Step 1: Record what changed**

Call out:
- new parent example
- new plan-phase library
- new implementation-phase library
- minimal runtime fix for `repeat_until` persistence inside call frames
- prompt adjustments
- test coverage

**Step 2: Record what improved**

Summarize the real modularity gain:
- parent workflow is smaller
- plan and implementation loops are independently reusable
- final outputs flow through call-step exports instead of a manual adapter step

**Step 3: Record remaining limits**

Be explicit about any remaining constraints, especially:
- literal-only `repeat_until.max_iterations`
- any prompt/path indirection still needed because prompt files are literal
