"""Smoke tests for v0 artifact-contract example workflows."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_bundle_helpers import bundle_context_dict


EXAMPLE_FILES = [
    "assert_gate_demo.yaml",
    "backlog_plan_execute_v0.yaml",
    "backlog_plan_execute_v1_2_dataflow.yaml",
    "backlog_plan_execute_v1_3_json_bundles.yaml",
    "backlog_priority_design_plan_impl_stack_v2_call.yaml",
    "call_subworkflow_demo.yaml",
    "cycle_guard_demo.yaml",
    "design_plan_impl_review_stack_v2_call.yaml",
    "dsl_follow_on_plan_impl_review_loop.yaml",
    "dsl_follow_on_plan_impl_review_loop_v2.yaml",
    "dsl_follow_on_plan_impl_review_loop_v2_call.yaml",
    "dsl_tracked_plan_review_loop.yaml",
    "dsl_review_first_fix_loop.yaml",
    "dsl_review_first_fix_loop_provider_session.yaml",
    "finally_demo.yaml",
    "match_demo.yaml",
    "repeat_until_demo.yaml",
    "score_gate_demo.yaml",
    "scalar_bookkeeping_demo.yaml",
    "structured_if_else_demo.yaml",
    "test_fix_loop_v0.yaml",
    "typed_predicate_routing.yaml",
    "unit_of_work_plus_test_fix_v0.yaml",
    "workflow_signature_demo.yaml",
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


def _copy_repo_file_to_workspace(workspace: Path, repo_relpath: str) -> None:
    src = _repo_root() / repo_relpath
    dest = workspace / repo_relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text())


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
    provider_stdout: dict[str, bytes | str | Callable[[Path], bytes | str]] | None = None,
    captured_prompts: list[dict[str, str]] | None = None,
) -> dict:
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        if captured_prompts is not None:
            prompt = kwargs.get("prompt_content", "") or ""
            step_name = provider_sequence[call_index["value"]] if call_index["value"] < len(provider_sequence) else ""
            captured_prompts.append({"step": step_name, "prompt": prompt})
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        step_name = provider_sequence[call_index["value"]]
        call_index["value"] += 1
        provider_writers[step_name](workspace)
        stdout_value = b"ok"
        if provider_stdout and step_name in provider_stdout:
            configured = provider_stdout[step_name]
            if callable(configured):
                configured = configured(workspace)
            stdout_value = configured if isinstance(configured, bytes) else configured.encode("utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=stdout_value,
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
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
        assert workflow.surface.raw["steps"], f"Expected steps in {example_file}"


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


def test_assert_gate_demo_runtime(tmp_path: Path):
    """Assert gate demo routes through failure recovery with exit code 3."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "assert_gate_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["GateApproval"]["exit_code"] == 3
    assert state["steps"]["GateApproval"]["error"]["type"] == "assert_failed"
    assert state["steps"]["WriteRevision"]["status"] == "completed"
    assert not (workspace / "approval.txt").exists()


def test_call_subworkflow_demo_runtime(tmp_path: Path):
    """Call demo runs a reusable subworkflow and surfaces only declared outputs."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "call_subworkflow_demo.yaml")
    _copy_repo_file_to_workspace(workspace, "workflows/library/review_fix_loop.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}
    assert state["steps"]["VerifyApproved"]["status"] == "completed"
    assert (workspace / "state" / "review-loop" / "history.log").read_text() == "review-loop-started\n"
    assert len(state.get("call_frames", {})) == 1


def test_structured_if_else_demo_runtime(tmp_path: Path):
    """Structured if/else demo lowers branch outputs onto the statement node."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "structured_if_else_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RouteReview.then.WriteApproved"]["status"] == "completed"
    assert state["steps"]["RouteReview.else.WriteRevision"]["status"] == "skipped"
    assert state["steps"]["RouteReview"]["artifacts"]["review_decision"] == "APPROVE"


def test_finally_demo_runtime(tmp_path: Path):
    """Finally demo runs cleanup before exporting workflow outputs."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "finally_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["WriteDecision"]["artifacts"]["review_decision"] == "APPROVE"
    assert state["steps"]["finally.AssertOutputsPending"]["status"] == "completed"
    assert state["steps"]["finally.WriteCleanupMarker"]["status"] == "completed"
    assert state["workflow_outputs"] == {"final_decision": "APPROVE"}


def test_match_demo_runtime(tmp_path: Path):
    """Match demo branches on an enum decision and materializes the selected output."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "match_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RouteDecision.APPROVE.WriteApprovedAction"]["status"] == "skipped"
    assert state["steps"]["RouteDecision.REVISE.WriteRevisionAction"]["status"] == "skipped"
    assert state["steps"]["RouteDecision.BLOCKED.WriteBlockedAction"]["status"] == "completed"
    assert state["steps"]["RouteDecision"]["artifacts"] == {"route_action": "ESCALATE"}


def test_repeat_until_demo_runtime(tmp_path: Path):
    """repeat_until demo exposes loop-frame outputs and persists per-iteration results."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "repeat_until_demo.yaml")
    _copy_repo_file_to_workspace(workspace, "workflows/examples/library/repeat_until_review_loop.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ReviewLoop[0].RunReviewLoop"]["artifacts"]["review_decision"] == "REVISE"
    assert state["steps"]["ReviewLoop[1].RunReviewLoop"]["artifacts"]["review_decision"] == "REVISE"
    assert state["steps"]["ReviewLoop[2].RunReviewLoop"]["artifacts"]["review_decision"] == "APPROVE"
    assert state["steps"]["ReviewLoop[0].RouteDecision.REVISE.WriteRevision"]["status"] == "completed"
    assert state["steps"]["ReviewLoop[2].RouteDecision.APPROVE.WriteApproved"]["status"] == "completed"
    assert len(state.get("call_frames", {})) == 3
    assert (workspace / "state" / "review-loop" / "history.log").read_text(encoding="utf-8").splitlines() == [
        "iteration-1",
        "iteration-2",
        "iteration-3",
    ]


def test_score_gate_demo_runtime(tmp_path: Path):
    """Score gate demo uses score thresholds and score bands without shell glue."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "score_gate_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["GatePassingScore"]["status"] == "completed"
    assert state["steps"]["RouteScoreBand"]["artifacts"] == {"route_action": "REVIEW"}
    assert state["steps"]["CheckRouteAction"]["status"] == "completed"


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


