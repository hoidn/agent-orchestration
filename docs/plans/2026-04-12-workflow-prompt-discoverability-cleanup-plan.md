# Workflow Prompt Discoverability Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make workflow-to-prompt ownership easy to discover, then clean up the stale examples and ambiguous prompt wording exposed by that map.

**Architecture:** Add a small YAML-aware prompt-reference mapper and a generated documentation page that resolves every provider prompt source from workflow YAML. Wire that page into the existing docs and workflow catalogs, then use the map as the audit surface for example status, missing prompt assets, and prompt/output-contract wording cleanup. Keep this as documentation and fixture hygiene: no runtime prompt-composition semantics change.

**Tech Stack:** Python 3.11+, PyYAML, Markdown docs, workflow YAML fixtures, pytest, orchestrator dry-run smoke checks.

---

## Global Guardrails

- Do not create a git worktree. This repo explicitly disallows worktrees for this work.
- Keep runtime behavior unchanged. Do not change provider prompt composition, `input_file`, `asset_file`, `asset_depends_on`, `depends_on`, `consumes`, `expected_outputs`, or publication semantics.
- Treat `docs/workflow_prompt_map.md` as an aid, not a normative spec. Normative behavior stays in `specs/`.
- Prefer visibility before cleanup. First generate the map, then update catalogs and examples based on the concrete rows it exposes.
- Do not add tests that assert literal prompt prose. Tests may assert prompt reference discovery, path resolution, map freshness, and example validation behavior.
- Keep missing prompt references visible in the generated map unless a later task either restores the prompt file or explicitly marks the workflow as legacy/external in the catalog.
- Run all commands from the repo root.

## File Structure

- Create `scripts/workflow_prompt_map.py`
  - CLI and reusable helper functions for scanning workflow YAML prompt references.
  - Resolves `input_file` from repo root.
  - Resolves `asset_file` and `asset_depends_on` from the workflow YAML file's directory.
  - Walks nested workflow step forms: top-level `steps`, `for_each.steps`, `repeat_until.steps`, `if.then.steps`, `else.steps`, and `match.cases.*.steps`.
  - Emits a Markdown table suitable for `docs/workflow_prompt_map.md`.
  - Provides `--check` to compare generated output with the checked-in doc.

- Create `tests/test_workflow_prompt_map.py`
  - Unit tests for path resolution and nested traversal.
  - Tests should use temporary workflow files, not the full repo tree, so failures are focused.

- Create `docs/workflow_prompt_map.md`
  - Generated output from `scripts/workflow_prompt_map.py`.
  - Includes resolution rules and the exhaustive prompt-reference table.

- Modify `docs/index.md`
  - Add the new workflow-prompt map near the existing Workflow Index and Prompt Index entries.

- Modify `workflows/README.md`
  - Add a short prompt-resolution section.
  - Link to `docs/workflow_prompt_map.md`.
  - Add status categories so current examples, legacy examples, negative fixtures, and input-required examples do not look equivalent.

- Modify `prompts/README.md`
  - State clearly that it is curated and not exhaustive.
  - Link to `docs/workflow_prompt_map.md` for the exhaustive map.

- Modify current library prompt files under `workflows/library/prompts/design_plan_impl_stack_v2_call/`
  - Replace literal `${inputs.state_root}/...` output-path wording with references to the injected Output Contract.
  - Affected files:
    - `draft_design.md`
    - `draft_plan.md`
    - `fix_implementation.md`
    - `implement_plan.md`
    - `review_design.md`
    - `review_implementation.md`
    - `review_plan.md`
    - `revise_design.md`
    - `revise_plan.md`

- Modify stale example workflow fixtures only after the map exists:
  - `workflows/examples/injection_demo.yaml`
  - `workflows/examples/conditional_demo.yaml`
  - `workflows/examples/output_capture_demo.yaml`
  - `workflows/examples/retry_demo.yaml`

