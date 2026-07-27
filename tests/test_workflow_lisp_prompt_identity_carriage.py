"""Target-2.22 compiler-owned prompt-attempt carrier acceptance tests."""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

import orchestrator.workflow_lisp as workflow_lisp
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.workflow.core_ast import (
    validate_core_workflow_ast,
    workflow_core_ast_to_json,
)
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow.semantic_ir import (
    validate_workflow_semantic_ir,
    workflow_semantic_ir_to_json,
)
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)


def _module_source(target_dsl: str, *, with_output: bool) -> str:
    output_role = " :out" if with_output else ""
    return f"""
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target_dsl}")
  (defmodule demo/prompt-attempt-identity)

  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)
  (defpath WorkReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defprompt review
    (:fills
      (target_doc :doc DesignDocPath)
      (message :text)
      (score :value Int)
      (report_path :path{output_role} WorkReportPath))
    -> Bool
    "Message={{message}}; score={{score}}; report={{report_path}}")

  (defworkflow run-review
    ((target_doc DesignDocPath)
     (message String)
     (score Int)
     (report_path WorkReportPath))
    -> Bool
    (provider-result providers.review
      :prompt
        (review
          :report_path report_path
          :score score
          :target_doc target_doc
          :message message))))
""".strip() + "\n"


def _slotless_module_source() -> str:
    return """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.22")
  (defmodule demo/slotless-prompt-attempt-identity)

  (defprompt review
    (:fills)
    -> Bool
    "Review the current workspace.")

  (defworkflow run-review
    ()
    -> Bool
    (provider-result providers.review
      :prompt (review))))
""".strip() + "\n"


def _compile(
    tmp_path: Path,
    *,
    target_dsl: str,
    lowering_route: str,
    with_output: bool,
):
    source_path = (
        tmp_path
        / f"prompt_attempt_{target_dsl.replace('.', '_')}_{lowering_route}.orc"
    )
    source_path.write_text(
        _module_source(target_dsl, with_output=with_output),
        encoding="utf-8",
    )
    return workflow_lisp.compile_stage3_module(
        source_path,
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )


def _compile_slotless(
    tmp_path: Path,
    *,
    lowering_route: str,
):
    source_path = tmp_path / f"slotless_prompt_attempt_{lowering_route}.orc"
    source_path.write_text(
        _slotless_module_source(),
        encoding="utf-8",
    )
    return workflow_lisp.compile_stage3_module(
        source_path,
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )


def _provider_carriers(result):
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-review"
    )
    mapping_step = lowered.authored_mapping["steps"][0]
    bundle = result.validated_bundles["run-review"]
    surface = next(
        step for step in bundle.surface.steps if step.kind.value == "provider"
    )
    core = next(
        statement
        for statement in bundle.core_workflow_ast.body
        if statement.meta.step_kind == "provider"
    )
    semantic = next(iter(bundle.semantic_ir.prompt_surfaces.values()))
    executable = next(
        node.execution_config
        for node in bundle.ir.nodes.values()
        if hasattr(node.execution_config, "provider")
    )
    typed_application = lowered.typed_workflow.typed_body.expr.prompt
    return (
        mapping_step,
        surface,
        core,
        semantic,
        executable,
        typed_application,
        bundle,
    )


def _validate_lowered_mapping(
    lowered,
    authored_mapping,
    *,
    workspace_root: Path,
):
    return validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping=authored_mapping,
            workflow_path=Path(
                lowered.typed_workflow.definition.span.start.path
            ),
            frontend_kind="workflow_lisp",
            compiler_prompt_dependency_contracts=(
                lowered.compiler_prompt_dependency_contracts
            ),
            generated_path_allocations=lowered.generated_path_allocations,
            lexical_checkpoint_points=lowered.lexical_checkpoint_points,
            private_exec_context_bindings=(
                lowered.private_exec_context_bindings
            ),
            compatibility_bridge_inputs=(
                lowered.compatibility_bridge_inputs
            ),
            private_artifact_ids=lowered.private_artifact_ids,
            compiler_owned_repeat_until_metadata=(
                lowered.compiler_owned_repeat_until_metadata
            ),
            compiler_owned_nested_if_step_ids=(
                lowered.compiler_owned_nested_if_step_ids
            ),
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=workspace_root,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
            allow_private_collection_output_schemas=True,
        ),
    )


