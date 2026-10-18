"""Append-only JSONL records, skeleton hashing and the final-choice rule.

Design: docs/design/orc_structural_search_driver.md ("Search Modes" for the
skeleton hash, "Objective, Selection And Local Observations" for the
final-choice rule, "Records" for the log).

Dependencies: the Workflow Lisp reader (`read_sexpr_text`) for authored
source; the filesystem for the log. No other state.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
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
_DEFINITION_HEADS = {"defworkflow", "defproc"}
_KEYWORD_MARKERS = {":prompt": "#prompt", ":model": "#lit", ":effort": "#lit"}
_PROVIDER_PREFIX = "providers."


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

    Binders (`let*` names, `defworkflow`/`defproc` parameters, `match` arm
    names) and their references become per-definition ordinals `$0`, `$1`...;
    string and numeric literals and `:model`/`:effort` values become `#lit`;
    `:prompt` arguments become `#prompt`; `providers.*` externs become
    `#provider`. Form heads, keywords and arity are kept. Raises ValueError
    when a named definition is absent.
    """

    found = {}
    _collect_definitions(read_sexpr_text(source, source_path="<skeleton>"), found)
    missing = [name for name in definitions if name not in found]
    if missing:
        raise ValueError(f"definitions not found in source: {missing}")
    canonical = "\n".join(_normalize_definition(found[name]) for name in definitions)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _collect_definitions(expr: SExpr, found: dict[str, ListExpr]) -> None:
    if not isinstance(expr, ListExpr):
        return
    items = expr.items
    if (
        len(items) >= 2
        and isinstance(items[0], SymbolAtom)
        and items[0].value in _DEFINITION_HEADS
        and isinstance(items[1], SymbolAtom)
    ):
        found[items[1].value] = expr
        return
    for item in items:
        _collect_definitions(item, found)


class _Normalizer:
    """Render one definition with scope-ordinal placeholders."""

    def __init__(self) -> None:
        self._next = 0

    def bind(self, name: str, scope: dict[str, str]) -> dict[str, str]:
        placeholder = f"${self._next}"
        self._next += 1
        return {**scope, name: placeholder}

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
        if head == "let*" and len(items) >= 2 and isinstance(items[1], ListExpr):
            return self._render_let(items, scope)
        if head == "match" and len(items) >= 2:
            return self._render_match(items, scope)
        return self._render_items(items, scope)

    def _render_items(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        parts = []
        marker = None
        for item in items:
            parts.append(marker or self.render(item, scope))
            marker = _KEYWORD_MARKERS.get(item.value) if isinstance(item, KeywordAtom) else None
        return "(" + " ".join(parts) + ")"

    def _render_let(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        bindings = []
        for binding in items[1].items:
            if isinstance(binding, ListExpr) and binding.items and isinstance(binding.items[0], SymbolAtom):
                init = [self.render(value, scope) for value in binding.items[1:]]
                scope = self.bind(binding.items[0].value, scope)
                bindings.append("(" + " ".join([scope[binding.items[0].value], *init]) + ")")
            else:
                bindings.append(self.render(binding, scope))
        body = [self.render(item, scope) for item in items[2:]]
        return "(" + " ".join(["let*", "(" + " ".join(bindings) + ")", *body]) + ")"

    def _render_match(self, items: Sequence[SExpr], scope: dict[str, str]) -> str:
        parts = ["match", self.render(items[1], scope)]
        for arm in items[2:]:
            pattern = arm.items[0] if isinstance(arm, ListExpr) and arm.items else None
            if not (isinstance(pattern, ListExpr) and len(pattern.items) == 2 and isinstance(pattern.items[1], SymbolAtom)):
                parts.append(self.render(arm, scope))
                continue
            arm_scope = self.bind(pattern.items[1].value, scope)
            rendered_pattern = f"({self.render(pattern.items[0], scope)} {arm_scope[pattern.items[1].value]})"
            body = [self.render(item, arm_scope) for item in arm.items[1:]]
            parts.append("(" + " ".join([rendered_pattern, *body]) + ")")
        return "(" + " ".join(parts) + ")"


def _render_symbol(value: str, scope: dict[str, str]) -> str:
    if value.startswith(_PROVIDER_PREFIX):
        return "#provider"
    root, dot, rest = value.partition(".")
    return scope[root] + dot + rest if root in scope else value


def _normalize_definition(definition: ListExpr) -> str:
    """Render `(defworkflow|defproc name ((param Type) ...) ...)` canonically."""

    normalizer = _Normalizer()
    items = definition.items
    scope: dict[str, str] = {}
    params = []
    parameter_list = items[2] if len(items) > 2 and isinstance(items[2], ListExpr) else ListExpr((), definition.span)
    for param in parameter_list.items:
        if isinstance(param, ListExpr) and param.items and isinstance(param.items[0], SymbolAtom):
            scope = normalizer.bind(param.items[0].value, scope)
            rest = [normalizer.render(item, {}) for item in param.items[1:]]
            params.append("(" + " ".join([scope[param.items[0].value], *rest]) + ")")
        else:
            params.append(normalizer.render(param, {}))
    rest = [normalizer.render(item, scope) for item in items[3:]]
    head = [normalizer.render(item, {}) for item in items[:2]]
    return "(" + " ".join([*head, "(" + " ".join(params) + ")", *rest]) + ")"


def final_choice(rows: Sequence[Mapping], *, criterion: Mapping) -> str:
    """Return the `candidate_id` the frozen criterion selects among `rows`.

    Rows above `mean_cost_ceiling` are excluded ("unavailable" cost counts as
    above a numeric ceiling and below an "unavailable" ceiling). Among the
    rest: rows within `equivalence_tolerance` of the best
    `validation_success`, then lower `mean_cost`, fewer `provider_calls`,
    lexically earlier `candidate_id`. The reference seed competes like any row.
    """

    if not criterion.get("criterion_sha256"):
        raise ValueError("criterion_sha256 required")
    if not any(row["is_reference"] for row in rows):
        raise ValueError("reference seed missing")
    ceiling = criterion["mean_cost_ceiling"]
    eligible = [row for row in rows if _under_ceiling(row["mean_cost"], ceiling)]
    if not eligible:
        raise ValueError(f"no candidate under mean_cost_ceiling {ceiling!r}")
    best = max(row["validation_success"] for row in eligible)
    tied = [row for row in eligible if row["validation_success"] >= best - criterion["equivalence_tolerance"]]
    return min(tied, key=_tie_key)["candidate_id"]


def _under_ceiling(cost: float | str, ceiling: float | str) -> bool:
    if ceiling == UNAVAILABLE:
        return True
    return cost != UNAVAILABLE and cost <= ceiling


def _tie_key(row: Mapping) -> tuple:
    cost = row["mean_cost"]
    unavailable = cost == UNAVAILABLE
    return (unavailable, 0.0 if unavailable else cost, row["provider_calls"], row["candidate_id"])
