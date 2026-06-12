"""Resolved type references used while checking Workflow Lisp expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    ResourceDef,
    TransitionDef,
    UnionDef,
    UnionVariant,
    WorkflowLispModule,
)
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .modules import canonical_callable_key
from .spans import SourcePosition, SourceSpan
from .type_expressions import (
    ListTypeExpr,
    MapTypeExpr,
    NamedTypeExpr,
    OptionalTypeExpr,
    ParsedTypeExpr,
    ProcRefTypeExpr,
    WorkflowRefTypeExpr,
    parse_type_expression,
)

if TYPE_CHECKING:
    from .modules import ModuleImportScope


PRELUDE_PRIMITIVE_TYPE_NAMES = frozenset(
    {
        "String",
        "Int",
        "Float",
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
_STRUCTURAL_CONTEXT_RECORD_NAMES = frozenset(
    {
        "RunCtx",
        "PhaseCtx",
        "ItemCtx",
        "DrainCtx",
        "SelectionCtx",
        "RecoveryCtx",
    }
)


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
class ProcRefTypeRef:
    """One compile-time-only procedure reference type."""

    name: str
    param_type_refs: tuple["TypeRef", ...]
    return_type_ref: "TypeRef"


@dataclass(frozen=True)
class TypeParamRef:
    """One compile-time-only parametric type placeholder."""

    name: str


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
    | ProcRefTypeRef
    | TypeParamRef
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
        resource_defs: Mapping[str, ResourceDef] | None = None,
        transition_defs: Mapping[str, TransitionDef] | None = None,
    ):
        self._type_refs = dict(type_refs)
        self._import_scope = import_scope
        self._canonical_name_overrides = dict(canonical_name_overrides or {})
        self._schema_names = frozenset(schema_names)
        self._resource_defs = dict(resource_defs or {})
        self._transition_defs = dict(transition_defs or {})

    @classmethod
    def from_module(
        cls,
        module: WorkflowLispModule,
        *,
        import_scope: "ModuleImportScope | None" = None,
        imported_type_refs: dict[str, TypeRef] | None = None,
        imported_resource_defs: Mapping[str, ResourceDef] | None = None,
        imported_transition_defs: Mapping[str, TransitionDef] | None = None,
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
                enum_ref = PrimitiveTypeRef(
                    name=definition.name,
                    allowed_values=tuple(value.name for value in definition.values),
                )
                type_refs[definition.name] = enum_ref
                if module.module_name:
                    type_refs[f"{module.module_name}/{definition.name}"] = enum_ref
            elif isinstance(definition, PathDef):
                path_ref = PathTypeRef(name=definition.name, definition=definition)
                type_refs[definition.name] = path_ref
                if module.module_name:
                    type_refs[f"{module.module_name}/{definition.name}"] = path_ref
            elif isinstance(definition, RecordDef):
                record_ref = RecordTypeRef(
                    name=definition.name,
                    definition=definition,
                    field_types={},
                )
                type_refs[definition.name] = record_ref
                if module.module_name:
                    type_refs[f"{module.module_name}/{definition.name}"] = record_ref
            elif isinstance(definition, UnionDef):
                union_ref = UnionTypeRef(
                    name=definition.name,
                    definition=definition,
                    variant_field_types={},
                )
                type_refs[definition.name] = union_ref
                if module.module_name:
                    type_refs[f"{module.module_name}/{definition.name}"] = union_ref
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
                    for field_name, field_type in record_ref.field_types.items():
                        if _type_ref_contains_proc_ref(field_type):
                            _raise_error(
                                f"proc-ref types cannot be transported in record field `{definition.name}.{field_name}`",
                                code="proc_ref_runtime_transport_forbidden",
                                span=next(field.span for field in definition.fields if field.name == field_name),
                                form_path=("workflow-lisp", definition.name, field_name),
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
                    for variant in definition.variants:
                        for field_name, field_type in union_ref.variant_field_types[variant.name].items():
                            if _type_ref_contains_proc_ref(field_type):
                                _raise_error(
                                    "proc-ref types cannot be transported in union payloads "
                                    f"`{definition.name}.{variant.name}.{field_name}`",
                                    code="proc_ref_runtime_transport_forbidden",
                                    span=next(field.span for field in variant.fields if field.name == field_name),
                                    form_path=("workflow-lisp", definition.name, variant.name, field_name),
                                )
        return cls(
            type_refs,
            import_scope=import_scope,
            schema_names=frozenset(schema_names),
            resource_defs=_resource_declaration_map(
                module,
                import_scope=import_scope,
                imported_resource_defs=imported_resource_defs or {},
            ),
            transition_defs=_transition_declaration_map(
                module,
                import_scope=import_scope,
                imported_transition_defs=imported_transition_defs or {},
            ),
        )

    def resolve_type(
        self,
        name: str,
        *,
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        local_type_params: frozenset[str] = frozenset(),
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
            local_type_params=local_type_params,
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
                    union_type = _lookup_type_ref(
                        self._type_refs,
                        record_type.union_name,
                        import_scope=self._import_scope,
                    )
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
        union_type = _lookup_type_ref(
            self._type_refs,
            variant_type.union_name,
            import_scope=self._import_scope,
        )
        if not isinstance(union_type, UnionTypeRef):
            return False
        for variant in union_type.definition.variants:
            if variant.name == variant_type.variant_name:
                continue
            for field in variant.fields:
                if field.name == field_name:
                    return True
        return False

    def resolve_resource_declaration(
        self,
        name: str,
        *,
        code: str = "resource_transition_contract_invalid",
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> ResourceDef:
        lookup_name = name
        if self._import_scope is not None:
            lookup_name = self._import_scope.resolve_resource_name(
                name,
                span=span,
                form_path=form_path,
            )
        resource = self._resource_defs.get(lookup_name) or self._resource_defs.get(name)
        if resource is not None:
            return resource
        _raise_error(
            f"unknown resource `{name}`",
            code=code,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    def resolve_transition_declaration(
        self,
        name: str,
        *,
        code: str = "resource_transition_contract_invalid",
        span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
    ) -> TransitionDef:
        lookup_name = name
        if self._import_scope is not None:
            lookup_name = self._import_scope.resolve_transition_name(
                name,
                span=span,
                form_path=form_path,
            )
        transition = self._transition_defs.get(lookup_name) or self._transition_defs.get(name)
        if transition is not None:
            return transition
        _raise_error(
            f"unknown transition `{name}`",
            code=code,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

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
        local_type_params: frozenset[str] = frozenset(),
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
            local_type_params=local_type_params,
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
    local_type_params: frozenset[str],
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
            local_type_params=local_type_params,
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
            local_type_params=local_type_params,
        )
        if _type_ref_contains_workflow_ref(item_type_ref):
            _raise_error(
                f"workflow-ref types cannot be nested inside collections in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        if _type_ref_contains_proc_ref(item_type_ref):
            _raise_error(
                f"proc-ref types cannot be nested inside collections in `{authored_name}`",
                code="proc_ref_runtime_transport_forbidden",
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
            local_type_params=local_type_params,
        )
        if _type_ref_contains_workflow_ref(item_type_ref):
            _raise_error(
                f"workflow-ref types cannot be nested inside collections in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        if _type_ref_contains_proc_ref(item_type_ref):
            _raise_error(
                f"proc-ref types cannot be nested inside collections in `{authored_name}`",
                code="proc_ref_runtime_transport_forbidden",
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
            local_type_params=local_type_params,
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
            local_type_params=local_type_params,
        )
        if _type_ref_contains_workflow_ref(value_type_ref):
            _raise_error(
                f"workflow-ref types cannot be nested inside collections in `{authored_name}`",
                code="workflow_ref_runtime_transport_forbidden",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        if _type_ref_contains_proc_ref(value_type_ref):
            _raise_error(
                f"proc-ref types cannot be nested inside collections in `{authored_name}`",
                code="proc_ref_runtime_transport_forbidden",
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
                local_type_params=local_type_params,
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
            local_type_params=local_type_params,
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
    if isinstance(parsed, ProcRefTypeExpr):
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
                local_type_params=local_type_params,
            )
            for param_type in parsed.param_types
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
            local_type_params=local_type_params,
        )
        return ProcRefTypeRef(
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
    local_type_params: frozenset[str],
) -> TypeRef:
    if name in local_type_params:
        return TypeParamRef(name=name)
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


def _resource_declaration_map(
    module: WorkflowLispModule,
    *,
    import_scope: "ModuleImportScope | None",
    imported_resource_defs: Mapping[str, ResourceDef],
) -> dict[str, ResourceDef]:
    declarations = dict(imported_resource_defs)
    for resource in module.resources:
        declarations[resource.name] = resource
        if module.module_name:
            declarations[canonical_callable_key(module.module_name, resource.name)] = resource
    if import_scope is not None:
        for binding in import_scope.resource_bindings.values():
            declaration = imported_resource_defs.get(binding.canonical_name)
            if declaration is not None:
                declarations[binding.member_name] = declaration
    return declarations


def _transition_declaration_map(
    module: WorkflowLispModule,
    *,
    import_scope: "ModuleImportScope | None",
    imported_transition_defs: Mapping[str, TransitionDef],
) -> dict[str, TransitionDef]:
    declarations = dict(imported_transition_defs)
    for transition in module.transitions:
        declarations[transition.name] = transition
        if module.module_name:
            declarations[canonical_callable_key(module.module_name, transition.name)] = transition
    if import_scope is not None:
        for binding in import_scope.transition_bindings.values():
            declaration = imported_transition_defs.get(binding.canonical_name)
            if declaration is not None:
                declarations[binding.member_name] = declaration
    return declarations


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
    if isinstance(parsed, ProcRefTypeExpr):
        params = " ".join(_render_type_expr(param_type) for param_type in parsed.param_types)
        params_label = f"({params})" if params else "()"
        return f"ProcRef[{params_label} -> {_render_type_expr(parsed.return_type)}]"
    raise TypeError(f"unsupported parsed type expression: {type(parsed)!r}")


def render_type_ref(type_ref: TypeRef) -> str:
    if isinstance(type_ref, (PrimitiveTypeRef, PathTypeRef, RecordTypeRef, UnionTypeRef, OptionalTypeRef, ListTypeRef, MapTypeRef)):
        return type_ref.name
    if isinstance(type_ref, VariantCaseTypeRef):
        return type_ref.union_name
    if isinstance(type_ref, WorkflowRefTypeRef):
        params = " ".join(render_type_ref(param_type) for param_type in type_ref.param_type_refs)
        params_label = f"({params})" if params else "()"
        return f"WorkflowRef[{params_label} -> {render_type_ref(type_ref.return_type_ref)}]"
    if isinstance(type_ref, ProcRefTypeRef):
        params = " ".join(render_type_ref(param_type) for param_type in type_ref.param_type_refs)
        params_label = render_type_ref(type_ref.param_type_refs[0]) if len(type_ref.param_type_refs) == 1 else f"({params})" if params else "()"
        return f"ProcRef[{params_label} -> {render_type_ref(type_ref.return_type_ref)}]"
    if isinstance(type_ref, TypeParamRef):
        return type_ref.name
    raise TypeError(f"unsupported type ref: {type(type_ref)!r}")


def _render_named_type_ref(name: str) -> str:
    if "::" in name:
        module_name, member_name = name.split("::", 1)
        return f"{module_name}/{member_name}"
    return name


def _lookup_type_ref(
    type_refs: dict[str, TypeRef],
    name: str,
    *,
    import_scope: "ModuleImportScope | None" = None,
) -> TypeRef | None:
    direct = type_refs.get(name)
    if direct is not None:
        return direct
    if import_scope is not None:
        binding = import_scope.unqualified_type_bindings.get(name) or import_scope.type_bindings.get(name)
        if binding is not None:
            resolved = type_refs.get(binding.canonical_name)
            if resolved is not None:
                return resolved
    if "::" in name:
        return type_refs.get(_render_named_type_ref(name))
    if "/" in name:
        module_name, member_name = name.rsplit("/", 1)
        return type_refs.get(f"{module_name}::{member_name}")
    return None


def type_refs_compatible(expected: TypeRef, actual: TypeRef) -> bool:
    """Return whether two resolved type refs denote the same semantic type."""

    if expected == actual:
        return True
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, PrimitiveTypeRef):
        return expected.name == actual.name and expected.allowed_values == actual.allowed_values
    if isinstance(expected, PathTypeRef):
        return expected.definition == actual.definition
    if isinstance(expected, RecordTypeRef):
        if _record_refs_are_structural_contexts(expected, actual):
            return expected.field_types.keys() == actual.field_types.keys() and all(
                type_refs_compatible(expected.field_types[field_name], actual.field_types[field_name])
                for field_name in expected.field_types
            )
        return expected.definition == actual.definition
    if isinstance(expected, UnionTypeRef):
        return expected.definition == actual.definition
    if isinstance(expected, VariantCaseTypeRef):
        return (
            expected.union_name == actual.union_name
            and expected.variant_name == actual.variant_name
            and expected.definition == actual.definition
        )
    if isinstance(expected, WorkflowRefTypeRef):
        return (
            len(expected.param_type_refs) == len(actual.param_type_refs)
            and all(
                type_refs_compatible(expected_param, actual_param)
                for expected_param, actual_param in zip(
                    expected.param_type_refs,
                    actual.param_type_refs,
                    strict=True,
                )
            )
            and type_refs_compatible(expected.return_type_ref, actual.return_type_ref)
        )
    if isinstance(expected, ProcRefTypeRef):
        return (
            len(expected.param_type_refs) == len(actual.param_type_refs)
            and all(
                type_refs_compatible(expected_param, actual_param)
                for expected_param, actual_param in zip(
                    expected.param_type_refs,
                    actual.param_type_refs,
                    strict=True,
                )
            )
            and type_refs_compatible(expected.return_type_ref, actual.return_type_ref)
        )
    if isinstance(expected, TypeParamRef):
        return expected.name == actual.name
    if isinstance(expected, OptionalTypeRef):
        return type_refs_compatible(expected.item_type_ref, actual.item_type_ref)
    if isinstance(expected, ListTypeRef):
        return type_refs_compatible(expected.item_type_ref, actual.item_type_ref)
    if isinstance(expected, MapTypeRef):
        return type_refs_compatible(expected.key_type_ref, actual.key_type_ref) and type_refs_compatible(
            expected.value_type_ref,
            actual.value_type_ref,
        )
    raise TypeError(f"unsupported type ref: {type(expected)!r}")


def _record_refs_are_structural_contexts(expected: RecordTypeRef, actual: RecordTypeRef) -> bool:
    from .context_classification import (
        classify_structural_private_exec_context,
        record_name_lane_fallback,
    )

    expected_name = _record_type_basename(expected)
    actual_name = _record_type_basename(actual)
    if expected_name != actual_name:
        return False
    if (
        classify_structural_private_exec_context(expected) is not None
        and classify_structural_private_exec_context(actual) is not None
    ):
        return True
    if expected_name in _STRUCTURAL_CONTEXT_RECORD_NAMES:
        record_name_lane_fallback("structural_context_record_names")
        return True
    return False


def _record_type_basename(type_ref: RecordTypeRef) -> str:
    return type_ref.definition.name.rsplit("::", 1)[-1].rsplit("/", 1)[-1]


def substitute_type_params(type_ref: TypeRef, bindings: dict[str, TypeRef]) -> TypeRef:
    """Rewrite compile-time type parameters to concrete type refs."""

    if isinstance(type_ref, TypeParamRef):
        return bindings.get(type_ref.name, type_ref)
    if isinstance(type_ref, WorkflowRefTypeRef):
        param_type_refs = tuple(substitute_type_params(param, bindings) for param in type_ref.param_type_refs)
        return_type_ref = substitute_type_params(type_ref.return_type_ref, bindings)
        return WorkflowRefTypeRef(
            name=f"WorkflowRef[({' '.join(render_type_ref(param) for param in param_type_refs)}) -> {render_type_ref(return_type_ref)}]",
            param_type_refs=param_type_refs,
            return_type_ref=return_type_ref,
        )
    if isinstance(type_ref, ProcRefTypeRef):
        param_type_refs = tuple(substitute_type_params(param, bindings) for param in type_ref.param_type_refs)
        return_type_ref = substitute_type_params(type_ref.return_type_ref, bindings)
        params = " ".join(render_type_ref(param) for param in param_type_refs)
        params_label = render_type_ref(param_type_refs[0]) if len(param_type_refs) == 1 else f"({params})" if params else "()"
        return ProcRefTypeRef(
            name=f"ProcRef[{params_label} -> {render_type_ref(return_type_ref)}]",
            param_type_refs=param_type_refs,
            return_type_ref=return_type_ref,
        )
    if isinstance(type_ref, OptionalTypeRef):
        item_type_ref = substitute_type_params(type_ref.item_type_ref, bindings)
        return OptionalTypeRef(
            name=f"Optional[{render_type_ref(item_type_ref)}]",
            item_type_ref=item_type_ref,
        )
    if isinstance(type_ref, ListTypeRef):
        item_type_ref = substitute_type_params(type_ref.item_type_ref, bindings)
        return ListTypeRef(
            name=f"List[{render_type_ref(item_type_ref)}]",
            item_type_ref=item_type_ref,
        )
    if isinstance(type_ref, MapTypeRef):
        key_type_ref = substitute_type_params(type_ref.key_type_ref, bindings)
        value_type_ref = substitute_type_params(type_ref.value_type_ref, bindings)
        return MapTypeRef(
            name=f"Map[{render_type_ref(key_type_ref)}, {render_type_ref(value_type_ref)}]",
            key_type_ref=key_type_ref,
            value_type_ref=value_type_ref,
        )
    if isinstance(type_ref, RecordTypeRef):
        return RecordTypeRef(
            name=type_ref.name,
            definition=type_ref.definition,
            field_types={
                field_name: substitute_type_params(field_type, bindings)
                for field_name, field_type in type_ref.field_types.items()
            },
        )
    if isinstance(type_ref, UnionTypeRef):
        return UnionTypeRef(
            name=type_ref.name,
            definition=type_ref.definition,
            variant_field_types={
                variant_name: {
                    field_name: substitute_type_params(field_type, bindings)
                    for field_name, field_type in field_types.items()
                }
                for variant_name, field_types in type_ref.variant_field_types.items()
            },
        )
    return type_ref


def ensure_no_type_params(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    """Reject unresolved compile-time type parameters at monomorphic boundaries."""

    unresolved = _first_type_param_ref(type_ref)
    if unresolved is None:
        return
    _raise_error(
        f"unresolved procedure type parameter `{unresolved.name}` cannot reach a monomorphic boundary",
        code="type_param_unresolved",
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


def _type_ref_contains_proc_ref(type_ref: TypeRef) -> bool:
    if isinstance(type_ref, ProcRefTypeRef):
        return True
    if isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        return _type_ref_contains_proc_ref(type_ref.item_type_ref)
    if isinstance(type_ref, MapTypeRef):
        return _type_ref_contains_proc_ref(type_ref.key_type_ref) or _type_ref_contains_proc_ref(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, RecordTypeRef):
        return any(_type_ref_contains_proc_ref(field_type) for field_type in type_ref.field_types.values())
    if isinstance(type_ref, UnionTypeRef):
        return any(
            _type_ref_contains_proc_ref(field_type)
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