def _replace_provider_carrier(
    bundle,
    *,
    boundary: str,
    identity_version,
    binding_plan,
):
    if boundary == "surface":
        provider_step = next(
            step
            for step in bundle.surface.steps
            if step.kind.value == "provider"
        )
        replacement = replace(
            provider_step,
            prompt_attempt_identity_version=identity_version,
            compiler_prompt_attempt_binding_plan=binding_plan,
        )
        return replace(
            bundle.surface,
            steps=tuple(
                replacement if step is provider_step else step
                for step in bundle.surface.steps
            ),
        )
    if boundary == "core":
        provider_step = next(
            statement
            for statement in bundle.core_workflow_ast.body
            if statement.meta.step_kind == "provider"
        )
        replacement = replace(
            provider_step,
            prompt_attempt_identity_version=identity_version,
            compiler_prompt_attempt_binding_plan=binding_plan,
        )
        return replace(
            bundle.core_workflow_ast,
            body=tuple(
                replacement if statement is provider_step else statement
                for statement in bundle.core_workflow_ast.body
            ),
        )
    if boundary == "semantic":
        prompt_surface_id, prompt_surface = next(
            iter(bundle.semantic_ir.prompt_surfaces.items())
        )
        replacement = replace(
            prompt_surface,
            prompt_attempt_identity_version=identity_version,
            compiler_prompt_attempt_binding_plan=binding_plan,
        )
        return replace(
            bundle.semantic_ir,
            prompt_surfaces=MappingProxyType(
                {
                    **bundle.semantic_ir.prompt_surfaces,
                    prompt_surface_id: replacement,
                }
            ),
        )
    if boundary == "executable":
        node_id, node = next(
            (node_id, node)
            for node_id, node in bundle.ir.nodes.items()
            if hasattr(node.execution_config, "provider")
        )
        replacement_config = replace(
            node.execution_config,
            prompt_attempt_identity_version=identity_version,
            compiler_prompt_attempt_binding_plan=binding_plan,
        )
        replacement_node = replace(
            node,
            execution_config=replacement_config,
        )
        return replace(
            bundle.ir,
            nodes=MappingProxyType(
                {**bundle.ir.nodes, node_id: replacement_node}
            ),
        )
    raise AssertionError(boundary)


def _validate_boundary(bundle, *, boundary: str, candidate) -> None:
    if boundary == "surface":
        return
    if boundary == "core":
        validate_core_workflow_ast(candidate, imports={})
        return
    if boundary == "semantic":
        validate_workflow_semantic_ir(
            candidate,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            surface=bundle.surface,
            imports=bundle.imports,
        )
        return
    if boundary == "executable":
        validate_executable_workflow(candidate)
        return
    raise AssertionError(boundary)


