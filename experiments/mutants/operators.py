"""Mechanical mutation operators over `.orc` source text, and a deterministic sample of mutants.

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md ("Operators"; Task T1).

A mutation is a set of character-range edits, found by reading the source with the package's
reader and spliced into the text at the nodes' spans: there is no printer, and comments and layout
survive. `text` is decoded source and spans index its characters, not bytes. A source is spliced
as given: no line end is changed here, so a caller that compares digests or offsets with the
compiler's must normalise line ends (`\\r\\n` and `\\r` to `\\n`) before it calls an operator.
Nothing here compiles, runs or reads a file, and the module holds no state. It depends on
`orchestrator.workflow_lisp.reader.read_sexpr_text` and the node types of `sexpr` only.

The closed value sets live here and nowhere else (AGENTS.md, experiment rules: nothing above the
Sonnet ceiling, no Fable model). A caller may narrow them and can never widen them: there is no
override from the environment, a file or a command line. `tests/experiments/test_mutants.py`
repeats both tuples as literals. A source that already holds a string literal outside the sets in
`:model` or `:effort` position is refused, never mutated: every operator and `sample` raise
ValueError for it (`undeclared_literals` is the one check). A model or effort that arrives as a
name is an input, bound at launch: it is left alone, and only the launcher can pin it.

Shared terms. A call form is a list headed `provider-result` or `agent`; its role is its first
operand when that is a symbol `providers.R` (role `R`). The operand of `:k` is the item after the
keyword `:k` among a form's own items. Forms are numbered from zero in order of start offset. No
operator yields a mutation whose replacement equals the text it replaces. No operator changes the
module name, imports, exports, the target, a type declaration, a prompt's `:fills` or return type,
or the entry workflow's parameter list, and none but `graft` adds a line.
"""

import hashlib
import random
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import IntAtom, KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
ROUNDS = (1, 2, 3, 4)
APPENDED = " Check the result before you report."
EXPRESSION_HEADS = frozenset(
    "provider-result command-result call loop/recur let* if match list/map-effect list/map done continue variant "
    "record loop-state agent not and or = + list/append list/length".split())
_DECLARED = {":model": MODELS, ":effort": EFFORTS}
_CALL_HEADS = ("provider-result", "agent")
_ROLE_PREFIX = "providers."
_DEFINITIONS = ("defworkflow", "defproc")
_BINDER_HEADS = ("let*", "loop/recur", "list/map-effect", "list/map")
# What the reader takes between the quotes of a string (`reader._Reader._read_string`), not empty.
_STRING_BODY = re.compile(r'''(?:[^"\\\n\r]|\\[\\"nt])+''')


@dataclass(frozen=True)
class Mutation:
    """One mutation of one source: `apply(text, mutation)` is the mutant.

    `operator` is a key of `OPERATORS`; `params` names the mutation among that operator's
    mutations of the source (`reviewer=low`, `loop1=3`, `9<-18`, `work.drop2`), so
    `program/operator/params` is one mutant and reproduces it; for a proposed prompt text it holds
    a digest of the text (`replace_prompt`), which tells proposals apart and needs the text to
    reproduce the mutant. `edits` are disjoint `(start, end, replacement)` character ranges of the
    source the mutation was made from.
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


def _undeclared(root: ListExpr) -> list[tuple[str, str, int, int]]:
    found = []
    for form in _lists(root):
        for key, declared in _DECLARED.items():
            site = _operand(form, key)
            if isinstance(site, StringAtom) and site.value not in declared:
                found.append((key, site.value, site.span.start.line, site.span.start.column))
    return sorted(found, key=lambda literal: literal[2:])


def undeclared_literals(text: str) -> list[tuple[str, str, int, int]]:
    """The string literals of a source that are outside the closed sets, as `(keyword, value, line, column)`.

    A literal is the operand of `:model` or of `:effort` in any form of the source, a call form or
    not, in document order; lines and columns count from one. A name in that position is an input
    and is not listed. This is the one check of what a seed already holds: no operator mutates a
    source for which it is not empty.
    """
    return _undeclared(read_sexpr_text(text, source_path="<mutant>"))


def _headed(text: str, *heads: str) -> list[ListExpr]:
    """The lists of the source headed by one of `heads`, in order of start offset.

    Every operator reads its source here, so every operator raises ValueError for a source that
    holds a model or effort literal outside the closed sets.
    """
    root = read_sexpr_text(text, source_path="<mutant>")
    outside = _undeclared(root)
    if outside:
        raise ValueError("the source holds a model or effort literal outside the closed sets, as "
                         f"(keyword, value, line, column): {outside}")
    return [form for form in _lists(root) if _head(form) in heads]


def entry_inputs(text: str) -> list[str]:
    """The names of the inputs the entry workflow, `run`, declares, in order; read from the source, no compile."""
    (entry,) = [form for form in _headed(text, "defworkflow") if form.items[1].value == "run"]
    return [param.items[0].value for param in entry.items[2].items]


def _operand(form: ListExpr, key: str) -> SExpr | None:
    """The item after the keyword `key` among the form's own items, or None."""
    for item, after in zip(form.items, form.items[1:]):
        if isinstance(item, KeywordAtom) and item.value == key:
            return after
    return None


