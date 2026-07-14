"""Effect atoms and summary helpers for Workflow Lisp.

See `../../docs/design/workflow_lisp_effect_graph.md` for the intended effect graph
model and `../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the
current implemented scope.
"""

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
    """Declared or inferred read of a workflow value, path, or artifact."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class WriteEffect:
    """Declared or inferred write to a path, contract, or generated output."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class PublishEffect:
    """Declared publication of an artifact name."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class UsesProviderEffect:
    """Declared provider invocation dependency."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class UsesCommandEffect:
    """Declared command or adapter invocation dependency."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class CallsWorkflowEffect:
    """Declared call into another workflow boundary."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class UpdatesStateEffect:
    """Declared mutation of workflow-owned state."""

    subject: tuple[str, ...]


@dataclass(frozen=True)
class MovesResourceEffect:
    """Internal promoted resource movement derived from validated workflow forms."""

    subject: tuple[str, ...]
    from_queue: tuple[str, ...]
    to_queue: tuple[str, ...]


@dataclass(frozen=True)
class UpdatesLedgerEffect:
    """Internal promoted ledger write derived from validated workflow forms."""

    subject: tuple[str, ...]
    event_name: tuple[str, ...]


@dataclass(frozen=True)
class CapturesSnapshotEffect:
    """Internal promoted snapshot capture derived during lowering."""

    subject: tuple[str, ...]
    snapshot_kind: tuple[str, ...]
    candidate_names: tuple[str, ...]


@dataclass(frozen=True)
class MaterializesPointerEffect:
    """Internal promoted pointer materialization derived during lowering."""

    subject: tuple[str, ...]
    pointer_path: tuple[str, ...]
    representation_role: tuple[str, ...]


EffectAtom = (
    ReadEffect
    | WriteEffect
    | PublishEffect
    | UsesProviderEffect
    | UsesCommandEffect
    | CallsWorkflowEffect
    | UpdatesStateEffect
    | MovesResourceEffect
    | UpdatesLedgerEffect
    | CapturesSnapshotEffect
    | MaterializesPointerEffect
)


@dataclass(frozen=True)
class ProcedureCallEdge:
    """Procedure call edge used to compute transitive effects."""

    callee_name: str
    span: SourceSpan | None = None
    form_path: tuple[str, ...] = ()
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class EffectSummary:
    """Direct effects, transitive effects, and procedure edges for a form."""

    direct_effects: frozenset[EffectAtom]
    transitive_effects: frozenset[EffectAtom]
    procedure_edges: frozenset[ProcedureCallEdge]


def empty_effect_summary() -> EffectSummary:
    """Return the identity summary for effect aggregation."""

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
    """Build an effect summary from explicit direct and transitive sets."""

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
    """Build a summary whose transitive effects initially equal direct effects."""

    return effect_summary(
        direct_effects=direct_effects,
        procedure_edges=procedure_edges,
    )


def effect_summary_from_procedure_call(
    *,
    callee_effects: Iterable[EffectAtom],
    edge: ProcedureCallEdge,
) -> EffectSummary:
    """Build a call summary whose callee effects are transitive-only."""

    return effect_summary(
        direct_effects=(),
        transitive_effects=callee_effects,
        procedure_edges=(edge,),
    )


def merge_effect_summaries(*summaries: EffectSummary) -> EffectSummary:
    """Union multiple effect summaries for sequential or nested forms."""

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
    """Return a summary with additional transitive effects attached."""

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
    """Parse a `:effects` syntax list into Workflow Lisp effect atoms."""

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
    """Parse one effect clause and validate supported effect group heads."""

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
    """Render one effect atom for diagnostics."""

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
    elif isinstance(effect, MovesResourceEffect):
        return (
            "moves-resource("
            f"{'.'.join(effect.subject)}, "
            f"from={'.'.join(effect.from_queue)}, "
            f"to={'.'.join(effect.to_queue)})"
        )
    elif isinstance(effect, UpdatesLedgerEffect):
        return f"updates-ledger({'.'.join(effect.subject)}, event={'.'.join(effect.event_name)})"
    elif isinstance(effect, CapturesSnapshotEffect):
        candidates = "|".join(effect.candidate_names)
        return (
            "captures-snapshot("
            f"{'.'.join(effect.subject)}, "
            f"kind={'.'.join(effect.snapshot_kind)}, "
            f"candidates={candidates})"
        )
    elif isinstance(effect, MaterializesPointerEffect):
        return (
            "materializes-pointer("
            f"{'.'.join(effect.subject)}, "
            f"path={'.'.join(effect.pointer_path)}, "
            f"role={'.'.join(effect.representation_role)})"
        )
    else:
        raise TypeError(f"unsupported effect type: {type(effect)!r}")
    return f"{label}({'.'.join(effect.subject)})"


def render_effect_set(effects: Iterable[EffectAtom]) -> str:
    """Render a stable effect-set label for diagnostics."""

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