@pytest.mark.parametrize(
    "boundary",
    ("surface", "core", "semantic", "executable"),
)
@pytest.mark.parametrize(
    ("target_dsl", "mutation", "with_output"),
    (
        ("2.22", "drop_pair", True),
        ("2.20", "inject_pair", False),
        ("2.21", "inject_pair", True),
    ),
)
def test_prompt_attempt_pair_is_target_gated_at_every_ir_root(
    tmp_path: Path,
    boundary: str,
    target_dsl: str,
    mutation: str,
    with_output: bool,
) -> None:
    target_result = _compile(
        tmp_path,
        target_dsl=target_dsl,
        lowering_route="legacy",
        with_output=with_output,
    )
    target_bundle = _provider_carriers(target_result)[-1]
    if mutation == "drop_pair":
        identity_version = None
        binding_plan = None
        diagnostic = "prompt_attempt_identity_version_missing"
    else:
        q3_result = _compile(
            tmp_path,
            target_dsl="2.22",
            lowering_route="legacy",
            with_output=with_output,
        )
        q3_surface = _provider_carriers(q3_result)[1]
        identity_version = q3_surface.prompt_attempt_identity_version
        binding_plan = q3_surface.compiler_prompt_attempt_binding_plan
        diagnostic = "prompt_attempt_identity_version_invalid"

    with pytest.raises(
        (ValueError, WorkflowValidationError),
        match=diagnostic,
    ):
        candidate = _replace_provider_carrier(
            target_bundle,
            boundary=boundary,
            identity_version=identity_version,
            binding_plan=binding_plan,
        )
        _validate_boundary(
            target_bundle,
            boundary=boundary,
            candidate=candidate,
        )


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_target_2_22_slotless_fragment_seals_empty_binding_plan(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    contract_module = importlib.import_module(
        "orchestrator.workflow.prompt_fragment_contract"
    )
    result = _compile_slotless(
        tmp_path,
        lowering_route=lowering_route,
    )
    mapping_step, surface, _, _, _, _, _ = _provider_carriers(result)
    plan = surface.compiler_prompt_attempt_binding_plan
    serialized = (
        contract_module.serialize_compiler_prompt_attempt_binding_plan(plan)
    )

    assert mapping_step["compiler_prompt_attempt_binding_plan"] == plan
    assert serialized == {
        "schema_version": "compiler_prompt_attempt_binding_plan.v1",
        "rows": [],
        "plan_sha256": (
            contract_module
            .canonical_compiler_prompt_attempt_binding_plan_sha256(
                {
                    "schema_version": (
                        "compiler_prompt_attempt_binding_plan.v1"
                    ),
                    "rows": [],
                }
            )
        ),
    }
    assert (
        surface.compiler_prompt_fragment_contract.schema_version
        == "compiler_prompt_fragment_contract.v1"
    )


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
@pytest.mark.parametrize("with_output", (False, True))
def test_target_2_22_carries_closed_binding_plan_through_every_compiler_ir_boundary(
    tmp_path: Path,
    lowering_route: str,
    with_output: bool,
) -> None:
    contract_module = importlib.import_module(
        "orchestrator.workflow.prompt_fragment_contract"
    )
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route=lowering_route,
        with_output=with_output,
    )
    (
        mapping_step,
        surface,
        core,
        semantic,
        executable,
        typed_application,
        bundle,
    ) = _provider_carriers(result)

    expected_version = "workflow_prompt_attempt_identity.v1"
    expected_rows = [
        {
            "declaration_ordinal": 0,
            "slot_name": "target_doc",
            "slot_kind": "doc",
            "refinement": {
                "kind": "path",
                "must_exist_target": True,
                "name": "DesignDocPath",
                "under": "docs/design",
            },
            "output_role": "none",
            "delivery": "dependency",
            "runtime_source": {
                "kind": "required_dependency",
                "ordinal": 0,
            },
            "renderer": None,
        },
        {
            "declaration_ordinal": 1,
            "slot_name": "message",
            "slot_kind": "text",
            "refinement": None,
            "output_role": "none",
            "delivery": "template",
            "runtime_source": {
                "kind": "rendered_slot",
                "ordinal": 0,
            },
            "renderer": {
                "renderer_id": "raw-utf8-string",
                "renderer_version": 1,
            },
        },
        {
            "declaration_ordinal": 2,
            "slot_name": "score",
            "slot_kind": "value",
            "refinement": {
                "kind": "primitive",
                "name": "Int",
            },
            "output_role": "none",
            "delivery": "template",
            "runtime_source": {
                "kind": "rendered_slot",
                "ordinal": 1,
            },
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
            },
        },
        {
            "declaration_ordinal": 3,
            "slot_name": "report_path",
            "slot_kind": "path",
            "refinement": {
                "kind": "path",
                "must_exist_target": False,
                "name": "WorkReportPath",
                "under": "artifacts/work",
            },
            "output_role": (
                "required_string_file" if with_output else "none"
            ),
            "delivery": "template",
            "runtime_source": {
                "kind": "rendered_slot",
                "ordinal": 2,
            },
            "renderer": {
                "renderer_id": "posix-path-line",
                "renderer_version": 1,
            },
        },
    ]

    plan = mapping_step["compiler_prompt_attempt_binding_plan"]
    serialized = (
        contract_module.serialize_compiler_prompt_attempt_binding_plan(plan)
    )
    assert serialized == {
        "schema_version": "compiler_prompt_attempt_binding_plan.v1",
        "rows": expected_rows,
        "plan_sha256": serialized["plan_sha256"],
    }
    assert serialized["plan_sha256"].startswith("sha256:")
    assert (
        contract_module.canonical_compiler_prompt_attempt_binding_plan_sha256(
            {
                "schema_version": serialized["schema_version"],
                "rows": serialized["rows"],
            }
        )
        == serialized["plan_sha256"]
    )

    carriers = (
        mapping_step,
        surface,
        core,
        semantic,
        executable,
        typed_application,
    )
    for carrier in carriers:
        if isinstance(carrier, dict):
            assert carrier["prompt_attempt_identity_version"] == expected_version
            assert carrier["compiler_prompt_attempt_binding_plan"] == plan
        else:
            assert carrier.prompt_attempt_identity_version == expected_version
            assert carrier.compiler_prompt_attempt_binding_plan == plan

    fragment_contract = surface.compiler_prompt_fragment_contract
    assert fragment_contract.schema_version == (
        "compiler_prompt_fragment_contract.v2"
        if with_output
        else "compiler_prompt_fragment_contract.v1"
    )
    assert fragment_contract.compiled_prompt_fragment_identity.startswith(
        "sha256:"
    )
    assert typed_application.canonical_identity_projection[
        "schema_version"
    ] == (
        "compiled_prompt_fragment_identity.v2"
        if with_output
        else "compiled_prompt_fragment_identity.v1"
    )

    semantic_json = workflow_semantic_ir_to_json(bundle.semantic_ir)
    executable_json = workflow_executable_ir_to_json(bundle.ir)
    for payload in (semantic_json, executable_json):
        serialized_payload = json.dumps(payload, sort_keys=True)
        assert expected_version in serialized_payload
        assert serialized["plan_sha256"] in serialized_payload


