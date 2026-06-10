"""Direct straight-line defunctionalization from WCC to lowered workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

from ..contracts import GeneratedInternalInput, derive_workflow_signature_contracts
from ..conditionals import render_condition_predicate
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    FieldAccessExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    RecordExpr,
    UnionVariantExpr,
)
from ..phase_stdlib import ProduceOneOfProducerSpec
from ..phase_family_boundary import (
    apply_phase_family_boundary_classification,
    classify_phase_family_boundary,
    record_direct_entry_phase_context_binding,
)
from ..procedures import ProcedureCatalog, ProcedureLoweringMode, TypedProcedureDef
from ..typecheck_context import TypedExpr
from ..type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef, WorkflowRefTypeRef
from ..workflows import CommandBoundaryEnvironment, ExternEnvironment, TypedWorkflowDef, WorkflowCatalog, WorkflowDef, WorkflowSignature
from ..workflow_refs import WorkflowCallableSpecialization, specialization_name
from ..workflow_refs import ResolvedWorkflowRef
from .route import LOWERING_SCHEMA_WCC
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from ..lowering import core as lowering_core
from ..lowering.context import _LoweringContext, _TerminalResult, _copy_context_with_phase_scope
from ..lowering.control_dispatch import _binding_local_value_from_terminal
from ..lowering.origins import LoweringOrigin, LoweringOriginMap, _build_validation_subject_bindings, _derive_generated_semantic_effects, _origins_with_keys, _origin_for_workflow as _origin_for_workflow_owner, _record_step_origin, _with_origin_key
from ..lowering.generated_paths import allocate_generated_result_bundle, allocation_reason
from ..lowering.phase_scope import _resolve_active_phase_scope_parts
from ..lowering.values import ProjectedPathRef, attach_provider_bundle_identity, _flatten_inline_output_refs, _procedure_signature_local_type_bindings, _resolve_inline_expr_value, _signature_local_values
from ..lowering.effects import LowerableCommandResult, LowerableProviderResult, _lower_command_result_operation, _lower_provider_result_operation
from ..lowering.phase_flow import (
    _phase_stdlib_lower_produce_one_of_impl,
    _phase_stdlib_lower_resume_or_start_impl,
    _phase_stdlib_lower_run_provider_phase_impl,
)
from ..loops import RepeatUntilEmitterInput
from ..lowering.control_loops import _emit_repeat_until_from_emitter_input
from ..lowering.procedures import LowerableProcedureCall, _private_workflow_from_procedure, _resolve_procedure_lowering, _lower_procedure_call, _rewrite_nested_sibling_step_refs
from ..lowering.workflow_calls import LowerableWorkflowCall, _lower_workflow_call
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole, derive_entrypoint_managed_write_root_allocations
from .anf import normalize_wcc_body_to_anf
from .elaborate import elaborate_typed_workflow, elaborate_typed_workflow_body
from .model import (
    WCC_M2_ROUTE_SCHEMA_VERSION,
    WCC_M3_ROUTE_SCHEMA_VERSION,
    WccBody,
    WccCall,
    WccCase,
    WccFieldAccessAtom,
    WccHalt,
    WccIf,
    WccInject,
    WccJoin,
    WccJoinParam,
    WccJump,
    WccLet,
    WccLiteralAtom,
    WccLoopContinue,
    WccLoopDone,
    WccNameAtom,
    WccOpaqueFrontendValue,
    WccPerform,
    WccPhaseScope,
    WccPhaseTargetAtom,
    WccProduceOneOfPayload,
    WccRecJoin,
    WccRecordAtom,
    WccResumeOrStartPayload,
    WccRunProviderPhasePayload,
    WccValue,
)
from .analysis import WccScopeAnalysis, analyze_wcc_body
from ..lowering.control_match import (
    _binding_terminal_for_inline_match,
    _build_match_projection_anchor_step,
    _conditional_case_outputs,
    _conditional_output_refs,
    _match_arm_local_values,
    _normalize_union_match_case_terminal,
)


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
    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
        route_schema_version=WCC_M2_ROUTE_SCHEMA_VERSION,
    )


def lower_wcc_m3_workflow_definitions(
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
    """Lower bounded same-file match workflows through WCC M3."""

    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
        route_schema_version=WCC_M3_ROUTE_SCHEMA_VERSION,
    )


def lower_wcc_m4_workflow_definitions(
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
    """Lower bounded loop workflows through WCC M4."""

    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
        route_schema_version="wcc_m4",
    )


def _lower_wcc_workflow_definitions(
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
    route_schema_version: str,
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower WCC workflows through one route-selected normalized program shape."""

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
            route_schema_version=route_schema_version,
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
    route_schema_version: str,
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

    pre_lowering_phase_family_classification = classify_phase_family_boundary(
        workflow_name=typed_workflow.definition.name,
        params=typed_workflow.signature.params,
        flattened_inputs=boundary_projection.flattened_inputs,
    )
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
        private_exec_context_bindings=[],
        generated_output_spans=origin_outputs,
        generated_path_spans={},
        generated_path_allocations=[],
        generated_semantic_effects=[],
        output_projection_metadata={},
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
        lowering_schema_version=LOWERING_SCHEMA_WCC if route_schema_version == "wcc_m4" else None,
        wcc_effect_lowerer=_lower_wcc_effect_expr,
        requires_guarded_case_step_hoist=bool(
            pre_lowering_phase_family_classification.compatibility_bridge_inputs
        ),
    )
    workflow_return_types = {
        name: workflow.signature.return_type_ref
        for name, workflow in workflows_by_name.items()
    }
    workflow_return_types.update(
        {
            name: signature.return_type_ref
            for name, signature in workflow_catalog.signatures_by_name.items()
        }
    )
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
            route_schema_version=route_schema_version,
        )
    )
    scope_analysis = analyze_wcc_body(wcc_body)
    local_values = _signature_local_values(typed_workflow)
    steps, terminal = _defunctionalize_body(
        wcc_body,
        context=context,
        local_values=local_values,
        scope_analysis=scope_analysis,
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

    phase_family_classification = apply_phase_family_boundary_classification(
        workflow_name=typed_workflow.definition.name,
        params=typed_workflow.signature.params,
        boundary_projection=context.boundary_projection,
        context=context,
    )
    record_direct_entry_phase_context_binding(
        context=context,
        typed_workflow=typed_workflow,
        generated_input_names=phase_family_classification.runtime_owned_context_inputs,
    )

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
            context=context,
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
        private_exec_context_bindings=tuple(context.private_exec_context_bindings),
        compatibility_bridge_inputs=tuple(
            name
            for name, reason in sorted(context.internal_generated_input_reasons.items())
            if reason == "compatibility_bridge"
        ),
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
    scope_analysis: WccScopeAnalysis,
    jump_target: tuple[str, tuple[WccJoinParam, ...]] | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if isinstance(body, WccLet):
        binding_type = body.bound_type_ref
        updated_locals = dict(local_values)
        binding_steps: list[dict[str, Any]] = []
        binding_hidden_inputs: dict[str, Any] = {}
        if isinstance(body.bound_value, (WccPerform, WccCall)):
            binding_context = _context_with_wcc_phase_scope(
                context,
                phase_scope=body.bound_value.metadata.phase_scope,
                local_values=updated_locals,
            )
            step_context = lowering_core._copy_context_with_step_prefix(
                binding_context,
                step_name_prefix=_binding_step_prefix(context, body.bound_name),
            )
            binding_steps, binding_terminal = _lower_effectful_binding(
                body.bound_value,
                binding_type=binding_type,
                context=step_context,
                local_values=updated_locals,
            )
            binding_hidden_inputs.update(binding_terminal.hidden_inputs)
            local_value = _binding_local_value_from_terminal(
                body.bound_value,
                binding_type=binding_type,
                binding_terminal=binding_terminal,
            )
            if (
                isinstance(body.bound_value, WccPerform)
                and body.bound_value.perform_kind == "provider_result"
                and binding_terminal.provider_bundle_identity is not None
                and isinstance(local_value, Mapping)
            ):
                local_value = attach_provider_bundle_identity(
                    local_value,
                    provider_bundle_identity=binding_terminal.provider_bundle_identity,
                )
            if local_value is not None:
                updated_locals[body.bound_name] = local_value
        else:
            binding_expr = _frontend_expr_from_wcc_binding_value(body.bound_value)
            updated_locals[body.bound_name] = _resolve_wcc_inline_expr_value(
                binding_expr,
                local_values=updated_locals,
            )
        nested_steps, nested_terminal = _defunctionalize_body(
            body.body,
            context=lowering_core._context_with_local_type_binding(
                context,
                binding_name=body.bound_name,
                binding_type=binding_type,
            ),
            local_values=updated_locals,
            scope_analysis=scope_analysis,
            jump_target=jump_target,
        )
        return [*binding_steps, *nested_steps], replace(
            nested_terminal,
            hidden_inputs={**binding_hidden_inputs, **nested_terminal.hidden_inputs},
        )

    if isinstance(body, WccCase):
        return _defunctionalize_case(
            body,
            context=context,
            local_values=local_values,
            scope_analysis=scope_analysis,
            jump_target=jump_target,
        )

    if isinstance(body, WccIf):
        return _defunctionalize_if(
            body,
            context=context,
            local_values=local_values,
            scope_analysis=scope_analysis,
            jump_target=jump_target,
        )

    if isinstance(body, WccRecJoin):
        return _defunctionalize_rec_join(
            body,
            context=context,
            local_values=local_values,
        )

    if isinstance(body, WccJoin):
        return _defunctionalize_join(
            body,
            context=context,
            local_values=local_values,
            scope_analysis=scope_analysis,
            jump_target=jump_target,
        )

    if isinstance(body, WccJump):
        return _defunctionalize_jump(
            body,
            context=context,
            local_values=local_values,
            scope_analysis=scope_analysis,
            jump_target=jump_target,
        )

    return _lower_wcc_terminal_export(
        _frontend_expr_from_wcc_value(body.result),
        type_ref=body.metadata.type_ref,
        context=context,
        local_values=local_values,
        span=body.metadata.source_span,
        form_path=body.metadata.form_path,
        message="WCC defunctionalization could not export the normalized halt value",
    )


def _defunctionalize_rec_join(
    body: WccRecJoin,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if len(body.params) != 1:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message="WCC M4 loop lowering currently supports one loop state parameter",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    param = body.params[0]
    if body.initial_state is None:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message="WCC M4 loop lowering requires an explicit initial loop state",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    loop_local_values = _materialize_wcc_record_locals(local_values)
    return _emit_repeat_until_from_emitter_input(
        RepeatUntilEmitterInput(
            max_iterations_expr=_frontend_expr_from_wcc_value(body.budget),
            initial_state_expr=_frontend_expr_from_wcc_value(body.initial_state),
            binding_name=param.name,
            body_expr=_frontend_expr_from_wcc_loop_body(body.body),
            result_type_ref=body.metadata.type_ref,
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            on_exhausted_result_expr=(
                _frontend_expr_from_wcc_loop_result_body(body.exhaustion)
                if body.exhaustion is not None
                else None
            ),
        ),
        context=context,
        local_values=loop_local_values,
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


def _guard_hoisted_case_steps(
    steps: list[dict[str, Any]],
    *,
    producer_step_name: str,
    producer_variant_ref: str,
    required_variant: str,
    include_requires_variant: bool = True,
) -> list[dict[str, Any]]:
    outer_when = {
        "compare": {
            "left": {"ref": producer_variant_ref},
            "op": "eq",
            "right": required_variant,
        }
    }
    outer_requires_variant = {
        "step": producer_step_name,
        "value": required_variant,
    }
    guarded_steps: list[dict[str, Any]] = []
    for step in steps:
        guarded_step = dict(step)
        existing_when = guarded_step.get("when")
        if existing_when is None:
            guarded_step["when"] = outer_when
        else:
            guarded_step["when"] = {
                "all_of": [outer_when, existing_when],
            }
        if include_requires_variant and "match" not in guarded_step:
            guarded_step.setdefault("requires_variant", outer_requires_variant)
        guarded_steps.append(guarded_step)
    return guarded_steps


_STRUCTURED_CONTROL_CASE_STEP_KEYS = frozenset({"if"})


def _case_steps_require_guarded_hoist(steps: list[dict[str, Any]]) -> bool:
    return any(_STRUCTURED_CONTROL_CASE_STEP_KEYS.intersection(step) for step in steps)


def _match_subject_producer_step_name(binding_terminal: _TerminalResult) -> str | None:
    if binding_terminal.step_name:
        return binding_terminal.step_name
    variant_ref = binding_terminal.output_refs.get("return__variant")
    if not isinstance(variant_ref, str):
        return None
    for prefix in ("root.steps.", "self.steps."):
        if not variant_ref.startswith(prefix):
            continue
        suffix = variant_ref.removeprefix(prefix)
        step_name, separator, remainder = suffix.partition(".artifacts.")
        if separator and step_name and remainder in {"variant", "return__variant"}:
            return step_name
    return None


def _defunctionalize_case(
    body: WccCase,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    scope_analysis: WccScopeAnalysis,
    jump_target: tuple[str, tuple[WccJoinParam, ...]] | None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    subject_expr = _frontend_expr_from_wcc_value(body.subject)
    resolved_subject = _resolve_inline_expr_value(subject_expr, local_values=local_values)
    binding_terminal = _binding_terminal_for_inline_match(resolved_subject)
    if binding_terminal is None:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_return_not_exportable",
                    message="WCC M3 lowering requires case subjects to resolve to structured match bindings",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )

    binding_name = _match_binding_name(subject_expr)
    match_step_name = f"{context.step_name_prefix}__match_{binding_name}"
    match_step_id = lowering_core._normalize_generated_step_id(match_step_name)
    producer_variant_ref = binding_terminal.output_refs.get("return__variant")
    output_contracts = lowering_core._output_contracts_for_type(
        body.metadata.type_ref,
        context=context,
        span=body.metadata.source_span,
        form_path=body.metadata.form_path,
    )
    producer_step_name = _match_subject_producer_step_name(binding_terminal)
    if producer_step_name is None or not isinstance(producer_variant_ref, str):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message="WCC M3 lowering requires case subjects with stable producer step identities",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    hoisted_steps: list[dict[str, Any]] = []
    cases: dict[str, Any] = {}
    hidden_inputs: dict[str, LoweringOrigin] = {}
    shared_union_bundle_allocation = (
        allocate_generated_result_bundle(
            context=context,
            source_expr=_frontend_expr_from_wcc_value(body.subject),
            step_name=match_step_name,
            step_id=match_step_id,
            semantic_role=GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
            stable_target="match_union_projection",
        )
        if isinstance(body.metadata.type_ref, UnionTypeRef)
        and not context.is_generated_private_workflow
        and _union_variant_fields_are_bundle_unique(body.metadata.type_ref)
        else None
    )
    for arm in body.arms:
        case_name = f"{match_step_name}__{arm.variant_name.lower()}"
        arm_context = lowering_core._copy_context_with_step_prefix(context, step_name_prefix=case_name)
        arm_steps, arm_terminal = _defunctionalize_body(
            arm.body,
            context=arm_context,
            local_values=_match_arm_local_values(
                local_values=local_values,
                binding_name=arm.binding_name,
                binding_terminal=binding_terminal,
            ),
            scope_analysis=scope_analysis,
            jump_target=jump_target,
        )
        if isinstance(body.metadata.type_ref, UnionTypeRef) and shared_union_bundle_allocation is not None:
            target_variant_name = _static_union_variant_name(arm.body)
        if (
            isinstance(body.metadata.type_ref, UnionTypeRef)
            and shared_union_bundle_allocation is not None
            and target_variant_name is not None
        ):
            arm_steps, arm_terminal = _normalize_union_match_case_terminal(
                case_name=case_name,
                case_steps=arm_steps,
                case_terminal=arm_terminal,
                result_type=body.metadata.type_ref,
                source_variant_name=target_variant_name,
                subject_union_type=body.metadata.type_ref,
                shared_bundle_input_name=shared_union_bundle_allocation.generated_input_name,
                shared_bundle_path=shared_union_bundle_allocation.concrete_path_template,
                context=context,
                span=arm.body.metadata.source_span,
                form_path=arm.body.metadata.form_path,
            )
        hoist_effectful_case_steps = bool(arm_steps) and (
            context.is_generated_private_workflow
            or context.requires_guarded_case_step_hoist
            or _case_steps_require_guarded_hoist(arm_steps)
        )
        if any("match" in step for step in arm_steps) or hoist_effectful_case_steps:
            hoisted_steps.extend(
                _guard_hoisted_case_steps(
                    arm_steps,
                    producer_step_name=producer_step_name,
                    producer_variant_ref=producer_variant_ref,
                    required_variant=arm.variant_name,
                    include_requires_variant=not hoist_effectful_case_steps,
                )
            )
            arm_steps = []
            arm_terminal = replace(arm_terminal, step_name="")
        case_outputs = _conditional_case_outputs(
            arm_terminal,
            output_contracts=output_contracts,
            span=arm.body.metadata.source_span,
            form_path=arm.body.metadata.form_path,
        )
        if not arm_steps:
            arm_steps.append(
                _build_match_projection_anchor_step(
                    match_step_name=match_step_name,
                    variant_name=arm.variant_name,
                    case_outputs=case_outputs,
                    context=context,
                    span=arm.body.metadata.source_span,
                )
            )
        hidden_inputs.update(arm_terminal.hidden_inputs)
        cases[arm.variant_name] = {
            "id": lowering_core._normalize_generated_step_id(case_name),
            "outputs": case_outputs,
            "steps": arm_steps,
        }

    step_origin = LoweringOrigin(
        span=body.metadata.source_span,
        form_path=body.metadata.form_path,
        expansion_stack=body.metadata.expansion_stack,
    )
    _record_step_origin(context, step_name=match_step_name, step_id=match_step_id, source=step_origin)
    match_step = {
        "name": match_step_name,
        "id": match_step_id,
        "match": {
            "ref": binding_terminal.output_refs["return__variant"],
            "cases": cases,
        },
    }
    return [*hoisted_steps, match_step], _TerminalResult(
        step_name=match_step_name,
        step_id=match_step_id,
        output_refs=_conditional_output_refs(
            step_name=match_step_name,
            output_contracts=output_contracts,
            result_type=body.metadata.type_ref,
        ),
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _defunctionalize_if(
    body: WccIf,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    scope_analysis: WccScopeAnalysis,
    jump_target: tuple[str, tuple[WccJoinParam, ...]] | None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    step_name = context.step_name_prefix
    step_id = lowering_core._normalize_generated_step_id(step_name)
    condition = render_condition_predicate(
        body.condition_shape,
        local_values=local_values,
    )
    output_contracts = lowering_core._output_contracts_for_type(
        body.metadata.type_ref,
        context=context,
        span=body.metadata.source_span,
        form_path=body.metadata.form_path,
    )
    then_step_name = f"{step_name}__then"
    else_step_name = f"{step_name}__else"
    then_steps, then_terminal = _defunctionalize_body(
        body.then_body,
        context=lowering_core._copy_context_with_step_prefix(context, step_name_prefix=then_step_name),
        local_values=local_values,
        scope_analysis=scope_analysis,
        jump_target=jump_target,
    )
    then_steps = [
        _rewrite_branch_local_refs_in_value(step, branch_step_prefix=then_step_name)
        for step in then_steps
    ]
    else_steps, else_terminal = _defunctionalize_body(
        body.else_body,
        context=lowering_core._copy_context_with_step_prefix(context, step_name_prefix=else_step_name),
        local_values=local_values,
        scope_analysis=scope_analysis,
        jump_target=jump_target,
    )
    else_steps = [
        _rewrite_branch_local_refs_in_value(step, branch_step_prefix=else_step_name)
        for step in else_steps
    ]
    then_terminal = _with_branch_local_refs(then_terminal, branch_step_prefix=then_step_name)
    else_terminal = _with_branch_local_refs(else_terminal, branch_step_prefix=else_step_name)
    then_outputs = _conditional_case_outputs(
        then_terminal,
        output_contracts=output_contracts,
        span=body.then_body.metadata.source_span,
        form_path=body.then_body.metadata.form_path,
    )
    else_outputs = _conditional_case_outputs(
        else_terminal,
        output_contracts=output_contracts,
        span=body.else_body.metadata.source_span,
        form_path=body.else_body.metadata.form_path,
    )
    if not then_steps:
        then_steps = [
            _build_match_projection_anchor_step(
                match_step_name=step_name,
                variant_name="then",
                case_outputs=then_outputs,
                context=context,
                span=body.then_body.metadata.source_span,
            )
        ]
    if not else_steps:
        else_steps = [
            _build_match_projection_anchor_step(
                match_step_name=step_name,
                variant_name="else",
                case_outputs=else_outputs,
                context=context,
                span=body.else_body.metadata.source_span,
            )
        ]
    step_origin = LoweringOrigin(
        span=body.metadata.source_span,
        form_path=body.metadata.form_path,
        expansion_stack=body.metadata.expansion_stack,
    )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=step_origin)
    return [
        {
            "name": step_name,
            "id": step_id,
            "if": condition,
            "then": {
                "id": lowering_core._normalize_generated_step_id(then_step_name),
                "outputs": then_outputs,
                "steps": then_steps,
            },
            "else": {
                "id": lowering_core._normalize_generated_step_id(else_step_name),
                "outputs": else_outputs,
                "steps": else_steps,
            },
        }
    ], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_conditional_output_refs(
            step_name=step_name,
            output_contracts=output_contracts,
            result_type=body.metadata.type_ref,
        ),
        output_kind="if",
        hidden_inputs={**then_terminal.hidden_inputs, **else_terminal.hidden_inputs},
    )


def _with_branch_local_refs(
    terminal: _TerminalResult,
    *,
    branch_step_prefix: str,
) -> _TerminalResult:
    root_prefix = f"root.steps.{branch_step_prefix}"
    output_refs = {
        name: (
            "self.steps." + ref.removeprefix("root.steps.")
            if isinstance(ref, str) and ref.startswith(root_prefix)
            else ref
        )
        for name, ref in terminal.output_refs.items()
    }
    return replace(terminal, output_refs=output_refs)


def _rewrite_branch_local_refs_in_value(value: Any, *, branch_step_prefix: str) -> Any:
    root_prefix = f"root.steps.{branch_step_prefix}"
    if isinstance(value, str):
        if value.startswith(root_prefix):
            return "self.steps." + value.removeprefix("root.steps.")
        return value
    if isinstance(value, list):
        return [
            _rewrite_branch_local_refs_in_value(item, branch_step_prefix=branch_step_prefix)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _rewrite_branch_local_refs_in_value(item, branch_step_prefix=branch_step_prefix)
            for item in value
        )
    if isinstance(value, Mapping):
        return {
            key: _rewrite_branch_local_refs_in_value(
                item,
                branch_step_prefix=branch_step_prefix,
            )
            for key, item in value.items()
        }
    return value


def _union_variant_fields_are_bundle_unique(result_type: UnionTypeRef) -> bool:
    variant_count = len(result_type.definition.variants)
    fields_by_name: dict[str, list[Any]] = {}
    for variant in result_type.definition.variants:
        for field in variant.fields:
            fields_by_name.setdefault(field.name, []).append(field)
    for fields in fields_by_name.values():
        if len(fields) in {1, variant_count}:
            continue
        return False
    return True


def _defunctionalize_join(
    body: WccJoin,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    scope_analysis: WccScopeAnalysis,
    jump_target: tuple[str, tuple[WccJoinParam, ...]] | None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if len(body.params) != 1:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message="WCC M3 lowering currently supports one join parameter per join point",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    param = body.params[0]
    join_steps, join_terminal = _defunctionalize_body(
        body.body,
        context=lowering_core._copy_context_with_step_prefix(
            context,
            step_name_prefix=_binding_step_prefix(context, param.name),
        ),
        local_values=local_values,
        scope_analysis=scope_analysis,
        jump_target=_join_target_from_analysis(body.join_name, body.params, scope_analysis=scope_analysis),
    )
    joined_local_values = dict(local_values)
    joined_local_value = _binding_local_value_from_terminal(
        NameExpr(
            name=param.name,
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        ),
        binding_type=param.type_ref,
        binding_terminal=join_terminal,
    )
    if joined_local_value is not None:
        joined_local_values[param.name] = joined_local_value
    continuation_steps, continuation_terminal = _defunctionalize_body(
        body.continuation,
        context=lowering_core._context_with_local_type_binding(
            context,
            binding_name=param.name,
            binding_type=param.type_ref,
        ),
        local_values=joined_local_values,
        scope_analysis=scope_analysis,
        jump_target=jump_target,
    )
    return [*join_steps, *continuation_steps], replace(
        continuation_terminal,
        hidden_inputs={**join_terminal.hidden_inputs, **continuation_terminal.hidden_inputs},
    )


def _defunctionalize_jump(
    body: WccJump,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    scope_analysis: WccScopeAnalysis,
    jump_target: tuple[str, tuple[WccJoinParam, ...]] | None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if jump_target is None or body.join_name != jump_target[0]:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message=(
                        "WCC M3 lowering rejected a branch-local value that escaped its case arm / join scope; "
                        f"jump `{body.join_name}` could not be transported at this position"
                    ),
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    params = jump_target[1]
    if len(body.args) != len(params):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message=f"WCC M3 jump `{body.join_name}` argument count did not match its join parameters",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    if len(params) != 1:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="wcc_lowering_route_unsupported",
                    message="WCC M3 lowering currently supports one join parameter per jump",
                    span=body.metadata.source_span,
                    form_path=body.metadata.form_path,
                    phase="lowering",
                ),
            )
        )
    param = params[0]
    return _lower_wcc_terminal_export(
        _frontend_expr_from_wcc_value(body.args[0]),
        type_ref=param.type_ref,
        context=context,
        local_values=local_values,
        span=body.metadata.source_span,
        form_path=body.metadata.form_path,
        message=f"WCC M3 jump `{body.join_name}` could not export join argument `{param.name}`",
    )


def _lower_resolved_union_variant_terminal(
    expr: Any,
    *,
    type_ref: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    span,
    form_path: tuple[str, ...],
) -> tuple[list[dict[str, Any]], _TerminalResult] | None:
    resolved_expr = expr
    if not isinstance(resolved_expr, UnionVariantExpr):
        resolved_expr = _resolve_inline_expr_value(expr, local_values=local_values)
    if not isinstance(resolved_expr, UnionVariantExpr):
        return None
    return lowering_core._lower_union_variant_expr(
        TypedExpr(
            expr=resolved_expr,
            type_ref=type_ref,
            span=span,
            form_path=form_path,
        ),
        context=context,
        local_values=local_values,
    )


def _lower_wcc_terminal_export(
    expr: Any,
    *,
    type_ref: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    span,
    form_path: tuple[str, ...],
    message: str,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    union_terminal = _lower_resolved_union_variant_terminal(
        expr,
        type_ref=type_ref,
        context=context,
        local_values=local_values,
        span=span,
        form_path=form_path,
    )
    if union_terminal is not None:
        return union_terminal
    output_refs = _wcc_terminal_output_refs_for_expr(
        expr,
        type_ref=type_ref,
        context=context,
        local_values=local_values,
    )
    if output_refs is None:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_return_not_exportable",
                    message=message,
                    span=span,
                    form_path=form_path,
                    phase="lowering",
                ),
            )
        )
    return [], _TerminalResult(
        step_name=context.step_name_prefix,
        step_id=lowering_core._normalize_generated_step_id(context.step_name_prefix),
        output_refs=output_refs,
        output_kind="projection",
        hidden_inputs={},
    )


