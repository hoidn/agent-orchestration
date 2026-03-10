"""Typed loaded-workflow bundle plus legacy compatibility adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional

from .surface_ast import ImportedWorkflowMetadata, SurfaceWorkflow, WorkflowProvenance


LEGACY_TYPED_PROVENANCE_KEY = "__typed_provenance"
LEGACY_TYPED_IMPORTS_KEY = "__typed_imports"


@dataclass(frozen=True)
class LoadedWorkflowBundle:
    """Typed loaded-workflow bundle with a legacy dict compatibility slot."""

    surface: SurfaceWorkflow
    legacy_workflow: Dict[str, Any]
    imports: Mapping[str, "LoadedWorkflowBundle"]
    provenance: WorkflowProvenance


def attach_legacy_workflow_metadata(legacy_workflow: Dict[str, Any], bundle: LoadedWorkflowBundle) -> Dict[str, Any]:
    """Attach typed compatibility adapters onto the legacy loaded-workflow dict."""
    legacy_workflow[LEGACY_TYPED_PROVENANCE_KEY] = bundle.provenance
    legacy_workflow[LEGACY_TYPED_IMPORTS_KEY] = MappingProxyType(dict(bundle.surface.imports))
    return legacy_workflow


def workflow_provenance(workflow_or_bundle: Any) -> Optional[WorkflowProvenance]:
    """Return typed workflow provenance for either a bundle or legacy workflow dict."""
    if isinstance(workflow_or_bundle, LoadedWorkflowBundle):
        return workflow_or_bundle.provenance
    if isinstance(workflow_or_bundle, dict):
        provenance = workflow_or_bundle.get(LEGACY_TYPED_PROVENANCE_KEY)
        if isinstance(provenance, WorkflowProvenance):
            return provenance
        workflow_path = workflow_or_bundle.get("__workflow_path")
        source_root = workflow_or_bundle.get("__source_root")
        managed_inputs = workflow_or_bundle.get("__managed_write_root_inputs", [])
        if isinstance(workflow_path, str) and workflow_path:
            return WorkflowProvenance(
                workflow_path=Path(workflow_path).resolve(),
                source_root=Path(source_root).resolve() if isinstance(source_root, str) and source_root else Path(workflow_path).resolve().parent,
                managed_write_root_inputs=tuple(
                    item for item in managed_inputs if isinstance(item, str)
                ),
                imported_aliases=tuple(
                    alias
                    for alias in workflow_or_bundle.get("__imports", {})
                    if isinstance(alias, str)
                ),
            )
    return None


def workflow_import_metadata(workflow_or_bundle: Any, alias: str) -> Optional[ImportedWorkflowMetadata]:
    """Return typed imported-workflow metadata for one alias."""
    if not isinstance(alias, str) or not alias:
        return None
    if isinstance(workflow_or_bundle, LoadedWorkflowBundle):
        return workflow_or_bundle.surface.imports.get(alias)
    if isinstance(workflow_or_bundle, dict):
        imports = workflow_or_bundle.get(LEGACY_TYPED_IMPORTS_KEY)
        if isinstance(imports, Mapping):
            metadata = imports.get(alias)
            if isinstance(metadata, ImportedWorkflowMetadata):
                return metadata
        imported = workflow_or_bundle.get("__imports", {}).get(alias) if isinstance(workflow_or_bundle.get("__imports"), dict) else None
        provenance = workflow_provenance(imported)
        if provenance is None:
            return None
        return ImportedWorkflowMetadata(
            alias=alias,
            workflow_path=provenance.workflow_path,
            source_root=provenance.source_root,
            managed_write_root_inputs=provenance.managed_write_root_inputs,
            workflow_name=imported.get("name") if isinstance(imported, dict) and isinstance(imported.get("name"), str) else None,
        )
    return None


def workflow_managed_write_root_inputs(workflow_or_bundle: Any) -> tuple[str, ...]:
    """Return typed managed write-root inputs for one loaded workflow."""
    provenance = workflow_provenance(workflow_or_bundle)
    if provenance is None:
        return ()
    return provenance.managed_write_root_inputs
