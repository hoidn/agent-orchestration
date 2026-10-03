"""Strict admission for the isolated dynamic-core JSON experiment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from types import MappingProxyType
from typing import Any

from orchestrator.contracts.output_contract import strict_json_loads
from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow.type_descriptor import (
    is_transportable_type_descriptor,
    validate_compiler_normalized_type_descriptor,
)
from orchestrator.workflow_lisp.closed.program import canonical_digest


SCHEMA = "workflow-lisp/dynamic-spike/1"
EFFECT_SCHEMA = "workflow-lisp/dynamic-spike/2"
DYNAMIC_SCHEMA = "workflow-lisp/dynamic-spike/3"
_TOP_FIELDS = {"schema", "entry", "budget", "schemas", "inputs", "result", "definitions"}
_EFFECT_TOP_FIELDS = _TOP_FIELDS | {"effects"}
_OPERATORS = {"+", "-", "*", "/", "<", "<=", ">", ">=", "=", "!=", "not", "string/concat", "string/empty?"}
DYNAMIC_OPERATORS = {"list/append", "list/length"}
_NODE_FIELDS = {
    "lit": {"v"},
    "name": {"n"},
    "let": {"bindings", "body"},
    "fn": {"code", "captures"},
    "call": {"callee", "args"},
    "if": {"cond", "then", "else"},
    "record": {"fields"},
    "field": {"base", "name"},
    "list": {"items"},
    "at": {"base", "index"},
    "op": {"name", "args"},
    "effect": {"name", "inputs"},
}
_DYNAMIC_NODE_FIELDS = {
    "record-update": {"base", "fields"},
    "fail": {"reason"},
}
_PRIMITIVES = {"Bool", "Int", "Float", "String", "Value"}


def _invalid(message: str, location: str = "") -> EvaluatedValueError:
    return EvaluatedValueError(
        "dynamic_spike_invalid",
        message,
        location=location or None,
    )


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(f"{context} must be a non-empty string")
    return value


def _sequence(value: Any, context: str) -> list[Any]:
    if type(value) is not list:
        raise _invalid(f"{context} must be an array")
    return value


def _pointer(pointer: str, token: str | int) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class DynamicProgram:
    tree: Mapping[str, Any]
    entry: str
    budget: int
    schemas: Mapping[str, Mapping[str, Any]]
    inputs: tuple[tuple[str, str], ...]
    result: str
    definitions: Mapping[str, Mapping[str, Any]]
    digest: str
    _canonical_artifact: str
    effects: tuple[str, ...] = ()
    schema: str = SCHEMA

    @classmethod
    def from_artifact(cls, text: str) -> DynamicProgram:
        try:
            raw = strict_json_loads(text)
            if type(raw) is not dict:
                raise _invalid("artifact must be a JSON object")
            _validate_artifact(raw)
            canonical = json.dumps(
                raw,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            digest = canonical_digest(raw)
            frozen = _freeze(raw)
        except EvaluatedValueError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise _invalid(f"invalid strict JSON artifact: {exc}") from exc

        return cls(
            tree=frozen,
            entry=raw["entry"],
            budget=raw["budget"],
            schemas=frozen["schemas"],
            inputs=tuple(tuple(row) for row in raw["inputs"]),
            result=raw["result"],
            definitions=frozen["definitions"],
            digest=digest,
            _canonical_artifact=canonical + "\n",
            effects=tuple(raw.get("effects", ())),
            schema=raw["schema"],
        )

    def artifact(self) -> str:
        return self._canonical_artifact


def _validate_artifact(raw: dict[str, Any]) -> None:
    schema = raw.get("schema")
    if schema not in {SCHEMA, EFFECT_SCHEMA, DYNAMIC_SCHEMA}:
        raise _invalid(f"expected artifact schema {SCHEMA!r}, {EFFECT_SCHEMA!r} or {DYNAMIC_SCHEMA!r}", "/schema")
    expected_fields = _TOP_FIELDS if schema == SCHEMA else _EFFECT_TOP_FIELDS
    if set(raw) != expected_fields:
        raise _invalid("artifact fields must be exactly the dynamic-spike contract")
    _identifier(raw["entry"], "/entry")
    if type(raw["budget"]) is not int or raw["budget"] <= 0:
        raise _invalid("budget must be a positive integer", "/budget")

    schemas = raw["schemas"]
    if type(schemas) is not dict:
        raise _invalid("schemas must be an object", "/schemas")
    for schema_name, descriptor in schemas.items():
        _identifier(schema_name, "/schemas")
        try:
            validate_compiler_normalized_type_descriptor(descriptor, context=f"/schemas/{schema_name}")
            _validate_schema_kinds(descriptor)
        except (TypeError, ValueError, RecursionError) as exc:
            raise _invalid(f"invalid boundary schema: {exc}", _pointer("/schemas", schema_name)) from exc

    inputs = _sequence(raw["inputs"], "/inputs")
    input_names: list[str] = []
    seen_input_names: set[str] = set()
    for index, row in enumerate(inputs):
        pointer = _pointer("/inputs", index)
        if type(row) is not list or len(row) != 2:
            raise _invalid("input rows must be [name, schema] pairs", pointer)
        name = _identifier(row[0], _pointer(pointer, 0))
        schema_name = _identifier(row[1], _pointer(pointer, 1))
        if name in seen_input_names:
            raise _invalid("input names must be unique", pointer)
        if schema_name not in schemas:
            raise _invalid("input refers to an unknown schema", _pointer(pointer, 1))
        input_names.append(name)
        seen_input_names.add(name)

    result = _identifier(raw["result"], "/result")
    if result not in schemas:
        raise _invalid("result refers to an unknown schema", "/result")

    definitions = raw["definitions"]
    if type(definitions) is not dict or not definitions:
        raise _invalid("definitions must be a non-empty object", "/definitions")
    headers: dict[str, tuple[list[str], list[str]]] = {}
    effects: list[str] = []
    if schema in {EFFECT_SCHEMA, DYNAMIC_SCHEMA}:
        for index, effect in enumerate(_sequence(raw["effects"], "/effects")):
            effect = _identifier(effect, _pointer("/effects", index))
            if effect in effects:
                raise _invalid("effect identifiers must be unique", _pointer("/effects", index))
            effects.append(effect)

    for code, definition in definitions.items():
        pointer = _pointer("/definitions", code)
        _identifier(code, pointer)
        if type(definition) is not dict or set(definition) != {"params", "captures", "body"}:
            raise _invalid("definition fields must be exactly params, captures and body", pointer)
        params = _names(definition["params"], _pointer(pointer, "params"))
        captures = _names(definition["captures"], _pointer(pointer, "captures"))
        if len(set(params)) != len(params) or len(set(captures)) != len(captures):
            raise _invalid("parameter and capture names must be unique", pointer)
        if set(params) & set(captures):
            raise _invalid("parameter and capture names must be disjoint", pointer)
        headers[code] = (params, captures)

    for code, definition in definitions.items():
        params, captures = headers[code]
        pointer = _pointer("/definitions", code)
        _validate_node(
            definition["body"],
            set(params) | set(captures),
            definitions,
            _pointer(pointer, "body"),
            set(effects),
            schema,
        )

    entry = definitions.get(raw["entry"])
    if entry is None:
        raise _invalid("entry refers to an unknown definition", "/entry")
    if entry["params"] != input_names:
        raise _invalid("entry parameters must match ordered input names", _pointer("/definitions", raw["entry"]))
    if entry["captures"]:
        raise _invalid("entry definition cannot capture values", _pointer("/definitions", raw["entry"]))


def _names(value: Any, context: str) -> list[str]:
    names = _sequence(value, context)
    for index, name in enumerate(names):
        _identifier(name, _pointer(context, index))
    return names


def _validate_schema_kinds(descriptor: Any) -> None:
    kind = descriptor["kind"]
    if kind == "primitive":
        if descriptor["name"] not in _PRIMITIVES:
            raise ValueError("only Bool, Int, Float, String and Value primitives are admitted")
    elif kind == "enum":
        return
    elif kind in {"optional", "list"}:
        _validate_schema_kinds(descriptor["item"])
    elif kind == "map":
        if descriptor["key"] != {"kind": "primitive", "name": "String"}:
            raise ValueError("only string-keyed maps are admitted")
        _validate_schema_kinds(descriptor["value"])
    elif kind == "record":
        for field in descriptor["fields"]:
            _validate_schema_kinds(field["type"])
    elif kind == "union":
        for variant in descriptor["variants"]:
            for field in variant["fields"]:
                _validate_schema_kinds(field["type"])
    else:
        raise ValueError("path and unsupported schemas are outside this experiment")
    if not is_transportable_type_descriptor(descriptor, allow_nested_structures=True):
        raise ValueError("schema is not transportable")


def _validate_node(
    node: Any,
    bound: set[str],
    definitions: Mapping[str, Any],
    pointer: str,
    effects: set[str] | None = None,
    schema: str = SCHEMA,
) -> None:
    effects = effects or set()
    if type(node) is not dict or not isinstance(node.get("k"), str):
        raise _invalid("node must be an object with a kind", pointer)
    kind = node["k"]
    fields = _NODE_FIELDS.get(kind)
    if fields is None and schema == DYNAMIC_SCHEMA:
        fields = _DYNAMIC_NODE_FIELDS.get(kind)
    if fields is None:
        raise _invalid(f"unsupported node kind {kind!r}", pointer)
    if set(node) != {"k", *fields}:
        raise _invalid("node fields do not match its kind", pointer)

    if kind == "lit":
        value = node["v"]
        if value is not None and type(value) not in {bool, int, float, str}:
            raise _invalid("literal must be a scalar JSON value", pointer)
        if type(value) is float and not math.isfinite(value):
            raise _invalid("literal Float must be finite", pointer)
    elif kind == "name":
        name = _identifier(node["n"], _pointer(pointer, "n"))
        if name not in bound:
            raise _invalid(f"unbound lexical name {name!r}", pointer)
    elif kind == "let":
        local = set(bound)
        seen: set[str] = set()
        for index, row in enumerate(_sequence(node["bindings"], _pointer(pointer, "bindings"))):
            row_pointer = _pointer(_pointer(pointer, "bindings"), index)
            if type(row) is not list or len(row) != 2:
                raise _invalid("let bindings must be [name, node] pairs", row_pointer)
            binder = _identifier(row[0], _pointer(row_pointer, 0))
            if binder in seen:
                raise _invalid("let binding names must be unique", row_pointer)
            _validate_node(row[1], local, definitions, _pointer(row_pointer, 1), effects, schema)
            seen.add(binder)
            local.add(binder)
        _validate_node(node["body"], local, definitions, _pointer(pointer, "body"), effects, schema)
    elif kind == "fn":
        code = _identifier(node["code"], _pointer(pointer, "code"))
        target = definitions.get(code)
        if target is None:
            raise _invalid("function refers to unknown code", _pointer(pointer, "code"))
        captures = _sequence(node["captures"], _pointer(pointer, "captures"))
        if len(captures) != len(target["captures"]):
            raise _invalid("function capture count does not match its definition", pointer)
        for index, child in enumerate(captures):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "captures"), index), effects, schema)
    elif kind == "call":
        _validate_node(node["callee"], bound, definitions, _pointer(pointer, "callee"), effects, schema)
        for index, child in enumerate(_sequence(node["args"], _pointer(pointer, "args"))):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "args"), index), effects, schema)
    elif kind == "if":
        for field in ("cond", "then", "else"):
            _validate_node(node[field], bound, definitions, _pointer(pointer, field), effects, schema)
    elif kind == "record":
        seen = set()
        for index, row in enumerate(_sequence(node["fields"], _pointer(pointer, "fields"))):
            row_pointer = _pointer(_pointer(pointer, "fields"), index)
            if type(row) is not list or len(row) != 2:
                raise _invalid("record fields must be [name, node] pairs", row_pointer)
            field_name = _identifier(row[0], _pointer(row_pointer, 0))
            if field_name in seen:
                raise _invalid("record field names must be unique", row_pointer)
            seen.add(field_name)
            _validate_node(row[1], bound, definitions, _pointer(row_pointer, 1), effects, schema)
    elif kind == "field":
        _identifier(node["name"], _pointer(pointer, "name"))
        _validate_node(node["base"], bound, definitions, _pointer(pointer, "base"), effects, schema)
    elif kind == "list":
        for index, child in enumerate(_sequence(node["items"], _pointer(pointer, "items"))):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "items"), index), effects, schema)
    elif kind == "at":
        _validate_node(node["base"], bound, definitions, _pointer(pointer, "base"), effects, schema)
        _validate_node(node["index"], bound, definitions, _pointer(pointer, "index"), effects, schema)
    elif kind == "op":
        operator = _identifier(node["name"], _pointer(pointer, "name"))
        if operator not in _OPERATORS and not (schema == DYNAMIC_SCHEMA and operator in DYNAMIC_OPERATORS):
            raise _invalid(f"unsupported primitive {operator!r}", pointer)
        for index, child in enumerate(_sequence(node["args"], _pointer(pointer, "args"))):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "args"), index), effects, schema)
    elif kind == "effect":
        effect_name = _identifier(node["name"], _pointer(pointer, "name"))
        if effect_name not in effects:
            raise _invalid("effect node refers to an undeclared operation", _pointer(pointer, "name"))
        _validate_node(node["inputs"], bound, definitions, _pointer(pointer, "inputs"), effects, schema)
    elif kind == "record-update":
        _validate_node(node["base"], bound, definitions, _pointer(pointer, "base"), effects, schema)
        fields = _sequence(node["fields"], _pointer(pointer, "fields"))
        if not fields:
            raise _invalid("record update fields must be non-empty", _pointer(pointer, "fields"))
        seen: set[str] = set()
        for index, row in enumerate(fields):
            row_pointer = _pointer(_pointer(pointer, "fields"), index)
            if type(row) is not list or len(row) != 2:
                raise _invalid("record update fields must be [name, node] pairs", row_pointer)
            field_name = _identifier(row[0], _pointer(row_pointer, 0))
            if field_name in seen:
                raise _invalid("record update field names must be unique", row_pointer)
            seen.add(field_name)
            _validate_node(row[1], bound, definitions, _pointer(row_pointer, 1), effects, schema)
    elif kind == "fail":
        reason = node["reason"]
        if not isinstance(reason, str) or not reason:
            raise _invalid("failure reason must be a non-empty string", _pointer(pointer, "reason"))


__all__ = ["DynamicProgram", "SCHEMA", "EFFECT_SCHEMA", "DYNAMIC_SCHEMA", "strict_json_loads"]