def test_typed_predicate_routing_runtime(tmp_path: Path):
    """Typed predicate demo gates on normalized failure outcome and artifact refs."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "typed_predicate_routing.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["steps"]["RunCheck"]["outcome"]["class"] == "command_failed"
    assert state["steps"]["GateRecoveredFailure"]["status"] == "completed"
    assert state["steps"]["RunHighScorePath"]["status"] == "completed"


def test_workflow_signature_demo_runtime(tmp_path: Path):
    """Workflow-signature demo binds typed inputs and exports typed workflow outputs."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "workflow_signature_demo.yaml")
    _copy_repo_file_to_workspace(workspace, "workflows/examples/inputs/demo-task.md")

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bound_inputs={
            "task_path": "workflows/examples/inputs/demo-task.md",
            "max_cycles": 3,
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "report_path": "artifacts/reports/demo-task-report.md",
        "cycles_used": 3,
    }


def test_scalar_bookkeeping_demo_runtime(tmp_path: Path):
    """Scalar bookkeeping demo emits local artifacts and publishes lineage."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "scalar_bookkeeping_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["IncrementCount"]["artifacts"] == {"failed_count": 2}
    assert [entry["value"] for entry in state["artifact_versions"]["failed_count"]] == [0, 2]
    assert state["steps"]["GateFinalCount"]["status"] == "completed"


def test_cycle_guard_demo_runtime(tmp_path: Path):
    """Cycle guard demo fails closed once the visit budget is exhausted."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(tmp_path, "cycle_guard_demo.yaml")
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    state = executor.execute(on_error="continue")

    assert state["status"] == "failed"
    assert state["steps"]["GuardLoop"]["error"]["type"] == "cycle_guard_exceeded"
    assert state["step_visits"]["GuardLoop"] == 3
    assert "RecordGuardTrip" not in state["steps"]


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


def test_dsl_review_first_fix_loop_runtime(tmp_path: Path):
    """Review-first fix loop exits only after a review pass omits the high-severity section."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "dsl_review_first_fix_loop.yaml"
    )
    _copy_repo_file_to_workspace(workspace, "prompts/workflows/dsl_review_fix_loop/review.md")
    _copy_repo_file_to_workspace(workspace, "prompts/workflows/dsl_review_fix_loop/fix.md")
    _copy_repo_file_to_workspace(workspace, "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md")

    review_calls = {"count": 0}

    def _write_review(ws: Path) -> None:
        review_calls["count"] += 1
        review_relpath = (ws / "state" / "review_path.txt").read_text().strip()
        review_path = ws / review_relpath
        review_path.parent.mkdir(parents=True, exist_ok=True)
        if review_calls["count"] == 1:
            review_path.write_text(
                "## High\n- The typed predicate boundary is underspecified.\n"
            )
            return
        review_path.write_text("## Medium\n- Remaining edits are polish-level.\n")

    def _apply_fix(ws: Path) -> None:
        target = ws / "docs" / "plans" / "2026-03-06-dsl-evolution-control-flow-and-reuse.md"
        target.write_text(target.read_text() + "\nResolved the highest-severity review feedback.\n")

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["ReviewDraft", "FixIssues", "ReviewDraft"],
        provider_writers={
            "ReviewDraft": _write_review,
            "FixIssues": _apply_fix,
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 3
    assert state["steps"]["IncrementReviewCycle"]["artifacts"]["review_cycle"] == 1

    versions = state.get("artifact_versions", {}).get("review", [])
    assert [entry["producer"] for entry in versions] == ["ReviewDraft", "ReviewDraft"]
    assert [entry["value"] for entry in versions] == [
        "artifacts/review/review-cycle-0.md",
        "artifacts/review/review-cycle-1.md",
    ]

    consumes = state.get("artifact_consumes", {}).get("FixIssues", {})
    assert consumes.get("review") == 1


def test_dsl_review_first_fix_loop_provider_session_runtime(tmp_path: Path):
    """Provider-session example publishes review-loop session handles and keeps them out of prompts."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "dsl_review_first_fix_loop_provider_session.yaml"
    )
    _copy_repo_file_to_workspace(workspace, "prompts/workflows/dsl_review_fix_loop_provider_session/review.md")
    _copy_repo_file_to_workspace(workspace, "prompts/workflows/dsl_review_fix_loop_provider_session/fix.md")
    _copy_repo_file_to_workspace(workspace, "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md")

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    provider_sequence = ["ReviewDraft", "FixIssues", "ReviewDraft"]
    prepare_index = {"value": 0}
    execute_index = {"value": 0}
    captured_prompts: list[dict[str, str]] = []

    def _write_review(ws: Path, *, high: bool) -> None:
        review_relpath = (ws / "state" / "review_path.txt").read_text(encoding="utf-8").strip()
        review_path = ws / review_relpath
        review_path.parent.mkdir(parents=True, exist_ok=True)
        if high:
            review_path.write_text("## High\n- The typed predicate boundary is underspecified.\n", encoding="utf-8")
        else:
            review_path.write_text("## Medium\n- Remaining edits are polish-level.\n", encoding="utf-8")

    def _prepare_invocation(_self, *args, **kwargs):
        step_name = provider_sequence[prepare_index["value"]]
        prepare_index["value"] += 1
        session_request = kwargs.get("session_request")
        command_variant = "command"
        metadata_mode = None
        if session_request is not None:
            command_variant = "fresh_command" if session_request.mode.value == "fresh" else "resume_command"
            metadata_mode = "codex_exec_jsonl_stdout"
        captured_prompts.append({"step": step_name, "prompt": kwargs.get("prompt_content", "") or ""})
        return SimpleNamespace(
            input_mode="stdin",
            prompt=kwargs.get("prompt_content", "") or "",
            command=["mock-provider", step_name],
            command_variant=command_variant,
            metadata_mode=metadata_mode,
            session_request=session_request,
        ), None

    def _execute(_self, invocation, **_kwargs):
        step_name = provider_sequence[execute_index["value"]]
        execute_index["value"] += 1

        if step_name == "ReviewDraft" and execute_index["value"] == 1:
            _write_review(workspace, high=True)
            session_id = "sess-123"
        elif step_name == "FixIssues":
            target = workspace / "docs" / "plans" / "2026-03-06-dsl-evolution-control-flow-and-reuse.md"
            target.write_text(
                target.read_text(encoding="utf-8") + "\nResolved the highest-severity review feedback.\n",
                encoding="utf-8",
            )
            session_id = invocation.session_request.session_id
        else:
            _write_review(workspace, high=False)
            session_id = "sess-456"

        raw_stdout = "\n".join(
            [
                json.dumps({"type": "session.started", "session_id": session_id}),
                json.dumps({"type": "assistant.message", "role": "assistant", "text": "ok"}),
                json.dumps({"type": "response.completed", "session_id": session_id}),
            ]
        ).encode("utf-8") + b"\n"

        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=raw_stdout,
            normalized_stdout=b"ok",
            provider_session={
                "session_id": session_id,
                "normalized_stdout": "ok",
                "event_count": 3,
            },
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()

    assert state["status"] == "completed"
    assert execute_index["value"] == 3
    versions = state.get("artifact_versions", {}).get("implementation_session_id", [])
    assert [entry["value"] for entry in versions] == ["sess-123", "sess-456"]
    consumes = state.get("artifact_consumes", {}).get("root.fixissues", {})
    assert consumes.get("implementation_session_id") == 1
    assert consumes.get("review") == 1

    fix_prompt = next(item["prompt"] for item in captured_prompts if item["step"] == "FixIssues")
    assert "artifacts/review/review-cycle-0.md" in fix_prompt
    assert "sess-123" not in fix_prompt


