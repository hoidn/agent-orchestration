"""Managed-job policy loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from .extractors import metadata_from_extractor
from .models import ManagedJobMetadata, ManagedJobPolicy, ManagedJobPolicyEntry


class ManagedJobPolicyError(ValueError):
    """Raised when managed-job policy loading fails."""


MANAGED_MODES = {"force_managed", "auto_managed"}
UNMANAGED_MODES = {"force_local", "unmanaged"}
VALID_BACKENDS = {"auto", "local", "slurm"}


def _validate_relpath(value: str, context: str) -> None:
    path = Path(value)
    if path.is_absolute():
        raise ManagedJobPolicyError(f"{context}: absolute paths not allowed")
    if ".." in path.parts:
        raise ManagedJobPolicyError(f"{context}: parent directory traversal not allowed")


def _string_tuple(node: Any, context: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(node, list) or (not allow_empty and not node):
        raise ManagedJobPolicyError(f"{context} must be a non-empty list")
    values: list[str] = []
    for index, item in enumerate(node):
        if not isinstance(item, str) or not item:
            raise ManagedJobPolicyError(f"{context}[{index}] must be a non-empty string")
        values.append(item)
    return tuple(values)


def metadata_from_mapping(node: Mapping[str, Any], *, context: str) -> ManagedJobMetadata:
    """Normalize explicit job metadata from policy YAML."""

    name_template = node.get("name_template")
    state_root_template = node.get("state_root_template")
    output_root_arg = node.get("output_root_arg")
    if not isinstance(name_template, str) or not name_template:
        raise ManagedJobPolicyError(f"{context}.name_template is required")
    if not isinstance(state_root_template, str) or not state_root_template:
        raise ManagedJobPolicyError(f"{context}.state_root_template is required")
    _validate_relpath(state_root_template, f"{context}.state_root_template")
    if output_root_arg is not None and not isinstance(output_root_arg, str):
        raise ManagedJobPolicyError(f"{context}.output_root_arg must be a string")
    verify_files = _string_tuple(node.get("verify_files"), f"{context}.verify_files")
    snapshot_roots = _string_tuple(node.get("snapshot_roots"), f"{context}.snapshot_roots")
    config_globs = _string_tuple(node.get("config_globs", []), f"{context}.config_globs", allow_empty=True)
    for index, snapshot_root in enumerate(snapshot_roots):
        _validate_relpath(snapshot_root, f"{context}.snapshot_roots[{index}]")
    return ManagedJobMetadata(
        name_template=name_template,
        state_root_template=state_root_template,
        output_root_arg=output_root_arg,
        verify_files=verify_files,
        snapshot_roots=snapshot_roots,
        config_globs=config_globs,
    )


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ManagedJobPolicyError(f"could not parse policy YAML: {exc}") from exc
    except OSError as exc:
        raise ManagedJobPolicyError(f"could not read policy: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ManagedJobPolicyError("policy must be a mapping")
    return payload


def load_policy(path: Path, *, workspace: Path) -> ManagedJobPolicy:
    """Load and normalize a managed-job policy file."""

    if not path.exists():
        raise ManagedJobPolicyError(f"policy file '{path}' does not exist")
    payload = _load_yaml(path)
    defaults = payload.get("backend_defaults", {})
    default_backend = "auto"
    if isinstance(defaults, Mapping) and isinstance(defaults.get("backend"), str):
        default_backend = defaults["backend"]
    if default_backend not in VALID_BACKENDS:
        raise ManagedJobPolicyError("backend_defaults.backend must be auto, local, or slurm")

    extractor_specs = payload.get("extractors", {})
    if extractor_specs is None:
        extractor_specs = {}
    if not isinstance(extractor_specs, Mapping):
        raise ManagedJobPolicyError("extractors must be a mapping")

    entries_node = payload.get("entries")
    if not isinstance(entries_node, list):
        raise ManagedJobPolicyError("entries must be a list")

    entries: list[ManagedJobPolicyEntry] = []
    for index, entry_node in enumerate(entries_node):
        context = f"entries[{index}]"
        if not isinstance(entry_node, Mapping):
            raise ManagedJobPolicyError(f"{context} must be a mapping")
        entry_id = entry_node.get("id")
        mode = entry_node.get("mode")
        entry_path = entry_node.get("path")
        if not isinstance(entry_id, str) or not entry_id:
            raise ManagedJobPolicyError(f"{context}.id is required")
        if mode not in MANAGED_MODES | UNMANAGED_MODES:
            raise ManagedJobPolicyError(f"{context}.mode is invalid")
        if not isinstance(entry_path, str) or not entry_path:
            raise ManagedJobPolicyError(f"{context}.path is required")
        _validate_relpath(entry_path, f"{context}.path")

        backend = entry_node.get("backend", default_backend)
        if backend not in VALID_BACKENDS:
            raise ManagedJobPolicyError(f"{context}.backend must be auto, local, or slurm")

        metadata = None
        if mode in MANAGED_MODES:
            job = entry_node.get("job")
            extractor = entry_node.get("extractor")
            if isinstance(job, Mapping):
                metadata = metadata_from_mapping(job, context=f"{context}.job")
            elif isinstance(extractor, str) and extractor:
                extractor_spec = extractor_specs.get(extractor)
                if not isinstance(extractor_spec, Mapping):
                    raise ManagedJobPolicyError(f"{context}.extractor references unknown extractor '{extractor}'")
                try:
                    metadata = metadata_from_extractor(extractor, extractor_spec)
                except ValueError as exc:
                    raise ManagedJobPolicyError(str(exc)) from exc
            else:
                raise ManagedJobPolicyError(f"{context} requires job metadata or extractor")

        entries.append(
            ManagedJobPolicyEntry(
                id=entry_id,
                mode=mode,
                path=entry_path,
                backend=backend,
                metadata=metadata,
            )
        )

    return ManagedJobPolicy(entries=tuple(entries), default_backend=default_backend)