## Known Inputs From Initial Audit

- `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` dry-runs successfully and is the best current reference family.
- `workflows/examples/injection_demo.yaml` fails dry-run validation because `providers` is a list instead of the current mapping shape.
- `workflows/examples/conditional_demo.yaml`, `workflows/examples/output_capture_demo.yaml`, and `workflows/examples/retry_demo.yaml` fail dry-run validation due stale top-level `description` and/or provider-template shape.
- `workflows/examples/bad_processed.yaml` is an intentional negative fixture and should be documented as such, not "fixed."
- Some workflow prompt paths are missing or intentionally external/downstream snapshots. The map should expose them before the repo decides whether to restore, replace, or label them.

---

### Task 1: Add Prompt Map Scanner Tests

**Files:**
- Create: `tests/test_workflow_prompt_map.py`
- Reference: `scripts/workflow_prompt_map.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_workflow_prompt_map.py` with focused tests for the scanner API that does not exist yet:

```python
from pathlib import Path

from scripts.workflow_prompt_map import collect_prompt_refs, render_markdown


def test_collect_prompt_refs_resolves_input_and_asset_paths(tmp_path: Path):
    repo = tmp_path
    workflow_dir = repo / "workflows" / "library"
    workflow_dir.mkdir(parents=True)
    (repo / "prompts" / "workflows").mkdir(parents=True)
    (workflow_dir / "prompts").mkdir()
    (workflow_dir / "rubrics").mkdir()
    (repo / "prompts" / "workflows" / "review.md").write_text("review\n", encoding="utf-8")
    (workflow_dir / "prompts" / "draft.md").write_text("draft\n", encoding="utf-8")
    (workflow_dir / "rubrics" / "rubric.md").write_text("rubric\n", encoding="utf-8")
    workflow = workflow_dir / "example.yaml"
    workflow.write_text(
        """
version: "2.7"
steps:
  - name: Draft
    provider: codex
    asset_file: prompts/draft.md
    asset_depends_on:
      - rubrics/rubric.md
  - name: Review
    provider: codex
    input_file: prompts/workflows/review.md
""",
        encoding="utf-8",
    )

    refs = collect_prompt_refs(repo, [workflow])

    assert [(ref.step_path, ref.field, ref.authored_path, ref.exists) for ref in refs] == [
        ("Draft", "asset_file", "prompts/draft.md", True),
        ("Draft", "asset_depends_on", "rubrics/rubric.md", True),
        ("Review", "input_file", "prompts/workflows/review.md", True),
    ]
    assert refs[0].resolved_path == workflow_dir / "prompts" / "draft.md"
    assert refs[1].resolved_path == workflow_dir / "rubrics" / "rubric.md"
    assert refs[2].resolved_path == repo / "prompts" / "workflows" / "review.md"


def test_collect_prompt_refs_walks_nested_control_flow(tmp_path: Path):
    repo = tmp_path
    workflow_dir = repo / "workflows" / "examples"
    prompt_dir = repo / "prompts"
    workflow_dir.mkdir(parents=True)
    prompt_dir.mkdir()
    for name in ["loop.md", "then.md", "else.md", "case.md", "for_each.md"]:
        (prompt_dir / name).write_text(name, encoding="utf-8")
    workflow = workflow_dir / "nested.yaml"
    workflow.write_text(
        """
version: "2.7"
steps:
  - name: Loop
    repeat_until:
      steps:
        - name: LoopPrompt
          provider: codex
          input_file: prompts/loop.md
  - name: Branch
    if:
      compare: {left: 1, op: eq, right: 1}
    then:
      steps:
        - name: ThenPrompt
          provider: codex
          input_file: prompts/then.md
    else:
      steps:
        - name: ElsePrompt
          provider: codex
          input_file: prompts/else.md
  - name: Route
    match:
      ref: inputs.decision
      cases:
        APPROVE:
          steps:
            - name: CasePrompt
              provider: codex
              input_file: prompts/case.md
  - name: Items
    for_each:
      items: [one]
      steps:
        - name: ForEachPrompt
          provider: codex
          input_file: prompts/for_each.md
""",
        encoding="utf-8",
    )

    refs = collect_prompt_refs(repo, [workflow])

    assert [ref.step_path for ref in refs] == [
        "Loop > LoopPrompt",
        "Branch > then > ThenPrompt",
        "Branch > else > ElsePrompt",
        "Route > case APPROVE > CasePrompt",
        "Items > ForEachPrompt",
    ]


def test_render_markdown_includes_missing_status(tmp_path: Path):
    repo = tmp_path
    workflow_dir = repo / "workflows" / "examples"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "missing.yaml"
    workflow.write_text(
        """
version: "1.1"
steps:
  - name: MissingPrompt
    provider: codex
    input_file: prompts/missing.md
""",
        encoding="utf-8",
    )

    refs = collect_prompt_refs(repo, [workflow])
    markdown = render_markdown(repo, refs)

    assert "`workflows/examples/missing.yaml`" in markdown
    assert "`prompts/missing.md`" in markdown
    assert "| no |" in markdown
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
pytest tests/test_workflow_prompt_map.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.workflow_prompt_map'`.

