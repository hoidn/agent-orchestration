"""Compiler-owned projection of directly authored definition symbols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    UnionDef,
)
from .modules import ResolvedModuleSource
from .spans import SourceSpan
from .syntax import SyntaxIdentifier, SyntaxList, syntax_node_datum
from .workflows import Stage3CompileResult


AuthoredSymbolKind = Literal[
    "module",
    "procedure",
    "workflow",
    "enum",
    "path",
    "record",
    "union",
    "schema",
    "resource",
    "transition",
]


@dataclass(frozen=True)
class AuthoredSymbolProjectionRow:
    """One compiler-validated original-syntax definition row."""

    kind: AuthoredSymbolKind
    name: str
    definition_span: SourceSpan
    selection_span: SourceSpan
    source_ordinal: int


class AuthoredSymbolProjectionError(ValueError):
    """The original-syntax projection cannot be cross-checked exactly."""


_DIRECT_HEAD_KINDS: dict[str, AuthoredSymbolKind] = {
    "defproc": "procedure",
    "defworkflow": "workflow",
    "defenum": "enum",
    "defpath": "path",
    "defrecord": "record",
    "defunion": "union",
    "defschema": "schema",
    "defresource": "resource",
    "deftransition": "transition",
}


def _span_is_nonempty_and_ordered(span: SourceSpan) -> bool:
    return (
        span.start.path == span.end.path
        and span.start.line >= 1
        and span.start.column >= 1
        and span.start.offset >= 0
        and span.end.line >= 1
        and span.end.column >= 1
        and span.end.offset > span.start.offset
        and (span.end.line, span.end.column) >= (span.start.line, span.start.column)
    )


def _validate_selection_span(
    *,
    definition_span: SourceSpan,
    selection_span: SourceSpan,
    kind: str,
    name: str,
) -> None:
    if not _span_is_nonempty_and_ordered(selection_span):
        raise AuthoredSymbolProjectionError(
            f"invalid selection span for authored {kind} `{name}`"
        )
    if (
        definition_span.start.path != definition_span.end.path
        or selection_span.start.path != definition_span.start.path
        or selection_span.end.path != definition_span.end.path
        or selection_span.start.offset < definition_span.start.offset
        or selection_span.end.offset > definition_span.end.offset
    ):
        raise AuthoredSymbolProjectionError(
            f"selection span is outside authored {kind} `{name}`"
        )


def _compiled_candidates(
    compiled_result: Stage3CompileResult,
) -> dict[AuthoredSymbolKind, tuple[object, ...]]:
    definitions = compiled_result.module.definitions
    specialized_procedure_definition_ids = {
        id(procedure.definition)
        for procedure in compiled_result.typed_procedures
        if procedure.specialization is not None
    }
    specialized_workflow_definition_ids = {
        id(workflow.definition)
        for workflow in compiled_result.typed_workflows
        if workflow.specialization is not None
    }
    return {
        "module": (),
        "procedure": tuple(
            definition
            for definition in (
                compiled_result.procedure_catalog.definitions_by_name.values()
            )
            if definition.generated_local_procedure is None
            and id(definition) not in specialized_procedure_definition_ids
        ),
        "workflow": tuple(
            definition
            for definition in (
                compiled_result.workflow_catalog.definitions_by_name.values()
            )
            if id(definition) not in specialized_workflow_definition_ids
        ),
        "enum": tuple(
            definition
            for definition in definitions
            if isinstance(definition, EnumDef)
        ),
        "path": tuple(
            definition
            for definition in definitions
            if isinstance(definition, PathDef)
        ),
        "record": tuple(
            definition
            for definition in definitions
            if isinstance(definition, RecordDef)
        ),
        "union": tuple(
            definition
            for definition in definitions
            if isinstance(definition, UnionDef)
        ),
        "schema": tuple(compiled_result.module.schemas),
        "resource": tuple(compiled_result.module.resources),
        "transition": tuple(compiled_result.module.transitions),
    }


def _candidate_name(
    candidate: object,
    *,
    kind: AuthoredSymbolKind,
    compiled_module_name: str,
) -> str | None:
    name = getattr(candidate, "name", None)
    if not isinstance(name, str):
        return None
    if kind in {"procedure", "workflow"}:
        prefix = f"{compiled_module_name}::"
        if not name.startswith(prefix):
            return None
        return name[len(prefix) :]
    return name


def _crosscheck_direct_row(
    row: AuthoredSymbolProjectionRow,
    *,
    candidates_by_kind: dict[AuthoredSymbolKind, tuple[object, ...]],
    compiled_module_name: str,
) -> None:
    candidates = candidates_by_kind[row.kind]
    matches = tuple(
        candidate
        for candidate in candidates
        if _candidate_name(
            candidate,
            kind=row.kind,
            compiled_module_name=compiled_module_name,
        )
        == row.name
        and getattr(candidate, "span", None) == row.definition_span
    )
    if len(matches) != 1:
        raise AuthoredSymbolProjectionError(
            f"authored {row.kind} `{row.name}` requires exactly one "
            "same-kind/name/full-span compiled definition"
        )


def project_authored_symbols(
    resolved_source: ResolvedModuleSource,
    compiled_result: Stage3CompileResult,
) -> tuple[AuthoredSymbolProjectionRow, ...]:
    """Project direct original-syntax definitions and fail closed on drift."""

    syntax_module = resolved_source.syntax_module
    module_directive = syntax_module.module_directive
    if module_directive is None:
        raise AuthoredSymbolProjectionError(
            "authored symbol projection requires a module directive"
        )
    compiled_module_name = compiled_result.module.module_name
    if not (
        compiled_module_name is not None
        and module_directive.name
        == resolved_source.module_name
        == compiled_module_name
    ):
        raise AuthoredSymbolProjectionError(
            "authored, resolved, and compiled module identities differ"
        )

    module_row = AuthoredSymbolProjectionRow(
        kind="module",
        name=module_directive.name,
        definition_span=module_directive.span,
        selection_span=module_directive.name_span,
        source_ordinal=0,
    )
    _validate_selection_span(
        definition_span=module_row.definition_span,
        selection_span=module_row.selection_span,
        kind=module_row.kind,
        name=module_row.name,
    )

    rows: list[AuthoredSymbolProjectionRow] = [module_row]
    candidates_by_kind = _compiled_candidates(compiled_result)
    for source_ordinal, form in enumerate(syntax_module.forms, start=1):
        datum = syntax_node_datum(form)
        if not isinstance(datum, SyntaxList) or not datum.items:
            continue
        head = datum.items[0]
        if not isinstance(head, SyntaxIdentifier):
            continue
        kind = _DIRECT_HEAD_KINDS.get(head.resolved_name)
        if kind is None:
            continue
        if len(datum.items) < 2 or not isinstance(
            datum.items[1], SyntaxIdentifier
        ):
            raise AuthoredSymbolProjectionError(
                f"authored {kind} definition lacks a retained name token"
            )
        name_identifier = datum.items[1]
        row = AuthoredSymbolProjectionRow(
            kind=kind,
            name=name_identifier.resolved_name,
            definition_span=form.span,
            selection_span=name_identifier.span,
            source_ordinal=source_ordinal,
        )
        _validate_selection_span(
            definition_span=row.definition_span,
            selection_span=row.selection_span,
            kind=row.kind,
            name=row.name,
        )
        _crosscheck_direct_row(
            row,
            candidates_by_kind=candidates_by_kind,
            compiled_module_name=compiled_module_name,
        )
        rows.append(row)

    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.definition_span.start.offset,
                row.source_ordinal,
            ),
        )
    )
