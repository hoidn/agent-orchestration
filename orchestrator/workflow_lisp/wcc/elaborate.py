"""Elaboration from typed frontend expressions into Workflow Core Calculus."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields as dataclass_fields, is_dataclass, replace

from ..conditionals import (
    _contains_effect,
    classify_condition_expr,
    fold_pure_short_circuit,
    _normalize_operand,
    prepare_closed_condition_expr,
    _wrap_bindings,
)
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic, records_defect_provenance
from ..effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from ..expression_traversal import map_expr, walk_expr
from ..expressions import (
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    CompilerListNonemptyHeadExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    ListExpr,
    ListMapExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MaterializeViewExpr,
    MatchExpr,
    NameExpr,
    PathJoinUnderExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    PureOpExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    RequestInputExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunRefBundleProgram,
    RunRefExpr,
    RunRefPathProgram,
    TrialExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    UnionVariantTagExpr,
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from ..procedures import (
    ProcedureLoweringMode,
    TypedProcedureDef,
    procedure_type_env_for,
)
from ..prompts import PromptApplicationExpr
from ..procedure_refs import ResolvedProcRefValue
from ..phase import (
    IMPLEMENTATION_ATTEMPT_TARGET_FIELDS,
    PHASE_TARGET_SPECS,
    build_phase_scope,
    resolve_phase_target_type,
)
from ..spans import SourceSpan
from ..typecheck_pure_ops import catalog_operator_result_type
from ..type_env import (
    DiscriminantTypeRef,
    FrontendTypeEnvironment,
    ListTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    WorkflowRefTypeRef,
    type_refs_compatible,
)
from ..typecheck_context import TypedExpr
from ..loops import LoopControlTypeRef
from ..loop_state import carrier_metadata_for_expr
from ..lowering.pure_projection import is_pure_projection_expr
from ..normalized_type_descriptor import compiler_normalized_type_descriptor
from ..run_ref_result_contract import derive_run_ref_result_contract
from ..trial_result_contract import derive_trial_result_contract
from ..syntax import (
    HUMAN_REPLY_TYPE_NAME,
    HelperExpansionFrame,
    ProcedureExpansionFrame,
    target_dsl_is_2_33_or_newer,
    target_dsl_supports_nested_structural_transport,
    target_dsl_supports_pure_call_composition,
    target_dsl_supports_strict_boolean_control_flow,
)
from ..typecheck_run_ref import resolve_unique_run_ref_site_metadata
from ..workflows import TypedWorkflowDef
from ..workflow_refs import ResolvedWorkflowRef
from .hygiene import (
    fresh_name,
    generated_name_scope,
    hoist_parts_without_capture,
    hoist_without_capture,
    reserved_identifiers,
)
from .model import (
    WccBindingValue,
    WccBody,
    WccCase,
    WccCaseArm,
    WccCall,
    WccFieldAccessAtom,
    WccHalt,
    WccIdentityFactory,
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
    WccPhaseScope,
    WccPhaseTargetAtom,
    WccPerform,
    WccProviderPeerGroup,
    WccProviderPeerGroupMember,
    WccProviderSupervision,
    WccProviderSupervisionMember,
    WccPureOp,
    WccProduceOneOfPayload,
    WccRecJoin,
    WccRecordAtom,
    WccSelect,
    WccSelectArm,
    WccResumeOrStartPayload,
    WccRunRefPayload,
    WccTrialArmPayload,
    WccTrialPayload,
    WccRunProviderPhasePayload,
    WccSpecializationCapture,
    WccValue,
)


@dataclass(frozen=True)
class WccPromptDependencyRow:
    """One typed authored dependency row retained in a provider payload."""

    role: str
    authored_index: int
    value: WccValue
    source_span: object
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...]


@dataclass(frozen=True)
class WccPromptDependencyPayload:
    """Closed prompt-dependency payload owned by ``WccPerform``."""

    rows: tuple[WccPromptDependencyRow, ...]
    position: str
    instruction: str | None
    source_span: object
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...]


@dataclass(frozen=True)
class _WccBoundProcedureBinding:
    """A compile-time procedure value plus bind-site runtime captures."""

    capture_values: tuple[tuple[str, WccValue, object | None], ...]
    source_binding: object | None = None


@dataclass(frozen=True)
class _WccCompileTimeAlias:
    """One erased alias retaining its original compile-time owner."""

    value: object
    source_name: str


@dataclass(frozen=True)
class _WccRuntimeCaptureAlias:
    """One runtime alias materialized at a ``bind-proc`` site."""

    source_name: str
    alias_name: str
    type_ref: TypeRef
    source_expr: NameExpr
    source_atom: WccNameAtom
    alias_atom: WccNameAtom
    scope: WccIdentityFactory


@dataclass(frozen=True)
class _WccDirectBoundProcedureArgument:
    """One inline ``bind-proc`` argument prebound for WCC closure."""

    binding_name: str
    type_ref: TypeRef
    compile_time_value: _WccBoundProcedureBinding
    capture_aliases: tuple[_WccRuntimeCaptureAlias, ...]


_PRESERVE_BOUND_PROC_CAPTURES = (
    "\x00wcc-preserve-bound-proc-captures"
)


_COMMAND_SCOPE_CONTEXT = object()
_CLOSED_PROCEDURE_SELECTION = object()


def _closed_reference_actual(argument, bindings):
    value = bindings.get(argument.name, argument) if isinstance(argument, NameExpr) else argument
    value, _ = _unwrap_compile_time_alias(value)
    return value.source_binding if isinstance(value, _WccBoundProcedureBinding) else value


def _closed_workflow_actual(argument, bindings, expected_type, catalog, workflows):
    from ..workflow_refs import resolve_workflow_ref_expr

    value = _closed_reference_actual(argument, bindings)
    if isinstance(value, ResolvedWorkflowRef):
        return value
    if not isinstance(value, (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr)):
        raise TypeError("compiler-owned WorkflowRef actual has no retained reference binding")
    return resolve_workflow_ref_expr(value, workflow_catalog=catalog,
        span=argument.span, form_path=argument.form_path, expansion_stack=argument.expansion_stack,
        expected_type=expected_type, typed_workflows_by_name=workflows, allow_extern_rebinding=True)


def _closed_proc_actual(argument, bindings, catalog, expected_type=None):
    from ..procedure_refs import resolve_proc_ref_value

    proc_env = {name: value for name, binding in bindings.items()
        if isinstance((value := _closed_reference_actual(binding, bindings)), ResolvedProcRefValue)}
    return resolve_proc_ref_value(_closed_reference_actual(argument, bindings),
        procedure_catalog=catalog, proc_ref_env=proc_env, expected_type=expected_type)


def _closed_application_params(expr, bindings, catalog):
    if expr.callee_name in bindings:
        resolved = _closed_proc_actual(bindings[expr.callee_name], bindings, catalog)
        if resolved is None:
            raise TypeError("compiler-owned lexical procedure callee has no retained signature")
        return resolved.residual_params
    signature = catalog.signatures_by_name.get(expr.callee_name)
    if signature is None:
        raise TypeError("compiler-owned procedure application has no authored signature")
    return signature.params


def _closed_call_reference_bindings(procedure, expr, bindings, *, procedure_catalog,
    workflow_catalog, typed_workflows, argument_params):
    workflow_refs, proc_refs = {}, {}
    actual_by_formal = {name: argument for (name, _), argument
        in zip(argument_params, expr.args, strict=True)}
    for name, type_ref in procedure.signature.params:
        if isinstance(type_ref, WorkflowRefTypeRef):
            workflow_refs[name] = _closed_workflow_actual(actual_by_formal[name], bindings, type_ref,
                workflow_catalog, typed_workflows)
        elif isinstance(type_ref, ProcRefTypeRef):
            resolved = _closed_proc_actual(actual_by_formal[name], bindings, procedure_catalog, type_ref)
            if resolved is None:
                raise TypeError("compiler-owned ProcRef actual has no retained reference binding")
            proc_refs[name] = resolved
    return workflow_refs, proc_refs


def _complete_named_reference_procedure(expr, bindings, procedures):
    if expr.callee_name in bindings:
        return None
    procedure = procedures.get(expr.callee_name)
    if procedure is None or procedure.specialization is None:
        return None
    specialization = procedure.specialization
    if not (specialization.proc_ref_bindings or specialization.workflow_ref_bindings):
        return None
    if any(isinstance(type_ref, (ProcRefTypeRef, WorkflowRefTypeRef))
        for _, type_ref in procedure.signature.params):
        return None
    return procedure


def _select_closed_procedure_edge(expr, selected_name, bindings, *, procedures,
    procedure_catalog, workflow_catalog, typed_workflows):
    from ..procedure_specialization import materialized_specialization_rows

    complete = _complete_named_reference_procedure(expr, bindings, procedures)
    if complete is not None:
        return complete.definition.name
    procedure = procedures.get(selected_name)
    if procedure is None:
        return selected_name
    if not any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in procedure.signature.params):
        return selected_name
    workflow_refs, proc_refs = _closed_call_reference_bindings(procedure, expr, bindings,
        procedure_catalog=procedure_catalog, workflow_catalog=workflow_catalog,
        typed_workflows=typed_workflows,
        argument_params=_closed_application_params(expr, bindings, procedure_catalog))
    rows = materialized_specialization_rows(procedure, workflow_ref_bindings=workflow_refs,
        proc_ref_bindings=proc_refs, typed_procedures=procedures)
    if len(rows) != 1:
        raise TypeError("compiler-owned reference specialization has no unique materialized WCC row")
    return rows[0].definition.name


def _site_procedure_specializations(node, edge_name, resolved_procedures_by_name):
    return tuple(
        procedure
        for procedure in resolved_procedures_by_name.values()
        if (
            procedure.specialization is not None
            and procedure.specialization.base_name == edge_name
            and procedure.specialization.origin_span == node.span
            and procedure.specialization.origin_form_path
            == node.form_path
        )
    )


def _select_elaboration_procedure_edges(typed_body, procedure_edges_by_site, resolved_procedures_by_name):
    if resolved_procedures_by_name is not None:
        for node in walk_expr(typed_body.expr):
            if not isinstance(node, ProcedureCallExpr):
                continue
            site = (node.span, node.form_path)
            edge_name = procedure_edges_by_site.get(site)
            edge_procedure = (
                None
                if edge_name is None
                else resolved_procedures_by_name.get(edge_name)
            )
            if (
                edge_procedure is None
                or edge_procedure.specialization is not None
            ):
                continue
            site_specializations = _site_procedure_specializations(
                node, edge_name, resolved_procedures_by_name,
            )
            if len(site_specializations) > 1:
                raise TypeError(
                    "compiler-owned procedure specialization is "
                    "ambiguous at one WCC call site"
                )
            if site_specializations:
                procedure_edges_by_site[site] = (
                    site_specializations[0].definition.name
                )


def _elaboration_procedure_return_types(typed_body, procedure_edges_by_site, procedure_return_types,
    *, closed_program=False, resolved_procedures_by_name=None):
    resolved_procedure_return_types = dict(procedure_return_types or {})
    for node in walk_expr(typed_body.expr):
        if not isinstance(node, ProcedureCallExpr):
            continue
        specialized_name = procedure_edges_by_site.get(
            (node.span, node.form_path)
        )
        if closed_program:
            complete = _complete_named_reference_procedure(
                node, {}, resolved_procedures_by_name or {})
            if complete is not None:
                specialized_name = complete.definition.name
        if specialized_name is None:
            continue
        specialized_return_type = resolved_procedure_return_types.get(
            specialized_name
        )
        if specialized_return_type is None:
            continue
        existing_return_type = resolved_procedure_return_types.get(
            node.callee_name
        )
        if (
            existing_return_type is not None
            and not type_refs_compatible(
                existing_return_type,
                specialized_return_type,
            )
        ):
            raise TypeError(
                "one lexical procedure binding resolved to incompatible "
                "return types during WCC elaboration"
            )
        resolved_procedure_return_types[node.callee_name] = (
            specialized_return_type
        )
    return resolved_procedure_return_types


def _prepare_elaboration_body(typed_body, *, closed_program):
    if closed_program:
        return replace(typed_body, expr=prepare_closed_condition_expr(typed_body.expr))
    return typed_body


def prepare_elaboration_call_types(
    typed_body: TypedExpr, *, resolved_procedures_by_name=None, procedure_return_types=None,
    closed_program=False,
):
    """Use the elaboration owner's selected call edges and return types."""
    typed_body = _prepare_elaboration_body(typed_body, closed_program=closed_program)
    procedure_edges_by_site = {
        (edge.span, edge.form_path): edge.callee_name
        for edge in typed_body.effect_summary.procedure_edges
        if edge.span is not None
    }
    _select_elaboration_procedure_edges(typed_body, procedure_edges_by_site, resolved_procedures_by_name)
    returns = _elaboration_procedure_return_types(typed_body, procedure_edges_by_site,
        procedure_return_types, closed_program=closed_program,
        resolved_procedures_by_name=resolved_procedures_by_name)
    return procedure_edges_by_site, returns


def elaborate_typed_workflow_body(
    typed_body: TypedExpr,
    *,
    owner_name: str,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef] | None = None,
    procedure_return_types: Mapping[str, TypeRef] | None = None,
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef] | None = None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    compile_time_bindings: Mapping[str, object] | None = None,
    route_schema_version: str | None = None,
    closed_program: bool = False,
    command_scope_context=None,
    workflow_catalog=None,
    typed_workflows_by_name=None,
) -> WccBody:
    """Elaborate one typed workflow body into WCC."""

    typed_body = _prepare_elaboration_body(typed_body, closed_program=closed_program)

    scope = WccIdentityFactory(
        owner_name=owner_name,
        lexical_owner_chain=("workflow",),
        route_schema_version=route_schema_version or WccIdentityFactory.route_schema_version,
        closed_program=closed_program,
    )
    procedure_edges_by_site, resolved_procedure_return_types = prepare_elaboration_call_types(
        typed_body, resolved_procedures_by_name=resolved_procedures_by_name,
        procedure_return_types=procedure_return_types, closed_program=closed_program,
    )
    initial_compile_time_bindings = dict(
        compile_time_bindings or {}
    )
    if closed_program and workflow_catalog is not None:
        from functools import partial
        from ..procedures import ProcedureCatalog

        procedures = resolved_procedures_by_name or {}
        initial_compile_time_bindings[_CLOSED_PROCEDURE_SELECTION] = partial(
            _select_closed_procedure_edge, procedures=procedures,
            procedure_catalog=ProcedureCatalog(
                signatures_by_name={name: row.signature for name, row in procedures.items()},
                definitions_by_name={name: row.definition for name, row in procedures.items()}, call_graph={}),
            workflow_catalog=workflow_catalog, typed_workflows=typed_workflows_by_name or {})
    if command_scope_context is not None:
        initial_compile_time_bindings[_COMMAND_SCOPE_CONTEXT] = command_scope_context
    if closed_program or any(
        isinstance(node, (WithLiveProvidersExpr, WithLiveProviderPeersExpr))
        for node in walk_expr(typed_body.expr)
    ):
        initial_compile_time_bindings[
            _PRESERVE_BOUND_PROC_CAPTURES
        ] = True
    body = _elaborate_expr_to_body(
        typed_body.expr,
        scope=scope,
        type_env=type_env,
        value_env=dict(value_env),
        workflow_return_types=dict(workflow_return_types or {}),
        procedure_return_types=resolved_procedure_return_types,
        effect_summary=typed_body.effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=initial_compile_time_bindings,
    )
    if resolved_procedures_by_name is None:
        return body
    return close_wcc_provider_supervision_members(
        body,
        resolved_procedures_by_name=resolved_procedures_by_name,
        procedure_type_envs=procedure_type_envs or {},
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types or {},
    )


def elaborate_typed_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    type_env: FrontendTypeEnvironment,
    workflow_return_types: Mapping[str, TypeRef] | None = None,
    procedure_return_types: Mapping[str, TypeRef] | None = None,
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef] | None = None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    route_schema_version: str | None = None,
) -> WccBody:
    """Convenience wrapper for elaborating one typed workflow definition."""

    return elaborate_typed_workflow_body(
        typed_workflow.typed_body,
        owner_name=typed_workflow.definition.name,
        type_env=type_env,
        value_env=dict(typed_workflow.signature.params),
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        resolved_procedures_by_name=resolved_procedures_by_name,
        procedure_type_envs=procedure_type_envs,
        route_schema_version=route_schema_version,
    )


def close_wcc_provider_supervision_members(
    node: WccBody | WccProviderSupervision | WccProviderPeerGroup,
    *,
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment],
    type_env: FrontendTypeEnvironment,
    procedure_return_types: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef] | None = None,
) -> WccBody | WccProviderSupervision | WccProviderPeerGroup:
    """Close every live-provider region by recursively inlining explicit procedures."""

    context = _ProviderRegionClosureContext(
        resolved_procedures_by_name=resolved_procedures_by_name,
        procedure_type_envs=procedure_type_envs,
        type_env=type_env,
        workflow_return_types=dict(workflow_return_types or {}),
        procedure_return_types=dict(procedure_return_types),
    )
    if isinstance(node, WccProviderSupervision):
        return _close_provider_supervision(node, context=context)
    if isinstance(node, WccProviderPeerGroup):
        return _close_provider_peer_group(node, context=context)
    return _close_provider_groups_in_body(node, context=context)


def close_wcc_provider_peer_group_members(
    node: WccBody | WccProviderPeerGroup,
    *,
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment],
    type_env: FrontendTypeEnvironment,
    procedure_return_types: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef] | None = None,
) -> WccBody | WccProviderPeerGroup:
    """Close peer-group members through the shared provider-region contract."""

    closed = close_wcc_provider_supervision_members(
        node,
        resolved_procedures_by_name=resolved_procedures_by_name,
        procedure_type_envs=procedure_type_envs,
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    return closed


@dataclass(frozen=True)
class _ProviderRegionClosureContext:
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef]
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment]
    type_env: FrontendTypeEnvironment
    workflow_return_types: Mapping[str, TypeRef]
    procedure_return_types: Mapping[str, TypeRef]


def _close_provider_groups_in_body(
    body: WccBody,
    *,
    context: _ProviderRegionClosureContext,
) -> WccBody:
    if isinstance(body, WccLet):
        bound_value = body.bound_value
        if isinstance(bound_value, WccProviderSupervision):
            bound_value = _close_provider_supervision(
                bound_value,
                context=context,
            )
        elif isinstance(bound_value, WccProviderPeerGroup):
            bound_value = _close_provider_peer_group(
                bound_value,
                context=context,
            )
        return replace(
            body,
            bound_value=bound_value,
            body=_close_provider_groups_in_body(
                body.body,
                context=context,
            ),
        )
    if isinstance(body, WccCase):
        return replace(
            body,
            arms=tuple(
                replace(
                    arm,
                    body=_close_provider_groups_in_body(
                        arm.body,
                        context=context,
                    ),
                )
                for arm in body.arms
            ),
        )
    if isinstance(body, WccIf):
        return replace(
            body,
            then_body=_close_provider_groups_in_body(
                body.then_body,
                context=context,
            ),
            else_body=_close_provider_groups_in_body(
                body.else_body,
                context=context,
            ),
        )
    if isinstance(body, WccJoin):
        return replace(
            body,
            body=_close_provider_groups_in_body(
                body.body,
                context=context,
            ),
            continuation=_close_provider_groups_in_body(
                body.continuation,
                context=context,
            ),
        )
    if isinstance(body, WccRecJoin):
        return replace(
            body,
            body=_close_provider_groups_in_body(
                body.body,
                context=context,
            ),
            exhaustion=(
                _close_provider_groups_in_body(
                    body.exhaustion,
                    context=context,
                )
                if body.exhaustion is not None
                else None
            ),
        )
    return body


def _close_provider_supervision(
    group: WccProviderSupervision,
    *,
    context: _ProviderRegionClosureContext,
) -> WccProviderSupervision:
    from .anf import normalize_wcc_body_to_anf
    from .analysis import validate_wcc_provider_supervision

    closed = replace(
        group,
        members=tuple(
            replace(
                member,
                normalized_body=_inline_provider_region_member(
                    replace(
                        member,
                        normalized_body=normalize_wcc_body_to_anf(
                            member.normalized_body
                        ),
                    ),
                    context=context,
                ),
            )
            for member in group.members
        ),
        settlement_body=normalize_wcc_body_to_anf(group.settlement_body),
    )
    return validate_wcc_provider_supervision(closed)


def _close_provider_peer_group(
    group: WccProviderPeerGroup,
    *,
    context: _ProviderRegionClosureContext,
) -> WccProviderPeerGroup:
    from .anf import normalize_wcc_body_to_anf
    from .analysis import validate_wcc_provider_peer_group

    closed = replace(
        group,
        members=tuple(
            replace(
                member,
                normalized_body=_inline_provider_region_member(
                    replace(
                        member,
                        normalized_body=normalize_wcc_body_to_anf(
                            member.normalized_body
                        ),
                    ),
                    context=context,
                ),
            )
            for member in group.members
        ),
        settlement_body=normalize_wcc_body_to_anf(
            group.settlement_body
        ),
    )
    return validate_wcc_provider_peer_group(closed)


def _inline_provider_region_member(
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    *,
    context: _ProviderRegionClosureContext,
) -> WccBody:
    return _inline_linear_provider_region(
        member.normalized_body,
        substitutions={},
        namespace=None,
        member=member,
        context=context,
        active_procedures=frozenset(),
        deferred_specialization_captures=(),
        terminal_builder=lambda halt, result: replace(halt, result=result),
    )


