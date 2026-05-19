"""Bounded Stage 2 expression AST and elaboration helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    SyntaxBool,
    SyntaxIdentifier,
    SyntaxInt,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
)


@dataclass(frozen=True)
class NameExpr:
    """One lexical name reference."""

    name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LiteralExpr:
    """One primitive literal."""

    value: str | int | bool
    literal_kind: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class FieldAccessExpr:
    """One dotted field-access chain rooted at a lexical name."""

    base: NameExpr
    fields: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class RecordExpr:
    """One record-construction form."""

    type_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetStarExpr:
    """One sequential lexical binding form."""

    bindings: tuple[tuple[str, "ExprNode"], ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MatchArm:
    """One `match` variant arm."""

    variant_name: str
    binding_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MatchExpr:
    """One exhaustive variant match form."""

    subject: "ExprNode"
    arms: tuple[MatchArm, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CallExpr:
    """One same-file workflow call."""

    callee_name: str
    bindings: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureCallExpr:
    """One same-file procedure call."""

    callee_name: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WithPhaseExpr:
    """One compile-time phase-scope wrapper."""

    ctx_expr: "ExprNode"
    phase_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PhaseTargetExpr:
    """One named phase-target reference."""

    target_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProviderResultExpr:
    """One provider result with a typed structured return contract."""

    provider: "ExprNode"
    prompt: "ExprNode"
    inputs: tuple["ExprNode", ...]
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CommandResultExpr:
    """One command result with a typed structured return contract."""

    step_name: str
    argv: tuple["ExprNode", ...]
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


ExprNode = (
    NameExpr
    | LiteralExpr
    | FieldAccessExpr
    | RecordExpr
    | LetStarExpr
    | MatchExpr
    | CallExpr
    | ProcedureCallExpr
    | WithPhaseExpr
    | PhaseTargetExpr
    | ProviderResultExpr
    | CommandResultExpr
)


def elaborate_expression(
    node: SyntaxNode,
    *,
    bound_names: frozenset[str],
    procedure_names: frozenset[str] = frozenset(),
) -> ExprNode:
    """Elaborate one syntax node into the bounded Stage 2 expression AST."""

    return _elaborate(
        syntax_node_datum(node),
        form_path=node.form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )


def _elaborate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if isinstance(datum, SyntaxString):
        return LiteralExpr(
            value=datum.value,
            literal_kind="string",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxInt):
        return LiteralExpr(
            value=datum.value,
            literal_kind="int",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxBool):
        return LiteralExpr(
            value=datum.value,
            literal_kind="bool",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxIdentifier):
        return _elaborate_symbol(datum, form_path=form_path, bound_names=bound_names)
    if isinstance(datum, SyntaxList):
        return _elaborate_list(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    raise TypeError(f"unsupported expression datum: {type(datum)!r}")


def _elaborate_symbol(
    datum: SyntaxIdentifier,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ExprNode:
    if datum.resolved_name in bound_names:
        return NameExpr(
            name=datum.resolved_name,
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    segments = datum.resolved_name.split(".")
    if len(segments) > 1 and segments[0] in bound_names:
        return FieldAccessExpr(
            base=NameExpr(
                name=segments[0],
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            ),
            fields=tuple(segments[1:]),
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return NameExpr(
        name=datum.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_list(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if not datum.items:
        _raise_error(
            "expression forms must be non-empty lists",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    head = syntax_head(datum)
    if head is None:
        _raise_error(
            "expression forms must start with a symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if head.resolved_name == "record":
        return _elaborate_record(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "let*":
        return _elaborate_letstar(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "match":
        return _elaborate_match(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "call":
        return _elaborate_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "with-phase":
        return _elaborate_with_phase(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "phase-target":
        return _elaborate_phase_target(datum, form_path=form_path)
    if head.resolved_name == "provider-result":
        return _elaborate_provider_result(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "command-result":
        return _elaborate_command_result(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name in procedure_names:
        return _elaborate_procedure_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    _raise_error(
        f"unknown same-file procedure callee `{head.display_name}`",
        code="procedure_call_unknown",
        span=head.span,
        form_path=form_path,
        expansion_stack=head.expansion_stack,
    )


def _elaborate_record(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> RecordExpr:
    if len(datum.items) < 2:
        _raise_error("`record` requires a type name", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    type_node = datum.items[1]
    type_identifier = syntax_identifier(type_node)
    if type_identifier is None:
        _raise_error(
            "`record` type name must be a symbol",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    raw_fields = datum.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`record` requires keyword/value field pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    fields: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`record` fields must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        fields.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return RecordExpr(
        type_name=type_identifier.resolved_name,
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_letstar(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LetStarExpr:
    if len(datum.items) != 3:
        _raise_error(
            "`let*` requires a binding list and one body",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_bindings = datum.items[1]
    if not isinstance(raw_bindings, SyntaxList):
        _raise_error(
            "`let*` bindings must be a list",
            span=raw_bindings.span,
            form_path=form_path,
            expansion_stack=raw_bindings.expansion_stack,
        )
    current_names = set(bound_names)
    bindings: list[tuple[str, ExprNode]] = []
    for raw_binding in raw_bindings.items:
        if not isinstance(raw_binding, SyntaxList) or len(raw_binding.items) != 2:
            _raise_error(
                "`let*` bindings must be two-item lists of `(name expr)`",
                span=raw_binding.span,
                form_path=form_path,
                expansion_stack=raw_binding.expansion_stack,
            )
        name_node = syntax_identifier(raw_binding.items[0])
        if name_node is None:
            _raise_error(
                "`let*` binding names must be symbols",
                span=raw_binding.items[0].span,
                form_path=form_path,
                expansion_stack=raw_binding.items[0].expansion_stack,
            )
        value_expr = _elaborate(
            raw_binding.items[1],
            form_path=form_path,
            bound_names=frozenset(current_names),
            procedure_names=procedure_names,
        )
        bindings.append((name_node.resolved_name, value_expr))
        current_names.add(name_node.resolved_name)
    body = _elaborate(
        datum.items[2],
        form_path=form_path,
        bound_names=frozenset(current_names),
        procedure_names=procedure_names,
    )
    return LetStarExpr(
        bindings=tuple(bindings),
        body=body,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_match(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> MatchExpr:
    if len(datum.items) < 2:
        _raise_error("`match` requires a subject", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    subject = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    arms: list[MatchArm] = []
    for raw_arm in datum.items[2:]:
        if not isinstance(raw_arm, SyntaxList) or len(raw_arm.items) != 2:
            _raise_error(
                "`match` arms must be `((VARIANT binding) body)`",
                span=raw_arm.span,
                form_path=form_path,
                expansion_stack=raw_arm.expansion_stack,
            )
        pattern = raw_arm.items[0]
        if not isinstance(pattern, SyntaxList) or len(pattern.items) != 2:
            _raise_error(
                "`match` arm patterns must be `(VARIANT binding)`",
                span=pattern.span,
                form_path=form_path,
                expansion_stack=pattern.expansion_stack,
            )
        variant_node = syntax_identifier(pattern.items[0])
        binding_node = syntax_identifier(pattern.items[1])
        if variant_node is None:
            _raise_error(
                "`match` variant names must be symbols",
                span=pattern.items[0].span,
                form_path=form_path,
                expansion_stack=pattern.items[0].expansion_stack,
            )
        if binding_node is None:
            _raise_error(
                "`match` binding names must be symbols",
                span=pattern.items[1].span,
                form_path=form_path,
                expansion_stack=pattern.items[1].expansion_stack,
            )
        body = _elaborate(
            raw_arm.items[1],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | {binding_node.resolved_name}),
            procedure_names=procedure_names,
        )
        arms.append(
            MatchArm(
                variant_name=variant_node.resolved_name,
                binding_name=binding_node.resolved_name,
                body=body,
                span=raw_arm.span,
                form_path=form_path,
                expansion_stack=raw_arm.expansion_stack,
            )
        )
    return MatchExpr(
        subject=subject,
        arms=tuple(arms),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> CallExpr:
    if len(datum.items) < 2:
        _raise_error("`call` requires a callee name", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    callee_node = datum.items[1]
    callee_identifier = syntax_identifier(callee_node)
    if callee_identifier is None:
        _raise_error(
            "`call` callee name must be a symbol",
            span=callee_node.span,
            form_path=form_path,
            expansion_stack=callee_node.expansion_stack,
        )
    raw_bindings = datum.items[2:]
    if len(raw_bindings) % 2 != 0:
        _raise_error(
            "`call` requires keyword/value binding pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    bindings: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_bindings), 2):
        keyword_node = raw_bindings[index]
        value_node = raw_bindings[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`call` bindings must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        bindings.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return CallExpr(
        callee_name=callee_identifier.resolved_name,
        bindings=tuple(bindings),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_procedure_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProcedureCallExpr:
    callee_identifier = syntax_identifier(datum.items[0])
    assert callee_identifier is not None
    return ProcedureCallExpr(
        callee_name=callee_identifier.resolved_name,
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_with_phase(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> WithPhaseExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`with-phase` requires a context, phase name, and one body",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    phase_name_node = datum.items[2]
    phase_identifier = syntax_identifier(phase_name_node)
    if phase_identifier is None:
        _raise_error(
            "`with-phase` phase name must be a symbol",
            span=phase_name_node.span,
            form_path=form_path,
            expansion_stack=phase_name_node.expansion_stack,
        )
    return WithPhaseExpr(
        ctx_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        phase_name=phase_identifier.resolved_name,
        body=_elaborate(
            datum.items[3],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_phase_target(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> PhaseTargetExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`phase-target` requires exactly one target symbol",
            code="phase_target_name_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_node = datum.items[1]
    target_identifier = syntax_identifier(target_node)
    if target_identifier is None:
        _raise_error(
            "`phase-target` target name must be a symbol",
            code="phase_target_name_invalid",
            span=target_node.span,
            form_path=form_path,
            expansion_stack=target_node.expansion_stack,
        )
    return PhaseTargetExpr(
        target_name=target_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_provider_result(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProviderResultExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`provider-result` requires provider, :prompt, :inputs, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    provider = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`provider-result`")
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    returns_node = sections.get(":returns")
    if prompt_node is None or inputs_node is None or returns_node is None:
        _raise_error(
            "`provider-result` requires :prompt, :inputs, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`provider-result :inputs` must be a list",
            span=inputs_node.span,
            form_path=form_path,
            expansion_stack=inputs_node.expansion_stack,
        )
    returns_identifier = syntax_identifier(returns_node)
    if returns_identifier is None:
        _raise_error(
            "`provider-result :returns` must be a symbol",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    return ProviderResultExpr(
        provider=provider,
        prompt=_elaborate(
            prompt_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        inputs=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in inputs_node.items
        ),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_command_result(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> CommandResultExpr:
    if len(datum.items) < 5:
        _raise_error(
            "`command-result` requires a step name plus :argv and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    step_name_node = datum.items[1]
    step_identifier = syntax_identifier(step_name_node)
    if step_identifier is None:
        _raise_error(
            "`command-result` step name must be a symbol",
            span=step_name_node.span,
            form_path=form_path,
            expansion_stack=step_name_node.expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`command-result`")
    argv_node = sections.get(":argv")
    returns_node = sections.get(":returns")
    if argv_node is None or returns_node is None:
        _raise_error(
            "`command-result` requires :argv and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if not isinstance(argv_node, SyntaxList):
        _raise_error(
            "`command-result :argv` must be a list",
            span=argv_node.span,
            form_path=form_path,
            expansion_stack=argv_node.expansion_stack,
        )
    returns_identifier = syntax_identifier(returns_node)
    if returns_identifier is None:
        _raise_error(
            "`command-result :returns` must be a symbol",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    return CommandResultExpr(
        step_name=step_identifier.resolved_name,
        argv=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in argv_node.items
        ),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _keyword_sections(
    items: list[object],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    if len(items) % 2 != 0:
        _raise_error(
            f"{label} requires keyword/value pairs",
            span=items[-1].span,
            form_path=form_path,
            expansion_stack=items[-1].expansion_stack,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                f"{label} entries must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        if keyword_node.value in sections:
            _raise_error(
                f"{label} duplicated keyword `{keyword_node.value}`",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        sections[keyword_node.value] = value_node
    return sections


def _raise_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    code: str = "frontend_parse_error",
    expansion_stack: ExpansionStack = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