def _wcc_terminal_output_refs_for_expr(
    expr: Any,
    *,
    type_ref: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> dict[str, str] | None:
    output_refs = lowering_core._inline_output_refs_for_expr(
        expr,
        type_ref=type_ref,
        local_values=local_values,
        context=context,
    )
    if output_refs is not None:
        return output_refs
    resolved_expr = _resolve_inline_expr_value(expr, local_values=local_values)
    projected_refs = _wcc_projected_output_refs_for_resolved_value(
        resolved_expr,
        type_ref=type_ref,
        context=context,
    )
    if projected_refs is not None:
        return projected_refs
    if isinstance(resolved_expr, (RecordExpr, UnionVariantExpr)):
        output_refs = lowering_core._inline_output_refs_for_expr(
            resolved_expr,
            type_ref=type_ref,
            local_values=local_values,
            context=context,
        )
        if output_refs is not None:
            return output_refs
    flattened_refs = _flatten_inline_output_refs(resolved_expr)
    if flattened_refs:
        return flattened_refs
    return None


def _wcc_projected_output_refs_for_resolved_value(
    resolved_value: Any,
    *,
    type_ref: TypeRef,
    context: _LoweringContext,
) -> dict[str, str] | None:
    if not isinstance(type_ref, RecordTypeRef):
        return None
    if not isinstance(resolved_value, Mapping):
        return None

    output_refs: dict[str, str] = {}
    for field in lowering_core.derive_workflow_boundary_fields(
        type_ref,
        generated_name="return",
        source_path=("return",),
        span=context.signature.span,
        form_path=context.signature.form_path,
    ):
        field_path = field.source_path[1:]
        leaf: Any = resolved_value
        for field_name in field_path:
            if not isinstance(leaf, Mapping):
                return None
            leaf = leaf.get(field_name)
        if isinstance(leaf, ProjectedPathRef):
            context.output_projection_metadata[field.generated_name] = {
                **dict(leaf.projection),
                "projection_id": f"{context.workflow_name}:{field.generated_name}",
                "projected_output_name": field.generated_name,
            }
            output_refs[field.generated_name] = leaf.ref
            continue
        if isinstance(leaf, str):
            output_refs[field.generated_name] = leaf
            continue
        return None
    return output_refs


def _static_union_variant_name(body: WccBody) -> str | None:
    local_variants: dict[str, str] = {}

    def resolve_value(value: WccValue) -> str | None:
        if isinstance(value, WccInject):
            return value.variant_name
        if isinstance(value, WccNameAtom):
            return local_variants.get(value.name)
        return None

    current = body
    while isinstance(current, WccLet):
        variant_name = resolve_value(current.bound_value)
        if variant_name is not None:
            local_variants[current.bound_name] = variant_name
        current = current.body
    if isinstance(current, WccHalt):
        return resolve_value(current.result)
    if isinstance(current, WccJump) and len(current.args) == 1:
        return resolve_value(current.args[0])
    return None


def _join_target_from_analysis(
    join_name: str,
    fallback_params: tuple[WccJoinParam, ...],
    *,
    scope_analysis: WccScopeAnalysis,
) -> tuple[str, tuple[WccJoinParam, ...]]:
    join_site = scope_analysis.joins_by_name.get(join_name)
    if join_site is None:
        return join_name, fallback_params
    return join_site.join_name, join_site.params


def _match_binding_name(subject_expr: Any) -> str:
    if isinstance(subject_expr, NameExpr):
        return subject_expr.name
    if isinstance(subject_expr, FieldAccessExpr) and isinstance(subject_expr.base, NameExpr):
        return subject_expr.base.name
    return "binding"


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
        if value.perform_kind in {"run_provider_phase", "produce_one_of", "resume_or_start"}:
            steps, terminal = _lower_wcc_phase_effect(
                value,
                binding_type=binding_type,
                context=context,
                local_values=local_values,
            )
            return steps, _terminal_with_union_variant_ref(terminal, binding_type=binding_type)
    return _lower_wcc_procedure_call(
        value,
        binding_type=binding_type,
        context=context,
        local_values=local_values,
    )


def _terminal_with_union_variant_ref(
    terminal: _TerminalResult,
    *,
    binding_type: TypeRef,
) -> _TerminalResult:
    if isinstance(binding_type, UnionTypeRef) and "return__variant" not in terminal.output_refs:
        return replace(
            terminal,
            output_refs={
                **terminal.output_refs,
                "return__variant": f"root.steps.{terminal.step_name}.artifacts.variant",
            },
        )
    return terminal


def _name_expr_for_wcc(name: str, value: WccPerform) -> NameExpr:
    return NameExpr(
        name=name,
        span=value.metadata.source_span,
        form_path=value.metadata.form_path,
        expansion_stack=value.metadata.expansion_stack,
    )


def _lower_wcc_phase_effect(
    value: WccPerform,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    payload = value.operation_payload
    if isinstance(payload, WccRunProviderPhasePayload):
        phase_expr = SimpleNamespace(
            phase_name=payload.phase_name,
            ctx_expr=_frontend_expr_from_wcc_value(payload.ctx_expr),
            inputs_expr=_frontend_expr_from_wcc_value(payload.inputs_expr),
            provider=_name_expr_for_wcc(payload.provider_name, value),
            prompt=_name_expr_for_wcc(payload.prompt_name, value),
            returns_type_name=value.returns_type_name or binding_type.name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
        return _phase_stdlib_lower_run_provider_phase_impl(
            TypedExpr(
                expr=phase_expr,
                type_ref=binding_type,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                effect_summary=value.metadata.effect_summary,
            ),
            context=context,
            local_values=local_values,
        )
    if isinstance(payload, WccProduceOneOfPayload):
        phase_expr = SimpleNamespace(
            ctx_expr=_frontend_expr_from_wcc_value(payload.ctx_expr),
            producer=ProduceOneOfProducerSpec(
                kind="provider",
                provider_expr=_name_expr_for_wcc(payload.provider_name, value),
                prompt_expr=_name_expr_for_wcc(payload.prompt_name, value),
                inputs=tuple(_frontend_expr_from_wcc_value(item) for item in payload.producer_inputs),
            ),
            candidates=payload.candidates,
            returns_type_name=value.returns_type_name or binding_type.name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
        return _phase_stdlib_lower_produce_one_of_impl(
            TypedExpr(
                expr=phase_expr,
                type_ref=binding_type,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                effect_summary=value.metadata.effect_summary,
            ),
            context=context,
            local_values=local_values,
        )
    if isinstance(payload, WccResumeOrStartPayload):
        phase_expr = SimpleNamespace(
            resume_name=payload.resume_name,
            ctx_expr=_frontend_expr_from_wcc_value(payload.ctx_expr),
            resume_from_expr=_frontend_expr_from_wcc_value(payload.resume_from_expr),
            valid_when=payload.valid_when,
            start_expr=payload.start_value,
            returns_type_name=value.returns_type_name or binding_type.name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
            validation_spec=payload.validation_spec,
        )
        return _phase_stdlib_lower_resume_or_start_impl(
            TypedExpr(
                expr=phase_expr,
                type_ref=binding_type,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                effect_summary=value.metadata.effect_summary,
            ),
            context=context,
            local_values=local_values,
        )
    raise TypeError(f"WCC {value.perform_kind} lowering requires a typed operation payload")


def _lower_wcc_effect_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = _resolve_inline_expr_value(typed_expr.expr, local_values=local_values)
    if isinstance(expr, (WccPerform, WccCall)):
        return _lower_effectful_binding(
            expr,
            binding_type=typed_expr.type_ref,
            context=context,
            local_values=local_values,
        )
    if isinstance(expr, ProviderResultExpr):
        steps, terminal = _lower_provider_result_operation(
            LowerableProviderResult(
                provider_name=expr.provider.name,
                prompt_name=expr.prompt.name,
                inputs=tuple(expr.inputs),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            result_type=typed_expr.type_ref,
            context=context,
            local_values=local_values,
            step_name=None if context.step_name_prefix == context.workflow_name else context.step_name_prefix,
        )
        return steps, _terminal_with_union_variant_ref(terminal, binding_type=typed_expr.type_ref)
    if isinstance(expr, CallExpr):
        steps, terminal = _lower_workflow_call(
            LowerableWorkflowCall(
                callee_name=expr.callee_name,
                bindings=tuple(expr.bindings),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            result_type=typed_expr.type_ref,
            context=context,
            local_values=local_values,
        )
        return steps, _terminal_with_union_variant_ref(terminal, binding_type=typed_expr.type_ref)
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="wcc_effect_unsupported",
                message=f"WCC default route cannot lower frontend effect `{type(expr).__name__}` through an emitter",
                span=typed_expr.span,
                form_path=typed_expr.form_path,
                phase="lowering",
            ),
        )
    )


def _lower_wcc_procedure_call(
    value: WccCall,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    procedure = context.typed_procedures.get(value.specialized_callee_name) or context.typed_procedures.get(
        value.callee_name
    )
    if procedure is None or procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
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
    if procedure.signature.name in context.active_procedure_calls:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="proc_lowering_cycle",
                    message=f"recursive procedure specialization cycle detected for `{procedure.signature.name}`",
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    phase="lowering",
                ),
            )
        )

    arg_exprs = tuple(_frontend_expr_from_wcc_value(arg) for arg in value.args)
    arg_exprs = _residual_wcc_procedure_call_args(
        arg_exprs,
        procedure=procedure,
        context=context,
        span=value.metadata.source_span,
        form_path=value.metadata.form_path,
    )
    child_locals = dict(local_values)
    if procedure.specialization is not None:
        child_locals.update(dict(getattr(procedure.specialization, "workflow_ref_bindings", {})))
        child_locals.update(dict(getattr(procedure.specialization, "proc_ref_bindings", {})))
        child_locals.update(dict(getattr(procedure.specialization, "value_bindings", {})))
    for arg_expr, (param_name, _) in zip(arg_exprs, procedure.signature.params, strict=True):
        child_locals[param_name] = _resolve_wcc_inline_expr_value(arg_expr, local_values=local_values)

    prefix_ordinal = context.inline_call_counters.get(value.callee_name, 0) + 1
    context.inline_call_counters[value.callee_name] = prefix_ordinal
    child_context = replace(
        context,
        step_name_prefix=lowering_core._inline_procedure_step_prefix(
            context=context,
            callee_name=value.callee_name,
            procedure=procedure,
            ordinal=prefix_ordinal,
        ),
        local_type_bindings={
            **dict(context.local_type_bindings),
            **_procedure_signature_local_type_bindings(procedure),
        },
        active_procedure_calls=context.active_procedure_calls | {procedure.signature.name},
    )
    workflow_return_types = {
        name: workflow.signature.return_type_ref
        for name, workflow in context.workflows_by_name.items()
    }
    workflow_return_types.update(
        {
            name: signature.return_type_ref
            for name, signature in context.workflow_catalog.signatures_by_name.items()
        }
    )
    procedure_return_types = {
        name: candidate.signature.return_type_ref
        for name, candidate in context.typed_procedures.items()
    }
    route_schema_version = value.metadata.node_id.split(":", 2)[1]
    wcc_body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            procedure.typed_body,
            owner_name=procedure.definition.name,
            type_env=context.type_env,
            value_env=_procedure_signature_local_type_bindings(procedure),
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            route_schema_version=route_schema_version,
        )
    )
    steps, terminal = _defunctionalize_body(
        wcc_body,
        context=child_context,
        local_values=child_locals,
        scope_analysis=analyze_wcc_body(wcc_body),
    )
    if isinstance(binding_type, UnionTypeRef) and "return__variant" not in terminal.output_refs and terminal.step_name:
        terminal = replace(
            terminal,
            output_refs={
                **terminal.output_refs,
                "return__variant": f"root.steps.{terminal.step_name}.artifacts.variant",
            },
        )
    _rewrite_nested_sibling_step_refs(steps)
    return steps, terminal


