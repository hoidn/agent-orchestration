"""Mechanical mutation operators over `.orc` source text, and a deterministic sample of mutants.

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md ("Operators"; Task T1).

A mutation is a set of character-range edits, found by reading the source with the package's
reader and spliced into the text at the nodes' spans: there is no printer, and comments and layout
survive. `text` is always decoded source with `\\n` line ends, and spans index its characters.
Nothing here compiles, runs or reads a file, and the module holds no state. It depends on
`orchestrator.workflow_lisp.reader.read_sexpr_text` and the node types of `sexpr` only.

The closed value sets live here and nowhere else (AGENTS.md, experiment rules: nothing above the
Sonnet ceiling, no Fable model). A caller may narrow them and can never widen them: there is no
override from the environment, a file or a command line. `tests/experiments/test_mutants.py`
repeats both tuples as literals.

Shared terms. A call form is a list headed `provider-result` or `agent`; its role is its first
operand when that is a symbol `providers.R` (role `R`). The operand of `:k` is the item after the
keyword `:k` among a form's own items. Forms are numbered from zero in order of start offset. No
operator yields a mutation whose replacement equals the text it replaces. No operator changes the
module name, imports, exports, the target, a type declaration, a prompt's `:fills` or return type,
or the entry workflow's parameter list, and none but `graft` adds a line.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, SExpr, SymbolAtom

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_CALL_HEADS = ("provider-result", "agent")
_ROLE_PREFIX = "providers."


@dataclass(frozen=True)
class Mutation:
    """One mutation of one source: `apply(text, mutation)` is the mutant.

    `operator` is a key of `OPERATORS`; `params` names the mutation among that operator's
    mutations of the source (`reviewer=low`, `loop1=3`, `9<-18`), so `program/operator/params`
    reproduces the mutant; `edits` are disjoint `(start, end, replacement)` character ranges of
    the source the mutation was made from.
    """

    operator: str
    params: str
    edits: tuple[tuple[int, int, str], ...]


def _head(node: SExpr) -> str | None:
    """The symbol that heads a list, or None."""
    if isinstance(node, ListExpr) and node.items and isinstance(node.items[0], SymbolAtom):
        return node.items[0].value
    return None


def _lists(node: SExpr) -> Iterator[ListExpr]:
    """Every list at or under `node`, in order of start offset."""
    if isinstance(node, ListExpr):
        yield node
        for item in node.items:
            yield from _lists(item)


def _headed(text: str, *heads: str) -> list[ListExpr]:
    """The lists of the source headed by one of `heads`, in order of start offset."""
    return [form for form in _lists(read_sexpr_text(text, source_path="<mutant>")) if _head(form) in heads]


def _operand(form: ListExpr, key: str) -> SExpr | None:
    """The item after the keyword `key` among the form's own items, or None."""
    for item, after in zip(form.items, form.items[1:]):
        if isinstance(item, KeywordAtom) and item.value == key:
            return after
    return None


def _range(node: SExpr) -> tuple[int, int]:
    """The character range of a node in the text it was read from."""
    return node.span.start.offset, node.span.end.offset


def _require_declared(operator: str, values: Sequence[str], declared: tuple[str, ...]) -> None:
    outside = [value for value in values if value not in declared]
    if outside:
        raise ValueError(f"{operator}: {outside} is outside the closed set {declared}")


def _role_literals(text: str, operator: str, key: str, values: Sequence[str]) -> Iterator[Mutation]:
    """For each role and value: the operand of `key` at every call form of the role, set to the value."""
    sites: dict[str, list[SExpr]] = {}
    for form in _headed(text, *_CALL_HEADS):
        role, site = form.items[1] if len(form.items) > 1 else None, _operand(form, key)
        if isinstance(role, SymbolAtom) and role.value.startswith(_ROLE_PREFIX) and site is not None:
            sites.setdefault(role.value.removeprefix(_ROLE_PREFIX), []).append(site)
    for role, operands in sites.items():
        for value in values:
            literal = f'"{value}"'
            edits = tuple((start, end, literal) for start, end in map(_range, operands) if text[start:end] != literal)
            if edits:
                yield Mutation(operator, f"{role}={value}", edits)


def effort(text: str, levels: Sequence[str] = EFFORTS) -> Iterator[Mutation]:
    """Effort per role.

    Input: a module's source. Edit: the operand of `:effort` in every call form of one role, all of
    them in one mutation, replaced by a string literal. Parameters: the role, in order of its first
    call; the level, in the order of `levels`. Raises ValueError, before the first mutation, for a
    level outside `EFFORTS`.

    Must not produce: a level outside `EFFORTS`; an edit of some of a role's sites (a site that
    already holds the level is left as it is); an inserted `:effort`; an edit of an input or of
    its default.
    """
    _require_declared("effort", levels, EFFORTS)
    return _role_literals(text, "effort", ":effort", levels)


def model(text: str, models: Sequence[str] = MODELS) -> Iterator[Mutation]:
    """Model per role: as `effort`, for the operand of `:model`.

    Raises ValueError, before the first mutation, for a model outside `MODELS`. Must not produce:
    a model outside `MODELS`; an edit of some of a role's sites; an inserted `:model`; an edit of
    an input or of its default.
    """
    _require_declared("model", models, MODELS)
    return _role_literals(text, "model", ":model", models)


OPERATORS: dict[str, Callable[[str], Iterator[Mutation]]] = {"effort": effort, "model": model}
"""Every mutation of one source per operator, in document order. Iteration order is the sample's."""


def apply(text: str, mutation: Mutation) -> str:
    """`text` with the mutation's edits spliced in, right to left.

    Raises ValueError when two edits overlap or an edit leaves the text: a mutation is applied to
    the source it was made from, and anything else is a caller's error.
    """
    edits = sorted(mutation.edits)
    last = 0
    for start, end, _ in edits:
        if not last <= start <= end <= len(text):
            raise ValueError(f"{mutation.operator}/{mutation.params}: the edit ({start}, {end}) overlaps the one "
                             f"before it or leaves the text of {len(text)} characters")
        last = end
    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    return text
