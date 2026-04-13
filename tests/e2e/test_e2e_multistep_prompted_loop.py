"""E2E: Multi-step prompted workflow with deterministic artifact handoff.

This test covers a non-trivial provider workflow where every provider step uses
an on-disk prompt file via `input_file`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from orchestrator.loader import WorkflowLoader
from tests.workflow_bundle_helpers import thaw_surface_workflow
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e
from tests.e2e.reporter import reporter


WORKFLOW_FILENAME = "multistep_prompted_loop.yaml"


def _write_seed_project(workspace: Path) -> None:
    (workspace / "docs" / "backlog").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)
    (workspace / "state").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "fixes").mkdir(parents=True, exist_ok=True)

    (workspace / "docs" / "backlog" / "item-001-fix-add.md").write_text(
        "# Backlog Item 001: Fix add()\n\n"
        "## Problem\n"
        "`src/calculator.py::add` is currently incorrect.\n\n"
        "## Acceptance Criteria\n"
        "- `add(2, 3)` returns `5`\n"
        "- `add(-2, 5)` returns `3`\n"
        "- `pytest -q tests/test_calculator.py` passes\n"
    )

    (workspace / "src" / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n"
        "    # Intentionally wrong seed behavior for workflow fix step.\n"
        "    return a - b\n"
    )

    (workspace / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n"
        "def test_add_positive_numbers() -> None:\n"
        "    assert add(2, 3) == 5\n\n"
        "def test_add_mixed_sign_numbers() -> None:\n"
        "    assert add(-2, 5) == 3\n"
    )


def _write_prompts(workspace: Path) -> None:
    (workspace / "prompts" / "draft_plan.md").write_text(
        "You are planning a tiny implementation task in this repository.\n\n"
        "Inputs to read:\n"
        "- state/backlog_item_path.txt (contains a relative path to a backlog markdown file)\n"
        "- The backlog markdown file referenced in that pointer\n\n"
        "Required actions:\n"
        "1. Read the backlog item and draft a short actionable plan.\n"
        "2. Write the plan to docs/plans/plan-item-001.md.\n"
        "3. Write exactly this relative path to state/plan_path.txt:\n"
        "   docs/plans/plan-item-001.md\n\n"
        "Constraints:\n"
        "- Keep the plan concise and concrete.\n"
        "- Do not write absolute paths.\n"
        "- Ensure files are written before finishing.\n"
    )

    (workspace / "prompts" / "execute_plan.md").write_text(
        "You are implementing the selected backlog item.\n\n"
        "Inputs to read:\n"
        "- state/plan_path.txt (relative path to implementation plan)\n"
        "- The plan file referenced by that pointer\n"
        "- src/calculator.py and tests/test_calculator.py\n\n"
        "Required actions:\n"
        "1. Apply the plan to the toy codebase.\n"
        "2. Make add(a, b) correct in src/calculator.py.\n"
        "3. Write an execution summary to artifacts/work/execution-log.md.\n"
        "4. Write exactly this relative path to state/execution_log_path.txt:\n"
        "   artifacts/work/execution-log.md\n\n"
        "Constraints:\n"
        "- Keep changes minimal and focused on the backlog item.\n"
        "- Do not run broad test suites here; the workflow has a dedicated test-fix loop.\n"
    )

    (workspace / "prompts" / "fix_tests.md").write_text(
        "You are the test-fix phase for this workflow.\n\n"
        "Inputs to read:\n"
        "- state/post_failed_count.txt\n"
        "- state/post_pytest.log (if present)\n"
        "- src/calculator.py and tests/test_calculator.py\n\n"
        "Required actions:\n"
        "1. If tests are failing, fix the implementation so tests pass.\n"
        "2. Run pytest -q tests/test_calculator.py to verify the fix.\n"
        "3. Write a short fix summary to artifacts/fixes/post-fix-log.md.\n"
        "4. Write exactly this relative path to state/post_fix_path.txt:\n"
        "   artifacts/fixes/post-fix-log.md\n\n"
        "Constraints:\n"
        "- Do not make unrelated refactors.\n"
        "- Keep the fix summary focused on what changed and test result.\n"
    )


def _write_workflow(workspace: Path) -> Path:
    workflow = """
