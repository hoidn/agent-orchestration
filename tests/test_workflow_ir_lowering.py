"""Characterization tests for typed executable IR lowering."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executable_ir import (
    CallOutputAddress,
    ExecutableNodeKind,
    LoopOutputAddress,
    MatchJoinNode,
    NodeResultAddress,
    RepeatUntilFrameNode,
)
from orchestrator.workflow.lowering import render_legacy_compatible_workflow


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


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


def _write_ir_workflow(workspace: Path) -> Path:
    _write_review_loop_library(workspace)
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.7",
            "name": "typed-ir",
            "imports": {
                "review_loop": "workflows/library/review_loop.yaml",
            },
            "artifacts": {
                "ready": {"kind": "scalar", "type": "bool"},
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
                                "left": {
                                    "ref": "self.outputs.review_decision",
                                },
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


def _write_goto_workflow(workspace: Path) -> Path:
    return _write_yaml(
        workspace / "goto_workflow.yaml",
        {
            "version": "2.7",
            "name": "goto-ir",
            "artifacts": {
                "ready": {"kind": "scalar", "type": "bool"},
            },
            "steps": [
                {
                    "name": "RouteToDone",
                    "id": "route_to_done",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                    "goto": "Done",
                },
                {
                    "name": "SkippedStep",
                    "id": "skipped_step",
                    "command": ["bash", "-lc", "printf 'skip\\n'"],
                },
                {
                    "name": "Done",
                    "id": "done",
                    "command": ["bash", "-lc", "printf 'done\\n'"],
                },
            ],
        },
    )


def test_loader_bundle_exposes_executable_ir_topology_and_node_kinds(tmp_path: Path):
    workflow_path = _write_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    ir = bundle.ir

    assert ir.body_region == (
        "root.set_ready",
        "root.route_review.approve_path",
        "root.route_review.approve_path.write_approved",
        "root.route_review.revise_path",
        "root.route_review.revise_path.write_revision",
        "root.route_review",
        "root.set_decision",
        "root.route_decision.approve_path",
        "root.route_decision.approve_path.write_approved",
        "root.route_decision.revise_path",
        "root.route_decision.revise_path.write_revision",
        "root.route_decision",
        "root.review_loop",
    )
    assert ir.finalization_region == ("root.finally.cleanup.write_cleanup_marker",)

    assert ir.nodes["root.set_ready"].kind is ExecutableNodeKind.SET_SCALAR
    assert ir.nodes["root.route_review.approve_path"].kind is ExecutableNodeKind.IF_BRANCH_MARKER
    assert ir.nodes["root.route_review"].kind is ExecutableNodeKind.IF_JOIN
    assert ir.nodes["root.route_decision.approve_path"].kind is ExecutableNodeKind.MATCH_CASE_MARKER
    assert ir.nodes["root.route_decision"].kind is ExecutableNodeKind.MATCH_JOIN
    assert ir.nodes["root.review_loop"].kind is ExecutableNodeKind.REPEAT_UNTIL_FRAME
    assert ir.nodes["root.review_loop.iteration_body.run_review_loop"].kind is ExecutableNodeKind.CALL_BOUNDARY
    assert ir.nodes["root.finally.cleanup.write_cleanup_marker"].kind is ExecutableNodeKind.FINALIZATION_STEP


def test_ir_lowering_binds_structured_refs_to_durable_node_addresses(tmp_path: Path):
    workflow_path = _write_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    ir = bundle.ir

    route_decision = ir.nodes["root.route_decision"]
    assert isinstance(route_decision, MatchJoinNode)
    assert route_decision.selector_address == NodeResultAddress(
        node_id="root.set_decision",
        field="artifacts",
        member="review_decision",
    )
    assert route_decision.case_outputs["APPROVE"]["route_action"].source_address == NodeResultAddress(
        node_id="root.route_decision.approve_path.write_approved",
        field="artifacts",
        member="route_action",
    )

    review_loop = ir.nodes["root.review_loop"]
    assert isinstance(review_loop, RepeatUntilFrameNode)
    assert review_loop.output_contracts["review_decision"].source_address == CallOutputAddress(
        node_id="root.review_loop.iteration_body.run_review_loop",
        output_name="review_decision",
    )
    assert review_loop.condition.left == LoopOutputAddress(
        node_id="root.review_loop",
        output_name="review_decision",
    )


def test_loader_bundle_legacy_workflow_is_rendered_from_ir_projection_adapter(tmp_path: Path):
    workflow_path = _write_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    rendered = render_legacy_compatible_workflow(
        bundle.surface,
        bundle.ir,
        bundle.projection,
        imported_workflows={
            alias: imported.legacy_workflow
            for alias, imported in bundle.imports.items()
        },
    )

    assert rendered["steps"] == bundle.legacy_workflow["steps"]
    assert rendered["finally"] == bundle.legacy_workflow["finally"]


def test_ir_lowering_exposes_routed_transfers_for_goto_loop_call_and_finalization(tmp_path: Path):
    workflow_path = _write_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    ir = bundle.ir
    review_loop = ir.nodes["root.review_loop"]
    call_node = ir.nodes["root.review_loop.iteration_body.run_review_loop"]

    assert ir.finalization_entry_node_id == "root.finally.cleanup.write_cleanup_marker"
    assert review_loop.routed_transfers["loop_continue"].target_node_id == (
        "root.review_loop.iteration_body.run_review_loop"
    )
    assert review_loop.routed_transfers["loop_exit"].target_node_id == ir.finalization_entry_node_id
    assert review_loop.routed_transfers["loop_exit"].counts_as_transition is False
    assert call_node.routed_transfers["call_return"].target_node_id == "root.review_loop"
    assert call_node.routed_transfers["call_return"].counts_as_transition is False

    goto_path = _write_goto_workflow(tmp_path)
    goto_bundle = WorkflowLoader(tmp_path).load_bundle(goto_path)
    goto_node = goto_bundle.ir.nodes["root.route_to_done"]

    assert goto_node.routed_transfers["goto"].target_node_id == "root.done"
    assert goto_node.routed_transfers["goto"].counts_as_transition is True
