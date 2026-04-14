# Major Project Tranche Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Do not create a git worktree in this repository.

**Goal:** Add a reusable workflow family for major backlog items that first produces an approved project roadmap and tranche manifest, then runs one selected tranche through big-design, normal plan, and normal implementation phases.

**Architecture:** Add one roadmap phase workflow, one big-design phase workflow, one tranche stack workflow, and one runnable example driver. The runnable driver must call the roadmap phase first, then select one ready tranche from the generated manifest and call the tranche stack. Reuse the existing tracked plan and implementation phase workflows by making the approved big-design document self-contained enough for downstream plan/implementation phases. Keep prompt judgment in prompt files and deterministic selection, routing, validation, and artifact paths in workflow YAML. Put manifest shape/path/prerequisite validation in a deterministic helper so workflow command steps and tests exercise the same contract.

**Tech Stack:** Agent-orchestration DSL v2.7, reusable `call` workflows, Codex provider prompts, JSON output contracts, deterministic Python manifest validation, pytest workflow example tests, mocked-provider runtime smoke tests, orchestrator dry-run validation.

---

## File Structure

Create:

- `workflows/library/major_project_roadmap_phase.yaml` - reusable roadmap/review/revise phase for broad project briefs.
- `workflows/library/tracked_big_design_phase.yaml` - reusable big-design/review/revise phase for one selected tranche.
- `workflows/library/major_project_tranche_design_plan_impl_stack.yaml` - reusable tranche stack that calls big design, tracked plan, and implementation phases.
- `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml` - runnable example driver that generates the manifest by calling the roadmap phase.
- `workflows/examples/inputs/major_project_brief.md` - small fixture broad brief.
- `workflows/library/prompts/major_project_stack/draft_project_roadmap.md`
- `workflows/library/prompts/major_project_stack/review_project_roadmap.md`
- `workflows/library/prompts/major_project_stack/revise_project_roadmap.md`
- `workflows/library/prompts/major_project_stack/draft_big_design.md`
- `workflows/library/prompts/major_project_stack/review_big_design.md`
- `workflows/library/prompts/major_project_stack/revise_big_design.md`
- `workflows/library/scripts/validate_major_project_tranche_manifest.py` - shared deterministic validator for roadmap-phase manifest command steps and unit tests.
- `tests/test_major_project_workflows.py`
- `tests/test_major_project_manifest_validator.py`

Modify:

- `workflows/README.md` - index new library workflows and example.
- `prompts/README.md` - index new prompt family.
- `docs/workflow_prompt_map.md` - update prompt map after adding workflows.
- `tests/test_workflow_examples_v0.py` - add the runnable example to the shared example load registry.

Do not modify:

- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`

## Task 1: Add Workflow Contract Tests

**Files:**

- Create: `tests/test_major_project_workflows.py`
- Create: `tests/test_major_project_manifest_validator.py`

- [x] **Step 1: Write tests for workflow presence and import shape**

Add tests that assert the expected new files exist, that the tranche stack imports `tracked_big_design_phase.yaml`, `tracked_plan_phase.yaml`, and `design_plan_impl_implementation_phase.yaml`, and that the runnable example imports both the roadmap phase and the tranche stack.

Example structure:

```python
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_major_project_workflow_files_exist():
    for relpath in [
        "workflows/library/major_project_roadmap_phase.yaml",
        "workflows/library/tracked_big_design_phase.yaml",
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
        "workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml",
    ]:
        assert (ROOT / relpath).is_file(), relpath


def test_tranche_stack_reuses_existing_plan_and_implementation_phases():
    workflow = _load_yaml(ROOT / "workflows/library/major_project_tranche_design_plan_impl_stack.yaml")
    assert workflow["imports"] == {
        "big_design_phase": "tracked_big_design_phase.yaml",
        "plan_phase": "tracked_plan_phase.yaml",
        "implementation_phase": "design_plan_impl_implementation_phase.yaml",
    }


def test_example_calls_roadmap_before_selected_tranche_stack():
    workflow = _load_yaml(ROOT / "workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml")
    assert workflow["imports"] == {
        "roadmap_phase": "../library/major_project_roadmap_phase.yaml",
        "tranche_stack": "../library/major_project_tranche_design_plan_impl_stack.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "RunRoadmapPhase",
        "SelectNextTranche",
        "RunSelectedTranche",
    ]