version: "1.1.1"
name: "e2e-multistep-prompted-loop"
context:
  max_cycles: "3"
providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model", "${model}", "--config", "reasoning_effort=${reasoning_effort}"]
    input_mode: stdin
    defaults:
      model: "gpt-5.3-codex"
      reasoning_effort: "high"
  claude:
    command: ["claude", "-p", "${PROMPT}", "--dangerously-skip-permissions", "--model", "${model}"]
    input_mode: argv
    defaults:
      model: "claude-opus-4-6"
steps:
  - name: SelectBacklogItem
    command:
      - bash
      - -lc
      - "mkdir -p state && ls docs/backlog/*.md | head -n1 > state/backlog_item_path.txt"
    expected_outputs:
      - name: backlog_item_path
        path: state/backlog_item_path.txt
        type: relpath
        under: docs/backlog
        must_exist_target: true

  - name: DraftPlan
    provider: codex
    input_file: prompts/draft_plan.md
    timeout_sec: 180
    expected_outputs:
      - name: plan_path
        path: state/plan_path.txt
        type: relpath
        under: docs/plans
        must_exist_target: true

  - name: ExecutePlan
    provider: claude
    input_file: prompts/execute_plan.md
    timeout_sec: 240
    expected_outputs:
      - name: execution_log_path
        path: state/execution_log_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true

  - name: InitializePostTestCycle
    command:
      - bash
      - -lc
      - "mkdir -p state && printf '0\\n' > state/post_test_cycle.txt"
    expected_outputs:
      - name: post_test_cycle
        path: state/post_test_cycle.txt
        type: integer

  - name: RunPostWorkTests
    command:
      - bash
      - -lc
      - "mkdir -p state && if pytest -q tests/test_calculator.py > state/post_pytest.log 2>&1; then printf '0\\n' > state/post_failed_count.txt; else printf '1\\n' > state/post_failed_count.txt; fi"
    expected_outputs:
      - name: failed_count
        path: state/post_failed_count.txt
        type: integer

  - name: PostWorkGate
    command:
      - bash
      - -lc
      - 'test "$(cat state/post_failed_count.txt)" -eq 0'
    on:
      success:
        goto: _end
      failure:
        goto: FixPostWorkIssues

  - name: FixPostWorkIssues
    provider: claude
    input_file: prompts/fix_tests.md
    timeout_sec: 240
    expected_outputs:
      - name: post_fix_path
        path: state/post_fix_path.txt
        type: relpath
        under: artifacts/fixes
        must_exist_target: true
    on:
      success:
        goto: IncrementPostTestCycle

  - name: IncrementPostTestCycle
    command:
      - bash
      - -lc
      - 'c=$(cat state/post_test_cycle.txt); printf "%s\\n" "$((c+1))" > state/post_test_cycle.txt'
    expected_outputs:
      - name: post_test_cycle
        path: state/post_test_cycle.txt
        type: integer

  - name: PostCycleGate
    command:
      - bash
      - -lc
      - 'test "$(cat state/post_test_cycle.txt)" -lt 3'
    on:
      success:
        goto: RunPostWorkTests