@pytest.mark.parametrize(
    ("target_dsl", "with_output", "expects_q3"),
    (
        ("2.20", False, False),
        ("2.21", True, False),
        ("2.22", True, True),
    ),
)
def test_core_json_emits_q3_pair_only_at_target_2_22(
    tmp_path: Path,
    target_dsl: str,
    with_output: bool,
    expects_q3: bool,
) -> None:
    contract_module = importlib.import_module(
        "orchestrator.workflow.prompt_fragment_contract"
    )
    result = _compile(
        tmp_path,
        target_dsl=target_dsl,
        lowering_route="legacy",
        with_output=with_output,
    )
    _, _, core, _, _, _, bundle = _provider_carriers(result)
    core_json = workflow_core_ast_to_json(bundle.core_workflow_ast)
    provider_json = next(
        statement
        for statement in core_json["body"]
        if statement["kind"] == "provider"
    )

    if not expects_q3:
        assert "prompt_attempt_identity_version" not in provider_json
        assert "compiler_prompt_attempt_binding_plan" not in provider_json
        return
    assert (
        provider_json["prompt_attempt_identity_version"]
        == core.prompt_attempt_identity_version
        == "workflow_prompt_attempt_identity.v1"
    )
    assert provider_json["compiler_prompt_attempt_binding_plan"] == (
        contract_module.serialize_compiler_prompt_attempt_binding_plan(
            core.compiler_prompt_attempt_binding_plan
        )
    )


def test_core_json_bytes_change_or_reject_when_q3_pair_changes(
    tmp_path: Path,
) -> None:
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    _, _, core, _, _, _, bundle = _provider_carriers(result)
    original_json = workflow_core_ast_to_json(bundle.core_workflow_ast)
    plan = core.compiler_prompt_attempt_binding_plan
    rows = list(plan.rows)
    rows[2] = replace(
        rows[2],
        refinement=MappingProxyType(
            {"kind": "primitive", "name": "String"}
        ),
    )
    changed_plan = replace(
        plan,
        rows=tuple(rows),
        plan_sha256=None,
    ).with_canonical_sha256()
    changed_core = replace(
        core,
        compiler_prompt_attempt_binding_plan=changed_plan,
    )
    changed_ast = replace(
        bundle.core_workflow_ast,
        body=tuple(
            changed_core if statement is core else statement
            for statement in bundle.core_workflow_ast.body
        ),
    )

    changed_json = workflow_core_ast_to_json(changed_ast)

    assert json.dumps(
        changed_json,
        sort_keys=True,
        separators=(",", ":"),
    ) != json.dumps(
        original_json,
        sort_keys=True,
        separators=(",", ":"),
    )
    with pytest.raises(
        ValueError,
        match="prompt_attempt_identity_version_invalid",
    ):
        replace(
            core,
            prompt_attempt_identity_version=(
                "workflow_prompt_attempt_identity.v999"
            ),
        )