```

- [x] **Step 2: Write tests for prompt references and contract surfaces**

Assert that roadmap and big-design phases use `asset_file` paths under `prompts/major_project_stack/`.

Do not assert literal prompt text or exact prompt phrasing. Tests should assert stable workflow contracts such as `asset_file`, `consumes`, `prompt_consumes`, `expected_outputs`, `output_bundle`, call inputs, and exported outputs. Review prompt quality manually as part of implementation review.

- [x] **Step 3: Write tests for consumed context and self-contained big design**

Assert that `DraftBigDesign` prompt consumes or otherwise receives the selected tranche brief, project brief, project roadmap, and tranche manifest artifacts.

Also assert the workflow contract that supports the self-contained downstream design requirement: `DraftBigDesign`, `ReviewBigDesign`, and `ReviseBigDesign` consume the selected-tranche, project-brief, roadmap, manifest, design, review, and open-finding artifacts needed at each step, while the downstream generic plan and implementation calls remain narrow and receive only design/plan artifacts.

- [x] **Step 4: Write tests for deterministic manifest and selector contracts**

Assert that the roadmap phase contains a manifest validation command step after initial draft and after roadmap revision, and that both validation steps invoke `workflows/library/scripts/validate_major_project_tranche_manifest.py` rather than carrying divergent inline validator copies.

Add focused validator tests for:

- valid manifest
- duplicate tranche IDs
- unknown prerequisite
- cyclic prerequisites
- path escape such as `../outside.md`
- missing tranche brief file
- bad `status`, `design_depth`, or `completion_gate`
- pending tranche with an incomplete prerequisite is not counted as ready

Assert that the example driver has a `SelectNextTranche` or equivalent command step with an `output_bundle` publishing at least:

- `selection_status` as enum `SELECTED`
- `project_brief_path`
- `project_roadmap_path`
- `tranche_manifest_path`
- `tranche_brief_path`
- `item_state_root`
- `big_design_phase_state_root`
- `plan_phase_state_root`
- `implementation_phase_state_root`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`

The first driver does not route `NONE_READY` or `BLOCKED`. If no pending tranche has satisfied prerequisites, the selector command should fail before writing the selection bundle and before calling the tranche stack.

- [x] **Step 5: Write a mocked-provider runtime smoke test**

Add a runtime test, modeled on the existing `WorkflowExecutor`/`ProviderExecutor` patch tests in `tests/test_workflow_examples_v0.py`, that copies the new example and library workflows into a temporary workspace, mocks provider outputs, and executes the workflow far enough to prove:

- roadmap draft writes a roadmap, manifest, and tranche brief
- roadmap review approves
- `SelectNextTranche` parses the generated manifest and validates the output bundle
- the tranche stack call receives selected-tranche paths from the selector artifacts
- big-design, plan, and implementation phases can complete with mocked provider writers
- root workflow outputs expose the selected tranche stack's item outcome, execution report path, and item summary path

This smoke test must exercise runtime output-contract substitution and call-frame output export; loader validation or `--dry-run` is not a substitute.

- [x] **Step 6: Run collect-only and confirm tests fail**

Run:

```bash
pytest --collect-only tests/test_major_project_workflows.py
pytest tests/test_major_project_manifest_validator.py tests/test_major_project_workflows.py -q
```

Expected: collection succeeds; tests fail because files do not exist yet.

## Task 2: Implement `major_project_roadmap_phase.yaml`

**Files:**

- Create: `workflows/library/major_project_roadmap_phase.yaml`
- Create: `workflows/library/prompts/major_project_stack/draft_project_roadmap.md`
- Create: `workflows/library/prompts/major_project_stack/review_project_roadmap.md`
- Create: `workflows/library/prompts/major_project_stack/revise_project_roadmap.md`
- Create: `workflows/library/scripts/validate_major_project_tranche_manifest.py`

- [x] **Step 1: Create prompt directory**

Create `workflows/library/prompts/major_project_stack/`.

- [x] **Step 2: Draft roadmap prompt**

The prompt must tell the provider to:

- read `Consumed Artifacts` first
- treat `project_brief` as the broad input
- read `docs/index.md` first when present and use it to select relevant specs, architecture docs, workflow guides, and findings docs
- produce a project roadmap markdown file
- produce a tranche manifest JSON file
- avoid implementation
- avoid drafting full designs for every tranche
- create standalone tranche brief files when requested by the output contract
- make every generated tranche brief standalone enough to feed the big-design phase without requiring the provider to rediscover the whole project

- [x] **Step 3: Draft roadmap review prompt**

The review prompt must enforce:

- coherent sequential tranches
- explicit prerequisites
- no hidden architecture/API/oracle/data-flow decisions
- tranches are independently designable and verifiable
- generated tranche briefs can feed a design phase
- manifest entries include all required paths, prerequisites, status, design depth, and completion gate fields
- JSON review output with stable findings and `APPROVE`, `REVISE`, or `BLOCK`