def _residual_wcc_procedure_call_args(
    arg_exprs: tuple[Any, ...],
    *,
    procedure: TypedProcedureDef,
    context: _LoweringContext,
    span,
    form_path: tuple[str, ...],
) -> tuple[Any, ...]:
    if len(arg_exprs) == len(procedure.signature.params):
        return arg_exprs
    specialization = procedure.specialization
    base_name = getattr(specialization, "base_name", None)
    base_procedure = context.typed_procedures.get(base_name) if isinstance(base_name, str) else None
    if base_procedure is not None and len(arg_exprs) == len(base_procedure.signature.params):
        bound_param_names = set(getattr(specialization, "bound_param_types", {}))
        bound_param_names.update(getattr(specialization, "workflow_ref_bindings", {}))
        bound_param_names.update(getattr(specialization, "proc_ref_bindings", {}))
        bound_param_names.update(getattr(specialization, "value_bindings", {}))
        residual_args = tuple(
            arg_expr
            for arg_expr, (param_name, _param_type) in zip(
                arg_exprs,
                base_procedure.signature.params,
                strict=True,
            )
            if param_name not in bound_param_names
        )
        if len(residual_args) == len(procedure.signature.params):
            return residual_args
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_arity_mismatch",
                message=(
                    f"procedure `{procedure.signature.name}` expected {len(procedure.signature.params)} "
                    f"runtime arguments during WCC lowering but got {len(arg_exprs)}"
                ),
                span=span,
                form_path=form_path,
                phase="lowering",
            ),
        )
    )


