"""Syntax-object layer for the workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .sexpr import BoolAtom, IntAtom, KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom
from .spans import SourceSpan


@dataclass(frozen=True)
class ExpansionFrame:
    """One macro-expansion provenance frame."""

    macro_name: str
    expansion_id: str
    call_span: SourceSpan
    definition_span: SourceSpan
    template_path: tuple[str, ...]


ExpansionStack = tuple[ExpansionFrame, ...]


@dataclass(frozen=True)
class SyntaxIdentifier:
    """One syntax-layer identifier with authored and resolved names."""

    display_name: str
    resolved_name: str
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack
    introduced_by_expansion_id: str | None = None


@dataclass(frozen=True)
class SyntaxKeyword:
    """One syntax-layer keyword atom."""

    value: str
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack


@dataclass(frozen=True)
class SyntaxString:
    """One syntax-layer string atom."""

    value: str
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack


@dataclass(frozen=True)
class SyntaxInt:
    """One syntax-layer int atom."""

    value: int
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack


@dataclass(frozen=True)
class SyntaxBool:
    """One syntax-layer bool atom."""

    value: bool
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack


SyntaxAtom = SyntaxIdentifier | SyntaxKeyword | SyntaxString | SyntaxInt | SyntaxBool


@dataclass(frozen=True)
class SyntaxList:
    """One recursive syntax list."""

    items: tuple["SyntaxDatum", ...]
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack


SyntaxDatum = SyntaxAtom | SyntaxList


@dataclass(frozen=True)
class SyntaxNode:
    """Top-level syntax wrapper over one authored or expanded form."""

    datum: SExpr | SyntaxDatum
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]

    @property
    def items(self) -> tuple[SyntaxDatum, ...]:
        datum = ensure_syntax_datum(self.datum, module_path=self.module_path, form_path=self.form_path)
        if isinstance(datum, SyntaxList):
            return datum.items
        return ()

    @property
    def expansion_stack(self) -> ExpansionStack:
        return syntax_expansion_stack(
            ensure_syntax_datum(self.datum, module_path=self.module_path, form_path=self.form_path)
        )


@dataclass(frozen=True)
class ModuleDirective:
    name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class ImportDirective:
    module_name: str
    alias: str
    only: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class ExportDirective:
    names: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowLispSyntaxModule:
    """Validated syntax-layer module header plus top-level forms."""

    language_version: str
    target_dsl_version: str
    module_directive: ModuleDirective | None
    imports: tuple[ImportDirective, ...]
    export_directive: ExportDirective | None
    forms: tuple[SyntaxNode, ...]
    span: SourceSpan
    module_path: str

    @property
    def module_name(self) -> str | None:
        if self.module_directive is None:
            return None
        return self.module_directive.name

    @property
    def exports(self) -> tuple[str, ...]:
        if self.export_directive is None:
            return ()
        return self.export_directive.names


def build_syntax_module(parse_tree: ListExpr) -> WorkflowLispSyntaxModule:
    """Validate the root module form and wrap top-level forms in syntax objects."""

    module_path = parse_tree.span.start.path
    if len(parse_tree.items) != 1:
        _raise_error(
            "expected exactly one top-level `(workflow-lisp ...)` form",
            span=parse_tree.span,
        )
    root = parse_tree.items[0]
    if not isinstance(root, ListExpr) or not root.items:
        _raise_error("expected top-level `(workflow-lisp ...)` form", span=parse_tree.span)
    head = root.items[0]
    if not isinstance(head, SymbolAtom) or head.value != "workflow-lisp":
        _raise_error("expected top-level `workflow-lisp` root form", span=root.span)

    header_values: dict[str, str] = {}
    forms: list[SyntaxNode] = []
    module_directive: ModuleDirective | None = None
    import_directives: list[ImportDirective] = []
    export_directive: ExportDirective | None = None
    seen_non_directive = False
    for item in root.items[1:]:
        if isinstance(item, ListExpr) and item.items and isinstance(item.items[0], KeywordAtom):
            keyword = item.items[0]
            if keyword.value not in {":language", ":target-dsl"}:
                _raise_error(f"unknown header keyword `{keyword.value}`", span=keyword.span)
            value = _parse_header_value(item)
            if keyword.value in header_values:
                _raise_error(f"duplicate header keyword `{keyword.value}`", span=keyword.span)
            header_values[keyword.value] = value.value
            if keyword.value == ":language" and value.value != "0.1":
                _raise_error(
                    f"unsupported language version `{value.value}`",
                    span=value.span,
                    code="language_version_unsupported",
                )
            if keyword.value == ":target-dsl" and value.value != "2.14":
                _raise_error(
                    f"unsupported target DSL `{value.value}`",
                    span=value.span,
                    code="target_dsl_unsupported",
                )
            continue
        syntax_node = _build_top_level_syntax_node(item, module_path)
        datum = syntax_node_datum(syntax_node)
        head_name = syntax_head_name(datum)
        if head_name == "defmodule":
            if seen_non_directive or import_directives or export_directive is not None:
                _raise_error(
                    "`defmodule` must appear before imports, exports, or ordinary definitions",
                    span=syntax_node.span,
                    code="frontend_parse_error",
                )
            if module_directive is not None:
                _raise_error(
                    "duplicate `defmodule` directive",
                    span=syntax_node.span,
                    code="frontend_parse_error",
                )
            module_directive = _parse_module_directive(syntax_node, datum)
            continue
        if head_name == "import":
            if seen_non_directive or export_directive is not None:
                _raise_error(
                    "`import` directives must appear before `export` and ordinary definitions",
                    span=syntax_node.span,
                    code="frontend_parse_error",
                )
            import_directives.append(_parse_import_directive(syntax_node, datum))
            continue
        if head_name == "export":
            if seen_non_directive:
                _raise_error(
                    "`export` must appear before ordinary definitions",
                    span=syntax_node.span,
                    code="frontend_parse_error",
                )
            if export_directive is not None:
                _raise_error(
                    "duplicate `export` directive",
                    span=syntax_node.span,
                    code="frontend_parse_error",
                )
            export_directive = _parse_export_directive(syntax_node, datum)
            continue
        seen_non_directive = True
        forms.append(syntax_node)

    if ":language" not in header_values:
        _raise_error("missing required header `:language`", span=root.span)
    if ":target-dsl" not in header_values:
        _raise_error("missing required header `:target-dsl`", span=root.span)
    if module_directive is None and (import_directives or export_directive is not None):
        _raise_error(
            "`import` and `export` require a preceding `defmodule` directive",
            span=root.span,
            code="module_declaration_missing",
        )
    return WorkflowLispSyntaxModule(
        language_version=header_values[":language"],
        target_dsl_version=header_values[":target-dsl"],
        module_directive=module_directive,
        imports=tuple(import_directives),
        export_directive=export_directive,
        forms=tuple(forms),
        span=root.span,
        module_path=module_path,
    )


def ensure_syntax_datum(
    datum: SExpr | SyntaxDatum,
    *,
    module_path: str,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
) -> SyntaxDatum:
    """Return one recursive syntax datum, converting raw reader nodes on demand."""

    if isinstance(
        datum,
        (SyntaxIdentifier, SyntaxKeyword, SyntaxString, SyntaxInt, SyntaxBool, SyntaxList),
    ):
        return datum
    if isinstance(datum, SymbolAtom):
        return SyntaxIdentifier(
            display_name=datum.value,
            resolved_name=datum.value,
            span=datum.span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(datum, KeywordAtom):
        return SyntaxKeyword(
            value=datum.value,
            span=datum.span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(datum, StringAtom):
        return SyntaxString(
            value=datum.value,
            span=datum.span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(datum, IntAtom):
        return SyntaxInt(
            value=datum.value,
            span=datum.span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(datum, BoolAtom):
        return SyntaxBool(
            value=datum.value,
            span=datum.span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(datum, ListExpr):
        return SyntaxList(
            items=tuple(
                ensure_syntax_datum(
                    item,
                    module_path=module_path,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                for item in datum.items
            ),
            span=datum.span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    raise TypeError(f"unsupported syntax datum: {type(datum)!r}")


def syntax_node_datum(node: SyntaxNode) -> SyntaxDatum:
    """Return one syntax node's recursive datum."""

    return ensure_syntax_datum(node.datum, module_path=node.module_path, form_path=node.form_path)