- [x] **Step 4: Draft roadmap revise prompt**

The revise prompt must consume the roadmap, manifest, brief, review report, and open findings. It should revise the roadmap and manifest without implementing source changes.

- [x] **Step 5: Create the manifest validator helper**

Create `workflows/library/scripts/validate_major_project_tranche_manifest.py` as a small deterministic CLI that accepts:

```bash
python workflows/library/scripts/validate_major_project_tranche_manifest.py \
  --project-brief-path <relpath> \
  --project-roadmap-pointer <state/.../project_roadmap_path.txt> \
  --tranche-manifest-pointer <state/.../tranche_manifest_path.txt> \
  --state-root <state/...>
```

The helper should:

- read the roadmap and manifest paths from the pointer files
- validate the roadmap path is under `docs/plans` and exists
- validate the manifest path is under `state` and contains JSON object content
- validate the manifest `project_brief_path` and `project_roadmap_path` match the current inputs
- validate a non-empty `project_id`
- validate a non-empty `tranches` list
- validate required tranche fields, unique `tranche_id` values, and path-safe tranche IDs
- validate all generated paths stay under their intended roots
- validate `brief_path` exists
- validate prerequisites reference known tranche IDs and are acyclic
- validate `status`, `design_depth`, and `completion_gate` against explicit allowed sets
- write `validated_tranche_count.txt` and `ready_tranche_count.txt` under `state_root`

Define a ready tranche as `status: "pending"` with every prerequisite tranche in a completed status (`done`, `completed`, or `approved`). `ready_tranche_count.txt` must not count pending tranches whose prerequisites are still pending or blocked.

First-tranche allowed values:

- `status`: `pending`, `blocked`, `done`, `completed`, `approved`
- `design_depth`: `big`, `standard`
- `completion_gate`: `implementation_approved`

Use these same constants in the roadmap prompt, validator helper, and validator tests. Do not let the YAML command step, prompt prose, and tests each invent their own enum list.

Keep this helper free of provider/prompt logic. It is the deterministic runtime contract for roadmap-manifest shape.

- [x] **Step 6: Create the phase workflow**

Model it on `workflows/library/tracked_design_phase.yaml`.

Required inputs:

- `state_root`
- `project_brief_path`
- `project_roadmap_target_path`
- `tranche_manifest_target_path`
- `roadmap_review_report_target_path`

Required outputs:

- `project_roadmap_path`
- `tranche_manifest_path`
- `roadmap_review_report_path`
- `roadmap_review_decision`

Use a `repeat_until` review loop with `max_iterations: 20`.

Route `APPROVE` out of the loop, route `REVISE` through the revise/validate path, and route `BLOCK` to an immediate phase failure/finalization path. Do not allow `BLOCK` to spin until the iteration cap.

- [x] **Step 7: Add deterministic manifest validation**

Add a command step that validates the generated manifest immediately after `DraftProjectRoadmap` and after every `ReviseProjectRoadmap`, before the next review or finalization can proceed.

The validation steps must call `workflows/library/scripts/validate_major_project_tranche_manifest.py` with the current pointers and fail the workflow on invalid manifest shape. The helper should check:

- manifest is a JSON object with a non-empty `project_id`
- `tranches` is a non-empty list
- every tranche has `tranche_id`, `title`, `brief_path`, `design_target_path`, `design_review_report_target_path`, `plan_target_path`, `plan_review_report_target_path`, `execution_report_target_path`, `implementation_review_report_target_path`, `item_summary_target_path`, `prerequisites`, `status`, `design_depth`, and `completion_gate`
- tranche ids are unique
- prerequisites reference known tranche ids and are acyclic
- `brief_path` files exist
- `brief_path`, `design_target_path`, `plan_target_path`, and report paths stay under the intended workspace-relative roots
- `status`, `design_depth`, and `completion_gate` values match the first-tranche allowed sets defined above

The validation step may write a small JSON report under `state_root`, but the important contract is that invalid manifests fail before review approval or downstream tranche selection.

- [x] **Step 8: Run validation**

Run:

```bash
python -m orchestrator run workflows/library/major_project_roadmap_phase.yaml --dry-run
```

Expected: dry-run validation succeeds or fails only because required inputs are absent. If direct dry-run cannot validate input-required library workflows, validate through the example driver after Task 4.

## Task 3: Implement `tracked_big_design_phase.yaml`

**Files:**

- Create: `workflows/library/tracked_big_design_phase.yaml`
- Create: `workflows/library/prompts/major_project_stack/draft_big_design.md`
- Create: `workflows/library/prompts/major_project_stack/review_big_design.md`
- Create: `workflows/library/prompts/major_project_stack/revise_big_design.md`

