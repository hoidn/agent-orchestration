"""Tests for structured if/else lowering and runtime semantics."""

from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return workflow_file


def _route_review_statement() -> dict:
    return {
        "name": "RouteReview",
        "id": "route_review",
        "if": {
            "artifact_bool": {
                "ref": "root.steps.SetReady.artifacts.ready",
            }
        },
        "then": {
            "id": "approve_path",
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "self.steps.WriteApproved.artifacts.review_decision",
                    },
                }
            },
            "steps": [
                {
                    "name": "WriteApproved",
                    "id": "write_approved",
                    "set_scalar": {
                        "artifact": "review_decision",
                        "value": "APPROVE",
                    },
                }
            ],
        },
        "else": {
            "id": "revise_path",
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "self.steps.WriteRevision.artifacts.review_decision",
                    },
                }
            },
            "steps": [
                {
                    "name": "WriteRevision",
                    "id": "write_revision",
                    "set_scalar": {
                        "artifact": "review_decision",
                        "value": "REVISE",
                    },
                }
            ],
        },
    }


def _structured_if_else_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
        {
            "name": "SetReady",
            "id": "set_ready",
            "set_scalar": {
                "artifact": "ready",
                "value": True,
            },
        },
        _route_review_statement(),
        {
            "name": "CheckRouteDecision",
            "id": "check_route_decision",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.RouteReview.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        },
    ]
    if include_inserted_sibling:
        steps.insert(
            1,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "printf 'inserted\\n'"],
            },
        )

    return {
        "version": "2.2",
        "name": "structured-if-else",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            },
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            },
        },
        "steps": steps,
    }


def _load_workflow(tmp_path: Path, workflow: dict) -> dict:
    workflow_path = _write_workflow(tmp_path, workflow)
    return WorkflowLoader(tmp_path).load(workflow_path)


def _run_workflow(tmp_path: Path, workflow: dict) -> dict:
    workflow_path = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    return WorkflowExecutor(loaded, tmp_path, state_manager).execute(on_error="continue")


def test_if_else_lowered_step_ids_stay_stable_when_siblings_shift(tmp_path: Path):
    workflow_a = _structured_if_else_workflow()
    workflow_b = _structured_if_else_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {step["name"]: step["step_id"] for step in loaded_a["steps"]}
    steps_b = {step["name"]: step["step_id"] for step in loaded_b["steps"]}

    assert steps_a["RouteReview.then.WriteApproved"] == "root.route_review.approve_path.write_approved"
    assert steps_a["RouteReview.else.WriteRevision"] == "root.route_review.revise_path.write_revision"
    assert steps_a["RouteReview"] == "root.route_review"
    assert steps_b["RouteReview.then.WriteApproved"] == steps_a["RouteReview.then.WriteApproved"]
    assert steps_b["RouteReview.else.WriteRevision"] == steps_a["RouteReview.else.WriteRevision"]
    assert steps_b["RouteReview"] == steps_a["RouteReview"]


def test_if_else_branch_outputs_materialize_on_statement_and_skip_non_taken_branch(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_if_else_workflow())

    assert state["status"] == "completed"
    assert state["steps"]["RouteReview.then.WriteApproved"]["status"] == "completed"
    assert state["steps"]["RouteReview.else.WriteRevision"]["status"] == "skipped"
    assert state["steps"]["RouteReview"]["artifacts"]["review_decision"] == "APPROVE"
    assert state["steps"]["RouteReview"]["debug"]["structured_if"]["selected_branch"] == "then"
    assert state["steps"]["CheckRouteDecision"]["exit_code"] == 0


def test_if_else_branch_steps_are_not_visible_outside_statement(tmp_path: Path):
    workflow = _structured_if_else_workflow()
    workflow["steps"].append(
        {
            "name": "IllegalDirectBranchRead",
            "id": "illegal_direct_branch_read",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.WriteApproved.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        }
    )

    workflow_path = _write_workflow(tmp_path, workflow)

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(workflow_path)

    assert any("WriteApproved" in str(err.message) for err in exc_info.value.errors)
