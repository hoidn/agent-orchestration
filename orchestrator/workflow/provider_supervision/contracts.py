"""Pure typed-result contracts shared by provider-supervision layers."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from orchestrator._common.canonical import compact_ascii_json_dumps
from ...contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
)
from ...exceptions import parse_validation_subject_ref

if TYPE_CHECKING:
    from ..executable_ir import (
        ExecutableContract,
        ProviderSupervisionMemberConfig,
    )


_RESULT_METADATA_KEYS = frozenset(
    {
        "source_map_subject",
        "source_map_subjects_by_variant",
        "guidance",
        "description",
        "format_hint",
        "example",
        "guidance_context",
        "guidance_by_variant",
        "result_guidance",
    }
)
_DIRECT_GUIDANCE_KEYS = frozenset(
    {"description", "format_hint", "example", "guidance_context"}
)
_SUBJECT_KEYS = frozenset(
    {"subject_kind", "subject_name", "workflow_name"}
)
_MAX_CONTRACT_NESTING = 256


def _thaw(
    value: Any,
    *,
    _active: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    if _depth > _MAX_CONTRACT_NESTING:
        raise ValueError("result contract nesting exceeds the supported limit")
    if isinstance(value, (Mapping, tuple, list)):
        active = set() if _active is None else _active
        identity = id(value)
        if identity in active:
            raise ValueError("result contract contains a reference cycle")
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                return {
                    key: _thaw(
                        item,
                        _active=active,
                        _depth=_depth + 1,
                    )
                    for key, item in value.items()
                }
            return [
                _thaw(
                    item,
                    _active=active,
                    _depth=_depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return value


def _validate_descriptor_shape(
    descriptor: Mapping[str, Any],
) -> None:
    kind = descriptor.get("kind")
    expected_keys = {
        "primitive": {"kind", "name"},
        "enum": {"kind", "name", "allowed"},
        "path": {
            "kind",
            "name",
            "under",
            "must_exist_target",
        },
        "optional": {"kind", "item"},
        "list": {"kind", "item"},
        "map": {"kind", "key", "value"},
        "record": {"kind", "name", "fields"},
        "union": {"kind", "name", "variants"},
    }.get(kind)
    if expected_keys is None or set(descriptor) != expected_keys:
        raise ValueError("result type descriptor is not closed")
    if kind in {"primitive", "enum", "path", "record", "union"}:
        if (
            not isinstance(descriptor.get("name"), str)
            or not descriptor["name"]
        ):
            raise ValueError("result type descriptor name is invalid")
    if kind == "primitive":
        return
    if kind == "enum":
        allowed = descriptor.get("allowed")
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(not isinstance(item, str) or not item for item in allowed)
            or len(set(allowed)) != len(allowed)
        ):
            raise ValueError("enum result type descriptor is invalid")
        return
    if kind == "path":
        under = descriptor.get("under")
        under_path = (
            PurePosixPath(under)
            if isinstance(under, str)
            else None
        )
        if (
            under_path is None
            or under_path.is_absolute()
            or ".." in under_path.parts
            or not isinstance(
                descriptor.get("must_exist_target"),
                bool,
            )
        ):
            raise ValueError("path result type descriptor is invalid")
        return
    if kind in {"optional", "list"}:
        item = _mapping(descriptor.get("item"), f"{kind}.item")
        _validate_descriptor_shape(item)
        return
    if kind == "map":
        key = _mapping(descriptor.get("key"), "map.key")
        value = _mapping(descriptor.get("value"), "map.value")
        _validate_descriptor_shape(key)
        _validate_descriptor_shape(value)
        return
    member_key = "fields" if kind == "record" else "variants"
    members = descriptor.get(member_key)
    if not isinstance(members, list):
        raise ValueError(f"{kind} result type members are invalid")
    seen: set[str] = set()
    for member in members:
        node = _mapping(member, f"{kind} result type member")
        if set(node) != {"name", "fields" if kind == "union" else "type"}:
            raise ValueError(f"{kind} result type member is not closed")
        name = node.get("name")
        if (
            not isinstance(name, str)
            or not name
            or name in seen
        ):
            raise ValueError(
                f"{kind} result type member name is invalid"
            )
        seen.add(name)
        if kind == "record":
            child = _mapping(node.get("type"), "record field type")
            _validate_descriptor_shape(child)
            continue
        fields = node.get("fields")
        if not isinstance(fields, list):
            raise ValueError("union variant fields are invalid")
        field_names: set[str] = set()
        for field in fields:
            field_node = _mapping(field, "union variant field")
            if set(field_node) != {"name", "type"}:
                raise ValueError("union variant field is not closed")
            field_name = field_node.get("name")
            if (
                not isinstance(field_name, str)
                or not field_name
                or field_name in field_names
            ):
                raise ValueError("union variant field name is invalid")
            field_names.add(field_name)
            child = _mapping(
                field_node.get("type"),
                "union variant field type",
            )
            _validate_descriptor_shape(child)


def _descriptor(contract: ExecutableContract) -> dict[str, Any]:
    definition = contract.definition
    if not isinstance(definition, Mapping) or set(definition) != {"type"}:
        raise ValueError(
            "executable result contract definition must contain only type"
        )
    descriptor = definition.get("type")
    if not isinstance(descriptor, Mapping):
        raise ValueError("executable result contract type descriptor is missing")
    thawed = _thaw(descriptor)
    _validate_descriptor_shape(thawed)
    _validate_transportable_descriptor(thawed)
    return thawed


def _pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(
        part.replace("~", "~0").replace("/", "~1")
        for part in path
    )


def _leaf_contract(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    kind = descriptor.get("kind")
    if kind == "primitive":
        names = {
            "String": "string",
            "Int": "integer",
            "Float": "float",
            "Bool": "bool",
            "Symbol": "string",
            "RunId": "string",
            "PathRel": "string",
            "Value": "value",
        }
        name = descriptor.get("name")
        if name not in names:
            raise ValueError(f"unsupported primitive result type: {name!r}")
        return {"type": names[name]}
    if kind == "enum":
        allowed = descriptor.get("allowed")
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(not isinstance(item, str) for item in allowed)
        ):
            raise ValueError("enum result descriptor is invalid")
        return {"type": "enum", "allowed": list(allowed)}
    if kind == "path":
        under = descriptor.get("under")
        must_exist = descriptor.get("must_exist_target")
        if not isinstance(under, str) or not isinstance(must_exist, bool):
            raise ValueError(
                "path result descriptor must preserve under and "
                "must_exist_target refinement metadata"
            )
        return {
            "type": "relpath",
            "under": under,
            "must_exist_target": must_exist,
        }
    if kind == "optional":
        return {
            "type": "optional",
            "item": _leaf_contract(
                _mapping(descriptor.get("item"), "optional.item")
            ),
        }
    if kind == "list":
        return {
            "type": "list",
            "items": _leaf_contract(
                _mapping(descriptor.get("item"), "list.item")
            ),
        }
    if kind == "map":
        key = _mapping(descriptor.get("key"), "map.key")
        if key.get("kind") != "primitive" or key.get("name") != "String":
            raise ValueError("transportable map result keys must be String")
        return {
            "type": "map",
            "keys": {"type": "string"},
            "values": _leaf_contract(
                _mapping(descriptor.get("value"), "map.value")
            ),
        }
    raise ValueError(
        f"unsupported leaf result descriptor kind: {kind!r}"
    )


def _fields(
    fields: Any,
    *,
    prefix: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if not isinstance(fields, list):
        raise ValueError("result descriptor fields must be a list")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in fields:
        node = _mapping(field, "result descriptor field")
        name = node.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("result descriptor field names must be unique")
        seen.add(name)
        descriptor = _mapping(node.get("type"), f"field {name}.type")
        path = (*prefix, name)
        if descriptor.get("kind") == "record":
            output.extend(
                _fields(descriptor.get("fields"), prefix=path)
            )
            continue
        output.append(
            {
                "name": "__".join(path),
                "json_pointer": _pointer(path),
                **_leaf_contract(descriptor),
            }
        )
    generated_names = [field["name"] for field in output]
    if len(generated_names) != len(set(generated_names)):
        raise ValueError(
            "flattened result descriptor field names must be unique"
        )
    return output


def derive_result_bundle_contract(
    contract: ExecutableContract,
    *,
    path: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Derive ordinary validator and prompt contracts for one typed result."""

    descriptor = _descriptor(contract)
    kind = descriptor.get("kind")
    if kind == "record":
        payload = {
            "path": path,
            "fields": _fields(descriptor.get("fields")),
        }
        return "output_bundle", payload, descriptor
    if kind == "union":
        variants = descriptor.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError("union result descriptor variants are invalid")
        variant_fields: dict[str, list[dict[str, Any]]] = {}
        for variant in variants:
            node = _mapping(variant, "union variant")
            name = node.get("name")
            if (
                not isinstance(name, str)
                or not name
                or name in variant_fields
            ):
                raise ValueError("union variant names must be unique")
            variant_fields[name] = _fields(node.get("fields"))

        common_keys: set[str] | None = None
        specs_by_variant: dict[str, dict[str, dict[str, Any]]] = {}
        for name, fields in variant_fields.items():
            indexed = {
                compact_ascii_json_dumps(field): field
                for field in fields
            }
            specs_by_variant[name] = indexed
            common_keys = (
                set(indexed)
                if common_keys is None
                else common_keys & set(indexed)
            )
        shared_keys = common_keys or set()
        first_variant = next(iter(specs_by_variant.values()))
        shared_fields = [
            field
            for key, field in first_variant.items()
            if key in shared_keys
        ]
        payload = {
            "path": path,
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": list(variant_fields),
            },
            "shared_fields": shared_fields,
            "variants": {
                name: {
                    "fields": [
                        field
                        for key, field in indexed.items()
                        if key not in shared_keys
                    ]
                }
                for name, indexed in specs_by_variant.items()
            },
        }
        return "variant_output", payload, descriptor
    payload = {
        "path": path,
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                **_leaf_contract(descriptor),
            }
        ],
    }
    return "output_bundle", payload, descriptor


