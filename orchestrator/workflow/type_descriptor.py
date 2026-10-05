"""Neutral validation for compiler-normalized transport type descriptors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import json
import math
from typing import Any, Callable


MAX_TRANSPORT_VALUE_DEPTH = 64
MAX_TRANSPORT_VALUE_BYTES = 16_777_216
_NONTRANSPORTABLE_PRIMITIVES = frozenset({"Json", "Provider", "Prompt"})
COMPILER_PRIMITIVE_TYPE_NAMES = frozenset(
    {
        "String", "Int", "Float", "Bool", "Json", "Provider", "Prompt",
        "PathRel", "RunId", "Symbol", "Value",
    }
)


class _TransportValueError(ValueError):
    """A transport failure retains its known leaf and optional path violation."""

    def __init__(self, message, *, value_path=None, violation=None):
        super().__init__(message)
        self.value_path = value_path
        self.violation = violation


def _require_exact_descriptor_keys(
    descriptor: Mapping[str, Any],
    expected: set[str],
    *,
    context: str,
) -> None:
    if set(descriptor) != expected:
        raise ValueError(f"{context} must contain exactly {sorted(expected)}")


def _require_descriptor_name(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _descriptor_sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{context} must be a sequence")
    return value


def _validate_normalized_descriptor_fields(
    fields: Any,
    *,
    context: str,
) -> None:
    names: set[str] = set()
    for index, descriptor_field in enumerate(
        _descriptor_sequence(fields, context=context)
    ):
        field_context = f"{context}[{index}]"
        if not isinstance(descriptor_field, Mapping):
            raise ValueError(f"{field_context} must be a mapping")
        _require_exact_descriptor_keys(
            descriptor_field,
            {"name", "type"},
            context=field_context,
        )
        name = _require_descriptor_name(
            descriptor_field["name"],
            context=f"{field_context}.name",
        )
        if name in names:
            raise ValueError(f"{context} contains duplicate names")
        names.add(name)
        validate_compiler_normalized_type_descriptor(
            descriptor_field["type"],
            context=f"{field_context}.type",
        )


def validate_compiler_normalized_type_descriptor(
    descriptor: Any,
    *,
    context: str = "normalized_type_descriptor",
) -> None:
    """Validate the compiler's one closed normalized type-descriptor schema."""

    if not isinstance(descriptor, Mapping):
        raise ValueError(f"{context} must be a mapping")
    kind = descriptor.get("kind")
    if kind == "primitive":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        return
    if kind == "enum":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "allowed"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        allowed = _descriptor_sequence(
            descriptor["allowed"],
            context=f"{context}.allowed",
        )
        if (
            not allowed
            or any(not isinstance(item, str) or not item for item in allowed)
            or len(set(allowed)) != len(allowed)
        ):
            raise ValueError(
                f"{context}.allowed must be a non-empty unique string sequence"
            )
        return
    if kind == "path":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "under", "must_exist_target"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        _require_descriptor_name(descriptor["under"], context=f"{context}.under")
        if not isinstance(descriptor["must_exist_target"], bool):
            raise ValueError(f"{context}.must_exist_target must be boolean")
        return
    if kind in {"optional", "list"}:
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "item"},
            context=context,
        )
        validate_compiler_normalized_type_descriptor(
            descriptor["item"],
            context=f"{context}.item",
        )
        return
    if kind == "map":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "key", "value"},
            context=context,
        )
        validate_compiler_normalized_type_descriptor(
            descriptor["key"],
            context=f"{context}.key",
        )
        validate_compiler_normalized_type_descriptor(
            descriptor["value"],
            context=f"{context}.value",
        )
        return
    if kind == "record":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "fields"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        _validate_normalized_descriptor_fields(
            descriptor["fields"],
            context=f"{context}.fields",
        )
        return
    if kind == "union":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "name", "variants"},
            context=context,
        )
        _require_descriptor_name(descriptor["name"], context=f"{context}.name")
        variants = _descriptor_sequence(
            descriptor["variants"],
            context=f"{context}.variants",
        )
        if not variants:
            raise ValueError(f"{context}.variants must be a non-empty sequence")
        names: set[str] = set()
        for index, variant in enumerate(variants):
            variant_context = f"{context}.variants[{index}]"
            if not isinstance(variant, Mapping):
                raise ValueError(f"{variant_context} must be a mapping")
            _require_exact_descriptor_keys(
                variant,
                {"name", "fields"},
                context=variant_context,
            )
            name = _require_descriptor_name(
                variant["name"],
                context=f"{variant_context}.name",
            )
            if name in names:
                raise ValueError(f"{context}.variants contains duplicate names")
            names.add(name)
            _validate_normalized_descriptor_fields(
                variant["fields"],
                context=f"{variant_context}.fields",
            )
        return
    if kind == "variant_case":
        _require_exact_descriptor_keys(
            descriptor,
            {"kind", "union_name", "variant", "fields"},
            context=context,
        )
        _require_descriptor_name(
            descriptor["union_name"],
            context=f"{context}.union_name",
        )
        _require_descriptor_name(
            descriptor["variant"],
            context=f"{context}.variant",
        )
        _validate_normalized_descriptor_fields(
            descriptor["fields"],
            context=f"{context}.fields",
        )
        return
    raise ValueError(f"{context} uses an unsupported type kind")


