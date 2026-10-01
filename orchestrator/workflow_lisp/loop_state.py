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
    DiscriminantTypeRef,
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeParamRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
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
    type_env: FrontendTypeEnvironment | None = None,
) -> LoopStateCarrierMetadata | None:
    """Return loop-state metadata for one generated carrier type, if present."""

    if not isinstance(type_ref, RecordTypeRef):
        return None
    metadata = session_state.loop_carrier_metadata_by_name.get(type_ref.name)
    if metadata is None:
        return None
    if field_types is not None and not _loop_state_metadata_matches_field_types(
        metadata, field_types, type_env=type_env
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
    type_env: FrontendTypeEnvironment | None = None,
) -> LoopStateCarrierMetadata | None:
    """Return loop-state metadata for one authored seed expression, if present."""

    source_key = _expr_metadata_key(expr)
    family = expr.carrier_family or session_state.loop_carrier_families_by_expr_key.get(
        source_key
    )
    family_key = _carrier_metadata_expr_key(source_key, family) if family is not None else source_key
    metadata_rows = [
        (row_key, metadata)
        for outer_key, rows in session_state.loop_carrier_metadata_by_expr_key.items()
        if outer_key == family_key or outer_key == source_key
        for row_key, metadata in rows.items()
    ]
    if not metadata_rows and family is None:
        # A typed carrier may have moved away from its source span during
        # expansion. Its retained family selects among those rows.
        metadata_rows = [
            (row_key, metadata)
            for outer_key, rows in session_state.loop_carrier_metadata_by_expr_key.items()
            if outer_key[:4] == source_key
            for row_key, metadata in rows.items()
        ]
    if family is not None:
        metadata_rows = [
            (key, metadata)
            for key, metadata in metadata_rows
            if metadata.family == family
        ]
    if not metadata_rows:
        return None
    has_concrete_variants = any(
        isinstance(key, tuple)
        and len(key) == 2
        and isinstance(key[1], str)
        and key[1] == metadata.generated_type_name
        for key, metadata in metadata_rows
    )
    metadata_values = [metadata for _, metadata in metadata_rows]
    if has_concrete_variants:
        if field_types is None:
            return None
        matches = [
            metadata
            for metadata in metadata_values
            if _loop_state_metadata_matches_field_types(
                metadata,
                field_types,
                type_env=type_env,
            )
        ]
        return matches[0] if len(matches) == 1 else None
    if field_signature is not None:
        matched = next(
            (
                metadata
                for metadata in metadata_values
                if tuple((name, type_ref.name) for name, type_ref in metadata.field_types)
                == field_signature
            ),
            None,
        )
        if matched is not None:
            return matched
    if field_types is not None:
        for metadata in metadata_values:
            if _legacy_loop_state_metadata_matches_field_types(metadata, field_types):
                return metadata
    return metadata_values[-1] if metadata_values else None


def _select_closed_carrier_variant_name(
    base_name: str,
    *,
    family: tuple[object, int],
    field_signature: tuple[tuple[str, str], ...],
    field_types: tuple[tuple[str, TypeRef], ...],
    session_state: TypecheckSessionState,
    type_env: FrontendTypeEnvironment,
) -> str:
    """Reuse or allocate a provisional name for one exact concrete variant."""

    candidates = [
        metadata
        for metadata in session_state.loop_carrier_metadata_by_name.values()
        if metadata.family == family
        and tuple((name, type_ref.name) for name, type_ref in metadata.field_types)
        == field_signature
    ]
    for metadata in candidates:
        if _loop_state_metadata_matches_field_types(
            metadata,
            field_types,
            type_env=type_env,
        ):
            return metadata.generated_type_name

    if not candidates:
        return base_name
    occupied = set(session_state.loop_carrier_metadata_by_name)
    variant = 1
    while f"{base_name}__variant{variant}" in occupied:
        variant += 1
    return f"{base_name}__variant{variant}"