- [x] **Step 1: Draft big-design prompt**

The prompt must tell the provider to consume:

- selected tranche brief
- project brief
- approved project roadmap
- tranche manifest

The prompt must ask for deeper design sections where relevant:

- ADR or architecture decision
- type-driven interfaces
- data flow and ownership
- module/package boundaries
- source-of-truth, oracle, and provenance contracts
- spec and documentation updates
- migration and compatibility strategy
- performance and batching implications
- verification strategy
- sequencing constraints and non-goals

The prompt must also require a self-contained downstream contract section. Because `tracked_plan_phase.yaml` consumes only the approved design and `design_plan_impl_implementation_phase.yaml` consumes only the approved design plus approved plan, the big-design document must carry the project context needed later:

- selected tranche brief summary and exact tranche id
- relevant manifest fields, including prerequisites, status assumptions, design depth, completion gate, and target artifact paths
- roadmap constraints that the tranche must preserve
- repo docs/specs/findings consulted and their bearing on the tranche
- prerequisite evidence or explicit blocked assumptions
- verification strategy and completion evidence expected from implementation
- deferred work and non-goals for later tranches

- [x] **Step 2: Draft big-design review prompt**

The review prompt must reject designs that:

- do not justify semantically material choices
- conflict with the project roadmap without explaining why
- are not self-contained enough for the generic plan and implementation phases to use without separately consuming the roadmap or manifest
- omit necessary data contracts, interfaces, or ownership
- omit spec/doc updates required by the tranche
- propose implementation before blocking design decisions are resolved
- provide weak verification for the tranche risk

- [x] **Step 3: Draft big-design revise prompt**

The revise prompt must revise only the tranche design, preserve the approved roadmap unless explicitly explaining a necessary conflict, keep open findings reconciled, and maintain the self-contained downstream contract section.

- [x] **Step 4: Create the phase workflow**

Model it on `tracked_design_phase.yaml`, but add artifacts and inputs for:

- `project_brief`
- `project_roadmap`
- `tranche_manifest`

Keep the same output names as tracked design where possible:

- `design_path`
- `design_review_report_path`
- `design_review_decision`

Use a `repeat_until` review loop with `max_iterations: 20`. Route `APPROVE` out of the loop, route `REVISE` through the revise path, and route `BLOCK` to an immediate phase failure/finalization path. Do not allow `BLOCK` to spin until the iteration cap.

- [x] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_major_project_workflows.py -q
```

Expected: tests for file presence and prompt references pass once Task 2 and Task 3 are complete.

## Task 4: Implement Tranche Stack and Example Driver

**Files:**

- Create: `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- Create: `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
- Create: `workflows/examples/inputs/major_project_brief.md`

- [x] **Step 1: Create tranche stack workflow**

Model it on `backlog_item_design_plan_impl_stack.yaml`.

Imports:

```yaml
imports:
  big_design_phase: tracked_big_design_phase.yaml
  plan_phase: tracked_plan_phase.yaml
  implementation_phase: design_plan_impl_implementation_phase.yaml
```

The stack inputs should include:

- `item_state_root`
- `big_design_phase_state_root`
- `plan_phase_state_root`
- `implementation_phase_state_root`
- `project_brief_path`
- `project_roadmap_path`
- `tranche_manifest_path`
- `tranche_brief_path`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`

- [x] **Step 2: Call big-design phase**

Pass selected tranche and project context to `tracked_big_design_phase.yaml`.

- [x] **Step 3: Reuse tracked plan phase**

Pass:

- design path from `RunBigDesignPhase`
- plan target path
- plan review report target path

Do not fork the generic plan phase.

The plan phase receives only the approved big-design path. This is intentional; the big-design review gate must guarantee that the design contains the relevant selected-tranche, roadmap, manifest, prerequisite, and completion-gate context.

- [x] **Step 4: Reuse implementation phase**

Pass:

- design path from `RunBigDesignPhase`
- plan path from `RunPlanPhase`
- execution report target path
- implementation review report target path

Do not fork the generic implementation phase.

The implementation phase receives only the approved design and approved plan. Do not add project-roadmap or manifest inputs to this phase unless a concrete downstream failure proves the self-contained design contract is insufficient.

- [x] **Step 5: Create example fixture inputs**

Create a minimal broad project brief that can be decomposed by the roadmap phase into one or two synthetic tranches. Keep the fixture small and repo-local.

Do not provide a pre-baked manifest fixture to the runnable example. The example must generate the manifest through `RunProjectRoadmapPhase` so the roadmap phase is exercised end-to-end.

