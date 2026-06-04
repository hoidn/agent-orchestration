"""Typecheck owner for authored loop-state carriers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha1
import re

from .diagnostics import LispFrontendCompileError
from .effects import EMPTY_EFFECT_SUMMARY, merge_effect_summaries
from .expressions import LoopStateField, LoopStateSeedExpr, LoopStateUpdateExpr
from .loops import ensure_loop_projectable_type
from .type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeParamRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
)


@dataclass(frozen=True)
class LoopStateCarrierMetadata:
    """Generated local carrier metadata for one loop-state family."""

    generated_type_name: str
    field_names: tuple[str, ...]
    field_types: tuple[tuple[str, TypeRef], ...]
    source_kind: str


_CARRIER_METADATA_BY_NAME: dict[str, LoopStateCarrierMetadata] = {}
_CARRIER_METADATA_BY_EXPR_KEY: dict[tuple[str, int, int, tuple[str, ...]], LoopStateCarrierMetadata] = {}


def carrier_metadata_for_type(type_ref: TypeRef) -> LoopStateCarrierMetadata | None:
    """Return loop-state metadata for one generated carrier type, if present."""

    if not isinstance(type_ref, RecordTypeRef):
        return None
    return _CARRIER_METADATA_BY_NAME.get(type_ref.name)


def carrier_metadata_for_expr(expr) -> LoopStateCarrierMetadata | None:
    """Return loop-state metadata for one authored seed expression, if present."""

    return _CARRIER_METADATA_BY_EXPR_KEY.get(_expr_metadata_key(expr))


def loop_state_field_origin(expr, field_path: tuple[str, ...]):
    """Return the authored loop-state field node that owns one projected field."""

    if not field_path:
        return None
    field_name = field_path[0]
    if isinstance(expr, LoopStateSeedExpr):
        for field in expr.fields:
            if field.name == field_name:
                return field
        return None
    if isinstance(expr, LoopStateUpdateExpr):
        for override_name, override_expr in expr.overrides:
            if override_name == field_name:
                return override_expr
        return loop_state_field_origin(expr.base_expr, field_path)
    return None


def typecheck_loop_state_expr(
    expr,
    *,
    context,
    recurse,
    typed_factory,
    raise_error,
    type_label,
):
    if isinstance(expr, LoopStateSeedExpr):
        return _typecheck_loop_state_seed(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=typed_factory,
            raise_error=raise_error,
            type_label=type_label,
        )
    if isinstance(expr, LoopStateUpdateExpr):
        return _typecheck_loop_state_update(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=typed_factory,
            raise_error=raise_error,
            type_label=type_label,
        )
    raise TypeError(f"unsupported loop-state expression: {type(expr)!r}")


def _typecheck_loop_state_seed(
    expr: LoopStateSeedExpr,
    *,
    context,
    recurse,
    typed_factory,
    raise_error,
    type_label,
):
    from .typecheck_dispatch import _register_generated_record_type, _type_refs_compatible

    field_effects = []
    rewritten_fields: list[LoopStateField] = []
    resolved_fields: list[tuple[str, TypeRef]] = []
    for field in expr.fields:
        resolved_type, allows_generic_type_param = _resolve_authored_field_type(
            field.type_name,
            context=context,
            span=field.span,
            form_path=field.form_path,
            expansion_stack=field.expansion_stack,
        )
        if not allows_generic_type_param:
            _ensure_no_unresolved_type_params(
                resolved_type,
                field_name=field.name,
                raise_error=raise_error,
                span=field.span,
                form_path=field.form_path,
                expansion_stack=field.expansion_stack,
            )
            _ensure_runtime_transport_allowed(
                resolved_type,
                field_name=field.name,
                raise_error=raise_error,
                span=field.span,
                form_path=field.form_path,
                expansion_stack=field.expansion_stack,
            )
            ensure_loop_projectable_type(
                resolved_type,
                code="loop_state_not_projectable",
                span=field.span,
                form_path=field.form_path,
            )
        typed_value = recurse(field.value_expr)
        if not _type_refs_compatible(resolved_type, typed_value.type_ref):
            raise_error(
                (
                    f"`loop-state` field `{field.name}` expected `{type_label(resolved_type)}` "
                    f"but got `{type_label(typed_value.type_ref)}`"
                ),
                code="loop_state_field_type_mismatch",
                span=field.value_expr.span,
                form_path=field.value_expr.form_path,
                expansion_stack=field.value_expr.expansion_stack,
            )
        field_effects.append(typed_value.effect_summary)
        rewritten_fields.append(
            replace(
                field,
                value_expr=typed_value.expr,
            )
        )
        resolved_fields.append((field.name, resolved_type))

    generated_name = _generated_loop_state_type_name(
        expr,
        context=context,
        field_signature=tuple((name, field_type.name) for name, field_type in resolved_fields),
    )
    _register_generated_record_type(
        context.type_env,
        name=generated_name,
        fields=tuple(resolved_fields),
        span=expr.span,
        form_path=expr.form_path,
    )
    _CARRIER_METADATA_BY_NAME[generated_name] = LoopStateCarrierMetadata(
        generated_type_name=generated_name,
        field_names=tuple(name for name, _ in resolved_fields),
        field_types=tuple(resolved_fields),
        source_kind="seed",
    )
    _CARRIER_METADATA_BY_EXPR_KEY[_expr_metadata_key(expr)] = _CARRIER_METADATA_BY_NAME[generated_name]
    record_type = context.type_env.resolve_type(
        generated_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    assert isinstance(record_type, RecordTypeRef)
    return typed_factory(
        expr=replace(expr, fields=tuple(rewritten_fields)),
        type_ref=record_type,
        effect=merge_effect_summaries(*field_effects) if field_effects else EMPTY_EFFECT_SUMMARY,
    )


def _typecheck_loop_state_update(
    expr: LoopStateUpdateExpr,
    *,
    context,
    recurse,
    typed_factory,
    raise_error,
    type_label,
):
    from .typecheck_dispatch import _type_refs_compatible

    typed_base = recurse(expr.base_expr)
    metadata = carrier_metadata_for_type(typed_base.type_ref)
    if metadata is None:
        raise_error(
            "`loop-state :like` requires a loop-state carrier base",
            code="loop_state_like_not_loop_state",
            span=expr.base_expr.span,
            form_path=expr.base_expr.form_path,
            expansion_stack=expr.base_expr.expansion_stack,
        )
    expected_fields = dict(metadata.field_types)
    override_effects = [typed_base.effect_summary]
    rewritten_overrides: list[tuple[str, object]] = []
    for field_name, field_expr in expr.overrides:
        expected_type = expected_fields.get(field_name)
        if expected_type is None:
            raise_error(
                f"unknown `loop-state` field `{field_name}`",
                code="loop_state_unknown_field",
                span=field_expr.span,
                form_path=field_expr.form_path,
                expansion_stack=field_expr.expansion_stack,
            )
        typed_value = recurse(field_expr)
        if not _type_refs_compatible(expected_type, typed_value.type_ref):
            raise_error(
                (
                    f"`loop-state` field `{field_name}` expected `{type_label(expected_type)}` "
                    f"but got `{type_label(typed_value.type_ref)}`"
                ),
                code="loop_state_field_type_mismatch",
                span=field_expr.span,
                form_path=field_expr.form_path,
                expansion_stack=field_expr.expansion_stack,
            )
        override_effects.append(typed_value.effect_summary)
        rewritten_overrides.append((field_name, typed_value.expr))
    return typed_factory(
        expr=replace(
            expr,
            base_expr=typed_base.expr,
            overrides=tuple(rewritten_overrides),
        ),
        type_ref=typed_base.type_ref,
        effect=merge_effect_summaries(*override_effects),
    )


def _generated_loop_state_type_name(
    expr: LoopStateSeedExpr,
    *,
    context,
    field_signature: tuple[tuple[str, str], ...],
) -> str:
    owner = getattr(context.session_state.workflow_signature, "name", None)
    if owner is None:
        owner = expr.form_path[-1] if expr.form_path else "local"
    normalized_owner = re.sub(r"[^A-Za-z0-9_.-]+", "_", owner)
    digest = sha1(
        repr(
            (
                normalized_owner,
                expr.span.start.path,
                expr.span.start.line,
                expr.span.start.column,
                expr.form_path,
                field_signature,
            )
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"%loop-state.{normalized_owner}.{digest}"


def _resolve_authored_field_type(
    type_name: str,
    *,
    context,
    span,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> tuple[TypeRef, bool]:
    direct_binding = context.value_env.get(type_name)
    if isinstance(direct_binding, _TYPE_REF_CLASSES):
        return direct_binding, isinstance(direct_binding, TypeParamRef)
    try:
        return (
            context.type_env.resolve_type(
                type_name,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            False,
        )
    except LispFrontendCompileError:
        if isinstance(direct_binding, _TYPE_REF_CLASSES):
            return direct_binding, isinstance(direct_binding, TypeParamRef)
        raise


def _ensure_no_unresolved_type_params(
    type_ref: TypeRef,
    *,
    field_name: str,
    raise_error,
    span,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> None:
    unresolved = _first_type_param_ref(type_ref)
    if unresolved is None:
        return
    raise_error(
        f"`loop-state` field `{field_name}` cannot use unresolved type parameter `{unresolved.name}`",
        code="loop_state_unresolved_type_parameter",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def _ensure_runtime_transport_allowed(
    type_ref: TypeRef,
    *,
    field_name: str,
    raise_error,
    span,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> None:
    forbidden = _first_runtime_forbidden_type(type_ref)
    if forbidden is None:
        return
    raise_error(
        f"`loop-state` field `{field_name}` cannot carry runtime-forbidden type `{forbidden}`",
        code="loop_state_runtime_transport_forbidden",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def _first_type_param_ref(type_ref: TypeRef) -> TypeParamRef | None:
    if isinstance(type_ref, TypeParamRef):
        return type_ref
    if isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        return _first_type_param_ref(type_ref.item_type_ref)
    if isinstance(type_ref, MapTypeRef):
        return _first_type_param_ref(type_ref.key_type_ref) or _first_type_param_ref(type_ref.value_type_ref)
    if isinstance(type_ref, WorkflowRefTypeRef):
        for param_type in type_ref.param_type_refs:
            unresolved = _first_type_param_ref(param_type)
            if unresolved is not None:
                return unresolved
        return _first_type_param_ref(type_ref.return_type_ref)
    if isinstance(type_ref, ProcRefTypeRef):
        for param_type in type_ref.param_type_refs:
            unresolved = _first_type_param_ref(param_type)
            if unresolved is not None:
                return unresolved
        return _first_type_param_ref(type_ref.return_type_ref)
    if isinstance(type_ref, RecordTypeRef):
        for field_type in type_ref.field_types.values():
            unresolved = _first_type_param_ref(field_type)
            if unresolved is not None:
                return unresolved
        return None
    if isinstance(type_ref, UnionTypeRef):
        for field_types in type_ref.variant_field_types.values():
            for field_type in field_types.values():
                unresolved = _first_type_param_ref(field_type)
                if unresolved is not None:
                    return unresolved
        return None
    return None


def _first_runtime_forbidden_type(type_ref: TypeRef) -> str | None:
    if isinstance(type_ref, WorkflowRefTypeRef):
        return "WorkflowRef"
    if isinstance(type_ref, ProcRefTypeRef):
        return "ProcRef"
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.name in {"Json", "Provider", "Prompt"}:
        return type_ref.name
    if isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        return _first_runtime_forbidden_type(type_ref.item_type_ref)
    if isinstance(type_ref, MapTypeRef):
        return _first_runtime_forbidden_type(type_ref.key_type_ref) or _first_runtime_forbidden_type(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, RecordTypeRef):
        for field_type in type_ref.field_types.values():
            forbidden = _first_runtime_forbidden_type(field_type)
            if forbidden is not None:
                return forbidden
        return None
    if isinstance(type_ref, UnionTypeRef):
        for field_types in type_ref.variant_field_types.values():
            for field_type in field_types.values():
                forbidden = _first_runtime_forbidden_type(field_type)
                if forbidden is not None:
                    return forbidden
        return None
    return None


def _expr_metadata_key(expr) -> tuple[str, int, int, tuple[str, ...]]:
    return (
        expr.span.start.path,
        expr.span.start.line,
        expr.span.start.column,
        expr.form_path,
    )


_TYPE_REF_CLASSES = (
    PrimitiveTypeRef,
    RecordTypeRef,
    WorkflowRefTypeRef,
    ProcRefTypeRef,
    TypeParamRef,
    OptionalTypeRef,
    ListTypeRef,
    MapTypeRef,
    UnionTypeRef,
)
