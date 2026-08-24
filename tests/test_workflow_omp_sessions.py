"""Workflow-level OMP session evidence (Task 5 fix round: findings 5, 8, 13).

Drives the real WorkflowExecutor with an OMP-metadata provider step while
patching only the provider subprocess execution, so the workflow's own visit
directory, spool, and projection persistence logic is exercised end to end.
"""

import json
import sys
from pathlib import Path

import pytest

from tests.workflow_fixture_loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _load_workflow(workspace: Path, workflow: dict) -> dict:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(json.dumps(workflow, sort_keys=False), encoding="utf-8")
    return WorkflowLoader(workspace).load(workflow_file)


def _omp_workflow(run_id: str, metadata_mode: str = "omp_json_stdout") -> dict:
    is_omp = metadata_mode == "omp_json_stdout"
    fresh_command = (
        [
            sys.executable,
            "-m",
            "orchestrator.providers.omp_launch",
            "run",
            "--lane",
            "omp",
            "--model",
            "gpt-5.6-sol",
            "--provider-session-dir",
            "${PROVIDER_SESSION_DIR}",
        ]
        if is_omp
        else [sys.executable, "-c", "import sys; sys.stdout.write('ok')"]
    )
    return {
        "version": "2.10",
        "name": run_id,
        "artifacts": {
            "session": {"kind": "scalar", "type": "string"},
        },
        "providers": {
            "ompsim": {
                "command": [
                    sys.executable,
                    "-m",
                    "orchestrator.providers.omp_launch",
                    "run",
                    "--lane",
                    "omp",
                    "--model",
                    "gpt-5.6-sol",
                ],
                "session_support": {
                    "metadata_mode": metadata_mode,
                    "fresh_command": fresh_command,
                },
            }
        },
        "steps": [
            {
                "name": "Ask",
                "provider": "ompsim",
                "provider_session": {"mode": "fresh", "publish_artifact": "session"},
            }
        ],
    }


def _fresh_projection(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "event_count": 12,
        "messages": [
            {
                "provider": "omp",
                "model": "gpt-5.6-sol",
                "usage": {"totalTokens": 42},
                "stop_reason": "stop",
            }
        ],
        "total_tokens": 42,
        "total_cost": 0.0,
        "final_provider": "omp",
        "final_model": "gpt-5.6-sol",
        "launch_frame": {
            "type": "orchestrator.omp_launch.v1",
            "lane": "ambient",
            "persistence": "fresh",
        },
    }


def _canned_result(projection: dict, exit_code: int = 0):
    from orchestrator.providers.executor import ProviderExecutionResult

    return ProviderExecutionResult(
        exit_code=exit_code,
        stdout=b"",
        stderr=b"",
        duration_ms=1,
        provider_session=projection if exit_code == 0 else None,
    )


def _install_canned_provider(monkeypatch: pytest.MonkeyPatch, result) -> None:
    import orchestrator.workflow.executor as workflow_module

    monkeypatch.setattr(
        workflow_module.WorkflowExecutor,
        "_execute_provider_invocation",
        lambda self, *args, **kwargs: result,
    )


def _visit_dir(tmp_path: Path, run_id: str) -> Path:
    return (
        tmp_path / ".orchestrate" / "runs" / run_id
        / "provider_sessions" / "root.ask__v1.live"
    )


def _run_fresh(tmp_path: Path, run_id: str, monkeypatch: pytest.MonkeyPatch, exit_code: int = 0):
    workflow = _omp_workflow(run_id)
    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    _install_canned_provider(
        monkeypatch,
        _canned_result(_fresh_projection("sess-123"), exit_code=exit_code),
    )
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    return executor.execute()


def test_omp_fresh_non_private_visit_parent_fails_closed(tmp_path, monkeypatch) -> None:
    """T5-SEC-005: the run-owned visit parent must be private before creation."""
    parent = _visit_dir(tmp_path, "bad-parent").parent
    parent.mkdir(parents=True, exist_ok=True)
    parent.chmod(0o755)
    with pytest.raises(RuntimeError, match="parent"):
        _run_fresh(tmp_path, "bad-parent", monkeypatch)


