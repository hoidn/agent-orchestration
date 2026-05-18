"""Typed Stage 1 definition AST and elaboration helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .sexpr import BoolAtom, KeywordAtom, ListExpr, StringAtom, SymbolAtom
from .spans import SourceSpan
from .syntax import SyntaxNode, WorkflowLispSyntaxModule


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


@dataclass(frozen=True)
class UnionVariant:
    """One union variant."""

    name: str
    fields: tuple[RecordField, ...]
    span: SourceSpan


@dataclass(frozen=True)
class EnumDef:
    """One Stage 1 enum definition."""

    name: str
    values: tuple[EnumValue, ...]
    span: SourceSpan


@dataclass(frozen=True)
class PathDef:
    """One Stage 1 path-contract definition."""

    name: str
    kind: str
    under: str
    must_exist: bool
    span: SourceSpan


@dataclass(frozen=True)
class RecordDef:
    """One Stage 1 record definition."""

    name: str
    fields: tuple[RecordField, ...]
    span: SourceSpan


@dataclass(frozen=True)
class UnionDef:
    """One Stage 1 union definition."""

    name: str
    variants: tuple[UnionVariant, ...]
    span: SourceSpan


DefinitionNode = EnumDef | PathDef | RecordDef | UnionDef


@dataclass(frozen=True)
class WorkflowLispModule:
    """Typed Stage 1 module after syntax elaboration."""

    language_version: str
    target_dsl_version: str
    definitions: tuple[DefinitionNode, ...]
    span: SourceSpan


def elaborate_definition_module(module: WorkflowLispSyntaxModule) -> WorkflowLispModule:
    """Elaborate syntax-layer top-level forms into typed Stage 1 definitions."""

    definitions: list[DefinitionNode] = []
    for form in module.forms:
        definitions.append(_elaborate_top_level_form(form))
    return WorkflowLispModule(
        language_version=module.language_version,
        target_dsl_version=module.target_dsl_version,
        definitions=tuple(definitions),
        span=module.span,
    )


def _elaborate_top_level_form(form: SyntaxNode) -> DefinitionNode:
    datum = form.datum
    if not isinstance(datum, ListExpr) or not datum.items:
        _raise_error("top-level forms must be non-empty lists", span=form.span, form_path=form.form_path)
    head = datum.items[0]
    if not isinstance(head, SymbolAtom):
        _raise_error("top-level forms must start with a symbol", span=head.span, form_path=form.form_path)
    if head.value == "defenum":
        return _elaborate_defenum(form, datum)
    if head.value == "defpath":
        return _elaborate_defpath(form, datum)
    if head.value == "defrecord":
        return _elaborate_defrecord(form, datum)
    if head.value == "defunion":
        return _elaborate_defunion(form, datum)
    _raise_error(
        f"unsupported top-level definition form `{head.value}`",
        code="definition_form_unknown",
        span=head.span,
        form_path=form.form_path,
    )


def _elaborate_defenum(form: SyntaxNode, datum: ListExpr) -> EnumDef:
    name = _expect_symbol(datum, 1, "enum name", form_path=form.form_path)
    raw_values = datum.items[2:]
    if not raw_values:
        _raise_error("`defenum` requires at least one value", span=datum.span, form_path=form.form_path)
    values = []
    for raw_value in raw_values:
        if not isinstance(raw_value, SymbolAtom):
            _raise_error("enum values must be symbols", span=raw_value.span, form_path=form.form_path)
        values.append(EnumValue(name=raw_value.value, span=raw_value.span))
    return EnumDef(name=name.value, values=tuple(values), span=datum.span)


def _elaborate_defpath(form: SyntaxNode, datum: ListExpr) -> PathDef:
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
        if not isinstance(keyword_node, KeywordAtom):
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
    if not isinstance(kind_node, SymbolAtom) or kind_node.value != "relpath":
        _raise_error(
            "`defpath :kind` must be `relpath` in Stage 1",
            code="path_definition_invalid",
            span=kind_node.span,
            form_path=form.form_path,
        )
    if not isinstance(under_node, StringAtom):
        _raise_error(
            "`defpath :under` must be a string",
            code="path_definition_invalid",
            span=under_node.span,
            form_path=form.form_path,
        )
    if not isinstance(must_exist_node, BoolAtom):
        _raise_error(
            "`defpath :must-exist` must be a boolean",
            code="path_definition_invalid",
            span=must_exist_node.span,
            form_path=form.form_path,
        )
    return PathDef(
        name=name.value,
        kind=kind_node.value,
        under=under_node.value,
        must_exist=must_exist_node.value,
        span=datum.span,
    )


def _elaborate_defrecord(form: SyntaxNode, datum: ListExpr) -> RecordDef:
    name = _expect_symbol(datum, 1, "record name", form_path=form.form_path)
    raw_fields = datum.items[2:]
    if not raw_fields:
        _raise_error("`defrecord` requires at least one field", span=datum.span, form_path=form.form_path)
    fields = tuple(_elaborate_field(raw_field, form.form_path) for raw_field in raw_fields)
    return RecordDef(name=name.value, fields=fields, span=datum.span)


def _elaborate_defunion(form: SyntaxNode, datum: ListExpr) -> UnionDef:
    name = _expect_symbol(datum, 1, "union name", form_path=form.form_path)
    raw_variants = datum.items[2:]
    if not raw_variants:
        _raise_error("`defunion` requires at least one variant", span=datum.span, form_path=form.form_path)
    variants: list[UnionVariant] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, ListExpr) or not raw_variant.items:
            _raise_error("union variants must be non-empty lists", span=raw_variant.span, form_path=form.form_path)
        variant_name = raw_variant.items[0]
        if not isinstance(variant_name, SymbolAtom):
            _raise_error("union variant names must be symbols", span=variant_name.span, form_path=form.form_path)
        fields = tuple(_elaborate_field(raw_field, form.form_path) for raw_field in raw_variant.items[1:])
        variants.append(
            UnionVariant(
                name=variant_name.value,
                fields=fields,
                span=raw_variant.span,
            )
        )
    return UnionDef(name=name.value, variants=tuple(variants), span=datum.span)


def _elaborate_field(raw_field: object, form_path: tuple[str, ...]) -> RecordField:
    if not isinstance(raw_field, ListExpr) or len(raw_field.items) != 2:
        span = raw_field.span if hasattr(raw_field, "span") else None
        if span is None:
            raise TypeError("field entries must carry spans")
        _raise_error(
            "field entries must be two-item lists of `(name Type)`",
            span=span,
            form_path=form_path,
        )
    field_name = raw_field.items[0]
    field_type = raw_field.items[1]
    if not isinstance(field_name, SymbolAtom):
        _raise_error("field names must be symbols", span=field_name.span, form_path=form_path)
    if not isinstance(field_type, SymbolAtom):
        _raise_error("field type references must be symbols", span=field_type.span, form_path=form_path)
    return RecordField(name=field_name.value, type_name=field_type.value, span=raw_field.span)


def _expect_symbol(
    datum: ListExpr,
    index: int,
    label: str,
    *,
    form_path: tuple[str, ...],
) -> SymbolAtom:
    if len(datum.items) <= index:
        _raise_error(f"missing {label}", span=datum.span, form_path=form_path)
    value = datum.items[index]
    if not isinstance(value, SymbolAtom):
        _raise_error(f"{label} must be a symbol", span=value.span, form_path=form_path)
    return value


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
