"""Specialized compiler contract for generated ``run-ref`` result carriers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re
from typing import Any

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    validate_run_ref_result_descriptor,
)
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor

from .contracts import is_transportable_result_type
from .normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
    validate_compiler_normalized_type_descriptor,
)
from .syntax import target_dsl_supports_nested_structural_transport
from .type_env import FrontendTypeEnvironment, RecordTypeRef
from .typecheck_run_ref import compiler_run_ref_fixed_types


_GENERATED_RESULT_NAME = re.compile(r"RunRefResult\$[0-9a-f]{16}\Z")
_RESULT_FIELD_NAMES = ("value", "workspace_delta", "accounting")


@dataclass(frozen=True, init=False)
class GeneratedRunRefResultContract:
    """Content-addressed normalized contract for one generated result carrier."""

    _descriptor_json: bytes = field(repr=False)
    digest: str
    type_ref: RecordTypeRef
    allow_nested_structures: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "GeneratedRunRefResultContract must be created by "
            "derive_run_ref_result_contract"
        )

    @property
    def descriptor(self) -> dict[str, Any]:
        """Return a defensive copy of the canonical descriptor."""

        return json.loads(self._descriptor_json)


def _make_generated_run_ref_result_contract(
    descriptor: dict[str, Any],
    *,
    type_ref: RecordTypeRef,
    allow_nested_structures: bool,
) -> GeneratedRunRefResultContract:
    contract = object.__new__(GeneratedRunRefResultContract)
    object.__setattr__(
        contract,
        "_descriptor_json",
        canonical_json_bytes(descriptor),
    )
    object.__setattr__(contract, "digest", canonical_sha256(descriptor))
    object.__setattr__(contract, "type_ref", type_ref)
    object.__setattr__(
        contract,
        "allow_nested_structures",
        allow_nested_structures,
    )
    return contract


def _require_generated_result_shape(result_type_ref: RecordTypeRef) -> None:
    if _GENERATED_RESULT_NAME.fullmatch(result_type_ref.name) is None:
        raise ValueError(
            "run-ref result contract requires a generated RunRefResult$ type"
        )
    if result_type_ref.definition.name != result_type_ref.name:
        raise ValueError("run-ref result type and definition names must match")
    field_names = tuple(
        field.name for field in result_type_ref.definition.fields
    )
    if field_names != _RESULT_FIELD_NAMES:
        raise ValueError(
            "run-ref result fields must be exactly value, workspace_delta, accounting"
        )
    if tuple(result_type_ref.field_types) != _RESULT_FIELD_NAMES:
        raise ValueError(
            "run-ref result field types must match the exact ordered definition"
        )


def derive_run_ref_result_contract(
    result_type_ref: RecordTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
) -> GeneratedRunRefResultContract:
    """Derive and validate one exact compiler-owned ``run-ref`` result contract."""

    if not isinstance(result_type_ref, RecordTypeRef):
        raise ValueError("run-ref result contract requires a record type")
    _require_generated_result_shape(result_type_ref)

    value_type = result_type_ref.field_types["value"]
    workspace_delta_type = result_type_ref.field_types["workspace_delta"]
    accounting_type = result_type_ref.field_types["accounting"]
    allow_nested_structures = target_dsl_supports_nested_structural_transport(
        type_env.target_dsl_version
    )
    if not is_transportable_result_type(value_type, type_env=type_env):
        raise ValueError("run-ref result value type must be transportable")
    if not isinstance(workspace_delta_type, RecordTypeRef) or (
        workspace_delta_type.name != "WorkspaceDelta"
    ):
        raise ValueError(
            "run-ref result workspace_delta must use WorkspaceDelta"
        )
    if not isinstance(accounting_type, RecordTypeRef) or (
        accounting_type.name != "RunRefAccounting"
    ):
        raise ValueError(
            "run-ref result accounting must use RunRefAccounting"
        )

    envelope = compiler_normalized_type_descriptor(
        result_type_ref,
        type_env=type_env,
    )
    validate_compiler_normalized_type_descriptor(
        envelope,
        context="run_ref_result_contract.envelope",
    )

    expected_fixed = dict(compiler_run_ref_fixed_types(type_env))
    expected_workspace_delta = compiler_normalized_type_descriptor(
        expected_fixed["WorkspaceDelta"],
        type_env=type_env,
    )
    expected_accounting = compiler_normalized_type_descriptor(
        expected_fixed["RunRefAccounting"],
        type_env=type_env,
    )
    if envelope["fields"][1]["type"] != expected_workspace_delta:
        raise ValueError(
            "run-ref result workspace_delta does not match the fixed compiler schema"
        )
    if envelope["fields"][2]["type"] != expected_accounting:
        raise ValueError(
            "run-ref result accounting does not match the fixed compiler schema"
        )

    descriptor = {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": envelope,
    }
    validate_run_ref_result_descriptor(
        descriptor,
        expected_generated_name=result_type_ref.name,
        expected_digest=canonical_sha256(descriptor),
        allow_nested_structures=allow_nested_structures,
    )
    return _make_generated_run_ref_result_contract(
        descriptor,
        type_ref=result_type_ref,
        allow_nested_structures=allow_nested_structures,
    )


def derive_run_ref_output_bundle_fields(
    contract: GeneratedRunRefResultContract,
) -> list[dict[str, Any]]:
    """Project the exact run-ref envelope into runtime bundle artifact fields.

    The generated result descriptor remains the authority for recursive value
    validation. This projection only exposes the same record leaves that
    lowering publishes through ``_record_output_refs``; collection elements
    that contain records or unions use the transportable ``value`` schema
    inside the collection rather than stretching the generic result encoder.
    """

    if not isinstance(contract, GeneratedRunRefResultContract):
        raise TypeError("run-ref output bundle fields require a generated contract")
    descriptor = contract.descriptor
    validate_run_ref_result_descriptor(
        descriptor,
        expected_generated_name=contract.type_ref.name,
        expected_digest=contract.digest,
        allow_nested_structures=contract.allow_nested_structures,
    )
    fields: list[dict[str, Any]] = []
    field_paths_by_name: dict[str, tuple[str, ...]] = {}

    def visit(node: Mapping[str, Any], *, path: tuple[str, ...]) -> None:
        if node.get("kind") == "record":
            raw_fields = node.get("fields")
            if not isinstance(raw_fields, list):
                raise ValueError("run-ref record descriptor fields are malformed")
            for field in raw_fields:
                if not isinstance(field, Mapping):
                    raise ValueError("run-ref record descriptor field is malformed")
                name = field.get("name")
                field_type = field.get("type")
                if not isinstance(name, str) or not isinstance(field_type, Mapping):
                    raise ValueError("run-ref record descriptor field is malformed")
                visit(field_type, path=(*path, name))
            return
        flattened_name = "__".join(path)
        prior_path = field_paths_by_name.get(flattened_name)
        if prior_path is not None:
            raise ValueError(
                "run-ref output bundle artifact-name collision: "
                f"{prior_path!r} and {path!r} both project to "
                f"{flattened_name!r}"
            )
        field_paths_by_name[flattened_name] = path
        fields.append(
            {
                "name": flattened_name,
                "json_pointer": "/" + "/".join(
                    part.replace("~", "~0").replace("/", "~1")
                    for part in path
                ),
                **(
                    transport_schema_for_descriptor(
                        node,
                        allow_nested_structures=True,
                    )
                    if contract.allow_nested_structures
                    else _run_ref_output_schema(node)
                ),
            }
        )

    envelope = descriptor.get("envelope")
    if not isinstance(envelope, Mapping) or envelope.get("kind") != "record":
        raise ValueError("run-ref result envelope descriptor is malformed")
    visit(envelope, path=())
    if not fields or any(not field["name"] for field in fields):
        raise ValueError("run-ref output bundle projection is empty")
    return fields


def _run_ref_output_schema(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    kind = descriptor.get("kind")
    if kind == "primitive":
        primitive = descriptor.get("name")
        return {
            "type": {
                "String": "string",
                "Int": "integer",
                "Float": "float",
                "Bool": "bool",
                "Value": "value",
            }.get(primitive, "string")
        }
    if kind == "enum":
        allowed = descriptor.get("allowed")
        if not isinstance(allowed, list):
            raise ValueError("run-ref enum descriptor is malformed")
        return {"type": "enum", "allowed": list(allowed)}
    if kind == "path":
        under = descriptor.get("under")
        must_exist = descriptor.get("must_exist_target")
        if not isinstance(under, str) or not isinstance(must_exist, bool):
            raise ValueError("run-ref path descriptor is malformed")
        return {
            "type": "relpath",
            "under": under,
            "must_exist_target": must_exist,
        }
    if kind == "optional":
        item = descriptor.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("run-ref optional descriptor is malformed")
        return {"type": "optional", "item": _run_ref_nested_output_schema(item)}
    if kind == "list":
        item = descriptor.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("run-ref list descriptor is malformed")
        return {"type": "list", "items": _run_ref_nested_output_schema(item)}
    if kind == "map":
        key = descriptor.get("key")
        value = descriptor.get("value")
        if not isinstance(key, Mapping) or not isinstance(value, Mapping):
            raise ValueError("run-ref map descriptor is malformed")
        return {
            "type": "map",
            "keys": _run_ref_nested_output_schema(key),
            "values": _run_ref_nested_output_schema(value),
        }
    if kind in {"record", "union", "variant_case"}:
        return {"type": "value"}
    raise ValueError("run-ref output descriptor kind is unsupported")


def _run_ref_nested_output_schema(
    descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    if descriptor.get("kind") in {"record", "union", "variant_case"}:
        return {"type": "value"}
    return _run_ref_output_schema(descriptor)
