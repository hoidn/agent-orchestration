"""Top-level definition shaping for the Workflow Lisp MVP."""

from __future__ import annotations

from dataclasses import dataclass

from .parser import WorkflowLispSyntaxError
from .syntax import AtomKind, ParsedWorkflowModule, SourceSpan, SyntaxAtom, SyntaxDiagnostic, SyntaxList, SyntaxNode


@dataclass(frozen=True)
class DefinitionTypeRef:
    """Type reference used by later definition kinds."""

    name: str
    span: SourceSpan


@dataclass(frozen=True)
class DefinitionReference:
    """Named reference used by later definition and expression phases."""

    name: str
    span: SourceSpan


@dataclass(frozen=True)
class EnumDefinition:
    """Shaped top-level defenum declaration."""

    name: str
    name_span: SourceSpan
    values: tuple[str, ...]
    value_spans: tuple[SourceSpan, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class PathDefinition:
    """Shaped top-level defpath declaration."""

    name: str
    name_span: SourceSpan
    kind: str
    kind_span: SourceSpan
    under: str
    under_span: SourceSpan
    must_exist: bool
    must_exist_span: SourceSpan
    form_span: SourceSpan


@dataclass(frozen=True)
class DefinitionField:
    """Named field paired with a type reference."""

    name: str
    name_span: SourceSpan
    type_ref: DefinitionTypeRef
    form_span: SourceSpan


@dataclass(frozen=True)
class WorkflowParameter:
    """One defworkflow parameter entry."""

    name: str
    name_span: SourceSpan
    type_ref: DefinitionTypeRef
    form_span: SourceSpan


@dataclass(frozen=True)
class WorkflowDefinition:
    """Shaped top-level defworkflow declaration."""

    name: str
    name_span: SourceSpan
    parameters: tuple[WorkflowParameter, ...]
    return_type: DefinitionTypeRef
    body_forms: tuple[SyntaxNode, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class ProcedureDefinition:
    """Shaped top-level defproc declaration."""

    name: str
    name_span: SourceSpan
    parameters: tuple[WorkflowParameter, ...]
    return_type: DefinitionTypeRef
    body_forms: tuple[SyntaxNode, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class FunctionDefinition:
    """Shaped top-level defun declaration."""

    name: str
    name_span: SourceSpan
    parameters: tuple[WorkflowParameter, ...]
    return_type: DefinitionTypeRef
    body_forms: tuple[SyntaxNode, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class RecordDefinition:
    """Shaped top-level defrecord declaration."""

    name: str
    name_span: SourceSpan
    fields: tuple[DefinitionField, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class SchemaDefinition(RecordDefinition):
    """Shaped top-level defschema declaration."""


@dataclass(frozen=True)
class UnionVariant:
    """Shaped variant entry inside one defunion declaration."""

    name: str
    name_span: SourceSpan
    fields: tuple[DefinitionField, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class UnionDefinition:
    """Shaped top-level defunion declaration."""

    name: str
    name_span: SourceSpan
    variants: tuple[UnionVariant, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class ImportDefinition:
    """Shaped top-level import declaration."""

    module_ref: str
    module_span: SourceSpan
    alias: str | None
    alias_span: SourceSpan | None
    only_names: tuple[str, ...]
    only_name_spans: tuple[SourceSpan, ...]
    form_span: SourceSpan


@dataclass(frozen=True)
class ExportDefinition:
    """Shaped top-level export declaration."""

    names: tuple[str, ...]
    name_spans: tuple[SourceSpan, ...]
    form_span: SourceSpan


DefinitionNode = EnumDefinition | PathDefinition | RecordDefinition | SchemaDefinition | UnionDefinition


def _raise_definition_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    enclosing_form_name: str | None = None,
    generated_core_node_id: str | None = None,
) -> None:
    raise WorkflowLispSyntaxError(
        SyntaxDiagnostic(
            code=code,
            message=message,
            span=span,
            source_file=span.source_file,
            line=span.line_start,
            column=span.column_start,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=generated_core_node_id,
        )
    )


def _expect_symbol(node: SyntaxNode, *, message: str, enclosing_form_name: str) -> SyntaxAtom:
    if not isinstance(node, SyntaxAtom) or node.kind is not AtomKind.SYMBOL:
        _raise_definition_error(
            code="frontend_parse_error",
            message=message,
            span=node.span,
            enclosing_form_name=enclosing_form_name,
        )
    return node


def _expect_keyword(node: SyntaxNode, *, message: str, enclosing_form_name: str) -> SyntaxAtom:
    if not isinstance(node, SyntaxAtom) or node.kind is not AtomKind.KEYWORD:
        _raise_definition_error(
            code="frontend_parse_error",
            message=message,
            span=node.span,
            enclosing_form_name=enclosing_form_name,
        )
    return node


def _shape_defenum(form: SyntaxList) -> EnumDefinition:
    if len(form.items) < 3:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defenum requires a name and at least one enum value",
            span=form.span,
            enclosing_form_name="defenum",
        )
    name_atom = _expect_symbol(
        form.items[1],
        message="defenum name must be a symbol",
        enclosing_form_name="defenum",
    )
    values: list[str] = []
    value_spans: list[SourceSpan] = []
    seen: set[str] = set()
    for value_node in form.items[2:]:
        value_atom = _expect_symbol(
            value_node,
            message="defenum values must be symbols",
            enclosing_form_name="defenum",
        )
        value_text = str(value_atom.value)
        if value_text in seen:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate defenum value: {value_text}",
                span=value_atom.span,
                enclosing_form_name="defenum",
            )
        seen.add(value_text)
        values.append(value_text)
        value_spans.append(value_atom.span)

    return EnumDefinition(
        name=str(name_atom.value),
        name_span=name_atom.span,
        values=tuple(values),
        value_spans=tuple(value_spans),
        form_span=form.span,
    )


def _shape_defpath(form: SyntaxList) -> PathDefinition:
    if len(form.items) < 3:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defpath requires a name and keyword clauses",
            span=form.span,
            enclosing_form_name="defpath",
        )
    name_atom = _expect_symbol(
        form.items[1],
        message="defpath name must be a symbol",
        enclosing_form_name="defpath",
    )
    clauses = form.items[2:]
    if len(clauses) % 2 != 0:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defpath keyword clauses must be key/value pairs",
            span=form.span,
            enclosing_form_name="defpath",
        )

    kind_atom: SyntaxAtom | None = None
    under_atom: SyntaxAtom | None = None
    must_exist_atom: SyntaxAtom | None = None
    seen_keys: set[str] = set()
    for index in range(0, len(clauses), 2):
        key_atom = _expect_keyword(
            clauses[index],
            message="defpath clause keys must be keywords",
            enclosing_form_name="defpath",
        )
        value_node = clauses[index + 1]
        key_text = str(key_atom.value)
        if key_text in seen_keys:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate defpath clause: {key_text}",
                span=key_atom.span,
                enclosing_form_name="defpath",
            )
        seen_keys.add(key_text)

        if key_text == ":kind":
            kind_atom = _expect_symbol(
                value_node,
                message="defpath :kind value must be a symbol",
                enclosing_form_name="defpath",
            )
            if kind_atom.value != "relpath":
                _raise_definition_error(
                    code="frontend_parse_error",
                    message=f"Unsupported defpath :kind value: {kind_atom.value}",
                    span=kind_atom.span,
                    enclosing_form_name="defpath",
                )
            continue
        if key_text == ":under":
            if not isinstance(value_node, SyntaxAtom) or value_node.kind is not AtomKind.STRING:
                _raise_definition_error(
                    code="frontend_parse_error",
                    message="defpath :under value must be a string literal",
                    span=value_node.span,
                    enclosing_form_name="defpath",
                )
            under_atom = value_node
            continue
        if key_text == ":must-exist":
            if not isinstance(value_node, SyntaxAtom) or value_node.kind is not AtomKind.BOOL:
                _raise_definition_error(
                    code="frontend_parse_error",
                    message="defpath :must-exist value must be a boolean literal",
                    span=value_node.span,
                    enclosing_form_name="defpath",
                )
            must_exist_atom = value_node
            continue
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"Unsupported defpath clause: {key_text}",
            span=key_atom.span,
            enclosing_form_name="defpath",
        )

    if kind_atom is None:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defpath requires :kind",
            span=form.span,
            enclosing_form_name="defpath",
        )
    if under_atom is None:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defpath requires :under",
            span=form.span,
            enclosing_form_name="defpath",
        )
    if must_exist_atom is None:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defpath requires :must-exist",
            span=form.span,
            enclosing_form_name="defpath",
        )

    return PathDefinition(
        name=str(name_atom.value),
        name_span=name_atom.span,
        kind=str(kind_atom.value),
        kind_span=kind_atom.span,
        under=str(under_atom.value),
        under_span=under_atom.span,
        must_exist=bool(must_exist_atom.value),
        must_exist_span=must_exist_atom.span,
        form_span=form.span,
    )


