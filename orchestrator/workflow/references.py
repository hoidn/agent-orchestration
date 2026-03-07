"""Structured ref resolution for typed predicates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


class ReferenceResolutionError(ValueError):
    """Raised when a structured ref cannot be resolved at runtime."""


@dataclass(frozen=True)
class ResolvedReference:
    """Resolved structured ref value."""

    value: Any


class ReferenceResolver:
    """Resolve v1.6 structured refs against run state."""

    def resolve(
        self,
        ref: str,
        state: Dict[str, Any],
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResolvedReference:
        if not isinstance(ref, str) or not ref:
            raise ReferenceResolutionError("Structured ref must be a non-empty string")
        scope_map = scope if isinstance(scope, dict) else None

        if ref.startswith("root.steps."):
            parts = ref.split(".")
            if scope_map is not None and "root_steps" in scope_map:
                step_results = scope_map.get("root_steps")
            else:
                step_results = state.get("steps", {})
        elif ref.startswith("self.steps."):
            parts = ref.split(".")
            if scope_map is None:
                step_results = state.get("steps", {})
            elif "self_steps" in scope_map:
                step_results = scope_map.get("self_steps")
            else:
                raise ReferenceResolutionError(f"Structured ref target scope is unavailable for '{ref}'")
        elif ref.startswith("parent.steps."):
            parts = ref.split(".")
            step_results = scope_map.get("parent_steps") if scope_map is not None else None
            if not isinstance(step_results, dict):
                raise ReferenceResolutionError(f"Structured ref target scope is unavailable for '{ref}'")
        else:
            raise ReferenceResolutionError(f"Unsupported structured ref '{ref}'")
        if len(parts) < 4:
            raise ReferenceResolutionError(f"Invalid structured ref '{ref}'")

        step_name = parts[2]
        step_result = step_results.get(step_name) if isinstance(step_results, dict) else None
        if not isinstance(step_result, dict):
            raise ReferenceResolutionError(f"Structured ref target step '{step_name}' is unavailable")

        tail = parts[3:]
        if tail == ["exit_code"]:
            if "exit_code" not in step_result:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(step_result["exit_code"])

        if len(tail) == 2 and tail[0] == "artifacts":
            artifacts = step_result.get("artifacts")
            if not isinstance(artifacts, dict) or tail[1] not in artifacts:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(artifacts[tail[1]])

        if len(tail) == 2 and tail[0] == "outcome":
            outcome = step_result.get("outcome")
            if not isinstance(outcome, dict) or tail[1] not in outcome:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(outcome[tail[1]])

        raise ReferenceResolutionError(f"Unsupported structured ref '{ref}'")
