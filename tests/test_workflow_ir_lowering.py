"""Characterization tests for typed executable IR lowering."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from types import MappingProxyType

from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow.executable_ir import (
    CallStepConfig,
    CallOutputAddress,
    CommandStepConfig,
    ExecutableNodeKind,
    ForEachStepConfig,
    LoopOutputAddress,
    MatchJoinNode,
    ProviderStepConfig,
    NodeResultAddress,
    RepeatUntilFrameNode,
    RepeatUntilStepConfig,
    SetScalarStepConfig,
    _json_value,
)
from orchestrator.workflow import lowering
from orchestrator.workflow import executable_ir
from tests.workflow_bundle_helpers import materialize_execution_config_for_test


WORKFLOW_LISP_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "workflow_lisp" / "valid"
ENTRY_PUBLICATION_RUNTIME_FIXTURE = WORKFLOW_LISP_FIXTURES / "entry_publication_runtime.orc"


def _detach_core_ast_surface_links(value):
    if isinstance(value, tuple):
        return tuple(_detach_core_ast_surface_links(item) for item in value)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _detach_core_ast_surface_links(item) for key, item in value.items()})
    if not is_dataclass(value):
        return value

    updates = {}
    for field_def in fields(value):
        field_value = getattr(value, field_def.name)
        if field_def.name in {"_surface_step", "_surface_workflow"}:
            updates[field_def.name] = None
            continue
        detached = _detach_core_ast_surface_links(field_value)
        if detached is not field_value:
            updates[field_def.name] = detached
    return replace(value, **updates) if updates else value


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


def _write_consume_prompt_ir_workflow(workspace: Path) -> Path:
    return _write_yaml(
        workspace / "consume_prompt_workflow.yaml",
        {
            "version": "2.7",
            "name": "consume-prompt-ir",
            "providers": {
                "audit_provider": {
                    "command": ["echo", "${PROMPT}"],
                    "input_mode": "argv",
                }
            },
            "artifacts": {
                "baseline_design": {
                    "pointer": "state/baseline_design.txt",
                    "type": "relpath",
                    "under": "docs",
                },
                "execution_log": {
                    "pointer": "state/execution_log.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                },
            },
            "steps": [
                {
                    "name": "Review",
                    "id": "review",
                    "provider": "audit_provider",
                    "input_file": "prompts/review.md",
                    "prompt_consumes": [],
                    "consumes": [
                        {
                            "artifact": "baseline_design",
                            "prompt": {
                                "mode": "reference",
                                "label": "Baseline design",
                            },
                        },
                        {
                            "artifact": "execution_log",
                            "prompt": {"mode": "content"},
                        },
                    ],
                }
            ],
        },
    )


def test_executable_ir_does_not_export_legacy_runtime_materializer():
    assert not hasattr(executable_ir, "materialize_execution_config")


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


def _write_leaf_payload_ir_workflow(workspace: Path) -> Path:
    return _write_yaml(
        workspace / "leaf_payload_workflow.yaml",
        {
            "version": "1.1.1",
            "providers": {
                "audit_provider": {
                    "command": ["echo", "${PROMPT}"],
                    "input_mode": "argv",
                    "defaults": {
                        "model": "test-model",
                    },
                }
            },
            "steps": [
                {
                    "name": "RunShell",
                    "command": 'echo "hello ${context.name}"',
                },
                {
                    "name": "RenderPrompt",
                    "provider": "audit_provider",
                    "input_file": "prompt.txt",
                    "depends_on": {
                        "required": ["data.txt"],
                        "inject": True,
                    },
                    "output_capture": "text",
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


def test_loader_bundle_exposes_versioned_executable_ir_contract_and_serializer(tmp_path: Path) -> None:
    workflow_path = _write_ir_workflow(tmp_path)
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    schema_version = getattr(executable_ir, "WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION", None)
    assert schema_version == "workflow_executable_ir.v1"
    assert getattr(bundle.ir, "schema_version", None) == schema_version

    serializer = getattr(executable_ir, "workflow_executable_ir_to_json", None)
    assert callable(serializer)
    payload = serializer(bundle.ir)

    assert payload["schema_version"] == schema_version
    assert payload["version"] == bundle.ir.version


def test_validate_executable_workflow_accepts_loaded_bundle(tmp_path: Path) -> None:
    workflow_path = _write_ir_workflow(tmp_path)
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    validator = getattr(executable_ir, "validate_executable_workflow", None)
    assert callable(validator)
    validator(bundle.ir)


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (
            "unknown_body_node",
            "body region references unknown node",
        ),
        (
            "kind_config_mismatch",
            "kind/config mismatch",
        ),
        (
            "unknown_contract_address",
            "unknown node id",
        ),
        (
            "call_output_wrong_kind",
            "must reference call boundary node",
        ),
        (
            "call_output_missing_output",
            "references unknown call output",
        ),
        (
            "loop_output_wrong_kind",
            "must reference repeat-until frame node",
        ),
        (
            "loop_output_missing_output",
            "references unknown repeat-until output",
        ),
    ],
)
def test_validate_executable_workflow_rejects_invalid_topology_and_addresses(
    tmp_path: Path,
    mutation: str,
    expected_fragment: str,
) -> None:
    workflow_path = _write_ir_workflow(tmp_path)
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    validator = getattr(executable_ir, "validate_executable_workflow", None)
    assert callable(validator)

    if mutation == "unknown_body_node":
        broken_ir = replace(bundle.ir, body_region=bundle.ir.body_region + ("root.missing",))
    elif mutation == "kind_config_mismatch":
        set_ready = bundle.ir.nodes["root.set_ready"]
        broken_node = replace(set_ready, kind=ExecutableNodeKind.PROVIDER)
        broken_ir = replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    broken_node.node_id: broken_node,
                }
            ),
        )
    elif mutation == "unknown_contract_address":
        review_loop = bundle.ir.nodes["root.review_loop"]
        assert isinstance(review_loop, RepeatUntilFrameNode)
        broken_contract = replace(
            review_loop.output_contracts["review_decision"],
            source_address=CallOutputAddress(
                node_id="root.missing",
                output_name="review_decision",
            ),
        )
        broken_node = replace(
            review_loop,
            output_contracts=MappingProxyType(
                {
                    **dict(review_loop.output_contracts),
                    "review_decision": broken_contract,
                }
            ),
        )
        broken_ir = replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    broken_node.node_id: broken_node,
                }
            ),
        )
    elif mutation == "call_output_wrong_kind":
        review_loop = bundle.ir.nodes["root.review_loop"]
        assert isinstance(review_loop, RepeatUntilFrameNode)
        broken_contract = replace(
            review_loop.output_contracts["review_decision"],
            source_address=CallOutputAddress(
                node_id="root.set_ready",
                output_name="review_decision",
            ),
        )
        broken_node = replace(
            review_loop,
            output_contracts=MappingProxyType(
                {
                    **dict(review_loop.output_contracts),
                    "review_decision": broken_contract,
                }
            ),
        )
        broken_ir = replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    broken_node.node_id: broken_node,
                }
            ),
        )
    elif mutation == "call_output_missing_output":
        review_loop = bundle.ir.nodes["root.review_loop"]
        assert isinstance(review_loop, RepeatUntilFrameNode)
        broken_contract = replace(
            review_loop.output_contracts["review_decision"],
            source_address=CallOutputAddress(
                node_id="root.review_loop.iteration_body.run_review_loop",
                output_name="missing_output",
            ),
        )
        broken_node = replace(
            review_loop,
            output_contracts=MappingProxyType(
                {
                    **dict(review_loop.output_contracts),
                    "review_decision": broken_contract,
                }
            ),
        )
        broken_ir = replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    broken_node.node_id: broken_node,
                }
            ),
        )
    elif mutation == "loop_output_wrong_kind":
        review_loop = bundle.ir.nodes["root.review_loop"]
        assert isinstance(review_loop, RepeatUntilFrameNode)
        broken_condition = replace(
            review_loop.condition,
            left=LoopOutputAddress(
                node_id="root.review_loop.iteration_body.run_review_loop",
                output_name="review_decision",
            ),
        )
        broken_node = replace(review_loop, condition=broken_condition)
        broken_ir = replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    broken_node.node_id: broken_node,
                }
            ),
        )
    else:
        review_loop = bundle.ir.nodes["root.review_loop"]
        assert isinstance(review_loop, RepeatUntilFrameNode)
        broken_condition = replace(
            review_loop.condition,
            left=LoopOutputAddress(
                node_id="root.review_loop",
                output_name="missing_output",
            ),
        )
        broken_node = replace(review_loop, condition=broken_condition)
        broken_ir = replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    broken_node.node_id: broken_node,
                }
            ),
        )

    with pytest.raises(WorkflowValidationError) as excinfo:
        validator(broken_ir)

    assert excinfo.value.errors
    assert excinfo.value.errors[0].message.startswith("executable_ir_invalid:")
    assert expected_fragment in excinfo.value.errors[0].message


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


def test_ir_nodes_expose_no_legacy_raw_payloads(tmp_path: Path):
    workflow_path = _write_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    assert all(not hasattr(node, "raw") for node in bundle.ir.nodes.values())


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


def test_ir_lowering_uses_typed_surface_goto_without_raw_payloads(tmp_path: Path):
    goto_path = _write_goto_workflow(tmp_path)
    bundle = WorkflowLoader(tmp_path).load_bundle(goto_path)
    route_to_done = bundle.surface.steps[0]
    assert not hasattr(route_to_done, "raw")

    ir, _ = lowering.lower_surface_workflow(bundle.surface)
    goto_node = ir.nodes["root.route_to_done"]

    assert goto_node.execution_config is not None
    assert goto_node.execution_config.common.on["success"]["goto"] == "Done"
    assert goto_node.routed_transfers["on_success_goto"].target_node_id == "root.done"


def test_lower_core_workflow_ast_matches_surface_lowering_characterization(tmp_path: Path, monkeypatch):
    workflow_path = _write_ir_workflow(tmp_path)
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    detached_core_ast = _detach_core_ast_surface_links(bundle.core_workflow_ast)

    def _unexpected_surface_lowering(*args, **kwargs):
        raise AssertionError("lower_core_workflow_ast should not delegate to lower_surface_workflow")

    surface_ir, surface_projection = lowering.lower_surface_workflow(bundle.surface)
    monkeypatch.setattr(lowering, "lower_surface_workflow", _unexpected_surface_lowering)
    core_ir, core_projection = lowering.lower_core_workflow_ast(detached_core_ast)

    assert core_ir.body_region == surface_ir.body_region
    assert core_ir.finalization_region == surface_ir.finalization_region
    assert set(core_ir.nodes) == set(surface_ir.nodes)
    assert core_projection.node_id_by_step_id == surface_projection.node_id_by_step_id
    assert bundle.runtime_plan.ordered_node_ids == surface_projection.ordered_execution_node_ids()
    assert bundle.runtime_plan.ordered_node_ids == core_projection.ordered_execution_node_ids()


def test_ir_lowering_preserves_scalar_commands_and_provider_dependency_mappings(tmp_path: Path):
    workflow_path = _write_leaf_payload_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    run_shell_step, render_prompt_step = bundle.surface.steps
    run_shell = bundle.ir.nodes[run_shell_step.step_id]
    render_prompt = bundle.ir.nodes[render_prompt_step.step_id]

    assert isinstance(run_shell.execution_config, CommandStepConfig)
    assert run_shell.execution_config.command == 'echo "hello ${context.name}"'
    materialized_command = materialize_execution_config_for_test(
        run_shell.execution_config,
        step_name="RunShell",
        step_id=run_shell_step.step_id,
    )
    assert materialized_command["command"] == 'echo "hello ${context.name}"'

    assert isinstance(render_prompt.execution_config, ProviderStepConfig)
    assert render_prompt.execution_config.depends_on["required"] == ("data.txt",)
    assert render_prompt.execution_config.depends_on["inject"] is True
    materialized_provider = materialize_execution_config_for_test(
        render_prompt.execution_config,
        step_name="RenderPrompt",
        step_id=render_prompt_step.step_id,
    )
    assert materialized_provider["depends_on"] == {
        "required": ["data.txt"],
        "inject": True,
    }


def test_unrelated_mapping_order_remains_lexical_in_executable_ir_serializer() -> None:
    config = ProviderStepConfig(
        provider="provider",
        depends_on=MappingProxyType({"required": ("data.txt",), "inject": True}),
    )

    payload = _json_value(config)

    assert list(payload["depends_on"]) == ["inject", "required"]


def test_ir_lowering_preserves_consume_prompt_metadata_and_empty_prompt_consumes(
    tmp_path: Path,
):
    workflow_path = _write_consume_prompt_ir_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    review_step = bundle.surface.steps[0]
    review_node = bundle.ir.nodes[review_step.step_id]

    assert isinstance(review_node.execution_config, ProviderStepConfig)
    materialized_provider = materialize_execution_config_for_test(
        review_node.execution_config,
        step_name="Review",
        step_id=review_step.step_id,
    )

    assert materialized_provider["prompt_consumes"] == []
    assert materialized_provider["consumes"][0]["prompt"]["mode"] == "reference"
    assert materialized_provider["consumes"][0]["prompt"]["label"] == "Baseline design"
    assert materialized_provider["consumes"][1]["prompt"]["mode"] == "content"


def test_managed_jobs_lowers_to_provider_config_and_routes(tmp_path: Path):
    workflow_path = _write_yaml(
        tmp_path / "managed_provider.yaml",
        {
            "version": "2.13",
            "name": "managed-provider-ir",
            "providers": {
                "impl": {
                    "command": ["python", "-c", "print('ok')"],
                    "input_mode": "stdin",
                }
            },
            "steps": [
                {
                    "name": "Execute",
                    "id": "execute",
                    "provider": "impl",
                    "managed_jobs": {
                        "policy": "workflows/managed_jobs/policy.yaml",
                        "watch_roots": ["scripts/training", "scripts/studies"],
                        "backend": "auto",
                        "poll_budget_sec": 60,
                        "on": {
                            "complete": "Review",
                            "failed": "Fix",
                            "invalid": "Fix",
                            "outstanding": "fail_resumable",
                        },
                    },
                },
                {"name": "Review", "id": "review", "command": ["true"]},
                {"name": "Fix", "id": "fix", "command": ["true"]},
            ],
        },
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    execute_step = bundle.surface.steps[0]
    execute_node = bundle.ir.nodes[execute_step.step_id]

    assert execute_step.managed_jobs is not None
    assert execute_step.managed_jobs.policy == "workflows/managed_jobs/policy.yaml"
    assert isinstance(execute_node.execution_config, ProviderStepConfig)
    managed_jobs = execute_node.execution_config.managed_jobs
    assert managed_jobs is not None
    assert managed_jobs.watch_roots == ("scripts/training", "scripts/studies")
    assert managed_jobs.on.complete == "Review"
    assert execute_node.routed_transfers["managed_jobs_complete_goto"].target_node_id == "root.review"
    assert execute_node.routed_transfers["managed_jobs_failed_goto"].target_node_id == "root.fix"
    assert execute_node.routed_transfers["managed_jobs_invalid_goto"].target_node_id == "root.fix"

    materialized = materialize_execution_config_for_test(
        execute_node.execution_config,
        step_name="Execute",
        step_id=execute_step.step_id,
    )
    assert materialized["managed_jobs"] == {
        "policy": "workflows/managed_jobs/policy.yaml",
        "watch_roots": ["scripts/training", "scripts/studies"],
        "backend": "auto",
        "poll_budget_sec": 60,
        "on": {
            "complete": "Review",
            "failed": "Fix",
            "invalid": "Fix",
            "outstanding": "fail_resumable",
        },
    }


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


def test_loaded_bundle_exposes_runtime_plan_with_ordered_and_nested_node_metadata(tmp_path: Path):
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_ir_workflow(tmp_path))
    for_each_bundle = WorkflowLoader(tmp_path).load_bundle(_write_for_each_call_ir_workflow(tmp_path))

    runtime_plan = bundle.runtime_plan
    ordered_node_ids = bundle.projection.ordered_execution_node_ids()

    assert runtime_plan.schema_version == "workflow_runtime_plan.v1"
    assert runtime_plan.workflow_name == bundle.surface.name
    assert runtime_plan.ordered_node_ids == ordered_node_ids
    assert set(runtime_plan.nodes) == set(bundle.ir.nodes)
    assert not hasattr(bundle, "workflow_projection")

    for execution_index, node_id in enumerate(ordered_node_ids):
        assert runtime_plan.nodes[node_id].execution_index == execution_index

    nested_repeat_until_node = runtime_plan.nodes["root.review_loop.iteration_body.run_review_loop"]
    assert nested_repeat_until_node.execution_index is None
    assert nested_repeat_until_node.call_alias == "review_loop"

    for_each_nested_node = for_each_bundle.runtime_plan.nodes[
        "root.process_items.run_review_loop_from_for_each"
    ]
    assert for_each_nested_node.execution_index is None
    assert for_each_nested_node.call_alias == "review_loop"

    cleanup_node = runtime_plan.nodes["root.finally.cleanup.write_cleanup_marker"]
    assert cleanup_node.command_boundary_kind is None
    assert cleanup_node.command_boundary_name is None


def test_loaded_bundle_exposes_semantic_ir_with_runtime_bridge(tmp_path: Path):
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_ir_workflow(tmp_path))
    semantic_workflow = bundle.semantic_ir.workflows[bundle.surface.name]

    assert bundle.semantic_ir.schema_version == "workflow_semantic_ir.v1"
    assert set(semantic_workflow.executable_bridge.node_ids) == set(bundle.ir.nodes)
    assert set(semantic_workflow.executable_bridge.presentation_keys) == {
        node.presentation_key for node in bundle.runtime_plan.nodes.values()
    }


def test_entry_publication_lowering_emits_generated_materialize_view_steps_for_published_variants_only(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        ENTRY_PUBLICATION_RUNTIME_FIXTURE,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["entry-publication-runtime"]
    step_ids = [step.step_id for step in bundle.surface.steps]

    assert any("publish" in step_id for step_id in step_ids)
    assert not any("SKIPPED" in step_id for step_id in step_ids)


def test_entry_publication_lowering_does_not_emit_boundary_publication_when_workflow_is_only_called(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        ENTRY_PUBLICATION_RUNTIME_FIXTURE,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["call-entry-publication-runtime"]
    assert not any("publish" in step.step_id for step in bundle.surface.steps)