def _shape_field(node: SyntaxNode, *, enclosing_form_name: str) -> DefinitionField:
    if not isinstance(node, SyntaxList):
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{enclosing_form_name} fields must be list forms",
            span=node.span,
            enclosing_form_name=enclosing_form_name,
        )
    if len(node.items) != 2:
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{enclosing_form_name} fields must have shape (name Type)",
            span=node.span,
            enclosing_form_name=enclosing_form_name,
        )
    field_name_atom = _expect_symbol(
        node.items[0],
        message=f"{enclosing_form_name} field names must be symbols",
        enclosing_form_name=enclosing_form_name,
    )
    type_atom = _expect_symbol(
        node.items[1],
        message=f"{enclosing_form_name} field types must be symbols",
        enclosing_form_name=enclosing_form_name,
    )
    return DefinitionField(
        name=str(field_name_atom.value),
        name_span=field_name_atom.span,
        type_ref=DefinitionTypeRef(name=str(type_atom.value), span=type_atom.span),
        form_span=node.span,
    )


def _shape_workflow_parameter(node: SyntaxNode) -> WorkflowParameter:
    field = _shape_field(node, enclosing_form_name="defworkflow")
    return WorkflowParameter(
        name=field.name,
        name_span=field.name_span,
        type_ref=field.type_ref,
        form_span=field.form_span,
    )


