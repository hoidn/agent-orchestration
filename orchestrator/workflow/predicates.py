"""Typed predicate evaluation for v1.6 workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .references import ReferenceResolutionError, ReferenceResolver

SCORE_PREDICATE_BOUND_KEYS = ("gt", "gte", "lt", "lte")
TYPED_PREDICATE_OPERATOR_KEYS = ("artifact_bool", "compare", "score", "all_of", "any_of", "not")


class PredicateEvaluationError(ValueError):
    """Raised when a typed predicate cannot be evaluated."""


def typed_predicate_operator_keys(predicate: Dict[str, Any]) -> list[str]:
    """Return the typed predicate operators present on one predicate node."""
    return [key for key in TYPED_PREDICATE_OPERATOR_KEYS if key in predicate]


def is_numeric_predicate_value(value: Any) -> bool:
    """Return True when one predicate operand is an integer or float, excluding bool."""
    return type(value) is int or isinstance(value, float)


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