def _descriptor_name(descriptor: Mapping[str, Any]) -> str:
    kind = descriptor.get("kind")
    if kind in {"primitive", "enum", "path", "record", "union"}:
        name = descriptor.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("result descriptor name is invalid")
        return name
    if kind == "optional":
        return (
            "Optional["
            + _descriptor_name(
                _mapping(descriptor.get("item"), "optional.item")
            )
            + "]"
        )
    if kind == "list":
        return (
            "List["
            + _descriptor_name(
                _mapping(descriptor.get("item"), "list.item")
            )
            + "]"
        )
    if kind == "map":
        return (
            "Map["
            + _descriptor_name(
                _mapping(descriptor.get("key"), "map.key")
            )
            + ", "
            + _descriptor_name(
                _mapping(descriptor.get("value"), "map.value")
            )
            + "]"
        )
    raise ValueError("result descriptor kind is invalid")


def _validate_transportable_descriptor(
    descriptor: Mapping[str, Any],
) -> None:
    kind = descriptor.get("kind")
    if kind == "record":
        _fields(descriptor.get("fields"))
        return
    if kind == "union":
        variants = descriptor.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError("union result descriptor variants are invalid")
        for variant in variants:
            node = _mapping(variant, "union variant")
            fields = _fields(node.get("fields"))
            if any(
                field.get("name") == "variant"
                or field.get("json_pointer") == "/variant"
                for field in fields
            ):
                raise ValueError(
                    "union result field collides with its discriminant"
                )
        return
    _leaf_contract(descriptor)


