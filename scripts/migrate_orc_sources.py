"""Migrate Workflow Lisp sources to target 2.40 and to the binder form of `loop/recur`.

usage: python scripts/migrate_orc_sources.py [--check] FILE...

One pass over each named file, for `.orc` files and for `.orc` source held in Python string
literals (a string that contains `(:target-dsl` or `loop/recur`):

1. Header and clauses (the stage 4 one-target plan): a literal `(:target-dsl "2.35")` to `"2.39"`
   becomes `"2.40"`; every `:lowering inline|private-workflow|auto` clause goes; below 2.39 every
   `:effects (...)` clause goes, with its line when it had the line to itself.
2. Loops (surface coherence design, section 5): each `(loop/recur ... :state init ... (fn (s) body))`
   becomes `(loop/recur ((s init)) ... body)`. After rewriting one loop the source is compiled
   again; the rewrite stays only when every workflow of the source builds before and after and
   each keeps its program hash (normalized as the stage 4 plan defines: `target` replaced, every `@`
   provenance object removed). Otherwise the loop stays in the `fn` form and is listed with the
   reason. Python strings that are f-strings, that hold escape sequences or whose header is a
   parameter such as `{TARGET}` are skipped and listed.

Text outside the rewritten forms, comments included, is kept byte for byte. A second run changes
nothing. `--check` writes nothing, reports what it would change, and exits 1 if anything would.

Dependencies: the repository's own reader and compiler (`orchestrator.workflow_lisp`), so run it
from the repository root with the tree to migrate on `PYTHONPATH`. Commands, providers and
prompts are made up from the source, as the stage 4 plan's `classify.py` does; a source whose
workflows do not build that way keeps its loops in the `fn` form.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tokenize

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, SymbolAtom

OLD_HEADER = re.compile(r'\(:target-dsl\s+"(2\.3[5-9])"\)')
ANY_HEADER = re.compile(r'\(:target-dsl\s+"([^"]*)"\)')
LOWERING = re.compile(r"[ \t]*:lowering\s+(inline|private-workflow|auto)\b")
FN_LOOP_TEXT = re.compile(r"\(loop/recur(?!\s*\(\()")


@dataclass
class Report:
    """What one file's migration did or would do."""

    path: str
    headers: int = 0
    lowering: int = 0
    effects: int = 0
    loops_found: int = 0
    loops_rewritten: int = 0
    left: list[tuple[int, str]] = field(default_factory=list)  # (line, reason)

    @property
    def changes(self) -> int:
        return self.headers + self.lowering + self.effects + self.loops_rewritten


# --- 1. header and clauses (`migrate2.py` of the stage 4 plan) -------------------------------

def _cut(text: str, start: int, end: int) -> str:
    """Remove `text[start:end]`, and the rest of its line when the clause had the line to itself."""
    rest = re.match(r"[ \t]*\n", text[end:])
    if (start == 0 or text[start - 1] == "\n") and rest is not None:
        end += rest.end()
    return text[:start] + text[end:]


def _drop_lowering(text: str) -> tuple[str, int]:
    matches = list(LOWERING.finditer(text))
    for match in reversed(matches):
        text = _cut(text, match.start(), match.end())
    return text, len(matches)


def _drop_effects(text: str) -> tuple[str, int]:
    count = 0
    while (match := re.search(r"[ \t]*:effects\s*\(", text)) is not None:
        cursor, depth = match.end(), 1
        while depth:
            depth += {"(": 1, ")": -1}.get(text[cursor], 0)
            cursor += 1
        text, count = _cut(text, match.start(), cursor), count + 1
    return text, count


def migrate_header(text: str, report: Report) -> str:
    """Retarget a 2.35-2.39 source to 2.40 and drop the clauses 2.40 refuses."""
    match = OLD_HEADER.search(text)
    if match is None:
        return text
    text = text[:match.start()] + '(:target-dsl "2.40")' + text[match.end():]
    text, lowering = _drop_lowering(text)
    effects = 0
    if match.group(1) != "2.39":
        text, effects = _drop_effects(text)
    report.headers += 1
    report.lowering += lowering
    report.effects += effects
    return text


# --- 2. loops ----------------------------------------------------------------------------------

def _is_symbol(node: object, value: str) -> bool:
    return isinstance(node, SymbolAtom) and node.value == value


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
    if [key.value for key in keys].count(":state") != 1:
        return "the loop has no single `:state`"
    return None


def fn_loops(text: str) -> list[ListExpr]:
    """Every `(loop/recur ... (fn ...))` list of the source, in document order."""
    found: list[ListExpr] = []

    def walk(node: object) -> None:
        if not isinstance(node, ListExpr):
            return
        items = node.items
        if (len(items) > 1 and _is_symbol(items[0], "loop/recur") and isinstance(items[-1], ListExpr)
                and items[-1].items and _is_symbol(items[-1].items[0], "fn")):
            found.append(node)
        for item in items:
            walk(item)

    walk(read_sexpr_text(text, source_path="<migrate>"))
    return found


