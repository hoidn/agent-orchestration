"""Iterative pure evaluator for the dynamic-core experiment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow.pure_expr import (
    PURE_EXPR_OPERATOR_CATALOG,
    PureExprEvaluationError,
    coerce_pure_value,
    evaluate_pure_operator,
)
from orchestrator.workflow.type_descriptor import validate_transport_value

from .program import DynamicProgram, _pointer


_BOOL = {"kind": "primitive", "name": "Bool"}
_INT = {"kind": "primitive", "name": "Int"}
_FLOAT = {"kind": "primitive", "name": "Float"}
_Frame = tuple[str, str, str]
_Activation = tuple[Any, _Frame] | None


@dataclass(frozen=True)
class _Closure:
    code: str
    captures: tuple[Any, ...]


@dataclass(frozen=True)
class EvaluationResult:
    value: Any
    steps: int
    call_trace: tuple[_Frame, ...]

    def json_value(self) -> Any:
        return _thaw(self.value)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in {list, tuple}:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, _Closure):
        raise TypeError("a closure is not ordinary JSON data")
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "Bool"
    if type(value) is int:
        return "Int"
    if type(value) is float:
        return "Float"
    if isinstance(value, str):
        return "String"
    if isinstance(value, _Closure):
        return "closure"
    if isinstance(value, Mapping):
        return "record"
    if type(value) is tuple:
        return "list"
    return "host value"


def _formed_boundary_value(
    value: Any,
    pointer: str,
    call_context: _Activation,
    field_path: str = "$",
) -> Any:
    if value is None or type(value) in {bool, str}:
        return value
    if type(value) is int:
        try:
            return coerce_pure_value(value, _INT, context="boundary value")
        except PureExprEvaluationError as exc:
            raise EvaluatedValueError(
                "dynamic_boundary_invalid",
                "integer boundary value is outside the admitted range",
                location=pointer,
                metadata={"field_path": field_path, "call_context": _call_context_frames(call_context)},
            ) from exc
    if type(value) is float:
        try:
            return coerce_pure_value(value, _FLOAT, context="boundary value")
        except PureExprEvaluationError as exc:
            raise EvaluatedValueError(
                "dynamic_boundary_invalid",
                "Float boundary value is not finite",
                location=pointer,
                metadata={"field_path": field_path, "call_context": _call_context_frames(call_context)},
            ) from exc
    if type(value) is list:
        return tuple(
            _formed_boundary_value(
                item,
                _pointer(pointer, index),
                call_context,
                _pointer(field_path, index),
            )
            for index, item in enumerate(value)
        )
    if type(value) is dict:
        return MappingProxyType({
            key: _formed_boundary_value(
                item,
                _pointer(pointer, key),
                call_context,
                _pointer(field_path, key),
            )
            for key, item in value.items()
        })
    raise EvaluatedValueError(
        "dynamic_boundary_invalid",
        "boundary value must contain only ordinary JSON data",
        location=pointer,
        metadata={"field_path": field_path, "call_context": _call_context_frames(call_context)},
    )


def _boundary_value(
    value: Any,
    descriptor: Mapping[str, Any],
    pointer: str,
    call_context: _Activation,
) -> Any:
    try:
        normalized = validate_transport_value(
            value,
            descriptor,
            allow_nested_structures=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        message = str(exc)
        raise EvaluatedValueError(
            "dynamic_boundary_invalid",
            "boundary value does not satisfy its declared schema",
            location=pointer,
            metadata={
                "validator_error": message,
                "call_context": _call_context_frames(call_context),
            },
        ) from exc
    return _formed_boundary_value(normalized, pointer, call_context)


def _call_context_frames(context: _Activation) -> tuple[_Frame, ...]:
    frames: list[_Frame] = []
    while context is not None:
        context, frame = context
        frames.append(frame)
    return tuple(reversed(frames))


def _call_context_metadata(context: _Activation) -> dict[str, Any]:
    return {"call_context": _call_context_frames(context)}


def _error(
    code: str,
    message: str,
    pointer: str,
    context: _Activation,
    steps: int,
    **metadata: Any,
) -> EvaluatedValueError:
    return EvaluatedValueError(
        code,
        message,
        location=pointer,
        metadata={"steps": steps, **_call_context_metadata(context), **metadata},
    )


def _pop_values(values: list[Any], count: int) -> list[Any]:
    if count == 0:
        return []
    result = values[-count:]
    del values[-count:]
    return result


def evaluate(program: DynamicProgram, inputs: Mapping[str, Any]) -> EvaluationResult:
    """Validate declared input data, evaluate one entry body and validate its result."""

    if not isinstance(inputs, Mapping):
        raise EvaluatedValueError("dynamic_boundary_invalid", "entry inputs must be an object", location="/inputs")
    expected_names = [name for name, _ in program.inputs]
    if len(inputs) != len(expected_names) or any(name not in inputs for name in expected_names):
        raise EvaluatedValueError("dynamic_boundary_invalid", "entry inputs do not match the declaration", location="/inputs")

    environment: dict[str, Any] = {}
    for index, (name, schema_name) in enumerate(program.inputs):
        pointer = _pointer("/inputs", index)
        environment[name] = _boundary_value(
            inputs[name], program.schemas[schema_name], pointer, None
        )

    values: list[Any] = []
    tasks: list[tuple[Any, ...]] = [
        (
            "enter",
            program.definitions[program.entry]["body"],
            MappingProxyType(environment),
            _pointer(_pointer("/definitions", program.entry), "body"),
            program.entry,
            None,
        )
    ]
    steps = 0
    call_trace: list[_Frame] = []

    while tasks:
        task = tasks.pop()
        action = task[0]

        if action == "enter":
            _, node, env, pointer, code, context = task
            if steps >= program.budget:
                raise _error(
                    "dynamic_budget_exhausted",
                    "evaluation node budget exhausted",
                    pointer,
                    context,
                    steps,
                )
            steps += 1
            kind = node["k"]
            if kind == "lit":
                value = node["v"]
                if type(value) is int:
                    try:
                        value = coerce_pure_value(value, _INT, context="literal")
                    except PureExprEvaluationError as exc:
                        raise _error("dynamic_operand_type", "integer literal is outside the admitted range", pointer, context, steps) from exc
                elif type(value) is float:
                    try:
                        value = coerce_pure_value(value, _FLOAT, context="literal")
                    except PureExprEvaluationError as exc:
                        raise _error("dynamic_operand_type", "Float literal must be finite", pointer, context, steps) from exc
                values.append(value)
            elif kind == "name":
                values.append(env[node["n"]])
            elif kind == "let":
                tasks.append(("let_next", node, 0, env, pointer, code, context))
            elif kind == "fn":
                captures = node["captures"]
                tasks.append(("fn_done", node["code"], len(captures)))
                for index in reversed(range(len(captures))):
                    tasks.append(("enter", captures[index], env, _pointer(_pointer(pointer, "captures"), index), code, context))
            elif kind == "call":
                args = node["args"]
                tasks.append(("call_apply", len(args), pointer, code, context))
                for index in reversed(range(len(args))):
                    tasks.append(("enter", args[index], env, _pointer(_pointer(pointer, "args"), index), code, context))
                tasks.append(("enter", node["callee"], env, _pointer(pointer, "callee"), code, context))
            elif kind == "if":
                tasks.append(("if_done", node, env, pointer, code, context))
                tasks.append(("enter", node["cond"], env, _pointer(pointer, "cond"), code, context))
            elif kind == "record":
                fields = node["fields"]
                tasks.append(("record_done", tuple(row[0] for row in fields), len(fields)))
                for index in reversed(range(len(fields))):
                    tasks.append(("enter", fields[index][1], env, _pointer(_pointer(_pointer(pointer, "fields"), index), 1), code, context))
            elif kind == "field":
                tasks.append(("field_done", node["name"], pointer, context))
                tasks.append(("enter", node["base"], env, _pointer(pointer, "base"), code, context))
            elif kind == "list":
                items = node["items"]
                tasks.append(("list_done", len(items)))
                for index in reversed(range(len(items))):
                    tasks.append(("enter", items[index], env, _pointer(_pointer(pointer, "items"), index), code, context))
            elif kind == "at":
                tasks.append(("at_done", pointer, context))
                tasks.append(("enter", node["index"], env, _pointer(pointer, "index"), code, context))
                tasks.append(("enter", node["base"], env, _pointer(pointer, "base"), code, context))
            elif kind == "op":
                args = node["args"]
                tasks.append(("op_done", node["name"], len(args), pointer, context))
                for index in reversed(range(len(args))):
                    tasks.append(("enter", args[index], env, _pointer(_pointer(pointer, "args"), index), code, context))
            continue

        if action == "let_next":
            _, node, index, env, pointer, code, context = task
            if index == len(node["bindings"]):
                tasks.append(("enter", node["body"], env, _pointer(pointer, "body"), code, context))
            else:
                row = node["bindings"][index]
                row_pointer = _pointer(_pointer(pointer, "bindings"), index)
                tasks.append(("let_bind", node, index, env, row[0], pointer, code, context))
                tasks.append(("enter", row[1], env, _pointer(row_pointer, 1), code, context))
            continue

        if action == "let_bind":
            _, node, index, env, binder, pointer, code, context = task
            value = values.pop()
            updated = dict(env)
            updated[binder] = value
            tasks.append(("let_next", node, index + 1, MappingProxyType(updated), pointer, code, context))
            continue

        if action == "fn_done":
            _, target_code, count = task
            captures = tuple(_pop_values(values, count))
            values.append(_Closure(target_code, captures))
            continue

        if action == "call_apply":
            _, count, pointer, caller_code, context = task
            evaluated = _pop_values(values, count + 1)
            callee, args = evaluated[0], evaluated[1:]
            if not isinstance(callee, _Closure):
                raise _error(
                    "dynamic_not_callable",
                    f"call target has value kind {_kind(callee)}",
                    pointer,
                    context,
                    steps,
                    value_kind=_kind(callee),
                )
            definition = program.definitions[callee.code]
            parameters = definition["params"]
            if len(args) != len(parameters):
                raise _error(
                    "dynamic_call_arity",
                    "call argument count does not match the selected function",
                    pointer,
                    context,
                    steps,
                    expected_arity=len(parameters),
                    observed_arity=len(args),
                )
            frame = (caller_code, pointer, callee.code)
            activation = (context, frame)
            call_trace.append(frame)
            bindings = dict(zip(definition["captures"], callee.captures))
            bindings.update(zip(parameters, args))
            tasks.append((
                "enter",
                definition["body"],
                MappingProxyType(bindings),
                _pointer(_pointer("/definitions", callee.code), "body"),
                callee.code,
                activation,
            ))
            continue

        if action == "if_done":
            _, node, env, pointer, code, context = task
            condition = values.pop()
            if type(condition) is not bool:
                raise _error(
                    "dynamic_condition_type",
                    f"condition must be Bool, observed {_kind(condition)}",
                    pointer,
                    context,
                    steps,
                    observed_kind=_kind(condition),
                )
            branch = "then" if condition else "else"
            tasks.append(("enter", node[branch], env, _pointer(pointer, branch), code, context))
            continue

        if action == "record_done":
            _, fields, count = task
            items = _pop_values(values, count)
            values.append(MappingProxyType(dict(zip(fields, items))))
            continue

        if action == "field_done":
            _, field_name, pointer, context = task
            base = values.pop()
            if not isinstance(base, Mapping):
                raise _error(
                    "dynamic_operand_type",
                    f"field access requires a record or map, observed {_kind(base)}",
                    pointer,
                    context,
                    steps,
                    observed_kind=_kind(base),
                )
            if field_name not in base:
                raise _error(
                    "dynamic_field_missing",
                    "record or map does not contain the requested field",
                    pointer,
                    context,
                    steps,
                    field=field_name,
                )
            values.append(base[field_name])
            continue

        if action == "list_done":
            _, count = task
            values.append(tuple(_pop_values(values, count)))
            continue

        if action == "at_done":
            _, pointer, context = task
            base, index = _pop_values(values, 2)
            if type(base) is not tuple or type(index) is not int or index < 0 or index >= len(base):
                raise _error(
                    "dynamic_index_invalid",
                    "index requires an in-range nonnegative Int and a list",
                    pointer,
                    context,
                    steps,
                    observed_base=_kind(base),
                    observed_index=_kind(index),
                )
            values.append(base[index])
            continue

        if action == "op_done":
            _, operator, count, pointer, context = task
            args = _pop_values(values, count)
            spec = PURE_EXPR_OPERATOR_CATALOG[operator]
            if count < spec.min_arity or (spec.max_arity is not None and count > spec.max_arity):
                raise _error(
                    "dynamic_operand_type",
                    f"primitive {operator!r} received the wrong number of operands",
                    pointer,
                    context,
                    steps,
                    operator=operator,
                    expected_arity=[spec.min_arity, spec.max_arity],
                    observed_arity=count,
                )
            kinds = [_kind(arg) for arg in args]
            descriptors = {"Bool": _BOOL, "Int": _INT, "Float": _FLOAT, "String": {"kind": "primitive", "name": "String"}}
            if any(kind not in descriptors for kind in kinds):
                raise _error(
                    "dynamic_operand_type",
                    f"primitive {operator!r} requires scalar operands; observed {kinds}",
                    pointer,
                    context,
                    steps,
                    operator=operator,
                    operand_kinds=kinds,
                )
            try:
                _, result = evaluate_pure_operator(
                    operator,
                    [(descriptors[kind], arg) for kind, arg in zip(kinds, args)],
                )
            except PureExprEvaluationError as exc:
                code = "dynamic_operand_type" if exc.code == "pure_expr_operand_type_mismatch" else exc.code
                raise _error(
                    code,
                    f"primitive {operator!r} refused operand kinds {kinds}",
                    pointer,
                    context,
                    steps,
                    operator=operator,
                    operand_kinds=kinds,
                ) from exc
            values.append(result)
            continue

        raise AssertionError(f"unknown evaluator continuation {action!r}")

    if len(values) != 1:
        raise AssertionError("dynamic evaluator value stack is unbalanced")
    try:
        ordinary = _thaw(values.pop())
    except (TypeError, RecursionError) as exc:
        raise EvaluatedValueError(
            "dynamic_boundary_invalid",
            "closures cannot cross a data boundary",
            location=_pointer("/definitions", program.entry),
            metadata={"field_path": "$", "call_context": (), "steps": steps},
        ) from exc
    result_pointer = "/result"
    normalized = _boundary_value(
        ordinary,
        program.schemas[program.result],
        result_pointer,
        None,
    )
    return EvaluationResult(_freeze(normalized), steps, tuple(call_trace))


__all__ = ["EvaluationResult", "evaluate"]
