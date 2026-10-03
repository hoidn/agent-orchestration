"""Structured evaluation of checked workflow-lisp programs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from orchestrator.workflow.pure_expr import coerce_pure_value
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes, _effect_value_children

from .calls import call_environment, call_result
from .values import (
    BindingEvaluator,
    EvaluatedValue,
    EvaluatedValueError,
    LexicalEnvironment,
    coerce_evaluated_value,
    evaluate_closed_value,
)


EffectHandler = Callable[
    [Mapping[str, Any], tuple[EvaluatedValue, ...], str], EvaluatedValue
]
_LoopActivation = tuple[str, int]


def site_classes(program: ClosedProgram) -> dict[str, str]:
    """Map checked effect identities through each statically checked call frame."""
    tree = program.tree
    definitions = tree["definitions"]
    classes: dict[str, str] = {}

    def visit(body: Mapping[str, Any], activation: tuple[str, ...]) -> None:
        nodes = tuple(_ast_nodes(body))
        for node in nodes:
            if node.get("k") != "perform":
                continue
            identity = " / ".join((*activation, *node["site"].split(" / ")))
            effect_class = node["class"]
            previous = classes.setdefault(identity, effect_class)
            if previous != effect_class:
                raise ValueError(f"checked effect identity has conflicting classes: {identity}")

        for node in nodes:
            if node.get("k") != "call":
                continue
            callee = node["callee"]
            frame = node.get("frame")
            call_activation = activation
            if frame is not None:
                call_activation = (*activation, *frame.split(" / "))
            visit(definitions[callee]["body"], call_activation)

    entry = tree["entry"]
    visit(tree["body"], (entry,))
    return classes


class _ControlTransfer(Exception):
    def __init__(
        self, kind: str, target: str | None, values: tuple[EvaluatedValue, ...],
        selection_dependencies: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(kind)
        self.kind = kind
        self.target = target
        self.values = values
        self.selection_dependencies = selection_dependencies


@dataclass(frozen=True)
class _Machine:
    program: ClosedProgram
    effect_handler: EffectHandler | None
    run_id: str | None

    def evaluate(self, inputs: Mapping[str, Any]) -> EvaluatedValue:
        entry = self.program.tree
        environment = self._input_environment(entry, inputs)
        result = self._body(
            entry["body"], environment, entry["entry"], (entry["entry"],), ()
        )
        return self._coerce_result(result, entry["result"], entry["body"])

    def _input_environment(
        self, entry: Mapping[str, Any], inputs: Mapping[str, Any]
    ) -> LexicalEnvironment:
        if not isinstance(inputs, Mapping):
            raise TypeError("program inputs must be a mapping")
        params = dict(entry["params"])
        defaults = dict(entry.get("defaults", {}))
        unknown = set(inputs) - set(params)
        missing = set(params) - set(inputs) - set(defaults)
        if unknown or missing:
            raise EvaluatedValueError(
                "closed_input_names",
                f"input names differ from the entry signature (unknown={sorted(unknown)!r}, missing={sorted(missing)!r})",
            )
        supplied = {**defaults, **inputs}
        values = {
            name: self._coerce_result(
                value
                if isinstance(value, EvaluatedValue)
                else coerce_evaluated_value(value, params[name], context=f"input {name}"),
                params[name],
                entry,
            )
            for name, value in supplied.items()
        }
        return LexicalEnvironment(values, run_id=self.run_id)

    def _body(
        self,
        node: Mapping[str, Any],
        environment: LexicalEnvironment,
        owner: str,
        activation: tuple[str, ...],
        loops: tuple[_LoopActivation, ...],
    ) -> EvaluatedValue:
        evaluator = {
            "let": self._let,
            "halt": self._halt,
            "if": self._if,
            "case": self._case,
            "join": self._join,
            "jump": self._jump,
            "loop": self._loop,
            "continue": self._continue,
            "done": self._done,
        }.get(node.get("k"))
        if evaluator is None:
            raise self._error("closed_body_kind", f"unsupported body kind {node.get('k')!r}", node)
        return evaluator(node, environment, owner, activation, loops)

    def _let(self, node, environment, owner, activation, loops):
        value = self._bound(node["value"], environment, owner, activation, loops)
        return self._body(
            node["body"], environment.extend(node["name"], value), owner, activation, loops
        )

    def _halt(self, node, environment, owner, activation, loops):
        return self._value(node["value"], environment, owner, activation, loops)

    def _if(self, node, environment, owner, activation, loops):
        condition = self._value(node["cond"], environment, owner, activation, loops)
        selected = self._strict_bool(condition, node["cond"])
        branch = node["then"] if selected else node["else"]
        return self._selected(
            condition.dependencies,
            lambda: self._body(branch, environment, owner, activation, loops),
        )

    def _case(self, node, environment, owner, activation, loops):
        subject = self._value(node["subject"], environment, owner, activation, loops)
        selected = subject.value.get("variant") if isinstance(subject.value, Mapping) else None
        arm = next((row for row in node["arms"] if row["variant"] == selected), None)
        if arm is None:
            raise self._error("closed_case_variant", f"no arm for variant {selected!r}", node)
        descriptor = self._variant_descriptor(subject.descriptor, selected)
        bound = self._coerce_result(subject, descriptor, arm)
        local = environment.extend(arm["bind"], bound)
        return self._selected(
            subject.dependencies,
            lambda: self._body(arm["body"], local, owner, activation, loops),
        )

    def _selected(self, dependencies, evaluate):
        try:
            result = evaluate()
        except _ControlTransfer as transfer:
            raise _ControlTransfer(
                transfer.kind,
                transfer.target,
                tuple(self._add_dependencies(value, dependencies) for value in transfer.values),
                transfer.selection_dependencies | dependencies,
            ) from transfer
        return self._add_dependencies(result, dependencies)

    def _join(self, node, environment, owner, activation, loops):
        try:
            joined = self._body(node["body"], environment, owner, activation, loops)
        except _ControlTransfer as transfer:
            if transfer.kind != "jump" or transfer.target != node["name"]:
                raise
            if len(transfer.values) != 1:
                raise self._error("join_arity", "join expects one result value", node)
            (joined,) = transfer.values
        joined = self._coerce_result(joined, node["result"], node)
        parameter = node["params"][0][0]
        continuation = environment.extend(parameter, joined)
        return self._body(node["cont"], continuation, owner, activation, loops)

    def _jump(self, node, environment, owner, activation, loops):
        values = tuple(
            self._value(argument, environment, owner, activation, loops)
            for argument in node["args"]
        )
        raise _ControlTransfer("jump", node["join"], values)

    def _loop(self, node, environment, owner, activation, loops):
        budget_value = self._value(node["budget"], environment, owner, activation, loops)
        initial = self._value(node["init"], environment, owner, activation, loops)
        try:
            budget = coerce_pure_value(
                budget_value.value, {"kind": "primitive", "name": "Int"}, context="loop budget"
            )
        except (TypeError, ValueError) as exc:
            raise self._error("loop_budget_invalid", str(exc), node["budget"]) from exc
        state = self._coerce_result(initial, node["state_type"], node["init"])
        # Choices select the eventual loop result even when it does not read state.
        selection_dependencies = budget_value.dependencies
        for ordinal in range(1, max(0, budget) + 1):
            local = environment.extend(node["param"], state)
            if "index" in node:
                local = local.extend(
                    node["index"],
                    coerce_evaluated_value(
                        ordinal - 1,
                        {"kind": "primitive", "name": "Int"},
                        context="command loop index",
                    ),
                )
            active = (*loops, (node["name"], ordinal))
            try:
                self._body(node["body"], local, owner, activation, active)
            except _ControlTransfer as transfer:
                if transfer.target != node["name"]:
                    raise
                selection_dependencies |= transfer.selection_dependencies
                if transfer.kind == "done":
                    (result,) = transfer.values
                    completed = self._coerce_result(result, node["result"], node)
                    return self._add_dependencies(completed, selection_dependencies)
                if transfer.kind == "continue":
                    (next_state,) = transfer.values
                    state = self._coerce_result(next_state, node["state_type"], node)
                    continue
                raise self._error("loop_control", "invalid loop transfer", node)
            raise self._error("loop_control", "loop body returned without continue or done", node)
        exhausted = self._exhausted(node, environment, state, owner, activation, loops)
        return self._add_dependencies(exhausted, selection_dependencies)

    def _exhausted(self, node, environment, state, owner, activation, loops):
        exhausted = node.get("exhausted")
        if exhausted is None:
            code = node.get("code") or "loop_exhausted"
            raise self._error(code, "bounded loop exhausted without a result", node)
        local = environment.extend(node["param"], state)
        result = self._body(exhausted, local, owner, activation, loops)
        return self._coerce_result(result, node["result"], exhausted)

    def _continue(self, node, environment, owner, activation, loops):
        state = self._value(node["args"][0], environment, owner, activation, loops)
        raise _ControlTransfer("continue", node["loop"], (state,))

    def _done(self, node, environment, owner, activation, loops):
        result = self._value(node["value"], environment, owner, activation, loops)
        raise _ControlTransfer("done", loops[-1][0] if loops else None, (result,))

    def _bound(self, node, environment, owner, activation, loops):
        kind = node.get("k")
        if kind == "perform":
            return self._perform(node, environment, owner, activation, loops)
        if kind == "call":
            return self._call(node, environment, owner, activation, loops)
        return self._value(node, environment, owner, activation, loops)

    def _value(self, node, environment, owner, activation, loops):
        evaluate_body = lambda body, scope: self._body(
            body, scope, owner, activation, loops
        )
        evaluate_binding: BindingEvaluator = lambda value, scope: self._bound(
            value, scope, owner, activation, loops
        )
        return evaluate_closed_value(
            node,
            environment,
            evaluate_body=evaluate_body,
            evaluate_binding=evaluate_binding,
        )

    def _call(self, node, environment, owner, activation, loops):
        definition = self.program.tree["definitions"].get(node["callee"])
        if definition is None:
            raise self._error("closed_call_target", f"unknown call target {node['callee']!r}", node)
        arguments = tuple(
            self._value(value, environment, owner, activation, loops)
            for value in node["args"]
        )
        native_environment = call_environment(
            node, definition, arguments, run_id=self.run_id
        )
        frame = node.get("frame")
        call_activation = activation
        if frame is not None:
            call_activation = (*activation, *self._segments(self._instantiate(frame, loops)))
        result = self._body(
            definition["body"], native_environment, node["callee"], call_activation, ()
        )
        return call_result(node, definition, result)

    def _perform(self, node, environment, owner, activation, loops):
        if self.effect_handler is None:
            raise self._error("closed_effect_handler_missing", "effect callback is required", node)
        operands = tuple(
            self._value(value, environment, owner, activation, loops)
            for value in _effect_value_children(node)
        )
        site = self._instantiate(node["site"], loops)
        identity = self._identity((*activation, *self._segments(site)))
        result = self.effect_handler(node, operands, identity)
        if not isinstance(result, EvaluatedValue):
            raise TypeError("effect handler must return an EvaluatedValue")
        return self._coerce_result(result, node["result"], node)

    @staticmethod
    def _variant_descriptor(union: Mapping[str, Any], name: str) -> Mapping[str, Any]:
        variant = next((row for row in union.get("variants", ()) if row["name"] == name), None)
        if variant is None:
            raise EvaluatedValueError("closed_case_variant", f"unknown union variant {name!r}")
        return {
            "kind": "variant_case",
            "union_name": union["name"],
            "variant": name,
            "fields": variant["fields"],
        }

    @staticmethod
    def _strict_bool(value: EvaluatedValue, node: Mapping[str, Any]) -> bool:
        try:
            return coerce_pure_value(
                value.value, {"kind": "primitive", "name": "Bool"}, context="if condition"
            )
        except (TypeError, ValueError) as exc:
            location = node.get("@", {}).get("span") if isinstance(node.get("@"), Mapping) else None
            raise EvaluatedValueError("closed_condition_type", str(exc), location=location) from exc

    @staticmethod
    def _coerce_result(
        value: EvaluatedValue, descriptor: Mapping[str, Any], node: Mapping[str, Any]
    ) -> EvaluatedValue:
        try:
            return coerce_evaluated_value(
                value.value,
                descriptor,
                dependencies=value.dependencies,
                committed_result_path=value.committed_result_path,
                context="closed evaluation result",
            )
        except (TypeError, ValueError) as exc:
            location = node.get("@", {}).get("span") if isinstance(node.get("@"), Mapping) else None
            raise EvaluatedValueError(
                "closed_result_type", str(exc), location=location
            ) from exc

    @staticmethod
    def _add_dependencies(value: EvaluatedValue, dependencies: frozenset[str]) -> EvaluatedValue:
        if not dependencies:
            return value
        return EvaluatedValue(
            value.value,
            value.descriptor,
            value.dependencies | dependencies,
            value.committed_result_path,
        )

    @staticmethod
    def _segments(path: str) -> tuple[str, ...]:
        return tuple(path.split(" / ")) if path else ()

    @staticmethod
    def _identity(segments: Sequence[str]) -> str:
        return " / ".join(segments)

    @staticmethod
    def _instantiate(path: str, loops: tuple[_LoopActivation, ...]) -> str:
        ordinals = iter(ordinal for _, ordinal in loops)

        def replace(_match: re.Match[str]) -> str:
            try:
                return f"[{next(ordinals)}]"
            except StopIteration as exc:
                raise EvaluatedValueError(
                    "closed_identity_loop", "checked identity has more loop sites than active loops"
                ) from exc

        result = re.sub(r"\[\*\]", replace, path)
        try:
            next(ordinals)
        except StopIteration:
            return result
        raise EvaluatedValueError(
            "closed_identity_loop", "active loop count differs from checked identity path"
        )

    @staticmethod
    def _error(code: str, message: str, node: Mapping[str, Any]) -> EvaluatedValueError:
        location = node.get("@", {}).get("span") if isinstance(node.get("@"), Mapping) else None
        return EvaluatedValueError(code, message, location=location)


def evaluate_closed_program(
    program: ClosedProgram,
    inputs: Mapping[str, Any],
    *,
    effect_handler: EffectHandler | None = None,
    run_id: str | None = None,
) -> EvaluatedValue:
    """Evaluate a validated closed artifact using one structured control machine."""

    if not isinstance(program, ClosedProgram):
        raise TypeError("program must be a validated ClosedProgram")
    return _Machine(program, effect_handler, run_id).evaluate(inputs)
