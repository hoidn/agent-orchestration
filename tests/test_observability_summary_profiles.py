"""Tests for profile-specific observability summary snapshots."""

from pathlib import Path
from types import SimpleNamespace

from orchestrator.workflow.executor import WorkflowExecutor


def _make_executor_with_summary_profile(tmp_path: Path, profile: str) -> WorkflowExecutor:
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.observability = {
        "step_summaries": {
            "enabled": True,
            "profile": profile,
        }
    }
    executor.workflow_name = "summary-profile-test"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    executor.state_manager = SimpleNamespace(run_id="run-summary-profile", logs_dir=logs_dir)
    return executor


def test_summary_kind_for_provider_step(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "phase-performance")

    assert executor._summary_kind_for_step({"provider": "codex"}) == "provider"
    assert executor._summary_kind_for_step({"adjudicated_provider": {"candidates": []}}) == "provider"


def test_summary_kind_for_phase_boundaries(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "phase-performance")

    assert executor._summary_kind_for_step({"call": "plan_phase"}) == "phase"
    assert executor._summary_kind_for_step({"repeat_until": {"steps": []}}) == "phase"


def test_phase_performance_profile_skips_plain_command_steps(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "phase-performance")

    assert executor._summary_kind_for_step({"command": ["true"]}) is None


def test_basic_profile_keeps_step_summary_kind(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "basic")

    assert executor._summary_kind_for_step({"command": ["true"]}) == "step"
    assert executor._summary_kind_for_step({"provider": "codex"}) == "step"


def test_provider_summary_snapshot_includes_profile_metadata(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "phase-performance")

    snapshot = executor._build_step_summary_snapshot(
        "ExecuteImplementation",
        {
            "provider": "codex",
            "timeout_sec": 7200,
            "variant_output": {"path": "state/x.json"},
            "prompt_consumes": ["plan"],
        },
        {
            "status": "completed",
            "duration_ms": 1000,
            "artifacts": {"implementation_state": "COMPLETED"},
        },
        summary_kind="provider",
    )

    assert snapshot["summary"]["kind"] == "provider"
    assert snapshot["summary"]["profile"] == "phase-performance"
    assert snapshot["summary"]["advisory_only"] is True
    assert snapshot["step"]["input"]["has_variant_output"] is True
    assert snapshot["step"]["input"]["prompt_sources"]["prompt_consumes"] == ["plan"]
    assert snapshot["step"]["output"]["duration_ms"] == 1000


def test_phase_summary_snapshot_includes_boundary_metadata(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "phase-performance")

    snapshot = executor._build_step_summary_snapshot(
        "PlanPhase",
        {"id": "plan_phase", "call": "plan_phase"},
        {"status": "completed", "duration_ms": 2000, "artifacts": {"plan_state": "APPROVE"}},
        summary_kind="phase",
    )

    assert snapshot["summary"]["kind"] == "phase"
    assert snapshot["step"]["input"]["phase_boundary"] == {
        "call": "plan_phase",
        "repeat_until": False,
        "step_id": "plan_phase",
    }


def test_summary_observer_uses_parent_run_root_for_call_frame_hub(tmp_path: Path):
    executor = _make_executor_with_summary_profile(tmp_path, "phase-performance")
    parent_root = tmp_path / ".orchestrate" / "runs" / "run-summary-profile"
    frame_root = parent_root / "call_frames" / "frame_a"
    executor.state_manager = SimpleNamespace(
        run_root=frame_root,
        parent_manager=SimpleNamespace(run_root=parent_root),
    )
    executor.provider_executor = object()
    executor.workflow_context_defaults = {}

    observer = executor._create_summary_observer()

    assert observer is not None
    assert observer.run_root == frame_root
    assert observer.aggregate_run_root == parent_root
