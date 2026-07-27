"""Pure closed-matrix navigation views over one successful Stage-3 result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from orchestrator.workflow_lisp.authored_symbols import (
    project_authored_symbols,
)
from orchestrator.workflow_lisp.compiler import LinkedStage3CompileResult
from orchestrator.workflow_lisp.effects import render_effect_set
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    ProcedureCallExpr,
    ProcRefLiteralExpr,
    ProviderResultExpr,
)
from orchestrator.workflow_lisp.modules import build_import_scope
from orchestrator.workflow_lisp.procedures import (
    ProcedureDef,
    ProcedureSignature,
)
from orchestrator.workflow_lisp.prompts import (
    PromptApplicationExpr,
    PromptCatalog,
)
from orchestrator.workflow_lisp.spans import SourceSpan
from orchestrator.workflow_lisp.syntax import (
    SyntaxIdentifier,
    SyntaxList,
    WorkflowLispSyntaxModule,
    ensure_syntax_datum,
)
from orchestrator.workflow_lisp.type_env import TypeRef, render_type_ref
from orchestrator.workflow_lisp.workflows import WorkflowSignature

from .coordinates import CoordinateTranslationError, source_span_to_lsp_range


@dataclass(frozen=True, slots=True)
class DefinitionLink:
    """One exact authored reference and its compiler-owned target."""

    reference_kind: str
    reference_span: SourceSpan
    canonical_target: str
    target_kind: str
    definition_span: SourceSpan

    def __post_init__(self) -> None:
        if self.reference_kind not in _REFERENCE_KINDS:
            raise ValueError(
                f"unsupported definition reference kind: {self.reference_kind}"
            )
        if self.target_kind not in _TARGET_KINDS:
            raise ValueError(
                f"unsupported definition target kind: {self.target_kind}"
            )


@dataclass(frozen=True, slots=True)
class NavigationSymbol:
    """One compiler-proven direct authored definition."""

    name: str
    kind: str
    definition_span: SourceSpan
    selection_span: SourceSpan
    source_ordinal: int


@dataclass(frozen=True, slots=True)
class NavigationCompletion:
    """One compiler-visible callable or registered form head."""

    label: str
    kind: str
    canonical_target: str
    detail: str


@dataclass(frozen=True, slots=True)
class NavigationIndex:
    """Immutable compiler-derived navigation views for one build result."""

    definition_links: tuple[DefinitionLink, ...]
    symbols_by_path: tuple[tuple[Path, tuple[NavigationSymbol, ...]], ...]
    completions_by_path: tuple[
        tuple[Path, tuple[NavigationCompletion, ...]],
        ...,
    ]


def project_form_completion_rows(
    heads: tuple[str, ...],
) -> tuple[NavigationCompletion, ...]:
    """Validate and project one exact process-frozen form-head catalog."""

    if type(heads) is not tuple:
        raise TypeError("form completion heads must be a tuple")
    if any(type(head) is not str for head in heads):
        raise TypeError("form completion heads must contain only strings")
    if any(not head for head in heads):
        raise ValueError("form completion heads must be non-empty")
    if len(set(heads)) != len(heads):
        raise ValueError("form completion heads must be unique")
    if tuple(sorted(heads)) != heads:
        raise ValueError("form completion heads must be lexicographically sorted")
    return tuple(
        NavigationCompletion(
            label=head,
            kind="form",
            canonical_target=head,
            detail="form",
        )
        for head in heads
    )


def build_navigation_index(
    compile_result: LinkedStage3CompileResult,
    *,
    frozen_form_completions: tuple[NavigationCompletion, ...],
) -> NavigationIndex:
    """Derive the complete v1 navigation index without reading source text."""

    if not isinstance(compile_result, LinkedStage3CompileResult):
        raise TypeError("navigation requires a LinkedStage3CompileResult")
    _validate_frozen_form_completions(frozen_form_completions)

    definition_spans = _definition_spans(compile_result)
    procedure_definitions = _procedure_definitions(compile_result)
    definition_links: dict[
        tuple[str, str, int, int],
        DefinitionLink,
    ] = {}
    reference_kinds_by_span: dict[
        tuple[str, int, int],
        str,
    ] = {}
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
        resolved_source = compile_result.graph.modules_by_name[module_name]
        projected_symbols = tuple(
            NavigationSymbol(
                name=row.name,
                kind=row.kind,
                definition_span=row.definition_span,
                selection_span=row.selection_span,
                source_ordinal=row.source_ordinal,
            )
            for row in project_authored_symbols(
                resolved_source,
                compiled,
            )
        )
        symbols.extend(projected_symbols)
        syntax_lists = _original_syntax_lists(
            resolved_source.syntax_module
        )
        prompt_catalog = compiled.prompt_catalog

        for typed_procedure in compiled.typed_procedures:
            definition = typed_procedure.definition
            if (
                typed_procedure.specialization is not None
                or definition.generated_local_procedure is not None
                or definition.expansion_stack
            ):
                continue
            for link in _reference_links_for_authored_owner(
                typed_procedure.typed_body.expr,
                definition_spans=definition_spans,
                syntax_lists=syntax_lists,
                prompt_catalog=prompt_catalog,
                procedure_definitions=procedure_definitions,
            ):
                _insert_unique_reference_link(
                    definition_links,
                    reference_kinds_by_span,
                    link,
                )
        for typed_workflow in compiled.typed_workflows:
            definition = typed_workflow.definition
            if typed_workflow.specialization is not None or definition.expansion_stack:
                continue
            for link in _reference_links_for_authored_owner(
                typed_workflow.typed_body.expr,
                definition_spans=definition_spans,
                syntax_lists=syntax_lists,
                prompt_catalog=prompt_catalog,
                procedure_definitions=procedure_definitions,
            ):
                _insert_unique_reference_link(
                    definition_links,
                    reference_kinds_by_span,
                    link,
                )

        completion_rows: list[NavigationCompletion] = []
        for symbol in projected_symbols:
            if symbol.kind == "procedure":
                signature = compiled.procedure_catalog.signatures_by_name.get(
                    symbol.name
                )
                if signature is None:
                    raise ValueError(
                        "authored procedure completion is missing its "
                        f"compiler signature: {symbol.name}"
                    )
                completion_rows.append(
                    _procedure_completion(
                        label=symbol.name,
                        canonical_target=signature.name,
                        signature=signature,
                    )
                )
            elif symbol.kind == "workflow":
                signature = compiled.workflow_catalog.signatures_by_name.get(
                    symbol.name
                )
                if signature is None:
                    raise ValueError(
                        "authored workflow completion is missing its "
                        f"compiler signature: {symbol.name}"
                    )
                completion_rows.append(
                    _workflow_completion(
                        label=symbol.name,
                        canonical_target=signature.name,
                        signature=signature,
                    )
                )

        if compiled.module.module_name is not None:
            import_scope = build_import_scope(
                compiled.module,
                export_surfaces_by_name=(
                    compile_result.graph.export_surfaces_by_name
                ),
            )
            for label, binding in import_scope.procedure_bindings.items():
                signature = (
                    compiled.procedure_catalog.signatures_by_name.get(
                        binding.canonical_name
                    )
                )
                if signature is None:
                    raise ValueError(
                        "imported procedure completion is missing its "
                        f"compiler signature: {binding.canonical_name}"
                    )
                completion_rows.append(
                    _procedure_completion(
                        label=label,
                        canonical_target=binding.canonical_name,
                        signature=signature,
                    )
                )
            for label, binding in import_scope.workflow_bindings.items():
                signature = (
                    compiled.workflow_catalog.signatures_by_name.get(
                        binding.canonical_name
                    )
                )
                if signature is None:
                    raise ValueError(
                        "imported workflow completion is missing its "
                        f"compiler signature: {binding.canonical_name}"
                    )
                completion_rows.append(
                    _workflow_completion(
                        label=label,
                        canonical_target=binding.canonical_name,
                        signature=signature,
                    )
                )
        completion_rows.extend(frozen_form_completions)
        completions_by_path[module_path] = tuple(
            sorted(
                completion_rows,
                key=lambda item: (
                    item.label,
                    _COMPLETION_KIND_RANK[item.kind],
                    item.canonical_target,
                ),
            )
        )

    normalized_symbols = tuple(
        (
            path,
            tuple(
                sorted(
                    symbols,
                    key=lambda symbol: (
                        symbol.definition_span.start.offset,
                        symbol.source_ordinal,
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
                definition_links.values(),
                key=lambda link: (
                    Path(link.reference_span.start.path)
                    .resolve(strict=False)
                    .as_posix(),
                    link.reference_span.start.offset,
                    link.reference_span.end.offset,
                    link.reference_kind,
                    link.target_kind,
                    link.canonical_target,
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
    """Return a target only for a cursor inside an exact reference span."""

    path = Path(source_path).resolve(strict=False)
    accepted_text = accepted_text_by_path.get(path)
    if not isinstance(accepted_text, str):
        return None
    for link in index.definition_links:
        reference_path = Path(
            link.reference_span.start.path
        ).resolve(strict=False)
        if reference_path != path:
            continue
        if lsp_position_in_source_span(
            link.reference_span,
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
    """Return all compiler-proven authored symbols for one source path."""

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
            _insert_unique_definition_target(
                spans,
                target_kind="procedure",
                canonical_target=name,
                definition_span=definition.span,
            )
        workflow_definitions = compiled.workflow_catalog.definitions_by_name
        for name, definition in workflow_definitions.items():
            if definition.expansion_stack:
                continue
            _insert_unique_definition_target(
                spans,
                target_kind="workflow",
                canonical_target=name,
                definition_span=definition.span,
            )
        prompt_catalog = compiled.prompt_catalog
        if isinstance(prompt_catalog, PromptCatalog):
            for definition in prompt_catalog.definitions_by_name.values():
                declaration = definition.declaration
                if declaration.expansion_stack:
                    continue
                _insert_unique_definition_target(
                    spans,
                    target_kind="prompt",
                    canonical_target=definition.qualified_name,
                    definition_span=declaration.span,
                )
    return spans


def _procedure_definitions(
    compile_result: LinkedStage3CompileResult,
) -> dict[str, ProcedureDef]:
    """Return the unique canonical definitions from compiler catalogs."""

    definitions: dict[str, ProcedureDef] = {}
    for compiled in compile_result.compiled_results_by_name.values():
        for name, definition in (
            compiled.procedure_catalog.definitions_by_name.items()
        ):
            if definition.name != name:
                raise ValueError(
                    "procedure catalog definition canonical identity mismatch"
                )
            existing = definitions.get(name)
            if existing is not None and existing != definition:
                raise ValueError(
                    "procedure catalog has conflicting canonical definitions: "
                    f"{name}"
                )
            definitions[name] = definition
    return definitions


def _insert_unique_definition_target(
    targets: dict[tuple[str, str], SourceSpan],
    *,
    target_kind: str,
    canonical_target: str,
    definition_span: SourceSpan,
) -> None:
    key = (target_kind, canonical_target)
    existing = targets.get(key)
    if existing is not None and existing != definition_span:
        raise ValueError(
            "definition target has conflicting authored spans: "
            f"{target_kind} {canonical_target}"
        )
    targets[key] = definition_span


def _insert_unique_reference_link(
    links_by_occurrence: dict[
        tuple[str, str, int, int],
        DefinitionLink,
    ],
    reference_kinds_by_span: dict[tuple[str, int, int], str],
    link: DefinitionLink,
) -> None:
    canonical_path = (
        Path(link.reference_span.start.path)
        .resolve(strict=False)
        .as_posix()
    )
    span_key = (
        canonical_path,
        link.reference_span.start.offset,
        link.reference_span.end.offset,
    )
    existing_kind = reference_kinds_by_span.get(span_key)
    if existing_kind is not None and existing_kind != link.reference_kind:
        raise ValueError(
            "definition reference span has conflicting reference kinds: "
            f"{existing_kind} and {link.reference_kind}"
        )
    occurrence_key = (link.reference_kind, *span_key)
    existing = links_by_occurrence.get(occurrence_key)
    if existing is not None and existing != link:
        raise ValueError(
            "definition reference occurrence has conflicting semantic facts"
        )
    reference_kinds_by_span[span_key] = link.reference_kind
    links_by_occurrence[occurrence_key] = link


def _validate_frozen_form_completions(
    rows: tuple[NavigationCompletion, ...],
) -> None:
    if type(rows) is not tuple:
        raise TypeError("frozen form completions must be a tuple")
    if any(type(row) is not NavigationCompletion for row in rows):
        raise TypeError(
            "frozen form completions must contain NavigationCompletion rows"
        )
    labels = tuple(row.label for row in rows)
    if any(type(label) is not str for label in labels):
        raise TypeError("frozen form completion labels must be strings")
    if any(not label for label in labels):
        raise ValueError("frozen form completion labels must be non-empty")
    if len(set(labels)) != len(labels):
        raise ValueError("frozen form completion labels must be unique")
    if tuple(sorted(labels)) != labels:
        raise ValueError(
            "frozen form completion labels must be lexicographically sorted"
        )
    if any(
        row.kind != "form"
        or row.canonical_target != row.label
        or row.detail != "form"
        for row in rows
    ):
        raise ValueError(
            "frozen form completions must contain exact projected form rows"
        )


def _original_syntax_lists(
    syntax_module: WorkflowLispSyntaxModule,
) -> tuple[SyntaxList, ...]:
    """Return original retained lists in deterministic source-tree order."""

    rows: list[SyntaxList] = []

    def visit(datum: object) -> None:
        if not isinstance(datum, SyntaxList):
            return
        rows.append(datum)
        for item in datum.items:
            visit(item)

    for form in syntax_module.forms:
        visit(
            ensure_syntax_datum(
                form.datum,
                module_path=form.module_path,
                form_path=form.form_path,
            )
        )
    return tuple(rows)


def _prompt_application_assertions(
    expr: object,
) -> tuple[PromptApplicationExpr, ...]:
    """Return only final direct prompt applications retained by Stage 3."""

    return tuple(
        node.prompt
        for node in walk_expr(expr)
        if type(node) is ProviderResultExpr
        and type(node.prompt) is PromptApplicationExpr
    )


def _reference_links_for_authored_owner(
    expr: object,
    *,
    definition_spans: Mapping[tuple[str, str], SourceSpan],
    syntax_lists: tuple[SyntaxList, ...],
    prompt_catalog: object,
    procedure_definitions: Mapping[str, ProcedureDef],
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
                reference_kind=(
                    "workflow-call"
                    if callable_kind == "workflow"
                    else "procedure-call"
                ),
                reference_span=callee_span,
                canonical_target=node.callee_name,
                target_kind=callable_kind,
                definition_span=definition_span,
            )
        )
    for occurrence in walk_expr(expr):
        if type(occurrence) is not ProcRefLiteralExpr:
            continue
        if occurrence.expansion_stack:
            continue
        links.append(
            _project_proc_ref_link(
                occurrence,
                syntax_lists=syntax_lists,
                procedure_definitions=procedure_definitions,
                definition_spans=definition_spans,
            )
        )
    for application in _prompt_application_assertions(expr):
        links.append(
            _project_prompt_application_link(
                application,
                syntax_lists=syntax_lists,
                prompt_catalog=prompt_catalog,
                definition_spans=definition_spans,
            )
        )
    return tuple(links)


def _project_proc_ref_link(
    occurrence: ProcRefLiteralExpr,
    *,
    syntax_lists: tuple[SyntaxList, ...],
    procedure_definitions: Mapping[str, ProcedureDef],
    definition_spans: Mapping[tuple[str, str], SourceSpan],
) -> DefinitionLink:
    """Join one retained proc-ref assertion to its exact authored name."""

    if occurrence.expansion_stack:
        raise ValueError(
            "proc-ref navigation requires an unexpanded occurrence"
        )
    matching_lists = tuple(
        syntax_list
        for syntax_list in syntax_lists
        if syntax_list.span == occurrence.span
    )
    if len(matching_lists) != 1:
        raise ValueError(
            "proc-ref navigation requires one original syntax match"
        )
    syntax_list = matching_lists[0]
    if syntax_list.expansion_stack:
        raise ValueError(
            "proc-ref navigation requires unexpanded original syntax"
        )
    if (
        len(syntax_list.items) != 2
        or type(syntax_list.items[0]) is not SyntaxIdentifier
        or syntax_list.items[0].resolved_name != "proc-ref"
        or type(syntax_list.items[1]) is not SyntaxIdentifier
    ):
        raise ValueError(
            "proc-ref navigation requires an exact proc-ref name form"
        )
    name = syntax_list.items[1]
    if name.resolved_name != occurrence.authored_name:
        raise ValueError(
            "proc-ref navigation authored identity mismatch"
        )
    _validate_authored_token_span(
        name.span,
        whole_form_span=occurrence.span,
    )
    definition = procedure_definitions.get(occurrence.target_name)
    if definition is None:
        raise ValueError(
            "proc-ref navigation target is absent from procedure catalogs"
        )
    if definition.name != occurrence.target_name:
        raise ValueError(
            "proc-ref navigation canonical identity mismatch"
        )
    if (
        definition.generated_local_procedure is not None
        or definition.expansion_stack
    ):
        raise ValueError(
            "proc-ref navigation requires an authored procedure target"
        )
    definition_span = definition_spans.get(
        ("procedure", occurrence.target_name)
    )
    if definition_span is None:
        raise ValueError(
            "proc-ref navigation is missing its authored target"
        )
    if definition_span != definition.span:
        raise ValueError(
            "proc-ref navigation target span mismatch"
        )
    _validate_target_definition_span(definition_span)
    return DefinitionLink(
        reference_kind="proc-ref",
        reference_span=name.span,
        canonical_target=occurrence.target_name,
        target_kind="procedure",
        definition_span=definition_span,
    )


def _project_prompt_application_link(
    application: PromptApplicationExpr,
    *,
    syntax_lists: tuple[SyntaxList, ...],
    prompt_catalog: object,
    definition_spans: Mapping[tuple[str, str], SourceSpan],
) -> DefinitionLink:
    """Join one retained prompt assertion to one exact authored head."""

    if application.expansion_stack:
        raise ValueError(
            "prompt application navigation requires an unexpanded occurrence"
        )
    matching_lists = tuple(
        syntax_list
        for syntax_list in syntax_lists
        if syntax_list.span == application.span
    )
    if len(matching_lists) != 1:
        raise ValueError(
            "prompt application navigation requires one original syntax match"
        )
    syntax_list = matching_lists[0]
    if syntax_list.expansion_stack:
        raise ValueError(
            "prompt application navigation requires unexpanded original syntax"
        )
    if not syntax_list.items or type(syntax_list.items[0]) is not SyntaxIdentifier:
        raise ValueError(
            "prompt application navigation requires an identifier head"
        )
    head = syntax_list.items[0]
    _validate_authored_token_span(
        head.span,
        whole_form_span=application.span,
    )
    if not isinstance(prompt_catalog, PromptCatalog):
        raise ValueError(
            "prompt application navigation requires a compiler prompt catalog"
        )
    resolved = prompt_catalog.resolve(head.resolved_name)
    if resolved is None:
        raise ValueError(
            "prompt application navigation target is absent from the prompt catalog"
        )
    if resolved.qualified_name != application.prompt.qualified_name:
        raise ValueError(
            "prompt application navigation canonical identity mismatch"
        )
    if resolved.declaration.span != application.prompt.declaration.span:
        raise ValueError(
            "prompt application navigation declaration span mismatch"
        )
    if (
        resolved.declaration.expansion_stack
        or application.prompt.declaration.expansion_stack
    ):
        raise ValueError(
            "prompt application navigation requires an authored prompt target"
        )
    definition_span = definition_spans.get(
        ("prompt", application.prompt.qualified_name)
    )
    if definition_span is None:
        raise ValueError(
            "prompt application navigation is missing its authored target"
        )
    if definition_span != resolved.declaration.span:
        raise ValueError(
            "prompt application navigation target span mismatch"
        )
    _validate_target_definition_span(definition_span)
    return DefinitionLink(
        reference_kind="prompt-application",
        reference_span=head.span,
        canonical_target=application.prompt.qualified_name,
        target_kind="prompt",
        definition_span=definition_span,
    )


def _validate_target_definition_span(
    definition_span: SourceSpan,
) -> None:
    """Require one same-path, non-empty, positive target offset range."""

    if (
        definition_span.start.path != definition_span.end.path
        or definition_span.start.offset < 0
        or definition_span.end.offset <= definition_span.start.offset
    ):
        raise ValueError(
            "definition target span must be a non-empty same-path range"
        )


def _validate_authored_token_span(
    token_span: SourceSpan,
    *,
    whole_form_span: SourceSpan,
) -> None:
    """Require one non-empty same-path token strictly inside its form."""

    if (
        token_span.start.path != token_span.end.path
        or whole_form_span.start.path != whole_form_span.end.path
        or token_span.start.path != whole_form_span.start.path
        or token_span.start.offset >= token_span.end.offset
        or token_span.start.offset <= whole_form_span.start.offset
        or token_span.end.offset >= whole_form_span.end.offset
    ):
        raise ValueError(
            "definition reference token is not strictly contained in its form"
        )


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


_COMPLETION_KIND_RANK = {
    "procedure": 0,
    "workflow": 1,
    "form": 2,
}

_REFERENCE_KINDS = frozenset(
    {
        "procedure-call",
        "workflow-call",
        "prompt-application",
        "proc-ref",
    }
)
_TARGET_KINDS = frozenset({"procedure", "workflow", "prompt"})


def _procedure_completion(
    *,
    label: str,
    canonical_target: str,
    signature: ProcedureSignature,
) -> NavigationCompletion:
    return NavigationCompletion(
        label=label,
        kind="procedure",
        canonical_target=canonical_target,
        detail=(
            f"procedure ({_render_signature_params(signature.params)}) -> "
            f"{render_type_ref(signature.return_type_ref)} effects "
            f"{render_effect_set(signature.declared_effects)}"
        ),
    )


def _workflow_completion(
    *,
    label: str,
    canonical_target: str,
    signature: WorkflowSignature,
) -> NavigationCompletion:
    return NavigationCompletion(
        label=label,
        kind="workflow",
        canonical_target=canonical_target,
        detail=(
            f"workflow ({_render_signature_params(signature.params)}) -> "
            f"{render_type_ref(signature.return_type_ref)}"
        ),
    )


def _render_signature_params(
    params: tuple[tuple[str, TypeRef], ...],
) -> str:
    return ", ".join(
        f"{name}: {render_type_ref(type_ref)}"
        for name, type_ref in params
    )


__all__ = [
    "DefinitionLink",
    "NavigationCompletion",
    "NavigationIndex",
    "NavigationSymbol",
    "build_navigation_index",
    "completion_for_document",
    "definition_at_lsp_position",
    "lsp_position_in_source_span",
    "project_form_completion_rows",
    "symbols_for_document",
]
