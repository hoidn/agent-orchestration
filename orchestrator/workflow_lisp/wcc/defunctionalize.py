"""Direct straight-line defunctionalization from WCC to lowered workflows."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

from ..contracts import GeneratedInternalInput, derive_workflow_signature_contracts
from ..conditionals import PureExprCondition, render_condition_predicate
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    FieldAccessExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    MaterializeViewExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    PureOpExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    FinalizeSelectedItemExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
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
from orchestrator.workflow.references import MaterializeViewBindingReference
from orchestrator.workflow.view_renderer import VIEW_RENDERER_SCHEMA_VERSION, resolve_view_renderer
from ..lowering import core as lowering_core
from ..entry_publication import EntryPublicationPolicyRow, resolve_publication_role_registry
from ..lexical_checkpoint_restore import build_restore_metadata
from ..lexical_checkpoint_effect_policies import build_effect_resume_policy
from ..lexical_checkpoints import allocate_checkpoint_storage, derive_checkpoint_id, derive_program_point_id
from ..lowering.context import (
    _LoweringContext,
    _TerminalResult,
    _context_with_local_type_binding,
    _copy_context_with_phase_scope,
)
from ..lowering.control_dispatch import _binding_local_value_from_terminal
from ..lowering.origins import GeneratedSemanticEffectBinding, LoweringOrigin, LoweringOriginMap, _build_validation_subject_bindings, _derive_generated_semantic_effects, _origins_with_keys, _origin_for_workflow as _origin_for_workflow_owner, _record_step_origin, _with_origin_key
from ..lowering.generated_paths import allocate_generated_result_bundle, allocate_materialized_value_view, allocation_reason
from ..lowering.phase_scope import _resolve_active_phase_scope_parts
from ..lowering.materialize_view import lower_materialize_view_step
from ..lowering.pure_projection import is_pure_projection_expr, lower_pure_projection_step, try_evaluate_static_pure_expr
from ..lowering.values import ProjectedPathRef, attach_provider_bundle_identity, _flatten_inline_output_refs, _procedure_signature_local_type_bindings, _resolve_inline_expr_value, _signature_local_values
from ..lowering.effects import LowerableCommandResult, LowerableProviderResult, _lower_command_result_operation, _lower_provider_result_operation
from ..lowering.phase_flow import (
    _phase_stdlib_lower_produce_one_of_impl,
    _phase_stdlib_lower_resume_or_start_impl,
    _phase_stdlib_lower_run_provider_phase_impl,
)
from ..lowering.phase_resource import (
    _phase_stdlib_lower_finalize_selected_item_impl,
    _phase_stdlib_lower_resource_transition_impl,
)
from ..loops import RepeatUntilEmitterInput
from ..lowering.control_loops import _emit_repeat_until_from_emitter_input
from ..phase import eligible_private_context_source_param_names
from ..lowering.procedures import LowerableProcedureCall, _private_workflow_from_procedure, _procedure_type_env_for, _resolve_procedure_lowering, _lower_procedure_call, _rewrite_nested_sibling_step_refs
from ..lowering.workflow_calls import LowerableWorkflowCall, _lower_workflow_call
from orchestrator.workflow.state_layout import GeneratedPathPrivacy, GeneratedPathSemanticRole, derive_entrypoint_managed_write_root_allocations
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
    WccPureOp,
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


def _sha256_text(value: object) -> str:
    return f"sha256:{hashlib.sha256(str(value).encode('utf-8')).hexdigest()}"


def _sha256_json(value: object) -> str:
    return _sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _workflow_version_policy_from_path(path: Path | None) -> str:
    if path is None or not path.exists():
        return "unknown"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    if path.suffix == ".orc":
        match = re.search(r'\(:target-dsl\s+"([^"]+)"\)', text)
        return match.group(1) if match is not None else "unknown"
    for line in text.splitlines():
        if line.strip().startswith("version:"):
            _, _, value = line.partition(":")
            version = value.strip()
            if version:
                return version
    return "unknown"


def _provider_prompt_input_contract_digest(
    *,
    context: _LoweringContext,
    provider_result: LowerableProviderResult,
) -> str:
    prompt_binding = context.extern_environment.bindings_by_name.get(provider_result.prompt_name)
    provider_binding = context.extern_environment.bindings_by_name.get(provider_result.provider_name)
    prompt_payload = None
    if prompt_binding is not None:
        prompt_payload = {
            "source_kind": getattr(prompt_binding, "source_kind", None),
            "path": getattr(prompt_binding, "path", None),
        }
    provider_id = getattr(provider_binding, "provider_id", provider_result.provider_name)
    return _sha256_json(
        {
            "provider": provider_id,
            "prompt_binding": prompt_payload,
            "input_count": len(provider_result.inputs),
        }
    )


def _workflow_call_policy_metadata(
    *,
    context: _LoweringContext,
    callee_workflow: str,
) -> tuple[str, str]:
    imported_bundle = context.imported_workflow_bundles.get(callee_workflow)
    workflow_path = imported_bundle.provenance.workflow_path if imported_bundle is not None else context.workflow_path
    target_dsl_version = (
        imported_bundle.surface.version
        if imported_bundle is not None
        else _workflow_version_policy_from_path(workflow_path)
    )
    callee_checksum = (
        _sha256_bytes(workflow_path.read_bytes())
        if workflow_path is not None and workflow_path.exists()
        else _sha256_text(callee_workflow)
    )
    return target_dsl_version, callee_checksum


def lower_wcc_m2_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    available_workflows_by_name: Mapping[str, TypedWorkflowDef] | None = None,
    procedure_type_envs: Mapping[str, object],
    workflow_type_envs: Mapping[str, object] | None = None,
    procedure_catalog: ProcedureCatalog,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env,
    target_dsl_version: str = "2.14",
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded straight-line workflows through WCC M2."""
    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        available_workflows_by_name=available_workflows_by_name,
        procedure_type_envs=procedure_type_envs,
        workflow_type_envs=workflow_type_envs,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
        route_schema_version=WCC_M2_ROUTE_SCHEMA_VERSION,
        target_dsl_version=target_dsl_version,
    )


def lower_wcc_m3_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    available_workflows_by_name: Mapping[str, TypedWorkflowDef] | None = None,
    procedure_type_envs: Mapping[str, object],
    workflow_type_envs: Mapping[str, object] | None = None,
    procedure_catalog: ProcedureCatalog,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env,
    target_dsl_version: str = "2.14",
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded same-file match workflows through WCC M3."""

    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        available_workflows_by_name=available_workflows_by_name,
        procedure_type_envs=procedure_type_envs,
        workflow_type_envs=workflow_type_envs,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
        route_schema_version=WCC_M3_ROUTE_SCHEMA_VERSION,
        target_dsl_version=target_dsl_version,
    )


def lower_wcc_m4_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    available_workflows_by_name: Mapping[str, TypedWorkflowDef] | None = None,
    procedure_type_envs: Mapping[str, object],
    workflow_type_envs: Mapping[str, object] | None = None,
    procedure_catalog: ProcedureCatalog,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env,
    target_dsl_version: str = "2.14",
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded loop workflows through WCC M4."""

    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        available_workflows_by_name=available_workflows_by_name,
        procedure_type_envs=procedure_type_envs,
        workflow_type_envs=workflow_type_envs,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
        route_schema_version="wcc_m4",
        target_dsl_version=target_dsl_version,
    )


