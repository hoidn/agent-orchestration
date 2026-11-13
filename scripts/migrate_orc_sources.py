"""Migrate Workflow Lisp sources to target 2.40 and to the binder form of `loop/recur`.

usage: python scripts/migrate_orc_sources.py [--check] [--verify] [--report FILE.json] PATH...

A PATH is a file or a directory; a directory stands for every `.orc` and `.py` file below it
outside hidden directories and `__pycache__`, except the fixtures of this tool's own tests
(OWN_FIXTURES), which keep `fn`-form loops on purpose and are migrated only when named as files.

Units. A `.orc` file is one unit. In a Python module a unit is a string literal, or a run of
implicitly concatenated literals with one prefix, that contains `(:target-dsl` or `loop/recur`;
plain, raw and f-strings are read through their escapes, and each f-string replacement field is
read as an unknown symbol. A unit the reader refuses changes in nothing. A Python unit is never
touched, only reported, when the literal is a docstring, an operand of a comparison
(`==`, `in`, ...), the receiver or an argument of a text call (`.replace`, `re.sub`, `.format`,
`.count`, `.index`, `.find`, `.split`, `.startswith`, `.endswith`, `.partition`, `.strip`), the left
side of `%`, or assigned to a name used in one of those places: such text is a pattern or an
expectation, not a source.

1. Header and clauses (the stage 4 one-target plan, its `migrate2.py`), per whole source: a literal
   `(:target-dsl "2.35")` to `"2.39"` becomes `"2.40"`; every `:lowering inline|private-workflow|auto`
   clause of a `defproc` goes; below 2.39 every `:effects (...)` clause of a `defproc` goes. A clause
   that had its line to itself takes the line with it. In Python this applies only to a unit the
   reader reads as whole `(workflow-lisp ...)` modules; a header in any other literal is reported
   and left, so a source split over several literals never gets a 2.40 header beside 2.35 clauses.
   A header that is not a literal version (`{TARGET}`, `TARGET`) is reported with its clause count.

2. Loops (surface coherence design, section 5). Each `(loop/recur ... :state init ... (fn (s) body))`
   becomes `(loop/recur ((s init)) ... body)`. The two forms build the same program unless both
   `:max` and `:state` hold an effect and `:max` is written first, because the binder form evaluates
   the initial state first. So a loop outside a `defmacro` is rewritten WITHOUT compiling when the
   syntactic rule holds:

       `:state` is written before `:max`; or
       `:max` is an atom; or
       `:state` is an atom or a constant constructor.

   An *atom* is an integer, float, boolean or string literal, or a plain symbol (`limit`, `c.r`),
   except a parameter of an enclosing `defmacro` (its argument may be any expression) and a symbol
   holding an f-string replacement field (unknown text). A *constant constructor* is `(record ...)`,
   `(list ...)`, `(variant ...)` or `(loop-state ...)` whose every operand is a keyword, an atom or a
   constant constructor (for `loop-state`, every field `(name Type value)` has such a value).
   Neither can run an effect.

   Any other loop, and every loop inside a `defmacro` template, is compiled before and after its
   rewrite (a temporary copy of the source; the commands, providers and prompts are made up from the
   source, as the stage 4 plan's `classify.py` does). It is rewritten only when every exported
   workflow builds, each keeps its program hash, normalized as the stage 4 plan defines (`target`
   replaced, every `@` provenance object removed), and the loop is inside an exported `defworkflow`
   or in a template whose macro the source uses. Otherwise it stays in the `fn` form and is listed.

   The rewrite edits three places: the binder is inserted after `loop/recur` (a multi-line initial
   state is re-indented by the distance it moves), the `:state` pair is cut, and `(fn (s) body)` is
   replaced by its body, dedented by the width the wrapper added when every later body line is
   indented with spaces at least as deep as the body's first character (otherwise the indentation is
   kept and counted). A Workflow Lisp string cannot span lines, so re-indenting never changes a value.

Text outside the rewritten parts, comments and Python escape sequences included, is kept byte for
byte (line endings too); f-string replacement fields are kept exactly, and a literal whose fields a
clause drop would lose is left as it was. Every edit is an insertion or a deletion of Workflow Lisp
text, so quotes and line breaks between concatenated literals stay; the moved initial state is
re-encoded for its new literal when it spanned several. A Python file that would not parse
afterwards is not written; a file that cannot be read or tokenized is reported and skipped. A second
run changes nothing. `--check` writes nothing and exits 1 if anything would change. `--verify` also
compiles each syntactically rewritten loop's source, the original text against the rewritten, when
at least one workflow builds, and refuses the rewrite on a moved hash (a defect of the rule above).
`--report` writes JSON: every changed file with its counts, and every unit left for hand work with
file, line, category and reason.

Dependencies: the repository's own reader and compiler (`orchestrator.workflow_lisp`); run it from
the repository root with the tree to migrate on `PYTHONPATH`.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
import ast
import codecs
from dataclasses import dataclass, field
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import tokenize
import warnings

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import (
    BoolAtom, FloatAtom, IntAtom, KeywordAtom, ListExpr, StringAtom, SymbolAtom,
)

OLD_VERSION = re.compile(r'\(:target-dsl\s+"(2\.3[5-9])"\)')
ANY_HEADER = re.compile(r'\(:target-dsl\s+"([^"]*)"\)')
LOWERING_MODES = {"inline", "private-workflow", "auto"}
FN_LOOP_TEXT = re.compile(r"\(loop/recur(?!\s*\(\()")
FIELD = "__orcfield{}__"
LITERALS = (IntAtom, FloatAtom, BoolAtom, StringAtom)
CONSTRUCTORS = {"record", "list", "variant", "loop-state"}
TEXT_METHODS = {"replace", "sub", "subn", "format", "count", "index", "rindex", "find", "rfind", "split",
                "rsplit", "startswith", "endswith", "partition", "rpartition", "strip", "removeprefix",
                "removesuffix"}


@dataclass
class Report:
    """What one file's migration did or would do."""

    path: str
    headers: int = 0
    lowering: int = 0
    effects: int = 0
    loops_found: int = 0
    syntactic: int = 0
    hashed: int = 0
    kept_indent: int = 0
    verified: int = 0
    unverifiable: int = 0
    mismatches: list[int] = field(default_factory=list)
    left: list[tuple[int, str, str]] = field(default_factory=list)  # loops: (line, category, reason)
    notes: list[tuple[int, str, str]] = field(default_factory=list)  # headers and literals: the same
    error: str | None = None

    def leave(self, line: int, category: str, reason: str) -> None:
        self.left.append((line, category, reason))

    def note(self, line: int, category: str, reason: str) -> None:
        self.notes.append((line, category, reason))

    def absorb(self, other: "Report") -> None:
        for name in ("headers", "lowering", "effects", "loops_found", "syntactic", "hashed", "kept_indent",
                     "verified", "unverifiable"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.mismatches += other.mismatches
        self.left += other.left
        self.notes += other.notes

    @property
    def changes(self) -> int:
        return self.headers + self.lowering + self.effects + self.syntactic + self.hashed


# --- text with a map from read offsets to source offsets ------------------------------------

@dataclass
class Unit:
    """One `.orc` source: `src` is what the file holds, `value` what the reader reads.

    For a `.orc` file the two are the same. For Python, `src` is one string literal or a run of
    implicitly concatenated literals with one prefix, quotes included, and `value` the text their
    bodies make; escape sequences and doubled f-string braces are decoded. `pos[i]` is the offset in
    `src` of `value[i]` (`pos[len(value)]` is the end of the last body), so an edit planned on
    `value` is applied to `src` and every byte outside it is kept. `col0` is the column of `src[0]`.
    """

    src: str
    python: bool = False
    line0: int = 1
    col0: int = 0
    value: str = ""
    pos: list[int] = field(default_factory=list)
    bodies: list[tuple[int, int, str, str]] = field(default_factory=list)  # start, end, prefix, quote

    def __post_init__(self) -> None:
        self.decode()

    def decode(self) -> None:
        if not self.python:
            self.value, self.pos, self.bodies = self.src, list(range(len(self.src) + 1)), [(0, len(self.src), "r", "")]
            return
        value, pos, self.bodies = [], [], []
        for start, end in _string_tokens("(" + self.src + ")"):
            prefix, quote = _prefix_quote(self.src[start - 1:end - 1])
            body_start, body_end = start - 1 + len(prefix) + len(quote), end - 1 - len(quote)
            self.bodies.append((body_start, body_end, prefix.lower(), quote))
            _decode_body(self.src, body_start, body_end, prefix.lower(), value, pos)
        pos.append(self.bodies[-1][1])
        self.value, self.pos = "".join(value), pos

    def slice(self, start: int, end: int) -> str:
        return self.src[self.pos[start]:self.pos[end]]

    def apply(self, edits: list[tuple[int, int, str]]) -> None:
        """Apply (value start, value end, source text) edits, then read again.

        A deletion removes only body text, so quotes and separators between literals stay.
        """
        spans = []
        for start, end, text in edits:
            if text:
                spans.append((self.pos[start], self.pos[end], text))
                continue
            spans.extend((max(a, self.pos[start]), min(b, self.pos[end]), "") for a, b, _, _ in self.bodies
                         if max(a, self.pos[start]) < min(b, self.pos[end]))
        for start, end, text in sorted(spans, reverse=True):
            self.src = self.src[:start] + text + self.src[end:]
        self.decode()

    def text(self, start: int, end: int, at: int) -> str:
        """Source text for `value[start:end]` to insert at value offset `at`.

        The source slice itself when it lies in one literal; otherwise the value re-encoded for the
        literal that holds `at` (a slice across literals may close a literal with another quote).
        """
        inside = [body for body in self.bodies if body[0] <= self.pos[start] and self.pos[end] <= body[1]]
        if inside:
            return self.slice(start, end)
        _, _, prefix, quote = next(body for body in self.bodies if body[0] <= self.pos[at] <= body[1])
        return _encode(self.value[start:end], prefix, quote)

    def value_column(self, offset: int) -> int:
        """The column of `value[offset]` in the Workflow Lisp text; the first line starts where the file puts it."""
        start = self.value.rfind("\n", 0, offset) + 1
        return offset - start + (self.column(0) if start == 0 else 0)

    def line(self, offset: int) -> int:
        return self.line0 + self.src.count("\n", 0, self.pos[offset])

    def column(self, offset: int) -> int:
        at = self.pos[offset]
        start = self.src.rfind("\n", 0, at) + 1
        return at - start + (self.col0 if start == 0 else 0)


ESCAPE = r"\\(?:\n|[0-7]{1,3}|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|N\{[^}]*\}|.)"


class LiteralBreak(ValueError):
    """The rewrite cannot be written into the Python literal it falls in."""


def _encode(text: str, prefix: str, quote: str) -> str:
    if "r" in prefix:
        if quote[0] in text or "\\" in text or (len(quote) == 1 and "\n" in text):
            raise LiteralBreak("the moved text cannot be written in a raw literal")
        return text
    text = text.replace("\\", "\\\\").replace(quote[0], "\\" + quote[0])
    if len(quote) == 1:
        text = text.replace("\n", "\\n")
    return text.replace("{", "{{").replace("}", "}}") if "f" in prefix else text


def _prefix_quote(token: str) -> tuple[str, str]:
    prefix = re.match(r"[rRbBuUfF]*", token).group()
    triple = token[len(prefix):len(prefix) + 3]
    return prefix, triple if triple in {'"""', "'''"} else token[len(prefix)]


def _decode_body(src: str, start: int, end: int, prefix: str, value: list[str], pos: list[int]) -> None:
    pattern = "|".join(([r"\{\{|\}\}"] if "f" in prefix else []) + ([] if "r" in prefix else [ESCAPE])) or r"(?!)"
    index = start
    for match in re.compile(pattern, re.S).finditer(src, start, end):
        value.extend(src[index:match.start()])
        pos.extend(range(index, match.start()))
        piece = _decoded(match.group())
        value.extend(piece)
        pos.extend([match.start()] * len(piece))
        index = match.end()
    value.extend(src[index:end])
    pos.extend(range(index, end))


def _decoded(escape: str) -> str:
    if escape in {"{{", "}}"}:
        return escape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return codecs.decode(escape, "unicode_escape")


# --- 1. header and clauses -----------------------------------------------------------------

def _read(text: str) -> ListExpr | None:
    try:
        return read_sexpr_text(text, source_path="<migrate>")
    except LispFrontendCompileError:
        return None


def _whole_modules(tree: ListExpr) -> bool:
    """Whether the text is one or more complete `(workflow-lisp ...)` modules and nothing else."""
    return bool(tree.items) and all(
        isinstance(item, ListExpr) and item.items and _is_symbol(item.items[0], "workflow-lisp")
        for item in tree.items)


def _clause_span(value: str, start: int, end: int) -> tuple[int, int]:
    """The clause with the blanks before it on its line, and its line when it had the line to itself."""
    while start > 0 and value[start - 1] in " \t":
        start -= 1
    rest = re.match(r"[ \t]*\n", value[end:])
    if (start == 0 or value[start - 1] == "\n") and rest is not None:
        end += rest.end()
    return start, end


def _merged(value: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Join clauses that touch (`:effects (...) :lowering inline`), then extend them as one."""
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [_clause_span(value, start, end) for start, end in merged]


def _defprocs(node: object):
    if isinstance(node, ListExpr):
        if node.items and _is_symbol(node.items[0], "defproc"):
            yield node
        for item in node.items:
            yield from _defprocs(item)


def clause_spans(tree: ListExpr, value: str, *, effects: bool) -> tuple[list, list]:
    """The `:lowering <mode>` and (when asked) `:effects (...)` clauses of every `defproc`."""
    lowering, effect = [], []
    for proc in _defprocs(tree):
        for key, value_node in zip(proc.items, proc.items[1:]):
            if not isinstance(key, KeywordAtom):
                continue
            if key.value == ":lowering" and isinstance(value_node, SymbolAtom) and value_node.value in LOWERING_MODES:
                lowering.append(_clause_span(value, _start(key), _end(value_node)))
            elif effects and key.value == ":effects" and isinstance(value_node, ListExpr):
                effect.append(_clause_span(value, _start(key), _end(value_node)))
    return lowering, effect


def _header(tree: ListExpr) -> StringAtom | None:
    for module in tree.items:
        for item in (module.items if isinstance(module, ListExpr) else ()):
            if (isinstance(item, ListExpr) and len(item.items) == 2 and isinstance(item.items[0], KeywordAtom)
                    and item.items[0].value == ":target-dsl" and isinstance(item.items[1], StringAtom)):
                return item.items[1]
    return None


def migrate_header(unit: Unit, tree: ListExpr | None, report: Report) -> None:
    """Retarget a whole 2.35-2.39 source to 2.40 and drop the clauses 2.40 refuses; report the rest."""
    found = ANY_HEADER.search(unit.value)
    if found is None:
        return
    line = unit.line(found.start())
    if unit.python and (tree is None or not _whole_modules(tree)):
        if OLD_VERSION.search(unit.value):
            report.note(line, "partial-source", "header in a literal that is not a whole module: left for hand work")
        return
    if tree is None:
        report.note(line, "reader", "the reader refuses the source: header and clauses left")
        return
    header = _header(tree)
    version = header.value if header is not None else found.group(1)
    if not re.fullmatch(r"\d+\.\d+", version):
        lowering, effects = clause_spans(tree, unit.value, effects=True)
        report.note(line, "parameter-header", f"header `{version}` is a parameter, left to the caller "
                    f"({len(lowering)} :lowering, {len(effects)} :effects clauses)")
        return
    if header is None or not OLD_VERSION.fullmatch(f'(:target-dsl "{version}")'):
        return
    lowering, effects = clause_spans(tree, unit.value, effects=version != "2.39")
    cuts = _merged(unit.value, lowering + effects)
    unit.apply([(_start(header) + 1, _end(header) - 1, "2.40"), *((s, e, "") for s, e in cuts)])
    report.headers += 1
    report.lowering += len(lowering)
    report.effects += len(effects)


# --- 2. loops: finding them and the syntactic rule -------------------------------------------

@dataclass
class Loop:
    node: ListExpr
    opaque: frozenset[str]
    workflow: str | None
    macro: str | None


def _is_symbol(node: object, value: str) -> bool:
    return isinstance(node, SymbolAtom) and node.value == value


def _is_fn_loop(node: ListExpr) -> bool:
    items = node.items
    return (len(items) > 1 and _is_symbol(items[0], "loop/recur") and isinstance(items[-1], ListExpr)
            and bool(items[-1].items) and _is_symbol(items[-1].items[0], "fn"))


def _context(node: ListExpr, opaque: frozenset[str], workflow: str | None, macro: str | None):
    head = node.items[0] if node.items else None
    named = len(node.items) > 1 and isinstance(node.items[1], SymbolAtom)
    if _is_symbol(head, "defmacro") and named and len(node.items) > 2 and isinstance(node.items[2], ListExpr):
        params = {item.value for item in node.items[2].items if isinstance(item, SymbolAtom)}
        return opaque | params, workflow, node.items[1].value
    if _is_symbol(head, "defworkflow") and named:
        return opaque, node.items[1].value, macro
    return opaque, workflow, macro


def fn_loops(text: str) -> list[Loop]:
    """Every `(loop/recur ... (fn ...))` list of the source, in document order."""
    found: list[Loop] = []

    def walk(node: object, opaque: frozenset[str], workflow: str | None, macro: str | None) -> None:
        if not isinstance(node, ListExpr):
            return
        opaque, workflow, macro = _context(node, opaque, workflow, macro)
        if _is_fn_loop(node):
            found.append(Loop(node, opaque, workflow, macro))
        for item in node.items:
            walk(item, opaque, workflow, macro)

    walk(read_sexpr_text(text, source_path="<migrate>"), frozenset(), None, None)
    return found


def _fn_loop_problem(node: ListExpr) -> str | None:
    """Why a `fn`-form loop cannot be rewritten mechanically, or None."""
    fn, options = node.items[-1], node.items[1:-1]
    if len(fn.items) != 3 or not isinstance(fn.items[1], ListExpr) or len(fn.items[1].items) != 1:
        return "the `fn` is not `(fn (state) body)`"
    if not isinstance(fn.items[1].items[0], SymbolAtom):
        return "the `fn` parameter is not a plain name"
    keys = options[::2]
    if len(options) % 2 or not all(isinstance(key, KeywordAtom) for key in keys):
        return "the options are not keyword/value pairs"
    names = [key.value for key in keys]
    if names.count(":state") != 1 or names.count(":max") != 1:
        return "the loop has no single `:state` and `:max`"
    return None


def _atomic(node: object, opaque: frozenset[str]) -> bool:
    if isinstance(node, LITERALS):
        return True
    return isinstance(node, SymbolAtom) and node.value not in opaque and "__orcfield" not in node.value


def _constant(node: object, opaque: frozenset[str]) -> bool:
    if _atomic(node, opaque):
        return True
    if not isinstance(node, ListExpr) or not node.items or not isinstance(node.items[0], SymbolAtom):
        return False
    if node.items[0].value not in CONSTRUCTORS:
        return False
    if node.items[0].value == "loop-state":
        return all(isinstance(item, ListExpr) and len(item.items) == 3 and _constant(item.items[2], opaque)
                   for item in node.items[1:])
    return all(isinstance(item, KeywordAtom) or _constant(item, opaque) for item in node.items[1:])


def _operands(node: ListExpr) -> dict[str, tuple[int, object]]:
    options = node.items[1:-1]
    return {key.value: (index, value) for index, (key, value) in enumerate(zip(options[::2], options[1::2]))}


def syntactic_rule(loop: Loop) -> bool:
    """True when the binder form cannot reorder an effect (see the module docstring).

    A loop inside a `defmacro` template is never decided here: its expansion is checked by compiling.
    """
    if loop.macro is not None:
        return False
    operands = _operands(loop.node)
    (max_at, max_node), (state_at, state_node) = operands[":max"], operands[":state"]
    return state_at < max_at or _atomic(max_node, loop.opaque) or _constant(state_node, loop.opaque)


# --- 2. loops: the rewrite -----------------------------------------------------------------

def _start(node: object) -> int:
    return node.span.start.offset


def _end(node: object) -> int:
    return node.span.end.offset


def _dedent_edits(unit: Unit, fn: ListExpr, body: object, lead: int) -> list[tuple[int, int, str]] | None:
    """Deletions that dedent the body by the width the `(fn (s)` wrapper added, or None if unsafe.

    Columns are those of the Workflow Lisp text (`unit.value`). A Workflow Lisp string cannot span
    lines, so removing leading spaces never changes a value.
    """
    width = unit.value_column(_start(body)) - unit.value_column(_start(fn))
    starts = [i + 1 for i in range(lead, _end(body)) if unit.value[i] == "\n"]
    lines = [(start, len(unit.value[start:_end(body)].split("\n", 1)[0])) for start in starts]
    leading = [(start, len(unit.value[start:start + length]) - len(unit.value[start:start + length].lstrip(" ")))
               for start, length in lines]
    filled = [(start, spaces) for (start, length), (_, spaces) in zip(lines, leading) if spaces < length]
    if width <= 0 or not filled:
        return []
    if any(unit.value[start + spaces] == "\t" for start, spaces in filled):  # tab indentation: kept
        return None
    if any(spaces < unit.value_column(_start(body)) for _, spaces in filled):
        return None
    return [(start, start + min(width, spaces), "") for start, spaces in leading]


def _reindented(unit: Unit, node: object, column: int) -> str | None:
    """The multi-line initial state, its later lines shifted by the distance it moves to `column`.

    None when it is one line, spans literals, holds escapes or tabs, or would lose non-blank text.
    """
    text = unit.value[_start(node):_end(node)]
    shift = column - unit.value_column(_start(node))
    if "\n" not in text or shift == 0 or unit.slice(_start(node), _end(node)) != text or "\t" in text:
        return None
    lines = text.split("\n")
    if shift < 0 and any(line.strip() and len(line) - len(line.lstrip(" ")) < -shift for line in lines[1:]):
        return None
    return "\n".join([lines[0], *((" " * shift + line if shift > 0 else line[-shift:]) if line.strip() else line
                                   for line in lines[1:])])


def rewrite_loop(unit: Unit, node: ListExpr) -> bool:
    """Rewrite one `fn`-form loop to the binder form in `unit`; return whether the body was dedented.

    Every edit is an insertion or a deletion of Workflow Lisp text, so in a Python literal the
    quotes, prefixes and line structure around the deleted parts stay.
    """
    head, fn = node.items[0], node.items[-1]
    params, body = fn.items[1], fn.items[2]
    index = next(i for i, item in enumerate(node.items) if isinstance(item, KeywordAtom) and item.value == ":state")
    key, value = node.items[index], node.items[index + 1]
    at = _end(head)
    name = unit.text(_start(params.items[0]), _end(params.items[0]), at)
    moved = _reindented(unit, value, unit.value_column(at) + len(" ((") + len(unit.value[_start(params.items[0]):_end(params.items[0])]) + 1)
    binder = f" (({name} {moved if moved is not None else unit.text(_start(value), _end(value), at)}))"
    cut_start = max(_end(node.items[index - 1]), len(unit.value[:_start(key)].rstrip()))
    gap = unit.value[_end(params):_start(body)]
    lead = _end(params) + len(gap) - len(gap.lstrip())
    keeps_comment = ";" in unit.value[_end(body):_end(fn) - 1]
    dedent = _dedent_edits(unit, fn, body, lead)
    unit.apply([
        (_end(head), _end(head), binder),
        (cut_start, _end(value), ""),
        (_start(fn), lead, ""),
        (_end(fn) - 1 if keeps_comment else _end(body), _end(fn), ""),
        *(dedent or []),
    ])
    return dedent is not None


# --- program hash ------------------------------------------------------------------------------

def _strip(value):
    if isinstance(value, dict):
        return {key: _strip(child) for key, child in value.items() if key != "@"}
    if isinstance(value, (list, tuple)):
        return [_strip(child) for child in value]
    return value


def normalized_hash(tree: dict) -> str:
    """The stage 4 plan's normalized hash: `target` replaced and every `@` object removed."""
    stripped = _strip(dict(tree))
    stripped["target"] = "X"
    return hashlib.sha256(json.dumps(stripped, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _externs(source: str):
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding

    providers = {name: name for name in set(re.findall(r"\bproviders\.[a-zA-Z_][\w.-]*", source))}
    prompts = {name: "prompt.md" for name in set(re.findall(r"\bprompts\.[a-zA-Z_][\w.-]*", source))}
    commands = {}
    for match in re.finditer(r"\(command-result\s+([^\s()]+)", source):
        argv = re.match(r'\s+:argv\s+\(((?:\s*"[^"]*")+)', source[match.end():match.end() + 400])
        stable = tuple(re.findall(r'"([^"]*)"', argv.group(1))) if argv else ()
        commands.setdefault(match.group(1), ExternalToolBinding(
            name=match.group(1), stable_command=stable or ("python", "tool.py"), closure=()))
    return providers, prompts, commands


def _module_parts(source: str) -> list[str]:
    match = re.search(r"\(defmodule\s+([^\s)]+)", source)
    return match.group(1).split("/") if match else ["entry"]


def _module_root(path: Path, source: str) -> Path:
    parts = _module_parts(source)
    owner = path.parents[len(parts) - 1] if len(parts) <= len(path.parents) else path.parent
    return owner if owner / Path(*parts).with_suffix(".orc") == path else path.parent


def _graph_source(path: Path, root: Path, seen: set[Path]) -> str:
    if path in seen or not path.is_file():
        return ""
    seen.add(path)
    source = path.read_text(encoding="utf-8")
    for match in re.finditer(r"\(import\s+([^\s)]+)", source):
        source += _graph_source(root / (match.group(1) + ".orc"), root, seen)
    return source


def entries(source: str) -> list[str]:
    defined = re.findall(r"\(defworkflow\s+([^\s()]+)", source)
    exported = [name for clause in re.findall(r"\(export\s+([^)]*)\)", source) for name in clause.split()]
    return [name for name in exported if name in defined] or defined


def program_outcomes(text: str, origin: Path | None) -> dict[str, str]:
    """Each workflow of the source: `built:<normalized hash>` or `refused:<first code>`.

    The source is compiled from a temporary copy at its module path; imports resolve beside it
    first and then from the module root of `origin`, the file it came from, when there is one.
    """
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program

    with tempfile.TemporaryDirectory(prefix="migrate-orc-") as scratch:
        path = Path(scratch, *_module_parts(text)).with_suffix(".orc")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        roots = (Path(scratch),) + ((_module_root(origin, text),) if origin is not None else ())
        imported = "".join(_graph_source(roots[-1] / (m.group(1) + ".orc"), roots[-1], set())
                           for m in re.finditer(r"\(import\s+([^\s)]+)", text))
        providers, prompts, commands = _externs(text + imported)
        outcomes = {}
        for entry in entries(text):
            try:
                typed = compile_typed_program(
                    path, entry_workflow=entry, source_roots=roots, workspace_root=Path(scratch),
                    command_boundaries=commands, provider_externs=providers, prompt_externs=prompts)
                outcomes[entry] = "built:" + normalized_hash(build_closed_program(typed).tree)
            except LispFrontendCompileError as error:
                outcomes[entry] = "refused:" + error.diagnostics[0].code
            except Exception as error:  # a compiler defect is a refusal here, recorded with its type
                outcomes[entry] = f"crash:{type(error).__name__}"
    return outcomes


# --- one source -------------------------------------------------------------------------------

@dataclass
class Baseline:
    """The program hashes of the source as it was before any loop was rewritten (`text`).

    `text` is taken when the baseline is made, before the first loop edit; the hashes are computed on
    first use, from that text, so a rewritten source is always compared with the original.
    """

    text: str
    origin: Path | None
    outcomes: dict[str, str] | None = None

    def why_not(self) -> str | None:
        if "__orcfield" in self.text:
            return "an f-string source cannot be compiled"
        header = ANY_HEADER.search(self.text)
        if header is None or not re.fullmatch(r"\d+\.\d+", header.group(1)):
            return "a source without a literal header cannot be compiled"
        if self.outcomes is None:
            self.outcomes = program_outcomes(self.text, self.origin)
        if not self.outcomes:
            return "no workflow to compare the program hash on"
        refused = sorted(f"{name} {o}" for name, o in self.outcomes.items() if not o.startswith("built:"))
        return f"does not build ({'; '.join(refused)})" if refused else None

    def any_built(self) -> bool:
        """Whether at least one workflow builds, so a moved hash would show (used by `--verify`)."""
        reason = self.why_not()
        return reason is None or (self.outcomes is not None and any(
            outcome.startswith("built:") for outcome in self.outcomes.values()))

    def keeps(self, text: str) -> bool:
        return program_outcomes(text, self.origin) == self.outcomes


def _rewrite(unit: Unit, loop: Loop) -> tuple[bool, str | None]:
    """Rewrite the loop in place: (whether its body was dedented, why it could not be written)."""
    before = unit.src
    try:
        return rewrite_loop(unit, loop.node), None
    except (LiteralBreak, tokenize.TokenError) as error:
        unit.src = before
        unit.decode()
        return False, f"the rewrite cannot be written into the Python literal ({error})"


def _undo(unit: Unit, before: str) -> None:
    unit.src = before
    unit.decode()


def _covered(loop: Loop, baseline: Baseline) -> bool:
    """Whether the compiled programs include the loop: in an exported workflow, or a used template."""
    if loop.macro is not None:
        return bool(re.search(r"\(" + re.escape(loop.macro) + r"[\s)]", baseline.text))
    return loop.workflow in baseline.outcomes


def _hash_rewrite(unit: Unit, loop: Loop, baseline: Baseline, report: Report) -> tuple[str, str] | None:
    """Rewrite a loop the syntactic rule does not decide if its program keeps its hash; else (category, why)."""
    what = "inside a `defmacro` template" if loop.macro else "effects may be reordered"
    category = "macro" if loop.macro else "reorder"
    reason = baseline.why_not()
    if reason is not None:
        return category, f"{what} and {reason}"
    if not _covered(loop, baseline):
        return category, f"{what} and no exported workflow reaches the loop"
    before = unit.src
    dedented, problem = _rewrite(unit, loop)
    if problem is not None:
        return "literal-break", problem
    if not baseline.keeps(unit.value):
        _undo(unit, before)
        return category, f"{what} and the program hash changes"
    report.hashed += 1
    report.kept_indent += not dedented
    return None


def _syntactic_rewrite(unit: Unit, loop: Loop, baseline: Baseline, report: Report,
                       verify: bool) -> tuple[str, str] | None:
    before = unit.src
    dedented, problem = _rewrite(unit, loop)
    if problem is not None:
        return "literal-break", problem
    if verify:
        if not baseline.any_built():
            report.unverifiable += 1
        elif baseline.keeps(unit.value):
            report.verified += 1
        else:
            _undo(unit, before)
            report.mismatches.append(unit.line(_start(loop.node)))
            return "mismatch", "MISMATCH: the syntactic rule held but the program hash changes"
    report.syntactic += 1
    report.kept_indent += not dedented
    return None


def migrate_loops(unit: Unit, origin: Path | None, report: Report, verify: bool) -> None:
    """Rewrite every `fn`-form loop the rule or the hash allows; list the others."""
    loops = fn_loops(unit.value)
    report.loops_found += len(loops)
    baseline, cursor = Baseline(unit.value, origin), len(unit.value) + 1
    # Last loop first: an edit only moves text after its own start, so every loop still to be
    # visited keeps its offset and its line.
    while (pending := [loop for loop in fn_loops(unit.value) if _start(loop.node) < cursor]):
        loop = pending[-1]
        cursor = _start(loop.node)
        line = unit.line(cursor)
        problem = _fn_loop_problem(loop.node)
        if problem is not None:
            left = ("malformed", problem)
        elif syntactic_rule(loop):
            left = _syntactic_rewrite(unit, loop, baseline, report, verify)
        else:
            left = _hash_rewrite(unit, loop, baseline, report)
        if left is not None:
            report.leave(line, *left)


def migrate_unit(unit: Unit, origin: Path | None, report: Report, verify: bool,
                 moved: Callable[[str, str], str | None] = lambda before, after: None) -> None:
    """Header and clauses, then loops; a unit the reader refuses changes in nothing.

    `moved(before, after)` judges the loop rewrites alone; when it gives a reason the loops are
    undone and listed under `pattern` (`_moved_pattern`).
    """
    tree = _read(unit.value)
    migrate_header(unit, tree, report)
    if tree is None:
        _skip(unit, report, "reader", "the reader refuses the source")
        return
    headed, loops = unit.src, Report(report.path)
    migrate_loops(unit, origin, loops, verify)
    reason = moved(headed, unit.src)
    if reason is None:
        report.absorb(loops)
        return
    _undo(unit, headed)
    _skip(unit, report, "pattern", reason)


def _skip(unit: Unit, report: Report, category: str, reason: str) -> None:
    for match in FN_LOOP_TEXT.finditer(unit.value):
        report.loops_found += 1
        report.leave(unit.line(match.start()), category, reason)


# --- Python files ------------------------------------------------------------------------------

def _tokens(source: str):
    """(kind, start offset, end offset): `string` for a literal (an f-string whole), else the token type."""
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    offset = lambda position: starts[position[0] - 1] + position[1]  # noqa: E731
    fstring_start, depth = 0, 0
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == getattr(tokenize, "FSTRING_START", None):
            fstring_start = offset(token.start) if depth == 0 else fstring_start
            depth += 1
        elif token.type == getattr(tokenize, "FSTRING_END", None):
            depth -= 1
            if depth == 0:
                yield "string", fstring_start, offset(token.end)
        elif depth == 0:
            kind = "string" if token.type == tokenize.STRING else tokenize.tok_name[token.type]
            yield kind, offset(token.start), offset(token.end)


def _string_tokens(source: str):
    """(start offset, end offset) of each string literal, f-strings whole."""
    return [(start, end) for kind, start, end in _tokens(source) if kind == "string"]


def _string_groups(source: str) -> list[list[tuple[int, int]]]:
    """Runs of implicitly concatenated literals (only line breaks and comments between them)."""
    groups, current = [], []
    for kind, start, end in _tokens(source):
        if kind == "string":
            current.append((start, end))
        elif kind not in {"NL", "COMMENT"} and current:
            groups.append(current)
            current = []
    return groups + ([current] if current else [])


def _fields(body: str, fields: list[str]) -> str:
    """Replace each f-string replacement field with a sentinel symbol, appending it to `fields`."""
    out, index = [], 0
    while index < len(body):
        if body.startswith(("{{", "}}"), index):
            out.append(body[index:index + 2])
            index += 2
        elif body[index] == "{":
            depth, cursor = 1, index + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(body[cursor], 0)
                cursor += 1
            out.append(FIELD.format(len(fields)))
            fields.append(body[index:cursor])
            index = cursor
        else:
            out.append(body[index])
            index += 1
    return "".join(out)


def _restore(src: str, fields: list[str]) -> str | None:
    for number, text in enumerate(fields):
        if src.count(FIELD.format(number)) != 1:
            return None
        src = src.replace(FIELD.format(number), text)
    return src


def _with_sentinels(source: str, group: list[tuple[int, int]]) -> tuple[str, list[str]]:
    """The group's source with every f-string field replaced by a sentinel, and the fields."""
    out, fields, cursor = [], [], group[0][0]
    for start, end in group:
        prefix, quote = _prefix_quote(source[start:end])
        body_start, body_end = start + len(prefix) + len(quote), end - len(quote)
        body = source[body_start:body_end]
        out.append(source[cursor:body_start] + (_fields(body, fields) if "f" in prefix.lower() else body))
        cursor = body_end
    out.append(source[cursor:group[-1][1]])
    return "".join(out), fields


def _python_group(source: str, group: list[tuple[int, int]], report: Report, verify: bool,
                  protected: dict[tuple[int, int], tuple[str, str]]) -> str:
    """The literals `group` of `source`, migrated (one prefix for all of them)."""
    start, end = group[0][0], group[-1][1]
    text, fields = _with_sentinels(source, group)
    col0 = start - (source.rfind("\n", 0, start) + 1)
    unit = Unit(text, python=True, line0=source.count("\n", 0, start) + 1, col0=col0)
    guard = next((why for (a, b), why in protected.items() if a < end and start < b), None)
    if guard is None and "b" in _prefix_quote(source[start:group[0][1]])[0].lower():
        guard = ("bytes", "inside a bytes literal")
    if guard is not None:
        _skip(unit, report, *guard)
        if OLD_VERSION.search(unit.value):
            report.note(unit.line0, guard[0], f"header left: {guard[1]}")
        return source[start:end]
    attempt = Report(report.path)
    migrate_unit(unit, None, attempt, verify)
    restored = _restore(unit.src, fields)
    if restored is None:  # e.g. a field inside a dropped `:effects` clause
        _skip(Unit(text, python=True, line0=unit.line0, col0=col0), report, "fstring-field",
              "an f-string field would be lost; the literal is left as it was")
        report.note(unit.line0, "fstring-field", "an f-string field would be lost or repeated; the literal is left as it was")
        return source[start:end]
    for rows in (attempt.notes, attempt.left):
        rows[:] = [(line, category, _unsentinel(reason, fields)) for line, category, reason in rows]
    report.absorb(attempt)
    return restored


def _unsentinel(text: str, fields: list[str]) -> str:
    for number, field_text in enumerate(fields):
        text = text.replace(FIELD.format(number), field_text)
    return text


def _offsets(source: str):
    """Map an AST (line, UTF-8 column) to a character offset."""
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    return lambda line, col: starts[line - 1] + len(lines[line - 1].encode("utf-8")[:col].decode("utf-8", "replace"))


def _is_text(node: ast.AST) -> bool:
    return isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str))


def _guarded_operands(node: ast.AST):
    """(operand, category, reason) of one node, when the node treats text as a pattern or a value."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in TEXT_METHODS:
        reason = f"operand of `.{node.func.attr}(`"
        return [(operand, "substitution", reason)
                for operand in (node.func.value, *node.args, *(keyword.value for keyword in node.keywords))]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return [(node.left, "substitution", "left side of `%`")]
    if isinstance(node, ast.Compare):
        return [(operand, "comparison", "operand of a comparison") for operand in (node.left, *node.comparators)]
    return [(text, "docstring", "a docstring") for text in _docstring(node)]


def _docstring(node: ast.AST) -> list[ast.AST]:
    if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or not node.body:
        return []
    first = node.body[0]
    return [first.value] if isinstance(first, ast.Expr) and _is_text(first.value) else []


def _text_spans(node: ast.AST, offset) -> list[tuple[int, int]]:
    return [(offset(part.lineno, part.col_offset), offset(part.end_lineno, part.end_col_offset))
            for part in ast.walk(node) if _is_text(part)]


def protected_spans(source: str) -> dict[tuple[int, int], tuple[str, str]]:
    """Character spans of literals the tool must not touch, with (category, reason).

    A literal is protected when it is a guarded operand (`_guarded_operands`) or part of one, or
    assigned to a name that is a guarded operand anywhere in the module.
    """
    tree = ast.parse(source)
    offset = _offsets(source)
    guarded, names = {}, {}
    for node in ast.walk(tree):
        for operand, category, reason in _guarded_operands(node):
            if isinstance(operand, ast.Name):
                names.setdefault(operand.id, (category, f"assigned to `{operand.id}`, an {reason}"))
            guarded.update(dict.fromkeys(_text_spans(operand, offset), (category, reason)))
    for node in ast.walk(tree):
        targets = [target.id for target in getattr(node, "targets", ()) if isinstance(target, ast.Name)]
        for name in (name for name in targets if name in names and isinstance(node, ast.Assign)):
            guarded.update(dict.fromkeys(_text_spans(node.value, offset), names[name]))
    return guarded


def _units(source: str) -> list[list[tuple[int, int]]]:
    """The literal runs that hold `.orc` source; a run with mixed prefixes is split into literals."""
    units = []
    for group in _string_groups(source):
        if not any(marker in source[group[0][0]:group[-1][1]] for marker in ("loop/recur", "(:target-dsl")):
            continue
        prefixes = {_prefix_quote(source[a:b])[0].lower().replace("u", "") for a, b in group}
        units.extend([group] if len(prefixes) == 1 else [[token] for token in group])
    return units


def migrate_python(source: str, report: Report, verify: bool) -> str:
    protected = protected_spans(source)
    out, cursor = [], 0
    for group in _units(source):
        out.append(source[cursor:group[0][0]] + _python_group(source, group, report, verify, protected))
        cursor = group[-1][1]
    out.append(source[cursor:])
    return "".join(out)


Pattern = tuple[str, str]  # (where: "module.py:line", the text a module matches against a fixture)


def text_patterns(paths: list[Path]) -> dict[str, list[Pattern]]:
    """For each `.orc` path literal in a module among `paths`, the module's text patterns.

    A pattern is a string constant of at least three characters with a parenthesis that is directly
    an operand of a text call or a comparison (`_guarded_operands`): Workflow Lisp text a test may
    match against a fixture after reading it. A pattern without a parenthesis (a version, a word,
    a separator) is not one. A module that cannot be read or parsed is skipped here;
    `migrate_file` reports it.
    """
    named = {}
    for path in (path for path in paths if path.suffix == ".py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        patterns = [(f"{path}:{operand.lineno}", operand.value) for node in ast.walk(tree)
                    for operand, category, _ in _guarded_operands(node)
                    if category != "docstring" and _lisp_text(operand)]
        for node in ast.walk(tree) if patterns else ():
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".orc"):
                named.setdefault(node.value.removeprefix("./"), []).extend(patterns)
    return named


def _lisp_text(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) >= 3
            and ("(" in node.value or ")" in node.value))


def _moved_pattern(path: Path, source: str, new: str, named: dict[str, list[Pattern]]) -> str | None:
    """Where a module that names `path` holds a pattern the migration makes match a different number of times."""
    target = "/" + path.resolve().as_posix()
    for suffix, patterns in named.items():
        for where, pattern in patterns if target.endswith("/" + suffix) else ():
            if pattern in source and source.count(pattern) != new.count(pattern):
                return f"{where} matches {pattern!r} against this file's text"
    return None


def migrate_file(path: Path, *, check: bool, verify: bool, patterns: dict[str, list[Pattern]] | None = None) -> Report:
    """Migrate one file; a file that cannot be read, tokenized or parsed is reported and left.

    In a `.orc` file the loops stay in the `fn` form, and are listed, when their rewrite would change
    how often a pattern of a module that names the file (`text_patterns`) occurs in its text: that
    module rewrites or inspects the text, and the two change together by hand. The header and
    clauses are migrated as `migrate2.py` does whatever a module matches.
    """
    report = Report(str(path))
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            source = handle.read()
        new = _migrated(path, source, report, verify, patterns or {})
    except (OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError) as error:
        report.error = f"cannot be migrated ({type(error).__name__}: {error}); left as it was"
        return report
    if new is not None and new != source and not check:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(new)
    return report


def _migrated(path: Path, source: str, report: Report, verify: bool,
              patterns: dict[str, list[Pattern]]) -> str | None:
    if path.suffix != ".py":
        unit = Unit(source)
        migrate_unit(unit, path.resolve(), report, verify,
                     lambda before, after: _moved_pattern(path, before, after, patterns))
        return unit.src
    new = migrate_python(source, report, verify)
    try:
        ast.parse(new)
    except SyntaxError as error:
        report.error = f"the migrated module would not parse ({error.msg}, line {error.lineno}); not written"
        return None
    return new


def _print(reports: list[Report], *, check: bool, verify: bool) -> None:
    verb = "would change" if check else "changed"
    for report in reports:
        if report.changes:
            print(f"{verb} {report.path}: {report.headers} header, {report.lowering} :lowering, "
                  f"{report.effects} :effects, {report.syntactic + report.hashed} loops")
        for line, category, reason in report.left:
            print(f"left in fn form {report.path}:{line}: [{category}] {reason}")
        for line, category, note in report.notes:
            print(f"note {report.path}:{line}: [{category}] {note}")
        if report.error:
            print(f"error {report.path}: {report.error}")
    total = lambda name: sum(getattr(r, name) for r in reports)  # noqa: E731
    print(f"{len(reports)} files, {sum(1 for r in reports if r.changes)} {verb}; loops: {total('loops_found')} found, "
          f"{total('syntactic')} rewritten by the syntactic rule, {total('hashed')} rewritten with equal hash, "
          f"{sum(len(r.left) for r in reports)} left in fn form; {total('kept_indent')} bodies kept their indentation")
    if verify:
        print(f"verify: {total('verified')} syntactic rewrites compiled with equal hash, "
              f"{total('unverifiable')} could not be compiled, {sum(len(r.mismatches) for r in reports)} mismatches")


def write_report(reports: list[Report], target: Path) -> None:
    """The JSON hand-work list for the sweep: changed files and every unit left, with its category."""
    document = {
        "changed": [{"path": r.path, "headers": r.headers, "lowering": r.lowering, "effects": r.effects,
                     "loops": r.syntactic + r.hashed} for r in reports if r.changes and not r.error],
        "hand_work": sorted(
            [{"path": r.path, "line": line, "kind": "loop", "category": category, "reason": reason}
             for r in reports for line, category, reason in r.left]
            + [{"path": r.path, "line": line, "kind": "literal", "category": category, "reason": reason}
               for r in reports for line, category, reason in r.notes]
            + [{"path": r.path, "line": 0, "kind": "file", "category": "error", "reason": r.error}
               for r in reports if r.error],
            key=lambda row: (row["path"], row["line"], row["kind"])),
    }
    target.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")


OWN_FIXTURES = ("tests/test_migrate_orc_sources.py", "tests/test_workflow_lisp_loop_recur_binder.py")


def expand(paths: list[Path]) -> list[Path]:
    """Files named, then the `.orc` and `.py` files below each directory, less OWN_FIXTURES."""
    files = []
    for path in paths:
        if not path.is_dir():
            files.append(path)
            continue
        for found in sorted(path.rglob("*")):
            parts = found.relative_to(path).parts
            hidden = any(part.startswith(".") or part == "__pycache__" for part in parts)
            own = any(found.resolve().as_posix().endswith("/" + fixture) for fixture in OWN_FIXTURES)
            if found.suffix in {".orc", ".py"} and found.is_file() and not hidden and not own:
                files.append(found)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=f"A directory skips {' and '.join(OWN_FIXTURES)}: they hold this tool's and the binder "
               "tests' fn-form fixtures. Name one as a file to migrate it; a file list such as "
               "`git ls-files` output names them, so leave them out of it.")
    parser.add_argument("--check", action="store_true", help="report what would change; write nothing")
    parser.add_argument("--verify", action="store_true", help="also compile syntactic rewrites and compare hashes")
    parser.add_argument("--report", type=Path, help="write the changed files and the hand work as JSON")
    parser.add_argument("paths", nargs="+", type=Path, help="files, or directories to walk")
    args = parser.parse_args(argv)
    files = expand(args.paths)
    patterns = text_patterns(files)
    reports = [migrate_file(path, check=args.check, verify=args.verify, patterns=patterns) for path in files]
    _print(reports, check=args.check, verify=args.verify)
    if args.report is not None:
        write_report(reports, args.report)
    if any(r.error for r in reports) or any(r.mismatches for r in reports):
        return 2
    return 1 if args.check and any(r.changes for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
