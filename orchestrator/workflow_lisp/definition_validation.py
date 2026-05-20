"""Definition-phase validation for the Workflow Lisp MVP."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .definitions import (
    DefinitionNode,
    DefinitionTypeRef,
    ExportDefinition,
    ImportDefinition,
    ProcedureDefinition,
    RecordDefinition,
    SchemaDefinition,
    UnionDefinition,
    shape_module_export_definitions,
    shape_module_definitions,
    shape_module_import_definitions,
    shape_module_procedure_definitions,
    shape_module_workflow_definitions,
    WorkflowDefinition,
)
from .parser import WorkflowLispSyntaxError
from .prelude import PRELUDE_RESERVED_NAMES
from .syntax import ParsedWorkflowModule, SourceSpan, SyntaxDiagnostic, SyntaxList


@dataclass(frozen=True)
class DefinitionCheckedModule:
    """Definition-checked single-file module payload."""

    source_path: str
    header_form: SyntaxList
    language_version: str
    target_dsl: str
    definitions: tuple[DefinitionNode, ...]
    definition_table: MappingProxyType[str, DefinitionNode]
    import_definitions: tuple[ImportDefinition, ...] = ()
    exported_names: tuple[str, ...] = ()
    workflow_definitions: tuple[WorkflowDefinition, ...] = ()
    procedure_definitions: tuple[ProcedureDefinition, ...] = ()


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


def validate_definition_module(module: ParsedWorkflowModule) -> DefinitionCheckedModule:
    """Shape and validate one parsed module's definition declarations."""

    definitions = shape_module_definitions(module)
    workflow_definitions = shape_module_workflow_definitions(module)
    procedure_definitions = shape_module_procedure_definitions(module)
    import_definitions = shape_module_import_definitions(module)
    export_definitions = shape_module_export_definitions(module)
    table: dict[str, DefinitionNode] = {}
    for definition in definitions:
        if definition.name in PRELUDE_RESERVED_NAMES:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Reserved prelude name cannot be redefined: {definition.name}",
                span=definition.name_span,
            )
        if definition.name in table:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate top-level definition: {definition.name}",
                span=definition.name_span,
            )
        table[definition.name] = definition
    seen_workflow_names: set[str] = set()
    for workflow_definition in workflow_definitions:
        if workflow_definition.name in PRELUDE_RESERVED_NAMES:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Reserved prelude name cannot be redefined: {workflow_definition.name}",
                span=workflow_definition.name_span,
            )
        if workflow_definition.name in table:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate top-level definition: {workflow_definition.name}",
                span=workflow_definition.name_span,
            )
        if workflow_definition.name in seen_workflow_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate top-level definition: {workflow_definition.name}",
                span=workflow_definition.name_span,
            )
        seen_workflow_names.add(workflow_definition.name)
    seen_procedure_names: set[str] = set()
    for procedure_definition in procedure_definitions:
        if procedure_definition.name in PRELUDE_RESERVED_NAMES:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Reserved prelude name cannot be redefined: {procedure_definition.name}",
                span=procedure_definition.name_span,
            )
        if procedure_definition.name in table:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate top-level definition: {procedure_definition.name}",
                span=procedure_definition.name_span,
            )
        if procedure_definition.name in seen_workflow_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate top-level definition: {procedure_definition.name}",
                span=procedure_definition.name_span,
            )
        if procedure_definition.name in seen_procedure_names:
            _raise_definition_error(
                code="frontend_parse_error",
                message=f"Duplicate top-level definition: {procedure_definition.name}",
                span=procedure_definition.name_span,
            )
        seen_procedure_names.add(procedure_definition.name)
    imported_only_names, import_aliases = _collect_imported_type_resolution(import_definitions)
    _validate_known_type_references(
        definitions=definitions,
        known_definition_names=frozenset(table),
        imported_only_names=imported_only_names,
        import_aliases=import_aliases,
    )
    _validate_callable_signature_type_references(
        workflow_definitions=workflow_definitions,
        procedure_definitions=procedure_definitions,
        known_definition_names=frozenset(table),
        imported_only_names=imported_only_names,
        import_aliases=import_aliases,
    )
    local_definition_names = frozenset(table)
    local_callable_names = frozenset(
        {workflow.name for workflow in workflow_definitions}.union(
            {procedure.name for procedure in procedure_definitions}
        )
    )
    _validate_import_aliases(
        import_definitions=import_definitions,
        local_definition_names=local_definition_names,
        local_workflow_names=local_callable_names,
        imported_only_names=imported_only_names,
    )
    _validate_import_only_name_resolution(
        import_definitions=import_definitions,
        local_definition_names=local_definition_names,
        local_workflow_names=local_callable_names,
    )
    exported_names = _validate_and_collect_exported_names(
        export_definitions=export_definitions,
        local_definition_names=local_definition_names,
        local_workflow_names=local_callable_names,
    )

    return DefinitionCheckedModule(
        source_path=module.source_path,
        header_form=module.header_form,
        language_version=module.language_version,
        target_dsl=module.target_dsl,
        definitions=definitions,
        definition_table=MappingProxyType(table),
        import_definitions=import_definitions,
        exported_names=exported_names,
        workflow_definitions=workflow_definitions,
        procedure_definitions=procedure_definitions,
    )


