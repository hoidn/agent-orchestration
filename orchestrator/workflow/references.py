"""Structured ref resolution for typed predicates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


class ReferenceResolutionError(ValueError):
    """Raised when a structured ref cannot be resolved at runtime."""


@dataclass(frozen=True)
class ResolvedReference:
    """Resolved structured ref value."""

    value: Any


@dataclass(frozen=True)
class StructuredRefTarget:
    """Parsed structured ref target."""

    scope: str
    step_name: str
    field: str
    member: Optional[str] = None


def parse_structured_ref(ref: str, step_names: Iterable[str]) -> StructuredRefTarget:
    """Parse a structured ref against the available step selectors."""
    if not isinstance(ref, str) or not ref:
        raise ReferenceResolutionError("Structured ref must be a non-empty string")

    for scope in ("root", "self", "parent"):
        prefix = f"{scope}.steps."
        if ref.startswith(prefix):
            remainder = ref[len(prefix):]
            return _parse_structured_ref_remainder(scope, remainder, ref, step_names)

    raise ReferenceResolutionError(f"Unsupported structured ref '{ref}'")


def _parse_structured_ref_remainder(
    scope: str,
    remainder: str,
    original_ref: str,
    step_names: Iterable[str],
) -> StructuredRefTarget:
    if not remainder:
        raise ReferenceResolutionError(f"Invalid structured ref '{original_ref}'")

    selectors = sorted(
        {name for name in step_names if isinstance(name, str) and name},
        key=len,
        reverse=True,
    )
    for step_name in selectors:
        prefix = f"{step_name}."
        if not remainder.startswith(prefix):
            continue

        tail = remainder[len(prefix):]
        if tail == "exit_code":
            return StructuredRefTarget(scope=scope, step_name=step_name, field="exit_code")
        if tail.startswith("artifacts.") and tail != "artifacts.":
            return StructuredRefTarget(
                scope=scope,
                step_name=step_name,
                field="artifacts",
                member=tail[len("artifacts."):],
            )
        if tail.startswith("outcome.") and tail != "outcome.":
            return StructuredRefTarget(
                scope=scope,
                step_name=step_name,
                field="outcome",
                member=tail[len("outcome."):],
            )

    if remainder.endswith(".exit_code"):
        step_name = remainder[: -len(".exit_code")]
        if step_name:
            return StructuredRefTarget(scope=scope, step_name=step_name, field="exit_code")
    if ".artifacts." in remainder:
        step_name, member = remainder.rsplit(".artifacts.", 1)
        if step_name and member:
            return StructuredRefTarget(
                scope=scope,
                step_name=step_name,
                field="artifacts",
                member=member,
            )
    if ".outcome." in remainder:
        step_name, member = remainder.rsplit(".outcome.", 1)
        if step_name and member:
            return StructuredRefTarget(
                scope=scope,
                step_name=step_name,
                field="outcome",
                member=member,
            )

    raise ReferenceResolutionError(f"Invalid structured ref '{original_ref}'")


class ReferenceResolver:
    """Resolve v1.6 structured refs against run state."""

    def resolve(
        self,
        ref: str,
        state: Dict[str, Any],
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResolvedReference:
        scope_map = scope if isinstance(scope, dict) else None

        if ref.startswith("inputs."):
            input_name = ref[len("inputs."):]
            if not input_name:
                raise ReferenceResolutionError(f"Invalid structured ref '{ref}'")
            if scope_map is not None and "inputs" in scope_map:
                bound_inputs = scope_map.get("inputs")
            else:
                bound_inputs = state.get("bound_inputs", {})
            if not isinstance(bound_inputs, dict) or input_name not in bound_inputs:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(bound_inputs[input_name])

        if ref.startswith("root.steps."):
            if scope_map is not None and "root_steps" in scope_map:
                step_results = scope_map.get("root_steps")
            else:
                step_results = state.get("steps", {})
        elif ref.startswith("self.steps."):
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

        if not isinstance(step_results, dict):
            raise ReferenceResolutionError(f"Structured ref target scope is unavailable for '{ref}'")

        target = parse_structured_ref(ref, step_results.keys())
        step_name = target.step_name
        step_result = step_results.get(step_name) if isinstance(step_results, dict) else None
        if not isinstance(step_result, dict):
            raise ReferenceResolutionError(f"Structured ref target step '{step_name}' is unavailable")

        if target.field == "exit_code":
            if "exit_code" not in step_result:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(step_result["exit_code"])

        if target.field == "artifacts":
            artifacts = step_result.get("artifacts")
            if not isinstance(artifacts, dict) or target.member not in artifacts:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(artifacts[target.member])

        if target.field == "outcome":
            outcome = step_result.get("outcome")
            if not isinstance(outcome, dict) or target.member not in outcome:
                raise ReferenceResolutionError(f"Structured ref '{ref}' is unavailable")
            return ResolvedReference(outcome[target.member])

        raise ReferenceResolutionError(f"Unsupported structured ref '{ref}'")