- [x] **Step 6: Create runnable example driver**

The example should:

- import `roadmap_phase: ../library/major_project_roadmap_phase.yaml`
- import `tranche_stack: ../library/major_project_tranche_design_plan_impl_stack.yaml`
- call `RunRoadmapPhase` using `workflows/examples/inputs/major_project_brief.md`
- write roadmap output to a repo-local `docs/plans/...` path and manifest output to a repo-local `state/...` path
- select one pending tranche with prerequisites satisfied from the generated manifest
- prepare unique state and artifact roots
- publish the selected tranche inputs through a typed `output_bundle`
- publish `selection_status` as typed enum `SELECTED`
- validate `tranche_id` as a path-safe slug before using it to derive state roots; do not publish it as a relpath artifact
- fail with a clear message before writing the output bundle if no tranche is ready in the first driver
- call `major_project_tranche_design_plan_impl_stack.yaml` only for the selected tranche

Do not implement drain-all behavior in the first example.

The selector should be deterministic and small for this first example. It should not expose `NONE_READY` or `BLOCKED` routing yet, because the first driver has no non-selected branch and should fail fast if no selected tranche exists. More flexible or agent-assisted tranche selection can be added later after the roadmap/manifest and one-tranche execution contracts are proven.

## Task 5: Update Indexes and Prompt Map

**Files:**

- Modify: `workflows/README.md`
- Modify: `prompts/README.md`
- Modify: `docs/workflow_prompt_map.md`

- [x] **Step 1: Update workflow index**

Add entries for:

- `workflows/library/major_project_roadmap_phase.yaml`
- `workflows/library/tracked_big_design_phase.yaml`
- `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`

- [x] **Step 2: Update prompt index**

Add a `major_project_stack/` prompt family entry and short descriptions for roadmap and big-design prompts.

- [x] **Step 3: Regenerate or update prompt map**

If this repo has a prompt-map generation command, use it. Otherwise update `docs/workflow_prompt_map.md` manually and run the relevant tests.

`scripts/workflow_prompt_map.py` uses `git ls-files` when run inside a git repository, so newly created workflow YAML is invisible until tracked or staged. Stage the new workflow and prompt files before regenerating/checking the prompt map, or explicitly defer prompt-map regeneration until staging.

Find generation commands with:

```bash
rg -n "workflow_prompt_map|Prompt Map|prompt map" .
```

Important: `scripts/workflow_prompt_map.py` discovers git-tracked workflow YAML with `git ls-files`. Stage the newly created workflow and prompt files before regenerating or checking the prompt map, or the new entries may be missing even though the files exist in the worktree.

## Task 6: Verification

**Files:**

- All files from Tasks 1-5.

- [x] **Step 1: Run unit tests**

Run:

```bash
pytest --collect-only tests/test_major_project_workflows.py
pytest --collect-only tests/test_major_project_manifest_validator.py
pytest tests/test_major_project_manifest_validator.py tests/test_major_project_workflows.py -q
```

Expected: collection succeeds and tests pass.

- [x] **Step 2: Run workflow dry-run**

Run:

```bash
python -m orchestrator run workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml --dry-run
```

Expected: workflow validation succeeds.

- [x] **Step 3: Run the mocked-provider runtime smoke**

Run:

```bash
pytest tests/test_major_project_workflows.py::test_major_project_example_runtime_with_mocked_providers -q
```

Expected: pass. This smoke must execute the new example through `WorkflowExecutor` with mocked provider writers and prove runtime output-contract substitution, `output_bundle` parsing, call-frame output export, and root outputs. Do not replace this with `--dry-run`; dry-run validates schema and dependencies but not post-execution contract behavior.

- [x] **Step 4: Run existing workflow example tests**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -q
```

Expected: pass.

- [x] **Step 5: Run full relevant test subset**

Run:

```bash
pytest tests/test_major_project_manifest_validator.py tests/test_major_project_workflows.py tests/test_workflow_examples_v0.py -q
```

Expected: pass.

- [x] **Step 6: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [x] **Step 7: Check prompt map freshness**

Run after new workflow/prompt files have been staged:

```bash
python scripts/workflow_prompt_map.py --check
```

Expected: pass. If stale, run `python scripts/workflow_prompt_map.py`, inspect the diff, and rerun `--check`.

- [x] **Step 8: Record follow-up for EasySpin**

Do not launch an EasySpin workflow from this implementation plan unless explicitly requested. If launching later, run from `/home/ollie/Documents/EasySpin`, activate `ptycho311`, and invoke `python -m orchestrator` directly so tmux streams output.