def test_dsl_follow_on_plan_impl_review_loop_runtime(tmp_path: Path):
    """Follow-on workflow waits for upstream completion, then runs plan and implementation review/fix loops."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "dsl_follow_on_plan_impl_review_loop.yaml"
    )
    for prompt_file in [
        "prompts/workflows/dsl_follow_on_plan_impl_loop/draft_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop/review_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop/revise_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop/implement_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop/review_implementation.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop/fix_implementation.md",
    ]:
        _copy_repo_file_to_workspace(workspace, prompt_file)
    _copy_repo_file_to_workspace(workspace, "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md")

    upstream_state = workspace / ".orchestrate" / "runs" / "20260307T083549Z-9hctad" / "state.json"
    upstream_state.parent.mkdir(parents=True, exist_ok=True)
    upstream_state.write_text('{"status":"completed"}\n')

    plan_review_calls = {"count": 0}
    implementation_review_calls = {"count": 0}
    def _write_plan(review_content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/plan_path.txt",
                "docs/plans/2026-03-06-dsl-evolution-execution-plan.md",
                review_content,
            )

        return _writer

    def _write_plan_review(ws: Path) -> None:
        plan_review_calls["count"] += 1
        report_relpath = (ws / "state" / "plan_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if plan_review_calls["count"] == 1:
            report_path.write_text("## High\n- The implementation sequence is underspecified.\n")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Residual edits are non-blocking.\n")
            decision = "APPROVE"
        (ws / "state" / "plan_review_decision.txt").write_text(f"{decision}\n")

    def _write_execution_report(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/execution_report_path.txt",
                "artifacts/work/dsl-evolution-implementation-report.md",
                content,
            )

        return _writer

    def _write_implementation_review(ws: Path) -> None:
        implementation_review_calls["count"] += 1
        report_relpath = (ws / "state" / "implementation_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if implementation_review_calls["count"] == 1:
            report_path.write_text("## High\n- The implementation missed a blocking edge case.\n")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Remaining follow-ups are polish.\n")
            decision = "APPROVE"
        (ws / "state" / "implementation_review_decision.txt").write_text(f"{decision}\n")

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=[
            "DraftPlan",
            "ReviewPlan",
            "RevisePlan",
            "ReviewPlan",
            "ExecuteImplementation",
            "ReviewImplementation",
            "FixImplementation",
            "ReviewImplementation",
        ],
        provider_writers={
            "DraftPlan": _write_plan("# Draft plan\n"),
            "ReviewPlan": _write_plan_review,
            "RevisePlan": _write_plan("# Revised plan\n"),
            "ExecuteImplementation": _write_execution_report("Initial implementation report\n"),
            "ReviewImplementation": _write_implementation_review,
            "FixImplementation": _write_execution_report("Updated implementation report after fixes\n"),
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 8
    assert state["steps"]["IncrementPlanCycle"]["artifacts"]["plan_cycle"] == 1
    assert state["steps"]["IncrementImplementationCycle"]["artifacts"]["implementation_cycle"] == 1

    plan_versions = state.get("artifact_versions", {}).get("plan", [])
    assert [entry["producer"] for entry in plan_versions] == ["DraftPlan", "RevisePlan"]

    execution_versions = state.get("artifact_versions", {}).get("execution_report", [])
    assert [entry["producer"] for entry in execution_versions] == ["ExecuteImplementation", "FixImplementation"]

    draft_consumes = state.get("artifact_consumes", {}).get("DraftPlan", {})
    assert draft_consumes == {"design": 1}

    review_plan_consumes = state.get("artifact_consumes", {}).get("ReviewPlan", {})
    assert review_plan_consumes == {"design": 1, "plan": 2}

    revise_consumes = state.get("artifact_consumes", {}).get("RevisePlan", {})
    assert revise_consumes == {"design": 1, "plan": 1, "plan_review_report": 1}

    execute_consumes = state.get("artifact_consumes", {}).get("ExecuteImplementation", {})
    assert execute_consumes == {"design": 1, "plan": 2}

    implementation_review_consumes = state.get("artifact_consumes", {}).get("ReviewImplementation", {})
    assert implementation_review_consumes == {"design": 1, "execution_report": 2, "plan": 2}

    fix_consumes = state.get("artifact_consumes", {}).get("FixImplementation", {})
    assert fix_consumes == {
        "design": 1,
        "execution_report": 1,
        "implementation_review_report": 1,
        "plan": 2,
    }


def test_dsl_follow_on_plan_impl_review_loop_v2_runtime(tmp_path: Path):
    """V2 follow-on workflow uses typed inputs plus structured match/repeat_until loops."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "dsl_follow_on_plan_impl_review_loop_v2.yaml"
    )
    for prompt_file in [
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2/draft_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2/review_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2/revise_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2/implement_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2/review_implementation.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2/fix_implementation.md",
        "workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json",
        "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md",
    ]:
        _copy_repo_file_to_workspace(workspace, prompt_file)

    plan_review_calls = {"count": 0}
    implementation_review_calls = {"count": 0}

    def _write_plan(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/plan_path.txt",
                "docs/plans/2026-03-06-dsl-evolution-execution-plan-v2.md",
                content,
            )

        return _writer

    def _write_plan_review(ws: Path) -> None:
        plan_review_calls["count"] += 1
        report_relpath = (ws / "state" / "plan_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if plan_review_calls["count"] == 1:
            report_path.write_text("## High\n- Plan needs one blocking revision.\n")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Remaining plan edits are non-blocking.\n")
            decision = "APPROVE"
        (ws / "state" / "plan_review_decision.txt").write_text(f"{decision}\n")

    def _write_execution_report(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/execution_report_path.txt",
                "artifacts/work/dsl-evolution-implementation-report-v2.md",
                content,
            )

        return _writer

    def _write_implementation_review(ws: Path) -> None:
        implementation_review_calls["count"] += 1
        report_relpath = (ws / "state" / "implementation_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if implementation_review_calls["count"] == 1:
            report_path.write_text("## High\n- Implementation needs one blocking fix.\n")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Remaining implementation edits are non-blocking.\n")
            decision = "APPROVE"
        (ws / "state" / "implementation_review_decision.txt").write_text(f"{decision}\n")

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bundle_context_dict(workflow),
        bound_inputs={
            "upstream_state_path": "workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json",
            "design_path": "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md",
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    provider_sequence = [
        "DraftPlan",
        "PlanReviewLoop[0].ReviewPlan",
        "PlanReviewLoop[0].RoutePlanDecision.REVISE.RevisePlan",
        "PlanReviewLoop[1].ReviewPlan",
        "ExecuteImplementation",
        "ImplementationReviewLoop[0].ReviewImplementation",
        "ImplementationReviewLoop[0].RouteImplementationDecision.REVISE.FixImplementation",
        "ImplementationReviewLoop[1].ReviewImplementation",
    ]
    call_index = {"value": 0}

    def _prepare_invocation(_self, *_args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        step_name = provider_sequence[call_index["value"]]
        call_index["value"] += 1
        if step_name == "DraftPlan":
            _write_plan("# Draft v2 plan\n")(workspace)
        elif step_name.endswith("ReviewPlan"):
            _write_plan_review(workspace)
        elif step_name.endswith("RevisePlan"):
            _write_plan("# Revised v2 plan\n")(workspace)
        elif step_name == "ExecuteImplementation":
            _write_execution_report("Initial v2 implementation report\n")(workspace)
        elif step_name.endswith("ReviewImplementation"):
            _write_implementation_review(workspace)
        elif step_name.endswith("FixImplementation"):
            _write_execution_report("Updated v2 implementation report after fixes\n")(workspace)
        else:
            raise AssertionError(f"Unexpected provider step {step_name}")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    state["__provider_calls"] = call_index["value"]

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 8
    assert state["workflow_outputs"] == {
        "plan_path": "docs/plans/2026-03-06-dsl-evolution-execution-plan-v2.md",
        "execution_report_path": "artifacts/work/dsl-evolution-implementation-report-v2.md",
        "implementation_review_report_path": "artifacts/review/dsl-evolution-implementation-review.md",
        "implementation_review_decision": "APPROVE",
    }

    assert state["steps"]["PlanReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ImplementationReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["PlanReviewLoop[0].RoutePlanDecision.REVISE.RevisePlan"]["status"] == "completed"
    assert state["steps"]["ImplementationReviewLoop[0].RouteImplementationDecision.REVISE.FixImplementation"][
        "status"
    ] == "completed"
    assert state["steps"]["PlanReviewLoop[1].RoutePlanDecision.APPROVE"]["status"] == "completed"
    assert state["steps"]["ImplementationReviewLoop[1].RouteImplementationDecision.APPROVE"]["status"] == "completed"
    assert "PlanReviewGate" not in state["steps"]
    assert "PlanCycleGate" not in state["steps"]
    assert "ImplementationReviewGate" not in state["steps"]
    assert "ImplementationCycleGate" not in state["steps"]

    assert state["bound_inputs"] == {
        "upstream_state_path": "workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json",
        "design_path": "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md",
    }

    plan_versions = state.get("artifact_versions", {}).get("plan", [])
    plan_producers = [entry["producer"] for entry in plan_versions]
    assert len(plan_producers) == 2
    assert plan_producers[0].endswith("draft_plan")
    assert plan_producers[1].endswith("revise_plan")

    execution_versions = state.get("artifact_versions", {}).get("execution_report", [])
    execution_producers = [entry["producer"] for entry in execution_versions]
    assert len(execution_producers) == 2
    assert execution_producers[0].endswith("execute_implementation")
    assert execution_producers[1].endswith("fix_implementation")


def test_dsl_follow_on_plan_impl_review_loop_v2_call_runtime(tmp_path: Path):
    """Modular v2 parent delegates plan and implementation phases through reusable call steps."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "dsl_follow_on_plan_impl_review_loop_v2_call.yaml"
    )
    for repo_file in [
        "workflows/library/follow_on_plan_phase.yaml",
        "workflows/library/follow_on_implementation_phase.yaml",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/draft_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/review_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/revise_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/implement_plan.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/review_implementation.md",
        "prompts/workflows/dsl_follow_on_plan_impl_loop_v2_call/fix_implementation.md",
        "workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json",
        "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md",
    ]:
        _copy_repo_file_to_workspace(workspace, repo_file)

    plan_review_calls = {"count": 0}
    implementation_review_calls = {"count": 0}
    call_index = {"value": 0}

    def _write_plan(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/follow-on-plan-phase/plan_path.txt",
                "docs/plans/2026-03-06-dsl-evolution-execution-plan-v2-call.md",
                content,
            )

        return _writer

    def _write_plan_review(ws: Path) -> None:
        plan_review_calls["count"] += 1
        report_relpath = (ws / "state" / "follow-on-plan-phase" / "plan_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if plan_review_calls["count"] == 1:
            report_path.write_text("## High\n- Plan needs one blocking revision.\n")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Remaining plan edits are non-blocking.\n")
            decision = "APPROVE"
        (ws / "state" / "follow-on-plan-phase" / "plan_review_decision.txt").write_text(f"{decision}\n")

    def _write_execution_report(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/follow-on-implementation-phase/execution_report_path.txt",
                "artifacts/work/dsl-evolution-implementation-report-v2-call.md",
                content,
            )

        return _writer

    def _write_implementation_review(ws: Path) -> None:
        implementation_review_calls["count"] += 1
        report_relpath = (
            ws / "state" / "follow-on-implementation-phase" / "implementation_review_report_path.txt"
        ).read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if implementation_review_calls["count"] == 1:
            report_path.write_text("## High\n- Implementation needs one blocking fix.\n")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Remaining implementation edits are non-blocking.\n")
            decision = "APPROVE"
        (ws / "state" / "follow-on-implementation-phase" / "implementation_review_decision.txt").write_text(
            f"{decision}\n"
        )

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bundle_context_dict(workflow),
        bound_inputs={
            "upstream_state_path": "workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json",
            "design_path": "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md",
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    def _prepare_invocation(_self, *_args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        index = call_index["value"]
        call_index["value"] += 1
        if index == 0:
            _write_plan("# Draft call-based v2 plan\n")(workspace)
        elif index == 1:
            _write_plan_review(workspace)
        elif index == 2:
            _write_plan("# Revised call-based v2 plan\n")(workspace)
        elif index == 3:
            _write_plan_review(workspace)
        elif index == 4:
            _write_execution_report("Initial call-based implementation report\n")(workspace)
        elif index == 5:
            _write_implementation_review(workspace)
        elif index == 6:
            _write_execution_report("Updated call-based implementation report after fixes\n")(workspace)
        elif index == 7:
            _write_implementation_review(workspace)
        else:
            raise AssertionError(f"Unexpected provider invocation index {index}")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    state["__provider_calls"] = call_index["value"]

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 8
    assert state["workflow_outputs"] == {
        "plan_path": "docs/plans/2026-03-06-dsl-evolution-execution-plan-v2-call.md",
        "execution_report_path": "artifacts/work/dsl-evolution-implementation-report-v2-call.md",
        "implementation_review_report_path": "artifacts/review/dsl-evolution-implementation-review-v2-call.md",
        "implementation_review_decision": "APPROVE",
    }
    assert state["steps"]["RunPlanPhase"]["artifacts"] == {
        "plan_path": "docs/plans/2026-03-06-dsl-evolution-execution-plan-v2-call.md",
        "plan_review_report_path": "artifacts/review/dsl-evolution-plan-review-v2-call.md",
        "plan_review_decision": "APPROVE",
    }
    assert state["steps"]["RunImplementationPhase"]["artifacts"] == {
        "execution_report_path": "artifacts/work/dsl-evolution-implementation-report-v2-call.md",
        "implementation_review_report_path": "artifacts/review/dsl-evolution-implementation-review-v2-call.md",
        "implementation_review_decision": "APPROVE",
    }
    assert "PublishFinalOutputs" not in state["steps"]
    assert len(state.get("call_frames", {})) == 2


def test_backlog_priority_design_plan_impl_stack_v2_call_runtime(tmp_path: Path):
    """Priority backlog driver skips failed items and keeps processing later ones."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "backlog_priority_design_plan_impl_stack_v2_call.yaml"
    )
    for repo_file in [
        "workflows/library/backlog_item_design_plan_impl_stack.yaml",
        "workflows/library/tracked_design_phase.yaml",
        "workflows/library/tracked_plan_phase.yaml",
        "workflows/library/design_plan_impl_implementation_phase.yaml",
        "prompts/workflows/design_plan_impl_stack_v2_call/draft_design.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/review_design.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/revise_design.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/draft_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/review_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/revise_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/implement_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/review_implementation.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/fix_implementation.md",
        "workflows/examples/inputs/backlog_priority_items.json",
        "docs/backlog/active/2026-03-09-typed-workflow-ast-ir-pipeline.md",
        "docs/backlog/active/2026-03-09-depends-on-inject-imported-v2-workflows.md",
        "docs/backlog/active/2026-03-09-provider-prompt-source-surface-clarity.md",
    ]:
        _copy_repo_file_to_workspace(workspace, repo_file)

    provider_index = {"value": 0}

    def _write_design(ws: Path, state_root: str, item_id: str) -> None:
        _write_relpath_artifact(
            ws,
            f"{state_root}/design_path.txt",
            f"docs/plans/{item_id}-design.md",
            f"# Design for {item_id}\n",
        )

    def _write_design_review(ws: Path, state_root: str, decision: str) -> None:
        report_relpath = (ws / state_root / "design_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "decision": decision,
            "summary": f"Design review decision: {decision}",
            "unresolved_high_count": 0 if decision == "APPROVE" else 1,
            "unresolved_medium_count": 0,
            "findings": [],
        }
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (ws / state_root / "design_review_decision.txt").write_text(f"{decision}\n", encoding="utf-8")
        (ws / state_root / "unresolved_high_count.txt").write_text(
            f"{payload['unresolved_high_count']}\n", encoding="utf-8"
        )
        (ws / state_root / "unresolved_medium_count.txt").write_text(
            f"{payload['unresolved_medium_count']}\n", encoding="utf-8"
        )

    def _write_plan(ws: Path, state_root: str, item_id: str) -> None:
        _write_relpath_artifact(
            ws,
            f"{state_root}/plan_path.txt",
            f"docs/plans/{item_id}-execution-plan.md",
            f"# Plan for {item_id}\n",
        )

    def _write_plan_review(ws: Path, state_root: str, decision: str) -> None:
        report_relpath = (ws / state_root / "plan_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "decision": decision,
            "summary": f"Plan review decision: {decision}",
            "unresolved_high_count": 0,
            "unresolved_medium_count": 0,
            "findings": [],
        }
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (ws / state_root / "plan_review_decision.txt").write_text(f"{decision}\n", encoding="utf-8")
        (ws / state_root / "unresolved_high_count.txt").write_text("0\n", encoding="utf-8")
        (ws / state_root / "unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")

    def _write_execution_report(ws: Path, state_root: str, item_id: str) -> None:
        _write_relpath_artifact(
            ws,
            f"{state_root}/execution_report_path.txt",
            f"artifacts/work/{item_id}-execution-report.md",
            f"Execution report for {item_id}\n",
        )

    def _write_implementation_review(ws: Path, state_root: str, decision: str) -> None:
        report_relpath = (ws / state_root / "implementation_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"## Decision\n{decision}\n", encoding="utf-8")
        (ws / state_root / "implementation_review_decision.txt").write_text(f"{decision}\n", encoding="utf-8")

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bundle_context_dict(workflow),
        bound_inputs={"backlog_manifest_path": "workflows/examples/inputs/backlog_priority_items.json"},
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    def _prepare_invocation(_self, *_args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        index = provider_index["value"]
        provider_index["value"] += 1
        if index == 0:
            return SimpleNamespace(
                exit_code=1,
                stdout=b"",
                stderr=b"draft design failed",
                duration_ms=1,
                error=None,
                missing_placeholders=None,
                invalid_prompt_placeholder=False,
                provider_session=None,
            )
        if index == 1:
            _write_design(
                workspace,
                "state/backlog-priority-stack/depends-on-inject-imported-v2-workflows/design-phase",
                "depends-on-inject-imported-v2-workflows",
            )
        elif index == 2:
            _write_design_review(
                workspace,
                "state/backlog-priority-stack/depends-on-inject-imported-v2-workflows/design-phase",
                "APPROVE",
            )
        elif index == 3:
            _write_plan(
                workspace,
                "state/backlog-priority-stack/depends-on-inject-imported-v2-workflows/plan-phase",
                "depends-on-inject-imported-v2-workflows",
            )
        elif index == 4:
            _write_plan_review(
                workspace,
                "state/backlog-priority-stack/depends-on-inject-imported-v2-workflows/plan-phase",
                "APPROVE",
            )
        elif index == 5:
            _write_execution_report(
                workspace,
                "state/backlog-priority-stack/depends-on-inject-imported-v2-workflows/implementation-phase",
                "depends-on-inject-imported-v2-workflows",
            )
        elif index == 6:
            _write_implementation_review(
                workspace,
                "state/backlog-priority-stack/depends-on-inject-imported-v2-workflows/implementation-phase",
                "APPROVE",
            )
        elif index == 7:
            _write_design(
                workspace,
                "state/backlog-priority-stack/workflow-authoring-surface-clarity/design-phase",
                "workflow-authoring-surface-clarity",
            )
        elif index == 8:
            _write_design_review(
                workspace,
                "state/backlog-priority-stack/workflow-authoring-surface-clarity/design-phase",
                "APPROVE",
            )
        elif index == 9:
            _write_plan(
                workspace,
                "state/backlog-priority-stack/workflow-authoring-surface-clarity/plan-phase",
                "workflow-authoring-surface-clarity",
            )
        elif index == 10:
            _write_plan_review(
                workspace,
                "state/backlog-priority-stack/workflow-authoring-surface-clarity/plan-phase",
                "APPROVE",
            )
        elif index == 11:
            _write_execution_report(
                workspace,
                "state/backlog-priority-stack/workflow-authoring-surface-clarity/implementation-phase",
                "workflow-authoring-surface-clarity",
            )
        elif index == 12:
            _write_implementation_review(
                workspace,
                "state/backlog-priority-stack/workflow-authoring-surface-clarity/implementation-phase",
                "APPROVE",
            )
        else:
            raise AssertionError(f"Unexpected provider invocation index {index}")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["ProcessBacklogItems"][0]["RunItemWorkflow"]["artifacts"]["item_outcome"] == "SKIPPED_AFTER_DESIGN"
    assert state["steps"]["ProcessBacklogItems"][1]["RunItemWorkflow"]["artifacts"]["item_outcome"] == "APPROVED"
    assert state["steps"]["ProcessBacklogItems"][2]["RunItemWorkflow"]["artifacts"]["item_outcome"] == "APPROVED"
    assert (
        state["steps"]["ProcessBacklogItems"][1]["RunItemWorkflow"]["artifacts"]["execution_report_path"]
        == "artifacts/work/depends-on-inject-imported-v2-workflows-execution-report.md"
    )


def test_design_plan_impl_review_stack_v2_call_runtime(tmp_path: Path):
    """Call-based stack runs tracked design, tracked plan, then implementation review/fix."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "design_plan_impl_review_stack_v2_call.yaml"
    )
    for repo_file in [
        "workflows/library/tracked_design_phase.yaml",
        "workflows/library/tracked_plan_phase.yaml",
        "workflows/library/design_plan_impl_implementation_phase.yaml",
        "prompts/workflows/design_plan_impl_stack_v2_call/draft_design.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/review_design.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/revise_design.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/draft_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/review_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/revise_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/implement_plan.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/review_implementation.md",
        "prompts/workflows/design_plan_impl_stack_v2_call/fix_implementation.md",
        "workflows/examples/inputs/provider_session_resume_brief.md",
    ]:
        _copy_repo_file_to_workspace(workspace, repo_file)

    design_review_calls = {"count": 0}
    plan_review_calls = {"count": 0}
    implementation_review_calls = {"count": 0}
    call_index = {"value": 0}

    def _write_design(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/design-phase-stack/design_path.txt",
                "docs/plans/2026-03-09-provider-session-resume-design.md",
                content,
            )

        return _writer

    def _write_design_review(ws: Path) -> None:
        import json

        design_review_calls["count"] += 1
        report_relpath = (ws / "state" / "design-phase-stack" / "design_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if design_review_calls["count"] == 1:
            payload = {
                "decision": "REVISE",
                "summary": "One blocking design issue remains.",
                "unresolved_high_count": 1,
                "unresolved_medium_count": 0,
                "findings": [
                    {
                        "id": "DESIGN-H1",
                        "status": "STILL_OPEN",
                        "severity": "high",
                        "scope_classification": "blocking_prerequisite",
                        "title": "Session ownership is underspecified",
                    }
                ],
            }
        else:
            payload = {
                "decision": "APPROVE",
                "summary": "Design is ready for planning.",
                "unresolved_high_count": 0,
                "unresolved_medium_count": 1,
                "findings": [
                    {
                        "id": "DESIGN-H1",
                        "status": "RESOLVED",
                        "severity": "high",
                        "scope_classification": "blocking_prerequisite",
                        "title": "Session ownership is underspecified",
                    }
                ],
            }
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (ws / "state" / "design-phase-stack" / "design_review_decision.txt").write_text(
            f"{payload['decision']}\n", encoding="utf-8"
        )
        (ws / "state" / "design-phase-stack" / "unresolved_high_count.txt").write_text(
            f"{payload['unresolved_high_count']}\n", encoding="utf-8"
        )
        (ws / "state" / "design-phase-stack" / "unresolved_medium_count.txt").write_text(
            f"{payload['unresolved_medium_count']}\n", encoding="utf-8"
        )

    def _write_plan(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/plan-phase-stack/plan_path.txt",
                "docs/plans/2026-03-09-provider-session-resume-execution-plan.md",
                content,
            )

        return _writer

    def _write_plan_review(ws: Path) -> None:
        import json

        plan_review_calls["count"] += 1
        report_relpath = (ws / "state" / "plan-phase-stack" / "plan_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if plan_review_calls["count"] == 1:
            payload = {
                "decision": "REVISE",
                "summary": "Plan needs one tranche adjustment.",
                "unresolved_high_count": 1,
                "unresolved_medium_count": 0,
                "findings": [
                    {
                        "id": "PLAN-H1",
                        "status": "STILL_OPEN",
                        "severity": "high",
                        "title": "String support must precede session DSL work",
                    }
                ],
            }
        else:
            payload = {
                "decision": "APPROVE",
                "summary": "Plan is ready to implement.",
                "unresolved_high_count": 0,
                "unresolved_medium_count": 0,
                "findings": [
                    {
                        "id": "PLAN-H1",
                        "status": "RESOLVED",
                        "severity": "high",
                        "title": "String support must precede session DSL work",
                    }
                ],
            }
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (ws / "state" / "plan-phase-stack" / "plan_review_decision.txt").write_text(
            f"{payload['decision']}\n", encoding="utf-8"
        )
        (ws / "state" / "plan-phase-stack" / "unresolved_high_count.txt").write_text(
            f"{payload['unresolved_high_count']}\n", encoding="utf-8"
        )
        (ws / "state" / "plan-phase-stack" / "unresolved_medium_count.txt").write_text(
            f"{payload['unresolved_medium_count']}\n", encoding="utf-8"
        )

    def _write_execution_report(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/implementation-phase-stack/execution_report_path.txt",
                "artifacts/work/provider-session-resume-execution-report.md",
                content,
            )

        return _writer

    def _write_implementation_review(ws: Path) -> None:
        implementation_review_calls["count"] += 1
        report_relpath = (
            ws / "state" / "implementation-phase-stack" / "implementation_review_report_path.txt"
        ).read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if implementation_review_calls["count"] == 1:
            report_path.write_text("## High\n- One blocking runtime gap remains.\n", encoding="utf-8")
            decision = "REVISE"
        else:
            report_path.write_text("## Medium\n- Remaining issues are non-blocking.\n", encoding="utf-8")
            decision = "APPROVE"
        (ws / "state" / "implementation-phase-stack" / "implementation_review_decision.txt").write_text(
            f"{decision}\n", encoding="utf-8"
        )

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bundle_context_dict(workflow),
        bound_inputs={
            "brief_path": "workflows/examples/inputs/provider_session_resume_brief.md",
            "design_target_path": "docs/plans/2026-03-09-provider-session-resume-design.md",
            "design_review_report_target_path": "artifacts/review/provider-session-resume-design-review.json",
            "plan_target_path": "docs/plans/2026-03-09-provider-session-resume-execution-plan.md",
            "plan_review_report_target_path": "artifacts/review/provider-session-resume-plan-review.json",
            "execution_report_target_path": "artifacts/work/provider-session-resume-execution-report.md",
            "implementation_review_report_target_path": "artifacts/review/provider-session-resume-implementation-review.md",
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    def _prepare_invocation(_self, *_args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        index = call_index["value"]
        call_index["value"] += 1
        if index == 0:
            _write_design("# Draft provider-session resume design\n")(workspace)
        elif index == 1:
            _write_design_review(workspace)
        elif index == 2:
            _write_design("# Revised provider-session resume design\n")(workspace)
        elif index == 3:
            _write_design_review(workspace)
        elif index == 4:
            _write_plan("# Draft provider-session resume plan\n")(workspace)
        elif index == 5:
            _write_plan_review(workspace)
        elif index == 6:
            _write_plan("# Revised provider-session resume plan\n")(workspace)
        elif index == 7:
            _write_plan_review(workspace)
        elif index == 8:
            _write_execution_report("Initial implementation report\n")(workspace)
        elif index == 9:
            _write_implementation_review(workspace)
        elif index == 10:
            _write_execution_report("Updated implementation report after fixes\n")(workspace)
        elif index == 11:
            _write_implementation_review(workspace)
        else:
            raise AssertionError(f"Unexpected provider invocation index {index}")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    state["__provider_calls"] = call_index["value"]

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 12
    assert state["workflow_outputs"] == {
        "design_path": "docs/plans/2026-03-09-provider-session-resume-design.md",
        "design_review_report_path": "artifacts/review/provider-session-resume-design-review.json",
        "design_review_decision": "APPROVE",
        "plan_path": "docs/plans/2026-03-09-provider-session-resume-execution-plan.md",
        "plan_review_report_path": "artifacts/review/provider-session-resume-plan-review.json",
        "plan_review_decision": "APPROVE",
        "execution_report_path": "artifacts/work/provider-session-resume-execution-report.md",
        "implementation_review_report_path": "artifacts/review/provider-session-resume-implementation-review.md",
        "implementation_review_decision": "APPROVE",
    }
    assert state["steps"]["RunDesignPhase"]["artifacts"] == {
        "design_path": "docs/plans/2026-03-09-provider-session-resume-design.md",
        "design_review_report_path": "artifacts/review/provider-session-resume-design-review.json",
        "design_review_decision": "APPROVE",
    }
    assert state["steps"]["RunPlanPhase"]["artifacts"] == {
        "plan_path": "docs/plans/2026-03-09-provider-session-resume-execution-plan.md",
        "plan_review_report_path": "artifacts/review/provider-session-resume-plan-review.json",
        "plan_review_decision": "APPROVE",
    }
    assert state["steps"]["RunImplementationPhase"]["artifacts"] == {
        "execution_report_path": "artifacts/work/provider-session-resume-execution-report.md",
        "implementation_review_report_path": "artifacts/review/provider-session-resume-implementation-review.md",
        "implementation_review_decision": "APPROVE",
    }
    assert len(state.get("call_frames", {})) == 3


def test_dsl_tracked_plan_review_loop_runtime(tmp_path: Path):
    """Tracked plan review loop carries forward only unresolved findings and exits when highs reach zero."""
    workspace, workflow_path, workflow_relpath = _copy_example_to_workspace(
        tmp_path, "dsl_tracked_plan_review_loop.yaml"
    )
    for prompt_file in [
        "prompts/workflows/dsl_tracked_plan_review_loop/draft_plan.md",
        "prompts/workflows/dsl_tracked_plan_review_loop/review_plan.md",
        "prompts/workflows/dsl_tracked_plan_review_loop/revise_plan.md",
    ]:
        _copy_repo_file_to_workspace(workspace, prompt_file)
    _copy_repo_file_to_workspace(workspace, "docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md")

    review_calls = {"count": 0}

    def _write_plan(content: str) -> Callable[[Path], None]:
        def _writer(ws: Path) -> None:
            _write_relpath_artifact(
                ws,
                "state/plan_path.txt",
                "docs/plans/2026-03-06-dsl-evolution-execution-plan.md",
                content,
            )

        return _writer

    def _write_review(ws: Path) -> None:
        import json

        review_calls["count"] += 1
        report_relpath = (ws / "state" / "plan_review_report_path.txt").read_text().strip()
        report_path = ws / report_relpath
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if review_calls["count"] == 1:
            payload = {
                "decision": "REVISE",
                "summary": "One blocking finding remains.",
                "unresolved_high_count": 1,
                "unresolved_medium_count": 0,
                "findings": [
                    {
                        "id": "PLAN-H1",
                        "status": "STILL_OPEN",
                        "severity": "high",
                        "title": "Missing typed assert coverage",
                    },
                    {
                        "id": "PLAN-M1",
                        "status": "RESOLVED",
                        "severity": "medium",
                        "title": "Legacy loop coverage added",
                    },
                ],
            }
        else:
            payload = {
                "decision": "APPROVE",
                "summary": "No unresolved high findings remain.",
                "unresolved_high_count": 0,
                "unresolved_medium_count": 1,
                "findings": [
                    {
                        "id": "PLAN-H1",
                        "status": "RESOLVED",
                        "severity": "high",
                        "title": "Missing typed assert coverage",
                    },
                    {
                        "id": "PLAN-M2",
                        "status": "NEW",
                        "severity": "medium",
                        "title": "Final sweep should retain one more smoke check",
                    },
                ],
            }
        report_path.write_text(json.dumps(payload, indent=2) + "\n")
        (ws / "state" / "plan_review_decision.txt").write_text(f"{payload['decision']}\n")
        (ws / "state" / "unresolved_high_count.txt").write_text(f"{payload['unresolved_high_count']}\n")
        (ws / "state" / "unresolved_medium_count.txt").write_text(f"{payload['unresolved_medium_count']}\n")

    def _write_resolution(ws: Path) -> None:
        import json

        resolution_relpath = (ws / "state" / "plan_resolution_report_path.txt").read_text().strip()
        resolution_path = ws / resolution_relpath
        resolution_path.parent.mkdir(parents=True, exist_ok=True)
        resolution_path.write_text(
            json.dumps(
                {
                    "addressed": [
                        {
                            "id": "PLAN-H1",
                            "change_summary": "Task 3 now broadens assert to typed predicates.",
                        }
                    ],
                    "not_addressed": [],
                },
                indent=2,
            )
            + "\n"
        )
        _write_plan("# Revised tracked plan\n")(ws)

    state = _run_with_mocked_providers(
        workspace=workspace,
        workflow_path=workflow_path,
        workflow_relpath=workflow_relpath,
        provider_sequence=["DraftPlan", "ReviewPlanTracked", "RevisePlanTracked", "ReviewPlanTracked"],
        provider_writers={
            "DraftPlan": _write_plan("# Draft tracked plan\n"),
            "ReviewPlanTracked": _write_review,
            "RevisePlanTracked": _write_resolution,
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 4
    assert state["steps"]["IncrementPlanCycle"]["artifacts"]["plan_cycle"] == 1

    review_versions = state.get("artifact_versions", {}).get("plan_review_report", [])
    assert [entry["value"] for entry in review_versions] == [
        "artifacts/review/plan-review-cycle-0.json",
        "artifacts/review/plan-review-cycle-1.json",
    ]

    open_findings_versions = state.get("artifact_versions", {}).get("open_findings", [])
    assert [entry["value"] for entry in open_findings_versions] == [
        "artifacts/review/open-findings-seed.json",
        "artifacts/review/open-findings-cycle-1.json",
    ]

    carried_findings = (workspace / "artifacts" / "review" / "open-findings-cycle-1.json").read_text()
    assert '"id": "PLAN-H1"' in carried_findings
    assert '"status": "STILL_OPEN"' in carried_findings
    assert "PLAN-M1" not in carried_findings

    review_consumes = state.get("artifact_consumes", {}).get("ReviewPlanTracked", {})
    assert review_consumes == {"design": 1, "open_findings": 2, "plan": 2}

    revise_consumes = state.get("artifact_consumes", {}).get("RevisePlanTracked", {})
    assert revise_consumes == {"design": 1, "plan": 1, "plan_review_report": 1}
