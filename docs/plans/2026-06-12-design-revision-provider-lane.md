# Design Revision Provider Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated provider/model/effort lane for blocked design-revision work in the Design Delta drain so `ReviseBlockedDesignGap` can use `claude-fable-5` without changing ordinary implementation execution or review routing.

**Architecture:** Treat provider choice as a task-role contract, not as incidental reuse of the implementation executor lane. The top-level drain gets local provider aliases plus `design_revision_provider`, `design_revision_model`, and `design_revision_effort` inputs; only the blocked target/gap/prerequisite design revision step consumes the new lane. Existing implementation execute/review provider inputs continue to route work-item implementation and review.

**Tech Stack:** YAML workflow DSL v2.14, built-in provider registry, `pytest`, `pyyaml`, `python -m orchestrator run --dry-run`.

---

## Context

The current top-level workflow at `workflows/examples/lisp_frontend_design_delta_drain.yaml` routes `ReviseBlockedDesignGap` through:

```yaml
provider: ${inputs.implementation_execute_provider}
```

That is the wrong abstraction. The step revises target/gap/prerequisite design material after blocked-recovery classification; it is not ordinary implementation execution. Switching `implementation_execute_provider` to reach this step would also affect selected-item implementation routes. The correct change is a separate design-revision provider lane.

Current relevant facts:

- `design_gap_draft_provider/model/effort` already exists for first-pass design gap drafting.
- `implementation_execute_provider` is used for work-item execution and should remain scoped to that work.
- `implementation_review_provider` is used for review gates and should remain scoped to review.
- The imported design-gap architect workflow defines local `codex` and `claude` providers whose parameter names are `model` and `effort`.
- The top-level drain currently has no local `providers:` block, which makes `implementation_*_provider=claude_opus` fragile for top-level blocked-recovery review steps because `claude_opus` is not a built-in provider alias.
- The top-level drain should define local `codex`, `claude`, and `claude_opus` aliases so provider-role inputs are self-contained and `design_revision_effort` maps consistently to `--effort` / `reasoning_effort`.

## File Structure

- Modify `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Add local provider aliases for `codex`, `claude`, and `claude_opus` if the top-level workflow still lacks a `providers:` block.
  - Add top-level inputs for the design-revision lane.
  - Rewire only `ReviseBlockedDesignGap` to the new lane.
  - Add `provider_params` for model/effort on the design-revision step.

- Modify `tests/test_provider_role_routing.py`
  - Add a focused workflow-contract test that confirms `ReviseBlockedDesignGap` uses `design_revision_*` and no longer consumes `implementation_execute_provider`.
  - Add a provider-template coverage test that confirms the top-level workflow defines every provider alias its provider inputs allow.

- Optionally modify `workflows/README.md`
  - Only if the workflow catalog or run notes currently document provider-role inputs for this drain. Do not add generic prose if there is no existing matching entry.

## Task 1: Add Failing Provider-Role Contract Tests

**Files:**
- Modify: `tests/test_provider_role_routing.py`

- [ ] **Step 1: Add a helper to find nested steps**

Add this helper near the existing YAML-focused tests:

```python
def _walk_yaml_steps(steps):
    for step in steps:
        yield step
        if isinstance(step.get("steps"), list):
            yield from _walk_yaml_steps(step["steps"])

        repeat = step.get("repeat_until")
        if isinstance(repeat, dict):
            yield from _walk_yaml_steps(repeat.get("steps", []))
            on_exhausted = repeat.get("on_exhausted")
            if isinstance(on_exhausted, dict):
                yield from _walk_yaml_steps(on_exhausted.get("steps", []))

        match = step.get("match")
        if isinstance(match, dict):
            cases = match.get("cases") or {}
            for case in cases.values():
                if isinstance(case, dict):
                    yield from _walk_yaml_steps(case.get("steps", []))
                elif isinstance(case, list):
                    yield from _walk_yaml_steps(case)


def _load_design_delta_drain_yaml() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text(
            encoding="utf-8"
        )
    )


def _yaml_step_by_id(workflow: dict, step_id: str) -> dict:
    return next(step for step in _walk_yaml_steps(workflow["steps"]) if step.get("id") == step_id)
```

- [ ] **Step 2: Add the failing provider-template coverage test**

Add:

```python
def test_design_delta_top_level_provider_aliases_cover_provider_inputs():
    workflow = _load_design_delta_drain_yaml()

    providers = workflow["providers"]
    assert set(providers) >= {"codex", "claude", "claude_opus"}

    for input_name in (
        "implementation_execute_provider",
        "implementation_review_provider",
        "design_revision_provider",
    ):
        for provider_name in workflow["inputs"][input_name]["allowed"]:
            assert provider_name in providers

    assert providers["codex"]["defaults"] == {
        "model": "${context.workflow_model}",
        "effort": "${context.workflow_effort}",
    }
    assert providers["claude"]["defaults"] == {
        "model": "claude-fable-5",
        "effort": "high",
    }
    assert providers["claude_opus"]["defaults"] == {
        "model": "opus",
        "effort": "high",
    }
