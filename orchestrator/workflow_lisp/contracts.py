"""Derive shared workflow contracts from Workflow Lisp structured types.

See `../../docs/design/workflow_lisp_type_catalog.md` for the type-to-contract model
and `../../docs/design/workflow_lisp_stdlib_lowering.md` for how generated contracts
are attached to provider and command steps.
"""

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
    """Workflow output contract generated from a frontend record or union type.

    The runtime validates provider and command outputs by reading a JSON file
    and checking it against a declared contract. Records use `output_bundle`
    because every field is present. Unions use `variant_output` because the
    discriminant chooses which fields are allowed or required. `type_ref` keeps
    that generated runtime contract tied to the original frontend type.
    """

    contract_kind: str
    path: str
    payload: Mapping[str, Any]
    type_ref: RecordTypeRef | UnionTypeRef


@dataclass(frozen=True)
class FlattenedContractField:
    """One leaf contract produced by flattening a structured frontend type."""

    generated_name: str
    source_path: tuple[str, ...]
    contract_definition: Mapping[str, Any]


@dataclass(frozen=True)
class WorkflowBoundaryParamSummary:
    """Small build-manifest summary of an authored workflow parameter."""

    name: str
    type_kind: str


@dataclass(frozen=True)
class GeneratedInternalInput:
    """Hidden workflow input added for generated state paths.

    The `.orc` author does not pass these explicitly. Lowering adds them when a
    generated step needs a stable path, such as the JSON bundle path for a
    provider or command result.
    """

    generated_name: str
    reason: str


@dataclass(frozen=True)
class UnionWorkflowBoundaryProjection:
    """Flattened workflow-boundary view of a tagged union return value.

    The discriminant is always exported; variant-specific fields are represented
    separately so callers and source maps can distinguish global availability
    from fields that require variant proof.
    """

    discriminant_field: FlattenedContractField
    shared_fields: tuple[FlattenedContractField, ...]
    variant_fields: Mapping[str, tuple[FlattenedContractField, ...]]


@dataclass(frozen=True)
class WorkflowBoundaryProjection:
    """Bridge from typed frontend signature to workflow input/output contracts.

    The runtime boundary currently exposes flat input and output names. A
    frontend workflow can use nested records or unions. This projection records
    how each frontend field was flattened so call lowering, source maps, and
    diagnostics can translate between the two shapes.
    """

    workflow_name: str
    display_name: str
    params: tuple[WorkflowBoundaryParamSummary, ...]
    return_kind: str
    flattened_inputs: tuple[FlattenedContractField, ...]
    flattened_outputs: tuple[FlattenedContractField, ...]
    generated_internal_inputs: tuple[GeneratedInternalInput, ...] = ()


