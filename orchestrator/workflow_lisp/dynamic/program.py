"""Strict admission for the production dynamic Workflow Lisp artifact.

`DynamicProgram.from_artifact` independently reads the exact `/1` envelope.
Its public boundary is `definitions[entry]["boundary"]`; schema references
resolve through the existing normalized descriptor table. `semantic_digest`
pins executable declarations, while `provenance_digest` pins source bytes and
the RFC 6901 source map. Source-map entries point to real artifact locations:
definition bodies, nested expressions, and each boundary parameter/default/
result subject.

`schema_reference` is the frontend helper for the same descriptor keys used by
admission: canonical declaration names for nominal descriptors and canonical
descriptor digests for structural descriptors.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from pathlib import PurePosixPath
from typing import Any

from orchestrator.contracts.output_contract import strict_json_loads
from orchestrator.workflow.evaluated.values import EvaluatedValueError, _freeze, _thaw
from orchestrator.workflow.pure_expr import PURE_EXPR_OPERATOR_CATALOG
from orchestrator.workflow.type_descriptor import (
    is_transportable_type_descriptor,
    transport_schema_for_descriptor,
    validate_compiler_normalized_type_descriptor,
    validate_transport_value,
)
from orchestrator.workflow_lisp.closed.program import (
    _canonical_json,
    canonical_digest,
    logical_asset_base_for_module,
)


SCHEMA = "workflow-lisp/dynamic-program/1"
SOURCE_MAP_SCHEMA = "workflow-lisp/dynamic-source-map/1"
TARGET = "3.0"
_SEMANTIC_FIELDS = ("schema", "target", "entry", "budget", "definitions", "schemas", "bindings")
_TOP_FIELDS = set(_SEMANTIC_FIELDS) | {"sources", "source_map"}
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
    "record-update": {"base", "fields"},
    "fail": {"reason"},
}
_OPERATORS = frozenset(
    {
        "+", "-", "*", "/", "<", "<=", ">", ">=", "=", "!=",
        "not", "string/concat", "string/empty?", "list/append", "list/length",
    }
)
_SCHEMA_PRIMITIVES = frozenset({"Bool", "Int", "Float", "String", "Value"})
_INT = {"kind": "primitive", "name": "Int"}
_VALUE = {"kind": "primitive", "name": "Value"}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SOURCE_ROW_FIELDS = {"root_role", "relative_path", "source_sha256"}
_SOURCE_MAP_FIELDS = {"schema", "entries"}
_SOURCE_MAP_ROW_FIELDS = {"source", "span", "form_path"}
_SPAN_FIELDS = {"start", "end"}
_POSITION_FIELDS = {"path", "line", "column", "offset"}


def _invalid(message: str, location: str | None = None) -> EvaluatedValueError:
    return EvaluatedValueError("dynamic_program_invalid", message, location=location)


def _pointer(pointer: str, token: str | int) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}"


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{context} must be a nonempty string", context)
    if "\x00" in value:
        raise _invalid(f"{context} contains a NUL character", context)
    return value


def _array(value: Any, context: str) -> list[Any]:
    if type(value) is not list:
        raise _invalid(f"{context} must be an array", context)
    return value


def _object(value: Any, context: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise _invalid(f"{context} must be an object", context)
    return value


def _expect_fields(value: Mapping[str, Any], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise _invalid(f"{context} fields must be exactly {sorted(expected)!r}", context)


def schema_reference(descriptor: Mapping[str, Any]) -> str:
    """Return the canonical catalog key for a normalized descriptor."""

    value = _thaw(descriptor)
    validate_compiler_normalized_type_descriptor(value)
    kind = value["kind"]
    if kind in {"primitive", "enum", "record", "union", "path"}:
        return value["name"]
    if kind == "variant_case":
        return f"{value['union_name']}::{value['variant']}"
    return canonical_digest(value)


def _schema_kinds(descriptor: Mapping[str, Any], context: str) -> None:
    kind = descriptor["kind"]
    if kind == "primitive":
        if descriptor["name"] not in _SCHEMA_PRIMITIVES:
            raise _invalid(f"{context} uses an unsupported primitive", context)
    elif kind in {"enum", "path"}:
        return
    elif kind in {"optional", "list"}:
        _schema_kinds(descriptor["item"], _pointer(context, "item"))
    elif kind == "map":
        if descriptor["key"] != {"kind": "primitive", "name": "String"}:
            raise _invalid("dynamic maps require String keys", _pointer(context, "key"))
        _schema_kinds(descriptor["value"], _pointer(context, "value"))
    elif kind == "record":
        for index, field in enumerate(descriptor["fields"]):
            _schema_kinds(field["type"], _pointer(_pointer(context, "fields"), index))
    elif kind == "union":
        for index, variant in enumerate(descriptor["variants"]):
            for field_index, field in enumerate(variant["fields"]):
                location = _pointer(_pointer(_pointer(context, "variants"), index), "fields")
                _schema_kinds(field["type"], _pointer(location, field_index))
    elif kind == "variant_case":
        for index, field in enumerate(descriptor["fields"]):
            _schema_kinds(field["type"], _pointer(_pointer(context, "fields"), index))
    else:
        raise _invalid(f"{context} uses an unsupported boundary type", context)
    # A variant case is a valid compiler descriptor and may appear in the
    # catalog, but the shared transport owner intentionally has no standalone
    # variant-case wire codec. Parent descriptors still fail the common
    # transportability check when they contain one.
    if kind != "variant_case" and not is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=True,
    ):
        raise _invalid(f"{context} is not transportable", context)


def _validate_catalog_references(
    descriptor: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
    context: str,
) -> None:
    """Require nested nominal descriptors to match the canonical catalog row."""

    kind = descriptor["kind"]
    if kind in {"enum", "record", "union", "path"}:
        reference = schema_reference(descriptor)
        registered = schemas.get(reference)
        if registered is None:
            raise _invalid("nested nominal descriptor has no catalog definition", context)
        if registered != descriptor:
            raise _invalid("nested nominal descriptor differs from its catalog definition", context)
    elif kind == "variant_case":
        union_name = descriptor["union_name"]
        registered_union = schemas.get(union_name)
        if not isinstance(registered_union, Mapping) or registered_union.get("kind") != "union":
            raise _invalid("variant case has no registered union definition", context)
        variant = next(
            (row for row in registered_union["variants"] if row["name"] == descriptor["variant"]),
            None,
        )
        if variant is None or variant["fields"] != descriptor["fields"]:
            raise _invalid("variant case differs from its registered union variant", context)

    if kind in {"optional", "list"}:
        _validate_catalog_references(descriptor["item"], schemas, _pointer(context, "item"))
    elif kind == "map":
        _validate_catalog_references(descriptor["key"], schemas, _pointer(context, "key"))
        _validate_catalog_references(descriptor["value"], schemas, _pointer(context, "value"))
    elif kind == "record":
        for index, field in enumerate(descriptor["fields"]):
            _validate_catalog_references(
                field["type"],
                schemas,
                _pointer(_pointer(context, "fields"), index),
            )
    elif kind == "union":
        for index, variant in enumerate(descriptor["variants"]):
            for field_index, field in enumerate(variant["fields"]):
                field_pointer = _pointer(
                    _pointer(_pointer(context, "variants"), index),
                    "fields",
                )
                _validate_catalog_references(
                    field["type"],
                    schemas,
                    _pointer(field_pointer, field_index),
                )
    elif kind == "variant_case":
        for index, field in enumerate(descriptor["fields"]):
            _validate_catalog_references(
                field["type"],
                schemas,
                _pointer(_pointer(context, "fields"), index),
            )


def _validate_schemas(value: Any) -> dict[str, dict[str, Any]]:
    schemas = _object(value, "/schemas")
    if not schemas:
        raise _invalid("schemas must contain at least one boundary descriptor", "/schemas")
    normalized: dict[str, dict[str, Any]] = {}
    for reference, descriptor in schemas.items():
        _identifier(reference, _pointer("/schemas", reference))
        location = _pointer("/schemas", reference)
        try:
            validate_compiler_normalized_type_descriptor(descriptor, context=location)
            _schema_kinds(descriptor, location)
            expected = schema_reference(descriptor)
        except EvaluatedValueError:
            raise
        except (TypeError, ValueError, RecursionError) as exc:
            raise _invalid(f"invalid boundary descriptor: {exc}", location) from exc
        if reference != expected:
            raise _invalid("schema key is not the descriptor's canonical identity", location)
        normalized[reference] = descriptor
    for reference, descriptor in normalized.items():
        _validate_catalog_references(descriptor, normalized, _pointer("/schemas", reference))
    return normalized


def _check_data_value(value: Any, descriptor: Mapping[str, Any], context: str) -> None:
    try:
        validate_transport_value(
            value,
            descriptor,
            allow_nested_structures=True,
            require_int64=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise _invalid(f"{context} does not match its declared schema: {exc}", context) from exc


def _validate_sources(value: Any) -> dict[str, dict[str, Any]]:
    sources = _object(value, "/sources")
    if not sources:
        raise _invalid("sources must identify every defining module", "/sources")
    validated: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for module, source in sources.items():
        location = _pointer("/sources", module)
        _identifier(module, location)
        try:
            logical_asset_base_for_module(module)
        except ValueError as exc:
            raise _invalid("source module must be a canonical relative logical path", location) from exc
        source = _object(source, location)
        _expect_fields(source, _SOURCE_ROW_FIELDS, location)
        root_role = _identifier(source["root_role"], _pointer(location, "root_role"))
        relative_path = _identifier(source["relative_path"], _pointer(location, "relative_path"))
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in relative_path
            or relative_path in {".", ".."}
            or path.as_posix() != relative_path
        ):
            raise _invalid("source path must be a normalized path relative to its root", _pointer(location, "relative_path"))
        identity = (root_role, relative_path)
        if identity in identities:
            raise _invalid("sources contain a duplicate source identity", location)
        identities.add(identity)
        if not isinstance(source["source_sha256"], str) or not _SHA256_RE.fullmatch(source["source_sha256"]):
            raise _invalid("source revision must be a sha256 identity", _pointer(location, "source_sha256"))
        validated[module] = source
    return validated


def _names(value: Any, context: str) -> list[str]:
    rows = _array(value, context)
    names = [_identifier(name, _pointer(context, index)) for index, name in enumerate(rows)]
    if len(names) != len(set(names)):
        raise _invalid(f"{context} must contain unique names", context)
    return names


def _validate_owner(value: Any, code: str, sources: Mapping[str, Any], context: str) -> dict[str, Any]:
    owner = _object(value, context)
    _expect_fields(owner, {"module", "asset_base"}, context)
    module = _identifier(owner["module"], _pointer(context, "module"))
    if module not in sources:
        raise _invalid("definition owner has no pinned source", _pointer(context, "module"))
    code_module, separator, member = code.rpartition("::")
    if not separator or code_module != module or not member.strip() or "::" in module:
        raise _invalid("code identifier does not belong to its canonical owner module", context)
    asset_base = owner["asset_base"]
    if not isinstance(asset_base, str) or "\x00" in asset_base:
        raise _invalid("asset_base must be a logical relative path", _pointer(context, "asset_base"))
    try:
        expected_asset_base = logical_asset_base_for_module(module)
    except ValueError as exc:
        raise _invalid("definition owner module is not a canonical logical path", _pointer(context, "module")) from exc
    if asset_base != expected_asset_base:
        raise _invalid("asset_base must equal the canonical module asset base", _pointer(context, "asset_base"))
    return owner


def _validate_boundary(value: Any, params: list[str], schemas: Mapping[str, Any], context: str) -> dict[str, Any] | None:
    if value is None:
        return None
    boundary = _object(value, context)
    _expect_fields(boundary, {"params", "defaults", "result"}, context)
    parameter_rows = _array(boundary["params"], _pointer(context, "params"))
    names: list[str] = []
    for index, row in enumerate(parameter_rows):
        location = _pointer(_pointer(context, "params"), index)
        if type(row) is not list or len(row) != 2:
            raise _invalid("boundary parameter rows must be [name, schema] pairs", location)
        name = _identifier(row[0], _pointer(location, 0))
        reference = _identifier(row[1], _pointer(location, 1))
        if name in names:
            raise _invalid("boundary parameter names must be unique", location)
        if reference not in schemas:
            raise _invalid("boundary parameter refers to an unknown schema", _pointer(location, 1))
        try:
            transport_schema_for_descriptor(schemas[reference], allow_nested_structures=True)
        except (TypeError, ValueError, RecursionError) as exc:
            raise _invalid(
                f"boundary parameter cannot derive a native input schema: {exc}",
                _pointer(location, 1),
            ) from exc
        names.append(name)
    if names != params:
        raise _invalid("boundary parameters must preserve the definition's ordered names", _pointer(context, "params"))
    defaults = _object(boundary["defaults"], _pointer(context, "defaults"))
    if not set(defaults).issubset(names):
        raise _invalid("boundary defaults refer to an unknown parameter", _pointer(context, "defaults"))
    descriptor_by_name = {row[0]: schemas[row[1]] for row in parameter_rows}
    for name, default in defaults.items():
        _check_data_value(default, descriptor_by_name[name], _pointer(_pointer(context, "defaults"), name))
    result = _identifier(boundary["result"], _pointer(context, "result"))
    if result not in schemas:
        raise _invalid("boundary result refers to an unknown schema", _pointer(context, "result"))
    try:
        transport_schema_for_descriptor(schemas[result], allow_nested_structures=True)
    except (TypeError, ValueError, RecursionError) as exc:
        raise _invalid(f"boundary result cannot derive a native output contract: {exc}", _pointer(context, "result")) from exc
    return boundary


def _node_children(node: Mapping[str, Any], pointer: str) -> tuple[tuple[str, Any], ...]:
    kind = node.get("k")
    if kind == "let":
        return tuple(
            (_pointer(_pointer(_pointer(pointer, "bindings"), index), 1), row[1])
            for index, row in enumerate(node["bindings"])
        ) + ((_pointer(pointer, "body"), node["body"]),)
    if kind == "fn":
        return tuple((_pointer(_pointer(pointer, "captures"), index), child) for index, child in enumerate(node["captures"]))
    if kind == "call":
        return ((_pointer(pointer, "callee"), node["callee"]),) + tuple(
            (_pointer(_pointer(pointer, "args"), index), child) for index, child in enumerate(node["args"])
        )
    if kind == "if":
        return tuple((_pointer(pointer, name), node[name]) for name in ("cond", "then", "else"))
    if kind in {"record", "record-update"}:
        rows = tuple(
            (_pointer(_pointer(_pointer(pointer, "fields"), index), 1), row[1])
            for index, row in enumerate(node["fields"])
        )
        return rows if kind == "record" else ((_pointer(pointer, "base"), node["base"]),) + rows
    if kind == "field":
        return ((_pointer(pointer, "base"), node["base"]),)
    if kind == "list":
        return tuple((_pointer(_pointer(pointer, "items"), index), child) for index, child in enumerate(node["items"]))
    if kind == "at":
        return ((_pointer(pointer, "base"), node["base"]), (_pointer(pointer, "index"), node["index"]))
    if kind == "op":
        return tuple((_pointer(_pointer(pointer, "args"), index), child) for index, child in enumerate(node["args"]))
    return ()


def _node_paths(node: Mapping[str, Any], pointer: str):
    yield pointer
    for child_pointer, child in _node_children(node, pointer):
        yield from _node_paths(child, child_pointer)


def _validate_node(node: Any, bound: set[str], definitions: Mapping[str, Any], pointer: str) -> None:
    if type(node) is not dict:
        raise _invalid("expression must be an object", pointer)
    kind = node.get("k")
    if not isinstance(kind, str) or kind not in _NODE_FIELDS:
        if kind == "effect":
            raise _invalid("effect nodes await shared static-payload admission", pointer)
        raise _invalid("unsupported dynamic expression node", pointer)
    _expect_fields(node, {"k", *_NODE_FIELDS[kind]}, pointer)
    if kind == "lit":
        value = node["v"]
        if value is not None and type(value) not in (bool, int, float, str):
            raise _invalid("literal nodes admit only scalar JSON values", _pointer(pointer, "v"))
        _check_data_value(value, _VALUE, _pointer(pointer, "v"))
    elif kind == "name":
        name = _identifier(node["n"], _pointer(pointer, "n"))
        if name not in bound:
            raise _invalid(f"unbound lexical name {name!r}", _pointer(pointer, "n"))
    elif kind == "let":
        bindings = _array(node["bindings"], _pointer(pointer, "bindings"))
        local = set(bound)
        names: set[str] = set()
        for index, row in enumerate(bindings):
            location = _pointer(_pointer(pointer, "bindings"), index)
            if type(row) is not list or len(row) != 2:
                raise _invalid("let bindings must be [name, expression] pairs", location)
            name = _identifier(row[0], _pointer(location, 0))
            if name in names:
                raise _invalid("let binding names must be unique", location)
            _validate_node(row[1], local, definitions, _pointer(location, 1))
            names.add(name)
            local.add(name)
        _validate_node(node["body"], local, definitions, _pointer(pointer, "body"))
    elif kind == "fn":
        code = _identifier(node["code"], _pointer(pointer, "code"))
        definition = definitions.get(code)
        if definition is None:
            raise _invalid("closure refers to an unknown code identifier", _pointer(pointer, "code"))
        captures = _array(node["captures"], _pointer(pointer, "captures"))
        if len(captures) != len(definition["captures"]):
            raise _invalid("closure capture count differs from its definition", _pointer(pointer, "captures"))
        for index, child in enumerate(captures):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "captures"), index))
    elif kind == "call":
        _validate_node(node["callee"], bound, definitions, _pointer(pointer, "callee"))
        for index, child in enumerate(_array(node["args"], _pointer(pointer, "args"))):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "args"), index))
    elif kind == "if":
        for field in ("cond", "then", "else"):
            _validate_node(node[field], bound, definitions, _pointer(pointer, field))
    elif kind == "record":
        seen: set[str] = set()
        for index, row in enumerate(_array(node["fields"], _pointer(pointer, "fields"))):
            location = _pointer(_pointer(pointer, "fields"), index)
            if type(row) is not list or len(row) != 2:
                raise _invalid("record fields must be [name, expression] pairs", location)
            name = _identifier(row[0], _pointer(location, 0))
            if name in seen:
                raise _invalid("record field names must be unique", location)
            seen.add(name)
            _validate_node(row[1], bound, definitions, _pointer(location, 1))
    elif kind == "field":
        _identifier(node["name"], _pointer(pointer, "name"))
        _validate_node(node["base"], bound, definitions, _pointer(pointer, "base"))
    elif kind == "list":
        for index, child in enumerate(_array(node["items"], _pointer(pointer, "items"))):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "items"), index))
    elif kind == "at":
        _validate_node(node["base"], bound, definitions, _pointer(pointer, "base"))
        _validate_node(node["index"], bound, definitions, _pointer(pointer, "index"))
    elif kind == "op":
        name = _identifier(node["name"], _pointer(pointer, "name"))
        if name not in _OPERATORS:
            raise _invalid(f"unsupported primitive {name!r}", _pointer(pointer, "name"))
        args = _array(node["args"], _pointer(pointer, "args"))
        spec = PURE_EXPR_OPERATOR_CATALOG[name]
        if len(args) < spec.min_arity or (spec.max_arity is not None and len(args) > spec.max_arity):
            raise _invalid(f"primitive {name!r} has an invalid operand count", _pointer(pointer, "args"))
        for index, child in enumerate(args):
            _validate_node(child, bound, definitions, _pointer(_pointer(pointer, "args"), index))
    elif kind == "record-update":
        _validate_node(node["base"], bound, definitions, _pointer(pointer, "base"))
        seen: set[str] = set()
        for index, row in enumerate(_array(node["fields"], _pointer(pointer, "fields"))):
            location = _pointer(_pointer(pointer, "fields"), index)
            if type(row) is not list or len(row) != 2:
                raise _invalid("record updates must be [name, expression] pairs", location)
            name = _identifier(row[0], _pointer(location, 0))
            if name in seen:
                raise _invalid("record update fields must be unique", location)
            seen.add(name)
            _validate_node(row[1], bound, definitions, _pointer(location, 1))
        if not seen:
            raise _invalid("record updates must replace at least one field", _pointer(pointer, "fields"))
    elif kind == "fail":
        _identifier(node["reason"], _pointer(pointer, "reason"))


def _source_subjects(definitions: Mapping[str, Any]) -> dict[str, str]:
    subjects: dict[str, str] = {}
    for code, definition in definitions.items():
        module = definition["owner"]["module"]
        definition_pointer = _pointer("/definitions", code)
        subjects[definition_pointer] = module
        body_pointer = _pointer(definition_pointer, "body")
        for node_pointer in _node_paths(definition["body"], body_pointer):
            subjects[node_pointer] = module
        boundary = definition["boundary"]
        if boundary is not None:
            boundary_pointer = _pointer(definition_pointer, "boundary")
            for index, _ in enumerate(boundary["params"]):
                subjects[_pointer(_pointer(boundary_pointer, "params"), index)] = module
            for name in boundary["defaults"]:
                subjects[_pointer(_pointer(boundary_pointer, "defaults"), name)] = module
            subjects[_pointer(boundary_pointer, "result")] = module
    return subjects


def _validate_span(value: Any, source: Mapping[str, Any], context: str) -> None:
    span = _object(value, context)
    _expect_fields(span, _SPAN_FIELDS, context)
    positions = []
    for side in ("start", "end"):
        location = _pointer(context, side)
        position = _object(span[side], location)
        _expect_fields(position, _POSITION_FIELDS, location)
        if position["path"] != source["relative_path"]:
            raise _invalid("source-map span path differs from its pinned source", _pointer(location, "path"))
        if (
            type(position["line"]) is not int
            or position["line"] < 1
            or type(position["column"]) is not int
            or position["column"] < 1
            or type(position["offset"]) is not int
            or position["offset"] < 0
        ):
            raise _invalid("source-map positions need positive lines/columns and a nonnegative offset", location)
        positions.append((position["line"], position["column"], position["offset"]))
    start, end = positions
    if (end[0], end[1]) <= (start[0], start[1]) or end[2] <= start[2]:
        raise _invalid("source-map span end must advance in location and offset", context)


def _validate_source_map(value: Any, sources: Mapping[str, Any], definitions: Mapping[str, Any]) -> dict[str, Any]:
    source_map = _object(value, "/source_map")
    _expect_fields(source_map, _SOURCE_MAP_FIELDS, "/source_map")
    if source_map["schema"] != SOURCE_MAP_SCHEMA:
        raise _invalid(f"source map schema must be {SOURCE_MAP_SCHEMA!r}", "/source_map/schema")
    entries = _object(source_map["entries"], "/source_map/entries")
    expected = _source_subjects(definitions)
    if set(entries) != set(expected):
        missing = sorted(set(expected) - set(entries))
        extra = sorted(set(entries) - set(expected))
        raise _invalid(f"source map coverage differs from program subjects (missing={missing!r}, extra={extra!r})", "/source_map/entries")
    for pointer, module in expected.items():
        location = _pointer("/source_map/entries", pointer)
        row = _object(entries[pointer], location)
        _expect_fields(row, _SOURCE_MAP_ROW_FIELDS, location)
        source_name = _identifier(row["source"], _pointer(location, "source"))
        if source_name != module or source_name not in sources:
            raise _invalid("source-map subject must point to its defining module's pinned source", _pointer(location, "source"))
        _validate_span(row["span"], sources[source_name], _pointer(location, "span"))
        form_path = _array(row["form_path"], _pointer(location, "form_path"))
        if not form_path or any(not isinstance(part, str) or not part for part in form_path):
            raise _invalid("source-map form_path must contain nonempty path components", _pointer(location, "form_path"))
    return source_map


def _validate_artifact(raw: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    tree = _object(raw, "<artifact>")
    _expect_fields(tree, _TOP_FIELDS, "<artifact>")
    if tree["schema"] != SCHEMA:
        raise _invalid(f"expected artifact schema {SCHEMA!r}", "/schema")
    if tree["target"] != TARGET:
        raise _invalid(f"target must be exactly {TARGET!r}", "/target")
    entry_code = _identifier(tree["entry"], "/entry")
    if type(tree["budget"]) is not int or tree["budget"] <= 0:
        raise _invalid("budget must be a positive non-Boolean integer", "/budget")
    _check_data_value(tree["budget"], _INT, "/budget")

    schemas = _validate_schemas(tree["schemas"])
    sources = _validate_sources(tree["sources"])
    bindings = _object(tree["bindings"], "/bindings")
    if bindings:
        raise _invalid("nonempty effect bindings await shared static-payload admission", "/bindings")
    definitions = _object(tree["definitions"], "/definitions")
    if not definitions:
        raise _invalid("definitions must contain the entry", "/definitions")

    definition_rows: dict[str, dict[str, Any]] = {}
    for code, value in definitions.items():
        location = _pointer("/definitions", code)
        _identifier(code, location)
        definition = _object(value, location)
        _expect_fields(definition, {"params", "captures", "body", "owner", "boundary"}, location)
        params = _names(definition["params"], _pointer(location, "params"))
        captures = _names(definition["captures"], _pointer(location, "captures"))
        if set(params) & set(captures):
            raise _invalid("parameter and capture names must be disjoint", location)
        owner = _validate_owner(definition["owner"], code, sources, _pointer(location, "owner"))
        boundary = _validate_boundary(definition["boundary"], params, schemas, _pointer(location, "boundary"))
        definition_rows[code] = {**definition, "params": params, "captures": captures, "owner": owner, "boundary": boundary}

    entry = definition_rows.get(entry_code)
    if entry is None:
        raise _invalid("entry refers to an unknown definition", "/entry")
    if entry["captures"] or entry["boundary"] is None:
        raise _invalid("entry must have no captures and a declared boundary", _pointer("/definitions", entry_code))

    for code, definition in definition_rows.items():
        pointer = _pointer(_pointer("/definitions", code), "body")
        _validate_node(definition["body"], set(definition["params"]) | set(definition["captures"]), definition_rows, pointer)

    source_map = _validate_source_map(tree["source_map"], sources, definition_rows)
    return definition_rows, schemas, sources, source_map


@dataclass(frozen=True)
class DynamicProgram:
    """An immutable, independently checked `dynamic-program/1` artifact."""

    tree: Mapping[str, Any]
    entry: str
    budget: int
    definitions: Mapping[str, Mapping[str, Any]]
    schemas: Mapping[str, Mapping[str, Any]]
    bindings: Mapping[str, Any]
    sources: Mapping[str, Mapping[str, Any]]
    source_map: Mapping[str, Any]
    semantic_digest: str
    provenance_digest: str
    schema: str = SCHEMA

    @classmethod
    def from_artifact(cls, text: str | bytes) -> DynamicProgram:
        try:
            raw = strict_json_loads(text)
            if type(raw) is not dict:
                raise _invalid("artifact must be a JSON object")
            definitions, schemas, sources, source_map = _validate_artifact(raw)
            canonical = _canonical_json(raw)
            semantic = {name: raw[name] for name in _SEMANTIC_FIELDS}
            provenance = {"sources": raw["sources"], "source_map": raw["source_map"]}
            tree = _freeze(raw)
        except EvaluatedValueError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise _invalid(f"invalid production dynamic artifact: {exc}") from exc
        return cls(
            tree=tree,
            entry=raw["entry"],
            budget=raw["budget"],
            definitions=tree["definitions"],
            schemas=tree["schemas"],
            bindings=tree["bindings"],
            sources=tree["sources"],
            source_map=tree["source_map"],
            semantic_digest=canonical_digest(semantic),
            provenance_digest=canonical_digest(provenance),
            schema=raw["schema"],
        )

    @property
    def digest(self) -> str:
        """Compatibility name for consumers pinning semantic identity."""

        return self.semantic_digest

    @property
    def root_result_contract(self) -> Mapping[str, Any]:
        """Derive the native whole-value `__result__` contract from its schema."""

        boundary = self.definitions[self.entry]["boundary"]
        descriptor = self.schemas[boundary["result"]]
        schema = transport_schema_for_descriptor(descriptor, allow_nested_structures=True)
        return _freeze({
            "kind": "output_bundle",
            "payload": {
                "fields": [
                    {"name": "__result__", "json_pointer": "", **schema}
                ]
            },
        })

    def artifact(self) -> str:
        """Return canonical checked JSON with one final newline."""

        return _canonical_json(_thaw(self.tree)) + "\n"


__all__ = ["DynamicProgram", "SCHEMA", "SOURCE_MAP_SCHEMA", "schema_reference"]
