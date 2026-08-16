"""Direct straight-line defunctionalization from WCC to lowered workflows."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast

from ..contracts import GeneratedInternalInput, derive_workflow_signature_contracts
from ..compiler_session import LoweringSessionState
from ..conditionals import PureExprCondition, render_condition_predicate
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expression_traversal import free_expr_names, iter_child_exprs, map_expr
from ..expressions import (
    CallExpr,
    CommandResultExpr,
    CompilerListNonemptyHeadExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    IfExpr,
    LetStarExpr,
    ListExpr,
    ListMapExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    MaterializeViewExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    PathJoinUnderExpr,
    PureOpExpr,
    ProcedureCallExpr,
    PromptDependencySpec,
    ProviderResultExpr,
    FinalizeSelectedItemExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    UnionVariantExpr,
    UnionVariantTagExpr,
)
from ..phase_stdlib import ProduceOneOfProducerSpec
from ..prompts import PromptApplicationExpr
from ..phase_family_boundary import (
    apply_phase_family_boundary_classification,
    classify_phase_family_boundary,
    record_direct_entry_phase_context_binding,
)
from ..procedures import ProcedureCatalog, ProcedureLoweringMode, TypedProcedureDef
from ..reader import SourceReadTrace, _read_source_file_views
from ..syntax import target_dsl_supports_list_traversal
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
from ..lowering.pure_projection import (
    _type_descriptor,
    build_pure_projection_payload,
    is_pure_projection_expr,
    lower_pure_projection_step,
    try_evaluate_static_pure_expr,
)
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
from ..lowering.run_ref import (
    LowerableRunRef,
    LowerableRunRefInput,
    _lower_run_ref_operation,
)
from ..lowering.trial import (
    LowerableTrial,
    LowerableTrialInput,
    _lower_trial_operation,
)
from ..loops import RepeatUntilEmitterInput
from ..lowering.control_loops import _emit_repeat_until_from_emitter_input
from ..phase import eligible_private_context_source_param_names
from ..lowering.procedures import (
    LowerableProcedureCall,
    _lower_procedure_call,
    _merge_origin_notes,
    _private_workflow_from_procedure,
    _procedure_provenance_notes,
    _procedure_type_env_for,
    _rewrite_nested_sibling_step_refs,
    _validate_resolved_procedure_mapping,
)
from ..lowering.workflow_calls import LowerableWorkflowCall, _lower_workflow_call
from orchestrator.workflow.state_layout import GeneratedPathPrivacy, GeneratedPathSemanticRole, derive_entrypoint_managed_write_root_allocations
from .anf import normalize_wcc_body_to_anf
from .elaborate import (
    WccPromptDependencyPayload,
    elaborate_typed_workflow,
    elaborate_typed_workflow_body,
)
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
    WccProviderPeerGroup,
    WccProviderPeerGroupMember,
    WccProviderSupervision,
    WccProviderSupervisionMember,
    WccProduceOneOfPayload,
    WccRecJoin,
    WccRecordAtom,
    WccSelect,
    WccSelectArm,
    WccResumeOrStartPayload,
    WccRunRefPayload,
    WccTrialPayload,
    WccRunProviderPhasePayload,
    WccValue,
)
from .analysis import WccScopeAnalysis, analyze_wcc_body
from orchestrator.workflow.executable_ir import (
    PROVIDER_PEER_GROUP_MESSAGING_POLICY,
    PROVIDER_PEER_GROUP_SCHEMA_VERSION,
    PROVIDER_SUPERVISION_SCHEMA_VERSION,
    ExecutableContract,
    ProviderPeerGroupMemberConfig,
    ProviderPeerGroupMemberSourceOwnership,
    ProviderPeerGroupSourceOwnership,
    ProviderPeerGroupStepConfig,
    ProviderStepConfig,
    ProviderSupervisionMemberConfig,
    ProviderSupervisionStepConfig,
    StepCommonConfig,
    _json_value as _executable_ir_json_value,
    provider_peer_group_config_to_runtime_dict,
)
from orchestrator.providers.types import (
    INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION,
)
from orchestrator.workflow.provider_peer_group.paths import (
    derive_provider_peer_group_paths,
)
from orchestrator.workflow.provider_supervision.models import (
    ProviderSupervisionObservation,
    ProviderSupervisionSourceOwnership,
)
from orchestrator.workflow.provider_supervision.contracts import (
    derive_result_contract_identity,
)
from orchestrator.workflow.provider_supervision.paths import (
    derive_provider_supervision_paths,
)
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.pure_expr import (
    PURE_EXPR_OPERATOR_CATALOG,
    validate_pure_expr_payload,
)
from orchestrator.workflow.surface_ast import freeze_value
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


def _workflow_source_policy_metadata(
    path: Path | None,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[str, str | None]:
    if path is None:
        return "unknown", None
    try:
        views = _read_source_file_views(
            path,
            source_read_trace=source_read_trace,
        )
    except OSError:
        return "unknown", None
    text = views.parser_text
    if path.suffix == ".orc":
        match = re.search(r'\(:target-dsl\s+"([^"]+)"\)', text)
        version = match.group(1) if match is not None else "unknown"
    else:
        version = "unknown"
        for line in text.splitlines():
            if line.strip().startswith("version:"):
                _, _, value = line.partition(":")
                candidate = value.strip()
                if candidate:
                    version = candidate
                    break
    return version, _sha256_bytes(views.raw_bytes)


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
    source_version, source_checksum = _workflow_source_policy_metadata(
        workflow_path,
        source_read_trace=context.source_read_trace,
    )
    target_dsl_version = imported_bundle.surface.version if imported_bundle is not None else source_version
    callee_checksum = (
        source_checksum
        if source_checksum is not None
        else _sha256_text(callee_workflow)
    )
    return target_dsl_version, callee_checksum


def lower_wcc_m2_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
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
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded straight-line workflows through WCC M2."""
    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        resolved_procedures_by_name=resolved_procedures_by_name,
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
        source_read_trace=source_read_trace,
    )


def lower_wcc_m3_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
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
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded same-file match workflows through WCC M3."""

    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        resolved_procedures_by_name=resolved_procedures_by_name,
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
        source_read_trace=source_read_trace,
    )


def lower_wcc_m4_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
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
    source_read_trace: SourceReadTrace | None = None,
    lowering_session: LoweringSessionState | None = None,
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower bounded loop workflows through WCC M4."""

    return _lower_wcc_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        resolved_procedures_by_name=resolved_procedures_by_name,
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
        source_read_trace=source_read_trace,
        lowering_session=lowering_session,
    )