def _range(node: SExpr) -> tuple[int, int]:
    """The character range of a node in the text it was read from."""
    return node.span.start.offset, node.span.end.offset


def _declared_values(operator: str, values: Iterable[str], declared: tuple[str, ...]) -> tuple[str, ...]:
    """`values` read once, as a tuple. Raises ValueError for one outside `declared` or given twice."""
    values = tuple(values)
    outside = [value for value in values if value not in declared]
    if outside or len(set(values)) != len(values):
        raise ValueError(f"{operator}: {values} holds a value outside the closed set {declared} or holds one twice")
    return values


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


def effort(text: str, levels: Iterable[str] = EFFORTS) -> Iterator[Mutation]:
    """Effort per role.

    Input: a module's source. Edit: the operand of `:effort` in every call form of one role, all of
    them in one mutation, replaced by a string literal. Parameters: the role, in order of its first
    call; the level, in the order of `levels`, which is read once. Raises ValueError, before the
    first mutation, for a level outside `EFFORTS` or given twice.

    Must not produce: a level outside `EFFORTS`; an edit of some of a role's sites (a site that
    already holds the level is left as it is); an inserted `:effort`; an edit of an input or of
    its default.
    """
    return _role_literals(text, "effort", ":effort", _declared_values("effort", levels, EFFORTS))


def model(text: str, models: Iterable[str] = MODELS) -> Iterator[Mutation]:
    """Model per role: as `effort`, for the operand of `:model`.

    Raises ValueError, before the first mutation, for a model outside `MODELS` or given twice. Must not produce:
    a model outside `MODELS`; an edit of some of a role's sites; an inserted `:model`; an edit of
    an input or of its default.
    """
    return _role_literals(text, "model", ":model", _declared_values("model", models, MODELS))


def rounds(text: str) -> Iterator[Mutation]:
    """Revision rounds.

    Input: a module's source. Edit: the operand of `:max` of one `loop/recur`, when it is an
    integer literal, replaced by another integer. Parameters: the loop's number among the
    `loop/recur` forms; n in 1 to 4.

    Must not produce: 0; a value above 4; an edit of a `list/map-effect` cap; an edit of a bound
    that is not a literal.
    """
    for number, loop in enumerate(_headed(text, "loop/recur")):
        bound = _operand(loop, ":max")
        if isinstance(bound, IntAtom):
            for n in ROUNDS:
                if n != bound.value:
                    yield Mutation("rounds", f"loop{number}={n}", ((*_range(bound), str(n)),))


def drop_step(text: str) -> Iterator[Mutation]:
    """A step absent.

    Input: a module's source. Edit: one binding pair of one `let*` inside a `defworkflow` or a
    `defproc`, deleted, with the white space that follows it. Parameters: the `let*`'s number
    among the `let*` forms of those definitions; the pair's number in its binding list.

    Must not produce: anything but the deletion of one whole pair (a comment stays; a use of the
    dropped name stays, and the compiler refuses it).
    """
    lets = [form for definition in _headed(text, *_DEFINITIONS) for form in _lists(definition) if _head(form) == "let*"]
    for number, form in enumerate(lets):
        if len(form.items) > 1 and isinstance(form.items[1], ListExpr):
            for k, pair in enumerate(form.items[1].items):
                start, end = _range(pair)
                rest = text[end:]
                yield Mutation("drop_step", f"let{number}.{k}", ((start, end + len(rest) - len(rest.lstrip()), ""),))