- [ ] **Step 3: Commit the failing-test checkpoint if using incremental commits**

```bash
git add tests/test_workflow_prompt_map.py
git commit -m "test: cover workflow prompt map scanning"
```

Skip the commit only if the user has asked not to commit or the current session is intentionally batching changes.

---

### Task 2: Implement The Prompt Map Scanner

**Files:**
- Create: `scripts/workflow_prompt_map.py`
- Test: `tests/test_workflow_prompt_map.py`

- [ ] **Step 1: Add the scanner implementation**

Create `scripts/workflow_prompt_map.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclass(frozen=True)
class PromptRef:
    workflow_path: Path
    step_path: str
    field: str
    authored_path: str
    resolved_path: Path
    exists: bool


def workflow_files(root: Path) -> list[Path]:
    workflows_root = root / "workflows"
    return sorted(
        path
        for suffix in ("*.yaml", "*.yml")
        for path in workflows_root.rglob(suffix)
        if path.is_file()
    )


def collect_prompt_refs(root: Path, workflows: Iterable[Path] | None = None) -> list[PromptRef]:
    root = root.resolve()
    refs: list[PromptRef] = []
    for workflow in workflows or workflow_files(root):
        workflow = workflow.resolve()
        payload = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for step_path, step in iter_steps(payload.get("steps", [])):
            refs.extend(refs_for_step(root, workflow, step_path, step))
    return refs


def iter_steps(steps: Any, prefix: tuple[str, ...] = ()) -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(steps, list):
        return
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        name = str(step.get("name") or step.get("id") or f"<step {index}>")
        step_prefix = prefix + (name,)
        yield " > ".join(step_prefix), step

        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from iter_steps(repeat_until.get("steps", []), step_prefix)

        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            yield from iter_steps(for_each.get("steps", []), step_prefix)

        then_branch = step.get("then")
        if isinstance(then_branch, dict):
            yield from iter_steps(then_branch.get("steps", []), step_prefix + ("then",))

        else_branch = step.get("else")
        if isinstance(else_branch, dict):
            yield from iter_steps(else_branch.get("steps", []), step_prefix + ("else",))

        match = step.get("match")
        if isinstance(match, dict):
            cases = match.get("cases", {})
            if isinstance(cases, dict):
                for case_name, case_body in cases.items():
                    if isinstance(case_body, dict):
                        yield from iter_steps(
                            case_body.get("steps", []),
                            step_prefix + (f"case {case_name}",),
                        )


def refs_for_step(root: Path, workflow: Path, step_path: str, step: dict[str, Any]) -> list[PromptRef]:
    refs: list[PromptRef] = []
    input_file = step.get("input_file")
    if isinstance(input_file, str):
        refs.append(make_ref(root, workflow, step_path, "input_file", input_file))

    asset_file = step.get("asset_file")
    if isinstance(asset_file, str):
        refs.append(make_ref(root, workflow, step_path, "asset_file", asset_file))

    asset_depends_on = step.get("asset_depends_on")
    if isinstance(asset_depends_on, list):
        for item in asset_depends_on:
            if isinstance(item, str):
                refs.append(make_ref(root, workflow, step_path, "asset_depends_on", item))
    elif isinstance(asset_depends_on, str):
        refs.append(make_ref(root, workflow, step_path, "asset_depends_on", asset_depends_on))

    return refs


def make_ref(root: Path, workflow: Path, step_path: str, field: str, authored_path: str) -> PromptRef:
    base = workflow.parent if field in {"asset_file", "asset_depends_on"} else root
    resolved_path = (base / authored_path).resolve()
    return PromptRef(
        workflow_path=workflow,
        step_path=step_path,
        field=field,
        authored_path=authored_path,
        resolved_path=resolved_path,
        exists=resolved_path.is_file(),
    )


def render_markdown(root: Path, refs: Iterable[PromptRef]) -> str:
    lines = [
        "# Workflow Prompt Map",
        "",
        "Generated by `python scripts/workflow_prompt_map.py`.",
        "",
        "Resolution rules:",
        "- `input_file` is repo-root relative.",
        "- `asset_file` is relative to the workflow YAML file's directory.",
        "- `asset_depends_on` is relative to the workflow YAML file's directory.",
        "",
        "| Workflow | Step | Field | Authored Path | Resolved Path | Exists |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for ref in sorted(refs, key=lambda item: (item.workflow_path, item.step_path, item.field, item.authored_path)):
        lines.append(
            "| "
            f"`{relative_to(root, ref.workflow_path)}` | "
            f"`{ref.step_path}` | "
            f"`{ref.field}` | "
            f"`{ref.authored_path}` | "
            f"`{relative_to(root, ref.resolved_path)}` | "
            f"{'yes' if ref.exists else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)


def relative_to(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the workflow-to-prompt map.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("docs/workflow_prompt_map.md"))
    parser.add_argument("--check", action="store_true", help="Fail if the checked-in map is stale.")
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    markdown = render_markdown(root, collect_prompt_refs(root))

    if args.check:
        if not output.exists():
            print(f"Missing generated map: {relative_to(root, output)}")
            return 1
        existing = output.read_text(encoding="utf-8")
        if existing != markdown:
            print(f"Stale generated map: {relative_to(root, output)}")
            print("Run: python scripts/workflow_prompt_map.py")
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"Wrote {relative_to(root, output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the scanner tests**

Run:

```bash
pytest tests/test_workflow_prompt_map.py -q
```

Expected: PASS.

- [ ] **Step 3: Run collection check for the new test module**

Run:

```bash
pytest --collect-only -q tests/test_workflow_prompt_map.py
```

Expected: pytest collects the three tests in `tests/test_workflow_prompt_map.py`.

- [ ] **Step 4: Commit scanner implementation if using incremental commits**

```bash
git add scripts/workflow_prompt_map.py tests/test_workflow_prompt_map.py
git commit -m "feat: add workflow prompt map scanner"
```

---

### Task 3: Generate And Link The Workflow Prompt Map

**Files:**
- Create: `docs/workflow_prompt_map.md`
- Modify: `docs/index.md`
- Modify: `workflows/README.md`
- Modify: `prompts/README.md`
- Test: `tests/test_workflow_prompt_map.py`

- [ ] **Step 1: Generate the map**

Run:

```bash
python scripts/workflow_prompt_map.py
```

Expected: `docs/workflow_prompt_map.md` is created and includes rows for `input_file`, `asset_file`, and `asset_depends_on` references.

- [ ] **Step 2: Verify the generated map is stable**

Run:

```bash
python scripts/workflow_prompt_map.py --check
```

Expected: exit 0.

- [ ] **Step 3: Link the map from `docs/index.md`**

Add a Quick Start entry near the Workflow Index and Prompt Index:

```md
### [Workflow Prompt Map](workflow_prompt_map.md)
**Description:** Exhaustive generated map of workflow provider prompt sources, including `input_file`, `asset_file`, and `asset_depends_on` resolution and missing-file status.  
**Keywords:** workflows, prompts, input_file, asset_file, prompt-assets  
**Use this when:** You need to find which prompt files a workflow step uses or audit missing/stale prompt references.
```

Also add it to the workflow author fast path after the Workflow Index / Prompt Index bullet.

- [ ] **Step 4: Add prompt-resolution guidance to `workflows/README.md`**

Insert after the Directory Map:

```md
## Prompt Resolution

