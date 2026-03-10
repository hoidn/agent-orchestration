"""Characterization tests for IR-to-state compatibility projection tables."""

from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.resume_planner import ResumePlanner, ResumeStateIntegrityError
from tests.workflow_bundle_helpers import (
    materialize_projection_body_steps,
    materialize_projection_finalization_steps,
)


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
            "inputs": {
                "iteration": {
                    "kind": "scalar",
                    "type": "integer",
                },
                "write_root": {
                    "kind": "relpath",
                    "type": "relpath",
                },
            },
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
                                "with": {
                                    "iteration": 1,
                                    "write_root": "state/review-loop",
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
                                "name": "RunReviewLoopFromForEach",
                                "id": "run_review_loop_from_for_each",
                                "call": "review_loop",
                                "with": {
                                    "iteration": 1,
                                    "write_root": "state/review-loop",
                                },
                            }
                        ],
                    },
                },
            ],
        },
    )


def _write_provider_session_projection_workflow(workspace: Path) -> Path:
    return _write_yaml(
        workspace / "provider_session_projection.yaml",
        {
            "version": "2.10",
            "name": "provider-session-projection",
            "providers": {
                "codex_session": {
                    "command": ["bash", "-lc", "echo should-not-run"],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["bash", "-lc", "echo should-not-run"],
                        "resume_command": [
                            "bash",
                            "-lc",
                            "echo should-not-run ${SESSION_ID}",
                        ],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [
                {
                    "name": "StartImplementation",
                    "id": "start_implementation",
                    "provider": "codex_session",
                    "provider_session": {
                        "mode": "fresh",
                        "publish_artifact": "implementation_session_id",
                    },
                }
            ],
        },
    )


def test_projection_preserves_existing_lowered_order_and_presentation_keys(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    projection = bundle.projection
    body_steps = materialize_projection_body_steps(bundle)
    final_steps = materialize_projection_finalization_steps(bundle)

    for index, step in enumerate(body_steps):
        node_id = step["step_id"]
        assert projection.node_id_by_compatibility_index[index] == node_id
        assert projection.compatibility_index_by_node_id[node_id] == index
        assert projection.presentation_key_by_node_id[node_id] == step["name"]
        assert projection.node_id_by_step_id[node_id] == node_id

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
    for_each_call_boundary = projection.call_boundaries[
        "root.process_items.run_review_loop_from_for_each"
    ]

    assert call_boundary.runtime_step_id(iteration_index=1) == (
        "root.review_loop#1.iteration_body.run_review_loop"
    )
    assert projection.call_boundary_runtime_step_id(
        "root.review_loop.iteration_body.run_review_loop",
        iteration_index=1,
    ) == "root.review_loop#1.iteration_body.run_review_loop"
    assert for_each_call_boundary.iteration_owner_node_id == "root.process_items"
    assert for_each_call_boundary.runtime_step_id(iteration_index=1) == (
        "root.process_items#1.run_review_loop_from_for_each"
    )
    assert projection.call_boundary_runtime_step_id(
        "root.process_items.run_review_loop_from_for_each",
        iteration_index=1,
    ) == "root.process_items#1.run_review_loop_from_for_each"


def test_resume_planner_uses_projection_step_id_mapping_for_running_current_step(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    body_steps = materialize_projection_body_steps(bundle)
    restart_index = planner.determine_restart_index(
        {
            "steps": {},
            "current_step": {
                "name": "RouteReady",
                "status": "running",
                "step_id": "root.route_ready",
            },
        },
        body_steps,
        projection=bundle.projection,
    )

    assert restart_index == bundle.projection.compatibility_index_by_node_id["root.route_ready"]


def test_resume_planner_maps_finalization_current_step_step_ids_to_execution_order(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    body_steps = materialize_projection_body_steps(bundle)
    final_steps = materialize_projection_finalization_steps(bundle)
    steps = list(body_steps) + list(final_steps)
    restart_index = planner.determine_restart_index(
        {
            "steps": {
                "SetReady": {"status": "completed"},
                "RouteReady": {"status": "completed"},
                "ReviewLoop": {"status": "completed"},
                "ProcessItems": {"status": "completed"},
                "finally.WriteCleanupMarker": {"status": "pending"},
            },
            "current_step": {
                "name": "finally.WriteCleanupMarker",
                "index": len(body_steps),
                "status": "running",
                "step_id": "root.finally.cleanup.write_cleanup_marker",
            },
        },
        steps,
        projection=bundle.projection,
    )

    assert restart_index == len(body_steps)


def test_resume_planner_uses_projection_ordering_when_legacy_step_names_drift(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    body_steps = materialize_projection_body_steps(bundle)
    body_steps[0]["name"] = "LegacySetReady"
    body_steps[1]["name"] = "LegacyRouteReady"
    planner = ResumePlanner()

    restart_index = planner.determine_restart_index(
        {
            "steps": {
                "SetReady": {"status": "completed"},
                "RouteReady": {"status": "pending"},
            },
        },
        body_steps,
        projection=bundle.projection,
    )

    assert restart_index == bundle.projection.compatibility_index_by_node_id[
        "root.route_ready.approve_path"
    ]


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
    body_steps = materialize_projection_body_steps(bundle)
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
            body_steps,
            projection=bundle.projection,
        )

    assert exc_info.value.context["step_id"] == "root.route_ready"
    assert exc_info.value.context["field"] == field


def test_resume_planner_quarantines_provider_session_visits_without_current_step_name(tmp_path: Path):
    workflow_path = _write_provider_session_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    body_steps = materialize_projection_body_steps(bundle)
    guard = planner.detect_interrupted_provider_session_visit(
        {
            "steps": {
                "StartImplementation": {
                    "status": "completed",
                    "step_id": "root.start_implementation",
                    "visit_count": 1,
                    "artifacts": {
                        "implementation_session_id": "sess-old",
                    },
                }
            },
            "current_step": {
                "index": 0,
                "status": "running",
                "step_id": "root.start_implementation",
                "visit_count": 2,
            },
        },
        body_steps,
        projection=bundle.projection,
    )

    assert guard == {
        "kind": "quarantine",
        "step_name": "StartImplementation",
        "step_id": "root.start_implementation",
        "visit_count": 2,
        "provider": "codex_session",
        "mode": "fresh",
    }


def test_resume_planner_quarantines_provider_session_visits_when_legacy_step_order_drifts(tmp_path: Path):
    workflow_path = _write_provider_session_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    body_steps = [
        {
            "name": "LegacyDrift",
            "step_id": "root.legacy_drift",
            "command": ["bash", "-lc", "echo drift"],
        },
        *materialize_projection_body_steps(bundle),
    ]

    guard = planner.detect_interrupted_provider_session_visit(
        {
            "steps": {},
            "current_step": {
                "index": 0,
                "status": "running",
                "step_id": "root.start_implementation",
                "visit_count": 2,
            },
        },
        body_steps,
        projection=bundle.projection,
    )

    assert guard == {
        "kind": "quarantine",
        "step_name": "StartImplementation",
        "step_id": "root.start_implementation",
        "visit_count": 2,
        "provider": "codex_session",
        "mode": "fresh",
    }


def test_resume_planner_uses_projection_without_runtime_steps_argument(tmp_path: Path):
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
        projection=bundle.projection,
    )

    assert restart_index == bundle.projection.compatibility_index_by_node_id["root.route_ready"]


def test_resume_planner_quarantines_provider_session_visits_from_projection_without_runtime_steps(
    tmp_path: Path,
):
    workflow_path = _write_provider_session_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    guard = planner.detect_interrupted_provider_session_visit(
        {
            "steps": {
                "StartImplementation": {
                    "status": "completed",
                    "step_id": "root.start_implementation",
                    "visit_count": 1,
                    "artifacts": {
                        "implementation_session_id": "sess-old",
                    },
                }
            },
            "current_step": {
                "index": 0,
                "status": "running",
                "step_id": "root.start_implementation",
                "visit_count": 2,
            },
        },
        projection=bundle.projection,
    )

    assert guard == {
        "kind": "quarantine",
        "step_name": "StartImplementation",
        "step_id": "root.start_implementation",
        "visit_count": 2,
        "provider": "codex_session",
        "mode": "fresh",
    }
