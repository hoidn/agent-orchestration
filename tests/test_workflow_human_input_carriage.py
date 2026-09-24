"""Direct shared-carriage checks for the future request-input leaf."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from dataclasses import replace

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.executable_ir import NodeResultAddress, WorkflowInputAddress
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.pure_result_replay import _compiled_node_result_contract
from orchestrator.workflow.pure_result_replay import _durable_node_result_value, _DURABLE_VALUE_MISSING
from orchestrator.workflow.pure_result_replay import _typed_node_result_addresses
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.semantic_ir import validate_workflow_semantic_ir
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    _WorkflowMappingValidator,
)


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _bundle(question: object):
    surface = elaborate_surface_workflow(
        {
            "version": "2.32",
            "name": "human-input-carriage",
            "inputs": {"question": {"type": "string"}},
            "steps": [{"name": "Ask", "request_input": {"question": question}}],
        },
        workflow_path=Path("workflows/human-input-carriage.orc"),
        imported_bundles={},
    )
    assert surface is not None
    return build_loaded_workflow_bundle(surface, imports={})


@pytest.mark.parametrize(
    ("question", "expected"),
    (
        ({"literal": "Continue?"}, {"literal": "Continue?"}),
        ({"ref": "inputs.question"}, {"ref": WorkflowInputAddress("question")}),
    ),
)
def test_request_input_carries_closed_question_through_shared_views(question, expected) -> None:
    bundle = _bundle(question)
    surface_step = bundle.surface.steps[0]
    core_step = bundle.core_workflow_ast.body[0]
    node = next(iter(bundle.ir.nodes.values()))

    assert surface_step.kind.value == "request_input"
    assert _plain(surface_step.request_input) == {"question": question}
    assert type(core_step).__name__ == "CoreRequestInputStep"
    assert _plain(core_step.request_input) == {"question": question}
    assert type(node.execution_config).__name__ == "RequestInputStepConfig"
    assert _plain(node.execution_config.request_input) == {"question": expected}
    assert dict(RuntimeStep(node=node, name="Ask", step_id="ask"))["request_input"] == {
        "question": expected,
    }
    assert _plain(next(iter(bundle.runtime_plan.nodes.values())).request_input) == {
        "question": expected,
    }


@pytest.mark.parametrize(
    "question",
    (
        {},
        {"literal": "question", "ref": "inputs.question"},
        {"literal": 7},
        {"ref": "inputs.missing"},
        {"ref": "root.steps.Missing.artifacts.value"},
    ),
)
def test_request_input_validation_rejects_non_closed_or_unavailable_question(tmp_path, question) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.32", "inputs": {"question": {"type": "string"}}},
            workflow_path=tmp_path / "human-input.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.32"]
    validator._validate_steps(
        [{"name": "Ask", "request_input": {"question": question}}], "2.32",
    )

    assert any("request input" in str(error).lower() for error in validator.errors)


def test_request_input_has_the_fixed_human_reply_contract_without_a_bundle() -> None:
    bundle = _bundle({"literal": "Continue?"})
    node = next(iter(bundle.ir.nodes.values()))

    variant = _compiled_node_result_contract(
        bundle, NodeResultAddress(node.node_id, "artifacts", "variant"),
    )
    text = _compiled_node_result_contract(
        bundle, NodeResultAddress(node.node_id, "artifacts", "text"),
    )
    assert variant == {
        "type": "enum",
        "allowed": ["ANSWERED", "CANCELLED"],
        "projection": {
            "projection_class": "union_workflow_boundary",
            "return_kind": "union",
            "union_output_group": "human_reply",
            "discriminant_output": "variant",
            "field_role": "discriminant",
            "active_variants": ["ANSWERED", "CANCELLED"],
        },
    }
    assert text == {
        "type": "string",
        "projection": {
            "projection_class": "union_workflow_boundary",
            "return_kind": "union",
            "union_output_group": "human_reply",
            "discriminant_output": "variant",
            "field_role": "variant",
            "active_variants": ["ANSWERED"],
        },
    }


def test_request_input_text_is_a_typed_dependency_for_a_later_question() -> None:
    surface = elaborate_surface_workflow(
        {
            "version": "2.32",
            "name": "human-input-dependency",
            "steps": [
                {"name": "First", "request_input": {"question": {"literal": "First?"}}},
                {
                    "name": "Second",
                    "requires_variant": {"step": "First", "value": "ANSWERED"},
                    "request_input": {
                        "question": {"ref": "root.steps.First.artifacts.text"},
                    },
                },
            ],
        },
        workflow_path=Path("workflows/human-input-dependency.orc"),
        imported_bundles={},
    )
    assert surface is not None
    bundle = build_loaded_workflow_bundle(surface, imports={})
    first, second = tuple(bundle.ir.nodes.values())
    address = NodeResultAddress(first.node_id, "artifacts", "text")

    assert second.execution_config.request_input["question"]["ref"] == address
    assert address in _typed_node_result_addresses(second)
    assert _compiled_node_result_contract(bundle, address)["type"] == "string"


@pytest.mark.parametrize("proven", [False, True])
def test_question_ref_requires_the_active_human_reply_variant(tmp_path, proven) -> None:
    steps = [
        {"name": "First", "request_input": {"question": {"literal": "First?"}}},
        {"name": "Second", "request_input": {
            "question": {"ref": "root.steps.First.artifacts.text"},
        }},
    ]
    if proven:
        steps[1]["requires_variant"] = {"step": "First", "value": "ANSWERED"}
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.32"}, workflow_path=tmp_path / "reply.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.32"]
    validator._validate_steps(steps, "2.32")
    assert bool(validator.errors) is not proven


@pytest.mark.parametrize("artifacts,member,expected", [
    ({"variant": "CANCELLED", "text": "inactive"}, "text", _DURABLE_VALUE_MISSING),
    ({"variant": "ANSWERED"}, "variant", _DURABLE_VALUE_MISSING),
    ({"variant": "UNKNOWN"}, "variant", _DURABLE_VALUE_MISSING),
    ({"variant": "CANCELLED"}, "variant", "CANCELLED"),
    ({"variant": "ANSWERED", "text": ""}, "text", ""),
])
def test_durable_human_reply_retrieval_validates_the_complete_reply(artifacts, member, expected) -> None:
    bundle = _bundle({"literal": "Continue?"})
    node = next(iter(bundle.ir.nodes.values()))
    value, _ = _durable_node_result_value(
        bundle, NodeResultAddress(node.node_id, "artifacts", member),
        {"artifacts": artifacts},
    )
    assert value == expected


def test_source_request_input_rejects_an_otherwise_valid_output_bundle(tmp_path) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.32"}, workflow_path=tmp_path / "reply.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.32"]
    validator._validate_steps([{
        "name": "Ask", "request_input": {"question": {"literal": "Question?"}},
        "output_bundle": {"path": "reply.json", "fields": [{
            "name": "other", "json_pointer": "/other", "type": "string",
        }]},
    }], "2.32")
    assert len(validator.errors) == 1
    assert "fixed reply" in str(validator.errors[0])


@pytest.mark.parametrize("field", ["output_bundle", "variant_output"])
def test_request_input_cannot_replace_its_fixed_reply_contract(field) -> None:
    from orchestrator.workflow.executable_ir import validate_executable_workflow

    bundle = _bundle({"literal": "Continue?"})
    node = next(iter(bundle.ir.nodes.values()))
    changed_config = replace(node.execution_config, common=replace(node.execution_config.common, **{field: {}}))
    changed_ir = replace(bundle.ir, nodes={node.node_id: replace(node, execution_config=changed_config)})
    with pytest.raises(WorkflowValidationError, match="request input"):
        validate_executable_workflow(changed_ir)


def test_request_input_remains_target_gated_before_public_232_admission(tmp_path) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.31"},
            workflow_path=tmp_path / "human-input-old-target.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator._validate_steps(
        [{"name": "Ask", "request_input": {"question": {"literal": "Continue?"}}}],
        "2.31",
    )

    assert any("request input requires target dsl 2.32" in str(error).lower() for error in validator.errors)


def test_request_input_is_not_a_common_or_non_request_carrier() -> None:
    with pytest.raises(ValueError, match="request_input requires a request input step"):
        SurfaceStep(
            name="Command",
            step_id="command",
            kind=SurfaceStepKind.COMMAND,
            request_input={"question": {"literal": "Continue?"}},
        )


def test_request_input_semantic_check_rejects_a_source_executable_mismatch() -> None:
    bundle = _bundle({"literal": "Continue?"})
    node = next(iter(bundle.ir.nodes.values()))
    changed = replace(
        node,
        execution_config=replace(
            node.execution_config,
            request_input={"question": {"literal": "Different?"}},
        ),
    )
    changed_ir = replace(bundle.ir, nodes={changed.node_id: changed})

    with pytest.raises(WorkflowValidationError, match="request input source/executable mismatch"):
        validate_workflow_semantic_ir(
            bundle.semantic_ir,
            ir=changed_ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            surface=bundle.surface,
            imports={},
        )


def test_request_input_selects_closed_v6_persisted_carriage() -> None:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows/human-input-persisted.orc"),
        source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="2.32",
        name="human-input-persisted",
        steps=(
            SurfaceStep(
                name="Ask",
                step_id="ask",
                kind=SurfaceStepKind.REQUEST_INPUT,
                request_input={"question": {"literal": "Continue?"}},
            ),
        ),
        provenance=provenance,
    )
    bundle = LoadedWorkflowBundle(
        surface=surface,
        core_workflow_ast=None,  # type: ignore[arg-type]
        semantic_ir=None,  # type: ignore[arg-type]
        ir=None,  # type: ignore[arg-type]
        projection=None,  # type: ignore[arg-type]
        runtime_plan=None,  # type: ignore[arg-type]
        imports={},
        provenance=provenance,
    )

    wire = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == "persisted_workflow_surface_graph.v6"
    assert wire["nodes"]["human-input-persisted"]["steps"][0]["request_input"] == {
        "question": {"literal": "Continue?"},
    }
    assert _plain(decoded.entry_node.steps[0].request_input) == {
        "question": {"literal": "Continue?"},
    }


def test_request_input_v6_retains_existing_provider_context_carriage() -> None:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows/human-input-mixed.orc"), source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="2.32",
        name="human-input-mixed",
        steps=(
            SurfaceStep(
                name="Ask", step_id="ask", kind=SurfaceStepKind.REQUEST_INPUT,
                request_input={"question": {"literal": "Continue?"}},
            ),
            SurfaceStep(
                name="Context", step_id="context", kind=SurfaceStepKind.PROVIDER,
                provider="configured-codex",
                provider_context={"input": {"ref": "inputs.history"}},
            ),
        ),
        provenance=provenance,
    )
    bundle = LoadedWorkflowBundle(
        surface=surface, core_workflow_ast=None, semantic_ir=None, ir=None,
        projection=None, runtime_plan=None, imports={}, provenance=provenance,
    )  # type: ignore[arg-type]

    wire = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == "persisted_workflow_surface_graph.v6"
    assert _plain(decoded.entry_node.steps[1].provider_context) == {
        "input": {"ref": "inputs.history"},
    }


@pytest.mark.parametrize("mutation", ("missing_map", "wrong_kind", "wrong_schema", "null_map", "output_bundle", "variant_output"))
def test_request_input_v6_decoder_requires_the_exact_kind_map_and_schema(mutation) -> None:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows/human-input-forged.orc"), source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version="2.32",
        name="human-input-forged",
        steps=(SurfaceStep(
            name="Ask", step_id="ask", kind=SurfaceStepKind.REQUEST_INPUT,
            request_input={"question": {"literal": "Continue?"}},
        ),),
        provenance=provenance,
    )
    bundle = LoadedWorkflowBundle(
        surface=surface, core_workflow_ast=None, semantic_ir=None, ir=None,
        projection=None, runtime_plan=None, imports={}, provenance=provenance,
    )  # type: ignore[arg-type]
    wire = serialize_persisted_workflow_surface_graph(bundle)
    step = wire["nodes"]["human-input-forged"]["steps"][0]
    if mutation == "missing_map":
        step.pop("request_input")
    elif mutation == "wrong_kind":
        step["kind"] = "command"
    elif mutation == "null_map":
        step["request_input"] = None
    elif mutation in {"output_bundle", "variant_output"}:
        step["common"][mutation] = {}
    else:
        wire["schema_version"] = "persisted_workflow_surface_graph.v5"

    with pytest.raises(ValueError, match="request_input_persistence_mismatch"):
        decode_persisted_workflow_surface_graph(canonical_persisted_surface_bytes(wire))