For an exhaustive workflow-to-prompt table, see `docs/workflow_prompt_map.md`.

Resolution rules:
- `input_file` is repo-root relative and is intended for workspace-owned or runtime-generated prompt material.
- `asset_file` is relative to the workflow YAML file and is intended for prompt assets bundled with reusable workflows.
- `asset_depends_on` follows the same workflow-source-relative rule as `asset_file`.

The prompt map reports missing paths; a missing path may indicate a stale example, a downstream snapshot with external assets, or a prompt generated at runtime by an earlier step.
```

- [ ] **Step 5: Clarify `prompts/README.md` scope**

Replace the opening paragraph with:

```md
This index catalogs the canonical prompt files worth reusing. It is intentionally curated rather than exhaustive.

For the exhaustive workflow-to-prompt map, including `input_file`, `asset_file`, and `asset_depends_on` resolution, see `docs/workflow_prompt_map.md`.
```

- [ ] **Step 6: Run focused verification**

Run:

```bash
python scripts/workflow_prompt_map.py --check
pytest tests/test_workflow_prompt_map.py -q
```

Expected: both pass.

- [ ] **Step 7: Commit doc map and links if using incremental commits**

```bash
git add docs/workflow_prompt_map.md docs/index.md workflows/README.md prompts/README.md
git commit -m "docs: add workflow prompt map"
```

---

### Task 4: Categorize Workflow Examples By Maintenance Status

**Files:**
- Modify: `workflows/README.md`
- Reference: `docs/workflow_prompt_map.md`

- [ ] **Step 1: Add catalog status categories**

In `workflows/README.md`, add a short section before the catalog table:

```md
## Catalog Status