"""

    workflow_path = workspace / "workflows" / WORKFLOW_FILENAME
    workflow_path.write_text(workflow.strip() + "\n")
    return workflow_path


def _seed_prompted_loop_workspace(workspace: Path) -> Path:
    _write_seed_project(workspace)
    _write_prompts(workspace)
    return _write_workflow(workspace)


def _extract_run_id(stderr: str) -> str:
    match = re.search(r"Created new run: ([a-zA-Z0-9\-]+)", stderr)
    assert match, f"Could not parse run id from stderr: {stderr}"
    return match.group(1)


def _run_workflow(workspace: Path, workflow_path: Path) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).parent.parent.parent
    orchestrate_path = repo_root / "orchestrate"
    if orchestrate_path.exists():
        cmd = ["python", str(orchestrate_path), "run", str(workflow_path), "--debug"]
    else:
        cmd = ["python", "-m", "orchestrator.cli.main", "run", str(workflow_path), "--debug"]

    env = os.environ.copy()
    env["ORCHESTRATE_E2E"] = "1"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{repo_root}:{existing_pythonpath}" if existing_pythonpath else str(repo_root)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=workspace,
        env=env,
        timeout=900,
    )


def test_multistep_prompt_file_contract(e2e_workspace: Path):
    """Workflow contract: every provider step references an on-disk prompt file."""
    workflow_path = _seed_prompted_loop_workspace(e2e_workspace)

    loader = WorkflowLoader(e2e_workspace)
    workflow = thaw_surface_workflow(loader.load(workflow_path))

    provider_steps = [step for step in workflow["steps"] if "provider" in step]
    assert provider_steps, "Expected provider steps in prompted loop workflow"

    for step in provider_steps:
        assert step.get("input_file"), f"Provider step {step['name']} must define input_file"
        assert step.get("expected_outputs"), f"Provider step {step['name']} must define expected_outputs"

        prompt_path = e2e_workspace / step["input_file"]
        assert prompt_path.exists(), f"Prompt file missing for {step['name']}: {prompt_path}"
        assert prompt_path.read_text().strip(), f"Prompt file should not be empty for {step['name']}"


@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_e2e_multistep_prompted_loop(e2e_workspace: Path):
    """Run a real multi-step codex+claude workflow backed by real prompt files."""
    skip_if_no_e2e()
    skip_if_no_cli("codex")
    skip_if_no_cli("claude")

    workflow_path = _seed_prompted_loop_workspace(e2e_workspace)

    reporter.section("E2E: Multi-step prompted loop")
    result = _run_workflow(e2e_workspace, workflow_path)

    assert result.returncode == 0, f"Workflow execution failed: {result.stderr}"

    run_id = _extract_run_id(result.stderr)
    run_dir = e2e_workspace / ".orchestrate" / "runs" / run_id
    state_file = run_dir / "state.json"
    assert state_file.exists(), f"Missing state file: {state_file}"

    state = json.loads(state_file.read_text())
    assert state["status"] == "completed"

    assert state["steps"]["DraftPlan"]["exit_code"] == 0
    assert state["steps"]["ExecutePlan"]["exit_code"] == 0

    assert state["steps"]["DraftPlan"]["artifacts"]["plan_path"] == "docs/plans/plan-item-001.md"
    assert (
        state["steps"]["ExecutePlan"]["artifacts"]["execution_log_path"]
        == "artifacts/work/execution-log.md"
    )
    assert state["steps"]["RunPostWorkTests"]["artifacts"]["failed_count"] == 0

    draft_prompt_log = run_dir / "logs" / "DraftPlan.prompt.txt"
    exec_prompt_log = run_dir / "logs" / "ExecutePlan.prompt.txt"
    assert draft_prompt_log.exists(), "Expected DraftPlan prompt audit file"
    assert exec_prompt_log.exists(), "Expected ExecutePlan prompt audit file"
    if "FixPostWorkIssues" in state["steps"]:
        assert state["steps"]["FixPostWorkIssues"]["exit_code"] == 0
        fix_prompt_log = run_dir / "logs" / "FixPostWorkIssues.prompt.txt"
        assert fix_prompt_log.exists(), "Expected FixPostWorkIssues prompt audit file when step runs"

    pytest_result = subprocess.run(
        ["pytest", "-q", "tests/test_calculator.py"],
        cwd=e2e_workspace,
        capture_output=True,
        text=True,
    )
    assert pytest_result.returncode == 0, (
        "Final toy-project tests should pass after workflow run. "
        f"stdout={pytest_result.stdout}\nstderr={pytest_result.stderr}"
    )