def is_transportable_type_descriptor(
    descriptor: Mapping[str, Any],
    *,
    allow_nested_structures: bool = False,
) -> bool:
    """Return whether one closed descriptor fits the direct JSON transport."""

    try:
        validate_compiler_normalized_type_descriptor(descriptor)
        return _is_transportable_descriptor(
            descriptor,
            allow_nested_structures=allow_nested_structures,
            collection_item=False,
            depth=0,
        )
    except (RecursionError, TypeError, ValueError):
        return False


def _is_transportable_descriptor(
    descriptor: Mapping[str, Any],
    *,
    allow_nested_structures: bool,
    collection_item: bool,
    depth: int,
) -> bool:
    if depth > MAX_TRANSPORT_VALUE_DEPTH:
        return False
    kind = descriptor["kind"]
    if kind == "primitive":
        return descriptor["name"] not in _NONTRANSPORTABLE_PRIMITIVES
    if kind in {"enum", "path"}:
        return True
    if kind in {"optional", "list"}:
        return _is_transportable_descriptor(
            descriptor["item"],
            allow_nested_structures=allow_nested_structures,
            collection_item=True,
            depth=depth + 1,
        )
    if kind == "map":
        return descriptor["key"] == {
            "kind": "primitive",
            "name": "String",
        } and _is_transportable_descriptor(
            descriptor["value"],
            allow_nested_structures=allow_nested_structures,
            collection_item=True,
            depth=depth + 1,
        )
    if kind == "record":
        return (
            (allow_nested_structures or not collection_item)
            and all(
                _is_transportable_descriptor(
                    field["type"],
                    allow_nested_structures=allow_nested_structures,
                    collection_item=False,
                    depth=depth + 1,
                )
                for field in descriptor["fields"]
            )
        )
    if kind == "union":
        return (
            (allow_nested_structures or not collection_item)
            and (
                not allow_nested_structures
                or all(
                    field["name"] != "variant"
                    for variant in descriptor["variants"]
                    for field in variant["fields"]
                )
            )
            and all(
                _is_transportable_descriptor(
                    field["type"],
                    allow_nested_structures=allow_nested_structures,
                    collection_item=False,
                    depth=depth + 1,
                )
                for variant in descriptor["variants"]
                for field in variant["fields"]
            )
        )
    return False


def transport_schema_for_descriptor(
    descriptor: Mapping[str, Any],
    *,
    allow_nested_structures: bool = False,
) -> dict[str, Any]:
    """Encode one transportable descriptor as an exact direct-value schema."""

    if not is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=allow_nested_structures,
    ):
        raise ValueError("normalized type descriptor is not transportable")
    return _transport_schema(descriptor)


_BOUNDARY_IGNORED_CONTRACT_KEYS = frozenset(
    {"default", "from", "projection", "__allow_unresolved_source"}
)


def normalize_boundary_contract_definition(value: Any) -> dict[str, Any]:
    """Return the existing structural wire-contract view without provenance."""

    if not isinstance(value, Mapping):
        raise ValueError("boundary contract must be a mapping")
    return {
        str(key): item
        for key, item in value.items()
        if key not in _BOUNDARY_IGNORED_CONTRACT_KEYS
    }


