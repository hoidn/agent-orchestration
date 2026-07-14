"""Derive shared workflow contracts from Workflow Lisp structured types.

See `../../docs/design/workflow_lisp_type_catalog.md` for the type-to-contract model
and `../../docs/design/workflow_lisp_stdlib_lowering.md` for how generated contracts
are attached to provider and command steps.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator import __version__ as ORCHESTRATOR_VERSION
from orchestrator.exceptions import ValidationSubjectRef, serialize_validation_subject_ref
from orchestrator.workflow.surface_ast import SurfaceContract

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .phase_stdlib import ReusableArtifactRequirement
from .result_guidance import ResultGuidance, normalized_result_guidance_payload
from .spans import SourceSpan
from .type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
)
from .workflows import WorkflowParamDefault, WorkflowSignature

REUSABLE_PHASE_STATE_SCHEMA = "ReusablePhaseState.v1"
REUSABLE_PHASE_STATE_VERSION = "v1"
REUSABLE_PHASE_STATE_SIDECAR_SUFFIX = ".reusable_state.json"
REUSABLE_PHASE_STATE_CANONICAL_BUNDLE_DIGEST_FIELD = "canonical_bundle_sha256"
_NON_SEMANTIC_CONTRACT_PROVENANCE_KEYS = frozenset(
    {
        "source_map_subject",
        "source_map_subjects_by_variant",
        "guidance",
        "description",
        "format_hint",
        "example",
        "guidance_context",
        "guidance_by_variant",
    }
)


def is_review_findings_type(type_ref: TypeRef) -> bool:
    """Return whether a type resolves to the canonical stdlib ReviewFindings carrier."""

    if not isinstance(type_ref, RecordTypeRef):
        return False
    if type_ref.definition.name != "ReviewFindings":
        return False
    if not type_ref.definition.span.start.path.endswith("orchestrator/workflow_lisp/stdlib_modules/std/phase.orc"):
        return False
    schema_version_type = type_ref.field_types.get("schema_version")
    items_path_type = type_ref.field_types.get("items_path")
    return schema_version_type == PrimitiveTypeRef(name="String") and is_review_findings_json_path_type(
        items_path_type
    )


def is_review_findings_json_path_type(type_ref: TypeRef | None) -> bool:
    if not isinstance(type_ref, PathTypeRef):
        return False
    if type_ref.definition.name != "ReviewFindingsJsonPath":
        return False
    if not type_ref.definition.span.start.path.endswith("orchestrator/workflow_lisp/stdlib_modules/std/phase.orc"):
        return False
    return (
        type_ref.definition.kind == "relpath"
        and type_ref.definition.under == "artifacts/work"
        and type_ref.definition.must_exist is True
    )


def review_findings_types_compatible(expected: TypeRef, actual: TypeRef) -> bool:
    """Allow only the bounded ReviewFindings alias surface to bypass identity checks."""

    if is_review_findings_type(expected) and is_review_findings_type(actual):
        return True
    if is_review_findings_json_path_type(expected) and is_review_findings_json_path_type(actual):
        return True
    return False


@dataclass(frozen=True)
class GeneratedContractFieldOrigin:
    """Authored union-field origin for one generated runtime contract leaf."""

    subject_ref: ValidationSubjectRef
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedBundleContract:
    """Workflow output contract generated from a frontend result type.

    The runtime validates provider and command outputs by reading a JSON file
    and checking it against a declared contract. Records use `output_bundle`
    because every field is present. Unions use `variant_output` because the
    discriminant chooses which fields are allowed or required. Every other
    transportable type uses `output_bundle` with one root `__result__` field at
    JSON pointer `""` (see
    `../../docs/design/workflow_lisp_native_transportable_returns.md`).
    `type_ref` keeps that generated runtime contract tied to the original
    frontend type.
    """

    contract_kind: str
    path: str
    payload: Mapping[str, Any]
    type_ref: TypeRef
    field_origins: tuple[GeneratedContractFieldOrigin, ...] = ()

    @property
    def result_shape(self) -> str:
        """Structural result classification: `root_value`, `record_value`, or `union_value`."""

        if isinstance(self.type_ref, RecordTypeRef):
            return "record_value"
        if isinstance(self.type_ref, UnionTypeRef):
            return "union_value"
        return "root_value"


def is_transportable_result_type(type_ref: TypeRef) -> bool:
    """Return whether one declared result type can derive a runtime result contract.

    This is the single shared transportability decision for workflow, provider,
    command, and procedure return declarations (see
    `../../docs/design/workflow_lisp_native_transportable_returns.md`). Records
    and unions derive the existing structured-result contracts; any other type
    is transportable exactly when the existing structured-result field rules can
    express it as one direct JSON root value.
    """

    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return True
    try:
        _structured_result_field_definition(type_ref, span=None, form_path=())
    except (LispFrontendCompileError, TypeError):
        return False
    return True


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
    type_ref: TypeRef,
    *,
    workflow_name: str,
    step_id: str,
    span: SourceSpan | None = None,
    form_path: tuple[str, ...] = (),
    guidance: ResultGuidance | None = None,
    type_env: Any | None = None,
) -> GeneratedBundleContract:
    """Derive the runtime-validated result contract for a provider/command form.

    Provider and command forms produce semantic state by writing a JSON file,
    not by emitting prose. This helper chooses the generated bundle path and the
    runtime contract that will validate that JSON before later steps can refer
    to its fields. Non-record/non-union transportable types derive one root
    `output_bundle` field named `__result__` at JSON pointer `""`.
    """

    path = _bundle_path(workflow_name=workflow_name, step_id=step_id)
    root_guidance = normalized_result_guidance_payload(
        guidance,
        expected_type=type_ref,
        type_env=type_env,
    )
    if not isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        root_subject = ValidationSubjectRef(
            subject_kind="output_bundle_field",
            subject_name=f"{step_id}::root-result::__result__",
            workflow_name=workflow_name,
        )
        payload = {
            "path": path,
            "fields": [
                {
                    "name": "__result__",
                    "json_pointer": "",
                    **_structured_result_field_definition(
                        type_ref,
                        span=span,
                        form_path=form_path,
                    ),
                    **(root_guidance or {}),
                    "source_map_subject": serialize_validation_subject_ref(root_subject),
                }
            ],
        }
        field_origins: tuple[GeneratedContractFieldOrigin, ...] = ()
        if span is not None:
            # The authored return declaration (`:returns ...` in the effect
            # form) is the root subject's origin; derivations without a span
            # keep the enclosing-step fallback.
            field_origins = (
                GeneratedContractFieldOrigin(
                    subject_ref=root_subject,
                    span=span,
                    form_path=form_path,
                ),
            )
        return GeneratedBundleContract(
            contract_kind="output_bundle",
            path=path,
            payload=payload,
            type_ref=type_ref,
            field_origins=field_origins,
        )

    if isinstance(type_ref, RecordTypeRef):
        payload = {
            "path": path,
            **({"guidance": root_guidance} if root_guidance else {}),
            "fields": _flatten_structured_result_fields(
                type_ref,
                span=span,
                form_path=form_path,
                type_env=type_env,
                include_guidance=True,
            ),
        }
        return GeneratedBundleContract(
            contract_kind="output_bundle",
            path=path,
            payload=payload,
            type_ref=type_ref,
        )

    shared_fields = _shared_variant_structured_result_fields(
        type_ref,
        span=span,
        form_path=form_path,
        type_env=type_env,
        include_guidance=True,
    )
    variant_fields = {
        variant.name: _flatten_variant_structured_result_fields(
            type_ref,
            variant.name,
            span=span,
            form_path=form_path,
            type_env=type_env,
            include_guidance=True,
        )
        for variant in type_ref.definition.variants
    }
    subjects_by_variant, field_origins = _derive_union_contract_field_lineage(
        type_ref,
        workflow_name=workflow_name,
        step_id=step_id,
        span=span,
        form_path=form_path,
    )
    for variant_name, fields in variant_fields.items():
        for field in fields:
            field["source_map_subject"] = serialize_validation_subject_ref(
                subjects_by_variant[variant_name][field["name"]]
            )
    for field in shared_fields:
        field["source_map_subjects_by_variant"] = {
            variant.name: serialize_validation_subject_ref(
                subjects_by_variant[variant.name][field["name"]]
            )
            for variant in type_ref.definition.variants
        }

    payload = {
        "path": path,
        **({"guidance": root_guidance} if root_guidance else {}),
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": [variant.name for variant in type_ref.definition.variants],
        },
        "shared_fields": shared_fields,
        "variants": {
            variant.name: {
                "fields": variant_fields[variant.name],
            }
            for variant in type_ref.definition.variants
        },
    }
    return GeneratedBundleContract(
        contract_kind="variant_output",
        path=path,
        payload=payload,
        type_ref=type_ref,
        field_origins=field_origins,
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
            flattened_field = _apply_workflow_input_defaults(
                param_name=param_name,
                param_type=type_ref,
                flattened_field=flattened_field,
                authored_default=signature.param_defaults.get(param_name),
            )
            inputs[flattened_field.generated_name] = SurfaceContract(
                name=flattened_field.generated_name,
                kind=flattened_field.contract_definition["kind"],
                value_type=flattened_field.contract_definition["type"],
                definition=flattened_field.contract_definition,
            )
            flattened_inputs.append(flattened_field)

    return_projection: UnionWorkflowBoundaryProjection | None = None
    if isinstance(signature.return_type_ref, (RecordTypeRef, UnionTypeRef)):
        return_kind = "record" if isinstance(signature.return_type_ref, RecordTypeRef) else "union"
        return_fields = derive_workflow_boundary_fields(
            signature.return_type_ref,
            generated_name="return",
            source_path=("return",),
            span=signature.span,
            form_path=signature.form_path,
        )
        if isinstance(signature.return_type_ref, UnionTypeRef):
            return_projection = derive_union_workflow_boundary_projection(
                signature.return_type_ref,
                span=signature.span,
                form_path=signature.form_path,
            )
            return_fields = _relax_variant_only_relpath_outputs(
                signature.return_type_ref,
                return_fields,
                span=signature.span,
                form_path=signature.form_path,
            )
    else:
        return_kind = "root"
        return_fields = (
            root_workflow_boundary_field(
                signature.return_type_ref,
                span=signature.span,
                form_path=signature.form_path,
            ),
        )

    for flattened_field in return_fields:
        definition = dict(flattened_field.contract_definition)
        if return_projection is not None:
            definition = _annotate_union_workflow_output_definition(
                definition,
                flattened_field=flattened_field,
                projection=return_projection,
            )
        outputs[flattened_field.generated_name] = SurfaceContract(
            name=flattened_field.generated_name,
            kind=definition["kind"],
            value_type=definition["type"],
            definition=definition,
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
            return_kind=return_kind,
            flattened_inputs=tuple(flattened_inputs),
            flattened_outputs=tuple(flattened_outputs),
        ),
    )


def _annotate_union_workflow_output_definition(
    definition: dict[str, Any],
    *,
    flattened_field: FlattenedContractField,
    projection: UnionWorkflowBoundaryProjection,
) -> dict[str, Any]:
    """Attach active-variant availability to one flattened union output."""

    output_name = flattened_field.generated_name
    variant_names = tuple(projection.variant_fields)
    metadata: dict[str, Any] = {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": "return",
        "discriminant_output": projection.discriminant_field.generated_name,
    }
    if output_name == projection.discriminant_field.generated_name:
        metadata["field_role"] = "discriminant"
        metadata["active_variants"] = list(variant_names)
    elif any(field.generated_name == output_name for field in projection.shared_fields):
        metadata["field_role"] = "shared"
        metadata["active_variants"] = list(variant_names)
    else:
        active_variants = [
            variant_name
            for variant_name, fields in projection.variant_fields.items()
            if any(field.generated_name == output_name for field in fields)
        ]
        metadata["field_role"] = "variant" if active_variants else "unknown"
        metadata["active_variants"] = active_variants
    definition["projection"] = metadata
    return definition


def _relax_variant_only_relpath_outputs(
    type_ref: UnionTypeRef,
    fields: tuple[FlattenedContractField, ...],
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[FlattenedContractField, ...]:
    """Do not require inactive union-variant relpaths at the flat output boundary.

    The selected variant's producer contract still validates its active relpath
    fields. A flattened workflow output has no variant proof, so requiring every
    variant-only relpath to exist would make valid alternate variants fail at
    workflow-output export time.
    """

    projection = derive_union_workflow_boundary_projection(
        type_ref,
        span=span,
        form_path=form_path,
    )
    variant_only_names = {
        field.generated_name
        for variant_fields in projection.variant_fields.values()
        for field in variant_fields
    }
    relaxed: list[FlattenedContractField] = []
    for field in fields:
        if field.generated_name not in variant_only_names:
            relaxed.append(field)
            continue
        definition = dict(field.contract_definition)
        if definition.get("type") == "relpath" and definition.get("must_exist_target"):
            definition["must_exist_target"] = False
            field = FlattenedContractField(
                generated_name=field.generated_name,
                source_path=field.source_path,
                contract_definition=definition,
            )
        relaxed.append(field)
    return tuple(relaxed)


def _apply_workflow_input_defaults(
    *,
    param_name: str,
    param_type: TypeRef,
    flattened_field: FlattenedContractField,
    authored_default: WorkflowParamDefault | None,
) -> FlattenedContractField:
    """Attach bounded defaults for top-level phase-context inputs.

    The runtime already supports workflow-input defaults. Providing deterministic
    defaults for authored top-level `PhaseCtx` parameters keeps compile/dry-run
    example entry workflows usable without manual injection of synthetic phase
    roots and run metadata.
    """

    if authored_default is not None and authored_default.normalized_value is not None:
        definition = dict(flattened_field.contract_definition)
        definition["default"] = authored_default.normalized_value
        return FlattenedContractField(
            generated_name=flattened_field.generated_name,
            source_path=flattened_field.source_path,
            contract_definition=definition,
        )

    if not isinstance(param_type, RecordTypeRef) or param_type.name != "PhaseCtx":
        return flattened_field

    default_value = _phase_ctx_default_input_value(
        param_name=param_name,
        source_path=flattened_field.source_path,
    )
    if default_value is None:
        return flattened_field

    definition = dict(flattened_field.contract_definition)
    definition["default"] = default_value
    return FlattenedContractField(
        generated_name=flattened_field.generated_name,
        source_path=flattened_field.source_path,
        contract_definition=definition,
    )


def _phase_ctx_default_input_value(*, param_name: str, source_path: tuple[str, ...]) -> str | None:
    phase_name = _default_phase_name_for_param(param_name)
    if source_path == (param_name, "phase-name"):
        return phase_name
    if source_path == (param_name, "state-root"):
        return f"state/{phase_name}"
    if source_path == (param_name, "artifact-root"):
        return f"artifacts/{phase_name}"
    if source_path == (param_name, "run", "run-id"):
        return "test-run"
    if source_path == (param_name, "run", "state-root"):
        return "state/run"
    if source_path == (param_name, "run", "artifact-root"):
        return "artifacts/run"
    return None


def _default_phase_name_for_param(param_name: str) -> str:
    if param_name.endswith("-ctx"):
        return param_name[: -len("-ctx")]
    if param_name.endswith("_ctx"):
        return param_name[: -len("_ctx")]
    return param_name


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


def derive_reusable_state_contract_metadata(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    target_dsl_version: str,
    workflow_name: str,
    step_id: str,
    reusable_variants: tuple[str, ...] = (),
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> tuple[str, str, Mapping[str, tuple[ReusableArtifactRequirement, ...]], Mapping[str, Any]]:
    """Derive reusable-state schema metadata from structured-result contracts."""

    bundle_contract = derive_structured_result_contract(
        type_ref,
        workflow_name=workflow_name,
        step_id=step_id,
        span=span,
        form_path=form_path,
    )
    structured_contract = {
        key: value
        for key, value in bundle_contract.payload.items()
        if key != "path"
    }
    structured_contract_kind = "record" if isinstance(type_ref, RecordTypeRef) else "union"
    digest = structured_contract_semantic_digest(structured_contract)
    fingerprint = f"{target_dsl_version}:{type_ref.name}:{structured_contract_kind}:{digest}"
    artifact_requirements = _derive_reusable_artifact_requirements(
        type_ref,
        reusable_variants=reusable_variants,
        span=span,
        form_path=form_path,
    )
    return structured_contract_kind, fingerprint, artifact_requirements, structured_contract


def structured_contract_semantic_digest(structured_contract: Mapping[str, Any]) -> str:
    """Hash structured contract semantics while retaining runtime provenance."""

    return hashlib.sha256(
        json.dumps(
            _strip_contract_provenance_for_fingerprint(structured_contract),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _strip_contract_provenance_for_fingerprint(value: Any) -> Any:
    """Return the semantic contract value used for reusable-state identity."""

    if isinstance(value, Mapping):
        return {
            key: _strip_contract_provenance_for_fingerprint(item)
            for key, item in value.items()
            if key not in _NON_SEMANTIC_CONTRACT_PROVENANCE_KEYS
        }
    if isinstance(value, list):
        return [_strip_contract_provenance_for_fingerprint(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_contract_provenance_for_fingerprint(item) for item in value)
    return value


def derive_reusable_state_public_input_hash_basis(signature: WorkflowSignature) -> tuple[str, ...]:
    """Return the flattened public workflow input names that feed reuse hashing."""

    _, _, projection = derive_workflow_signature_contracts(signature)
    return tuple(
        field.generated_name
        for field in projection.flattened_inputs
        if not _exclude_reusable_state_hash_field(field.source_path)
    )


def _exclude_reusable_state_hash_field(source_path: tuple[str, ...]) -> bool:
    """Exclude run-local and compiler-managed root fields from reuse hashing."""

    if len(source_path) < 2:
        return False
    suffix = source_path[1:]
    return suffix in {
        ("state-root",),
        ("artifact-root",),
        ("run", "run-id"),
        ("run", "state-root"),
        ("run", "artifact-root"),
    }


def derive_reusable_state_producer_fingerprint_basis(
    *,
    signature: WorkflowSignature,
    return_type_name: str,
    structured_contract_kind: str,
    expected_contract_fingerprint: str,
    target_dsl_version: str,
    reusable_variants: tuple[str, ...],
    producer_context: Mapping[str, object] | None = None,
) -> Mapping[str, Any]:
    """Return the compiler-owned producer identity basis for reusable-state summaries."""

    basis = {
        "workflow_name": signature.name,
        "return_type_name": return_type_name,
        "structured_contract_kind": structured_contract_kind,
        "expected_contract_fingerprint": expected_contract_fingerprint,
        "target_dsl_version": target_dsl_version,
        "compiler_version": ORCHESTRATOR_VERSION,
        "reusable_variants": list(reusable_variants),
        "public_input_hash_basis": list(derive_reusable_state_public_input_hash_basis(signature)),
    }
    if producer_context is not None:
        basis.update(producer_context)
    return basis


def derive_reusable_phase_state_compatibility(
    *,
    target_dsl_version: str,
    summary_version: str,
) -> Mapping[str, str]:
    """Return the required compatibility metadata for reusable-state sidecars."""

    return {
        "dsl_version": target_dsl_version,
        "state_schema_version": summary_version,
    }


def derive_workflow_boundary_fields(
    type_ref: TypeRef,
    *,
    generated_name: str,
    source_path: tuple[str, ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[FlattenedContractField, ...]:
    """Flatten one frontend boundary type into concrete shared contract fields.

    Current workflow signatures expose scalar/path leaves and bounded collection
    leaves to the shared runtime. Nested frontend records are recursively
    flattened while preserving their original source path for source-map
    diagnostics.
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