def syntax_head_name(datum: SyntaxDatum) -> str | None:
    """Return the resolved head symbol of one syntax list."""

    if not isinstance(datum, SyntaxList) or not datum.items:
        return None
    head = datum.items[0]
    if isinstance(head, SyntaxIdentifier):
        return head.resolved_name
    return None


def syntax_identifier(node: object) -> SyntaxIdentifier | None:
    """Return one identifier syntax node when available."""

    if isinstance(node, SyntaxIdentifier):
        return node
    return None


def syntax_head(node: SyntaxNode | SyntaxDatum) -> SyntaxIdentifier | None:
    """Return the identifier head of one syntax list or top-level form."""

    datum = syntax_node_datum(node) if isinstance(node, SyntaxNode) else node
    if not isinstance(datum, SyntaxList) or not datum.items:
        return None
    return syntax_identifier(datum.items[0])


def syntax_display_name(datum: object) -> str | None:
    """Return the authored display name of one identifier."""

    if isinstance(datum, SyntaxIdentifier):
        return datum.display_name
    return None


def syntax_resolved_name(datum: object) -> str | None:
    """Return the resolved name of one identifier."""

    if isinstance(datum, SyntaxIdentifier):
        return datum.resolved_name
    return None


def syntax_span(datum: SyntaxDatum) -> SourceSpan:
    """Return the source span for one syntax datum."""

    return datum.span


