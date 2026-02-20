"""Smoke tests for v0 artifact-contract example workflows."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


EXAMPLE_FILES = [
    "backlog_plan_execute_v0.yaml",
    "test_fix_loop_v0.yaml",
    "unit_of_work_plus_test_fix_v0.yaml",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _copy_example_to_workspace(tmp_path: Path, example_file: str) -> tuple[Path, Path, str]:
    workspace = tmp_path / example_file.replace(".yaml", "")
    workflow_rel = Path("workflows/examples") / example_file
    workflow_path = workspace / workflow_rel
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    src = _repo_root() / workflow_rel
    workflow_path.write_text(src.read_text())
    return workspace, workflow_path, workflow_rel.as_posix()


def _write_relpath_artifact(workspace: Path, pointer_path: str, target_relpath: str, content: str) -> None:
    pointer = workspace / pointer_path
    target = workspace / target_relpath
    pointer.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    pointer.write_text(f"{target_relpath}\n")


def _run_with_mocked_providers(
    workspace: Path,
    workflow_path: Path,
    workflow_relpath: str,
    provider_sequence: list[str],
    provider_writers: dict[str, Callable[[Path], None]],
) -> dict:
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, workflow.get("context", {}))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    call_index = {"value": 0}

    def _prepare_invocation(*args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_invocation):
        step_name = provider_sequence[call_index["value"]]
        call_index["value"] += 1
        provider_writers[step_name](workspace)
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute
    state = executor.execute()
    state["__provider_calls"] = call_index["value"]
    return state


def test_workflow_examples_v0_load():
    """All v0 examples parse and validate under strict loader checks."""
    root = _repo_root()
    loader = WorkflowLoader(root)

    for example_file in EXAMPLE_FILES:
        workflow_path = root / "workflows" / "examples" / example_file
        workflow = loader.load(workflow_path)
        assert workflow["steps"], f"Expected steps in {example_file}"


def test_backlog_plan_execute_v0_runtime(tmp_path: Path):
    """Backlog -> plan -> execute flow produces deterministic handoff artifacts."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "backlog_plan_execute_v0.yaml")
    backlog_file = workspace / "docs" / "backlog" / "item-001.md"
    backlog_file.parent.mkdir(parents=True, exist_ok=True)
    backlog_file.write_text("# Backlog item\n")

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["DraftPlan", "ExecutePlan"],
        provider_writers={
            "DraftPlan": lambda ws: _write_relpath_artifact(
                ws, "state/plan_path.txt", "docs/plans/plan-item-001.md", "# Draft plan\n"
            ),
            "ExecutePlan": lambda ws: _write_relpath_artifact(
                ws, "state/execution_log_path.txt", "artifacts/execution/run.log", "execution ok\n"
            ),
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 2
    assert state["steps"]["SelectBacklogItem"]["artifacts"]["backlog_item_path"] == "docs/backlog/item-001.md"
    assert state["steps"]["DraftPlan"]["artifacts"]["plan_path"] == "docs/plans/plan-item-001.md"
    assert state["steps"]["ExecutePlan"]["artifacts"]["execution_log_path"] == "artifacts/execution/run.log"


def test_test_fix_loop_v0_runtime(tmp_path: Path):
    """Test/fix loop iterates once, writes fix artifact, then exits when failures drop to zero."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "test_fix_loop_v0.yaml")

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["FixIssues"],
        provider_writers={
            "FixIssues": lambda ws: (
                _write_relpath_artifact(ws, "state/fix_patch_path.txt", "artifacts/fixes/fix.patch", "patch\n"),
                (ws / "state" / "fixed.marker").write_text("fixed\n"),
            ),
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 1
    assert state["steps"]["RunTests"]["artifacts"]["failed_count"] == 0
    assert state["steps"]["FixIssues"]["artifacts"]["fix_patch_path"] == "artifacts/fixes/fix.patch"


def test_unit_of_work_plus_test_fix_v0_runtime(tmp_path: Path):
    """Unit-of-work flow runs work, then test/fix loop until tests pass."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "unit_of_work_plus_test_fix_v0.yaml")

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["ExecuteUnitOfWork", "FixPostWorkIssues"],
        provider_writers={
            "ExecuteUnitOfWork": lambda ws: _write_relpath_artifact(
                ws, "state/unit_result_path.txt", "artifacts/work/unit-result.md", "unit work\n"
            ),
            "FixPostWorkIssues": lambda ws: (
                _write_relpath_artifact(ws, "state/post_fix_path.txt", "artifacts/fixes/post-fix.patch", "post-fix\n"),
                (ws / "state" / "post_fixed.marker").write_text("fixed\n"),
            ),
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 2
    assert state["steps"]["ExecuteUnitOfWork"]["artifacts"]["unit_result_path"] == "artifacts/work/unit-result.md"
    assert state["steps"]["RunPostWorkTests"]["artifacts"]["failed_count"] == 0
    assert state["steps"]["FixPostWorkIssues"]["artifacts"]["post_fix_path"] == "artifacts/fixes/post-fix.patch"
