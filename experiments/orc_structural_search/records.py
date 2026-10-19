"""Append-only JSONL records, skeleton hashing, control-flow head counts and the final-choice rule.

Design: docs/design/orc_structural_search_driver.md ("Search Modes" for the
skeleton hash, "Objective, Selection And Local Observations" for the
final-choice rule, "Records" for the log).

Dependencies: the Workflow Lisp reader (`read_sexpr_text`) for authored
source, `ast` for an I3 candidate's Python module; the filesystem for the
log. No other state.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import (
    BoolAtom,
    KeywordAtom,
    ListExpr,
    SExpr,
    SymbolAtom,
)

UNAVAILABLE = "unavailable"
_DEFINITION_HEADS = {"defworkflow", "defproc", "defun"}
_TYPE_HEADS = {"defrecord", "defunion", "defenum"}
_PROMPT_HEAD = "defprompt"  # a named prompt is found but contributes nothing to the skeleton or allocation
_LITERAL_KEYWORDS = {":model", ":effort"}
_PROVIDER_PREFIX = "providers."
CONTROL_HEADS = ("if", "cond", "match", "loop/recur", "list/map-effect")
_PROVIDERS_NAME = "PROVIDERS"  # an I3 module's role -> provider adapter mapping
_PROMPT_SUFFIX = "_PROMPT"  # an I3 module's prompt constants


def append_record(log: Path, record: Mapping[str, object]) -> None:
    """Append `record` to `log` as one JSON line with sorted keys.

    Missing receipts are the caller's string "unavailable" and are written
    verbatim; nothing here substitutes zero.
    """

    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")


def read_records(log: Path) -> list[dict]:
    """Return every record in `log`, in append order."""

    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def skeleton_hash(source: str, *, definitions: Sequence[str]) -> str:
    """Return the sha256 of the normalized named definitions in `source`.

    Binders (see `_Normalizer`; definition parameters included) and their
    references become per-definition ordinals `$0`, `$1`...;
    string and numeric literals and `:model`/`:effort` values become `#lit`;
    a `:prompt` name (bare, or the head of a prompt call whose fill keywords
    and values are kept) becomes `#prompt`; `providers.*` externs become
    `#provider`. Form heads, keywords and arity are kept. A named `defprompt`
    contributes nothing, so a prompt-only child hashes equal to its parent.
    Raises ValueError when a named definition is absent.
    """

    canonical = "\n".join(_normalize_definition(d) for d in _named_definitions(source, definitions))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def provider_allocation(source: str, *, definitions: Sequence[str]) -> dict[str, list[str]]:
    """Return, per named non-prompt definition, the `providers.*` externs it
    names in source order (the role allocation the skeleton hash masks).
    Raises ValueError when a named definition is absent."""

    return {d.items[1].value: _provider_externs(d) for d in _named_definitions(source, definitions)}


def control_heads(source: str, *, definitions: Sequence[str]) -> dict[str, int]:
    """Return how many forms of each `CONTROL_HEADS` head the named non-prompt
    definitions of `source` contain (zero included). Raises ValueError when a
    named definition is absent."""

    counts = dict.fromkeys(CONTROL_HEADS, 0)
    pending: list[SExpr] = list(_named_definitions(source, definitions))
    while pending:
        expr = pending.pop()
        if isinstance(expr, ListExpr):
            head = expr.items[0] if expr.items else None
            if isinstance(head, SymbolAtom) and head.value in counts:
                counts[head.value] += 1
            pending += expr.items
    return counts


def _named_definitions(source: str, definitions: Sequence[str]) -> list[ListExpr]:
    """The named definitions of `source` in `definitions` order, prompts left out."""

    found: dict[str, ListExpr] = {}
    _collect_definitions(read_sexpr_text(source, source_path="<skeleton>"), found)
    missing = [name for name in definitions if name not in found]
    if missing:
        raise ValueError(f"definitions not found in source: {missing}")
    return [found[name] for name in definitions if found[name].items[0].value != _PROMPT_HEAD]


def _provider_externs(expr: SExpr) -> list[str]:
    if isinstance(expr, ListExpr):
        return [name for item in expr.items for name in _provider_externs(item)]
    if isinstance(expr, SymbolAtom) and expr.value.startswith(_PROVIDER_PREFIX):
        return [expr.value]
    return []


def _collect_definitions(expr: SExpr, found: dict[str, ListExpr]) -> None:
    if not isinstance(expr, ListExpr):
        return
    items = expr.items
    if (
        len(items) >= 2
        and isinstance(items[0], SymbolAtom)
        and items[0].value in _DEFINITION_HEADS | _TYPE_HEADS | {_PROMPT_HEAD}
        and isinstance(items[1], SymbolAtom)
    ):
        found[items[1].value] = expr
        return
    for item in items:
        _collect_definitions(item, found)


class _Normalizer:
    """Render one definition with scope-ordinal placeholders.

    Binding forms: `let*` (sequential); `list/map`, `list/map-effect`,
    `with-live-providers`, `with-live-provider-peers` (initializers in the
    outer scope); `fn` parameters; `let-proc` names and parameters; `match`
    arm names. Every other list keeps its head and arity.
    """

    def __init__(self) -> None:
        self._next = 0

    def bind(self, name: str, scope: dict[str, str]) -> dict[str, str]:
        placeholder = f"${self._next}"
        self._next += 1
        return {**scope, name: placeholder}

    def bind_params(self, params: SExpr, scope: dict[str, str]) -> tuple[str, dict[str, str]]:
        """Bind `(p ...)` or `((p Type) ...)`; return the rendered list and the scope."""

        rendered = []
        for param in params.items if isinstance(params, ListExpr) else ():
            name = _binder_name(param)
            if name is None:
                rendered.append(self.render(param, {}))
                continue
            scope = self.bind(name, scope)
            rest = [self.render(item, {}) for item in param.items[1:]] if isinstance(param, ListExpr) else []
            rendered.append(_wrap([scope[name], *rest]) if isinstance(param, ListExpr) else scope[name])
        return _wrap(rendered), scope

    def render(self, expr: SExpr, scope: dict[str, str]) -> str:
        if isinstance(expr, ListExpr):
            return self._render_list(expr, scope)
        if isinstance(expr, SymbolAtom):
            return _render_symbol(expr.value, scope)
        if isinstance(expr, KeywordAtom):
            return expr.value
        if isinstance(expr, BoolAtom):
            return "true" if expr.value else "false"
        return "#lit"  # string, int and float literals

    def _render_list(self, expr: ListExpr, scope: dict[str, str]) -> str:
        items = expr.items
        head = items[0].value if items and isinstance(items[0], SymbolAtom) else None
        has_bindings = len(items) >= 2 and isinstance(items[1], ListExpr)
        rendered = self._render_binding_form(head, items, scope) if has_bindings else None
        if rendered is not None:
            return rendered
        if head == "match" and len(items) >= 2:
            return self._render_match(items, scope)
        return self._render_items(items, scope)

    def _render_binding_form(self, head: str | None, items: Sequence[SExpr], scope: dict[str, str]) -> str | None:
        """A binding form (its second item a list), or None when `head` binds nothing."""

        if head == "let*":
            return self._render_bindings(items, scope, sequential=True)
        if head in _PARALLEL_BINDING_HEADS:
            return self._render_bindings(items, scope, sequential=False)
        if head == "fn":
            params, inner = self.bind_params(items[1], scope)
            return _wrap(["fn", params, *self._render_all(items[2:], inner)])
        if head == "let-proc":
            return self._render_let_proc(items, scope)
        return None

    def _render_all(self, items: Sequence[SExpr], scope: dict[str, str]) -> list[str]:
        return [self.render(item, scope) for item in items]

    def _render_items(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        parts = []
        previous = None
        for item in items:
            if previous == ":prompt":
                parts.append(self._render_prompt(item, scope))
            elif previous in _LITERAL_KEYWORDS:
                parts.append("#lit")
            else:
                parts.append(self.render(item, scope))
            previous = item.value if isinstance(item, KeywordAtom) else None
        return _wrap(parts)

    def _render_prompt(self, expr: SExpr, scope: dict[str, str]) -> str:
        """Mark the prompt name; keep a prompt call's fill keywords and values."""

        if isinstance(expr, ListExpr) and expr.items:
            return _wrap(["#prompt", *self._render_all(expr.items[1:], scope)])
        return "#prompt"

    def _render_bindings(self, items: Sequence[SExpr], scope: dict[str, str], *, sequential: bool) -> str:
        """Render `(head ((name init rest...) ...) body...)`.

        Sequential: each initializer sees earlier names. Otherwise every
        initializer sees the outer scope and `rest` (`:observes x`) and the
        body see all names.
        """

        outer = scope
        bound: list[tuple[ListExpr | None, list[str]]] = []
        for binding in items[1].items:
            if not (isinstance(binding, ListExpr) and _binder_name(binding)):
                bound.append((None, [self.render(binding, scope)]))
                continue
            init = self._render_all(binding.items[1:2], scope if sequential else outer)
            scope = self.bind(binding.items[0].value, scope)
            bound.append((binding, [scope[binding.items[0].value], *init]))
        rendered = [
            parts[0] if binding is None else _wrap([*parts, *self._render_all(binding.items[2:], scope)])
            for binding, parts in bound
        ]
        return _wrap([items[0].value, _wrap(rendered), *self._render_all(items[2:], scope)])

    def _render_let_proc(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        """`(let-proc ((name (params) body...) ...) body...)`: names see each other."""

        procs = [proc for proc in items[1].items if isinstance(proc, ListExpr) and len(proc.items) >= 2 and _binder_name(proc)]
        for proc in procs:
            scope = self.bind(proc.items[0].value, scope)
        rendered = []
        for proc in items[1].items:
            if proc not in procs:
                rendered.append(self.render(proc, scope))
                continue
            params, inner = self.bind_params(proc.items[1], scope)
            rendered.append(_wrap([scope[proc.items[0].value], params, *self._render_all(proc.items[2:], inner)]))
        return _wrap(["let-proc", _wrap(rendered), *self._render_all(items[2:], scope)])

    def _render_match(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        parts = ["match", self.render(items[1], scope)]
        for arm in items[2:]:
            pattern = arm.items[0] if isinstance(arm, ListExpr) and arm.items else None
            if not (isinstance(pattern, ListExpr) and len(pattern.items) == 2 and isinstance(pattern.items[1], SymbolAtom)):
                parts.append(self.render(arm, scope))
                continue
            arm_scope = self.bind(pattern.items[1].value, scope)
            rendered_pattern = _wrap([self.render(pattern.items[0], scope), arm_scope[pattern.items[1].value]])
            parts.append(_wrap([rendered_pattern, *self._render_all(arm.items[1:], arm_scope)]))
        return _wrap(parts)


_PARALLEL_BINDING_HEADS = {"list/map", "list/map-effect", "with-live-providers", "with-live-provider-peers"}


def _binder_name(expr: SExpr) -> str | None:
    """Return the name a binder item introduces: `name` or `(name ...)`."""

    if isinstance(expr, SymbolAtom):
        return expr.value
    if isinstance(expr, ListExpr) and expr.items and isinstance(expr.items[0], SymbolAtom):
        return expr.items[0].value
    return None


def _wrap(parts: Sequence[str]) -> str:
    return "(" + " ".join(parts) + ")"


def _render_symbol(value: str, scope: dict[str, str]) -> str:
    if value.startswith(_PROVIDER_PREFIX):
        return "#provider"
    root, dot, rest = value.partition(".")
    return scope[root] + dot + rest if root in scope else value


def _normalize_definition(definition: ListExpr) -> str:
    """Render `(defworkflow|defproc|defun name ((param Type) ...) ...)` canonically."""

    normalizer = _Normalizer()
    items = definition.items
    if items[0].value in _TYPE_HEADS:
        return normalizer.render(definition, {})
    head = normalizer._render_all(items[:2], {})
    if len(items) < 3 or not isinstance(items[2], ListExpr):
        return _wrap([*head, *normalizer._render_all(items[2:], {})])
    params, scope = normalizer.bind_params(items[2], {})
    return _wrap([*head, params, *normalizer._render_all(items[3:], scope)])


def python_skeleton_hash(source: str, *, definitions: Sequence[str]) -> str:
    """Return the sha256 of the normalized named top-level functions of the
    Python module `source` (I3).

    Names bound inside a function (parameters; assignment, `for`,
    comprehension and `with ... as` targets; `except ... as` names; nested
    function and class names) and their references become per-function
    ordinals `$0`, `$1`... in first-binding order. Other names are kept,
    except `PROVIDERS` and its subscripts (`#provider`) and prompt constants,
    names ending `_PROMPT` (`#prompt`). Every constant becomes `#lit`;
    docstrings are dropped; attribute names, calls, keywords, operators and
    statement kinds are kept. The functions' canonical `ast.dump` is hashed.
    Raises ValueError when a named function is absent.
    """

    canonical = "\n".join(ast.dump(_PythonSkeleton(f).visit(f)) for f in _python_functions(source, definitions))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def python_provider_allocation(source: str, *, definitions: Sequence[str]) -> dict[str, list[str]]:
    """Return, per named top-level function of the Python module `source`,
    the provider keys its `PROVIDERS["..."]` subscripts name, in source order.
    Raises ValueError when a named function is absent."""

    return {f.name: [key for node in _preorder(f) if (key := _provider_key(node))]
            for f in _python_functions(source, definitions)}


def python_program_digest(source: str) -> str:
    """Return "sha256:" over the `ast.dump` of the whole Python module
    `source`: comments and formatting leave it unchanged, a rename does not."""

    return "sha256:" + hashlib.sha256(ast.dump(ast.parse(source)).encode("utf-8")).hexdigest()


def _python_functions(source: str, definitions: Sequence[str]) -> list[ast.FunctionDef]:
    """The first top-level function of each name in `definitions`, in that order."""

    found: dict[str, ast.FunctionDef] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            found.setdefault(node.name, node)
    missing = [name for name in definitions if name not in found]
    if missing:
        raise ValueError(f"definitions not found in source: {missing}")
    return [found[name] for name in definitions]


def _preorder(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _preorder(child)


def _provider_key(node: ast.AST) -> str | None:
    """The key of a `PROVIDERS["key"]` subscript, else None."""

    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == _PROVIDERS_NAME
            and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
        return node.slice.value
    return None


def _python_binders(node: ast.AST, function: ast.FunctionDef) -> list[str]:
    """The names `node` binds inside `function` (its own name excluded)."""

    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return [node.id]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not function:
        return [node.name]
    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]
    return []


class _PythonSkeleton(ast.NodeTransformer):
    """Normalize one top-level function in place (see `python_skeleton_hash`)."""

    def __init__(self, function: ast.FunctionDef) -> None:
        self.function = function
        self.local: dict[str, str] = {}
        for node in _preorder(function):
            for name in _python_binders(node, function):
                self.local.setdefault(name, f"${len(self.local)}")

    def _name(self, name: str) -> str:
        if name in self.local:
            return self.local[name]
        if name == _PROVIDERS_NAME:
            return "#provider"
        return "#prompt" if name.endswith(_PROMPT_SUFFIX) else name

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.Name(self._name(node.id), node.ctx)

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        if isinstance(node.value, ast.Name) and self._name(node.value.id) == "#provider":
            return ast.Name("#provider", node.ctx)
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.Constant("#lit")

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self.local[node.arg]
        return self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        if node.name:
            node.name = self.local[node.name]
        return self.generic_visit(node)

    def _visit_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> ast.AST:
        if ast.get_docstring(node, clean=False) is not None:
            node.body = node.body[1:]
        if node is not self.function:
            node.name = self.local[node.name]
        return self.generic_visit(node)

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _visit_scope


def final_choice(rows: Sequence[Mapping], *, criterion: Mapping) -> str:
    """Return the `candidate_id` the frozen criterion selects among `rows`.

    `mean_cost_ceiling` must be numeric; rows above it, and rows whose cost is
    "unavailable", are excluded. Among the
    rest: rows within `equivalence_tolerance` of the best
    `validation_success`, then lower `mean_cost`, fewer `provider_calls`,
    lexically earlier `candidate_id`. The reference seed competes like any row.
    """

    if not criterion.get("criterion_sha256"):
        raise ValueError("criterion_sha256 required")
    if not any(row["is_reference"] for row in rows):
        raise ValueError("reference seed missing")
    ceiling = criterion["mean_cost_ceiling"]
    if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)):
        raise ValueError("mean_cost_ceiling must be numeric")
    eligible = [row for row in rows if _under_ceiling(row["mean_cost"], ceiling)]
    if not eligible:
        raise ValueError(f"no candidate under mean_cost_ceiling {ceiling!r}")
    best = max(row["validation_success"] for row in eligible)
    tied = [row for row in eligible if row["validation_success"] >= best - criterion["equivalence_tolerance"]]
    return min(tied, key=_tie_key)["candidate_id"]


def _under_ceiling(cost: float | str, ceiling: float) -> bool:
    return cost != UNAVAILABLE and cost <= ceiling


def _tie_key(row: Mapping) -> tuple:
    return (row["mean_cost"], row["provider_calls"], row["candidate_id"])
