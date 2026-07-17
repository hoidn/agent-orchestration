"""Read a run-bound persisted Workflow Lisp surface graph without a frontend."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.workflow.persisted_surface import (
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
    PersistedWorkflowSurfaceGraph,
    decode_persisted_workflow_surface_graph,
)


_BUILD_SCHEMA_VERSION = "workflow_lisp_build.v2"
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{16}")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
_ANCHOR_KEYS = {"schema_version", "path", "entry_workflow", "sha256"}


class PersistedCompiledWorkflowError(ValueError):
    """A persisted compiled-frontend surface binding fails closed."""


def load_persisted_compiled_workflow_surface(
    *,
    workspace_root: Path,
    workflow_path: Path,
    state: Mapping[str, Any],
) -> PersistedWorkflowSurfaceGraph:
    """Verify state + manifest authority and decode the persisted surface graph."""

    workspace = workspace_root.resolve(strict=True)
    compiled = _compiled_frontend_record(state)
    state_anchor = _state_surface_anchor(compiled)
    build_root = _validated_build_root(workspace, compiled)
    manifest = _load_authoritative_manifest(build_root)
    if manifest.get("schema_version") != _BUILD_SCHEMA_VERSION:
        _fail("manifest schema version is unsupported for persisted surface reads")
    if manifest.get("fingerprint") != build_root.name:
        _fail("manifest fingerprint does not match the content-addressed build root")
    if manifest.get("shared_validation_status") != "validated":
        _fail("manifest does not record shared validation success")
    manifest_anchor = _closed_anchor(
        manifest.get("persisted_workflow_surface"),
        label="manifest persisted workflow surface anchor",
    )
    if manifest_anchor != state_anchor:
        _fail("state and manifest persisted workflow surface anchors do not match")
    anchor_entry = state_anchor["entry_workflow"]
    if manifest.get("entry_workflow") != anchor_entry:
        _fail("manifest entry workflow does not match the persisted surface anchor")
    if compiled.get("frontend_entry_workflow") != anchor_entry:
        _fail("state entry workflow does not match the persisted surface anchor")
    expected_source = _validate_manifest_source_binding(
        manifest,
        workspace=workspace,
        workflow_path=workflow_path,
        compiled=compiled,
    )
    artifact_path = _validated_surface_artifact_path(
        workspace,
        build_root=build_root,
        anchor=state_anchor,
    )
    payload = artifact_path.read_bytes()
    observed_digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if observed_digest != state_anchor["sha256"]:
        _fail("persisted workflow surface digest does not match the run binding")
    try:
        graph = decode_persisted_workflow_surface_graph(payload)
    except ValueError as exc:
        _fail(f"persisted workflow surface graph is invalid: {exc}")
    if (
        graph.schema_version != state_anchor["schema_version"]
        or graph.entry_workflow != state_anchor["entry_workflow"]
    ):
        _fail("persisted workflow surface graph identity mismatches its anchor")
    graph_entry_source = _lexical_workspace_path(
        workspace,
        str(graph.entry_node.workflow_path),
        label="persisted workflow surface entry source path",
    )
    if graph_entry_source != expected_source:
        _fail("persisted workflow surface entry source path mismatches the run binding")
    return graph


def _compiled_frontend_record(state: Mapping[str, Any]) -> Mapping[str, Any]:
    runtime = state.get("runtime_observability")
    compiled = runtime.get("compiled_frontend") if isinstance(runtime, Mapping) else None
    if not isinstance(compiled, Mapping):
        _fail("state is missing runtime_observability.compiled_frontend")
    if compiled.get("frontend_kind") != "workflow_lisp":
        _fail("frontend_kind is not workflow_lisp")
    return compiled


def _state_surface_anchor(compiled: Mapping[str, Any]) -> dict[str, str]:
    if "persisted_workflow_surface" not in compiled:
        _fail("legacy persisted compiled frontend has no persisted workflow surface anchor")
    return _closed_anchor(
        compiled.get("persisted_workflow_surface"),
        label="state persisted workflow surface anchor",
    )


def _closed_anchor(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _ANCHOR_KEYS:
        _fail(f"{label} is partial or malformed")
    anchor = dict(value)
    if anchor.get("schema_version") != PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA:
        _fail(f"{label} schema version is unsupported")
    for key in ("path", "entry_workflow"):
        if not isinstance(anchor.get(key), str) or not anchor[key]:
            _fail(f"{label} field {key} is invalid")
    digest = anchor.get("sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        _fail(f"{label} digest syntax is invalid")
    return anchor


def _validated_build_root(
    workspace: Path,
    compiled: Mapping[str, Any],
) -> Path:
    raw_build_root = _required_string(compiled, "frontend_build_root")
    build_root = _resolved_workspace_path(
        workspace,
        raw_build_root,
        label="persisted compiled frontend build root",
    )
    expected_parent = (workspace / ".orchestrate" / "build").resolve(strict=False)
    if build_root.parent != expected_parent:
        _fail("build root is outside the workspace content-addressed build store")
    if _FINGERPRINT_RE.fullmatch(build_root.name) is None:
        _fail("build root does not end in a canonical build fingerprint")
    return build_root


def _validate_manifest_source_binding(
    manifest: Mapping[str, Any],
    *,
    workspace: Path,
    workflow_path: Path,
    compiled: Mapping[str, Any],
) -> Path:
    source_path = _lexical_workspace_path(
        workspace,
        _required_string(manifest, "source_path"),
        label="persisted compiled frontend manifest source",
    )
    expected_source = _lexical_workspace_path(
        workspace,
        str(workflow_path),
        label="persisted run workflow path",
    )
    if source_path != expected_source:
        _fail("manifest source_path does not match the run workflow_file")
    entry_workflow = _required_string(manifest, "entry_workflow")
    if compiled.get("frontend_entry_workflow") != entry_workflow:
        _fail("state entry workflow does not match the manifest entry workflow")
    return source_path


def _validated_surface_artifact_path(
    workspace: Path,
    *,
    build_root: Path,
    anchor: Mapping[str, str],
) -> Path:
    raw_path = anchor["path"]
    pointer = Path(raw_path)
    if pointer.is_absolute() or pointer.as_posix() != raw_path:
        _fail("persisted workflow surface path must be build-relative POSIX")
    expected_raw = f"build/{build_root.name}/persisted_workflow_surface.json"
    if raw_path != expected_raw:
        _fail("persisted workflow surface path mismatches the bound build root")
    lexical_artifact = build_root / "persisted_workflow_surface.json"
    if lexical_artifact.is_symlink():
        _fail("persisted workflow surface artifact escapes its bound build root")
    try:
        resolved = (workspace / ".orchestrate" / pointer).resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("persisted workflow surface artifact is missing or unreadable")
    expected = lexical_artifact.resolve(strict=True)
    if resolved != expected or not resolved.is_file():
        _fail("persisted workflow surface artifact escapes its bound build root")
    return resolved


def _load_json_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail(f"{label} is missing, unreadable, or invalid JSON")
    if not isinstance(payload, Mapping):
        _fail(f"{label} must be a JSON object")
    return payload


def _load_authoritative_manifest(build_root: Path) -> Mapping[str, Any]:
    manifest_path = build_root / "manifest.json"
    if manifest_path.is_symlink():
        _fail("persisted compiled frontend manifest path is unsafe")
    try:
        resolved = manifest_path.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("persisted compiled frontend manifest is missing or unsafe")
    if resolved != manifest_path or resolved.parent != build_root or not resolved.is_file():
        _fail("persisted compiled frontend manifest path is unsafe")
    return _load_json_mapping(
        resolved,
        label="persisted compiled frontend manifest",
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _resolved_workspace_path(workspace: Path, raw: str, *, label: str) -> Path:
    path = Path(raw)
    candidate = path if path.is_absolute() else workspace / path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(workspace)
    except (OSError, RuntimeError, ValueError):
        _fail(f"{label} is unsafe, missing, or outside the workspace")
    return resolved


def _lexical_workspace_path(workspace: Path, raw: str, *, label: str) -> Path:
    path = Path(raw)
    candidate = path if path.is_absolute() else workspace / path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(workspace)
    except (OSError, RuntimeError, ValueError):
        _fail(f"{label} is unsafe or outside the workspace")
    return resolved


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        _fail(f"persisted compiled frontend field {key} is missing or invalid")
    return item


def _fail(message: str) -> None:
    raise PersistedCompiledWorkflowError(message)
