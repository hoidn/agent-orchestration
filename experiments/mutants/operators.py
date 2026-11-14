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

from collections.abc import Callable, Iterator
from dataclasses import dataclass

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


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


OPERATORS: dict[str, Callable[[str], Iterator[Mutation]]] = {}
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
