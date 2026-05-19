"""Stage 3 contract derivation helpers for structured results and workflow boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.surface_ast import SurfaceContract

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
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
    span: SourceSpan | None = None,
    form_path: tuple[str, ...] = (),
) -> GeneratedBundleContract:
    """Derive one deterministic structured step-result contract from a frontend type."""

    path = _bundle_path(workflow_name=workflow_name, step_id=step_id)
    if isinstance(type_ref, RecordTypeRef):
        payload = {
            "path": path,
            "fields": _flatten_structured_result_fields(
                type_ref,
                span=span,
                form_path=form_path,
            ),
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
                "fields": _flatten_variant_structured_result_fields(
                    type_ref,
                    variant.name,
                    span=span,
                    form_path=form_path,
                ),
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
        for flattened_field in _flatten_workflow_boundary_fields(
            type_ref,
            generated_name=param_name,
            source_path=(param_name,),
            span=signature.span,
            form_path=signature.form_path,
        ):
            inputs[flattened_field.generated_name] = SurfaceContract(
                name=flattened_field.generated_name,
                kind=flattened_field.contract_definition["kind"],
                value_type=flattened_field.contract_definition["type"],
                definition=flattened_field.contract_definition,
            )
            flattened_fields.append(flattened_field)

    if isinstance(signature.return_type_ref, RecordTypeRef):
        for flattened_field in _flatten_workflow_boundary_fields(
            signature.return_type_ref,
            generated_name="return",
            source_path=("return",),
            span=signature.span,
            form_path=signature.form_path,
        ):
            outputs[flattened_field.generated_name] = SurfaceContract(
                name=flattened_field.generated_name,
                kind=flattened_field.contract_definition["kind"],
                value_type=flattened_field.contract_definition["type"],
                definition=flattened_field.contract_definition,
            )
            flattened_fields.append(flattened_field)

    return inputs, outputs, tuple(flattened_fields)


def _flatten_workflow_boundary_fields(
    type_ref: TypeRef,
    *,
    generated_name: str,
    source_path: tuple[str, ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[FlattenedContractField, ...]:
    if isinstance(type_ref, RecordTypeRef):
        flattened: list[FlattenedContractField] = []
        for field in type_ref.definition.fields:
            field_type = _resolve_record_field_type(type_ref, field.name)
            flattened.extend(
                _flatten_workflow_boundary_fields(
                    field_type,
                    generated_name=f"{generated_name}__{field.name}",
                    source_path=source_path + (field.name,),
                    span=span,
                    form_path=form_path,
                )
            )
        return tuple(flattened)

    definition = _workflow_boundary_contract_definition(
        type_ref,
        span=span,
        form_path=form_path,
    )
    return (
        FlattenedContractField(
            generated_name=generated_name,
            source_path=source_path,
            contract_definition=definition,
        ),
    )


def _workflow_boundary_contract_definition(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    definition = _field_contract_definition(type_ref, span=span, form_path=form_path)
    if definition["type"] == "relpath":
        return {
            "kind": "relpath",
            **definition,
        }
    return {
        "kind": "scalar",
        **definition,
    }


def _field_contract_definition(
    type_ref: TypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    if isinstance(type_ref, PathTypeRef):
        return {
            "type": "relpath",
            "under": type_ref.definition.under,
            "must_exist_target": type_ref.definition.must_exist,
        }
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.name == "String":
            return {"type": "string"}
        if type_ref.name == "Int":
            return {"type": "integer"}
        if type_ref.name == "Bool":
            return {"type": "bool"}
        if type_ref.name == "Json":
            _raise_contract_error(
                code="json_surface_unsupported",
                message="`Json` cannot lower into workflow boundary or structured-result contracts",
                span=span,
                form_path=form_path,
            )
        if type_ref.name in {"Provider", "Prompt"}:
            _raise_contract_error(
                code="workflow_boundary_type_invalid",
                message=f"`{type_ref.name}` cannot lower into workflow boundary or structured-result contracts",
                span=span,
                form_path=form_path,
            )
        if type_ref.allowed_values:
            return {
                "type": "enum",
                "allowed": list(type_ref.allowed_values),
            }
        return {"type": "string"}
    raise TypeError(f"unsupported field contract type: {type(type_ref)!r}")


def _flatten_structured_result_fields(
    type_ref: RecordTypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for field in type_ref.definition.fields:
        field_type = _resolve_record_field_type(type_ref, field.name)
        flattened.extend(
            _flatten_structured_result_field(
                field_type,
                field_path=(field.name,),
                span=span,
                form_path=form_path,
            )
        )
    return flattened


def _flatten_variant_structured_result_fields(
    type_ref: UnionTypeRef,
    variant_name: str,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for field in next(variant for variant in type_ref.definition.variants if variant.name == variant_name).fields:
        field_type = _resolve_variant_field_type(type_ref, variant_name, field.name)
        flattened.extend(
            _flatten_structured_result_field(
                field_type,
                field_path=(field.name,),
                span=span,
                form_path=form_path,
            )
        )
    return flattened


def _flatten_structured_result_field(
    type_ref: TypeRef,
    *,
    field_path: tuple[str, ...],
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> list[dict[str, Any]]:
    if isinstance(type_ref, RecordTypeRef):
        flattened: list[dict[str, Any]] = []
        for field in type_ref.definition.fields:
            field_type = _resolve_record_field_type(type_ref, field.name)
            flattened.extend(
                _flatten_structured_result_field(
                    field_type,
                    field_path=field_path + (field.name,),
                    span=span,
                    form_path=form_path,
                )
            )
        return flattened

    return [
        {
            "name": "__".join(field_path),
            "json_pointer": "/" + "/".join(field_path),
            **_field_contract_definition(type_ref, span=span, form_path=form_path),
        }
    ]


def _raise_contract_error(
    *,
    code: str,
    message: str,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> None:
    if span is None:
        raise TypeError(message)
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )


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