def test_omp_fresh_preexisting_live_dir_fails_closed(tmp_path, monkeypatch) -> None:
    """Finding 5: the .live visit dir is created exclusively and no-follow."""
    live = _visit_dir(tmp_path, "preexisting-live")
    live.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    live.mkdir(mode=0o700)
    with pytest.raises(RuntimeError, match="already exists"):
        _run_fresh(tmp_path, "preexisting-live", monkeypatch)


def test_omp_fresh_persists_the_full_minimized_projection(tmp_path, monkeypatch) -> None:
    """Finding 8: the provider_session projection is persisted in full."""
    state = _run_fresh(tmp_path, "full-projection", monkeypatch)
    step = state["steps"]["Ask"]
    assert step["status"] == "completed", step
    provider_session = step["debug"]["provider_session"]
    assert provider_session["session_id"] == "sess-123"
    assert provider_session["event_count"] == 12
    assert provider_session["messages"] == [
        {
            "provider": "omp",
            "model": "gpt-5.6-sol",
            "usage": {"totalTokens": 42},
            "stop_reason": "stop",
        }
    ]
    assert provider_session["total_tokens"] == 42
    assert provider_session["final_model"] == "gpt-5.6-sol"
    assert provider_session["launch_frame"]["type"] == "orchestrator.omp_launch.v1"
    assert provider_session["mode"] == "fresh"

    metadata_file = (
        tmp_path / ".orchestrate" / "runs" / "full-projection"
        / "provider_sessions" / "root.ask__v1.json"
    )
    assert metadata_file.exists()
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["parser_summary"]["session_id"] == "sess-123"
    assert metadata["parser_summary"]["event_count"] == 12
    assert metadata["parser_summary"]["total_tokens"] == 42
    assert len(metadata["parser_summary"]["messages"]) == 1
    assert metadata["parser_summary"]["launch_frame"]["persistence"] == "fresh"


def test_omp_fresh_success_removes_the_empty_transport_spool(tmp_path, monkeypatch) -> None:
    """Finding 13: OMP JSON transport is memory-only; the spool is removed."""
    _run_fresh(tmp_path, "spool-removed", monkeypatch)
    spool = (
        tmp_path / ".orchestrate" / "runs" / "spool-removed"
        / "provider_sessions" / "root.ask__v1.transport.log"
    )
    assert not spool.exists(), "OMP fresh success must remove the empty spool"


def test_omp_fresh_failure_removes_the_empty_transport_spool(tmp_path, monkeypatch) -> None:
    """Finding 13: a failed OMP visit still removes the empty spool.

    OMP JSON transport is memory-only: the compatibility spool stays empty
    and is removed on every finalized OMP fresh visit, success or failure.
    """
    state = _run_fresh(tmp_path, "spool-removed-failure", monkeypatch, exit_code=1)
    assert state["steps"]["Ask"]["status"] == "failed"
    spool = (
        tmp_path / ".orchestrate" / "runs" / "spool-removed-failure"
        / "provider_sessions" / "root.ask__v1.transport.log"
    )
    assert not spool.exists(), "failed OMP fresh visits must remove the empty spool"


def test_non_omp_fresh_retains_the_transport_spool(tmp_path, monkeypatch) -> None:
    """Finding 13: non-OMP metadata modes keep the pre-Task-5 retention rules.

    The pre-Task-5 predicate retains the spool on failure (and under debug)
    for every non-OMP metadata mode; a failed codex visit therefore keeps
    its transport spool.
    """
    run_id = "non-omp-retention"
    workflow = _omp_workflow(run_id, metadata_mode="codex_exec_jsonl_stdout")
    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    _install_canned_provider(
        monkeypatch, _canned_result(_fresh_projection("sess-456"), exit_code=1)
    )
    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    assert state["steps"]["Ask"]["status"] == "failed"
    spool = (
        tmp_path / ".orchestrate" / "runs" / run_id
        / "provider_sessions" / "root.ask__v1.transport.log"
    )
    assert spool.exists(), "failed non-OMP fresh visits keep the transport spool"