def derive_result_contract_identity(
    descriptor: Mapping[str, Any],
) -> tuple[str, str, str]:
    """Return canonical executable name, kind, and value type."""

    thawed = _thaw(descriptor)
    if not isinstance(thawed, Mapping):
        raise ValueError("result descriptor must be a mapping")
    _validate_descriptor_shape(thawed)
    _validate_transportable_descriptor(thawed)
    name = _descriptor_name(thawed)
    descriptor_kind = thawed.get("kind")
    contract_kind = (
        descriptor_kind
        if descriptor_kind in {"record", "union"}
        else "scalar"
    )
    primitive_value_types = {
        "Bool": "bool",
        "Float": "float",
        "Int": "integer",
        "String": "string",
        "Symbol": "string",
        "RunId": "string",
        "PathRel": "string",
    }
    value_type = (
        primitive_value_types.get(name, name)
        if descriptor_kind == "primitive"
        else name
    )
    return name, contract_kind, value_type


def validate_result_contract_identity(
    contract: ExecutableContract,
) -> dict[str, Any]:
    """Validate a closed wrapper against its canonical type descriptor."""

    descriptor = _descriptor(contract)
    expected = derive_result_contract_identity(descriptor)
    observed = (contract.name, contract.kind, contract.value_type)
    if observed != expected:
        raise ValueError(
            "executable result contract identity contradicts its descriptor"
        )
    return descriptor