def _resolve_wcc_inline_expr_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    if isinstance(expr, RecordExpr):
        inline_value: dict[str, Any] = {}
        for field_name, field_expr in expr.fields:
            resolved_field = _resolve_wcc_inline_expr_value(field_expr, local_values=local_values)
            if resolved_field is None:
                return expr
            inline_value[field_name] = resolved_field
        return inline_value
    return _resolve_inline_expr_value(expr, local_values=local_values)


def _materialize_wcc_record_locals(local_values: Mapping[str, Any]) -> dict[str, Any]:
    materialized = dict(local_values)
    for name, value in local_values.items():
        if isinstance(value, RecordExpr):
            materialized[name] = _resolve_wcc_inline_expr_value(value, local_values=materialized)
    return materialized


def _frontend_expr_from_wcc_binding_value(value):
    if isinstance(value, (WccPerform, WccCall)):
        raise TypeError("effectful WCC bindings must lower through owner emitters, not rebuilt frontend expressions")
    return _frontend_expr_from_wcc_value(value)


def _frontend_expr_from_wcc_loop_body(body: WccBody):
    if isinstance(body, WccLet):
        return LetStarExpr(
            bindings=((body.bound_name, _frontend_expr_from_wcc_loop_binding_value(body.bound_value)),),
            body=_frontend_expr_from_wcc_loop_body(body.body),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccCase):
        return MatchExpr(
            subject=_frontend_expr_from_wcc_value(body.subject),
            arms=tuple(
                MatchArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    body=_frontend_expr_from_wcc_loop_body(arm.body),
                    span=arm.body.metadata.source_span,
                    form_path=arm.body.metadata.form_path,
                    expansion_stack=arm.body.metadata.expansion_stack,
                )
                for arm in body.arms
            ),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccIf):
        return IfExpr(
            condition_expr=_frontend_expr_from_wcc_value(body.condition),
            then_expr=_frontend_expr_from_wcc_loop_body(body.then_body),
            else_expr=_frontend_expr_from_wcc_loop_body(body.else_body),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccLoopContinue):
        if len(body.state_args) != 1:
            raise TypeError("WCC M4 loop body conversion supports one continue state argument")
        return ContinueExpr(
            state_expr=_frontend_expr_from_wcc_value(body.state_args[0]),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccLoopDone):
        return DoneExpr(
            result_expr=_frontend_expr_from_wcc_value(body.result),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccHalt):
        return _frontend_expr_from_wcc_value(body.result)
    raise TypeError(f"unsupported WCC loop body during defunctionalization: {type(body).__name__}")


