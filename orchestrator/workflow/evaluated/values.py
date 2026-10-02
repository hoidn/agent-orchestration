"""Immutable typed values and pure closed-value evaluation."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.pure_expr import (
    PureExprEvaluationError,
    coerce_pure_value,
    evaluate_pure_expr,
    evaluate_pure_path_join,
    value_coercion_payload,
)


@dataclass(frozen=True)
class EvaluatedValue:
    value: Any
    descriptor: Mapping[str, Any]
    dependencies: frozenset[str] = frozenset()
    committed_result_path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "descriptor", _freeze(self.descriptor))
        object.__setattr__(self, "dependencies", frozenset(self.dependencies))

    def json_value(self) -> Any:
        """Return the ordinary JSON-shaped value at an effect/serialization boundary."""

        return _thaw(self.value)


@dataclass(frozen=True)
class LexicalEnvironment:
    bindings: Mapping[str, EvaluatedValue] = field(default_factory=dict)
    parent: LexicalEnvironment | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))

    def lookup(self, name: str) -> EvaluatedValue:
        frame: LexicalEnvironment | None = self
        while frame is not None:
            if name in frame.bindings:
                return frame.bindings[name]
            frame = frame.parent
        raise KeyError(name)

    def extend(self, name: str, value: EvaluatedValue) -> LexicalEnvironment:
        return LexicalEnvironment({name: value}, self, self.run_id)


class EvaluatedValueError(PureExprEvaluationError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        location: str | None = None,
        operands: Iterable[Any] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, metadata=metadata, source=location)
        self.location = location
        self.operands = tuple(operands)


BodyEvaluator = Callable[[Mapping[str, Any], LexicalEnvironment], EvaluatedValue]
BindingEvaluator = Callable[[Mapping[str, Any], LexicalEnvironment], EvaluatedValue]
ValueEvaluator = Callable[
    [Mapping[str, Any], LexicalEnvironment, BodyEvaluator | None, BindingEvaluator | None],
    EvaluatedValue,
]


def coerce_evaluated_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    dependencies: Iterable[str] = (),
    committed_result_path: str | None = None,
    context: str = "value",
) -> EvaluatedValue:
    try:
        normalized = coerce_pure_value(value, descriptor, context=context)
    except PureExprEvaluationError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise EvaluatedValueError("pure_expr_operand_type_mismatch", str(exc)) from exc
    return EvaluatedValue(
        normalized, descriptor, frozenset(dependencies), committed_result_path
    )


def evaluate_closed_value(
    node: Mapping[str, Any],
    environment: LexicalEnvironment,
    *,
    evaluate_body: BodyEvaluator | None = None,
    evaluate_binding: BindingEvaluator | None = None,
) -> EvaluatedValue:
    evaluator = _VALUE_EVALUATORS.get(node.get("k"))
    if evaluator is None:
        raise _value_error(
            "closed_value_kind",
            f"unsupported closed value kind {node.get('k')!r}",
            node,
        )
    return evaluator(node, environment, evaluate_body, evaluate_binding)


def _evaluate_literal(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    return coerce_evaluated_value(node.get("v"), node["type"], context="literal")


def _evaluate_name(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    try:
        return environment.lookup(node["n"])
    except KeyError as exc:
        raise _value_error(
            "pure_expr_binding_missing", f"missing value for {node['n']!r}", node
        ) from exc


def _evaluate_context(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    if node.get("field") != "run-id" or environment.run_id is None:
        raise _value_error("closed_context_missing", "run-id context is unavailable", node)
    return coerce_evaluated_value(
        environment.run_id, {"kind": "primitive", "name": "RunId"},
        context="run-id context",
    )


def _evaluate_result_path(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    try:
        producer = environment.lookup(node["n"])
    except KeyError as exc:
        raise _value_error(
            "provider_result_path_missing", "committed provider result is unavailable", node
        ) from exc
    if producer.committed_result_path is None:
        raise _value_error(
            "provider_result_path_missing", "committed provider result path is unavailable", node
        )
    return coerce_evaluated_value(
        producer.committed_result_path,
        node["type"],
        dependencies=producer.dependencies,
        context="committed result path",
    )


def _evaluate_field(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    base = evaluate_closed_value(
        node["base"], environment, evaluate_body=evaluate_body,
        evaluate_binding=evaluate_binding,
    )
    value, descriptor = base.value, base.descriptor
    for field_name in node["path"]:
        descriptor = _field_descriptor(descriptor, field_name)
        if not isinstance(value, Mapping) or field_name not in value:
            raise _value_error(
                "pure_expr_operand_type_mismatch",
                f"field {field_name!r} is unavailable",
                node,
            )
        value = value[field_name]
    return coerce_evaluated_value(
        value, descriptor, dependencies=base.dependencies, context="field"
    )


def _evaluate_list(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    items = [
        evaluate_closed_value(
            item, environment, evaluate_body=evaluate_body,
            evaluate_binding=evaluate_binding,
        )
        for item in node["items"]
    ]
    return coerce_evaluated_value(
        [item.value for item in items], node["type"],
        dependencies=_dependencies(items), context="list",
    )


def _evaluate_path_join(
    node: Mapping[str, Any], environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None, evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    base = evaluate_closed_value(
        node["base"], environment, evaluate_body=evaluate_body,
        evaluate_binding=evaluate_binding,
    )
    child = evaluate_closed_value(
        node["child"], environment, evaluate_body=evaluate_body,
        evaluate_binding=evaluate_binding,
    )
    try:
        descriptor, value = evaluate_pure_path_join(base.value, child.value, node["type"])
        return coerce_evaluated_value(
            value, descriptor, dependencies=base.dependencies | child.dependencies,
            context="path_join",
        )
    except PureExprEvaluationError as exc:
        raise _operator_error(exc, node, (base, child)) from exc


def _evaluate_aggregate(
    node: Mapping[str, Any],
    environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None,
    evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    values = [
        (name, evaluate_closed_value(
            value, environment, evaluate_body=evaluate_body,
            evaluate_binding=evaluate_binding,
        ))
        for name, value in node["fields"]
    ]
    result = {name: value.value for name, value in values}
    descriptor = node["type"]
    if node["k"] == "inject":
        result = {"variant": node["variant"], **result}
    return coerce_evaluated_value(
        result, descriptor,
        dependencies=_dependencies(value for _, value in values),
        context=node["k"],
    )


def _evaluate_operator(
    node: Mapping[str, Any],
    environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None,
    evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    operands = tuple(
        evaluate_closed_value(
            arg, environment, evaluate_body=evaluate_body,
            evaluate_binding=evaluate_binding,
        )
        for arg in node["args"]
    )
    payload = node["payload"]
    catalog_payload = value_coercion_payload(payload)
    resolved = {f"a{index}": operand.value for index, operand in enumerate(operands)}
    try:
        result = evaluate_pure_expr(
            catalog_payload, resolved_bindings=resolved, max_nodes=None
        )
        return coerce_evaluated_value(
            result, payload["result_type"],
            dependencies=_dependencies(operands), context="operator result",
        )
    except PureExprEvaluationError as exc:
        raise _operator_error(exc, node, operands) from exc


def _evaluate_select(
    node: Mapping[str, Any],
    environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None,
    evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    condition = evaluate_closed_value(
        node["cond"], environment, evaluate_body=evaluate_body,
        evaluate_binding=evaluate_binding,
    )
    try:
        condition_value = coerce_pure_value(
            condition.value,
            {"kind": "primitive", "name": "Bool"},
            context="select condition",
        )
    except PureExprEvaluationError as exc:
        raise _operator_error(exc, node, (condition,)) from exc
    arm = node["then"] if condition_value else node["else"]
    scope = environment
    for row in arm["prefix"]:
        value = (
            evaluate_binding(row["value"], scope)
            if evaluate_binding is not None
            else evaluate_closed_value(
                row["value"], scope, evaluate_body=evaluate_body,
                evaluate_binding=evaluate_binding,
            )
        )
        scope = scope.extend(row["name"], value)
    result = evaluate_closed_value(
        arm["value"], scope, evaluate_body=evaluate_body,
        evaluate_binding=evaluate_binding,
    )
    return coerce_evaluated_value(
        result.value, result.descriptor,
        dependencies=condition.dependencies | result.dependencies,
        committed_result_path=result.committed_result_path,
        context="select result",
    )


def _evaluate_list_map(
    node: Mapping[str, Any],
    environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None,
    evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    source = evaluate_closed_value(
        node["source"], environment, evaluate_body=evaluate_body,
        evaluate_binding=evaluate_binding,
    )
    if not isinstance(source.value, tuple):
        raise _value_error("pure_expr_operand_type_mismatch", "list_map source is not a list", node)
    item_descriptor = source.descriptor["item"]
    mapped: list[EvaluatedValue] = []
    for item in source.value:
        bound = coerce_evaluated_value(
            item, item_descriptor, dependencies=source.dependencies,
            context="list_map binder",
        )
        local = environment.extend(node["binder"], bound)
        result = evaluate_closed_value(
            node["body"], local, evaluate_body=evaluate_body,
            evaluate_binding=evaluate_binding,
        )
        mapped.append(coerce_evaluated_value(
            result.value, node["type"]["item"], dependencies=result.dependencies,
            context="list_map result item",
        ))
    return coerce_evaluated_value(
        [item.value for item in mapped], node["type"],
        dependencies=source.dependencies | _dependencies(mapped), context="list_map result",
    )


def _evaluate_block(
    node: Mapping[str, Any],
    environment: LexicalEnvironment,
    evaluate_body: BodyEvaluator | None,
    evaluate_binding: BindingEvaluator | None,
) -> EvaluatedValue:
    if evaluate_body is None:
        raise EvaluatedValueError(
            "closed_body_evaluator_missing",
            "closed block needs the structured evaluator",
        )
    result = evaluate_body(node["body"], environment)
    if not isinstance(result, EvaluatedValue):
        raise TypeError("closed body evaluator must return an EvaluatedValue")
    return result


def _field_descriptor(descriptor: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    kind = descriptor.get("kind")
    if kind == "record":
        fields = descriptor["fields"]
    elif kind == "variant_case":
        if name == "variant":
            return {
                "kind": "enum",
                "name": descriptor["union_name"],
                "allowed": [descriptor["variant"]],
            }
        fields = descriptor["fields"]
    elif kind == "union" and name == "variant":
        return {
            "kind": "enum",
            "name": descriptor["name"] + ".variant",
            "allowed": [row["name"] for row in descriptor["variants"]],
        }
    else:
        raise EvaluatedValueError(
            "pure_expr_operand_type_mismatch",
            f"field {name!r} requires a record or proven variant",
        )
    for field_descriptor in fields:
        if field_descriptor["name"] == name:
            return field_descriptor["type"]
    raise EvaluatedValueError("record_field_unknown", f"unknown field {name!r}")


def _operator_error(
    error: PureExprEvaluationError,
    node: Mapping[str, Any],
    operands: Iterable[EvaluatedValue],
) -> EvaluatedValueError:
    values = tuple(operand.json_value() for operand in operands)
    location = node.get("@", {}).get("span") if isinstance(node.get("@"), Mapping) else None
    rendered = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return EvaluatedValueError(
        error.code, f"{error}: operands={rendered}", location=location,
        operands=values, metadata={**error.metadata, "operands": values},
    )


def _value_error(code: str, message: str, node: Mapping[str, Any]) -> EvaluatedValueError:
    location = node.get("@", {}).get("span") if isinstance(node.get("@"), Mapping) else None
    return EvaluatedValueError(code, message, location=location)


def _dependencies(values: Iterable[EvaluatedValue]) -> frozenset[str]:
    return frozenset(dependency for value in values for dependency in value.dependencies)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


_VALUE_EVALUATORS: Mapping[str, ValueEvaluator] = {
    "lit": _evaluate_literal,
    "name": _evaluate_name,
    "context": _evaluate_context,
    "result_path": _evaluate_result_path,
    "field": _evaluate_field,
    "record": _evaluate_aggregate,
    "inject": _evaluate_aggregate,
    "op": _evaluate_operator,
    "select": _evaluate_select,
    "list": _evaluate_list,
    "list_map": _evaluate_list_map,
    "path_join": _evaluate_path_join,
    "block": _evaluate_block,
}
