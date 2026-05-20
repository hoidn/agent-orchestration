"""Elaborate supported Workflow Lisp expression forms into typed AST nodes.

See `../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the current
expression scope and `../../docs/design/workflow_lisp_frontend_specification.md` for
the full intended language surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from .drain_stdlib import BacklogDrainSpec
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .phase_stdlib import (
    ProduceOneOfCandidateFieldSpec,
    ProduceOneOfCandidateSpec,
    ProduceOneOfProducerSpec,
)
from .resource_stdlib import FinalizeSelectedItemSpec, ResourceTransitionSpec
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


@dataclass(frozen=True)
class RunProviderPhaseExpr:
    """One high-level typed phase provider execution form."""

    phase_name: str
    ctx_expr: "ExprNode"
    inputs_expr: "ExprNode"
    provider: "ExprNode"
    prompt: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProduceOneOfExpr:
    """One high-level produced-outcome selection form."""

    returns_type_name: str
    ctx_expr: "ExprNode"
    producer: ProduceOneOfProducerSpec
    candidates: tuple[ProduceOneOfCandidateSpec, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ReviewReviseLoopExpr:
    """One supported review/revise loop form."""

    loop_name: str
    ctx_expr: "ExprNode"
    completed_expr: "ExprNode"
    inputs_expr: "ExprNode"
    review_provider: "ExprNode"
    fix_provider: "ExprNode"
    review_prompt: "ExprNode"
    fix_prompt: "ExprNode"
    max_expr: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ResumeOrStartExpr:
    """One typed reusable-state gate around resume or fresh start."""

    resume_name: str
    ctx_expr: "ExprNode"
    resume_from_expr: "ExprNode"
    valid_when: tuple[str, ...]
    start_expr: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    validation_spec: object | None = None


@dataclass(frozen=True)
class ResourceTransitionExpr:
    """One supported resource movement form."""

    spec: ResourceTransitionSpec
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class FinalizeSelectedItemExpr:
    """One selected-item final result routing form."""

    spec: FinalizeSelectedItemSpec
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class BacklogDrainExpr:
    """One supported compile-time drain loop form."""

    spec: BacklogDrainSpec
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
    | RunProviderPhaseExpr
    | ProduceOneOfExpr
    | ReviewReviseLoopExpr
    | ResumeOrStartExpr
    | ResourceTransitionExpr
    | FinalizeSelectedItemExpr
    | BacklogDrainExpr
)


_ACTIVE_PROCEDURE_NAME_RESOLVER = None
_ACTIVE_WORKFLOW_NAME_RESOLVER = None


def elaborate_expression(
    node: SyntaxNode,
    *,
    bound_names: frozenset[str],
    procedure_names: frozenset[str] = frozenset(),
    procedure_name_resolver=None,
    workflow_name_resolver=None,
) -> ExprNode:
    """Elaborate one syntax node into a supported Workflow Lisp expression."""

    global _ACTIVE_PROCEDURE_NAME_RESOLVER, _ACTIVE_WORKFLOW_NAME_RESOLVER

    previous_procedure_resolver = _ACTIVE_PROCEDURE_NAME_RESOLVER
    previous_workflow_resolver = _ACTIVE_WORKFLOW_NAME_RESOLVER
    _ACTIVE_PROCEDURE_NAME_RESOLVER = procedure_name_resolver
    _ACTIVE_WORKFLOW_NAME_RESOLVER = workflow_name_resolver
    try:
        return _elaborate(
            syntax_node_datum(node),
            form_path=node.form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    finally:
        _ACTIVE_PROCEDURE_NAME_RESOLVER = previous_procedure_resolver
        _ACTIVE_WORKFLOW_NAME_RESOLVER = previous_workflow_resolver


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
    if head.resolved_name == "run-provider-phase":
        return _elaborate_run_provider_phase(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "produce-one-of":
        return _elaborate_produce_one_of(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "review-revise-loop":
        return _elaborate_review_revise_loop(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "resume-or-start":
        return _elaborate_resume_or_start(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "resource-transition":
        return _elaborate_resource_transition(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "finalize-selected-item":
        return _elaborate_finalize_selected_item(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name == "backlog-drain":
        return _elaborate_backlog_drain(
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
        callee_name=(
            _ACTIVE_WORKFLOW_NAME_RESOLVER(
                callee_identifier.resolved_name,
                callee_identifier.span,
                form_path,
            )
            if _ACTIVE_WORKFLOW_NAME_RESOLVER is not None
            else callee_identifier.resolved_name
        ),
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
        callee_name=(
            _ACTIVE_PROCEDURE_NAME_RESOLVER(
                callee_identifier.resolved_name,
                callee_identifier.span,
                form_path,
            )
            if _ACTIVE_PROCEDURE_NAME_RESOLVER is not None
            else callee_identifier.resolved_name
        ),
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


def _elaborate_run_provider_phase(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> RunProviderPhaseExpr:
    if len(datum.items) < 7:
        _raise_error(
            "`run-provider-phase` requires a phase name plus :ctx, :inputs, :provider, :prompt, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    phase_identifier = syntax_identifier(datum.items[1])
    if phase_identifier is None:
        _raise_error(
            "`run-provider-phase` phase name must be a symbol",
            code="run_provider_phase_return_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`run-provider-phase`")
    ctx_node = sections.get(":ctx")
    inputs_node = sections.get(":inputs")
    provider_node = sections.get(":provider")
    prompt_node = sections.get(":prompt")
    returns_node = sections.get(":returns")
    if any(node is None for node in (ctx_node, inputs_node, provider_node, prompt_node, returns_node)):
        _raise_error(
            "`run-provider-phase` requires :ctx, :inputs, :provider, :prompt, and :returns",
            code="run_provider_phase_return_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(returns_node)
    if returns_identifier is None:
        _raise_error(
            "`run-provider-phase :returns` must be a symbol",
            code="run_provider_phase_return_invalid",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    return RunProviderPhaseExpr(
        phase_name=phase_identifier.resolved_name,
        ctx_expr=_elaborate(ctx_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        inputs_expr=_elaborate(inputs_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        provider=_elaborate(provider_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        prompt=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_produce_one_of(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`produce-one-of` requires a return type plus :ctx, :producer, and :candidates",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(datum.items[1])
    if returns_identifier is None:
        _raise_error(
            "`produce-one-of` return type must be a symbol",
            code="produce_one_of_candidate_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of`")
    ctx_node = sections.get(":ctx")
    producer_node = sections.get(":producer")
    candidates_node = sections.get(":candidates")
    if ctx_node is None or producer_node is None or candidates_node is None:
        _raise_error(
            "`produce-one-of` requires :ctx, :producer, and :candidates",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if not isinstance(producer_node, SyntaxList):
        _raise_error(
            "`produce-one-of :producer` must be a list",
            code="produce_one_of_candidate_invalid",
            span=producer_node.span,
            form_path=form_path,
            expansion_stack=producer_node.expansion_stack,
        )
    producer = _elaborate_produce_one_of_producer(
        producer_node,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    if not isinstance(candidates_node, SyntaxList):
        _raise_error(
            "`produce-one-of :candidates` must be a list",
            code="produce_one_of_candidate_invalid",
            span=candidates_node.span,
            form_path=form_path,
            expansion_stack=candidates_node.expansion_stack,
        )
    return ProduceOneOfExpr(
        returns_type_name=returns_identifier.resolved_name,
        ctx_expr=_elaborate(ctx_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        producer=producer,
        candidates=tuple(
            _elaborate_produce_one_of_candidate(
                candidate_node,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for candidate_node in candidates_node.items
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_review_revise_loop(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ReviewReviseLoopExpr:
    if len(datum.items) < 9:
        _raise_error(
            "`review-revise-loop` requires a loop name plus :ctx, :completed, :inputs, provider, prompt, :max, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    loop_identifier = syntax_identifier(datum.items[1])
    if loop_identifier is None:
        _raise_error(
            "`review-revise-loop` loop name must be a symbol",
            code="review_loop_result_contract_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`review-revise-loop`")
    required = (
        ":ctx",
        ":completed",
        ":inputs",
        ":review-provider",
        ":fix-provider",
        ":review-prompt",
        ":fix-prompt",
        ":max",
        ":returns",
    )
    missing = [keyword for keyword in required if sections.get(keyword) is None]
    if missing:
        _raise_error(
            "`review-revise-loop` requires :ctx, :completed, :inputs, :review-provider, :fix-provider, :review-prompt, :fix-prompt, :max, and :returns",
            code="review_loop_result_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(sections[":returns"])
    if returns_identifier is None:
        _raise_error(
            "`review-revise-loop :returns` must be a symbol",
            code="review_loop_result_contract_invalid",
            span=sections[":returns"].span,
            form_path=form_path,
            expansion_stack=sections[":returns"].expansion_stack,
        )
    return ReviewReviseLoopExpr(
        loop_name=loop_identifier.resolved_name,
        ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        completed_expr=_elaborate(sections[":completed"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        inputs_expr=_elaborate(sections[":inputs"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        review_provider=_elaborate(sections[":review-provider"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        fix_provider=_elaborate(sections[":fix-provider"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        review_prompt=_elaborate(sections[":review-prompt"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        fix_prompt=_elaborate(sections[":fix-prompt"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        max_expr=_elaborate(sections[":max"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_resume_or_start(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ResumeOrStartExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`resume-or-start` requires a name plus :ctx, :resume-from, :start, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    resume_identifier = syntax_identifier(datum.items[1])
    if resume_identifier is None:
        _raise_error(
            "`resume-or-start` name must be a symbol",
            code="resume_or_start_contract_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`resume-or-start`")
    required = (":ctx", ":resume-from", ":start", ":returns")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`resume-or-start` requires :ctx, :resume-from, :start, and :returns",
            code="resume_or_start_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    valid_when_node = sections.get(":valid-when")
    valid_variants: tuple[str, ...] = ()
    if valid_when_node is not None:
        if not isinstance(valid_when_node, SyntaxList):
            _raise_error(
                "`resume-or-start :valid-when` must be a list of variants",
                code="resume_or_start_contract_invalid",
                span=valid_when_node.span,
                form_path=form_path,
                expansion_stack=valid_when_node.expansion_stack,
            )
        variants: list[str] = []
        for item in valid_when_node.items:
            variant_identifier = syntax_identifier(item)
            if variant_identifier is None:
                _raise_error(
                    "`resume-or-start :valid-when` entries must be symbols",
                    code="resume_or_start_contract_invalid",
                    span=item.span,
                    form_path=form_path,
                    expansion_stack=item.expansion_stack,
                )
            variants.append(variant_identifier.resolved_name)
        valid_variants = tuple(variants)
    returns_identifier = syntax_identifier(sections[":returns"])
    if returns_identifier is None:
        _raise_error(
            "`resume-or-start :returns` must be a symbol",
            code="resume_or_start_contract_invalid",
            span=sections[":returns"].span,
            form_path=form_path,
            expansion_stack=sections[":returns"].expansion_stack,
    )
    return ResumeOrStartExpr(
        resume_name=resume_identifier.resolved_name,
        ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        resume_from_expr=_elaborate(sections[":resume-from"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        valid_when=valid_variants,
        start_expr=_elaborate(sections[":start"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_resource_transition(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ResourceTransitionExpr:
    if len(datum.items) < 8:
        _raise_error(
            "`resource-transition` requires a transition name plus :ctx, :resource, :from, :to, :ledger, and :event",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    transition_identifier = syntax_identifier(datum.items[1])
    if transition_identifier is None:
        _raise_error(
            "`resource-transition` transition name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`resource-transition`")
    required = (":ctx", ":resource", ":from", ":to", ":ledger", ":event")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`resource-transition` requires :ctx, :resource, :from, :to, :ledger, and :event",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    from_identifier = syntax_identifier(sections[":from"])
    to_identifier = syntax_identifier(sections[":to"])
    event_identifier = syntax_identifier(sections[":event"])
    if from_identifier is None or to_identifier is None or event_identifier is None:
        _raise_error(
            "`resource-transition` queue and event operands must be symbols",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ResourceTransitionExpr(
        spec=ResourceTransitionSpec(
            transition_name=transition_identifier.resolved_name,
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            when_expr=(
                _elaborate(sections[":when"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names)
                if sections.get(":when") is not None
                else None
            ),
            resource_expr=_elaborate(
                sections[":resource"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
            from_queue_name=from_identifier.resolved_name,
            to_queue_name=to_identifier.resolved_name,
            ledger_expr=_elaborate(sections[":ledger"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            event_name=event_identifier.resolved_name,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_finalize_selected_item(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> FinalizeSelectedItemExpr:
    sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`finalize-selected-item`")
    required = (":ctx", ":selected", ":queue-transition", ":roadmap", ":plan", ":implementation")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`finalize-selected-item` requires :ctx, :selected, :queue-transition, :roadmap, :plan, and :implementation",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return FinalizeSelectedItemExpr(
        spec=FinalizeSelectedItemSpec(
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            selected_expr=_elaborate(
                sections[":selected"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
            queue_transition_expr=_elaborate(
                sections[":queue-transition"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
            roadmap_expr=_elaborate(sections[":roadmap"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            plan_expr=_elaborate(sections[":plan"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            implementation_expr=_elaborate(
                sections[":implementation"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_backlog_drain(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> BacklogDrainExpr:
    if len(datum.items) < 7:
        _raise_error(
            "`backlog-drain` requires a drain name plus :ctx, :selector, :run-item, :gap-drafter, and :max-iterations",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    drain_identifier = syntax_identifier(datum.items[1])
    if drain_identifier is None:
        _raise_error(
            "`backlog-drain` drain name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`backlog-drain`")
    required = (":ctx", ":selector", ":run-item", ":gap-drafter", ":max-iterations")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`backlog-drain` requires :ctx, :selector, :run-item, :gap-drafter, and :max-iterations",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    selector_identifier = syntax_identifier(sections[":selector"])
    run_item_identifier = syntax_identifier(sections[":run-item"])
    gap_drafter_identifier = syntax_identifier(sections[":gap-drafter"])
    if selector_identifier is None or run_item_identifier is None or gap_drafter_identifier is None:
        _raise_error(
            "`backlog-drain` workflow refs must be symbols",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return BacklogDrainExpr(
        spec=BacklogDrainSpec(
            drain_name=drain_identifier.resolved_name,
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            selector_name=selector_identifier.resolved_name,
            run_item_name=run_item_identifier.resolved_name,
            gap_drafter_name=gap_drafter_identifier.resolved_name,
            providers_expr=(
                _elaborate(sections[":providers"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names)
                if sections.get(":providers") is not None
                else None
            ),
            max_iterations_expr=_elaborate(
                sections[":max-iterations"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_produce_one_of_producer(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfProducerSpec:
    head = syntax_head(datum)
    if head is None or head.resolved_name != "provider" or len(datum.items) < 5:
        _raise_error(
            "`produce-one-of :producer` must be a `(provider ...)` form",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of :producer`")
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    if prompt_node is None or inputs_node is None or not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`produce-one-of :producer` requires :prompt and list-valued :inputs",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfProducerSpec(
        kind="provider",
        provider_expr=_elaborate(datum.items[1], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        prompt_expr=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        inputs=tuple(
            _elaborate(item, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names)
            for item in inputs_node.items
        ),
    )


def _elaborate_produce_one_of_candidate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfCandidateSpec:
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_error(
            "`produce-one-of` candidates must be non-empty lists",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    variant_identifier = syntax_identifier(datum.items[0])
    if variant_identifier is None:
        _raise_error(
            "`produce-one-of` candidate variants must be symbols",
            code="produce_one_of_candidate_invalid",
            span=datum.items[0].span,
            form_path=form_path,
            expansion_stack=datum.items[0].expansion_stack,
        )
    fields = tuple(
        _elaborate_produce_one_of_candidate_field(
            item,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
        for item in datum.items[1:]
    )
    if not fields:
        _raise_error(
            "`produce-one-of` candidates must describe at least one field",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfCandidateSpec(variant_name=variant_identifier.resolved_name, fields=fields)


def _elaborate_produce_one_of_candidate_field(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfCandidateFieldSpec:
    if not isinstance(datum, SyntaxList) or len(datum.items) < 3:
        _raise_error(
            "`produce-one-of` candidate fields must be structured lists",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    field_identifier = syntax_identifier(datum.items[0])
    if field_identifier is None:
        _raise_error(
            "`produce-one-of` candidate field names must be symbols",
            code="produce_one_of_candidate_invalid",
            span=datum.items[0].span,
            form_path=form_path,
            expansion_stack=datum.items[0].expansion_stack,
        )
    if len(datum.items) >= 4 and isinstance(datum.items[1], SyntaxIdentifier) and isinstance(datum.items[2], SyntaxKeyword):
        source_type_identifier = syntax_identifier(datum.items[1])
        sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of` candidate field")
        source_node = sections.get(":source")
        source_identifier = syntax_identifier(source_node) if source_node is not None else None
        if source_type_identifier is None or source_identifier is None:
            _raise_error(
                "`produce-one-of` candidate source fields require a type name and `:source` symbol",
                code="produce_one_of_candidate_invalid",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        return ProduceOneOfCandidateFieldSpec(
            field_name=field_identifier.resolved_name,
            source_type_name=source_type_identifier.resolved_name,
            source_kind=source_identifier.resolved_name,
        )
    sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`produce-one-of` candidate field")
    target_node = sections.get(":target")
    schema_node = sections.get(":schema")
    schema_identifier = syntax_identifier(schema_node) if schema_node is not None else None
    if target_node is None or schema_identifier is None:
        _raise_error(
            "`produce-one-of` candidate path fields require `:target` and `:schema`",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfCandidateFieldSpec(
        field_name=field_identifier.resolved_name,
        schema_type_name=schema_identifier.resolved_name,
        target_expr=_elaborate(target_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
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
