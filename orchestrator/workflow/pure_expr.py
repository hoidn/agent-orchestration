"""Closed pure-expression payload validation and evaluation.

This module is runtime-owned and intentionally independent from
``orchestrator.workflow_lisp`` so compile-time folding and runtime projection
execution share one authoritative implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any


PURE_EXPR_SCHEMA_VERSION = 1
DEFAULT_PURE_EXPR_MAX_NODES = 256
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


@dataclass(frozen=True)
class PureOperatorSpec:
    """One supported pure operator."""

    name: str
    group: str
    min_arity: int
    max_arity: int | None = None


PURE_EXPR_OPERATOR_CATALOG = MappingProxyType(
    {
        "=": PureOperatorSpec(name="=", group="equality", min_arity=2, max_arity=2),
        "!=": PureOperatorSpec(name="!=", group="equality", min_arity=2, max_arity=2),
        "<": PureOperatorSpec(name="<", group="ordering", min_arity=2, max_arity=2),
        "<=": PureOperatorSpec(name="<=", group="ordering", min_arity=2, max_arity=2),
        ">": PureOperatorSpec(name=">", group="ordering", min_arity=2, max_arity=2),
        ">=": PureOperatorSpec(name=">=", group="ordering", min_arity=2, max_arity=2),
        "and": PureOperatorSpec(name="and", group="boolean", min_arity=2),
        "or": PureOperatorSpec(name="or", group="boolean", min_arity=2),
        "not": PureOperatorSpec(name="not", group="boolean", min_arity=1, max_arity=1),
        "+": PureOperatorSpec(name="+", group="arithmetic", min_arity=2),
        "-": PureOperatorSpec(name="-", group="arithmetic", min_arity=2, max_arity=2),
        "*": PureOperatorSpec(name="*", group="arithmetic", min_arity=2),
        "min": PureOperatorSpec(name="min", group="arithmetic", min_arity=2),
        "max": PureOperatorSpec(name="max", group="arithmetic", min_arity=2),
        "string/concat": PureOperatorSpec(name="string/concat", group="string", min_arity=2),
        "string/empty?": PureOperatorSpec(name="string/empty?", group="string", min_arity=1, max_arity=1),
        "symbol/name": PureOperatorSpec(name="symbol/name", group="string", min_arity=1, max_arity=1),
        "some?": PureOperatorSpec(name="some?", group="option", min_arity=1, max_arity=1),
        "or-else": PureOperatorSpec(name="or-else", group="option", min_arity=2, max_arity=2),
        "record-update": PureOperatorSpec(name="record-update", group="record", min_arity=2),
    }
)


class PureExprEvaluationError(ValueError):
    """Raised when one pure-expression payload cannot be evaluated."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = dict(metadata or {})
        self.source = source


def canonical_json_for_pure_value(value: Any) -> str:
    """Return deterministic canonical JSON for one pure runtime value."""

    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json_for_pure_payload(payload: Mapping[str, Any]) -> str:
    """Return deterministic canonical JSON for one pure-expression payload."""

    return canonical_json_for_pure_value(payload)


def pure_expr_payload_digest(payload: Mapping[str, Any]) -> str:
    """Return a stable digest for one validated payload."""

    return f"sha256:{sha256(canonical_json_for_pure_payload(payload).encode('utf-8')).hexdigest()}"


def validate_pure_expr_payload(
    payload: Mapping[str, Any],
    *,
    max_nodes: int = DEFAULT_PURE_EXPR_MAX_NODES,
) -> Mapping[str, Any]:
    """Validate one pure-expression payload and raise on structural violations."""

    if not isinstance(payload, Mapping):
        _raise("pure_expr_payload_invalid", "pure-expression payload must be a mapping")
    if payload.get("pure_expr_schema_version") != PURE_EXPR_SCHEMA_VERSION:
        _raise(
            "pure_expr_schema_mismatch",
            "unsupported pure-expression schema version",
            metadata={
                "observed": payload.get("pure_expr_schema_version"),
                "expected": PURE_EXPR_SCHEMA_VERSION,
            },
        )

    result_type = payload.get("result_type")
    _validate_type_descriptor(result_type, context="payload.result_type")

    bindings = payload.get("bindings")
    if not isinstance(bindings, Mapping):
        _raise("pure_expr_payload_invalid", "pure-expression payload bindings must be a mapping")
    for name, spec in bindings.items():
        if not isinstance(name, str) or not name:
            _raise("pure_expr_payload_invalid", "pure-expression binding names must be non-empty strings")
        if not isinstance(spec, Mapping):
            _raise("pure_expr_payload_invalid", f"binding `{name}` must be a mapping")
        _validate_type_descriptor(spec.get("type"), context=f"bindings.{name}.type")
        if "value" in spec:
            _coerce_value(spec["value"], spec["type"], context=f"bindings.{name}.value")

    expr = payload.get("expr")
    node_count = _validate_expr_node(expr, bindings=bindings)
    if node_count > max_nodes:
        _raise(
            "pure_expr_payload_too_large",
            "pure-expression payload exceeds the maximum node count",
            metadata={"node_count": node_count, "max_nodes": max_nodes},
        )
    return payload