def _prompt_bodies(text: str) -> dict[str, tuple[int, int]]:
    """Per `defprompt` whose last item is a string, by name: the character range between its quotes."""
    bodies = {}
    for form in _headed(text, "defprompt"):
        if len(form.items) > 2 and isinstance(form.items[1], SymbolAtom) and isinstance(form.items[-1], StringAtom):
            start, end = _range(form.items[-1])
            bodies[form.items[1].value] = (start + 1, end - 1)
    return bodies


def replace_prompt(text: str, name: str, raw: str) -> Mutation:
    """Prompt wording: the primitive a proposer uses.

    Input: a module's source. Edit: the body of the `defprompt` called `name` (its last item, a
    string) replaced by `raw`, which is source text as it stands between the quotes, so an escape
    is never re-encoded. Parameters: the prompt's name; the raw text. The mutation's `params` is
    the name and the first twelve hexadecimal digits of the SHA-256 of the raw text (UTF-8), so two
    proposals for one prompt have two names and one proposal has one name in every process.

    Must not produce: an empty body; an edit of two prompts; a change to `:fills`. Raises
    ValueError for a prompt the module does not have, for a raw text equal to the body's own, and
    for one that is not a string body: empty, or with an unescaped quote, a line end or an escape
    the reader refuses.
    """
    bodies = _prompt_bodies(text)
    if name not in bodies:
        raise ValueError(f"replace_prompt: no prompt {name!r} with a string body among {sorted(bodies)}")
    start, end = bodies[name]
    if not _STRING_BODY.fullmatch(raw):
        raise ValueError(f"replace_prompt: the raw text for {name!r} is not the body of a string: {raw!r}")
    if raw == text[start:end]:
        raise ValueError(f"replace_prompt: the raw text for {name!r} is the body it already has")
    return Mutation("prompt", f"{name}.{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}", ((start, end, raw),))


def prompt(text: str) -> Iterator[Mutation]:
    """Prompt wording, mechanically: it feeds the compile check and is not what a search uses.

    Input: a module's source. Edit: one `replace_prompt` per mutation. `drop k` gives the pieces
    of the raw body split at `". "` without piece k, joined by `". "`; `append` gives the body
    followed by the constant `APPENDED` (no brace, quote or backslash). Parameters: the prompt's
    name; `drop k` or `append`.

    Must not produce: an empty body; an edit of two prompts; a change to `:fills`.
    """
    for name, (start, end) in _prompt_bodies(text).items():
        pieces = text[start:end].split(". ")
        bodies = {f"drop{k}": ". ".join(pieces[:k] + pieces[k + 1:]) for k in range(len(pieces))}
        bodies["append"] = text[start:end] + APPENDED
        for label, raw in bodies.items():
            if raw:
                # ponytail: replace_prompt reads the source again for every mutation; pass the
                # ranges in if prompts ever dominate the time of a readout.
                yield replace(replace_prompt(text, name, raw), params=f"{name}.{label}")


def _tails(forms: Sequence[SExpr]) -> list[SExpr]:
    """What follows the first item of each list among `forms`: a binding's value, an arm's body."""
    return [item for form in forms if isinstance(form, ListExpr) for item in form.items[1:]]


def _loop_state_positions(items: Sequence[SExpr]) -> list[SExpr]:
    """The items of a `loop-state` form that may hold an expression: of a field declaration, the initial value."""
    kept: list[SExpr] = []
    for before, item in zip(items, items[1:]):
        declaration = isinstance(item, ListExpr) and not isinstance(before, KeywordAtom)
        kept += item.items[2:] if declaration else [item]
    return kept


def _expression_positions(form: ListExpr) -> Sequence[SExpr]:
    """The items of `form` that may hold an expression.

    Name positions are passed over and what they bind is kept: a binding pair of a `let*`, of a
    `loop/recur` binder list or of a map form's, the parameter list of `fn`, the pattern of a
    `match` arm, a field declaration `(name Type initial)` of a `loop-state` (a list that is not
    the operand of a keyword).
    """
    head, items = _head(form), form.items
    if head in _BINDER_HEADS and len(items) > 1 and isinstance(items[1], ListExpr):
        return [*_tails(items[1].items), *items[2:]]
    if head == "loop-state":
        return _loop_state_positions(items)
    if head == "fn":
        return items[2:]
    if head == "match":
        return [*items[1:2], *_tails(items[2:])]
    return items