def _frontend_expr_from_wcc_loop_result_body(body: WccBody):
    env: dict[str, object] = {}
    current = body
    while isinstance(current, WccLet):
        env[current.bound_name] = _frontend_expr_from_wcc_value_with_env(current.bound_value, env)
        current = current.body
    if not isinstance(current, WccHalt):
        return _frontend_expr_from_wcc_loop_body(body)
    return _frontend_expr_from_wcc_value_with_env(current.result, env)


def _frontend_expr_from_wcc_value_with_env(value: WccValue, env: Mapping[str, object]):
    if isinstance(value, WccNameAtom):
        resolved = env.get(value.name)
        if resolved is not None:
            return resolved
    if isinstance(value, WccFieldAccessAtom):
        base_expr = _frontend_expr_from_wcc_value_with_env(value.base, env)
        if isinstance(base_expr, NameExpr):
            return FieldAccessExpr(
                base=base_expr,
                fields=value.fields,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
    if isinstance(value, WccRecordAtom):
        return RecordExpr(
            type_name=value.type_name,
            fields=tuple(
                (field_name, _frontend_expr_from_wcc_value_with_env(field_value, env))
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
                (field_name, _frontend_expr_from_wcc_value_with_env(field_value, env))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    return _frontend_expr_from_wcc_value(value)


def _frontend_expr_from_wcc_loop_binding_value(value):
    if isinstance(value, WccPerform):
        if value.perform_kind == "provider_result":
            return ProviderResultExpr(
                provider=NameExpr(
                    name=value.target_name,
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                prompt=NameExpr(
                    name=value.prompt_name or "",
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                inputs=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                returns_type_name=value.returns_type_name or "",
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        if value.perform_kind == "command_result":
            return CommandResultExpr(
                step_name=value.target_name,
                argv=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                returns_type_name=value.returns_type_name or "",
                adapter_name=None,
                adapter_inputs=(),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
    if isinstance(value, WccCall):
        return ProcedureCallExpr(
            callee_name=value.callee_name,
            args=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.args),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
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
    if isinstance(value, WccPhaseTargetAtom):
        from ..expressions import PhaseTargetExpr

        return PhaseTargetExpr(
            target_name=value.target_name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccOpaqueFrontendValue):
        return value.expr
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