def evaluate_pure_expr(
    payload: Mapping[str, Any],
    *,
    resolved_bindings: Mapping[str, Any] | None = None,
    max_nodes: int = DEFAULT_PURE_EXPR_MAX_NODES,
) -> Any:
    """Evaluate one validated pure-expression payload."""

    validate_pure_expr_payload(payload, max_nodes=max_nodes)
    bindings = payload["bindings"]
    resolved = dict(resolved_bindings or {})
    for name in resolved:
        if name not in bindings:
            _raise(
                "pure_expr_binding_unexpected",
                f"unexpected resolved binding `{name}`",
                metadata={"binding": name},
            )

    result_type, result_value = _evaluate_expr(
        payload["expr"],
        bindings=bindings,
        resolved_bindings=resolved,
    )
    expected_type = payload["result_type"]
    if _descriptor_key(result_type) != _descriptor_key(expected_type):
        _raise(
            "pure_expr_payload_invalid",
            "pure-expression result type does not match the declared payload result type",
            metadata={
                "observed": result_type,
                "expected": expected_type,
            },
        )
    return _coerce_value(result_value, expected_type, context="result")


def _raise(code: str, message: str, *, metadata: Mapping[str, Any] | None = None) -> None:
    raise PureExprEvaluationError(code, message, metadata=metadata)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _descriptor_key(descriptor: Mapping[str, Any]) -> str:
    return canonical_json_for_pure_value(descriptor)


def _descriptor_kind(descriptor: Mapping[str, Any]) -> str:
    kind = descriptor.get("kind")
    if not isinstance(kind, str) or not kind:
        _raise("pure_expr_payload_invalid", "type descriptors must declare a non-empty `kind`")
    return kind


def _validate_type_descriptor(descriptor: Any, *, context: str) -> None:
    if not isinstance(descriptor, Mapping):
        _raise("pure_expr_payload_invalid", f"{context} must be a mapping type descriptor")

    kind = _descriptor_kind(descriptor)
    if kind == "primitive":
        name = descriptor.get("name")
        if not isinstance(name, str) or not name:
            _raise("pure_expr_payload_invalid", f"{context}.name must be a non-empty string")
        return

    if kind == "enum":
        if not isinstance(descriptor.get("name"), str) or not descriptor.get("name"):
            _raise("pure_expr_payload_invalid", f"{context}.name must be a non-empty string")
        allowed = descriptor.get("allowed")
        if not isinstance(allowed, list) or not allowed or any(not isinstance(item, str) for item in allowed):
            _raise("pure_expr_payload_invalid", f"{context}.allowed must be a non-empty string list")
        return

    if kind == "path":
        if not isinstance(descriptor.get("name"), str) or not descriptor.get("name"):
            _raise("pure_expr_payload_invalid", f"{context}.name must be a non-empty string")
        return

    if kind == "optional":
        _validate_type_descriptor(descriptor.get("item"), context=f"{context}.item")
        return

    if kind == "list":
        _validate_type_descriptor(descriptor.get("item"), context=f"{context}.item")
        return

    if kind == "map":
        _validate_type_descriptor(descriptor.get("key"), context=f"{context}.key")
        _validate_type_descriptor(descriptor.get("value"), context=f"{context}.value")
        return

    if kind == "record":
        _validate_field_descriptor_list(descriptor.get("fields"), context=f"{context}.fields")
        return

    if kind == "union":
        variants = descriptor.get("variants")
        if not isinstance(variants, list) or not variants:
            _raise("pure_expr_payload_invalid", f"{context}.variants must be a non-empty list")
        seen: set[str] = set()
        for index, variant in enumerate(variants):
            if not isinstance(variant, Mapping):
                _raise("pure_expr_payload_invalid", f"{context}.variants[{index}] must be a mapping")
            name = variant.get("name")
            if not isinstance(name, str) or not name:
                _raise("pure_expr_payload_invalid", f"{context}.variants[{index}].name must be a non-empty string")
            if name in seen:
                _raise("pure_expr_payload_invalid", f"{context}.variants declares duplicate variant `{name}`")
            seen.add(name)
            _validate_field_descriptor_list(variant.get("fields"), context=f"{context}.variants[{index}].fields")
        return

    if kind == "variant_case":
        if not isinstance(descriptor.get("union_name"), str) or not descriptor.get("union_name"):
            _raise("pure_expr_payload_invalid", f"{context}.union_name must be a non-empty string")
        if not isinstance(descriptor.get("variant"), str) or not descriptor.get("variant"):
            _raise("pure_expr_payload_invalid", f"{context}.variant must be a non-empty string")
        _validate_field_descriptor_list(descriptor.get("fields"), context=f"{context}.fields")
        return

    _raise("pure_expr_payload_invalid", f"{context} uses unsupported kind `{kind}`")