@pytest.mark.parametrize(
    ("target_dsl", "with_output"),
    (("2.20", False), ("2.21", False), ("2.21", True)),
)
@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_targets_below_2_22_omit_q3_pair_without_changing_q1_q2_identity(
    tmp_path: Path,
    target_dsl: str,
    with_output: bool,
    lowering_route: str,
) -> None:
    result = _compile(
        tmp_path,
        target_dsl=target_dsl,
        lowering_route=lowering_route,
        with_output=with_output,
    )
    carriers = _provider_carriers(result)[:-1]
    for carrier in carriers:
        if isinstance(carrier, dict):
            assert "prompt_attempt_identity_version" not in carrier
            assert "compiler_prompt_attempt_binding_plan" not in carrier
        else:
            assert carrier.prompt_attempt_identity_version is None
            assert carrier.compiler_prompt_attempt_binding_plan is None
    typed_application = carriers[-1]
    assert typed_application.canonical_identity_projection[
        "schema_version"
    ] == (
        "compiled_prompt_fragment_identity.v2"
        if with_output
        else "compiled_prompt_fragment_identity.v1"
    )


@pytest.mark.parametrize(
    ("baseline_target", "with_output"),
    (("2.20", False), ("2.21", True)),
)
def test_target_2_22_adds_q3_pair_without_recalculating_q1_q2_identity_bytes(
    tmp_path: Path,
    baseline_target: str,
    with_output: bool,
) -> None:
    contract_module = importlib.import_module(
        "orchestrator.workflow.prompt_fragment_contract"
    )
    baseline = _compile(
        tmp_path,
        target_dsl=baseline_target,
        lowering_route="legacy",
        with_output=with_output,
    )
    q3 = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=with_output,
    )
    baseline_surface = _provider_carriers(baseline)[1]
    q3_surface = _provider_carriers(q3)[1]

    assert (
        baseline_surface.compiled_prompt_fragment_identity
        == q3_surface.compiled_prompt_fragment_identity
    )
    assert (
        contract_module.canonical_compiler_prompt_fragment_contract_json(
            baseline_surface.compiler_prompt_fragment_contract
        )
        == contract_module.canonical_compiler_prompt_fragment_contract_json(
            q3_surface.compiler_prompt_fragment_contract
        )
    )


def test_q3_pair_fails_closed_at_surface_core_semantic_and_executable_boundaries(
    tmp_path: Path,
) -> None:
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    _, surface, core, semantic, executable, _, bundle = _provider_carriers(
        result
    )
    carriers = (surface, core, semantic, executable)

    for carrier in carriers:
        with pytest.raises(
            ValueError,
            match="prompt_attempt_identity_version_missing",
        ):
            replace(carrier, prompt_attempt_identity_version=None)
        with pytest.raises(
            ValueError,
            match="prompt_attempt_binding_plan_missing",
        ):
            replace(carrier, compiler_prompt_attempt_binding_plan=None)
        with pytest.raises(
            ValueError,
            match="prompt_attempt_identity_version_invalid",
        ):
            replace(
                carrier,
                prompt_attempt_identity_version=(
                    "workflow_prompt_attempt_identity.v999"
                ),
            )
        with pytest.raises(
            ValueError,
            match="prompt_attempt_binding_plan_invalid",
        ):
            replace(
                carrier,
                compiler_prompt_attempt_binding_plan=replace(
                    carrier.compiler_prompt_attempt_binding_plan,
                    plan_sha256="sha256:" + "0" * 64,
                ),
            )

    plan = surface.compiler_prompt_attempt_binding_plan
    changed_row = replace(plan.rows[-1], slot_name="other_report_path")
    resealed = replace(
        plan,
        rows=(*plan.rows[:-1], changed_row),
        plan_sha256=None,
    ).with_canonical_sha256()
    for carrier in carriers:
        with pytest.raises(
            ValueError,
            match="prompt_attempt_binding_plan_mismatch",
        ):
            replace(
                carrier,
                compiler_prompt_attempt_binding_plan=resealed,
            )

    q3_surface = next(iter(bundle.semantic_ir.prompt_surfaces.values()))
    prompt_surface_id = q3_surface.prompt_surface_id
    mutated_surface = replace(q3_surface)
    object.__setattr__(
        mutated_surface,
        "compiler_prompt_attempt_binding_plan",
        resealed,
    )
    mismatched_semantic = replace(
        bundle.semantic_ir,
        prompt_surfaces=MappingProxyType(
            {
                **bundle.semantic_ir.prompt_surfaces,
                prompt_surface_id: mutated_surface,
            }
        ),
    )
    with pytest.raises(
        WorkflowValidationError,
        match="prompt_attempt_binding_plan_mismatch",
    ):
        validate_workflow_semantic_ir(
            mismatched_semantic,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            surface=bundle.surface,
            imports=bundle.imports,
        )


