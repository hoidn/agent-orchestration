"""Tests for v1.7 scalar bookkeeping runtime primitives."""

import json
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow), encoding="utf-8")
    return workflow_file


def _run_workflow(tmp_path: Path, workflow: dict, run_id: str = "scalar-bookkeeping-run", on_error: str = "stop") -> tuple[dict, dict]:
    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    final_state = executor.execute(on_error=on_error)
    persisted = state_manager.load().to_dict()
    return final_state, persisted


def _scalar_registry() -> dict:
    return {
        "failed_count": {
            "kind": "scalar",
            "type": "integer",
        }
    }


def test_set_scalar_emits_local_artifact_and_publishable_value(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "set-scalar-local-artifact",
        "artifacts": _scalar_registry(),
        "steps": [
            {
                "name": "Initialize",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 2,
                },
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            }
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow)

    assert state["steps"]["Initialize"]["status"] == "completed"
    assert state["steps"]["Initialize"]["artifacts"] == {"failed_count": 2}
    assert persisted["steps"]["Initialize"]["artifacts"] == {"failed_count": 2}
    assert persisted["artifact_versions"]["failed_count"] == [
        {"version": 1, "value": 2, "producer": "Initialize", "step_index": 0}
    ]


def test_increment_scalar_uses_latest_published_value(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "increment-scalar-latest-version",
        "artifacts": _scalar_registry(),
        "steps": [
            {
                "name": "Initialize",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 1,
                },
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
            {
                "name": "Increment",
                "increment_scalar": {
                    "artifact": "failed_count",
                    "by": 2,
                },
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, run_id="increment-scalar-run")

    assert state["steps"]["Increment"]["artifacts"] == {"failed_count": 3}
    assert [entry["value"] for entry in persisted["artifact_versions"]["failed_count"]] == [1, 3]


def test_set_scalar_runtime_type_mismatch_fails_as_contract_violation(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "set-scalar-type-mismatch",
        "artifacts": _scalar_registry(),
        "steps": [
            {
                "name": "Initialize",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": "two",
                },
            }
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow, run_id="set-scalar-mismatch", on_error="continue")

    step = state["steps"]["Initialize"]
    assert step["status"] == "failed"
    assert step["exit_code"] == 2
    assert step["error"]["type"] == "contract_violation"
    assert step["error"]["context"]["reason"] == "invalid_scalar_value"
    assert step["outcome"]["class"] == "contract_violation"


def test_scalar_consume_bundle_sees_latest_published_increment(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "scalar-consume-after-increment",
        "artifacts": _scalar_registry(),
        "steps": [
            {
                "name": "Initialize",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 1,
                },
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
            {
                "name": "Increment",
                "increment_scalar": {
                    "artifact": "failed_count",
                    "by": 2,
                },
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
            {
                "name": "ReadLatest",
                "consumes": [
                    {
                        "artifact": "failed_count",
                        "producers": ["Initialize", "Increment"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "consume_bundle": {
                    "path": "state/consumed.json",
                },
                "command": ["bash", "-lc", "cat state/consumed.json"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, run_id="scalar-consume-run")

    assert json.loads(state["steps"]["ReadLatest"]["output"]) == {"failed_count": 3}
    assert persisted["artifact_consumes"]["ReadLatest"]["failed_count"] == 2
