"""Direct straight-line defunctionalization from WCC to lowered workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..contracts import GeneratedInternalInput, derive_workflow_signature_contracts
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import FieldAccessExpr, LiteralExpr, NameExpr, RecordExpr, UnionVariantExpr
from ..procedures import ProcedureCatalog, ProcedureLoweringMode, TypedProcedureDef
from ..type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef, WorkflowRefTypeRef
from ..workflows import CommandBoundaryEnvironment, ExternEnvironment, TypedWorkflowDef, WorkflowCatalog, WorkflowDef, WorkflowSignature
from ..workflow_refs import WorkflowCallableSpecialization, specialization_name
from ..workflow_refs import ResolvedWorkflowRef
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from ..lowering import core as lowering_core
from ..lowering.context import _LoweringContext, _TerminalResult, _copy_context_with_phase_scope
from ..lowering.control_dispatch import _binding_local_value_from_terminal
from ..lowering.origins import LoweringOrigin, LoweringOriginMap, _build_validation_subject_bindings, _derive_generated_semantic_effects, _origins_with_keys, _origin_for_workflow as _origin_for_workflow_owner, _with_origin_key
from ..lowering.generated_paths import allocation_reason
from ..lowering.phase_scope import _resolve_active_phase_scope_parts
from ..lowering.values import _resolve_inline_expr_value, _signature_local_values
from ..lowering.effects import LowerableCommandResult, LowerableProviderResult, _lower_command_result_operation, _lower_provider_result_operation
from ..lowering.procedures import LowerableProcedureCall, _private_workflow_from_procedure, _resolve_procedure_lowering, _lower_procedure_call
from ..lowering.workflow_calls import LowerableWorkflowCall, _lower_workflow_call
from orchestrator.workflow.state_layout import derive_entrypoint_managed_write_root_allocations
from .anf import normalize_wcc_body_to_anf
from .elaborate import elaborate_typed_workflow
from .model import WCC_M2_ROUTE_SCHEMA_VERSION, WccBody, WccCall, WccFieldAccessAtom, WccHalt, WccInject, WccLet, WccLiteralAtom, WccNameAtom, WccPerform, WccPhaseScope, WccRecordAtom, WccValue


def lower_wcc_m2_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    procedure_catalog: ProcedureCatalog,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env,
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded straight-line workflows through WCC M2."""

    resolved_procedures = _resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=workflow_path,
        type_env=type_env,
    )
    private_workflows = {
        procedure.generated_workflow_name: _private_workflow_from_procedure(procedure)
        for procedure in resolved_procedures.values()
        if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW
        and procedure.generated_workflow_name is not None
    }
    generated_private_workflow_names = frozenset(private_workflows)
    workflows_by_name: dict[str, TypedWorkflowDef] = {
        **{workflow.definition.name: workflow for workflow in typed_workflows},
        **private_workflows,
    }
    lowered_by_name: dict[str, lowering_core.LoweredWorkflow] = {}
    visiting: set[str] = set()
    specialized_workflows: dict[tuple[str, tuple[tuple[str, str], ...]], TypedWorkflowDef] = {}

    def specialize_workflow(base_workflow_name: str, bindings: Mapping[str, ResolvedWorkflowRef]) -> TypedWorkflowDef:
        key = (
            base_workflow_name,
            tuple(sorted((name, resolved.workflow_name) for name, resolved in bindings.items())),
        )
        existing = specialized_workflows.get(key)
        if existing is not None:
            return existing
        base = workflows_by_name[base_workflow_name]
        specialized_name = specialization_name(base.signature.name, bindings)
        specialized = TypedWorkflowDef(
            definition=WorkflowDef(
                name=specialized_name,
                params=tuple(param for param in base.definition.params if param.name not in bindings),
                return_type_name=base.definition.return_type_name,
                body=base.definition.body,
                span=base.definition.span,
                form_path=base.definition.form_path,
                expansion_stack=base.definition.expansion_stack,
            ),
            signature=WorkflowSignature(
                name=specialized_name,
                params=tuple((name, type_ref) for name, type_ref in base.signature.params if name not in bindings),
                return_type_ref=base.signature.return_type_ref,
                span=base.signature.span,
                form_path=base.signature.form_path,
                param_defaults={
                    name: default
                    for name, default in base.signature.param_defaults.items()
                    if name not in bindings
                },
                hidden_context_requirements=base.signature.hidden_context_requirements,
                hidden_context_ambiguities=base.signature.hidden_context_ambiguities,
                allow_hidden_context_binding=base.signature.allow_hidden_context_binding,
            ),
            typed_body=base.typed_body,
            effect_summary=base.effect_summary,
            specialization=WorkflowCallableSpecialization(
                base_name=base.signature.name,
                workflow_ref_bindings=dict(bindings),
                specialized_name=specialized_name,
            ),
        )
        workflows_by_name[specialized_name] = specialized
        specialized_workflows[key] = specialized
        return specialized

    def lower_one(workflow_name: str) -> lowering_core.LoweredWorkflow:
        existing = lowered_by_name.get(workflow_name)
        if existing is not None:
            return existing
        if workflow_name in visiting:
            workflow = workflows_by_name[workflow_name]
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="workflow_signature_mismatch",
                        message=f"cyclic same-file workflow call detected for `{workflow_name}`",
                        span=workflow.definition.span,
                        form_path=workflow.definition.form_path,
                        phase="lowering",
                    ),
                )
            )
        visiting.add(workflow_name)
        typed_workflow = workflows_by_name[workflow_name]
        for dependency in lowering_core._typed_workflow_dependencies(
            typed_workflow,
            typed_procedures=resolved_procedures,
            workflow_catalog=workflow_catalog,
        ):
            if dependency in workflows_by_name:
                lower_one(dependency)
        lowered = _lower_one_wcc_workflow(
            typed_workflow,
            workflow_path=workflow_path,
            generated_private_workflow_names=generated_private_workflow_names,
            workflow_catalog=workflow_catalog,
            imported_workflow_bundles=imported_workflow_bundles,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            lowered_callees=lowered_by_name,
            type_env=type_env,
            typed_procedures=resolved_procedures,
            workflows_by_name=workflows_by_name,
            ensure_workflow_lowered=lower_one,
            specialize_workflow=specialize_workflow,
        )
        lowered_by_name[workflow_name] = lowered
        visiting.remove(workflow_name)
        return lowered

    private_order = [name for name in private_workflows]
    for workflow_name in private_order:
        lower_one(workflow_name)

    ordered: list[lowering_core.LoweredWorkflow] = []
    included_names: set[str] = set()
    for workflow in typed_workflows:
        if any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in workflow.signature.params):
            continue
        lowered = lower_one(workflow.definition.name)
        ordered.append(lowered)
        included_names.add(lowered.typed_workflow.definition.name)
    for workflow_name in private_order:
        ordered.append(lowered_by_name[workflow_name])
        included_names.add(workflow_name)
    for workflow_name, lowered in lowered_by_name.items():
        if workflow_name not in included_names:
            ordered.append(lowered)
    return tuple(ordered)


