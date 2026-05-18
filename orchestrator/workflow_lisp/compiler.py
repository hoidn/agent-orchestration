"""Pure Stage 1 compiler pipeline for the workflow Lisp frontend."""

from __future__ import annotations

from pathlib import Path

from .definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    RecordField,
    UnionDef,
    UnionVariant,
    WorkflowLispModule,
    elaborate_definition_module,
)
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .reader import read_sexpr_file
from .syntax import build_syntax_module


PRELUDE_TYPE_NAMES = frozenset({"String", "Int", "Bool", "Json", "Provider", "Prompt", "PathRel"})


def compile_stage1_module(path: Path) -> WorkflowLispModule:
    """Compile one `.orc` file through the Stage 1 frontend pipeline."""

    parse_tree = read_sexpr_file(path)
    syntax_module = build_syntax_module(parse_tree)
    module = elaborate_definition_module(syntax_module)
    _validate_definition_module(module)
    return module


def _validate_definition_module(module: WorkflowLispModule) -> None:
    diagnostics: list[LispFrontendDiagnostic] = []
    definition_names: dict[str, object] = {}
    for definition in module.definitions:
        if definition.name in definition_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="definition_duplicate",
                    message=f"duplicate definition `{definition.name}`",
                    span=definition.span,
                    form_path=_definition_form_path(definition),
                )
            )
        else:
            definition_names[definition.name] = definition

    available_type_names = PRELUDE_TYPE_NAMES | frozenset(definition_names)
    for definition in module.definitions:
        if isinstance(definition, RecordDef):
            diagnostics.extend(_validate_field_list(definition.fields, _definition_form_path(definition)))
            diagnostics.extend(_validate_field_types(definition.fields, _definition_form_path(definition), available_type_names))
        elif isinstance(definition, UnionDef):
            diagnostics.extend(_validate_union_definition(definition, available_type_names))

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))


def _validate_union_definition(
    definition: UnionDef,
    available_type_names: frozenset[str],
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    seen_variants: set[str] = set()
    form_path = _definition_form_path(definition)
    for variant in definition.variants:
        if variant.name in seen_variants:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="union_variant_duplicate",
                    message=f"duplicate union variant `{variant.name}`",
                    span=variant.span,
                    form_path=form_path,
                )
            )
        else:
            seen_variants.add(variant.name)
        diagnostics.extend(
            _validate_field_list(
                variant.fields,
                form_path,
                scope_label=f"union variant `{variant.name}`",
            )
        )
        diagnostics.extend(_validate_field_types(variant.fields, form_path, available_type_names))
    return diagnostics


def _validate_field_list(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    *,
    scope_label: str = "record",
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    seen_fields: set[str] = set()
    for field in fields:
        if field.name in seen_fields:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="record_field_duplicate",
                    message=f"duplicate field `{field.name}` in {scope_label}",
                    span=field.span,
                    form_path=form_path,
                )
            )
        else:
            seen_fields.add(field.name)
    return diagnostics


def _validate_field_types(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    available_type_names: frozenset[str],
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    for field in fields:
        if field.type_name not in available_type_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="type_unknown",
                    message=f"unknown type `{field.type_name}`",
                    span=field.span,
                    form_path=form_path,
                )
            )
    return diagnostics


def _definition_form_path(definition: EnumDef | PathDef | RecordDef | UnionDef) -> tuple[str, ...]:
    if isinstance(definition, EnumDef):
        return ("workflow-lisp", "defenum", definition.name)
    if isinstance(definition, PathDef):
        return ("workflow-lisp", "defpath", definition.name)
    if isinstance(definition, RecordDef):
        return ("workflow-lisp", "defrecord", definition.name)
    return ("workflow-lisp", "defunion", definition.name)
