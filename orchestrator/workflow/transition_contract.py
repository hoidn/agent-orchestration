"""Runtime-owned transition declaration and audit helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .pure_expr import PureExprEvaluationError, canonical_json_for_pure_value, validate_pure_expr_payload


TRANSITION_SCHEMA_VERSION = 1
UPDATE_OPS = frozenset({"set_field", "clear_field", "append_item"})


class TransitionContractError(ValueError):
    """Raised when one transition declaration is structurally invalid."""

    def __init__(self, code: str, message: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = dict(metadata or {})


@dataclass(frozen=True)
class ResourceBacking:
    kind: str
    path_input: str | None = None


@dataclass(frozen=True)
class ResourceDeclaration:
    resource_kind: str
    state_type: Mapping[str, Any]
    backing: ResourceBacking
    version_token_type: str = "String"


@dataclass(frozen=True)
class TransitionUpdate:
    op: str
    target: str
    value: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class TransitionDeclaration:
    name: str
    request_type: Mapping[str, Any]
    result_type: Mapping[str, Any]
    preconditions: tuple[Mapping[str, Any], ...]
    updates: tuple[TransitionUpdate, ...]
    write_set: tuple[str, ...]
    idempotency_fields: tuple[str, ...]
    result_projection: Mapping[str, Any]
    audit_projection: Mapping[str, Any]
    conflict_policy: str
    backend: Mapping[str, Any]


@dataclass(frozen=True)
class ValidatedTransitionDeclaration:
    transition_schema_version: int
    resource: ResourceDeclaration
    transition: TransitionDeclaration


def validate_transition_declaration(payload: Mapping[str, Any]) -> ValidatedTransitionDeclaration:
    if not isinstance(payload, Mapping):
        _raise("transition_declaration_invalid", "transition declaration must be a mapping")
    if payload.get("transition_schema_version") != TRANSITION_SCHEMA_VERSION:
        _raise(
            "transition_declaration_invalid",
            "unsupported transition schema version",
            metadata={
                "observed": payload.get("transition_schema_version"),
                "expected": TRANSITION_SCHEMA_VERSION,
            },
        )

    resource_payload = _mapping(payload.get("resource"), "resource")
    resource_kind = _non_empty_string(resource_payload.get("resource_kind"), "resource.resource_kind")
    state_type = _validated_type_descriptor(resource_payload.get("state_type"), context="resource.state_type")
    backing_payload = _mapping(resource_payload.get("backing"), "resource.backing")
    backing_kind = _non_empty_string(backing_payload.get("kind"), "resource.backing.kind")
    if backing_kind not in {"state_layout", "bridge"}:
        _raise("transition_declaration_invalid", f"unsupported resource backing `{backing_kind}`")
    path_input = None
    if backing_kind == "bridge":
        path_input = _non_empty_string(backing_payload.get("path_input"), "resource.backing.path_input")
    resource = ResourceDeclaration(
        resource_kind=resource_kind,
        state_type=state_type,
        backing=ResourceBacking(kind="native" if backing_kind == "state_layout" else "bridge", path_input=path_input),
    )

    transition_payload = _mapping(payload.get("transition"), "transition")
    request_type = _validated_type_descriptor(transition_payload.get("request_type"), context="transition.request_type")
    result_type = _validated_type_descriptor(transition_payload.get("result_type"), context="transition.result_type")
    transition_name = _non_empty_string(transition_payload.get("name"), "transition.name")
    preconditions = tuple(_validated_precondition(item) for item in _sequence(transition_payload.get("preconditions"), "transition.preconditions"))
    write_set = tuple(_validated_write_set(transition_payload.get("write_set"), state_type))
    request_fields = set(_record_field_types(request_type))
    idempotency_fields = tuple(_validated_idempotency_fields(transition_payload.get("idempotency_fields"), request_fields))
    updates = tuple(
        _validated_update(
            item,
            state_type=state_type,
            request_type=request_type,
            write_set=write_set,
            context=f"transition.updates[{index}]",
        )
        for index, item in enumerate(_sequence(transition_payload.get("updates"), "transition.updates"))
    )
    result_projection = _validated_projection(
        transition_payload.get("result_projection"),
        expected_type=result_type,
        code="transition_result_projection_type_mismatch",
        context="transition.result_projection",
    )
    audit_projection = _validated_projection(
        transition_payload.get("audit_projection"),
        expected_type=None,
        code="transition_declaration_invalid",
        context="transition.audit_projection",
    )
    conflict_policy = _non_empty_string(transition_payload.get("conflict_policy"), "transition.conflict_policy")
    backend = _mapping(transition_payload.get("backend"), "transition.backend")
    _non_empty_string(backend.get("kind"), "transition.backend.kind")

    return ValidatedTransitionDeclaration(
        transition_schema_version=TRANSITION_SCHEMA_VERSION,
        resource=resource,
        transition=TransitionDeclaration(
            name=transition_name,
            request_type=request_type,
            result_type=result_type,
            preconditions=preconditions,
            updates=updates,
            write_set=write_set,
            idempotency_fields=idempotency_fields,
            result_projection=result_projection,
            audit_projection=audit_projection,
            conflict_policy=conflict_policy,
            backend=dict(backend),
        ),
    )


def derive_idempotency_key(
    declaration: ValidatedTransitionDeclaration,
    *,
    resource_id: str,
    request_values: Mapping[str, Any],
) -> str:
    coerced_request = coerce_transition_value(
        request_values,
        declaration.transition.request_type,
        context="request_values",
    )
    key_payload = {
        "transition_schema_version": declaration.transition_schema_version,
        "transition_name": declaration.transition.name,
        "resource_id": resource_id,
        "fields": {
            field_name: coerced_request.get(field_name)
            for field_name in declaration.transition.idempotency_fields
        },
    }
    return f"sha256:{sha256(canonical_transition_json(key_payload).encode('utf-8')).hexdigest()}"


def serialize_transition_audit_record(record: Mapping[str, Any]) -> str:
    if not isinstance(record, Mapping):
        _raise("transition_declaration_invalid", "audit record must be a mapping")
    return canonical_transition_json(record)


def canonical_transition_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_transition_digest(value: Any) -> str:
    return f"sha256:{sha256(canonical_transition_json(value).encode('utf-8')).hexdigest()}"


def coerce_transition_value(value: Any, descriptor: Mapping[str, Any], *, context: str) -> Any:
    kind = _descriptor_kind(descriptor, context=context)
    if kind == "primitive":
        name = descriptor["name"]
        if name == "Bool":
            if type(value) is not bool:
                _raise("transition_declaration_invalid", f"{context} must be Bool")
            return value
        if name == "Int":
            if type(value) is not int:
                _raise("transition_declaration_invalid", f"{context} must be Int")
            return value
        if name in {"String", "Symbol", "PathRel", "RunId"}:
            if not isinstance(value, str):
                _raise("transition_declaration_invalid", f"{context} must be {name}")
            return value
        if name == "Json":
            canonical_json_for_pure_value(value)
            return _jsonable(value)
        if not isinstance(value, str):
            _raise("transition_declaration_invalid", f"{context} must be {name}")
        return value
    if kind == "enum":
        if not isinstance(value, str) or value not in descriptor["allowed"]:
            _raise("transition_declaration_invalid", f"{context} must be one of `{descriptor['allowed']}`")
        return value
    if kind == "path":
        if not isinstance(value, str):
            _raise("transition_declaration_invalid", f"{context} must be a path string")
        return value
    if kind == "optional":
        if value is None:
            return None
        return coerce_transition_value(value, descriptor["item"], context=context)
    if kind == "list":
        if not isinstance(value, list):
            _raise("transition_declaration_invalid", f"{context} must be a list")
        return [coerce_transition_value(item, descriptor["item"], context=f"{context}[]") for item in value]
    if kind == "map":
        if not isinstance(value, Mapping):
            _raise("transition_declaration_invalid", f"{context} must be a mapping")
        return {
            str(coerce_transition_value(key, descriptor["key"], context=f"{context}.key")): coerce_transition_value(
                item, descriptor["value"], context=f"{context}[{key}]"
            )
            for key, item in value.items()
        }
    if kind == "record":
        if not isinstance(value, Mapping):
            _raise("transition_declaration_invalid", f"{context} must be a record mapping")
        field_types = _record_field_types(descriptor)
        extra = set(value) - set(field_types)
        if extra:
            _raise("transition_declaration_invalid", f"{context} includes unexpected fields: {sorted(extra)}")
        result: dict[str, Any] = {}
        for field_name, field_type in field_types.items():
            if field_name not in value:
                _raise("transition_declaration_invalid", f"{context} is missing field `{field_name}`")
            result[field_name] = coerce_transition_value(value[field_name], field_type, context=f"{context}.{field_name}")
        return result
    if kind == "union":
        if not isinstance(value, Mapping) or not isinstance(value.get("variant"), str):
            _raise("transition_declaration_invalid", f"{context} must be a tagged union mapping")
        variant_name = value["variant"]
        variant = _union_variant(descriptor, variant_name)
        variant_value = dict(value)
        for field in variant["fields"]:
            field_name = field["name"]
            if field_name not in variant_value:
                _raise("transition_declaration_invalid", f"{context} is missing variant field `{field_name}`")
            variant_value[field_name] = coerce_transition_value(
                variant_value[field_name],
                field["type"],
                context=f"{context}.{field_name}",
            )
        return variant_value
    if kind == "variant_case":
        return coerce_transition_value(value, {"kind": "record", "name": descriptor.get("variant"), "fields": descriptor["fields"]}, context=context)
    _raise("transition_declaration_invalid", f"{context} uses unsupported type kind `{kind}`")


def _validated_projection(
    payload: Any,
    *,
    expected_type: Mapping[str, Any] | None,
    code: str,
    context: str,
) -> Mapping[str, Any]:
    mapping = _mapping(payload, context)
    try:
        validate_pure_expr_payload(mapping)
    except PureExprEvaluationError as exc:
        _raise(code, str(exc), metadata={"pure_expr_code": exc.code})
    if expected_type is not None and canonical_transition_json(mapping["result_type"]) != canonical_transition_json(expected_type):
        _raise(code, f"{context} result type does not match the declared transition result type")
    return mapping


def _validated_precondition(payload: Any) -> Mapping[str, Any]:
    mapping = _mapping(payload, "transition.preconditions[]")
    try:
        validate_pure_expr_payload(mapping)
    except PureExprEvaluationError as exc:
        _raise("transition_declaration_invalid", str(exc), metadata={"pure_expr_code": exc.code})
    if canonical_transition_json(mapping["result_type"]) != canonical_transition_json({"kind": "primitive", "name": "Bool"}):
        _raise("transition_declaration_invalid", "transition preconditions must evaluate to Bool")
    return mapping


def _validated_update(
    payload: Any,
    *,
    state_type: Mapping[str, Any],
    request_type: Mapping[str, Any],
    write_set: tuple[str, ...],
    context: str,
) -> TransitionUpdate:
    mapping = _mapping(payload, context)
    op = _non_empty_string(mapping.get("op"), f"{context}.op")
    if op not in UPDATE_OPS:
        _raise("transition_declaration_invalid", f"{context}.op uses unsupported update op `{op}`")
    target = _non_empty_string(mapping.get("target"), f"{context}.target")
    field_types = _record_field_types(state_type)
    if target not in field_types:
        _raise("transition_update_target_unknown", f"{context}.target `{target}` is not declared on the resource state")
    if target not in write_set:
        _raise("transition_write_set_undeclared", f"{context}.target `{target}` is missing from the declared write_set")
    if op == "clear_field":
        target_type = field_types[target]
        if _descriptor_kind(target_type, context=f"{context}.target_type") != "optional":
            _raise("transition_declaration_invalid", f"{context}.clear_field requires an Optional target")
        return TransitionUpdate(op=op, target=target)
    value = _mapping(mapping.get("value"), f"{context}.value")
    try:
        validate_pure_expr_payload(value)
    except PureExprEvaluationError as exc:
        _raise("transition_declaration_invalid", str(exc), metadata={"pure_expr_code": exc.code})
    target_type = field_types[target]
    if op == "append_item":
        if _descriptor_kind(target_type, context=f"{context}.target_type") != "list":
            _raise("transition_declaration_invalid", f"{context}.append_item requires a List target")
        expected_type = target_type["item"]
    else:
        expected_type = target_type
    if canonical_transition_json(value["result_type"]) != canonical_transition_json(expected_type):
        code = "transition_result_projection_type_mismatch" if context.endswith("result_projection") else "transition_declaration_invalid"
        _raise(code, f"{context}.value result type does not match target `{target}`")
    _validated_binding_shape(value, state_type=state_type, request_type=request_type, context=context)
    return TransitionUpdate(op=op, target=target, value=value)


def _validated_binding_shape(
    payload: Mapping[str, Any],
    *,
    state_type: Mapping[str, Any],
    request_type: Mapping[str, Any],
    context: str,
) -> None:
    bindings = _mapping(payload.get("bindings"), f"{context}.bindings")
    expected = {"state": state_type, "request": request_type}
    for binding_name, binding_type in expected.items():
        if binding_name not in bindings:
            _raise("transition_declaration_invalid", f"{context}.bindings is missing `{binding_name}`")
        observed = _mapping(bindings[binding_name], f"{context}.bindings.{binding_name}")
        if canonical_transition_json(observed.get("type")) != canonical_transition_json(binding_type):
            _raise("transition_declaration_invalid", f"{context}.bindings.{binding_name} must match the declared type")


def _validated_idempotency_fields(payload: Any, request_fields: set[str]) -> list[str]:
    names = []
    for field_name in _sequence(payload, "transition.idempotency_fields"):
        token = _non_empty_string(field_name, "transition.idempotency_fields[]")
        if token not in request_fields:
            _raise("transition_declaration_invalid", f"idempotency field `{token}` is not declared on the request")
        names.append(token)
    return names


def _validated_write_set(payload: Any, state_type: Mapping[str, Any]) -> list[str]:
    state_fields = set(_record_field_types(state_type))
    values: list[str] = []
    for field_name in _sequence(payload, "transition.write_set"):
        token = _non_empty_string(field_name, "transition.write_set[]")
        if token not in state_fields:
            _raise("transition_update_target_unknown", f"write_set field `{token}` is not declared on the resource state")
        values.append(token)
    return values


def _record_field_types(descriptor: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if _descriptor_kind(descriptor, context="record") != "record":
        _raise("transition_declaration_invalid", "transition declarations require record request and state types")
    return {field["name"]: field["type"] for field in descriptor["fields"]}


def _validated_type_descriptor(descriptor: Any, *, context: str) -> Mapping[str, Any]:
    mapping = _mapping(descriptor, context)
    kind = _descriptor_kind(mapping, context=context)
    if kind == "primitive":
        _non_empty_string(mapping.get("name"), f"{context}.name")
        return mapping
    if kind == "enum":
        _non_empty_string(mapping.get("name"), f"{context}.name")
        allowed = _sequence(mapping.get("allowed"), f"{context}.allowed")
        if not allowed or any(not isinstance(item, str) or not item for item in allowed):
            _raise("transition_declaration_invalid", f"{context}.allowed must be a non-empty string list")
        return mapping
    if kind == "path":
        _non_empty_string(mapping.get("name"), f"{context}.name")
        return mapping
    if kind == "optional":
        _validated_type_descriptor(mapping.get("item"), context=f"{context}.item")
        return mapping
    if kind == "list":
        _validated_type_descriptor(mapping.get("item"), context=f"{context}.item")
        return mapping
    if kind == "map":
        _validated_type_descriptor(mapping.get("key"), context=f"{context}.key")
        _validated_type_descriptor(mapping.get("value"), context=f"{context}.value")
        return mapping
    if kind in {"record", "variant_case"}:
        fields = _sequence(mapping.get("fields"), f"{context}.fields")
        seen: set[str] = set()
        for index, field in enumerate(fields):
            item = _mapping(field, f"{context}.fields[{index}]")
            name = _non_empty_string(item.get("name"), f"{context}.fields[{index}].name")
            if name in seen:
                _raise("transition_declaration_invalid", f"{context}.fields declares duplicate field `{name}`")
            seen.add(name)
            _validated_type_descriptor(item.get("type"), context=f"{context}.fields[{index}].type")
        if kind == "variant_case":
            _non_empty_string(mapping.get("variant"), f"{context}.variant")
            _non_empty_string(mapping.get("union_name"), f"{context}.union_name")
        return mapping
    if kind == "union":
        variants = _sequence(mapping.get("variants"), f"{context}.variants")
        seen_variants: set[str] = set()
        for index, variant in enumerate(variants):
            item = _mapping(variant, f"{context}.variants[{index}]")
            name = _non_empty_string(item.get("name"), f"{context}.variants[{index}].name")
            if name in seen_variants:
                _raise("transition_declaration_invalid", f"{context}.variants declares duplicate variant `{name}`")
            seen_variants.add(name)
            _validated_type_descriptor(
                {"kind": "record", "name": f"{name}Payload", "fields": item.get("fields")},
                context=f"{context}.variants[{index}]",
            )
        return mapping
    _raise("transition_declaration_invalid", f"{context} uses unsupported type kind `{kind}`")


def _union_variant(descriptor: Mapping[str, Any], variant_name: str) -> Mapping[str, Any]:
    for variant in descriptor.get("variants", []):
        if variant.get("name") == variant_name:
            return variant
    _raise("transition_declaration_invalid", f"unknown union variant `{variant_name}`")


def _descriptor_kind(descriptor: Mapping[str, Any], *, context: str) -> str:
    kind = descriptor.get("kind")
    if not isinstance(kind, str) or not kind:
        _raise("transition_declaration_invalid", f"{context} requires a non-empty `kind`")
    return kind


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise("transition_declaration_invalid", f"{context} must be a mapping")
    return value


def _sequence(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        _raise("transition_declaration_invalid", f"{context} must be a list")
    return value


def _non_empty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        _raise("transition_declaration_invalid", f"{context} must be a non-empty string")
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _raise(code: str, message: str, *, metadata: Mapping[str, Any] | None = None) -> None:
    raise TransitionContractError(code, message, metadata=metadata)
