"""Characterization tests for loader/lowering compatibility surfaces."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.surface_ast import SurfaceStepKind
from tests.workflow_bundle_helpers import (
    materialize_projection_body_steps,
    materialize_projection_finalization_steps,
)


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _load_workflow(workspace: Path, workflow: dict):
    workflow_path = _write_yaml(workspace / "workflow.yaml", workflow)
    return WorkflowLoader(workspace).load_bundle(workflow_path)


def _write_review_loop_library(workspace: Path) -> None:
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
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {"ref": "root.steps.WriteDecision.artifacts.review_decision"},
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


def _top_level_structured_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
        {
            "name": "SetReady",
            "id": "set_ready",
            "set_scalar": {
                "artifact": "ready",
                "value": True,
            },
        },
        {
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
        },
        {
            "name": "SetDecision",
            "id": "set_decision",
            "set_scalar": {
                "artifact": "review_decision",
                "value": "REVISE",
            },
        },
        {
            "name": "RouteDecision",
            "id": "route_decision",
            "match": {
                "ref": "root.steps.SetDecision.artifacts.review_decision",
                "cases": {
                    "APPROVE": {
                        "id": "approve_path",
                        "outputs": {
                            "route_action": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["SHIP", "FIX"],
                                "from": {
                                    "ref": "self.steps.WriteApproved.artifacts.route_action",
                                },
                            }
                        },
                        "steps": [
                            {
                                "name": "WriteApproved",
                                "id": "write_approved",
                                "set_scalar": {
                                    "artifact": "route_action",
                                    "value": "SHIP",
                                },
                            }
                        ],
                    },
                    "REVISE": {
                        "id": "revise_path",
                        "outputs": {
                            "route_action": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["SHIP", "FIX"],
                                "from": {
                                    "ref": "self.steps.WriteRevision.artifacts.route_action",
                                },
                            }
                        },
                        "steps": [
                            {
                                "name": "WriteRevision",
                                "id": "write_revision",
                                "set_scalar": {
                                    "artifact": "route_action",
                                    "value": "FIX",
                                },
                            }
                        ],
                    },
                },
            },
        },
        {
            "name": "RunReviewLoop",
            "id": "run_review_loop",
            "call": "review_loop",
            "with": {
                "iteration": 1,
                "write_root": "state/review-loop",
            },
        },
        {
            "name": "CheckRouteAction",
            "id": "check_route_action",
            "assert": {
                "compare": {
                    "left": {"ref": "root.steps.RouteDecision.artifacts.route_action"},
                    "op": "eq",
                    "right": "FIX",
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
        "version": "2.7",
        "name": "top-level-structured-surfaces",
        "imports": {
            "review_loop": "workflows/library/review_loop.yaml",
        },
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
            "route_action": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["SHIP", "FIX"],
            },
        },
        "steps": steps,
    }


def _repeat_until_structured_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
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
                        "from": {"ref": "self.steps.RouteDecision.artifacts.review_decision"},
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
                        "name": "PrepareCallInputs",
                        "id": "prepare_call_inputs",
                        "command": [
                            "bash",
                            "-lc",
                            "\n".join(
                                [
                                    "mkdir -p state/review-loop-inputs",
                                    "iteration=$(( ${loop.index} + 1 ))",
                                    (
                                        "printf '{\"write_root\":\"state/review-loop/iterations/%s\","
                                        "\"iteration\":%s}\\n' \"$iteration\" \"$iteration\" "
                                        "> state/review-loop-inputs/current.json"
                                    ),
                                ]
                            ),
                        ],
                        "output_bundle": {
                            "path": "state/review-loop-inputs/current.json",
                            "fields": [
                                {
                                    "name": "write_root",
                                    "json_pointer": "/write_root",
                                    "type": "relpath",
                                },
                                {
                                    "name": "iteration",
                                    "json_pointer": "/iteration",
                                    "type": "integer",
                                },
                            ],
                        },
                    },
                    {
                        "name": "RunReviewLoop",
                        "id": "run_review_loop",
                        "call": "review_loop",
                        "with": {
                            "iteration": {
                                "ref": "self.steps.PrepareCallInputs.artifacts.iteration",
                            },
                            "write_root": {
                                "ref": "self.steps.PrepareCallInputs.artifacts.write_root",
                            },
                        },
                    },
                    {
                        "name": "RouteDecision",
                        "id": "route_decision",
                        "match": {
                            "ref": "self.steps.RunReviewLoop.artifacts.review_decision",
                            "cases": {
                                "APPROVE": {
                                    "id": "approve_path",
                                    "outputs": {
                                        "review_decision": {
                                            "kind": "scalar",
                                            "type": "enum",
                                            "allowed": ["APPROVE", "REVISE"],
                                            "from": {
                                                "ref": (
                                                    "self.steps.WriteApproved.artifacts.review_decision"
                                                ),
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
                                "REVISE": {
                                    "id": "revise_path",
                                    "outputs": {
                                        "review_decision": {
                                            "kind": "scalar",
                                            "type": "enum",
                                            "allowed": ["APPROVE", "REVISE"],
                                            "from": {
                                                "ref": (
                                                    "self.steps.WriteRevision.artifacts.review_decision"
                                                ),
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
                            },
                        },
                    },
                ],
            },
        }
    ]
    if include_inserted_sibling:
        steps.insert(
            0,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "printf 'inserted\\n'"],
            },
        )

    return {
        "version": "2.7",
        "name": "repeat-until-structured-surfaces",
        "imports": {
            "review_loop": "workflows/library/review_loop.yaml",
        },
        "artifacts": {
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }
        },
        "steps": steps,
    }


def _for_each_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
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
        }
    ]
    if include_inserted_sibling:
        steps.insert(
            0,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "printf 'inserted\\n'"],
            },
        )

    return {
        "version": "2.0",
        "name": "for-each-stable-ids",
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": steps,
    }


def _finalization_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
        {
            "name": "WriteDecision",
            "id": "write_decision",
            "set_scalar": {
                "artifact": "decision",
                "value": "APPROVE",
            },
        }
    ]
    if include_inserted_sibling:
        steps.insert(
            0,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "printf 'inserted\\n'"],
            },
        )

    return {
        "version": "2.3",
        "name": "finalization-surfaces",
        "artifacts": {
            "decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }
        },
        "steps": steps,
        "finally": {
            "id": "cleanup",
            "steps": [
                {
                    "name": "ObserveOutputsPending",
                    "id": "observe_outputs_pending",
                    "command": ["bash", "-lc", "printf 'pending\\n'"],
                },
                {
                    "name": "WriteCleanupMarker",
                    "id": "write_cleanup_marker",
                    "command": ["bash", "-lc", "printf 'cleanup\\n'"],
                },
            ],
        },
    }


def test_structured_top_level_lowering_preserves_order_presentation_names_and_stable_ids(tmp_path: Path):
    _write_review_loop_library(tmp_path / "a")
    _write_review_loop_library(tmp_path / "b")

    loaded_a = _load_workflow(tmp_path / "a", _top_level_structured_workflow())
    loaded_b = _load_workflow(
        tmp_path / "b",
        _top_level_structured_workflow(include_inserted_sibling=True),
    )

    body_steps_a = materialize_projection_body_steps(loaded_a)
    body_steps_b = materialize_projection_body_steps(loaded_b)

    assert [step["name"] for step in body_steps_a] == [
        "SetReady",
        "RouteReview.then",
        "RouteReview.then.WriteApproved",
        "RouteReview.else",
        "RouteReview.else.WriteRevision",
        "RouteReview",
        "SetDecision",
        "RouteDecision.APPROVE",
        "RouteDecision.APPROVE.WriteApproved",
        "RouteDecision.REVISE",
        "RouteDecision.REVISE.WriteRevision",
        "RouteDecision",
        "RunReviewLoop",
        "CheckRouteAction",
    ]

    steps_a = {step["name"]: step["step_id"] for step in body_steps_a}
    steps_b = {step["name"]: step["step_id"] for step in body_steps_b}

    assert steps_a["RouteReview.then"] == "root.route_review.approve_path"
    assert steps_a["RouteReview.then.WriteApproved"] == "root.route_review.approve_path.write_approved"
    assert steps_a["RouteReview"] == "root.route_review"
    assert steps_a["RouteDecision.APPROVE"] == "root.route_decision.approve_path"
    assert (
        steps_a["RouteDecision.REVISE.WriteRevision"]
        == "root.route_decision.revise_path.write_revision"
    )
    assert steps_a["RouteDecision"] == "root.route_decision"
    assert steps_a["RunReviewLoop"] == "root.run_review_loop"
    assert steps_b["RouteReview.then"] == steps_a["RouteReview.then"]
    assert steps_b["RouteReview.then.WriteApproved"] == steps_a["RouteReview.then.WriteApproved"]
    assert steps_b["RouteReview"] == steps_a["RouteReview"]
    assert steps_b["RouteDecision.APPROVE"] == steps_a["RouteDecision.APPROVE"]
    assert steps_b["RouteDecision.REVISE.WriteRevision"] == steps_a["RouteDecision.REVISE.WriteRevision"]
    assert steps_b["RouteDecision"] == steps_a["RouteDecision"]
    assert steps_b["RunReviewLoop"] == steps_a["RunReviewLoop"]


def test_repeat_until_nested_call_and_match_surfaces_keep_stable_body_step_ids(tmp_path: Path):
    _write_review_loop_library(tmp_path / "a")
    _write_review_loop_library(tmp_path / "b")

    loaded_a = _load_workflow(tmp_path / "a", _repeat_until_structured_workflow())
    loaded_b = _load_workflow(
        tmp_path / "b",
        _repeat_until_structured_workflow(include_inserted_sibling=True),
    )

    steps_a = {step["name"]: step for step in materialize_projection_body_steps(loaded_a)}
    steps_b = {step["name"]: step for step in materialize_projection_body_steps(loaded_b)}

    body_a = {
        step["name"]: step["step_id"]
        for step in steps_a["ReviewLoop"]["repeat_until"]["steps"]
    }
    body_b = {
        step["name"]: step["step_id"]
        for step in steps_b["ReviewLoop"]["repeat_until"]["steps"]
    }

    assert steps_a["ReviewLoop"]["step_id"] == "root.review_loop"
    assert body_a["PrepareCallInputs"] == "root.review_loop.iteration_body.prepare_call_inputs"
    assert body_a["RunReviewLoop"] == "root.review_loop.iteration_body.run_review_loop"
    assert body_a["RouteDecision.APPROVE"] == "root.review_loop.iteration_body.route_decision.approve_path"
    assert (
        body_a["RouteDecision.REVISE.WriteRevision"]
        == "root.review_loop.iteration_body.route_decision.revise_path.write_revision"
    )
    assert body_a["RouteDecision"] == "root.review_loop.iteration_body.route_decision"
    assert steps_b["ReviewLoop"]["step_id"] == steps_a["ReviewLoop"]["step_id"]
    assert body_b == body_a


def test_for_each_nested_step_ids_stay_stable_when_siblings_shift(tmp_path: Path):
    loaded_a = _load_workflow(tmp_path / "a", _for_each_workflow())
    loaded_b = _load_workflow(tmp_path / "b", _for_each_workflow(include_inserted_sibling=True))

    steps_a = {step["name"]: step for step in materialize_projection_body_steps(loaded_a)}
    steps_b = {step["name"]: step for step in materialize_projection_body_steps(loaded_b)}
    nested_a = {
        step["name"]: step["step_id"]
        for step in steps_a["ProcessItems"]["for_each"]["steps"]
    }
    nested_b = {
        step["name"]: step["step_id"]
        for step in steps_b["ProcessItems"]["for_each"]["steps"]
    }

    assert steps_a["ProcessItems"]["step_id"] == "root.process_items"
    assert nested_a["InitializeCount"] == "root.process_items.initialize_count"
    assert nested_a["IncrementCount"] == "root.process_items.increment_count"
    assert steps_b["ProcessItems"]["step_id"] == steps_a["ProcessItems"]["step_id"]
    assert nested_b == nested_a


def test_finalization_steps_use_prefixed_presentation_names_and_stable_ids(tmp_path: Path):
    loaded_a = _load_workflow(tmp_path / "a", _finalization_workflow())
    loaded_b = _load_workflow(tmp_path / "b", _finalization_workflow(include_inserted_sibling=True))

    body_steps_a = materialize_projection_body_steps(loaded_a)
    body_steps_b = materialize_projection_body_steps(loaded_b)
    final_steps_a = materialize_projection_finalization_steps(loaded_a)
    final_steps_b = materialize_projection_finalization_steps(loaded_b)

    assert [step["name"] for step in final_steps_a] == [
        "finally.ObserveOutputsPending",
        "finally.WriteCleanupMarker",
    ]

    steps_a = {step["name"]: step["step_id"] for step in body_steps_a + final_steps_a}
    steps_b = {step["name"]: step["step_id"] for step in body_steps_b + final_steps_b}

    assert steps_a["finally.ObserveOutputsPending"] == "root.finally.cleanup.observe_outputs_pending"
    assert steps_a["finally.WriteCleanupMarker"] == "root.finally.cleanup.write_cleanup_marker"
    assert steps_b["finally.ObserveOutputsPending"] == steps_a["finally.ObserveOutputsPending"]
    assert steps_b["finally.WriteCleanupMarker"] == steps_a["finally.WriteCleanupMarker"]


def test_surface_ast_step_ids_match_projection_compatibility_ids(tmp_path: Path):
    _write_review_loop_library(tmp_path)

    workflow = _top_level_structured_workflow()
    workflow["finally"] = {
        "id": "cleanup",
        "steps": [
            {
                "name": "WriteCleanupMarker",
                "id": "write_cleanup_marker",
                "command": ["bash", "-lc", "printf 'cleanup\\n'"],
            }
        ],
    }
    workflow_path = _write_yaml(tmp_path / "workflow.yaml", workflow)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    surface_steps = {step.name: step for step in bundle.surface.steps}
    projection_steps = {
        step["name"]: step["step_id"]
        for step in materialize_projection_body_steps(bundle)
    }

    assert surface_steps["RouteReview"].kind is SurfaceStepKind.IF
    assert surface_steps["RouteReview"].then_branch is not None
    assert (
        surface_steps["RouteReview"].then_branch.steps[0].step_id
        == projection_steps["RouteReview.then.WriteApproved"]
    )
    assert surface_steps["RouteReview"].step_id == projection_steps["RouteReview"]

    assert surface_steps["RouteDecision"].kind is SurfaceStepKind.MATCH
    assert surface_steps["RouteDecision"].match_cases["APPROVE"].steps[0].step_id == (
        projection_steps["RouteDecision.APPROVE.WriteApproved"]
    )

    assert surface_steps["RunReviewLoop"].kind is SurfaceStepKind.CALL
    assert surface_steps["RunReviewLoop"].step_id == projection_steps["RunReviewLoop"]

    assert bundle.surface.finalization is not None
    final_step = bundle.surface.finalization.steps[0]
    assert final_step.step_id == materialize_projection_finalization_steps(bundle)[0]["step_id"]
