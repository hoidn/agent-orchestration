"""Characterization tests for typed executable IR lowering."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executable_ir import (
    CallStepConfig,
    CallOutputAddress,
    ExecutableNodeKind,
    ForEachStepConfig,
    LoopOutputAddress,
    MatchJoinNode,
    NodeResultAddress,
    RepeatUntilFrameNode,
    RepeatUntilStepConfig,
    SetScalarStepConfig,
)
from orchestrator.workflow import lowering


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


def _write_for_each_call_ir_workflow(workspace: Path) -> Path:
    _write_review_loop_library(workspace)
    return _write_yaml(
        workspace / "for_each_call_workflow.yaml",
        {
            "version": "2.7",
            "name": "typed-ir-for-each",
            "imports": {
                "review_loop": "workflows/library/review_loop.yaml",
            },
            "steps": [
                {
                    "name": "ProcessItems",
                    "id": "process_items",
                    "for_each": {
                        "items": ["alpha", "beta"],
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
                {
                    "name": "Done",
                    "id": "done",
                    "command": ["bash", "-lc", "printf 'done\\n'"],
                },
            ],
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
                    "on": {
                        "success": {
                            "goto": "Done",
                        }
                    },
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


def test_loader_bundle_exposes_no_legacy_workflow_projection_adapter(tmp_path: Path):
    workflow_path = _write_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    assert not hasattr(bundle, "legacy_workflow")
    assert not hasattr(lowering, "render_legacy_compatible_workflow")


def test_ir_lowering_exposes_routed_transfers_for_on_goto_loop_call_and_finalization(tmp_path: Path):
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

    assert goto_node.routed_transfers["on_success_goto"].target_node_id == "root.done"
    assert goto_node.routed_transfers["on_success_goto"].counts_as_transition is True


def test_ir_lowering_patches_for_each_body_fallthrough_and_iteration_owned_call_boundaries(
    tmp_path: Path,
):
    workflow_path = _write_for_each_call_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    ir = bundle.ir
    loop_node = ir.nodes["root.process_items"]
    call_node = ir.nodes["root.process_items.run_review_loop_from_for_each"]
    call_boundary = bundle.projection.call_boundaries["root.process_items.run_review_loop_from_for_each"]

    assert loop_node.kind is ExecutableNodeKind.FOR_EACH
    assert loop_node.body_entry_node_id == "root.process_items.run_review_loop_from_for_each"
    assert loop_node.body_node_ids == ("root.process_items.run_review_loop_from_for_each",)
    assert loop_node.fallthrough_node_id == "root.done"
    assert loop_node.routed_transfers["loop_exit"].target_node_id == "root.done"
    assert call_node.fallthrough_node_id == "root.process_items"
    assert call_node.routed_transfers["call_return"].target_node_id == "root.process_items"
    assert call_boundary.iteration_owner_node_id == "root.process_items"
    assert call_boundary.runtime_step_id(iteration_index=1) == (
        "root.process_items#1.run_review_loop_from_for_each"
    )


def test_lowering_emits_typed_execution_configs_for_leaf_and_loop_nodes(tmp_path: Path):
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_ir_workflow(tmp_path))
    for_each_bundle = WorkflowLoader(tmp_path).load_bundle(_write_for_each_call_ir_workflow(tmp_path))

    set_ready = bundle.ir.nodes["root.set_ready"]
    review_loop = bundle.ir.nodes["root.review_loop"]
    process_items = for_each_bundle.ir.nodes["root.process_items"]
    run_review_loop = for_each_bundle.ir.nodes["root.process_items.run_review_loop_from_for_each"]

    assert isinstance(set_ready.execution_config, SetScalarStepConfig)
    assert set_ready.execution_config.set_scalar["artifact"] == "ready"
    assert set_ready.execution_config.set_scalar["value"] is True

    assert isinstance(review_loop.execution_config, RepeatUntilStepConfig)
    assert review_loop.execution_config.body_id == "iteration_body"
    assert review_loop.execution_config.max_iterations == 3

    assert isinstance(process_items.execution_config, ForEachStepConfig)
    assert list(process_items.execution_config.items) == ["alpha", "beta"]
    assert process_items.execution_config.item_name == "item"

    assert isinstance(run_review_loop.execution_config, CallStepConfig)
    assert run_review_loop.execution_config.call == "review_loop"