def _shape_defrecord(form: SyntaxList) -> RecordDefinition:
    return _shape_record_like_definition(form, definition_form_name="defrecord", definition_cls=RecordDefinition)


def _shape_defschema(form: SyntaxList) -> SchemaDefinition:
    return _shape_record_like_definition(form, definition_form_name="defschema", definition_cls=SchemaDefinition)


def _shape_record_like_definition(
    form: SyntaxList,
    *,
    definition_form_name: str,
    definition_cls: type[RecordDefinition] | type[SchemaDefinition],
) -> RecordDefinition | SchemaDefinition:
    if len(form.items) < 3:
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{definition_form_name} requires a name and at least one field",
            span=form.span,
            enclosing_form_name=definition_form_name,
        )
    name_atom = _expect_symbol(
        form.items[1],
        message=f"{definition_form_name} name must be a symbol",
        enclosing_form_name=definition_form_name,
    )
    fields: list[DefinitionField] = []
    seen_field_names: set[str] = set()
    for field_node in form.items[2:]:
        field = _shape_field(field_node, enclosing_form_name=definition_form_name)
        if field.name in seen_field_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate {definition_form_name} field name: {field.name}",
                span=field.name_span,
                enclosing_form_name=definition_form_name,
            )
        seen_field_names.add(field.name)
        fields.append(field)
    return definition_cls(
        name=str(name_atom.value),
        name_span=name_atom.span,
        fields=tuple(fields),
        form_span=form.span,
    )


def _shape_union_variant(node: SyntaxNode) -> UnionVariant:
    if not isinstance(node, SyntaxList) or not node.items:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defunion variants must be non-empty list forms",
            span=node.span,
            enclosing_form_name="defunion",
        )
    name_atom = _expect_symbol(
        node.items[0],
        message="defunion variant names must be symbols",
        enclosing_form_name="defunion",
    )
    fields: list[DefinitionField] = []
    seen_field_names: set[str] = set()
    for field_node in node.items[1:]:
        field = _shape_field(field_node, enclosing_form_name="defunion")
        if field.name in seen_field_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate field name in defunion variant {name_atom.value}: {field.name}",
                span=field.name_span,
                enclosing_form_name="defunion",
            )
        seen_field_names.add(field.name)
        fields.append(field)
    return UnionVariant(
        name=str(name_atom.value),
        name_span=name_atom.span,
        fields=tuple(fields),
        form_span=node.span,
    )


