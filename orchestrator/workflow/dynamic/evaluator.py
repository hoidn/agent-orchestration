"""Iterative pure evaluator for checked dynamic Workflow Lisp programs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.evaluated.values import (
    EvaluatedValueError,
    _freeze,
    _thaw,
)
from orchestrator.workflow.pure_expr import (
    PURE_EXPR_OPERATOR_CATALOG,
    PureExprEvaluationError,
    coerce_pure_value,
    evaluate_pure_operator,
)
from orchestrator.workflow.type_descriptor import validate_transport_value
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram, _pointer


_BOOL = {"kind": "primitive", "name": "Bool"}
_INT = {"kind": "primitive", "name": "Int"}
_FLOAT = {"kind": "primitive", "name": "Float"}
_STRING = {"kind": "primitive", "name": "String"}
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


def _call_context_frames(context: _Activation) -> tuple[_Frame, ...]:
    frames: list[_Frame] = []
    while context is not None:
        context, frame = context
        frames.append(frame)
    return tuple(reversed(frames))


def _call_stack(program: DynamicProgram, context: _Activation) -> tuple[Mapping[str, Any], ...]:
    frames = []
    for caller, pointer, callee in _call_context_frames(context):
        frames.append(
            {
                "caller": caller,
                "caller_module": program.definitions[caller]["owner"]["module"],
                "callee": callee,
                "callee_module": program.definitions[callee]["owner"]["module"],
                "call_site": pointer,
            }
        )
    return tuple(frames)


def _error(
    program: DynamicProgram,
    code: str,
    message: str,
    pointer: str,
    context: _Activation,
    steps: int,
    **metadata: Any,
) -> EvaluatedValueError:
    details: dict[str, Any] = {
        "steps": steps,
        "artifact_pointer": pointer,
        "call_context": _call_context_frames(context),
        "call_stack": _call_stack(program, context),
        **metadata,
    }
    source = program.source_map["entries"].get(pointer)
    if source is not None:
        details.update(
            module=source["source"],
            span=source["span"],
            form_path=source["form_path"],
        )
    return EvaluatedValueError(code, message, location=pointer, metadata=details)


def _workspace_path_validator(workspace_files: WorkspaceFiles | None):
    if workspace_files is None:
        def require_owner(_value: str, _descriptor: Mapping[str, Any]) -> str:
            raise ValueError("path boundary requires the pinned workspace file owner")

        return require_owner

    from orchestrator.contracts.output_contract import _require_nested_transport_path

    return lambda value, descriptor: _require_nested_transport_path(
        value,
        descriptor,
        workspace_files.workspace,
        workspace_files=workspace_files,
    )


def _boundary_value(
    program: DynamicProgram,
    value: Any,
    descriptor: Mapping[str, Any],
    pointer: str,
    context: _Activation,
    steps: int,
    workspace_files: WorkspaceFiles | None,
) -> Any:
    try:
        normalized = validate_transport_value(
            _thaw(value),
            descriptor,
            allow_nested_structures=True,
            require_int64=True,
            redact_runtime_keys=True,
            path_validator=_workspace_path_validator(workspace_files),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        field_path = getattr(exc, "value_path", None)
        details: dict[str, Any] = {"validator_error": str(exc)}
        if field_path is not None:
            details["field_path"] = field_path
        raise _error(
            program,
            "dynamic_boundary_invalid",
            "boundary value does not satisfy its declared schema",
            pointer,
            context,
            steps,
            **details,
        ) from None
    return _freeze(normalized)


def _definition_pointer(code: str) -> str:
    return _pointer("/definitions", code)


def _parameter_pointer(code: str, index: int) -> str:
    return _pointer(_pointer(_pointer(_pointer("/definitions", code), "boundary"), "params"), index)


def _default_pointer(code: str, name: str) -> str:
    return _pointer(_pointer(_pointer(_pointer("/definitions", code), "boundary"), "defaults"), name)


def _pop_values(values: list[Any], count: int) -> list[Any]:
    if count == 0:
        return []
    result = values[-count:]
    del values[-count:]
    return result


def _entry_environment(
    program: DynamicProgram,
    inputs: Mapping[str, Any],
    workspace_files: WorkspaceFiles | None,
) -> Mapping[str, Any]:
    definition = program.definitions[program.entry]
    boundary = definition["boundary"]
    code_pointer = _definition_pointer(program.entry)
    if not isinstance(inputs, Mapping):
        raise _error(
            program,
            "dynamic_boundary_invalid",
            "entry inputs must be an object",
            code_pointer,
            None,
            0,
        )
    parameters = boundary["params"]
    names = {row[0] for row in parameters}
    try:
        extra_count = len(set(inputs) - names)
    except (TypeError, ValueError):
        raise _error(
            program,
            "dynamic_boundary_invalid",
            "entry inputs must use declared parameter names",
            code_pointer,
            None,
            0,
        ) from None
    if extra_count:
        raise _error(
            program,
            "dynamic_boundary_invalid",
            "entry inputs contain undeclared parameters",
            code_pointer,
            None,
            0,
            extra_parameter_count=extra_count,
        )

    environment: dict[str, Any] = {}
    for index, (name, schema_ref) in enumerate(parameters):
        if name in inputs:
            value = inputs[name]
            pointer = _parameter_pointer(program.entry, index)
        elif name in boundary["defaults"]:
            value = boundary["defaults"][name]
            pointer = _default_pointer(program.entry, name)
        else:
            raise _error(
                program,
                "dynamic_boundary_invalid",
                "entry input is missing a required parameter",
                _parameter_pointer(program.entry, index),
                None,
                0,
                parameter=name,
            )
        environment[name] = _boundary_value(
            program,
            value,
            program.schemas[schema_ref],
            pointer,
            None,
            0,
            workspace_files,
        )
    return MappingProxyType(environment)


def bind_inputs(
    program: DynamicProgram,
    inputs: Mapping[str, Any],
    *,
    workspace_files: WorkspaceFiles | None = None,
) -> Mapping[str, Any]:
    """Bind defaults and strictly validate entry inputs without evaluating code."""
    if not isinstance(program, DynamicProgram):
        raise TypeError("program must be a checked DynamicProgram")
    if workspace_files is not None and not isinstance(workspace_files, WorkspaceFiles):
        raise TypeError("workspace_files must be a WorkspaceFiles owner or None")
    return _entry_environment(program, inputs, workspace_files)


def evaluate(
    program: DynamicProgram,
    inputs: Mapping[str, Any],
    *,
    workspace_files: WorkspaceFiles | None = None,
) -> EvaluationResult:
    """Evaluate one checked entry using the caller's optional workspace owner."""

    if not isinstance(program, DynamicProgram):
        raise TypeError("program must be a checked DynamicProgram")
    if workspace_files is not None and not isinstance(workspace_files, WorkspaceFiles):
        raise TypeError("workspace_files must be a WorkspaceFiles owner or None")

    entry = program.definitions[program.entry]
    boundary = entry["boundary"]
    environment = bind_inputs(program, inputs, workspace_files=workspace_files)
    result_pointer = _pointer(_pointer(_definition_pointer(program.entry), "boundary"), "result")
    tasks: list[tuple[Any, ...]] = [
        ("boundary_return", boundary["result"], result_pointer, None),
        (
            "enter",
            entry["body"],
            environment,
            _pointer(_definition_pointer(program.entry), "body"),
            program.entry,
            None,
        ),
    ]
    values: list[Any] = []
    steps = 0
    call_trace: list[_Frame] = []

    while tasks:
        task = tasks.pop()
        action = task[0]

        if action == "enter":
            _, node, env, pointer, code, context = task
            if steps >= program.budget:
                raise _error(
                    program,
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
                    except PureExprEvaluationError:
                        raise _error(
                            program,
                            "dynamic_operand_type",
                            "integer literal is outside the admitted range",
                            pointer,
                            context,
                            steps,
                        ) from None
                elif type(value) is float:
                    try:
                        value = coerce_pure_value(value, _FLOAT, context="literal")
                    except PureExprEvaluationError:
                        raise _error(
                            program,
                            "dynamic_operand_type",
                            "Float literal must be finite",
                            pointer,
                            context,
                            steps,
                        ) from None
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
            elif kind == "record-update":
                tasks.append(("record_update_base_done", node, env, pointer, code, context))
                tasks.append(("enter", node["base"], env, _pointer(pointer, "base"), code, context))
            elif kind == "perform":
                raise _error(
                    program,
                    "dynamic_effect_unsupported",
                    "direct dynamic effect execution is not available",
                    pointer,
                    context,
                    steps,
                )
            elif kind == "fail":
                raise _error(
                    program,
                    "dynamic_explicit_failure",
                    "dynamic program failed explicitly",
                    pointer,
                    context,
                    steps,
                    reason=node["reason"],
                )
            else:
                raise AssertionError(f"unadmitted dynamic node {kind!r}")
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
            updated = dict(env)
            updated[binder] = values.pop()
            tasks.append(("let_next", node, index + 1, MappingProxyType(updated), pointer, code, context))
            continue

        if action == "fn_done":
            _, target_code, count = task
            values.append(_Closure(target_code, tuple(_pop_values(values, count))))
            continue

        if action == "call_apply":
            _, count, pointer, caller_code, context = task
            evaluated = _pop_values(values, count + 1)
            callee, args = evaluated[0], evaluated[1:]
            if not isinstance(callee, _Closure):
                raise _error(
                    program,
                    "dynamic_not_callable",
                    f"call target has value kind {_kind(callee)}",
                    pointer,
                    context,
                    steps,
                    value_kind=_kind(callee),
                )
            definition = program.definitions[callee.code]
            parameters = definition["params"]
            boundary = definition["boundary"]
            defaults = {} if boundary is None else boundary["defaults"]
            frame = (caller_code, pointer, callee.code)
            activation = (context, frame)
            missing_required = any(name not in defaults for name in parameters[len(args):])
            if len(args) > len(parameters) or missing_required or (boundary is None and len(args) != len(parameters)):
                raise _error(
                    program,
                    "dynamic_call_arity",
                    "call argument count does not match the selected function",
                    pointer,
                    activation,
                    steps,
                    expected_arity=len(parameters),
                    observed_arity=len(args),
                )

            bound_args: list[Any] = []
            if boundary is None:
                bound_args.extend(args)
            else:
                for index, (name, schema_ref) in enumerate(boundary["params"]):
                    if index < len(args):
                        argument = args[index]
                        parameter_location = _parameter_pointer(callee.code, index)
                    else:
                        argument = defaults[name]
                        parameter_location = _default_pointer(callee.code, name)
                    bound_args.append(
                        _boundary_value(
                            program,
                            argument,
                            program.schemas[schema_ref],
                            parameter_location,
                            activation,
                            steps,
                            workspace_files,
                        )
                    )
            call_trace.append(frame)
            bindings = dict(zip(definition["captures"], callee.captures))
            bindings.update(zip(parameters, bound_args))
            if boundary is not None:
                result_pointer = _pointer(_pointer(_definition_pointer(callee.code), "boundary"), "result")
                tasks.append(("boundary_return", boundary["result"], result_pointer, activation))
            tasks.append(
                (
                    "enter",
                    definition["body"],
                    MappingProxyType(bindings),
                    _pointer(_definition_pointer(callee.code), "body"),
                    callee.code,
                    activation,
                )
            )
            continue

        if action == "boundary_return":
            _, schema_ref, pointer, context = task
            values.append(
                _boundary_value(
                    program,
                    values.pop(),
                    program.schemas[schema_ref],
                    pointer,
                    context,
                    steps,
                    workspace_files,
                )
            )
            continue

        if action == "if_done":
            _, node, env, pointer, code, context = task
            condition = values.pop()
            if type(condition) is not bool:
                raise _error(
                    program,
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
            values.append(MappingProxyType(dict(zip(fields, _pop_values(values, count)))))
            continue

        if action == "field_done":
            _, field_name, pointer, context = task
            base = values.pop()
            if not isinstance(base, Mapping):
                raise _error(
                    program,
                    "dynamic_operand_type",
                    f"field access requires a record or map, observed {_kind(base)}",
                    pointer,
                    context,
                    steps,
                    observed_kind=_kind(base),
                )
            if field_name not in base:
                raise _error(
                    program,
                    "dynamic_field_missing",
                    "record or map does not contain the requested field",
                    pointer,
                    context,
                    steps,
                    field=field_name,
                )
            values.append(base[field_name])
            continue

        if action == "record_update_base_done":
            _, node, env, pointer, code, context = task
            base = values.pop()
            if not isinstance(base, Mapping):
                raise _error(
                    program,
                    "dynamic_operand_type",
                    f"record update requires a record or map, observed {_kind(base)}",
                    pointer,
                    context,
                    steps,
                    observed_kind=_kind(base),
                )
            for index, (field_name, _replacement) in enumerate(node["fields"]):
                if field_name not in base:
                    raise _error(
                        program,
                        "dynamic_field_missing",
                        "record update cannot add a field absent from its base",
                        pointer,
                        context,
                        steps,
                        field=field_name,
                    )
            fields = node["fields"]
            tasks.append(("record_update_done", base, tuple(row[0] for row in fields), len(fields)))
            for index in reversed(range(len(fields))):
                tasks.append(
                    (
                        "enter",
                        fields[index][1],
                        env,
                        _pointer(_pointer(_pointer(pointer, "fields"), index), 1),
                        code,
                        context,
                    )
                )
            continue

        if action == "record_update_done":
            _, base, fields, count = task
            updated = dict(base)
            updated.update(zip(fields, _pop_values(values, count)))
            values.append(MappingProxyType(updated))
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
                    program,
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
                    program,
                    "dynamic_operand_type",
                    f"primitive {operator!r} received the wrong number of operands",
                    pointer,
                    context,
                    steps,
                    operator=operator,
                    expected_arity=[spec.min_arity, spec.max_arity],
                    observed_arity=count,
                )
            if operator in {"list/append", "list/length"}:
                base = args[0]
                if type(base) is not tuple:
                    raise _error(
                        program,
                        "dynamic_operand_type",
                        f"primitive {operator!r} requires a list operand",
                        pointer,
                        context,
                        steps,
                        operator=operator,
                        operand_kinds=[_kind(base)],
                    )
                if operator == "list/append":
                    values.append(base + (args[1],))
                else:
                    try:
                        values.append(coerce_pure_value(len(base), _INT, context="list length"))
                    except PureExprEvaluationError:
                        raise _error(
                            program,
                            "dynamic_operand_type",
                            "list length is outside the admitted Int range",
                            pointer,
                            context,
                            steps,
                            operator=operator,
                        ) from None
                continue
            descriptors = {"Bool": _BOOL, "Int": _INT, "Float": _FLOAT, "String": _STRING}
            kinds = [_kind(value) for value in args]
            if any(kind not in descriptors for kind in kinds):
                raise _error(
                    program,
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
                    [(descriptors[kind], value) for kind, value in zip(kinds, args)],
                )
            except PureExprEvaluationError as exc:
                code = "dynamic_operand_type" if exc.code == "pure_expr_operand_type_mismatch" else exc.code
                raise _error(
                    program,
                    code,
                    f"primitive {operator!r} refused operand kinds {kinds}",
                    pointer,
                    context,
                    steps,
                    operator=operator,
                    operand_kinds=kinds,
                ) from None
            values.append(result)
            continue

        raise AssertionError(f"unknown evaluator continuation {action!r}")

    if len(values) != 1:
        raise AssertionError("dynamic evaluator value stack is unbalanced")
    return EvaluationResult(values[0], steps, tuple(call_trace))


__all__ = ["EvaluationResult", "evaluate"]