def _inline_linear_provider_region(
    body: WccBody,
    *,
    substitutions: Mapping[str, WccValue],
    namespace: str | None,
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    context: _ProviderRegionClosureContext,
    active_procedures: frozenset[str],
    deferred_specialization_captures: tuple[
        tuple[str, str, WccValue],
        ...,
    ],
    terminal_builder,
) -> WccBody:
    if isinstance(body, WccHalt):
        return terminal_builder(
            body,
            _substitute_wcc_value(body.result, substitutions),
        )
    if not isinstance(body, WccLet):
        _raise_provider_member_ineligible(
            member,
            offending_metadata=body.metadata,
            message=(
                "live-provider members must normalize to a straight "
                "`WccLet`/`WccHalt` region"
            ),
        )

    bound_name = (
        body.bound_name
        if namespace is None
        else f"{namespace}{body.bound_name}"
    )
    bound_ref = _provider_inline_name_ref(
        body,
        name=bound_name,
        member=member,
    )
    continuation = _inline_linear_provider_region(
        body.body,
        substitutions={**substitutions, body.bound_name: bound_ref},
        namespace=namespace,
        member=member,
        context=context,
        active_procedures=active_procedures,
        deferred_specialization_captures=(
            deferred_specialization_captures
        ),
        terminal_builder=terminal_builder,
    )
    bound_value = _substitute_wcc_binding_value(
        body.bound_value,
        substitutions,
    )
    if isinstance(bound_value, WccCall):
        return _inline_provider_procedure_call(
            bound_value,
            output_let=replace(body, bound_name=bound_name),
            continuation=continuation,
            member=member,
            context=context,
            active_procedures=active_procedures,
            caller_substitutions=substitutions,
            deferred_specialization_captures=(
                deferred_specialization_captures
            ),
        )
    if isinstance(
        bound_value,
        (WccProviderSupervision, WccProviderPeerGroup),
    ):
        _raise_provider_member_ineligible(
            member,
            offending_metadata=bound_value.metadata,
            message="nested live-provider groups are not eligible as members",
        )
    return replace(
        body,
        bound_name=bound_name,
        bound_value=bound_value,
        body=continuation,
    )


def _inline_provider_procedure_call(
    call: WccCall,
    *,
    output_let: WccLet,
    continuation: WccBody,
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    context: _ProviderRegionClosureContext,
    active_procedures: frozenset[str],
    caller_substitutions: Mapping[str, WccValue],
    deferred_specialization_captures: tuple[
        tuple[str, str, WccValue],
        ...,
    ],
) -> WccBody:
    procedure = context.resolved_procedures_by_name.get(
        call.specialized_callee_name
    )
    if procedure is None:
        _raise_provider_member_ineligible(
            member,
            offending_metadata=call.metadata,
            message=(
                "live-provider procedure members require a resolved "
                "monomorphic specialization"
            ),
        )
    if (
        procedure.signature.requested_lowering_mode
        is not ProcedureLoweringMode.INLINE
        or procedure.resolved_lowering_mode
        is not ProcedureLoweringMode.INLINE
    ):
        _raise_provider_member_ineligible(
            member,
            offending_metadata=procedure.definition,
            message=(
                "every live-provider member procedure must be authored "
                "with `:lowering inline` and resolve inline"
            ),
        )
    if procedure.signature.name in active_procedures:
        _raise_provider_member_ineligible(
            member,
            offending_metadata=call.metadata,
            message="recursive live-provider member procedures are not eligible",
        )
    if len(call.args) != len(procedure.signature.params):
        _raise_provider_member_ineligible(
            member,
            offending_metadata=call.metadata,
            message="live-provider procedure specialization arguments are ambiguous",
        )

    immediate_captures, forwarded_captures = (
        _partition_call_specialization_captures(
            call,
            procedure=procedure,
            context=context,
            member=member,
            deferred_specialization_captures=(
                deferred_specialization_captures
            ),
        )
    )
    call_capture_substitutions: dict[str, WccValue] = {}
    for capture_name, capture_value in immediate_captures:
        if (
            capture_name in call_capture_substitutions
            and call_capture_substitutions[capture_name] != capture_value
        ):
            _raise_provider_member_ineligible(
                member,
                offending_metadata=call.metadata,
                message=(
                    "live-provider procedure specialization captures "
                    f"`{capture_name}` ambiguously"
                ),
            )
        call_capture_substitutions[capture_name] = capture_value
    effective_caller_substitutions = {
        **caller_substitutions,
        **call_capture_substitutions,
    }

    specialization = procedure.specialization
    workflow_ref_values = (
        {}
        if specialization is None
        else dict(getattr(specialization, "workflow_ref_bindings", {}))
    )
    proc_ref_values = (
        {}
        if specialization is None
        else dict(getattr(specialization, "proc_ref_bindings", {}))
    )
    specialization_values = (
        {}
        if specialization is None
        else dict(getattr(specialization, "value_bindings", {}))
    )
    capture_substitutions: dict[str, WccValue] = {}
    rewritten_specialization_values: dict[str, object] = {}
    peer_group_member = isinstance(
        member,
        WccProviderPeerGroupMember,
    )
    for ordinal, (name, value) in enumerate(
        specialization_values.items()
    ):
        rewritten, captures = _rewrite_specialization_value_captures(
            value,
            caller_substitutions=effective_caller_substitutions,
            member=member,
            token_prefix=(
                (
                    "__wcc_peer_group_capture_"
                    if peer_group_member
                    else "__wcc_supervision_capture_"
                )
                + f"{call.metadata.node_id.rsplit(':', 1)[-1]}_"
                f"{ordinal}_"
            ),
        )
        rewritten_specialization_values[name] = rewritten
        capture_substitutions.update(captures)
    compile_time_values = {
        _PRESERVE_BOUND_PROC_CAPTURES: True,
        **workflow_ref_values,
        **proc_ref_values,
        **rewritten_specialization_values,
    }

    procedure_env = procedure_type_env_for(
        procedure,
        procedure_type_envs=context.procedure_type_envs,
        default=context.type_env,
    )
    procedure_value_env = dict(procedure.signature.params)
    if specialization is not None:
        procedure_value_env.update(
            dict(getattr(specialization, "bound_param_types", {}))
        )
    procedure_value_env.update(
        {
            name: value.metadata.type_ref
            for name, value in capture_substitutions.items()
        }
    )
    route_schema_version = _wcc_route_schema_version(call.metadata)
    callee_body = elaborate_typed_workflow_body(
        procedure.typed_body,
        owner_name=(
            f"{procedure.definition.name}"
            f"@{_provider_region_role(member)}:{call.metadata.node_id}"
        ),
        type_env=procedure_env,
        value_env=procedure_value_env,
        workflow_return_types=context.workflow_return_types,
        procedure_return_types=context.procedure_return_types,
        compile_time_bindings=compile_time_values,
        route_schema_version=route_schema_version,
    )
    from .anf import normalize_wcc_body_to_anf

    callee_body = normalize_wcc_body_to_anf(callee_body)
    parameter_substitutions = {
        name: arg
        for (name, _), arg in zip(
            procedure.signature.params,
            call.args,
            strict=True,
        )
    }
    namespace = (
        (
            "__wcc_peer_group_inline_"
            if peer_group_member
            else "__wcc_supervision_inline_"
        )
        + f"{call.metadata.node_id.rsplit(':', 1)[-1]}__"
    )

    def bind_call_result(
        _halt: WccHalt,
        result: WccValue,
    ) -> WccBody:
        return replace(
            output_let,
            bound_value=result,
            body=continuation,
        )

    return _inline_linear_provider_region(
        callee_body,
        substitutions={
            **capture_substitutions,
            **parameter_substitutions,
        },
        namespace=namespace,
        member=member,
        context=context,
        active_procedures=(
            active_procedures | {procedure.signature.name}
        ),
        deferred_specialization_captures=tuple(
            forwarded_captures
        ),
        terminal_builder=bind_call_result,
    )


def _partition_call_specialization_captures(
    call: WccCall,
    *,
    procedure: TypedProcedureDef,
    context: _ProviderRegionClosureContext,
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    deferred_specialization_captures: tuple[
        tuple[str, str, WccValue],
        ...,
    ],
) -> tuple[
    tuple[tuple[str, WccValue], ...],
    tuple[tuple[str, str, WccValue], ...],
]:
    specialization = procedure.specialization
    base_procedure = (
        None
        if specialization is None
        else context.resolved_procedures_by_name.get(
            specialization.base_name
        )
    )
    base_params = (
        ()
        if base_procedure is None
        else base_procedure.signature.params
    )
    proc_ref_bindings = (
        {}
        if specialization is None
        else dict(specialization.proc_ref_bindings)
    )
    def target_parameter_name(argument_index: int) -> str:
        if argument_index >= len(base_params):
            _raise_provider_member_ineligible(
                member,
                offending_metadata=call.metadata,
                message=(
                    "live-provider specialization capture argument "
                    "is outside the base procedure signature"
                ),
            )
        parameter_name = base_params[argument_index][0]
        resolved_ref = proc_ref_bindings.get(parameter_name)
        if not isinstance(resolved_ref, ResolvedProcRefValue):
            _raise_provider_member_ineligible(
                member,
                offending_metadata=call.metadata,
                message=(
                    "live-provider direct bind-proc capture "
                    "does not have an exact specialized target"
                ),
            )
        return parameter_name

    callee_capture_owner = (
        call.proc_ref_callee_source or call.callee_name
    )
    immediate: list[tuple[str, WccValue]] = (
        []
        if call.proc_ref_callee_masks_deferred
        else [
            (capture_name, capture_value)
            for owner_name, capture_name, capture_value
            in deferred_specialization_captures
            if owner_name == callee_capture_owner
        ]
    )
    forwarded: list[tuple[str, str, WccValue]] = []
    for argument_index, source_name, masks_deferred in (
        call.proc_ref_argument_sources
    ):
        target_name = target_parameter_name(argument_index)
        if not masks_deferred:
            forwarded.extend(
                (
                    target_name,
                    capture_name,
                    capture_value,
                )
                for owner_name, capture_name, capture_value
                in deferred_specialization_captures
                if owner_name == source_name
            )
    for capture in call.specialization_captures:
        if capture.owner_kind == "callee":
            immediate.append(
                (capture.source_name, capture.value)
            )
        elif (
            capture.owner_kind == "argument"
            and capture.argument_index is not None
        ):
            forwarded.append(
                (
                    target_parameter_name(
                        capture.argument_index
                    ),
                    capture.source_name,
                    capture.value,
                )
            )
        else:
            _raise_provider_member_ineligible(
                member,
                offending_metadata=call.metadata,
                message=(
                    "live-provider specialization capture owner "
                    "is not exact"
                ),
            )
    return tuple(immediate), tuple(forwarded)


def _rewrite_specialization_value_captures(
    value: object,
    *,
    caller_substitutions: Mapping[str, WccValue],
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    token_prefix: str,
) -> tuple[object, Mapping[str, WccValue]]:
    capture_substitutions: dict[str, WccValue] = {}
    tokens_by_name: dict[str, str] = {}

    def capture_token(expr: NameExpr) -> str:
        name = expr.name
        token = tokens_by_name.get(name)
        if token is not None:
            return token
        token = f"{token_prefix}{len(tokens_by_name)}__"
        tokens_by_name[name] = token
        capture_value = caller_substitutions.get(name)
        if capture_value is None:
            _raise_provider_member_ineligible(
                member,
                offending_metadata=expr,
                message=(
                    "live-provider procedure specialization capture "
                    f"`{name}` has no bind-site lexical identity"
                ),
            )
            raise AssertionError("unreachable")
        capture_substitutions[token] = capture_value
        return token

    def rewrite(node: object, *, shadowed: frozenset[str]) -> object:
        if isinstance(node, NameExpr):
            if (
                (
                    node.name in caller_substitutions
                )
                and node.name not in shadowed
            ):
                return replace(node, name=capture_token(node))
            if node.name not in shadowed:
                capture_token(node)
            return node
        if isinstance(node, FieldAccessExpr):
            rewritten_base = rewrite(node.base, shadowed=shadowed)
            if rewritten_base is node.base:
                return node
            return replace(node, base=rewritten_base)
        if isinstance(node, LetStarExpr):
            local_shadowed = set(shadowed)
            rewritten_bindings: list[tuple[str, object]] = []
            changed = False
            for binding_name, binding_expr in node.bindings:
                rewritten_binding = rewrite(
                    binding_expr,
                    shadowed=frozenset(local_shadowed),
                )
                rewritten_bindings.append(
                    (binding_name, rewritten_binding)
                )
                changed = changed or rewritten_binding is not binding_expr
                local_shadowed.add(binding_name)
            rewritten_body = rewrite(
                node.body,
                shadowed=frozenset(local_shadowed),
            )
            changed = changed or rewritten_body is not node.body
            if not changed:
                return node
            return replace(
                node,
                bindings=tuple(rewritten_bindings),
                body=rewritten_body,
            )
        if isinstance(node, ListMapExpr):
            rewritten_source = rewrite(
                node.source_expr,
                shadowed=shadowed,
            )
            rewritten_body = rewrite(
                node.body_expr,
                shadowed=shadowed | {node.binder_name},
            )
            if (
                rewritten_source is node.source_expr
                and rewritten_body is node.body_expr
            ):
                return node
            return replace(
                node,
                source_expr=rewritten_source,
                body_expr=rewritten_body,
            )
        if isinstance(node, tuple):
            rewritten_items = tuple(
                rewrite(item, shadowed=shadowed)
                for item in node
            )
            return (
                node
                if all(
                    rewritten is original
                    for rewritten, original in zip(
                        rewritten_items,
                        node,
                        strict=True,
                    )
                )
                else rewritten_items
            )
        if isinstance(node, list):
            rewritten_items = [
                rewrite(item, shadowed=shadowed)
                for item in node
            ]
            return (
                node
                if all(
                    rewritten is original
                    for rewritten, original in zip(
                        rewritten_items,
                        node,
                        strict=True,
                    )
                )
                else rewritten_items
            )
        if isinstance(node, Mapping):
            rewritten_items = {
                key: rewrite(item, shadowed=shadowed)
                for key, item in node.items()
            }
            return (
                node
                if all(
                    rewritten_items[key] is item
                    for key, item in node.items()
                )
                else rewritten_items
            )
        if is_dataclass(node):
            updates = {
                field.name: rewrite(
                    getattr(node, field.name),
                    shadowed=shadowed,
                )
                for field in dataclass_fields(node)
                if field.init and field.name not in {"run_ref_metadata", "run_ref_origin", "carrier_family", "owner_union", "discriminant_owner", "resolved_type_ref"}
            }
            changed_updates = {
                name: rewritten
                for name, rewritten in updates.items()
                if rewritten is not getattr(node, name)
            }
            if changed_updates:
                return replace(node, **changed_updates)
        return node

    return (
        rewrite(value, shadowed=frozenset()),
        capture_substitutions,
    )


def _provider_inline_name_ref(
    binding: WccLet,
    *,
    name: str,
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
) -> WccNameAtom:
    region_role = _provider_region_role(member)
    factory = WccIdentityFactory(
        owner_name=binding.metadata.node_id,
        lexical_owner_chain=(
            binding.metadata.scope_id,
            f"{region_role}-inline-ref",
            name,
        ),
        route_schema_version=_wcc_route_schema_version(binding.metadata),
    )
    return WccNameAtom(
        metadata=factory.atom_metadata(
            role=f"name:{name}",
            type_ref=binding.bound_type_ref,
            source_span=binding.metadata.source_span,
            form_path=binding.metadata.form_path,
            expansion_stack=binding.metadata.expansion_stack,
        ),
        name=name,
    )


def _substitute_wcc_binding_value(
    value,
    substitutions: Mapping[str, WccValue],
):
    if isinstance(value, WccPerform):
        return replace(
            value,
            positional_args=tuple(
                _substitute_wcc_value(arg, substitutions)
                for arg in value.positional_args
            ),
            keyword_args=tuple(
                (
                    name,
                    _substitute_wcc_value(arg, substitutions),
                )
                for name, arg in value.keyword_args
            ),
            operation_payload=_substitute_wcc_payload(
                value.operation_payload,
                substitutions,
            ),
        )
    if isinstance(value, WccCall):
        return replace(
            value,
            args=tuple(
                _substitute_wcc_value(arg, substitutions)
                for arg in value.args
            ),
            specialization_captures=tuple(
                replace(
                    capture,
                    value=_substitute_wcc_value(
                        capture.value,
                        substitutions,
                    ),
                )
                for capture in value.specialization_captures
            ),
        )
    if isinstance(
        value,
        (WccProviderSupervision, WccProviderPeerGroup),
    ):
        return value
    return _substitute_wcc_value(value, substitutions)


def _substitute_wcc_opaque_expr(
    expr: object,
    substitutions: Mapping[str, WccValue],
) -> object:
    """Substitute free names inside one opaque frontend expression.

    A bind-site rename keeps the authored reference span; any non-name
    substitution value is materialized through the shared WCC-to-frontend
    reconstruction so the opaque child stays a closed frontend term.
    """

    from .defunctionalize import _frontend_expr_from_wcc_value

    def on_name(node: NameExpr):
        replacement = substitutions.get(node.name)
        if replacement is None:
            return node
        if isinstance(replacement, WccNameAtom):
            if replacement.name == node.name:
                return node
            return replace(node, name=replacement.name)
        return _frontend_expr_from_wcc_value(replacement)

    return map_expr(expr, on_name)


def _substitute_wcc_value(
    value: WccValue,
    substitutions: Mapping[str, WccValue],
) -> WccValue:
    if isinstance(value, WccNameAtom):
        return substitutions.get(value.name, value)
    if isinstance(value, WccFieldAccessAtom):
        base = _substitute_wcc_value(value.base, substitutions)
        if not isinstance(
            base,
            (
                WccLiteralAtom,
                WccNameAtom,
                WccFieldAccessAtom,
                WccPhaseTargetAtom,
                WccRecordAtom,
                WccOpaqueFrontendValue,
            ),
        ):
            raise TypeError("field-access substitution must remain atomic")
        return replace(value, base=base)
    if isinstance(value, WccRecordAtom):
        return replace(
            value,
            fields=tuple(
                (
                    name,
                    _substitute_wcc_value(field_value, substitutions),
                )
                for name, field_value in value.fields
            ),
        )
    if isinstance(value, WccInject):
        return replace(
            value,
            fields=tuple(
                (
                    name,
                    _substitute_wcc_value(field_value, substitutions),
                )
                for name, field_value in value.fields
            ),
        )
    if isinstance(value, WccPureOp):
        return replace(
            value,
            args=tuple(
                _substitute_wcc_value(arg, substitutions)
                for arg in value.args
            ),
        )
    if isinstance(value, WccSelect):
        return replace(
            value,
            condition=_substitute_wcc_value(value.condition, substitutions),
            then_arm=_substitute_wcc_select_arm(value.then_arm, substitutions),
            else_arm=_substitute_wcc_select_arm(value.else_arm, substitutions),
        )
    if isinstance(value, WccOpaqueFrontendValue):
        return replace(
            value,
            expr=_substitute_wcc_opaque_expr(value.expr, substitutions),
        )
    return value


def _substitute_wcc_select_arm(
    arm: WccSelectArm,
    substitutions: Mapping[str, WccValue],
) -> WccSelectArm:
    """Substitute free names through one arm, respecting arm-local shadowing.

    Each bound name shadows the outer substitution mapping only for the rest
    of that arm, so a later binding or the terminal value sees the local
    binding rather than the outer replacement.
    """

    shadowed: set[str] = set()
    prefix: list[WccLet] = []
    for let_node in arm.prefix:
        active = {
            name: value
            for name, value in substitutions.items()
            if name not in shadowed
        }
        prefix.append(
            replace(
                let_node,
                bound_value=_substitute_wcc_value(let_node.bound_value, active),
            )
        )
        shadowed.add(let_node.bound_name)
    active = {
        name: value
        for name, value in substitutions.items()
        if name not in shadowed
    }
    return WccSelectArm(
        prefix=tuple(prefix),
        value=_substitute_wcc_value(arm.value, active),
    )


def _substitute_wcc_payload(
    value,
    substitutions: Mapping[str, WccValue],
):
    if isinstance(value, (WccRunRefPayload, WccTrialPayload)):
        return value
    if isinstance(
        value,
        (
            WccLiteralAtom,
            WccNameAtom,
            WccFieldAccessAtom,
            WccPhaseTargetAtom,
            WccRecordAtom,
            WccOpaqueFrontendValue,
            WccInject,
            WccPureOp,
            WccSelect,
        ),
    ):
        return _substitute_wcc_value(value, substitutions)
    if isinstance(value, tuple):
        return tuple(
            _substitute_wcc_payload(item, substitutions)
            for item in value
        )
    if isinstance(value, list):
        return [
            _substitute_wcc_payload(item, substitutions)
            for item in value
        ]
    if isinstance(value, Mapping):
        return {
            key: _substitute_wcc_payload(item, substitutions)
            for key, item in value.items()
        }
    if is_dataclass(value):
        updates = {
            field.name: _substitute_wcc_payload(
                getattr(value, field.name),
                substitutions,
            )
            for field in dataclass_fields(value)
            if field.init and field.name not in {"run_ref_metadata", "run_ref_origin", "carrier_family", "owner_union", "discriminant_owner", "resolved_type_ref"}
        }
        if any(
            updates[name] is not getattr(value, name)
            for name in updates
        ):
            return replace(value, **updates)
    return value


