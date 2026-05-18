"""Syntax-object layer for the workflow Lisp Stage 1 frontend."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .sexpr import KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom
from .spans import SourceSpan


@dataclass(frozen=True)
class SyntaxNode:
    """Syntax wrapper over one authored S-expression node."""

    datum: SExpr
    span: SourceSpan
    module_path: str
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowLispSyntaxModule:
    """Validated syntax-layer module header plus top-level forms."""

    language_version: str
    target_dsl_version: str
    forms: tuple[SyntaxNode, ...]
    span: SourceSpan
    module_path: str


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
        forms.append(_build_top_level_syntax_node(item, module_path))

    if ":language" not in header_values:
        _raise_error("missing required header `:language`", span=root.span)
    if ":target-dsl" not in header_values:
        _raise_error("missing required header `:target-dsl`", span=root.span)
    return WorkflowLispSyntaxModule(
        language_version=header_values[":language"],
        target_dsl_version=header_values[":target-dsl"],
        forms=tuple(forms),
        span=root.span,
        module_path=module_path,
    )


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
    return SyntaxNode(
        datum=item,
        span=item.span,
        module_path=module_path,
        form_path=tuple(form_path),
    )


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