def compiled_boundary_rows(
    roots: Sequence[tuple[str, Mapping[str, Any]]],
    *,
    output: bool = False,
    relax_inactive_union_paths: bool = False,
    allow_nested_structures: bool = True,
) -> list[dict[str, Any]]:
    """Derive flattened call-boundary rows from checked nominal descriptors.

    This mirrors the frontend's established wire schema while deriving names,
    structural paths, exact transport contracts, and union activity from the
    neutral descriptors retained in the closed program.
    """

    rows: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}

    def contract_for(descriptor: Mapping[str, Any]) -> dict[str, Any]:
        validate_compiler_normalized_type_descriptor(descriptor)
        kind = descriptor["kind"]
        schema = transport_schema_for_descriptor(
            descriptor,
            allow_nested_structures=allow_nested_structures,
        )
        if schema["type"] == "relpath":
            schema = {"kind": "relpath", **schema}
        elif schema["type"] in {"optional", "list", "map"}:
            schema = {"kind": "collection", **schema}
        elif schema["type"] == "value":
            schema = {"kind": "value", **schema}
        else:
            schema = {"kind": "scalar", **schema}
        if kind == "primitive" and descriptor["name"] in {"RunId", "Symbol"}:
            # These prelude primitives have an established string wire shape.
            # Keep the exact builtin cases explicit so unknown primitives
            # cannot inherit the neutral codec's compatibility fallback.
            return {"kind": "scalar", "type": "string"}
        if kind == "primitive" and descriptor["name"] not in {
            "String", "Int", "Float", "Bool", "Value"
        }:
            raise ValueError("unsupported primitive has no exact boundary contract")
        return schema

    def add(name: str, path: tuple[str, ...], contract: dict[str, Any]) -> None:
        row = {"name": name, "path": list(path), "contract": contract}
        previous = seen.get(name)
        if previous is not None:
            if previous != row:
                raise ValueError("boundary projection has a conflicting wire name")
            return
        seen[name] = row
        rows.append(row)

    def flatten(
        descriptor: Mapping[str, Any],
        *,
        wire_root: str,
        path: tuple[str, ...],
        relax_here: bool = False,
    ) -> None:
        kind = descriptor["kind"]
        if kind == "record":
            for field in descriptor["fields"]:
                flatten(
                    field["type"],
                    wire_root=f"{wire_root}__{field['name']}",
                    path=(*path, field["name"]),
                )
            return
        if kind == "union":
            variant_names = tuple(variant["name"] for variant in descriptor["variants"])
            discr_name = f"{wire_root}__variant"
            discr_contract = {
                "kind": "scalar",
                "type": "enum",
                "allowed": list(variant_names),
            }
            if output:
                discr_contract["projection"] = {
                    "projection_class": "union_workflow_boundary",
                    "return_kind": "union",
                    "union_output_group": wire_root,
                    "discriminant_output": discr_name,
                    "field_role": "discriminant",
                    "active_variants": list(variant_names),
                }
            add(discr_name, (*path, "variant"), discr_contract)

            variant_rows: dict[str, list[tuple[str, tuple[str, ...], dict[str, Any]]]] = {}
            for variant in descriptor["variants"]:
                expanded: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []
                for field in variant["fields"]:
                    leaves = _flatten_descriptor_leaves(
                        field["type"],
                        wire_root=f"{wire_root}__{field['name']}",
                        path=(*path, field["name"]),
                        contract_for=contract_for,
                    )
                    expanded.extend(leaves)
                variant_rows[variant["name"]] = expanded

            all_rows: dict[
                str,
                dict[str, tuple[tuple[str, ...], dict[str, Any]]],
            ] = {}
            for variant_name, leaves in variant_rows.items():
                for leaf_name, leaf_path, leaf_contract in leaves:
                    all_rows.setdefault(leaf_name, {})[variant_name] = (
                        leaf_path,
                        leaf_contract,
                    )
            first_variant_rows = variant_rows[variant_names[0]]
            shared_names = {
                leaf_name
                for leaf_name, by_variant in all_rows.items()
                if len(by_variant) == len(variant_names)
                and all(
                    row_path == next(iter(by_variant.values()))[0]
                    and row_contract == next(iter(by_variant.values()))[1]
                    for row_path, row_contract in by_variant.values()
                )
            }
            ordered_names: list[str] = []
            ordered_names.extend(
                leaf_name
                for leaf_name, _, _ in first_variant_rows
                if leaf_name in shared_names
            )
            for variant_name in variant_names:
                ordered_names.extend(
                    leaf_name
                    for leaf_name, _, _ in variant_rows[variant_name]
                    if leaf_name not in shared_names and leaf_name not in ordered_names
                )
            for leaf_name in ordered_names:
                by_variant = all_rows[leaf_name]
                active = tuple(name for name in variant_names if name in by_variant)
                sample_path, sample_contract = by_variant[active[0]]
                if any(
                    row_path != sample_path or row_contract != sample_contract
                    for row_path, row_contract in by_variant.values()
                ):
                    raise ValueError("union boundary row is structurally ambiguous")
                contract = deepcopy(sample_contract)
                is_shared = len(active) == len(variant_names)
                if (
                    relax_here
                    and output
                    and not is_shared
                    and contract.get("type") == "relpath"
                    and contract.get("must_exist_target") is True
                ):
                    contract["must_exist_target"] = False
                if output:
                    contract["projection"] = {
                        "projection_class": "union_workflow_boundary",
                        "return_kind": "union",
                        "union_output_group": wire_root,
                        "discriminant_output": discr_name,
                        "field_role": "shared" if is_shared else "variant",
                        "active_variants": list(variant_names if is_shared else active),
                    }
                add(leaf_name, sample_path, contract)
            return
        add(f"{wire_root}", path, contract_for(descriptor))

    for root_name, descriptor in roots:
        validate_compiler_normalized_type_descriptor(descriptor)
        relax_root_union = relax_inactive_union_paths or (
            output and descriptor["kind"] == "union"
        )
        if descriptor["kind"] in {"record", "union"}:
            flatten(
                descriptor,
                wire_root=root_name,
                path=(root_name,),
                relax_here=descriptor["kind"] == "union" and relax_root_union,
            )
        else:
            add(root_name, (root_name,), contract_for(descriptor))
    return rows