def _lower_wcc_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
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
    source_read_trace: SourceReadTrace | None = None,
    lowering_session: LoweringSessionState | None = None,
) -> tuple[lowering_core.LoweredWorkflow, ...]:
    """Lower WCC workflows through one route-selected normalized program shape."""

    lowering_session = lowering_session or LoweringSessionState()
    resolved_procedures = _validate_resolved_procedure_mapping(
        typed_procedures,
        resolved_procedures_by_name,
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
            source_read_trace=source_read_trace,
            lowering_session=lowering_session,
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
    source_read_trace: SourceReadTrace | None = None,
    lowering_session: LoweringSessionState,
) -> lowering_core.LoweredWorkflow:
    inputs, outputs, boundary_projection = derive_workflow_signature_contracts(
        typed_workflow.signature,
        allow_transportable_inputs=(
            workflow_catalog.allow_transportable_input_boundaries
        ),
        type_env=type_env,
    )
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
        lowering_session=lowering_session,
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
        compiler_prompt_dependency_contracts={},
        prompt_dependency_lineages=[],
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
        source_read_trace=source_read_trace,
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
            resolved_procedures_by_name=typed_procedures,
            procedure_type_envs=procedure_type_envs,
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
        prompt_dependency_lineages=tuple(context.prompt_dependency_lineages),
        provider_supervision_origins=MappingProxyType(
            dict(context.provider_supervision_origins)
        ),
        provider_supervision_prompt_dependency_lineages=tuple(
            context.provider_supervision_prompt_dependency_lineages
        ),
        provider_peer_group_origins=MappingProxyType(
            dict(context.provider_peer_group_origins)
        ),
        provider_peer_group_prompt_dependency_lineages=tuple(
            context.provider_peer_group_prompt_dependency_lineages
        ),
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
        compiler_prompt_dependency_contracts=MappingProxyType(
            dict(context.compiler_prompt_dependency_contracts)
        ),
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
        compiler_owned_repeat_until_metadata=(
            lowering_core._capture_compiler_owned_repeat_until_metadata(
                authored_mapping
            )
        ),
        compiler_owned_nested_if_step_ids=(
            lowering_core._capture_compiler_owned_nested_if_step_ids(
                authored_mapping
            )
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
    identity_component_digest: str | None = None,
) -> str:
    payload = {
        "workflow_name": workflow_name,
        "point_kind": point_kind,
        "step_id": step_id,
        "type_ref": repr(type_ref),
        "form_path": form_path,
    }
    if identity_component_digest is not None:
        payload["identity_component_digest"] = identity_component_digest
    return _sha256_json(payload)


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
    identity_component_digest: str | None = None,
    trial_result_contract_digest: str | None = None,
) -> Mapping[str, object]:
    point_identity = {
        "wcc_node_id": wcc_node_id,
        "wcc_scope_id": wcc_scope_id,
        "step_id": step_id,
        "storage_scope": storage_scope,
    }
    checkpoint_executable_identity = (
        f"{wcc_node_id}:{step_id}"
        if point_kind == "effect_boundary"
        else f"{wcc_scope_id}:{step_id}"
    )
    executable_identity: dict[str, object] = {
        "step_id": step_id,
    }
    if identity_component_digest is not None:
        point_identity["identity_component_digest"] = (
            identity_component_digest
        )
        checkpoint_executable_identity = (
            f"{checkpoint_executable_identity}:"
            f"{identity_component_digest}"
        )
        executable_identity["identity_component_digest"] = (
            identity_component_digest
        )
    if trial_result_contract_digest is not None:
        if not isinstance(identity_component_digest, str):
            raise ValueError("trial checkpoint authority is incomplete")
        point_identity["trial_result_contract_digest"] = (
            trial_result_contract_digest
        )
        executable_identity["trial_result_contract_digest"] = (
            trial_result_contract_digest
        )
    program_point_id = derive_program_point_id(
        workflow_name=workflow_name,
        point_kind=point_kind,
        origin_key=origin_key,
        identity_digest=_sha256_json(point_identity),
    )
    checkpoint_id = derive_checkpoint_id(
        workflow_name=workflow_name,
        program_point_id=program_point_id,
        executable_identity=checkpoint_executable_identity,
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
            "executable_identity": executable_identity,
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

_ACTIVE_VARIANT_PROOFS_KEY = "__active_variant_proofs__"

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

    active_proofs = local_values.get(_ACTIVE_VARIANT_PROOFS_KEY)
    if isinstance(active_proofs, tuple):
        for triple in active_proofs:
            binding_name, union_name, variant_name = triple
            producer_step_name = _local_value_source_step_name(local_values.get(binding_name))
            if not isinstance(producer_step_name, str) or not producer_step_name:
                continue
            source_step_id = lowering_core._normalize_generated_step_id(producer_step_name)
            proof_id = f"proof:{context.workflow_name}:{source_step_id}:predicate:{variant_name}"
            if proof_id in seen_proof_sources:
                continue
            proof_descriptors.append(
                {
                    "proof_id": proof_id,
                    "proof_kind": "predicate",
                    "subject_binding": binding_name,
                    "union_type": union_name,
                    "variant": variant_name,
                    "variant_name": variant_name,
                    "producer_step_name": producer_step_name,
                    "proof_source": source_step_id,
                    "source_step_name": producer_step_name,
                    "source_step_id": source_step_id,
                    "source_map_origin_key": _origin_key_for_step(
                        context=context,
                        step_name=producer_step_name,
                        step_id=source_step_id,
                    ),
                }
            )
            seen_proof_sources.add(proof_id)

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


def _effect_boundary_step_kind(
    value: (
        WccPerform
        | WccCall
        | WccProviderSupervision
        | WccProviderPeerGroup
    ),
) -> str:
    if isinstance(value, WccProviderPeerGroup):
        return "provider_peer_group"
    if isinstance(value, WccProviderSupervision):
        return "provider_supervision"
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
    value: (
        WccPerform
        | WccCall
        | WccProviderSupervision
        | WccProviderPeerGroup
        | None
    ),
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
    if step_kind == "run_ref":
        step_config_digest = terminal.checkpoint_identity_component_digest
        if not isinstance(step_config_digest, str):
            raise ValueError(
                "run_ref checkpoint identity component is unavailable"
            )
        return build_effect_resume_policy(
            policy_kind="reuse_validated_run_ref_result",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={
                "run_ref_result": {
                    "step_config_digest": step_config_digest,
                }
            },
            unsafe_pending_behavior="fail_closed",
        )
    if step_kind == "trial":
        step_config_digest = terminal.checkpoint_identity_component_digest
        result_digest = terminal.checkpoint_result_contract_digest
        if not all(
            isinstance(value, str)
            for value in (step_config_digest, result_digest)
        ):
            raise ValueError("trial checkpoint identity authority is unavailable")
        return build_effect_resume_policy(
            policy_kind="reuse_validated_trial_result",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={
                "trial_result": {
                    "trial_static_config_digest": step_config_digest,
                    "result_contract_digest": result_digest,
                }
            },
            unsafe_pending_behavior="fail_closed",
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
        elif (
            isinstance(value, WccPerform)
            and value.perform_kind == "workflow_call"
            and (
                target_dsl_supports_list_traversal(
                    context.type_env.target_dsl_version or ""
                )
                or value.target_name in context.imported_workflow_bundles
            )
        ):
            callee_workflow = value.target_name
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
    if step_kind in {"provider_supervision", "provider_peer_group"}:
        return build_effect_resume_policy(
            policy_kind="fail_closed_non_idempotent",
            effect_kind=step_kind,
            boundary_kind=step_kind,
            step_id=step_id,
            source_map_origin_key=origin_key,
            evidence_requirements={},
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
    value: (
        WccPerform
        | WccCall
        | WccProviderSupervision
        | WccProviderPeerGroup
    ),
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
        identity_component_digest=(
            terminal.checkpoint_identity_component_digest
        ),
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
            identity_component_digest=(
                terminal.checkpoint_identity_component_digest
            ),
            trial_result_contract_digest=(
                terminal.checkpoint_result_contract_digest
            ),
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
        if isinstance(body.bound_value, WccProviderPeerGroup):
            binding_context = _context_with_wcc_phase_scope(
                context,
                phase_scope=body.bound_value.metadata.phase_scope,
                local_values=updated_locals,
            )
            step_context = lowering_core._copy_context_with_step_prefix(
                binding_context,
                step_name_prefix=_binding_step_prefix(
                    context,
                    body.bound_name,
                ),
            )
            binding_steps, binding_terminal = (
                _lower_provider_peer_group_binding(
                    body.bound_value,
                    binding_type=binding_type,
                    context=step_context,
                    local_values=updated_locals,
                )
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
            local_value = _binding_local_value_from_terminal(
                body.bound_value,
                binding_type=binding_type,
                binding_terminal=binding_terminal,
            )
            if local_value is not None:
                updated_locals[body.bound_name] = local_value
        elif isinstance(body.bound_value, WccProviderSupervision):
            binding_context = _context_with_wcc_phase_scope(
                context,
                phase_scope=body.bound_value.metadata.phase_scope,
                local_values=updated_locals,
            )
            step_context = lowering_core._copy_context_with_step_prefix(
                binding_context,
                step_name_prefix=_binding_step_prefix(
                    context,
                    body.bound_name,
                ),
            )
            binding_steps, binding_terminal = (
                _lower_provider_supervision_binding(
                    body.bound_value,
                    binding_type=binding_type,
                    context=step_context,
                    local_values=updated_locals,
                )
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
            local_value = _binding_local_value_from_terminal(
                body.bound_value,
                binding_type=binding_type,
                binding_terminal=binding_terminal,
            )
            if local_value is not None:
                updated_locals[body.bound_name] = local_value
        elif isinstance(body.bound_value, (WccPerform, WccCall)):
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
            procedure = (
                context.typed_procedures.get(body.bound_value.specialized_callee_name)
                or context.typed_procedures.get(body.bound_value.callee_name)
                if isinstance(body.bound_value, WccCall)
                else None
            )
            is_inline_procedure_call = (
                procedure is not None
                and procedure.resolved_lowering_mode == ProcedureLoweringMode.INLINE
            )
            if lexical_checkpoint_points is not None and not is_inline_procedure_call:
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
                is_pure_projection_expr(binding_expr)
                and _wcc_run_ref_input_references_name(
                    body.body,
                    body.bound_name,
                )
            ):
                resolved_binding = binding_expr
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


def _lowered_effect_boundary_kind(
    emitted_steps: list[dict[str, Any]],
    *,
    terminal: _TerminalResult,
) -> str | None:
    """Classify an observed boundary from its lowered structural step."""

    matching_steps: list[Mapping[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("id") == terminal.step_id:
                matching_steps.append(value)
            for nested in value.values():
                visit(nested)
            return
        if isinstance(value, (tuple, list)):
            for nested in value:
                visit(nested)

    visit(emitted_steps)
    if not matching_steps:
        return None
    if len(matching_steps) != 1:
        raise ValueError(
            "lowered loop iteration terminal identity is ambiguous"
        )
    step = matching_steps[0]
    boundary_keys = (
        ("provider", "provider"),
        ("command", "command"),
        ("call", "call"),
        ("materialize_view", "materialize_view"),
        ("resource_transition", "resource_transition"),
        ("resume_or_start", "resume_or_start"),
        ("provider_supervision", "provider_supervision"),
        ("provider_peer_group", "provider_peer_group"),
        ("finalize_selected_item", "finalize_selected_item"),
    )
    observed = tuple(
        kind
        for key, kind in boundary_keys
        if key in step
    )
    if not observed:
        return None
    if len(observed) != 1:
        raise ValueError(
            "lowered loop iteration terminal effect kind is ambiguous"
        )
    return observed[0]


def _normalized_inline_procedure_wcc_body(
    value: WccCall,
    *,
    procedure: TypedProcedureDef,
    context: _LoweringContext,
) -> WccBody:
    workflow_return_types = {
        name: workflow.signature.return_type_ref
        for name, workflow in context.workflows_by_name.items()
    }
    workflow_return_types.update(
        {
            name: signature.return_type_ref
            for name, signature
            in context.workflow_catalog.signatures_by_name.items()
        }
    )
    procedure_return_types = {
        name: candidate.signature.return_type_ref
        for name, candidate in context.typed_procedures.items()
    }
    route_schema_version = value.metadata.node_id.split(":", 2)[1]
    return normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            procedure.typed_body,
            owner_name=procedure.definition.name,
            type_env=_procedure_type_env_for(
                procedure,
                procedure_type_envs=context.procedure_type_envs,
                default=context.type_env,
            ),
            value_env=_procedure_signature_local_type_bindings(procedure),
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            route_schema_version=route_schema_version,
        )
    )


def _iter_specialized_loop_effect_values(
    body: WccBody,
    *,
    context: _LoweringContext,
    active_procedures: frozenset[str] = frozenset(),
):
    if isinstance(body, WccLet):
        value = body.bound_value
        if isinstance(
            value,
            (WccPerform, WccProviderSupervision, WccProviderPeerGroup),
        ):
            yield value
        elif isinstance(value, WccCall):
            procedure = (
                context.typed_procedures.get(
                    value.specialized_callee_name
                )
                or context.typed_procedures.get(value.callee_name)
            )
            if (
                procedure is not None
                and procedure.resolved_lowering_mode
                is ProcedureLoweringMode.INLINE
            ):
                procedure_name = procedure.signature.name
                if procedure_name in active_procedures:
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="proc_lowering_cycle",
                                message=(
                                    "recursive procedure specialization "
                                    f"cycle detected for `{procedure_name}`"
                                ),
                                span=value.metadata.source_span,
                                form_path=value.metadata.form_path,
                                phase="lowering",
                            ),
                        )
                    )
                yield from _iter_specialized_loop_effect_values(
                    _normalized_inline_procedure_wcc_body(
                        value,
                        procedure=procedure,
                        context=context,
                    ),
                    context=context,
                    active_procedures=(
                        active_procedures | {procedure_name}
                    ),
                )
            else:
                yield value
        yield from _iter_specialized_loop_effect_values(
            body.body,
            context=context,
            active_procedures=active_procedures,
        )
        return
    if isinstance(body, WccIf):
        yield from _iter_specialized_loop_effect_values(
            body.then_body,
            context=context,
            active_procedures=active_procedures,
        )
        yield from _iter_specialized_loop_effect_values(
            body.else_body,
            context=context,
            active_procedures=active_procedures,
        )
        return
    if isinstance(body, WccCase):
        for arm in body.arms:
            yield from _iter_specialized_loop_effect_values(
                arm.body,
                context=context,
                active_procedures=active_procedures,
            )
        return
    if isinstance(body, WccJoin):
        yield from _iter_specialized_loop_effect_values(
            body.body,
            context=context,
            active_procedures=active_procedures,
        )
        yield from _iter_specialized_loop_effect_values(
            body.continuation,
            context=context,
            active_procedures=active_procedures,
        )
        return
    if isinstance(body, WccRecJoin):
        yield from _iter_specialized_loop_effect_values(
            body.body,
            context=context,
            active_procedures=active_procedures,
        )
        if body.exhaustion is not None:
            yield from _iter_specialized_loop_effect_values(
                body.exhaustion,
                context=context,
                active_procedures=active_procedures,
            )


def _loop_effect_compile_error(
    body: WccRecJoin,
    *,
    code: str,
    message: str,
) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=body.metadata.source_span,
                form_path=body.metadata.form_path,
                phase="lowering",
            ),
        )
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
    constrained_effect_kinds = body.single_iteration_effect_kinds
    expected_effect_values = (
        list(
            _iter_specialized_loop_effect_values(
                body.body,
                context=context,
            )
        )
        if constrained_effect_kinds is not None
        else []
    )
    pending_effect_values = list(expected_effect_values)
    lowered_effect_step_ids: set[str] = set()
    lowered_effect_kinds: list[str] = []

    def observe_lowered_effect(
        *,
        expr: Any,
        type_ref: TypeRef | None,
        terminal: _TerminalResult,
        emitted_steps: list[dict[str, Any]],
        context: _LoweringContext,
        local_values: Mapping[str, Any],
    ) -> None:
        del expr, type_ref
        effect_kind = _lowered_effect_boundary_kind(
            emitted_steps,
            terminal=terminal,
        )
        if effect_kind is None or terminal.step_id in lowered_effect_step_ids:
            return
        if not pending_effect_values:
            raise _loop_effect_compile_error(
                body,
                code=(
                    body.effect_cardinality_diagnostic_code
                    or "wcc_lowering_route_unsupported"
                ),
                message=(
                    "lowered loop iteration produced an effect boundary "
                    "without a specialized WCC source"
                ),
            )
        value = pending_effect_values.pop(0)
        expected_kind = _effect_boundary_step_kind(value)
        if expected_kind != effect_kind:
            raise _loop_effect_compile_error(
                body,
                code=(
                    body.effect_cardinality_diagnostic_code
                    or "wcc_lowering_route_unsupported"
                ),
                message=(
                    "lowered loop iteration effect kind does not match its "
                    "specialized WCC source"
                ),
            )
        lowered_effect_step_ids.add(terminal.step_id)
        lowered_effect_kinds.append(effect_kind)
        if lexical_checkpoint_points is not None:
            lexical_checkpoint_points.append(
                _effect_boundary_checkpoint_point_payload(
                    workflow_name=context.workflow_name,
                    value=value,
                    terminal=terminal,
                    context=context,
                    local_values=local_values,
                )
            )

    loop_local_values = _materialize_wcc_record_locals(local_values)
    loop_context = (
        replace(
            context,
            effect_boundary_observer=observe_lowered_effect,
        )
        if constrained_effect_kinds is not None
        else context
    )
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
            exhaustion_diagnostic_code=body.exhaustion_diagnostic_code,
            single_iteration_effect_kinds=(
                body.single_iteration_effect_kinds
            ),
            effect_cardinality_diagnostic_code=(
                body.effect_cardinality_diagnostic_code
            ),
        ),
        context=loop_context,
        local_values=loop_local_values,
    )
    if pending_effect_values:
        raise _loop_effect_compile_error(
            body,
            code=(
                body.effect_cardinality_diagnostic_code
                or "wcc_lowering_route_unsupported"
            ),
            message=(
                "specialized WCC loop effect did not bind to exactly one "
                "lowered iteration boundary"
            ),
        )
    if body.single_iteration_effect_kinds is not None and (
        len(lowered_effect_kinds) != 1
        or lowered_effect_kinds[0]
        not in body.single_iteration_effect_kinds
    ):
        raise _loop_effect_compile_error(
            body,
            code=(
                body.effect_cardinality_diagnostic_code
                or "wcc_lowering_route_unsupported"
            ),
            message=(
                "loop iteration must lower to exactly one permitted effect "
                "boundary after specialization"
            ),
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


def _requires_variant_guard(
    *,
    producer_step_name: str,
    required_variant: str,
) -> dict[str, str]:
    """Build the existing runtime ``requires_variant`` contract."""
    return {
        "step": producer_step_name,
        "value": required_variant,
    }


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
    outer_requires_variant = _requires_variant_guard(
        producer_step_name=producer_step_name,
        required_variant=required_variant,
    )
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

def _render_discriminant_condition(
    condition_expr,
    *,
    local_values: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Render a discriminant comparison predicate, or ``None``.

    Recognizes ``(= x.variant TAG)`` and ``(!= x.variant TAG)`` where ``TAG`` is
    a compiler-owned ``UnionVariantTagExpr`` and resolves the discriminant to
    the producer's ``variant`` artifact ref.
    """
    if not isinstance(condition_expr, PureOpExpr) or condition_expr.operator not in ("=", "!="):
        return None
    left, right = condition_expr.args
    if (
        isinstance(left, UnionVariantTagExpr)
        and isinstance(right, FieldAccessExpr)
        and right.fields == ("variant",)
    ):
        tag, variant_access = left, right
    elif (
        isinstance(right, UnionVariantTagExpr)
        and isinstance(left, FieldAccessExpr)
        and left.fields == ("variant",)
    ):
        tag, variant_access = right, left
    else:
        return None
    variant_ref = _resolve_inline_expr_value(variant_access, local_values=local_values)
    if not isinstance(variant_ref, str):
        return None
    return {
        "compare": {
            "left": {"ref": variant_ref},
            "op": "eq" if condition_expr.operator == "=" else "ne",
            "right": tag.variant_name,
        }
    }


def _variant_field_names(
    context: _LoweringContext,
    *,
    union_name: str,
    variant_name: str,
    span,
    form_path: tuple[str, ...],
) -> tuple[str, ...]:
    union_type = context.type_env.resolve_type(union_name, span=span, form_path=form_path)
    if not isinstance(union_type, UnionTypeRef):
        return ()
    variant_type = context.type_env.union_variant(
        union_type,
        variant_name,
        span=span,
        form_path=form_path,
    )
    return tuple(field.name for field in variant_type.definition.fields)


def _step_references_any_prefix(value: Any, prefixes: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(prefix in value for prefix in prefixes)
    if isinstance(value, (list, tuple)):
        return any(_step_references_any_prefix(item, prefixes) for item in value)
    if isinstance(value, Mapping):
        return any(_step_references_any_prefix(item, prefixes) for item in value.values())
    return False


def _attach_branch_proof_guards(
    steps: list[dict[str, Any]],
    *,
    proof_context: tuple[object, ...],
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    span,
    form_path: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Attach ``requires_variant`` to the first consumer of each narrowed field."""
    if not proof_context:
        return steps
    guarded = [dict(step) for step in steps]
    for triple in proof_context:
        binding_name, union_name, variant_name = triple
        producer_step_name = _local_value_source_step_name(local_values.get(binding_name))
        if not isinstance(producer_step_name, str):
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="variant_guard_producer_missing",
                        message=(
                            f"variant proof for `{binding_name}` could not resolve "
                            "a producer step identity"
                        ),
                        span=span,
                        form_path=form_path,
                        phase="lowering",
                    ),
                )
            )
        field_names = _variant_field_names(
            context,
            union_name=union_name,
            variant_name=variant_name,
            span=span,
            form_path=form_path,
        )
        guard = _requires_variant_guard(
            producer_step_name=producer_step_name,
            required_variant=variant_name,
        )
        prefixes = tuple(
            f"{scope}steps.{producer_step_name}.artifacts.{field_name}"
            for scope in ("root.", "self.", "parent.")
            for field_name in field_names
        )
        if not prefixes:
            continue
        for step in guarded:
            if _step_references_any_prefix(step, prefixes):
                step.setdefault("requires_variant", guard)
                break
    return guarded



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
    condition_shape = body.condition_shape
    discriminant_condition = None
    if isinstance(condition_shape, PureExprCondition):
        discriminant_condition = _render_discriminant_condition(
            condition_shape.expr,
            local_values=local_values,
        )
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
    if discriminant_condition is not None:
        condition = discriminant_condition
    elif pure_condition_expr is not None:
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
    then_local_values = (
        {**dict(local_values), _ACTIVE_VARIANT_PROOFS_KEY: body.then_proof_context}
        if body.then_proof_context
        else local_values
    )
    else_local_values = (
        {**dict(local_values), _ACTIVE_VARIANT_PROOFS_KEY: body.else_proof_context}
        if body.else_proof_context
        else local_values
    )
    then_steps, then_terminal = _defunctionalize_body(
        body.then_body,
        context=lowering_core._copy_context_with_step_prefix(context, step_name_prefix=then_step_name),
        local_values=then_local_values,
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
        local_values=else_local_values,
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
    then_steps = _attach_branch_proof_guards(
        then_steps,
        proof_context=body.then_proof_context,
        context=context,
        local_values=local_values,
        span=body.then_body.metadata.source_span,
        form_path=body.then_body.metadata.form_path,
    )
    else_steps = _attach_branch_proof_guards(
        else_steps,
        proof_context=body.else_proof_context,
        context=context,
        local_values=local_values,
        span=body.else_body.metadata.source_span,
        form_path=body.else_body.metadata.form_path,
    )
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
    if _contains_schema2_list_form(
        resolved_expr,
        local_values=local_values,
    ):
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
    if isinstance(
        expr,
        (
            CompilerListNonemptyHeadExpr,
            PureOpExpr,
            ListExpr,
            ListMapExpr,
            PathJoinUnderExpr,
        ),
    ):
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


def _contains_schema2_list_form(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
) -> bool:
    if isinstance(
        expr,
        (
            CompilerListNonemptyHeadExpr,
            ListExpr,
            ListMapExpr,
            PathJoinUnderExpr,
        ),
    ):
        return True
    if isinstance(expr, PureOpExpr):
        spec = PURE_EXPR_OPERATOR_CATALOG.get(expr.operator)
        if spec is not None and spec.min_schema_version >= 2:
            return True
    if isinstance(expr, NameExpr):
        local_expr = local_values.get(expr.name)
        return (
            local_expr is not None
            and local_expr is not expr
            and _contains_schema2_list_form(
                local_expr,
                local_values=local_values,
            )
        )
    try:
        children = iter_child_exprs(expr)
    except TypeError:
        return False
    return any(
        _contains_schema2_list_form(child, local_values=local_values)
        for child in children
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


def _raise_provider_peer_group_lowering_error(
    owner: WccProviderPeerGroup | WccProviderPeerGroupMember,
    *,
    code: str,
    message: str,
) -> None:
    metadata = owner.metadata
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=metadata.source_span,
                form_path=metadata.form_path,
                expansion_stack=metadata.expansion_stack,
                phase="lowering",
            ),
        )
    )


