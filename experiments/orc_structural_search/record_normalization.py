"""Canonical Workflow Lisp source metrics for structural search records."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.type_expressions import (
    parse_type_expression,
    type_expression_application_heads,
    type_expression_names,
)
from orchestrator.workflow_lisp.sexpr import (
    BoolAtom,
    KeywordAtom,
    ListExpr,
    SExpr,
    SymbolAtom,
)

_DEFINITION_HEADS = {"defworkflow", "defproc", "defun"}
_TYPE_HEADS = {"defrecord", "defunion", "defenum"}
_PROMPT_HEAD = "defprompt"
_LITERAL_KEYWORDS = {":model", ":effort"}
_PROVIDER_PREFIX = "providers."
CONTROL_HEADS = ("if", "cond", "match", "loop/recur", "list/map-effect")


def _head_name(items: Sequence[SExpr]) -> str | None:
    return items[0].value if items and isinstance(items[0], SymbolAtom) else None


def _definition_names_by_kind(definitions: Sequence[ListExpr]) -> tuple[set[str], set[str], set[str]]:
    types, calls, enums = set(), set(), set()
    for definition in definitions:
        head, name = definition.items[0].value, definition.items[1].value
        if head in _TYPE_HEADS:
            types.add(name)
        if head in _DEFINITION_HEADS:
            calls.add(name)
        if head == "defenum":
            enums.add(name)
    return types, calls, enums


def _ordinal_names(names: dict[str, str], definitions: set[str]) -> dict[str, str]:
    return {name: value for name, value in names.items() if name.rsplit("/", 1)[-1] in definitions}


def skeleton_hash(source: str, *, definitions: Sequence[str], module_entry: str | None = None) -> str:
    """Return the sha256 of the normalized named definitions in `source`.

    Binders (see `_Normalizer`; definition parameters included) and their
    references become per-definition ordinals `$0`, `$1`...;
    string and numeric literals and `:model`/`:effort` values become `#lit`;
    a `:prompt` name (bare, or the head of a prompt call whose fill keywords
    and values are kept) becomes `#prompt`; `providers.*` externs become
    `#provider`. Form heads, keywords and arity are kept. A named `defprompt`
    contributes nothing, so a prompt-only child hashes equal to its parent.
    With `module_entry` (optionally module::entry), private declarations and
    their references share ordinals in selection order; field/variant/member
    labels stay authored. This recognizes consistent order-preserving renames,
    not declaration reordering or semantic equivalence.
    Raises ValueError when a named definition is absent.
    """

    selected = _named_definitions(source, definitions)
    names = _module_names(selected, module_entry) if module_entry is not None else None
    canonical = "\n".join(_ModuleNormalizer(selected, names).definition(d) if names is not None
                          else _normalize_definition(d) for d in selected)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def provider_allocation(source: str, *, definitions: Sequence[str], module_entry: str | None = None) -> dict[str, list[str]]:
    """Return, per named non-prompt definition, the `providers.*` externs it
    names in source order (the role allocation the skeleton hash masks).
    `module_entry` uses the same private declaration keys as `skeleton_hash`.
    Raises ValueError when a named definition is absent."""

    selected = _named_definitions(source, definitions)
    names = _module_names(selected, module_entry) if module_entry is not None else {}
    return {names.get(d.items[1].value, d.items[1].value): _provider_externs(d) for d in selected}


def _module_names(definitions: Sequence[ListExpr], entry: str) -> dict[str, str]:
    """Prompts are already excluded, so adding one cannot shift declaration IDs."""
    module, _, entry_name = entry.rpartition("::")
    private = [d.items[1].value for d in definitions if d.items[1].value != entry_name]
    names = {name: f"$decl{i}" for i, name in enumerate(private)}
    return {**names, **{f"{module}/{name}": ordinal for name, ordinal in names.items()}} if module else names


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
        head = _head_name(items)
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


class _ModuleNormalizer(_Normalizer):
    """Module references have distinct value, type and literal-label positions."""

    def __init__(self, definitions: Sequence[ListExpr], names: dict[str, str]) -> None:
        super().__init__()
        self.names = names
        self.local_procs: dict[str, str] = {}
        types, calls, enums = _definition_names_by_kind(definitions)
        self.types = _ordinal_names(names, types)
        self.calls = _ordinal_names(names, calls)
        self.enums = _ordinal_names(self.types, enums)

    def _type(self, expr: SExpr) -> str:
        if isinstance(expr, ListExpr) and len(expr.items) >= 2 and isinstance(expr.items[0], SymbolAtom) and expr.items[0].value == "result":
            return _wrap(["result", self._type(expr.items[1]), *self._render_all(expr.items[2:], {})])
        if not isinstance(expr, SymbolAtom):
            return self.render(expr, {})
        parsed = parse_type_expression(expr.value, span=expr.span, form_path=())
        referenced = type_expression_names(parsed) | frozenset(type_expression_application_heads(parsed))
        names = {name: self.types.get(name, name) for name in referenced}
        return re.sub(r"->|(?:[^\s\[\](),-]|-(?!>))+", lambda match: names.get(match[0], match[0]), expr.value)

    def bind_params(self, params: SExpr, scope: dict[str, str]) -> tuple[str, dict[str, str]]:
        rendered = []
        for param in params.items if isinstance(params, ListExpr) else ():
            name = _binder_name(param)
            if name is None:
                rendered.append(self.render(param, {}))
                continue
            scope = self.bind(name, scope)
            rest = [self._type(item) for item in param.items[1:]] if isinstance(param, ListExpr) else []
            rendered.append(_wrap([scope[name], *rest]) if isinstance(param, ListExpr) else scope[name])
        return _wrap(rendered), scope

    def definition(self, definition: ListExpr) -> str:
        items = definition.items
        head, name = items[0].value, items[1].value
        parts = [head, self.names.get(name, name)]
        index = 2
        if index < len(items) and isinstance(items[index], KeywordAtom) and items[index].value == ":forall":
            params = items[index + 1]
            bound = []
            for i, param in enumerate(params.items):
                self.types[param.value] = f"$type{i}"
                bound.append(self.types[param.value])
            parts += [":forall", _wrap(bound)]
            index += 2
        if head in _TYPE_HEADS:
            for item in items[index:]:
                if head == "defrecord":
                    parts.append(self._field(item))
                elif head == "defunion" and isinstance(item, ListExpr) and item.items:
                    parts.append(_wrap([self.render(item.items[0], {}), *[self._field(f) for f in item.items[1:]]]))
                else:
                    parts.append(self.render(item, {}))
            return _wrap(parts)
        params, scope = self.bind_params(items[index], {})
        tail = self._render_items(items[index + 1:], scope)
        return _wrap([*parts, params, tail[1:-1]])

    def _field(self, expr: SExpr) -> str:
        if isinstance(expr, ListExpr) and expr.items:
            return _wrap([self.render(expr.items[0], {}), *[self._type(t) for t in expr.items[1:]]])
        return self.render(expr, {})

    def render(self, expr: SExpr, scope: dict[str, str]) -> str:
        if isinstance(expr, SymbolAtom):
            root, dot, member = expr.value.partition(".")
            if dot and root not in scope and root in self.enums:
                return self.enums[root] + dot + member
        return super().render(expr, scope)

    def _render_list(self, expr: ListExpr, scope: dict[str, str]) -> str:
        items = expr.items
        head = _head_name(items)
        if head == "call" and len(items) >= 2 and isinstance(items[1], SymbolAtom):
            return self._render_call(items, scope)
        if head in {"record", "variant"} and len(items) >= 2:
            return self._render_constructor(head, items, scope)
        if head in {"proc-ref", "workflow-ref"} and len(items) == 2 and isinstance(items[1], SymbolAtom):
            return self._render_reference(head, items)
        if head == "loop-state" and len(items) > 1 and isinstance(items[1], ListExpr):
            return self._render_loop_state(items, scope)
        return super()._render_list(expr, scope)

    def _render_call(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        target = items[1].value
        return _wrap(["call", scope.get(target, self.calls.get(target, target)), *self._render_all(items[2:], scope)])

    def _render_constructor(self, head: str, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        prefix = [head, self._type(items[1])]
        start = 2
        if head == "variant" and len(items) >= 3:
            prefix.append(super().render(items[2], {}))
            start = 3
        return _wrap([*prefix, *self._render_all(items[start:], scope)])

    def _render_reference(self, head: str, items: Sequence[SExpr]) -> str:
        target = items[1].value
        local = self.local_procs if head == "proc-ref" else {}
        return _wrap([head, local.get(target, self.calls.get(target, target))])

    def _render_loop_state(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        fields = []
        for field in items[1:]:
            if isinstance(field, ListExpr) and len(field.items) >= 2:
                fields.append(_wrap([super().render(field.items[0], {}), self._type(field.items[1]),
                                     *self._render_all(field.items[2:], scope)]))
            else:
                fields.append(self.render(field, scope))
        return _wrap(["loop-state", *fields])

    @staticmethod
    def _let_proc_bindings(binding: ListExpr) -> tuple[bool, Sequence[SExpr]]:
        single = bool(binding.items) and isinstance(binding.items[0], SymbolAtom)
        return single, (binding,) if single else binding.items

    def _render_let_proc(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        single, bindings = self._let_proc_bindings(items[1])
        procs = [proc for proc in bindings if isinstance(proc, ListExpr) and len(proc.items) >= 2 and _binder_name(proc)]
        outer = self.local_procs
        for proc in procs:
            scope = self.bind(proc.items[0].value, scope)
        self.local_procs = {**outer, **{proc.items[0].value: scope[proc.items[0].value] for proc in procs}}
        try:
            rendered = []
            for proc in bindings:
                if proc not in procs:
                    rendered.append(self.render(proc, scope))
                    continue
                params, inner = self.bind_params(proc.items[1], scope)
                header = self._render_items(proc.items[2:-1], scope)[1:-1]
                parts = [self.local_procs[proc.items[0].value], params]
                if header:
                    parts.append(header)
                rendered.append(_wrap([*parts, self.render(proc.items[-1], inner)]))
            return _wrap(["let-proc", rendered[0] if single else _wrap(rendered),
                          *self._render_all(items[2:], scope)])
        finally:
            self.local_procs = outer

    def _render_items(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        parts = []
        previous = None
        for index, item in enumerate(items):
            if previous in {"->", ":returns"}:
                parts.append(self._type(item))
            elif previous == ":where" and isinstance(item, ListExpr):
                parts.append(self._render_where(item))
            elif previous == ":prompt":
                parts.append(self._render_prompt(item, scope))
            elif previous == ":captures" and isinstance(item, ListExpr):
                parts.append(_wrap(self._render_all(item.items, scope)))
            elif previous in _LITERAL_KEYWORDS:
                parts.append("#lit")
            elif index == 0 and isinstance(item, SymbolAtom):
                parts.append(self.local_procs.get(item.value, self.calls.get(item.value, self.render(item, scope))))
            else:
                parts.append(self.render(item, scope))
            previous = item.value if isinstance(item, (KeywordAtom, SymbolAtom)) else None
        return _wrap(parts)

    def _render_where(self, item: ListExpr) -> str:
        clauses = []
        for clause in item.items:
            subject, constraint, *operands = clause.items
            args = []
            for index, operand in enumerate(operands):
                args.append(self._field(operand) if isinstance(operand, ListExpr) else
                            self._type(operand) if constraint.value in {"has-field", "has-shared-union-field"} and index == 1
                            else super().render(operand, {}))
            clauses.append(_wrap([self._type(subject), constraint.value, *args]))
        return _wrap(clauses)


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