- **Current canonical**: preferred examples for new workflow authoring.
- **Reusable call-based**: examples that exercise imported library workflows and bundled prompt assets.
- **Legacy or migration**: still useful as historical or migration references, but not the first place to copy patterns.
- **Negative fixture**: expected to fail validation or runtime checks for a specific test purpose.
- **Input-required**: requires `--input` or fixture files for dry-run validation.
- **Prompt asset issue**: references missing or external prompt assets; check `docs/workflow_prompt_map.md` before running.
```

- [ ] **Step 2: Add a Status column to the workflow catalog**

Change the table header from:

```md
| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
```

to:

```md
| Path | Status | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- | --- |
```

Update each row conservatively. Initial statuses to use:

- `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`: `Current canonical; reusable call-based`
- `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml`: `Reusable call-based; input-required`
- `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`: `Current structured; input-required`
- `workflows/examples/bad_processed.yaml`: `Negative fixture`
- `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml`: `Downstream reference; prompt asset issue`
- older shell-gate/raw-goto loops that dry-run with lint warnings: `Legacy or migration`
- stale validation failures from the audit: `Needs schema cleanup`

- [ ] **Step 3: Add dry-run examples for input-required workflows**

Add examples near the run command section:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/workflow_signature_demo.yaml \
  --dry-run --input task_path=workflows/examples/inputs/demo-task.md

PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml \
  --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json
```

