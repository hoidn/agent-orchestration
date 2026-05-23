"""Resolved type references used while checking Workflow Lisp expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .definitions import EnumDef, PathDef, RecordDef, UnionDef, UnionVariant, WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourcePosition, SourceSpan
from .type_expressions import (
    ListTypeExpr,
    MapTypeExpr,
    NamedTypeExpr,
    OptionalTypeExpr,
    ParsedTypeExpr,
    WorkflowRefTypeExpr,
    parse_type_expression,
)

if TYPE_CHECKING:
    from .modules import ModuleImportScope


PRELUDE_PRIMITIVE_TYPE_NAMES = frozenset(
    {
        "String",
        "Int",
        "Bool",
        "Json",
        "Provider",
        "Prompt",
        "PathRel",
        "RunId",
        "Symbol",
    }
)


def _prelude_span(name: str) -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(path=f"<prelude:{name}>", line=1, column=1, offset=0),
        end=SourcePosition(path=f"<prelude:{name}>", line=1, column=1, offset=0),
    )


PRELUDE_PATH_TYPES = {
    "Path.state-root": PathDef(
        name="Path.state-root",
        kind="relpath",
        under="state",
        must_exist=False,
        span=_prelude_span("Path.state-root"),
    ),
    "Path.artifact-root": PathDef(
        name="Path.artifact-root",
        kind="relpath",
        under="artifacts",
        must_exist=False,
        span=_prelude_span("Path.artifact-root"),
    ),
}


PRELUDE_TYPE_NAMES = PRELUDE_PRIMITIVE_TYPE_NAMES | frozenset(PRELUDE_PATH_TYPES)


@dataclass(frozen=True)
class PrimitiveTypeRef:
    """One prelude or enum type reference."""

    name: str
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathTypeRef:
    """One resolved path-contract type reference."""

    name: str
    definition: PathDef


@dataclass(frozen=True)
class RecordTypeRef:
    """One resolved record type reference."""

    name: str
    definition: RecordDef
    field_types: dict[str, "TypeRef"]


@dataclass(frozen=True)
class UnionTypeRef:
    """One resolved union type reference."""

    name: str
    definition: UnionDef
    variant_field_types: dict[str, dict[str, "TypeRef"]]


@dataclass(frozen=True)
class VariantCaseTypeRef:
    """One resolved union-variant payload reference."""

    union_name: str
    variant_name: str
    definition: UnionVariant


@dataclass(frozen=True)
class WorkflowRefTypeRef:
    """One compile-time-only workflow reference type."""

    name: str
    param_type_refs: tuple["TypeRef", ...]
    return_type_ref: RecordTypeRef | UnionTypeRef


@dataclass(frozen=True)
class OptionalTypeRef:
    """One resolved optional type reference."""

    name: str
    item_type_ref: "TypeRef"


@dataclass(frozen=True)
class ListTypeRef:
    """One resolved list type reference."""

    name: str
    item_type_ref: "TypeRef"


@dataclass(frozen=True)
class MapTypeRef:
    """One resolved map type reference."""

    name: str
    key_type_ref: "TypeRef"
    value_type_ref: "TypeRef"


TypeRef = (
    PrimitiveTypeRef
    | PathTypeRef
    | RecordTypeRef
    | UnionTypeRef
    | VariantCaseTypeRef
    | WorkflowRefTypeRef
    | OptionalTypeRef
    | ListTypeRef
    | MapTypeRef
)


class FrontendTypeEnvironment:
    """Resolved type lookup helpers derived from module type definitions."""

    def __init__(
        self,
        type_refs: dict[str, TypeRef],
        *,
        import_scope: "ModuleImportScope | None" = None,
        canonical_name_overrides: dict[str, str] | None = None,
        schema_names: frozenset[str] = frozenset(),
    ):
        self._type_refs = dict(type_refs)
        self._import_scope = import_scope
        self._canonical_name_overrides = dict(canonical_name_overrides or {})
        self._schema_names = frozenset(schema_names)

    @classmethod
    def from_module(
        cls,
        module: WorkflowLispModule,
        *,
        import_scope: "ModuleImportScope | None" = None,
        imported_type_refs: dict[str, TypeRef] | None = None,
    ) -> "FrontendTypeEnvironment":
        type_refs: dict[str, TypeRef] = {
            name: PrimitiveTypeRef(name=name) for name in PRELUDE_PRIMITIVE_TYPE_NAMES
        }
        type_refs.update(
            {
                name: PathTypeRef(name=name, definition=definition)
                for name, definition in PRELUDE_PATH_TYPES.items()
            }
        )
        for definition in module.definitions:
            if isinstance(definition, EnumDef):
                type_refs[definition.name] = PrimitiveTypeRef(
                    name=definition.name,
                    allowed_values=tuple(value.name for value in definition.values),
                )
            elif isinstance(definition, PathDef):
                type_refs[definition.name] = PathTypeRef(name=definition.name, definition=definition)
            elif isinstance(definition, RecordDef):
                type_refs[definition.name] = RecordTypeRef(
                    name=definition.name,
                    definition=definition,
                    field_types={},
                )
            elif isinstance(definition, UnionDef):
                type_refs[definition.name] = UnionTypeRef(
                    name=definition.name,
                    definition=definition,
                    variant_field_types={},
                )
        if imported_type_refs:
            type_refs.update(imported_type_refs)
        schema_names = {schema.name for schema in module.schemas}
        if import_scope is not None:
            schema_names.update(import_scope.schema_bindings)
            schema_names.update(import_scope.unqualified_schema_bindings)
            schema_names.update(
                binding.canonical_name
                for binding in (
                    *import_scope.schema_bindings.values(),
                    *import_scope.unqualified_schema_bindings.values(),
                )
            )
        for definition in module.definitions:
            if isinstance(definition, RecordDef):
                record_ref = type_refs.get(definition.name)
                if isinstance(record_ref, RecordTypeRef):
                    record_ref.field_types.update(
                        {
                            field.name: cls._resolve_inline_type(
                                field.type_name,
                                type_refs=type_refs,
                                import_scope=import_scope,
                                span=field.span,
                                form_path=("workflow-lisp", definition.name, field.name),
                            )
                            for field in definition.fields
                        }
                    )
            elif isinstance(definition, UnionDef):
                union_ref = type_refs.get(definition.name)
                if isinstance(union_ref, UnionTypeRef):
                    union_ref.variant_field_types.update(
                        {
                            variant.name: {
                                field.name: cls._resolve_inline_type(
                                    field.type_name,
                                    type_refs=type_refs,
                                    import_scope=import_scope,
                                    span=field.span,
                                    form_path=("workflow-lisp", definition.name, variant.name, field.name),
                                )
                                for field in variant.fields
                            }
                            for variant in definition.variants
                        }
                    )
        return cls(
            type_refs,
            import_scope=import_scope,
            schema_names=frozenset(schema_names),
        )

    def resolve_type(
        self,
        name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> TypeRef:
        return self._resolve_inline_type(
            name,
            type_refs=self._type_refs,
            import_scope=self._import_scope,
            canonical_name_overrides=self._canonical_name_overrides,
            schema_names=self._schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    def record_field(
        self,
        record_type: RecordTypeRef | VariantCaseTypeRef,
        field_name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> TypeRef:
        fields = (
            record_type.definition.fields
            if isinstance(record_type, (RecordTypeRef, VariantCaseTypeRef))
            else ()
        )
        for field in fields:
            if field.name == field_name:
                if isinstance(record_type, RecordTypeRef):
                    resolved = record_type.field_types.get(field_name)
                else:
                    union_type = self._type_refs.get(record_type.union_name)
                    resolved = (
                        union_type.variant_field_types.get(record_type.variant_name, {}).get(field_name)
                        if isinstance(union_type, UnionTypeRef)
                        else None
                    )
                if resolved is not None:
                    return resolved
                return self.resolve_type(
                    field.type_name,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
        _raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    def union_variant(
        self,
        union_type: UnionTypeRef,
        variant_name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> VariantCaseTypeRef:
        for variant in union_type.definition.variants:
            if variant.name == variant_name:
                return VariantCaseTypeRef(
                    union_name=union_type.name,
                    variant_name=variant_name,
                    definition=variant,
                )
        _raise_error(
            f"unknown union variant `{variant_name}` for `{union_type.name}`",
            code="union_variant_unknown",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    def field_exists_in_other_variant(
        self,
        variant_type: VariantCaseTypeRef,
        field_name: str,
    ) -> bool:
        union_type = self._type_refs.get(variant_type.union_name)
        if not isinstance(union_type, UnionTypeRef):
            return False
        for variant in union_type.definition.variants:
            if variant.name == variant_type.variant_name:
                continue
            for field in variant.fields:
                if field.name == field_name:
                    return True
        return False

    @staticmethod
    def _resolve_inline_type(
        name: str,
        *,
        type_refs: dict[str, TypeRef],
        import_scope: "ModuleImportScope | None",
        span: SourceSpan,
        form_path: tuple[str, ...],
        canonical_name_overrides: dict[str, str] | None = None,
        schema_names: frozenset[str] = frozenset(),
        expansion_stack: tuple[object, ...] = (),
    ) -> TypeRef:
        parsed = parse_type_expression(
            name,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        return _resolve_parsed_type_expr(
            parsed,
            authored_name=name,
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides or {},
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )


def _resolve_parsed_type_expr(
    parsed: ParsedTypeExpr,
    *,
    authored_name: str,
    type_refs: dict[str, TypeRef],
    import_scope: "ModuleImportScope | None",
    canonical_name_overrides: dict[str, str],
    schema_names: frozenset[str],
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> TypeRef:
    if isinstance(parsed, NamedTypeExpr):
        return _resolve_named_type(
            parsed.name,
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides,
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(parsed, OptionalTypeExpr):
        item_type_ref = _resolve_parsed_type_expr(
            parsed.item_type,
            authored_name=_render_type_expr(parsed.item_type),
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides,
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        if _type_ref_contains_workflow_ref(item_type_ref):
            _raise_error(
                f"workflow-ref types cannot be nested inside collections in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return OptionalTypeRef(name=authored_name, item_type_ref=item_type_ref)
    if isinstance(parsed, ListTypeExpr):
        item_type_ref = _resolve_parsed_type_expr(
            parsed.item_type,
            authored_name=_render_type_expr(parsed.item_type),
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides,
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        if _type_ref_contains_workflow_ref(item_type_ref):
            _raise_error(
                f"workflow-ref types cannot be nested inside collections in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return ListTypeRef(name=authored_name, item_type_ref=item_type_ref)
    if isinstance(parsed, MapTypeExpr):
        key_type_ref = _resolve_parsed_type_expr(
            parsed.key_type,
            authored_name=_render_type_expr(parsed.key_type),
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides,
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        if not isinstance(key_type_ref, PrimitiveTypeRef) or key_type_ref.name != "String":
            _raise_error(
                f"`Map` keys must resolve to `String` in `{authored_name}`",
                code="collection_key_type_invalid",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        value_type_ref = _resolve_parsed_type_expr(
            parsed.value_type,
            authored_name=_render_type_expr(parsed.value_type),
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides,
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        if _type_ref_contains_workflow_ref(value_type_ref):
            _raise_error(
                f"workflow-ref types cannot be nested inside collections in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return MapTypeRef(
            name=authored_name,
            key_type_ref=key_type_ref,
            value_type_ref=value_type_ref,
        )
    if isinstance(parsed, WorkflowRefTypeExpr):
        param_refs = tuple(
            _resolve_parsed_type_expr(
                param_type,
                authored_name=_render_type_expr(param_type),
                type_refs=type_refs,
                import_scope=import_scope,
                canonical_name_overrides=canonical_name_overrides,
                schema_names=schema_names,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
            for param_type in parsed.param_types
        )
        if any(_type_ref_contains_workflow_ref(param_ref) for param_ref in param_refs):
            _raise_error(
                f"workflow-ref parameters cannot contain workflow refs in `{authored_name}`",
                code="workflow_ref_type_invalid",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return_type_ref = _resolve_parsed_type_expr(
            parsed.return_type,
            authored_name=_render_type_expr(parsed.return_type),
            type_refs=type_refs,
            import_scope=import_scope,
            canonical_name_overrides=canonical_name_overrides,
            schema_names=schema_names,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        if not isinstance(return_type_ref, (RecordTypeRef, UnionTypeRef)):
            _raise_error(
                f"workflow-ref return type must resolve to a record or union in `{authored_name}`",
                code="workflow_ref_type_invalid",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        if _type_ref_contains_workflow_ref(return_type_ref):
            _raise_error(
                f"workflow-ref return types cannot transport workflow refs in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return WorkflowRefTypeRef(
            name=authored_name,
            param_type_refs=param_refs,
            return_type_ref=return_type_ref,
        )
    raise TypeError(f"unsupported parsed type expression: {type(parsed)!r}")


def _resolve_named_type(
    name: str,
    *,
    type_refs: dict[str, TypeRef],
    import_scope: "ModuleImportScope | None",
    canonical_name_overrides: dict[str, str],
    schema_names: frozenset[str],
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> TypeRef:
    lookup_name = canonical_name_overrides.get(name, name)
    local_ref = type_refs.get(lookup_name)
    if local_ref is not None:
        return local_ref
    resolved_name = (
        import_scope.resolve_type_name(
            lookup_name,
            span=span,
            form_path=form_path,
        )
        if import_scope is not None
        else lookup_name
    )
    local_ref = type_refs.get(resolved_name)
    if local_ref is not None:
        return local_ref
    if lookup_name in schema_names or resolved_name in schema_names or (
        import_scope is not None and import_scope.has_visible_schema_name(lookup_name)
    ):
        _raise_error(
            f"schema `{name}` cannot be used as a type",
            code="schema_used_as_type",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    _raise_error(
        f"unknown type `{name}`",
        code="type_unknown",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def _render_type_expr(parsed: ParsedTypeExpr) -> str:
    if isinstance(parsed, NamedTypeExpr):
        return parsed.name
    if isinstance(parsed, OptionalTypeExpr):
        return f"Optional[{_render_type_expr(parsed.item_type)}]"
    if isinstance(parsed, ListTypeExpr):
        return f"List[{_render_type_expr(parsed.item_type)}]"
    if isinstance(parsed, MapTypeExpr):
        return f"Map[{_render_type_expr(parsed.key_type)}, {_render_type_expr(parsed.value_type)}]"
    if isinstance(parsed, WorkflowRefTypeExpr):
        params = " ".join(_render_type_expr(param_type) for param_type in parsed.param_types)
        return f"WorkflowRef[({params}) -> {_render_type_expr(parsed.return_type)}]"
    raise TypeError(f"unsupported parsed type expression: {type(parsed)!r}")


def _type_ref_contains_workflow_ref(type_ref: TypeRef) -> bool:
    if isinstance(type_ref, WorkflowRefTypeRef):
        return True
    if isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        return _type_ref_contains_workflow_ref(type_ref.item_type_ref)
    if isinstance(type_ref, MapTypeRef):
        return _type_ref_contains_workflow_ref(type_ref.key_type_ref) or _type_ref_contains_workflow_ref(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, RecordTypeRef):
        return any(_type_ref_contains_workflow_ref(field_type) for field_type in type_ref.field_types.values())
    if isinstance(type_ref, UnionTypeRef):
        return any(
            _type_ref_contains_workflow_ref(field_type)
            for field_types in type_ref.variant_field_types.values()
            for field_type in field_types.values()
        )
    return False


def _raise_error(
    message: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
