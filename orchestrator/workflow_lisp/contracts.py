"""Stage 3 contract derivation helpers for structured results and workflow boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.surface_ast import SurfaceContract

from .type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from .workflows import WorkflowSignature


@dataclass(frozen=True)
class GeneratedBundleContract:
    contract_kind: str
    path: str
    payload: Mapping[str, Any]
    type_ref: RecordTypeRef | UnionTypeRef


@dataclass(frozen=True)
class FlattenedContractField:
    generated_name: str
    source_path: tuple[str, ...]
    contract_definition: Mapping[str, Any]


def derive_structured_result_contract(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    workflow_name: str,
    step_id: str,
) -> GeneratedBundleContract:
    """Derive one deterministic structured step-result contract from a frontend type."""

    path = _bundle_path(workflow_name=workflow_name, step_id=step_id)
    if isinstance(type_ref, RecordTypeRef):
        payload = {
            "path": path,
            "fields": [
                {
                    "name": field.name,
                    "json_pointer": f"/{field.name}",
                    **_field_contract_definition(_resolve_record_field_type(type_ref, field.name)),
                }
                for field in type_ref.definition.fields
            ],
        }
        return GeneratedBundleContract(
            contract_kind="output_bundle",
            path=path,
            payload=payload,
            type_ref=type_ref,
        )

    payload = {
        "path": path,
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": [variant.name for variant in type_ref.definition.variants],
        },
        "shared_fields": [],
        "variants": {
            variant.name: {
                "fields": [
                    {
                        "name": field.name,
                        "json_pointer": f"/{field.name}",
                        **_field_contract_definition(_resolve_variant_field_type(type_ref, variant.name, field.name)),
                    }
                    for field in variant.fields
                ]
            }
            for variant in type_ref.definition.variants
        },
    }
    return GeneratedBundleContract(
        contract_kind="variant_output",
        path=path,
        payload=payload,
        type_ref=type_ref,
    )


def derive_workflow_signature_contracts(
    signature: WorkflowSignature,
) -> tuple[Mapping[str, SurfaceContract], Mapping[str, SurfaceContract], tuple[FlattenedContractField, ...]]:
    """Flatten workflow-boundary contracts into the current shared surface vocabulary."""

    inputs: dict[str, SurfaceContract] = {}
    outputs: dict[str, SurfaceContract] = {}
    flattened_fields: list[FlattenedContractField] = []

    for param_name, type_ref in signature.params:
        if isinstance(type_ref, RecordTypeRef):
            for field in type_ref.definition.fields:
                field_type = _resolve_record_field_type(type_ref, field.name)
                generated_name = f"{param_name}__{field.name}"
                definition = _workflow_boundary_contract_definition(field_type)
                inputs[generated_name] = SurfaceContract(
                    name=generated_name,
                    kind=definition["kind"],
                    value_type=definition["type"],
                    definition=definition,
                )
                flattened_fields.append(
                    FlattenedContractField(
                        generated_name=generated_name,
                        source_path=(param_name, field.name),
                        contract_definition=definition,
                    )
                )
            continue

        definition = _workflow_boundary_contract_definition(type_ref)
        inputs[param_name] = SurfaceContract(
            name=param_name,
            kind=definition["kind"],
            value_type=definition["type"],
            definition=definition,
        )
        flattened_fields.append(
            FlattenedContractField(
                generated_name=param_name,
                source_path=(param_name,),
                contract_definition=definition,
            )
        )

    if isinstance(signature.return_type_ref, RecordTypeRef):
        for field in signature.return_type_ref.definition.fields:
            field_type = _resolve_record_field_type(signature.return_type_ref, field.name)
            generated_name = f"return__{field.name}"
            definition = _workflow_boundary_contract_definition(field_type)
            outputs[generated_name] = SurfaceContract(
                name=generated_name,
                kind=definition["kind"],
                value_type=definition["type"],
                definition=definition,
            )
            flattened_fields.append(
                FlattenedContractField(
                    generated_name=generated_name,
                    source_path=("return", field.name),
                    contract_definition=definition,
                )
            )

    return inputs, outputs, tuple(flattened_fields)


def _workflow_boundary_contract_definition(type_ref: TypeRef) -> dict[str, Any]:
    definition = _field_contract_definition(type_ref)
    if definition["type"] == "relpath":
        return {
            "kind": "relpath",
            **definition,
        }
    return {
        "kind": "scalar",
        **definition,
    }


def _field_contract_definition(type_ref: TypeRef) -> dict[str, Any]:
    if isinstance(type_ref, PathTypeRef):
        return {
            "type": "relpath",
            "under": type_ref.definition.under,
            "must_exist_target": type_ref.definition.must_exist,
        }
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.name == "String" or type_ref.name in {"Provider", "Prompt", "Json"}:
            return {"type": "string"}
        if type_ref.name == "Int":
            return {"type": "integer"}
        if type_ref.name == "Bool":
            return {"type": "bool"}
        if type_ref.allowed_values:
            return {
                "type": "enum",
                "allowed": list(type_ref.allowed_values),
            }
        return {"type": "string"}
    raise TypeError(f"unsupported field contract type: {type(type_ref)!r}")


def _resolve_record_field_type(record_type: RecordTypeRef, field_name: str) -> TypeRef:
    try:
        return record_type.field_types[field_name]
    except KeyError as exc:
        raise TypeError(f"missing resolved record field type for `{record_type.name}.{field_name}`") from exc


def _resolve_variant_field_type(union_type: UnionTypeRef, variant_name: str, field_name: str) -> TypeRef:
    variant_fields = union_type.variant_field_types.get(variant_name, {})
    try:
        return variant_fields[field_name]
    except KeyError as exc:
        raise TypeError(
            f"missing resolved union field type for `{union_type.name}.{variant_name}.{field_name}`"
        ) from exc


def _bundle_path(*, workflow_name: str, step_id: str) -> str:
    return f".orchestrate/workflow_lisp/{workflow_name}/{step_id}/result.json"
