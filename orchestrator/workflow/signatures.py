"""Workflow-boundary input/output contract helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Sequence

from orchestrator.contracts.output_contract import OutputContractError, validate_contract_value

from .executable_ir import ExecutableContract
from .references import ReferenceResolutionError, ReferenceResolver


WORKFLOW_SIGNATURE_VERSION = "2.1"


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
    for name, spec in specs.items():
        validation_spec: Any = spec.definition if isinstance(spec, ExecutableContract) else spec
        boundary = _workflow_boundary_metadata(validation_spec)
        if boundary.get("field_role") != "discriminant":
            continue
        group = str(boundary.get("union_output_group") or name)
        binding = validation_spec.get("from") if isinstance(validation_spec, Mapping) else None
        ref = binding.get("ref") if isinstance(binding, Mapping) else None
        source = spec.source_address if isinstance(spec, ExecutableContract) else None
        if source is None and isinstance(ref, str) and ref:
            source = {"ref": ref}
        if source is None:
            continue
        try:
            if resolve_source is not None:
                raw_value = resolve_source(source, state)
            else:
                raw_value = resolver.resolve(ref, state).value
            active_variants[group] = validate_contract_value(
                raw_value,
                validation_spec,
                workspace=workspace,
            )
        except (ReferenceResolutionError, OutputContractError):
            # The main export loop will report the discriminant failure with the
            # normal workflow-output diagnostic context.
            continue
    return active_variants


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