def _shape_defunion(form: SyntaxList) -> UnionDefinition:
    if len(form.items) < 3:
        _raise_definition_error(
            code="frontend_parse_error",
            message="defunion requires a name and at least one variant",
            span=form.span,
            enclosing_form_name="defunion",
        )
    name_atom = _expect_symbol(
        form.items[1],
        message="defunion name must be a symbol",
        enclosing_form_name="defunion",
    )
    variants: list[UnionVariant] = []
    seen_variant_names: set[str] = set()
    for variant_node in form.items[2:]:
        variant = _shape_union_variant(variant_node)
        if variant.name in seen_variant_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate defunion variant name: {variant.name}",
                span=variant.name_span,
                enclosing_form_name="defunion",
            )
        seen_variant_names.add(variant.name)
        variants.append(variant)
    return UnionDefinition(
        name=str(name_atom.value),
        name_span=name_atom.span,
        variants=tuple(variants),
        form_span=form.span,
    )


def _shape_callable_definition(
    form: SyntaxList,
    *,
    callable_form_name: str,
) -> WorkflowDefinition | ProcedureDefinition | FunctionDefinition:
    if len(form.items) < 6:
        _raise_definition_error(
            code="frontend_parse_error",
            message=(
                f"{callable_form_name} requires name, parameter list, return marker, "
                "return type, and body"
            ),
            span=form.span,
            enclosing_form_name=callable_form_name,
        )

    name_atom = _expect_symbol(
        form.items[1],
        message=f"{callable_form_name} name must be a symbol",
        enclosing_form_name=callable_form_name,
    )
    callable_name = str(name_atom.value)

    params_node = form.items[2]
    if not isinstance(params_node, SyntaxList):
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{callable_form_name} parameters must be a list form",
            span=params_node.span,
            enclosing_form_name=callable_form_name,
        )

    arrow_node = form.items[3]
    if not isinstance(arrow_node, SyntaxAtom) or arrow_node.kind is not AtomKind.SYMBOL or arrow_node.value != "->":
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{callable_form_name} requires -> before return type",
            span=arrow_node.span,
            enclosing_form_name=callable_form_name,
            generated_core_node_id=f"{callable_name}.result",
        )

    return_type_node = form.items[4]
    if not isinstance(return_type_node, SyntaxAtom) or return_type_node.kind is not AtomKind.SYMBOL:
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{callable_form_name} return type must be a symbol",
            span=return_type_node.span,
            enclosing_form_name=callable_form_name,
            generated_core_node_id=f"{callable_name}.result",
        )
    return_type_atom = return_type_node

    body_forms = tuple(form.items[5:])
    if not body_forms:
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"{callable_form_name} requires at least one body form",
            span=form.span,
            enclosing_form_name=callable_form_name,
        )

    parameters: list[WorkflowParameter] = []
    seen_parameter_names: set[str] = set()
    for parameter_node in params_node.items:
        parameter = _shape_workflow_parameter(parameter_node)
        if parameter.name in seen_parameter_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate {callable_form_name} parameter name: {parameter.name}",
                span=parameter.name_span,
                enclosing_form_name=callable_form_name,
                generated_core_node_id=f"{callable_name}.input.{parameter.name}",
            )
        seen_parameter_names.add(parameter.name)
        parameters.append(parameter)

    callable_kwargs = {
        "name": callable_name,
        "name_span": name_atom.span,
        "parameters": tuple(parameters),
        "return_type": DefinitionTypeRef(
            name=str(return_type_atom.value),
            span=return_type_atom.span,
        ),
        "body_forms": body_forms,
        "form_span": form.span,
    }
    if callable_form_name == "defworkflow":
        return WorkflowDefinition(**callable_kwargs)
    if callable_form_name == "defproc":
        return ProcedureDefinition(**callable_kwargs)
    return FunctionDefinition(**callable_kwargs)


def _shape_defworkflow(form: SyntaxList) -> WorkflowDefinition:
    shaped = _shape_callable_definition(
        form,
        callable_form_name="defworkflow",
    )
    assert isinstance(shaped, WorkflowDefinition)
    return shaped


def _shape_defproc(form: SyntaxList) -> ProcedureDefinition:
    shaped = _shape_callable_definition(
        form,
        callable_form_name="defproc",
    )
    assert isinstance(shaped, ProcedureDefinition)
    return shaped


def _shape_defun(form: SyntaxList) -> FunctionDefinition:
    shaped = _shape_callable_definition(
        form,
        callable_form_name="defun",
    )
    assert isinstance(shaped, FunctionDefinition)
    return shaped