def _expressions(node: SExpr) -> Iterator[ListExpr]:
    """The expression forms at or under `node`, which is in an expression position, by start offset."""
    if isinstance(node, ListExpr):
        if _head(node) in EXPRESSION_HEADS:
            yield node
        for item in _expression_positions(node):
            yield from _expressions(item)


def graft(text: str) -> Iterator[Mutation]:
    """A subtree moved: it stands for "the program's structure also mutates" and feeds the compile check.

    Input: a module's source. Edit: one expression form replaced by the source text of another of
    the same module. An expression form is a list inside the body of a `defworkflow` or `defproc`
    (what follows its parameter list) whose head is in `EXPRESSION_HEADS` and which is not in a
    name position (`_expression_positions`). Parameters: the target's number and the donor's
    among the expression forms, as `target<-donor`. The only operator that may add a line.

    Must not produce: a donor from another file; a donor that is or contains the target; a
    replacement equal to the target's text; a binding pair or a parameter list named like a head
    taken for an expression.
    """
    forms = [form for definition in _headed(text, *_DEFINITIONS)
             for item in definition.items[3:] for form in _expressions(item)]
    ranges = [_range(form) for form in forms]
    for t, (start, end) in enumerate(ranges):
        for d, (donor_start, donor_end) in enumerate(ranges):
            donor = text[donor_start:donor_end]
            if not donor_start <= start <= end <= donor_end and donor != text[start:end]:
                yield Mutation("graft", f"{t}<-{d}", ((start, end, donor),))


OPERATORS: dict[str, Callable[[str], Iterator[Mutation]]] = {
    "effort": effort, "model": model, "rounds": rounds, "drop_step": drop_step, "prompt": prompt, "graft": graft}
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


def _smallest_draws(mutations: list[Mutation], cap: int, seed: str) -> list[Mutation]:
    """All of `mutations` when there are at most `cap`; else the `cap` with the smallest draws, in document order.

    One `random()` is drawn per mutation from `random.Random(seed)`: the one method whose sequence
    the Python documentation fixes across versions.
    """
    if len(mutations) <= cap:
        return mutations
    generator = random.Random(seed)
    draws = [generator.random() for _ in mutations]
    kept = sorted(sorted(range(len(mutations)), key=draws.__getitem__)[:cap])
    return [mutations[index] for index in kept]


def _require_sampleable(sources: Mapping[str, str], cap: int, operators: Sequence[str]) -> None:
    """Raises ValueError for what `sample` refuses (its docstring), before any source is mutated."""
    unknown = [name for name in operators if name not in OPERATORS]
    if unknown or cap < 0:
        raise ValueError(f"sample: cap {cap} is negative, or {unknown} holds an operator not among {list(OPERATORS)}")
    outside = {program: found for program in sorted(sources) if (found := undeclared_literals(sources[program]))}
    if outside:
        raise ValueError("sample: a model or effort literal outside the closed sets, as (keyword, value, line, "
                         f"column) per program: {outside}")


def sample(sources: Mapping[str, str], cap: int, number: int,
           operators: Sequence[str] = tuple(OPERATORS)) -> list[tuple[str, Mutation]]:
    """At most `cap` mutations per program and operator, as `(program, mutation)`, the same for one `number`.

    `sources` maps a program's name to its source. Programs are taken in name order and operators
    in `OPERATORS` order, among those named in `operators`. All of an operator's mutations are
    kept when there are at most `cap`; else one `random()` is drawn per mutation from
    `random.Random(f"{number}/{program}/{operator}")` and the `cap` mutations with the smallest
    draws are kept, in document order.

    Raises ValueError, before any mutation is made, for a name `OPERATORS` lacks, for a negative
    `cap`, and for a source that holds a model or effort literal outside the closed sets, naming
    the program, the literal and its line and column.
    """
    _require_sampleable(sources, cap, operators)
    drawn = []
    for program in sorted(sources):
        for operator in (name for name in OPERATORS if name in operators):
            mutations = list(OPERATORS[operator](sources[program]))
            drawn += [(program, mutation)
                      for mutation in _smallest_draws(mutations, cap, f"{number}/{program}/{operator}")]
    return drawn