def _isolated_provider_peer_group_member_context(
    context: _LoweringContext,
    *,
    step_name_prefix: str,
) -> _LoweringContext:
    """Return a side-effect-isolated context for one peer member."""

    return replace(
        context,
        step_name_prefix=step_name_prefix,
        step_spans={},
        generated_input_spans={},
        authored_generated_inputs=set(),
        internal_generated_input_reasons={},
        internal_generated_input_contracts={},
        private_exec_context_bindings=[],
        generated_output_spans={},
        generated_path_spans={},
        generated_path_allocations=[],
        generated_semantic_effects=[],
        compiler_prompt_dependency_contracts={},
        prompt_dependency_lineages=[],
        output_projection_metadata={},
        top_level_artifacts={},
        inline_call_counters=dict(context.inline_call_counters),
        generated_contract_field_bindings=(
            context.generated_contract_field_bindings
        ),
        provider_supervision_origins={},
        provider_supervision_prompt_dependency_lineages=[],
        provider_peer_group_origins={},
        provider_peer_group_prompt_dependency_lineages=[],
    )


def _provider_peer_group_origin(
    metadata: object,
    *,
    owner_key: str,
) -> LoweringOrigin:
    return LoweringOrigin(
        span=metadata.source_span,
        form_path=metadata.form_path,
        origin_key=owner_key,
        expansion_stack=metadata.expansion_stack,
    )


def _record_provider_peer_group_origin(
    context: _LoweringContext,
    *,
    owner_key: str,
    metadata: object | None = None,
    origin: LoweringOrigin | None = None,
) -> None:
    if (metadata is None) == (origin is None):
        raise TypeError(
            "provider peer group origin requires exactly one source owner"
        )
    resolved = (
        _provider_peer_group_origin(metadata, owner_key=owner_key)
        if metadata is not None
        else replace(origin, origin_key=owner_key)
    )
    existing = context.provider_peer_group_origins.get(owner_key)
    if existing is not None and existing != resolved:
        raise TypeError(
            f"provider peer group source owner collision: {owner_key}"
        )
    context.provider_peer_group_origins[owner_key] = resolved



def _wrap_free_env_owner_names(
    result,
    env: Mapping[str, object],
    *,
    metadata,
):
    """Re-bind still-free names whose env values are non-name replacements.

    Generic opaque reconstruction inlines ``NameExpr``/``FieldAccessExpr`` env
    replacements and leaves field-access bases name-rooted; any other env
    replacement still free in ``result`` is wrapped in one surrounding
    ``let*`` so the owner stays bound. Bindings follow env order.
    """

    free_names = set(free_expr_names(result))
    # Reverse closure: a retained owner may reference an earlier collapsed
    # owner by name; pull those in so every retained replacement stays bound.
    changed = True
    while changed:
        changed = False
        for name in tuple(free_names):
            if name not in env or isinstance(
                env[name],
                (NameExpr, FieldAccessExpr),
            ):
                continue
            for dependency in free_expr_names(env[name]):
                if dependency in env and dependency not in free_names:
                    free_names.add(dependency)
                    changed = True
    retained = [
        name
        for name in env
        if name in free_names
        and not isinstance(env[name], (NameExpr, FieldAccessExpr))
    ]
    if not retained:
        return result
    return LetStarExpr(
        bindings=tuple((name, cast(ExprNode, env[name])) for name in retained),
        body=cast(ExprNode, result),
        span=metadata.source_span,
        form_path=metadata.form_path,
        expansion_stack=metadata.expansion_stack,
    )


