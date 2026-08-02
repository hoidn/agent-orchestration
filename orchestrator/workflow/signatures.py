"""Workflow-boundary input/output contract helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, NoReturn, Sequence

from orchestrator.contracts.output_contract import OutputContractError, validate_contract_value

from .executable_ir import ExecutableContract
from .references import ReferenceResolutionError, ReferenceResolver


WORKFLOW_SIGNATURE_VERSION = "2.1"
_UNION_WORKFLOW_BOUNDARY_KEYS = frozenset(
    {
        "projection_class",
        "return_kind",
        "union_output_group",
        "discriminant_output",
        "field_role",
        "active_variants",
    }
)


class WorkflowSignatureError(ValueError):
    """Raised when workflow-boundary input/output contracts fail."""

    def __init__(self, message: str, *, context: Dict[str, Any]):
        self.error = {
            "type": "contract_violation",
            "message": message,
            "context": context,
        }
        super().__init__(message)


def bind_workflow_inputs(
    input_specs: Mapping[str, Dict[str, Any]] | None,
    provided_inputs: Mapping[str, Any] | None,
    workspace: Path,
) -> Dict[str, Any]:
    """Bind and validate workflow inputs from CLI/runtime values."""
    specs = dict(input_specs or {})
    raw_inputs = dict(provided_inputs or {})
    bound_inputs: Dict[str, Any] = {}

    unexpected = sorted(name for name in raw_inputs if name not in specs)
    if unexpected:
        raise WorkflowSignatureError(
            "Workflow input binding failed",
            context={
                "scope": "workflow_inputs",
                "reason": "unknown_inputs",
                "inputs": unexpected,
            },
        )

    for name, spec in specs.items():
        if name in raw_inputs:
            candidate = raw_inputs[name]
        elif "default" in spec:
            candidate = spec["default"]
        elif spec.get("required", True):
            raise WorkflowSignatureError(
                "Workflow input binding failed",
                context={
                    "scope": "workflow_inputs",
                    "input": name,
                    "reason": "missing_required_input",
                },
            )
        else:
            continue

        try:
            bound_inputs[name] = validate_contract_value(candidate, spec, workspace=workspace)
        except OutputContractError as exc:
            raise WorkflowSignatureError(
                "Workflow input binding failed",
                context={
                    "scope": "workflow_inputs",
                    "input": name,
                    "reason": "invalid_value",
                    "violations": exc.violations,
                },
            ) from exc

    return bound_inputs


def resolve_workflow_outputs(
    output_specs: Mapping[str, Any] | None,
    state: Dict[str, Any],
    workspace: Path,
    *,
    resolve_source: Callable[[Any, Dict[str, Any]], Any] | None = None,
) -> Dict[str, Any]:
    """Resolve and validate declared workflow outputs from run state."""
    specs = dict(output_specs or {})
    if not specs:
        return {}

    resolver = ReferenceResolver()
    resolved_outputs: Dict[str, Any] = {}
    active_union_variants = _resolve_workflow_output_discriminants(
        specs,
        state,
        workspace,
        resolver=resolver,
        resolve_source=resolve_source,
    )
    for name, spec in specs.items():
        validation_spec: Any = spec.definition if isinstance(spec, ExecutableContract) else spec
        boundary = _workflow_boundary_metadata(validation_spec)
        if _is_inactive_union_variant_output(boundary, active_union_variants):
            continue
        binding = validation_spec.get("from") if isinstance(validation_spec, Mapping) else None
        ref = binding.get("ref") if isinstance(binding, Mapping) else None
        source = spec.source_address if isinstance(spec, ExecutableContract) else None
        if source is None and isinstance(ref, str) and ref:
            source = {"ref": ref}
        if source is None:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "missing_from_ref",
                },
            )

        try:
            if resolve_source is not None:
                raw_value = resolve_source(source, state)
            else:
                raw_value = resolver.resolve(ref, state).value
        except ReferenceResolutionError as exc:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "unresolved_source",
                    "ref": ref,
                    "error": str(exc),
                },
            ) from exc

        try:
            resolved_outputs[name] = validate_contract_value(
                raw_value,
                _workflow_output_validation_spec(validation_spec),
                workspace=workspace,
            )
        except OutputContractError as exc:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "invalid_export_value",
                    "ref": ref,
                    "violations": exc.violations,
                },
            ) from exc

    return resolved_outputs


def _workflow_output_validation_spec(validation_spec: Any) -> Any:
    if not isinstance(validation_spec, Mapping):
        return validation_spec
    projection = validation_spec.get("projection")
    if (
        not isinstance(projection, Mapping)
        or projection.get("projection_class") != "provider_bundle_path_projection"
    ):
        return validation_spec
    return {
        key: value
        for key, value in validation_spec.items()
        if key not in {"under", "must_exist_target"}
    }


def _workflow_boundary_metadata(validation_spec: Any) -> Mapping[str, Any]:
    if not isinstance(validation_spec, Mapping):
        return {}
    metadata = validation_spec.get("workflow_boundary")
    if isinstance(metadata, Mapping):
        return metadata
    metadata = validation_spec.get("projection")
    if (
        isinstance(metadata, Mapping)
        and metadata.get("projection_class") == "union_workflow_boundary"
    ):
        return metadata
    return metadata if isinstance(metadata, Mapping) else {}


def _resolve_workflow_output_discriminants(
    specs: Mapping[str, Any],
    state: Dict[str, Any],
    workspace: Path,
    *,
    resolver: ReferenceResolver,
    resolve_source: Callable[[Any, Dict[str, Any]], Any] | None,
) -> Dict[str, Any]:
    """Resolve flattened union discriminants before variant field exports."""

    active_variants: Dict[str, Any] = {}
    groups = _validated_union_workflow_output_groups(specs)
    for group, members in groups.items():
        name, spec, validation_spec, _ = next(
            member
            for member in members
            if member[3]["field_role"] == "discriminant"
        )
        binding = validation_spec.get("from") if isinstance(validation_spec, Mapping) else None
        ref = binding.get("ref") if isinstance(binding, Mapping) else None
        source = spec.source_address if isinstance(spec, ExecutableContract) else None
        if source is None and isinstance(ref, str) and ref:
            source = {"ref": ref}
        if source is None:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "invalid_union_projection",
                    "detail": "discriminant_source_missing",
                },
            )
        try:
            if resolve_source is not None:
                raw_value = resolve_source(source, state)
            elif isinstance(ref, str):
                raw_value = resolver.resolve(ref, state).value
            else:
                raise WorkflowSignatureError(
                    "Workflow output export failed",
                    context={
                        "scope": "workflow_outputs",
                        "output": name,
                        "reason": "invalid_union_projection",
                        "detail": "discriminant_source_missing",
                    },
                )
            active_variants[group] = validate_contract_value(
                raw_value,
                dict(validation_spec),
                workspace=workspace,
            )
        except ReferenceResolutionError as exc:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "unresolved_union_discriminant",
                    "ref": ref,
                    "error": str(exc),
                },
            ) from exc
        except OutputContractError as exc:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "invalid_union_discriminant",
                    "ref": ref,
                    "violations": exc.violations,
                },
            ) from exc
    return active_variants


def _validated_union_workflow_output_groups(
    specs: Mapping[str, Any],
) -> Dict[
    str,
    list[tuple[str, Any, Mapping[str, Any], Mapping[str, Any]]],
]:
    """Validate exact union group authority before any payload is skipped."""

    groups: Dict[
        str,
        list[tuple[str, Any, Mapping[str, Any], Mapping[str, Any]]],
    ] = {}

    def reject(name: str, detail: str) -> NoReturn:
        raise WorkflowSignatureError(
            "Workflow output export failed",
            context={
                "scope": "workflow_outputs",
                "output": name,
                "reason": "invalid_union_projection",
                "detail": detail,
            },
        )

    for name, spec in specs.items():
        validation_spec: Any = (
            spec.definition if isinstance(spec, ExecutableContract) else spec
        )
        if not isinstance(validation_spec, Mapping):
            continue
        boundary = _union_workflow_boundary_candidate(
            validation_spec,
            output_name=name,
            reject=reject,
        )
        if boundary is None:
            continue
        if set(boundary) != _UNION_WORKFLOW_BOUNDARY_KEYS:
            reject(name, "metadata_keys_mismatch")
        group = boundary.get("union_output_group")
        discriminant_output = boundary.get("discriminant_output")
        field_role = boundary.get("field_role")
        active = boundary.get("active_variants")
        if (
            boundary.get("projection_class")
            != "union_workflow_boundary"
            or boundary.get("return_kind") != "union"
            or not isinstance(group, str)
            or not group
            or not isinstance(discriminant_output, str)
            or not discriminant_output
            or field_role not in {"discriminant", "shared", "variant"}
            or not isinstance(active, Sequence)
            or isinstance(active, (str, bytes))
            or not active
            or any(not isinstance(variant, str) or not variant for variant in active)
            or len(set(active)) != len(active)
        ):
            reject(name, "metadata_value_invalid")
        groups.setdefault(group, []).append(
            (name, spec, validation_spec, boundary)
        )

    for group, members in groups.items():
        discriminants = [
            member
            for member in members
            if member[3]["field_role"] == "discriminant"
        ]
        if len(discriminants) != 1:
            reject(members[0][0], "group_discriminant_count_invalid")
        discriminant_name, _, discriminant_spec, discriminant = (
            discriminants[0]
        )
        if (
            not discriminant_name.endswith("__variant")
            or group != discriminant_name.removesuffix("__variant")
        ):
            reject(discriminant_name, "group_discriminant_prefix_mismatch")
        allowed = discriminant_spec.get("allowed")
        active_variants = tuple(discriminant["active_variants"])
        if (
            discriminant_spec.get("type") != "enum"
            or discriminant_spec.get("required", True) is False
            or not isinstance(allowed, Sequence)
            or isinstance(allowed, (str, bytes))
            or tuple(allowed) != active_variants
        ):
            reject(discriminant_name, "discriminant_schema_mismatch")
        for name, _, _, boundary in members:
            member_active = tuple(boundary["active_variants"])
            active_set = set(member_active)
            ordered_active = tuple(
                variant
                for variant in active_variants
                if variant in active_set
            )
            role = boundary["field_role"]
            if (
                boundary["discriminant_output"] != discriminant_name
                or not active_set.issubset(active_variants)
                or member_active != ordered_active
                or (
                    role in {"discriminant", "shared"}
                    and member_active != active_variants
                )
                or (
                    role == "variant"
                    and member_active == active_variants
                )
            ):
                reject(name, "group_membership_invalid")
    return groups


def _union_workflow_boundary_candidate(
    validation_spec: Mapping[str, Any],
    *,
    output_name: str,
    reject: Callable[[str, str], NoReturn],
) -> Mapping[str, Any] | None:
    """Select one unambiguous union metadata carrier, if present."""

    candidates: list[Mapping[str, Any]] = []
    workflow_boundary = validation_spec.get("workflow_boundary")
    if isinstance(workflow_boundary, Mapping) and (
        _signals_union_workflow_boundary(workflow_boundary)
    ):
        candidates.append(workflow_boundary)
    if "projection" in validation_spec:
        projection = validation_spec.get("projection")
        if not isinstance(projection, Mapping):
            reject(output_name, "metadata_not_object")
        if _signals_union_workflow_boundary(projection):
            candidates.append(projection)
    if len(candidates) > 1:
        reject(output_name, "metadata_carrier_ambiguous")
    return candidates[0] if candidates else None


def _signals_union_workflow_boundary(metadata: Mapping[str, Any]) -> bool:
    """Return whether metadata claims or partially describes union authority."""

    return (
        metadata.get("projection_class") == "union_workflow_boundary"
        or metadata.get("return_kind") == "union"
        or any(
            key in metadata
            for key in _UNION_WORKFLOW_BOUNDARY_KEYS
            - {"projection_class", "return_kind"}
        )
    )


def _is_inactive_union_variant_output(
    boundary: Mapping[str, Any],
    active_union_variants: Mapping[str, Any],
) -> bool:
    if boundary.get("return_kind") == "root":
        # A root-valued `__result__` output is always active; only flattened
        # union variant outputs are gated on the resolved discriminant.
        return False
    if boundary.get("return_kind") != "union":
        return False
    if boundary.get("field_role") != "variant":
        return False
    group = str(boundary.get("union_output_group") or "")
    active_variant = active_union_variants.get(group)
    if not isinstance(active_variant, str):
        return False
    active_variants = boundary.get("active_variants")
    if not isinstance(active_variants, Sequence) or isinstance(active_variants, (str, bytes)):
        return False
    return active_variant not in {variant for variant in active_variants if isinstance(variant, str)}
