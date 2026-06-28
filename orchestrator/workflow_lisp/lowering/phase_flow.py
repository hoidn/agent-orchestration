"""Phase-flow owner surface for stdlib lowering."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_managed_write_root_inputs
from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole
from orchestrator.workflow.surface_ast import SurfaceStep

from ..contracts import derive_reusable_state_contract_metadata, derive_structured_result_contract, derive_workflow_boundary_fields
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    WithPhaseExpr,
)
from ..phase import IMPLEMENTATION_ATTEMPT_PHASE_NAME, PHASE_TARGET_SPECS, PhaseScope
from ..procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from ..procedures import ProcedureCatalog
from ..spans import SourceSpan
from ..type_env import PathTypeRef, PrimitiveTypeRef, ProcRefTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from ..workflow_refs import ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name, workflow_ref_target_name
from ..workflows import CertifiedAdapterBinding, PromptExtern, ProviderExtern, analyze_workflow_boundary_type
from . import core as lowering_core
from .context import (
    _ActivePhaseScope,
    _copy_context_with_phase_scope,
    _copy_context_with_step_prefix,
    _LoweringContext,
    _TerminalResult,
)
from .effects import _lower_provider_result
from .generated_paths import allocate_generated_result_bundle
from .origins import LoweringOrigin, _rekey_origin_map
from .phase_scope import (
    _build_phase_stdlib_prompt_input_prelude,
    _build_typed_prompt_inputs_for_prompt_specs,
    _managed_write_root_bindings,
    _managed_write_root_requirements_for_callable,
    _phase_prompt_artifact_name_for_target,
    _typed_prompt_input_row_metadata,
    _require_phase_scope_name_match,
    _surface_contract_from_structured_field,
    _union_output_contracts,
)
from .values import _render_existing_output_ref, _resolve_inline_expr_value


def _compile_error(*args, **kwargs):
    return lowering_core._compile_error(*args, **kwargs)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _record_step_origin(*args, **kwargs):
    return lowering_core._record_step_origin(*args, **kwargs)


def _origin_from_context_source(*args, **kwargs):
    return lowering_core._origin_from_context_source(*args, **kwargs)


def _record_output_refs(*args, **kwargs):
    return lowering_core._record_output_refs(*args, **kwargs)


def _record_missing_step_origins(*args, **kwargs):
    return lowering_core._record_missing_step_origins(*args, **kwargs)


def _materialize_values_step(*args, **kwargs):
    return lowering_core._materialize_values_step(*args, **kwargs)


def _conditional_case_ref(*args, **kwargs):
    return lowering_core._conditional_case_ref(*args, **kwargs)


def _render_boolean_predicate(*args, **kwargs):
    return lowering_core._render_boolean_predicate(*args, **kwargs)


def _template_for_ref(ref: str) -> str:
    if ref.startswith("${"):
        return ref
    return "${" + ref + "}"


def _lower_expression(*args, **kwargs):
    context = kwargs.get("context")
    lowerer = getattr(context, "wcc_effect_lowerer", None)
    if callable(lowerer):
        return lowerer(*args, **kwargs)
    return lowering_core._lower_expression(*args, **kwargs)


def _lower_call_expr(*args, **kwargs):
    return lowering_core._lower_call_expr(*args, **kwargs)


def _render_call_binding_ref(*args, **kwargs):
    return lowering_core._render_call_binding_ref(*args, **kwargs)


def _render_record_call_bindings(*args, **kwargs):
    return lowering_core._render_record_call_bindings(*args, **kwargs)


def _flatten_boundary_leaf_paths(*args, **kwargs):
    return lowering_core._flatten_boundary_leaf_paths(*args, **kwargs)


def _record_expr_value_at_path(*args, **kwargs):
    return lowering_core._record_expr_value_at_path(*args, **kwargs)


def _normalize_union_field_path(*args, **kwargs):
    return lowering_core._normalize_union_field_path(*args, **kwargs)


def _union_variant_expr_value_at_path(*args, **kwargs):
    return lowering_core._union_variant_expr_value_at_path(*args, **kwargs)


def _phase_target_inline_ref(*args, **kwargs):
    return lowering_core._phase_target_inline_ref(*args, **kwargs)


def _join_ref_path(*args, **kwargs):
    return lowering_core._join_ref_path(*args, **kwargs)


def _resolve_nested_local_value(*args, **kwargs):
    return lowering_core._resolve_nested_local_value(*args, **kwargs)




def _lower_run_provider_phase(*args, **kwargs):
    return _phase_stdlib_lower_run_provider_phase_impl(*args, **kwargs)

def _lower_produce_one_of(*args, **kwargs):
    return _phase_stdlib_lower_produce_one_of_impl(*args, **kwargs)

def _lower_resume_or_start(*args, **kwargs):
    return _phase_stdlib_lower_resume_or_start_impl(*args, **kwargs)

def _provider_metadata_names(expr: Any, *, local_values: Mapping[str, Any]) -> set[str]:
    """Collect provider/prompt name expressions reachable from a metadata value."""

    resolved = _resolve_inline_expr_value(expr, local_values=local_values)
    names: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, NameExpr):
            names.add(value.name)
            return
        if isinstance(value, RecordExpr):
            for _, field_value in value.fields:
                walk(field_value)
            return
        if isinstance(value, Mapping):
            for field_value in value.values():
                walk(field_value)
            return
        if isinstance(value, tuple):
            for item in value:
                walk(item)

    walk(resolved if resolved is not None else expr)
    return names


def _build_match_projection_anchor_step(
    *,
    match_step_name: str,
    variant_name: str,
    case_outputs: Mapping[str, Any],
    context: _LoweringContext,
    span: SourceSpan,
) -> dict[str, Any]:
    """Build a small step that gives a match branch stable output refs."""

    anchor_ref = _first_case_output_ref(case_outputs)
    if anchor_ref is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="match return arms must expose at least one exportable field in this Stage 3 slice",
            span=span,
            form_path=context.signature.form_path,
        )
    step_name = f"{match_step_name}__{variant_name.lower()}__projection_anchor"
    step_id = _normalize_generated_step_id(step_name)
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=LoweringOrigin(span=span, form_path=context.signature.form_path),
    )
    return {
        "name": step_name,
        "id": step_id,
        "assert": {
            "compare": {
                "left": {"ref": anchor_ref},
                "op": "eq",
                "right": {"ref": anchor_ref},
            }
        },
    }


def _first_case_output_ref(case_outputs: Mapping[str, Any]) -> str | None:
    """Find any output ref suitable for a match projection anchor assert."""

    for output in case_outputs.values():
        if not isinstance(output, Mapping):
            continue
        source = output.get("from")
        if isinstance(source, Mapping) and isinstance(source.get("ref"), str):
            return str(source["ref"])
    return None


def _assign_nested_local_value(*args, **kwargs):
    return lowering_core._assign_nested_local_value(*args, **kwargs)


def _phase_stdlib_lower_run_provider_phase_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower the phase helper that runs one provider-backed phase.

    `run-provider-phase` is a convenience form over `provider-result` for phase
    code that has a `with-phase` context. It derives prompt-input
    materializations, consumed-artifact metadata, and the phase result JSON path
    from that context instead of making the `.orc` author spell those paths.
    """

    expr = typed_expr.expr
    if context.phase_scope is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`run-provider-phase` lowering requires an active phase scope",
            span=expr.span,
            form_path=expr.form_path,
        )
    _require_phase_scope_name_match(
        context.phase_scope,
        authored_name=expr.phase_name,
        form_name="run-provider-phase",
        span=expr.span,
        form_path=expr.form_path,
    )
    provider_binding = context.extern_environment.bindings_by_name.get(expr.provider.name)
    prompt_binding = context.extern_environment.bindings_by_name.get(expr.prompt.name)
    if not isinstance(provider_binding, ProviderExtern) or not isinstance(prompt_binding, PromptExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="run-provider-phase lowering requires validated provider/prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=expr,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
        path_template=context.phase_scope.bundle_path_ref,
    )
    authored_contract["path"] = allocation.concrete_path_template
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    provider_call_locator = expr.provider.name if isinstance(expr.provider, NameExpr) else None
    row_metadata = _typed_prompt_input_row_metadata(
        context.workflow_name,
        provider_call_locator,
        context=context,
    )
    generated_steps: list[dict[str, Any]] = []
    consumes: list[dict[str, str]] = []
    prompt_consumes: list[str] = []
    hidden_inputs: dict[str, LoweringOrigin] = {}
    if not bool((row_metadata or {}).get("preserve_request_record")):
        (
            generated_steps,
            consumes,
            prompt_consumes,
            hidden_inputs,
        ) = _build_phase_stdlib_prompt_input_prelude(
            (
                ("inputs", expr.inputs_expr),
                (
                    "execution_report_target",
                    PhaseTargetExpr("execution-report", expr.span, expr.form_path, expr.expansion_stack),
                ),
                (
                    "progress_report_target",
                    PhaseTargetExpr("progress-report", expr.span, expr.form_path, expr.expansion_stack),
                ),
            ),
            context=context,
            local_values=local_values,
            source_expr=expr,
        )
    typed_prompt_inputs, typed_hidden_inputs = _build_typed_prompt_inputs_for_prompt_specs(
        (
            ("inputs", expr.inputs_expr),
            (
                "execution_report_target",
                PhaseTargetExpr("execution-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
            (
                "progress_report_target",
                PhaseTargetExpr("progress-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
        ),
        context=context,
        local_values=local_values,
        source_expr=expr,
        provider_call_locator=provider_call_locator,
    )
    step = {
        "name": step_name,
        "id": step_id,
        "provider": provider_binding.provider_id,
        "inject_output_contract": True,
        bundle_contract.contract_kind: authored_contract,
    }
    if typed_prompt_inputs:
        hidden_inputs.update(typed_hidden_inputs)
        step["typed_prompt_inputs"] = typed_prompt_inputs
        generated_steps = []
    else:
        step["consumes"] = consumes
        step["prompt_consumes"] = prompt_consumes
    step.update(lowering_core._prompt_source_step_fields(prompt_binding))
    generated_steps.append(step)
    _record_missing_step_origins(context, generated_steps, source=expr)
    return generated_steps, _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs=hidden_inputs,
    )


def _phase_stdlib_lower_produce_one_of_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower candidate-file production to evidence-backed variant selection.

    `produce-one-of` is used when a producer may create exactly one of several
    candidate outputs, such as a completed report or blocked-progress report.
    Lowering records file state before the producer runs, runs the producer,
    uses `select_variant_output` to prove which candidate changed, and exposes
    only the fields for the selected variant.
    """

    expr = typed_expr.expr
    if context.phase_scope is None or context.phase_scope.snapshot_root_ref is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`produce-one-of` lowering requires an active generic phase scope",
            span=expr.span,
            form_path=expr.form_path,
        )
    provider_binding = context.extern_environment.bindings_by_name.get(expr.producer.provider_expr.name)
    prompt_binding = context.extern_environment.bindings_by_name.get(expr.producer.prompt_expr.name)
    if not isinstance(provider_binding, ProviderExtern) or not isinstance(prompt_binding, PromptExtern):
        raise _compile_error(
            code="provider_result_provider_invalid",
            message="produce-one-of lowering requires validated provider/prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_prefix = context.step_name_prefix
    execute_step_name = f"{step_prefix}__produce"
    execute_step_id = _normalize_generated_step_id(execute_step_name)
    select_step_name = f"{step_prefix}__select_variant"
    select_step_id = _normalize_generated_step_id(select_step_name)
    result_step_name = step_prefix
    result_step_id = _normalize_generated_step_id(result_step_name)
    _record_step_origin(context, step_name=execute_step_name, step_id=execute_step_id, source=expr)
    _record_step_origin(context, step_name=select_step_name, step_id=select_step_id, source=expr)
    select_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=select_step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    select_payload = dict(select_contract.payload)
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=expr,
        step_name=select_step_name,
        step_id=select_step_id,
        semantic_role=GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
        path_template=context.phase_scope.bundle_path_ref,
        stable_target="select_variant",
    )
    select_payload["path"] = allocation.concrete_path_template
    select_payload["evidence"] = {
        "mode": "snapshot_diff",
        "snapshot": {
            "ref": f"root.steps.{execute_step_name}.snapshots.{step_prefix}_before",
        },
    }
    generated_steps, consumes, prompt_consumes, hidden_inputs = _build_phase_stdlib_prompt_input_prelude(
        (
            ("producer", expr.producer.inputs),
            (
                "execution_report_target",
                PhaseTargetExpr("execution-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
            (
                "progress_report_target",
                PhaseTargetExpr("progress-report", expr.span, expr.form_path, expr.expansion_stack),
            ),
        ),
        context=context,
        local_values=local_values,
        source_expr=expr,
    )
    prompt_input_step_name = generated_steps[0]["name"]
    snapshot_candidates = {
        candidate.variant_name: {
            "ref": f"root.steps.{prompt_input_step_name}.artifacts.{_render_candidate_target_artifact_name(candidate)}"
        }
        for candidate in expr.candidates
    }
    union_payload = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=result_step_name,
        span=expr.span,
        form_path=expr.form_path,
    ).payload
    output_contracts = _union_output_contracts(
        typed_expr.type_ref,
        payload=union_payload,
        span=expr.span,
        form_path=expr.form_path,
    )
    shared_field_names = {field["name"] for field in union_payload["shared_fields"]}

    def _produce_one_of_case_block(variant_name: str) -> dict[str, Any]:
        variant_payload = union_payload["variants"][variant_name]
        variant_field_names = {field["name"] for field in variant_payload["fields"]}
        variant_relpath_fields = [
            field["name"] for field in variant_payload["fields"] if field.get("type") == "relpath"
        ]
        fallback_relpath_ref = None
        if variant_relpath_fields:
            fallback_relpath_ref = f"root.steps.{select_step_name}.artifacts.{variant_relpath_fields[0]}"
        local_values_payload: list[dict[str, Any]] = []
        case_outputs: dict[str, Any] = {}

        for field_name, definition in output_contracts.items():
            if field_name == "variant":
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"root.steps.{select_step_name}.artifacts.variant"},
                }
                continue
            if field_name in variant_field_names:
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"root.steps.{select_step_name}.artifacts.{field_name}"},
                }
                continue
            if field_name in shared_field_names:
                if definition.get("kind") == "scalar" and definition.get("type") == "enum" and variant_name in definition.get("allowed", []):
                    local_values_payload.append(
                        {
                            "name": field_name,
                            "source": {"literal": variant_name},
                            "contract": dict(definition),
                        }
                    )
                    case_outputs[field_name] = {
                        **definition,
                        "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                    }
                    continue
                if definition.get("kind") == "scalar" and definition.get("type") == "string":
                    local_values_payload.append(
                        {
                            "name": field_name,
                            "source": {"literal": variant_name.lower()},
                            "contract": dict(definition),
                        }
                    )
                    case_outputs[field_name] = {
                        **definition,
                        "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                    }
                    continue
            if definition.get("kind") == "relpath" and fallback_relpath_ref is not None:
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": fallback_relpath_ref},
                }
                continue
            if definition.get("kind") == "scalar" and definition.get("type") == "enum":
                allowed = definition.get("allowed", [])
                literal_value = allowed[0] if isinstance(allowed, list) and allowed else variant_name
                local_values_payload.append(
                    {
                        "name": field_name,
                        "source": {"literal": literal_value},
                        "contract": dict(definition),
                    }
                )
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                }
                continue
            if definition.get("kind") == "scalar" and definition.get("type") == "string":
                local_values_payload.append(
                    {
                        "name": field_name,
                        "source": {"literal": variant_name.lower()},
                        "contract": dict(definition),
                    }
                )
                case_outputs[field_name] = {
                    **definition,
                    "from": {"ref": f"self.steps.MaterializeSharedFields.artifacts.{field_name}"},
                }
                continue
            raise _compile_error(
                code="produce_one_of_candidate_invalid",
                message=f"`produce-one-of` cannot normalize field `{field_name}` for variant `{variant_name}` in this slice",
                span=expr.span,
                form_path=expr.form_path,
            )

        case_steps: list[dict[str, Any]] = []
        if local_values_payload:
            case_steps.append(
                {
                    "name": "MaterializeSharedFields",
                    "id": "materialize_shared_fields",
                    "materialize_artifacts": {"values": local_values_payload},
                }
            )
        case_steps.append(
            _build_match_projection_anchor_step(
                match_step_name=result_step_name,
                variant_name=variant_name,
                case_outputs=case_outputs,
                context=context,
                span=expr.span,
            )
        )
        return {
            "id": _normalize_generated_step_id(f"{result_step_name}__{variant_name.lower()}"),
            "outputs": case_outputs,
            "steps": case_steps,
        }

    generated_steps.extend(
        [
            {
                "name": execute_step_name,
                "id": execute_step_id,
                "pre_snapshot": {
                    "name": f"{step_prefix}_before",
                    "digest": "sha256",
                    "candidates": snapshot_candidates,
                },
                "provider": provider_binding.provider_id,
                "consumes": consumes,
                "prompt_consumes": prompt_consumes,
                **lowering_core._prompt_source_step_fields(prompt_binding),
            },
            {
                "name": select_step_name,
                "id": select_step_id,
                "select_variant_output": select_payload,
            },
            {
                "name": result_step_name,
                "id": result_step_id,
                "match": {
                    "ref": f"root.steps.{select_step_name}.artifacts.variant",
                    "cases": {
                        variant_name: _produce_one_of_case_block(variant_name)
                        for variant_name in union_payload["variants"]
                    },
                },
            },
        ]
    )
    _record_missing_step_origins(context, generated_steps, source=expr)
    return generated_steps, _TerminalResult(
        step_name=result_step_name,
        step_id=result_step_id,
        output_refs=_record_output_refs(result_step_name, typed_expr.type_ref),
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _phase_stdlib_lower_resume_or_start_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower reusable-state logic into validate, branch, and load steps.

    `resume-or-start` means "reuse a prior validated result when it is still
    complete, otherwise run the supplied start expression." A certified adapter
    checks whether the previous JSON bundle and referenced artifacts are still
    valid; a workflow `match` chooses reuse or fresh execution; both branches
    return the same typed result shape.
    """

    expr = typed_expr.expr
    validator_binding_name = "validate_reusable_phase_state"
    writer_binding_name = "write_reusable_phase_state_v1"
    loader_binding_name = f"load_canonical_phase_result__{expr.returns_type_name}"
    validator_binding = context.command_boundary_environment.bindings_by_name.get(validator_binding_name)
    writer_binding = context.command_boundary_environment.bindings_by_name.get(writer_binding_name)
    loader_binding = context.command_boundary_environment.bindings_by_name.get(loader_binding_name)
    if context.phase_scope is not None:
        _require_phase_scope_name_match(
            context.phase_scope,
            authored_name=expr.resume_name,
            form_name="resume-or-start",
            span=expr.span,
            form_path=expr.form_path,
        )
    if not isinstance(validator_binding, CertifiedAdapterBinding):
        raise _compile_error(
            code="resume_or_start_uncertified_backend",
            message="`resume-or-start` lowering requires the certified reusable-state validator binding",
            span=expr.span,
            form_path=expr.form_path,
        )
    if not isinstance(writer_binding, CertifiedAdapterBinding):
        raise _compile_error(
            code="resume_or_start_uncertified_backend",
            message="`resume-or-start` lowering requires the certified reusable-state writer binding",
            span=expr.span,
            form_path=expr.form_path,
        )
    if not isinstance(loader_binding, CertifiedAdapterBinding):
        raise _compile_error(
            code="resume_or_start_uncertified_backend",
            message=f"`resume-or-start` lowering requires `{loader_binding_name}`",
            span=expr.span,
            form_path=expr.form_path,
        )
    validation_spec = getattr(expr, "validation_spec", None)
    if validation_spec is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start` lowering requires typed reusable-state validation metadata",
            span=expr.span,
            form_path=expr.form_path,
        )
    (
        structured_contract_kind,
        expected_contract_fingerprint,
        _,
        structured_contract,
    ) = derive_reusable_state_contract_metadata(
        typed_expr.type_ref,
        target_dsl_version="2.14",
        workflow_name=context.workflow_name,
        step_id=context.step_name_prefix,
        reusable_variants=tuple(expr.valid_when),
        span=expr.span,
        form_path=expr.form_path,
    )
    validator_step_name = f"{context.step_name_prefix}__resume_decision"
    validator_step_id = _normalize_generated_step_id(validator_step_name)
    result_step_name = context.step_name_prefix
    result_step_id = _normalize_generated_step_id(result_step_name)
    reuse_loader_step_name = f"{context.step_name_prefix}__reuse_load"
    reuse_loader_step_id = _normalize_generated_step_id(reuse_loader_step_name)
    _record_step_origin(context, step_name=validator_step_name, step_id=validator_step_id, source=expr)
    _record_step_origin(context, step_name=result_step_name, step_id=result_step_id, source=expr)
    _record_step_origin(context, step_name=reuse_loader_step_name, step_id=reuse_loader_step_id, source=expr)
    resume_from_ref = _render_existing_output_ref(expr.resume_from_expr, local_values=local_values)
    if resume_from_ref is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :resume-from` must lower from one workflow input or existing output ref",
            span=expr.resume_from_expr.span,
            form_path=expr.resume_from_expr.form_path,
        )
    validator_allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=expr,
        step_name=validator_step_name,
        step_id=validator_step_id,
        semantic_role=GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
        stable_target="resume_validation",
    )
    validator_hidden_input = validator_allocation.generated_input_name
    public_input_templates = {
        name: f"${{inputs.{name}}}"
        for name in validation_spec.public_input_hash_basis
    }
    validator_payload = json.dumps(
        {
            "resume_from": _template_for_ref(resume_from_ref),
            "target_dsl_version": "2.14",
            "return_type_name": typed_expr.type_ref.name,
            "structured_contract_kind": structured_contract_kind,
            "expected_contract_fingerprint": expected_contract_fingerprint,
            "structured_contract": structured_contract,
            "summary_schema": validation_spec.summary_schema,
            "summary_version": validation_spec.summary_version,
            "sidecar_suffix": validation_spec.sidecar_suffix,
            "canonical_bundle_digest_field": validation_spec.canonical_bundle_digest_field,
            "reusable_variants": list(expr.valid_when),
            "artifact_requirements": {
                key: [
                    {
                        "field_path": list(requirement.field_path),
                        "under": requirement.under,
                    }
                    for requirement in requirements
                ]
                for key, requirements in validation_spec.artifact_requirements.items()
            },
            "public_input_hash_basis": list(validation_spec.public_input_hash_basis),
            "current_public_inputs": public_input_templates,
            "producer_fingerprint_basis": dict(validation_spec.producer_fingerprint_basis),
        }
    )
    reuse_fields = [
        {
            "name": "source_bundle_path",
            "json_pointer": "/source_bundle_path",
            "type": "relpath",
        },
        {
            "name": "source_bundle_sha256",
            "json_pointer": "/source_bundle_sha256",
            "type": "string",
        },
    ]
    if isinstance(typed_expr.type_ref, UnionTypeRef):
        reuse_fields.append(
            {
                "name": "matched_variant",
                "json_pointer": "/matched_variant",
                "type": "enum",
                "allowed": list(expr.valid_when),
            }
        )
    validator_step = {
        "name": validator_step_name,
        "id": validator_step_id,
        "command": [*validator_binding.stable_command, validator_payload],
        "variant_output": {
            "path": validator_allocation.concrete_path_template,
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": [
                    "REUSABLE",
                    "START",
                    "STALE",
                    "MISSING_ARTIFACT",
                    "FAILED_PRIOR_STATE",
                ],
            },
            "shared_fields": [],
            "variants": {
                "REUSABLE": {
                    "fields": reuse_fields
                },
                "START": {
                    "fields": []
                },
                "STALE": {"fields": []},
                "MISSING_ARTIFACT": {"fields": []},
                "FAILED_PRIOR_STATE": {"fields": []},
            },
        },
    }
    fresh_case_variants = ("START", "STALE", "MISSING_ARTIFACT", "FAILED_PRIOR_STATE")

    def _build_fresh_case(variant_name: str) -> tuple[list[dict[str, Any]], _TerminalResult, str]:
        case_prefix = f"{context.step_name_prefix}__{variant_name.lower()}"
        case_context = _copy_context_with_step_prefix(
            context,
            step_name_prefix=case_prefix,
        )
        start_metadata = getattr(expr.start_expr, "metadata", None)
        start_span = getattr(expr.start_expr, "span", getattr(start_metadata, "source_span", None))
        start_form_path = getattr(expr.start_expr, "form_path", getattr(start_metadata, "form_path", ()))
        case_steps, case_terminal = _lower_expression(
            TypedExpr(
                expr=expr.start_expr,
                type_ref=typed_expr.type_ref,
                span=start_span,
                form_path=start_form_path,
            ),
            context=case_context,
            local_values=local_values,
        )
        case_writer_step_name = f"{case_prefix}__write_reusable_state"
        case_writer_step_id = _normalize_generated_step_id(case_writer_step_name)
        _record_step_origin(context, step_name=case_writer_step_name, step_id=case_writer_step_id, source=expr)
        case_bundle_ref = _resume_start_bundle_ref(
            expr.start_expr,
            start_terminal=case_terminal,
            context=case_context,
        )
        case_writer_allocation = allocate_generated_result_bundle(
            context=context,
            source_expr=expr,
            step_name=case_writer_step_name,
            step_id=case_writer_step_id,
            semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
            stable_target="reusable_state_write",
        )
        case_writer_hidden_input = case_writer_allocation.generated_input_name
        case_writer_payload = json.dumps(
            {
                "bundle_path": _template_for_ref(case_bundle_ref),
                "target_dsl_version": "2.14",
                "return_type_name": typed_expr.type_ref.name,
                "structured_contract_kind": structured_contract_kind,
                "expected_contract_fingerprint": expected_contract_fingerprint,
                "structured_contract": structured_contract,
                "summary_schema": validation_spec.summary_schema,
                "summary_version": validation_spec.summary_version,
                "sidecar_suffix": validation_spec.sidecar_suffix,
                "canonical_bundle_digest_field": validation_spec.canonical_bundle_digest_field,
                "reusable_variants": list(expr.valid_when),
                "artifact_requirements": {
                    key: [
                        {
                            "field_path": list(requirement.field_path),
                            "under": requirement.under,
                        }
                        for requirement in requirements
                    ]
                    for key, requirements in validation_spec.artifact_requirements.items()
                },
                "public_input_hash_basis": list(validation_spec.public_input_hash_basis),
                "current_public_inputs": public_input_templates,
                "producer_fingerprint_basis": dict(validation_spec.producer_fingerprint_basis),
                "source_run_id": public_input_templates.get("phase-ctx__run__run-id", "workflow-lisp-run"),
                "source_step_id": case_writer_step_name,
                "source_call_frame_id": "root",
                "phase_id": expr.resume_name,
                "created_at": f"{context.workflow_name}:{case_writer_step_name}",
            }
        )
        case_writer_step = {
            "name": case_writer_step_name,
            "id": case_writer_step_id,
            "command": [*writer_binding.stable_command, case_writer_payload],
            "output_bundle": {
                "path": case_writer_allocation.concrete_path_template,
                "fields": [
                    {
                        "name": "status",
                        "json_pointer": "/status",
                        "type": "string",
                    },
                    {
                        "name": "bundle_path",
                        "json_pointer": "/bundle_path",
                        "type": "relpath",
                    },
                    {
                        "name": "summary_path",
                        "json_pointer": "/summary_path",
                        "type": "relpath",
                    },
                    {
                        "name": "schema",
                        "json_pointer": "/schema",
                        "type": "string",
                    },
                ],
            },
        }
        return [*case_steps, case_writer_step], case_terminal, case_writer_hidden_input

    fresh_case_data = {
        variant_name: _build_fresh_case(variant_name) for variant_name in fresh_case_variants
    }
    loader_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=reuse_loader_step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    loader_allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=expr,
        step_name=reuse_loader_step_name,
        step_id=reuse_loader_step_id,
        semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
        stable_target="reusable_state_load",
    )
    loader_hidden_input = loader_allocation.generated_input_name
    loader_payload = json.dumps(
        {
            "bundle_path": "${root.steps."
            + validator_step_name
            + ".artifacts.source_bundle_path}",
            "target_dsl_version": "2.14",
            "return_type_name": typed_expr.type_ref.name,
            "structured_contract_kind": structured_contract_kind,
            "expected_contract_fingerprint": expected_contract_fingerprint,
            "structured_contract": structured_contract,
            "source_bundle_sha256": "${root.steps."
            + validator_step_name
            + ".artifacts.source_bundle_sha256}",
        }
    )
    loader_step = {
        "name": reuse_loader_step_name,
        "id": reuse_loader_step_id,
        "command": [*loader_binding.stable_command, loader_payload],
        loader_contract.contract_kind: {
            **dict(loader_contract.payload),
            "path": loader_allocation.concrete_path_template,
        },
    }
    resume_output_contracts = {
        field.generated_name.removeprefix("return__"): dict(field.contract_definition)
        for field in derive_workflow_boundary_fields(
            typed_expr.type_ref,
            generated_name="return",
            source_path=("return",),
            span=expr.span,
            form_path=expr.form_path,
        )
    }

    def _case_ref(ref: str) -> str:
        if ref.startswith("root.steps."):
            return "self.steps." + ref.removeprefix("root.steps.")
        return ref

    def _case_outputs(terminal: _TerminalResult) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for field_name, definition in resume_output_contracts.items():
            outputs[field_name] = {
                **definition,
                "from": {"ref": _case_ref(terminal.output_refs[f"return__{field_name}"])},
            }
        return outputs

    reuse_terminal = _TerminalResult(
        step_name=reuse_loader_step_name,
        step_id=reuse_loader_step_id,
        output_refs=_record_output_refs(reuse_loader_step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs={loader_hidden_input: _origin_from_context_source(context, expr)},
    )
    reuse_case_outputs = _case_outputs(reuse_terminal)
    result_step = {
        "name": result_step_name,
        "id": result_step_id,
        "match": {
            "ref": f"root.steps.{validator_step_name}.artifacts.variant",
            "cases": {
                "REUSABLE": {
                    "id": _normalize_generated_step_id(f"{context.step_name_prefix}__reuse"),
                    "outputs": reuse_case_outputs,
                    "steps": [
                        loader_step,
                        _build_match_projection_anchor_step(
                            match_step_name=result_step_name,
                            variant_name="REUSABLE",
                            case_outputs=reuse_case_outputs,
                            context=context,
                            span=expr.span,
                        ),
                    ],
                },
                **{
                    variant_name: {
                        "id": _normalize_generated_step_id(f"{context.step_name_prefix}__{variant_name.lower()}"),
                        "outputs": _case_outputs(fresh_case_data[variant_name][1]),
                        "steps": [
                            *fresh_case_data[variant_name][0],
                            _build_match_projection_anchor_step(
                                match_step_name=result_step_name,
                                variant_name=variant_name,
                                case_outputs=_case_outputs(fresh_case_data[variant_name][1]),
                                context=context,
                                span=expr.span,
                            ),
                        ],
                    }
                    for variant_name in fresh_case_variants
                },
            },
        },
    }
    hidden_inputs = {
        validator_hidden_input: _origin_from_context_source(context, expr),
    }
    hidden_inputs.update(reuse_terminal.hidden_inputs)
    for _, case_terminal, case_writer_hidden_input in fresh_case_data.values():
        hidden_inputs.update(case_terminal.hidden_inputs)
        hidden_inputs[case_writer_hidden_input] = _origin_from_context_source(context, expr)
    _record_missing_step_origins(context, [validator_step, result_step], source=expr)
    return [validator_step, result_step], _TerminalResult(
        step_name=result_step_name,
        step_id=result_step_id,
        output_refs=_record_output_refs(result_step_name, typed_expr.type_ref),
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _resume_start_bundle_ref(
    start_expr: Any,
    *,
    start_terminal: _TerminalResult,
    context: _LoweringContext,
) -> str:
    """Find the canonical bundle path produced by a `resume-or-start` start arm."""

    # emitter: resume-or-start bundle selection for command-result owner output.
    if isinstance(start_expr, CommandResultExpr):
        return f"inputs.__write_root__{start_terminal.step_id}__result_bundle"
    if isinstance(start_expr, CallExpr):
        lowered_callee = context.lowered_callees.get(start_expr.callee_name)
        imported_bundle = context.imported_workflow_bundles.get(start_expr.callee_name)
        if lowered_callee is None and imported_bundle is None and start_expr.callee_name in context.workflows_by_name:
            lowered_callee = context.ensure_workflow_lowered(start_expr.callee_name)
        bundle_input_name = _call_result_bundle_input_name(
            start_expr.callee_name,
            context=context,
            span=start_expr.span,
            form_path=start_expr.form_path,
        )
        managed_inputs = _managed_write_root_requirements_for_callable(
            lowered_callee=lowered_callee,
            imported_bundle=imported_bundle,
            span=start_expr.span,
            form_path=start_expr.form_path,
        )
        if bundle_input_name not in set(managed_inputs):
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call canonical bundle input must be a managed write root",
                span=start_expr.span,
                form_path=start_expr.form_path,
            )
        return _managed_write_root_bindings(
            caller_workflow_name=context.workflow_name,
            call_step_name=start_terminal.step_name,
            callee_name=start_expr.callee_name,
            managed_inputs=(bundle_input_name,),
        )[bundle_input_name]
    # emitter: phase stdlib starts expose the active phase bundle.
    if isinstance(start_expr, (RunProviderPhaseExpr, ProduceOneOfExpr)):
        if context.phase_scope is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-scoped resume start lowering requires an active phase scope",
                span=start_expr.span,
                form_path=start_expr.form_path,
            )
        return context.phase_scope.bundle_path_ref
    # emitter: provider-result starts expose the active phase bundle.
    if isinstance(start_expr, ProviderResultExpr):
        if context.phase_scope is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` provider results must lower inside an active phase scope",
                span=start_expr.span,
                form_path=start_expr.form_path,
            )
        return context.phase_scope.bundle_path_ref
    perform_kind = getattr(start_expr, "perform_kind", None)
    if perform_kind == "workflow_call":
        callee_name = start_expr.target_name
        lowered_callee = context.lowered_callees.get(callee_name)
        imported_bundle = context.imported_workflow_bundles.get(callee_name)
        if lowered_callee is None and imported_bundle is None and callee_name in context.workflows_by_name:
            lowered_callee = context.ensure_workflow_lowered(callee_name)
        bundle_input_name = _call_result_bundle_input_name(
            callee_name,
            context=context,
            span=start_expr.metadata.source_span,
            form_path=start_expr.metadata.form_path,
        )
        managed_inputs = _managed_write_root_requirements_for_callable(
            lowered_callee=lowered_callee,
            imported_bundle=imported_bundle,
            span=start_expr.metadata.source_span,
            form_path=start_expr.metadata.form_path,
        )
        if bundle_input_name not in set(managed_inputs):
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call canonical bundle input must be a managed write root",
                span=start_expr.metadata.source_span,
                form_path=start_expr.metadata.form_path,
            )
        return _managed_write_root_bindings(
            caller_workflow_name=context.workflow_name,
            call_step_name=start_terminal.step_name,
            callee_name=callee_name,
            managed_inputs=(bundle_input_name,),
        )[bundle_input_name]
    if perform_kind in {"provider_result", "run_provider_phase", "produce_one_of"}:
        if context.phase_scope is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="phase-scoped WCC resume start lowering requires an active phase scope",
                span=start_expr.metadata.source_span,
                form_path=start_expr.metadata.form_path,
            )
        return context.phase_scope.bundle_path_ref
    if perform_kind == "command_result":
        return f"inputs.__write_root__{start_terminal.step_id}__result_bundle"
    fallback_metadata = getattr(start_expr, "metadata", None)
    raise _compile_error(
        code="resume_or_start_contract_invalid",
        message="`resume-or-start :start` must lower to one canonical bundle path in this slice",
        span=getattr(start_expr, "span", getattr(fallback_metadata, "source_span", None)),
        form_path=getattr(start_expr, "form_path", getattr(fallback_metadata, "form_path", ())),
    )


def _call_result_bundle_input_name(
    callee_name: str,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    """Find the generated bundle input name for a structured workflow call."""

    lowered_callee = context.lowered_callees.get(callee_name)
    imported_bundle = context.imported_workflow_bundles.get(callee_name)
    if lowered_callee is None and imported_bundle is None and callee_name in context.workflows_by_name:
        lowered_callee = context.ensure_workflow_lowered(callee_name)
    if lowered_callee is None and imported_bundle is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must lower through an available structured-result callee",
            span=span,
            form_path=form_path,
        )
    return _workflow_result_bundle_input_name(
        lowered_callee=lowered_callee,
        imported_bundle=imported_bundle,
        span=span,
        form_path=form_path,
    )


def _workflow_result_bundle_input_name(
    *,
    lowered_callee: LoweredWorkflow | None,
    imported_bundle: LoadedWorkflowBundle | None,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    """Inspect a lowered callee and recover its terminal result-bundle input."""

    if lowered_callee is not None:
        terminal_step_name = _authored_terminal_step_name(
            lowered_callee.authored_mapping.get("outputs"),
            span=span,
            form_path=form_path,
        )
        terminal_step = _find_authored_step_by_name(lowered_callee.authored_mapping.get("steps"), terminal_step_name)
        if terminal_step is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call terminal step is not available for bundle recovery",
                span=span,
                form_path=form_path,
            )
        bundle_input = _structured_result_bundle_input_name(terminal_step)
        if bundle_input is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call must expose one canonical structured-result bundle path",
                span=span,
                form_path=form_path,
            )
        return bundle_input
    if imported_bundle is not None:
        terminal_step_name = _surface_terminal_step_name(
            imported_bundle.surface.outputs,
            span=span,
            form_path=form_path,
        )
        terminal_step = _find_surface_step_by_name(imported_bundle.surface.steps, terminal_step_name)
        if terminal_step is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` imported workflow call terminal step is not available for bundle recovery",
                span=span,
                form_path=form_path,
            )
        bundle_input = _structured_result_bundle_input_name(terminal_step)
        if bundle_input is None:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call must expose one canonical structured-result bundle path",
                span=span,
                form_path=form_path,
            )
        return bundle_input
    raise _compile_error(
        code="resume_or_start_contract_invalid",
        message="`resume-or-start :start` workflow call must lower through an available structured-result callee",
        span=span,
        form_path=form_path,
    )