def root_workflow_boundary_field(
    type_ref: TypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> FlattenedContractField:
    """Derive the single generated `__result__` output for a root-valued return.

    Root workflow boundaries (`result_shape == "root_value"`) expose one
    compiler-owned output named `__result__` whose contract comes from the same
    structured-result schema rules as provider/command root results, so
    Optional/List/Map roots use the widened v2.15 collection output schema
    instead of the record-flattening Stage 3 rules
    (`docs/design/workflow_lisp_native_transportable_returns.md`).
    """

    definition = _workflow_boundary_contract_from_structured_field(
        _structured_result_field_definition(
            type_ref,
            span=span,
            form_path=form_path,
        )
    )
    return FlattenedContractField(
        generated_name="__result__",
        source_path=("return",),
        contract_definition=definition,
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


def _derive_reusable_artifact_requirements(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    reusable_variants: tuple[str, ...] = (),
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> Mapping[str, tuple[ReusableArtifactRequirement, ...]]:
    if isinstance(type_ref, RecordTypeRef):
        return {
            type_ref.name: _artifact_requirements_from_fields(
                _flatten_structured_result_fields(
                    type_ref,
                    span=span,
                    form_path=form_path,
                )
            )
        }

    requirements: dict[str, tuple[ReusableArtifactRequirement, ...]] = {}
    selected_variants = set(reusable_variants)
    shared_fields = _shared_variant_structured_result_fields(
        type_ref,
        span=span,
        form_path=form_path,
    )
    for variant in type_ref.definition.variants:
        if selected_variants and variant.name not in selected_variants:
            continue
        requirements[variant.name] = _artifact_requirements_from_fields(
            [
                *shared_fields,
                *_flatten_variant_structured_result_fields(
                    type_ref,
                    variant.name,
                    span=span,
                    form_path=form_path,
                ),
            ]
        )
    return requirements


def _artifact_requirements_from_fields(
    fields: list[dict[str, Any]],
) -> tuple[ReusableArtifactRequirement, ...]:
    requirements: list[ReusableArtifactRequirement] = []
    for field in fields:
        if field.get("type") != "relpath" or not field.get("must_exist_target"):
            continue
        json_pointer = str(field.get("json_pointer", ""))
        requirements.append(
            ReusableArtifactRequirement(
                field_path=tuple(part for part in json_pointer.split("/") if part),
                under=str(field.get("under", "")),
            )
        )
    return tuple(requirements)


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
    if definition["type"] in {"optional", "list", "map"}:
        return {
            "kind": "collection",
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
    if isinstance(type_ref, ListTypeRef):
        return "list"
    if isinstance(type_ref, PathTypeRef):
        return "relpath"
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            return "enum"
        if type_ref.name == "String":
            return "string"
        if type_ref.name == "Int":
            return "integer"
        if type_ref.name == "Float":
            return "float"
        if type_ref.name == "Bool":
            return "bool"
        return type_ref.name.lower()
    raise TypeError(f"unsupported workflow-boundary type kind: {type(type_ref)!r}")


def _workflow_boundary_contract_from_structured_field(field_definition: Mapping[str, Any]) -> dict[str, Any]:
    definition = {
        key: value
        for key, value in field_definition.items()
        if key in {"type", "allowed", "under", "must_exist_target", "item", "items", "keys", "values"}
    }
    if definition.get("type") == "relpath":
        definition["kind"] = "relpath"
    elif definition.get("type") in {"optional", "list", "map"}:
        definition["kind"] = "collection"
    else:
        definition["kind"] = "scalar"
    return definition


def _field_contract_definition(
    type_ref: TypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    if isinstance(type_ref, ListTypeRef):
        return {
            "type": "list",
            "items": _structured_result_field_definition(
                type_ref.item_type_ref,
                span=span,
                form_path=form_path,
            ),
        }
    if isinstance(type_ref, (OptionalTypeRef, MapTypeRef)):
        _raise_contract_error(
            code="workflow_boundary_collection_unsupported",
            message=f"`{type_ref.name}` cannot lower across a workflow boundary in Stage 3",
            span=span,
            form_path=form_path,
        )
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
        if type_ref.name == "Float":
            return {"type": "float"}
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
    type_env: Any | None = None,
    include_guidance: bool = False,
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
                field_guidance=field.guidance,
                type_env=type_env,
                include_guidance=include_guidance,
            )
        )
    return flattened


def _derive_union_contract_field_lineage(
    type_ref: UnionTypeRef,
    *,
    workflow_name: str,
    step_id: str,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> tuple[
    dict[str, dict[str, ValidationSubjectRef]],
    tuple[GeneratedContractFieldOrigin, ...],
]:
    subjects_by_variant: dict[str, dict[str, ValidationSubjectRef]] = {}
    origins: list[GeneratedContractFieldOrigin] = []
    seen_subjects: set[tuple[str, str, str | None]] = set()

    for variant in type_ref.definition.variants:
        variant_subjects: dict[str, ValidationSubjectRef] = {}
        for field in variant.fields:
            field_type = _resolve_variant_field_type(type_ref, variant.name, field.name)
            origin_form_path = (
                "workflow-lisp",
                "defunion",
                type_ref.definition.name,
                variant.name,
                field.name,
            )
            flattened_fields = _flatten_structured_result_field(
                field_type,
                field_path=(field.name,),
                span=span,
                form_path=form_path,
            )
            for flattened_field in flattened_fields:
                subject_ref = ValidationSubjectRef(
                    subject_kind="variant_output_field",
                    subject_name=(
                        f"{step_id}::{type_ref.name}::{variant.name}::"
                        f"{flattened_field['name']}"
                    ),
                    workflow_name=workflow_name,
                )
                variant_subjects[flattened_field["name"]] = subject_ref
                subject_key = (
                    subject_ref.subject_kind,
                    subject_ref.subject_name,
                    subject_ref.workflow_name,
                )
                if subject_key in seen_subjects:
                    continue
                seen_subjects.add(subject_key)
                origins.append(
                    GeneratedContractFieldOrigin(
                        subject_ref=subject_ref,
                        span=field.span,
                        form_path=origin_form_path,
                    )
                )
        subjects_by_variant[variant.name] = variant_subjects

    return subjects_by_variant, tuple(origins)


def _flatten_variant_structured_result_fields(
    type_ref: UnionTypeRef,
    variant_name: str,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
    type_env: Any | None = None,
    include_guidance: bool = False,
) -> list[dict[str, Any]]:
    shared_field_names = {
        field["name"]
        for field in _shared_variant_structured_result_fields(
            type_ref,
            span=span,
            form_path=form_path,
            type_env=type_env,
            include_guidance=include_guidance,
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
            field_guidance=field.guidance,
            type_env=type_env,
            include_guidance=include_guidance,
        ):
            if flattened_field["name"] not in shared_field_names:
                flattened.append(flattened_field)
    return flattened


def _shared_variant_structured_result_fields(
    type_ref: UnionTypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
    type_env: Any | None = None,
    include_guidance: bool = False,
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
                field_guidance=field.guidance,
                type_env=type_env,
                include_guidance=include_guidance,
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
            field_guidance=field.guidance,
            type_env=type_env,
            include_guidance=include_guidance,
        ):
            field_name = flattened_field["name"]
            if field_name not in common_names:
                continue
            structural_field = _without_guidance(flattened_field)
            if not all(
                _without_guidance(field_map[field_name]) == structural_field
                for field_map in variant_field_maps[1:]
            ):
                continue
            if not include_guidance:
                shared.append(structural_field)
                continue
            payloads = [
                _field_guidance_payload(field_map[field_name])
                for field_map in variant_field_maps
            ]
            nonempty_payloads = [payload for payload in payloads if payload]
            if nonempty_payloads and all(
                _canonical_guidance_payload(payload)
                == _canonical_guidance_payload(payloads[0])
                for payload in payloads
            ):
                shared.append({**structural_field, **payloads[0]})
                continue
            guidance_by_variant = {
                variant.name: payload
                for variant, payload in zip(type_ref.definition.variants, payloads, strict=True)
                if payload
            }
            shared.append(
                {
                    **structural_field,
                    **(
                        {"guidance_by_variant": guidance_by_variant}
                        if guidance_by_variant
                        else {}
                    ),
                }
            )
    return shared


def _flatten_structured_result_field(
    type_ref: TypeRef,
    *,
    field_path: tuple[str, ...],
    span: SourceSpan | None,
    form_path: tuple[str, ...],
    field_guidance: ResultGuidance | None = None,
    guidance_context: tuple[dict[str, Any], ...] = (),
    type_env: Any | None = None,
    include_guidance: bool = False,
) -> list[dict[str, Any]]:
    if isinstance(type_ref, RecordTypeRef):
        nested_context = guidance_context
        if include_guidance:
            ancestor_payload = normalized_result_guidance_payload(
                field_guidance,
                expected_type=type_ref,
                type_env=type_env,
            )
            if ancestor_payload:
                nested_context = (
                    *guidance_context,
                    {
                        "json_pointer": _json_pointer(field_path),
                        **ancestor_payload,
                    },
                )
        flattened: list[dict[str, Any]] = []
        for field in type_ref.definition.fields:
            field_type = _resolve_record_field_type(type_ref, field.name)
            flattened.extend(
                _flatten_structured_result_field(
                    field_type,
                    field_path=field_path + (field.name,),
                    span=span,
                    form_path=form_path,
                    field_guidance=field.guidance,
                    guidance_context=nested_context,
                    type_env=type_env,
                    include_guidance=include_guidance,
                )
            )
        return flattened

    direct_guidance = (
        normalized_result_guidance_payload(
            field_guidance,
            expected_type=type_ref,
            type_env=type_env,
        )
        if include_guidance
        else None
    )
    return [{
        "name": "__".join(field_path),
        "json_pointer": _json_pointer(field_path),
        **_structured_result_field_definition(type_ref, span=span, form_path=form_path),
        **({"guidance_context": list(guidance_context)} if guidance_context else {}),
        **(direct_guidance or {}),
    }]


_FIELD_GUIDANCE_KEYS = frozenset(
    {"description", "format_hint", "example", "guidance_context", "guidance_by_variant"}
)


def _field_guidance_payload(field: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: field[key]
        for key in ("description", "format_hint", "example", "guidance_context")
        if key in field
    }


def _without_guidance(field: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in field.items() if key not in _FIELD_GUIDANCE_KEYS}


def _canonical_guidance_payload(payload: Mapping[str, Any]) -> str:
    """Return a deterministic deep-JSON representation for union deduplication."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_pointer(field_path: tuple[str, ...]) -> str:
    return "/" + "/".join(
        component.replace("~", "~0").replace("/", "~1")
        for component in field_path
    )


def _structured_result_field_definition(
    type_ref: TypeRef,
    *,
    span: SourceSpan | None,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    if isinstance(type_ref, OptionalTypeRef):
        return {
            "type": "optional",
            "item": _structured_result_field_definition(
                type_ref.item_type_ref,
                span=span,
                form_path=form_path,
            ),
        }
    if isinstance(type_ref, ListTypeRef):
        return {
            "type": "list",
            "items": _structured_result_field_definition(
                type_ref.item_type_ref,
                span=span,
                form_path=form_path,
            ),
        }
    if isinstance(type_ref, MapTypeRef):
        return {
            "type": "map",
            "keys": {"type": "string"},
            "values": _structured_result_field_definition(
                type_ref.value_type_ref,
                span=span,
                form_path=form_path,
            ),
        }
    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        _raise_contract_error(
            code="collection_element_type_unsupported",
            message=f"`{type_ref.name}` cannot appear inside a collection-valued structured result",
            span=span,
            form_path=form_path,
        )
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.name in {"Json", "Provider", "Prompt"}:
        _raise_contract_error(
            code="collection_element_type_unsupported",
            message=f"`{type_ref.name}` cannot appear inside a collection-valued structured result",
            span=span,
            form_path=form_path,
        )
    return _field_contract_definition(type_ref, span=span, form_path=form_path)


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
