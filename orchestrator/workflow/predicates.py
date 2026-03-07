"""Typed predicate evaluation for v1.6 workflows."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .references import ReferenceResolutionError, ReferenceResolver

TYPED_PREDICATE_OPERATOR_KEYS = ("artifact_bool", "compare", "all_of", "any_of", "not")


class PredicateEvaluationError(ValueError):
    """Raised when a typed predicate cannot be evaluated."""


def typed_predicate_operator_keys(predicate: Dict[str, Any]) -> list[str]:
    """Return the typed predicate operators present on one predicate node."""
    return [key for key in TYPED_PREDICATE_OPERATOR_KEYS if key in predicate]


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
            if op == "lt":
                return left < right
            if op == "lte":
                return left <= right
            if op == "gt":
                return left > right
            if op == "gte":
                return left >= right
            raise PredicateEvaluationError(f"Unsupported compare operator '{op}'")

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
        if isinstance(operand, dict):
            if set(operand.keys()) == {"ref"}:
                try:
                    return self.reference_resolver.resolve(operand["ref"], state, scope=scope).value
                except ReferenceResolutionError as exc:
                    raise PredicateEvaluationError(str(exc)) from exc
            raise PredicateEvaluationError("Operand dictionaries must contain only 'ref'")
        return operand