def _shape_import(form: SyntaxList) -> ImportDefinition:
    if len(form.items) < 2:
        _raise_definition_error(
            code="frontend_parse_error",
            message="import requires a module reference symbol",
            span=form.span,
            enclosing_form_name="import",
        )
    module_atom = _expect_symbol(
        form.items[1],
        message="import module reference must be a symbol",
        enclosing_form_name="import",
    )
    alias_atom: SyntaxAtom | None = None
    only_names: list[str] = []
    only_name_spans: list[SourceSpan] = []
    seen_only_names: set[str] = set()

    clauses = form.items[2:]
    if len(clauses) % 2 != 0:
        _raise_definition_error(
            code="frontend_parse_error",
            message="import clauses must be key/value pairs",
            span=form.span,
            enclosing_form_name="import",
        )
    seen_keys: set[str] = set()
    for index in range(0, len(clauses), 2):
        key_atom = _expect_keyword(
            clauses[index],
            message="import clause keys must be keywords",
            enclosing_form_name="import",
        )
        value_node = clauses[index + 1]
        key_text = str(key_atom.value)
        if key_text in seen_keys:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate import clause: {key_text}",
                span=key_atom.span,
                enclosing_form_name="import",
            )
        seen_keys.add(key_text)
        if key_text == ":as":
            alias_atom = _expect_symbol(
                value_node,
                message="import :as value must be a symbol",
                enclosing_form_name="import",
            )
            continue
        if key_text == ":only":
            if not isinstance(value_node, SyntaxList):
                _raise_definition_error(
                    code="frontend_parse_error",
                    message="import :only value must be a list of symbols",
                    span=value_node.span,
                    enclosing_form_name="import",
                )
            if not value_node.items:
                _raise_definition_error(
                    code="frontend_parse_error",
                    message="import :only list must not be empty",
                    span=value_node.span,
                    enclosing_form_name="import",
                )
            for name_node in value_node.items:
                only_name_atom = _expect_symbol(
                    name_node,
                    message="import :only names must be symbols",
                    enclosing_form_name="import",
                )
                only_name = str(only_name_atom.value)
                if only_name in seen_only_names:
                    _raise_definition_error(
                        code="frontend_parse_error",
                        message=f"Duplicate import :only name: {only_name}",
                        span=only_name_atom.span,
                        enclosing_form_name="import",
                    )
                seen_only_names.add(only_name)
                only_names.append(only_name)
                only_name_spans.append(only_name_atom.span)
            continue
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"Unsupported import clause: {key_text}",
            span=key_atom.span,
            enclosing_form_name="import",
        )

    return ImportDefinition(
        module_ref=str(module_atom.value),
        module_span=module_atom.span,
        alias=str(alias_atom.value) if alias_atom else None,
        alias_span=alias_atom.span if alias_atom else None,
        only_names=tuple(only_names),
        only_name_spans=tuple(only_name_spans),
        form_span=form.span,
    )


def _shape_export(form: SyntaxList) -> ExportDefinition:
    if len(form.items) < 2:
        _raise_definition_error(
            code="frontend_parse_error",
            message="export requires at least one exported symbol",
            span=form.span,
            enclosing_form_name="export",
        )
    names: list[str] = []
    name_spans: list[SourceSpan] = []
    seen_names: set[str] = set()
    for name_node in form.items[1:]:
        name_atom = _expect_symbol(
            name_node,
            message="export names must be symbols",
            enclosing_form_name="export",
        )
        name_text = str(name_atom.value)
        if name_text in seen_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate export name: {name_text}",
                span=name_atom.span,
                enclosing_form_name="export",
            )
        seen_names.add(name_text)
        names.append(name_text)
        name_spans.append(name_atom.span)
    return ExportDefinition(
        names=tuple(names),
        name_spans=tuple(name_spans),
        form_span=form.span,
    )


