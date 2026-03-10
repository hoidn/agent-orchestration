"""Characterization tests for IR-to-state compatibility projection tables."""

from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.resume_planner import ResumePlanner, ResumeStateIntegrityError


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_projection_workflow(workspace: Path) -> Path:
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.7",
            "name": "projection-surfaces",
            "artifacts": {
                "ready": {"kind": "scalar", "type": "bool"},
                "failed_count": {"kind": "scalar", "type": "integer"},
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
            },
            "steps": [
                {
                    "name": "SetReady",
                    "id": "set_ready",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                },
                {
                    "name": "RouteReady",
                    "id": "route_ready",
                    "if": {
                        "artifact_bool": {
                            "ref": "root.steps.SetReady.artifacts.ready",
                        }
                    },
                    "then": {
                        "id": "approve_path",
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
                },
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {"ref": "self.steps.WriteDecision.artifacts.review_decision"},
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {"ref": "self.outputs.review_decision"},
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "max_iterations": 4,
                        "steps": [
                            {
                                "name": "WriteDecision",
                                "id": "write_decision",
                                "set_scalar": {
                                    "artifact": "review_decision",
                                    "value": "REVISE",
                                },
                            }
                        ],
                    },
                },
                {
                    "name": "ProcessItems",
                    "id": "process_items",
                    "for_each": {
                        "items": ["alpha"],
                        "steps": [
                            {
                                "name": "InitializeCount",
                                "id": "initialize_count",
                                "set_scalar": {
                                    "artifact": "failed_count",
                                    "value": 0,
                                },
                            },
                            {
                                "name": "IncrementCount",
                                "id": "increment_count",
                                "increment_scalar": {
                                    "artifact": "failed_count",
                                    "by": 1,
                                },
                            },
                        ],
                    },
                },
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "WriteCleanupMarker",
                        "id": "write_cleanup_marker",
                        "command": ["bash", "-lc", "printf 'cleanup\\n'"],
                    }
                ],
            },
        },
    )


def _write_projection_call_workflow(workspace: Path) -> Path:
    _write_yaml(
        workspace / "workflows" / "library" / "review_loop.yaml",
        {
            "version": "2.7",
            "name": "review-loop",
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {"ref": "root.steps.WriteDecision.artifacts.review_decision"},
                }
            },
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "steps": [
                {
                    "name": "WriteDecision",
                    "id": "write_decision",
                    "set_scalar": {
                        "artifact": "review_decision",
                        "value": "APPROVE",
                    },
                }
            ],
        },
    )
    return _write_yaml(
        workspace / "projection_call.yaml",
        {
            "version": "2.7",
            "name": "projection-call",
            "imports": {
                "review_loop": "workflows/library/review_loop.yaml",
            },
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.RunReviewLoop.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {"ref": "self.outputs.review_decision"},
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "max_iterations": 3,
                        "steps": [
                            {
                                "name": "RunReviewLoop",
                                "id": "run_review_loop",
                                "call": "review_loop",
                            }
                        ],
                    },
                }
            ],
        },
    )


def test_projection_preserves_existing_lowered_order_and_presentation_keys(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    projection = bundle.projection

    for index, step in enumerate(bundle.legacy_workflow["steps"]):
        node_id = step["step_id"]
        assert projection.node_id_by_compatibility_index[index] == node_id
        assert projection.compatibility_index_by_node_id[node_id] == index
        assert projection.presentation_key_by_node_id[node_id] == step["name"]
        assert projection.node_id_by_step_id[node_id] == node_id

    final_steps = bundle.legacy_workflow["finally"]["steps"]
    for index, step in enumerate(final_steps):
        node_id = step["step_id"]
        assert projection.finalization_node_id_by_index[index] == node_id
        assert projection.finalization_index_by_node_id[node_id] == index
        assert projection.presentation_key_by_node_id[node_id] == step["name"]


def test_projection_formats_repeat_until_and_for_each_iteration_step_keys(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    projection = bundle.projection

    assert projection.repeat_until_step_key(
        "root.review_loop",
        1,
        "root.review_loop.iteration_body.write_decision",
    ) == "ReviewLoop[1].WriteDecision"
    assert projection.for_each_step_key(
        "root.process_items",
        0,
        "root.process_items.initialize_count",
    ) == "ProcessItems[0].InitializeCount"
    assert projection.repeat_until_runtime_step_id(
        "root.review_loop",
        1,
        "root.review_loop.iteration_body.write_decision",
    ) == "root.review_loop#1.iteration_body.write_decision"
    assert projection.for_each_runtime_step_id(
        "root.process_items",
        0,
        "root.process_items.increment_count",
    ) == "root.process_items#0.increment_count"


def test_projection_formats_call_boundary_checkpoint_runtime_step_ids(tmp_path: Path):
    workflow_path = _write_projection_call_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    projection = bundle.projection
    call_boundary = projection.call_boundaries["root.review_loop.iteration_body.run_review_loop"]

    assert call_boundary.runtime_step_id(iteration_index=1) == (
        "root.review_loop#1.iteration_body.run_review_loop"
    )
    assert projection.call_boundary_runtime_step_id(
        "root.review_loop.iteration_body.run_review_loop",
        iteration_index=1,
    ) == "root.review_loop#1.iteration_body.run_review_loop"


def test_resume_planner_uses_projection_step_id_mapping_for_running_current_step(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    restart_index = planner.determine_restart_index(
        {
            "steps": {},
            "current_step": {
                "name": "RouteReady",
                "status": "running",
                "step_id": "root.route_ready",
            },
        },
        bundle.legacy_workflow["steps"],
        projection=bundle.projection,
    )

    assert restart_index == bundle.projection.compatibility_index_by_node_id["root.route_ready"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "SetReady"),
        ("index", 0),
    ],
)
def test_resume_planner_rejects_inconsistent_projection_compatibility_fields(
    tmp_path: Path,
    field: str,
    value: object,
):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    current_step = {
        "name": "RouteReady",
        "index": bundle.projection.compatibility_index_by_node_id["root.route_ready"],
        "status": "running",
        "step_id": "root.route_ready",
    }
    current_step[field] = value

    with pytest.raises(ResumeStateIntegrityError) as exc_info:
        planner.determine_restart_index(
            {
                "steps": {},
                "current_step": current_step,
            },
            bundle.legacy_workflow["steps"],
            projection=bundle.projection,
        )

    assert exc_info.value.context["step_id"] == "root.route_ready"
    assert exc_info.value.context["field"] == field
