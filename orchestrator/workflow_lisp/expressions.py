"""Bounded Stage 2 expression AST and elaboration helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .sexpr import BoolAtom, IntAtom, KeywordAtom, ListExpr, StringAtom, SymbolAtom
from .spans import SourceSpan
from .syntax import SyntaxNode


@dataclass(frozen=True)
class NameExpr:
    """One lexical name reference."""

    name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class LiteralExpr:
    """One primitive literal."""

    value: str | int | bool
    literal_kind: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class FieldAccessExpr:
    """One dotted field-access chain rooted at a lexical name."""

    base: NameExpr
    fields: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class RecordExpr:
    """One record-construction form."""

    type_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class LetStarExpr:
    """One sequential lexical binding form."""

    bindings: tuple[tuple[str, "ExprNode"], ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class MatchArm:
    """One `match` variant arm."""

    variant_name: str
    binding_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class MatchExpr:
    """One exhaustive variant match form."""

    subject: "ExprNode"
    arms: tuple[MatchArm, ...]
    span: SourceSpan
    form_path: tuple[str, ...]


ExprNode = NameExpr | LiteralExpr | FieldAccessExpr | RecordExpr | LetStarExpr | MatchExpr


def elaborate_expression(node: SyntaxNode, *, bound_names: frozenset[str]) -> ExprNode:
    """Elaborate one syntax node into the bounded Stage 2 expression AST."""

    return _elaborate(node.datum, form_path=node.form_path, bound_names=bound_names)


def _elaborate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ExprNode:
    if isinstance(datum, StringAtom):
        return LiteralExpr(
            value=datum.value,
            literal_kind="string",
            span=datum.span,
            form_path=form_path,
        )
    if isinstance(datum, IntAtom):
        return LiteralExpr(
            value=datum.value,
            literal_kind="int",
            span=datum.span,
            form_path=form_path,
        )
    if isinstance(datum, BoolAtom):
        return LiteralExpr(
            value=datum.value,
            literal_kind="bool",
            span=datum.span,
            form_path=form_path,
        )
    if isinstance(datum, SymbolAtom):
        return _elaborate_symbol(datum, form_path=form_path, bound_names=bound_names)
    if isinstance(datum, ListExpr):
        return _elaborate_list(datum, form_path=form_path, bound_names=bound_names)
    raise TypeError(f"unsupported expression datum: {type(datum)!r}")


def _elaborate_symbol(
    datum: SymbolAtom,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ExprNode:
    if datum.value in bound_names:
        return NameExpr(name=datum.value, span=datum.span, form_path=form_path)
    segments = datum.value.split(".")
    if len(segments) > 1 and segments[0] in bound_names:
        return FieldAccessExpr(
            base=NameExpr(name=segments[0], span=datum.span, form_path=form_path),
            fields=tuple(segments[1:]),
            span=datum.span,
            form_path=form_path,
        )
    return NameExpr(name=datum.value, span=datum.span, form_path=form_path)


def _elaborate_list(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ExprNode:
    if not datum.items:
        _raise_error("expression forms must be non-empty lists", span=datum.span, form_path=form_path)
    head = datum.items[0]
    if not isinstance(head, SymbolAtom):
        _raise_error("expression forms must start with a symbol", span=head.span, form_path=form_path)
    if head.value == "record":
        return _elaborate_record(datum, form_path=form_path, bound_names=bound_names)
    if head.value == "let*":
        return _elaborate_letstar(datum, form_path=form_path, bound_names=bound_names)
    if head.value == "match":
        return _elaborate_match(datum, form_path=form_path, bound_names=bound_names)
    _raise_error(
        f"unsupported expression form `{head.value}`",
        code="expression_form_unknown",
        span=head.span,
        form_path=form_path,
    )


def _elaborate_record(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> RecordExpr:
    if len(datum.items) < 2:
        _raise_error("`record` requires a type name", span=datum.span, form_path=form_path)
    type_node = datum.items[1]
    if not isinstance(type_node, SymbolAtom):
        _raise_error("`record` type name must be a symbol", span=type_node.span, form_path=form_path)
    raw_fields = datum.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_error("`record` requires keyword/value field pairs", span=datum.span, form_path=form_path)
    fields: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, KeywordAtom):
            _raise_error("`record` fields must start with keywords", span=keyword_node.span, form_path=form_path)
        fields.append(
            (
                keyword_node.value[1:],
                _elaborate(value_node, form_path=form_path, bound_names=bound_names),
            )
        )
    return RecordExpr(
        type_name=type_node.value,
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
    )


def _elaborate_letstar(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> LetStarExpr:
    if len(datum.items) != 3:
        _raise_error("`let*` requires a binding list and one body", span=datum.span, form_path=form_path)
    raw_bindings = datum.items[1]
    if not isinstance(raw_bindings, ListExpr):
        _raise_error("`let*` bindings must be a list", span=raw_bindings.span, form_path=form_path)
    current_names = set(bound_names)
    bindings: list[tuple[str, ExprNode]] = []
    for raw_binding in raw_bindings.items:
        if not isinstance(raw_binding, ListExpr) or len(raw_binding.items) != 2:
            _raise_error(
                "`let*` bindings must be two-item lists of `(name expr)`",
                span=raw_binding.span,
                form_path=form_path,
            )
        name_node = raw_binding.items[0]
        if not isinstance(name_node, SymbolAtom):
            _raise_error("`let*` binding names must be symbols", span=name_node.span, form_path=form_path)
        value_expr = _elaborate(
            raw_binding.items[1],
            form_path=form_path,
            bound_names=frozenset(current_names),
        )
        bindings.append((name_node.value, value_expr))
        current_names.add(name_node.value)
    body = _elaborate(datum.items[2], form_path=form_path, bound_names=frozenset(current_names))
    return LetStarExpr(bindings=tuple(bindings), body=body, span=datum.span, form_path=form_path)


def _elaborate_match(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> MatchExpr:
    if len(datum.items) < 2:
        _raise_error("`match` requires a subject", span=datum.span, form_path=form_path)
    subject = _elaborate(datum.items[1], form_path=form_path, bound_names=bound_names)
    arms: list[MatchArm] = []
    for raw_arm in datum.items[2:]:
        if not isinstance(raw_arm, ListExpr) or len(raw_arm.items) != 2:
            _raise_error(
                "`match` arms must be `((VARIANT binding) body)`",
                span=raw_arm.span,
                form_path=form_path,
            )
        pattern = raw_arm.items[0]
        if not isinstance(pattern, ListExpr) or len(pattern.items) != 2:
            _raise_error(
                "`match` arm patterns must be `(VARIANT binding)`",
                span=pattern.span,
                form_path=form_path,
            )
        variant_node = pattern.items[0]
        binding_node = pattern.items[1]
        if not isinstance(variant_node, SymbolAtom):
            _raise_error("`match` variant names must be symbols", span=variant_node.span, form_path=form_path)
        if not isinstance(binding_node, SymbolAtom):
            _raise_error("`match` binding names must be symbols", span=binding_node.span, form_path=form_path)
        body = _elaborate(
            raw_arm.items[1],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | {binding_node.value}),
        )
        arms.append(
            MatchArm(
                variant_name=variant_node.value,
                binding_name=binding_node.value,
                body=body,
                span=raw_arm.span,
                form_path=form_path,
            )
        )
    return MatchExpr(subject=subject, arms=tuple(arms), span=datum.span, form_path=form_path)


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
