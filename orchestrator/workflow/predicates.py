"""Typed predicate evaluation for v1.6 workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .references import (
    ReferenceResolutionError,
    ReferenceResolver,
    SurfaceRefScopeCatalog,
    parse_surface_ref,
)

SCORE_PREDICATE_BOUND_KEYS = ("gt", "gte", "lt", "lte")
TYPED_PREDICATE_OPERATOR_KEYS = ("artifact_bool", "compare", "score", "all_of", "any_of", "not")


class PredicateEvaluationError(ValueError):
    """Raised when a typed predicate cannot be evaluated."""


@dataclass(frozen=True)
class ArtifactBoolPredicateNode:
    """Typed authored artifact_bool predicate node."""

    ref: Any


@dataclass(frozen=True)
class ComparePredicateNode:
    """Typed authored compare predicate node."""

    left: Any
    op: str
    right: Any


@dataclass(frozen=True)
class ScorePredicateNode:
    """Typed authored score predicate node."""

    ref: Any
    gt: Optional[float] = None
    gte: Optional[float] = None
    lt: Optional[float] = None
    lte: Optional[float] = None


@dataclass(frozen=True)
class AllOfPredicateNode:
    """Typed authored all_of predicate node."""

    items: tuple[Any, ...]


@dataclass(frozen=True)
class AnyOfPredicateNode:
    """Typed authored any_of predicate node."""

    items: tuple[Any, ...]


@dataclass(frozen=True)
class NotPredicateNode:
    """Typed authored not predicate node."""

    item: Any


def typed_predicate_operator_keys(predicate: Dict[str, Any]) -> list[str]:
    """Return the typed predicate operators present on one predicate node."""
    return [key for key in TYPED_PREDICATE_OPERATOR_KEYS if key in predicate]


def is_numeric_predicate_value(value: Any) -> bool:
    """Return True when one predicate operand is an integer or float, excluding bool."""
    return type(value) is int or isinstance(value, float)


def parse_typed_operand(operand: Any, catalog: SurfaceRefScopeCatalog) -> Any:
    """Parse one authored predicate operand into a typed value/ref node."""
    if isinstance(operand, dict):
        if set(operand.keys()) != {"ref"}:
            raise PredicateEvaluationError("Operand dictionaries must contain only 'ref'")
        return parse_surface_ref(operand["ref"], catalog)
    return operand


def parse_typed_predicate(predicate: Dict[str, Any], catalog: SurfaceRefScopeCatalog) -> Any:
    """Parse one authored typed predicate into immutable AST nodes."""
    if not isinstance(predicate, dict):
        raise PredicateEvaluationError("Typed predicate must be a dictionary")

    present_keys = typed_predicate_operator_keys(predicate)
    if len(present_keys) != 1:
        raise PredicateEvaluationError("Typed predicate nodes must declare exactly one operator")

    if "artifact_bool" in predicate:
        node = predicate["artifact_bool"]
        if not isinstance(node, dict) or set(node.keys()) != {"ref"}:
            raise PredicateEvaluationError("artifact_bool requires a ref operand")
        return ArtifactBoolPredicateNode(ref=parse_surface_ref(node["ref"], catalog))

    if "compare" in predicate:
        node = predicate["compare"]
        if not isinstance(node, dict):
            raise PredicateEvaluationError("compare predicate must be a dictionary")
        return ComparePredicateNode(
            left=parse_typed_operand(node.get("left"), catalog),
            op=str(node.get("op")),
            right=parse_typed_operand(node.get("right"), catalog),
        )

    if "score" in predicate:
        node = predicate["score"]
        if not isinstance(node, dict):
            raise PredicateEvaluationError("score predicate must be a dictionary")
        ref = node.get("ref")
        if not isinstance(ref, str) or not ref:
            raise PredicateEvaluationError("score requires a ref")
        return ScorePredicateNode(
            ref=parse_surface_ref(ref, catalog),
            gt=node.get("gt"),
            gte=node.get("gte"),
            lt=node.get("lt"),
            lte=node.get("lte"),
        )

    if "all_of" in predicate:
        items = predicate["all_of"]
        if not isinstance(items, list):
            raise PredicateEvaluationError("all_of requires a list")
        return AllOfPredicateNode(items=tuple(parse_typed_predicate(item, catalog) for item in items))

    if "any_of" in predicate:
        items = predicate["any_of"]
        if not isinstance(items, list):
            raise PredicateEvaluationError("any_of requires a list")
        return AnyOfPredicateNode(items=tuple(parse_typed_predicate(item, catalog) for item in items))

    if "not" in predicate:
        return NotPredicateNode(item=parse_typed_predicate(predicate["not"], catalog))

    raise PredicateEvaluationError("Unsupported typed predicate")


class TypedPredicateEvaluator:
    """Evaluate structured predicates against run state."""

    def __init__(self):
        self.reference_resolver = ReferenceResolver()

    def evaluate(
        self,
        predicate: Dict[str, Any],
        state: Dict[str, Any],
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        if not isinstance(predicate, dict):
            raise PredicateEvaluationError("Typed predicate must be a dictionary")

        present_keys = typed_predicate_operator_keys(predicate)
        if len(present_keys) != 1:
            raise PredicateEvaluationError("Typed predicate nodes must declare exactly one operator")

        if "artifact_bool" in predicate:
            node = predicate["artifact_bool"]
            if not isinstance(node, dict) or "ref" not in node:
                raise PredicateEvaluationError("artifact_bool requires a ref operand")
            value = self._resolve_operand(node, state, scope)
            if not isinstance(value, bool):
                raise PredicateEvaluationError("artifact_bool ref must resolve to a bool")
            return value

        if "compare" in predicate:
            node = predicate["compare"]
            if not isinstance(node, dict):
                raise PredicateEvaluationError("compare predicate must be a dictionary")
            left = self._resolve_operand(node.get("left"), state, scope)
            right = self._resolve_operand(node.get("right"), state, scope)
            op = node.get("op")
            if op == "eq":
                return left == right
            if op == "ne":
                return left != right
            if op in {"lt", "lte", "gt", "gte"}:
                if not is_numeric_predicate_value(left) or not is_numeric_predicate_value(right):
                    raise PredicateEvaluationError("ordered compare operators require numeric operands")
            if op == "lt":
                return left < right
            if op == "lte":
                return left <= right
            if op == "gt":
                return left > right
            if op == "gte":
                return left >= right
            raise PredicateEvaluationError(f"Unsupported compare operator '{op}'")

        if "score" in predicate:
            node = predicate["score"]
            if not isinstance(node, dict):
                raise PredicateEvaluationError("score predicate must be a dictionary")

            score_ref = node.get("ref")
            if not isinstance(score_ref, str) or not score_ref:
                raise PredicateEvaluationError("score requires a ref")

            if "gt" in node and "gte" in node:
                raise PredicateEvaluationError("score cannot declare both gt and gte")
            if "lt" in node and "lte" in node:
                raise PredicateEvaluationError("score cannot declare both lt and lte")

            bounds = {
                key: node[key]
                for key in SCORE_PREDICATE_BOUND_KEYS
                if key in node
            }
            if not bounds:
                raise PredicateEvaluationError("score requires at least one bound")
            if any(not is_numeric_predicate_value(value) for value in bounds.values()):
                raise PredicateEvaluationError("score bounds must be numeric")

            score_value = self._resolve_operand({"ref": score_ref}, state, scope)
            if not is_numeric_predicate_value(score_value):
                raise PredicateEvaluationError("score requires a numeric ref")

            if "gt" in bounds and not score_value > bounds["gt"]:
                return False
            if "gte" in bounds and not score_value >= bounds["gte"]:
                return False
            if "lt" in bounds and not score_value < bounds["lt"]:
                return False
            if "lte" in bounds and not score_value <= bounds["lte"]:
                return False
            return True

        if "all_of" in predicate:
            items = predicate["all_of"]
            if not isinstance(items, list) or not items:
                raise PredicateEvaluationError("all_of requires a non-empty list")
            return all(self.evaluate(item, state, scope) for item in items)

        if "any_of" in predicate:
            items = predicate["any_of"]
            if not isinstance(items, list) or not items:
                raise PredicateEvaluationError("any_of requires a non-empty list")
            return any(self.evaluate(item, state, scope) for item in items)

        if "not" in predicate:
            return not self.evaluate(predicate["not"], state, scope)

        raise PredicateEvaluationError("Unsupported typed predicate")

    def _resolve_operand(
        self,
        operand: Any,
        state: Dict[str, Any],
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Any:
        return resolve_typed_operand(operand, state, scope=scope)


def resolve_typed_operand(
    operand: Any,
    state: Dict[str, Any],
    scope: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Any:
    """Resolve one typed-predicate operand or return a literal unchanged."""
    if isinstance(operand, dict):
        if set(operand.keys()) == {"ref"}:
            try:
                return ReferenceResolver().resolve(operand["ref"], state, scope=scope).value
            except ReferenceResolutionError as exc:
                raise PredicateEvaluationError(str(exc)) from exc
        raise PredicateEvaluationError("Operand dictionaries must contain only 'ref'")
    return operand