def test_binding_plan_refinement_is_declaration_owned_not_fill_static_type(
    tmp_path: Path,
) -> None:
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    _, surface, _, _, _, _, _ = _provider_carriers(result)
    contract = surface.compiler_prompt_fragment_contract
    rendered_rows = list(contract.rendered_slots)
    path_row = rendered_rows[-1]
    rendered_rows[-1] = replace(
        path_row,
        static_type=MappingProxyType(
            {
                **path_row.static_type,
                "name": f"demo::{path_row.static_type['name']}",
            }
        ),
    )
    compatible_fill_contract = replace(
        contract,
        rendered_slots=tuple(rendered_rows),
    )

    candidate = replace(
        surface,
        compiler_prompt_fragment_contract=compatible_fill_contract,
    )

    assert (
        candidate.compiler_prompt_attempt_binding_plan
        == surface.compiler_prompt_attempt_binding_plan
    )


@pytest.mark.parametrize(
    ("removed", "diagnostic"),
    (
        (
            frozenset(
                {
                    "prompt_attempt_identity_version",
                    "compiler_prompt_attempt_binding_plan",
                }
            ),
            "prompt_attempt_identity_version_missing",
        ),
        (
            frozenset({"prompt_attempt_identity_version"}),
            "prompt_attempt_identity_version_missing",
        ),
        (
            frozenset({"compiler_prompt_attempt_binding_plan"}),
            "prompt_attempt_binding_plan_missing",
        ),
    ),
)
def test_target_2_22_shared_validation_requires_exact_q3_pair_with_step_owner(
    tmp_path: Path,
    removed: frozenset[str],
    diagnostic: str,
) -> None:
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-review"
    )
    authored_mapping = dict(lowered.authored_mapping)
    step = dict(authored_mapping["steps"][0])
    for field_name in removed:
        step.pop(field_name)
    authored_mapping["steps"] = [step]

    validation = _validate_lowered_mapping(
        lowered,
        authored_mapping,
        workspace_root=tmp_path,
    )

    assert validation.bundle is None
    assert any(
        error.message.startswith(diagnostic)
        and error.subject_refs
        and error.subject_refs[0].subject_kind == "step_id"
        for error in validation.errors
    )


