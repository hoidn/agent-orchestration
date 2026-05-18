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


@dataclass(frozen=True)
class CallExpr:
    """One same-file workflow call."""

    callee_name: str
    bindings: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class ProviderResultExpr:
    """One provider result with a typed structured return contract."""

    provider: "ExprNode"
    prompt: "ExprNode"
    inputs: tuple["ExprNode", ...]
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class CommandResultExpr:
    """One command result with a typed structured return contract."""

    step_name: str
    argv: tuple["ExprNode", ...]
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]


ExprNode = (
    NameExpr
    | LiteralExpr
    | FieldAccessExpr
    | RecordExpr
    | LetStarExpr
    | MatchExpr
    | CallExpr
    | ProviderResultExpr
    | CommandResultExpr
)


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
    if head.value == "call":
        return _elaborate_call(datum, form_path=form_path, bound_names=bound_names)
    if head.value == "provider-result":
        return _elaborate_provider_result(datum, form_path=form_path, bound_names=bound_names)
    if head.value == "command-result":
        return _elaborate_command_result(datum, form_path=form_path, bound_names=bound_names)
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


def _elaborate_call(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> CallExpr:
    if len(datum.items) < 2:
        _raise_error("`call` requires a callee name", span=datum.span, form_path=form_path)
    callee_node = datum.items[1]
    if not isinstance(callee_node, SymbolAtom):
        _raise_error("`call` callee name must be a symbol", span=callee_node.span, form_path=form_path)
    raw_bindings = datum.items[2:]
    if len(raw_bindings) % 2 != 0:
        _raise_error("`call` requires keyword/value binding pairs", span=datum.span, form_path=form_path)
    bindings: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_bindings), 2):
        keyword_node = raw_bindings[index]
        value_node = raw_bindings[index + 1]
        if not isinstance(keyword_node, KeywordAtom):
            _raise_error("`call` bindings must start with keywords", span=keyword_node.span, form_path=form_path)
        bindings.append(
            (
                keyword_node.value[1:],
                _elaborate(value_node, form_path=form_path, bound_names=bound_names),
            )
        )
    return CallExpr(
        callee_name=callee_node.value,
        bindings=tuple(bindings),
        span=datum.span,
        form_path=form_path,
    )


def _elaborate_provider_result(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ProviderResultExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`provider-result` requires provider, :prompt, :inputs, and :returns",
            span=datum.span,
            form_path=form_path,
        )
    provider = _elaborate(datum.items[1], form_path=form_path, bound_names=bound_names)
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`provider-result`")
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    returns_node = sections.get(":returns")
    if prompt_node is None or inputs_node is None or returns_node is None:
        _raise_error(
            "`provider-result` requires :prompt, :inputs, and :returns",
            span=datum.span,
            form_path=form_path,
        )
    if not isinstance(inputs_node, ListExpr):
        _raise_error("`provider-result :inputs` must be a list", span=inputs_node.span, form_path=form_path)
    if not isinstance(returns_node, SymbolAtom):
        _raise_error("`provider-result :returns` must be a symbol", span=returns_node.span, form_path=form_path)
    return ProviderResultExpr(
        provider=provider,
        prompt=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names),
        inputs=tuple(
            _elaborate(item, form_path=form_path, bound_names=bound_names) for item in inputs_node.items
        ),
        returns_type_name=returns_node.value,
        span=datum.span,
        form_path=form_path,
    )


def _elaborate_command_result(
    datum: ListExpr,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> CommandResultExpr:
    if len(datum.items) < 5:
        _raise_error(
            "`command-result` requires a step name plus :argv and :returns",
            span=datum.span,
            form_path=form_path,
        )
    step_name_node = datum.items[1]
    if not isinstance(step_name_node, SymbolAtom):
        _raise_error("`command-result` step name must be a symbol", span=step_name_node.span, form_path=form_path)
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`command-result`")
    argv_node = sections.get(":argv")
    returns_node = sections.get(":returns")
    if argv_node is None or returns_node is None:
        _raise_error("`command-result` requires :argv and :returns", span=datum.span, form_path=form_path)
    if not isinstance(argv_node, ListExpr):
        _raise_error("`command-result :argv` must be a list", span=argv_node.span, form_path=form_path)
    if not isinstance(returns_node, SymbolAtom):
        _raise_error("`command-result :returns` must be a symbol", span=returns_node.span, form_path=form_path)
    return CommandResultExpr(
        step_name=step_name_node.value,
        argv=tuple(
            _elaborate(item, form_path=form_path, bound_names=bound_names) for item in argv_node.items
        ),
        returns_type_name=returns_node.value,
        span=datum.span,
        form_path=form_path,
    )


def _keyword_sections(
    items: list[object],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    if len(items) % 2 != 0:
        _raise_error(f"{label} requires keyword/value pairs", span=items[-1].span, form_path=form_path)
    sections: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, KeywordAtom):
            _raise_error(f"{label} entries must start with keywords", span=keyword_node.span, form_path=form_path)
        if keyword_node.value in sections:
            _raise_error(f"{label} duplicated keyword `{keyword_node.value}`", span=keyword_node.span, form_path=form_path)
        sections[keyword_node.value] = value_node
    return sections


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
