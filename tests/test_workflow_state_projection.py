"""Characterization tests for IR-to-state compatibility projection tables."""

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.state_projection import (
    CallBoundaryProjection,
    CompatibilityNodeProjection,
)
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

    assert projection.repeat_until_frame_key("root.review_loop") == "ReviewLoop"
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


def test_runtime_plan_derives_topology_dependencies_and_nested_body_summaries(tmp_path: Path):
    workflow_path = _write_projection_call_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    runtime_plan = bundle.runtime_plan

    review_loop = runtime_plan.nodes["root.review_loop"]
    nested_repeat_call = runtime_plan.nodes["root.review_loop.iteration_body.run_review_loop"]
    process_items = runtime_plan.nodes["root.process_items"]
    nested_for_each_call = runtime_plan.nodes["root.process_items.run_review_loop_from_for_each"]

    assert review_loop.nested_body_node_ids == ("root.review_loop.iteration_body.run_review_loop",)
    assert nested_repeat_call.dependency_node_ids == ("root.review_loop",)
    assert process_items.dependency_node_ids == (
        "root.review_loop",
        "root.process_items.run_review_loop_from_for_each",
    )
    assert process_items.nested_body_node_ids == ("root.process_items.run_review_loop_from_for_each",)
    assert nested_for_each_call.dependency_node_ids == ("root.process_items",)


def test_runtime_plan_uses_projection_order_for_execution_indexes_and_finalization_checkpoints(
    tmp_path: Path,
):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    runtime_plan = bundle.runtime_plan
    ordered_node_ids = bundle.projection.ordered_execution_node_ids()

    for execution_index, node_id in enumerate(ordered_node_ids):
        assert runtime_plan.nodes[node_id].execution_index == execution_index

    finalization_node_id = "root.finally.cleanup.write_cleanup_marker"
    finalization_checkpoint = next(
        checkpoint
        for checkpoint in runtime_plan.resume_checkpoints
        if checkpoint.node_id == finalization_node_id
    )
    assert finalization_checkpoint.checkpoint_kind == "finalization_node"
    assert runtime_plan.nodes[finalization_node_id].execution_index == len(bundle.ir.body_region)


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
        projection=bundle.projection,
    )

    assert restart_index == bundle.projection.compatibility_index_by_node_id["root.route_ready"]


def test_resume_planner_maps_finalization_current_step_step_ids_to_execution_order(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    body_steps = materialize_projection_body_steps(bundle)
    final_steps = materialize_projection_finalization_steps(bundle)
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
        projection=bundle.projection,
    )

    assert restart_index == len(body_steps)


def test_resume_planner_uses_projection_ordering_when_legacy_step_names_drift(tmp_path: Path):
    workflow_path = _write_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()

    restart_index = planner.determine_restart_index(
        {
            "steps": {
                "SetReady": {"status": "completed"},
                "RouteReady": {"status": "pending"},
            },
        },
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
            projection=bundle.projection,
        )

    assert exc_info.value.context["step_id"] == "root.route_ready"
    assert exc_info.value.context["field"] == field


def test_resume_planner_quarantines_provider_session_visits_without_current_step_name(tmp_path: Path):
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


def test_resume_planner_quarantines_provider_session_visits_when_legacy_step_order_drifts(tmp_path: Path):
    workflow_path = _write_provider_session_projection_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
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


def test_resume_planner_requires_projection_for_restart_index() -> None:
    planner = ResumePlanner()

    with pytest.raises(TypeError, match="WorkflowStateProjection"):
        planner.determine_restart_index({"steps": {}})


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


def test_resume_planner_requires_projection_for_provider_session_guard() -> None:
    planner = ResumePlanner()

    with pytest.raises(TypeError, match="WorkflowStateProjection"):
        planner.detect_interrupted_provider_session_visit(
            {
                "current_step": {
                    "name": "Step",
                    "status": "running",
                    "step_id": "root.step",
                    "visit_count": 1,
                }
            }
        )