@pytest.mark.parametrize(
    "mutation",
    ("value_refinement", "document_slot_name"),
)
def test_shared_validation_rejects_resealed_declaration_plan_tampering(
    tmp_path: Path,
    mutation: str,
) -> None:
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-review"
    )
    authored_mapping = dict(lowered.authored_mapping)
    step = dict(authored_mapping["steps"][0])
    plan = step["compiler_prompt_attempt_binding_plan"]
    rows = list(plan.rows)
    if mutation == "value_refinement":
        rows[2] = replace(
            rows[2],
            refinement=MappingProxyType(
                {"kind": "primitive", "name": "String"}
            ),
        )
    else:
        rows[0] = replace(rows[0], slot_name="other_document")
    step["compiler_prompt_attempt_binding_plan"] = replace(
        plan,
        rows=tuple(rows),
        plan_sha256=None,
    ).with_canonical_sha256()
    authored_mapping["steps"] = [step]

    validation = _validate_lowered_mapping(
        lowered,
        authored_mapping,
        workspace_root=tmp_path,
    )

    assert validation.bundle is None
    assert any(
        error.message.startswith("prompt_attempt_binding_plan_mismatch")
        and error.subject_refs
        and error.subject_refs[0].subject_kind == "step_id"
        and error.subject_refs[0].subject_name == step["name"]
        for error in validation.errors
    )


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    (
        ("schema", "prompt_attempt_binding_plan_invalid"),
        ("extra_row", "prompt_attempt_binding_plan_invalid"),
        ("missing_row", "prompt_attempt_binding_plan_invalid"),
        ("reordered_row", "prompt_attempt_binding_plan_invalid"),
        ("duplicate_locator", "prompt_attempt_binding_plan_invalid"),
        ("bad_renderer_version", "prompt_attempt_binding_plan_invalid"),
        ("boolean_renderer_version", "prompt_attempt_binding_plan_invalid"),
        ("document_renderer", "prompt_attempt_binding_plan_invalid"),
        ("text_refinement", "prompt_attempt_binding_plan_invalid"),
        ("wrong_refinement", "prompt_attempt_binding_plan_mismatch"),
        ("wrong_output_role", "prompt_attempt_binding_plan_mismatch"),
        ("fragment_disagreement", "prompt_attempt_binding_plan_mismatch"),
    ),
)
def test_binding_plan_rejects_malformed_and_independently_resealed_mismatch(
    tmp_path: Path,
    mutation: str,
    diagnostic: str,
) -> None:
    contract_module = importlib.import_module(
        "orchestrator.workflow.prompt_fragment_contract"
    )
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    _, surface, _, semantic, _, _, bundle = _provider_carriers(result)
    plan = surface.compiler_prompt_attempt_binding_plan
    rows = list(plan.rows)
    schema_version = plan.schema_version

    if mutation == "schema":
        schema_version = "compiler_prompt_attempt_binding_plan.v999"
    elif mutation == "extra_row":
        rows.append(replace(rows[-1], declaration_ordinal=4, slot_name="extra"))
    elif mutation == "missing_row":
        rows.pop()
    elif mutation == "reordered_row":
        rows[1], rows[2] = rows[2], rows[1]
    elif mutation == "duplicate_locator":
        rows[2] = replace(rows[2], runtime_source=rows[1].runtime_source)
    elif mutation == "bad_renderer_version":
        with pytest.raises(ValueError, match=diagnostic):
            replace(
                rows[1],
                renderer=MappingProxyType(
                    {
                        "renderer_id": "raw-utf8-string",
                        "renderer_version": 2,
                    }
                ),
            )
        return
    elif mutation == "boolean_renderer_version":
        with pytest.raises(ValueError, match=diagnostic):
            replace(
                rows[1],
                renderer=MappingProxyType(
                    {
                        "renderer_id": "raw-utf8-string",
                        "renderer_version": True,
                    }
                ),
            )
        return
    elif mutation == "document_renderer":
        with pytest.raises(ValueError, match=diagnostic):
            replace(
                rows[0],
                renderer=MappingProxyType(
                    {
                        "renderer_id": "required-document",
                        "renderer_version": 1,
                    }
                ),
            )
        return
    elif mutation == "text_refinement":
        with pytest.raises(ValueError, match=diagnostic):
            replace(
                rows[1],
                refinement=MappingProxyType(
                    {"kind": "primitive", "name": "String"}
                ),
            )
        return
    elif mutation == "wrong_refinement":
        rows[2] = replace(
            rows[2],
            refinement=MappingProxyType(
                {"kind": "primitive", "name": "String"}
            ),
        )
    elif mutation == "wrong_output_role":
        rows[-1] = replace(rows[-1], output_role="none")
    elif mutation == "fragment_disagreement":
        rows[-1] = replace(rows[-1], slot_name="renamed_report")
    else:
        raise AssertionError(mutation)

    if diagnostic.endswith("_invalid"):
        with pytest.raises(ValueError, match=diagnostic):
            contract_module.CompilerPromptAttemptBindingPlan(
                schema_version=schema_version,
                rows=tuple(rows),
                plan_sha256=(
                    "sha256:" + "f" * 64
                    if mutation == "schema"
                    else plan.plan_sha256
                ),
            )
        return

    candidate = contract_module.CompilerPromptAttemptBindingPlan(
        schema_version=schema_version,
        rows=tuple(rows),
        plan_sha256=None,
    ).with_canonical_sha256()
    if mutation == "wrong_refinement":
        prompt_surface_id = semantic.prompt_surface_id
        mutated_surface = replace(
            semantic,
            compiler_prompt_attempt_binding_plan=candidate,
        )
        mismatched_semantic = replace(
            bundle.semantic_ir,
            prompt_surfaces=MappingProxyType(
                {
                    **bundle.semantic_ir.prompt_surfaces,
                    prompt_surface_id: mutated_surface,
                }
            ),
        )
        with pytest.raises(WorkflowValidationError, match=diagnostic):
            validate_workflow_semantic_ir(
                mismatched_semantic,
                ir=bundle.ir,
                projection=bundle.projection,
                runtime_plan=bundle.runtime_plan,
                surface=bundle.surface,
                imports=bundle.imports,
            )
        return
    with pytest.raises(ValueError, match=diagnostic):
        replace(
            surface,
            compiler_prompt_attempt_binding_plan=candidate,
        )