- [ ] **Step 4: Review the rendered table for usefulness**

Run:

```bash
rg -n "Needs schema cleanup|Negative fixture|Current canonical|Prompt asset issue|input-required" workflows/README.md
```

Expected: output shows the new statuses in the catalog.

- [ ] **Step 5: Commit catalog changes if using incremental commits**

```bash
git add workflows/README.md
git commit -m "docs: categorize workflow examples"
```

---

### Task 5: Clean Up Current Library Prompt Output-Path Wording

**Files:**
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_design.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_design.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/revise_design.md`
- Modify: `workflows/library/prompts/design_plan_impl_stack_v2_call/revise_plan.md`
- Reference: `workflows/library/tracked_design_phase.yaml`
- Reference: `workflows/library/tracked_plan_phase.yaml`
- Reference: `workflows/library/design_plan_impl_implementation_phase.yaml`

- [ ] **Step 1: Replace literal `${inputs.state_root}` path wording**

Apply these wording changes:

```md
Write the design to the exact path named by `${inputs.state_root}/design_path.txt`.
```

becomes:

```md
Write the design to the `design_path` path specified in the Output Contract.
```

```md
Write the plan to the exact path named by `${inputs.state_root}/plan_path.txt`.
```

becomes:

```md
Write the plan to the `plan_path` path specified in the Output Contract.
```

```md
Write a concise execution report to the exact path named by `${inputs.state_root}/execution_report_path.txt`.
```

becomes:

```md
Write a concise execution report to the `execution_report_path` path specified in the Output Contract.
```

```md
Write JSON to the exact path named by `${inputs.state_root}/design_review_report_path.txt` using this shape:
```

becomes:

```md
Write JSON to the `design_review_report_path` path specified in the Output Contract using this shape:
```

```md
Write JSON to the exact path named by `${inputs.state_root}/plan_review_report_path.txt` using this shape:
```

becomes:

```md
Write JSON to the `plan_review_report_path` path specified in the Output Contract using this shape:
```

```md
Write the review as markdown to the exact path named by `${inputs.state_root}/implementation_review_report_path.txt`.
Write `APPROVE` or `REVISE` to `${inputs.state_root}/implementation_review_decision.txt`.
```

becomes:

```md
Write the review as markdown to the `implementation_review_report_path` path specified in the Output Contract.
Write `APPROVE` or `REVISE` to the `implementation_review_decision` path specified in the Output Contract.
```

For count/decision bullets in `review_design.md` and `review_plan.md`, replace `${inputs.state_root}/...` paths with the corresponding Output Contract names:

- `design_review_decision`
- `plan_review_decision`
- `unresolved_high_count`
- `unresolved_medium_count`

- [ ] **Step 2: Confirm literal input placeholders are gone from current library prompts**

Run:

```bash
rg -n '\$\{inputs\.' workflows/library/prompts/design_plan_impl_stack_v2_call -g '*.md'
```

Expected: no output.

- [ ] **Step 3: Inspect prompt/workflow contract alignment**

Run:

```bash
rg -n "expected_outputs:|name: (design_path|plan_path|execution_report_path|design_review_report_path|plan_review_report_path|implementation_review_report_path|implementation_review_decision|unresolved_high_count|unresolved_medium_count)" \
  workflows/library/tracked_design_phase.yaml \
  workflows/library/tracked_plan_phase.yaml \
  workflows/library/design_plan_impl_implementation_phase.yaml