def _provider_peer_group_member_projection(
    member: WccProviderPeerGroupMember,
) -> tuple[WccPerform, Mapping[str, object], object, tuple[tuple[str, IfExpr, TypeRef], ...]]:
    """Extract one provider perform and its pure projected peer value."""

    env: dict[str, object] = {}
    provider_perform: WccPerform | None = None
    provider_env: dict[str, object] | None = None
    preludes: list[tuple[str, IfExpr, TypeRef]] = []
    current = member.normalized_body
    while isinstance(current, WccLet):
        if isinstance(current.bound_value, WccPerform):
            if provider_perform is not None:
                _raise_provider_peer_group_lowering_error(
                    member,
                    code="provider_peer_group_member_ineligible",
                    message=(
                        "provider peer group member lowered more than one "
                        "provider owner"
                    ),
                )
            provider_perform = current.bound_value
            provider_env = dict(env)
            env[current.bound_name] = NameExpr(
                name=member.binding_name,
                span=current.metadata.source_span,
                form_path=current.metadata.form_path,
                expansion_stack=current.metadata.expansion_stack,
            )
        elif isinstance(current.bound_value, WccSelect) and provider_perform is None:
            preludes.append(
                (
                    current.bound_name,
                    _frontend_expr_from_wcc_value_with_env(
                        current.bound_value,
                        env,
                    ),
                    current.bound_value.metadata.type_ref,
                )
            )
            env[current.bound_name] = NameExpr(
                name=current.bound_name,
                span=current.metadata.source_span,
                form_path=current.metadata.form_path,
                expansion_stack=current.metadata.expansion_stack,
            )
        else:
            env[current.bound_name] = _frontend_expr_from_wcc_value_with_env(
                current.bound_value,
                env,
            )
        current = current.body
    if (
        provider_perform is None
        or provider_env is None
        or not isinstance(current, WccHalt)
    ):
        _raise_provider_peer_group_lowering_error(
            member,
            code="provider_peer_group_member_ineligible",
            message=(
                "provider peer group member did not retain one closed "
                "provider projection"
            ),
        )
    result = _frontend_expr_from_wcc_value_with_env(current.result, env)
    result = _wrap_free_env_owner_names(
        result,
        env,
        metadata=current.result.metadata,
    )
    return (
        provider_perform,
        provider_env,
        result,
        tuple(preludes),
    )


def _positive_provider_peer_group_timeout(
    member: WccProviderPeerGroupMember,
    perform: WccPerform,
) -> int:
    payload = (
        perform.operation_payload
        if isinstance(perform.operation_payload, Mapping)
        else {}
    )
    timeout = payload.get("timeout_sec")
    if (
        not isinstance(timeout, WccLiteralAtom)
        or timeout.literal_kind != "int"
        or isinstance(timeout.value, bool)
        or not isinstance(timeout.value, int)
        or timeout.value <= 0
    ):
        _raise_provider_peer_group_lowering_error(
            member,
            code="provider_peer_group_member_timeout_required",
            message=(
                "provider peer group members require an explicit positive "
                "integer :timeout-sec"
            ),
        )
    return timeout.value


def _raise_provider_supervision_lowering_error(
    owner: WccProviderSupervision | WccProviderSupervisionMember,
    *,
    code: str,
    message: str,
) -> None:
    metadata = owner.metadata
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=metadata.source_span,
                form_path=metadata.form_path,
                expansion_stack=metadata.expansion_stack,
                phase="lowering",
            ),
        )
    )


def _isolated_provider_supervision_member_context(
    context: _LoweringContext,
    *,
    step_name_prefix: str,
) -> _LoweringContext:
    """Return a side-effect-isolated context for one non-emitted member."""

    return replace(
        context,
        step_name_prefix=step_name_prefix,
        step_spans={},
        generated_input_spans={},
        authored_generated_inputs=set(),
        internal_generated_input_reasons={},
        internal_generated_input_contracts={},
        private_exec_context_bindings=[],
        generated_output_spans={},
        generated_path_spans={},
        generated_path_allocations=[],
        generated_semantic_effects=[],
        compiler_prompt_dependency_contracts={},
        prompt_dependency_lineages=[],
        output_projection_metadata={},
        top_level_artifacts={},
        inline_call_counters=dict(context.inline_call_counters),
        generated_contract_field_bindings=(
            context.generated_contract_field_bindings
        ),
        provider_supervision_origins={},
        provider_supervision_prompt_dependency_lineages=[],
        provider_peer_group_origins={},
        provider_peer_group_prompt_dependency_lineages=[],
    )


def _provider_supervision_origin(
    metadata: object,
    *,
    owner_key: str,
) -> LoweringOrigin:
    return LoweringOrigin(
        span=metadata.source_span,
        form_path=metadata.form_path,
        origin_key=owner_key,
        expansion_stack=metadata.expansion_stack,
    )


def _record_provider_supervision_origin(
    context: _LoweringContext,
    *,
    owner_key: str,
    metadata: object | None = None,
    origin: LoweringOrigin | None = None,
) -> None:
    if (metadata is None) == (origin is None):
        raise TypeError(
            "provider supervision origin requires exactly one source owner"
        )
    resolved = (
        _provider_supervision_origin(metadata, owner_key=owner_key)
        if metadata is not None
        else replace(origin, origin_key=owner_key)
    )
    existing = context.provider_supervision_origins.get(owner_key)
    if existing is not None and existing != resolved:
        raise TypeError(
            f"provider supervision source owner collision: {owner_key}"
        )
    context.provider_supervision_origins[owner_key] = resolved


def _provider_supervision_member_projection(
    member: WccProviderSupervisionMember,
) -> tuple[WccPerform, Mapping[str, object], object, tuple[tuple[str, IfExpr, TypeRef], ...]]:
    """Extract one provider perform and its pure projected member value."""

    env: dict[str, object] = {}
    provider_perform: WccPerform | None = None
    provider_env: dict[str, object] | None = None
    preludes: list[tuple[str, IfExpr, TypeRef]] = []
    current = member.normalized_body
    while isinstance(current, WccLet):
        if isinstance(current.bound_value, WccPerform):
            if provider_perform is not None:
                _raise_provider_supervision_lowering_error(
                    member,
                    code="provider_supervision_member_ineligible",
                    message=(
                        "provider supervision member lowered more than one "
                        "provider owner"
                    ),
                )
            provider_perform = current.bound_value
            provider_env = dict(env)
            env[current.bound_name] = NameExpr(
                name=member.binding_name,
                span=current.metadata.source_span,
                form_path=current.metadata.form_path,
                expansion_stack=current.metadata.expansion_stack,
            )
        elif isinstance(current.bound_value, WccSelect) and provider_perform is None:
            preludes.append(
                (
                    current.bound_name,
                    _frontend_expr_from_wcc_value_with_env(
                        current.bound_value,
                        env,
                    ),
                    current.bound_value.metadata.type_ref,
                )
            )
            env[current.bound_name] = NameExpr(
                name=current.bound_name,
                span=current.metadata.source_span,
                form_path=current.metadata.form_path,
                expansion_stack=current.metadata.expansion_stack,
            )
        else:
            env[current.bound_name] = _frontend_expr_from_wcc_value_with_env(
                current.bound_value,
                env,
            )
        current = current.body
    if (
        provider_perform is None
        or provider_env is None
        or not isinstance(current, WccHalt)
    ):
        _raise_provider_supervision_lowering_error(
            member,
            code="provider_supervision_member_ineligible",
            message=(
                "provider supervision member did not retain one closed "
                "provider projection"
            ),
        )
    result = _frontend_expr_from_wcc_value_with_env(current.result, env)
    result = _wrap_free_env_owner_names(
        result,
        env,
        metadata=current.result.metadata,
    )
    return (
        provider_perform,
        provider_env,
        result,
        tuple(preludes),
    )


