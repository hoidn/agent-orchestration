"""Pure strict prompt-contract parsing, normalization, hashing, and rendering.

Implements X6's closed contract surface with no filesystem, compiler, or
registry dependency:

- strict UTF-8, duplicate-key-rejecting JSON for ``--returns`` and the
  inferred ``OutputContractDraft``;
- canonical type strings ``String``, ``Bool``, ``Int``, ``Float``,
  ``Optional[T]``, ``List[T]``, ``Map[String,T]`` with recursion limited to
  ``MAX_TYPE_DEPTH`` and no whitespace/alias spellings;
- the ``scaffold_output_contract.v1`` document with closed default/exact/
  inferred authoring provenance;
- deterministic ``PromptResult_<8hex>`` record names derived from a closed
  non-recursive basis (schema + renderer version + prompt digest + fields);
- canonical JSON bytes (UTF-8 ``ensure_ascii=False``, sorted keys, compact
  separators) with no permissive serializer fallback.

The scaffold renderer and identity (``prompt_scaffold.py``) build on these
pure primitives; nothing here reads process or filesystem state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, TypeAlias

SCHEMA_VERSION = "scaffold_output_contract.v1"
RENDERER_VERSION = "prompt_scaffold_renderer.v1"
MAX_TYPE_DEPTH = 16

_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PRIMITIVE_TYPE_NAMES = frozenset({"String", "Bool", "Int", "Float"})
_TYPE_CONSTRUCTOR_NAMES = frozenset({"Optional", "List", "Map"})
# Record names must not shadow prelude primitive/path types or the canonical
# type constructors; the ordinary compiler is not reached for such names.
RESERVED_RECORD_NAMES = frozenset(
    {
        "String",
        "Bool",
        "Int",
        "Float",
        "Json",
        "Provider",
        "Prompt",
        "PathRel",
        "RunId",
        "Symbol",
        "Optional",
        "List",
        "Map",
    }
)


class PromptContractError(ValueError):
    """A prompt contract document, type, name, or digest failed a closed rule."""


@dataclass(frozen=True, slots=True)
class PrimitiveType:
    """One canonical scalar type name (``String``, ``Bool``, ``Int``, ``Float``)."""

    name: str


@dataclass(frozen=True, slots=True)
class OptionalType:
    """``Optional[T]`` — a value or absent."""

    item: "TypeNode"


@dataclass(frozen=True, slots=True)
class ListType:
    """``List[T]`` — an ordered collection."""

    item: "TypeNode"


@dataclass(frozen=True, slots=True)
class MapType:
    """``Map[String,T]`` — a string-keyed mapping."""

    value: "TypeNode"


TypeNode: TypeAlias = PrimitiveType | OptionalType | ListType | MapType


@dataclass(frozen=True, slots=True)
class ContractField:
    """One ordered record field: an admitted identifier and canonical type."""

    name: str
    type: TypeNode


@dataclass(frozen=True, slots=True)
class SemanticContract:
    """The normalized semantic contract accepted by the scaffolder."""

    mode: Literal["scalar", "record"]
    type: TypeNode | None = None
    record_name: str | None = None
    fields: tuple[ContractField, ...] = ()


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of exact bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Return canonical JSON bytes: UTF-8, sorted keys, compact separators.

    Strictly rejects non-finite floats and any object without a JSON
    representation; there is deliberately no permissive ``default`` fallback.
    """
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PromptContractError(f"value is not canonical JSON: {exc}") from exc
    return text.encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise PromptContractError(f"duplicate JSON key {key!r}")
        mapping[key] = value
    return mapping


def parse_strict_json_object(payload: str | bytes) -> dict[str, object]:
    """Parse one strict UTF-8 JSON object; duplicate keys fail closed."""
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PromptContractError("document is not valid UTF-8") from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise PromptContractError("document must be a string or bytes")
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise PromptContractError(f"invalid JSON document: {exc}") from exc
    if not isinstance(document, dict):
        raise PromptContractError("document must be a JSON object")
    return document


