"""Characterization tests for IR-to-state compatibility projection tables."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader


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