def _lower_one_wcc_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    workflow_path: Path,
    generated_private_workflow_names: frozenset[str],
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    lowered_callees: Mapping[str, lowering_core.LoweredWorkflow],
    type_env,
    typed_procedures: Mapping[str, TypedProcedureDef],
    workflows_by_name: Mapping[str, TypedWorkflowDef],
    ensure_workflow_lowered: Any,
    specialize_workflow: Any,
) -> lowering_core.LoweredWorkflow:
    inputs, outputs, boundary_projection = derive_workflow_signature_contracts(typed_workflow.signature)
    authored_inputs = {name: dict(contract.definition) for name, contract in inputs.items()}
    authored_outputs = {name: dict(contract.definition) for name, contract in outputs.items()}
    is_generated_private_workflow = typed_workflow.definition.name in generated_private_workflow_names
    if isinstance(typed_workflow.signature.return_type_ref, UnionTypeRef) and is_generated_private_workflow:
        for definition in authored_outputs.values():
            if isinstance(definition, dict) and definition.get("type") == "relpath":
                definition["must_exist_target"] = False
    workflow_origin = _origin_for_workflow_owner(typed_workflow, typed_procedures=typed_procedures)
    origin_inputs = {name: workflow_origin for name in authored_inputs}
    origin_outputs = {name: workflow_origin for name in authored_outputs}

    context = _LoweringContext(
        workflow_name=typed_workflow.definition.name,
        step_name_prefix=typed_workflow.definition.name,
        workflow_path=workflow_path,
        signature=typed_workflow.signature,
        authored_input_contracts=MappingProxyType({name: dict(definition) for name, definition in authored_inputs.items()}),
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        lowered_callees=lowered_callees,
        typed_procedures=typed_procedures,
        workflows_by_name=workflows_by_name,
        ensure_workflow_lowered=ensure_workflow_lowered,
        specialize_workflow=specialize_workflow,
        type_env=type_env,
        step_spans={},
        generated_input_spans=origin_inputs,
        authored_generated_inputs=set(authored_inputs),
        internal_generated_input_reasons={},
        internal_generated_input_contracts={},
        generated_output_spans=origin_outputs,
        generated_path_spans={},
        generated_path_allocations=[],
        generated_semantic_effects=[],
        top_level_artifacts={},
        inline_call_counters={},
        origin_notes=workflow_origin.notes,
        boundary_projection=boundary_projection,
        return_output_contracts=MappingProxyType(
            {
                name.removeprefix("return__"): dict(definition)
                for name, definition in authored_outputs.items()
            }
        ),
        local_type_bindings={name: type_ref for name, type_ref in typed_workflow.signature.params},
        is_generated_private_workflow=is_generated_private_workflow,
    )
    workflow_return_types = {
        name: workflow.signature.return_type_ref
        for name, workflow in workflows_by_name.items()
    }
    procedure_return_types = {
        name: procedure.signature.return_type_ref
        for name, procedure in typed_procedures.items()
    }
    wcc_body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow(
            typed_workflow,
            type_env=type_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            route_schema_version=WCC_M2_ROUTE_SCHEMA_VERSION,
        )
    )
    local_values = _signature_local_values(typed_workflow)
    steps, terminal = _defunctionalize_body(
        wcc_body,
        context=context,
        local_values=local_values,
    )
    steps, terminal = lowering_core._normalize_top_level_terminal(
        typed_workflow=typed_workflow,
        authored_outputs=authored_outputs,
        steps=steps,
        terminal=terminal,
        context=context,
    )

    for hidden_input_name, origin in terminal.hidden_inputs.items():
        authored_inputs[hidden_input_name] = {"kind": "relpath", "type": "relpath"}
        context.generated_input_spans[hidden_input_name] = origin
        context.internal_generated_input_reasons.setdefault(hidden_input_name, "managed_write_root")
    for allocation in context.generated_path_allocations:
        hidden_input_name = allocation.generated_input_name
        reason = allocation_reason(allocation)
        if not isinstance(hidden_input_name, str) or reason is None:
            continue
        authored_inputs.setdefault(hidden_input_name, {"kind": "relpath", "type": "relpath"})
        origin = context.generated_path_spans.get(allocation.concrete_path_template)
        if origin is not None:
            context.generated_input_spans.setdefault(hidden_input_name, origin)
        context.internal_generated_input_reasons.setdefault(hidden_input_name, reason)
    for hidden_input_name, contract_definition in context.internal_generated_input_contracts.items():
        authored_inputs[hidden_input_name] = dict(contract_definition)

    base_allocations = tuple(context.generated_path_allocations)
    for derived_allocation in derive_entrypoint_managed_write_root_allocations(base_allocations):
        source_allocation_id = derived_allocation.projection_hints.get("source_allocation_id")
        source_origin = next(
            (
                context.generated_path_spans.get(allocation.concrete_path_template)
                for allocation in base_allocations
                if allocation.allocation_id == source_allocation_id
            ),
            None,
        )
        context.generated_path_allocations.append(derived_allocation)
        if source_origin is not None:
            context.generated_path_spans.setdefault(derived_allocation.concrete_path_template, source_origin)

    authored_input_spans = {
        name: origin
        for name, origin in context.generated_input_spans.items()
        if name in context.authored_generated_inputs
    }
    internal_input_spans = {
        name: origin
        for name, origin in context.generated_input_spans.items()
        if name in context.internal_generated_input_reasons
    }
    finalized_projection = replace(
        context.boundary_projection,
        generated_internal_inputs=tuple(
            GeneratedInternalInput(generated_name=name, reason=reason)
            for name, reason in sorted(context.internal_generated_input_reasons.items())
        ),
    )
    lowering_core._validate_projection_origin_coverage(
        workflow_name=typed_workflow.definition.name,
        boundary_projection=finalized_projection,
        authored_input_spans=authored_input_spans,
        internal_input_spans=internal_input_spans,
        generated_output_spans=context.generated_output_spans,
        span=typed_workflow.definition.span,
        form_path=typed_workflow.definition.form_path,
    )

    authored_mapping: dict[str, object] = {
        "version": "2.14",
        "name": typed_workflow.definition.name,
        "inputs": authored_inputs,
        "outputs": lowering_core._lower_workflow_outputs(
            typed_workflow=typed_workflow,
            authored_outputs=authored_outputs,
            terminal=terminal,
        ),
        "steps": steps,
    }
    if context.top_level_artifacts:
        authored_mapping["artifacts"] = dict(context.top_level_artifacts)

    generated_semantic_effects = _derive_generated_semantic_effects(
        authored_mapping.get("steps"),
        context=context,
        workflow_origin=workflow_origin,
    )

    return lowering_core.LoweredWorkflow(
        typed_workflow=typed_workflow,
        authored_mapping=authored_mapping,
        origin_map=LoweringOriginMap(
            workflow_name=typed_workflow.definition.name,
            workflow_origin=_with_origin_key(
                LoweringOrigin(
                    span=workflow_origin.span,
                    form_path=workflow_origin.form_path,
                    expansion_stack=workflow_origin.expansion_stack,
                    notes=context.origin_notes or workflow_origin.notes,
                ),
                workflow_name=typed_workflow.definition.name,
                entity_kind="workflow",
                subject_name=typed_workflow.definition.name,
            ),
            step_spans=MappingProxyType(
                _origins_with_keys(context.step_spans, workflow_name=typed_workflow.definition.name, entity_kind="step_id")
            ),
            authored_input_spans=MappingProxyType(
                _origins_with_keys(authored_input_spans, workflow_name=typed_workflow.definition.name, entity_kind="generated_input")
            ),
            internal_input_spans=MappingProxyType(
                _origins_with_keys(
                    internal_input_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_internal_input",
                )
            ),
            generated_output_spans=MappingProxyType(
                _origins_with_keys(
                    context.generated_output_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_output",
                )
            ),
            generated_path_spans=MappingProxyType(
                _origins_with_keys(
                    context.generated_path_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_path",
                )
            ),
            validation_subject_bindings=_build_validation_subject_bindings(
                workflow_name=typed_workflow.definition.name,
                workflow_origin=_with_origin_key(
                    LoweringOrigin(
                        span=workflow_origin.span,
                        form_path=workflow_origin.form_path,
                        expansion_stack=workflow_origin.expansion_stack,
                        notes=context.origin_notes or workflow_origin.notes,
                    ),
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="workflow",
                    subject_name=typed_workflow.definition.name,
                ),
                step_spans=_origins_with_keys(
                    context.step_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="step_id",
                ),
                generated_inputs={
                    **_origins_with_keys(
                        authored_input_spans,
                        workflow_name=typed_workflow.definition.name,
                        entity_kind="generated_input",
                    ),
                    **_origins_with_keys(
                        internal_input_spans,
                        workflow_name=typed_workflow.definition.name,
                        entity_kind="generated_internal_input",
                    ),
                },
                generated_outputs=_origins_with_keys(
                    context.generated_output_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_output",
                ),
                generated_paths=_origins_with_keys(
                    context.generated_path_spans,
                    workflow_name=typed_workflow.definition.name,
                    entity_kind="generated_path",
                ),
            ),
            generated_semantic_effects=generated_semantic_effects,
        ),
        boundary_projection=finalized_projection,
        generated_path_allocations=tuple(context.generated_path_allocations),
        private_artifact_ids=tuple(
            name
            for name, definition in context.top_level_artifacts.items()
            if isinstance(name, str) and isinstance(definition, Mapping) and definition.get("kind") == "collection"
        ),
    )