def _materialize_member_conditional_preludes(
    preludes: tuple[tuple[str, IfExpr, TypeRef], ...],
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    member_step_name: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Materialize pre-provider pure conditional member inputs once.

    Each authored pure conditional selection consumed as a member perform input
    becomes exactly one owner-scope ``pure_projection`` step. The returned ref
    mapping keys the authored binding name to the projection's
    ``root.steps.*`` output ref, which the existing ``typed_binding_ref`` input
    source then targets.
    """

    prelude_steps: list[dict[str, Any]] = []
    refs: dict[str, str] = {}
    mutable_locals: dict[str, Any] = dict(local_values)
    mutable_context = context
    for binding_name, ifexpr, type_ref in preludes:
        step_name = f"{member_step_name}__{binding_name}"
        step_id = lowering_core._normalize_generated_step_id(step_name)
        lowered = lower_pure_projection_step(
            ifexpr,
            result_type=type_ref,
            context=mutable_context,
            local_values=mutable_locals,
            step_name=step_name,
            step_id=step_id,
            stable_target="binding_projection",
        )
        prelude_steps.append(lowered.step)
        refs[binding_name] = lowered.output_refs["return"]
        mutable_locals[binding_name] = lowered.output_refs["return"]
        mutable_context = _context_with_local_type_binding(
            mutable_context,
            binding_name=binding_name,
            binding_type=type_ref,
        )
    return prelude_steps, refs




def _positive_provider_supervision_timeout(
    member: WccProviderSupervisionMember,
    perform: WccPerform,
) -> int:
    payload = (
        perform.operation_payload
        if isinstance(perform.operation_payload, Mapping)
        else {}
    )
    timeout = payload.get("timeout_sec")
    if (
        not isinstance(timeout, WccLiteralAtom)
        or timeout.literal_kind != "int"
        or isinstance(timeout.value, bool)
        or not isinstance(timeout.value, int)
        or timeout.value <= 0
    ):
        _raise_provider_supervision_lowering_error(
            member,
            code="provider_supervision_member_timeout_required",
            message=(
                "provider supervision members require an explicit positive "
                "integer :timeout-sec"
            ),
        )
    return timeout.value


def _frozen_mapping(value: object) -> Mapping[str, Any]:
    frozen = freeze_value(value if isinstance(value, Mapping) else {})
    if not isinstance(frozen, Mapping):
        raise TypeError("expected a frozen mapping")
    return frozen


def _pathless_provider_contract_prototype(
    step: Mapping[str, Any],
    field_name: str,
) -> Any:
    value = step.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(
            f"generated provider {field_name} must be a mapping"
        )
    if not isinstance(value.get("path"), str) or not value["path"]:
        raise TypeError(
            f"generated provider {field_name} must carry one path"
        )
    return freeze_value(
        {
            key: item
            for key, item in value.items()
            if key != "path"
        }
    )


def _provider_step_config_from_generated_mapping(
    step: Mapping[str, Any],
    *,
    timeout_sec: int,
    compiler_prompt_dependency_contract: object | None,
) -> ProviderStepConfig:
    """Bind one ordinary generated provider mapping into its typed config."""

    allowed_fields = {
        "name",
        "id",
        "provider",
        "provider_params",
        "provider_call_policy",
        "input_file",
        "asset_file",
        "depends_on",
        "asset_depends_on",
        "inject_output_contract",
        "inject_consumes",
        "prompt_consumes",
        "typed_prompt_inputs",
        "consumes_injection_position",
        "consumes",
        "consume_bundle",
        "publishes",
        "expected_outputs",
        "output_bundle",
        "variant_output",
        "pre_snapshot",
        "requires_variant",
        "persist_artifacts_in_state",
        "provider_session",
        "max_visits",
        "retries",
        "env",
        "secrets",
        "timeout_sec",
        "output_capture",
        "output_file",
        "allow_parse_error",
    }
    unknown = set(step) - allowed_fields
    if unknown:
        raise TypeError(
            "unsupported generated provider fields in supervision member: "
            + ", ".join(sorted(unknown))
        )
    provider = step.get("provider")
    if not isinstance(provider, str) or not provider:
        raise TypeError(
            "provider supervision member requires one generated provider"
        )
    prompt_consumes = step.get("prompt_consumes")
    call_policy = step.get("provider_call_policy")
    return ProviderStepConfig(
        common=StepCommonConfig(
            consumes=tuple(
                freeze_value(item)
                for item in (step.get("consumes") or ())
            ),
            consume_bundle=freeze_value(step.get("consume_bundle")),
            publishes=tuple(
                freeze_value(item)
                for item in (step.get("publishes") or ())
            ),
            expected_outputs=tuple(
                freeze_value(item)
                for item in (step.get("expected_outputs") or ())
            ),
            output_bundle=_pathless_provider_contract_prototype(
                step,
                "output_bundle",
            ),
            variant_output=_pathless_provider_contract_prototype(
                step,
                "variant_output",
            ),
            pre_snapshot=freeze_value(step.get("pre_snapshot")),
            requires_variant=freeze_value(step.get("requires_variant")),
            persist_artifacts_in_state=step.get(
                "persist_artifacts_in_state"
            ),
            provider_session=_frozen_mapping(step.get("provider_session"))
            if isinstance(step.get("provider_session"), Mapping)
            else None,
            max_visits=step.get("max_visits"),
            retries=freeze_value(step.get("retries")),
            env=_frozen_mapping(step.get("env"))
            if isinstance(step.get("env"), Mapping)
            else None,
            secrets=tuple(str(item) for item in (step.get("secrets") or ())),
            timeout_sec=timeout_sec,
            output_capture=freeze_value(step.get("output_capture")),
            output_file=freeze_value(step.get("output_file")),
            allow_parse_error=step.get("allow_parse_error"),
        ),
        provider=provider,
        provider_params=freeze_value(step.get("provider_params")),
        provider_call_policy=(
            _frozen_mapping(call_policy)
            if isinstance(call_policy, Mapping)
            else None
        ),
        input_file=freeze_value(step.get("input_file")),
        asset_file=freeze_value(step.get("asset_file")),
        depends_on=_frozen_mapping(step.get("depends_on")),
        asset_depends_on=tuple(
            freeze_value(item)
            for item in (step.get("asset_depends_on") or ())
        ),
        inject_output_contract=step.get("inject_output_contract"),
        inject_consumes=step.get("inject_consumes"),
        prompt_consumes=(
            tuple(freeze_value(item) for item in prompt_consumes)
            if isinstance(prompt_consumes, (list, tuple))
            else None
        ),
        typed_prompt_inputs=tuple(
            freeze_value(item)
            for item in (step.get("typed_prompt_inputs") or ())
        ),
        consumes_injection_position=step.get(
            "consumes_injection_position"
        ),
        compiler_prompt_dependency_contract=(
            compiler_prompt_dependency_contract
        ),
    )


def _provider_supervision_contract(
    *,
    name: str,
    type_ref: TypeRef,
    type_env: object,
    source_read_trace: SourceReadTrace | None = None,
) -> ExecutableContract:
    descriptor = _type_descriptor(
        type_ref,
        type_env=type_env,
        source_read_trace=source_read_trace,
    )
    canonical_name, contract_kind, value_type = (
        derive_result_contract_identity(descriptor)
    )
    if name != type_ref.name:
        raise ValueError(
            "provider supervision result contract owner name changed"
        )
    return ExecutableContract(
        name=canonical_name,
        kind=contract_kind,
        value_type=value_type,
        definition=_frozen_mapping({"type": descriptor}),
    )


def _provider_peer_group_contract(
    *,
    name: str,
    type_ref: TypeRef,
    type_env: object,
    source_read_trace: SourceReadTrace | None = None,
) -> ExecutableContract:
    descriptor = _type_descriptor(
        type_ref,
        type_env=type_env,
        source_read_trace=source_read_trace,
    )
    canonical_name, contract_kind, value_type = (
        derive_result_contract_identity(descriptor)
    )
    if name != type_ref.name:
        raise ValueError(
            "provider peer group result contract owner name changed"
        )
    return ExecutableContract(
        name=canonical_name,
        kind=contract_kind,
        value_type=value_type,
        definition=_frozen_mapping({"type": descriptor}),
    )


def _provider_peer_group_checkpoint_identity_payload(
    config: ProviderPeerGroupStepConfig,
    *,
    target_dsl_version: str,
) -> dict[str, Any]:
    """Return the complete canonical peer config used by point identity."""

    if not isinstance(target_dsl_version, str) or not target_dsl_version:
        raise ValueError(
            "provider peer group checkpoint identity requires target DSL"
        )
    common = _executable_ir_json_value(config.common)
    if not isinstance(common, dict):
        raise TypeError(
            "provider peer group common config must serialize to an object"
        )
    return {
        "target_dsl_version": target_dsl_version,
        "common": common,
        "provider_peer_group": (
            provider_peer_group_config_to_runtime_dict(config)
        ),
    }


def _lower_provider_peer_group_member(
    member: WccProviderPeerGroupMember,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    group_step_name: str,
) -> tuple[ProviderPeerGroupMemberConfig, object, TypeRef, list[dict[str, Any]]]:
    perform, provider_env, projection, preludes = (
        _provider_peer_group_member_projection(member)
    )
    timeout_sec = _positive_provider_peer_group_timeout(
        member,
        perform,
    )
    payload = (
        perform.operation_payload
        if isinstance(perform.operation_payload, Mapping)
        else {}
    )
    member_step_name = f"{group_step_name}__{member.binding_name}"
    member_context = _isolated_provider_peer_group_member_context(
        context,
        step_name_prefix=member_step_name,
    )
    prelude_steps, prelude_refs = _materialize_member_conditional_preludes(
        preludes,
        context=context,
        local_values=local_values,
        member_step_name=member_step_name,
    )
    for binding_name, _ifexpr, type_ref in preludes:
        member_context = _context_with_local_type_binding(
            member_context,
            binding_name=binding_name,
            binding_type=type_ref,
        )
    member_local_values = {
        **dict(local_values),
        **dict(provider_env),
        **prelude_refs,
    }
    member_steps, _terminal = _lower_provider_result_operation(
        LowerableProviderResult(
            provider_name=perform.target_name,
            prompt_name=perform.prompt_name,
            inputs=tuple(
                _frontend_expr_from_wcc_value_with_env(
                    argument,
                    provider_env,
                )
                for argument in perform.positional_args
            ),
            span=perform.metadata.source_span,
            form_path=perform.metadata.form_path,
            expansion_stack=perform.metadata.expansion_stack,
            guidance=(
                payload["return_spec"].guidance
                if payload.get("return_spec") is not None
                else None
            ),
            model=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["model"],
                    provider_env,
                )
                if payload.get("model") is not None
                else None
            ),
            effort=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["effort"],
                    provider_env,
                )
                if payload.get("effort") is not None
                else None
            ),
            delivery=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["delivery"],
                    provider_env,
                )
                if payload.get("delivery") is not None
                else None
            ),
            materialization_attempts=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["materialization_attempts"],
                    provider_env,
                )
                if payload.get("materialization_attempts") is not None
                else None
            ),
            prompt_application=_prompt_application_from_wcc_payload(
                payload,
                env=provider_env,
            ),
            timeout_sec=_frontend_expr_from_wcc_value_with_env(
                payload["timeout_sec"],
                provider_env,
            ),
            prompt_dependencies=_prompt_dependency_spec_from_wcc_payload(
                payload.get("prompt_dependencies")
            ),
        ),
        result_type=perform.metadata.type_ref,
        context=member_context,
        local_values=member_local_values,
        step_name=member_step_name,
    )
    if (
        len(member_steps) != 1
        or not isinstance(member_steps[0], Mapping)
        or "provider" not in member_steps[0]
    ):
        _raise_provider_peer_group_lowering_error(
            member,
            code="provider_peer_group_member_translation_invalid",
            message=(
                "provider peer group member translation must produce exactly "
                "one provider owner and no prelude steps"
            ),
        )
    provider_step = member_steps[0]
    provider_step_id = provider_step.get("id")
    prompt_contract = (
        member_context.compiler_prompt_dependency_contracts.get(
            provider_step_id
        )
        if isinstance(provider_step_id, str)
        else None
    )
    if prompt_contract is None:
        try:
            source_workflow_bytes = _read_source_file_views(
                context.workflow_path,
                source_read_trace=context.source_read_trace,
            ).raw_bytes
        except OSError:
            _raise_provider_peer_group_lowering_error(
                member,
                code="provider_peer_group_member_source_unreadable",
                message=(
                    "provider peer group member source bytes could not be "
                    "read for its prompt-dependency contract"
                ),
            )
        prompt_origin_key = (
            f"{context.workflow_name}::"
            "provider_peer_group_member_prompt_dependencies::"
            f"{provider_step_id}"
        )
        prompt_contract = _build_compiler_prompt_dependency_contract(
            required_binding_refs=(),
            optional_binding_refs=(),
            position=PromptDependencyPosition.PREPEND,
            instruction=None,
            source_origin_key=prompt_origin_key,
            source_workflow_bytes=source_workflow_bytes,
            origin_kind=(
                PromptDependencyOriginKind
                .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY
            ),
        )
        provider_step = {
            **provider_step,
            "depends_on": {
                "required": [],
                "optional": [],
                "inject": {
                    "mode": "content",
                    "position": "prepend",
                },
            },
        }
        _record_provider_peer_group_origin(
            context,
            owner_key=prompt_origin_key,
            metadata=perform.metadata,
        )
    else:
        lineage = next(
            (
                candidate
                for candidate in member_context.prompt_dependency_lineages
                if candidate.step_id == provider_step_id
                and candidate.source_origin_key
                == prompt_contract.source_origin_key
            ),
            None,
        )
        if lineage is None:
            _raise_provider_peer_group_lowering_error(
                member,
                code="provider_peer_group_member_prompt_lineage_missing",
                message=(
                    "provider peer group member prompt-dependency contract "
                    "has no exact source lineage"
                ),
            )
        _record_provider_peer_group_origin(
            context,
            owner_key=prompt_contract.source_origin_key,
            origin=lineage.clause_origin,
        )
        lineage_identity = (
            lineage.step_id,
            lineage.source_origin_key,
        )
        existing_lineage = next(
            (
                candidate
                for candidate in (
                    context
                    .provider_peer_group_prompt_dependency_lineages
                )
                if (
                    candidate.step_id,
                    candidate.source_origin_key,
                )
                == lineage_identity
            ),
            None,
        )
        if existing_lineage is not None and existing_lineage != lineage:
            _raise_provider_peer_group_lowering_error(
                member,
                code="provider_peer_group_member_prompt_lineage_duplicate",
                message=(
                    "provider peer group member prompt-dependency lineage "
                    "conflicts with an existing nested member"
                ),
            )
        if existing_lineage is None:
            context.provider_peer_group_prompt_dependency_lineages.append(
                lineage
            )
    try:
        provider_config = _provider_step_config_from_generated_mapping(
            provider_step,
            timeout_sec=timeout_sec,
            compiler_prompt_dependency_contract=prompt_contract,
        )
        result_contract = _provider_peer_group_contract(
            name=perform.metadata.type_ref.name,
            type_ref=perform.metadata.type_ref,
            type_env=context.type_env,
            source_read_trace=context.source_read_trace,
        )
    except (TypeError, ValueError) as exc:
        _raise_provider_peer_group_lowering_error(
            member,
            code="provider_peer_group_member_translation_invalid",
            message=(
                "provider peer group member translation did not produce one "
                "closed typed provider config"
            ),
        )
        raise AssertionError("unreachable") from exc
    return (
        ProviderPeerGroupMemberConfig(
            member_id=member.binding_name,
            provider_config=provider_config,
            result_contract=result_contract,
            timeout_sec=timeout_sec,
        ),
        projection,
        perform.metadata.type_ref,
        prelude_steps,
    )


def _lower_provider_supervision_member(
    member: WccProviderSupervisionMember,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    group_step_name: str,
) -> tuple[ProviderSupervisionMemberConfig, object, TypeRef, list[dict[str, Any]]]:
    perform, provider_env, projection, preludes = (
        _provider_supervision_member_projection(member)
    )
    timeout_sec = _positive_provider_supervision_timeout(
        member,
        perform,
    )
    payload = (
        perform.operation_payload
        if isinstance(perform.operation_payload, Mapping)
        else {}
    )
    member_step_name = (
        f"{group_step_name}__{member.binding_name}"
    )
    member_context = _isolated_provider_supervision_member_context(
        context,
        step_name_prefix=member_step_name,
    )
    prelude_steps, prelude_refs = _materialize_member_conditional_preludes(
        preludes,
        context=context,
        local_values=local_values,
        member_step_name=member_step_name,
    )
    for binding_name, _ifexpr, type_ref in preludes:
        member_context = _context_with_local_type_binding(
            member_context,
            binding_name=binding_name,
            binding_type=type_ref,
        )
    member_local_values = {
        **dict(local_values),
        **dict(provider_env),
        **prelude_refs,
    }
    member_steps, _terminal = _lower_provider_result_operation(
        LowerableProviderResult(
            provider_name=perform.target_name,
            prompt_name=perform.prompt_name,
            inputs=tuple(
                _frontend_expr_from_wcc_value_with_env(
                    argument,
                    provider_env,
                )
                for argument in perform.positional_args
            ),
            span=perform.metadata.source_span,
            form_path=perform.metadata.form_path,
            expansion_stack=perform.metadata.expansion_stack,
            guidance=(
                payload["return_spec"].guidance
                if payload.get("return_spec") is not None
                else None
            ),
            model=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["model"],
                    provider_env,
                )
                if payload.get("model") is not None
                else None
            ),
            effort=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["effort"],
                    provider_env,
                )
                if payload.get("effort") is not None
                else None
            ),
            delivery=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["delivery"],
                    provider_env,
                )
                if payload.get("delivery") is not None
                else None
            ),
            materialization_attempts=(
                _frontend_expr_from_wcc_value_with_env(
                    payload["materialization_attempts"],
                    provider_env,
                )
                if payload.get("materialization_attempts") is not None
                else None
            ),
            prompt_application=_prompt_application_from_wcc_payload(
                payload,
                env=provider_env,
            ),
            timeout_sec=_frontend_expr_from_wcc_value_with_env(
                payload["timeout_sec"],
                provider_env,
            ),
            prompt_dependencies=_prompt_dependency_spec_from_wcc_payload(
                payload.get("prompt_dependencies")
            ),
        ),
        result_type=perform.metadata.type_ref,
        context=member_context,
        local_values=member_local_values,
        step_name=member_step_name,
    )
    if (
        len(member_steps) != 1
        or not isinstance(member_steps[0], Mapping)
        or "provider" not in member_steps[0]
    ):
        _raise_provider_supervision_lowering_error(
            member,
            code="provider_supervision_member_translation_invalid",
            message=(
                "provider supervision member translation must produce "
                "exactly one provider owner and no prelude steps"
            ),
        )
    provider_step = member_steps[0]
    provider_step_id = provider_step.get("id")
    prompt_contract = (
        member_context.compiler_prompt_dependency_contracts.get(
            provider_step_id
        )
        if isinstance(provider_step_id, str)
        else None
    )
    if prompt_contract is None:
        try:
            source_workflow_bytes = _read_source_file_views(
                context.workflow_path,
                source_read_trace=context.source_read_trace,
            ).raw_bytes
        except OSError:
            _raise_provider_supervision_lowering_error(
                member,
                code="provider_supervision_member_source_unreadable",
                message=(
                    "provider supervision member source bytes could not "
                    "be read for its prompt-dependency contract"
                ),
            )
        prompt_origin_key = (
            f"{context.workflow_name}::"
            "provider_supervision_member_prompt_dependencies::"
            f"{provider_step_id}"
        )
        prompt_contract = _build_compiler_prompt_dependency_contract(
            required_binding_refs=(),
            optional_binding_refs=(),
            position=PromptDependencyPosition.PREPEND,
            instruction=None,
            source_origin_key=prompt_origin_key,
            source_workflow_bytes=source_workflow_bytes,
            origin_kind=(
                PromptDependencyOriginKind
                .WORKFLOW_LISP_PROVIDER_SUPERVISION_MEMBER_IMPLICIT_EMPTY
            ),
        )
        provider_step = {
            **provider_step,
            "depends_on": {
                "required": [],
                "optional": [],
                "inject": {
                    "mode": "content",
                    "position": "prepend",
                },
            },
        }
        _record_provider_supervision_origin(
            context,
            owner_key=prompt_origin_key,
            metadata=perform.metadata,
        )
    else:
        lineage = next(
            (
                candidate
                for candidate in member_context.prompt_dependency_lineages
                if candidate.step_id == provider_step_id
                and candidate.source_origin_key
                == prompt_contract.source_origin_key
            ),
            None,
        )
        if lineage is None:
            _raise_provider_supervision_lowering_error(
                member,
                code="provider_supervision_member_prompt_lineage_missing",
                message=(
                    "provider supervision member prompt-dependency "
                    "contract has no exact source lineage"
                ),
            )
        _record_provider_supervision_origin(
            context,
            owner_key=prompt_contract.source_origin_key,
            origin=lineage.clause_origin,
        )
        lineage_identity = (
            lineage.step_id,
            lineage.source_origin_key,
        )
        existing_lineage = next(
            (
                candidate
                for candidate in (
                    context
                    .provider_supervision_prompt_dependency_lineages
                )
                if (
                    candidate.step_id,
                    candidate.source_origin_key,
                )
                == lineage_identity
            ),
            None,
        )
        if existing_lineage is not None and existing_lineage != lineage:
            _raise_provider_supervision_lowering_error(
                member,
                code=(
                    "provider_supervision_member_prompt_lineage_duplicate"
                ),
                message=(
                    "provider supervision member prompt-dependency "
                    "lineage conflicts with an existing nested member"
                ),
            )
        if existing_lineage is None:
            context.provider_supervision_prompt_dependency_lineages.append(
                lineage
            )
    try:
        provider_config = _provider_step_config_from_generated_mapping(
            provider_step,
            timeout_sec=timeout_sec,
            compiler_prompt_dependency_contract=prompt_contract,
        )
        result_contract = _provider_supervision_contract(
            name=perform.metadata.type_ref.name,
            type_ref=perform.metadata.type_ref,
            type_env=context.type_env,
            source_read_trace=context.source_read_trace,
        )
    except (TypeError, ValueError) as exc:
        _raise_provider_supervision_lowering_error(
            member,
            code="provider_supervision_member_translation_invalid",
            message=(
                "provider supervision member translation did not produce "
                "one closed typed provider config"
            ),
        )
        raise AssertionError("unreachable") from exc
    return (
        ProviderSupervisionMemberConfig(
            member_id=member.binding_name,
            provider_config=provider_config,
            result_contract=result_contract,
            timeout_sec=timeout_sec,
        ),
        projection,
        perform.metadata.type_ref,
        prelude_steps,
    )


def _pure_wcc_body_expr(
    body: WccBody,
    *,
    env: Mapping[str, object],
) -> object:
    resolved = dict(env)
    collapsed: dict[str, object] = {}
    current = body
    while isinstance(current, WccLet):
        bound_name = current.bound_name
        bound_value = _frontend_expr_from_wcc_value_with_env(
            current.bound_value,
            resolved,
        )
        if bound_name in resolved:
            if isinstance(bound_value, (NameExpr, FieldAccessExpr)):
                resolved[bound_name] = bound_value
            else:
                generated = (
                    f"__wcc_settlement_{bound_name}_"
                    f"{current.metadata.node_id.rsplit(':', 1)[-1]}"
                )
                collapsed[generated] = bound_value
                resolved[bound_name] = NameExpr(
                    name=generated,
                    span=current.metadata.source_span,
                    form_path=current.metadata.form_path,
                    expansion_stack=current.metadata.expansion_stack,
                )
        else:
            collapsed[bound_name] = bound_value
            resolved[bound_name] = bound_value
        current = current.body
    if not isinstance(current, WccHalt):
        raise TypeError(
            "provider supervision settlement must be a pure linear WCC body"
        )
    result = _frontend_expr_from_wcc_value_with_env(current.result, resolved)
    return _wrap_free_env_owner_names(
        result,
        collapsed,
        metadata=current.result.metadata,
    )


def _lower_provider_peer_group_binding(
    group: WccProviderPeerGroup,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    group_step_name = (
        f"{context.workflow_name}__result"
        if context.step_name_prefix == context.workflow_name
        else context.step_name_prefix
    )
    group_step_id = lowering_core._normalize_generated_step_id(
        group_step_name
    )
    member_ids = tuple(member.binding_name for member in group.members)
    source_origins = {
        group.metadata.node_id: group.metadata,
        **{
            member.binding_metadata.node_id: member.binding_metadata
            for member in group.members
        },
        group.settlement_body.metadata.node_id: (
            group.settlement_body.metadata
        ),
    }
    if len(source_origins) != len(group.members) + 2:
        _raise_provider_peer_group_lowering_error(
            group,
            code="provider_peer_group_source_ownership_collision",
            message=(
                "provider peer group source ownership must contain the form, "
                "each authored member binding, and settlement as distinct "
                "WCC owners"
            ),
        )
    for owner_key, metadata in source_origins.items():
        _record_provider_peer_group_origin(
            context,
            owner_key=owner_key,
            metadata=metadata,
        )

    lowered_members = tuple(
        _lower_provider_peer_group_member(
            member,
            context=context,
            local_values=local_values,
            group_step_name=group_step_name,
        )
        for member in group.members
    )
    member_prelude_steps = [
        step for lowered in lowered_members for step in lowered[3]
    ]
    member_configs = tuple(item[0] for item in lowered_members)
    member_projections = {
        member.binding_name: lowered[1]
        for member, lowered in zip(
            group.members,
            lowered_members,
            strict=True,
        )
    }
    member_types = {
        member.binding_name: lowered[2]
        for member, lowered in zip(
            group.members,
            lowered_members,
            strict=True,
        )
    }
    settlement_expr = _pure_wcc_body_expr(
        group.settlement_body,
        env=member_projections,
    )
    settlement_context = context
    for member_id in member_ids:
        settlement_context = _context_with_local_type_binding(
            settlement_context,
            binding_name=member_id,
            binding_type=member_types[member_id],
        )
    settlement_payload, binding_refs = build_pure_projection_payload(
        settlement_expr,
        result_type=binding_type,
        context=settlement_context,
        local_values={
            **dict(local_values),
            **{
                member_id: f"provider_peer_group.members.{member_id}"
                for member_id in member_ids
            },
        },
    )
    dynamic_captures = set(binding_refs) - set(member_ids)
    if dynamic_captures:
        metadata = group.settlement_body.metadata
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code=(
                        "provider_peer_group_settlement_dynamic_capture_"
                        "unsupported"
                    ),
                    message=(
                        "provider peer group settlement may capture only its "
                        "authored member bindings"
                    ),
                    span=metadata.source_span,
                    form_path=metadata.form_path,
                    expansion_stack=metadata.expansion_stack,
                    phase="lowering",
                ),
            )
        )
    settlement_payload = {
        **settlement_payload,
        "bindings": {
            member_id: {
                "type": _type_descriptor(
                    member_types[member_id],
                    type_env=context.type_env,
                    source_read_trace=context.source_read_trace,
                )
            }
            for member_id in member_ids
        },
    }
    validate_pure_expr_payload(settlement_payload)
    whole_timeout = max(member.timeout_sec for member in member_configs)
    try:
        settlement_result_contract = _provider_peer_group_contract(
            name=binding_type.name,
            type_ref=binding_type,
            type_env=context.type_env,
            source_read_trace=context.source_read_trace,
        )
    except (TypeError, ValueError) as exc:
        _raise_provider_peer_group_lowering_error(
            group,
            code="provider_peer_group_settlement_contract_invalid",
            message=(
                "provider peer group settlement did not produce one closed "
                "transportable result contract"
            ),
        )
        raise AssertionError("unreachable") from exc
    config = ProviderPeerGroupStepConfig(
        common=StepCommonConfig(timeout_sec=whole_timeout),
        schema_version=PROVIDER_PEER_GROUP_SCHEMA_VERSION,
        node_id=group_step_id,
        members=member_configs,
        messaging_policy=PROVIDER_PEER_GROUP_MESSAGING_POLICY,
        settlement_payload=_frozen_mapping(settlement_payload),
        settlement_result_contract=settlement_result_contract,
        interactive_session_schema_version=(
            INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION
        ),
        max_steers=0,
        paths=derive_provider_peer_group_paths(
            node_id=group_step_id,
            member_ids=member_ids,
        ),
        source_ownership=ProviderPeerGroupSourceOwnership(
            form=group.metadata.node_id,
            members=tuple(
                ProviderPeerGroupMemberSourceOwnership(
                    member_id=member.binding_name,
                    binding=member.binding_metadata.node_id,
                )
                for member in group.members
            ),
            settlement=group.settlement_body.metadata.node_id,
        ),
    )
    try:
        checkpoint_identity_component_digest = _sha256_json(
            _provider_peer_group_checkpoint_identity_payload(
                config,
                target_dsl_version=(
                    context.type_env.target_dsl_version or ""
                ),
            )
        )
    except (TypeError, ValueError) as exc:
        _raise_provider_peer_group_lowering_error(
            group,
            code="provider_peer_group_checkpoint_identity_invalid",
            message=(
                "provider peer group typed config could not produce one "
                "canonical checkpoint identity"
            ),
        )
        raise AssertionError("unreachable") from exc
    source = SimpleNamespace(
        span=group.metadata.source_span,
        form_path=group.metadata.form_path,
        expansion_stack=group.metadata.expansion_stack,
    )
    _record_step_origin(
        context,
        step_name=group_step_name,
        step_id=group_step_id,
        source=source,
    )
    return (
        [
            *member_prelude_steps,
            {
                "name": group_step_name,
                "id": group_step_id,
                "timeout_sec": whole_timeout,
                "provider_peer_group": config,
            },
        ],
        _TerminalResult(
            step_name=group_step_name,
            step_id=group_step_id,
            output_refs=lowering_core._record_output_refs(
                group_step_name,
                binding_type,
            ),
            output_kind="step",
            hidden_inputs={},
            checkpoint_identity_component_digest=(
                checkpoint_identity_component_digest
            ),
            returned_union_type_name=(
                binding_type.name
                if isinstance(binding_type, UnionTypeRef)
                else None
            ),
        ),
    )


def _lower_provider_supervision_binding(
    group: WccProviderSupervision,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    group_step_name = (
        f"{context.workflow_name}__result"
        if context.step_name_prefix == context.workflow_name
        else context.step_name_prefix
    )
    group_step_id = lowering_core._normalize_generated_step_id(
        group_step_name
    )
    members = {
        member.binding_name: member
        for member in group.members
    }
    worker_member = members[group.worker_name]
    supervisor_member = members[group.supervisor_name]
    source_origins = {
        group.metadata.node_id: group.metadata,
        worker_member.binding_metadata.node_id: (
            worker_member.binding_metadata
        ),
        supervisor_member.binding_metadata.node_id: (
            supervisor_member.binding_metadata
        ),
        group.observation_metadata.node_id: group.observation_metadata,
        group.settlement_body.metadata.node_id: (
            group.settlement_body.metadata
        ),
    }
    if len(source_origins) != 5:
        _raise_provider_supervision_lowering_error(
            group,
            code="provider_supervision_source_ownership_collision",
            message=(
                "provider supervision source ownership must contain five "
                "distinct WCC owners"
            ),
        )
    for owner_key, metadata in source_origins.items():
        _record_provider_supervision_origin(
            context,
            owner_key=owner_key,
            metadata=metadata,
        )
    worker, worker_projection, worker_raw_type, worker_preludes = (
        _lower_provider_supervision_member(
            worker_member,
            context=context,
            local_values=local_values,
            group_step_name=group_step_name,
        )
    )
    supervisor, supervisor_projection, supervisor_raw_type, supervisor_preludes = (
        _lower_provider_supervision_member(
            supervisor_member,
            context=context,
            local_values=local_values,
            group_step_name=group_step_name,
        )
    )
    member_prelude_steps = [*worker_preludes, *supervisor_preludes]
    settlement_expr = _pure_wcc_body_expr(
        group.settlement_body,
        env={
            group.worker_name: worker_projection,
            group.supervisor_name: supervisor_projection,
        },
    )
    settlement_context = _context_with_local_type_binding(
        _context_with_local_type_binding(
            context,
            binding_name=group.worker_name,
            binding_type=worker_raw_type,
        ),
        binding_name=group.supervisor_name,
        binding_type=supervisor_raw_type,
    )
    settlement_payload, binding_refs = (
        build_pure_projection_payload(
            settlement_expr,
            result_type=binding_type,
            context=settlement_context,
            local_values={
                **dict(local_values),
                group.worker_name: (
                    f"provider_supervision.members.{group.worker_name}"
                ),
                group.supervisor_name: (
                    f"provider_supervision.members.{group.supervisor_name}"
                ),
            },
        )
    )
    dynamic_captures = set(binding_refs) - {
        group.worker_name,
        group.supervisor_name,
    }
    if dynamic_captures:
        metadata = group.settlement_body.metadata
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code=(
                        "provider_supervision_settlement_dynamic_capture_"
                        "unsupported"
                    ),
                    message=(
                        "provider supervision settlement may capture only "
                        "compile-time outer values and its two member "
                        "bindings"
                    ),
                    span=metadata.source_span,
                    form_path=metadata.form_path,
                    expansion_stack=metadata.expansion_stack,
                    phase="lowering",
                ),
            )
        )
    settlement_bindings = dict(
        settlement_payload.get("bindings", {})
    )
    settlement_bindings[group.worker_name] = {
        "type": _type_descriptor(
            worker_raw_type,
            type_env=context.type_env,
            source_read_trace=context.source_read_trace,
        )
    }
    settlement_bindings[group.supervisor_name] = {
        "type": _type_descriptor(
            supervisor_raw_type,
            type_env=context.type_env,
            source_read_trace=context.source_read_trace,
        )
    }
    settlement_payload = {
        **settlement_payload,
        "bindings": settlement_bindings,
    }
    validate_pure_expr_payload(settlement_payload)
    whole_timeout = (
        max(worker.timeout_sec, supervisor.timeout_sec)
        + worker.timeout_sec
    )
    try:
        settlement_result_contract = _provider_supervision_contract(
            name=binding_type.name,
            type_ref=binding_type,
            type_env=context.type_env,
            source_read_trace=context.source_read_trace,
        )
    except (TypeError, ValueError) as exc:
        _raise_provider_supervision_lowering_error(
            group,
            code="provider_supervision_settlement_contract_invalid",
            message=(
                "provider supervision settlement did not produce "
                "one closed transportable result contract"
            ),
        )
        raise AssertionError("unreachable") from exc
    config = ProviderSupervisionStepConfig(
        common=StepCommonConfig(timeout_sec=whole_timeout),
        schema_version=PROVIDER_SUPERVISION_SCHEMA_VERSION,
        node_id=group_step_id,
        worker=worker,
        supervisor=supervisor,
        observation=ProviderSupervisionObservation(
            observer_member_id=group.supervisor_name,
            observed_member_id=group.worker_name,
        ),
        settlement_payload=_frozen_mapping(settlement_payload),
        settlement_result_contract=settlement_result_contract,
        max_steers=1,
        paths=derive_provider_supervision_paths(
            node_id=group_step_id,
            worker_member_id=group.worker_name,
            supervisor_member_id=group.supervisor_name,
        ),
        source_ownership=ProviderSupervisionSourceOwnership(
            form=group.metadata.node_id,
            worker_binding=worker_member.binding_metadata.node_id,
            supervisor_binding=(
                supervisor_member.binding_metadata.node_id
            ),
            observation=group.observation_metadata.node_id,
            settlement=group.settlement_body.metadata.node_id,
        ),
    )
    source = SimpleNamespace(
        span=group.metadata.source_span,
        form_path=group.metadata.form_path,
        expansion_stack=group.metadata.expansion_stack,
    )
    _record_step_origin(
        context,
        step_name=group_step_name,
        step_id=group_step_id,
        source=source,
    )
    return (
        [
            *member_prelude_steps,
            {
                "name": group_step_name,
                "id": group_step_id,
                "timeout_sec": whole_timeout,
                "provider_supervision": config,
            },
        ],
        _TerminalResult(
            step_name=group_step_name,
            step_id=group_step_id,
            output_refs=lowering_core._record_output_refs(
                group_step_name,
                binding_type,
            ),
            output_kind="step",
            hidden_inputs={},
            returned_union_type_name=(
                binding_type.name
                if isinstance(binding_type, UnionTypeRef)
                else None
            ),
        ),
    )


def _lower_effectful_binding(
    value: WccPerform | WccCall,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    lexical_checkpoint_points: list[Mapping[str, object]] | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if isinstance(value, WccPerform):
        if value.perform_kind == "run_ref":
            payload = value.operation_payload
            if not isinstance(payload, WccRunRefPayload):
                raise TypeError("run-ref WCC lowering requires a typed payload")
            descriptor_rows = payload.input_type_descriptors
            if tuple(name for name, _ in value.keyword_args) != tuple(
                name for name, _ in descriptor_rows
            ):
                raise TypeError(
                    "run-ref WCC input atoms disagree with typed payload order"
                )
            return _lower_run_ref_operation(
                LowerableRunRef(
                    payload=payload,
                    inputs=tuple(
                        LowerableRunRefInput(
                            name=name,
                            value_expr=_frontend_expr_from_wcc_value_with_env(
                                atom,
                                local_values,
                            ),
                            type_ref=atom.metadata.type_ref,
                            type_descriptor=descriptor,
                        )
                        for (name, atom), (_, descriptor) in zip(
                            value.keyword_args,
                            descriptor_rows,
                            strict=True,
                        )
                    ),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                result_type=binding_type,
                context=context,
                local_values=local_values,
            )
        if value.perform_kind == "trial":
            payload = value.operation_payload
            if not isinstance(payload, WccTrialPayload):
                raise TypeError("trial WCC lowering requires a typed payload")
            expected_keywords = tuple(
                keyword
                for arm in payload.arms
                for _, keyword in arm.input_keywords
            )
            if tuple(name for name, _ in value.keyword_args) != expected_keywords:
                raise TypeError(
                    "trial WCC input atoms disagree with typed payload order"
                )
            return _lower_trial_operation(
                LowerableTrial(
                    payload=payload,
                    inputs=tuple(
                        LowerableTrialInput(
                            keyword=name,
                            value_expr=_frontend_expr_from_wcc_value_with_env(
                                atom,
                                local_values,
                            ),
                            type_ref=atom.metadata.type_ref,
                        )
                        for name, atom in value.keyword_args
                    ),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                result_type=binding_type,
                context=context,
                local_values=local_values,
            )
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
                    prompt_name=value.prompt_name,
                    inputs=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                    guidance=(
                        operation_payload["return_spec"].guidance
                        if operation_payload.get("return_spec") is not None
                        else None
                    ),
                    model=(
                        _frontend_expr_from_wcc_value(operation_payload["model"])
                        if operation_payload.get("model") is not None
                        else None
                    ),
                    effort=(
                        _frontend_expr_from_wcc_value(operation_payload["effort"])
                        if operation_payload.get("effort") is not None
                        else None
                    ),
                    delivery=(
                        _frontend_expr_from_wcc_value(operation_payload["delivery"])
                        if operation_payload.get("delivery") is not None
                        else None
                    ),
                    materialization_attempts=(
                        _frontend_expr_from_wcc_value(
                            operation_payload["materialization_attempts"]
                        )
                        if operation_payload.get("materialization_attempts") is not None
                        else None
                    ),
                    timeout_sec=(
                        _frontend_expr_from_wcc_value(operation_payload["timeout_sec"])
                        if operation_payload.get("timeout_sec") is not None
                        else None
                    ),
                    prompt_dependencies=_prompt_dependency_spec_from_wcc_payload(
                        operation_payload.get("prompt_dependencies")
                    ),
                    prompt_application=_prompt_application_from_wcc_payload(
                        operation_payload,
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
                prompt_name=(
                    None
                    if isinstance(expr.prompt, PromptApplicationExpr)
                    else expr.prompt.name
                ),
                inputs=tuple(expr.inputs),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                guidance=expr.return_spec.guidance,
                model=expr.model,
                effort=expr.effort,
                delivery=expr.delivery,
                materialization_attempts=expr.materialization_attempts,
                timeout_sec=expr.timeout_sec,
                prompt_dependencies=expr.prompt_dependencies,
                prompt_application=(
                    expr.prompt
                    if isinstance(expr.prompt, PromptApplicationExpr)
                    else None
                ),
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
    call_source = LowerableProcedureCall(
        callee_name=value.callee_name,
        args=arg_exprs,
        span=value.metadata.source_span,
        form_path=value.metadata.form_path,
        expansion_stack=value.metadata.expansion_stack,
        specialized_callee_name=value.specialized_callee_name,
    )
    procedure_notes = _merge_origin_notes(
        context.origin_notes,
        _procedure_provenance_notes(
            call_source,
            procedure,
            typed_procedures=context.typed_procedures,
        ),
    )
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
        origin_notes=procedure_notes,
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


def _wcc_tree_references_name(value: object, name: str) -> bool:
    if isinstance(value, WccNameAtom):
        return value.name == name
    if isinstance(value, Mapping):
        return any(
            _wcc_tree_references_name(item, name)
            for item in value.values()
        )
    if isinstance(value, (tuple, list)):
        return any(
            _wcc_tree_references_name(item, name)
            for item in value
        )
    if is_dataclass(value):
        return any(
            _wcc_tree_references_name(
                getattr(value, field.name),
                name,
            )
            for field in fields(value)
        )
    return False


def _wcc_run_ref_input_references_name(value: object, name: str) -> bool:
    """Return whether a later run-ref input consumes one ANF binding."""

    if isinstance(value, WccPerform):
        return value.perform_kind == "run_ref" and any(
            _wcc_tree_references_name(input_value, name)
            for _, input_value in value.keyword_args
        )
    if isinstance(value, Mapping):
        return any(
            _wcc_run_ref_input_references_name(item, name)
            for item in value.values()
        )
    if isinstance(value, (tuple, list)):
        return any(
            _wcc_run_ref_input_references_name(item, name)
            for item in value
        )
    if is_dataclass(value):
        return any(
            _wcc_run_ref_input_references_name(
                getattr(value, field_info.name),
                name,
            )
            for field_info in fields(value)
        )
    return False


def _wcc_workflow_call_exclusively_consumes_binding(
    body: WccBody,
    binding_name: str,
) -> bool:
    if (
        not isinstance(body, WccLet)
        or not isinstance(body.bound_value, WccPerform)
        or body.bound_value.perform_kind != "workflow_call"
    ):
        return False
    perform = body.bound_value
    if not any(
        _wcc_tree_references_name(value, binding_name)
        for _, value in perform.keyword_args
    ):
        return False
    if (
        _wcc_tree_references_name(
            perform.positional_args,
            binding_name,
        )
        or _wcc_tree_references_name(
            perform.operation_payload,
            binding_name,
        )
    ):
        return False
    return not _wcc_tree_references_name(body.body, binding_name)


def _frontend_expr_from_wcc_loop_body(body: WccBody, env: Mapping[str, object] | None = None):
    resolved_env: Mapping[str, object] = env or {}
    if isinstance(body, WccLet):
        binding_expr = (
            _frontend_expr_from_wcc_loop_binding_value(
                body.bound_value,
                env=resolved_env,
            )
            if isinstance(body.bound_value, (WccPerform, WccCall))
            else _frontend_expr_from_wcc_value_with_env(body.bound_value, resolved_env)
        )
        nested_env: Mapping[str, object] = resolved_env
        if not isinstance(body.bound_value, (WccPerform, WccCall)):
            nested_env = {**dict(resolved_env), body.bound_name: binding_expr}
        if (
            isinstance(binding_expr, PathJoinUnderExpr)
            and _wcc_workflow_call_exclusively_consumes_binding(
                body.body,
                body.bound_name,
            )
        ):
            return _frontend_expr_from_wcc_loop_body(
                body.body,
                nested_env,
            )
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
            terminal_state_expr=(
                _frontend_expr_from_wcc_value_with_env(
                    body.state,
                    resolved_env,
                )
                if body.state is not None
                else None
            ),
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
        env[current.bound_name] = _frontend_expr_from_wcc_value_with_env(
            current.bound_value,
            env,
        )
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
            # A live union is retained in the WCC environment as its flattened
            # variant/payload reference map.  Preserve the authored name here
            # so the shared pure-projection lane can reconstitute the tagged
            # direct value instead of mistaking that map for a static union.
            if isinstance(value.metadata.type_ref, UnionTypeRef) and isinstance(
                resolved,
                Mapping,
            ):
                return _frontend_expr_from_wcc_value(value)
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
        if isinstance(base_expr, FieldAccessExpr):
            return FieldAccessExpr(
                base=base_expr.base,
                fields=(*base_expr.fields, *value.fields),
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
    if isinstance(value, WccSelect):
        return IfExpr(
            condition_expr=_frontend_expr_from_wcc_value_with_env(value.condition, env),
            then_expr=_frontend_wcc_select_arm_with_env(value.then_arm, env),
            else_expr=_frontend_wcc_select_arm_with_env(value.else_arm, env),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccOpaqueFrontendValue):
        return map_expr(
            _frontend_expr_from_wcc_value(value),
            lambda node: env.get(node.name, node),
        )
    return _frontend_expr_from_wcc_value(value)


def _frontend_wcc_select_arm_with_env(
    arm: WccSelectArm,
    env: Mapping[str, object],
):
    """Reconstruct one select arm, wrapping a non-empty prefix in ``LetStarExpr``."""

    local_env: dict[str, object] = dict(env)
    bindings: list[tuple[str, object]] = []
    for let_node in arm.prefix:
        bindings.append(
            (
                let_node.bound_name,
                _frontend_expr_from_wcc_value_with_env(
                    let_node.bound_value,
                    local_env,
                ),
            )
        )
        local_env[let_node.bound_name] = NameExpr(
            name=let_node.bound_name,
            span=let_node.metadata.source_span,
            form_path=let_node.metadata.form_path,
            expansion_stack=let_node.metadata.expansion_stack,
        )
    value_expr = _frontend_expr_from_wcc_value_with_env(arm.value, local_env)
    if not bindings:
        return value_expr
    return LetStarExpr(
        bindings=tuple(bindings),
        body=value_expr,
        span=arm.value.metadata.source_span,
        form_path=arm.value.metadata.form_path,
        expansion_stack=arm.value.metadata.expansion_stack,
    )


def _prompt_dependency_spec_from_wcc_payload(
    payload: object,
) -> PromptDependencySpec | None:
    """Reconstruct the frontend owner payload retained by WCC."""

    if payload is None:
        return None
    if not isinstance(payload, WccPromptDependencyPayload):
        raise TypeError("WCC provider prompt dependencies require a typed payload")
    required = []
    optional = []
    expected_indices = {"required": 0, "optional": 0}
    for row in payload.rows:
        if row.role not in expected_indices:
            raise TypeError(f"unsupported WCC prompt dependency role {row.role!r}")
        if row.authored_index != expected_indices[row.role]:
            raise TypeError(
                f"non-contiguous WCC prompt dependency index for {row.role!r}"
            )
        expected_indices[row.role] += 1
        reconstructed = _frontend_expr_from_wcc_value(row.value)
        if row.role == "required":
            required.append(reconstructed)
        else:
            optional.append(reconstructed)
    if not required and not optional:
        raise TypeError("WCC prompt dependency payload must contain at least one row")
    if payload.position not in {"prepend", "append"}:
        raise TypeError("WCC prompt dependency position must be prepend or append")
    if payload.instruction is not None and not isinstance(payload.instruction, str):
        raise TypeError("WCC prompt dependency instruction must be a string or None")
    return PromptDependencySpec(
        required=tuple(required),
        optional=tuple(optional),
        position=payload.position,
        instruction=payload.instruction,
        span=payload.source_span,
        form_path=payload.form_path,
        expansion_stack=payload.expansion_stack,
    )


def _prompt_application_from_wcc_payload(
    payload: Mapping[str, object],
    *,
    env: Mapping[str, object] | None = None,
) -> PromptApplicationExpr | None:
    """Reconstruct the typed compile-time application retained by one perform."""

    application = payload.get("prompt_application")
    if application is None:
        return None
    if not isinstance(application, PromptApplicationExpr):
        raise TypeError("WCC prompt application payload must be typed")
    convert = (
        (lambda value: _frontend_expr_from_wcc_value_with_env(value, env))
        if env is not None
        else _frontend_expr_from_wcc_value
    )
    return replace(
        application,
        fills=tuple(
            replace(
                fill,
                value_expr=convert(fill.value_expr),
            )
            for fill in application.fills
        ),
    )


def _frontend_expr_from_wcc_loop_binding_value(
    value,
    *,
    env: Mapping[str, object] | None = None,
):
    if isinstance(value, WccPerform):
        if value.perform_kind == "provider_result":
            operation_payload = value.operation_payload if isinstance(value.operation_payload, dict) else {}
            prompt_application = _prompt_application_from_wcc_payload(
                operation_payload,
            )
            return ProviderResultExpr(
                provider=NameExpr(
                    name=value.target_name,
                    span=value.metadata.source_span,
                    form_path=value.metadata.form_path,
                    expansion_stack=value.metadata.expansion_stack,
                ),
                prompt=(
                    prompt_application
                    if prompt_application is not None
                    else NameExpr(
                        name=value.prompt_name or "",
                        span=value.metadata.source_span,
                        form_path=value.metadata.form_path,
                        expansion_stack=value.metadata.expansion_stack,
                    )
                ),
                inputs=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.positional_args),
                return_spec=operation_payload.get("return_spec"),
                returns_type_name=value.returns_type_name or "",
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
                model=(
                    _frontend_expr_from_wcc_value(operation_payload["model"])
                    if operation_payload.get("model") is not None
                    else None
                ),
                effort=(
                    _frontend_expr_from_wcc_value(operation_payload["effort"])
                    if operation_payload.get("effort") is not None
                    else None
                ),
                delivery=(
                    _frontend_expr_from_wcc_value(operation_payload["delivery"])
                    if operation_payload.get("delivery") is not None
                    else None
                ),
                materialization_attempts=(
                    _frontend_expr_from_wcc_value(
                        operation_payload["materialization_attempts"]
                    )
                    if operation_payload.get("materialization_attempts") is not None
                    else None
                ),
                timeout_sec=(
                    _frontend_expr_from_wcc_value(operation_payload["timeout_sec"])
                    if operation_payload.get("timeout_sec") is not None
                    else None
                ),
                prompt_dependencies=_prompt_dependency_spec_from_wcc_payload(
                    operation_payload.get("prompt_dependencies")
                ),
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
            path_binding_env = (
                {
                    name: binding
                    for name, binding in env.items()
                    if isinstance(binding, PathJoinUnderExpr)
                }
                if env is not None
                else None
            )
            return CallExpr(
                callee_name=value.target_name,
                bindings=tuple(
                    (
                        binding_name,
                        (
                            _frontend_expr_from_wcc_value_with_env(
                                binding_value,
                                path_binding_env,
                            )
                            if path_binding_env
                            else _frontend_expr_from_wcc_value(binding_value)
                        ),
                    )
                    for binding_name, binding_value in value.keyword_args
                ),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
                authored_callee_span=None,
            )
    if isinstance(value, WccCall):
        return ProcedureCallExpr(
            callee_name=value.callee_name,
            args=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.args),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
            authored_callee_span=None,
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
    if isinstance(value, WccSelect):
        return IfExpr(
            condition_expr=_frontend_expr_from_wcc_value(value.condition),
            then_expr=_frontend_wcc_select_arm(value.then_arm),
            else_expr=_frontend_wcc_select_arm(value.else_arm),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    raise TypeError(f"unsupported WCC value during defunctionalization: {type(value).__name__}")


def _frontend_wcc_select_arm(arm: WccSelectArm):
    """Reconstruct one select arm without an environment substitution."""

    bindings = tuple(
        (
            let_node.bound_name,
            _frontend_expr_from_wcc_value(let_node.bound_value),
        )
        for let_node in arm.prefix
    )
    value_expr = _frontend_expr_from_wcc_value(arm.value)
    if not bindings:
        return value_expr
    return LetStarExpr(
        bindings=bindings,
        body=value_expr,
        span=arm.value.metadata.source_span,
        form_path=arm.value.metadata.form_path,
        expansion_stack=arm.value.metadata.expansion_stack,
    )