def _require_identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PromptContractError(f"{context} must be a valid identifier")
    return value


# --- canonical type parsing and rendering ------------------------------------


def _parse_type(text: str, depth: int) -> TypeNode:
    if depth > MAX_TYPE_DEPTH:
        raise PromptContractError(
            f"type nesting exceeds {MAX_TYPE_DEPTH}"
        )
    if not isinstance(text, str) or not text:
        raise PromptContractError("type must be a non-empty canonical string")
    if any(ch.isspace() for ch in text):
        raise PromptContractError(f"non-canonical whitespace in type {text!r}")
    if text in _PRIMITIVE_TYPE_NAMES:
        return PrimitiveType(text)
    constructor, separator, rest = text.partition("[")
    if (
        constructor in ("Optional", "List", "Map")
        and separator
        and rest.endswith("]")
    ):
        inner = rest[:-1]
        if constructor == "Map":
            key, separator, value_text = inner.partition(",")
            if key != "String" or not separator:
                raise PromptContractError(
                    f"Map key must be the literal type String: {text!r}"
                )
            return MapType(_parse_type(value_text, depth + 1))
        return {
            "Optional": OptionalType,
            "List": ListType,
        }[constructor](_parse_type(inner, depth + 1))
    raise PromptContractError(f"unknown or malformed type {text!r}")


def parse_type_string(text: object) -> TypeNode:
    """Parse one canonical type string; unknown/wrong spellings fail."""
    if not isinstance(text, str):
        raise PromptContractError("type must be a string")
    return _parse_type(text, depth=0)


def render_type(node: TypeNode) -> str:
    """Render one canonical type node to its exact canonical spelling."""
    if isinstance(node, PrimitiveType):
        return node.name
    if isinstance(node, OptionalType):
        return f"Optional[{render_type(node.item)}]"
    if isinstance(node, ListType):
        return f"List[{render_type(node.item)}]"
    if isinstance(node, MapType):
        return f"Map[String,{render_type(node.value)}]"
    raise PromptContractError(f"unknown type node {node!r}")


def _validate_record_name(value: object) -> str:
    name = _require_identifier(value, "record_name")
    if name in RESERVED_RECORD_NAMES:
        raise PromptContractError(f"record_name is reserved: {name!r}")
    return name


# --- semantic contract parsing -----------------------------------------------


def _require_field_name(value: object, context: str) -> str:
    name = _require_identifier(value, context)
    if name in RESERVED_RECORD_NAMES:
        raise PromptContractError(
            f"{context} must not shadow a canonical type name: {name!r}"
        )
    return name


def _parse_field_rows(raw_fields: object) -> tuple[ContractField, ...]:
    if not isinstance(raw_fields, list) or not raw_fields:
        raise PromptContractError("fields must be a non-empty ordered list")
    rows: list[ContractField] = []
    seen: set[str] = set()
    for index, raw_row in enumerate(raw_fields):
        if not isinstance(raw_row, dict):
            raise PromptContractError(f"field row {index} must be an object")
        if set(raw_row) != {"name", "type"}:
            raise PromptContractError(
                f"field row {index} must have exactly name and type"
            )
        name = _require_field_name(raw_row["name"], f"field {index} name")
        if name in seen:
            raise PromptContractError(f"duplicate field name {name!r}")
        seen.add(name)
        rows.append(
            ContractField(name, parse_type_string(raw_row["type"]))
        )
    return tuple(rows)


def default_semantic_contract() -> SemanticContract:
    """The default semantic contract: scalar ``String`` (no contract flag)."""
    return SemanticContract(mode="scalar", type=PrimitiveType("String"))