def _defunctionalize_body(
    body: WccBody,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    steps: list[dict[str, Any]] = []
    hidden_inputs: dict[str, Any] = {}
    local_bindings = dict(local_values)
    current_context = context
    current = body
    while isinstance(current, WccLet):
        binding_type = current.bound_type_ref
        if isinstance(current.bound_value, (WccPerform, WccCall)):
            binding_context = _context_with_wcc_phase_scope(
                current_context,
                phase_scope=current.bound_value.metadata.phase_scope,
                local_values=local_bindings,
            )
            step_context = lowering_core._copy_context_with_step_prefix(
                binding_context,
                step_name_prefix=_binding_step_prefix(current_context, current.bound_name),
            )
            binding_steps, binding_terminal = _lower_effectful_binding(
                current.bound_value,
                binding_type=binding_type,
                context=step_context,
                local_values=local_bindings,
            )
            steps.extend(binding_steps)
            hidden_inputs.update(binding_terminal.hidden_inputs)
            local_value = _binding_local_value_from_terminal(
                current.bound_value,
                binding_type=binding_type,
                binding_terminal=binding_terminal,
            )
            if local_value is not None:
                local_bindings[current.bound_name] = local_value
        else:
            binding_expr = _frontend_expr_from_wcc_binding_value(current.bound_value)
            resolved_binding = _resolve_inline_expr_value(binding_expr, local_values=local_bindings)
            local_bindings[current.bound_name] = resolved_binding
        current_context = lowering_core._context_with_local_type_binding(
            current_context,
            binding_name=current.bound_name,
            binding_type=binding_type,
        )
        current = current.body

    result_expr = _frontend_expr_from_wcc_value(current.result)
    output_refs = lowering_core._inline_output_refs_for_expr(
        result_expr,
        type_ref=current.metadata.type_ref,
        local_values=local_bindings,
        context=current_context,
    )
    if output_refs is None:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_return_not_exportable",
                    message="WCC M2 defunctionalization could not export the normalized halt value",
                    span=current.metadata.source_span,
                    form_path=current.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    return steps, _TerminalResult(
        step_name=current_context.step_name_prefix,
        step_id=lowering_core._normalize_generated_step_id(current_context.step_name_prefix),
        output_refs=output_refs,
        output_kind="projection",
        hidden_inputs=hidden_inputs,
    )


def _binding_step_prefix(context: _LoweringContext, binding_name: str) -> str:
    if binding_name.startswith("__wcc_effect_"):
        return context.step_name_prefix
    return f"{context.step_name_prefix}__{binding_name}"


def _context_with_wcc_phase_scope(
    context: _LoweringContext,
    *,
    phase_scope: WccPhaseScope | None,
    local_values: Mapping[str, Any],
) -> _LoweringContext:
    if phase_scope is None:
        return context
    resolved_phase_scope = _resolve_active_phase_scope_parts(
        ctx_expr=phase_scope.ctx_expr,
        phase_name=phase_scope.phase_name,
        span=phase_scope.source_span,
        form_path=phase_scope.form_path,
        local_values=local_values,
    )
    return _copy_context_with_phase_scope(context, resolved_phase_scope)


def _lower_effectful_binding(
    value: WccPerform | WccCall,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if isinstance(value, WccPerform):
        if value.perform_kind == "command_result":
            return _lower_command_result_operation(
                LowerableCommandResult(
                    step_name=value.target_name,
                    argv=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                result_type=binding_type,
                context=context,
                local_values=local_values,
            )
        if value.perform_kind == "provider_result":
            return _lower_provider_result_operation(
                LowerableProviderResult(
                    provider_name=value.target_name,
                    prompt_name=value.prompt_name or "",
                    inputs=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                result_type=binding_type,
                context=context,
                local_values=local_values,
                step_name=None if context.step_name_prefix == context.workflow_name else context.step_name_prefix,
            )
        if value.perform_kind == "workflow_call":
            return _lower_workflow_call(
                LowerableWorkflowCall(
                    callee_name=value.target_name,
                    bindings=tuple(
                        (binding_name, _frontend_expr_from_wcc_value(binding_value))
                        for binding_name, binding_value in value.keyword_args
                    ),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                result_type=binding_type,
                context=context,
                local_values=local_values,
            )
    return _lower_procedure_call(
        LowerableProcedureCall(
            callee_name=value.callee_name,
            args=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.args),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
            specialized_callee_name=value.specialized_callee_name,
        ),
        result_type=binding_type,
        context=context,
        local_values=local_values,
    )


def _frontend_expr_from_wcc_binding_value(value):
    if isinstance(value, (WccPerform, WccCall)):
        raise TypeError("effectful WCC bindings must lower through owner emitters, not rebuilt frontend expressions")
    return _frontend_expr_from_wcc_value(value)


def _frontend_expr_from_wcc_value(value: WccValue):
    if isinstance(value, WccLiteralAtom):
        return LiteralExpr(
            value=value.value,
            literal_kind=value.literal_kind,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccNameAtom):
        return NameExpr(
            name=value.name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccFieldAccessAtom):
        return FieldAccessExpr(
            base=_frontend_expr_from_wcc_value(value.base),
            fields=value.fields,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccRecordAtom):
        return RecordExpr(
            type_name=value.type_name,
            fields=tuple(
                (field_name, _frontend_expr_from_wcc_value(field_value))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccInject):
        return UnionVariantExpr(
            type_name=value.union_name,
            variant_name=value.variant_name,
            fields=tuple(
                (field_name, _frontend_expr_from_wcc_value(field_value))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    raise TypeError(f"unsupported WCC value during defunctionalization: {type(value).__name__}")
