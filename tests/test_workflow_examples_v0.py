"""Smoke tests for v0 artifact-contract example workflows."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


EXAMPLE_FILES = [
    "backlog_plan_execute_v0.yaml",
    "backlog_plan_execute_v1_2_dataflow.yaml",
    "backlog_plan_execute_v1_3_json_bundles.yaml",
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
    provider_stdout: dict[str, bytes | str] | None = None,
    captured_prompts: list[dict[str, str]] | None = None,
) -> dict:
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, workflow.get("context", {}))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    call_index = {"value": 0}

    def _prepare_invocation(*args, **kwargs):
        if captured_prompts is not None:
            prompt = kwargs.get("prompt_content", "") or ""
            step_name = provider_sequence[call_index["value"]] if call_index["value"] < len(provider_sequence) else ""
            captured_prompts.append({"step": step_name, "prompt": prompt})
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_invocation, **_kwargs):
        step_name = provider_sequence[call_index["value"]]
        call_index["value"] += 1
        provider_writers[step_name](workspace)
        stdout_value = b"ok"
        if provider_stdout and step_name in provider_stdout:
            configured = provider_stdout[step_name]
            stdout_value = configured if isinstance(configured, bytes) else configured.encode("utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=stdout_value,
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
    assert "artifacts" not in state["steps"]["SelectBacklogItem"]
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


def test_backlog_plan_execute_v1_2_dataflow_runtime(tmp_path: Path):
    """v1.2 example enforces publish/consume lineage across execute/fix/review loop."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "backlog_plan_execute_v1_2_dataflow.yaml"
    )

    review_calls = {"count": 0}
    captured_prompts: list[dict[str, str]] = []

    def _write_review_decision(ws: Path) -> None:
        failed_count = int((ws / "state" / "failed_count.txt").read_text().strip())
        decision = "APPROVE" if failed_count == 0 else "REVISE"
        review_calls["count"] += 1
        (ws / "state").mkdir(parents=True, exist_ok=True)
        (ws / "state" / "review_decision.txt").write_text(f"{decision}\n")

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["ExecutePlan", "ReviewPlan", "FixIssues", "ReviewPlan"],
        captured_prompts=captured_prompts,
        provider_writers={
            "ExecutePlan": lambda ws: _write_relpath_artifact(
                ws, "state/execution_log_path.txt", "artifacts/work/execute.log", "execute\n"
            ),
            "FixIssues": lambda ws: (
                _write_relpath_artifact(
                    ws, "state/execution_log_path.txt", "artifacts/work/fix.log", "fix\n"
                ),
                (ws / "state" / "fixed.marker").write_text("fixed\n"),
            ),
            "ReviewPlan": _write_review_decision,
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 4
    assert state["steps"]["ReviewPlan"]["artifacts"]["review_decision"] == "APPROVE"

    versions = state.get("artifact_versions", {}).get("execution_log", [])
    assert [entry["producer"] for entry in versions] == ["ExecutePlan", "FixIssues"]
    assert [entry["value"] for entry in versions] == ["artifacts/work/execute.log", "artifacts/work/fix.log"]

    consumes = state.get("artifact_consumes", {}).get("ReviewPlan", {})
    assert consumes.get("execution_log") == 2
    assert consumes.get("failed_count") == 2

    scalar_versions = state.get("artifact_versions", {}).get("failed_count", [])
    assert [entry["producer"] for entry in scalar_versions] == ["RunChecks", "RunChecks"]
    assert [entry["value"] for entry in scalar_versions] == [1, 0]

    review_prompts = [entry["prompt"] for entry in captured_prompts if entry["step"] == "ReviewPlan"]
    assert len(review_prompts) == 2
    assert "- execution_log: artifacts/work/execute.log" in review_prompts[0]
    assert "- execution_log: artifacts/work/fix.log" in review_prompts[1]
    assert "- failed_count:" not in review_prompts[0]
    assert "- failed_count:" not in review_prompts[1]


def test_backlog_plan_execute_v1_3_json_bundles_runtime(tmp_path: Path):
    """v1.3 example uses strict assessment artifacts to drive execute/fix gating."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "backlog_plan_execute_v1_3_json_bundles.yaml"
    )

    captured_prompts: list[dict[str, str]] = []

    def _write_assessment(ws: Path) -> None:
        failed_count = int((ws / "state" / "failed_count.txt").read_text().strip())
        decision = "APPROVE" if failed_count == 0 else "REVISE"
        (ws / "state").mkdir(parents=True, exist_ok=True)
        (ws / "state" / "assessment_output.json").write_text(
            f'{{"review_decision":"{decision}"}}\n'
        )

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["ExecutePlan", "AssessExecutionCompletion", "FixIssues", "AssessExecutionCompletion"],
        captured_prompts=captured_prompts,
        provider_stdout={
            "AssessExecutionCompletion": b'{"assessment":"ok"}\n',
        },
        provider_writers={
            "ExecutePlan": lambda ws: _write_relpath_artifact(
                ws, "state/execution_log_path.txt", "artifacts/work/execute.log", "execute\n"
            ),
            "FixIssues": lambda ws: (
                _write_relpath_artifact(
                    ws, "state/execution_log_path.txt", "artifacts/work/fix.log", "fix\n"
                ),
                (ws / "state" / "fixed.marker").write_text("fixed\n"),
            ),
            "AssessExecutionCompletion": _write_assessment,
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 4

    versions = state.get("artifact_versions", {}).get("review_decision", [])
    assert [entry["value"] for entry in versions] == ["REVISE", "APPROVE"]
    assert [entry["producer"] for entry in versions] == ["AssessExecutionCompletion", "AssessExecutionCompletion"]

    consumes = state.get("artifact_consumes", {}).get("ReviewGate", {})
    assert consumes.get("review_decision") == 2

    gate_bundle = workspace / "state" / "consumes" / "review_gate.json"
    assert gate_bundle.exists()
    assert '"review_decision": "APPROVE"' in gate_bundle.read_text()