def _iter_definition_type_references(
    definition: DefinitionNode,
) -> tuple[tuple[DefinitionTypeRef, str, str], ...]:
    if isinstance(definition, SchemaDefinition):
        return tuple(
            (
                field.type_ref,
                f"{definition.name}.field.{field.name}",
                "defschema",
            )
            for field in definition.fields
        )
    if isinstance(definition, RecordDefinition):
        return tuple(
            (
                field.type_ref,
                f"{definition.name}.field.{field.name}",
                "defrecord",
            )
            for field in definition.fields
        )
    if isinstance(definition, UnionDefinition):
        refs: list[tuple[DefinitionTypeRef, str, str]] = []
        for variant in definition.variants:
            refs.extend(
                (
                    field.type_ref,
                    f"{definition.name}.variant.{variant.name}.field.{field.name}",
                    "defunion",
                )
                for field in variant.fields
            )
        return tuple(refs)
    return ()


def _validate_known_type_references(
    *,
    definitions: tuple[DefinitionNode, ...],
    known_definition_names: frozenset[str],
    imported_only_names: frozenset[str],
    import_aliases: frozenset[str],
) -> None:
    known_type_names = PRELUDE_RESERVED_NAMES.union(known_definition_names).union(imported_only_names)
    for definition in definitions:
        for type_ref, generated_core_node_id, enclosing_form_name in _iter_definition_type_references(definition):
            if _is_known_type_reference(
                type_ref.name,
                known_type_names=known_type_names,
                import_aliases=import_aliases,
            ):
                continue
            _raise_definition_error(
                code="type_unknown",
                message=f"Unknown type reference: {type_ref.name}",
                span=type_ref.span,
                enclosing_form_name=enclosing_form_name,
                generated_core_node_id=generated_core_node_id,
            )


def _iter_callable_signature_type_references(
    callable_definition: WorkflowDefinition | ProcedureDefinition,
) -> tuple[tuple[DefinitionTypeRef, str, str], ...]:
    form_name = "defworkflow" if isinstance(callable_definition, WorkflowDefinition) else "defproc"
    refs: list[tuple[DefinitionTypeRef, str, str]] = [
        (
            parameter.type_ref,
            f"{callable_definition.name}.input.{parameter.name}",
            form_name,
        )
        for parameter in callable_definition.parameters
    ]
    refs.append(
        (
            callable_definition.return_type,
            f"{callable_definition.name}.result",
            form_name,
        )
    )
    return tuple(refs)


def _validate_callable_signature_type_references(
    *,
    workflow_definitions: tuple[WorkflowDefinition, ...],
    procedure_definitions: tuple[ProcedureDefinition, ...],
    known_definition_names: frozenset[str],
    imported_only_names: frozenset[str],
    import_aliases: frozenset[str],
) -> None:
    known_type_names = PRELUDE_RESERVED_NAMES.union(known_definition_names).union(imported_only_names)
    callable_definitions: tuple[WorkflowDefinition | ProcedureDefinition, ...] = (
        workflow_definitions + procedure_definitions
    )
    for callable_definition in callable_definitions:
        for type_ref, generated_core_node_id, enclosing_form_name in _iter_callable_signature_type_references(
            callable_definition
        ):
            if _is_known_type_reference(
                type_ref.name,
                known_type_names=known_type_names,
                import_aliases=import_aliases,
            ):
                continue
            _raise_definition_error(
                code="type_unknown",
                message=f"Unknown type reference: {type_ref.name}",
                span=type_ref.span,
                enclosing_form_name=enclosing_form_name,
                generated_core_node_id=generated_core_node_id,
            )


def _collect_imported_type_resolution(
    import_definitions: tuple[ImportDefinition, ...],
) -> tuple[frozenset[str], frozenset[str]]:
    only_names: set[str] = set()
    aliases: set[str] = set()
    for import_definition in import_definitions:
        only_names.update(import_definition.only_names)
        if import_definition.alias is None:
            aliases.add(import_definition.module_ref)
            continue
        if import_definition.only_names:
            for imported_name in import_definition.only_names:
                only_names.add(f"{import_definition.alias}.{imported_name}")
                only_names.add(f"{import_definition.alias}/{imported_name}")
            continue
        aliases.add(import_definition.alias)
    return frozenset(only_names), frozenset(aliases)