def _same_concrete_type_origin(
    expected: TypeRef,
    actual: TypeRef,
    *,
    type_env: FrontendTypeEnvironment | None,
    active: set[tuple[int, int]] | None = None,
) -> bool:
    """Match retained type origins, not the language's looser assignability."""

    if expected is actual:
        return True
    if type(expected) is not type(actual):
        return False
    active = active if active is not None else set()
    pair = (id(expected), id(actual))
    if pair in active:
        return True
    active.add(pair)
    try:
        if isinstance(expected, PrimitiveTypeRef):
            if expected.allowed_values != actual.allowed_values:
                return False
            if not expected.allowed_values:
                return expected.name == actual.name
            if type_env is not None:
                expected_owner = (
                    type_env.declaring_module(expected),
                    type_env.declaring_name(expected),
                )
                actual_owner = (
                    type_env.declaring_module(actual),
                    type_env.declaring_name(actual),
                )
                if all(expected_owner) and all(actual_owner):
                    return expected_owner == actual_owner
            return False
        if isinstance(expected, PathTypeRef):
            return _same_nominal_declaration(
                expected,
                actual,
                type_env=type_env,
            )
        if isinstance(expected, RecordTypeRef):
            expected_origin = expected.run_ref_origin
            actual_origin = actual.run_ref_origin
            if expected_origin is not None or actual_origin is not None:
                if (
                    expected_origin is None
                    or actual_origin is None
                    or expected_origin[0] != actual_origin[0]
                    or len(expected_origin[1]) != len(actual_origin[1])
                ):
                    return False
                same_origin_inputs = all(
                    expected_name == actual_name
                    and _same_concrete_type_origin(
                        expected_ref,
                        actual_ref,
                        type_env=type_env,
                        active=active,
                    )
                    for (expected_name, expected_ref), (actual_name, actual_ref) in zip(
                        expected_origin[1], actual_origin[1], strict=True
                    )
                )
                if not same_origin_inputs:
                    return False
                expected_value = expected.field_types.get("value")
                actual_value = actual.field_types.get("value")
                return (
                    tuple(expected.field_types) == tuple(actual.field_types)
                    and expected_value is not None
                    and actual_value is not None
                    and _same_concrete_type_origin(
                        expected_value,
                        actual_value,
                        type_env=type_env,
                        active=active,
                    )
                )
            return (
                _same_nominal_declaration(
                    expected,
                    actual,
                    type_env=type_env,
                )
                and tuple(expected.field_types) == tuple(actual.field_types)
                and all(
                    _same_concrete_type_origin(
                        expected.field_types[name],
                        actual.field_types[name],
                        type_env=type_env,
                        active=active,
                    )
                    for name in expected.field_types
                )
            )
        if isinstance(expected, UnionTypeRef):
            return (
                _same_nominal_declaration(
                    expected,
                    actual,
                    type_env=type_env,
                )
                and len(expected.type_args) == len(actual.type_args)
                and all(
                    _same_concrete_type_origin(
                        expected_arg,
                        actual_arg,
                        type_env=type_env,
                        active=active,
                    )
                    for expected_arg, actual_arg in zip(
                        expected.type_args,
                        actual.type_args,
                        strict=True,
                    )
                )
                and tuple(expected.variant_field_types)
                == tuple(actual.variant_field_types)
                and all(
                    tuple(expected.variant_field_types[variant_name])
                    == tuple(actual.variant_field_types[variant_name])
                    and all(
                        _same_concrete_type_origin(
                            expected.variant_field_types[variant_name][field_name],
                            actual.variant_field_types[variant_name][field_name],
                            type_env=type_env,
                            active=active,
                        )
                        for field_name in expected.variant_field_types[variant_name]
                    )
                    for variant_name in expected.variant_field_types
                )
            )
        if isinstance(expected, VariantCaseTypeRef):
            return (
                expected.definition is actual.definition
                and expected.variant_name == actual.variant_name
                and len(expected.union_type_args) == len(actual.union_type_args)
                and all(
                    _same_concrete_type_origin(
                        expected_arg,
                        actual_arg,
                        type_env=type_env,
                        active=active,
                    )
                    for expected_arg, actual_arg in zip(
                        expected.union_type_args,
                        actual.union_type_args,
                        strict=True,
                    )
                )
                and (
                    expected.field_types is None
                    and actual.field_types is None
                    or expected.field_types is not None
                    and actual.field_types is not None
                    and tuple(expected.field_types) == tuple(actual.field_types)
                    and all(
                        _same_concrete_type_origin(
                            expected.field_types[field_name],
                            actual.field_types[field_name],
                            type_env=type_env,
                            active=active,
                        )
                        for field_name in expected.field_types
                    )
                )
            )
        if isinstance(expected, DiscriminantTypeRef):
            expected_union = expected.owner_union or expected.applied_union
            actual_union = actual.owner_union or actual.applied_union
            if expected_union is None or actual_union is None:
                return (
                    expected_union is None
                    and actual_union is None
                    and expected.union_name == actual.union_name
                    and expected.variant_names == actual.variant_names
                )
            return _same_concrete_type_origin(
                expected_union,
                actual_union,
                type_env=type_env,
                active=active,
            )
        if isinstance(expected, (OptionalTypeRef, ListTypeRef)):
            return _same_concrete_type_origin(
                expected.item_type_ref,
                actual.item_type_ref,
                type_env=type_env,
                active=active,
            )
        if isinstance(expected, MapTypeRef):
            return _same_concrete_type_origin(
                expected.key_type_ref,
                actual.key_type_ref,
                type_env=type_env,
                active=active,
            ) and _same_concrete_type_origin(
                expected.value_type_ref,
                actual.value_type_ref,
                type_env=type_env,
                active=active,
            )
        if isinstance(expected, TypeParamRef):
            return expected.name == actual.name
        if isinstance(expected, (ProcRefTypeRef, WorkflowRefTypeRef)):
            return (
                len(expected.param_type_refs) == len(actual.param_type_refs)
                and all(
                    _same_concrete_type_origin(
                        expected_param,
                        actual_param,
                        type_env=type_env,
                        active=active,
                    )
                    for expected_param, actual_param in zip(
                        expected.param_type_refs,
                        actual.param_type_refs,
                        strict=True,
                    )
                )
                and _same_concrete_type_origin(
                    expected.return_type_ref,
                    actual.return_type_ref,
                    type_env=type_env,
                    active=active,
                )
            )
        return False
    finally:
        active.remove(pair)