def _validate_field_descriptor_list(fields: Any, *, context: str) -> None:
    if not isinstance(fields, list):
        _raise("pure_expr_payload_invalid", f"{context} must be a list")
    seen: set[str] = set()
    for index, field in enumerate(fields):
        if not isinstance(field, Mapping):
            _raise("pure_expr_payload_invalid", f"{context}[{index}] must be a mapping")
        name = field.get("name")
        if not isinstance(name, str) or not name:
            _raise("pure_expr_payload_invalid", f"{context}[{index}].name must be a non-empty string")
        if name in seen:
            _raise("pure_expr_payload_invalid", f"{context} declares duplicate field `{name}`")
        seen.add(name)
        _validate_type_descriptor(field.get("type"), context=f"{context}[{index}].type")


def _validate_expr_node(node: Any, *, bindings: Mapping[str, Any]) -> int:
    if not isinstance(node, Mapping):
        _raise("pure_expr_payload_invalid", "pure-expression nodes must be mappings")
    kind = node.get("kind")
    if not isinstance(kind, str) or not kind:
        _raise("pure_expr_payload_invalid", "pure-expression nodes must declare a non-empty `kind`")

    count = 1
    if kind == "literal":
        _validate_type_descriptor(node.get("type"), context="expr.type")
        _coerce_value(node.get("value"), node["type"], context="expr.value")
        return count

    if kind == "binding":
        name = node.get("name")
        if not isinstance(name, str) or not name:
            _raise("pure_expr_payload_invalid", "binding nodes must declare a non-empty `name`")
        if name not in bindings:
            _raise(
                "pure_expr_payload_invalid",
                f"binding node references unknown binding `{name}`",
                metadata={"binding": name},
            )
        return count

    if kind == "field_access":
        field = node.get("field")
        if not isinstance(field, str) or not field:
            _raise("pure_expr_payload_invalid", "field_access nodes must declare a non-empty `field`")
        return count + _validate_expr_node(node.get("base"), bindings=bindings)

    if kind == "if":
        return (
            count
            + _validate_expr_node(node.get("condition"), bindings=bindings)
            + _validate_expr_node(node.get("then"), bindings=bindings)
            + _validate_expr_node(node.get("else"), bindings=bindings)
        )

    if kind == "record":
        _validate_type_descriptor(node.get("type"), context="expr.type")
        if _descriptor_kind(node["type"]) != "record":
            _raise("pure_expr_payload_invalid", "record nodes require a record type descriptor")
        fields = node.get("fields")
        if not isinstance(fields, list):
            _raise("pure_expr_payload_invalid", "record nodes must declare a `fields` list")
        for field in fields:
            if not isinstance(field, Mapping):
                _raise("pure_expr_payload_invalid", "record node fields must be mappings")
            count += _validate_expr_node(field.get("value"), bindings=bindings)
        return count

    if kind == "union":
        _validate_type_descriptor(node.get("type"), context="expr.type")
        if _descriptor_kind(node["type"]) not in {"union", "variant_case"}:
            _raise("pure_expr_payload_invalid", "union nodes require a union or variant_case descriptor")
        if not isinstance(node.get("variant"), str) or not node.get("variant"):
            _raise("pure_expr_payload_invalid", "union nodes must declare a non-empty `variant`")
        fields = node.get("fields")
        if not isinstance(fields, list):
            _raise("pure_expr_payload_invalid", "union nodes must declare a `fields` list")
        for field in fields:
            if not isinstance(field, Mapping):
                _raise("pure_expr_payload_invalid", "union node fields must be mappings")
            count += _validate_expr_node(field.get("value"), bindings=bindings)
        return count

    if kind == "record_update":
        _validate_type_descriptor(node.get("record_type"), context="expr.record_type")
        if _descriptor_kind(node["record_type"]) != "record":
            _raise("pure_expr_payload_invalid", "record_update nodes require a record_type descriptor")
        count += _validate_expr_node(node.get("base"), bindings=bindings)
        fields = node.get("fields")
        if not isinstance(fields, list) or not fields:
            _raise("pure_expr_payload_invalid", "record_update nodes must declare a non-empty `fields` list")
        for field in fields:
            if not isinstance(field, Mapping):
                _raise("pure_expr_payload_invalid", "record_update fields must be mappings")
            if not isinstance(field.get("name"), str) or not field.get("name"):
                _raise("pure_expr_payload_invalid", "record_update fields must declare a non-empty `name`")
            count += _validate_expr_node(field.get("value"), bindings=bindings)
        return count

    if kind == "op":
        operator = node.get("operator")
        if not isinstance(operator, str) or not operator:
            _raise("pure_expr_payload_invalid", "op nodes must declare a non-empty `operator`")
        spec = PURE_EXPR_OPERATOR_CATALOG.get(operator)
        if spec is None:
            _raise(
                "pure_expr_operator_unsupported",
                f"unsupported pure operator `{operator}`",
                metadata={"operator": operator},
            )
        args = node.get("args")
        if not isinstance(args, list):
            _raise("pure_expr_payload_invalid", f"operator `{operator}` args must be a list")
        if len(args) < spec.min_arity or (spec.max_arity is not None and len(args) > spec.max_arity):
            _raise(
                "pure_expr_payload_invalid",
                f"operator `{operator}` received an unsupported arity",
                metadata={
                    "operator": operator,
                    "arity": len(args),
                    "min_arity": spec.min_arity,
                    "max_arity": spec.max_arity,
                },
            )
        for arg in args:
            count += _validate_expr_node(arg, bindings=bindings)
        return count

    _raise("pure_expr_payload_invalid", f"unsupported pure-expression node kind `{kind}`")