def derive_structured_result_contract(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    workflow_name: str,
    step_id: str,
    span: SourceSpan | None = None,
    form_path: tuple[str, ...] = (),
) -> GeneratedBundleContract:
    """Derive the runtime-validated result contract for a provider/command form.

    Provider and command forms produce semantic state by writing a JSON file,
    not by emitting prose. This helper chooses the generated bundle path and the
    runtime contract that will validate that JSON before later steps can refer
    to its fields.
    """

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
        "shared_fields": _shared_variant_structured_result_fields(
            type_ref,
            span=span,
            form_path=form_path,
        ),
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
) -> tuple[Mapping[str, SurfaceContract], Mapping[str, SurfaceContract], WorkflowBoundaryProjection]:
    """Flatten workflow-boundary contracts into loader-accepted field specs."""

    inputs: dict[str, SurfaceContract] = {}
    outputs: dict[str, SurfaceContract] = {}
    flattened_inputs: list[FlattenedContractField] = []
    flattened_outputs: list[FlattenedContractField] = []

    for param_name, type_ref in signature.params:
        for flattened_field in derive_workflow_boundary_fields(
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
            flattened_inputs.append(flattened_field)

    for flattened_field in derive_workflow_boundary_fields(
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
        flattened_outputs.append(flattened_field)

    return (
        inputs,
        outputs,
        WorkflowBoundaryProjection(
            workflow_name=signature.name,
            display_name=signature.name.split("::", 1)[-1],
            params=tuple(
                WorkflowBoundaryParamSummary(
                    name=param_name,
                    type_kind=_workflow_boundary_type_kind(type_ref),
                )
                for param_name, type_ref in signature.params
            ),
            return_kind="record" if isinstance(signature.return_type_ref, RecordTypeRef) else "union",
            flattened_inputs=tuple(flattened_inputs),
            flattened_outputs=tuple(flattened_outputs),
        ),
    )


def derive_union_workflow_boundary_projection(
    type_ref: UnionTypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> UnionWorkflowBoundaryProjection:
    """Project a frontend union into flattened output-contract metadata.

    This keeps the discriminant, shared fields, and variant fields explicit so
    downstream validation can preserve variant availability instead of treating
    every field as globally present.
    """

    discriminant_field = FlattenedContractField(
        generated_name="return__variant",
        source_path=("return", "variant"),
        contract_definition={
            "kind": "scalar",
            "type": "enum",
            "allowed": [variant.name for variant in type_ref.definition.variants],
        },
    )
    shared_fields = tuple(
        FlattenedContractField(
            generated_name=f"return__{field['name']}",
            source_path=("return", field["name"]),
            contract_definition=_workflow_boundary_contract_from_structured_field(field),
        )
        for field in _shared_variant_structured_result_fields(
            type_ref,
            span=span,
            form_path=form_path,
        )
    )
    variant_fields: dict[str, tuple[FlattenedContractField, ...]] = {}
    for variant in type_ref.definition.variants:
        variant_fields[variant.name] = tuple(
            FlattenedContractField(
                generated_name=f"return__{field['name']}",
                source_path=("return", field["name"]),
                contract_definition=_workflow_boundary_contract_from_structured_field(field),
            )
            for field in _flatten_variant_structured_result_fields(
                type_ref,
                variant.name,
                span=span,
                form_path=form_path,
            )
        )
    return UnionWorkflowBoundaryProjection(
        discriminant_field=discriminant_field,
        shared_fields=shared_fields,
        variant_fields=variant_fields,
    )


def derive_workflow_boundary_fields(
    type_ref: TypeRef,
    *,
    generated_name: str,
    source_path: tuple[str, ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[FlattenedContractField, ...]:
    """Flatten one frontend boundary type into concrete shared contract fields.

    Current workflow signatures expose only scalar/path leaves to the shared
    runtime. Nested frontend records are recursively flattened while preserving
    their original source path for source-map diagnostics.
    """

    if isinstance(type_ref, UnionTypeRef):
        return _union_projection_fields(
            derive_union_workflow_boundary_projection(
                type_ref,
                span=span,
                form_path=form_path,
            ),
            span=span,
            form_path=form_path,
        )
    return _flatten_workflow_boundary_fields(
        type_ref,
        generated_name=generated_name,
        source_path=source_path,
        span=span,
        form_path=form_path,
    )


def _union_projection_fields(
    projection: UnionWorkflowBoundaryProjection,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[FlattenedContractField, ...]:
    fields: list[FlattenedContractField] = [
        projection.discriminant_field,
        *projection.shared_fields,
    ]
    for variant_fields in projection.variant_fields.values():
        fields.extend(variant_fields)
    return _dedupe_projection_fields(fields, span=span, form_path=form_path)


def _dedupe_projection_fields(
    fields: list[FlattenedContractField],
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[FlattenedContractField, ...]:
    deduped: dict[str, FlattenedContractField] = {}
    for field in fields:
        existing = deduped.get(field.generated_name)
        if existing is None:
            deduped[field.generated_name] = field
            continue
        if (
            existing.source_path == field.source_path
            and dict(existing.contract_definition) == dict(field.contract_definition)
        ):
            continue
        _raise_contract_error(
            code="workflow_boundary_projection_collision",
            message=(
                f"workflow boundary projection collision for `{field.generated_name}` across "
                f"`{'.'.join(existing.source_path)}` and `{'.'.join(field.source_path)}`"
            ),
            span=span,
            form_path=form_path,
        )
    return tuple(deduped.values())


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
        return _dedupe_projection_fields(flattened, span=span, form_path=form_path)

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


def _workflow_boundary_type_kind(type_ref: TypeRef) -> str:
    if isinstance(type_ref, RecordTypeRef):
        return "record"
    if isinstance(type_ref, UnionTypeRef):
        return "union"
    if isinstance(type_ref, PathTypeRef):
        return "relpath"
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            return "enum"
        if type_ref.name == "String":
            return "string"
        if type_ref.name == "Int":
            return "integer"
        if type_ref.name == "Bool":
            return "bool"
        return type_ref.name.lower()
    raise TypeError(f"unsupported workflow-boundary type kind: {type(type_ref)!r}")


def _workflow_boundary_contract_from_structured_field(field_definition: Mapping[str, Any]) -> dict[str, Any]:
    definition = {
        key: value
        for key, value in field_definition.items()
        if key in {"type", "allowed", "under", "must_exist_target"}
    }
    definition["kind"] = "relpath" if definition.get("type") == "relpath" else "scalar"
    return definition


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
    shared_field_names = {
        field["name"]
        for field in _shared_variant_structured_result_fields(
            type_ref,
            span=span,
            form_path=form_path,
        )
    }
    flattened: list[dict[str, Any]] = []
    for field in next(variant for variant in type_ref.definition.variants if variant.name == variant_name).fields:
        field_type = _resolve_variant_field_type(type_ref, variant_name, field.name)
        for flattened_field in _flatten_structured_result_field(
            field_type,
            field_path=(field.name,),
            span=span,
            form_path=form_path,
        ):
            if flattened_field["name"] not in shared_field_names:
                flattened.append(flattened_field)
    return flattened


def _shared_variant_structured_result_fields(
    type_ref: UnionTypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not type_ref.definition.variants:
        return []

    variant_field_maps: list[dict[str, dict[str, Any]]] = []
    for variant in type_ref.definition.variants:
        flattened_fields: dict[str, dict[str, Any]] = {}
        for field in variant.fields:
            field_type = _resolve_variant_field_type(type_ref, variant.name, field.name)
            for flattened_field in _flatten_structured_result_field(
                field_type,
                field_path=(field.name,),
                span=span,
                form_path=form_path,
            ):
                flattened_fields[flattened_field["name"]] = flattened_field
        variant_field_maps.append(flattened_fields)

    common_names = set(variant_field_maps[0])
    for field_map in variant_field_maps[1:]:
        common_names &= set(field_map)
    if not common_names:
        return []

    shared: list[dict[str, Any]] = []
    first_variant = type_ref.definition.variants[0]
    for field in first_variant.fields:
        field_type = _resolve_variant_field_type(type_ref, first_variant.name, field.name)
        for flattened_field in _flatten_structured_result_field(
            field_type,
            field_path=(field.name,),
            span=span,
            form_path=form_path,
        ):
            field_name = flattened_field["name"]
            if field_name not in common_names:
                continue
            if all(field_map.get(field_name) == flattened_field for field_map in variant_field_maps[1:]):
                shared.append(flattened_field)
    return shared


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