def shape_module_definitions(module: ParsedWorkflowModule) -> tuple[DefinitionNode, ...]:
    """Shape supported top-level definitions from one parsed module."""

    definitions: list[DefinitionNode] = []
    for form in module.body_forms:
        if not isinstance(form, SyntaxList) or not form.items:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must be a non-empty list",
                span=form.span,
            )
        head = form.items[0]
        if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must start with a symbol",
                span=head.span,
            )
        if head.value == "defenum":
            definitions.append(_shape_defenum(form))
            continue
        if head.value == "defpath":
            definitions.append(_shape_defpath(form))
            continue
        if head.value == "defrecord":
            definitions.append(_shape_defrecord(form))
            continue
        if head.value == "defschema":
            definitions.append(_shape_defschema(form))
            continue
        if head.value == "defunion":
            definitions.append(_shape_defunion(form))
            continue
        if head.value == "defworkflow":
            continue
        if head.value == "defproc":
            continue
        if head.value == "defun":
            continue
        if head.value in {"import", "export"}:
            continue
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"Unsupported top-level definition form: {head.value}",
            span=head.span,
        )
    return tuple(definitions)


def shape_module_workflow_definitions(module: ParsedWorkflowModule) -> tuple[WorkflowDefinition, ...]:
    """Shape supported top-level defworkflow declarations from one parsed module."""

    workflow_definitions: list[WorkflowDefinition] = []
    for form in module.body_forms:
        if not isinstance(form, SyntaxList) or not form.items:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must be a non-empty list",
                span=form.span,
            )
        head = form.items[0]
        if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must start with a symbol",
                span=head.span,
            )
        if head.value == "defworkflow":
            workflow_definitions.append(_shape_defworkflow(form))
            continue
        if head.value in {
            "defenum",
            "defpath",
            "defrecord",
            "defschema",
            "defunion",
            "defproc",
            "defun",
            "import",
            "export",
        }:
            continue
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"Unsupported top-level definition form: {head.value}",
            span=head.span,
        )
    return tuple(workflow_definitions)


def shape_module_procedure_definitions(module: ParsedWorkflowModule) -> tuple[ProcedureDefinition, ...]:
    """Shape supported top-level defproc declarations from one parsed module."""

    procedure_definitions: list[ProcedureDefinition] = []
    for form in module.body_forms:
        if not isinstance(form, SyntaxList) or not form.items:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must be a non-empty list",
                span=form.span,
            )
        head = form.items[0]
        if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must start with a symbol",
                span=head.span,
            )
        if head.value == "defproc":
            procedure_definitions.append(_shape_defproc(form))
            continue
        if head.value in {
            "defenum",
            "defpath",
            "defrecord",
            "defschema",
            "defunion",
            "defworkflow",
            "defun",
            "import",
            "export",
        }:
            continue
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"Unsupported top-level definition form: {head.value}",
            span=head.span,
        )
    return tuple(procedure_definitions)


def shape_module_import_definitions(module: ParsedWorkflowModule) -> tuple[ImportDefinition, ...]:
    """Shape top-level module import declarations."""

    imports: list[ImportDefinition] = []
    for form in module.body_forms:
        if not isinstance(form, SyntaxList) or not form.items:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must be a non-empty list",
                span=form.span,
            )
        head = form.items[0]
        if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must start with a symbol",
                span=head.span,
            )
        if head.value == "import":
            imports.append(_shape_import(form))
    return tuple(imports)


def shape_module_function_definitions(module: ParsedWorkflowModule) -> tuple[FunctionDefinition, ...]:
    """Shape supported top-level defun declarations."""

    function_definitions: list[FunctionDefinition] = []
    for form in module.body_forms:
        if not isinstance(form, SyntaxList) or not form.items:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must be a non-empty list",
                span=form.span,
            )
        head = form.items[0]
        if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must start with a symbol",
                span=head.span,
            )
        if head.value == "defun":
            function_definitions.append(_shape_defun(form))
            continue
        if head.value in {
            "defenum",
            "defpath",
            "defrecord",
            "defschema",
            "defunion",
            "defworkflow",
            "defproc",
            "import",
            "export",
        }:
            continue
        _raise_definition_error(
            code="frontend_parse_error",
            message=f"Unsupported top-level definition form: {head.value}",
            span=head.span,
        )
    return tuple(function_definitions)


def shape_module_export_definitions(module: ParsedWorkflowModule) -> tuple[ExportDefinition, ...]:
    """Shape top-level module export declarations."""

    exports: list[ExportDefinition] = []
    for form in module.body_forms:
        if not isinstance(form, SyntaxList) or not form.items:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must be a non-empty list",
                span=form.span,
            )
        head = form.items[0]
        if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
            _raise_definition_error(
                code="frontend_parse_error",
                message="Top-level definition must start with a symbol",
                span=head.span,
            )
        if head.value == "export":
            exports.append(_shape_export(form))
    return tuple(exports)