def syntax_expansion_stack(datum: SyntaxDatum) -> ExpansionStack:
    """Return one syntax datum's expansion provenance."""

    return datum.expansion_stack


def syntax_with_items(datum: SyntaxList, items: tuple[SyntaxDatum, ...]) -> SyntaxList:
    """Return one syntax list with updated items."""

    return replace(datum, items=items)


def clone_caller_syntax(datum: SyntaxDatum) -> SyntaxDatum:
    """Clone caller-authored syntax while preserving authored metadata."""

    if isinstance(datum, SyntaxList):
        return replace(datum, items=tuple(clone_caller_syntax(item) for item in datum.items))
    return replace(datum)


def clone_template_syntax(
    datum: SyntaxDatum,
    *,
    frame: ExpansionFrame,
    introduced_by_expansion_id: str | None = None,
) -> SyntaxDatum:
    """Clone template-authored syntax into one expansion provenance frame."""

    stack = datum.expansion_stack + (frame,)
    if isinstance(datum, SyntaxList):
        return replace(
            datum,
            items=tuple(
                clone_template_syntax(
                    item,
                    frame=frame,
                    introduced_by_expansion_id=introduced_by_expansion_id,
                )
                for item in datum.items
            ),
            expansion_stack=stack,
        )
    if isinstance(datum, SyntaxIdentifier):
        return replace(
            datum,
            expansion_stack=stack,
            introduced_by_expansion_id=introduced_by_expansion_id,
        )
    return replace(datum, expansion_stack=stack)


def introduced_identifier(
    identifier: SyntaxIdentifier,
    *,
    macro_name: str,
    expansion_id: str,
) -> SyntaxIdentifier:
    """Return one deterministically hygienic identifier binding or reference."""

    return replace(
        identifier,
        resolved_name=f"%macro__{macro_name}__{expansion_id}__{identifier.display_name}",
        introduced_by_expansion_id=expansion_id,
    )


def top_level_form_path(datum: SyntaxDatum) -> tuple[str, ...]:
    """Derive one deterministic top-level form path from expanded syntax."""

    head = syntax_head_name(datum)
    if head is None:
        return ("workflow-lisp",)
    form_path = ["workflow-lisp", syntax_display_name(datum.items[0]) or head]  # type: ignore[attr-defined]
    if (
        isinstance(datum, SyntaxList)
        and len(datum.items) > 1
        and isinstance(datum.items[1], SyntaxIdentifier)
    ):
        form_path.append(datum.items[1].display_name)
    return tuple(form_path)


def _parse_header_value(form: ListExpr) -> StringAtom:
    if len(form.items) != 2:
        _raise_error("module header forms must contain one keyword and one string value", span=form.span)
    value = form.items[1]
    if not isinstance(value, StringAtom):
        _raise_error("module header values must be strings", span=value.span)
    return value


def _build_top_level_syntax_node(item: SExpr, module_path: str) -> SyntaxNode:
    if not isinstance(item, ListExpr) or not item.items:
        _raise_error("top-level module entries must be non-empty lists", span=item.span)
    head = item.items[0]
    if not isinstance(head, SymbolAtom):
        _raise_error("top-level forms must start with a symbol", span=head.span)
    form_path = ["workflow-lisp", head.value]
    if len(item.items) > 1 and isinstance(item.items[1], SymbolAtom):
        form_path.append(item.items[1].value)
    syntax = ensure_syntax_datum(item, module_path=module_path, form_path=tuple(form_path))
    return SyntaxNode(
        datum=syntax,
        span=syntax.span,
        module_path=module_path,
        form_path=tuple(form_path),
    )