def _raise_provider_member_ineligible(
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    *,
    offending_metadata,
    message: str,
) -> None:
    is_peer_group = isinstance(
        member,
        WccProviderPeerGroupMember,
    )
    offending_span = getattr(
        offending_metadata,
        "source_span",
        getattr(offending_metadata, "span", member.metadata.source_span),
    )
    offending_form_path = getattr(
        offending_metadata,
        "form_path",
        member.metadata.form_path,
    )
    offending_expansion_stack = getattr(
        offending_metadata,
        "expansion_stack",
        member.metadata.expansion_stack,
    )
    diagnostics = [
        LispFrontendDiagnostic(
            code=(
                "provider_peer_group_member_ineligible"
                if is_peer_group
                else "provider_supervision_member_ineligible"
            ),
            message=message,
            span=member.metadata.source_span,
            form_path=member.metadata.form_path,
            expansion_stack=member.metadata.expansion_stack,
            phase="lowering",
        )
    ]
    if (
        offending_span != member.metadata.source_span
        or offending_form_path != member.metadata.form_path
    ):
        diagnostics.append(
            LispFrontendDiagnostic(
                code=(
                    "provider_peer_group_member_disqualifying_form"
                    if is_peer_group
                    else "provider_supervision_member_disqualifying_form"
                ),
                message="specialized member contains this disqualifying form",
                span=offending_span,
                form_path=offending_form_path,
                expansion_stack=offending_expansion_stack,
                phase="lowering",
            )
        )
    raise LispFrontendCompileError(tuple(diagnostics))


def _provider_region_role(
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
) -> str:
    if isinstance(member, WccProviderPeerGroupMember):
        return "provider-peer-group"
    return "provider-supervision"


def _wcc_route_schema_version(metadata) -> str:
    parts = metadata.node_id.split(":")
    if len(parts) >= 3:
        return parts[1]
    return WccIdentityFactory.route_schema_version


def _body_to_prefix_and_value(body: WccBody) -> tuple[tuple[WccLet, ...], WccValue]:
    prefix: list[WccLet] = []
    current = body
    while isinstance(current, WccLet):
        prefix.append(current)
        current = current.body
    if not isinstance(current, WccHalt):
        raise TypeError(f"expected linear WCC value body, found `{type(current).__name__}`")
    return tuple(prefix), current.result


def _wrap_prefix_lets(prefix: tuple[WccLet, ...], tail: WccBody) -> WccBody:
    current = tail
    for let_node in reversed(prefix):
        current = replace(let_node, body=current)
    return current