```

This fails before implementation because the top-level drain currently lacks a `providers:` block.

- [ ] **Step 3: Add the failing role-lane test**

Add:

```python
def test_design_delta_blocked_design_revision_uses_dedicated_provider_lane():
    workflow = _load_design_delta_drain_yaml()
    inputs = workflow["inputs"]

    assert inputs["design_revision_provider"] == {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["codex", "claude"],
        "default": "claude",
    }
    assert inputs["design_revision_model"] == {
        "kind": "scalar",
        "type": "string",
        "default": "claude-fable-5",
    }
    assert inputs["design_revision_effort"] == {
        "kind": "scalar",
        "type": "string",
        "default": "high",
    }

    revise = _yaml_step_by_id(workflow, "revise_blocked_design_gap")
    assert revise["provider"] == "${inputs.design_revision_provider}"
    assert revise["provider_params"] == {
        "model": "${inputs.design_revision_model}",
        "effort": "${inputs.design_revision_effort}",
    }
    assert revise["input_file"] == (
        "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
        "revise_prior_blocked_design_gap.md"
    )
```

- [ ] **Step 4: Run the failing tests**

Run:

```bash
pytest tests/test_provider_role_routing.py::test_design_delta_top_level_provider_aliases_cover_provider_inputs tests/test_provider_role_routing.py::test_design_delta_blocked_design_revision_uses_dedicated_provider_lane -q
```

Expected:

- `test_design_delta_top_level_provider_aliases_cover_provider_inputs` fails because the workflow does not yet define local provider aliases.
- `test_design_delta_blocked_design_revision_uses_dedicated_provider_lane` fails because the workflow does not yet define `design_revision_*` and the step still uses `${inputs.implementation_execute_provider}`.

## Task 2: Add Local Top-Level Provider Aliases

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`

- [ ] **Step 1: Add a top-level `providers:` block before `artifacts:`**

Insert after `outputs:` and before `artifacts:` if the workflow still has no top-level provider definitions:

```yaml
providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model", "${model}", "--config", "reasoning_effort=${effort}"]
    input_mode: "stdin"
    defaults:
      model: "${context.workflow_model}"
      effort: "${context.workflow_effort}"
  claude:
    command: ["claude", "-p", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    input_mode: "stdin"
    defaults:
      model: "claude-fable-5"
      effort: "high"
  claude_opus:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    input_mode: "argv"
    defaults:
      model: "opus"
      effort: "high"
```

The `claude` shape mirrors the design-gap architect workflow's local provider and accepts prompt input on stdin. `claude_opus` preserves the existing allowed implementation provider alias for any top-level blocked-recovery review route that selects it.

- [ ] **Step 2: Run provider-template coverage test**

Run:

```bash
pytest tests/test_provider_role_routing.py::test_design_delta_top_level_provider_aliases_cover_provider_inputs -q
```

Expected: still fails because the `design_revision_provider` input has not been added yet.

## Task 3: Add The Design-Revision Inputs

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`

- [ ] **Step 1: Add the new role inputs after `design_gap_draft_effort`**

Insert:

```yaml
  design_revision_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude"]
    default: "claude"
  design_revision_model:
    kind: scalar
    type: string
    default: "claude-fable-5"
  design_revision_effort:
    kind: scalar
    type: string
    default: "high"
```

Keep the existing `implementation_execute_provider` and `implementation_review_provider` inputs unchanged.

- [ ] **Step 2: Run the focused tests**

Run:

```bash
pytest tests/test_provider_role_routing.py::test_design_delta_top_level_provider_aliases_cover_provider_inputs tests/test_provider_role_routing.py::test_design_delta_blocked_design_revision_uses_dedicated_provider_lane -q
```

Expected: provider-template coverage passes; the role-lane test still fails because `ReviseBlockedDesignGap` has not been rewired yet.

## Task 4: Rewire Only `ReviseBlockedDesignGap`

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`

- [ ] **Step 1: Change the provider lane**

In the `ReviseBlockedDesignGap` step, replace:

```yaml
          provider: ${inputs.implementation_execute_provider}
```

with:

```yaml
          provider: ${inputs.design_revision_provider}
          provider_params:
            model: ${inputs.design_revision_model}
            effort: ${inputs.design_revision_effort}
```

- [ ] **Step 2: Do not change unrelated lanes**

Confirm these remain unchanged:

```yaml
RunSelectedBacklogItem.with.implementation_execute_provider: inputs.implementation_execute_provider
RunDesignGapWorkItem.with.implementation_execute_provider: inputs.implementation_execute_provider
RunDoneReview.with.implementation_execute_provider: inputs.implementation_execute_provider
ReviewBlockedTargetDesignRevision.provider: ${inputs.implementation_review_provider}
```