def _start(node: object) -> int:
    return node.span.start.offset


def _end(node: object) -> int:
    return node.span.end.offset


def rewrite_loop(text: str, node: ListExpr) -> str:
    """Rewrite one `fn`-form loop to the binder form, editing only the loop's own parts."""
    head, fn = node.items[0], node.items[-1]
    params, body = fn.items[1], fn.items[2]
    index = next(i for i, item in enumerate(node.items) if isinstance(item, KeywordAtom) and item.value == ":state")
    key, value = node.items[index], node.items[index + 1]
    binder = f" (({text[_start(params.items[0]):_end(params.items[0])]} {text[_start(value):_end(value)]}))"
    cut_start = max(_end(node.items[index - 1]), len(text[:_start(key)].rstrip()))
    trailing = text[_end(body):_end(fn) - 1]
    new_body = text[_end(params):_end(body)].lstrip() + (trailing if ";" in trailing else "")
    edits = sorted(
        [(_end(head), _end(head), binder), (cut_start, _end(value), ""), (_start(fn), _end(fn), new_body)],
        reverse=True,
    )
    for start, end, replacement in edits:
        text = text[:start] + replacement + text[end:]
    return text


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


def _module_root(path: Path, source: str) -> Path:
    match = re.search(r"\(defmodule\s+([^\s)]+)", source)
    if match is None:
        return path.parent
    parts = match.group(1).split("/")
    owner = path.parents[len(parts) - 1]
    return owner if owner / Path(*parts).with_suffix(".orc") == path else path.parent


def _graph_source(path: Path, root: Path, seen: set[Path], text: str | None = None) -> str:
    if path in seen or (text is None and not path.is_file()):
        return ""
    seen.add(path)
    source = path.read_text(encoding="utf-8") if text is None else text
    for match in re.finditer(r"\(import\s+([^\s)]+)", source):
        source += _graph_source(root / (match.group(1) + ".orc"), root, seen)
    return source


def _entries(source: str) -> list[str]:
    defined = re.findall(r"\(defworkflow\s+([^\s()]+)", source)
    exported = [name for clause in re.findall(r"\(export\s+([^)]*)\)", source) for name in clause.split()]
    return [name for name in exported if name in defined] or defined


@contextmanager
def _overlay(path: Path, text: str):
    """Let the compiler read `text` as the bytes of `path`, without writing the file."""
    original = Path.read_bytes
    target = os.path.realpath(path)

    def read_bytes(self: Path) -> bytes:
        return text.encode("utf-8") if os.path.realpath(self) == target else original(self)

    Path.read_bytes = read_bytes
    try:
        yield
    finally:
        Path.read_bytes = original


def program_outcomes(path: Path, text: str) -> dict[str, str]:
    """Each workflow of the source: `built:<normalized hash>` or `refused:<first code>`."""
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    root = _module_root(path, text)
    providers, prompts, commands = _externs(_graph_source(path, root, set(), text))
    outcomes = {}
    with _overlay(path, text):
        for entry in _entries(text):
            try:
                typed = compile_typed_program(
                    path, entry_workflow=entry, source_roots=(root,), workspace_root=root,
                    command_boundaries=commands, provider_externs=providers, prompt_externs=prompts)
                outcomes[entry] = "built:" + normalized_hash(build_closed_program(typed).tree)
            except LispFrontendCompileError as error:
                outcomes[entry] = "refused:" + error.diagnostics[0].code
            except Exception as error:  # a compiler defect is an outcome to report, not a crash of the tool
                outcomes[entry] = f"crash:{type(error).__name__}"
    return outcomes


def _unbuildable(outcomes: dict[str, str]) -> str | None:
    if not outcomes:
        return "no workflow to compare the program hash on"
    refused = sorted(f"{entry} {outcome}" for entry, outcome in outcomes.items() if not outcome.startswith("built:"))
    return f"does not build, so the hash cannot be compared ({'; '.join(refused)})" if refused else None


def migrate_loops(text: str, path: Path, report: Report, line_base: int) -> str:
    """Rewrite each `fn`-form loop whose rewrite keeps every program hash; list the others."""
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    try:
        loops = fn_loops(text)
    except LispFrontendCompileError as error:
        _skip(text, report, line_base, f"the reader refuses the source ({error.diagnostics[0].code})")
        return text
    report.loops_found += len(loops)
    if not loops:
        return text
    baseline = program_outcomes(path, text)
    blocked = _unbuildable(baseline)
    cursor = len(text) + 1
    # Last loop first: an edit only moves text after its own start, so every loop still to be
    # visited keeps its offset and its line.
    while (pending := [node for node in fn_loops(text) if _start(node) < cursor]):
        node = pending[-1]
        cursor = _start(node)
        line = line_base + node.span.start.line - 1
        reason = blocked or _fn_loop_problem(node)
        if reason is None:
            candidate = rewrite_loop(text, node)
            if program_outcomes(path, candidate) == baseline:
                text = candidate
                report.loops_rewritten += 1
                continue
            reason = "the program hash changes (an effect in both `:max` and `:state`?)"
        report.left.append((line, reason))
    return text