def test_projection_maps_root_result_output_bundle_step_like_any_other_step(
    tmp_path: Path,
):
    """State projection (presentation-key/step-id mapping) is agnostic to
    artifact contract shape: a step whose `output_bundle` is a native-return
    root field (`json_pointer: ""`) is mapped identically to an ordinary step,
    with no root-specific branch in the projection layer."""
    workflow_path = _write_yaml(
        tmp_path / "root_result_projection.yaml",
        {
            "version": "2.7",
            "name": "root-result-projection",
            "steps": [
                {
                    "name": "WriteRootResult",
                    "id": "write_root_result",
                    "command": ["bash", "-lc", "printf 'true\\n' > state/bundle.json"],
                    "output_bundle": {
                        "path": "state/bundle.json",
                        "fields": [{"name": "__result__", "json_pointer": "", "type": "bool"}],
                    },
                },
            ],
        },
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    projection = bundle.projection
    body_steps = materialize_projection_body_steps(bundle)

    assert len(body_steps) == 1
    node_id = body_steps[0]["step_id"]
    assert projection.node_id_by_compatibility_index[0] == node_id
    assert projection.compatibility_index_by_node_id[node_id] == 0
    assert projection.presentation_key_by_node_id[node_id] == "WriteRootResult"
    assert projection.node_id_by_step_id[node_id] == node_id


@pytest.mark.parametrize(
    ("presentation_key", "step_id", "expected_restart_node_id"),
    [
        ("SetReady", "root.set_ready", "root.route_ready.approve_path"),
        ("SetReady", "root.removed_step", "root.route_ready.approve_path"),
        ("SetReady", "root.route_ready", "root.route_ready.approve_path"),
    ],
)
def test_projection_resume_integrity_completed_row_feasibility_matrix(
    tmp_path: Path,
    presentation_key: str,
    step_id: str,
    expected_restart_node_id: str,
) -> None:
    """Characterize `ResumePlanner.determine_restart_node_id` completed-row handling.

    The public planner consumes the `WorkflowStateProjection` but currently
    treats completed rows as presentation-key compatibility state: a valid
    explicit id, a stale explicit id, and an id owned by another presentation
    key all produce the same restart point.  The latter two rows therefore
    freeze the missing whole-state projection-integrity audit prerequisite.
    """
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    state = {
        "steps": {
            presentation_key: {
                "status": "completed",
                "name": presentation_key,
                "step_id": step_id,
            }
        }
    }

    restart_node_id = ResumePlanner().determine_restart_node_id(
        state,
        projection=bundle.projection,
    )

    assert restart_node_id == expected_restart_node_id


def test_projection_resume_integrity_finalization_row_resolves_through_public_projection(
    tmp_path: Path,
) -> None:
    """Freeze finalization ownership through public projection/planner symbols."""
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    body_rows = {
        entry.presentation_key: {
            "status": "completed",
            "name": entry.presentation_key,
            "step_id": entry.step_id,
        }
        for entry in bundle.projection.entries_by_node_id.values()
        if entry.compatibility_index is not None
    }
    finalization_id = "root.finally.cleanup.write_cleanup_marker"
    finalization_entry = bundle.projection.entry_for_step_id(finalization_id)
    assert finalization_entry is not None
    state = {
        "steps": {
            **body_rows,
            finalization_entry.presentation_key: {
                "status": "running",
                "name": finalization_entry.presentation_key,
                "step_id": finalization_id,
            },
        },
        "current_step": {
            "status": "running",
            "name": finalization_entry.presentation_key,
            "step_id": finalization_id,
        },
    }

    assert ResumePlanner().determine_restart_node_id(
        state,
        projection=bundle.projection,
    ) == finalization_id


def test_projection_resume_integrity_loop_qualified_ancestry_is_forward_only_prerequisite(
    tmp_path: Path,
) -> None:
    """Public loop/call APIs enumerate ancestry but lack qualified-id reverse resolution.

    `WorkflowStateProjection.repeat_until_runtime_step_id`,
    `for_each_runtime_step_id`, and `call_boundary_runtime_step_id` construct
    qualified identities without test-side parsing.  There is no corresponding
    public scoped reverse resolver, which is an implementation prerequisite
    rather than a helper to add in this characterization tranche.
    """
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_call_workflow(tmp_path))
    projection = bundle.projection
    repeat_node_id = "root.review_loop.iteration_body.run_review_loop"
    for_each_node_id = "root.process_items.run_review_loop_from_for_each"

    qualified_ids = {
        projection.repeat_until_runtime_step_id(
            "root.review_loop",
            2,
            repeat_node_id,
        ),
        projection.for_each_runtime_step_id(
            "root.process_items",
            3,
            for_each_node_id,
        ),
        projection.call_boundary_runtime_step_id(repeat_node_id, iteration_index=2),
        projection.call_boundary_runtime_step_id(for_each_node_id, iteration_index=3),
    }

    assert qualified_ids == {
        "root.review_loop#2.iteration_body.run_review_loop",
        "root.process_items#3.run_review_loop_from_for_each",
    }
    assert set(projection.call_boundaries) == {repeat_node_id, for_each_node_id}
    assert not hasattr(projection, "entry_for_runtime_step_id")