def parse_semantic_contract(payload: str | bytes) -> SemanticContract:
    """Parse one strict ``--returns`` document into the normalized contract."""
    document = parse_strict_json_object(payload)
    if set(document) != {"mode", "type"} and set(document) != {
        "mode",
        "record_name",
        "fields",
    }:
        raise PromptContractError(
            "contract must be exactly {mode, type} or {mode, record_name, fields}"
        )
    mode = document["mode"]
    if mode == "scalar":
        if set(document) != {"mode", "type"}:
            raise PromptContractError("scalar contract must be exactly {mode, type}")
        return SemanticContract(
            mode="scalar", type=parse_type_string(document["type"])
        )
    if mode == "record":
        if set(document) != {"mode", "record_name", "fields"}:
            raise PromptContractError(
                "record contract must be exactly {mode, record_name, fields}"
            )
        record_name = _validate_record_name(document["record_name"])
        fields = _parse_field_rows(document["fields"])
        if not fields:
            raise PromptContractError("record contract requires at least one field")
        return SemanticContract(
            mode="record", record_name=record_name, fields=fields
        )
    raise PromptContractError(f"unknown contract mode {mode!r}")


def semantic_contract_object(contract: SemanticContract) -> dict[str, object]:
    """The closed JSON object for one normalized semantic contract."""
    if contract.mode == "scalar":
        return {"mode": "scalar", "type": render_type(contract.type)}
    return {
        "mode": "record",
        "record_name": contract.record_name,
        "fields": [
            {"name": field.name, "type": render_type(field.type)}
            for field in contract.fields
        ],
    }


def semantic_contract_sha256(contract: SemanticContract) -> str:
    """Digest of the semantic contract's canonical JSON object."""
    return sha256_hex(canonical_json_bytes(semantic_contract_object(contract)))


def contracts_structurally_equal(left: SemanticContract, right: SemanticContract) -> bool:
    """Structural equality: mode, scalar type, and ordered record fields.

    ``record_name`` is excluded: the compiled workflow mapping does not carry
    the authored record name, and the fixed renderer already embeds it in the
    source that compiled successfully.
    """
    if left.mode != right.mode:
        return False
    if left.mode == "scalar":
        return left.type == right.type
    if len(left.fields) != len(right.fields):
        return False
    return all(
        l.name == r.name and l.type == r.type
        for l, r in zip(left.fields, right.fields)
    )


def validate_type_node(node: object, depth: int = 0) -> None:
    """Reject a node that is not one canonical closed type node.

    Guards manually constructed ``SemanticContract`` objects (the dataclass
    is public) so identity, rendering, and publication never see an
    unnormalized type: unknown node kinds, unknown primitive names,
    non-string field carriers, and nesting beyond ``MAX_TYPE_DEPTH`` fail
    closed here, mirroring the parse-side depth rule.
    """
    if depth > MAX_TYPE_DEPTH:
        raise PromptContractError(f"type nesting exceeds {MAX_TYPE_DEPTH}")
    if isinstance(node, PrimitiveType):
        if not isinstance(node.name, str) or node.name not in _PRIMITIVE_TYPE_NAMES:
            raise PromptContractError(
                f"primitive type has an unknown name: {node!r}"
            )
        return
    if isinstance(node, (OptionalType, ListType)):
        validate_type_node(node.item, depth + 1)
        return
    if isinstance(node, MapType):
        validate_type_node(node.value, depth + 1)
        return
    raise PromptContractError(f"not a canonical type node: {node!r}")