def normalize_module_name(
    raw_name: str,
    *,
    span: SourceSpan,
    code: str = "module_name_invalid",
) -> str:
    if not raw_name or raw_name.startswith(("/", ".")) or raw_name.endswith(("/", ".")):
        _raise_error(f"invalid module name `{raw_name}`", span=span, code=code)
    if "/" in raw_name and "." in raw_name:
        _raise_error(f"invalid module name `{raw_name}`", span=span, code=code)
    separator = "/" if "/" in raw_name else "."
    parts = raw_name.split(separator)
    if any(not part for part in parts):
        _raise_error(f"invalid module name `{raw_name}`", span=span, code=code)
    return "/".join(parts)


def _parse_module_directive(node: SyntaxNode, datum: SyntaxDatum) -> ModuleDirective:
    if not isinstance(datum, SyntaxList) or len(datum.items) != 2:
        _raise_error("`defmodule` requires exactly one module name", span=node.span)
    name_identifier = syntax_identifier(datum.items[1])
    if name_identifier is None:
        _raise_error("`defmodule` requires a symbolic module name", span=node.span)
    return ModuleDirective(
        name=normalize_module_name(name_identifier.resolved_name, span=name_identifier.span),
        span=node.span,
        form_path=node.form_path,
    )


def _parse_import_directive(node: SyntaxNode, datum: SyntaxDatum) -> ImportDirective:
    if not isinstance(datum, SyntaxList) or len(datum.items) < 2:
        _raise_error("`import` requires a module name", span=node.span)
    module_identifier = syntax_identifier(datum.items[1])
    if module_identifier is None:
        _raise_error("`import` requires a symbolic module name", span=node.span)
    module_name = normalize_module_name(module_identifier.resolved_name, span=module_identifier.span)
    alias = module_name.rsplit("/", 1)[-1]
    only: tuple[str, ...] = ()
    remaining = datum.items[2:]
    if len(remaining) % 2 != 0:
        _raise_error("`import` requires keyword/value option pairs", span=node.span)
    seen_keywords: set[str] = set()
    for index in range(0, len(remaining), 2):
        keyword = remaining[index]
        value = remaining[index + 1]
        if not isinstance(keyword, SyntaxKeyword):
            _raise_error("`import` options must start with keywords", span=keyword.span)
        if keyword.value in seen_keywords:
            _raise_error(f"duplicate import option `{keyword.value}`", span=keyword.span)
        seen_keywords.add(keyword.value)
        if keyword.value == ":as":
            alias_identifier = syntax_identifier(value)
            if alias_identifier is None:
                _raise_error("`import :as` requires a symbolic alias", span=value.span)
            alias = alias_identifier.resolved_name
            continue
        if keyword.value == ":only":
            if not isinstance(value, SyntaxList):
                _raise_error("`import :only` requires a list of symbols", span=value.span)
            names: list[str] = []
            for item in value.items:
                member_identifier = syntax_identifier(item)
                if member_identifier is None:
                    _raise_error("`import :only` requires symbolic member names", span=item.span)
                names.append(member_identifier.resolved_name)
            only = tuple(names)
            continue
        _raise_error(f"unsupported import option `{keyword.value}`", span=keyword.span)
    return ImportDirective(
        module_name=module_name,
        alias=alias,
        only=only,
        span=node.span,
        form_path=node.form_path,
    )


def _parse_export_directive(node: SyntaxNode, datum: SyntaxDatum) -> ExportDirective:
    if not isinstance(datum, SyntaxList) or len(datum.items) < 2:
        _raise_error("`export` requires at least one member name", span=node.span)
    names: list[str] = []
    for item in datum.items[1:]:
        identifier = syntax_identifier(item)
        if identifier is None:
            _raise_error("`export` requires symbolic member names", span=item.span)
        names.append(identifier.resolved_name)
    return ExportDirective(names=tuple(names), span=node.span, form_path=node.form_path)


def _raise_error(message: str, *, span: SourceSpan, code: str = "frontend_parse_error") -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
            ),
        )
    )
