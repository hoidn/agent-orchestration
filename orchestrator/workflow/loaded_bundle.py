"""Typed loaded-workflow bundle and bundle-native compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .executable_ir import ExecutableWorkflow
from .state_projection import WorkflowStateProjection
from .surface_ast import ImportedWorkflowMetadata, SurfaceWorkflow, WorkflowProvenance


@dataclass(frozen=True)
class LoadedWorkflowBundle:
    """Typed loaded-workflow bundle."""

    surface: SurfaceWorkflow
    ir: ExecutableWorkflow
    projection: WorkflowStateProjection
    imports: Mapping[str, "LoadedWorkflowBundle"]
    provenance: WorkflowProvenance


def _compatibility_value(value: Any) -> Any:
    """Convert frozen AST contract payloads back into plain compatibility values."""
    if isinstance(value, Mapping):
        return {str(key): _compatibility_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_compatibility_value(item) for item in value]
    if isinstance(value, list):
        return [_compatibility_value(item) for item in value]
    return value


def workflow_bundle(workflow_or_bundle: Any) -> Optional[LoadedWorkflowBundle]:
    """Return the loaded workflow bundle when one is available."""
    if isinstance(workflow_or_bundle, LoadedWorkflowBundle):
        return workflow_or_bundle
    return None


def workflow_context(workflow_or_bundle: Any) -> Mapping[str, Any]:
    """Return workflow context values from typed bundle or raw workflow data."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.surface.context
    if isinstance(workflow_or_bundle, Mapping):
        context = workflow_or_bundle.get("context")
        if isinstance(context, Mapping):
            return context
    return MappingProxyType({})


def workflow_input_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    """Return workflow input contracts from typed or legacy workflow metadata."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return MappingProxyType({
            name: _compatibility_value(contract.definition)
            for name, contract in bundle.surface.inputs.items()
            if isinstance(name, str) and isinstance(contract.definition, Mapping)
        })
    if isinstance(workflow_or_bundle, Mapping):
        inputs = workflow_or_bundle.get("inputs")
        if isinstance(inputs, Mapping):
            return inputs
    return MappingProxyType({})


def workflow_output_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    """Return workflow output contracts from typed or legacy workflow metadata."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return MappingProxyType({
            name: _compatibility_value(contract.definition)
            for name, contract in bundle.surface.outputs.items()
            if isinstance(name, str) and isinstance(contract.definition, Mapping)
        })
    if isinstance(workflow_or_bundle, Mapping):
        outputs = workflow_or_bundle.get("outputs")
        if isinstance(outputs, Mapping):
            return outputs
    return MappingProxyType({})


def workflow_provenance(workflow_or_bundle: Any) -> Optional[WorkflowProvenance]:
    """Return typed workflow provenance for one loaded workflow bundle."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.provenance
    return None


def workflow_import_metadata(workflow_or_bundle: Any, alias: str) -> Optional[ImportedWorkflowMetadata]:
    """Return typed imported-workflow metadata for one alias."""
    if not isinstance(alias, str) or not alias:
        return None
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.surface.imports.get(alias)
    return None


def workflow_import_bundle(workflow_or_bundle: Any, alias: str) -> Optional[LoadedWorkflowBundle]:
    """Return the imported loaded-workflow bundle for one alias when available."""
    if not isinstance(alias, str) or not alias:
        return None
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.imports.get(alias)
    return None


def workflow_managed_write_root_inputs(workflow_or_bundle: Any) -> tuple[str, ...]:
    """Return typed managed write-root inputs for one loaded workflow."""
    provenance = workflow_provenance(workflow_or_bundle)
    if provenance is None:
        return ()
    return provenance.managed_write_root_inputs