def test_projection_resume_optional_step_id_supported_row_is_not_backfilled(
    tmp_path: Path,
) -> None:
    """A schema-valid supported completed row may omit optional `step_id`.

    `ResumePlanner.determine_restart_node_id` preserves the name/order
    compatibility lane and does not mutate or backfill the persisted row.
    """
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    state = {
        "steps": {
            "SetReady": {
                "status": "completed",
                "name": "SetReady",
            }
        }
    }
    before = yaml.safe_dump(state, sort_keys=True)

    restart_node_id = ResumePlanner().determine_restart_node_id(
        state,
        projection=bundle.projection,
    )

    assert restart_node_id == "root.route_ready.approve_path"
    assert yaml.safe_dump(state, sort_keys=True) == before
    assert "step_id" not in state["steps"]["SetReady"]


def test_projection_resume_slot_index_resolves_body_finalization_and_optional_omission(
    tmp_path: Path,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    projection = bundle.projection
    state = {
        "steps": {
            "SetReady": {"status": "completed", "name": "SetReady"},
            "RouteReady": {"status": "skipped", "name": "RouteReady"},
            "ReviewLoop": {"status": "running", "name": "ReviewLoop"},
            "ProcessItems": {"status": "failed", "name": "ProcessItems"},
            "finally.WriteCleanupMarker": {
                "status": "completed",
                "name": "finally.WriteCleanupMarker",
                "step_id": "root.finally.cleanup.write_cleanup_marker",
            },
        }
    }
    before = yaml.safe_dump(state, sort_keys=True)

    slot_index = projection.enumerate_resume_slots(state)

    assert slot_index.unclaimed_explicit_rows == ()
    assert projection.resolve_resume_step_id(
        slot_index,
        "root.set_ready",
        presentation_key="SetReady",
    ).slot.node_id == "root.set_ready"
    assert projection.resolve_resume_step_id(
        slot_index,
        "root.finally.cleanup.write_cleanup_marker",
        presentation_key="finally.WriteCleanupMarker",
    ).slot.region.value == "finalization"
    assert yaml.safe_dump(state, sort_keys=True) == before
    for presentation_key in ("SetReady", "RouteReady", "ReviewLoop", "ProcessItems"):
        assert "step_id" not in state["steps"][presentation_key]

    duplicate_entry = CompatibilityNodeProjection(
        node_id="root.duplicate_set_ready",
        step_id="root.set_ready",
        presentation_key="SetReady",
        display_name="SetReady",
        region=projection.entries_by_node_id["root.set_ready"].region,
    )
    second_duplicate_entry = replace(
        duplicate_entry,
        node_id="root.second_duplicate_set_ready",
    )
    duplicate_boundary = CallBoundaryProjection(
        node_id="root.review_loop.iteration_body.run_review_loop",
        presentation_key="RunReviewLoop",
        step_id="root.review_loop.iteration_body.run_review_loop",
        import_alias="review_loop",
        iteration_owner_node_id="root.review_loop",
        iteration_step_id_suffix="iteration_body.run_review_loop",
    )
    call_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_call_workflow(tmp_path)
    )
    duplicate_projection = replace(
        call_bundle.projection,
        entries_by_node_id=MappingProxyType(
            {
                **call_bundle.projection.entries_by_node_id,
                duplicate_entry.node_id: duplicate_entry,
                second_duplicate_entry.node_id: second_duplicate_entry,
            }
        ),
        call_boundaries=MappingProxyType(
            {
                **call_bundle.projection.call_boundaries,
                "duplicate_boundary_projection": duplicate_boundary,
            }
        ),
    )
    duplicate_state = {
        "repeat_until": {
            "ReviewLoop": {
                "current_iteration": 0,
                "completed_iterations": [],
                "condition_evaluated_for_iteration": None,
                "last_condition_result": None,
            }
        },
        "steps": {
            "ReviewLoop": {"status": "running"},
        },
    }
    duplicate_index = duplicate_projection.enumerate_resume_slots(duplicate_state)

    assert len(duplicate_index.candidates_by_step_id["root.set_ready"]) == 2
    assert projection.resolve_resume_step_id(
        slot_index,
        "root.route_ready",
        presentation_key="SetReady",
    ).slot is None
    duplicate_resolution = duplicate_projection.resolve_resume_step_id(
        duplicate_index,
        "root.set_ready",
        presentation_key="SetReady",
    )
    assert duplicate_resolution.slot is None
    assert duplicate_resolution.candidate_count == 2
    duplicate_call_resolution = duplicate_projection.resolve_call_boundary(
        duplicate_index,
        "root.review_loop#0.iteration_body.run_review_loop",
    )
    assert duplicate_call_resolution.boundary is None
    assert duplicate_call_resolution.candidate_count == 2