def _same_nominal_declaration(
    expected: TypeRef,
    actual: TypeRef,
    *,
    type_env: FrontendTypeEnvironment | None,
) -> bool:
    expected_definition = getattr(expected, "definition", None)
    actual_definition = getattr(actual, "definition", None)
    if expected_definition is actual_definition:
        return True
    if type_env is None:
        return False
    expected_owner = (
        type_env.declaring_module(expected),
        type_env.declaring_name(expected),
    )
    actual_owner = (
        type_env.declaring_module(actual),
        type_env.declaring_name(actual),
    )
    return all(expected_owner) and expected_owner == actual_owner


def _loop_state_metadata_matches_field_types(
    metadata: LoopStateCarrierMetadata,
    field_types: tuple[tuple[str, TypeRef], ...],
    *,
    type_env: FrontendTypeEnvironment | None = None,
) -> bool:
    if len(metadata.field_types) != len(field_types):
        return False
    for (expected_name, expected_type), (actual_name, actual_type) in zip(
        metadata.field_types,
        field_types,
        strict=True,
    ):
        if expected_name != actual_name or not _same_concrete_type_origin(
            expected_type,
            actual_type,
            type_env=type_env,
        ):
            return False
    return True


def _legacy_loop_state_metadata_matches_field_types(
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
        retained_type = field.resolved_type_ref
        if (
            context.compiler_session.closed_program
            and retained_type is not None
            and _first_type_param_ref(
                retained_type,
                include_retained_facts=True,
            )
            is None
        ):
            resolved_type, allows_generic_type_param = retained_type, False
        else:
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
                include_retained_facts=context.compiler_session.closed_program,
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
                resolved_type_ref=(
                    resolved_type
                    if context.compiler_session.closed_program
                    else field.resolved_type_ref
                ),
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
    base_generated_name = generated_name
    if context.compiler_session.closed_program and family is not None:
        generated_name = _select_closed_carrier_variant_name(
            generated_name,
            family=family,
            field_signature=field_signature,
            field_types=tuple(resolved_fields),
            session_state=context.session_state,
            type_env=context.type_env,
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
    )[
        field_signature
        if generated_name == base_generated_name
        else (field_signature, generated_name)
    ] = (
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
        type_env=context.type_env,
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
    include_retained_facts: bool = False,
) -> None:
    unresolved = _first_type_param_ref(
        type_ref,
        include_retained_facts=include_retained_facts,
    )
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


def _first_type_param_ref(
    type_ref: TypeRef,
    *,
    include_retained_facts: bool = False,
) -> TypeParamRef | None:
    if isinstance(type_ref, TypeParamRef):
        return type_ref
    if isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        return _first_type_param_ref(
            type_ref.item_type_ref,
            include_retained_facts=include_retained_facts,
        )
    if isinstance(type_ref, MapTypeRef):
        return _first_type_param_ref(
            type_ref.key_type_ref,
            include_retained_facts=include_retained_facts,
        ) or _first_type_param_ref(
            type_ref.value_type_ref,
            include_retained_facts=include_retained_facts,
        )
    if isinstance(type_ref, WorkflowRefTypeRef):
        for param_type in type_ref.param_type_refs:
            unresolved = _first_type_param_ref(
                param_type,
                include_retained_facts=include_retained_facts,
            )
            if unresolved is not None:
                return unresolved
        return _first_type_param_ref(
            type_ref.return_type_ref,
            include_retained_facts=include_retained_facts,
        )
    if isinstance(type_ref, ProcRefTypeRef):
        for param_type in type_ref.param_type_refs:
            unresolved = _first_type_param_ref(
                param_type,
                include_retained_facts=include_retained_facts,
            )
            if unresolved is not None:
                return unresolved
        return _first_type_param_ref(
            type_ref.return_type_ref,
            include_retained_facts=include_retained_facts,
        )
    if isinstance(type_ref, RecordTypeRef):
        if include_retained_facts and type_ref.run_ref_origin is not None:
            for _, input_type in type_ref.run_ref_origin[1]:
                unresolved = _first_type_param_ref(
                    input_type,
                    include_retained_facts=True,
                )
                if unresolved is not None:
                    return unresolved
        for field_type in type_ref.field_types.values():
            unresolved = _first_type_param_ref(
                field_type,
                include_retained_facts=include_retained_facts,
            )
            if unresolved is not None:
                return unresolved
        return None
    if isinstance(type_ref, UnionTypeRef):
        if include_retained_facts:
            for type_arg in type_ref.type_args:
                unresolved = _first_type_param_ref(
                    type_arg,
                    include_retained_facts=True,
                )
                if unresolved is not None:
                    return unresolved
        for field_types in type_ref.variant_field_types.values():
            for field_type in field_types.values():
                unresolved = _first_type_param_ref(
                    field_type,
                    include_retained_facts=include_retained_facts,
                )
                if unresolved is not None:
                    return unresolved
        return None
    if include_retained_facts and isinstance(type_ref, VariantCaseTypeRef):
        for type_arg in type_ref.union_type_args:
            unresolved = _first_type_param_ref(
                type_arg,
                include_retained_facts=True,
            )
            if unresolved is not None:
                return unresolved
        for field_type in (type_ref.field_types or {}).values():
            unresolved = _first_type_param_ref(
                field_type,
                include_retained_facts=True,
            )
            if unresolved is not None:
                return unresolved
    if include_retained_facts and isinstance(type_ref, DiscriminantTypeRef):
        owner = type_ref.owner_union or type_ref.applied_union
        if owner is not None:
            return _first_type_param_ref(owner, include_retained_facts=True)
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
