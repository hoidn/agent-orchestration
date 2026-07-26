"""Pure closed-matrix navigation views over one successful Stage-3 result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from orchestrator.workflow_lisp.compiler import LinkedStage3CompileResult
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import CallExpr, ProcedureCallExpr
from orchestrator.workflow_lisp.form_registry import registered_form_heads
from orchestrator.workflow_lisp.modules import build_import_scope
from orchestrator.workflow_lisp.spans import SourceSpan

from .coordinates import CoordinateTranslationError, source_span_to_lsp_range


@dataclass(frozen=True, slots=True)
class DefinitionLink:
    """One exact authored call-head span and its compiler definition."""

    callee_span: SourceSpan
    definition_span: SourceSpan


@dataclass(frozen=True, slots=True)
class NavigationSymbol:
    """One authored definition admitted by the v1 document-symbol matrix."""

    name: str
    kind: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class NavigationCompletion:
    """One compiler-visible callable or registered form head."""

    label: str
    kind: str


@dataclass(frozen=True, slots=True)
class NavigationIndex:
    """Immutable compiler-derived navigation views for one build result."""

    definition_links: tuple[DefinitionLink, ...]
    symbols_by_path: tuple[tuple[Path, tuple[NavigationSymbol, ...]], ...]
    completions_by_path: tuple[
        tuple[Path, tuple[NavigationCompletion, ...]],
        ...,
    ]


def build_navigation_index(
    compile_result: LinkedStage3CompileResult,
) -> NavigationIndex:
    """Derive the complete v1 navigation index without reading source text."""

    if not isinstance(compile_result, LinkedStage3CompileResult):
        raise TypeError("navigation requires a LinkedStage3CompileResult")

    definition_spans = _definition_spans(compile_result)
    definition_links: list[DefinitionLink] = []
    symbols_by_path: dict[Path, list[NavigationSymbol]] = {}
    completions_by_path: dict[Path, tuple[NavigationCompletion, ...]] = {}

    for module_name in compile_result.graph.topological_order:
        compiled = compile_result.compiled_results_by_name.get(module_name)
        if compiled is None:
            continue
        module_path = _module_path(
            compile_result,
            module_name=module_name,
            fallback_span=compiled.module.span,
        )
        symbols = symbols_by_path.setdefault(module_path, [])
        resolved_source = compile_result.graph.modules_by_name.get(module_name)
        if (
            resolved_source is not None
            and resolved_source.syntax_module.module_directive is not None
        ):
            directive = resolved_source.syntax_module.module_directive
            symbols.append(
                NavigationSymbol(
                    name=directive.name,
                    kind="module",
                    span=directive.span,
                )
            )

        local_callable_names: set[str] = set()
        for typed_procedure in compiled.typed_procedures:
            definition = typed_procedure.definition
            if (
                typed_procedure.specialization is not None
                or definition.generated_local_procedure is not None
                or definition.expansion_stack
            ):
                continue
            local_callable_names.add(_authored_callable_name(definition.name))
            symbols.append(
                NavigationSymbol(
                    name=_authored_callable_name(definition.name),
                    kind="procedure",
                    span=definition.span,
                )
            )
            definition_links.extend(
                _definition_links_for_expr(
                    typed_procedure.typed_body.expr,
                    definition_spans=definition_spans,
                )
            )
        for typed_workflow in compiled.typed_workflows:
            definition = typed_workflow.definition
            if typed_workflow.specialization is not None or definition.expansion_stack:
                continue
            local_callable_names.add(_authored_callable_name(definition.name))
            symbols.append(
                NavigationSymbol(
                    name=_authored_callable_name(definition.name),
                    kind="workflow",
                    span=definition.span,
                )
            )
            definition_links.extend(
                _definition_links_for_expr(
                    typed_workflow.typed_body.expr,
                    definition_spans=definition_spans,
                )
            )

        imported_callable_names: set[str] = set()
        if compiled.module.module_name is not None:
            import_scope = build_import_scope(
                compiled.module,
                export_surfaces_by_name=(
                    compile_result.graph.export_surfaces_by_name
                ),
            )
            imported_callable_names.update(import_scope.procedure_bindings)
            imported_callable_names.update(import_scope.workflow_bindings)
        callable_names = local_callable_names | imported_callable_names
        form_heads = set(registered_form_heads())
        completions_by_path[module_path] = tuple(
            NavigationCompletion(
                label=label,
                kind="callable" if label in callable_names else "form",
            )
            for label in sorted(callable_names | form_heads)
        )

    normalized_symbols = tuple(
        (
            path,
            tuple(
                sorted(
                    symbols,
                    key=lambda symbol: (
                        symbol.span.start.offset,
                        symbol.span.end.offset,
                        symbol.name,
                    ),
                )
            ),
        )
        for path, symbols in sorted(
            symbols_by_path.items(),
            key=lambda item: item[0].as_posix(),
        )
    )
    normalized_completions = tuple(
        sorted(
            completions_by_path.items(),
            key=lambda item: item[0].as_posix(),
        )
    )
    return NavigationIndex(
        definition_links=tuple(
            sorted(
                definition_links,
                key=lambda link: (
                    Path(link.callee_span.start.path)
                    .resolve(strict=False)
                    .as_posix(),
                    link.callee_span.start.offset,
                    link.callee_span.end.offset,
                ),
            )
        ),
        symbols_by_path=normalized_symbols,
        completions_by_path=normalized_completions,
    )


def definition_at_lsp_position(
    index: NavigationIndex,
    *,
    source_path: str | Path,
    line: int,
    character: int,
    accepted_text_by_path: Mapping[Path, str],
) -> SourceSpan | None:
    """Return a target only for a cursor inside an exact indexed callee span."""

    path = Path(source_path).resolve(strict=False)
    accepted_text = accepted_text_by_path.get(path)
    if not isinstance(accepted_text, str):
        return None
    for link in index.definition_links:
        callee_path = Path(link.callee_span.start.path).resolve(strict=False)
        if callee_path != path:
            continue
        if lsp_position_in_source_span(
            link.callee_span,
            line=line,
            character=character,
            accepted_text=accepted_text,
        ):
            return link.definition_span
    return None


def symbols_for_document(
    index: NavigationIndex,
    *,
    source_path: str | Path,
) -> tuple[NavigationSymbol, ...]:
    """Return only authored module/procedure/workflow symbols for one path."""

    path = Path(source_path).resolve(strict=False)
    return dict(index.symbols_by_path).get(path, ())


def completion_for_document(
    index: NavigationIndex,
    *,
    source_path: str | Path,
) -> tuple[NavigationCompletion, ...]:
    """Return the exact visibility-plus-registry completion set."""

    path = Path(source_path).resolve(strict=False)
    return dict(index.completions_by_path).get(path, ())


def lsp_position_in_source_span(
    span: SourceSpan,
    *,
    line: int,
    character: int,
    accepted_text: str,
) -> bool:
    """Check one 0-based UTF-16 LSP position against a half-open raw span."""

    if type(line) is not int or type(character) is not int:
        return False
    if line < 0 or character < 0:
        return False
    try:
        lsp_range = source_span_to_lsp_range(span, accepted_text)
    except CoordinateTranslationError:
        return False
    position = (line, character)
    start = (
        lsp_range["start"]["line"],
        lsp_range["start"]["character"],
    )
    end = (
        lsp_range["end"]["line"],
        lsp_range["end"]["character"],
    )
    return start <= position < end


def _definition_spans(
    compile_result: LinkedStage3CompileResult,
) -> dict[tuple[str, str], SourceSpan]:
    spans: dict[tuple[str, str], SourceSpan] = {}
    for compiled in compile_result.compiled_results_by_name.values():
        procedure_definitions = (
            compiled.procedure_catalog.definitions_by_name
        )
        for name, definition in procedure_definitions.items():
            if definition.expansion_stack:
                continue
            spans[("procedure", name)] = definition.span
        workflow_definitions = compiled.workflow_catalog.definitions_by_name
        for name, definition in workflow_definitions.items():
            if definition.expansion_stack:
                continue
            spans[("workflow", name)] = definition.span
    return spans


def _definition_links_for_expr(
    expr: object,
    *,
    definition_spans: Mapping[tuple[str, str], SourceSpan],
) -> tuple[DefinitionLink, ...]:
    links: list[DefinitionLink] = []
    for node in walk_expr(expr):
        if type(node) not in {CallExpr, ProcedureCallExpr}:
            continue
        callee_span = node.authored_callee_span
        if callee_span is None:
            continue
        callable_kind = (
            "workflow" if type(node) is CallExpr else "procedure"
        )
        definition_span = definition_spans.get(
            (callable_kind, node.callee_name)
        )
        if definition_span is None:
            continue
        links.append(
            DefinitionLink(
                callee_span=callee_span,
                definition_span=definition_span,
            )
        )
    return tuple(links)


def _module_path(
    compile_result: LinkedStage3CompileResult,
    *,
    module_name: str,
    fallback_span: SourceSpan,
) -> Path:
    resolved = compile_result.graph.modules_by_name.get(module_name)
    if resolved is not None:
        return resolved.path.resolve(strict=False)
    return Path(fallback_span.start.path).resolve(strict=False)


def _authored_callable_name(canonical_name: str) -> str:
    return canonical_name.rsplit("::", 1)[-1]


__all__ = [
    "DefinitionLink",
    "NavigationCompletion",
    "NavigationIndex",
    "NavigationSymbol",
    "build_navigation_index",
    "completion_for_document",
    "definition_at_lsp_position",
    "lsp_position_in_source_span",
    "symbols_for_document",
]