@pytest.mark.parametrize(
    "malformed_step_id",
    [[], {}],
    ids=["list", "mapping"],
)
def test_projection_resume_slot_index_retains_unhashable_explicit_identity_for_shape_audit(
    tmp_path: Path,
    malformed_step_id: object,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    state = {
        "steps": {
            "SetReady": {
                "status": "completed",
                "name": "SetReady",
                "step_id": malformed_step_id,
            }
        }
    }

    slot_index = bundle.projection.enumerate_resume_slots(state)

    assert slot_index.unclaimed_explicit_rows == (("SetReady", malformed_step_id),)
    step_resolution = bundle.projection.resolve_resume_step_id(
        slot_index,
        malformed_step_id,
        presentation_key="SetReady",
    )
    assert step_resolution.slot is None
    assert step_resolution.candidate_count == 0
    assert step_resolution.exact_identity_candidate_count == 0
    call_resolution = bundle.projection.resolve_call_boundary(
        slot_index,
        malformed_step_id,
    )
    assert call_resolution.boundary is None
    assert call_resolution.candidate_count == 0


@pytest.mark.parametrize(
    ("repeat_progress", "repeat_frame"),
    [
        (
            {
                "current_iteration": 2,
                "completed_iterations": [0, 1],
                "condition_evaluated_for_iteration": None,
                "last_condition_result": None,
            },
            {"status": "running"},
        ),
        (
            {
                "current_iteration": None,
                "completed_iterations": [0, 1],
                "condition_evaluated_for_iteration": 1,
                "last_condition_result": True,
            },
            {"status": "completed"},
        ),
        (
            {
                "current_iteration": None,
                "completed_iterations": [0, 1, 2, 3],
                "condition_evaluated_for_iteration": 3,
                "last_condition_result": False,
                "exhausted": True,
            },
            {"status": "completed"},
        ),
        (
            {
                "current_iteration": None,
                "completed_iterations": [0, 1, 2, 3],
                "condition_evaluated_for_iteration": 3,
                "last_condition_result": False,
            },
            {
                "status": "failed",
                "error": {"type": "repeat_until_iterations_exhausted"},
            },
        ),
    ],
)
def test_projection_resume_slot_index_accepts_all_repeat_until_progress_forms(
    tmp_path: Path,
    repeat_progress: dict,
    repeat_frame: dict,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    projection = bundle.projection
    repeat_iterations = [
        *repeat_progress["completed_iterations"],
        *(
            [repeat_progress["current_iteration"]]
            if repeat_progress["current_iteration"] is not None
            else []
        ),
    ]
    state = {
        "steps": {
            "ReviewLoop": repeat_frame,
            "ProcessItems[0].InitializeCount": {
                "status": "completed",
                "step_id": projection.for_each_runtime_step_id(
                    "root.process_items",
                    0,
                    "root.process_items.initialize_count",
                ),
            },
            "ProcessItems[1].IncrementCount": {
                "status": "running",
                "step_id": projection.for_each_runtime_step_id(
                    "root.process_items",
                    1,
                    "root.process_items.increment_count",
                ),
            },
            **{
                f"ReviewLoop[{iteration}].WriteDecision": {
                    "status": "completed",
                    "step_id": projection.repeat_until_runtime_step_id(
                        "root.review_loop",
                        iteration,
                        "root.review_loop.iteration_body.write_decision",
                    ),
                }
                for iteration in repeat_iterations
            },
        },
        "for_each": {
            "ProcessItems": {
                "items": ["alpha", "beta"],
                "completed_indices": [0],
                "current_index": 1,
            }
        },
        "repeat_until": {"ReviewLoop": repeat_progress},
    }

    slot_index = projection.enumerate_resume_slots(state)

    assert slot_index.unclaimed_explicit_rows == ()
    for iteration in repeat_iterations:
        step_id = projection.repeat_until_runtime_step_id(
            "root.review_loop",
            iteration,
            "root.review_loop.iteration_body.write_decision",
        )
        assert projection.resolve_resume_step_id(
            slot_index,
            step_id,
            presentation_key=f"ReviewLoop[{iteration}].WriteDecision",
        ).slot.iteration_index == iteration
    assert projection.resolve_resume_step_id(
        slot_index,
        "root.process_items#0.initialize_count",
        presentation_key="ProcessItems[0].InitializeCount",
    ).slot.iteration_index == 0
    assert projection.resolve_resume_step_id(
        slot_index,
        "root.process_items#1.increment_count",
        presentation_key="ProcessItems[1].IncrementCount",
    ).slot.iteration_index == 1


_INVALID_LOOP_PROGRESS_CASES = (
    "for_each_container",
    "for_each_progress",
    "for_each_items",
    "for_each_boolean_index",
    "for_each_duplicate_index",
    "for_each_out_of_range",
    "for_each_current_completed_conflict",
    "repeat_container",
    "repeat_progress",
    "repeat_boolean_index",
    "repeat_duplicate_index",
    "repeat_out_of_range",
    "repeat_current_completed_conflict",
    "repeat_condition_result_conflict",
    "repeat_exhausted_type",
    "repeat_terminal_success_without_history",
    "repeat_successful_exhaustion_wrong_status",
    "repeat_failed_exhaustion_wrong_error",
)


def _valid_resume_loop_state() -> dict:
    return {
        "steps": {
            "ReviewLoop": {"status": "running"},
        },
        "for_each": {
            "ProcessItems": {
                "items": ["alpha", "beta"],
                "completed_indices": [0],
                "current_index": 1,
            }
        },
        "repeat_until": {
            "ReviewLoop": {
                "current_iteration": 1,
                "completed_iterations": [0],
                "condition_evaluated_for_iteration": None,
                "last_condition_result": None,
            }
        },
    }


def _corrupt_resume_loop_state(state: dict, corruption: str) -> str:
    if corruption == "for_each_container":
        state["for_each"] = []
        return "unsupported_shape"
    if corruption == "for_each_progress":
        state["for_each"]["ProcessItems"] = []
        return "unsupported_shape"
    if corruption == "for_each_items":
        state["for_each"]["ProcessItems"]["items"] = "alpha"
        return "unsupported_shape"
    if corruption == "for_each_boolean_index":
        state["for_each"]["ProcessItems"]["current_index"] = True
        return "unsupported_shape"
    if corruption == "for_each_duplicate_index":
        state["for_each"]["ProcessItems"]["completed_indices"] = [0, 0]
        return "invalid_loop_progress"
    if corruption == "for_each_out_of_range":
        state["for_each"]["ProcessItems"]["completed_indices"] = [2]
        return "invalid_loop_progress"
    if corruption == "for_each_current_completed_conflict":
        state["for_each"]["ProcessItems"]["completed_indices"] = [0, 1]
        return "invalid_loop_progress"
    if corruption == "repeat_container":
        state["repeat_until"] = []
        return "unsupported_shape"
    if corruption == "repeat_progress":
        state["repeat_until"]["ReviewLoop"] = []
        return "unsupported_shape"
    if corruption == "repeat_boolean_index":
        state["repeat_until"]["ReviewLoop"]["current_iteration"] = True
        return "unsupported_shape"
    if corruption == "repeat_duplicate_index":
        state["repeat_until"]["ReviewLoop"]["completed_iterations"] = [0, 0]
        return "invalid_loop_progress"
    if corruption == "repeat_out_of_range":
        state["repeat_until"]["ReviewLoop"]["current_iteration"] = 4
        return "invalid_loop_progress"
    if corruption == "repeat_current_completed_conflict":
        state["repeat_until"]["ReviewLoop"]["completed_iterations"] = [0, 1]
        return "invalid_loop_progress"
    if corruption == "repeat_condition_result_conflict":
        state["repeat_until"]["ReviewLoop"]["last_condition_result"] = False
        return "invalid_loop_progress"
    if corruption == "repeat_exhausted_type":
        state["repeat_until"]["ReviewLoop"]["exhausted"] = 1
        return "unsupported_shape"
    if corruption == "repeat_terminal_success_without_history":
        state["repeat_until"]["ReviewLoop"] = {
            "current_iteration": None,
            "completed_iterations": [],
            "condition_evaluated_for_iteration": None,
            "last_condition_result": True,
        }
        return "invalid_loop_progress"
    if corruption == "repeat_successful_exhaustion_wrong_status":
        state["repeat_until"]["ReviewLoop"] = {
            "current_iteration": None,
            "completed_iterations": [0, 1, 2, 3],
            "condition_evaluated_for_iteration": 3,
            "last_condition_result": False,
            "exhausted": True,
        }
        state["steps"]["ReviewLoop"] = {"status": "failed"}
        return "invalid_loop_progress"
    if corruption == "repeat_failed_exhaustion_wrong_error":
        state["repeat_until"]["ReviewLoop"] = {
            "current_iteration": None,
            "completed_iterations": [0, 1, 2, 3],
            "condition_evaluated_for_iteration": 3,
            "last_condition_result": False,
        }
        state["steps"]["ReviewLoop"] = {
            "status": "failed",
            "error": {"type": "repeat_until_body_step_failed"},
        }
        return "invalid_loop_progress"
    raise AssertionError(f"Unhandled corruption case: {corruption}")


@pytest.mark.parametrize("corruption", _INVALID_LOOP_PROGRESS_CASES)
def test_projection_resume_slot_index_rejects_invalid_loop_progress(
    tmp_path: Path,
    corruption: str,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_workflow(tmp_path))
    state = _valid_resume_loop_state()
    reason = _corrupt_resume_loop_state(state, corruption)

    with pytest.raises(ValueError, match=f"^{reason}:"):
        bundle.projection.enumerate_resume_slots(state)


def test_projection_resume_slot_index_rejects_stale_loop_local_and_call_ids(
    tmp_path: Path,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_call_workflow(tmp_path))
    projection = bundle.projection
    stale_repeat_id = "root.review_loop#2.iteration_body.run_review_loop"
    stale_for_each_id = "root.process_items#3.run_review_loop_from_for_each"
    state = {
        "steps": {
            "ReviewLoop": {"status": "running"},
            "ReviewLoop[0].RunReviewLoop": {
                "status": "failed",
                "step_id": stale_repeat_id,
            },
            "ProcessItems[0].RunReviewLoopFromForEach": {
                "status": "running",
                "step_id": stale_for_each_id,
            },
        },
        "repeat_until": {
            "ReviewLoop": {
                "current_iteration": 0,
                "completed_iterations": [],
                "condition_evaluated_for_iteration": None,
                "last_condition_result": None,
            }
        },
        "for_each": {
            "ProcessItems": {
                "items": ["alpha"],
                "completed_indices": [],
                "current_index": 0,
            }
        },
    }

    slot_index = projection.enumerate_resume_slots(state)

    assert slot_index.unclaimed_explicit_rows == (
        ("ReviewLoop[0].RunReviewLoop", stale_repeat_id),
        ("ProcessItems[0].RunReviewLoopFromForEach", stale_for_each_id),
    )
    assert projection.resolve_resume_step_id(
        slot_index,
        stale_repeat_id,
        presentation_key="ReviewLoop[0].RunReviewLoop",
    ).candidate_count == 0
    assert projection.resolve_resume_step_id(
        slot_index,
        stale_for_each_id,
        presentation_key="ProcessItems[0].RunReviewLoopFromForEach",
    ).candidate_count == 0
    assert projection.resolve_call_boundary(
        slot_index,
        stale_repeat_id,
    ).candidate_count == 0
    assert projection.resolve_call_boundary(
        slot_index,
        stale_for_each_id,
    ).candidate_count == 0


def test_call_boundary_projection_exposes_current_import_alias(tmp_path: Path) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_projection_call_workflow(tmp_path))

    assert {
        boundary.import_alias
        for boundary in bundle.projection.call_boundaries.values()
    } == {"review_loop"}