def validate_contract(contract: object) -> None:
    """Reject a manually malformed ``SemanticContract`` before any use.

    Enforces the exact normalized dataclass state, not only the visible mode
    fields: a scalar contract requires one canonical type plus ``record_name
    is None`` and ``fields == ()``; a record contract requires ``type is
    None``, an admissible record name, and a non-empty ordered field list of
    unique admissible identifiers with canonical closed type nodes.
    """
    if not isinstance(contract, SemanticContract):
        raise PromptContractError("contract must be a SemanticContract")
    if contract.mode == "scalar":
        if contract.type is None:
            raise PromptContractError("scalar contract requires a type")
        if contract.record_name is not None:
            raise PromptContractError(
                "scalar contract must not carry a record_name"
            )
        if contract.fields != ():
            raise PromptContractError(
                "scalar contract must not carry record fields"
            )
        validate_type_node(contract.type)
        return
    if contract.mode == "record":
        if contract.type is not None:
            raise PromptContractError(
                "record contract must not carry a scalar type"
            )
        _validate_record_name(contract.record_name)
        if not isinstance(contract.fields, tuple) or not contract.fields:
            raise PromptContractError(
                "record contract requires a non-empty ordered field list"
            )
        seen: set[str] = set()
        for field in contract.fields:
            if not isinstance(field, ContractField):
                raise PromptContractError("record field is not a ContractField")
            _require_field_name(field.name, "record field name")
            if field.name in seen:
                raise PromptContractError(f"duplicate field name {field.name!r}")
            seen.add(field.name)
            validate_type_node(field.type)
        return
    raise PromptContractError(f"unknown contract mode {contract.mode!r}")


# --- inferred draft naming and provenance -------------------------------------


def _require_sha256(value: object, context: str) -> str:
    if not isinstance(value, str) or _HEX_SHA256_RE.fullmatch(value) is None:
        raise PromptContractError(
            f"{context} must be a 64-char lowercase hex SHA-256"
        )
    return value


def inferred_record_name(
    fields: tuple[ContractField, ...], *, prompt_sha256: str
) -> str:
    """Derive ``PromptResult_<8hex>`` from a closed, non-recursive basis.

    The basis holds schema, renderer version, prompt digest, and the ordered
    exact ``[{name, type}]`` rows; it never references the scaffold identity
    or any derived value, so the name cannot recurse into identity.
    """
    _require_sha256(prompt_sha256, "prompt_sha256")
    basis = canonical_json_bytes(
        {
            "schema": "prompt_result_name.v1",
            "renderer_version": RENDERER_VERSION,
            "prompt_sha256": prompt_sha256,
            "fields": [
                {"name": field.name, "type": render_type(field.type)}
                for field in fields
            ],
        }
    )
    return f"PromptResult_{sha256_hex(basis)[:8]}"


def parse_inferred_draft(
    payload: str | bytes | object, *, prompt_sha256: str
) -> SemanticContract:
    """Accept one inferred ``OutputContractDraft`` of ordered ``{name,type}`` rows.

    The draft is exactly ``{"fields": [...]}`` with a non-empty ordered list
    of rows; each row has exactly string ``name`` and ``type``, unique
    identifiers, and canonical types. The record name is derived
    deterministically from the accepted fields.
    """
    _require_sha256(prompt_sha256, "prompt_sha256")
    if isinstance(payload, (str, bytes)):
        document = parse_strict_json_object(payload)
    elif isinstance(payload, dict):
        document = payload
    else:
        raise PromptContractError("draft must be a JSON object or its text")
    if set(document) != {"fields"}:
        raise PromptContractError("draft must be exactly {fields}")
    fields = _parse_field_rows(document["fields"])
    return SemanticContract(
        mode="record",
        record_name=inferred_record_name(fields, prompt_sha256=prompt_sha256),
        fields=fields,
    )


# --- authoring provenance and the closed output-contract document -------------

# The authoring-provenance section lives in the narrowly named sibling
# ``prompt_contract_authoring`` (500-line production-module cap); the public
# facade below keeps the documented import surface at ``orchestrator.
# prompt_contract``. The facade is lazy (PEP 562) so a fresh interpreter that
# imports the sibling first cannot deadlock the module cycle.
_AUTHORING_FACADE = ("output_contract_document", "validate_authoring")


def __getattr__(name: str):
    if name in _AUTHORING_FACADE:
        from orchestrator import prompt_contract_authoring

        value = getattr(prompt_contract_authoring, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