def _is_known_type_reference(
    type_name: str,
    *,
    known_type_names: frozenset[str],
    import_aliases: frozenset[str],
) -> bool:
    if type_name in known_type_names:
        return True
    for alias in import_aliases:
        for separator in (".", "/"):
            prefix = f"{alias}{separator}"
            if type_name.startswith(prefix) and len(type_name) > len(prefix):
                return True
    return False


def _validate_import_aliases(
    *,
    import_definitions: tuple[ImportDefinition, ...],
    local_definition_names: frozenset[str],
    local_workflow_names: frozenset[str],
    imported_only_names: frozenset[str],
) -> None:
    seen_aliases: set[str] = set()
    for import_definition in import_definitions:
        if import_definition.alias is None:
            continue
        if import_definition.alias in seen_aliases:
            assert import_definition.alias_span is not None
            _raise_definition_error(
                code="module_import_ambiguous",
                message=f"Duplicate import alias: {import_definition.alias}",
                span=import_definition.alias_span,
                enclosing_form_name="import",
                generated_core_node_id=f"module.import.alias.{import_definition.alias}",
            )
        if import_definition.alias in PRELUDE_RESERVED_NAMES:
            assert import_definition.alias_span is not None
            _raise_definition_error(
                code="module_import_ambiguous",
                message=f"Import alias conflicts with reserved name: {import_definition.alias}",
                span=import_definition.alias_span,
                enclosing_form_name="import",
                generated_core_node_id=f"module.import.alias.{import_definition.alias}",
            )
        if import_definition.alias in local_definition_names:
            assert import_definition.alias_span is not None
            _raise_definition_error(
                code="module_import_ambiguous",
                message=f"Import alias conflicts with local definition name: {import_definition.alias}",
                span=import_definition.alias_span,
                enclosing_form_name="import",
                generated_core_node_id=f"module.import.alias.{import_definition.alias}",
            )
        if import_definition.alias in local_workflow_names:
            assert import_definition.alias_span is not None
            _raise_definition_error(
                code="module_import_ambiguous",
                message=f"Import alias conflicts with local workflow name: {import_definition.alias}",
                span=import_definition.alias_span,
                enclosing_form_name="import",
                generated_core_node_id=f"module.import.alias.{import_definition.alias}",
            )
        if import_definition.alias in imported_only_names:
            assert import_definition.alias_span is not None
            _raise_definition_error(
                code="module_import_ambiguous",
                message=f"Import alias conflicts with imported :only name: {import_definition.alias}",
                span=import_definition.alias_span,
                enclosing_form_name="import",
                generated_core_node_id=f"module.import.alias.{import_definition.alias}",
            )
        seen_aliases.add(import_definition.alias)


def _validate_import_only_name_resolution(
    *,
    import_definitions: tuple[ImportDefinition, ...],
    local_definition_names: frozenset[str],
    local_workflow_names: frozenset[str],
) -> None:
    imported_names: set[str] = set()
    local_names = local_definition_names.union(local_workflow_names)
    for import_definition in import_definitions:
        for name, span in zip(import_definition.only_names, import_definition.only_name_spans):
            if name in imported_names:
                _raise_definition_error(
                    code="module_import_ambiguous",
                    message=f"Imported :only name is ambiguous across imports: {name}",
                    span=span,
                    enclosing_form_name="import",
                    generated_core_node_id=f"module.import.only.{name}",
                )
            if name in PRELUDE_RESERVED_NAMES:
                _raise_definition_error(
                    code="module_import_ambiguous",
                    message=f"Import :only name conflicts with reserved name: {name}",
                    span=span,
                    enclosing_form_name="import",
                    generated_core_node_id=f"module.import.only.{name}",
                )
            if name in local_names:
                _raise_definition_error(
                    code="module_import_ambiguous",
                    message=f"Import :only name conflicts with local name: {name}",
                    span=span,
                    enclosing_form_name="import",
                    generated_core_node_id=f"module.import.only.{name}",
                )
            imported_names.add(name)


def _validate_and_collect_exported_names(
    *,
    export_definitions: tuple[ExportDefinition, ...],
    local_definition_names: frozenset[str],
    local_workflow_names: frozenset[str],
) -> tuple[str, ...]:
    exported_names: list[str] = []
    known_names = local_definition_names.union(local_workflow_names)
    seen_names: set[str] = set()
    for export_definition in export_definitions:
        for name, name_span in zip(export_definition.names, export_definition.name_spans):
            if name in seen_names:
                _raise_definition_error(
                    code="frontend_parse_error",
                    message=f"Duplicate export name: {name}",
                    span=name_span,
                    enclosing_form_name="export",
                    generated_core_node_id=f"module.export.{name}",
                )
            seen_names.add(name)
            if name not in known_names:
                _raise_definition_error(
                    code="module_export_missing",
                    message=f"module export references unknown name: {name}",
                    span=name_span,
                    enclosing_form_name="export",
                    generated_core_node_id=f"module.export.{name}",
                )
            exported_names.append(name)
    return tuple(exported_names)
