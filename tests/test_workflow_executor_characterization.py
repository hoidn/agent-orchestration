"""Characterization tests for workflow executor seam behavior."""

import json
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return workflow_file


def _load_workflow(workspace: Path, workflow: dict) -> dict:
    workflow_path = _write_workflow(workspace, workflow)
    return WorkflowLoader(workspace).load(workflow_path)


def _persisted_state(workspace: Path, run_id: str) -> dict:
    state_file = workspace / ".orchestrate" / "runs" / run_id / "state.json"
    return json.loads(state_file.read_text(encoding="utf-8"))


def _structured_finally_resume_workflow() -> dict:
    return {
        "version": "2.3",
        "name": "structured-finally-resume",
        "artifacts": {
            "decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }
        },
        "outputs": {
            "final_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
                "from": {
                    "ref": "root.steps.WriteDecision.artifacts.decision",
                },
            }
        },
        "steps": [
            {
                "name": "WriteDecision",
                "id": "write_decision",
                "set_scalar": {
                    "artifact": "decision",
                    "value": "APPROVE",
                },
            }
        ],
        "finally": {
            "id": "cleanup",
            "steps": [
                {
                    "name": "ObserveOutputsPending",
                    "id": "observe_outputs_pending",
                    "command": [
                        "bash",
                        "-lc",
                        "\n".join(
                            [
                                "python - <<'PY'",
                                "import json",
                                "from pathlib import Path",
                                "state = json.loads(Path('${run.root}/state.json').read_text(encoding='utf-8'))",
                                "assert state.get('workflow_outputs', {}) == {}, state.get('workflow_outputs')",
                                "Path('state').mkdir(exist_ok=True)",
                                "with Path('state/finalization.log').open('a', encoding='utf-8') as handle:",
                                "    handle.write('outputs-pending\\n')",
                                "PY",
                            ]
                        ),
                    ],
                },
                {
                    "name": "WriteCleanupMarker",
                    "id": "write_cleanup_marker",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p state && printf 'cleanup-complete\\n' >> state/finalization.log",
                    ],
                },
            ],
        },
    }


def test_executor_resume_partial_finalization_restarts_remaining_cleanup_step(tmp_path: Path):
    loaded = _load_workflow(tmp_path, _structured_finally_resume_workflow())
    run_id = "executor-finalization-resume"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None

    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "finalization.log").write_text("outputs-pending\n", encoding="utf-8")

    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "WriteDecision": {
            "status": "completed",
            "exit_code": 0,
            "artifacts": {"decision": "APPROVE"},
        },
        "finally.ObserveOutputsPending": {
            "status": "completed",
            "exit_code": 0,
        },
        "finally.WriteCleanupMarker": {"status": "pending"},
    }
    state_manager.state.current_step = {
        "name": "finally.ObserveOutputsPending",
        "index": 1,
        "type": "command",
        "status": "running",
        "started_at": "2024-01-01T00:00:10Z",
        "last_heartbeat_at": "2024-01-01T00:00:11Z",
    }
    state_manager.state.finalization = {
        "block_id": "cleanup",
        "status": "running",
        "body_status": "completed",
        "current_index": None,
        "completed_indices": [0],
        "step_names": [
            "finally.ObserveOutputsPending",
            "finally.WriteCleanupMarker",
        ],
        "workflow_outputs_status": "pending",
    }
    state_manager.state.workflow_outputs = {}
    state_manager._write_state()

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)
    persisted = _persisted_state(tmp_path, run_id)

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"final_decision": "APPROVE"}
    assert state["steps"]["finally.ObserveOutputsPending"]["status"] == "completed"
    assert state["steps"]["finally.WriteCleanupMarker"]["status"] == "completed"
    assert (tmp_path / "state" / "finalization.log").read_text(encoding="utf-8").splitlines() == [
        "outputs-pending",
        "cleanup-complete",
    ]
    assert persisted["status"] == "completed"
    assert persisted.get("current_step") is None
    assert persisted["finalization"]["completed_indices"] == [0, 1]
    assert persisted["finalization"]["workflow_outputs_status"] == "completed"


def test_executor_for_each_nested_scalar_steps_materialize_artifacts_per_iteration(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "loop-nested-scalars",
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "ProcessItems",
                "for_each": {
                    "items": ["alpha", "beta"],
                    "steps": [
                        {
                            "name": "InitializeCount",
                            "set_scalar": {
                                "artifact": "failed_count",
                                "value": 0,
                            },
                            "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                        },
                        {
                            "name": "IncrementCount",
                            "increment_scalar": {
                                "artifact": "failed_count",
                                "by": 1,
                            },
                            "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                        },
                    ],
                },
            }
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="loop-nested-scalars")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "loop-nested-scalars")

    assert state["status"] == "completed"
    assert state["steps"]["ProcessItems"][0]["InitializeCount"]["artifacts"] == {"failed_count": 0}
    assert state["steps"]["ProcessItems"][0]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert state["steps"]["ProcessItems"][1]["InitializeCount"]["artifacts"] == {"failed_count": 0}
    assert state["steps"]["ProcessItems"][1]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert state["steps"]["ProcessItems[0].IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert state["steps"]["ProcessItems[1].IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert persisted["steps"]["ProcessItems"][0]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert persisted["steps"]["ProcessItems"][1]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    versions = persisted["artifact_versions"]["failed_count"]
    assert [entry["producer"] for entry in versions] == [
        "InitializeCount",
        "IncrementCount",
        "InitializeCount",
        "IncrementCount",
    ]


def test_executor_for_each_nested_provider_pre_execution_failures_normalize_outcomes(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "loop-provider-pre-execution",
        "providers": {
            "write_file": {
                "command": [
                    "bash",
                    "-lc",
                    "printf '%s' \"${value}\" > state/provider-ran.txt",
                ]
            }
        },
        "steps": [
            {
                "name": "ProcessItems",
                "for_each": {
                    "items": ["only"],
                    "steps": [
                        {
                            "name": "UseProvider",
                            "provider": "write_file",
                            "provider_params": {
                                "value": "${context.missing_value}",
                            },
                        }
                    ],
                },
            }
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="loop-provider-pre-execution")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute(on_error="continue")
    persisted = _persisted_state(tmp_path, "loop-provider-pre-execution")
    result = state["steps"]["ProcessItems"][0]["UseProvider"]

    assert result["status"] == "failed"
    assert result["error"]["type"] == "substitution_error"
    assert result["outcome"] == {
        "status": "failed",
        "phase": "pre_execution",
        "class": "pre_execution_failed",
        "retryable": False,
    }
    assert persisted["steps"]["ProcessItems"][0]["UseProvider"]["outcome"] == result["outcome"]
    assert not (tmp_path / "state" / "provider-ran.txt").exists()