```

Expected: each Output Contract name referenced in prompt wording appears as an `expected_outputs` name in the corresponding workflow.

- [ ] **Step 4: Dry-run the canonical call stack**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

Expected: `[DRY RUN] Workflow validation successful`.

- [ ] **Step 5: Commit prompt wording cleanup if using incremental commits**

```bash
git add workflows/library/prompts/design_plan_impl_stack_v2_call
git commit -m "docs: clarify library prompt output contracts"
```

---

### Task 6: Fix Stale Schema In Example Workflows

**Files:**
- Modify: `workflows/examples/injection_demo.yaml`
- Modify: `workflows/examples/conditional_demo.yaml`
- Modify: `workflows/examples/output_capture_demo.yaml`
- Modify: `workflows/examples/retry_demo.yaml`
- Reference: `workflows/README.md`

- [ ] **Step 1: Fix `injection_demo.yaml` provider shape**

Change:

```yaml
providers:
  - name: claude
    command: ["claude", "-p", "${PROMPT}"]
    input_mode: "argv"
```

to:

```yaml
providers:
  claude:
    command: ["claude", "-p", "${PROMPT}"]
    input_mode: "argv"
```

- [ ] **Step 2: Remove stale top-level `description` from `conditional_demo.yaml`**

Change:

```yaml
name: "Conditional Execution Demo"
description: |
  Demonstrates conditional execution with when.equals, when.exists, and when.not_exists.
  Tests AT-37, AT-46, AT-47.
```

to:

```yaml
name: "Conditional Execution Demo"
# Demonstrates conditional execution with when.equals, when.exists, and when.not_exists.
# Tests AT-37, AT-46, AT-47.
```

- [ ] **Step 3: Remove stale top-level `description` from `output_capture_demo.yaml`**

Change:

```yaml
name: output_capture_demo
description: Demonstrates text, lines, and JSON output capture
```

to:

```yaml
name: output_capture_demo
# Demonstrates text, lines, and JSON output capture.
```

- [ ] **Step 4: Fix `retry_demo.yaml` top-level description and provider shape**

Change:

```yaml
name: "Retry Demo Workflow"
description: "Demonstrates retry behavior for AT-20, AT-21"

providers:
  echo_provider:
    template: "echo ${PROMPT}"
    defaults:
      model: "test"
```

to:

```yaml
name: "Retry Demo Workflow"
# Demonstrates retry behavior for AT-20 and AT-21.

providers:
  echo_provider:
    command: ["echo", "${PROMPT}"]
    input_mode: "argv"
    defaults:
      model: "test"
```

- [ ] **Step 5: Dry-run the cleaned examples narrowly**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/injection_demo.yaml --dry-run --context phase=design
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/conditional_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/output_capture_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/retry_demo.yaml --dry-run
```

Expected: all four dry-runs validate successfully. Lint warnings are acceptable only if they are advisory and the workflow still validates.

- [ ] **Step 6: Regenerate the prompt map after workflow edits**

Run:

```bash
python scripts/workflow_prompt_map.py
python scripts/workflow_prompt_map.py --check
```

Expected: map regenerated and check passes.

- [ ] **Step 7: Update statuses in `workflows/README.md`**

If the four examples now validate, replace their `Needs schema cleanup` status with a more accurate status:

- `injection_demo.yaml`: `Legacy or migration`
- `conditional_demo.yaml`: `Legacy or migration`
- `output_capture_demo.yaml`: `Legacy or migration`
- `retry_demo.yaml`: `Legacy or migration`

Do not mark them as current canonical unless they are also modernized away from legacy patterns.

- [ ] **Step 8: Commit example schema cleanup if using incremental commits**

```bash
git add workflows/examples/injection_demo.yaml workflows/examples/conditional_demo.yaml workflows/examples/output_capture_demo.yaml workflows/examples/retry_demo.yaml docs/workflow_prompt_map.md workflows/README.md
git commit -m "fix: refresh legacy example workflow schema"
```

---

### Task 7: Triage Missing Prompt References Exposed By The Map

**Files:**
- Modify: `docs/workflow_prompt_map.md`
- Modify: `workflows/README.md`
- Possibly modify: workflow files that reference missing prompts
- Possibly create: prompt assets only when the missing prompt is truly repo-owned and needed for a runnable example

