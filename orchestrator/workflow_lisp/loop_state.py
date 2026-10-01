"""Typecheck owner for authored loop-state carriers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha1, sha256
import re

from .compiler_session import TypecheckSessionState
from .definitions import RecordDef, RecordField
from .diagnostics import LispFrontendCompileError
from .effects import EMPTY_EFFECT_SUMMARY, merge_effect_summaries
from .expressions import LoopStateField, LoopStateSeedExpr, LoopStateUpdateExpr
from .loops import ensure_loop_projectable_type
from .spans import SourceSpan
from .syntax import (
    SyntaxIdentifier,
    SyntaxKeyword,
    SyntaxList,
    syntax_node_datum,
)
from .type_env import (
    FrontendTypeEnvironment,
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
    type_refs_compatible,
)


@dataclass(frozen=True)
class LoopStateCarrierMetadata:
    """Generated local carrier metadata for one loop-state family."""

    generated_type_name: str
    field_names: tuple[str, ...]
    field_types: tuple[tuple[str, TypeRef], ...]
    type_ref: RecordTypeRef
    source_kind: str
    family: tuple[object, int] | None = field(
        default=None,
        repr=False,
        compare=False,
        hash=False,
        metadata={"json_omit_always": True},
    )


def _type_name(type_ref: TypeRef) -> str:
    return type_ref.name


def _register_generated_record_type(
    type_env: FrontendTypeEnvironment,
    *,
    name: str,
    fields: tuple[tuple[str, TypeRef], ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if type_env._type_refs.get(name) is not None:
        return
    definition = RecordDef(
        name=name,
        fields=tuple(
            RecordField(
                name=field_name,
                type_name=_type_name(field_type),
                span=span,
            )
            for field_name, field_type in fields
        ),
        span=span,
    )
    type_env._type_refs[name] = RecordTypeRef(
        name=name,
        definition=definition,
        field_types={field_name: field_type for field_name, field_type in fields},
    )


def reset_loop_state_metadata(session_state: TypecheckSessionState) -> None:
    """Clear generated loop-state carrier metadata between compile sessions."""

    session_state.loop_carrier_metadata_by_name.clear()
    session_state.loop_carrier_metadata_by_expr_key.clear()
    session_state.loop_carrier_families_by_expr_key.clear()


def retain_loop_carrier_families(
    module_name: str,
    *,
    procedures=(),
    workflows=(),
    session_state: TypecheckSessionState,
) -> None:
    """Associate expanded carrier introductions with declaration-only owners."""

    local_ordinals: dict[tuple[str, str], int] = {}

    def declaration_key(declaration: object) -> str:
        from orchestrator.workflow.pure_expr import canonical_json_for_pure_value

        return canonical_json_for_pure_value(declaration)

    def visit(
        datum,
        *,
        owner_did: list[object],
        top_owner_did: list[object],
        ordinal: list[int],
    ) -> None:
        if not isinstance(datum, SyntaxList) or not datum.items:
            return
        head = datum.items[0]
        head_name = head.resolved_name if isinstance(head, SyntaxIdentifier) else None
        if head_name == "let-proc" and len(datum.items) == 3:
            binding = datum.items[1]
            if isinstance(binding, SyntaxList) and len(binding.items) == 7:
                name = binding.items[0]
                if isinstance(name, SyntaxIdentifier):
                    owner_key = declaration_key(top_owner_did)
                    local_key = (owner_key, name.resolved_name)
                    local_ordinal = local_ordinals.get(local_key, 0)
                    local_ordinals[local_key] = local_ordinal + 1
                    local_did: list[object] = [
                        module_name,
                        "procedure",
                        {
                            "owner": top_owner_did,
                            "name": name.resolved_name,
                            "ordinal": local_ordinal,
                        },
                    ]
                    visit(
                        binding.items[6],
                        owner_did=local_did,
                        top_owner_did=top_owner_did,
                        ordinal=[0],
                    )
            # A local procedure body has its own declaration and ordinal
            # namespace; only its continuation belongs to this owner.
            visit(
                datum.items[2],
                owner_did=owner_did,
                top_owner_did=top_owner_did,
                ordinal=ordinal,
            )
            return

        introduces_carrier = head_name == "list/map-effect"
        if head_name == "loop-state":
            introduces_carrier = not (
                len(datum.items) > 1
                and isinstance(datum.items[1], SyntaxKeyword)
                and datum.items[1].value == ":like"
            )
        if introduces_carrier:
            key = _syntax_metadata_key(datum)
            family = (owner_did, ordinal[0])
            ordinal[0] += 1
            existing = session_state.loop_carrier_families_by_expr_key.get(key)
            if existing is not None and existing != family:
                raise RuntimeError(
                    "expanded loop carrier origin was associated with two declarations"
                )
            session_state.loop_carrier_families_by_expr_key[key] = family

        for item in datum.items:
            visit(
                item,
                owner_did=owner_did,
                top_owner_did=top_owner_did,
                ordinal=ordinal,
            )

    for kind, definitions in (("procedure", procedures), ("workflow", workflows)):
        for definition in definitions:
            declaration: list[object] = [module_name, kind, definition.name]
            visit(
                syntax_node_datum(definition.body),
                owner_did=declaration,
                top_owner_did=declaration,
                ordinal=[0],
            )


def _syntax_metadata_key(datum: SyntaxList) -> tuple[str, int, int, tuple[str, ...]]:
    return (
        datum.span.start.path,
        datum.span.start.line,
        datum.span.start.column,
        datum.form_path,
    )


def carrier_metadata_for_type(
    type_ref: TypeRef,
    *,
    session_state: TypecheckSessionState,
    field_types: tuple[tuple[str, TypeRef], ...] | None = None,
) -> LoopStateCarrierMetadata | None:
    """Return loop-state metadata for one generated carrier type, if present."""

    if not isinstance(type_ref, RecordTypeRef):
        return None
    metadata = session_state.loop_carrier_metadata_by_name.get(type_ref.name)
    if metadata is None:
        return None
    if field_types is not None and not _loop_state_metadata_matches_field_types(
        metadata, field_types
    ):
        return None
    return metadata


def register_known_carrier_type(
    type_env,
    *,
    session_state: TypecheckSessionState,
    type_name: str,
    span,
    form_path: tuple[str, ...],
) -> bool:
    """Re-register one generated loop-state carrier into another type env."""

    metadata = session_state.loop_carrier_metadata_by_name.get(type_name)
    if metadata is None:
        return False
    if type_env._type_refs.get(type_name) is None:
        type_env._type_refs[type_name] = metadata.type_ref
    return True


def register_all_known_carrier_types(
    type_env,
    *,
    session_state: TypecheckSessionState,
    span,
    form_path: tuple[str, ...],
) -> None:
    """Hydrate one type env with every generated loop-state carrier seen so far."""

    for type_name in tuple(session_state.loop_carrier_metadata_by_name):
        register_known_carrier_type(
            type_env,
            session_state=session_state,
            type_name=type_name,
            span=span,
            form_path=form_path,
        )


def carrier_metadata_for_expr(
    expr,
    *,
    session_state: TypecheckSessionState,
    field_signature: tuple[tuple[str, str], ...] | None = None,
    field_types: tuple[tuple[str, TypeRef], ...] | None = None,
) -> LoopStateCarrierMetadata | None:
    """Return loop-state metadata for one authored seed expression, if present."""

    source_key = _expr_metadata_key(expr)
    family = expr.carrier_family or session_state.loop_carrier_families_by_expr_key.get(
        source_key
    )
    family_key = _carrier_metadata_expr_key(source_key, family) if family is not None else source_key
    metadata_rows = [
        metadata
        for key, rows in session_state.loop_carrier_metadata_by_expr_key.items()
        if key == family_key or key == source_key
        for metadata in rows.values()
    ]
    if not metadata_rows and family is None:
        # A typed carrier may have moved away from its source span during
        # expansion. Its retained family selects among those rows.
        metadata_rows = [
            metadata
            for key, rows in session_state.loop_carrier_metadata_by_expr_key.items()
            if key[:4] == source_key
            for metadata in rows.values()
        ]
    if family is not None:
        metadata_rows = [metadata for metadata in metadata_rows if metadata.family == family]
    if not metadata_rows:
        return None
    if field_signature is not None:
        matched = next(
            (
                metadata
                for metadata in metadata_rows
                if tuple((name, type_ref.name) for name, type_ref in metadata.field_types)
                == field_signature
            ),
            None,
        )
        if matched is not None:
            return matched
    if field_types is not None:
        for metadata in metadata_rows:
            if _loop_state_metadata_matches_field_types(metadata, field_types):
                return metadata
    if len(metadata_rows) == 1:
        return metadata_rows[0]
    return metadata_rows[-1]


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
        typed_value = recurse(field.value_expr, expected_type=resolved_type)
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
                type_env=context.type_env,
            )
        if not type_refs_compatible(resolved_type, typed_value.type_ref):
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

    field_signature = tuple((name, field_type.name) for name, field_type in resolved_fields)
    family = expr.carrier_family or context.session_state.loop_carrier_families_by_expr_key.get(
        _expr_metadata_key(expr)
    )
    retained_family = context.session_state.loop_carrier_families_by_expr_key.get(
        _expr_metadata_key(expr)
    )
    if family is not None and retained_family is not None and family != retained_family:
        raise RuntimeError("loop-state carrier family disagrees with its retained source occurrence")
    if family is None and context.compiler_session.closed_program:
        raise RuntimeError(
            "typed loop-state carrier has no retained expanded-declaration family"
        )
    generated_name = _generated_loop_state_type_name(
        expr,
        context=context,
        field_signature=field_signature,
        family=(family if context.compiler_session.closed_program else None),
    )
    _register_generated_record_type(
        context.type_env,
        name=generated_name,
        fields=tuple(resolved_fields),
        span=expr.span,
        form_path=expr.form_path,
    )
    record_type = context.type_env.resolve_type(
        generated_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    assert isinstance(record_type, RecordTypeRef)
    context.session_state.loop_carrier_metadata_by_name[generated_name] = LoopStateCarrierMetadata(
        generated_type_name=generated_name,
        field_names=tuple(name for name, _ in resolved_fields),
        field_types=tuple(resolved_fields),
        type_ref=record_type,
        source_kind="seed",
        family=family,
    )
    typed_expr = replace(expr, carrier_family=family)
    metadata_expr_key = (
        _carrier_metadata_expr_key(_expr_metadata_key(expr), family)
        if family is not None and context.compiler_session.closed_program
        else _expr_metadata_key(expr)
    )
    context.session_state.loop_carrier_metadata_by_expr_key.setdefault(
        metadata_expr_key, {}
    )[field_signature] = (
        context.session_state.loop_carrier_metadata_by_name[generated_name]
    )
    return typed_factory(
        expr=replace(
            typed_expr,
            fields=tuple(rewritten_fields),
        ),
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
    typed_base = recurse(expr.base_expr)
    metadata = carrier_metadata_for_type(
        typed_base.type_ref,
        session_state=context.session_state,
    )
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
        typed_value = recurse(field_expr, expected_type=expected_type)
        if not type_refs_compatible(expected_type, typed_value.type_ref):
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
    family: tuple[object, int] | None,
) -> str:
    owner = getattr(context.session_state.workflow_signature, "name", None)
    if owner is None:
        owner = expr.form_path[-1] if expr.form_path else "local"
    normalized_owner = re.sub(r"[^A-Za-z0-9_-]+", "_", owner).strip("_") or "local"
    if family is None:
        identity = (
            normalized_owner,
            expr.span.start.path,
            expr.span.start.line,
            expr.span.start.column,
            expr.form_path,
            field_signature,
        )
    else:
        identity = (family, field_signature)
    digest = sha1(repr(identity).encode("utf-8")).hexdigest()[:12]
    return f"%loop-state.{normalized_owner}_{digest}"


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


def _carrier_metadata_expr_key(
    source_key: tuple[str, int, int, tuple[str, ...]],
    family: tuple[object, int],
) -> tuple[str, int, int, tuple[str, ...], str]:
    from orchestrator.workflow.pure_expr import canonical_json_for_pure_value

    token = sha256(canonical_json_for_pure_value(family).encode("utf-8")).hexdigest()
    return (*source_key, token)


def _loop_state_metadata_matches_field_types(
    metadata: LoopStateCarrierMetadata,
    field_types: tuple[tuple[str, TypeRef], ...],
) -> bool:
    if len(metadata.field_types) != len(field_types):
        return False
    for (expected_name, expected_type), (actual_name, actual_type) in zip(
        metadata.field_types,
        field_types,
        strict=True,
    ):
        if expected_name != actual_name:
            return False
        if not type_refs_compatible(expected_type, actual_type):
            return False
        if not type_refs_compatible(actual_type, expected_type):
            return False
    return True


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