def _lower_wcc_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    available_workflows_by_name: Mapping[str, TypedWorkflowDef] | None = None,
    procedure_type_envs: Mapping[str, object],
    workflow_type_envs: Mapping[str, object] | None = None,
    procedure_catalog: ProcedureCatalog,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env,
    route_schema_version: str,
    target_dsl_version: str = "2.14",
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower WCC workflows through one route-selected normalized program shape."""

    resolved_procedures = _resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=workflow_path,
        type_env=type_env,
        procedure_type_envs=procedure_type_envs,
    )
    private_workflows = {
        procedure.generated_workflow_name: _private_workflow_from_procedure(procedure)
        for procedure in resolved_procedures.values()
        if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW
        and procedure.generated_workflow_name is not None
    }
    generated_private_workflow_type_envs = {
        procedure.generated_workflow_name: _procedure_type_env_for(
            procedure,
            procedure_type_envs=procedure_type_envs,
            default=type_env,
        )
        for procedure in resolved_procedures.values()
        if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW
        and procedure.generated_workflow_name is not None
    }
    generated_private_workflow_names = frozenset(private_workflows)
    workflows_by_name: dict[str, TypedWorkflowDef] = {
        **dict(available_workflows_by_name or {}),
        **{workflow.definition.name: workflow for workflow in typed_workflows},
        **private_workflows,
    }
    lowered_by_name: dict[str, lowering_core.LoweredWorkflow] = {}
    visiting: set[str] = set()
    specialized_workflows: dict[tuple[str, tuple[tuple[str, str], ...]], TypedWorkflowDef] = {}
    lowered_order: list[str] = []

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
                return_spec=base.definition.return_spec,
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
                allow_private_compatibility_bridge_omission=(
                    base.signature.allow_private_compatibility_bridge_omission
                ),
                allowed_hidden_context_callees=base.signature.allowed_hidden_context_callees,
                derived_hidden_context_callees=base.signature.derived_hidden_context_callees,
                entry_hidden_context_callees=base.signature.entry_hidden_context_callees,
                allowed_private_compatibility_bridge_callees=(
                    base.signature.allowed_private_compatibility_bridge_callees
                ),
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
            generated_private_workflow_type_envs=generated_private_workflow_type_envs,
            procedure_type_envs=procedure_type_envs,
            workflow_catalog=workflow_catalog,
            imported_workflow_bundles=imported_workflow_bundles,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            lowered_callees=lowered_by_name,
            type_env=generated_private_workflow_type_envs.get(
                workflow_name,
                (workflow_type_envs or {}).get(workflow_name, type_env),
            ),
            typed_procedures=resolved_procedures,
            workflows_by_name=workflows_by_name,
            ensure_workflow_lowered=lower_one,
            specialize_workflow=specialize_workflow,
            route_schema_version=route_schema_version,
            target_dsl_version=target_dsl_version,
        )
        lowered_by_name[workflow_name] = lowered
        lowered_order.append(workflow_name)
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
    for workflow_name in lowered_order:
        lowered = lowered_by_name[workflow_name]
        if workflow_name in included_names:
            continue
        ordered.append(lowered)
        included_names.add(workflow_name)
    return tuple(ordered)


def _lower_one_wcc_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    workflow_path: Path,
    generated_private_workflow_names: frozenset[str],
    generated_private_workflow_type_envs: Mapping[str, object],
    procedure_type_envs: Mapping[str, object],
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
    target_dsl_version: str = "2.14",
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
        generated_private_workflow_type_envs=generated_private_workflow_type_envs,
        procedure_type_envs=procedure_type_envs,
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
        lower_expression=lowering_core._lower_expression,
        lower_call_expr=lowering_core._lower_call_expr,
        record_step_origin=lowering_core._record_step_origin,
        normalize_generated_step_id=lowering_core._normalize_generated_step_id,
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
    lexical_checkpoint_points: list[Mapping[str, object]] = []
    steps, terminal = _defunctionalize_body(
        wcc_body,
        context=context,
        local_values=local_values,
        scope_analysis=scope_analysis,
        lexical_checkpoint_points=lexical_checkpoint_points,
    )
    steps, terminal = lowering_core._normalize_top_level_terminal(
        typed_workflow=typed_workflow,
        authored_outputs=authored_outputs,
        steps=steps,
        terminal=terminal,
        context=context,
    )

    for hidden_input_name, origin in terminal.hidden_inputs.items():
        authored_inputs[hidden_input_name] = {
            "kind": "relpath",
            "type": "relpath",
        }
        context.generated_input_spans[hidden_input_name] = origin
        context.internal_generated_input_reasons.setdefault(hidden_input_name, "managed_write_root")
    for allocation in context.generated_path_allocations:
        hidden_input_name = allocation.generated_input_name
        reason = allocation_reason(allocation)
        if not isinstance(hidden_input_name, str) or reason is None:
            continue
        authored_inputs.setdefault(
            hidden_input_name,
            {
                "kind": "relpath",
                "type": "relpath",
            },
        )
        origin = context.generated_path_spans.get(allocation.concrete_path_template)
        if origin is not None:
            context.generated_input_spans.setdefault(hidden_input_name, origin)
        context.internal_generated_input_reasons.setdefault(hidden_input_name, reason)
    for hidden_input_name, contract_definition in context.internal_generated_input_contracts.items():
        authored_inputs[hidden_input_name] = dict(contract_definition)

    phase_family_classification = apply_phase_family_boundary_classification(
        workflow_name=typed_workflow.definition.name,
        params=typed_workflow.signature.params,
        hidden_context_requirements=typed_workflow.signature.hidden_context_requirements,
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
        "version": target_dsl_version,
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
    result_guidance = lowering_core._normalized_public_result_guidance(
        typed_workflow=typed_workflow,
        type_env=type_env,
    )
    if result_guidance:
        authored_mapping["result_guidance"] = result_guidance
    authored_mapping["steps"] = _append_entry_publication_steps(
        typed_workflow=typed_workflow,
        terminal=terminal,
        steps=list(authored_mapping["steps"]),
        context=context,
    )
    if context.top_level_artifacts:
        authored_mapping["artifacts"] = dict(context.top_level_artifacts)

    lowering_core._canonicalize_match_case_sibling_refs(authored_mapping)

    generated_semantic_effects = _derive_generated_semantic_effects(
        authored_mapping.get("steps"),
        context=context,
        workflow_origin=workflow_origin,
    )
    runtime_proof_nested_structured_step_names, runtime_proof_shared_validation_parent_ref_allowances, runtime_proof_executable_parent_ref_allowances = lowering_core._runtime_proof_allowances(
        authored_mapping,
        step_origins=context.step_spans,
        is_generated_private_workflow=is_generated_private_workflow,
    )
    origin_map = LoweringOriginMap(
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
            extra_bindings=context.generated_contract_field_bindings,
        ),
        generated_semantic_effects=generated_semantic_effects,
    )
    emitted_step_ids = {
        step_id
        for step in _walk_authored_steps(authored_mapping.get("steps"))
        for step_id in (step.get("id"),)
        if isinstance(step_id, str)
    }
    lexical_checkpoint_points = [
        point
        for point in lexical_checkpoint_points
        if isinstance(point.get("step_id"), str) and point.get("step_id") in emitted_step_ids
    ]
    return lowering_core.LoweredWorkflow(
        typed_workflow=typed_workflow,
        authored_mapping=authored_mapping,
        origin_map=origin_map,
        boundary_projection=finalized_projection,
        is_generated_private_workflow=is_generated_private_workflow,
        private_exec_context_bindings=tuple(context.private_exec_context_bindings),
        compatibility_bridge_inputs=tuple(
            name
            for name, reason in sorted(context.internal_generated_input_reasons.items())
            if reason == "compatibility_bridge"
        ),
        lexical_checkpoint_points=tuple(lexical_checkpoint_points),
        generated_path_allocations=tuple(context.generated_path_allocations),
        private_artifact_ids=tuple(
            name
            for name, definition in context.top_level_artifacts.items()
            if isinstance(name, str) and isinstance(definition, Mapping) and definition.get("kind") == "collection"
        ),
        runtime_proof_nested_structured_step_names=runtime_proof_nested_structured_step_names,
        runtime_proof_shared_validation_parent_ref_allowances=runtime_proof_shared_validation_parent_ref_allowances,
        runtime_proof_executable_parent_ref_allowances=runtime_proof_executable_parent_ref_allowances,
        generated_repeat_until_on_exhausted_refs=(
            lowering_core._capture_generated_repeat_until_on_exhausted_refs(authored_mapping)
        ),
    )


def _append_entry_publication_steps(
    *,
    typed_workflow: TypedWorkflowDef,
    terminal: _TerminalResult,
    steps: list[dict[str, Any]],
    context: _LoweringContext,
) -> list[dict[str, Any]]:
    policy = typed_workflow.definition.publication_policy
    if policy is None or not isinstance(typed_workflow.signature.return_type_ref, UnionTypeRef):
        return steps
    variant_ref = terminal.output_refs.get("return__variant")
    if not isinstance(variant_ref, str):
        return steps

    role_registry = resolve_publication_role_registry()
    cases: dict[str, dict[str, Any]] = {}
    for variant_index, variant in enumerate(typed_workflow.signature.return_type_ref.definition.variants):
        rows = [row for row in policy.rows if row.variant == variant.name]
        cases[variant.name] = {
            "id": lowering_core._normalize_generated_step_id(
                f"{typed_workflow.definition.name}__publish__{variant.name.lower()}"
            ),
            "steps": (
                [
                    _entry_publication_materialize_step(
                        typed_workflow=typed_workflow,
                        row=row,
                        variant_field_names=tuple(field.name for field in variant.fields),
                        terminal=terminal,
                        context=context,
                        role_descriptor=role_registry[row.role],
                    )
                    for row in rows
                ]
                if rows
                else [
                    _entry_publication_noop_step(
                        typed_workflow=typed_workflow,
                        terminal=terminal,
                        context=context,
                        case_ordinal=variant_index,
                    )
                ]
            ),
        }

    step_name = f"{typed_workflow.definition.name}__publish_boundary"
    step_id = lowering_core._normalize_generated_step_id(step_name)
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=policy)
    return [
        *steps,
        {
            "name": step_name,
            "id": step_id,
            "match": {
                "ref": variant_ref,
                "cases": cases,
            },
        },
    ]


def _entry_publication_materialize_step(
    *,
    typed_workflow: TypedWorkflowDef,
    row: EntryPublicationPolicyRow,
    variant_field_names: tuple[str, ...],
    terminal: _TerminalResult,
    context: _LoweringContext,
    role_descriptor: Mapping[str, object],
) -> dict[str, Any]:
    renderer_id = row.renderer_id or str(role_descriptor["renderer_id"])
    renderer_version = row.renderer_version or int(role_descriptor["renderer_version"])
    renderer = resolve_view_renderer(renderer_id, renderer_version)
    step_name = (
        f"{typed_workflow.definition.name}__publish__{row.variant.lower()}__"
        f"{_publication_slug(row.role)}"
    )
    step_id = lowering_core._normalize_generated_step_id(step_name)
    source = SimpleNamespace(
        span=row.span,
        form_path=row.form_path,
        expansion_stack=row.expansion_stack,
    )
    target_field_name = role_descriptor.get("runtime_target_field")
    target_output_ref = (
        terminal.output_refs.get(f"return__{row.role}__{target_field_name}")
        if isinstance(target_field_name, str)
        and row.role in variant_field_names
        else None
    )
    descriptor_path_template = role_descriptor.get("path_template")
    use_descriptor_target = row.role in variant_field_names
    target_path_template = (
        str(descriptor_path_template)
        if isinstance(descriptor_path_template, str)
        and descriptor_path_template
        and use_descriptor_target
        else (
            f"artifacts/work/workflow_lisp_entry_publication/"
            f"{_publication_slug(typed_workflow.definition.name)}/"
            f"{row.variant.lower()}-{_publication_slug(row.role)}{renderer.file_extension}"
        )
    )
    runtime_target_path: Any = target_path_template
    if isinstance(target_output_ref, str):
        runtime_target_path = {"ref": target_output_ref}
    allocation = allocate_materialized_value_view(
        context=context,
        source_expr=source,
        path_template=target_path_template,
        stable_target=f"entry-publication-{row.variant.lower()}-{_publication_slug(row.role)}",
        privacy=GeneratedPathPrivacy.PUBLIC_ARTIFACT,
    )
    origin = LoweringOrigin(
        span=row.span,
        form_path=row.form_path,
        expansion_stack=row.expansion_stack,
    )
    context.generated_path_spans[allocation.concrete_path_template] = origin
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=source)
    value_document: dict[str, Any] = {
        "variant": MaterializeViewBindingReference(
            ref=str(terminal.output_refs["return__variant"])
        )
    }
    for field_name in variant_field_names:
        output_ref = terminal.output_refs.get(f"return__{field_name}")
        if isinstance(output_ref, str):
            value_document[field_name] = MaterializeViewBindingReference(ref=output_ref)

    context.generated_semantic_effects.append(
        GeneratedSemanticEffectBinding(
            effect_key=f"materialize_view:{step_id}",
            step_id=step_id,
            effect_kind="materialize_view",
            origin=context.step_spans[step_id],
            details={
                "renderer_id": renderer_id,
                "renderer_version": renderer_version,
                "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
                "value_type": {
                    "kind": "union_variant",
                    "name": typed_workflow.signature.return_type_ref.name,
                    "variant": row.variant,
                    "fields": list(variant_field_names),
                },
                "target_path": allocation.concrete_path_template,
                "target_allocation_id": allocation.allocation_id,
                "authority_class": "public_artifact",
                "publication_role": row.role,
            },
        )
    )
    return {
        "name": step_name,
        "id": step_id,
        "materialize_view": {
            "renderer_id": renderer_id,
            "renderer_version": renderer_version,
            "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
            "value_type": {
                "kind": "union_variant",
                "name": typed_workflow.signature.return_type_ref.name,
                "variant": row.variant,
                "fields": list(variant_field_names),
            },
            "value_document": value_document,
            "target_path": runtime_target_path,
            "target_allocation_id": allocation.allocation_id,
            "authority_class": "public_artifact",
            "output_contracts": {"return": dict(role_descriptor["output_contract"])},
            "publication": {
                "schema_version": typed_workflow.definition.publication_policy.schema_version,
                "row_id": row.row_id,
                "role": row.role,
                "variant": row.variant,
                "workflow_name": typed_workflow.definition.name,
                "entry_boundary_only": True,
            },
        },
    }


def _entry_publication_noop_step(
    *,
    typed_workflow: TypedWorkflowDef,
    terminal: _TerminalResult,
    context: _LoweringContext,
    case_ordinal: int,
) -> dict[str, Any]:
    variant_ref = terminal.output_refs.get("return__variant")
    if not isinstance(variant_ref, str):
        raise ValueError("entry publication no-op step requires return__variant ref")
    step_name = f"{typed_workflow.definition.name}__publish__omitted_{case_ordinal}"
    step_id = lowering_core._normalize_generated_step_id(step_name)
    source = typed_workflow.definition.publication_policy or typed_workflow.definition
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=source)
    return {
        "name": step_name,
        "id": step_id,
        "assert": {
            "compare": {
                "left": {"ref": variant_ref},
                "op": "eq",
                "right": {"ref": variant_ref},
            }
        },
    }


def _publication_slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-") or "publication"


def _binding_schema_digest_for_point(
    *,
    workflow_name: str,
    point_kind: str,
    step_id: str,
    type_ref: TypeRef,
    form_path: tuple[str, ...],
) -> str:
    return _sha256_json(
        {
            "workflow_name": workflow_name,
            "point_kind": point_kind,
            "step_id": step_id,
            "type_ref": repr(type_ref),
            "form_path": form_path,
        }
    )


def _base_checkpoint_point_payload(
    *,
    workflow_name: str,
    point_kind: str,
    step_id: str,
    step_kind: str,
    origin_key: str,
    route_schema_version: str,
    wcc_node_id: str,
    wcc_scope_id: str,
    binding_schema_digest: str,
    storage_scope: str,
) -> Mapping[str, object]:
    program_point_id = derive_program_point_id(
        workflow_name=workflow_name,
        point_kind=point_kind,
        origin_key=origin_key,
        identity_digest=_sha256_json(
            {
                "wcc_node_id": wcc_node_id,
                "wcc_scope_id": wcc_scope_id,
                "step_id": step_id,
                "storage_scope": storage_scope,
            }
        ),
    )
    checkpoint_id = derive_checkpoint_id(
        workflow_name=workflow_name,
        program_point_id=program_point_id,
        executable_identity=f"{wcc_node_id}:{step_id}" if point_kind == "effect_boundary" else f"{wcc_scope_id}:{step_id}",
        lowering_schema_version=route_schema_version,
        storage_scope=storage_scope,
    )
    record_allocation = allocate_checkpoint_storage(
        workflow_name=workflow_name,
        checkpoint_id=checkpoint_id,
        semantic_role=GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD.value,
        storage_scope=storage_scope,
    )
    return MappingProxyType(
        {
            "checkpoint_id": checkpoint_id,
            "program_point_id": program_point_id,
            "point_kind": point_kind,
            "workflow_name": workflow_name,
            "step_id": step_id,
            "origin_key": origin_key,
            "step_kind": step_kind,
            "wcc_identity": {
                "node_id_digest": _sha256_text(wcc_node_id),
                "scope_id_digest": _sha256_text(wcc_scope_id),
            },
            "runtime_program_identity": {
                "lowering_schema_version": route_schema_version,
                "wcc_node_id": wcc_node_id,
                "wcc_scope_id": wcc_scope_id,
            },
            "executable_identity": {
                "step_id": step_id,
            },
            "binding_schema": {
                "schema_digest": binding_schema_digest,
                "bindings": [],
            },
            "storage": {
                "allocation_id": record_allocation.allocation_id,
                "semantic_role": "lexical_checkpoint_record",
                "privacy": "runtime_sidecar",
                "resume_scope": storage_scope,
            },
        }
    )


def _walk_authored_steps(raw_steps: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(raw_steps, list):
        return ()
    steps: list[Mapping[str, object]] = []
    for step in raw_steps:
        if not isinstance(step, Mapping):
            continue
        steps.append(step)
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, Mapping):
            steps.extend(_walk_authored_steps(repeat_until.get("steps")))
        then_block = step.get("then")
        else_block = step.get("else")
        if isinstance(then_block, Mapping):
            steps.extend(_walk_authored_steps(then_block.get("steps")))
        if isinstance(else_block, Mapping):
            steps.extend(_walk_authored_steps(else_block.get("steps")))
        match_block = step.get("match")
        if isinstance(match_block, Mapping):
            cases = match_block.get("cases")
            if isinstance(cases, Mapping):
                for case in cases.values():
                    if isinstance(case, Mapping):
                        steps.extend(_walk_authored_steps(case.get("steps")))
    return tuple(steps)


def _type_ref_name(type_ref: TypeRef | None) -> str:
    if isinstance(type_ref, (PrimitiveTypeRef, PathTypeRef, RecordTypeRef, UnionTypeRef)):
        return type_ref.name
    return repr(type_ref)


def _local_value_source_step_name(local_value: Any) -> str | None:
    if isinstance(local_value, str):
        match = re.match(r"^(?:root|self|parent)\.steps\.(?P<step_name>.+?)\.artifacts\.", local_value)
        if match is not None:
            return match.group("step_name")
        return None
    if isinstance(local_value, Mapping):
        step_names = {
            step_name
            for value in local_value.values()
            for step_name in (_local_value_source_step_name(value),)
            if isinstance(step_name, str) and step_name
        }
        if len(step_names) == 1:
            return next(iter(step_names))
    return None


def _match_subject_from_step_name(step_name: str) -> str | None:
    _, marker, subject_binding = step_name.rpartition("__match_")
    if marker != "__match_" or not subject_binding:
        return None
    return subject_binding


def _origin_key_for_step(
    *,
    context: _LoweringContext,
    step_name: str,
    step_id: str,
) -> str:
    origin = context.step_spans.get(step_id)
    if origin is None:
        origin = context.step_spans.get(step_name)
    if isinstance(origin, LoweringOrigin):
        return _with_origin_key(
            origin,
            workflow_name=context.workflow_name,
            entity_kind="step_id",
            subject_name=step_id,
        ).origin_key
    return f"{context.workflow_name}::step_id::{step_id}"


def _collect_restore_match_descriptors(
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, str], ...]]:
    binding_descriptors: list[dict[str, str]] = []
    proof_descriptors: list[dict[str, str]] = []
    seen_proof_sources: set[str] = set()
    signature_param_names = {
        name
        for name in context.authored_input_contracts
        if isinstance(name, str) and name
    }

    for binding_name, local_value in sorted(local_values.items()):
        if not isinstance(binding_name, str) or not binding_name or binding_name.startswith("__"):
            continue
        if binding_name in signature_param_names:
            continue
        if isinstance(local_value, Mapping) and "__lowering_returned_union_type" in local_value:
            continue
        value_document = _binding_restore_value_document(local_value)
        if value_document is None:
            continue
        source_step_name = _local_value_source_step_name(local_value)
        binding_step_name = _binding_step_prefix(context, binding_name)
        if (
            isinstance(local_value, str)
            and isinstance(source_step_name, str)
            and not source_step_name.endswith("__match_decision")
            and source_step_name != binding_step_name
        ):
            continue
        descriptor = {
            "binding_name": binding_name,
            "binding_kind": "pure_binding",
            "type_ref": _type_ref_name(context.local_type_bindings.get(binding_name)),
            "source_map_origin_key": f"{context.workflow_name}::binding::{binding_name}",
            "value_document": value_document,
        }
        source_step_id = None
        if isinstance(source_step_name, str) and source_step_name:
            source_step_id = lowering_core._normalize_generated_step_id(source_step_name)
            descriptor["source_step_name"] = source_step_name
            descriptor["source_step_id"] = source_step_id
            descriptor["source_map_origin_key"] = _origin_key_for_step(
                context=context,
                step_name=source_step_name,
                step_id=source_step_id,
            )
        binding_descriptors.append(descriptor)

        if not isinstance(source_step_name, str) or not source_step_name.endswith("__match_decision"):
            continue

        if source_step_id in seen_proof_sources:
            continue
        subject_binding = _match_subject_from_step_name(source_step_name)
        subject_type = context.local_type_bindings.get(subject_binding) if isinstance(subject_binding, str) else None
        if not isinstance(subject_binding, str) or not subject_binding:
            continue
        proof_descriptors.append(
            {
                "proof_id": f"proof:{context.workflow_name}:{source_step_id}",
                "subject_binding": subject_binding,
                "union_type": _type_ref_name(subject_type),
                "proof_source": source_step_id,
                "source_step_name": source_step_name,
                "source_step_id": source_step_id,
                "source_map_origin_key": descriptor["source_map_origin_key"],
            }
        )
        seen_proof_sources.add(source_step_id)

    return tuple(binding_descriptors), tuple(proof_descriptors)


def _binding_restore_value_document(local_value: Any) -> Any | None:
    if isinstance(local_value, ProjectedPathRef):
        return {"ref": local_value.ref}
    if isinstance(local_value, LiteralExpr):
        return local_value.value
    if isinstance(local_value, str):
        if local_value.startswith(("root.steps.", "self.steps.", "parent.steps.")):
            return {"ref": local_value}
        return local_value
    if local_value is None or isinstance(local_value, (int, float, bool)):
        return local_value
    if isinstance(local_value, Mapping):
        document: dict[str, Any] = {}
        for key, value in local_value.items():
            nested = _binding_restore_value_document(value)
            if nested is None:
                return None
            document[str(key)] = nested
        return document
    if isinstance(local_value, (list, tuple)):
        document_list: list[Any] = []
        for item in local_value:
            nested = _binding_restore_value_document(item)
            if nested is None:
                return None
            document_list.append(nested)
        return document_list
    return None


def _loop_frame_restore_descriptor(
    *,
    context: _LoweringContext,
    body: WccRecJoin,
    repeat_step_name: str,
    repeat_step_id: str,
) -> dict[str, str]:
    state_param = body.params[0] if body.params else WccJoinParam(name="state", type_ref=body.metadata.type_ref)
    return {
        "loop_name": repeat_step_name,
        "loop_site_id": f"loop:{_sha256_text(body.metadata.scope_id)[len('sha256:'):]}",
        "state_binding_name": state_param.name,
        "state_type_ref": _type_ref_name(state_param.type_ref),
        "source_map_origin_key": _origin_key_for_step(
            context=context,
            step_name=repeat_step_name,
            step_id=repeat_step_id,
        ),
    }


def _effect_boundary_step_kind(value: WccPerform | WccCall) -> str:
    if isinstance(value, WccCall):
        return "call"
    if (
        value.perform_kind == "resource_transition"
        and isinstance(value.operation_payload, ResourceTransitionExpr)
        and value.operation_payload.spec.mode != "declared_transition"
    ):
        return "command"
    return {
        "command_result": "command",
        "provider_result": "provider",
        "workflow_call": "call",
        "materialize_view": "materialize_view",
        "resource_transition": "resource_transition",
        "resume_or_start": "resume_or_start",
        "run_provider_phase": "provider",
        "produce_one_of": "provider",
        "finalize_selected_item": "finalize_selected_item",
    }.get(value.perform_kind, value.perform_kind)


def _build_effect_resume_policy_payload(
    *,
    context: _LoweringContext,
    step_kind: str,
    step_id: str,
    origin_key: str,
    binding_schema_digest: str,
    value: WccPerform | WccCall | None,
    terminal: _TerminalResult,
) -> Mapping[str, Any]:
    if step_kind == "pure_projection":
        return build_effect_resume_policy(
            policy_kind="recompute_or_reuse_checkpoint",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={},
        )
    if step_kind == "provider":
        bundle_identity = dict(terminal.provider_bundle_identity or {})
        prompt_input_contract_digest = _sha256_text(step_id)
        payload = value.operation_payload if isinstance(value, WccPerform) else None
        if isinstance(payload, LowerableProviderResult):
            prompt_input_contract_digest = _provider_prompt_input_contract_digest(
                context=context,
                provider_result=payload,
            )
        return build_effect_resume_policy(
            policy_kind="reuse_validated_structured_output",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={
                "structured_output": {
                    "bundle_path_ref": str(
                        bundle_identity.get("bundle_path_ref") or f"generated:provider_result_bundle:{step_id}"
                    ),
                    "contract_digest": str(bundle_identity.get("allocation_id") or binding_schema_digest),
                    "prompt_input_contract_digest": prompt_input_contract_digest,
                    "payload_digest_required": True,
                    "declared_target_only": True,
                }
            },
        )
    if step_kind == "command":
        payload = value.operation_payload if isinstance(value, WccPerform) else None
        adapter_name = None
        if isinstance(payload, LowerableCommandResult):
            adapter_name = payload.adapter_name
        elif isinstance(payload, ResourceTransitionExpr) and payload.spec.mode != "declared_transition":
            adapter_name = "apply_resource_transition"
        elif isinstance(payload, Mapping):
            raw_adapter_name = payload.get("adapter_name")
            if isinstance(raw_adapter_name, str) and raw_adapter_name:
                adapter_name = raw_adapter_name
        boundary_kind = step_kind
        evidence_requirements: dict[str, Any] = {
            "structured_output": {
                "bundle_path_ref": f"generated:command_result_bundle:{step_id}",
                "contract_digest": binding_schema_digest,
                "payload_digest_required": True,
                "declared_target_only": True,
            }
        }
        unsafe_pending_behavior = "fail_closed"
        policy_kind = "reuse_validated_structured_output"
        if adapter_name:
            boundary_kind = "certified_adapter"
            evidence_requirements["command_resume_protocol"] = {
                "protocol_name": adapter_name,
            }
            unsafe_pending_behavior = "requires_certified_resume_protocol"
            policy_kind = "certified_resume_protocol_required"
        return build_effect_resume_policy(
            policy_kind=policy_kind,
            effect_kind=step_kind,
            boundary_kind=boundary_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements=evidence_requirements,
            unsafe_pending_behavior=unsafe_pending_behavior,
        )
    if step_kind == "call":
        callee_workflow = None
        if isinstance(value, WccCall):
            callee_workflow = value.specialized_callee_name or value.callee_name
        target_dsl_version, callee_checksum = _workflow_call_policy_metadata(
            context=context,
            callee_workflow=callee_workflow or step_id,
        )
        return build_effect_resume_policy(
            policy_kind="reuse_validated_workflow_call",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={
                "workflow_call": {
                    "callee_workflow": callee_workflow or step_id,
                    "target_dsl_version": target_dsl_version,
                    "callee_checksum": callee_checksum,
                }
            },
        )
    if step_kind == "materialize_view":
        payload = value.operation_payload if isinstance(value, WccPerform) else None
        renderer_id = payload.renderer_id if isinstance(payload, MaterializeViewExpr) else "renderer"
        policy_kind = (
            "preserve_durable_view"
            if isinstance(payload, MaterializeViewExpr) and payload.target_expr is not None
            else "regenerate_deterministic_view"
        )
        return build_effect_resume_policy(
            policy_kind=policy_kind,
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={
                "materialized_view": {
                    "renderer_id": renderer_id,
                }
            },
        )
    if step_kind == "resource_transition":
        payload = value.operation_payload if isinstance(value, WccPerform) else None
        transition_identity = step_id
        if isinstance(payload, ResourceTransitionExpr):
            transition_identity = (
                payload.spec.transition_name
                or payload.spec.transition_ref_name
                or step_id
            )
        return build_effect_resume_policy(
            policy_kind="transition_idempotent_audit_required",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={
                "transition": {
                    "transition_identity": transition_identity,
                }
            },
            unsafe_pending_behavior="audit_barrier",
        )
    return build_effect_resume_policy(
        policy_kind="recompute_or_reuse_checkpoint",
        effect_kind=step_kind,
        boundary_kind=step_kind,
        step_id=step_id,
        source_map_origin_key=origin_key,
        evidence_requirements={},
    )


def _effect_boundary_checkpoint_point_payload(
    *,
    workflow_name: str,
    value: WccPerform | WccCall,
    terminal: _TerminalResult,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> Mapping[str, object]:
    step_kind = _effect_boundary_step_kind(value)
    origin_key = _with_origin_key(
        LoweringOrigin(
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        ),
        workflow_name=workflow_name,
        entity_kind="step_id",
        subject_name=terminal.step_id,
    ).origin_key
    binding_schema_digest = _binding_schema_digest_for_point(
        workflow_name=workflow_name,
        point_kind="effect_boundary",
        step_id=terminal.step_id,
        type_ref=value.metadata.type_ref,
        form_path=value.metadata.form_path,
    )
    payload = dict(
        _base_checkpoint_point_payload(
            workflow_name=workflow_name,
            point_kind="effect_boundary",
            step_id=terminal.step_id,
            step_kind=step_kind,
            origin_key=_sha256_text(value.metadata.source_span) if False else "",
            route_schema_version=value.metadata.node_id.split(":", 2)[1],
            wcc_node_id=value.metadata.node_id,
            wcc_scope_id=value.metadata.scope_id,
            binding_schema_digest=binding_schema_digest,
            storage_scope="step_visit",
        )
    )
    payload["origin_key"] = origin_key
    effect_policy = _build_effect_resume_policy_payload(
        context=context,
        step_kind=step_kind,
        step_id=terminal.step_id,
        origin_key=origin_key,
        binding_schema_digest=binding_schema_digest,
        value=value,
        terminal=terminal,
    )
    payload["effect_boundary"] = {
        "effect_kind": step_kind,
        "boundary_kind": effect_policy.get("boundary_kind", step_kind),
        "policy": effect_policy,
    }
    payload["loop_back_edge"] = None
    binding_descriptors, proof_descriptors = _collect_restore_match_descriptors(
        context=context,
        local_values=local_values,
    )
    payload["restore"] = build_restore_metadata(
        binding_descriptors=binding_descriptors,
        proof_descriptors=proof_descriptors,
    )
    return MappingProxyType(payload)


def _pure_projection_checkpoint_point_payload(
    *,
    workflow_name: str,
    let_binding: WccLet,
    terminal: _TerminalResult,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> Mapping[str, object]:
    origin_key = _with_origin_key(
        LoweringOrigin(
            span=let_binding.metadata.source_span,
            form_path=let_binding.metadata.form_path,
            expansion_stack=let_binding.metadata.expansion_stack,
        ),
        workflow_name=workflow_name,
        entity_kind="step_id",
        subject_name=terminal.step_id,
    ).origin_key
    binding_schema_digest = _binding_schema_digest_for_point(
        workflow_name=workflow_name,
        point_kind="effect_boundary",
        step_id=terminal.step_id,
        type_ref=let_binding.bound_type_ref,
        form_path=let_binding.metadata.form_path,
    )
    payload = dict(
        _base_checkpoint_point_payload(
            workflow_name=workflow_name,
            point_kind="effect_boundary",
            step_id=terminal.step_id,
            step_kind="pure_projection",
            origin_key=_sha256_text(let_binding.metadata.source_span) if False else "",
            route_schema_version=let_binding.metadata.node_id.split(":", 2)[1],
            wcc_node_id=let_binding.metadata.node_id,
            wcc_scope_id=let_binding.metadata.scope_id,
            binding_schema_digest=binding_schema_digest,
            storage_scope="step_visit",
        )
    )
    payload["origin_key"] = origin_key
    payload["effect_boundary"] = {
        "effect_kind": "pure_projection",
        "boundary_kind": "pure_projection",
        "policy": _build_effect_resume_policy_payload(
            context=context,
            step_kind="pure_projection",
            step_id=terminal.step_id,
            origin_key=origin_key,
            binding_schema_digest=binding_schema_digest,
            value=None,
            terminal=terminal,
        ),
    }
    payload["loop_back_edge"] = None
    binding_descriptors, proof_descriptors = _collect_restore_match_descriptors(
        context=context,
        local_values=local_values,
    )
    payload["restore"] = build_restore_metadata(
        binding_descriptors=binding_descriptors,
        proof_descriptors=proof_descriptors,
    )
    return MappingProxyType(payload)


def _loop_back_edge_checkpoint_point_payload(
    *,
    workflow_name: str,
    body: WccRecJoin,
    repeat_step_name: str,
    repeat_step_id: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> Mapping[str, object]:
    payload = dict(
        _base_checkpoint_point_payload(
            workflow_name=workflow_name,
            point_kind="loop_back_edge",
            step_id=repeat_step_id,
            step_kind="repeat_until",
            origin_key="",
            route_schema_version=body.metadata.node_id.split(":", 2)[1],
            wcc_node_id=body.metadata.node_id,
            wcc_scope_id=body.metadata.scope_id,
            binding_schema_digest=_binding_schema_digest_for_point(
                workflow_name=workflow_name,
                point_kind="loop_back_edge",
                step_id=repeat_step_id,
                type_ref=body.metadata.type_ref,
                form_path=body.metadata.form_path,
            ),
            storage_scope="loop_frame",
        )
    )
    payload["origin_key"] = _with_origin_key(
        LoweringOrigin(
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        ),
        workflow_name=workflow_name,
        entity_kind="step_id",
        subject_name=repeat_step_id,
    ).origin_key
    payload["effect_boundary"] = None
    payload["loop_back_edge"] = {
        "loop_name": body.loop_name,
        "state_param_schema_digest": _sha256_json([param.name for param in body.params]),
        "policy_status": "shadow_record_only",
    }
    binding_descriptors, proof_descriptors = _collect_restore_match_descriptors(
        context=context,
        local_values=local_values,
    )
    payload["restore"] = build_restore_metadata(
        binding_descriptors=binding_descriptors,
        proof_descriptors=proof_descriptors,
        loop_frame_descriptor=_loop_frame_restore_descriptor(
            context=context,
            body=body,
            repeat_step_name=repeat_step_name,
            repeat_step_id=repeat_step_id,
        ),
    )
    return MappingProxyType(payload)


def _defunctionalize_body(
    body: WccBody,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    scope_analysis: WccScopeAnalysis,
    lexical_checkpoint_points: list[Mapping[str, object]] | None = None,
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
                lexical_checkpoint_points=lexical_checkpoint_points,
            )
            if lexical_checkpoint_points is not None:
                lexical_checkpoint_points.append(
                    _effect_boundary_checkpoint_point_payload(
                        workflow_name=context.workflow_name,
                        value=body.bound_value,
                        terminal=binding_terminal,
                        context=context,
                        local_values=updated_locals,
                    )
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
            resolved_binding = _resolve_wcc_inline_expr_value(
                binding_expr,
                local_values=updated_locals,
            )
            if (
                isinstance(binding_expr, IfExpr)
                and resolved_binding is not None
                and not isinstance(resolved_binding, (str, Mapping))
                and is_pure_projection_expr(resolved_binding)
            ):
                binding_step_name = _binding_step_prefix(context, body.bound_name)
                binding_step_id = lowering_core._normalize_generated_step_id(binding_step_name)
                lowered_projection = lower_pure_projection_step(
                    resolved_binding,
                    result_type=binding_type,
                    context=context,
                    local_values=updated_locals,
                    step_name=binding_step_name,
                    step_id=binding_step_id,
                    stable_target="binding_projection",
                )
                binding_steps = [lowered_projection.step]
                binding_terminal = _TerminalResult(
                    step_name=binding_step_name,
                    step_id=binding_step_id,
                    output_refs=lowered_projection.output_refs,
                    output_kind="projection",
                    hidden_inputs={},
                )
                if lexical_checkpoint_points is not None:
                    lexical_checkpoint_points.append(
                        _pure_projection_checkpoint_point_payload(
                            workflow_name=context.workflow_name,
                            let_binding=body,
                            terminal=binding_terminal,
                            context=context,
                            local_values=updated_locals,
                        )
                    )
                binding_hidden_inputs.update(binding_terminal.hidden_inputs)
                updated_locals[body.bound_name] = _binding_local_value_from_terminal(
                    binding_expr,
                    binding_type=binding_type,
                    binding_terminal=binding_terminal,
                )
            else:
                updated_locals[body.bound_name] = resolved_binding
        nested_steps, nested_terminal = _defunctionalize_body(
            body.body,
            context=lowering_core._context_with_local_type_binding(
                context,
                binding_name=body.bound_name,
                binding_type=binding_type,
            ),
            local_values=updated_locals,
            scope_analysis=scope_analysis,
            lexical_checkpoint_points=lexical_checkpoint_points,
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
            lexical_checkpoint_points=lexical_checkpoint_points,
            jump_target=jump_target,
        )

    if isinstance(body, WccIf):
        return _defunctionalize_if(
            body,
            context=context,
            local_values=local_values,
            scope_analysis=scope_analysis,
            lexical_checkpoint_points=lexical_checkpoint_points,
            jump_target=jump_target,
        )

    if isinstance(body, WccRecJoin):
        return _defunctionalize_rec_join(
            body,
            context=context,
            local_values=local_values,
            lexical_checkpoint_points=lexical_checkpoint_points,
        )

    if isinstance(body, WccJoin):
        return _defunctionalize_join(
            body,
            context=context,
            local_values=local_values,
            scope_analysis=scope_analysis,
            lexical_checkpoint_points=lexical_checkpoint_points,
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
    lexical_checkpoint_points: list[Mapping[str, object]] | None = None,
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
    steps, terminal = _emit_repeat_until_from_emitter_input(
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
    if lexical_checkpoint_points is not None:
        repeat_step = next(
            (
                step
                for step in steps
                if isinstance(step, Mapping)
                and isinstance(step.get("id"), str)
                and "repeat_until" in step
            ),
            None,
        )
        repeat_step_id = repeat_step.get("id") if isinstance(repeat_step, Mapping) else None
        repeat_step_name = repeat_step.get("name") if isinstance(repeat_step, Mapping) else None
        if isinstance(repeat_step_id, str) and repeat_step_id:
            lexical_checkpoint_points.append(
                _loop_back_edge_checkpoint_point_payload(
                    workflow_name=context.workflow_name,
                    body=body,
                    repeat_step_name=repeat_step_name or repeat_step_id,
                    repeat_step_id=repeat_step_id,
                    context=context,
                    local_values=local_values,
                )
            )
    return steps, terminal


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


def _rewrite_nested_case_sibling_refs(
    steps: list[dict[str, Any]],
    *,
    ancestor_sibling_names: tuple[str, ...] = (),
) -> None:
    current_sibling_names = tuple(
        step_name
        for step in steps
        for step_name in (step.get("name"),)
        if isinstance(step_name, str)
    )
    sibling_names = ancestor_sibling_names + tuple(
        name for name in current_sibling_names if name not in ancestor_sibling_names
    )
    for step in steps:
        rewritten = _rewrite_case_sibling_refs_in_value(step, sibling_names=sibling_names)
        step.clear()
        step.update(rewritten)
        for nested_steps in _iter_nested_case_step_lists(step):
            _rewrite_nested_case_sibling_refs(
                nested_steps,
                ancestor_sibling_names=sibling_names,
            )


def _iter_nested_case_step_lists(step: Mapping[str, Any]) -> tuple[list[dict[str, Any]], ...]:
    nested: list[list[dict[str, Any]]] = []
    for branch_name in ("then", "else"):
        branch = step.get(branch_name)
        if isinstance(branch, Mapping) and isinstance(branch.get("steps"), list):
            nested.append(branch["steps"])
    match_node = step.get("match")
    if isinstance(match_node, Mapping):
        for case in (match_node.get("cases") or {}).values():
            if isinstance(case, Mapping) and isinstance(case.get("steps"), list):
                nested.append(case["steps"])
    repeat_until = step.get("repeat_until")
    if isinstance(repeat_until, Mapping) and isinstance(repeat_until.get("steps"), list):
        nested.append(repeat_until["steps"])
    return tuple(nested)


def _rewrite_case_sibling_refs_in_value(value: Any, *, sibling_names: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for step_name in sibling_names:
            for scope_prefix in ("parent.steps.", "root.steps."):
                prefix = f"{scope_prefix}{step_name}."
                if value.startswith(prefix):
                    return "self.steps." + value.removeprefix(scope_prefix)
        return value
    if isinstance(value, list):
        return [_rewrite_case_sibling_refs_in_value(item, sibling_names=sibling_names) for item in value]
    if isinstance(value, Mapping):
        rewritten: dict[Any, Any] = {}
        for key, item in value.items():
            if key == "steps" and isinstance(item, list):
                rewritten[key] = item
                continue
            rewritten[key] = _rewrite_case_sibling_refs_in_value(item, sibling_names=sibling_names)
        return rewritten
    return value


def _defunctionalize_case(
    body: WccCase,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    scope_analysis: WccScopeAnalysis,
    lexical_checkpoint_points: list[Mapping[str, object]] | None,
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
    subject_type = context.local_type_bindings.get(binding_name)
    for arm in body.arms:
        case_name = f"{match_step_name}__{arm.variant_name.lower()}"
        arm_context = lowering_core._copy_context_with_step_prefix(context, step_name_prefix=case_name)
        arm_binding_type = None
        if isinstance(subject_type, UnionTypeRef):
            arm_binding_type = context.type_env.union_variant(
                subject_type,
                arm.variant_name,
                span=body.metadata.source_span,
                form_path=body.metadata.form_path,
            )
            arm_context = _context_with_local_type_binding(
                arm_context,
                binding_name=arm.binding_name,
                binding_type=arm_binding_type,
            )
        arm_steps, arm_terminal = _defunctionalize_body(
            arm.body,
            context=arm_context,
            local_values=_match_arm_local_values(
                local_values=local_values,
                binding_name=arm.binding_name,
                binding_terminal=binding_terminal,
                binding_type=arm_binding_type,
            ),
            scope_analysis=scope_analysis,
            lexical_checkpoint_points=lexical_checkpoint_points,
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
            or arm_context.requires_guarded_case_step_hoist
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
        _rewrite_nested_case_sibling_refs(arm_steps)
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
    lexical_checkpoint_points: list[Mapping[str, object]] | None,
    jump_target: tuple[str, tuple[WccJoinParam, ...]] | None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    step_name = context.step_name_prefix
    step_id = lowering_core._normalize_generated_step_id(step_name)
    condition_steps: list[dict[str, Any]] = []
    condition_expr = _frontend_expr_from_wcc_value(body.condition)
    resolved_condition_expr = _resolve_inline_expr_value(
        condition_expr,
        local_values=local_values,
    )
    pure_condition_expr = (
        resolved_condition_expr
        if resolved_condition_expr is not condition_expr
        and is_pure_projection_expr(resolved_condition_expr)
        and not isinstance(resolved_condition_expr, (LiteralExpr, NameExpr, FieldAccessExpr))
        else condition_expr
        if isinstance(body.condition_shape, PureExprCondition)
        or (
            is_pure_projection_expr(condition_expr)
            and not isinstance(condition_expr, (LiteralExpr, NameExpr, FieldAccessExpr))
        )
        else None
    )
    if pure_condition_expr is not None:
        static_condition = try_evaluate_static_pure_expr(
            pure_condition_expr,
            result_type=PrimitiveTypeRef(name="Bool"),
            context=context,
            local_values=local_values,
        )
        if isinstance(static_condition, bool):
            condition = {
                "compare": {
                    "left": static_condition,
                    "op": "eq",
                    "right": True,
                }
            }
        else:
            condition_step_name = f"{step_name}__condition"
            condition_step_id = lowering_core._normalize_generated_step_id(condition_step_name)
            lowered_condition = lower_pure_projection_step(
                pure_condition_expr,
                result_type=PrimitiveTypeRef(name="Bool"),
                context=lowering_core._copy_context_with_step_prefix(
                    context,
                    step_name_prefix=condition_step_name,
                ),
                local_values=local_values,
                step_name=condition_step_name,
                step_id=condition_step_id,
                stable_target="if_condition",
            )
            condition_steps.append(lowered_condition.step)
            condition = {
                "compare": {
                    "left": {"ref": lowered_condition.output_refs["return"]},
                    "op": "eq",
                    "right": True,
                }
            }
    else:
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
        lexical_checkpoint_points=lexical_checkpoint_points,
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
        lexical_checkpoint_points=lexical_checkpoint_points,
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
        *condition_steps,
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
        },
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
    lexical_checkpoint_points: list[Mapping[str, object]] | None,
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
        lexical_checkpoint_points=lexical_checkpoint_points,
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
        lexical_checkpoint_points=lexical_checkpoint_points,
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
    if isinstance(resolved_expr, DoneExpr):
        resolved_expr = resolved_expr.result_expr
    if not isinstance(resolved_expr, UnionVariantExpr):
        resolved_expr = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(resolved_expr, DoneExpr):
        resolved_expr = resolved_expr.result_expr
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
    if output_refs is not None:
        return [], _TerminalResult(
            step_name=context.step_name_prefix,
            step_id=lowering_core._normalize_generated_step_id(context.step_name_prefix),
            output_refs=output_refs,
            output_kind="projection",
            hidden_inputs={},
        )
    if is_pure_projection_expr(expr):
        static_terminal = _lower_static_terminal_projection(
            expr,
            type_ref=type_ref,
            context=context,
            local_values=local_values,
        )
        if static_terminal is not None:
            return static_terminal
        terminal_step_name = f"{context.step_name_prefix}__terminal_projection"
        terminal_step_id = lowering_core._normalize_generated_step_id(terminal_step_name)
        lowered_projection = lower_pure_projection_step(
            expr,
            result_type=type_ref,
            context=context,
            local_values=local_values,
            step_name=terminal_step_name,
            step_id=terminal_step_id,
            stable_target="terminal_projection",
        )
        return [lowered_projection.step], _TerminalResult(
            step_name=terminal_step_name,
            step_id=terminal_step_id,
            output_refs=lowered_projection.output_refs,
            output_kind="projection",
            hidden_inputs={},
        )
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


def _lower_static_terminal_projection(
    expr: Any,
    *,
    type_ref: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult] | None:
    if not _contains_pure_operator(expr, local_values=local_values):
        return None
    static_value = try_evaluate_static_pure_expr(
        expr,
        result_type=type_ref,
        context=context,
        local_values=local_values,
    )
    if static_value is None:
        return None

    values: list[dict[str, Any]] = []
    output_refs: dict[str, str] = {}
    step_name = f"{context.step_name_prefix}__terminal_projection"
    step_id = lowering_core._normalize_generated_step_id(step_name)
    for field in lowering_core.derive_workflow_boundary_fields(
        type_ref,
        generated_name="return",
        source_path=("return",),
        span=context.signature.span,
        form_path=context.signature.form_path,
    ):
        leaf = _static_terminal_leaf(static_value, field_path=field.source_path[1:])
        if not _is_static_terminal_literal(leaf):
            return None
        artifact_name = (
            "__result__"
            if not isinstance(type_ref, (RecordTypeRef, UnionTypeRef))
            else field.generated_name
        )
        values.append(
            {
                "name": artifact_name,
                "source": {"literal": leaf},
                "contract": dict(field.contract_definition),
            }
        )
        output_refs[field.generated_name] = f"root.steps.{step_name}.artifacts.{artifact_name}"

    step = {
        "name": step_name,
        "id": step_id,
        "materialize_artifacts": {
            "values": values,
        },
    }
    lowering_core._record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=output_refs,
        output_kind="projection",
        hidden_inputs={},
    )


def _static_terminal_leaf(value: Any, *, field_path: tuple[str, ...]) -> Any:
    leaf = value
    for field_name in field_path:
        if not isinstance(leaf, Mapping):
            return None
        leaf = leaf.get(field_name)
    return leaf


def _is_static_terminal_literal(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _contains_pure_operator(expr: Any, *, local_values: Mapping[str, Any]) -> bool:
    if isinstance(expr, PureOpExpr):
        return True
    if isinstance(expr, NameExpr):
        local_expr = local_values.get(expr.name)
        return local_expr is not None and _contains_pure_operator(local_expr, local_values=local_values)
    if isinstance(expr, RecordUpdateExpr):
        return _contains_pure_operator(expr.base_expr, local_values=local_values) or any(
            _contains_pure_operator(override_expr, local_values=local_values)
            for _, override_expr in expr.overrides
        )
    if isinstance(expr, (RecordExpr, UnionVariantExpr)):
        return any(_contains_pure_operator(field_expr, local_values=local_values) for _, field_expr in expr.fields)
    if isinstance(expr, IfExpr):
        return (
            _contains_pure_operator(expr.condition_expr, local_values=local_values)
            or _contains_pure_operator(expr.then_expr, local_values=local_values)
            or _contains_pure_operator(expr.else_expr, local_values=local_values)
        )
    if isinstance(expr, LetStarExpr):
        return any(
            _contains_pure_operator(binding_expr, local_values=local_values)
            for _, binding_expr in expr.bindings
        ) or _contains_pure_operator(expr.body, local_values=local_values)
    return False


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
        expected_output_names = _expected_terminal_output_names(
            type_ref,
            context=context,
        )
        if expected_output_names and all(name in flattened_refs for name in expected_output_names):
            return {
                output_name: flattened_refs[output_name]
                for output_name in expected_output_names
            }
    return None


def _expected_terminal_output_names(
    type_ref: TypeRef,
    *,
    context: _LoweringContext,
) -> tuple[str, ...]:
    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return tuple(
            field.generated_name
            for field in lowering_core.derive_workflow_boundary_fields(
                type_ref,
                generated_name="return",
                source_path=("return",),
                span=context.signature.span,
                form_path=context.signature.form_path,
            )
        )
    return ("return",)


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
    lexical_checkpoint_points: list[Mapping[str, object]] | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if isinstance(value, WccPerform):
        if value.perform_kind == "command_result":
            operation_payload = value.operation_payload if isinstance(value.operation_payload, dict) else {}
            adapter_inputs = operation_payload.get("adapter_inputs") or ()
            return _lower_command_result_operation(
                LowerableCommandResult(
                    step_name=value.target_name,
                    argv=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                    adapter_name=operation_payload.get("adapter_name"),
                    adapter_inputs=tuple(
                        (field_name, _frontend_expr_from_wcc_value(input_value))
                        for field_name, input_value in adapter_inputs
                    ),
                    guidance=(
                        operation_payload["return_spec"].guidance
                        if operation_payload.get("return_spec") is not None
                        else None
                    ),
                ),
                result_type=binding_type,
                context=context,
                local_values=local_values,
            )
        if value.perform_kind == "provider_result":
            operation_payload = value.operation_payload if isinstance(value.operation_payload, dict) else {}
            return _lower_provider_result_operation(
                LowerableProviderResult(
                    provider_name=value.target_name,
                    prompt_name=value.prompt_name or "",
                    inputs=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                    guidance=(
                        operation_payload["return_spec"].guidance
                        if operation_payload.get("return_spec") is not None
                        else None
                    ),
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
        if value.perform_kind in {
            "run_provider_phase",
            "produce_one_of",
            "resume_or_start",
            "resource_transition",
            "finalize_selected_item",
            "materialize_view",
        }:
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
        lexical_checkpoint_points=lexical_checkpoint_points,
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
    if isinstance(payload, FinalizeSelectedItemExpr):
        return _phase_stdlib_lower_finalize_selected_item_impl(
            TypedExpr(
                expr=payload,
                type_ref=binding_type,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                effect_summary=value.metadata.effect_summary,
            ),
            context=context,
            local_values=local_values,
        )
    if isinstance(payload, ResourceTransitionExpr):
        return _phase_stdlib_lower_resource_transition_impl(
            TypedExpr(
                expr=payload,
                type_ref=binding_type,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                effect_summary=value.metadata.effect_summary,
            ),
            context=context,
            local_values=local_values,
        )
    if isinstance(payload, MaterializeViewExpr):
        return lower_materialize_view_step(
            TypedExpr(
                expr=payload,
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
                guidance=expr.return_spec.guidance,
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
    lexical_checkpoint_points: list[Mapping[str, object]] | None = None,
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
        # An inline proc body evaluates derived-private-child hidden-context
        # eligibility against the proc's own signature, not the enclosing
        # caller being lowered — same proc-local scope the frontend inline
        # lane installs in lowering/procedures.py (structural
        # private-exec-context / std/context contract,
        # docs/design/workflow_lisp_frontend_specification.md).
        procedure_hidden_context_signature=(
            procedure.signature
            if eligible_private_context_source_param_names(procedure.signature)
            else None
        ),
        local_type_bindings={
            **dict(context.local_type_bindings),
            **_procedure_signature_local_type_bindings(procedure),
        },
        type_env=_procedure_type_env_for(
            procedure,
            procedure_type_envs=context.procedure_type_envs,
            default=context.type_env,
        ),
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
    procedure_type_env = child_context.type_env
    route_schema_version = value.metadata.node_id.split(":", 2)[1]
    wcc_body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            procedure.typed_body,
            owner_name=procedure.definition.name,
            type_env=procedure_type_env,
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
        lexical_checkpoint_points=lexical_checkpoint_points,
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


def _frontend_expr_from_wcc_loop_body(body: WccBody, env: Mapping[str, object] | None = None):
    resolved_env: Mapping[str, object] = env or {}
    if isinstance(body, WccLet):
        binding_expr = (
            _frontend_expr_from_wcc_loop_binding_value(body.bound_value)
            if isinstance(body.bound_value, (WccPerform, WccCall))
            else _frontend_expr_from_wcc_value_with_env(body.bound_value, resolved_env)
        )
        nested_env: Mapping[str, object] = resolved_env
        if not isinstance(body.bound_value, (WccPerform, WccCall)):
            nested_env = {**dict(resolved_env), body.bound_name: binding_expr}
        return LetStarExpr(
            bindings=((body.bound_name, binding_expr),),
            body=_frontend_expr_from_wcc_loop_body(body.body, nested_env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccCase):
        return MatchExpr(
            subject=_frontend_expr_from_wcc_value_with_env(body.subject, resolved_env),
            arms=tuple(
                MatchArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    body=_frontend_expr_from_wcc_loop_body(arm.body, resolved_env),
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
            condition_expr=_frontend_expr_from_wcc_value_with_env(body.condition, resolved_env),
            then_expr=_frontend_expr_from_wcc_loop_body(body.then_body, resolved_env),
            else_expr=_frontend_expr_from_wcc_loop_body(body.else_body, resolved_env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccJoin):
        if len(body.params) != 1:
            raise TypeError("WCC M4 loop body conversion supports one join parameter")
        param = body.params[0]
        binding_expr = _frontend_expr_from_wcc_join_binding(body.body, join_name=body.join_name, env=resolved_env)
        nested_env = {**dict(resolved_env), param.name: binding_expr}
        return LetStarExpr(
            bindings=((param.name, binding_expr),),
            body=_frontend_expr_from_wcc_loop_body(body.continuation, nested_env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccLoopContinue):
        if len(body.state_args) != 1:
            raise TypeError("WCC M4 loop body conversion supports one continue state argument")
        return ContinueExpr(
            state_expr=_frontend_expr_from_wcc_value_with_env(body.state_args[0], resolved_env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccLoopDone):
        return DoneExpr(
            result_expr=_frontend_expr_from_wcc_value_with_env(body.result, resolved_env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccHalt):
        return _frontend_expr_from_wcc_value_with_env(body.result, resolved_env)
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


def _frontend_expr_from_wcc_join_binding(
    body: WccBody,
    *,
    join_name: str,
    env: Mapping[str, object],
):
    if isinstance(body, WccLet):
        binding_expr = (
            _frontend_expr_from_wcc_loop_binding_value(body.bound_value)
            if isinstance(body.bound_value, (WccPerform, WccCall))
            else _frontend_expr_from_wcc_value_with_env(body.bound_value, env)
        )
        nested_env = env
        if not isinstance(body.bound_value, (WccPerform, WccCall)):
            nested_env = {**dict(env), body.bound_name: binding_expr}
        return LetStarExpr(
            bindings=((body.bound_name, binding_expr),),
            body=_frontend_expr_from_wcc_join_binding(body.body, join_name=join_name, env=nested_env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccCase):
        return MatchExpr(
            subject=_frontend_expr_from_wcc_value_with_env(body.subject, env),
            arms=tuple(
                MatchArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    body=_frontend_expr_from_wcc_join_binding(arm.body, join_name=join_name, env=env),
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
            condition_expr=_frontend_expr_from_wcc_value_with_env(body.condition, env),
            then_expr=_frontend_expr_from_wcc_join_binding(body.then_body, join_name=join_name, env=env),
            else_expr=_frontend_expr_from_wcc_join_binding(body.else_body, join_name=join_name, env=env),
            span=body.metadata.source_span,
            form_path=body.metadata.form_path,
            expansion_stack=body.metadata.expansion_stack,
        )
    if isinstance(body, WccJump):
        if body.join_name != join_name or len(body.args) != 1:
            raise TypeError("WCC M4 loop join conversion encountered an unexpected jump shape")
        return _frontend_expr_from_wcc_value_with_env(body.args[0], env)
    if isinstance(body, WccHalt):
        return _frontend_expr_from_wcc_value_with_env(body.result, env)
    raise TypeError(f"unsupported WCC join binding during loop defunctionalization: {type(body).__name__}")


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
    if isinstance(value, WccPureOp):
        if value.operator == "record-update":
            if not value.args:
                raise TypeError("record-update WCC pure op requires a base argument")
            return RecordUpdateExpr(
                base_expr=_frontend_expr_from_wcc_value_with_env(value.args[0], env),
                overrides=tuple(
                    (
                        field_name,
                        _frontend_expr_from_wcc_value_with_env(field_value, env),
                    )
                    for field_name, field_value in zip(value.field_names, value.args[1:], strict=True)
                ),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        return PureOpExpr(
            operator=value.operator,
            args=tuple(
                _frontend_expr_from_wcc_value_with_env(arg, env)
                for arg in value.args
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
            operation_payload = value.operation_payload if isinstance(value.operation_payload, dict) else {}
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
                return_spec=operation_payload.get("return_spec"),
                returns_type_name=value.returns_type_name or "",
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        if value.perform_kind == "command_result":
            operation_payload = value.operation_payload if isinstance(value.operation_payload, dict) else {}
            adapter_inputs = operation_payload.get("adapter_inputs") or ()
            return CommandResultExpr(
                step_name=value.target_name,
                argv=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                return_spec=operation_payload.get("return_spec"),
                returns_type_name=value.returns_type_name or "",
                adapter_name=operation_payload.get("adapter_name"),
                adapter_inputs=tuple(
                    (field_name, _frontend_expr_from_wcc_value(input_value))
                    for field_name, input_value in adapter_inputs
                ),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        if value.perform_kind == "workflow_call":
            return CallExpr(
                callee_name=value.target_name,
                bindings=tuple(
                    (binding_name, _frontend_expr_from_wcc_value(binding_value))
                    for binding_name, binding_value in value.keyword_args
                ),
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
        if value.literal_kind == "enum":
            type_ref = value.metadata.type_ref
            if not isinstance(type_ref, PrimitiveTypeRef) or not type_ref.allowed_values:
                raise TypeError("enum WCC literal requires an enum primitive type")
            return EnumMemberExpr(
                enum_name=type_ref.name,
                member_name=str(value.value),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
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
        if isinstance(value.expr, LoopStateSeedExpr):
            type_ref = value.metadata.type_ref
            if isinstance(type_ref, RecordTypeRef):
                return RecordExpr(
                    type_name=type_ref.name,
                    fields=tuple(
                        (field.name, field.value_expr)
                        for field in value.expr.fields
                    ),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                )
        if isinstance(value.expr, LoopStateUpdateExpr):
            return RecordUpdateExpr(
                base_expr=value.expr.base_expr,
                overrides=value.expr.overrides,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
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
    if isinstance(value, WccPureOp):
        if value.operator == "record-update":
            if not value.args:
                raise TypeError("record-update WCC pure op requires a base argument")
            return RecordUpdateExpr(
                base_expr=_frontend_expr_from_wcc_value(value.args[0]),
                overrides=tuple(
                    (
                        field_name,
                        _frontend_expr_from_wcc_value(field_value),
                    )
                    for field_name, field_value in zip(value.field_names, value.args[1:], strict=True)
                ),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        return PureOpExpr(
            operator=value.operator,
            args=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.args),
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