- [ ] **Step 1: List missing prompt rows from the generated map**

Run:

```bash
rg -n '\| no \|' docs/workflow_prompt_map.md
```

Expected: output lists the missing prompt references currently needing a decision.

- [ ] **Step 2: Classify each missing prompt reference**

Use this classification:

- `external downstream snapshot`: workflow intentionally documents a downstream reference and the prompt files are not maintained here.
- `generated at runtime`: prompt path is created by an earlier command step before provider execution.
- `stale example asset`: workflow should either get a small checked-in prompt fixture or be moved/labeled as legacy.
- `bug`: workflow is meant to be runnable here and the prompt path should point at an existing repo prompt.

- [ ] **Step 3: Update `workflows/README.md` with the classification**

For any workflow with missing prompt references, add a note in its Purpose or Status. Example:

```md
Prompt asset issue: references downstream prompt files not included in this repo snapshot; use as a structure reference, not a runnable prompt example.
```

- [ ] **Step 4: Avoid premature prompt reconstruction**

Do not invent full replacement prompts for the downstream `ptychopinn` snapshot unless the user explicitly wants that workflow to become runnable in this repo. The safe first fix is discoverability and accurate labeling.

- [ ] **Step 5: Regenerate the map if workflow paths changed**

Run:

```bash
python scripts/workflow_prompt_map.py
python scripts/workflow_prompt_map.py --check
```

Expected: map is up to date.

- [ ] **Step 6: Commit triage notes if using incremental commits**

```bash
git add docs/workflow_prompt_map.md workflows/README.md
git commit -m "docs: classify missing workflow prompt assets"
```

---

### Task 8: Final Verification

**Files:**
- All files changed by prior tasks.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
pytest tests/test_workflow_prompt_map.py -q
```

Expected: PASS.

- [ ] **Step 2: Verify generated map freshness**

Run:

```bash
python scripts/workflow_prompt_map.py --check
```

Expected: exit 0.

- [ ] **Step 3: Dry-run canonical current workflow**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

Expected: `[DRY RUN] Workflow validation successful`.

- [ ] **Step 4: Dry-run cleaned legacy examples**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/injection_demo.yaml --dry-run --context phase=design
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/conditional_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/output_capture_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/retry_demo.yaml --dry-run
```

Expected: all four dry-runs validate successfully.

- [ ] **Step 5: Dry-run input-required workflow examples with fixture inputs**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/workflow_signature_demo.yaml \
  --dry-run --input task_path=workflows/examples/inputs/demo-task.md

PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml \
  --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json
```

Expected: both validate successfully.

- [ ] **Step 6: Inspect docs for stale claims**

Run:

```bash
rg -n "curated rather than exhaustive|workflow_prompt_map|Prompt asset issue|Needs schema cleanup|Negative fixture" docs/index.md prompts/README.md workflows/README.md docs/workflow_prompt_map.md
```

Expected: docs point to the new map, prompt index states it is curated, and workflow statuses reflect the final cleaned state.

- [ ] **Step 7: Check git diff**

Run:

```bash
git diff -- docs/index.md prompts/README.md workflows/README.md docs/workflow_prompt_map.md scripts/workflow_prompt_map.py tests/test_workflow_prompt_map.py workflows/examples workflows/library/prompts/design_plan_impl_stack_v2_call
```

Expected: diff is limited to workflow/prompt discoverability docs, scanner/tests, stale example schema cleanup, and prompt output-contract wording.

- [ ] **Step 8: Final commit if using a single commit**

```bash
git add docs/index.md prompts/README.md workflows/README.md docs/workflow_prompt_map.md scripts/workflow_prompt_map.py tests/test_workflow_prompt_map.py workflows/examples workflows/library/prompts/design_plan_impl_stack_v2_call
git commit -m "docs: improve workflow prompt discoverability"
```

If commits were made per task, skip this final single-commit step.