Rationale: the reviser is now independently steerable, while implementation and review still use their role-specific lanes.

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest tests/test_provider_role_routing.py::test_design_delta_top_level_provider_aliases_cover_provider_inputs tests/test_provider_role_routing.py::test_design_delta_blocked_design_revision_uses_dedicated_provider_lane -q
```

Expected: both pass.

## Task 5: Add A Runtime Resolution Regression Test

**Files:**
- Modify: `tests/test_provider_role_routing.py`

- [ ] **Step 1: Add a test that provider params resolve to Fable**

Add a small workflow-level assertion rather than mocking a full blocked-recovery route:

```python
def test_design_delta_design_revision_lane_defaults_to_claude_fable_params():
    workflow = _load_design_delta_drain_yaml()
    revise = _yaml_step_by_id(workflow, "revise_blocked_design_gap")

    assert workflow["inputs"]["design_revision_provider"]["default"] == "claude"
    assert workflow["inputs"]["design_revision_model"]["default"] == "claude-fable-5"
    assert workflow["inputs"]["design_revision_effort"]["default"] == "high"
    assert revise["provider"] == "${inputs.design_revision_provider}"
    assert revise["provider_params"]["model"] == "${inputs.design_revision_model}"
    assert revise["provider_params"]["effort"] == "${inputs.design_revision_effort}"
```

This protects the exact failure mode: future edits should not silently route design revision back to the implementation executor or drop the model override.

- [ ] **Step 2: Run provider-role tests**

Run:

```bash
pytest tests/test_provider_role_routing.py -q
```

Expected: all tests in the file pass.

## Task 6: Validate The Workflow Still Loads And Dry-Runs

**Files:**
- No edits.

- [ ] **Step 1: Run YAML/provider role checks**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_drain_checks_blocked_recovery_before_selection tests/test_lisp_frontend_autonomous_drain_runtime.py::test_blocked_target_design_revision_review_report_path_is_command_owned -q
```

Expected: pass. These tests cover the surrounding blocked-recovery route shape and review-report target handling.

- [ ] **Step 2: Run a workflow dry-run**

Run from repo root:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run \
  --input steering_path=docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md \
  --input target_design_path=docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input progress_ledger_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain \
  --input run_state_target_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN \
  --input architecture_index_root=docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps \
  --input design_gap_draft_provider=claude \
  --input design_gap_draft_model=claude-fable-5 \
  --input design_gap_draft_effort=high \
  --input design_revision_provider=claude \
  --input design_revision_model=claude-fable-5 \
  --input design_revision_effort=high
```

Expected: workflow validation/dry-run succeeds without resolving an unknown provider or unknown input.

If this command reports that `provider_params` is unsupported for top-level provider steps, stop and fix the runtime/workflow shape intentionally. Do not remove the model/effort lane silently. The acceptable fallback is to define a local top-level provider alias such as `claude_fable` and make `design_revision_provider` choose that alias, but only after adding a test that proves the model choice remains explicit and role-scoped.

## Task 7: Optional Documentation Update

**Files:**
- Maybe modify: `workflows/README.md`

- [ ] **Step 1: Search for this workflow in the catalog**

Run:

```bash
rg -n "lisp_frontend_design_delta_drain|design delta drain|implementation_execute_provider|design_gap_draft_provider" workflows/README.md
```

- [ ] **Step 2: Update only matching provider-role prose**

If the catalog documents provider-role inputs for this workflow, add `design_revision_provider/model/effort` to that entry. If it only catalogs the workflow path, make no documentation change.

- [ ] **Step 3: Run the provider-role tests again if docs were changed**

Run:

```bash
pytest tests/test_provider_role_routing.py -q
```

Expected: pass.

## Task 8: Final Verification And Commit

**Files:**
- Modified workflow and tests, plus optional docs.

- [ ] **Step 1: Run the focused test set**

Run:

```bash
pytest tests/test_provider_role_routing.py tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_drain_checks_blocked_recovery_before_selection tests/test_lisp_frontend_autonomous_drain_runtime.py::test_blocked_target_design_revision_review_report_path_is_command_owned -q
```

Expected: pass.

- [ ] **Step 2: Run dry-run validation one final time**

Run the `python -m orchestrator run ... --dry-run` command from Task 5.

Expected: pass.

- [ ] **Step 3: Inspect the diff**

Run:

```bash
git diff -- workflows/examples/lisp_frontend_design_delta_drain.yaml tests/test_provider_role_routing.py workflows/README.md
```

Expected:

- `ReviseBlockedDesignGap` is the only top-level step whose provider lane changes.
- Work-item implementation calls still pass `implementation_execute_provider`.
- `ReviewBlockedTargetDesignRevision` still uses `implementation_review_provider`.
- No prompt text changed.

- [ ] **Step 4: Commit**

Run:

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml tests/test_provider_role_routing.py workflows/README.md
git commit -m "route design revision through dedicated provider lane"
```

If `workflows/README.md` was not changed, omit it from `git add`.

## Non-Goals

- Do not change the active run in place as part of this implementation. After the workflow YAML is committed, relaunching or resuming a workflow is an operational decision.
- Do not route `ReviewBlockedTargetDesignRevision` through the new lane unless a separate review-lane decision is made.
- Do not change imported work-item implementation provider routing.
- Do not modify prompt files.
- Do not add a provider alias just to avoid testing `provider_params`; model/effort must remain explicit unless runtime validation proves a different shape is required.

## Handoff Notes

Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan. Do not create a worktree; this repo's `AGENTS.md` explicitly prohibits worktree creation for implementation work.
