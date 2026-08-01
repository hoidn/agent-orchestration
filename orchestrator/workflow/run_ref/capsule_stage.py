"""Clone-local staging and typed relocation for decoded run-ref capsules."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.core_ast import validate_core_workflow_ast
from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_plan import validate_workflow_runtime_plan
from orchestrator.workflow.semantic_ir import validate_workflow_semantic_ir
from orchestrator.workflow.surface_ast import WorkflowProvenance

from .bundle_transport import (
    BundleCapsuleClosureBlob,
    BundleCapsuleValidationError,
    DecodedBundleCapsule,
)


_CAPSULE_STAGE_RELATIVE_ROOT = Path(".orchestrate") / "run-ref-capsule"
_CLOSURE_ROLES = frozenset({"orc", "prompt_asset", "workflow_asset"})


@dataclass(frozen=True)
class StagedBundleCapsule:
    """One verified clone-local closure and its relocated typed catalog."""

    staged_root: Path
    target_workflow_names: tuple[str, ...]
    bundles_by_name: Mapping[str, LoadedWorkflowBundle]
    workflow_paths_by_name: Mapping[str, Path]


def _invalid(detail: str) -> None:
    raise BundleCapsuleValidationError(
        "run_ref_capsule_invalid",
        f"run_ref_capsule_invalid: {detail}",
    )


def _canonical_relative_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\0" in value
    ):
        _invalid("closure path is not a canonical relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        _invalid("closure path is not a canonical relative POSIX path")
    canonical = path.as_posix()
    if canonical != value:
        _invalid("closure path is not a canonical relative POSIX path")
    return canonical


def _validate_decoded_capsule(
    decoded: DecodedBundleCapsule,
) -> tuple[
    Mapping[str, LoadedWorkflowBundle],
    tuple[str, ...],
    Mapping[str, BundleCapsuleClosureBlob],
    Mapping[str, str],
]:
    if type(decoded) is not DecodedBundleCapsule:
        _invalid("decoded capsule has the wrong type")
    catalog_value = decoded.bundles_by_name
    if not isinstance(catalog_value, Mapping) or not catalog_value:
        _invalid("decoded capsule catalog is empty or malformed")
    catalog: dict[str, LoadedWorkflowBundle] = {}
    for name, bundle in catalog_value.items():
        if (
            not isinstance(name, str)
            or not name
            or type(bundle) is not LoadedWorkflowBundle
            or bundle.surface.name != name
            or name in catalog
        ):
            _invalid("decoded capsule catalog is not canonical")
        catalog[name] = bundle

    targets = decoded.target_workflow_names
    if (
        not isinstance(targets, tuple)
        or not targets
        or any(not isinstance(name, str) or not name for name in targets)
        or targets != tuple(sorted(set(targets)))
        or any(name not in catalog for name in targets)
    ):
        _invalid("decoded capsule targets are not canonical")

    if not isinstance(decoded.closure, tuple) or not decoded.closure:
        _invalid("decoded capsule closure is empty or malformed")
    closure_by_path: dict[str, BundleCapsuleClosureBlob] = {}
    for blob in decoded.closure:
        if type(blob) is not BundleCapsuleClosureBlob:
            _invalid("decoded capsule closure contains the wrong blob type")
        path = _canonical_relative_path(blob.path)
        if path in closure_by_path:
            _invalid("decoded capsule closure contains a path collision")
        if (
            not isinstance(blob.roles, tuple)
            or not blob.roles
            or tuple(sorted(set(blob.roles))) != blob.roles
            or any(role not in _CLOSURE_ROLES for role in blob.roles)
            or not isinstance(blob.payload, bytes)
        ):
            _invalid("decoded capsule closure blob is malformed")
        closure_by_path[path] = blob

    workflow_path_value = decoded.workflow_closure_paths
    if (
        not isinstance(workflow_path_value, Mapping)
        or set(workflow_path_value) != set(catalog)
    ):
        _invalid("decoded capsule workflow-path association is incomplete")
    workflow_paths: dict[str, str] = {}
    for name, raw_path in workflow_path_value.items():
        path = _canonical_relative_path(raw_path)
        blob = closure_by_path.get(path)
        if blob is None or "orc" not in blob.roles:
            _invalid("decoded capsule workflow path is not an orc closure blob")
        workflow_paths[name] = path

    for name, bundle in catalog.items():
        if not isinstance(bundle.imports, Mapping):
            _invalid(f"decoded capsule import graph is malformed at {name!r}")
        for alias, child in bundle.imports.items():
            if type(child) is not LoadedWorkflowBundle:
                _invalid(
                    f"decoded capsule import graph is not closed at {name!r}"
                )
            child_name = child.surface.name
            if (
                not isinstance(alias, str)
                or not alias
                or not isinstance(child_name, str)
                or catalog.get(child_name) is not child
            ):
                _invalid(
                    f"decoded capsule import graph is not closed at {name!r}"
                )

    reachable: set[str] = set()
    pending = list(reversed(targets))
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        pending.extend(
            child.surface.name
            for child in catalog[name].imports.values()
            if child.surface.name not in reachable
        )
    if reachable != set(catalog):
        _invalid("decoded capsule catalog contains unreachable workflows")

    return (
        MappingProxyType({name: catalog[name] for name in sorted(catalog)}),
        targets,
        MappingProxyType(
            {path: closure_by_path[path] for path in sorted(closure_by_path)}
        ),
        MappingProxyType(
            {name: workflow_paths[name] for name in sorted(workflow_paths)}
        ),
    )


def _reject_existing_symlink_or_nondirectory(
    root: Path,
    directory: Path,
) -> None:
    relative = directory.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _invalid(f"staging directory is a symlink: {current}")
        if current.exists() and not current.is_dir():
            _invalid(f"staging directory collides with a non-directory: {current}")


def _stage_destinations(
    *,
    clone_root: Path,
    closure_by_path: Mapping[str, BundleCapsuleClosureBlob],
) -> tuple[Path, Path, Mapping[str, Path]]:
    try:
        canonical_clone_root = Path(clone_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BundleCapsuleValidationError(
            "run_ref_capsule_invalid",
            "run_ref_capsule_invalid: clone root is missing or unreadable",
        ) from exc
    if not canonical_clone_root.is_dir():
        _invalid("clone root is not a directory")

    staged_root = canonical_clone_root / _CAPSULE_STAGE_RELATIVE_ROOT
    closure_root = staged_root / "closure"
    _reject_existing_symlink_or_nondirectory(
        canonical_clone_root,
        closure_root,
    )

    path_parts = {
        path: PurePosixPath(path).parts for path in closure_by_path
    }
    ordered_paths = sorted(path_parts)
    for index, path in enumerate(ordered_paths):
        parts = path_parts[path]
        for other in ordered_paths[index + 1 :]:
            other_parts = path_parts[other]
            if len(parts) < len(other_parts) and other_parts[: len(parts)] == parts:
                _invalid("decoded capsule closure contains a file/directory collision")

    destinations: dict[str, Path] = {}
    canonical_closure_root = closure_root.resolve(strict=False)
    for path in ordered_paths:
        destination = closure_root.joinpath(*path_parts[path])
        try:
            destination.resolve(strict=False).relative_to(canonical_closure_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise BundleCapsuleValidationError(
                "run_ref_capsule_invalid",
                "run_ref_capsule_invalid: closure destination escapes staging root",
            ) from exc
        _reject_existing_symlink_or_nondirectory(
            canonical_clone_root,
            destination.parent,
        )
        if destination.is_symlink() or (
            destination.exists() and not destination.is_file()
        ):
            _invalid(f"closure destination collides with an existing entry: {path}")
        if destination.exists():
            try:
                existing = destination.read_bytes()
            except OSError as exc:
                raise BundleCapsuleValidationError(
                    "run_ref_capsule_invalid",
                    f"run_ref_capsule_invalid: existing closure byte read failed: {path}",
                ) from exc
            if existing != closure_by_path[path].payload:
                _invalid(f"existing closure bytes disagree at {path}")
        destinations[path] = destination
    return (
        staged_root,
        closure_root,
        MappingProxyType(destinations),
    )


def _write_and_verify_closure(
    *,
    closure_by_path: Mapping[str, BundleCapsuleClosureBlob],
    destinations: Mapping[str, Path],
) -> None:
    for path, blob in closure_by_path.items():
        destination = destinations[path]
        if not destination.exists():
            try:
                durable_atomic_write(destination, blob.payload)
            except (OSError, RuntimeError) as exc:
                raise BundleCapsuleValidationError(
                    "run_ref_capsule_invalid",
                    f"run_ref_capsule_invalid: closure write failed: {path}",
                ) from exc

    for path, blob in closure_by_path.items():
        destination = destinations[path]
        try:
            observed = destination.read_bytes()
        except OSError as exc:
            raise BundleCapsuleValidationError(
                "run_ref_capsule_invalid",
                f"run_ref_capsule_invalid: staged closure byte read failed: {path}",
            ) from exc
        if (
            len(observed) != len(blob.payload)
            or hashlib.sha256(observed).digest()
            != hashlib.sha256(blob.payload).digest()
            or observed != blob.payload
        ):
            _invalid(f"staged closure bytes failed rehash at {path}")


def _candidate_closure_paths(
    path: Path,
    provenance: WorkflowProvenance,
) -> tuple[str, ...]:
    candidates: set[str] = set()
    if not path.is_absolute():
        raw = path.as_posix()
        try:
            candidates.add(_canonical_relative_path(raw))
        except BundleCapsuleValidationError:
            return ()
    else:
        for root in (
            provenance.source_root,
            provenance.frontend_build_root,
            provenance.workflow_path.parent,
        ):
            if root is None:
                continue
            try:
                relative = path.relative_to(root).as_posix()
                candidates.add(_canonical_relative_path(relative))
            except (BundleCapsuleValidationError, ValueError):
                continue
    return tuple(sorted(candidates))


def _relocate_carried_frontend_path(
    path: Path | None,
    *,
    provenance: WorkflowProvenance,
    closure_by_path: Mapping[str, BundleCapsuleClosureBlob],
    destinations: Mapping[str, Path],
) -> Path | None:
    if path is None:
        return None
    matches = {
        candidate
        for candidate in _candidate_closure_paths(path, provenance)
        if candidate in closure_by_path
        and "workflow_asset" in closure_by_path[candidate].roles
    }
    if len(matches) > 1:
        _invalid("frontend artifact path has ambiguous closure correspondence")
    if not matches:
        return None
    return destinations[matches.pop()]


def _relocated_import_metadata(
    metadata: object,
    *,
    alias: str,
    original: LoadedWorkflowBundle,
    catalog: Mapping[str, LoadedWorkflowBundle],
    provenance_by_name: Mapping[str, WorkflowProvenance],
) -> object:
    imported = original.imports.get(alias)
    object_name = None if imported is None else imported.surface.name
    metadata_name = getattr(metadata, "workflow_name", None)
    if (
        object_name is not None
        and metadata_name is not None
        and object_name != metadata_name
    ):
        _invalid("import metadata disagrees with the typed import graph")
    child_name = object_name or metadata_name
    if child_name is not None and (
        not isinstance(child_name, str) or not child_name
    ):
        _invalid("import metadata has an invalid workflow name")
    if child_name not in catalog:
        return metadata
    child_provenance = provenance_by_name[child_name]
    try:
        return replace(
            metadata,
            workflow_path=child_provenance.workflow_path,
            source_root=child_provenance.source_root,
        )
    except (TypeError, ValueError) as exc:
        raise BundleCapsuleValidationError(
            "run_ref_capsule_invalid",
            "run_ref_capsule_invalid: import metadata cannot be relocated",
        ) from exc


def _relocate_catalog(
    *,
    catalog: Mapping[str, LoadedWorkflowBundle],
    workflow_paths: Mapping[str, str],
    closure_root: Path,
    closure_by_path: Mapping[str, BundleCapsuleClosureBlob],
    destinations: Mapping[str, Path],
) -> tuple[Mapping[str, LoadedWorkflowBundle], Mapping[str, Path]]:
    provenance_by_name: dict[str, WorkflowProvenance] = {}
    for name, original in catalog.items():
        provenance = original.provenance
        provenance_by_name[name] = replace(
            provenance,
            workflow_path=destinations[workflow_paths[name]],
            source_root=closure_root,
            frontend_source_trace_path=_relocate_carried_frontend_path(
                provenance.frontend_source_trace_path,
                provenance=provenance,
                closure_by_path=closure_by_path,
                destinations=destinations,
            ),
            frontend_persisted_surface_path=_relocate_carried_frontend_path(
                provenance.frontend_persisted_surface_path,
                provenance=provenance,
                closure_by_path=closure_by_path,
                destinations=destinations,
            ),
        )
    frozen_provenance = MappingProxyType(provenance_by_name)

    import_storage_by_name: dict[str, dict[str, LoadedWorkflowBundle]] = {
        name: {} for name in catalog
    }
    rebuilt: dict[str, LoadedWorkflowBundle] = {}
    for name, original in catalog.items():
        provenance = frozen_provenance[name]
        surface_imports = MappingProxyType(
            {
                alias: _relocated_import_metadata(
                    metadata,
                    alias=alias,
                    original=original,
                    catalog=catalog,
                    provenance_by_name=frozen_provenance,
                )
                for alias, metadata in sorted(original.surface.imports.items())
            }
        )
        surface = replace(
            original.surface,
            provenance=provenance,
            imports=surface_imports,
        )
        core_imports = MappingProxyType(
            {
                alias: _relocated_import_metadata(
                    metadata,
                    alias=alias,
                    original=original,
                    catalog=catalog,
                    provenance_by_name=frozen_provenance,
                )
                for alias, metadata in sorted(
                    original.core_workflow_ast.imports.items()
                )
            }
        )
        core = replace(
            original.core_workflow_ast,
            imports=core_imports,
            provenance=provenance,
            _surface_workflow=(
                surface
                if original.core_workflow_ast._surface_workflow is not None
                else None
            ),
        )
        rebuilt[name] = replace(
            original,
            surface=surface,
            core_workflow_ast=core,
            ir=replace(original.ir, provenance=provenance),
            imports=MappingProxyType(import_storage_by_name[name]),
            provenance=provenance,
        )

    for name, original in catalog.items():
        storage = import_storage_by_name[name]
        for alias, child in sorted(original.imports.items()):
            child_name = child.surface.name
            if catalog.get(child_name) is not child:
                _invalid("decoded capsule import graph changed during relocation")
            storage[alias] = rebuilt[child_name]

    relocated = MappingProxyType(
        {name: rebuilt[name] for name in sorted(rebuilt)}
    )
    try:
        for bundle in relocated.values():
            validate_core_workflow_ast(
                bundle.core_workflow_ast,
                imports=bundle.imports,
            )
            validate_executable_workflow(bundle.ir)
            validate_workflow_runtime_plan(
                bundle.runtime_plan,
                bundle.ir,
                bundle.projection,
            )
            validate_workflow_semantic_ir(
                bundle.semantic_ir,
                ir=bundle.ir,
                projection=bundle.projection,
                runtime_plan=bundle.runtime_plan,
                surface=bundle.surface,
                imports=bundle.imports,
            )
            persisted = serialize_persisted_workflow_surface_graph(bundle)
            decode_persisted_workflow_surface_graph(
                canonical_persisted_surface_bytes(persisted)
            )
    except BundleCapsuleValidationError:
        raise
    except Exception as exc:
        raise BundleCapsuleValidationError(
            "run_ref_capsule_invalid",
            "run_ref_capsule_invalid: relocated catalog validation failed",
        ) from exc

    return (
        relocated,
        MappingProxyType(
            {
                name: provenance_by_name[name].workflow_path
                for name in sorted(provenance_by_name)
            }
        ),
    )


def stage_bundle_capsule(
    decoded: DecodedBundleCapsule,
    *,
    clone_root: Path,
) -> StagedBundleCapsule:
    """Stage exact closure bytes and relocate one decoded catalog in memory."""

    catalog, targets, closure_by_path, workflow_paths = (
        _validate_decoded_capsule(decoded)
    )
    staged_root, closure_root, destinations = _stage_destinations(
        clone_root=clone_root,
        closure_by_path=closure_by_path,
    )
    _write_and_verify_closure(
        closure_by_path=closure_by_path,
        destinations=destinations,
    )
    relocated, workflow_paths_by_name = _relocate_catalog(
        catalog=catalog,
        workflow_paths=workflow_paths,
        closure_root=closure_root,
        closure_by_path=closure_by_path,
        destinations=destinations,
    )
    return StagedBundleCapsule(
        staged_root=staged_root,
        target_workflow_names=targets,
        bundles_by_name=relocated,
        workflow_paths_by_name=workflow_paths_by_name,
    )