def _authored_terminal_step_name(
    outputs: Any,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    """Return the one terminal authored step referenced by workflow outputs."""

    if not isinstance(outputs, Mapping):
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must expose step-backed return outputs",
            span=span,
            form_path=form_path,
        )
    terminal_step_name: str | None = None
    for output_spec in outputs.values():
        if not isinstance(output_spec, Mapping):
            continue
        source = output_spec.get("from")
        if not isinstance(source, Mapping):
            continue
        ref = source.get("ref")
        if not isinstance(ref, str):
            continue
        match = re.match(r"^(?:self|root)\.steps\.([^.]+)\.artifacts\.[^.]+$", ref)
        if match is None:
            continue
        candidate = match.group(1)
        if terminal_step_name is None:
            terminal_step_name = candidate
            continue
        if terminal_step_name != candidate:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call must normalize through one terminal structured-result step",
                span=span,
                form_path=form_path,
            )
    if terminal_step_name is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must expose return outputs backed by one terminal step",
            span=span,
            form_path=form_path,
        )
    return terminal_step_name


def _surface_terminal_step_name(
    outputs: Mapping[str, Any],
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    """Return the one typed surface step referenced by workflow outputs."""

    terminal_step_name: str | None = None
    for contract in outputs.values():
        source = getattr(contract, "from_ref", None)
        if not isinstance(source, StructuredStepReference) or source.field != "artifacts":
            continue
        candidate = source.step_name
        if terminal_step_name is None:
            terminal_step_name = candidate
            continue
        if terminal_step_name != candidate:
            raise _compile_error(
                code="resume_or_start_contract_invalid",
                message="`resume-or-start :start` workflow call must normalize through one terminal structured-result step",
                span=span,
                form_path=form_path,
            )
    if terminal_step_name is None:
        raise _compile_error(
            code="resume_or_start_contract_invalid",
            message="`resume-or-start :start` workflow call must expose return outputs backed by one terminal step",
            span=span,
            form_path=form_path,
        )
    return terminal_step_name


def _structured_result_bundle_input_name(step: Mapping[str, object] | SurfaceStep) -> str | None:
    """Return the generated input name used for one structured-result bundle path."""

    if isinstance(step, Mapping):
        contracts = (step.get("output_bundle"), step.get("variant_output"))
    else:
        contracts = (step.common.output_bundle, step.common.variant_output)
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        path = contract.get("path")
        if isinstance(path, str) and path.startswith("${inputs.") and path.endswith("}"):
            return path.removeprefix("${inputs.").removesuffix("}")
    if isinstance(step, Mapping):
        match_block = step.get("match")
        if isinstance(match_block, Mapping):
            shared_bundle_input: str | None = None
            for case in (match_block.get("cases") or {}).values():
                if not isinstance(case, Mapping):
                    return None
                terminal_step_name = _mapping_terminal_step_name(case.get("outputs"))
                if terminal_step_name is None:
                    return None
                terminal_step = _find_authored_step_by_name(case.get("steps"), terminal_step_name)
                if terminal_step is None:
                    return None
                bundle_input = _structured_result_bundle_input_name(terminal_step)
                if bundle_input is None:
                    return None
                if shared_bundle_input is None:
                    shared_bundle_input = bundle_input
                    continue
                if shared_bundle_input != bundle_input:
                    return None
            return shared_bundle_input
    return None


def _mapping_terminal_step_name(outputs: Any) -> str | None:
    """Recover the one terminal step name referenced by one outputs mapping."""

    if not isinstance(outputs, Mapping):
        return None
    terminal_step_name: str | None = None
    for output_spec in outputs.values():
        if not isinstance(output_spec, Mapping):
            continue
        source = output_spec.get("from")
        if not isinstance(source, Mapping):
            continue
        ref = source.get("ref")
        if not isinstance(ref, str):
            continue
        match = re.match(r"^(?:self|root)\.steps\.([^.]+)\.artifacts\.[^.]+$", ref)
        if match is None:
            continue
        candidate = match.group(1)
        if terminal_step_name is None:
            terminal_step_name = candidate
            continue
        if terminal_step_name != candidate:
            return None
    return terminal_step_name


def _find_authored_step_by_name(steps: Any, step_name: str) -> Mapping[str, object] | None:
    """Find a generated step by name, recursing through match/repeat bodies."""

    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        if step.get("name") == step_name:
            return step
        repeat = step.get("repeat_until")
        if isinstance(repeat, Mapping):
            found = _find_authored_step_by_name(repeat.get("steps"), step_name)
            if found is not None:
                return found
        match = step.get("match")
        if isinstance(match, Mapping):
            for case in (match.get("cases") or {}).values():
                if not isinstance(case, Mapping):
                    continue
                found = _find_authored_step_by_name(case.get("steps"), step_name)
                if found is not None:
                    return found
    return None


def _find_surface_step_by_name(steps: Any, step_name: str) -> SurfaceStep | None:
    """Find one typed surface step by name, recursing through nested bodies."""

    if not isinstance(steps, tuple):
        return None
    for step in steps:
        if not isinstance(step, SurfaceStep):
            continue
        if step.name == step_name:
            return step
        if step.repeat_until is not None:
            found = _find_surface_step_by_name(step.repeat_until.steps, step_name)
            if found is not None:
                return found
        if step.match_cases:
            for case in step.match_cases.values():
                found = _find_surface_step_by_name(case.steps, step_name)
                if found is not None:
                    return found
        if step.then_branch is not None:
            found = _find_surface_step_by_name(step.then_branch.steps, step_name)
            if found is not None:
                return found
        if step.else_branch is not None:
            found = _find_surface_step_by_name(step.else_branch.steps, step_name)
            if found is not None:
                return found
        if step.for_each_steps:
            found = _find_surface_step_by_name(step.for_each_steps, step_name)
            if found is not None:
                return found
    return None


def _resume_required_artifact_fields(
    type_ref: Any,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Mapping[str, tuple[str, ...]]:
    """Compute artifact fields that must still exist for reusable state."""

    if isinstance(type_ref, RecordTypeRef):
        fields = derive_structured_result_contract(
            type_ref,
            workflow_name=context.workflow_name,
            step_id=context.step_name_prefix,
            span=span,
            form_path=form_path,
        ).payload["fields"]
        return {
            type_ref.name: tuple(
                field.name
                for index, field in enumerate(type_ref.definition.fields)
                if _surface_contract_from_structured_field(fields[index])["kind"] == "relpath"
            )
        }
    if not isinstance(type_ref, UnionTypeRef):
        return {}
    required: dict[str, tuple[str, ...]] = {}
    for variant in type_ref.definition.variants:
        contracts = _union_case_contract_definitions(
            type_ref,
            variant_name=variant.name,
            workflow_name=context.workflow_name,
            step_name=context.step_name_prefix,
            span=span,
            form_path=form_path,
        )
        required[variant.name] = tuple(
            field_name
            for field_name, definition in contracts.items()
            if field_name != "variant" and definition.get("kind") == "relpath"
        )
    return required

def _render_candidate_target(candidate: Any, *, context: _LoweringContext) -> str:
    """Render the output target for a `produce-one-of` candidate."""

    for field_spec in candidate.fields:
        target_expr = getattr(field_spec, "target_expr", None)
        if isinstance(target_expr, PhaseTargetExpr):
            target_ref = context.phase_scope.target_refs.get(target_expr.target_name) if context.phase_scope is not None else None
            if isinstance(target_ref, str):
                return target_ref
    raise _compile_error(
        code="produce_one_of_candidate_invalid",
        message=f"`produce-one-of` candidate `{candidate.variant_name}` requires a phase-target path",
        span=context.signature.span,
        form_path=context.signature.form_path,
    )


def _render_candidate_target_artifact_name(candidate: Any) -> str:
    """Choose the artifact name exposed for a `produce-one-of` candidate."""

    for field_spec in candidate.fields:
        target_expr = getattr(field_spec, "target_expr", None)
        if isinstance(target_expr, PhaseTargetExpr):
            return _phase_prompt_artifact_name_for_target(target_expr)
    fallback_target = next(
        (getattr(field_spec, "target_expr", None) for field_spec in candidate.fields if getattr(field_spec, "target_expr", None) is not None),
        None,
    )
    if fallback_target is None:
        raise ValueError(f"`produce-one-of` candidate `{candidate.variant_name}` requires a phase-target path")
    raise _compile_error(
        code="produce_one_of_candidate_invalid",
        message=f"`produce-one-of` candidate `{candidate.variant_name}` requires a phase-target path",
        span=fallback_target.span,
        form_path=fallback_target.form_path,
    )


def _join_ref_path(base_ref: str, suffix: str) -> str:
    """Append a path suffix to a substitution ref without losing templating."""

    if base_ref.startswith("${"):
        return f"{base_ref}/{suffix}"
    return "${" + base_ref + "}/" + suffix
