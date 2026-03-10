"""Helpers for step-local variable and scope context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


_CONTEXT_RESERVED_KEYS = frozenset({"run", "context", "steps", "loop", "item", "inputs"})


@dataclass(frozen=True)
class RuntimeContext:
    """Normalized view over the loose context bundles used during execution."""

    values: Mapping[str, Any] = field(default_factory=dict)
    workflow_context: Mapping[str, Any] = field(default_factory=dict)
    self_steps: Mapping[str, Any] = field(default_factory=dict)
    explicit_steps: bool = False
    parent_steps: Mapping[str, Any] = field(default_factory=dict)
    root_steps: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        context: Mapping[str, Any] | None,
        *,
        default_context: Mapping[str, Any] | None = None,
        parent_steps: Mapping[str, Any] | None = None,
        root_steps: Mapping[str, Any] | None = None,
    ) -> "RuntimeContext":
        raw = dict(context or {})
        explicit_context = raw.get("context")
        if isinstance(explicit_context, Mapping):
            workflow_context = dict(explicit_context)
        else:
            workflow_context = dict(default_context or {})
        explicit_steps_value = raw.get("steps")
        has_explicit_steps = isinstance(explicit_steps_value, Mapping)
        self_steps = dict(explicit_steps_value) if has_explicit_steps else {}
        return cls(
            values=raw,
            workflow_context=workflow_context,
            self_steps=self_steps,
            explicit_steps=has_explicit_steps,
            parent_steps=dict(parent_steps or {}),
            root_steps=dict(root_steps or {}),
        )

    def scoped_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        scoped_state = state.copy()
        if self.explicit_steps:
            scoped_state["steps"] = dict(self.self_steps)
        return scoped_state

    def build_variables(self, variable_substitutor: Any, run_state: Dict[str, Any]) -> Dict[str, Any]:
        variables = variable_substitutor.build_variables(
            run_state=self.scoped_state(run_state),
            context=dict(self.workflow_context),
            loop_vars=self.values.get("loop"),
            item=self.values.get("item"),
        )
        for key, value in self.values.items():
            if key not in _CONTEXT_RESERVED_KEYS:
                variables[key] = value
        return variables

    def build_dependency_variables(self, state: Dict[str, Any]) -> Dict[str, str]:
        variables: Dict[str, str] = {}

        run_values = self.values.get("run")
        if isinstance(run_values, Mapping):
            for key, value in run_values.items():
                variables[f"run.{key}"] = str(value)

        for key, value in self.workflow_context.items():
            variables[f"context.{key}"] = str(value)

        input_values = self.values.get("inputs")
        if isinstance(input_values, Mapping):
            for key, value in input_values.items():
                variables[f"inputs.{key}"] = str(value)
        else:
            bound_inputs = state.get("bound_inputs", {})
            if isinstance(bound_inputs, Mapping):
                for key, value in bound_inputs.items():
                    variables[f"inputs.{key}"] = str(value)

        loop_values = self.values.get("loop")
        if isinstance(loop_values, Mapping):
            for key, value in loop_values.items():
                variables[f"loop.{key}"] = str(value)

        if "item" in self.values:
            variables["item"] = str(self.values["item"])

        return variables

    def scope(self) -> Dict[str, Dict[str, Any]]:
        return {
            "self_steps": dict(self.self_steps),
            "parent_steps": dict(self.parent_steps),
            "root_steps": dict(self.root_steps),
        }