def migrate_source(text: str, path: Path, report: Report, line_base: int = 1) -> str:
    header = ANY_HEADER.search(text)
    if header is not None and not re.fullmatch(r"\d+\.\d+", header.group(1)):
        _skip(text, report, line_base, f"parameterized header `{header.group(1)}`")
        return text
    text = migrate_header(text, report)
    if header is None:
        _skip(text, report, line_base, "no `:target-dsl` header, so not a whole program")
        return text
    return migrate_loops(text, path, report, line_base)


def _skip(text: str, report: Report, line_base: int, reason: str) -> None:
    for match in FN_LOOP_TEXT.finditer(text):
        report.loops_found += 1
        report.left.append((line_base + text.count("\n", 0, match.start()), reason))


# --- files -------------------------------------------------------------------------------------

def _string_tokens(source: str):
    """(start offset, end offset, token text, is f-string) of each string literal."""
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    offset = lambda position: starts[position[0] - 1] + position[1]  # noqa: E731
    fstring_start, depth = None, 0
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING:
            yield offset(token.start), offset(token.end), token.string, "f" in token.string[:2].lower()
        elif token.type == getattr(tokenize, "FSTRING_START", None):
            fstring_start = offset(token.start) if depth == 0 else fstring_start
            depth += 1
        elif token.type == getattr(tokenize, "FSTRING_END", None):
            depth -= 1
            if depth == 0:
                yield fstring_start, offset(token.end), source[fstring_start:offset(token.end)], True


def _string_body(token: str) -> tuple[int, int, str | None]:
    """Offsets of the literal's body inside the token, and why it cannot be edited, if so."""
    prefix = re.match(r"[rRbBuUfF]*", token).group()
    quote = token[len(prefix):len(prefix) + 3] if token[len(prefix):len(prefix) + 3] in {'"""', "'''"} else token[len(prefix)]
    start, end = len(prefix) + len(quote), len(token) - len(quote)
    if "f" in prefix.lower():
        return start, end, "inside an f-string"
    if "b" in prefix.lower():
        return start, end, "inside a bytes literal"
    if "r" not in prefix.lower() and "\\" in token[start:end]:
        return start, end, "the Python string holds escape sequences"
    return start, end, None


def migrate_python(source: str, report: Report) -> str:
    out, cursor = [], 0
    for start, end, token, _fstring in _string_tokens(source):
        if "loop/recur" not in token and "(:target-dsl" not in token:
            continue
        body_start, body_end, problem = _string_body(token)
        line_base = source.count("\n", 0, start + body_start) + 1
        body = token[body_start:body_end]
        if problem is not None:
            _skip(body, report, line_base, problem)
            continue
        with tempfile.TemporaryDirectory(prefix="migrate-orc-") as scratch:
            module = re.search(r"\(defmodule\s+([^\s)]+)\)", body)
            unit_path = Path(scratch, *(module.group(1).split("/") if module else ["entry"])).with_suffix(".orc")
            unit_path.parent.mkdir(parents=True, exist_ok=True)
            unit_path.write_text(body, encoding="utf-8")
            new_body = migrate_source(body, unit_path, report, line_base)
        out.append(source[cursor:start] + token[:body_start] + new_body + token[body_end:])
        cursor = end
    out.append(source[cursor:])
    return "".join(out)


def migrate_file(path: Path, *, check: bool) -> Report:
    report = Report(str(path))
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        new = migrate_python(source, report)
    else:
        new = migrate_source(source, path.resolve(), report)
    if new != source and not check:
        path.write_text(new, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report what would change; write nothing")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    reports = [migrate_file(path, check=args.check) for path in args.files]
    verb = "would change" if args.check else "changed"
    for report in reports:
        if report.changes:
            print(f"{verb} {report.path}: {report.headers} header, {report.lowering} :lowering, "
                  f"{report.effects} :effects, {report.loops_rewritten} loops")
        for line, reason in report.left:
            print(f"left in fn form {report.path}:{line}: {reason}")
    found, rewritten = sum(r.loops_found for r in reports), sum(r.loops_rewritten for r in reports)
    print(f"{len(reports)} files, {sum(1 for r in reports if r.changes)} {verb}; loops: {found} found, "
          f"{rewritten} rewritten with equal hash, {sum(len(r.left) for r in reports)} left in fn form")
    return 1 if args.check and any(r.changes for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