def _structural_field(value: Any) -> dict[str, Any]:
    field = _mapping(value, "result contract field")
    return {
        key: _thaw(item)
        for key, item in field.items()
        if key not in _RESULT_METADATA_KEYS
    }


def _structural_prototype(
    contract_kind: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if contract_kind == "output_bundle":
        return {
            key: (
                [_structural_field(field) for field in item]
                if key == "fields"
                and isinstance(item, (tuple, list))
                else _thaw(item)
            )
            for key, item in value.items()
            if key != "guidance"
        }
    return {
        key: (
            [_structural_field(field) for field in item]
            if key == "shared_fields"
            and isinstance(item, (tuple, list))
            else {
                variant_name: {
                    variant_key: (
                        [
                            _structural_field(field)
                            for field in variant_value
                        ]
                        if variant_key == "fields"
                        and isinstance(variant_value, (tuple, list))
                        else _thaw(variant_value)
                    )
                    for variant_key, variant_value in _mapping(
                        variant,
                        "variant result contract",
                    ).items()
                }
                for variant_name, variant in _mapping(
                    item,
                    "variant result contracts",
                ).items()
            }
            if key == "variants"
            else _thaw(item)
        )
        for key, item in value.items()
        if key != "guidance"
    }


def _is_json_native(value: Any) -> bool:
    if value is None or isinstance(value, (bool, str)):
        return True
    if type(value) is int:
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_native(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_native(item)
            for key, item in value.items()
        )
    return False


def _decode_pointer(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, str) or (
        value and not value.startswith("/")
    ):
        return None
    if value == "":
        return ()
    decoded: list[str] = []
    for raw_part in value[1:].split("/"):
        index = 0
        chars: list[str] = []
        while index < len(raw_part):
            char = raw_part[index]
            if char != "~":
                chars.append(char)
                index += 1
                continue
            if (
                index + 1 >= len(raw_part)
                or raw_part[index + 1] not in {"0", "1"}
            ):
                return None
            chars.append(
                "~" if raw_part[index + 1] == "0" else "/"
            )
            index += 2
        decoded.append("".join(chars))
    return tuple(decoded)


def _metadata_free_schema(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                False
                if key == "must_exist_target"
                else _metadata_free_schema(item)
            )
            for key, item in value.items()
            if key not in _RESULT_METADATA_KEYS
        }
    if isinstance(value, (tuple, list)):
        return [_metadata_free_schema(item) for item in value]
    return value