def command_boundary_rows(
    source_formal: str, descriptor: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Derive command input rows, including a variant's payload-only view."""

    validate_compiler_normalized_type_descriptor(descriptor)
    if descriptor["kind"] != "variant_case":
        return compiled_boundary_rows([(source_formal, descriptor)])
    rows = []
    for field in descriptor["fields"]:
        field_name = field["name"]
        for row in compiled_boundary_rows([(f"{source_formal}__{field_name}", field["type"])]):
            rows.append({**row, "path": [source_formal, field_name, *row["path"][1:]]})
    return rows


def command_boundary_row(
    source_formal: str, descriptor: Mapping[str, Any], native_wire_name: str,
) -> dict[str, Any] | None:
    """Select the exact derived wire row; authored suffixes are separate."""

    return next((row for row in command_boundary_rows(source_formal, descriptor)
        if row["name"] == native_wire_name), None)


def command_boundary_value(
    value: Any, descriptor: Mapping[str, Any], row: Mapping[str, Any],
) -> Any:
    """Select an input row through active union payloads, returning None if absent."""

    current = value
    current_type = descriptor
    for field_name in row["path"][1:]:
        if not isinstance(current, Mapping):
            return None
        fields = _command_active_fields(current, current_type)
        if fields is None:
            return None
        if current_type["kind"] == "union" and field_name == "variant":
            return current.get("variant")
        selected = next((field for field in fields if field["name"] == field_name), None)
        if selected is None:
            return None
        current_type = selected["type"]
        current = current.get(field_name)
        if current is None:
            return None
    return current


def _command_active_fields(value, descriptor):
    if descriptor["kind"] != "union":
        return descriptor.get("fields", ())
    variant = next((variant for variant in descriptor["variants"]
        if variant["name"] == value.get("variant")), None)
    return variant["fields"] if variant is not None else None


def _flatten_descriptor_leaves(
    descriptor: Mapping[str, Any],
    *,
    wire_root: str,
    path: tuple[str, ...],
    contract_for: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> list[tuple[str, tuple[str, ...], dict[str, Any]]]:
    if descriptor["kind"] == "record":
        return [
            leaf
            for field in descriptor["fields"]
            for leaf in _flatten_descriptor_leaves(
                field["type"],
                wire_root=f"{wire_root}__{field['name']}",
                path=(*path, field["name"]),
                contract_for=contract_for,
            )
        ]
    return [(wire_root, path, contract_for(descriptor))]


def _transport_schema(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    kind = descriptor["kind"]
    if kind == "primitive":
        primitive = descriptor["name"]
        if primitive == "String":
            return {"type": "string"}
        if primitive == "Int":
            return {"type": "integer"}
        if primitive == "Float":
            return {"type": "float"}
        if primitive == "Bool":
            return {"type": "bool"}
        if primitive == "Value":
            return {"type": "value"}
        return {"type": "string"}
    if kind == "enum":
        return {"type": "enum", "allowed": list(descriptor["allowed"])}
    if kind == "path":
        return {
            "type": "relpath",
            "under": descriptor["under"],
            "must_exist_target": descriptor["must_exist_target"],
        }
    if kind == "optional":
        return {"type": "optional", "item": _transport_schema(descriptor["item"])}
    if kind == "list":
        return {"type": "list", "items": _transport_schema(descriptor["item"])}
    if kind == "map":
        return {
            "type": "map",
            "keys": {"type": "string"},
            "values": _transport_schema(descriptor["value"]),
        }
    if kind == "record":
        return {
            "type": "record",
            "record_name": descriptor["name"],
            "fields": [
                {"name": field["name"], **_transport_schema(field["type"])}
                for field in descriptor["fields"]
            ],
        }
    if kind == "union":
        variant_names = [variant["name"] for variant in descriptor["variants"]]
        return {
            "type": "union",
            "union_name": descriptor["name"],
            "discriminant": {
                "name": "variant",
                "type": "enum",
                "allowed": variant_names,
            },
            "variants": {
                variant["name"]: {
                    "fields": [
                        {
                            "name": field["name"],
                            **_transport_schema(field["type"]),
                        }
                        for field in variant["fields"]
                    ]
                }
                for variant in descriptor["variants"]
            },
        }
    raise ValueError("normalized type descriptor is not transportable")


def transport_descriptor_for_schema(
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Decode one generated direct-value schema into its neutral descriptor."""

    descriptor = _transport_descriptor_from_schema(
        schema,
        context="transport_schema",
        depth=0,
    )
    validate_compiler_normalized_type_descriptor(
        descriptor,
        context="transport_schema.descriptor",
    )
    return descriptor


def _transport_descriptor_from_schema(
    schema: Any,
    *,
    context: str,
    depth: int,
) -> dict[str, Any]:
    if depth > MAX_TRANSPORT_VALUE_DEPTH:
        raise ValueError("transport schema exceeds the maximum depth")
    if not isinstance(schema, Mapping):
        raise ValueError(f"{context} must be a mapping")
    value_type = schema.get("type")
    primitive_names = {
        "string": "String",
        "integer": "Int",
        "float": "Float",
        "bool": "Bool",
        "value": "Value",
    }
    if value_type in primitive_names:
        return {"kind": "primitive", "name": primitive_names[value_type]}
    if value_type == "enum":
        allowed = list(
            _descriptor_sequence(
                schema.get("allowed"),
                context=f"{context}.allowed",
            )
        )
        schema_name = schema.get("name")
        enum_name = (
            schema_name
            if isinstance(schema_name, str) and schema_name
            else "TransportEnum"
        )
        return {
            "kind": "enum",
            "name": enum_name,
            "allowed": allowed,
        }
    if value_type == "relpath":
        schema_name = schema.get("name")
        path_name = (
            schema_name
            if isinstance(schema_name, str) and schema_name
            else "TransportRelPath"
        )
        return {
            "kind": "path",
            "name": path_name,
            "under": schema.get("under"),
            "must_exist_target": schema.get("must_exist_target"),
        }
    if value_type == "optional":
        return {
            "kind": "optional",
            "item": _transport_descriptor_from_schema(
                schema.get("item"),
                context=f"{context}.item",
                depth=depth + 1,
            ),
        }
    if value_type == "list":
        return {
            "kind": "list",
            "item": _transport_descriptor_from_schema(
                schema.get("items"),
                context=f"{context}.items",
                depth=depth + 1,
            ),
        }
    if value_type == "map":
        key_descriptor = _transport_descriptor_from_schema(
            schema.get("keys"),
            context=f"{context}.keys",
            depth=depth + 1,
        )
        if key_descriptor != {"kind": "primitive", "name": "String"}:
            raise ValueError("transport schema map keys must be strings")
        return {
            "kind": "map",
            "key": key_descriptor,
            "value": _transport_descriptor_from_schema(
                schema.get("values"),
                context=f"{context}.values",
                depth=depth + 1,
            ),
        }
    if value_type == "record":
        record_name = _require_descriptor_name(
            schema.get("record_name"),
            context=f"{context}.record_name",
        )
        return {
            "kind": "record",
            "name": record_name,
            "fields": _transport_descriptor_fields_from_schema(
                schema.get("fields"),
                context=f"{context}.fields",
                depth=depth,
            ),
        }
    if value_type == "union":
        return _transport_union_descriptor_from_schema(schema, context=context, depth=depth)
    raise ValueError(f"{context} uses an unsupported transport schema type")


def _transport_union_descriptor_from_schema(
    schema: Mapping[str, Any], *, context: str, depth: int,
) -> dict[str, Any]:
    union_name = _require_descriptor_name(
        schema.get("union_name"),
        context=f"{context}.union_name",
    )
    discriminant = schema.get("discriminant")
    variants = schema.get("variants")
    if not isinstance(discriminant, Mapping) or not isinstance(
        variants,
        Mapping,
    ):
        raise ValueError(f"{context} union schema is malformed")
    allowed = list(
        _descriptor_sequence(
            discriminant.get("allowed"),
            context=f"{context}.discriminant.allowed",
        )
    )
    if (
        discriminant.get("name") != "variant"
        or discriminant.get("type") != "enum"
    ):
        raise ValueError(f"{context} union discriminant is malformed")
    _validate_transport_union_tags(allowed, variants, context=context)
    descriptor_variants: list[dict[str, Any]] = []
    for variant_name in allowed:
        variant = variants.get(variant_name)
        if not isinstance(variant, Mapping):
            raise ValueError(f"{context} union variant is malformed")
        descriptor_variants.append(
            {
                "name": variant_name,
                "fields": _transport_descriptor_fields_from_schema(
                    variant.get("fields"),
                    context=f"{context}.variants[{variant_name!r}].fields",
                    depth=depth,
                ),
            }
        )
    return {
        "kind": "union",
        "name": union_name,
        "variants": descriptor_variants,
    }


def _validate_transport_union_tags(allowed: list[Any], variants: Mapping[Any, Any], *, context: str) -> None:
    if any(not isinstance(name, str) for name in allowed) or any(
        not isinstance(name, str) for name in variants
    ):
        raise ValueError(f"{context} union discriminant is malformed")
    if len(set(allowed)) != len(allowed) or set(allowed) != set(variants):
        raise ValueError(f"{context} union discriminant is malformed")


def _transport_descriptor_fields_from_schema(
    fields: Any,
    *,
    context: str,
    depth: int,
) -> list[dict[str, Any]]:
    descriptor_fields: list[dict[str, Any]] = []
    for index, field in enumerate(_descriptor_sequence(fields, context=context)):
        field_context = f"{context}[{index}]"
        if not isinstance(field, Mapping):
            raise ValueError(f"{field_context} must be a mapping")
        descriptor_fields.append(
            {
                "name": _require_descriptor_name(
                    field.get("name"),
                    context=f"{field_context}.name",
                ),
                "type": _transport_descriptor_from_schema(
                    field,
                    context=field_context,
                    depth=depth + 1,
                ),
            }
        )
    return descriptor_fields


def validate_transport_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    allow_nested_structures: bool = False,
    path_validator: Callable[[str, Mapping[str, Any]], Any] | None = None,
) -> Any:
    """Validate and return one direct JSON value against its descriptor."""

    try:
        validate_compiler_normalized_type_descriptor(descriptor)
    except (RecursionError, TypeError, ValueError) as exc:
        raise _TransportValueError("normalized type descriptor is invalid", value_path="$") from exc
    if _descriptor_exceeds_transport_depth(descriptor, depth=0):
        raise _TransportValueError("transport descriptor exceeds the maximum depth", value_path="$")
    if not is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=allow_nested_structures,
    ):
        raise _TransportValueError("normalized type descriptor is not transportable", value_path="$")
    normalized = _validate_descriptor_value(
        value,
        descriptor,
        depth=0,
        value_path="$",
        active_container_ids=set(),
        path_validator=path_validator,
    )
    try:
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _TransportValueError("transport value is not canonical JSON", value_path="$") from exc
    if len(encoded) > MAX_TRANSPORT_VALUE_BYTES:
        raise _TransportValueError("transport value exceeds the canonical JSON byte limit", value_path="$")
    return normalized


def _descriptor_exceeds_transport_depth(
    descriptor: Mapping[str, Any],
    *,
    depth: int,
) -> bool:
    if depth > MAX_TRANSPORT_VALUE_DEPTH:
        return True
    kind = descriptor["kind"]
    if kind in {"optional", "list"}:
        return _descriptor_exceeds_transport_depth(
            descriptor["item"],
            depth=depth + 1,
        )
    if kind == "map":
        return _descriptor_exceeds_transport_depth(
            descriptor["key"],
            depth=depth + 1,
        ) or _descriptor_exceeds_transport_depth(
            descriptor["value"],
            depth=depth + 1,
        )
    if kind in {"record", "variant_case"}:
        return any(
            _descriptor_exceeds_transport_depth(
                field["type"],
                depth=depth + 1,
            )
            for field in descriptor["fields"]
        )
    if kind == "union":
        return any(
            _descriptor_exceeds_transport_depth(
                field["type"],
                depth=depth + 1,
            )
            for variant in descriptor["variants"]
            for field in variant["fields"]
        )
    return False


def _validate_descriptor_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    depth: int,
    value_path: str,
    active_container_ids: set[int],
    path_validator: Callable[[str, Mapping[str, Any]], Any] | None,
) -> Any:
    if depth > MAX_TRANSPORT_VALUE_DEPTH:
        raise _TransportValueError("transport value exceeds the maximum depth", value_path=value_path)
    kind = descriptor["kind"]
    if kind == "primitive":
        return _validate_primitive_value(
            value,
            descriptor["name"],
            value_path,
            depth=depth,
            active_container_ids=active_container_ids,
        )
    if kind == "enum":
        if type(value) is not str or value not in descriptor["allowed"]:
            raise _TransportValueError(f"{value_path} is not an allowed enum value", value_path=value_path)
        return value
    if kind == "path":
        return _validate_transport_path(value, descriptor, value_path, path_validator)
    if kind == "optional":
        if value is None:
            return None
        return _validate_descriptor_value(
            value,
            descriptor["item"],
            depth=depth + 1,
            value_path=value_path,
            active_container_ids=active_container_ids,
            path_validator=path_validator,
        )
    if kind == "list":
        if type(value) is not list:
            raise _TransportValueError(f"{value_path} is not a list", value_path=value_path)
        return _validate_container(
            value,
            value_path=value_path,
            active_container_ids=active_container_ids,
            visit=lambda: [
                _validate_descriptor_value(
                    item,
                    descriptor["item"],
                    depth=depth + 1,
                    value_path=f"{value_path}/{index}",
                    active_container_ids=active_container_ids,
                    path_validator=path_validator,
                )
                for index, item in enumerate(value)
            ],
        )
    if kind == "map":
        if type(value) is not dict:
            raise _TransportValueError(f"{value_path} is not a map", value_path=value_path)
        for key in value:
            if type(key) is not str:
                raise _TransportValueError(f"{value_path} map key is not a string", value_path=value_path)
        return _validate_container(
            value,
            value_path=value_path,
            active_container_ids=active_container_ids,
            visit=lambda: {
                key: _validate_descriptor_value(
                    item,
                    descriptor["value"],
                    depth=depth + 1,
                    value_path=f"{value_path}/{_escape_pointer_token(key)}",
                    active_container_ids=active_container_ids,
                    path_validator=path_validator,
                )
                for key, item in value.items()
            },
        )
    if kind == "record":
        if type(value) is not dict:
            raise _TransportValueError(f"{value_path} record fields are invalid", value_path=value_path)
        expected = [field["name"] for field in descriptor["fields"]]
        if set(value) != set(expected):
            raise _TransportValueError(f"{value_path} record fields are missing or extra", value_path=value_path)
        return _validate_container(
            value,
            value_path=value_path,
            active_container_ids=active_container_ids,
            visit=lambda: {
                field["name"]: _validate_descriptor_value(
                    value[field["name"]],
                    field["type"],
                    depth=depth + 1,
                    value_path=(
                        f"{value_path}/{_escape_pointer_token(field['name'])}"
                    ),
                    active_container_ids=active_container_ids,
                    path_validator=path_validator,
                )
                for field in descriptor["fields"]
            },
        )
    if kind == "union":
        if type(value) is not dict or type(value.get("variant")) is not str:
            raise _TransportValueError(f"{value_path} union tag is invalid", value_path=value_path)
        variants = {
            variant["name"]: variant for variant in descriptor["variants"]
        }
        variant = variants.get(value["variant"])
        if variant is None:
            raise _TransportValueError(f"{value_path} union tag is unknown", value_path=value_path)
        expected = {"variant", *(field["name"] for field in variant["fields"])}
        if set(value) != expected:
            raise _TransportValueError(f"{value_path} union record fields are missing or extra", value_path=value_path)
        return _validate_container(
            value,
            value_path=value_path,
            active_container_ids=active_container_ids,
            visit=lambda: {
                "variant": value["variant"],
                **{
                    field["name"]: _validate_descriptor_value(
                        value[field["name"]],
                        field["type"],
                        depth=depth + 1,
                        value_path=(
                            f"{value_path}/{_escape_pointer_token(field['name'])}"
                        ),
                        active_container_ids=active_container_ids,
                        path_validator=path_validator,
                    )
                    for field in variant["fields"]
                },
            },
        )
    raise _TransportValueError("normalized type descriptor is not transportable", value_path=value_path)


def _validate_primitive_value(
    value: Any,
    name: str,
    value_path: str,
    *,
    depth: int,
    active_container_ids: set[int],
) -> Any:
    if name == "Value":
        return _validate_json_value(
            value,
            depth=depth,
            value_path=value_path,
            active_container_ids=active_container_ids,
        )
    if name == "String" or name not in {"Int", "Float", "Bool"}:
        if type(value) is not str:
            raise _TransportValueError(f"{value_path} is not a {name} string", value_path=value_path)
        return value
    if name == "Int":
        if type(value) is not int:
            raise _TransportValueError(f"{value_path} is not an Int", value_path=value_path)
        return value
    if name == "Float":
        if type(value) not in {int, float}:
            raise _TransportValueError(f"{value_path} is not a finite Float", value_path=value_path)
        try:
            normalized_float = float(value)
        except (OverflowError, ValueError):
            raise _TransportValueError(f"{value_path} is not a finite Float", value_path=value_path) from None
        if not math.isfinite(normalized_float):
            raise _TransportValueError(f"{value_path} is not a finite Float", value_path=value_path)
        return normalized_float
    if name == "Bool":
        if type(value) is not bool:
            raise _TransportValueError(f"{value_path} is not a Bool", value_path=value_path)
        return value
    raise _TransportValueError(f"{value_path} is not transportable", value_path=value_path)


def _validate_json_value(
    value: Any,
    *,
    depth: int,
    value_path: str,
    active_container_ids: set[int],
) -> Any:
    if depth > MAX_TRANSPORT_VALUE_DEPTH:
        raise _TransportValueError("transport value exceeds the maximum depth", value_path=value_path)
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _TransportValueError(f"{value_path} is not a finite JSON number", value_path=value_path)
        return value
    if type(value) is list:
        return _validate_container(
            value,
            value_path=value_path,
            active_container_ids=active_container_ids,
            visit=lambda: [
                _validate_json_value(
                    item,
                    depth=depth + 1,
                    value_path=f"{value_path}/{index}",
                    active_container_ids=active_container_ids,
                )
                for index, item in enumerate(value)
            ],
        )
    if type(value) is dict:
        for key in value:
            if type(key) is not str:
                raise _TransportValueError(f"{value_path} map key is not a string", value_path=value_path)
        return _validate_container(
            value,
            value_path=value_path,
            active_container_ids=active_container_ids,
            visit=lambda: {
                key: _validate_json_value(
                    item,
                    depth=depth + 1,
                    value_path=f"{value_path}/{_escape_pointer_token(key)}",
                    active_container_ids=active_container_ids,
                )
                for key, item in value.items()
            },
        )
    raise _TransportValueError(f"{value_path} is not a transportable JSON value", value_path=value_path)


def _validate_transport_path(value, descriptor, value_path, path_validator):
    if type(value) is not str:
        raise _TransportValueError(f"{value_path} is not a path string", value_path=value_path)
    if path_validator is None:
        return value
    try:
        return path_validator(value, descriptor)
    except _TransportValueError as exc:
        if exc.value_path is None:
            exc.value_path = value_path
        raise
    except ValueError as exc:
        raise _TransportValueError(str(exc), value_path=value_path) from exc


def _validate_container(
    value: list[Any] | dict[Any, Any],
    *,
    active_container_ids: set[int],
    value_path: str,
    visit: Any,
) -> Any:
    container_id = id(value)
    if container_id in active_container_ids:
        raise _TransportValueError("transport value contains a container cycle", value_path=value_path)
    active_container_ids.add(container_id)
    try:
        return visit()
    finally:
        active_container_ids.remove(container_id)


def _escape_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


__all__ = [
    "COMPILER_PRIMITIVE_TYPE_NAMES",
    "MAX_TRANSPORT_VALUE_BYTES",
    "MAX_TRANSPORT_VALUE_DEPTH",
    "is_transportable_type_descriptor",
    "transport_descriptor_for_schema",
    "transport_schema_for_descriptor",
    "validate_compiler_normalized_type_descriptor",
    "validate_transport_value",
]
