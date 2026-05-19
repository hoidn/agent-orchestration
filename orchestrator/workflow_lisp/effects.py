"""Frontend-local effect atoms and summary helpers for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic

if TYPE_CHECKING:
    from .spans import SourceSpan
    from .syntax import ExpansionStack, SyntaxIdentifier, SyntaxList


def _normalize_subject(subject: str) -> tuple[str, ...]:
    return tuple(segment for segment in subject.split(".") if segment)


@dataclass(frozen=True)
class ReadEffect:
    subject: tuple[str, ...]


@dataclass(frozen=True)
class WriteEffect:
    subject: tuple[str, ...]


@dataclass(frozen=True)
class PublishEffect:
    subject: tuple[str, ...]


@dataclass(frozen=True)
class UsesProviderEffect:
    subject: tuple[str, ...]


@dataclass(frozen=True)
class UsesCommandEffect:
    subject: tuple[str, ...]


@dataclass(frozen=True)
class CallsWorkflowEffect:
    subject: tuple[str, ...]


@dataclass(frozen=True)
class UpdatesStateEffect:
    subject: tuple[str, ...]


EffectAtom = (
    ReadEffect
    | WriteEffect
    | PublishEffect
    | UsesProviderEffect
    | UsesCommandEffect
    | CallsWorkflowEffect
    | UpdatesStateEffect
)


@dataclass(frozen=True)
class ProcedureCallEdge:
    callee_name: str


@dataclass(frozen=True)
class EffectSummary:
    direct_effects: frozenset[EffectAtom]
    transitive_effects: frozenset[EffectAtom]
    procedure_edges: frozenset[ProcedureCallEdge]


def empty_effect_summary() -> EffectSummary:
    return EffectSummary(
        direct_effects=frozenset(),
        transitive_effects=frozenset(),
        procedure_edges=frozenset(),
    )


EMPTY_EFFECT_SUMMARY = empty_effect_summary()


def effect_summary(
    *,
    direct_effects: Iterable[EffectAtom] = (),
    transitive_effects: Iterable[EffectAtom] | None = None,
    procedure_edges: Iterable[ProcedureCallEdge] = (),
) -> EffectSummary:
    direct = frozenset(direct_effects)
    transitive = direct if transitive_effects is None else frozenset(transitive_effects)
    return EffectSummary(
        direct_effects=direct,
        transitive_effects=transitive,
        procedure_edges=frozenset(procedure_edges),
    )


def effect_summary_from_direct(
    *,
    direct_effects: Iterable[EffectAtom] = (),
    procedure_edges: Iterable[ProcedureCallEdge] = (),
) -> EffectSummary:
    return effect_summary(
        direct_effects=direct_effects,
        procedure_edges=procedure_edges,
    )


def merge_effect_summaries(*summaries: EffectSummary) -> EffectSummary:
    direct_effects: set[EffectAtom] = set()
    transitive_effects: set[EffectAtom] = set()
    procedure_edges: set[ProcedureCallEdge] = set()
    for summary in summaries:
        direct_effects.update(summary.direct_effects)
        transitive_effects.update(summary.transitive_effects)
        procedure_edges.update(summary.procedure_edges)
    return EffectSummary(
        direct_effects=frozenset(direct_effects),
        transitive_effects=frozenset(transitive_effects),
        procedure_edges=frozenset(procedure_edges),
    )


def with_transitive_effects(summary: EffectSummary, effects: Iterable[EffectAtom]) -> EffectSummary:
    transitive = set(summary.transitive_effects)
    transitive.update(effects)
    return EffectSummary(
        direct_effects=summary.direct_effects,
        transitive_effects=frozenset(transitive),
        procedure_edges=summary.procedure_edges,
    )


def parse_declared_effects(
    raw_effects: "SyntaxList",
    *,
    span: "SourceSpan",
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack" = (),
) -> frozenset[EffectAtom]:
    return parse_effect_clause(
        raw_effects,
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def parse_effect_clause(
    raw_effects: "SyntaxList",
    *,
    span: "SourceSpan",
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack" = (),
) -> frozenset[EffectAtom]:
    from .syntax import SyntaxIdentifier, SyntaxList

    effects: set[EffectAtom] = set()
    for raw_group in raw_effects.items:
        if not isinstance(raw_group, SyntaxList) or not raw_group.items:
            _raise_invalid_effect(
                "effect groups must be non-empty lists",
                span=getattr(raw_group, "span", span),
                form_path=form_path,
                expansion_stack=getattr(raw_group, "expansion_stack", expansion_stack),
            )
        head = raw_group.items[0]
        if not isinstance(head, SyntaxIdentifier):
            _raise_invalid_effect(
                "effect group heads must be symbols",
                span=head.span,
                form_path=form_path,
                expansion_stack=head.expansion_stack,
            )
        operands = raw_group.items[1:]
        parsed = _parse_effect_group(
            head.resolved_name,
            operands=operands,
            span=raw_group.span,
            form_path=form_path,
            expansion_stack=raw_group.expansion_stack,
        )
        effects.update(parsed)
    return frozenset(effects)


def render_effect_atom(effect: EffectAtom) -> str:
    if isinstance(effect, ReadEffect):
        label = "reads"
    elif isinstance(effect, WriteEffect):
        label = "writes"
    elif isinstance(effect, PublishEffect):
        label = "publishes"
    elif isinstance(effect, UsesProviderEffect):
        label = "uses-provider"
    elif isinstance(effect, UsesCommandEffect):
        label = "uses-command"
    elif isinstance(effect, CallsWorkflowEffect):
        label = "calls-workflow"
    elif isinstance(effect, UpdatesStateEffect):
        label = "updates-state"
    else:
        raise TypeError(f"unsupported effect type: {type(effect)!r}")
    return f"{label}({'.'.join(effect.subject)})"


def render_effect_set(effects: Iterable[EffectAtom]) -> str:
    ordered = sorted(render_effect_atom(effect) for effect in effects)
    if not ordered:
        return "()"
    return "(" + ", ".join(ordered) + ")"


def _parse_effect_group(
    kind: str,
    *,
    operands: tuple[object, ...],
    span: "SourceSpan",
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack",
) -> tuple[EffectAtom, ...]:
    names = tuple(_effect_operand_name(operand, form_path=form_path, expansion_stack=expansion_stack) for operand in operands)
    constructors = {
        "reads": lambda value: ReadEffect(subject=_normalize_subject(value)),
        "writes": lambda value: WriteEffect(subject=_normalize_subject(value)),
        "publishes": lambda value: PublishEffect(subject=_normalize_subject(value)),
        "uses-provider": lambda value: UsesProviderEffect(subject=_normalize_subject(value)),
        "uses-command": lambda value: UsesCommandEffect(subject=_normalize_subject(value)),
        "calls-workflow": lambda value: CallsWorkflowEffect(subject=_normalize_subject(value)),
        "updates-state": lambda value: UpdatesStateEffect(subject=_normalize_subject(value)),
    }
    constructor = constructors.get(kind)
    if constructor is None:
        _raise_invalid_effect(
            f"unsupported procedure effect kind `{kind}`",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    return tuple(constructor(name) for name in names)


def _effect_operand_name(
    operand: object,
    *,
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack",
) -> str:
    from .syntax import SyntaxIdentifier

    if not isinstance(operand, SyntaxIdentifier):
        _raise_invalid_effect(
            "effect operands must be symbols",
            span=getattr(operand, "span"),
            form_path=form_path,
            expansion_stack=getattr(operand, "expansion_stack", expansion_stack),
        )
    return operand.resolved_name


def _raise_invalid_effect(
    message: str,
    *,
    span: "SourceSpan",
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack",
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_effect_invalid",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