def _validate_field_example(example: Any, field: Mapping[str, Any]) -> None:
    if not _is_json_native(example):
        raise ValueError("result guidance example must be JSON-compatible")
    try:
        validate_contract_value(
            example,
            _metadata_free_schema(field),
            workspace=Path.cwd(),
        )
    except OutputContractError as exc:
        raise ValueError(
            "result guidance example contradicts its field schema"
        ) from exc


def _validate_descriptor_example(
    value: Any,
    descriptor: Mapping[str, Any],
) -> None:
    if not _is_json_native(value):
        raise ValueError("result guidance example must be JSON-compatible")
    kind = descriptor.get("kind")
    if kind == "primitive":
        name = descriptor.get("name")
        valid = {
            "String": isinstance(value, str),
            "Symbol": isinstance(value, str),
            "RunId": isinstance(value, str),
            "PathRel": isinstance(value, str),
            "Int": type(value) is int,
            "Float": (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
            ),
            "Bool": isinstance(value, bool),
        }.get(name, False)
    elif kind == "enum":
        valid = value in descriptor.get("allowed", ())
    elif kind == "path":
        valid = isinstance(value, str)
    elif kind == "optional":
        if value is None:
            return
        _validate_descriptor_example(
            value,
            _mapping(descriptor.get("item"), "optional.item"),
        )
        return
    elif kind == "list":
        if not isinstance(value, list):
            valid = False
        else:
            item = _mapping(descriptor.get("item"), "list.item")
            for member in value:
                _validate_descriptor_example(member, item)
            return
    elif kind == "map":
        if not isinstance(value, Mapping) or any(
            not isinstance(key, str) for key in value
        ):
            valid = False
        else:
            item = _mapping(descriptor.get("value"), "map.value")
            for member in value.values():
                _validate_descriptor_example(member, item)
            return
    elif kind == "record":
        if not isinstance(value, Mapping):
            valid = False
        else:
            fields = descriptor.get("fields")
            if not isinstance(fields, list):
                raise ValueError("record result descriptor is invalid")
            expected_names = {
                field.get("name")
                for field in fields
                if isinstance(field, Mapping)
            }
            valid = set(value) == expected_names
            if valid:
                for field in fields:
                    field_node = _mapping(field, "record field")
                    _validate_descriptor_example(
                        value[field_node["name"]],
                        _mapping(field_node.get("type"), "record field type"),
                    )
                return
    elif kind == "union":
        if not isinstance(value, Mapping):
            valid = False
        else:
            variant_name = value.get("variant")
            variants = descriptor.get("variants")
            if not isinstance(variants, list):
                raise ValueError("union result descriptor is invalid")
            selected = next(
                (
                    variant
                    for variant in variants
                    if isinstance(variant, Mapping)
                    and variant.get("name") == variant_name
                ),
                None,
            )
            if selected is None:
                valid = False
            else:
                fields = selected.get("fields")
                if not isinstance(fields, list):
                    raise ValueError("union variant descriptor is invalid")
                expected_names = {
                    "variant",
                    *(
                        field.get("name")
                        for field in fields
                        if isinstance(field, Mapping)
                    ),
                }
                valid = set(value) == expected_names
                if valid:
                    for field in fields:
                        field_node = _mapping(field, "union field")
                        _validate_descriptor_example(
                            value[field_node["name"]],
                            _mapping(
                                field_node.get("type"),
                                "union field type",
                            ),
                        )
                    return
    else:
        valid = False
    if not valid:
        raise ValueError(
            "result guidance example contradicts its result descriptor"
        )


