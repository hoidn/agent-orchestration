"""Elaborate type definitions from syntax objects into typed module records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .result_guidance import ResultGuidance, parse_result_guidance
from .spans import SourceSpan
from .syntax import (
    ImportDirective,
    SyntaxBool,
    SyntaxIdentifier,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    WorkflowLispSyntaxModule,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
)

if TYPE_CHECKING:
    from .modules import ModuleImportScope


@dataclass(frozen=True)
class EnumValue:
    """One enum member."""

    name: str
    span: SourceSpan


@dataclass(frozen=True)
class RecordField:
    """One record or variant payload field."""

    name: str
    type_name: str
    span: SourceSpan
    guidance: ResultGuidance | None = field(
        default=None,
        repr=False,
        compare=False,
        metadata={"json_omit_if_none": True},
    )


@dataclass(frozen=True)
class SchemaInclude:
    """One schema include member inside a schema, record, or variant."""

    schema_name: str
    span: SourceSpan


@dataclass(frozen=True)
class SchemaDef:
    """One reusable field-schema definition."""

    name: str
    members: tuple[RecordField | SchemaInclude, ...]
    span: SourceSpan


@dataclass(frozen=True)
class UnionVariant:
    """One union variant."""

    name: str
    fields: tuple[RecordField, ...]
    span: SourceSpan


@dataclass(frozen=True)
class EnumDef:
    """One enum type definition."""

    name: str
    values: tuple[EnumValue, ...]
    span: SourceSpan


@dataclass(frozen=True)
class PathDef:
    """One path-contract type definition."""

    name: str
    kind: str
    under: str
    must_exist: bool
    span: SourceSpan


@dataclass(frozen=True)
class RecordDef:
    """One record type definition."""

    name: str
    fields: tuple[RecordField, ...]
    span: SourceSpan


@dataclass(frozen=True)
class UnionDef:
    """One tagged-union type definition."""

    name: str
    variants: tuple[UnionVariant, ...]
    span: SourceSpan


DefinitionNode = EnumDef | PathDef | RecordDef | UnionDef


@dataclass(frozen=True)
class ResourceDef:
    """One declared resource contract."""

    name: str
    state_type_name: str
    backing_kind: str
    backing_path_input: str | None
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class TransitionUpdateDef:
    """One declared resource transition update operation."""

    op: str
    target: str
    value_expr: object | None
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class TransitionDef:
    """One declared transition contract."""

    name: str
    resource_name: str
    request_type_name: str
    result_type_name: str
    preconditions: tuple[object, ...]
    updates: tuple[TransitionUpdateDef, ...]
    write_set: tuple[str, ...]
    idempotency_fields: tuple[str, ...]
    result_expr: object
    audit_expr: object
    conflict_policy: str
    backend_kind: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class _AuthoredRecordDef:
    name: str
    members: tuple[RecordField | SchemaInclude, ...]
    span: SourceSpan


@dataclass(frozen=True)
class _AuthoredUnionVariant:
    name: str
    members: tuple[RecordField | SchemaInclude, ...]
    span: SourceSpan


@dataclass(frozen=True)
class _AuthoredUnionDef:
    name: str
    variants: tuple[_AuthoredUnionVariant, ...]
    span: SourceSpan


_TopLevelForm = (
    EnumDef
    | PathDef
    | SchemaDef
    | _AuthoredRecordDef
    | _AuthoredUnionDef
    | ResourceDef
    | TransitionDef
)


@dataclass(frozen=True)
class WorkflowLispModule:
    """Module header, imports, exports, and type definitions after elaboration."""

    language_version: str
    target_dsl_version: str
    module_name: str | None
    imports: tuple[ImportDirective, ...]
    exports: tuple[str, ...]
    definitions: tuple[DefinitionNode, ...]
    span: SourceSpan
    schemas: tuple[SchemaDef, ...] = ()
    resources: tuple[ResourceDef, ...] = ()
    transitions: tuple[TransitionDef, ...] = ()


def elaborate_definition_module(
    module: WorkflowLispSyntaxModule,
    *,
    import_scope: "ModuleImportScope | None" = None,
    imported_schemas: Mapping[str, SchemaDef] | None = None,
) -> WorkflowLispModule:
    """Elaborate syntax-layer top-level forms into typed definitions."""

    elaborated_forms: list[_TopLevelForm] = []
    local_schemas: list[SchemaDef] = []
    local_resources: list[ResourceDef] = []
    local_transitions: list[TransitionDef] = []
    for form in module.forms:
        elaborated = _elaborate_top_level_form(form)
        elaborated_forms.append(elaborated)
        if isinstance(elaborated, SchemaDef):
            local_schemas.append(elaborated)
        elif isinstance(elaborated, ResourceDef):
            local_resources.append(elaborated)
        elif isinstance(elaborated, TransitionDef):
            local_transitions.append(elaborated)

    concrete_definitions = _expand_concrete_definitions(
        elaborated_forms,
        local_schemas=tuple(local_schemas),
        import_scope=import_scope,
        imported_schemas=imported_schemas or {},
    )
    return WorkflowLispModule(
        language_version=module.language_version,
        target_dsl_version=module.target_dsl_version,
        module_name=module.module_name,
        imports=module.imports,
        exports=module.exports,
        definitions=concrete_definitions,
        span=module.span,
        schemas=tuple(local_schemas),
        resources=tuple(local_resources),
        transitions=tuple(local_transitions),
    )


def _expand_concrete_definitions(
    forms: tuple[_TopLevelForm, ...] | list[_TopLevelForm],
    *,
    local_schemas: tuple[SchemaDef, ...],
    import_scope: "ModuleImportScope | None",
    imported_schemas: Mapping[str, SchemaDef],
) -> tuple[DefinitionNode, ...]:
    local_schema_map = {schema.name: schema for schema in local_schemas}
    imported_schema_map = dict(imported_schemas)
    schema_cache: dict[str, tuple[RecordField, ...]] = {}
    active_schema_stack: list[str] = []

    for schema in local_schemas:
        _expand_schema_fields(
            schema.name,
            schema=schema,
            local_schema_map=local_schema_map,
            imported_schema_map=imported_schema_map,
            import_scope=import_scope,
            schema_cache=schema_cache,
            active_schema_stack=active_schema_stack,
            include_span=schema.span,
            form_path=("workflow-lisp", "defschema", schema.name),
        )

    definitions: list[DefinitionNode] = []
    for form in forms:
        if isinstance(form, (EnumDef, PathDef)):
            definitions.append(form)
            continue
        if isinstance(form, SchemaDef):
            continue
        if isinstance(form, (ResourceDef, TransitionDef)):
            continue
        if isinstance(form, _AuthoredRecordDef):
            definitions.append(
                RecordDef(
                    name=form.name,
                    fields=_expand_member_fields(
                        form.members,
                        local_schema_map=local_schema_map,
                        imported_schema_map=imported_schema_map,
                        import_scope=import_scope,
                        schema_cache=schema_cache,
                        active_schema_stack=active_schema_stack,
                        form_path=("workflow-lisp", "defrecord", form.name),
                    ),
                    span=form.span,
                )
            )
            continue
        definitions.append(
            UnionDef(
                name=form.name,
                variants=tuple(
                    UnionVariant(
                        name=variant.name,
                        fields=_expand_member_fields(
                            variant.members,
                            local_schema_map=local_schema_map,
                            imported_schema_map=imported_schema_map,
                            import_scope=import_scope,
                            schema_cache=schema_cache,
                            active_schema_stack=active_schema_stack,
                            form_path=("workflow-lisp", "defunion", form.name, variant.name),
                        ),
                        span=variant.span,
                    )
                    for variant in form.variants
                ),
                span=form.span,
            )
        )
    return tuple(definitions)


def _expand_member_fields(
    members: tuple[RecordField | SchemaInclude, ...],
    *,
    local_schema_map: Mapping[str, SchemaDef],
    imported_schema_map: Mapping[str, SchemaDef],
    import_scope: "ModuleImportScope | None",
    schema_cache: dict[str, tuple[RecordField, ...]],
    active_schema_stack: list[str],
    form_path: tuple[str, ...],
) -> tuple[RecordField, ...]:
    contains_schema_include = any(isinstance(member, SchemaInclude) for member in members)
    if not contains_schema_include:
        return tuple(member for member in members if isinstance(member, RecordField))

    expanded_fields: list[RecordField] = []
    seen_fields: set[str] = set()
    for member in members:
        if isinstance(member, RecordField):
            _append_field(
                member,
                seen_fields=seen_fields,
                expanded_fields=expanded_fields,
                form_path=form_path,
                code="record_field_duplicate",
                message=f"duplicate field `{member.name}` in expanded fields",
            )
            continue
        resolved_name, schema = _resolve_schema_reference(
            member.schema_name,
            span=member.span,
            form_path=form_path,
            local_schema_map=local_schema_map,
            imported_schema_map=imported_schema_map,
            import_scope=import_scope,
        )
        for field in _expand_schema_fields(
            resolved_name,
            schema=schema,
            local_schema_map=local_schema_map,
            imported_schema_map=imported_schema_map,
            import_scope=import_scope,
            schema_cache=schema_cache,
            active_schema_stack=active_schema_stack,
            include_span=member.span,
            form_path=form_path,
        ):
            _append_field(
                field,
                seen_fields=seen_fields,
                expanded_fields=expanded_fields,
                form_path=form_path,
                code="record_field_duplicate",
                message=f"duplicate field `{field.name}` in expanded fields",
            )
    return tuple(expanded_fields)


def _expand_schema_fields(
    resolved_name: str,
    *,
    schema: SchemaDef,
    local_schema_map: Mapping[str, SchemaDef],
    imported_schema_map: Mapping[str, SchemaDef],
    import_scope: "ModuleImportScope | None",
    schema_cache: dict[str, tuple[RecordField, ...]],
    active_schema_stack: list[str],
    include_span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[RecordField, ...]:
    cached = schema_cache.get(resolved_name)
    if cached is not None:
        return cached
    if resolved_name in active_schema_stack:
        cycle = " -> ".join([*active_schema_stack, resolved_name])
        _raise_error(
            f"schema cycle detected through `{resolved_name}`: {cycle}",
            code="schema_cycle",
            span=include_span,
            form_path=form_path,
        )

    active_schema_stack.append(resolved_name)
    expanded_fields: list[RecordField] = []
    seen_fields: set[str] = set()
    schema_form_path = ("workflow-lisp", "defschema", schema.name)
    try:
        for member in schema.members:
            if isinstance(member, RecordField):
                _append_field(
                    member,
                    seen_fields=seen_fields,
                    expanded_fields=expanded_fields,
                    form_path=schema_form_path,
                    code="schema_field_duplicate",
                    message=f"duplicate field `{member.name}` after schema expansion",
                )
                continue
            child_name, child_schema = _resolve_schema_reference(
                member.schema_name,
                span=member.span,
                form_path=schema_form_path,
                local_schema_map=local_schema_map,
                imported_schema_map=imported_schema_map,
                import_scope=import_scope,
            )
            for field in _expand_schema_fields(
                child_name,
                schema=child_schema,
                local_schema_map=local_schema_map,
                imported_schema_map=imported_schema_map,
                import_scope=import_scope,
                schema_cache=schema_cache,
                active_schema_stack=active_schema_stack,
                include_span=member.span,
                form_path=schema_form_path,
            ):
                _append_field(
                    field,
                    seen_fields=seen_fields,
                    expanded_fields=expanded_fields,
                    form_path=schema_form_path,
                    code="schema_field_duplicate",
                    message=f"duplicate field `{field.name}` after schema expansion",
                )
    finally:
        active_schema_stack.pop()

    result = tuple(expanded_fields)
    schema_cache[resolved_name] = result
    return result


def _append_field(
    field: RecordField,
    *,
    seen_fields: set[str],
    expanded_fields: list[RecordField],
    form_path: tuple[str, ...],
    code: str,
    message: str,
) -> None:
    if field.name in seen_fields:
        _raise_error(
            message,
            code=code,
            span=field.span,
            form_path=form_path,
        )
    seen_fields.add(field.name)
    expanded_fields.append(field)


def _resolve_schema_reference(
    name: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    local_schema_map: Mapping[str, SchemaDef],
    imported_schema_map: Mapping[str, SchemaDef],
    import_scope: "ModuleImportScope | None",
) -> tuple[str, SchemaDef]:
    local_schema = local_schema_map.get(name)
    if local_schema is not None:
        return name, local_schema
    imported_schema = imported_schema_map.get(name)
    if imported_schema is not None:
        return name, imported_schema
    if import_scope is not None:
        resolved_name = import_scope.resolve_schema_name(
            name,
            span=span,
            form_path=form_path,
        )
        resolved_schema = imported_schema_map.get(resolved_name)
        if resolved_schema is not None:
            return resolved_name, resolved_schema
    _raise_error(
        f"unknown schema `{name}`",
        code="schema_unknown",
        span=span,
        form_path=form_path,
    )


def _elaborate_top_level_form(form: SyntaxNode) -> _TopLevelForm:
    datum = syntax_node_datum(form)
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_error("top-level forms must be non-empty lists", span=form.span, form_path=form.form_path)
    head = syntax_head(form)
    if head is None:
        _raise_error("top-level forms must start with a symbol", span=form.span, form_path=form.form_path)
    if head.resolved_name == "defenum":
        return _elaborate_defenum(form, datum)
    if head.resolved_name == "defpath":
        return _elaborate_defpath(form, datum)
    if head.resolved_name == "defschema":
        return _elaborate_defschema(form, datum)
    if head.resolved_name == "defrecord":
        return _elaborate_defrecord(form, datum)
    if head.resolved_name == "defunion":
        return _elaborate_defunion(form, datum)
    if head.resolved_name == "defresource":
        return _elaborate_defresource(form, datum)
    if head.resolved_name == "deftransition":
        return _elaborate_deftransition(form, datum)
    _raise_error(
        f"unsupported top-level definition form `{head.display_name}`",
        code="definition_form_unknown",
        span=head.span,
        form_path=form.form_path,
    )


def _elaborate_defenum(form: SyntaxNode, datum: SyntaxList) -> EnumDef:
    name = _expect_symbol(datum, 1, "enum name", form_path=form.form_path)
    raw_values = datum.items[2:]
    if not raw_values:
        _raise_error("`defenum` requires at least one value", span=datum.span, form_path=form.form_path)
    values = []
    for raw_value in raw_values:
        value_identifier = syntax_identifier(raw_value)
        if value_identifier is None:
            _raise_error("enum values must be symbols", span=raw_value.span, form_path=form.form_path)
        values.append(EnumValue(name=value_identifier.resolved_name, span=raw_value.span))
    return EnumDef(name=name.resolved_name, values=tuple(values), span=datum.span)


def _elaborate_defpath(form: SyntaxNode, datum: SyntaxList) -> PathDef:
    name = _expect_symbol(datum, 1, "path name", form_path=form.form_path)
    entries = datum.items[2:]
    if len(entries) % 2 != 0:
        _raise_error(
            "`defpath` requires keyword/value pairs",
            code="path_definition_invalid",
            span=datum.span,
            form_path=form.form_path,
        )
    values: dict[str, object] = {}
    spans: dict[str, SourceSpan] = {}
    for index in range(0, len(entries), 2):
        keyword_node = entries[index]
        value_node = entries[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`defpath` entries must start with keywords",
                code="path_definition_invalid",
                span=keyword_node.span,
                form_path=form.form_path,
            )
        if keyword_node.value in values:
            _raise_error(
                f"duplicate path keyword `{keyword_node.value}`",
                code="path_definition_invalid",
                span=keyword_node.span,
                form_path=form.form_path,
            )
        values[keyword_node.value] = value_node
        spans[keyword_node.value] = keyword_node.span
    for required in (":kind", ":under", ":must-exist"):
        if required not in values:
            _raise_error(
                f"missing required keyword `{required}`",
                code="path_definition_invalid",
                span=datum.span,
                form_path=form.form_path,
            )
    kind_node = values[":kind"]
    under_node = values[":under"]
    must_exist_node = values[":must-exist"]
    if not isinstance(kind_node, SyntaxIdentifier) or kind_node.resolved_name != "relpath":
        _raise_error(
            "`defpath :kind` must be `relpath` in Stage 1",
            code="path_definition_invalid",
            span=kind_node.span,
            form_path=form.form_path,
        )
    if not isinstance(under_node, SyntaxString):
        _raise_error(
            "`defpath :under` must be a string",
            code="path_definition_invalid",
            span=under_node.span,
            form_path=form.form_path,
        )
    if not isinstance(must_exist_node, SyntaxBool):
        _raise_error(
            "`defpath :must-exist` must be a boolean",
            code="path_definition_invalid",
            span=must_exist_node.span,
            form_path=form.form_path,
        )
    return PathDef(
        name=name.resolved_name,
        kind=kind_node.resolved_name,
        under=under_node.value,
        must_exist=must_exist_node.value,
        span=datum.span,
    )


def _elaborate_defschema(form: SyntaxNode, datum: SyntaxList) -> SchemaDef:
    name = _expect_symbol(datum, 1, "schema name", form_path=form.form_path)
    raw_members = datum.items[2:]
    if not raw_members:
        _raise_error(
            "`defschema` requires at least one field or include",
            code="schema_definition_invalid",
            span=datum.span,
            form_path=form.form_path,
        )
    return SchemaDef(
        name=name.resolved_name,
        members=tuple(_elaborate_field_member(raw_member, form.form_path) for raw_member in raw_members),
        span=datum.span,
    )


def _elaborate_defrecord(form: SyntaxNode, datum: SyntaxList) -> _AuthoredRecordDef:
    name = _expect_symbol(datum, 1, "record name", form_path=form.form_path)
    raw_members = datum.items[2:]
    return _AuthoredRecordDef(
        name=name.resolved_name,
        members=tuple(_elaborate_field_member(raw_member, form.form_path) for raw_member in raw_members),
        span=datum.span,
    )


def _elaborate_defunion(form: SyntaxNode, datum: SyntaxList) -> _AuthoredUnionDef:
    name = _expect_symbol(datum, 1, "union name", form_path=form.form_path)
    raw_variants = datum.items[2:]
    if not raw_variants:
        _raise_error("`defunion` requires at least one variant", span=datum.span, form_path=form.form_path)
    variants: list[_AuthoredUnionVariant] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, SyntaxList) or not raw_variant.items:
            _raise_error("union variants must be non-empty lists", span=raw_variant.span, form_path=form.form_path)
        variant_name = syntax_identifier(raw_variant.items[0])
        if variant_name is None:
            _raise_error(
                "union variant names must be symbols",
                span=raw_variant.items[0].span,
                form_path=form.form_path,
            )
        fields = tuple(
            _elaborate_field_member(raw_field, form.form_path)
            for raw_field in raw_variant.items[1:]
        )
        variants.append(
            _AuthoredUnionVariant(
                name=variant_name.resolved_name,
                members=fields,
                span=raw_variant.span,
            )
        )
    return _AuthoredUnionDef(name=name.resolved_name, variants=tuple(variants), span=datum.span)


def _elaborate_defresource(form: SyntaxNode, datum: SyntaxList) -> ResourceDef:
    name = _expect_symbol(datum, 1, "resource name", form_path=form.form_path)
    sections = _keyword_argument_map(datum.items[2:], form_path=form.form_path, label="`defresource`")
    for required in (":state-type", ":backing"):
        if required not in sections:
            _raise_error(
                f"`defresource` requires `{required}`",
                code="resource_definition_invalid",
                span=datum.span,
                form_path=form.form_path,
            )
    state_type_identifier = syntax_identifier(sections[":state-type"])
    if state_type_identifier is None:
        _raise_error(
            "`defresource :state-type` must be a symbol",
            code="resource_definition_invalid",
            span=sections[":state-type"].span,
            form_path=form.form_path,
        )
    backing_kind, backing_path_input = _parse_resource_backing(
        sections[":backing"],
        form_path=form.form_path,
    )
    return ResourceDef(
        name=name.resolved_name,
        state_type_name=state_type_identifier.resolved_name,
        backing_kind=backing_kind,
        backing_path_input=backing_path_input,
        span=datum.span,
        form_path=form.form_path,
    )


def _elaborate_deftransition(form: SyntaxNode, datum: SyntaxList) -> TransitionDef:
    from .expressions import elaborate_expression

    name = _expect_symbol(datum, 1, "transition name", form_path=form.form_path)
    sections = _keyword_argument_map(datum.items[2:], form_path=form.form_path, label="`deftransition`")
    for required in (
        ":resource",
        ":request-type",
        ":result-type",
        ":preconditions",
        ":updates",
        ":write-set",
        ":idempotency-fields",
        ":result",
        ":audit",
        ":conflict-policy",
        ":backend",
    ):
        if required not in sections:
            _raise_error(
                f"`deftransition` requires `{required}`",
                code="transition_definition_invalid",
                span=datum.span,
                form_path=form.form_path,
            )
    resource_identifier = syntax_identifier(sections[":resource"])
    request_type_identifier = syntax_identifier(sections[":request-type"])
    result_type_identifier = syntax_identifier(sections[":result-type"])
    conflict_identifier = syntax_identifier(sections[":conflict-policy"])
    backend_identifier = syntax_identifier(sections[":backend"])
    if (
        resource_identifier is None
        or request_type_identifier is None
        or result_type_identifier is None
        or conflict_identifier is None
        or backend_identifier is None
    ):
        _raise_error(
            "`deftransition` requires symbolic `:resource`, `:request-type`, `:result-type`, `:conflict-policy`, and `:backend` values",
            code="transition_definition_invalid",
            span=datum.span,
            form_path=form.form_path,
        )
    preconditions_node = sections[":preconditions"]
    if not isinstance(preconditions_node, SyntaxList):
        _raise_error(
            "`deftransition :preconditions` must be a list",
            code="transition_definition_invalid",
            span=preconditions_node.span,
            form_path=form.form_path,
        )
    updates_node = sections[":updates"]
    if not isinstance(updates_node, SyntaxList):
        _raise_error(
            "`deftransition :updates` must be a list",
            code="transition_definition_invalid",
            span=updates_node.span,
            form_path=form.form_path,
        )
    write_set = _symbol_list(
        sections[":write-set"],
        form_path=form.form_path,
        label="`deftransition :write-set`",
    )
    idempotency_fields = _symbol_list(
        sections[":idempotency-fields"],
        form_path=form.form_path,
        label="`deftransition :idempotency-fields`",
    )
    bound_names = frozenset({"state", "request"})
    preconditions = tuple(
        elaborate_expression(
            SyntaxNode(
                datum=item,
                span=item.span,
                module_path=form.module_path,
                form_path=form.form_path,
            ),
            bound_names=bound_names,
        )
        for item in preconditions_node.items
    )
    updates = tuple(
        _elaborate_transition_update(
            item,
            module_path=form.module_path,
            form_path=form.form_path,
            bound_names=bound_names,
        )
        for item in updates_node.items
    )
    result_expr = elaborate_expression(
        SyntaxNode(
            datum=sections[":result"],
            span=sections[":result"].span,
            module_path=form.module_path,
            form_path=form.form_path,
        ),
        bound_names=bound_names,
    )
    audit_expr = elaborate_expression(
        SyntaxNode(
            datum=sections[":audit"],
            span=sections[":audit"].span,
            module_path=form.module_path,
            form_path=form.form_path,
        ),
        bound_names=bound_names,
    )
    return TransitionDef(
        name=name.resolved_name,
        resource_name=resource_identifier.resolved_name,
        request_type_name=request_type_identifier.resolved_name,
        result_type_name=result_type_identifier.resolved_name,
        preconditions=preconditions,
        updates=updates,
        write_set=write_set,
        idempotency_fields=idempotency_fields,
        result_expr=result_expr,
        audit_expr=audit_expr,
        conflict_policy=conflict_identifier.resolved_name,
        backend_kind=backend_identifier.resolved_name,
        span=datum.span,
        form_path=form.form_path,
    )


def _elaborate_field_member(
    raw_field: object,
    form_path: tuple[str, ...],
) -> RecordField | SchemaInclude:
    if not isinstance(raw_field, SyntaxList) or not raw_field.items:
        span = raw_field.span if hasattr(raw_field, "span") else None
        if span is None:
            raise TypeError("field entries must carry spans")
        _raise_error(
            "field entries must be `(name Type)` or `(:include SchemaName)`",
            code="schema_definition_invalid",
            span=span,
            form_path=form_path,
        )
    if isinstance(raw_field.items[0], SyntaxKeyword):
        return _elaborate_schema_include(raw_field, form_path)
    if len(raw_field.items) < 2:
        _raise_error(
            "field entries must start with `(name Type)`",
            code="schema_definition_invalid",
            span=raw_field.span,
            form_path=form_path,
        )
    field_name = raw_field.items[0]
    field_type = raw_field.items[1]
    field_name_identifier = syntax_identifier(field_name)
    field_type_identifier = syntax_identifier(field_type)
    if field_name_identifier is None:
        _raise_error(
            "field names must be symbols",
            code="schema_definition_invalid",
            span=field_name.span,
            form_path=form_path,
        )
    if field_type_identifier is None:
        _raise_error(
            "field type references must be symbols",
            code="schema_definition_invalid",
            span=field_type.span,
            form_path=form_path,
        )
    return RecordField(
        name=field_name_identifier.resolved_name,
        type_name=field_type_identifier.resolved_name,
        span=raw_field.span,
        guidance=parse_result_guidance(
            raw_field.items[2:],
            form_path=form_path,
            label=f"field `{field_name_identifier.resolved_name}`",
        ),
    )


def _elaborate_schema_include(raw_field: SyntaxList, form_path: tuple[str, ...]) -> SchemaInclude:
    include_keyword = raw_field.items[0]
    assert isinstance(include_keyword, SyntaxKeyword)
    if include_keyword.value != ":include" or len(raw_field.items) != 2:
        _raise_error(
            "schema includes must be exactly `(:include SchemaName)`",
            code="schema_definition_invalid",
            span=raw_field.span,
            form_path=form_path,
        )
    schema_name = syntax_identifier(raw_field.items[1])
    if schema_name is None:
        _raise_error(
            "schema include targets must be symbols",
            code="schema_definition_invalid",
            span=raw_field.items[1].span,
            form_path=form_path,
        )
    return SchemaInclude(schema_name=schema_name.resolved_name, span=raw_field.span)


def _parse_resource_backing(
    raw_value: object,
    *,
    form_path: tuple[str, ...],
) -> tuple[str, str | None]:
    if isinstance(raw_value, SyntaxIdentifier):
        if raw_value.resolved_name != "state-layout":
            _raise_error(
                "`defresource :backing` must be `state-layout` or `(bridge <path-input>)`",
                code="resource_definition_invalid",
                span=raw_value.span,
                form_path=form_path,
            )
        return "state_layout", None
    if not isinstance(raw_value, SyntaxList) or len(raw_value.items) != 2:
        _raise_error(
            "`defresource :backing` must be `state-layout` or `(bridge <path-input>)`",
            code="resource_definition_invalid",
            span=raw_value.span,
            form_path=form_path,
        )
    head = syntax_identifier(raw_value.items[0])
    path_input = syntax_identifier(raw_value.items[1])
    if head is None or head.resolved_name != "bridge" or path_input is None:
        _raise_error(
            "`defresource :backing` bridge form must be `(bridge <path-input>)`",
            code="resource_definition_invalid",
            span=raw_value.span,
            form_path=form_path,
        )
    return "bridge", path_input.resolved_name


def _elaborate_transition_update(
    raw_value: object,
    *,
    module_path: str,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> TransitionUpdateDef:
    from .expressions import elaborate_expression

    if not isinstance(raw_value, SyntaxList) or len(raw_value.items) < 2:
        _raise_error(
            "transition updates must be non-empty operation lists",
            code="transition_definition_invalid",
            span=raw_value.span if hasattr(raw_value, "span") else None,  # type: ignore[arg-type]
            form_path=form_path,
        )
    op_identifier = syntax_identifier(raw_value.items[0])
    target_identifier = syntax_identifier(raw_value.items[1])
    if op_identifier is None or target_identifier is None:
        _raise_error(
            "transition updates require symbolic op and target names",
            code="transition_definition_invalid",
            span=raw_value.span,
            form_path=form_path,
        )
    value_expr = None
    if op_identifier.resolved_name != "clear-field":
        if len(raw_value.items) != 3:
            _raise_error(
                "`set-field` and `append-item` updates require exactly one value expression",
                code="transition_definition_invalid",
                span=raw_value.span,
                form_path=form_path,
            )
        value_expr = elaborate_expression(
            SyntaxNode(
                datum=raw_value.items[2],
                span=raw_value.items[2].span,
                module_path=module_path,
                form_path=form_path,
            ),
            bound_names=bound_names,
        )
    elif len(raw_value.items) != 2:
        _raise_error(
            "`clear-field` updates do not take a value expression",
            code="transition_definition_invalid",
            span=raw_value.span,
            form_path=form_path,
        )
    return TransitionUpdateDef(
        op=op_identifier.resolved_name.replace("-", "_"),
        target=target_identifier.resolved_name,
        value_expr=value_expr,
        span=raw_value.span,
        form_path=form_path,
    )


def _keyword_argument_map(
    entries: tuple[object, ...],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    if len(entries) % 2 != 0:
        _raise_error(
            f"{label} requires keyword/value pairs",
            span=entries[-1].span if entries else None,  # type: ignore[arg-type]
            form_path=form_path,
        )
    values: dict[str, object] = {}
    for index in range(0, len(entries), 2):
        keyword = entries[index]
        value = entries[index + 1]
        if not isinstance(keyword, SyntaxKeyword):
            _raise_error(
                f"{label} entries must start with keywords",
                span=keyword.span,
                form_path=form_path,
            )
        if keyword.value in values:
            _raise_error(
                f"duplicate keyword `{keyword.value}`",
                span=keyword.span,
                form_path=form_path,
            )
        values[keyword.value] = value
    return values


def _symbol_list(
    raw_value: object,
    *,
    form_path: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    if not isinstance(raw_value, SyntaxList):
        _raise_error(
            f"{label} must be a list of symbols",
            span=raw_value.span,
            form_path=form_path,
        )
    values: list[str] = []
    for item in raw_value.items:
        identifier = syntax_identifier(item)
        if identifier is None:
            _raise_error(
                f"{label} must contain only symbols",
                span=item.span,
                form_path=form_path,
            )
        values.append(identifier.resolved_name)
    return tuple(values)


def _expect_symbol(
    datum: SyntaxList,
    index: int,
    label: str,
    *,
    form_path: tuple[str, ...],
) -> SyntaxIdentifier:
    if len(datum.items) <= index:
        _raise_error(f"missing {label}", span=datum.span, form_path=form_path)
    value = datum.items[index]
    identifier = syntax_identifier(value)
    if identifier is None:
        _raise_error(f"{label} must be a symbol", span=value.span, form_path=form_path)
    return identifier


def _raise_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    code: str = "frontend_parse_error",
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )
