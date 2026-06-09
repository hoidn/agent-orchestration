"""Typed loaded-workflow bundle and bundle-native compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .core_ast import CoreWorkflowAST
from .executable_ir import ExecutablePrivateArtifact, ExecutableWorkflow
from .runtime_plan import WorkflowRuntimePlan
from .semantic_ir import SemanticWorkflowIR
from .state_projection import WorkflowStateProjection
from .surface_ast import ImportedWorkflowMetadata, SurfaceWorkflow, WorkflowProvenance


@dataclass(frozen=True)
class LoadedWorkflowBundle:
    """Typed loaded-workflow bundle."""

    surface: SurfaceWorkflow
    core_workflow_ast: CoreWorkflowAST
    semantic_ir: SemanticWorkflowIR
    ir: ExecutableWorkflow
    projection: WorkflowStateProjection
    runtime_plan: WorkflowRuntimePlan
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


def _require_bundle(workflow_or_bundle: Any) -> LoadedWorkflowBundle:
    """Return one loaded-workflow bundle or raise for non-typed callers."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is None:
        raise TypeError("LoadedWorkflowBundle required")
    return bundle


def workflow_is_managed_write_root_input_name(name: Any) -> bool:
    """Return whether one input name uses the compiler-owned managed write-root prefix."""
    return isinstance(name, str) and name.startswith("__write_root__")


def workflow_context(workflow_or_bundle: Any) -> Mapping[str, Any]:
    """Return workflow context values from the typed bundle."""
    return _require_bundle(workflow_or_bundle).surface.context


def workflow_core_ast(workflow_or_bundle: Any) -> Optional[CoreWorkflowAST]:
    """Return typed Core Workflow AST for one loaded bundle."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.core_workflow_ast
    return None


def workflow_input_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    """Return workflow input contracts from the typed bundle."""
    if workflow_or_bundle is None:
        return MappingProxyType({})
    bundle = _require_bundle(workflow_or_bundle)
    return MappingProxyType({
        name: _compatibility_value(contract.definition)
        for name, contract in bundle.surface.inputs.items()
        if isinstance(name, str) and isinstance(contract.definition, Mapping)
    })


def _managed_write_root_input_set(bundle: LoadedWorkflowBundle) -> frozenset[str]:
    managed_inputs = workflow_managed_write_root_inputs(bundle)
    return frozenset(name for name in managed_inputs if isinstance(name, str))


def _runtime_context_input_set(bundle: LoadedWorkflowBundle) -> frozenset[str]:
    runtime_inputs = workflow_runtime_context_inputs(bundle)
    return frozenset(name for name in runtime_inputs if isinstance(name, str))


def workflow_public_input_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    """Return the user-bindable workflow input contracts from the typed bundle."""
    if workflow_or_bundle is None:
        return MappingProxyType({})
    bundle = _require_bundle(workflow_or_bundle)
    managed_inputs = _managed_write_root_input_set(bundle)
    runtime_context_inputs = _runtime_context_input_set(bundle)
    return MappingProxyType({
        name: _compatibility_value(contract.definition)
        for name, contract in bundle.surface.inputs.items()
        if isinstance(name, str)
        and name not in managed_inputs
        and name not in runtime_context_inputs
        and isinstance(contract.definition, Mapping)
    })


def workflow_runtime_input_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    """Return the runtime-required workflow input contracts from the typed bundle."""
    return workflow_input_contracts(workflow_or_bundle)


def workflow_output_contracts(workflow_or_bundle: Any) -> Mapping[str, Mapping[str, Any]]:
    """Return workflow output contracts from the typed bundle."""
    if workflow_or_bundle is None:
        return MappingProxyType({})
    bundle = _require_bundle(workflow_or_bundle)
    return MappingProxyType({
        name: _compatibility_value(contract.definition)
        for name, contract in bundle.surface.outputs.items()
        if isinstance(name, str) and isinstance(contract.definition, Mapping)
    })


def workflow_private_artifacts(
    workflow_or_bundle: Any,
) -> Mapping[str, ExecutablePrivateArtifact]:
    """Return the typed executable-private artifact catalog for one loaded bundle."""
    if workflow_or_bundle is None:
        return MappingProxyType({})
    bundle = _require_bundle(workflow_or_bundle)
    return MappingProxyType(dict(bundle.ir.private_artifacts))


def workflow_provenance(workflow_or_bundle: Any) -> Optional[WorkflowProvenance]:
    """Return typed workflow provenance for one loaded workflow bundle."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.provenance
    return None


def workflow_runtime_plan(workflow_or_bundle: Any) -> Optional[WorkflowRuntimePlan]:
    """Return typed workflow runtime-plan metadata for one loaded bundle."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.runtime_plan
    return None


def workflow_semantic_ir(workflow_or_bundle: Any) -> Optional[SemanticWorkflowIR]:
    """Return typed semantic workflow IR for one loaded bundle."""
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is not None:
        return bundle.semantic_ir
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
    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is None:
        return ()
    if bundle.provenance.managed_write_root_inputs:
        return bundle.provenance.managed_write_root_inputs
    return tuple(
        name
        for name in bundle.surface.inputs
        if workflow_is_managed_write_root_input_name(name)
    )


def workflow_runtime_context_inputs(workflow_or_bundle: Any) -> tuple[str, ...]:
    """Return typed runtime-owned context inputs for one loaded workflow."""

    bundle = workflow_bundle(workflow_or_bundle)
    if bundle is None:
        return ()
    return tuple(
        name
        for name in bundle.provenance.runtime_context_inputs
        if isinstance(name, str)
    )
