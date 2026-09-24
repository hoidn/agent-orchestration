"""Direct carriage checks for the future ordinary-provider context map."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
import copy
from dataclasses import replace
from types import MappingProxyType

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers.portable_context import PORTABLE_CONTEXT_V1_DESCRIPTOR
from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.executable_ir import (
    ProviderStepConfig,
    NodeResultAddress,
    WorkflowInputAddress,
    validate_executable_workflow,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5,
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.provider_context import validate_provider_context_config
from orchestrator.workflow.pure_result_replay import (
    _compiled_node_result_contract,
    _typed_node_result_addresses,
    _variant_output_declares_result_member,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.semantic_ir import (
    validate_workflow_semantic_ir,
    workflow_semantic_ir_to_json,
)
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    _WorkflowMappingValidator,
)
from orchestrator.workflow.surface_ast import (
    SurfaceFinallyBlock,
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)
from tests.test_workflow_lisp_phased_delivery_persistence import _phased_surface_bundle
from tests.test_workflow_lisp_prompt_identity_persistence import (
    _legacy_fragment_bundle,
    _q3_bundle,
)
from tests.test_workflow_lisp_trial_lowering import _build_trial


CONTEXT = {
    "input": {"ref": "inputs.history"},
    "capture": "portable",
    "result_descriptor": {
        "kind": "record",
        "name": "Answer",
        "fields": [
            {
                "name": "answer",
                "type": {"kind": "primitive", "name": "String"},
            }
        ],
    },
}


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@pytest.mark.parametrize("mutation", [
    None, "missing", "variant", "extra_field", "wrong_name", "pointer",
    "optional", "projection", "wrong_type",
])
def test_capture_model_contract_is_exactly_the_declared_root(mutation) -> None:
    from orchestrator.workflow.provider_context import validate_capture_output_contract

    config = {"capture": "portable", "result_descriptor": CONTEXT["result_descriptor"]}
    field = {
        "name": "__result__", "json_pointer": "",
        **transport_schema_for_descriptor(config["result_descriptor"], allow_nested_structures=True),
        "guidance": {"description": "Model answer"},
    }
    bundle = {"path": "answer.json", "fields": [field]}
    variant = None
    if mutation == "missing":
        bundle = None
    elif mutation == "variant":
        variant = {"path": "answer.json"}
    elif mutation == "extra_field":
        bundle["fields"].append({"name": "other", "type": "string", "json_pointer": "/other"})
    elif mutation == "wrong_name":
        field["name"] = "answer"
    elif mutation == "pointer":
        field["json_pointer"] = "/answer"
    elif mutation == "optional":
        field["required"] = False
    elif mutation == "projection":
        field["projection"] = {"projection_class": "union_workflow_boundary"}
    elif mutation == "wrong_type":
        field["fields"][0]["type"] = "integer"

    if mutation is None:
        validate_capture_output_contract(config, bundle, variant)
    else:
        with pytest.raises(ValueError, match="capture.*contract"):
            validate_capture_output_contract(config, bundle, variant)


@pytest.mark.parametrize(("version", "pointer", "example", "valid"), [
    ("2.30", "", "example", False),
    ("2.31", "", "example", True),
    ("2.31", "/nested", "example", False),
    ("2.31", "", 42, False),
])
def test_whole_root_structural_schema_and_nested_guidance_admission(
    tmp_path, version, pointer, example, valid,
) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": version}, workflow_path=tmp_path / "entry.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.31"]
    schema = transport_schema_for_descriptor(CONTEXT["result_descriptor"], allow_nested_structures=True)
    schema["fields"][0].update(description="Answer", example=example)

    validator._validate_output_bundle({"path": "answer.json", "fields": [{
        "name": "__result__", "json_pointer": pointer, **schema,
    }]}, "Ask", version)

    assert (not validator.errors) is valid, validator.errors


def _surface(*, provider_context: object = None, version: str = "2.31"):
    step = {"name": "Ask", "provider": "test-provider"}
    if provider_context is not None:
        step["provider_context"] = provider_context
        if isinstance(provider_context, Mapping) and "capture" in provider_context:
            step["output_bundle"] = {"path": "answer.json", "fields": [{
                "name": "__result__", "json_pointer": "",
                **transport_schema_for_descriptor(
                    provider_context["result_descriptor"], allow_nested_structures=True,
                ),
            }]}
    surface = elaborate_surface_workflow(
        {
            "version": version, "name": "context-carriage", "steps": [step],
            "inputs": {"history": transport_schema_for_descriptor(
                PORTABLE_CONTEXT_V1_DESCRIPTOR, allow_nested_structures=True,
            )},
        },
        workflow_path=Path("workflows/context-carriage.yaml"),
        imported_bundles={},
    )
    assert surface is not None
    return surface


def _bundle(*, provider_context: object = None, version: str = "2.31"):
    surface = _surface(provider_context=provider_context, version=version)
    return build_loaded_workflow_bundle(surface, imports={})


def _persisted_only_bundle(
    name: str,
    *,
    version: str = "2.31",
    steps: tuple[SurfaceStep, ...] = (),
    imports: dict[str, LoadedWorkflowBundle] | None = None,
    finalization: SurfaceFinallyBlock | None = None,
) -> LoadedWorkflowBundle:
    provenance = WorkflowProvenance(
        workflow_path=Path("workflows") / f"{name}.yaml",
        source_root=Path("workflows"),
    )
    surface = SurfaceWorkflow(
        version=version,
        name=name,
        steps=steps,
        provenance=provenance,
        finalization=finalization,
    )
    return LoadedWorkflowBundle(
        surface=surface,
        core_workflow_ast=None,  # type: ignore[arg-type]
        semantic_ir=None,  # type: ignore[arg-type]
        ir=None,  # type: ignore[arg-type]
        projection=None,  # type: ignore[arg-type]
        runtime_plan=None,  # type: ignore[arg-type]
        imports=MappingProxyType({} if imports is None else imports),
        provenance=provenance,
    )


def _provider(name: str = "Ask") -> SurfaceStep:
    return SurfaceStep(
        name=name,
        step_id=name.lower(),
        kind=SurfaceStepKind.PROVIDER,
        provider="test-provider",
        provider_context=CONTEXT,
    )


def test_provider_context_carries_through_shared_provider_projections() -> None:
    bundle = _bundle(provider_context=CONTEXT)
    surface_step = bundle.surface.steps[0]
    core_step = bundle.core_workflow_ast.body[0]
    node = next(iter(bundle.ir.nodes.values()))
    assert isinstance(node.execution_config, ProviderStepConfig)

    assert _plain(surface_step.provider_context) == CONTEXT
    assert _plain(core_step.provider_context) == CONTEXT
    bound_context = {**CONTEXT, "input": {"ref": WorkflowInputAddress("history")}}
    assert _plain(node.execution_config.provider_context) == bound_context
    assert dict(RuntimeStep(node=node, name="Ask", step_id="ask"))["provider_context"] == bound_context
    assert next(iter(bundle.semantic_ir.prompt_surfaces.values())).provider_context == surface_step.provider_context
    assert _plain(next(iter(bundle.runtime_plan.nodes.values())).provider_context) == bound_context

    assert workflow_core_ast_to_json(bundle.core_workflow_ast)["body"][0]["provider_context"] == CONTEXT
    semantic = workflow_semantic_ir_to_json(bundle.semantic_ir)
    assert next(iter(semantic["prompt_surfaces"].values()))["provider_context"] == CONTEXT
    executable = workflow_executable_ir_to_json(bundle.ir)
    assert next(iter(executable["nodes"].values()))["execution_config"]["provider_context"] == {
        **CONTEXT, "input": {"ref": {"input_name": "history"}}
    }


def test_absent_provider_context_is_omitted_from_in_memory_projections() -> None:
    bundle = _bundle()
    core = workflow_core_ast_to_json(bundle.core_workflow_ast)
    executable = workflow_executable_ir_to_json(bundle.ir)
    node = next(iter(bundle.ir.nodes.values()))

    assert "provider_context" not in core["body"][0]
    assert "provider_context" not in next(iter(executable["nodes"].values()))["execution_config"]
    assert "provider_context" not in dict(RuntimeStep(node=node, name="Ask", step_id="ask"))
    assert next(iter(bundle.semantic_ir.prompt_surfaces.values())).provider_context is None
    semantic = workflow_semantic_ir_to_json(bundle.semantic_ir)
    assert "provider_context" not in next(iter(semantic["prompt_surfaces"].values()))
    assert next(iter(bundle.runtime_plan.nodes.values())).provider_context is None


def test_executable_capture_rejects_a_disagreeing_model_contract() -> None:
    bundle = _bundle(provider_context=CONTEXT)
    node = next(iter(bundle.ir.nodes.values()))
    changed = replace(node, execution_config=replace(
        node.execution_config, common=replace(node.execution_config.common, output_bundle={
            "path": "answer.json", "fields": [{
                "name": "__result__", "json_pointer": "", "type": "string",
            }],
        }),
    ))
    with pytest.raises(WorkflowValidationError, match="capture output contract"):
        validate_executable_workflow(replace(bundle.ir, nodes={changed.node_id: changed}))


@pytest.mark.parametrize("ref", [
    "inputs.history", {"ref": "inputs.history"}, WorkflowInputAddress("missing"),
])
def test_executable_context_rejects_unbound_or_unknown_input(ref) -> None:
    bundle = _bundle(provider_context={"input": {"ref": "inputs.history"}})
    node = next(iter(bundle.ir.nodes.values()))
    changed = replace(node, execution_config=replace(
        node.execution_config, provider_context={"input": {"ref": ref}},
    ))

    with pytest.raises(WorkflowValidationError, match="provider context"):
        validate_executable_workflow(replace(bundle.ir, nodes={changed.node_id: changed}))


@pytest.mark.parametrize("mutation", ["missing_surface", "semantic_ref", "executable_ref"])
def test_context_coherence_requires_independent_source_authority(mutation) -> None:
    bundle = _bundle(provider_context={"input": {"ref": "inputs.history"}})
    surface, semantic, executable = bundle.surface, bundle.semantic_ir, bundle.ir
    if mutation == "missing_surface":
        surface = None
    elif mutation == "semantic_ref":
        key, prompt = next(iter(semantic.prompt_surfaces.items()))
        semantic = replace(semantic, prompt_surfaces={key: replace(
            prompt, provider_context={"input": {"ref": "inputs.other"}},
        )})
    else:
        key, node = next(iter(executable.nodes.items()))
        executable = replace(executable, nodes={key: replace(
            node, execution_config=replace(node.execution_config, provider_context={
                "input": {"ref": WorkflowInputAddress("other")},
            }),
        )})

    with pytest.raises(WorkflowValidationError, match="provider context"):
        validate_workflow_semantic_ir(
            semantic, ir=executable, projection=bundle.projection,
            runtime_plan=bundle.runtime_plan, surface=surface, imports={},
        )


def test_context_catalog_preserves_recursive_schema_and_capture_ownership(tmp_path) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.31"}, workflow_path=tmp_path / "entry.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    # Exercise the selected internal contract without admitting the public target.
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.31"]
    context_schema = transport_schema_for_descriptor(
        PORTABLE_CONTEXT_V1_DESCRIPTOR, allow_nested_structures=True,
    )
    outputs = validator._build_scope_artifact_catalog([
        {"name": "Prepared", "output_bundle": {"fields": [
            {"name": "history", **context_schema},
        ]}},
        {"name": "Captured", "provider": "configured-codex",
         "provider_context": {
             "capture": "portable", "result_descriptor": CONTEXT["result_descriptor"],
         },
         "output_bundle": {"fields": [{"name": "answer", "type": "string"}]}},
    ])

    for key, value in context_schema.items():
        assert outputs["Prepared"]["history"][key] == value
    assert set(outputs["Captured"]) == {"result", "context"}
    for key, value in context_schema.items():
        assert outputs["Captured"]["context"][key] == value
    assert outputs["Captured"]["result"]["record_name"] == "Answer"


@pytest.mark.parametrize("proven", [False, True])
def test_context_input_requires_proof_for_a_variant_specific_history(tmp_path, proven) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.31"}, workflow_path=tmp_path / "entry.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.31"]
    projection = {
        "projection_class": "union_workflow_boundary", "return_kind": "union",
        "union_output_group": "history", "discriminant_output": "tag",
    }
    producer = {"name": "Prepared", "materialize_artifacts": {"values": [
        {"name": "tag", "source": {"literal": "READY"}, "contract": {
            "type": "enum", "allowed": ["READY", "OTHER"],
            "projection": {**projection, "field_role": "discriminant", "active_variants": ["READY", "OTHER"]},
        }},
        {"name": "history", "source": {"literal": {
            "schema": "portable-context.v1", "events": [], "coverage": [], "lineage": [],
        }}, "contract": {
            **transport_schema_for_descriptor(PORTABLE_CONTEXT_V1_DESCRIPTOR, allow_nested_structures=True),
            "projection": {**projection, "field_role": "variant", "active_variants": ["READY"]},
        }},
    ]}}
    consumer = {"name": "Ask", "provider": "codex", "provider_context": {
        "input": {"ref": "root.steps.Prepared.artifacts.history"},
    }}
    if proven:
        consumer["requires_variant"] = {"ref": "root.steps.Prepared.artifacts.tag", "allowed": ["READY"]}
    validator._validate_steps([producer, consumer], "2.31")

    assert bool(validator.errors) is not proven, validator.errors


def test_context_workflow_input_reference_keeps_complete_schema(tmp_path) -> None:
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.31"}, workflow_path=tmp_path / "entry.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.31"]
    schema = transport_schema_for_descriptor(
        PORTABLE_CONTEXT_V1_DESCRIPTOR, allow_nested_structures=True,
    )
    validator._workflow_input_specs = {"history": schema}

    resolved = validator._resolve_structured_ref_contract(
        "inputs.history", "Ask", "2.31", {}, {}, set(), None, None, set(), None,
    )

    assert resolved is not None
    for key, value in schema.items():
        assert resolved[key] == value


@pytest.mark.parametrize("mutation", [None, "nested_type", "unknown_input", "session"])
def test_shared_context_input_validation_uses_complete_contract(tmp_path, mutation) -> None:
    schema = transport_schema_for_descriptor(
        PORTABLE_CONTEXT_V1_DESCRIPTOR, allow_nested_structures=True,
    )
    if mutation == "nested_type":
        schema["fields"][1]["items"]["variants"]["TASK"]["fields"][-1]["type"] = "integer"
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping={"version": "2.31", "inputs": {"history": schema}},
            workflow_path=tmp_path / "entry.orc",
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE,
        ),
    )
    validator.VERSION_ORDER = [*validator.VERSION_ORDER, "2.31"]
    step = {
        "name": "Ask", "provider": "configured-codex",
        "provider_context": {"input": {"ref": (
            "inputs.missing" if mutation == "unknown_input" else "inputs.history"
        )}},
    }
    if mutation == "session":
        step["provider_session"] = {"mode": "fresh", "publish_artifact": "session"}

    validator._validate_steps([step], "2.31")

    context_errors = [error for error in validator.errors if "provider context" in str(error)]
    assert bool(context_errors) is (mutation is not None), validator.errors


def test_capture_contracts_and_context_dependency_use_the_same_producer() -> None:
    result_descriptor = {
        "kind": "union", "name": "Answer",
        "variants": [{"name": "OK", "fields": []}],
    }
    surface = elaborate_surface_workflow(
        {"version": "2.31", "name": "handoff", "steps": [
            {"name": "Capture", "provider": "configured-codex", "provider_context": {
                "capture": "portable", "result_descriptor": result_descriptor,
            }, "output_bundle": {
                "path": "answer.json", "fields": [{
                    "name": "__result__", "json_pointer": "",
                    **transport_schema_for_descriptor(result_descriptor, allow_nested_structures=True),
                }],
            }},
            {"name": "Continue", "provider": "configured-codex", "provider_context": {
                "input": {"ref": "root.steps.Capture.artifacts.context"},
            }},
        ]},
        workflow_path=Path("workflows/handoff.orc"), imported_bundles={},
    )
    bundle = build_loaded_workflow_bundle(surface, imports={})
    capture, consumer = tuple(bundle.ir.nodes.values())
    context_address = NodeResultAddress(capture.node_id, "artifacts", "context")

    assert consumer.execution_config.provider_context["input"]["ref"] == context_address
    assert context_address in _typed_node_result_addresses(consumer)
    assert _compiled_node_result_contract(bundle, context_address)["record_name"] == "Context"
    assert _compiled_node_result_contract(
        bundle, NodeResultAddress(capture.node_id, "artifacts", "result"),
    )["union_name"] == "Answer"
    old_tag = NodeResultAddress(capture.node_id, "artifacts", "variant")
    assert _compiled_node_result_contract(bundle, old_tag) is None
    assert not _variant_output_declares_result_member(bundle, old_tag)


def test_provider_context_is_not_a_common_or_non_provider_carrier() -> None:
    with pytest.raises(ValueError, match="provider_context requires an ordinary provider step"):
        SurfaceStep(
            name="Command",
            step_id="command",
            kind=SurfaceStepKind.COMMAND,
            provider_context=CONTEXT,
        )


@pytest.mark.parametrize(
    "expected_context",
    (
        {"input": {"ref": "inputs.history"}},
        {"capture": "portable", "result_descriptor": CONTEXT["result_descriptor"]},
        CONTEXT,
    ),
)
def test_provider_context_closed_config_accepts_the_three_approved_shapes(expected_context) -> None:
    assert validate_provider_context_config(
        expected_context,
        step_kind="provider",
        target_dsl_version="2.31",
    ) == expected_context


@pytest.mark.parametrize(
    "expected_context",
    (
        {"input": {"ref": "inputs.history"}},
        {"capture": "portable", "result_descriptor": CONTEXT["result_descriptor"]},
        CONTEXT,
    ),
)
def test_provider_context_v5_round_trip_deep_freezes_and_preserves_legacy_absence(expected_context) -> None:
    wire = serialize_persisted_workflow_surface_graph(
        _bundle(provider_context=expected_context)
    )
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )
    context = decoded.entry_node.steps[0].provider_context

    assert wire["schema_version"] == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    assert _plain(context) == expected_context
    assert context is not None
    if "input" in context:
        with pytest.raises(TypeError):
            context["input"]["ref"] = "inputs.other"  # type: ignore[index]

    absent_wire = serialize_persisted_workflow_surface_graph(_bundle(version="2.30"))
    assert absent_wire["schema_version"] == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA


@pytest.mark.parametrize("placement", ("nested", "finalization"))
def test_provider_context_selects_v5_in_nested_and_finalization_steps(placement) -> None:
    provider = _provider()
    if placement == "nested":
        bundle = _persisted_only_bundle(
            "nested-context",
            steps=(
                SurfaceStep(
                    name="Loop",
                    step_id="loop",
                    kind=SurfaceStepKind.FOR_EACH,
                    for_each_steps=(provider,),
                ),
            ),
        )
    else:
        bundle = _persisted_only_bundle(
            "final-context",
            finalization=SurfaceFinallyBlock(
                token="finally",
                step_id="finally",
                steps=(provider,),
            ),
        )

    wire = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )
    assert wire["schema_version"] == (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    )
    if placement == "nested":
        assert decoded.entry_node.steps[0].for_each_steps[0].provider_context is not None
    else:
        assert decoded.entry_node.finalization_steps[0].provider_context is not None


def test_provider_context_selects_v5_only_for_reachable_imports() -> None:
    child = _persisted_only_bundle("child", steps=(_provider(),))
    root = _persisted_only_bundle(
        "root",
        steps=(
            SurfaceStep(
                name="Call",
                step_id="call",
                kind=SurfaceStepKind.CALL,
                call_alias="child",
            ),
        ),
        imports={"child": child},
    )
    unused = _persisted_only_bundle("unused", steps=(_provider(),))
    root_with_unused = _persisted_only_bundle("root", imports={"unused": unused})

    wire = serialize_persisted_workflow_surface_graph(root)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )
    assert wire["schema_version"] == (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    )
    assert decoded.nodes["child"].steps[0].provider_context is not None
    assert serialize_persisted_workflow_surface_graph(root_with_unused)["schema_version"] == (
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
    )


def test_provider_context_rejects_schema_context_mismatch() -> None:
    context_wire = serialize_persisted_workflow_surface_graph(
        _bundle(provider_context=CONTEXT)
    )
    old_schema = copy.deepcopy(context_wire)
    old_schema["schema_version"] = PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
    with pytest.raises(ValueError):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(old_schema)
        )

    absent_wire = serialize_persisted_workflow_surface_graph(_bundle(version="2.30"))
    v5_without_context = copy.deepcopy(absent_wire)
    v5_without_context["schema_version"] = PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    with pytest.raises(ValueError, match="provider context carriage"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(v5_without_context)
        )


def test_provider_context_v5_preserves_q3_legacy_fragment_carriage(tmp_path: Path) -> None:
    bundle = _q3_bundle(tmp_path)
    provider = next(
        step for step in bundle.surface.steps if step.kind is SurfaceStepKind.PROVIDER
    )
    surface = replace(
        bundle.surface,
        version="2.31",
        steps=(replace(provider, provider_context=CONTEXT),),
    )
    wire = serialize_persisted_workflow_surface_graph(
        replace(bundle, surface=surface)
    )
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    assert decoded.entry_node.steps[0].compiler_prompt_fragment_contract is not None


def test_provider_context_v5_mixed_graph_preserves_q2_q3_q5_and_trial(tmp_path: Path) -> None:
    q2 = _legacy_fragment_bundle(
        tmp_path / "q2",
        target_dsl="2.21",
        with_output=True,
        name="q2",
    )
    q3_bundle = _q3_bundle(tmp_path / "q3")
    q3 = replace(q3_bundle, surface=replace(q3_bundle.surface, name="q3"))
    q5_bundle = _phased_surface_bundle(tmp_path / "q5")
    q5 = replace(q5_bundle, surface=replace(q5_bundle.surface, name="q5"))
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    _source, trial_result = _build_trial(trial_dir)
    trial_bundle = trial_result.validated_bundle
    trial = replace(trial_bundle, surface=replace(trial_bundle.surface, name="trial"))
    imports = {"q2": q2, "q3": q3, "q5": q5, "trial": trial}
    root = _persisted_only_bundle(
        "mixed",
        steps=(
            _provider("Context"),
            *(
                SurfaceStep(
                    name=alias,
                    step_id=alias,
                    kind=SurfaceStepKind.CALL,
                    call_alias=alias,
                )
                for alias in imports
            ),
        ),
        imports=imports,
    )

    wire = serialize_persisted_workflow_surface_graph(root)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(wire)
    )

    assert wire["schema_version"] == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V5
    assert decoded.nodes["q2"].steps[0].compiler_prompt_fragment_contract is not None
    assert decoded.nodes["q3"].steps[0].prompt_attempt_identity_version is not None
    assert decoded.nodes["q5"].steps[0].provider_call_policy is not None
    assert decoded.nodes["trial"].steps[0].trial is not None


@pytest.mark.parametrize(
    "mutate",
    (
        lambda step, node: step["provider_context"].update(input=None),
        lambda step, node: step["provider_context"].update(capture="invalid"),
        lambda step, node: step["provider_context"].pop("result_descriptor"),
        lambda step, node: step["provider_context"].update(
            result_descriptor={"kind": "invalid"}
        ),
        lambda step, node: step.update(kind="command"),
        lambda step, node: node.update(version="2.30"),
    ),
)
def test_provider_context_v5_decoder_rejects_forged_invalid_maps(mutate) -> None:
    wire = serialize_persisted_workflow_surface_graph(_bundle(provider_context=CONTEXT))
    forged = copy.deepcopy(wire)
    node = forged["nodes"]["context-carriage"]
    step = node["steps"][0]
    mutate(step, node)

    with pytest.raises(ValueError):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(forged)
        )


@pytest.mark.parametrize(
    ("context", "version", "policy"),
    (
        ({}, "2.31", None),
        (CONTEXT, "2.30", None),
        (CONTEXT, "2.31", {"delivery": "phased", "materialization_attempts": 1}),
    ),
)
def test_provider_context_persistence_rejects_invalid_admission(context, version, policy) -> None:
    with pytest.raises(ValueError):
        serialize_persisted_workflow_surface_graph(
            _persisted_only_bundle(
                "invalid-context", version=version,
                steps=(SurfaceStep(
                    name="Ask", step_id="ask", kind=SurfaceStepKind.PROVIDER,
                    provider="test-provider", provider_context=context,
                    provider_call_policy=policy,
                ),),
            )
        )


@pytest.mark.parametrize(
    "context",
    (
        {},
        {"input": None},
        {"input": {"ref": 1}},
        {"capture": "portable"},
        {"result_descriptor": CONTEXT["result_descriptor"]},
        {"capture": "portable", "result_descriptor": None},
        {"input": {"ref": "inputs.history"}, "unknown": True},
    ),
)
def test_provider_context_closed_config_rejects_malformed_shapes(context) -> None:
    with pytest.raises(ValueError):
        validate_provider_context_config(
            context,
            step_kind="provider",
            target_dsl_version="2.31",
        )
