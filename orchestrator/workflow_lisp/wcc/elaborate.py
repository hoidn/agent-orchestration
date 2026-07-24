"""Elaboration from typed frontend expressions into Workflow Core Calculus."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields as dataclass_fields, is_dataclass, replace

from ..conditionals import classify_condition_expr
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from ..expression_traversal import walk_expr
from ..expressions import (
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MaterializeViewExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    PureOpExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from ..procedures import (
    ProcedureLoweringMode,
    TypedProcedureDef,
    procedure_type_env_for,
)
from ..procedure_refs import ResolvedProcRefValue
from ..spans import SourceSpan
from ..type_env import (
    FrontendTypeEnvironment,
    OptionalTypeRef,
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
from ..workflows import TypedWorkflowDef
from ..workflow_refs import ResolvedWorkflowRef
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
    WccProviderSupervision,
    WccProviderSupervisionMember,
    WccPureOp,
    WccProduceOneOfPayload,
    WccRecJoin,
    WccRecordAtom,
    WccResumeOrStartPayload,
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

    capture_values: tuple[tuple[str, WccValue], ...]


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
) -> WccBody:
    """Elaborate one typed workflow body into WCC."""

    scope = WccIdentityFactory(
        owner_name=owner_name,
        lexical_owner_chain=("workflow",),
        route_schema_version=route_schema_version or WccIdentityFactory.route_schema_version,
    )
    procedure_edges_by_site = {
        (edge.span, edge.form_path): edge.callee_name
        for edge in typed_body.effect_summary.procedure_edges
        if edge.span is not None
    }
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
            site_specializations = tuple(
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
            if len(site_specializations) > 1:
                raise TypeError(
                    "compiler-owned procedure specialization is "
                    "ambiguous at one WCC call site"
                )
            if site_specializations:
                procedure_edges_by_site[site] = (
                    site_specializations[0].definition.name
                )
    resolved_procedure_return_types = dict(procedure_return_types or {})
    for node in walk_expr(typed_body.expr):
        if not isinstance(node, ProcedureCallExpr):
            continue
        specialized_name = procedure_edges_by_site.get(
            (node.span, node.form_path)
        )
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
    initial_compile_time_bindings = dict(
        compile_time_bindings or {}
    )
    if any(
        isinstance(node, WithLiveProvidersExpr)
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
    node: WccBody | WccProviderSupervision,
    *,
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment],
    type_env: FrontendTypeEnvironment,
    procedure_return_types: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef] | None = None,
) -> WccBody | WccProviderSupervision:
    """Close every live-provider member by recursively inlining explicit procedures."""

    context = _ProviderSupervisionClosureContext(
        resolved_procedures_by_name=resolved_procedures_by_name,
        procedure_type_envs=procedure_type_envs,
        type_env=type_env,
        workflow_return_types=dict(workflow_return_types or {}),
        procedure_return_types=dict(procedure_return_types),
    )
    if isinstance(node, WccProviderSupervision):
        return _close_provider_supervision(node, context=context)
    return _close_provider_supervision_groups_in_body(node, context=context)


@dataclass(frozen=True)
class _ProviderSupervisionClosureContext:
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef]
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment]
    type_env: FrontendTypeEnvironment
    workflow_return_types: Mapping[str, TypeRef]
    procedure_return_types: Mapping[str, TypeRef]


def _close_provider_supervision_groups_in_body(
    body: WccBody,
    *,
    context: _ProviderSupervisionClosureContext,
) -> WccBody:
    if isinstance(body, WccLet):
        bound_value = body.bound_value
        if isinstance(bound_value, WccProviderSupervision):
            bound_value = _close_provider_supervision(
                bound_value,
                context=context,
            )
        return replace(
            body,
            bound_value=bound_value,
            body=_close_provider_supervision_groups_in_body(
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
                    body=_close_provider_supervision_groups_in_body(
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
            then_body=_close_provider_supervision_groups_in_body(
                body.then_body,
                context=context,
            ),
            else_body=_close_provider_supervision_groups_in_body(
                body.else_body,
                context=context,
            ),
        )
    if isinstance(body, WccJoin):
        return replace(
            body,
            body=_close_provider_supervision_groups_in_body(
                body.body,
                context=context,
            ),
            continuation=_close_provider_supervision_groups_in_body(
                body.continuation,
                context=context,
            ),
        )
    if isinstance(body, WccRecJoin):
        return replace(
            body,
            body=_close_provider_supervision_groups_in_body(
                body.body,
                context=context,
            ),
            exhaustion=(
                _close_provider_supervision_groups_in_body(
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
    context: _ProviderSupervisionClosureContext,
) -> WccProviderSupervision:
    from .anf import normalize_wcc_body_to_anf
    from .analysis import validate_wcc_provider_supervision

    closed = replace(
        group,
        members=tuple(
            replace(
                member,
                normalized_body=_inline_provider_supervision_member(
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


def _inline_provider_supervision_member(
    member: WccProviderSupervisionMember,
    *,
    context: _ProviderSupervisionClosureContext,
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
    member: WccProviderSupervisionMember,
    context: _ProviderSupervisionClosureContext,
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
    if isinstance(bound_value, WccProviderSupervision):
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
    member: WccProviderSupervisionMember,
    context: _ProviderSupervisionClosureContext,
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
    for ordinal, (name, value) in enumerate(
        specialization_values.items()
    ):
        rewritten, captures = _rewrite_specialization_value_captures(
            value,
            caller_substitutions=effective_caller_substitutions,
            member=member,
            token_prefix=(
                "__wcc_supervision_capture_"
                f"{call.metadata.node_id.rsplit(':', 1)[-1]}_"
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
            f"@provider-supervision:{call.metadata.node_id}"
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
        "__wcc_supervision_inline_"
        f"{call.metadata.node_id.rsplit(':', 1)[-1]}__"
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
    context: _ProviderSupervisionClosureContext,
    member: WccProviderSupervisionMember,
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
    member: WccProviderSupervisionMember,
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
                if field.init
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
) -> WccNameAtom:
    factory = WccIdentityFactory(
        owner_name=binding.metadata.node_id,
        lexical_owner_chain=(
            binding.metadata.scope_id,
            "provider-supervision-inline-ref",
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
    if isinstance(value, WccProviderSupervision):
        return value
    return _substitute_wcc_value(value, substitutions)


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
    return value


def _substitute_wcc_payload(
    value,
    substitutions: Mapping[str, WccValue],
):
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
            if field.init
        }
        if any(
            updates[name] is not getattr(value, name)
            for name in updates
        ):
            return replace(value, **updates)
    return value


def _raise_provider_member_ineligible(
    member: WccProviderSupervisionMember,
    *,
    offending_metadata,
    message: str,
) -> None:
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
            code="provider_supervision_member_ineligible",
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
                code="provider_supervision_member_disqualifying_form",
                message="specialized member contains this disqualifying form",
                span=offending_span,
                form_path=offending_form_path,
                expansion_stack=offending_expansion_stack,
                phase="lowering",
            )
        )
    raise LispFrontendCompileError(tuple(diagnostics))


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
    if isinstance(expr, LoopRecurExpr):
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
        done_node = WccLoopDone(
            metadata=scope.body_metadata(
                role="loop:done",
                type_ref=_infer_expr_type(
                    expr.result_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                ),
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            result=result_value,
        )
        return _wrap_prefix_lets(prefix, done_node)
    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            MaterializeViewExpr,
            FinalizeSelectedItemExpr,
            CallExpr,
            ProcedureCallExpr,
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
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=value,
    )
    return _wrap_prefix_lets(prefix, halt)


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
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )

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
        binding_type = _infer_expr_type(
            binding_expr,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
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
            next_compile_time_bindings[binding_name] = (
                _WccBoundProcedureBinding(
                    capture_values=(
                        *_inherited_bind_proc_capture_values(
                            binding_expr,
                            compile_time_bindings=(
                                local_compile_time_bindings
                            ),
                        ),
                        *(
                            (
                                capture.source_name,
                                capture.alias_atom,
                            )
                            for capture in capture_rows
                        ),
                    ),
                )
            )
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
                runtime_tail_compile_time_bindings,
            )
            return _elaborate_effect_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
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
                runtime_tail_compile_time_bindings,
            )
            return _elaborate_non_tail_match_binding(
                binding_name=binding_name,
                binding_type=binding_type,
                match_expr=binding_expr,
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
                runtime_tail_compile_time_bindings,
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
            runtime_tail_compile_time_bindings,
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
            )

        prefix, value = _body_to_prefix_and_value(binding_body)
        let_node = WccLet(
            metadata=local_scope.body_metadata(
                role=f"let:{binding_name}",
                type_ref=result_type,
                source_span=binding_expr.span,
                form_path=binding_expr.form_path,
                expansion_stack=binding_expr.expansion_stack,
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
                if field.init:
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
) -> tuple[tuple[str, WccValue], ...]:
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
    )
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    loop_scope = scope.child_scope("rec-join", authored_binding_name=expr.binding_name)
    loop_name = f"__wcc_loop_{expr.binding_name}_{loop_scope.scope_id.rsplit(':', 1)[-1]}"
    state_prefix, initial_state = _elaborate_expr_to_value(
        expr.initial_state_expr,
        scope=loop_scope.child_scope("loop-state", authored_binding_name=expr.binding_name),
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
        scope=loop_scope.child_scope("loop-budget", authored_binding_name=expr.binding_name),
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
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
        loop_name=loop_name,
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
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
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
        ),
        loop_name=loop_name,
        params=(WccJoinParam(name=expr.binding_name, type_ref=state_type),),
        budget=budget,
        body=body,
        exhaustion=exhaustion,
        initial_state=initial_state,
    )
    return _wrap_prefix_lets((*state_prefix, *budget_prefix), rec_join)


def _retarget_loop_continue(body: WccBody, *, loop_name: str) -> WccBody:
    if isinstance(body, WccLoopContinue):
        return replace(body, target_name=loop_name)
    if isinstance(body, WccLet):
        return replace(body, body=_retarget_loop_continue(body.body, loop_name=loop_name))
    if isinstance(body, WccCase):
        return replace(
            body,
            arms=tuple(
                WccCaseArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    binding_type_ref=arm.binding_type_ref,
                    body=_retarget_loop_continue(arm.body, loop_name=loop_name),
                )
                for arm in body.arms
            ),
        )
    if isinstance(body, WccIf):
        return replace(
            body,
            then_body=_retarget_loop_continue(body.then_body, loop_name=loop_name),
            else_body=_retarget_loop_continue(body.else_body, loop_name=loop_name),
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
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=expr.member_name,
                literal_kind="enum",
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
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                name=expr.name,
            ),
        )
    if isinstance(expr, PhaseTargetExpr):
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
            ),
        )
    if isinstance(expr, RecordExpr):
        record_type = _require_record_type(expr, type_env=type_env)
        prefix: list[WccLet] = []
        fields: list[tuple[str, WccValue]] = []
        for field_name, field_expr in expr.fields:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("record-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            fields.append((field_name, field_value))
        return (
            tuple(prefix),
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
            ),
        )
    if isinstance(expr, PureOpExpr):
        result_type = _infer_expr_type(
            expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        prefix: list[WccLet] = []
        args: list[WccValue] = []
        for index, arg_expr in enumerate(expr.args):
            arg_body = _elaborate_expr_to_body(
                arg_expr,
                scope=scope.child_scope("pure-op-arg", authored_binding_name=str(index)),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            arg_prefix, arg_value = _body_to_prefix_and_value(arg_body)
            prefix.extend(arg_prefix)
            args.append(arg_value)
        return (
            tuple(prefix),
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
        )
        prefix: list[WccLet] = []
        base_body = _elaborate_expr_to_body(
            expr.base_expr,
            scope=scope.child_scope("record-update-base", authored_binding_name="base"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        base_prefix, base_value = _body_to_prefix_and_value(base_body)
        prefix.extend(base_prefix)
        args: list[WccValue] = [base_value]
        field_names: list[str] = []
        for field_name, field_expr in expr.overrides:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("record-update-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            field_names.append(field_name)
            args.append(field_value)
        return (
            tuple(prefix),
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
        prefix: list[WccLet] = []
        fields: list[tuple[str, WccValue]] = []
        for field_name, field_expr in expr.fields:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("union-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            fields.append((field_name, field_value))
        return (
            tuple(prefix),
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
        return (
            (),
            WccOpaqueFrontendValue(
                metadata=scope.value_metadata(
                    role="opaque:IfExpr",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr=expr,
            ),
        )
    raise TypeError(f"unsupported WCC elaboration node: {type(expr).__name__}")


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
    )
    if isinstance(
        expr.subject,
        (
            ProviderResultExpr,
            CommandResultExpr,
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
    subject = _elaborate_atomic_value(
        expr.subject,
        scope=scope.child_scope("match-subject", authored_binding_name="subject"),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return _elaborate_match_case_with_subject(
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
                scope=scope.child_scope("match-arm", authored_binding_name=arm.binding_name),
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
    )
    condition_prefix, condition = _elaborate_expr_to_value(
        expr.condition_expr,
        scope=scope.child_scope("if-condition"),
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
        expr.condition_expr,
        type_ref=PrimitiveTypeRef(name="Bool"),
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
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
        else_body=_elaborate_expr_to_body(
            expr.else_expr,
            scope=scope.child_scope("if-else"),
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
    return _wrap_prefix_lets(condition_prefix, if_body)


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
    return WccCaseArm(
        variant_name=arm.variant_name,
        binding_name=arm.binding_name,
        binding_type_ref=binding_type_ref,
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


def _elaborate_non_tail_match_binding(
    *,
    binding_name: str,
    binding_type: TypeRef,
    match_expr: MatchExpr,
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
) -> WccBody:
    join_name = _generated_join_name(scope, binding_name=binding_name)
    case_body = _elaborate_match_to_body(
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


def _elaborate_effect_binding_to_body(
    *,
    binding_name: str,
    binding_type: TypeRef,
    binding_expr,
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
    normalized_expr, direct_bound_proc_args = (
        _prebind_direct_bind_proc_arguments(
            normalized_expr,
            scope=scope.child_scope(
                "effect-proc-args",
                authored_binding_name=binding_name,
            ),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            compile_time_bindings=compile_time_bindings,
        )
    )
    binding_value_env = {
        **value_env,
        **{
            name: type_ref
            for name, type_ref, _ in match_bindings
        },
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
    current: WccBody = WccLet(
        metadata=scope.body_metadata(
            role=f"let:{binding_name}",
            type_ref=let_result_type,
            source_span=binding_expr.span,
            form_path=binding_expr.form_path,
            expansion_stack=binding_expr.expansion_stack,
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
    for arg_name, arg_type, prebound_expr in reversed(match_bindings):
        if isinstance(prebound_expr, MatchExpr):
            current = _elaborate_non_tail_match_binding(
                binding_name=arg_name,
                binding_type=arg_type,
                match_expr=prebound_expr,
                continuation=current,
                scope=scope.child_scope("effect-arg-match", authored_binding_name=arg_name),
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
        prebound_body = _elaborate_expr_to_body(
            prebound_expr,
            scope=prebound_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        prebound_prefix, prebound_value = _body_to_prefix_and_value(prebound_body)
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
                            compile_time_bindings=(
                                compile_time_bindings
                            ),
                        ),
                        *(
                            (
                                capture.source_name,
                                capture.alias_atom,
                            )
                            for capture in capture_aliases
                        ),
                    ),
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

    def replace_arg(arg_expr, *, role: str):
        if not isinstance(arg_expr, (MatchExpr, LetStarExpr)):
            return arg_expr
        binding_type = _infer_expr_type(
            arg_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
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
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    metadata_kwargs = dict(
        type_ref=result_type,
        source_span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
        effect_summary=effect_summary,
        phase_scope=active_phase_scope,
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
        for field_name, field_expr in (
            ("model", expr.model),
            ("effort", expr.effort),
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
            prompt_name=_require_name_expr(expr.prompt),
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
        return WccPerform(
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
        return WccPerform(
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
    if isinstance(expr, ProcedureCallExpr):
        specialized_name = procedure_edges_by_site.get((expr.span, expr.form_path), expr.callee_name)
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
                )
                for name, value in compile_time_callee.capture_values
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
                    )
                    for name, value in compile_time_arg.capture_values
                )
        return WccCall(
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
                for index, item in enumerate(expr.args)
                if not (
                    _is_compile_time_reference_value(item)
                    or (
                        isinstance(item, NameExpr)
                        and _is_compile_time_reference_value(
                            compile_time_bindings.get(item.name)
                        )
                    )
                )
            ),
            specialization_captures=tuple(
                specialization_captures
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


def _generated_effect_binding_name_from_scope(scope: WccIdentityFactory, *, role: str) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    return f"__wcc_effect_{safe_role}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _generated_value_binding_name_from_scope(scope: WccIdentityFactory, *, role: str) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    return f"__wcc_value_{safe_role}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _require_record_type(expr: RecordExpr, *, type_env: FrontendTypeEnvironment) -> RecordTypeRef:
    resolved = type_env.resolve_type(
        expr.type_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not isinstance(resolved, RecordTypeRef):
        raise TypeError(f"expected record type for `{expr.type_name}`")
    return resolved


def _require_union_type(expr: UnionVariantExpr, *, type_env: FrontendTypeEnvironment) -> UnionTypeRef:
    resolved = type_env.resolve_type(
        expr.type_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
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
) -> TypeRef:
    if isinstance(expr, LiteralExpr):
        return {
            "string": PrimitiveTypeRef(name="String"),
            "int": PrimitiveTypeRef(name="Int"),
            "bool": PrimitiveTypeRef(name="Bool"),
            "float": PrimitiveTypeRef(name="Float"),
        }[expr.literal_kind]
    if isinstance(expr, EnumMemberExpr):
        return type_env.resolve_type(
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
                ),
            )
            for field in expr.fields
        )
        metadata = carrier_metadata_for_expr(
            expr,
            field_signature=tuple((field_name, field_type.name) for field_name, field_type in field_types),
            field_types=field_types,
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
        )
    if isinstance(expr, RecordUpdateExpr):
        return _infer_expr_type(
            expr.base_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, FieldAccessExpr):
        current: TypeRef = value_env[expr.base.name]
        for field_name in expr.fields:
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
            )
            for arg in expr.args
        )
        operator = expr.operator
        if operator in {"=", "!=", "<", "<=", ">", ">=", "and", "or", "not", "some?"}:
            return PrimitiveTypeRef(name="Bool")
        if operator in {"+", "-", "*", "min", "max"}:
            if not arg_types:
                raise TypeError(f"pure operator `{operator}` requires arguments during WCC inference")
            return arg_types[0]
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
        raise TypeError(f"unsupported WCC pure operator inference `{operator}`")
    if isinstance(expr, ContinueExpr):
        state_type = _infer_expr_type(
            expr.state_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        return LoopControlTypeRef(state_type_ref=state_type, result_type_ref=None)
    if isinstance(expr, DoneExpr):
        result_type = _infer_expr_type(
            expr.result_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        return LoopControlTypeRef(state_type_ref=result_type, result_type_ref=result_type)
    if isinstance(expr, LoopRecurExpr):
        state_type = _infer_expr_type(
            expr.initial_state_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        loop_env = dict(value_env)
        loop_env[expr.binding_name] = state_type
        body_type = _infer_expr_type(
            expr.body_expr,
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
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
            )
        raise TypeError("loop/recur body must expose a done result type")
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        for binding_name, binding_expr in expr.bindings:
            local_env[binding_name] = _infer_expr_type(
                binding_expr,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            )
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, IfExpr):
        then_type = _infer_expr_type(
            expr.then_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        else_type = _infer_expr_type(
            expr.else_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
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
            )
            for binding in expr.bindings
        }
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env={**value_env, **member_types},
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, WithPhaseExpr):
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, ProviderBundlePathExpr):
        return _resolve_wcc_type_name(
            expr.target_type_name,
            type_env=type_env,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(
        expr,
        (
            ProviderResultExpr,
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