def _validate_guidance_payload(
    payload: Any,
    *,
    allow_context: bool,
    leaf_pointer: Any = None,
    field: Mapping[str, Any] | None = None,
    descriptor: Mapping[str, Any] | None = None,
) -> None:
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("result guidance payload must be a non-empty mapping")
    allowed = {"description", "format_hint", "example"}
    if allow_context:
        allowed.add("guidance_context")
    if set(payload) - allowed:
        raise ValueError("result guidance payload is not closed")
    for key in ("description", "format_hint"):
        if key in payload and (
            not isinstance(payload[key], str)
            or not payload[key].strip()
        ):
            raise ValueError(
                f"result guidance {key} must be a non-empty string"
            )
    if "example" in payload:
        if field is not None:
            _validate_field_example(payload["example"], field)
        elif descriptor is not None:
            _validate_descriptor_example(payload["example"], descriptor)
        elif not _is_json_native(payload["example"]):
            raise ValueError(
                "result guidance example must be JSON-compatible"
            )
    if "guidance_context" not in payload:
        return
    rows = payload["guidance_context"]
    if not isinstance(rows, (tuple, list)) or not rows:
        raise ValueError(
            "result guidance_context must be a non-empty sequence"
        )
    leaf_parts = _decode_pointer(leaf_pointer)
    if not leaf_parts:
        raise ValueError(
            "root result fields cannot declare guidance_context"
        )
    previous_depth = -1
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("result guidance context row must be a mapping")
        pointer = row.get("json_pointer")
        parts = _decode_pointer(pointer)
        if (
            not isinstance(pointer, str)
            or not pointer
            or parts is None
            or pointer in seen
            or len(parts) >= len(leaf_parts)
            or leaf_parts[:len(parts)] != parts
            or len(parts) <= previous_depth
        ):
            raise ValueError(
                "result guidance context pointer is invalid"
            )
        seen.add(pointer)
        previous_depth = len(parts)
        _validate_guidance_payload(
            {
                key: value
                for key, value in row.items()
                if key != "json_pointer"
            },
            allow_context=False,
        )


def _validate_subject(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != _SUBJECT_KEYS
        or parse_validation_subject_ref(value) is None
    ):
        raise ValueError("result contract source-map subject is invalid")


def _reject_nested_metadata(field: Mapping[str, Any]) -> None:
    for key in ("item", "items", "keys", "values"):
        nested = field.get(key)
        if nested is None:
            continue
        node = _mapping(nested, f"result field {key}")
        if set(node) & _RESULT_METADATA_KEYS:
            raise ValueError(
                "result contract metadata is forbidden in nested schemas"
            )
        _reject_nested_metadata(node)


def _validate_field_metadata(
    field: Any,
    *,
    role: str,
    allowed_variants: tuple[str, ...] = (),
) -> None:
    node = _mapping(field, "result contract field")
    allowed_metadata = set(_DIRECT_GUIDANCE_KEYS)
    if role == "variant_shared":
        allowed_metadata.update(
            {"guidance_by_variant", "source_map_subjects_by_variant"}
        )
    else:
        allowed_metadata.add("source_map_subject")
    if (set(node) & _RESULT_METADATA_KEYS) - allowed_metadata:
        raise ValueError("result contract metadata is misplaced")

    direct = {
        key: node[key]
        for key in _DIRECT_GUIDANCE_KEYS
        if key in node
    }
    if direct:
        _validate_guidance_payload(
            direct,
            allow_context=True,
            leaf_pointer=node.get("json_pointer"),
            field=node,
        )
    if "guidance_by_variant" in node:
        if direct:
            raise ValueError(
                "variant-scoped and direct result guidance conflict"
            )
        payloads = node["guidance_by_variant"]
        if not isinstance(payloads, Mapping) or not payloads:
            raise ValueError(
                "variant-scoped result guidance must be a mapping"
            )
        expected_order = tuple(
            name for name in allowed_variants if name in payloads
        )
        if tuple(payloads) != expected_order:
            raise ValueError(
                "variant-scoped result guidance keys are invalid"
            )
        for payload in payloads.values():
            _validate_guidance_payload(
                payload,
                allow_context=True,
                leaf_pointer=node.get("json_pointer"),
                field=node,
            )
    if "source_map_subject" in node:
        _validate_subject(node["source_map_subject"])
    if "source_map_subjects_by_variant" in node:
        subjects = node["source_map_subjects_by_variant"]
        if (
            not isinstance(subjects, Mapping)
            or tuple(subjects) != allowed_variants
        ):
            raise ValueError(
                "variant-scoped source-map subjects are invalid"
            )
        for subject in subjects.values():
            _validate_subject(subject)
    _reject_nested_metadata(node)


