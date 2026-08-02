"""Shared typecheck context, diagnostics, and session state."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    PhasedDeliveryDiagnostic,
)

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .compiler_session import CompilerSession, TypecheckSessionState
from .effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from .expressions import ExprNode, LiteralExpr
from .lints import required_lint_diagnostic
from .loops import LoopControlTypeRef
from .parametric_constraints import SharedUnionFieldCapability
from .phase import (
    IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME,
    PHASE_CONTEXT_NAME,
    PhaseScope,
    is_record_definition_named,
)
from .procedure_refs import ResolvedProcRefValue
from .procedures import TypedProcedureDef
from .spans import SourceSpan
from .type_env import TypeRef, UnionTypeRef, VariantCaseTypeRef, type_refs_compatible

if TYPE_CHECKING:
    from .functions import FunctionCatalog


_Key = TypeVar("_Key")
_NestedKey = TypeVar("_NestedKey")
_Value = TypeVar("_Value")


class TypecheckSessionStateCollisionError(RuntimeError):
    """A nested typecheck produced an ambiguous compile-session output."""


@dataclass(frozen=True)
class TypedExpr:
    """One expression paired with its resolved Workflow Lisp type."""

    expr: ExprNode
    type_ref: TypeRef | LoopControlTypeRef
    span: SourceSpan
    form_path: tuple[str, ...]
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY


ValueEnvironment = Mapping[str, TypeRef]


@dataclass(frozen=True)
class LoopTypecheckContext:
    """Active loop typing contract for nested `continue` and `done` forms."""

    state_type_ref: TypeRef
    result_type_ref: TypeRef | None = None


@dataclass(frozen=True)
class TypecheckContext:
    """Recursive typecheck inputs carried through dispatch owners."""

    type_env: object
    value_env: ValueEnvironment
    proof_scope: object
    workflow_catalog: object | None
    procedure_catalog: object | None
    extern_environment: object | None
    command_boundary_environment: object | None
    active_phase_scope: object | None
    procedure_effects_by_name: Mapping[str, EffectSummary]
    workflow_effects_by_name: Mapping[str, EffectSummary]
    proc_ref_resolution_context: object | None
    prompt_catalog: object | None
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...]
    compiler_session: CompilerSession
    session_state: TypecheckSessionState


def snapshot_session_state(state: TypecheckSessionState) -> TypecheckSessionState:
    return TypecheckSessionState(
        function_catalog=state.function_catalog,
        proc_ref_value_env=dict(state.proc_ref_value_env),
        value_expr_env=dict(state.value_expr_env),
        loop_context=list(state.loop_context),
        generated_local_procedures=dict(state.generated_local_procedures),
        let_proc_rewrite_results=dict(state.let_proc_rewrite_results),
        workflow_signature=state.workflow_signature,
        procedure_hidden_context_signature=state.procedure_hidden_context_signature,
        reusable_state_producer_context=(
            None
            if state.reusable_state_producer_context is None
            else dict(state.reusable_state_producer_context)
        ),
        shared_union_field_capabilities=tuple(state.shared_union_field_capabilities),
        loop_carrier_metadata_by_name=dict(
            state.loop_carrier_metadata_by_name
        ),
        loop_carrier_metadata_by_expr_key={
            expr_key: dict(metadata_by_signature)
            for expr_key, metadata_by_signature in (
                state.loop_carrier_metadata_by_expr_key.items()
            )
        },
        run_ref_metadata_by_name=dict(state.run_ref_metadata_by_name),
        run_ref_metadata_by_expr_key={
            expr_key: dict(metadata_by_signature)
            for expr_key, metadata_by_signature in (
                state.run_ref_metadata_by_expr_key.items()
            )
        },
        parametric_specialization_requests=dict(
            state.parametric_specialization_requests
        ),
    )


def restore_session_state(
    state: TypecheckSessionState,
    snapshot: TypecheckSessionState,
) -> None:
    state.function_catalog = snapshot.function_catalog
    state.proc_ref_value_env = snapshot.proc_ref_value_env
    state.value_expr_env = snapshot.value_expr_env
    state.loop_context = list(snapshot.loop_context)
    state.generated_local_procedures = dict(snapshot.generated_local_procedures)
    state.let_proc_rewrite_results = dict(snapshot.let_proc_rewrite_results)
    state.workflow_signature = snapshot.workflow_signature
    state.procedure_hidden_context_signature = snapshot.procedure_hidden_context_signature
    state.reusable_state_producer_context = snapshot.reusable_state_producer_context
    state.shared_union_field_capabilities = tuple(snapshot.shared_union_field_capabilities)
    state.loop_carrier_metadata_by_name = dict(
        snapshot.loop_carrier_metadata_by_name
    )
    state.loop_carrier_metadata_by_expr_key = {
        expr_key: dict(metadata_by_signature)
        for expr_key, metadata_by_signature in (
            snapshot.loop_carrier_metadata_by_expr_key.items()
        )
    }
    state.run_ref_metadata_by_name = dict(snapshot.run_ref_metadata_by_name)
    state.run_ref_metadata_by_expr_key = {
        expr_key: dict(metadata_by_signature)
        for expr_key, metadata_by_signature in (
            snapshot.run_ref_metadata_by_expr_key.items()
        )
    }
    state.parametric_specialization_requests = dict(
        snapshot.parametric_specialization_requests
    )


def _values_match(left: object, right: object) -> bool:
    if left is right:
        return True
    try:
        comparison = left == right
        return comparison if isinstance(comparison, bool) else False
    except Exception:
        return False


def _merge_unique_outputs(
    root_name: str,
    outer: Mapping[_Key, _Value],
    completed: Mapping[_Key, _Value],
    *,
    values_match: Callable[[object, object], bool] = _values_match,
) -> dict[_Key, _Value]:
    merged = dict(outer)
    for key, value in completed.items():
        if key in outer and not values_match(outer[key], value):
            raise TypecheckSessionStateCollisionError(
                f"typecheck session output collision in {root_name}: {key!r}"
            )
        merged[key] = value
    return merged


def _specialization_requests_match(left: object, right: object) -> bool:
    semantic_fields = (
        "base_name",
        "specialized_name",
        "type_bindings",
        "proc_ref_bindings",
        "shared_union_field_capabilities",
        "remaining_params",
    )
    if not all(
        hasattr(left, field_name) and hasattr(right, field_name)
        for field_name in semantic_fields
    ):
        return _values_match(left, right)
    return all(
        _values_match(
            getattr(left, field_name),
            getattr(right, field_name),
        )
        for field_name in semantic_fields
    )


def _merge_nested_unique_outputs(
    root_name: str,
    outer: Mapping[_Key, Mapping[_NestedKey, _Value]],
    completed: Mapping[_Key, Mapping[_NestedKey, _Value]],
    *,
    values_match: Callable[[object, object], bool] = _values_match,
) -> dict[_Key, dict[_NestedKey, _Value]]:
    merged = {key: dict(values) for key, values in outer.items()}
    for key, completed_values in completed.items():
        merged[key] = _merge_unique_outputs(
            root_name,
            outer.get(key, {}),
            completed_values,
            values_match=values_match,
        )
    return merged


def merge_successful_session_outputs(
    outer: TypecheckSessionState,
    completed: TypecheckSessionState,
) -> TypecheckSessionState:
    """Merge persistent nested outputs without changing lexical state."""

    merged = snapshot_session_state(outer)
    merged.generated_local_procedures = _merge_unique_outputs(
        "generated_local_procedures",
        outer.generated_local_procedures,
        completed.generated_local_procedures,
    )
    merged.loop_carrier_metadata_by_name = _merge_unique_outputs(
        "loop_carrier_metadata_by_name",
        outer.loop_carrier_metadata_by_name,
        completed.loop_carrier_metadata_by_name,
    )
    merged.loop_carrier_metadata_by_expr_key = (
        _merge_nested_unique_outputs(
            "loop_carrier_metadata_by_expr_key",
            outer.loop_carrier_metadata_by_expr_key,
            completed.loop_carrier_metadata_by_expr_key,
        )
    )
    from .typecheck_run_ref import run_ref_metadata_equivalent

    merged.run_ref_metadata_by_name = _merge_unique_outputs(
        "run_ref_metadata_by_name",
        outer.run_ref_metadata_by_name,
        completed.run_ref_metadata_by_name,
        values_match=run_ref_metadata_equivalent,
    )
    merged.run_ref_metadata_by_expr_key = _merge_nested_unique_outputs(
        "run_ref_metadata_by_expr_key",
        outer.run_ref_metadata_by_expr_key,
        completed.run_ref_metadata_by_expr_key,
        values_match=run_ref_metadata_equivalent,
    )
    merged.parametric_specialization_requests = _merge_unique_outputs(
        "parametric_specialization_requests",
        outer.parametric_specialization_requests,
        completed.parametric_specialization_requests,
        values_match=_specialization_requests_match,
    )
    return merged


def consume_generated_local_procedures(
    state: TypecheckSessionState,
) -> tuple[TypedProcedureDef, ...]:
    """Return and clear generated `let-proc` procedures from the active pass."""

    procedures = tuple(state.generated_local_procedures.values())
    state.generated_local_procedures = {}
    return procedures


def reset_generated_local_procedure_state(
    state: TypecheckSessionState,
) -> None:
    """Clear compiler-pass-local `let-proc` generated state."""

    state.generated_local_procedures = {}
    state.let_proc_rewrite_results = {}


def set_active_workflow_signature(
    state: TypecheckSessionState,
    signature,
) -> None:
    """Record the current workflow signature for nested typecheck helpers."""

    state.workflow_signature = signature


def clear_active_workflow_signature(state: TypecheckSessionState) -> None:
    """Clear the active workflow signature after finishing one workflow body."""

    state.workflow_signature = None


def set_active_reusable_state_producer_context(
    state: TypecheckSessionState,
    context: Mapping[str, object] | None,
) -> None:
    """Record compiler-owned reuse identity inputs for the active workflow body."""

    state.reusable_state_producer_context = context


def clear_active_reusable_state_producer_context(
    state: TypecheckSessionState,
) -> None:
    """Clear the active compiler-owned reuse identity inputs."""

    state.reusable_state_producer_context = None


def raise_required_lint(
    message: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def raise_error(
    message: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
    notes: tuple[str, ...] = (),
    phased_delivery_diagnostic: PhasedDeliveryDiagnostic | None = None,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
                phase="typecheck",
                notes=notes,
                phased_delivery_diagnostic=phased_delivery_diagnostic,
            ),
        )
    )


def raise_run_ref_placement_invalid(
    expr: ExprNode,
    *,
    reason: str,
    effect_summary: EffectSummary | None = None,
) -> None:
    """Reject child-run work at its owning authored form or call boundary."""

    from .expression_traversal import walk_expr
    from .expressions import RunRefExpr, TrialExpr

    candidates = tuple(walk_expr(expr))
    owner = next(
        (candidate for candidate in candidates if isinstance(candidate, TrialExpr)),
        next(
            (candidate for candidate in candidates if isinstance(candidate, RunRefExpr)),
            expr,
        ),
    )
    from .effects import RunsTrialEffect

    summary_contains_trial = effect_summary is not None and any(
        isinstance(effect, RunsTrialEffect)
        for effect in (
            *effect_summary.direct_effects,
            *effect_summary.transitive_effects,
        )
    )
    if isinstance(owner, TrialExpr) or summary_contains_trial:
        raise_error(
            f"`trial` {reason}",
            code="trial_nested_unsupported",
            span=owner.span,
            form_path=owner.form_path,
            expansion_stack=owner.expansion_stack,
        )
    raise_error(
        f"`run-ref` {reason}",
        code="run_ref_placement_invalid",
        span=owner.span,
        form_path=owner.form_path,
        expansion_stack=owner.expansion_stack,
    )


def _require_normative_phase_ctx_type(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if is_record_definition_named(type_ref, IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME):
        raise_error(
            "generic phase stdlib forms require `PhaseCtx`; the legacy bridge is reserved for the Stage 4 implementation-attempt regression",
            code="phase_ctx_legacy_bridge_invalid",
            span=span,
            form_path=form_path,
        )
    if not is_record_definition_named(type_ref, PHASE_CONTEXT_NAME):
        raise_error(
            "generic phase stdlib forms require `PhaseCtx`",
            code="phase_context_invalid",
            span=span,
            form_path=form_path,
        )


def _require_phase_scope_name_match(
    active_phase_scope: PhaseScope | None,
    *,
    authored_name: str,
    form_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if active_phase_scope is None or active_phase_scope.phase_name == authored_name:
        return
    raise_error(
        f"`{form_name}` name `{authored_name}` must match the active `with-phase` scope `{active_phase_scope.phase_name}`",
        code="phase_scope_name_mismatch",
        span=span,
        form_path=form_path,
    )


def _typed(*, expr: ExprNode, type_ref: TypeRef, effect: EffectSummary) -> TypedExpr:
    return TypedExpr(
        expr=expr,
        type_ref=type_ref,
        effect_summary=effect,
        span=expr.span,
        form_path=expr.form_path,
    )


def _literal_type_name(literal_kind: str) -> str:
    if literal_kind == "string":
        return "String"
    if literal_kind == "int":
        return "Int"
    if literal_kind == "bool":
        return "Bool"
    if literal_kind == "float":
        return "Float"
    raise ValueError(f"unsupported literal kind: {literal_kind}")


def _type_refs_compatible(expected: TypeRef, actual: TypeRef) -> bool:
    return type_refs_compatible(expected, actual)


def _unify_loop_control_types(
    left: TypeRef | LoopControlTypeRef,
    right: TypeRef | LoopControlTypeRef,
) -> LoopControlTypeRef | None:
    """Unify loop-control payloads across match arms when possible."""

    if not isinstance(left, LoopControlTypeRef) or not isinstance(right, LoopControlTypeRef):
        return None
    if left.state_type_ref != right.state_type_ref:
        return None
    if left.result_type_ref is None:
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=right.result_type_ref,
        )
    if right.result_type_ref is None:
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=left.result_type_ref,
        )
    if left.result_type_ref != right.result_type_ref:
        return None
    return LoopControlTypeRef(
        state_type_ref=left.state_type_ref,
        result_type_ref=left.result_type_ref,
    )


def _type_label(type_ref: TypeRef | LoopControlTypeRef) -> str:
    if isinstance(type_ref, LoopControlTypeRef):
        result_label = (
            "?"
            if type_ref.result_type_ref is None
            else _type_label(type_ref.result_type_ref)
        )
        return f"LoopControl[{_type_label(type_ref.state_type_ref)} -> {result_label}]"
    if isinstance(type_ref, VariantCaseTypeRef):
        return f"{type_ref.union_name}.{type_ref.variant_name}"
    return type_ref.name


def _literal_string(expr: ExprNode) -> str | None:
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "string" and isinstance(expr.value, str):
        return expr.value
    return None


def _variant_has_field(variant_type: VariantCaseTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for field in variant_type.definition.fields)


def _union_has_any_field(union_type: UnionTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for variant in union_type.definition.variants for field in variant.fields)


def _span_contains(outer: SourceSpan | None, inner: SourceSpan) -> bool:
    if outer is None:
        return False
    if outer.start.path != inner.start.path or outer.end.path != inner.end.path:
        return False
    return outer.start.offset <= inner.start.offset and inner.end.offset <= outer.end.offset