def _evaluate_expr(
    node: Mapping[str, Any],
    *,
    bindings: Mapping[str, Any],
    resolved_bindings: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Any]:
    kind = node["kind"]
    if kind == "literal":
        descriptor = node["type"]
        return descriptor, _coerce_value(node.get("value"), descriptor, context="literal")

    if kind == "binding":
        name = node["name"]
        spec = bindings[name]
        if name in resolved_bindings:
            raw_value = resolved_bindings[name]
        elif "value" in spec:
            raw_value = spec["value"]
        else:
            _raise(
                "pure_expr_binding_missing",
                f"missing resolved value for binding `{name}`",
                metadata={"binding": name},
            )
        descriptor = spec["type"]
        return descriptor, _coerce_value(raw_value, descriptor, context=f"binding `{name}`")

    if kind == "field_access":
        base_type, base_value = _evaluate_expr(
            node["base"],
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        field_name = node["field"]
        field_type = _field_type(base_type, field_name)
        if base_value is None:
            _raise(
                "pure_expr_optional_access_unproved",
                f"field `{field_name}` requires a present optional value",
                metadata={"field": field_name},
            )
        if not isinstance(base_value, Mapping):
            _raise(
                "pure_expr_operand_type_mismatch",
                f"field access requires a record or variant value, got `{_type_label(base_type)}`",
                metadata={"field": field_name},
            )
        if field_name not in base_value:
            _raise(
                "pure_expr_operand_type_mismatch",
                f"field `{field_name}` is unavailable on `{_type_label(base_type)}`",
                metadata={"field": field_name},
            )
        return field_type, _coerce_value(base_value[field_name], field_type, context=f"field `{field_name}`")

    if kind == "if":
        condition_type, condition_value = _evaluate_expr(
            node["condition"],
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        _require_primitive(condition_type, "Bool", operator="if")
        branch_key = "then" if condition_value else "else"
        branch_type, branch_value = _evaluate_expr(
            node[branch_key],
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        other_type, _ = _evaluate_expr(
            node["else" if branch_key == "then" else "then"],
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        if _descriptor_key(branch_type) != _descriptor_key(other_type):
            _raise(
                "pure_expr_operand_type_mismatch",
                "`if` branches must return the same type",
                metadata={"then_type": branch_type, "else_type": other_type},
            )
        return branch_type, branch_value

    if kind == "record":
        descriptor = node["type"]
        result = _evaluate_record_fields(
            descriptor,
            node.get("fields", []),
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        return descriptor, result

    if kind == "union":
        descriptor = node["type"]
        variant_name = node["variant"]
        variant_descriptor = _variant_descriptor(descriptor, variant_name)
        field_values = _evaluate_record_fields(
            {
                "kind": "record",
                "name": f"{variant_name}Payload",
                "fields": variant_descriptor["fields"],
            },
            node.get("fields", []),
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        value: dict[str, Any] = {"variant": variant_name}
        value.update(field_values)
        if _descriptor_kind(descriptor) == "variant_case":
            return descriptor, value
        return descriptor, _coerce_value(value, descriptor, context=f"union `{variant_name}`")

    if kind == "record_update":
        descriptor = node["record_type"]
        base_type, base_value = _evaluate_expr(
            node["base"],
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        if _descriptor_key(base_type) != _descriptor_key(descriptor):
            _raise(
                "pure_expr_operand_type_mismatch",
                "record-update base value type does not match the declared record_type",
                metadata={"base_type": base_type, "record_type": descriptor},
            )
        record_value = _coerce_value(base_value, descriptor, context="record_update.base")
        field_lookup = {field["name"]: field["type"] for field in descriptor["fields"]}
        result = dict(record_value)
        for field_update in node["fields"]:
            field_name = field_update["name"]
            field_type = field_lookup.get(field_name)
            if field_type is None:
                _raise(
                    "record_field_unknown",
                    f"unknown record-update field `{field_name}`",
                    metadata={"field": field_name},
                )
            _, updated_value = _evaluate_expr(
                field_update["value"],
                bindings=bindings,
                resolved_bindings=resolved_bindings,
            )
            result[field_name] = _coerce_value(updated_value, field_type, context=f"record_update.{field_name}")
        return descriptor, result

    if kind == "op":
        evaluated_args = [
            _evaluate_expr(arg, bindings=bindings, resolved_bindings=resolved_bindings)
            for arg in node["args"]
        ]
        return _evaluate_operator(node["operator"], evaluated_args)

    _raise("pure_expr_payload_invalid", f"unsupported pure-expression node kind `{kind}`")


def _evaluate_record_fields(
    descriptor: Mapping[str, Any],
    authored_fields: list[Any],
    *,
    bindings: Mapping[str, Any],
    resolved_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(authored_fields, list):
        _raise("pure_expr_payload_invalid", "record-like nodes must declare a field list")
    authored_lookup: dict[str, Mapping[str, Any]] = {}
    for field in authored_fields:
        if not isinstance(field, Mapping):
            _raise("pure_expr_payload_invalid", "record-like fields must be mappings")
        field_name = field.get("name")
        if not isinstance(field_name, str) or not field_name:
            _raise("pure_expr_payload_invalid", "record-like fields require a non-empty `name`")
        if field_name in authored_lookup:
            _raise("pure_expr_payload_invalid", f"duplicate record field `{field_name}`")
        authored_lookup[field_name] = field

    result: dict[str, Any] = {}
    expected_names = []
    for field in descriptor["fields"]:
        field_name = field["name"]
        expected_names.append(field_name)
        if field_name not in authored_lookup:
            _raise(
                "pure_expr_payload_invalid",
                f"missing record field `{field_name}`",
                metadata={"field": field_name},
            )
        _, field_value = _evaluate_expr(
            authored_lookup[field_name]["value"],
            bindings=bindings,
            resolved_bindings=resolved_bindings,
        )
        result[field_name] = _coerce_value(field_value, field["type"], context=f"field `{field_name}`")

    extra = sorted(set(authored_lookup) - set(expected_names))
    if extra:
        _raise(
            "pure_expr_payload_invalid",
            f"unexpected record fields: {', '.join(extra)}",
            metadata={"fields": extra},
        )
    return result


def _evaluate_operator(
    operator: str,
    evaluated_args: list[tuple[Mapping[str, Any], Any]],
) -> tuple[Mapping[str, Any], Any]:
    arg_types = [arg_type for arg_type, _ in evaluated_args]
    arg_values = [arg_value for _, arg_value in evaluated_args]

    if operator in {"=", "!="}:
        left_type, right_type = arg_types
        left_value, right_value = arg_values
        if _is_float_type(left_type) or _is_float_type(right_type):
            _raise("pure_expr_float_equality_forbidden", "float equality is not supported")
        if _is_union_like(left_type) or _is_union_like(right_type):
            _raise("pure_expr_union_equality_forbidden", "union equality is not supported")
        if _descriptor_key(left_type) != _descriptor_key(right_type) or not _type_supports_equality(left_type):
            _raise(
                "pure_expr_operand_type_mismatch",
                f"operator `{operator}` requires equal comparable operand types",
            )
        return _bool_type(), (left_value == right_value if operator == "=" else left_value != right_value)

    if operator in {"<", "<=", ">", ">="}:
        left_type, right_type = arg_types
        left_value, right_value = arg_values
        if _descriptor_key(left_type) != _descriptor_key(right_type):
            _raise("pure_expr_operand_type_mismatch", f"operator `{operator}` requires matching operand types")
        if _is_primitive_type(left_type, "Int"):
            pass
        elif _is_primitive_type(left_type, "Float"):
            pass
        else:
            _raise("pure_expr_operand_type_mismatch", f"operator `{operator}` requires Int or Float operands")
        operations = {
            "<": left_value < right_value,
            "<=": left_value <= right_value,
            ">": left_value > right_value,
            ">=": left_value >= right_value,
        }
        return _bool_type(), operations[operator]

    if operator == "and":
        for arg_type in arg_types:
            _require_primitive(arg_type, "Bool", operator=operator)
        return _bool_type(), all(arg_values)

    if operator == "or":
        for arg_type in arg_types:
            _require_primitive(arg_type, "Bool", operator=operator)
        return _bool_type(), any(arg_values)

    if operator == "not":
        _require_primitive(arg_types[0], "Bool", operator=operator)
        return _bool_type(), not arg_values[0]

    if operator in {"+", "-", "*", "min", "max"}:
        for arg_type in arg_types:
            _require_primitive(arg_type, "Int", operator=operator)
        if operator == "+":
            total = 0
            for value in arg_values:
                total = _checked_int(total + value)
            return _int_type(), total
        if operator == "-":
            return _int_type(), _checked_int(arg_values[0] - arg_values[1])
        if operator == "*":
            total = 1
            for value in arg_values:
                total = _checked_int(total * value)
            return _int_type(), total
        if operator == "min":
            return _int_type(), min(arg_values)
        return _int_type(), max(arg_values)

    if operator == "string/concat":
        for arg_type in arg_types:
            if _is_path_type(arg_type):
                _raise("pure_expr_path_string_concat_forbidden", "path string concatenation is forbidden")
            _require_primitive(arg_type, "String", operator=operator)
        return _string_type(), "".join(arg_values)

    if operator == "string/empty?":
        _require_primitive(arg_types[0], "String", operator=operator)
        return _bool_type(), arg_values[0] == ""

    if operator == "symbol/name":
        _require_primitive(arg_types[0], "Symbol", operator=operator)
        return _string_type(), arg_values[0]

    if operator == "some?":
        if _descriptor_kind(arg_types[0]) != "optional":
            _raise("pure_expr_operand_type_mismatch", "`some?` requires an Optional operand")
        return _bool_type(), arg_values[0] is not None

    if operator == "or-else":
        optional_type = arg_types[0]
        fallback_type = arg_types[1]
        if _descriptor_kind(optional_type) != "optional":
            _raise("pure_expr_operand_type_mismatch", "`or-else` requires an Optional first operand")
        item_type = optional_type["item"]
        if _descriptor_key(item_type) != _descriptor_key(fallback_type):
            _raise("pure_expr_operand_type_mismatch", "`or-else` fallback type must match the optional item type")
        return item_type, arg_values[0] if arg_values[0] is not None else arg_values[1]

    _raise(
        "pure_expr_operator_unsupported",
        f"unsupported pure operator `{operator}`",
        metadata={"operator": operator},
    )


def _coerce_value(value: Any, descriptor: Mapping[str, Any], *, context: str) -> Any:
    kind = _descriptor_kind(descriptor)

    if kind == "primitive":
        name = descriptor["name"]
        if name == "Bool":
            if type(value) is not bool:
                _raise("pure_expr_operand_type_mismatch", f"{context} must be Bool")
            return value
        if name == "Int":
            if type(value) is not int:
                _raise("pure_expr_operand_type_mismatch", f"{context} must be Int")
            return _checked_int(value)
        if name == "Float":
            if type(value) is bool or not isinstance(value, float):
                _raise("pure_expr_operand_type_mismatch", f"{context} must be Float")
            return value
        if name in {"String", "Symbol", "PathRel", "RunId", "Json"}:
            if name == "Json":
                canonical_json_for_pure_value(value)
                return _jsonable(value)
            if not isinstance(value, str):
                _raise("pure_expr_operand_type_mismatch", f"{context} must be {name}")
            return value
        if not isinstance(value, str):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be {name}")
        return value

    if kind == "enum":
        if not isinstance(value, str):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be enum `{descriptor['name']}`")
        if value not in descriptor["allowed"]:
            _raise(
                "pure_expr_operand_type_mismatch",
                f"{context} must be one of `{descriptor['allowed']}`",
                metadata={"allowed": descriptor["allowed"], "value": value},
            )
        return value

    if kind == "path":
        if not isinstance(value, str):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be path `{descriptor['name']}`")
        return value

    if kind == "optional":
        if value is None:
            return None
        return _coerce_value(value, descriptor["item"], context=context)

    if kind == "list":
        if not isinstance(value, (list, tuple)):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be a list")
        return [_coerce_value(item, descriptor["item"], context=f"{context}[]") for item in value]

    if kind == "map":
        if not isinstance(value, Mapping):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be a map")
        return {
            _coerce_value(key, descriptor["key"], context=f"{context}.key"): _coerce_value(
                item,
                descriptor["value"],
                context=f"{context}[{key!r}]",
            )
            for key, item in value.items()
        }

    if kind == "record":
        if not isinstance(value, Mapping):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be record `{descriptor.get('name', '')}`")
        result: dict[str, Any] = {}
        expected_names = [field["name"] for field in descriptor["fields"]]
        for field in descriptor["fields"]:
            field_name = field["name"]
            if field_name not in value:
                _raise("pure_expr_operand_type_mismatch", f"{context} is missing record field `{field_name}`")
            result[field_name] = _coerce_value(value[field_name], field["type"], context=f"{context}.{field_name}")
        extra = sorted(set(value) - set(expected_names))
        if extra:
            _raise("pure_expr_operand_type_mismatch", f"{context} has unexpected record fields: {', '.join(extra)}")
        return result

    if kind in {"union", "variant_case"}:
        if not isinstance(value, Mapping):
            _raise("pure_expr_operand_type_mismatch", f"{context} must be a union value")
        variant_name = value.get("variant")
        if not isinstance(variant_name, str) or not variant_name:
            _raise("pure_expr_operand_type_mismatch", f"{context} must declare a string `variant`")
        variant_descriptor = _variant_descriptor(descriptor, variant_name)
        if kind == "variant_case" and variant_name != descriptor["variant"]:
            _raise(
                "pure_expr_operand_type_mismatch",
                f"{context} must carry variant `{descriptor['variant']}`",
                metadata={"observed_variant": variant_name},
            )
        result: dict[str, Any] = {"variant": variant_name}
        expected_names = [field["name"] for field in variant_descriptor["fields"]]
        for field in variant_descriptor["fields"]:
            field_name = field["name"]
            if field_name not in value:
                _raise("pure_expr_operand_type_mismatch", f"{context} is missing variant field `{field_name}`")
            result[field_name] = _coerce_value(value[field_name], field["type"], context=f"{context}.{field_name}")
        extra = sorted(set(value) - set(expected_names) - {"variant"})
        if extra:
            _raise("pure_expr_operand_type_mismatch", f"{context} has unexpected variant fields: {', '.join(extra)}")
        return result

    _raise("pure_expr_payload_invalid", f"{context} uses unsupported type kind `{kind}`")


def _field_type(descriptor: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    kind = _descriptor_kind(descriptor)
    if kind == "record":
        for field in descriptor["fields"]:
            if field["name"] == field_name:
                return field["type"]
        _raise("record_field_unknown", f"unknown record field `{field_name}`", metadata={"field": field_name})
    if kind == "variant_case":
        if field_name == "variant":
            return {"kind": "enum", "name": descriptor["union_name"], "allowed": [descriptor["variant"]]}
        for field in descriptor["fields"]:
            if field["name"] == field_name:
                return field["type"]
        _raise("pure_expr_operand_type_mismatch", f"field `{field_name}` is unavailable on variant `{descriptor['variant']}`")
    if kind == "union":
        if field_name == "variant":
            return {
                "kind": "enum",
                "name": descriptor["name"],
                "allowed": [variant["name"] for variant in descriptor["variants"]],
            }
        _raise("pure_expr_operand_type_mismatch", f"field `{field_name}` requires variant proof")
    if kind == "optional":
        _raise(
            "pure_expr_optional_access_unproved",
            f"field `{field_name}` requires proof that the optional base is present",
        )
    _raise("pure_expr_operand_type_mismatch", f"field access is unsupported on `{_type_label(descriptor)}`")


def _variant_descriptor(descriptor: Mapping[str, Any], variant_name: str) -> Mapping[str, Any]:
    kind = _descriptor_kind(descriptor)
    if kind == "variant_case":
        if descriptor["variant"] != variant_name:
            _raise(
                "pure_expr_operand_type_mismatch",
                f"expected variant `{descriptor['variant']}` but got `{variant_name}`",
            )
        return descriptor
    for variant in descriptor["variants"]:
        if variant["name"] == variant_name:
            return variant
    _raise(
        "pure_expr_operand_type_mismatch",
        f"union `{descriptor['name']}` does not declare variant `{variant_name}`",
        metadata={"variant": variant_name},
    )


def _type_supports_equality(descriptor: Mapping[str, Any]) -> bool:
    if _descriptor_kind(descriptor) == "enum":
        return True
    return any(
        _is_primitive_type(descriptor, primitive_name)
        for primitive_name in ("String", "Int", "Bool", "Symbol")
    )


def _is_primitive_type(descriptor: Mapping[str, Any], name: str) -> bool:
    return _descriptor_kind(descriptor) == "primitive" and descriptor.get("name") == name


def _is_float_type(descriptor: Mapping[str, Any]) -> bool:
    return _is_primitive_type(descriptor, "Float")


def _is_path_type(descriptor: Mapping[str, Any]) -> bool:
    return _descriptor_kind(descriptor) == "path"


def _is_union_like(descriptor: Mapping[str, Any]) -> bool:
    return _descriptor_kind(descriptor) in {"union", "variant_case"}


def _require_primitive(descriptor: Mapping[str, Any], primitive_name: str, *, operator: str) -> None:
    if not _is_primitive_type(descriptor, primitive_name):
        _raise(
            "pure_expr_operand_type_mismatch",
            f"operator `{operator}` requires {primitive_name} operands",
            metadata={"observed_type": descriptor},
        )


def _checked_int(value: int) -> int:
    if value < INT64_MIN or value > INT64_MAX:
        _raise(
            "pure_expr_overflow",
            "pure-expression integer arithmetic overflowed 64-bit bounds",
            metadata={"min": INT64_MIN, "max": INT64_MAX, "value": value},
        )
    return value


def _bool_type() -> Mapping[str, Any]:
    return {"kind": "primitive", "name": "Bool"}


def _int_type() -> Mapping[str, Any]:
    return {"kind": "primitive", "name": "Int"}


def _string_type() -> Mapping[str, Any]:
    return {"kind": "primitive", "name": "String"}


def _type_label(descriptor: Mapping[str, Any]) -> str:
    kind = _descriptor_kind(descriptor)
    if kind == "primitive":
        return str(descriptor["name"])
    if kind == "enum":
        return str(descriptor["name"])
    if kind == "path":
        return str(descriptor["name"])
    if kind == "optional":
        return f"Optional[{_type_label(descriptor['item'])}]"
    if kind == "list":
        return f"List[{_type_label(descriptor['item'])}]"
    if kind == "map":
        return f"Map[{_type_label(descriptor['key'])}, {_type_label(descriptor['value'])}]"
    if kind == "record":
        return str(descriptor.get("name", "Record"))
    if kind == "union":
        return str(descriptor.get("name", "Union"))
    if kind == "variant_case":
        return f"{descriptor['union_name']}.{descriptor['variant']}"
    return kind