def _generated_join_name(scope: WccIdentityFactory, *, binding_name: str) -> str:
    return f"__wcc_join_{binding_name}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _phase_scope_from_expr(expr: WithPhaseExpr) -> WccPhaseScope:
    return WccPhaseScope(
        ctx_expr=expr.ctx_expr,
        phase_name=expr.phase_name,
        source_span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


@records_defect_provenance("elaboration")
def _elaborate_expr_to_body(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    if isinstance(expr, WithPhaseExpr):
        if scope.closed_program and not isinstance(
            expr.ctx_expr,
            (NameExpr, FieldAccessExpr),
        ):
            reserved = reserved_identifiers(
                expr,
                value_env=value_env,
                compile_time_bindings=compile_time_bindings,
            )
            naming_scope = generated_name_scope(scope).child_scope(
                "with-phase-context",
                authored_binding_name="ctx",
            )
            binding_name = fresh_name(
                _generated_effect_binding_name_from_scope(
                    naming_scope,
                    role="ctx",
                ),
                reserved,
            )
            context_name = NameExpr(
                name=binding_name,
                span=expr.ctx_expr.span,
                form_path=expr.ctx_expr.form_path,
                expansion_stack=expr.ctx_expr.expansion_stack,
            )
            wrapped = LetStarExpr(
                bindings=((binding_name, expr.ctx_expr),),
                body=replace(expr, ctx_expr=context_name),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            return _elaborate_let_star(
                wrapped,
                scope=scope.child_scope("with-phase-context"),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        return _elaborate_expr_to_body(
            expr.body,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=_phase_scope_from_expr(expr),
        )
    if isinstance(expr, LetStarExpr):
        return _elaborate_let_star(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, MatchExpr):
        return _elaborate_match_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, IfExpr) and not is_pure_projection_expr(expr):
        return _elaborate_if_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if (
        scope.closed_program
        and isinstance(expr, PureOpExpr)
        and expr.operator in {"and", "or"}
        and target_dsl_supports_strict_boolean_control_flow(
            getattr(type_env, "target_dsl_version", "") or ""
        )
        and _contains_effect(expr)
    ):
        return _elaborate_if_to_body(
            fold_pure_short_circuit(expr),
            scope=scope.child_scope("short-circuit"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, LoopRecurExpr):
        if scope.closed_program:
            bound_operands = _bind_effectful_loop_operands(
                expr,
                scope=scope,
                value_env=value_env,
                compile_time_bindings=compile_time_bindings,
            )
            if bound_operands is not None:
                return _elaborate_let_star(
                    bound_operands,
                    scope=scope.child_scope("loop-operands"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
        return _elaborate_loop_recur_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, ContinueExpr):
        fields_scope = scope.child_scope("loop-continue-fields")
        bound_fields = _bind_effectful_loop_state_fields(
            expr,
            scope=fields_scope,
            type_env=type_env,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
        if bound_fields is not None:
            return _elaborate_let_star(
                bound_fields,
                scope=fields_scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        prefix, state_value = _elaborate_expr_to_value(
            expr.state_expr,
            scope=scope.child_scope("loop-continue", authored_binding_name="state"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        continue_node = WccLoopContinue(
            metadata=scope.body_metadata(
                role="loop:continue",
                type_ref=_infer_expr_type(
                    expr.state_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    closed_program=scope.closed_program,
                ),
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            target_name="__wcc_current_loop__",
            state_args=(state_value,),
        )
        return _wrap_prefix_lets(prefix, continue_node)
    if isinstance(expr, DoneExpr):
        if scope.closed_program:
            reserved = reserved_identifiers(
                expr,
                value_env=value_env,
                compile_time_bindings=compile_time_bindings,
            )
            naming_scope = generated_name_scope(scope).child_scope(
                "loop-done",
                authored_binding_name="result",
            )
            bindings: list[tuple[str, object]] = []
            changes: dict[str, object] = {}
            for field_name, operand in (
                ("result_expr", expr.result_expr),
                ("terminal_state_expr", expr.terminal_state_expr),
            ):
                if operand is None or not (
                    isinstance(operand, MatchExpr) or _contains_effect(operand)
                ):
                    continue
                binding_name = fresh_name(
                    _generated_effect_binding_name_from_scope(
                        naming_scope,
                        role=("result" if field_name == "result_expr" else "state"),
                    ),
                    reserved,
                )
                bindings.append((binding_name, operand))
                changes[field_name] = NameExpr(
                    name=binding_name,
                    span=operand.span,
                    form_path=operand.form_path,
                    expansion_stack=operand.expansion_stack,
                )
            if bindings:
                return _elaborate_let_star(
                    LetStarExpr(
                        bindings=tuple(bindings),
                        body=replace(expr, **changes),
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                    scope=scope.child_scope("loop-done-values"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
        prefix, result_value = _elaborate_expr_to_value(
            expr.result_expr,
            scope=scope.child_scope("loop-done", authored_binding_name="result"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        state_prefix: tuple[WccLet, ...] = ()
        state_value = None
        if expr.terminal_state_expr is not None:
            state_prefix, state_value = _elaborate_expr_to_value(
                expr.terminal_state_expr,
                scope=scope.child_scope(
                    "loop-done",
                    authored_binding_name="state",
                ),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        done_node = WccLoopDone(
            metadata=scope.body_metadata(
                role="loop:done",
                type_ref=_infer_expr_type(
                    expr.result_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    closed_program=scope.closed_program,
                ),
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            result=result_value,
            state=state_value,
        )
        return _wrap_prefix_lets((*prefix, *state_prefix), done_node)
    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RequestInputExpr,
            RunRefExpr,
            TrialExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            MaterializeViewExpr,
            FinalizeSelectedItemExpr,
            CallExpr,
            ProcedureCallExpr,
            WithLiveProviderPeersExpr,
            WithLiveProvidersExpr,
        ),
    ):
        return _elaborate_effect_expr_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, (RecordExpr, UnionVariantExpr)) and any(
        isinstance(field_expr, MatchExpr) for _, field_expr in expr.fields
    ):
        return _elaborate_constructor_field_matches_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if scope.closed_program and _contains_effect(expr):
        prefix, terminal = _normalize_operand(
            expr,
            path=(),
            closed_program=True,
        )
        if prefix:
            return _elaborate_let_star(
                LetStarExpr(
                    bindings=prefix,
                    body=terminal,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                scope=scope.child_scope("value-operands"),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
    prefix, value = _elaborate_expr_to_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    halt = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=_infer_expr_type(
                expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=scope.closed_program,
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=value,
    )
    return _wrap_prefix_lets(prefix, halt)


def _bind_effectful_loop_state_fields(
    expr: ContinueExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[str, object],
) -> LetStarExpr | None:
    """Bind each effectful `loop-state :like` field before `continue`, as `let*` would.

    From target 2.33 this returns ``(let* ((g1 e1) ...) (continue (loop-state
    :like base ... :f g1 ...)))`` with one generated binding per field that
    contains an effect, in authored field order, so each effect runs once and
    left to right. Each generated name is named by its field and the `case` arms
    around it, and differs from every identifier in scope and inside `expr`, so
    it captures no authored reference. It returns None below 2.33 or when no
    field has an effect; the state then stays an opaque value that the loop
    lowerer projects as pure.
    """

    state = expr.state_expr
    if not (
        isinstance(state, LoopStateUpdateExpr)
        and _at_2_33(type_env)
        and any(_contains_effect(field_expr) for _, field_expr in state.overrides)
    ):
        return None
    reserved = reserved_identifiers(expr, value_env=value_env, compile_time_bindings=compile_time_bindings)
    naming_scope = generated_name_scope(scope)
    bindings: list[tuple[str, object]] = []
    overrides: list[tuple[str, object]] = []
    for field_name, field_expr in state.overrides:
        if _contains_effect(field_expr):
            binding_name = fresh_name(
                _generated_effect_binding_name_from_scope(
                    naming_scope.child_scope("field", authored_binding_name=field_name),
                    role=field_name,
                ),
                reserved,
            )
            bindings.append((binding_name, field_expr))
            field_expr = NameExpr(
                name=binding_name,
                span=field_expr.span,
                form_path=field_expr.form_path,
                expansion_stack=field_expr.expansion_stack,
            )
        overrides.append((field_name, field_expr))
    return LetStarExpr(
        bindings=tuple(bindings),
        body=replace(expr, state_expr=replace(state, overrides=tuple(overrides))),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _command_narrowed_bindings(bindings, value_env):
    context = bindings.get(_COMMAND_SCOPE_CONTEXT)
    if context is None:
        return bindings
    return {**bindings, _COMMAND_SCOPE_CONTEXT: context.narrow(value_env)}


def _command_compile_time_binding(bindings, *, expr, name, type_ref):
    context = bindings.get(_COMMAND_SCOPE_CONTEXT)
    if context is None:
        return bindings
    return {**bindings, _COMMAND_SCOPE_CONTEXT: context.compile_time_bind(expr, name=name, type_ref=type_ref)}


def _command_bound_bindings(bindings, *, expr, name, type_ref, scope, metadata,
    expansion_owned=False, capture_source=None):
    context = bindings.get(_COMMAND_SCOPE_CONTEXT)
    if context is None:
        return bindings
    operand = WccNameAtom(metadata=scope.atom_metadata(
        role=f"name:{name}", type_ref=type_ref, source_span=expr.span,
        form_path=expr.form_path, binding_identity=metadata.binding_identity), name=name)
    child = context.bind(expr, name=name, type_ref=type_ref, operand=operand,
        metadata=metadata, variants=scope.enclosing_variants,
        expansion_owned=expansion_owned, capture_source=capture_source)
    return {**bindings, _COMMAND_SCOPE_CONTEXT: child}


def binding_type_for_elaboration(
    binding_expr, *, type_env, value_env, workflow_return_types,
    procedure_return_types, closed_program, capture_source=None,
):
    """Resolve the reached RHS under its incoming lexical environment."""
    if closed_program and capture_source is not None:
        return capture_source[1]
    return _infer_expr_type(
        binding_expr, type_env=type_env, value_env=value_env,
        workflow_return_types=workflow_return_types, procedure_return_types=procedure_return_types,
        closed_program=closed_program,
    )


def _elaborate_let_star(
    expr: LetStarExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    if scope.closed_program:
        reserved = reserved_identifiers(
            expr,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
        naming_scope = generated_name_scope(scope).child_scope(
            "bind-proc-values"
        )
        bindings: list[tuple[str, object]] = []
        labels: list[str | None] = []
        identities: list[object | None] = []
        capture_sources: list[tuple[object, TypeRef] | None] = []
        changed = False
        local_env = dict(value_env)

        def rewrite_bound_values(
            owner: BindProcExpr,
            owner_path: tuple[str, ...],
            owner_env: dict[str, TypeRef],
        ) -> tuple[BindProcExpr, list[tuple[str, object]]]:
            nonlocal changed
            rewritten = []
            prefixes: list[tuple[str, object]] = []
            for bound in owner.bindings:
                bound_expr = bound.value_expr
                if isinstance(bound_expr, BindProcExpr):
                    bound_expr, nested_prefixes = rewrite_bound_values(
                        bound_expr,
                        (*owner_path, bound.name),
                        owner_env,
                    )
                    prefixes.extend(nested_prefixes)
                if (
                    bound.source_binding_identity is None
                    and not isinstance(bound_expr, BindProcExpr)
                    and _contains_effect(bound_expr)
                ):
                    bound_type = _infer_expr_type(
                        bound_expr,
                        type_env=type_env,
                        value_env=owner_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    )
                    if isinstance(bound_type, ProcRefTypeRef):
                        rewritten.append(bound)
                        continue
                    binding_path = (*owner_path, bound.name)
                    binding_scope = naming_scope.child_scope(
                        "binding",
                        authored_binding_name=":".join(binding_path),
                    )
                    generated_name = fresh_name(
                        _generated_effect_binding_name_from_scope(
                            binding_scope,
                            role=bound.name,
                        ),
                        reserved,
                    )
                    prefixes.append((generated_name, bound_expr))
                    owner_env[generated_name] = bound_type
                    bound_expr = NameExpr(
                        name=generated_name,
                        span=bound.value_expr.span,
                        form_path=bound.value_expr.form_path,
                        expansion_stack=bound.value_expr.expansion_stack,
                    )
                if bound_expr is not bound.value_expr:
                    bound = replace(bound, value_expr=bound_expr)
                    changed = True
                rewritten.append(bound)
            if tuple(rewritten) != owner.bindings:
                owner = replace(owner, bindings=tuple(rewritten))
            return owner, prefixes

        for index, (name, value) in enumerate(expr.bindings):
            if isinstance(value, BindProcExpr):
                value, prefixes = rewrite_bound_values(
                    value,
                    (str(index), name),
                    local_env,
                )
                for prefix_name, prefix_value in prefixes:
                    bindings.append((prefix_name, prefix_value))
                    labels.append(None)
                    identities.append(None)
                    capture_sources.append(None)
            bindings.append((name, value))
            labels.append(
                expr.binding_labels[index]
                if index < len(expr.binding_labels)
                else None
            )
            identities.append(
                expr.binding_identities[index]
                if index < len(expr.binding_identities)
                else None
            )
            capture_sources.append(
                expr.binding_capture_sources[index]
                if index < len(expr.binding_capture_sources)
                else None
            )
            local_env[name] = binding_type_for_elaboration(
                value,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=True, capture_source=capture_sources[-1],
            )
        if changed:
            expr = replace(
                expr,
                bindings=tuple(bindings),
                binding_labels=tuple(labels),
                binding_identities=tuple(identities),
                binding_capture_sources=tuple(capture_sources),
            )

    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    def expansion_owned_binding_source(binding_expr):
        """Keep compiler call ancestry on its ordered lexical bindings.

        The normalizer owns a generated ``LetStarExpr`` while each actual and
        formal child retains its authored span.  WCC must retain both facts so
        lowering can materialize an eager initializer before a later effect
        without conflating separate call sites.
        """

        if not target_dsl_supports_pure_call_composition(
            getattr(type_env, "target_dsl_version", "") or ""
        ):
            return binding_expr, False
        ordered_frames: list[object] = []
        for frame in (*expr.expansion_stack, *binding_expr.expansion_stack):
            if frame not in ordered_frames:
                ordered_frames.append(frame)
        expansion_owned = any(
            isinstance(frame, (HelperExpansionFrame, ProcedureExpansionFrame))
            for frame in ordered_frames
        )
        if not expansion_owned:
            return binding_expr, False
        return replace(binding_expr, expansion_stack=tuple(ordered_frames)), True

    def build(
        index: int,
        local_env: Mapping[str, TypeRef],
        local_scope: WccIdentityFactory,
        local_compile_time_bindings: Mapping[str, object],
    ) -> WccBody:
        if index >= len(expr.bindings):
            return _elaborate_expr_to_body(
                expr.body,
                scope=local_scope.child_scope("body", authored_binding_name="result"),
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )

        binding_name, binding_expr = expr.bindings[index]
        binding_label = (
            expr.binding_labels[index]
            if index < len(expr.binding_labels)
            else None
        )
        binding_identity = (
            expr.binding_identities[index]
            if index < len(expr.binding_identities)
            else None
        )
        capture_source = (
            expr.binding_capture_sources[index]
            if index < len(expr.binding_capture_sources)
            else None
        )
        binding_expr, expansion_owned = expansion_owned_binding_source(binding_expr)
        binding_type = binding_type_for_elaboration(
            binding_expr, type_env=type_env, value_env=local_env,
            workflow_return_types=workflow_return_types, procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program, capture_source=capture_source,
        )
        next_env = dict(local_env)
        next_env[binding_name] = binding_type
        runtime_tail_compile_time_bindings = dict(
            local_compile_time_bindings
        )
        runtime_tail_compile_time_bindings.pop(
            binding_name,
            None,
        )
        def command_tail_bindings(owner_scope, role="let"):
            metadata = owner_scope.body_metadata(
                role=f"{role}:{binding_name}", type_ref=result_type,
                source_span=binding_expr.span, form_path=binding_expr.form_path,
                expansion_stack=binding_expr.expansion_stack,
                binding_label=binding_label, binding_identity=binding_identity)
            return _command_bound_bindings(runtime_tail_compile_time_bindings,
                expr=binding_expr, name=binding_name, type_ref=binding_type,
                scope=owner_scope, metadata=metadata,
                expansion_owned=expansion_owned, capture_source=capture_source)

        if scope.closed_program and capture_source is not None:
            source_identity, source_type_ref = capture_source
            source_name = getattr(source_identity, "name", None)
            if not isinstance(source_name, str):
                raise ValueError("pure-call capture row has no retained lexical binder name")
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                command_tail_bindings(local_scope),
            )
            return WccLet(
                metadata=local_scope.body_metadata(
                    role=f"let:{binding_name}",
                    type_ref=result_type,
                    source_span=binding_expr.span,
                    form_path=binding_expr.form_path,
                    expansion_stack=binding_expr.expansion_stack,
                    binding_label=binding_label,
                    binding_identity=binding_identity,
                ),
                bound_name=binding_name,
                bound_type_ref=source_type_ref,
                bound_value=WccNameAtom(
                    metadata=local_scope.atom_metadata(
                        role=f"name:{source_name}",
                        type_ref=source_type_ref,
                        source_span=binding_expr.span,
                        form_path=binding_expr.form_path,
                        expansion_stack=binding_expr.expansion_stack,
                        binding_identity=source_identity,
                    ),
                    name=source_name,
                ),
                body=tail,
            )
        if isinstance(binding_expr, BindProcExpr):
            if not local_compile_time_bindings.get(
                _PRESERVE_BOUND_PROC_CAPTURES,
                False,
            ):
                next_compile_time_bindings = dict(
                    local_compile_time_bindings
                )
                next_compile_time_bindings[binding_name] = (
                    binding_expr
                )
                next_compile_time_bindings = _command_compile_time_binding(next_compile_time_bindings,
                    expr=binding_expr, name=binding_name, type_ref=next_env[binding_name])
                return build(
                    index + 1,
                    next_env,
                    local_scope.child_scope(
                        "body",
                        authored_binding_name=binding_name,
                    ),
                    next_compile_time_bindings,
                )
            capture_rows = _materialize_bind_proc_capture_aliases(
                binding_expr,
                owner_role=binding_name,
                scope=local_scope,
                value_env=local_env,
                compile_time_bindings=local_compile_time_bindings,
            )
            next_env.update(
                {
                    capture.alias_name: capture.type_ref
                    for capture in capture_rows
                }
            )
            next_compile_time_bindings = dict(local_compile_time_bindings)
            inherited_captures = _inherited_bind_proc_capture_values(
                binding_expr,
                compile_time_bindings=local_compile_time_bindings,
            )
            next_compile_time_bindings[binding_name] = (
                _WccBoundProcedureBinding(
                    capture_values=(
                        *inherited_captures,
                        *(
                            (
                                capture.source_name,
                                capture.alias_atom,
                                binding_expr,
                            )
                            for capture in capture_rows
                        ),
                    ),
                    source_binding=binding_expr,
                )
            )
            next_compile_time_bindings = _command_compile_time_binding(next_compile_time_bindings,
                expr=binding_expr, name=binding_name, type_ref=next_env[binding_name])
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                next_compile_time_bindings,
            )
            return _wrap_bind_proc_capture_aliases(
                capture_rows,
                tail=tail,
                result_type=result_type,
            )
        if _is_compile_time_reference_value(binding_expr):
            next_compile_time_bindings = dict(
                local_compile_time_bindings
            )
            next_compile_time_bindings[binding_name] = binding_expr
            next_compile_time_bindings = _command_compile_time_binding(next_compile_time_bindings,
                expr=binding_expr, name=binding_name, type_ref=next_env[binding_name])
            return build(
                index + 1,
                next_env,
                local_scope.child_scope(
                    "body",
                    authored_binding_name=binding_name,
                ),
                next_compile_time_bindings,
            )
        if isinstance(binding_expr, NameExpr):
            forwarded_compile_time_value = (
                local_compile_time_bindings.get(binding_expr.name)
            )
            if _is_compile_time_reference_value(
                forwarded_compile_time_value
            ):
                alias_value, alias_source_name = (
                    _unwrap_compile_time_alias(
                        forwarded_compile_time_value,
                        default_source_name=binding_expr.name,
                    )
                )
                next_compile_time_bindings = dict(
                    local_compile_time_bindings
                )
                next_compile_time_bindings[binding_name] = (
                    _WccCompileTimeAlias(
                        value=alias_value,
                        source_name=alias_source_name,
                    )
                )
                next_compile_time_bindings = _command_compile_time_binding(next_compile_time_bindings,
                    expr=binding_expr, name=binding_name, type_ref=next_env[binding_name])
                return build(
                    index + 1,
                    next_env,
                    local_scope.child_scope(
                        "body",
                        authored_binding_name=binding_name,
                    ),
                    next_compile_time_bindings,
                )
        if isinstance(
            binding_expr,
            (
                ProviderResultExpr,
                CommandResultExpr,
                RequestInputExpr,
                RunRefExpr,
                TrialExpr,
                RunProviderPhaseExpr,
                ProduceOneOfExpr,
                ResumeOrStartExpr,
                ResourceTransitionExpr,
                FinalizeSelectedItemExpr,
                CallExpr,
                ProcedureCallExpr,
            ),
        ):
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                command_tail_bindings(local_scope),
            )
            return _elaborate_effect_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
                binding_label=binding_label,
                binding_identity=binding_identity,
                continuation=tail,
                let_result_type=result_type,
                scope=local_scope,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )

        if isinstance(binding_expr, MatchExpr):
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                command_tail_bindings(local_scope.child_scope("match", authored_binding_name=binding_name), "join"),
            )
            return _elaborate_non_tail_match_binding(
                binding_name=binding_name,
                binding_type=binding_type,
                match_expr=binding_expr,
                binding_label=binding_label,
                binding_identity=binding_identity,
                continuation=tail,
                scope=local_scope.child_scope("match", authored_binding_name=binding_name),
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )

        if isinstance(binding_expr, IfExpr) and not is_pure_projection_expr(binding_expr):
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                command_tail_bindings(local_scope.child_scope("if", authored_binding_name=binding_name), "join"),
            )
            binding_scope = local_scope.child_scope("if", authored_binding_name=binding_name)
            binding_body = _elaborate_if_to_body(
                binding_expr,
                scope=binding_scope,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            return _elaborate_control_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
                binding_body=binding_body,
                continuation=tail,
                scope=binding_scope,
                effect_summary=effect_summary,
                active_phase_scope=active_phase_scope,
                binding_label=binding_label,
                binding_identity=binding_identity,
            )

        if (
            expansion_owned
            and isinstance(binding_expr, LetStarExpr)
            and is_pure_projection_expr(binding_expr)
        ):
            normalized_body = None
            if local_scope.closed_program:
                from .anf import normalize_wcc_body_to_anf

                normalized_body = normalize_wcc_body_to_anf(_elaborate_expr_to_body(
                    binding_expr,
                    scope=local_scope.child_scope("opaque-block", authored_binding_name=binding_name),
                    type_env=type_env,
                    value_env=local_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=local_compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ))
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                command_tail_bindings(local_scope),
            )
            return WccLet(
                metadata=local_scope.body_metadata(
                    role=f"let:{binding_name}",
                    type_ref=result_type,
                    source_span=binding_expr.span,
                    form_path=binding_expr.form_path,
                    expansion_stack=binding_expr.expansion_stack,
                    binding_label=binding_label,
                    binding_identity=binding_identity,
                ),
                bound_name=binding_name,
                bound_type_ref=binding_type,
                bound_value=WccOpaqueFrontendValue(
                    metadata=local_scope.value_metadata(
                        role=f"opaque:expansion-let:{binding_name}",
                        type_ref=binding_type,
                        source_span=binding_expr.span,
                        form_path=binding_expr.form_path,
                        expansion_stack=binding_expr.expansion_stack,
                    ),
                    expr=binding_expr if normalized_body is None else None,
                    normalized_body=normalized_body,
                ),
                body=tail,
            )

        binding_scope = local_scope.child_scope("binding", authored_binding_name=binding_name)
        binding_body = _elaborate_expr_to_body(
            binding_expr,
            scope=binding_scope,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=local_compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        tail = build(
            index + 1,
            next_env,
            local_scope.child_scope("body", authored_binding_name=binding_name),
            command_tail_bindings(binding_scope, "join") if not _is_linear_value_body(binding_body) else command_tail_bindings(local_scope),
        )
        if not _is_linear_value_body(binding_body):
            return _elaborate_control_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
                binding_body=binding_body,
                continuation=tail,
                scope=binding_scope,
                effect_summary=effect_summary,
                active_phase_scope=active_phase_scope,
                binding_label=binding_label,
                binding_identity=binding_identity,
            )

        prefix, value = _body_to_prefix_and_value(binding_body)
        # At every target: a correction of values, not of acceptance.
        prefix, value = hoist_without_capture(
            prefix,
            value,
            over=((
                replace(
                    expr,
                    bindings=expr.bindings[index + 1 :],
                    binding_labels=expr.binding_labels[index + 1 :],
                    binding_identities=expr.binding_identities[index + 1 :],
                    binding_capture_sources=expr.binding_capture_sources[index + 1 :],
                ),
                frozenset({binding_name}),
            ),),
            scope=binding_scope,
            value_env=local_env,
            compile_time_bindings=local_compile_time_bindings,
        )
        let_node = WccLet(
            metadata=local_scope.body_metadata(
                role=f"let:{binding_name}",
                type_ref=result_type,
                source_span=binding_expr.span,
                form_path=binding_expr.form_path,
                expansion_stack=binding_expr.expansion_stack,
                binding_label=binding_label,
                binding_identity=binding_identity,
            ),
            bound_name=binding_name,
            bound_type_ref=binding_type,
            bound_value=value,
            body=tail,
        )
        return _wrap_prefix_lets(prefix, let_node)

    return build(0, dict(value_env), scope, dict(compile_time_bindings))


def _bind_proc_runtime_capture_sites(
    expr: BindProcExpr,
    *,
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[str, object],
) -> tuple[tuple[str, NameExpr], ...]:
    captures: dict[str, NameExpr] = {}

    def visit(node: object, *, shadowed: frozenset[str]) -> None:
        if isinstance(node, NameExpr):
            if node.name in shadowed:
                return
            type_ref = value_env.get(node.name)
            if type_ref is None or isinstance(
                type_ref,
                (ProcRefTypeRef, WorkflowRefTypeRef),
            ):
                return
            if _is_compile_time_reference_value(
                compile_time_bindings.get(node.name)
            ):
                return
            captures.setdefault(node.name, node)
            return
        if isinstance(node, LetStarExpr):
            local_shadowed = set(shadowed)
            for binding_name, binding_expr in node.bindings:
                visit(
                    binding_expr,
                    shadowed=frozenset(local_shadowed),
                )
                local_shadowed.add(binding_name)
            visit(node.body, shadowed=frozenset(local_shadowed))
            return
        if isinstance(node, MatchExpr):
            visit(node.subject, shadowed=shadowed)
            for arm in node.arms:
                visit(
                    arm.body,
                    shadowed=shadowed | {arm.binding_name},
                )
            return
        if isinstance(node, ListMapExpr):
            visit(node.source_expr, shadowed=shadowed)
            visit(
                node.body_expr,
                shadowed=shadowed | {node.binder_name},
            )
            return
        if isinstance(node, tuple | list):
            for item in node:
                visit(item, shadowed=shadowed)
            return
        if isinstance(node, Mapping):
            for item in node.values():
                visit(item, shadowed=shadowed)
            return
        if is_dataclass(node):
            for field in dataclass_fields(node):
                if field.init and field.name not in {"run_ref_metadata", "run_ref_origin", "carrier_family", "owner_union", "discriminant_owner", "resolved_type_ref"}:
                    visit(
                        getattr(node, field.name),
                        shadowed=shadowed,
                    )

    if isinstance(expr.base_expr, BindProcExpr):
        for capture_name, capture_expr in (
            _bind_proc_runtime_capture_sites(
                expr.base_expr,
                value_env=value_env,
                compile_time_bindings=compile_time_bindings,
            )
        ):
            captures.setdefault(capture_name, capture_expr)
    for binding in expr.bindings:
        visit(binding.value_expr, shadowed=frozenset())
    return tuple(captures.items())


def _materialize_bind_proc_capture_aliases(
    expr: BindProcExpr,
    *,
    owner_role: str,
    scope: WccIdentityFactory,
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[str, object],
) -> tuple[_WccRuntimeCaptureAlias, ...]:
    captures: list[_WccRuntimeCaptureAlias] = []
    for ordinal, (capture_name, capture_expr) in enumerate(
        _bind_proc_runtime_capture_sites(
            expr,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
    ):
        capture_type = value_env[capture_name]
        capture_scope = scope.child_scope(
            "bind-proc-capture",
            authored_binding_name=(
                f"{owner_role}:{capture_name}:{ordinal}"
            ),
        )
        alias_name = _generated_value_binding_name_from_scope(
            capture_scope,
            role=(
                f"bind-proc-capture:{owner_role}:"
                f"{capture_name}:{ordinal}"
            ),
        )
        captures.append(
            _WccRuntimeCaptureAlias(
                source_name=capture_name,
                alias_name=alias_name,
                type_ref=capture_type,
                source_expr=capture_expr,
                source_atom=WccNameAtom(
                    metadata=capture_scope.atom_metadata(
                        role=f"capture-source:{capture_name}",
                        type_ref=capture_type,
                        source_span=capture_expr.span,
                        form_path=capture_expr.form_path,
                        expansion_stack=capture_expr.expansion_stack,
                    ),
                    name=capture_name,
                ),
                alias_atom=WccNameAtom(
                    metadata=capture_scope.atom_metadata(
                        role=f"capture-alias:{alias_name}",
                        type_ref=capture_type,
                        source_span=capture_expr.span,
                        form_path=capture_expr.form_path,
                        expansion_stack=capture_expr.expansion_stack,
                    ),
                    name=alias_name,
                ),
                scope=capture_scope,
            )
        )
    return tuple(captures)


def _inherited_bind_proc_capture_values(
    expr: BindProcExpr,
    *,
    compile_time_bindings: Mapping[str, object],
) -> tuple[tuple[str, WccValue, object | None], ...]:
    if not isinstance(expr.base_expr, NameExpr):
        return ()
    base_binding, _ = _unwrap_compile_time_alias(
        compile_time_bindings.get(expr.base_expr.name),
    )
    if not isinstance(base_binding, _WccBoundProcedureBinding):
        return ()
    return base_binding.capture_values


def _wrap_bind_proc_capture_aliases(
    captures: tuple[_WccRuntimeCaptureAlias, ...],
    *,
    tail: WccBody,
    result_type: TypeRef,
) -> WccBody:
    current = tail
    for capture in reversed(captures):
        current = WccLet(
            metadata=capture.scope.body_metadata(
                role=f"let:{capture.alias_name}",
                type_ref=result_type,
                source_span=capture.source_expr.span,
                form_path=capture.source_expr.form_path,
                expansion_stack=capture.source_expr.expansion_stack,
            ),
            bound_name=capture.alias_name,
            bound_type_ref=capture.type_ref,
            bound_value=capture.source_atom,
            body=current,
        )
    return current


def _bind_effectful_loop_operands(
    expr: LoopRecurExpr,
    *,
    scope: WccIdentityFactory,
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[str, object],
) -> LetStarExpr | None:
    """Bind effectful loop operands in parser-retained keyword order.

    Macro argument spans can point back to a call-site order that differs
    from the expanded keyword order. Hand-built loops use the stable :max
    then :state fallback. Seed fields remain in their own authored order.
    """

    reserved = reserved_identifiers(
        expr,
        value_env=value_env,
        compile_time_bindings=compile_time_bindings,
    )
    naming_scope = generated_name_scope(scope).child_scope(
        "loop-operands",
        authored_binding_name=expr.binding_name,
    )
    bindings: list[tuple[str, object]] = []
    max_expr = expr.max_iterations_expr
    state_expr = expr.initial_state_expr

    def bind_operand(operand, *, role: str):
        binding_scope = naming_scope.child_scope(
            "operand",
            authored_binding_name=role,
        )
        binding_name = fresh_name(
            _generated_effect_binding_name_from_scope(
                binding_scope,
                role=role,
            ),
            reserved,
        )
        bindings.append((binding_name, operand))
        return NameExpr(
            name=binding_name,
            span=operand.span,
            form_path=operand.form_path,
            expansion_stack=operand.expansion_stack,
        )

    order = expr.operand_evaluation_order or (":max", ":state")
    if len(order) != 2 or set(order) != {":max", ":state"}:
        raise ValueError(
            "loop operand evaluation order must contain :max and :state exactly once"
        )
    for operand_name in order:
        if operand_name == ":max":
            if _contains_effect(max_expr):
                max_expr = bind_operand(max_expr, role="budget")
            continue
        if isinstance(state_expr, LoopStateSeedExpr):
            fields = []
            for state_field in state_expr.fields:
                field_expr = state_field.value_expr
                if _contains_effect(field_expr):
                    field_expr = bind_operand(
                        field_expr,
                        role=f"seed_{state_field.name}",
                    )
                fields.append(replace(state_field, value_expr=field_expr))
            if any(
                rewritten is not original
                for rewritten, original in zip(
                    fields,
                    state_expr.fields,
                    strict=True,
                )
            ):
                state_expr = replace(state_expr, fields=tuple(fields))
        elif _contains_effect(state_expr):
            state_expr = bind_operand(state_expr, role="seed")

    if not bindings:
        return None
    return LetStarExpr(
        bindings=tuple(bindings),
        body=replace(
            expr,
            max_iterations_expr=max_expr,
            initial_state_expr=state_expr,
        ),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _elaborate_loop_recur_to_body(
    expr: LoopRecurExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    state_type = _infer_expr_type(
        expr.initial_state_expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    loop_scope = scope.child_scope("rec-join", authored_binding_name=expr.binding_name)
    loop_name = f"__wcc_loop_{expr.binding_name}_{loop_scope.scope_id.rsplit(':', 1)[-1]}"
    state_scope = loop_scope.child_scope("loop-state", authored_binding_name=expr.binding_name)
    budget_scope = loop_scope.child_scope("loop-budget", authored_binding_name=expr.binding_name)
    state_prefix, initial_state = _elaborate_expr_to_value(
        expr.initial_state_expr,
        scope=state_scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    budget_prefix, budget = _elaborate_expr_to_value(
        expr.max_iterations_expr,
        scope=budget_scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    loop_env = dict(value_env)
    loop_env[expr.binding_name] = state_type
    loop_bindings = compile_time_bindings
    exhaustion_bindings = compile_time_bindings
    command_context = compile_time_bindings.get(_COMMAND_SCOPE_CONTEXT)
    if command_context is not None:
        from ..closed.command_templates import binding_demand_key, command_loop_index_name, runtime_binding_value

        operand = WccNameAtom(metadata=loop_scope.atom_metadata(
            role=f"name:{expr.binding_name}", type_ref=state_type,
            source_span=expr.span, form_path=expr.form_path,
            binding_identity=expr.binding_identity), name=expr.binding_name)
        command_types = {**command_context.control.local_type_bindings, expr.binding_name: state_type}
        control = replace(command_context.control, local_type_bindings=command_types, iteration_scope=True)
        state_value = runtime_binding_value(state_type, facts=control, span=expr.span, form_path=expr.form_path)
        loop_context = replace(command_context, control=control, owner="loop",
            values={**command_context.values, expr.binding_name: state_value},
            operands={**command_context.operands, expr.binding_name: operand},
            retained_bindings=(*command_context.retained_bindings,
                (binding_demand_key(operand.metadata, loop_scope.enclosing_variants),
                    expr.binding_identity, state_type, state_value, operand)))
        if command_context.include_command_plans:
            index_operand = WccNameAtom(metadata=loop_scope.atom_metadata(
                role="command-loop-index", type_ref=PrimitiveTypeRef(name="Int"),
                source_span=expr.span, form_path=expr.form_path),
                name=command_loop_index_name(loop_name))
            loop_context = replace(loop_context, command_index=index_operand)
        loop_bindings = {**compile_time_bindings, _COMMAND_SCOPE_CONTEXT: loop_context}
        exhaustion_context = replace(loop_context, owner=command_context.owner,
            command_index=command_context.command_index,
            control=replace(control, iteration_scope=command_context.control.iteration_scope))
        exhaustion_bindings = {**compile_time_bindings, _COMMAND_SCOPE_CONTEXT: exhaustion_context}
    body = _retarget_loop_continue(
        _elaborate_expr_to_body(
            expr.body_expr,
            scope=loop_scope.child_scope("loop-body", authored_binding_name=expr.binding_name),
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=loop_bindings,
            active_phase_scope=active_phase_scope,
        ),
        loop_name=loop_name,
        through_joins=scope.closed_program,
    )
    exhaustion = None
    if expr.on_exhausted_result_expr is not None:
        exhaustion = _elaborate_expr_to_body(
            expr.on_exhausted_result_expr,
            scope=loop_scope.child_scope("loop-exhaustion", authored_binding_name=expr.binding_name),
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=exhaustion_bindings,
            active_phase_scope=active_phase_scope,
        )
    # The seed's and the budget's bindings run before the loop, whose body and
    # exhaustion result are the source scope of the loop binder only.
    prefix, (initial_state, budget) = hoist_parts_without_capture(
        ((state_prefix, initial_state, state_scope), (budget_prefix, budget, budget_scope)),
        over=((body, frozenset({expr.binding_name})), (exhaustion, frozenset({expr.binding_name}))),
        value_env=value_env,
        compile_time_bindings=compile_time_bindings,
    )
    rec_join = WccRecJoin(
        metadata=loop_scope.body_metadata(
            role=f"rec-join:{expr.binding_name}",
            type_ref=result_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
            binding_label=expr.binding_label,
            binding_identity=expr.binding_identity,
        ),
        loop_name=loop_name,
        params=(WccJoinParam(name=expr.binding_name, type_ref=state_type),),
        budget=budget,
        body=body,
        exhaustion=exhaustion,
        initial_state=initial_state,
        exhaustion_diagnostic_code=expr.exhaustion_diagnostic_code,
        single_iteration_effect_kinds=(
            expr.single_iteration_effect_kinds
        ),
        effect_cardinality_diagnostic_code=(
            expr.effect_cardinality_diagnostic_code
        ),
    )
    return _wrap_prefix_lets(prefix, rec_join)


def _retarget_loop_continue(
    body: WccBody,
    *,
    loop_name: str,
    through_joins: bool,
) -> WccBody:
    if isinstance(body, WccLoopContinue):
        return replace(body, target_name=loop_name)
    if isinstance(body, WccLet):
        return replace(
            body,
            body=_retarget_loop_continue(
                body.body,
                loop_name=loop_name,
                through_joins=through_joins,
            ),
        )
    if isinstance(body, WccCase):
        return replace(
            body,
            arms=tuple(
                WccCaseArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    binding_type_ref=arm.binding_type_ref,
                    body=_retarget_loop_continue(
                        arm.body,
                        loop_name=loop_name,
                        through_joins=through_joins,
                    ),
                    binding_label=arm.binding_label,
                    binding_identity=arm.binding_identity,
                    command_scope=arm.command_scope,
                )
                for arm in body.arms
            ),
        )
    if isinstance(body, WccIf):
        return replace(
            body,
            then_body=_retarget_loop_continue(
                body.then_body,
                loop_name=loop_name,
                through_joins=through_joins,
            ),
            else_body=_retarget_loop_continue(
                body.else_body,
                loop_name=loop_name,
                through_joins=through_joins,
            ),
        )
    if through_joins and isinstance(body, WccJoin):
        return replace(
            body,
            body=_retarget_loop_continue(
                body.body,
                loop_name=loop_name,
                through_joins=through_joins,
            ),
            continuation=_retarget_loop_continue(
                body.continuation,
                loop_name=loop_name,
                through_joins=through_joins,
            ),
        )
    return body


def _is_linear_value_body(body: WccBody) -> bool:
    current = body
    while isinstance(current, WccLet):
        current = current.body
    return isinstance(current, WccHalt)


def _elaborate_control_binding_to_body(
    *,
    binding_name: str,
    binding_type: TypeRef,
    binding_expr,
    binding_body: WccBody,
    continuation: WccBody,
    scope: WccIdentityFactory,
    effect_summary: EffectSummary,
    active_phase_scope: WccPhaseScope | None = None,
    binding_label: str | None = None,
    binding_identity: object | None = None,
) -> WccBody:
    join_name = _generated_join_name(scope, binding_name=binding_name)
    return WccJoin(
        metadata=scope.body_metadata(
            role=f"join:{binding_name}",
            type_ref=continuation.metadata.type_ref,
            source_span=binding_expr.span,
            form_path=binding_expr.form_path,
            expansion_stack=binding_expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
            binding_label=binding_label,
            binding_identity=binding_identity,
        ),
        join_name=join_name,
        params=(WccJoinParam(name=binding_name, type_ref=binding_type),),
        body=_replace_halts_with_jump(
            binding_body,
            join_name=join_name,
            result_type=binding_type,
            scope=scope.child_scope("jump", authored_binding_name=binding_name),
        ),
        continuation=continuation,
    )


@records_defect_provenance("elaboration")
def _elaborate_expr_to_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> tuple[tuple[WccLet, ...], WccValue]:
    if isinstance(expr, NameExpr) and expr.name in compile_time_bindings:
        from ..lowering.values import _resolve_inline_expr_value

        bound_value = compile_time_bindings[expr.name]
        if _is_compile_time_reference_value(bound_value):
            raise TypeError(
                "compile-time procedure/workflow references cannot "
                "materialize as WCC runtime values"
            )
        resolved = _resolve_inline_expr_value(
            expr,
            local_values=compile_time_bindings,
        )
        if (
            resolved is not None
            and resolved is not expr
            and hasattr(resolved, "span")
        ):
            return _elaborate_expr_to_value(
                resolved,
                scope=scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        if hasattr(bound_value, "span") and bound_value is not expr:
            return _elaborate_expr_to_value(
                bound_value,
                scope=scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
    if isinstance(expr, LiteralExpr):
        return (
            (),
            WccLiteralAtom(
                metadata=scope.atom_metadata(
                    role=f"literal:{expr.literal_kind}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=expr.value,
                literal_kind=expr.literal_kind,
            ),
        )
    if isinstance(expr, EnumMemberExpr):
        return (
            (),
            WccLiteralAtom(
                metadata=scope.atom_metadata(
                    role=f"literal:enum:{expr.enum_name}.{expr.member_name}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=expr.member_name,
                literal_kind="enum",
            ),
        )
    if isinstance(expr, UnionVariantTagExpr):
        return (
            (),
            WccOpaqueFrontendValue(
                metadata=scope.value_metadata(
                    role=f"variant-tag:{expr.variant_name}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr=expr,
            ),
        )
    if isinstance(expr, NameExpr):
        return (
            (),
            WccNameAtom(
                metadata=scope.atom_metadata(
                    role=f"name:{expr.name}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                name=expr.name,
            ),
        )
    if isinstance(expr, PhaseTargetExpr):
        if scope.closed_program:
            if active_phase_scope is None:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="phase_translation_body_invalid",
                            message="phase-target lowering requires an unambiguous phase context",
                            span=expr.span,
                            form_path=expr.form_path,
                        ),
                    )
                )
            context_expr = active_phase_scope.ctx_expr
            if not isinstance(context_expr, (NameExpr, FieldAccessExpr)):
                raise TypeError(
                    "closed-program phase target context was not normalized at with-phase"
                )
            context_type = _infer_expr_type(
                context_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=scope.closed_program,
            )
            phase_scope = build_phase_scope(
                context_type,
                phase_name=active_phase_scope.phase_name,
                type_env=type_env,
                span=active_phase_scope.source_span,
                form_path=active_phase_scope.form_path,
            )
            target_type = resolve_phase_target_type(
                phase_scope,
                expr.target_name,
                type_env=type_env,
                span=expr.span,
                form_path=expr.form_path,
            )
            context_prefix, context_value = _elaborate_expr_to_value(
                context_expr,
                scope=scope.child_scope("phase-target-context"),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=None,
            )
            if phase_scope.uses_legacy_bridge:
                target_field = IMPLEMENTATION_ATTEMPT_TARGET_FIELDS.get(
                    expr.target_name
                )
                if target_field is None:
                    # Preserve the canonical phase target diagnostic.
                    resolve_phase_target_type(
                        phase_scope,
                        expr.target_name,
                        type_env=type_env,
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                    raise TypeError("implementation phase target field was unavailable")
                if isinstance(context_value, WccFieldAccessAtom):
                    context_base = context_value.base
                    context_fields = context_value.fields
                elif isinstance(context_value, WccNameAtom):
                    context_base = context_value
                    context_fields = ()
                else:
                    raise TypeError(
                        "closed-program phase context did not elaborate to a name or field access"
                    )
                return (
                    context_prefix,
                    WccFieldAccessAtom(
                        metadata=scope.atom_metadata(
                            role=f"phase-target:{expr.target_name}",
                            type_ref=target_type,
                            source_span=expr.span,
                            form_path=expr.form_path,
                            expansion_stack=expr.expansion_stack,
                        ),
                        base=context_base,
                        fields=(*context_fields, target_field),
                    ),
                )

            target_spec = PHASE_TARGET_SPECS[expr.target_name]
            artifact_root_fields = (
                *(
                    context_expr.fields
                    if isinstance(context_expr, FieldAccessExpr)
                    else ()
                ),
                "artifact-root",
            )
            artifact_root_expr = FieldAccessExpr(
                base=(
                    context_expr.base
                    if isinstance(context_expr, FieldAccessExpr)
                    else context_expr
                ),
                fields=artifact_root_fields,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            artifact_prefix, artifact_root = _elaborate_expr_to_value(
                artifact_root_expr,
                scope=scope.child_scope("phase-target-artifact-root"),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            suffix = target_spec[2]
            path_literal = WccLiteralAtom(
                metadata=scope.atom_metadata(
                    role="phase-target:path-suffix",
                    type_ref=PrimitiveTypeRef(name="String"),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=f"{active_phase_scope.phase_name}/{suffix}",
                literal_kind="string",
            )
            return (
                (*context_prefix, *artifact_prefix),
                WccPureOp(
                    metadata=scope.value_metadata(
                        role=f"phase-target:{expr.target_name}",
                        type_ref=target_type,
                        source_span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                    operator="path/join",
                    args=(artifact_root, path_literal),
                    field_names=(),
                ),
            )
        return (
            (),
            WccPhaseTargetAtom(
                metadata=scope.atom_metadata(
                    role=f"phase-target:{expr.target_name}",
                    type_ref=PrimitiveTypeRef(name="String"),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                target_name=expr.target_name,
            ),
        )
    if isinstance(
        expr,
        (
            LoopStateSeedExpr,
            LoopStateUpdateExpr,
            GeneratedRelpathSeedExpr,
            CompilerListNonemptyHeadExpr,
            ListExpr,
            ListMapExpr,
            PathJoinUnderExpr,
            ProviderBundlePathExpr,
            ResourceTransitionExpr,
        ),
    ):
        return (
            (),
            WccOpaqueFrontendValue(
                metadata=scope.atom_metadata(
                    role=f"opaque:{type(expr).__name__}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr=expr,
            ),
        )
    if isinstance(expr, FieldAccessExpr):
        base_type = value_env[expr.base.name]
        return (
            (),
            WccFieldAccessAtom(
                metadata=scope.atom_metadata(
                    role=f"field:{'.'.join((expr.base.name, *expr.fields))}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                base=WccNameAtom(
                    metadata=scope.atom_metadata(
                        role=f"name:{expr.base.name}",
                        type_ref=base_type,
                        source_span=expr.base.span,
                        form_path=expr.base.form_path,
                        expansion_stack=expr.base.expansion_stack,
                    ),
                    name=expr.base.name,
                ),
                fields=expr.fields,
                shared_field_types=expr.shared_field_types,
            ),
        )
    if isinstance(expr, RecordExpr):
        record_type = _require_record_type(expr, type_env=type_env)
        prefix, field_values = _elaborate_operands_to_values(
            tuple(
                (field_expr, scope.child_scope("record-field", authored_binding_name=field_name))
                for field_name, field_expr in expr.fields
            ),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        fields = [(field_name, value) for (field_name, _), value in zip(expr.fields, field_values)]
        return (
            prefix,
            WccRecordAtom(
                metadata=scope.atom_metadata(
                    role=f"record:{expr.type_name}",
                    type_ref=record_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                type_name=expr.type_name,
                fields=tuple(fields),
                resolved_type=expr.resolved_type,
            ),
        )
    if isinstance(expr, PureOpExpr) and expr.operator in {"and", "or"}:
        if (
            scope.closed_program
            and target_dsl_supports_strict_boolean_control_flow(
                getattr(type_env, "target_dsl_version", "") or ""
            )
            and _contains_effect(expr)
        ):
            return _elaborate_if_to_value(
                fold_pure_short_circuit(expr),
                scope=scope.child_scope("short-circuit"),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        if (
            target_dsl_supports_strict_boolean_control_flow(
                getattr(type_env, "target_dsl_version", "") or ""
            )
            and not _contains_effect(expr)
        ):
            return _elaborate_if_to_value(
                fold_pure_short_circuit(expr),
                scope=scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
    if isinstance(expr, PureOpExpr):
        result_type = _infer_expr_type(
            expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
        prefix, args = _elaborate_operands_to_values(
            tuple(
                (arg_expr, scope.child_scope("pure-op-arg", authored_binding_name=str(index)))
                for index, arg_expr in enumerate(expr.args)
            ),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        return (
            prefix,
            WccPureOp(
                metadata=scope.value_metadata(
                    role=f"pure-op:{expr.operator}",
                    type_ref=result_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                operator=expr.operator,
                args=tuple(args),
            ),
        )
    if isinstance(expr, RecordUpdateExpr):
        result_type = _infer_expr_type(
            expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
        prefix, args = _elaborate_operands_to_values(
            (
                (expr.base_expr, scope.child_scope("record-update-base", authored_binding_name="base")),
                *(
                    (field_expr, scope.child_scope("record-update-field", authored_binding_name=field_name))
                    for field_name, field_expr in expr.overrides
                ),
            ),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        field_names = [field_name for field_name, _ in expr.overrides]
        return (
            prefix,
            WccPureOp(
                metadata=scope.value_metadata(
                    role="pure-op:record-update",
                    type_ref=result_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                operator="record-update",
                args=tuple(args),
                field_names=tuple(field_names),
            ),
        )
    if isinstance(expr, UnionVariantExpr):
        union_type = _require_union_type(expr, type_env=type_env)
        prefix, field_values = _elaborate_operands_to_values(
            tuple(
                (field_expr, scope.child_scope("union-field", authored_binding_name=field_name))
                for field_name, field_expr in expr.fields
            ),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        fields = [(field_name, value) for (field_name, _), value in zip(expr.fields, field_values)]
        return (
            prefix,
            WccInject(
                metadata=scope.value_metadata(
                    role=f"inject:{expr.variant_name}",
                    type_ref=union_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                union_name=expr.type_name,
                variant_name=expr.variant_name,
                fields=tuple(fields),
                resolved_type=expr.resolved_type,
            ),
        )
    if isinstance(expr, LetStarExpr):
        prefix, value = _body_to_prefix_and_value(
            _elaborate_let_star(
                expr,
                scope=scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        )
        return prefix, value
    if isinstance(expr, IfExpr):
        return _elaborate_if_to_value(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    raise TypeError(f"unsupported WCC elaboration node: {type(expr).__name__}")


def _elaborate_operands_to_values(
    operands: tuple[tuple[object, WccIdentityFactory], ...],
    *,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> tuple[tuple[WccLet, ...], tuple[WccValue, ...]]:
    """Elaborate sibling operands, each in its scope, to one joined prefix and their values in order.

    Every operand's bindings run before all the values; a binding that a later
    operand or an earlier value can see is renamed (`hoist_parts_without_capture`),
    at every target.
    """

    parts = tuple(
        (
            *_body_to_prefix_and_value(
                _elaborate_expr_to_body(
                    operand,
                    scope=operand_scope,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
            ),
            operand_scope,
        )
        for operand, operand_scope in operands
    )
    return hoist_parts_without_capture(parts, value_env=value_env, compile_time_bindings=compile_time_bindings)


def _elaborate_if_to_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> tuple[tuple[WccLet, ...], WccValue]:
    """Elaborate one effect-free `IfExpr` in value position.

    Below target 2.26 a pure conditional value stays an opaque frontend value
    (preserving the legacy closed-member handling). At 2.26 it becomes an
    internal `WccSelect` whose three children are ordinary `WccValue` terms so
    the dependency/scope/substitution walks can recurse through them.
    """

    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    if not target_dsl_supports_strict_boolean_control_flow(
        getattr(type_env, "target_dsl_version", "") or ""
    ):
        return (
            (),
            WccOpaqueFrontendValue(
                metadata=scope.value_metadata(
                    role="opaque:IfExpr",
                    type_ref=result_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr=expr,
            ),
        )
    condition_scope = scope.child_scope("select-condition")
    if (
        scope.closed_program
        and _contains_effect(expr.condition_expr)
        and not isinstance(expr.condition_expr, IfExpr)
    ):
        condition_prefix, condition = _body_to_prefix_and_value(
            _elaborate_expr_to_body(
                expr.condition_expr,
                scope=condition_scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        )
    else:
        condition_prefix, condition = _elaborate_expr_to_value(
            expr.condition_expr,
            scope=condition_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    _, then_value_env = _branch_proof_narrowing(
        expr.true_proof_context,
        type_env=type_env,
        value_env=value_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    _, else_value_env = _branch_proof_narrowing(
        expr.false_proof_context,
        type_env=type_env,
        value_env=value_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    def elaborate_arm(arm_expr, *, arm_scope, arm_value_env):
        arm_bindings = _command_narrowed_bindings(compile_time_bindings, arm_value_env)
        if (
            scope.closed_program
            and _contains_effect(arm_expr)
            and not isinstance(arm_expr, IfExpr)
        ):
            return _body_to_prefix_and_value(
                _elaborate_expr_to_body(
                    arm_expr,
                    scope=arm_scope,
                    type_env=type_env,
                    value_env=arm_value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=arm_bindings,
                    active_phase_scope=active_phase_scope,
                )
            )
        return _elaborate_expr_to_value(
            arm_expr,
            scope=arm_scope,
            type_env=type_env,
            value_env=arm_value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=arm_bindings,
            active_phase_scope=active_phase_scope,
        )

    then_prefix, then_value = elaborate_arm(
        expr.then_expr,
        arm_scope=scope.child_scope("select-then"),
        arm_value_env=then_value_env,
    )
    else_prefix, else_value = elaborate_arm(
        expr.else_expr,
        arm_scope=scope.child_scope("select-else"),
        arm_value_env=else_value_env,
    )
    then_arm = WccSelectArm(prefix=then_prefix, value=then_value)
    else_arm = WccSelectArm(prefix=else_prefix, value=else_value)
    if scope.closed_program:
        condition_prefix, condition = hoist_without_capture(
            condition_prefix,
            condition,
            over=((then_arm, frozenset()), (else_arm, frozenset())),
            scope=condition_scope,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
    return (
        condition_prefix,
        WccSelect(
            metadata=scope.value_metadata(
                role="select",
                type_ref=result_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            condition=condition,
            then_arm=then_arm,
            else_arm=else_arm,
        ),
    )


def _elaborate_constructor_field_matches_to_body(
    expr: RecordExpr | UnionVariantExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    wrappers: list[object] = []
    field_values: list[tuple[str, WccValue]] = []
    generated_env: dict[str, TypeRef] = {}

    for field_name, field_expr in expr.fields:
        if isinstance(field_expr, MatchExpr):
            binding_scope = scope.child_scope("constructor-field-match", authored_binding_name=field_name)
            binding_name = _generated_value_binding_name_from_scope(binding_scope, role=field_name)
            binding_type = _infer_expr_type(
                field_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=scope.closed_program,
            )
            generated_env[binding_name] = binding_type
            field_values.append(
                (
                    field_name,
                    WccNameAtom(
                        metadata=binding_scope.atom_metadata(
                            role=f"name:{binding_name}",
                            type_ref=binding_type,
                            source_span=field_expr.span,
                            form_path=field_expr.form_path,
                            expansion_stack=field_expr.expansion_stack,
                        ),
                        name=binding_name,
                    ),
                )
            )
            wrappers.append(("match", binding_name, binding_type, field_expr, binding_scope))
            continue

        field_body = _elaborate_expr_to_body(
            field_expr,
            scope=scope.child_scope("constructor-field", authored_binding_name=field_name),
            type_env=type_env,
            value_env={**value_env, **generated_env},
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        field_prefix, field_value = _body_to_prefix_and_value(field_body)
        wrappers.append(("prefix", field_prefix))
        field_values.append((field_name, field_value))

    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env={**value_env, **generated_env},
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    if isinstance(expr, RecordExpr):
        result_value: WccValue = WccRecordAtom(
            metadata=scope.atom_metadata(
                role=f"record:{expr.type_name}",
                type_ref=result_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            type_name=expr.type_name,
            fields=tuple(field_values),
            resolved_type=expr.resolved_type,
        )
    else:
        result_value = WccInject(
            metadata=scope.value_metadata(
                role=f"inject:{expr.variant_name}",
                type_ref=result_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            union_name=expr.type_name,
            variant_name=expr.variant_name,
            fields=tuple(field_values),
            resolved_type=expr.resolved_type,
        )

    current: WccBody = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=result_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=result_value,
    )
    for wrapper in reversed(wrappers):
        if wrapper[0] == "prefix":
            current = _wrap_prefix_lets(wrapper[1], current)
            continue
        _, binding_name, binding_type, match_expr, binding_scope = wrapper
        current = _elaborate_non_tail_match_binding(
            binding_name=binding_name,
            binding_type=binding_type,
            match_expr=match_expr,
            continuation=current,
            scope=binding_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    return current


def _elaborate_match_to_body(
    expr: MatchExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    subject_type = _infer_expr_type(
        expr.subject,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    if isinstance(
        expr.subject,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RequestInputExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            FinalizeSelectedItemExpr,
            CallExpr,
            ProcedureCallExpr,
        ),
    ):
        subject_binding_scope = scope.child_scope("match-subject-effect", authored_binding_name="subject")
        subject_binding_name = _generated_effect_binding_name_from_scope(
            subject_binding_scope,
            role="subject",
        )
        subject_atom = WccNameAtom(
            metadata=subject_binding_scope.atom_metadata(
                role=f"name:{subject_binding_name}",
                type_ref=subject_type,
                source_span=expr.subject.span,
                form_path=expr.subject.form_path,
                expansion_stack=expr.subject.expansion_stack,
            ),
            name=subject_binding_name,
        )
        case_body = _elaborate_match_case_with_subject(
            expr,
            subject=subject_atom,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        return _elaborate_effect_binding_to_body(
            binding_name=subject_binding_name,
            binding_type=subject_type,
            binding_expr=expr.subject,
            continuation=case_body,
            let_result_type=case_body.metadata.type_ref,
            scope=subject_binding_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    subject_scope = scope.child_scope("match-subject", authored_binding_name="subject")
    subject_prefix, subject = _elaborate_expr_to_value(
        expr.subject,
        scope=subject_scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    # From target 2.33 the subject's bindings run before the case, as `let*` would,
    # under names the arms cannot see.
    if subject_prefix and not (_at_2_33(type_env) or scope.closed_program):
        raise TypeError(f"unsupported nested WCC M2 prefix for `{type(expr.subject).__name__}`")
    subject_prefix, subject = hoist_without_capture(
        subject_prefix,
        subject,
        over=tuple((arm.body, frozenset({arm.binding_name})) for arm in expr.arms),
        scope=subject_scope,
        value_env=value_env,
        compile_time_bindings=compile_time_bindings,
    )
    case_body = _elaborate_match_case_with_subject(
        expr,
        subject=subject,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return _wrap_prefix_lets(subject_prefix, case_body)


def _elaborate_match_case_with_subject(
    expr: MatchExpr,
    *,
    subject: WccValue,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccCase:
    return WccCase(
        metadata=scope.body_metadata(
            role="case:match",
            type_ref=_infer_expr_type(
                expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=scope.closed_program,
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        subject=subject,
        arms=tuple(
            _elaborate_case_arm(
                expr,
                arm,
                scope=replace(
                    scope.child_scope("match-arm", authored_binding_name=arm.binding_name),
                    enclosing_variants=(*scope.enclosing_variants, arm.variant_name),
                ),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            for arm in expr.arms
        ),
    )


def _elaborate_if_to_body(
    expr: IfExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    condition_scope = scope.child_scope("if-condition")
    condition_control_body = None
    condition_binding_name = None
    condition_source_expr = expr.condition_expr
    if (
        scope.closed_program
        and _contains_effect(expr.condition_expr)
    ):
        condition_control_body = _elaborate_expr_to_body(
            expr.condition_expr,
            scope=condition_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        if _is_linear_value_body(condition_control_body):
            condition_prefix, condition = _body_to_prefix_and_value(
                condition_control_body
            )
            condition_control_body = None
            from .defunctionalize import _frontend_expr_from_wcc_value

            condition_source_expr = _frontend_expr_from_wcc_value(condition)
        else:
            condition_prefix = ()
            condition_binding_name = fresh_name(
                _generated_value_binding_name_from_scope(
                    condition_scope,
                    role="condition",
                ),
                reserved_identifiers(
                    expr,
                    value_env=value_env,
                    compile_time_bindings=compile_time_bindings,
                ),
            )
            condition = WccNameAtom(
                metadata=condition_scope.atom_metadata(
                    role=f"name:{condition_binding_name}",
                    type_ref=PrimitiveTypeRef(name="Bool"),
                    source_span=expr.condition_expr.span,
                    form_path=expr.condition_expr.form_path,
                    expansion_stack=expr.condition_expr.expansion_stack,
                ),
                name=condition_binding_name,
            )
    else:
        condition_prefix, condition = _elaborate_expr_to_value(
            expr.condition_expr,
            scope=condition_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    condition_shape = classify_condition_expr(
        (
            NameExpr(
                name=condition_binding_name,
                span=expr.condition_expr.span,
                form_path=expr.condition_expr.form_path,
                expansion_stack=expr.condition_expr.expansion_stack,
            )
            if condition_binding_name is not None
            else condition_source_expr
        ),
        type_ref=PrimitiveTypeRef(name="Bool"),
        allow_pure_projection=True,
    )
    then_proof, then_value_env = _branch_proof_narrowing(
        expr.true_proof_context,
        type_env=type_env,
        value_env=value_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    else_proof, else_value_env = _branch_proof_narrowing(
        expr.false_proof_context,
        type_env=type_env,
        value_env=value_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    if_body = WccIf(
        metadata=scope.body_metadata(
            role="if",
            type_ref=result_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        condition=condition,
        condition_shape=condition_shape,
        then_body=_elaborate_expr_to_body(
            expr.then_expr,
            scope=scope.child_scope("if-then"),
            type_env=type_env,
            value_env=then_value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=_command_narrowed_bindings(compile_time_bindings, then_value_env),
            active_phase_scope=active_phase_scope,
        ),
        else_body=_elaborate_expr_to_body(
            expr.else_expr,
            scope=scope.child_scope("if-else"),
            type_env=type_env,
            value_env=else_value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=_command_narrowed_bindings(compile_time_bindings, else_value_env),
            active_phase_scope=active_phase_scope,
        ),
        then_proof_context=then_proof,
        else_proof_context=else_proof,
    )
    if condition_control_body is not None:
        return _elaborate_control_binding_to_body(
            binding_name=condition_binding_name,
            binding_type=PrimitiveTypeRef(name="Bool"),
            binding_expr=expr.condition_expr,
            binding_body=condition_control_body,
            continuation=if_body,
            scope=condition_scope,
            effect_summary=effect_summary,
            active_phase_scope=active_phase_scope,
        )
    if scope.closed_program and condition_prefix:
        condition_prefix, condition = hoist_without_capture(
            condition_prefix,
            condition,
            over=(
                (if_body.then_body, frozenset()),
                (if_body.else_body, frozenset()),
            ),
            scope=condition_scope,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
        if condition_binding_name is None:
            from .defunctionalize import _frontend_expr_from_wcc_value

            condition_source_expr = _frontend_expr_from_wcc_value(condition)
            condition_shape = classify_condition_expr(
                condition_source_expr,
                type_ref=PrimitiveTypeRef(name="Bool"),
                allow_pure_projection=True,
            )
        if_body = replace(
            if_body,
            condition=condition,
            condition_shape=condition_shape,
        )
    return _wrap_prefix_lets(condition_prefix, if_body)


def _branch_proof_narrowing(
    proof_context,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    span,
    form_path: tuple[str, ...],
) -> tuple[tuple[tuple[str, str, str], ...], Mapping[str, TypeRef]]:
    """Convert branch proof facts to WCC triples and narrow ``value_env``."""
    if not proof_context:
        return (), value_env
    triples: list[tuple[str, str, str]] = []
    narrowed = dict(value_env)
    for identity, possible in proof_context.items():
        variants = getattr(possible, "variants", ())
        if len(variants) != 1:
            continue
        variant_name = next(iter(variants))
        binding_name = getattr(identity, "name", "")
        union_name = getattr(possible, "union_name", "")
        if not binding_name:
            continue
        current = narrowed.get(binding_name)
        if not isinstance(current, UnionTypeRef) or current.name != union_name:
            # The fact belongs to a shadowed outer binding identity; the
            # binding now in scope is a different union. Applying it would
            # either raise ``union_variant_unknown`` or silently narrow the
            # wrong union, so emit no guard/descriptor triple for it.
            continue
        triples.append((binding_name, union_name, variant_name))
        narrowed[binding_name] = type_env.union_variant(
            current,
            variant_name,
            span=span,
            form_path=form_path,
        )
    return tuple(triples), narrowed


def _elaborate_case_arm(
    match_expr: MatchExpr,
    arm,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccCaseArm:
    subject_type = _infer_expr_type(
        match_expr.subject,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    if not isinstance(subject_type, UnionTypeRef):
        raise TypeError("match subject must elaborate from a union type")
    binding_type_ref = type_env.union_variant(
        subject_type,
        arm.variant_name,
        span=arm.span,
        form_path=arm.form_path,
        expansion_stack=arm.expansion_stack,
    )
    arm_env = dict(value_env)
    arm_env[arm.binding_name] = binding_type_ref
    command_scope = None
    command_context = compile_time_bindings.get(_COMMAND_SCOPE_CONTEXT)
    if command_context is not None:
        operand = WccNameAtom(metadata=scope.atom_metadata(
            role=f"name:{arm.binding_name}", type_ref=binding_type_ref,
            source_span=arm.span, form_path=arm.form_path,
            binding_identity=arm.binding_identity), name=arm.binding_name)
        command_scope, child_context = command_context.arm(
            arm.body, result_type=_infer_expr_type(match_expr, type_env=type_env,
                value_env=value_env, workflow_return_types=workflow_return_types,
                    closed_program=scope.closed_program,
                procedure_return_types=procedure_return_types),
            name=arm.binding_name, type_ref=binding_type_ref, operand=operand, value_env=arm_env)
        compile_time_bindings = {**compile_time_bindings, _COMMAND_SCOPE_CONTEXT: child_context}
    return WccCaseArm(
        variant_name=arm.variant_name,
        binding_name=arm.binding_name,
        binding_type_ref=binding_type_ref,
        binding_label=arm.binding_label,
        binding_identity=arm.binding_identity,
        command_scope=command_scope,
        body=_elaborate_expr_to_body(
            arm.body,
            scope=scope,
            type_env=type_env,
            value_env=arm_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
    )


def _surface_value_match_bindings(bindings):
    context = bindings.get(_COMMAND_SCOPE_CONTEXT)
    if context is not None and context.owner == "loop":
        return {**bindings, _COMMAND_SCOPE_CONTEXT: replace(context, owner="surface")}
    return bindings


def _elaborate_non_tail_match_binding(
    *,
    binding_name: str,
    binding_type: TypeRef,
    match_expr: MatchExpr,
    binding_label: str | None = None,
    binding_identity: object | None = None,
    continuation: WccBody,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
    case_body: WccBody | None = None,
) -> WccBody:
    compile_time_bindings = _surface_value_match_bindings(compile_time_bindings)
    join_name = _generated_join_name(scope, binding_name=binding_name)
    case_body = case_body if case_body is not None else _elaborate_match_to_body(
        match_expr,
        scope=scope.child_scope("case", authored_binding_name=binding_name),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return WccJoin(
        metadata=scope.body_metadata(
            role=f"join:{binding_name}",
            type_ref=continuation.metadata.type_ref,
            source_span=match_expr.span,
            form_path=match_expr.form_path,
            expansion_stack=match_expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
            binding_label=binding_label,
            binding_identity=binding_identity,
        ),
        join_name=join_name,
        params=(WccJoinParam(name=binding_name, type_ref=binding_type),),
        body=_replace_halts_with_jump(
            case_body,
            join_name=join_name,
            result_type=binding_type,
            scope=scope.child_scope("jump", authored_binding_name=binding_name),
        ),
        continuation=continuation,
    )


def _replace_halts_with_jump(
    body: WccBody,
    *,
    join_name: str,
    result_type: TypeRef,
    scope: WccIdentityFactory,
) -> WccBody:
    if isinstance(body, WccLet):
        return replace(
            body,
            body=_replace_halts_with_jump(
                body.body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("let-tail", authored_binding_name=body.bound_name),
            ),
        )
    if isinstance(body, WccCase):
        return replace(
            body,
            arms=tuple(
                replace(
                    arm,
                    body=_replace_halts_with_jump(
                        arm.body,
                        join_name=join_name,
                        result_type=result_type,
                        scope=scope.child_scope("arm-tail", authored_binding_name=arm.binding_name),
                    ),
                )
                for arm in body.arms
            ),
        )
    if isinstance(body, WccIf):
        return replace(
            body,
            then_body=_replace_halts_with_jump(
                body.then_body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("if-then"),
            ),
            else_body=_replace_halts_with_jump(
                body.else_body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("if-else"),
            ),
        )
    if isinstance(body, WccJoin):
        return replace(
            body,
            body=_replace_halts_with_jump(
                body.body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("join-body", authored_binding_name=body.join_name),
            ),
            continuation=_replace_halts_with_jump(
                body.continuation,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("join-cont", authored_binding_name=body.join_name),
            ),
        )
    if isinstance(body, WccRecJoin):
        return body
    if isinstance(body, WccHalt):
        return WccJump(
            metadata=scope.body_metadata(
                role=f"jump:{join_name}",
                type_ref=result_type,
                source_span=body.metadata.source_span,
                form_path=body.metadata.form_path,
                expansion_stack=body.metadata.expansion_stack,
                effect_summary=body.metadata.effect_summary,
                proof_context=body.metadata.proof_context,
                allocation_requests=body.metadata.allocation_requests,
                phase_scope=body.metadata.phase_scope,
            ),
            join_name=join_name,
            args=(body.result,),
        )
    if isinstance(body, WccJump):
        return body
    raise TypeError(f"unsupported WCC control rewrite node: {type(body).__name__}")


def _elaborate_effect_expr_to_body(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    binding_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        closed_program=scope.closed_program,
    )
    binding_name = _generated_effect_binding_name_from_scope(scope, role="result")
    halt = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=binding_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=WccNameAtom(
            metadata=scope.atom_metadata(
                role=f"name:{binding_name}",
                type_ref=binding_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            name=binding_name,
        ),
    )
    return _elaborate_effect_binding_to_body(
        binding_name=binding_name,
        binding_type=binding_type,
        binding_expr=expr,
        continuation=halt,
        let_result_type=binding_type,
        scope=scope.child_scope("effect", authored_binding_name="result"),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )


def _prepare_effect_argument_bodies(match_bindings, *, scope, compile_time_bindings, **inputs):
    """Prepare the real argument owners before their effect continuation."""
    prepared = []
    bindings = compile_time_bindings
    for name, type_ref, expr in match_bindings:
        is_match = isinstance(expr, MatchExpr)
        owner_scope = scope.child_scope("effect-arg-match" if is_match else "effect-arg-value",
            authored_binding_name=name)
        body_scope = owner_scope.child_scope("case", authored_binding_name=name) if is_match else owner_scope
        body_bindings = _surface_value_match_bindings(bindings) if is_match else bindings
        body = _elaborate_expr_to_body(expr, scope=body_scope,
            compile_time_bindings=body_bindings, **inputs)
        prepared.append((name, type_ref, expr, body))
        role = "join" if is_match or not _is_linear_value_body(body) else "let"
        metadata = owner_scope.body_metadata(role=f"{role}:{name}", type_ref=type_ref,
            source_span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
        bindings = _command_bound_bindings(bindings, expr=expr, name=name,
            type_ref=type_ref, scope=owner_scope, metadata=metadata)
    return tuple(prepared), bindings


def _elaborate_effect_binding_to_body(
    *,
    binding_name: str,
    binding_type: TypeRef,
    binding_expr,
    binding_label: str | None = None,
    binding_identity: object | None = None,
    continuation: WccBody,
    let_result_type: TypeRef,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    normalized_expr, match_bindings = _prebind_effect_argument_matches(
        binding_expr,
        scope=scope.child_scope("effect-args", authored_binding_name=binding_name),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    matched_value_env = {
        **value_env,
        **{name: type_ref for name, type_ref, _ in match_bindings},
    }
    normalized_expr, direct_bound_proc_args = (
        _prebind_direct_bind_proc_arguments(
            normalized_expr,
            scope=scope.child_scope(
                "effect-proc-args",
                authored_binding_name=binding_name,
            ),
            type_env=type_env,
            value_env=(matched_value_env if scope.closed_program else value_env),
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            compile_time_bindings=compile_time_bindings,
        )
    )
    binding_value_env = {
        **matched_value_env,
        **{
            item.binding_name: item.type_ref
            for item in direct_bound_proc_args
        },
    }
    binding_compile_time_bindings = {
        **compile_time_bindings,
        **{
            item.binding_name: item.compile_time_value
            for item in direct_bound_proc_args
        },
    }
    prepared_arguments, argument_bindings = _prepare_effect_argument_bodies(
        match_bindings, scope=scope, compile_time_bindings=compile_time_bindings,
        type_env=type_env, value_env=value_env, workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types, effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site, active_phase_scope=active_phase_scope)
    command_context = argument_bindings.get(_COMMAND_SCOPE_CONTEXT)
    if command_context is not None:
        binding_compile_time_bindings = {**binding_compile_time_bindings,
            _COMMAND_SCOPE_CONTEXT: command_context}
    current: WccBody = WccLet(
        metadata=scope.body_metadata(
            role=f"let:{binding_name}",
            type_ref=let_result_type,
            source_span=binding_expr.span,
            form_path=binding_expr.form_path,
            expansion_stack=binding_expr.expansion_stack,
            binding_label=binding_label,
            binding_identity=binding_identity,
        ),
        bound_name=binding_name,
        bound_type_ref=binding_type,
        bound_value=_elaborate_effect_expr_to_binding_value(
            normalized_expr,
            scope=scope.child_scope("binding", authored_binding_name=binding_name),
            type_env=type_env,
            value_env=binding_value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=binding_compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
        body=continuation,
    )
    if scope.closed_program:
        for item in reversed(direct_bound_proc_args):
            current = _wrap_bind_proc_capture_aliases(
                item.capture_aliases,
                tail=current,
                result_type=let_result_type,
            )
    for arg_name, arg_type, prebound_expr, prebound_body in reversed(prepared_arguments):
        if isinstance(prebound_expr, MatchExpr):
            current = _elaborate_non_tail_match_binding(
                binding_name=arg_name,
                binding_type=arg_type,
                match_expr=prebound_expr,
                continuation=current,
                scope=scope.child_scope("effect-arg-match", authored_binding_name=arg_name),
                case_body=prebound_body,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            continue
        prebound_scope = scope.child_scope("effect-arg-value", authored_binding_name=arg_name)
        if scope.closed_program and not _is_linear_value_body(prebound_body):
            current = _elaborate_control_binding_to_body(
                binding_name=arg_name,
                binding_type=arg_type,
                binding_expr=prebound_expr,
                binding_body=prebound_body,
                continuation=current,
                scope=prebound_scope,
                effect_summary=effect_summary,
                active_phase_scope=active_phase_scope,
            )
            continue
        prebound_prefix, prebound_value = _body_to_prefix_and_value(prebound_body)
        # The argument's bindings run before the later arguments, the call and its continuation.
        prebound_prefix, prebound_value = hoist_without_capture(
            prebound_prefix,
            prebound_value,
            over=((current, frozenset({arg_name})),),
            scope=prebound_scope,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
        current = WccLet(
            metadata=prebound_scope.body_metadata(
                role=f"let:{arg_name}",
                type_ref=arg_type,
                source_span=prebound_expr.span,
                form_path=prebound_expr.form_path,
                expansion_stack=prebound_expr.expansion_stack,
            ),
            bound_name=arg_name,
            bound_type_ref=arg_type,
            bound_value=prebound_value,
            body=current,
        )
        for prefix_let in reversed(prebound_prefix):
            current = replace(prefix_let, body=current)
    if not scope.closed_program:
        for item in reversed(direct_bound_proc_args):
            current = _wrap_bind_proc_capture_aliases(
                item.capture_aliases,
                tail=current,
                result_type=let_result_type,
            )
    return current


def _prebind_direct_bind_proc_arguments(
    expr: object,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[str, object],
) -> tuple[object, tuple[_WccDirectBoundProcedureArgument, ...]]:
    if (
        not isinstance(expr, ProcedureCallExpr)
        or not compile_time_bindings.get(
            _PRESERVE_BOUND_PROC_CAPTURES,
            False,
        )
    ):
        return expr, ()

    direct_args: list[_WccDirectBoundProcedureArgument] = []
    rewritten_args: list[object] = []
    for index, arg_expr in enumerate(expr.args):
        if not isinstance(arg_expr, BindProcExpr):
            rewritten_args.append(arg_expr)
            continue
        type_ref = _infer_expr_type(
            arg_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
        arg_scope = scope.child_scope(
            "direct-bind-proc",
            authored_binding_name=str(index),
        )
        binding_name = _generated_value_binding_name_from_scope(
            arg_scope,
            role=f"direct-bind-proc:{index}",
        )
        capture_aliases = _materialize_bind_proc_capture_aliases(
            arg_expr,
            owner_role=f"argument:{index}",
            scope=arg_scope,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
        direct_args.append(
            _WccDirectBoundProcedureArgument(
                binding_name=binding_name,
                type_ref=type_ref,
                compile_time_value=_WccBoundProcedureBinding(
                    capture_values=(
                        *_inherited_bind_proc_capture_values(
                            arg_expr,
                            compile_time_bindings=compile_time_bindings,
                        ),
                        *(
                            (
                                capture.source_name,
                                capture.alias_atom,
                                arg_expr,
                            )
                            for capture in capture_aliases
                        ),
                    ),
                    source_binding=arg_expr,
                ),
                capture_aliases=capture_aliases,
            )
        )
        rewritten_args.append(
            NameExpr(
                name=binding_name,
                span=arg_expr.span,
                form_path=arg_expr.form_path,
                expansion_stack=arg_expr.expansion_stack,
            )
        )
    if not direct_args:
        return expr, ()
    return (
        replace(expr, args=tuple(rewritten_args)),
        tuple(direct_args),
    )


def _prebind_effect_argument_matches(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
) -> tuple[object, tuple[tuple[str, TypeRef, object], ...]]:
    match_bindings: list[tuple[str, TypeRef, object]] = []
    if (
        scope.closed_program
        and isinstance(expr, ProcedureCallExpr)
        and any(
            isinstance(argument, BindProcExpr) and _contains_effect(argument)
            for argument in expr.args
        )
    ):
        from ..conditionals import _normalize_composite

        prefix, expr = _normalize_composite(
            expr,
            path=(),
            closed_program=True,
        )
        for name, value in prefix:
            match_bindings.append(
                (
                    name,
                    _infer_expr_type(
                        value,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    value,
                )
            )

    def replace_arg(
        arg_expr,
        *,
        role: str,
        prebind_pure_projection: bool = False,
        force_prebind: bool = False,
    ):
        if force_prebind and isinstance(
            arg_expr,
            (LiteralExpr, NameExpr, FieldAccessExpr),
        ):
            return arg_expr
        materialize_flattened_record = (
            prebind_pure_projection
            and (
                isinstance(arg_expr, NameExpr)
                and isinstance(value_env.get(arg_expr.name), RecordTypeRef)
                or isinstance(arg_expr, FieldAccessExpr)
                and isinstance(
                    _infer_expr_type(
                        arg_expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        closed_program=scope.closed_program,
                    ),
                    RecordTypeRef,
                )
            )
        )
        if (
            not force_prebind
            and not (scope.closed_program and _contains_effect(arg_expr))
            and not isinstance(arg_expr, (MatchExpr, LetStarExpr))
            and not (
            prebind_pure_projection
            and (materialize_flattened_record or not isinstance(arg_expr, (NameExpr, FieldAccessExpr)))
            and is_pure_projection_expr(arg_expr)
            )
        ):
            return arg_expr
        binding_type = _infer_expr_type(
            arg_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
        binding_name = _generated_effect_binding_name_from_scope(scope, role=role)
        match_bindings.append((binding_name, binding_type, arg_expr))
        return NameExpr(
            name=binding_name,
            span=arg_expr.span,
            form_path=arg_expr.form_path,
            expansion_stack=arg_expr.expansion_stack,
        )

    if isinstance(expr, ProviderResultExpr):
        prompt_dependencies = expr.prompt_dependencies
        if prompt_dependencies is not None:
            prompt_dependencies = replace(
                prompt_dependencies,
                required=tuple(
                    replace_arg(item, role=f"prompt-dependency:required:{index}")
                    for index, item in enumerate(prompt_dependencies.required)
                ),
                optional=tuple(
                    replace_arg(item, role=f"prompt-dependency:optional:{index}")
                    for index, item in enumerate(prompt_dependencies.optional)
                ),
            )
        return (
            replace(
                expr,
                inputs=tuple(
                    replace_arg(input_expr, role=f"provider-input:{index}")
                    for index, input_expr in enumerate(expr.inputs)
                ),
                prompt_dependencies=prompt_dependencies,
                context_expr=(
                    replace_arg(
                        expr.context_expr,
                        role="provider-context",
                        prebind_pure_projection=True,
                    )
                    if expr.context_expr is not None
                    else None
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, CommandResultExpr):
        return (
            replace(
                expr,
                argv=tuple(
                    replace_arg(arg_expr, role=f"command-arg:{index}")
                    for index, arg_expr in enumerate(expr.argv)
                ),
                adapter_inputs=(
                    tuple(
                        (
                            input_name,
                            replace_arg(
                                input_expr,
                                role=f"command-adapter-input:{input_name}",
                            ),
                        )
                        for input_name, input_expr in expr.adapter_inputs
                    )
                    if scope.closed_program
                    else expr.adapter_inputs
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, RequestInputExpr):
        return (
            replace(
                expr,
                question=replace_arg(
                    expr.question,
                    role="request-input:question",
                    prebind_pure_projection=True,
                    force_prebind=True,
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, RunRefExpr):
        return (
            replace(
                expr,
                inputs=tuple(
                    (
                        input_name,
                        replace_arg(
                            input_expr,
                            role=f"run-ref-input:{input_name}",
                        ),
                    )
                    for input_name, input_expr in expr.inputs
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, TrialExpr):
        return (
            replace(
                expr,
                arms=tuple(
                    replace(
                        arm,
                        run_ref=replace(
                            arm.run_ref,
                            inputs=tuple(
                                (
                                    input_name,
                                    replace_arg(
                                        input_expr,
                                        role=(
                                            f"trial-arm:{arm_index}:"
                                            f"run-ref-input:{input_name}"
                                        ),
                                    ),
                                )
                                for input_name, input_expr in arm.run_ref.inputs
                            ),
                        ),
                    )
                    for arm_index, arm in enumerate(expr.arms)
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, RunProviderPhaseExpr):
        return (
            replace(
                expr,
                ctx_expr=replace_arg(expr.ctx_expr, role="run-provider-phase:ctx"),
                inputs_expr=replace_arg(expr.inputs_expr, role="run-provider-phase:inputs"),
                provider=replace_arg(expr.provider, role="run-provider-phase:provider"),
                prompt=replace_arg(expr.prompt, role="run-provider-phase:prompt"),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, ProduceOneOfExpr):
        producer = replace(
            expr.producer,
            provider_expr=(
                replace_arg(expr.producer.provider_expr, role="produce-one-of:provider")
                if expr.producer.provider_expr is not None
                else None
            ),
            prompt_expr=(
                replace_arg(expr.producer.prompt_expr, role="produce-one-of:prompt")
                if expr.producer.prompt_expr is not None
                else None
            ),
            inputs=tuple(
                replace_arg(input_expr, role=f"produce-one-of:input:{index}")
                for index, input_expr in enumerate(expr.producer.inputs)
            ),
        )
        candidates = tuple(
            replace(
                candidate,
                fields=tuple(
                    replace(
                        field,
                        target_expr=(
                            replace_arg(field.target_expr, role=f"produce-one-of:{candidate.variant_name}:{field.field_name}")
                            if field.target_expr is not None
                            else None
                        ),
                    )
                    for field in candidate.fields
                ),
            )
            for candidate in expr.candidates
        )
        return (
            replace(expr, ctx_expr=replace_arg(expr.ctx_expr, role="produce-one-of:ctx"), producer=producer, candidates=candidates),
            tuple(match_bindings),
        )
    if isinstance(expr, CallExpr):
        return (
            replace(
                expr,
                bindings=tuple(
                    (binding_name, replace_arg(binding_expr, role=f"workflow-binding:{binding_name}"))
                    for binding_name, binding_expr in expr.bindings
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, ProcedureCallExpr):
        return (
            replace(
                expr,
                args=tuple(
                    replace_arg(arg_expr, role=f"procedure-arg:{index}")
                    for index, arg_expr in enumerate(expr.args)
                ),
            ),
            tuple(match_bindings),
        )
    return expr, ()


def _elaborate_live_provider_supervision(
    expr: WithLiveProvidersExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None,
) -> WccProviderSupervision:
    member_types = {
        binding.name: _infer_expr_type(
            binding.value_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
        for binding in expr.bindings
    }
    members = tuple(
        WccProviderSupervisionMember(
            metadata=scope.value_metadata(
                role=f"provider-supervision:member:{binding.name}",
                type_ref=member_types[binding.name],
                source_span=binding.value_expr.span,
                form_path=binding.value_expr.form_path,
                expansion_stack=binding.value_expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            binding_metadata=scope.value_metadata(
                role=f"provider-supervision:binding:{binding.name}",
                type_ref=member_types[binding.name],
                source_span=binding.span,
                form_path=binding.form_path,
                expansion_stack=binding.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            binding_name=binding.name,
            normalized_body=_elaborate_expr_to_body(
                binding.value_expr,
                scope=scope.child_scope(
                    "provider-supervision-member",
                    authored_binding_name=binding.name,
                ),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            ),
        )
        for binding in expr.bindings
    )
    supervisor_binding = next(
        binding for binding in expr.bindings if binding.observes is not None
    )
    assert supervisor_binding.observes_span is not None
    assert supervisor_binding.observed_name_span is not None
    observation_span = SourceSpan(
        start=supervisor_binding.observes_span.start,
        end=supervisor_binding.observed_name_span.end,
    )
    settlement_env = {**value_env, **member_types}
    settlement_body = _elaborate_expr_to_body(
        expr.body,
        scope=scope.child_scope("provider-supervision-settlement"),
        type_env=type_env,
        value_env=settlement_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=EMPTY_EFFECT_SUMMARY,
        procedure_edges_by_site={},
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return WccProviderSupervision(
        metadata=scope.value_metadata(
            role="provider-supervision",
            type_ref=_infer_expr_type(
                expr.body,
                type_env=type_env,
                value_env=settlement_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=scope.closed_program,
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        observation_metadata=scope.value_metadata(
            role="provider-supervision:observation",
            type_ref=member_types[supervisor_binding.name],
            source_span=observation_span,
            form_path=supervisor_binding.form_path,
            expansion_stack=supervisor_binding.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        members=members,
        supervisor_name=supervisor_binding.name,
        worker_name=supervisor_binding.observes,
        settlement_body=settlement_body,
    )


def _elaborate_live_provider_peer_group(
    expr: WithLiveProviderPeersExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[
        tuple[object, tuple[str, ...]],
        str,
    ],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None,
) -> WccProviderPeerGroup:
    member_types = {
        binding.name: _infer_expr_type(
            binding.value_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
        for binding in expr.bindings
    }
    members = tuple(
        WccProviderPeerGroupMember(
            metadata=scope.value_metadata(
                role=f"provider-peer-group:member:{binding.name}",
                type_ref=member_types[binding.name],
                source_span=binding.value_expr.span,
                form_path=binding.value_expr.form_path,
                expansion_stack=binding.value_expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            binding_metadata=scope.value_metadata(
                role=f"provider-peer-group:binding:{binding.name}",
                type_ref=member_types[binding.name],
                source_span=binding.span,
                form_path=binding.form_path,
                expansion_stack=binding.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            binding_name=binding.name,
            lexical_capture_names=tuple(sorted(value_env)),
            normalized_body=_elaborate_expr_to_body(
                binding.value_expr,
                scope=scope.child_scope(
                    "provider-peer-group-member",
                    authored_binding_name=binding.name,
                ),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            ),
        )
        for binding in expr.bindings
    )
    settlement_env = member_types
    settlement_body = _elaborate_expr_to_body(
        expr.body,
        scope=scope.child_scope("provider-peer-group-settlement"),
        type_env=type_env,
        value_env=settlement_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=EMPTY_EFFECT_SUMMARY,
        procedure_edges_by_site={},
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return WccProviderPeerGroup(
        metadata=scope.value_metadata(
            role="provider-peer-group",
            type_ref=_infer_expr_type(
                expr.body,
                type_env=type_env,
                value_env=settlement_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=scope.closed_program,
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        members=members,
        settlement_body=settlement_body,
    )


def _elaborate_effect_expr_to_binding_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBindingValue:
    if isinstance(expr, RunRefExpr):
        result_type = resolve_unique_run_ref_site_metadata(
            expr,
            session_state=type_env.session_state,
            prefer_retained=scope.closed_program,
            source_module=type_env.module_name,
        ).type_ref
    else:
        result_type = _infer_expr_type(
            expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=scope.closed_program,
        )
    metadata_kwargs = dict(
        type_ref=result_type,
        source_span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
        effect_summary=effect_summary,
        phase_scope=active_phase_scope,
    )
    if isinstance(expr, RunRefExpr):
        from orchestrator.workflow.run_ref.config import BundleProgram, PathProgram
        from orchestrator.workflow.run_ref.source import SourceRequest

        metadata = resolve_unique_run_ref_site_metadata(
            expr,
            session_state=type_env.session_state,
            prefer_retained=scope.closed_program,
            source_module=type_env.module_name,
        )
        result_contract = derive_run_ref_result_contract(
            metadata.type_ref,
            type_env=type_env,
        )
        input_names = tuple(name for name, _ in expr.inputs)
        metadata_input_names = tuple(name for name, _ in metadata.input_types)
        if input_names != metadata_input_names:
            raise TypeError("typed run-ref input metadata order changed before WCC")
        if isinstance(expr.program, RunRefBundleProgram):
            program = BundleProgram(workflow_name=expr.program.workflow_name)
            target_name = expr.program.workflow_name
        elif isinstance(expr.program, RunRefPathProgram):
            if expr.environment != "deterministic-effect-free":
                raise TypeError("typed path run-ref environment changed before WCC")
            program = PathProgram(
                path=expr.program.path,
                entry_name=expr.program.entry_name,
                return_refinement=(
                    None
                    if expr.returns_type_name is None
                    else compiler_normalized_type_descriptor(
                        metadata.value_type_ref,
                        type_env=type_env,
                    )
                ),
                allow_nested_structures=(
                    target_dsl_supports_nested_structural_transport(
                        type_env.target_dsl_version
                    )
                ),
            )
            target_name = expr.program.entry_name
        else:
            raise TypeError("typed run-ref program mode changed before WCC")
        payload = WccRunRefPayload(
            source=SourceRequest(
                locator=expr.source.repo,
                commit=expr.source.commit,
                setup=expr.setup,
            ),
            program=program,
            site_digest=metadata.site_digest,
            generated_result_type=metadata.generated_type_name,
            result_descriptor=result_contract.descriptor,
            result_digest=result_contract.digest,
            allow_nested_structures=result_contract.allow_nested_structures,
            input_type_descriptors=tuple(
                (
                    name,
                    compiler_normalized_type_descriptor(
                        input_type,
                        type_env=type_env,
                    ),
                )
                for name, input_type in metadata.input_types
            ),
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:run_ref", **metadata_kwargs),
            perform_kind="run_ref",
            target_name=target_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=tuple(
                (
                    name,
                    _elaborate_atomic_value(
                        input_expr,
                        scope=scope.child_scope(
                            "run-ref-input",
                            authored_binding_name=name,
                        ),
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        effect_summary=effect_summary,
                        procedure_edges_by_site=procedure_edges_by_site,
                        compile_time_bindings=compile_time_bindings,
                        active_phase_scope=active_phase_scope,
                    ),
                )
                for name, input_expr in expr.inputs
            ),
            returns_type_name=metadata.generated_type_name,
            operation_payload=payload,
        )
    if isinstance(expr, TrialExpr):
        from orchestrator.workflow.run_ref.config import BundleProgram, PathProgram
        from orchestrator.workflow.run_ref.source import SourceRequest

        if not isinstance(expr.site_digest, str):
            raise TypeError("typed trial site identity is unavailable before WCC")
        result_contract = derive_trial_result_contract(
            result_type,
            type_env=type_env,
        )
        arms: list[WccTrialArmPayload] = []
        keyword_args: list[tuple[str, WccValue]] = []
        for arm_index, arm in enumerate(expr.arms):
            run_ref = arm.run_ref
            metadata = resolve_unique_run_ref_site_metadata(
                run_ref,
                session_state=type_env.session_state,
                prefer_retained=scope.closed_program,
                source_module=type_env.module_name,
            )
            arm_contract = derive_run_ref_result_contract(
                metadata.type_ref,
                type_env=type_env,
            )
            if isinstance(run_ref.program, RunRefBundleProgram):
                program = BundleProgram(
                    workflow_name=run_ref.program.workflow_name
                )
            elif isinstance(run_ref.program, RunRefPathProgram):
                if run_ref.environment != "deterministic-effect-free":
                    raise TypeError(
                        "typed path run-ref environment changed before WCC"
                    )
                program = PathProgram(
                    path=run_ref.program.path,
                    entry_name=run_ref.program.entry_name,
                    return_refinement=(
                        None
                        if run_ref.returns_type_name is None
                        else compiler_normalized_type_descriptor(
                            metadata.value_type_ref,
                            type_env=type_env,
                        )
                    ),
                    allow_nested_structures=True,
                )
            else:
                raise TypeError("typed trial arm program mode changed before WCC")
            arm_payload = WccRunRefPayload(
                source=SourceRequest(
                    locator=run_ref.source.repo,
                    commit=run_ref.source.commit,
                    setup=run_ref.setup,
                ),
                program=program,
                site_digest=metadata.site_digest,
                generated_result_type=metadata.generated_type_name,
                result_descriptor=arm_contract.descriptor,
                result_digest=arm_contract.digest,
                allow_nested_structures=True,
                input_type_descriptors=tuple(
                    (
                        name,
                        compiler_normalized_type_descriptor(
                            input_type,
                            type_env=type_env,
                        ),
                    )
                    for name, input_type in metadata.input_types
                ),
            )
            input_keywords: list[tuple[str, str]] = []
            for input_name, input_expr in run_ref.inputs:
                keyword = f"arm_{arm_index}__{input_name}"
                input_keywords.append((input_name, keyword))
                keyword_args.append(
                    (
                        keyword,
                        _elaborate_atomic_value(
                            input_expr,
                            scope=scope.child_scope(
                                "trial-arm-input",
                                authored_binding_name=(
                                    f"{arm_index}:{input_name}"
                                ),
                            ),
                            type_env=type_env,
                            value_env=value_env,
                            workflow_return_types=workflow_return_types,
                            procedure_return_types=procedure_return_types,
                            effect_summary=effect_summary,
                            procedure_edges_by_site=procedure_edges_by_site,
                            compile_time_bindings=compile_time_bindings,
                            active_phase_scope=active_phase_scope,
                        ),
                    )
                )
            arms.append(
                WccTrialArmPayload(
                    arm_id=arm.arm_id,
                    run_ref=arm_payload,
                    input_keywords=tuple(input_keywords),
                )
            )
        payload = WccTrialPayload(
            arms=tuple(arms),
            site_digest=expr.site_digest,
            generated_result_type=result_type.name,
            result_descriptor=result_contract.descriptor,
            result_digest=result_contract.digest,
            reps=expr.reps,
            max_concurrency=expr.max_concurrency,
            evaluation=asdict(expr.evaluation),
            budget=asdict(expr.budget),
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:trial", **metadata_kwargs),
            perform_kind="trial",
            target_name="trial",
            prompt_name=None,
            positional_args=(),
            keyword_args=tuple(keyword_args),
            returns_type_name=result_type.name,
            operation_payload=payload,
        )
    if isinstance(expr, WithLiveProviderPeersExpr):
        return _elaborate_live_provider_peer_group(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, WithLiveProvidersExpr):
        return _elaborate_live_provider_supervision(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, ProviderResultExpr):
        operation_payload = {"return_spec": expr.return_spec}
        if isinstance(expr.prompt, PromptApplicationExpr):
            operation_payload["prompt_application"] = replace(
                expr.prompt,
                fills=tuple(
                    replace(
                        fill,
                        value_expr=_elaborate_atomic_value(
                            fill.value_expr,
                            scope=scope.child_scope(
                                "prompt-fragment-fill",
                                authored_binding_name=fill.name,
                            ),
                            type_env=type_env,
                            value_env=value_env,
                            workflow_return_types=workflow_return_types,
                            procedure_return_types=procedure_return_types,
                            effect_summary=effect_summary,
                            procedure_edges_by_site=procedure_edges_by_site,
                            compile_time_bindings=compile_time_bindings,
                            active_phase_scope=active_phase_scope,
                        ),
                    )
                    for fill in expr.prompt.fills
                ),
            )
        for field_name, field_expr in (
            ("model", expr.model),
            ("effort", expr.effort),
            ("delivery", expr.delivery),
            ("materialization_attempts", expr.materialization_attempts),
            ("timeout_sec", expr.timeout_sec),
        ):
            if field_expr is None:
                continue
            operation_payload[field_name] = _elaborate_atomic_value(
                field_expr,
                scope=scope.child_scope(
                    f"provider-policy:{field_name}",
                    authored_binding_name=field_name,
                ),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        if expr.session_artifact is not None:
            operation_payload["session_artifact"] = expr.session_artifact
        if expr.context_expr is not None:
            operation_payload["context_expr"] = _elaborate_atomic_value(
                expr.context_expr,
                scope=scope.child_scope(
                    "provider-context",
                    authored_binding_name="context",
                ),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        if expr.capture_context is not None:
            operation_payload["capture_context"] = expr.capture_context
        if expr.prompt_dependencies is not None:
            dependency_rows: list[WccPromptDependencyRow] = []
            for role, operands in (
                ("required", expr.prompt_dependencies.required),
                ("optional", expr.prompt_dependencies.optional),
            ):
                for index, operand in enumerate(operands):
                    value = _elaborate_atomic_value(
                        operand,
                        scope=scope.child_scope(
                            f"prompt-dependency:{role}",
                            authored_binding_name=str(index),
                        ),
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        effect_summary=effect_summary,
                        procedure_edges_by_site=procedure_edges_by_site,
                        compile_time_bindings=compile_time_bindings,
                        active_phase_scope=active_phase_scope,
                    )
                    dependency_rows.append(
                        WccPromptDependencyRow(
                            role=role,
                            authored_index=index,
                            value=value,
                            source_span=operand.span,
                            form_path=operand.form_path,
                            expansion_stack=operand.expansion_stack,
                        )
                    )
            spec = expr.prompt_dependencies
            operation_payload["prompt_dependencies"] = WccPromptDependencyPayload(
                rows=tuple(dependency_rows),
                position=spec.position,
                instruction=spec.instruction,
                source_span=spec.span,
                form_path=spec.form_path,
                expansion_stack=spec.expansion_stack,
            )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:provider_result", **metadata_kwargs),
            perform_kind="provider_result",
            target_name=_require_name_expr(expr.provider),
            prompt_name=(
                None
                if isinstance(expr.prompt, PromptApplicationExpr)
                else _require_name_expr(expr.prompt)
            ),
            positional_args=tuple(
                _elaborate_atomic_value(
                    item,
                    scope=scope.child_scope("provider-input", authored_binding_name=str(index)),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
                for index, item in enumerate(expr.inputs)
            ),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=operation_payload,
        )
    if isinstance(expr, RequestInputExpr):
        return WccPerform(
            metadata=scope.value_metadata(
                role="perform:request_input",
                **metadata_kwargs,
            ),
            perform_kind="request_input",
            target_name="request-input",
            prompt_name=None,
            positional_args=(
                _elaborate_atomic_value(
                    expr.question,
                    scope=scope.child_scope(
                        "request-input-question",
                        authored_binding_name="question",
                    ),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
            ),
            keyword_args=(),
            returns_type_name=HUMAN_REPLY_TYPE_NAME,
        )
    if isinstance(expr, CommandResultExpr):
        adapter_inputs = tuple(
            (
                field_name,
                _elaborate_atomic_value(
                    value_expr,
                    scope=scope.child_scope("command-adapter-input", authored_binding_name=field_name),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
            )
            for field_name, value_expr in expr.adapter_inputs
        )
        perform = WccPerform(
            metadata=scope.value_metadata(role="perform:command_result", **metadata_kwargs),
            perform_kind="command_result",
            target_name=expr.step_name,
            prompt_name=None,
            positional_args=tuple(
                _elaborate_atomic_value(
                    item,
                    scope=scope.child_scope("command-arg", authored_binding_name=str(index)),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
                for index, item in enumerate(expr.argv)
            ),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload={
                "adapter_name": expr.adapter_name,
                "adapter_inputs": adapter_inputs,
                "return_spec": expr.return_spec,
            },
        )
        command_context = compile_time_bindings.get(_COMMAND_SCOPE_CONTEXT)
        return command_context.plan_command(expr, perform) if command_context is not None else perform
    if isinstance(expr, RunProviderPhaseExpr):
        ctx_value = _elaborate_atomic_value(
            expr.ctx_expr,
            scope=scope.child_scope("run-provider-phase", authored_binding_name="ctx"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        inputs_value = _elaborate_atomic_value(
            expr.inputs_expr,
            scope=scope.child_scope("run-provider-phase", authored_binding_name="inputs"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:run_provider_phase", **metadata_kwargs),
            perform_kind="run_provider_phase",
            target_name=_require_name_expr(expr.provider),
            prompt_name=_require_name_expr(expr.prompt),
            positional_args=(ctx_value, inputs_value),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=WccRunProviderPhasePayload(
                phase_name=expr.phase_name,
                ctx_expr=ctx_value,
                inputs_expr=inputs_value,
                provider_name=_require_name_expr(expr.provider),
                prompt_name=_require_name_expr(expr.prompt),
            ),
        )
    if isinstance(expr, ProduceOneOfExpr):
        ctx_value = _elaborate_atomic_value(
            expr.ctx_expr,
            scope=scope.child_scope("produce-one-of", authored_binding_name="ctx"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        producer_inputs = tuple(
            _elaborate_atomic_value(
                item,
                scope=scope.child_scope("produce-one-of-input", authored_binding_name=str(index)),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            for index, item in enumerate(expr.producer.inputs)
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:produce_one_of", **metadata_kwargs),
            perform_kind="produce_one_of",
            target_name=_require_name_expr(expr.producer.provider_expr),
            prompt_name=_require_name_expr(expr.producer.prompt_expr),
            positional_args=(ctx_value, *producer_inputs),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=WccProduceOneOfPayload(
                ctx_expr=ctx_value,
                provider_name=_require_name_expr(expr.producer.provider_expr),
                prompt_name=_require_name_expr(expr.producer.prompt_expr),
                producer_inputs=producer_inputs,
                candidates=expr.candidates,
            ),
        )
    if isinstance(expr, ResumeOrStartExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:resume_or_start", **metadata_kwargs),
            perform_kind="resume_or_start",
            target_name=expr.resume_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=WccResumeOrStartPayload(
                resume_name=expr.resume_name,
                ctx_expr=_elaborate_atomic_value(
                    expr.ctx_expr,
                    scope=scope.child_scope("resume-or-start", authored_binding_name="ctx"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
                resume_from_expr=_elaborate_atomic_value(
                    expr.resume_from_expr,
                    scope=scope.child_scope("resume-or-start", authored_binding_name="resume-from"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
                valid_when=expr.valid_when,
                start_value=_elaborate_effect_expr_to_binding_value(
                    expr.start_expr,
                    scope=scope.child_scope("resume-or-start", authored_binding_name="start"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
                validation_spec=expr.validation_spec,
            ),
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:finalize_selected_item", **metadata_kwargs),
            perform_kind="finalize_selected_item",
            target_name="finalize-selected-item",
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=None,
            operation_payload=expr,
        )
    if isinstance(expr, ResourceTransitionExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:resource_transition", **metadata_kwargs),
            perform_kind="resource_transition",
            target_name=expr.spec.transition_ref_name or expr.spec.transition_name or "resource-transition",
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=None,
            operation_payload=expr,
        )
    if isinstance(expr, MaterializeViewExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:materialize_view", **metadata_kwargs),
            perform_kind="materialize_view",
            target_name=expr.view_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=expr,
        )
    if isinstance(expr, CallExpr):
        resolved_workflow_ref, _ = _unwrap_compile_time_alias(
            compile_time_bindings.get(expr.callee_name),
        )
        target_name = (
            resolved_workflow_ref.workflow_name
            if isinstance(resolved_workflow_ref, ResolvedWorkflowRef)
            else expr.callee_name
        )
        call = WccPerform(
            metadata=scope.value_metadata(role="perform:workflow_call", **metadata_kwargs),
            perform_kind="workflow_call",
            target_name=target_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=tuple(
                (
                    binding_name,
                    _elaborate_workflow_call_binding_value(
                        binding_expr,
                        scope=scope.child_scope("workflow-binding", authored_binding_name=binding_name),
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        effect_summary=effect_summary,
                        procedure_edges_by_site=procedure_edges_by_site,
                        compile_time_bindings=compile_time_bindings,
                        active_phase_scope=active_phase_scope,
                    ),
                )
                for binding_name, binding_expr in expr.bindings
            ),
            returns_type_name=None,
        )
        command_context = compile_time_bindings.get(_COMMAND_SCOPE_CONTEXT)
        if command_context is not None:
            command_context.prepare_call(expr, call, variants=scope.enclosing_variants)
        return call
    if isinstance(expr, ProcedureCallExpr):
        specialized_name = procedure_edges_by_site.get((expr.span, expr.form_path), expr.callee_name)
        select_edge = compile_time_bindings.get(_CLOSED_PROCEDURE_SELECTION)
        if select_edge is not None:
            specialized_name = select_edge(expr, specialized_name, compile_time_bindings)
        specialization_captures: list[
            WccSpecializationCapture
        ] = []
        proc_ref_argument_sources: list[
            tuple[int, str, bool]
        ] = []
        compile_time_callee, callee_source_name = (
            _unwrap_compile_time_alias(
                compile_time_bindings.get(expr.callee_name),
            )
        )
        if isinstance(
            compile_time_callee,
            _WccBoundProcedureBinding,
        ):
            specialization_captures.extend(
                WccSpecializationCapture(
                    owner_kind="callee",
                    argument_index=None,
                    source_name=name,
                    value=value,
                    source_binding=source_binding,
                )
                for name, value, source_binding in compile_time_callee.capture_values
            )
        for index, item in enumerate(expr.args):
            if not isinstance(item, NameExpr):
                continue
            compile_time_arg, argument_source_name = (
                _unwrap_compile_time_alias(
                    compile_time_bindings.get(item.name),
                )
            )
            if isinstance(
                compile_time_arg,
                (
                    _WccBoundProcedureBinding,
                    ResolvedProcRefValue,
                ),
            ):
                proc_ref_argument_sources.append(
                    (
                        index,
                        argument_source_name or item.name,
                        _compile_time_binding_masks_deferred_capture(
                            compile_time_arg
                        ),
                    )
                )
            if isinstance(
                compile_time_arg,
                _WccBoundProcedureBinding,
            ):
                specialization_captures.extend(
                    WccSpecializationCapture(
                        owner_kind="argument",
                        argument_index=index,
                        source_name=name,
                        value=value,
                        source_binding=source_binding,
                    )
                    for name, value, source_binding in compile_time_arg.capture_values
                )
        runtime_arguments = tuple(
            (index, item) for index, item in enumerate(expr.args)
            if not (
                _is_compile_time_reference_value(item)
                or (
                    isinstance(item, NameExpr)
                    and _is_compile_time_reference_value(
                        compile_time_bindings.get(item.name)
                    )
                )
            )
        )
        call = WccCall(
            metadata=scope.value_metadata(role=f"call:{specialized_name}", **metadata_kwargs),
            callee_name=expr.callee_name,
            specialized_callee_name=specialized_name,
            args=tuple(
                _elaborate_atomic_value(
                    item,
                    scope=scope.child_scope("procedure-arg", authored_binding_name=str(index)),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
                for index, item in runtime_arguments
            ),
            specialization_captures=tuple(
                specialization_captures
            ),
            bound_proc_source=(
                compile_time_callee.source_binding
                if isinstance(compile_time_callee, _WccBoundProcedureBinding)
                else None
            ),
            proc_ref_callee_source=(
                callee_source_name
                if isinstance(
                    compile_time_callee,
                    ResolvedProcRefValue,
                )
                else None
            ),
            proc_ref_callee_masks_deferred=(
                _compile_time_binding_masks_deferred_capture(
                    compile_time_callee
                )
            ),
            proc_ref_argument_sources=tuple(
                proc_ref_argument_sources
            ),
        )
        command_context = compile_time_bindings.get(_COMMAND_SCOPE_CONTEXT)
        if command_context is not None:
            command_context.prepare_call(expr, call, variants=scope.enclosing_variants,
                procedure_arguments=runtime_arguments)
        return call
    raise TypeError(f"unsupported WCC M2 effect node: {type(expr).__name__}")


def _is_compile_time_reference_value(value: object) -> bool:
    return isinstance(
        value,
        (
            BindProcExpr,
            _WccBoundProcedureBinding,
            _WccCompileTimeAlias,
            ProcRefLiteralExpr,
            ResolvedProcRefValue,
            ResolvedWorkflowRef,
            WorkflowRefLiteralExpr,
        ),
    )


def _compile_time_binding_masks_deferred_capture(
    value: object,
) -> bool:
    """Return whether ``value`` is a new lexical ProcRef owner."""

    return isinstance(
        value,
        (
            BindProcExpr,
            _WccBoundProcedureBinding,
            ProcRefLiteralExpr,
        ),
    )


def _unwrap_compile_time_alias(
    value: object,
    *,
    default_source_name: str | None = None,
) -> tuple[object, str | None]:
    source_name = default_source_name
    current = value
    while isinstance(current, _WccCompileTimeAlias):
        source_name = current.source_name
        current = current.value
    return current, source_name


def _elaborate_atomic_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccValue:
    prefix, value = _elaborate_expr_to_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    if prefix:
        raise TypeError(f"unsupported nested WCC M2 prefix for `{type(expr).__name__}`")
    return value


def _elaborate_workflow_call_binding_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccValue:
    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RequestInputExpr,
            RunRefExpr,
            TrialExpr,
            RunProviderPhaseExpr,
            FinalizeSelectedItemExpr,
            ResourceTransitionExpr,
            CallExpr,
        ),
    ):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_signature_mismatch",
                    message=(
                        "Stage 3 lowering requires same-file call bindings to resolve to workflow inputs"
                    ),
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            )
        )
    return _elaborate_atomic_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )


def _at_2_33(type_env: FrontendTypeEnvironment) -> bool:
    return target_dsl_is_2_33_or_newer(getattr(type_env, "target_dsl_version", "") or "")


def _generated_effect_binding_name_from_scope(scope: WccIdentityFactory, *, role: str) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    return f"__wcc_effect_{safe_role}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _generated_value_binding_name_from_scope(scope: WccIdentityFactory, *, role: str) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    return f"__wcc_value_{safe_role}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _require_record_type(expr: RecordExpr, *, type_env: FrontendTypeEnvironment) -> RecordTypeRef:
    resolved = type_env.resolve_constructor_type(expr, expansion_stack=expr.expansion_stack)
    if not isinstance(resolved, RecordTypeRef):
        raise TypeError(f"expected record type for `{expr.type_name}`")
    return resolved


def _require_union_type(expr: UnionVariantExpr, *, type_env: FrontendTypeEnvironment) -> UnionTypeRef:
    resolved = type_env.resolve_constructor_type(expr, expansion_stack=expr.expansion_stack)
    if not isinstance(resolved, UnionTypeRef):
        raise TypeError(f"expected union type for `{expr.type_name}`")
    return resolved


def _require_name_expr(expr) -> str:
    if not isinstance(expr, NameExpr):
        raise TypeError(f"expected name expression, found `{type(expr).__name__}`")
    return expr.name

def _infer_expr_type(
    expr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    closed_program: bool = False,
) -> TypeRef:
    if isinstance(expr, UnionVariantTagExpr):
        return DiscriminantTypeRef(
            union_name=expr.union_name,
            variant_names=expr.variant_names,
            applied_union=(
                expr.discriminant_owner
                if isinstance(expr.discriminant_owner, UnionTypeRef)
                and expr.discriminant_owner.type_args
                else None
            ),
            owner_union=(
                expr.discriminant_owner
                if isinstance(expr.discriminant_owner, UnionTypeRef)
                else None
            ),
        )
    if isinstance(expr, LiteralExpr):
        return {
            "string": PrimitiveTypeRef(name="String"),
            "int": PrimitiveTypeRef(name="Int"),
            "bool": PrimitiveTypeRef(name="Bool"),
            "float": PrimitiveTypeRef(name="Float"),
        }[expr.literal_kind]
    if isinstance(expr, EnumMemberExpr):
        return expr.resolved_type or type_env.resolve_type(
            expr.enum_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ProcRefLiteralExpr):
        return value_env.get(
            expr.target_name,
            PrimitiveTypeRef(name="String"),
        )
    if isinstance(expr, WorkflowRefLiteralExpr):
        return value_env.get(
            expr.target_name,
            PrimitiveTypeRef(name="String"),
        )
    if isinstance(expr, NameExpr):
        return value_env[expr.name]
    if isinstance(expr, PhaseTargetExpr):
        return PrimitiveTypeRef(name="String")
    if isinstance(expr, GeneratedRelpathSeedExpr):
        return expr.target_type_ref
    if isinstance(expr, LoopStateSeedExpr):
        field_types = tuple(
            (
                field.name,
                _infer_expr_type(
                    field.value_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    closed_program=closed_program,
                ),
            )
            for field in expr.fields
        )
        metadata = carrier_metadata_for_expr(
            expr,
            session_state=type_env.session_state,
            field_signature=tuple((field_name, field_type.name) for field_name, field_type in field_types),
            field_types=field_types,
            type_env=type_env,
        )
        if metadata is None:
            raise TypeError("loop-state seed metadata was unavailable during WCC inference")
        return type_env.resolve_type(
            metadata.generated_type_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, LoopStateUpdateExpr):
        return _infer_expr_type(
            expr.base_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    if isinstance(expr, RecordUpdateExpr):
        return _infer_expr_type(
            expr.base_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    if isinstance(expr, ListExpr):
        if expr.element_type_ref is None:
            raise TypeError("typed list expression is missing its element type")
        return ListTypeRef(
            name=f"List[{expr.element_type_ref.name}]",
            item_type_ref=expr.element_type_ref,
        )
    if isinstance(expr, ListMapExpr):
        if expr.result_item_type_ref is None:
            raise TypeError("typed list/map expression is missing its result element type")
        return ListTypeRef(
            name=f"List[{expr.result_item_type_ref.name}]",
            item_type_ref=expr.result_item_type_ref,
        )
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        return expr.element_type_ref
    if isinstance(expr, PathJoinUnderExpr):
        if not isinstance(expr.path_type_ref, PathTypeRef):
            raise TypeError("typed path/join-under expression is missing its path type")
        return expr.path_type_ref
    if isinstance(expr, FieldAccessExpr):
        current: TypeRef = value_env[expr.base.name]
        targets = expr.shared_field_types or (None,) * len(expr.fields)
        for field_name, target in zip(expr.fields, targets, strict=True):
            if target is not None:
                current = target
                continue
            if isinstance(current, UnionTypeRef) and field_name == "variant":
                current = DiscriminantTypeRef(
                    union_name=current.name,
                    variant_names=tuple(variant.name for variant in current.definition.variants),
                    applied_union=current if current.type_args else None,
                    owner_union=current,
                )
                continue
            if not isinstance(current, (RecordTypeRef, VariantCaseTypeRef)):
                raise TypeError(f"expected record type while resolving `{expr.base.name}.{'.'.join(expr.fields)}`")
            current = type_env.record_field(
                current,
                field_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return current
    if isinstance(expr, RecordExpr):
        return _require_record_type(expr, type_env=type_env)
    if isinstance(expr, UnionVariantExpr):
        return _require_union_type(expr, type_env=type_env)
    if isinstance(expr, PureOpExpr):
        arg_types = tuple(
            _infer_expr_type(
                arg,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
            )
            for arg in expr.args
        )
        operator = expr.operator
        catalog_type = catalog_operator_result_type(operator, arg_types)
        if catalog_type is not None:
            return catalog_type
        if operator in {"=", "!=", "and", "or", "not", "some?"}:
            return PrimitiveTypeRef(name="Bool")
        if operator == "or-else":
            if len(arg_types) != 2:
                raise TypeError("pure operator `or-else` requires exactly two operands during WCC inference")
            if isinstance(arg_types[0], OptionalTypeRef):
                return arg_types[0].item_type_ref
            return arg_types[1]
        if operator in {"string/concat", "symbol/name"}:
            return PrimitiveTypeRef(name="String")
        if operator == "string/empty?":
            return PrimitiveTypeRef(name="Bool")
        if operator == "list/empty?":
            return PrimitiveTypeRef(name="Bool")
        if operator == "list/head":
            if not isinstance(arg_types[0], ListTypeRef):
                raise TypeError("list/head requires a list during WCC inference")
            return OptionalTypeRef(
                name=f"Optional[{arg_types[0].item_type_ref.name}]",
                item_type_ref=arg_types[0].item_type_ref,
            )
        if operator in {"list/rest", "list/append"}:
            return arg_types[0]
        if operator == "list/length":
            return PrimitiveTypeRef(name="Int")
        raise TypeError(f"unsupported WCC pure operator inference `{operator}`")
    if isinstance(expr, ContinueExpr):
        state_type = _infer_expr_type(
            expr.state_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        return LoopControlTypeRef(state_type_ref=state_type, result_type_ref=None)
    if isinstance(expr, DoneExpr):
        result_type = _infer_expr_type(
            expr.result_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        state_type = (
            _infer_expr_type(
                expr.terminal_state_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
            )
            if expr.terminal_state_expr is not None
            else result_type
        )
        return LoopControlTypeRef(
            state_type_ref=state_type,
            result_type_ref=result_type,
        )
    if isinstance(expr, LoopRecurExpr):
        state_type = _infer_expr_type(
            expr.initial_state_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        loop_env = dict(value_env)
        loop_env[expr.binding_name] = state_type
        body_type = _infer_expr_type(
            expr.body_expr,
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        if isinstance(body_type, LoopControlTypeRef) and body_type.result_type_ref is not None:
            return body_type.result_type_ref
        if expr.on_exhausted_result_expr is not None:
            return _infer_expr_type(
                expr.on_exhausted_result_expr,
                type_env=type_env,
                value_env=loop_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
            )
        raise TypeError("loop/recur body must expose a done result type")
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        for index, (binding_name, binding_expr) in enumerate(expr.bindings):
            local_env[binding_name] = binding_type_for_elaboration(
                binding_expr,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
                capture_source=expr.binding_capture_sources[index] if index < len(expr.binding_capture_sources) else None,
            )
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    if isinstance(expr, IfExpr):
        _, then_value_env = _branch_proof_narrowing(
            expr.true_proof_context,
            type_env=type_env,
            value_env=value_env,
            span=expr.span,
            form_path=expr.form_path,
        )
        _, else_value_env = _branch_proof_narrowing(
            expr.false_proof_context,
            type_env=type_env,
            value_env=value_env,
            span=expr.span,
            form_path=expr.form_path,
        )
        then_type = _infer_expr_type(
            expr.then_expr,
            type_env=type_env,
            value_env=then_value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        else_type = _infer_expr_type(
            expr.else_expr,
            type_env=type_env,
            value_env=else_value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        if isinstance(then_type, LoopControlTypeRef) and isinstance(else_type, LoopControlTypeRef):
            return _merge_loop_control_types(then_type, else_type, owner="if")
        if not type_refs_compatible(then_type, else_type):
            raise TypeError("if branch types must match during WCC inference")
        return then_type
    if isinstance(expr, MatchExpr):
        subject_type = _infer_expr_type(
            expr.subject,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
        if not isinstance(subject_type, UnionTypeRef):
            raise TypeError("match subject must have a union type")
        inferred_type: TypeRef | LoopControlTypeRef | None = None
        for arm in expr.arms:
            arm_env = dict(value_env)
            arm_env[arm.binding_name] = type_env.union_variant(
                subject_type,
                arm.variant_name,
                span=arm.span,
                form_path=arm.form_path,
                expansion_stack=arm.expansion_stack,
            )
            arm_type = _infer_expr_type(
                arm.body,
                type_env=type_env,
                value_env=arm_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
            )
            if inferred_type is None:
                inferred_type = arm_type
                continue
            if isinstance(inferred_type, LoopControlTypeRef) and isinstance(arm_type, LoopControlTypeRef):
                inferred_type = _merge_loop_control_types(inferred_type, arm_type, owner="match")
                continue
            if not type_refs_compatible(inferred_type, arm_type):
                raise TypeError("match arm types must match during WCC inference")
        assert inferred_type is not None
        return inferred_type
    if isinstance(expr, WithLiveProvidersExpr):
        member_types = {
            binding.name: _infer_expr_type(
                binding.value_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
            )
            for binding in expr.bindings
        }
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env={**value_env, **member_types},
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    if isinstance(expr, WithLiveProviderPeersExpr):
        member_types = {
            binding.name: _infer_expr_type(
                binding.value_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                closed_program=closed_program,
            )
            for binding in expr.bindings
        }
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=member_types,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    if isinstance(expr, WithPhaseExpr):
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    if isinstance(expr, RunRefExpr):
        return resolve_unique_run_ref_site_metadata(
            expr,
            session_state=type_env.session_state,
        ).type_ref
    if isinstance(expr, TrialExpr):
        if not isinstance(expr.site_digest, str):
            raise TypeError("typed trial site identity is unavailable before WCC")
        resolved = type_env._type_refs.get(f"TrialResult${expr.site_digest[:16]}")
        if not isinstance(resolved, RecordTypeRef):
            raise TypeError("typed trial result contract is unavailable before WCC")
        return resolved
    if isinstance(expr, ProviderBundlePathExpr):
        return _resolve_wcc_type_name(
            expr.target_type_name,
            type_env=type_env,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ProviderResultExpr):
        model_result_type = (
            expr.prompt.prompt.return_type_ref
            if isinstance(expr.prompt, PromptApplicationExpr)
            else _resolve_wcc_type_name(
                expr.returns_type_name,
                type_env=type_env,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        )
        if expr.capture_context is None:
            return model_result_type
        from ..context_types import contextual_type

        return contextual_type(
            model_result_type,
            type_env.resolve_type(
                "Context",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
        )
    if isinstance(expr, RequestInputExpr):
        return type_env.resolve_type(
            HUMAN_REPLY_TYPE_NAME,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(
        expr,
        (
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            MaterializeViewExpr,
        ),
    ):
        return _resolve_wcc_type_name(
            expr.returns_type_name,
            type_env=type_env,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return type_env.resolve_type(
            "SelectedItemResult",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ResourceTransitionExpr):
        if getattr(expr.spec, "mode", None) == "declared_transition":
            transition_def = type_env.resolve_transition_declaration(
                expr.spec.transition_ref_name or "",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            return type_env.resolve_type(
                transition_def.result_type_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return type_env.resolve_type(
            "ResourceTransitionResult",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, CallExpr):
        workflow_ref_type = value_env.get(expr.callee_name)
        if isinstance(workflow_ref_type, WorkflowRefTypeRef):
            return workflow_ref_type.return_type_ref
        return workflow_return_types[expr.callee_name]
    if isinstance(expr, ProcedureCallExpr):
        proc_ref_type = value_env.get(expr.callee_name)
        if isinstance(proc_ref_type, ProcRefTypeRef):
            return proc_ref_type.return_type_ref
        return procedure_return_types[expr.callee_name]
    if isinstance(expr, BindProcExpr):
        return _infer_expr_type(
            expr.base_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            closed_program=closed_program,
        )
    raise TypeError(f"unsupported WCC type inference node: {type(expr).__name__}")


def _merge_loop_control_types(
    left: LoopControlTypeRef,
    right: LoopControlTypeRef,
    *,
    owner: str,
) -> LoopControlTypeRef:
    if left.result_type_ref is None and right.result_type_ref is None:
        if not type_refs_compatible(left.state_type_ref, right.state_type_ref):
            raise TypeError(f"{owner} loop-control continue state types must match during WCC inference")
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=None,
        )
    if left.result_type_ref is not None and right.result_type_ref is not None:
        if not type_refs_compatible(left.result_type_ref, right.result_type_ref):
            raise TypeError(f"{owner} loop-control done result types must match during WCC inference")
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=left.result_type_ref,
        )
    result_type_ref = left.result_type_ref or right.result_type_ref
    state_type_ref = left.state_type_ref if left.result_type_ref is None else right.state_type_ref
    return LoopControlTypeRef(
        state_type_ref=state_type_ref,
        result_type_ref=result_type_ref,
    )


def _resolve_wcc_type_name(
    type_name: str,
    *,
    type_env: FrontendTypeEnvironment,
    span,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> TypeRef:
    try:
        return type_env.resolve_type(
            type_name,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    except LispFrontendCompileError as exc:
        suffixes = (f"::{type_name}", f"/{type_name}")
        candidates: list[TypeRef] = []
        for name, candidate in type_env._type_refs.items():  # noqa: SLF001 - WCC consumes canonical import refs.
            if not any(name.endswith(suffix) for suffix in suffixes):
                continue
            if any(type_refs_compatible(existing, candidate) for existing in candidates):
                continue
            candidates.append(candidate)
        if len(candidates) == 1:
            return candidates[0]
        raise exc