def _validate_prototype_metadata(
    contract_kind: str,
    prototype: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> None:
    allowed_bundle_metadata = {"guidance"}
    if (set(prototype) & _RESULT_METADATA_KEYS) - allowed_bundle_metadata:
        raise ValueError("result contract bundle metadata is misplaced")
    if "guidance" in prototype:
        _validate_guidance_payload(
            prototype["guidance"],
            allow_context=False,
            descriptor=descriptor,
        )
    if contract_kind == "output_bundle":
        fields = prototype.get("fields")
        if not isinstance(fields, (tuple, list)):
            raise ValueError("output result contract fields are invalid")
        for field in fields:
            _validate_field_metadata(field, role="output")
        return

    discriminant = _mapping(
        prototype.get("discriminant"),
        "variant result discriminant",
    )
    if set(discriminant) & _RESULT_METADATA_KEYS:
        raise ValueError(
            "variant result discriminant cannot carry metadata"
        )
    allowed = discriminant.get("allowed")
    if (
        not isinstance(allowed, (tuple, list))
        or any(not isinstance(name, str) for name in allowed)
    ):
        raise ValueError("variant result discriminant is invalid")
    allowed_variants = tuple(allowed)
    shared_fields = prototype.get("shared_fields", ())
    if not isinstance(shared_fields, (tuple, list)):
        raise ValueError("variant shared result fields are invalid")
    for field in shared_fields:
        _validate_field_metadata(
            field,
            role="variant_shared",
            allowed_variants=allowed_variants,
        )
    variants = _mapping(
        prototype.get("variants"),
        "variant result contracts",
    )
    if tuple(variants) != allowed_variants:
        raise ValueError("variant result contract keys are invalid")
    for variant_name, variant in variants.items():
        variant_node = _mapping(variant, "variant result contract")
        if set(variant_node) & _RESULT_METADATA_KEYS:
            raise ValueError("variant result metadata is misplaced")
        fields = variant_node.get("fields")
        if not isinstance(fields, (tuple, list)):
            raise ValueError("variant result fields are invalid")
        for field in fields:
            _validate_field_metadata(field, role="variant")


def bind_member_result_contract(
    member: ProviderSupervisionMemberConfig,
    *,
    path: str,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Validate one immutable prototype and bind its sole runtime path."""

    validate_result_contract_identity(member.result_contract)
    contract_kind, derived_contract, descriptor = (
        derive_result_bundle_contract(
            member.result_contract,
            path=path,
        )
    )
    common = member.provider_config.common
    prototypes = {
        "output_bundle": common.output_bundle,
        "variant_output": common.variant_output,
    }
    prototype = prototypes[contract_kind]
    opposite_kind = (
        "variant_output"
        if contract_kind == "output_bundle"
        else "output_bundle"
    )
    if (
        not isinstance(prototype, Mapping)
        or prototypes[opposite_kind] is not None
    ):
        raise ValueError(
            "provider supervision member result contract prototype "
            "is missing, ambiguous, or has the wrong kind"
        )
    prototype = _thaw(prototype)
    if "path" in prototype:
        raise ValueError(
            "provider supervision member result contract prototype "
            "must be pathless"
        )
    _validate_prototype_metadata(
        contract_kind,
        prototype,
        descriptor,
    )
    derived_prototype = {
        key: value
        for key, value in derived_contract.items()
        if key != "path"
    }
    if (
        _structural_prototype(contract_kind, prototype)
        != _structural_prototype(contract_kind, derived_prototype)
    ):
        raise ValueError(
            "provider supervision member result contract prototype "
            "contradicts its typed descriptor"
        )
    bound_contract = dict(prototype)
    bound_contract["path"] = path
    return contract_kind, bound_contract, descriptor
