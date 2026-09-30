"""Transactional selected-output promotion for adjudicated-provider steps."""

from __future__ import annotations

import json
import errno
import stat
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_expected_outputs,
    validate_output_bundle,
)

from .models import BaselineManifest, PromotionConflictError, PromotionResult
from .utils import (
    _atomic_write_text,
    _matching_exclusion,
    _resolve_json_pointer,
    _safe_relpath,
_canonical_json,
)
from ..workspace_files import WorkspaceFiles
from ..._common.safe_tree import SafeTreeRejectionError


def _sha256_bytes(content: bytes) -> str:
    return "sha256:" + sha256(content).hexdigest()


def _open_nearest_existing_owner(path: Path) -> tuple[WorkspaceFiles, Path]:
    candidate = path
    while True:
        try:
            return WorkspaceFiles(candidate), candidate
        except SafeTreeRejectionError as exc:
            cause = exc.__cause__
            if not isinstance(cause, OSError) or cause.errno != errno.ENOENT:
                raise
            parent = candidate.parent
            if parent == candidate:
                raise
            candidate = parent

def promote_candidate_outputs(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    baseline_manifest: BaselineManifest,
    promotion_manifest_path: Path,
    selected_candidate_id: str | None = None,
    workspace_files: WorkspaceFiles | None = None,
    run_root: Path | None = None,
    run_workspace_files: WorkspaceFiles | None = None,
) -> PromotionResult:
    owns_parent_files = workspace_files is None
    parent_files = workspace_files or WorkspaceFiles(parent_workspace)
    candidate_files: WorkspaceFiles | None = None
    promotion_root = Path(promotion_manifest_path).parent
    promotion_files: WorkspaceFiles | None = None
    promotion_parent_files: WorkspaceFiles | None = None
    owners = ExitStack()
    if owns_parent_files:
        owners.callback(parent_files.close)
    try:
        if run_workspace_files is not None:
            if run_root is None:
                raise ValueError("run_root is required with run_workspace_files")
            promotion_relative = Path(promotion_root).relative_to(Path(run_root))
            run_workspace_files.ensure_directory(promotion_relative)
            promotion_files = run_workspace_files.subroot(promotion_relative)
            owners.callback(promotion_files.close)
        else:
            try:
                promotion_relative = parent_files.relative(promotion_root)
            except ValueError:
                promotion_parent_files, promotion_parent = _open_nearest_existing_owner(
                    promotion_root.parent
                )
                owners.callback(promotion_parent_files.close)
                promotion_relative = promotion_root.relative_to(promotion_parent)
                promotion_parent_files.ensure_directory(promotion_relative)
                promotion_files = promotion_parent_files.subroot(promotion_relative)
                owners.callback(promotion_files.close)
            else:
                parent_files.ensure_directory(promotion_relative)
                promotion_files = parent_files
        owns_candidate_files = owns_parent_files
        if run_workspace_files is not None:
            candidate_relative = Path(candidate_workspace).relative_to(Path(run_root))
            if not run_workspace_files.exists(candidate_relative):
                candidate_files = None
            else:
                candidate_files = run_workspace_files.subroot(candidate_relative)
                owners.callback(candidate_files.close)
        elif owns_candidate_files and not Path(candidate_workspace).exists():
            candidate_files = None
        else:
            try:
                candidate_files = (
                    WorkspaceFiles(candidate_workspace)
                    if owns_candidate_files
                    else parent_files.subroot(candidate_workspace)
                )
                owners.callback(candidate_files.close)
            except FileNotFoundError:
                candidate_files = None
        return _promote_candidate_outputs(
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            candidate_workspace=candidate_workspace,
            parent_workspace=parent_workspace,
            baseline_manifest=baseline_manifest,
            promotion_manifest_path=promotion_manifest_path,
            selected_candidate_id=selected_candidate_id,
            workspace_files=parent_files,
            candidate_files=candidate_files,
            promotion_files=promotion_files,
        )
    finally:
        owners.close()


def _promote_candidate_outputs(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    baseline_manifest: BaselineManifest,
    promotion_manifest_path: Path,
    selected_candidate_id: str | None,
    workspace_files: WorkspaceFiles,
    candidate_files: WorkspaceFiles | None,
    promotion_files: WorkspaceFiles,
) -> PromotionResult:

    if promotion_manifest_path.exists():
        manifest = _load_promotion_manifest(promotion_manifest_path)
        manifest_candidate_id = manifest.get("selected_candidate_id")
        if (
            selected_candidate_id is not None
            and manifest_candidate_id is not None
            and manifest_candidate_id != selected_candidate_id
        ):
            raise PromotionConflictError(
                "promotion manifest selected candidate does not match current selection",
                failure_type="adjudication_state_integrity_error",
            )
        if manifest.get("status") in {"prepared", "committing", "rolling_back", "failed", "committed"}:
            return _resume_promotion_manifest(
                manifest=manifest,
                expected_outputs=expected_outputs,
                output_bundle=output_bundle,
                parent_workspace=parent_workspace,
                promotion_manifest_path=promotion_manifest_path,
                workspace_files=workspace_files,
                candidate_files=candidate_files,
                promotion_files=promotion_files,
            )

    try:
        if candidate_files is None:
            raise FileNotFoundError("candidate workspace is unavailable")
        if output_bundle:
            artifacts = validate_output_bundle(
                output_bundle,
                workspace=candidate_workspace,
                workspace_files=candidate_files,
            )
        else:
            artifacts = validate_expected_outputs(
                expected_outputs or [],
                workspace=candidate_workspace,
                workspace_files=candidate_files,
            )
    except OutputContractError as exc:
        raise PromotionConflictError(str(exc), failure_type="promotion_validation_failed") from exc

    files, promoted_paths = _promotion_file_plan(
        expected_outputs=expected_outputs,
        output_bundle=output_bundle,
        candidate_workspace=candidate_workspace,
        parent_workspace=parent_workspace,
        artifacts=artifacts,
        candidate_files=candidate_files,
    )
    _reject_duplicate_destinations(files, candidate_files)
    for file_entry in files:
        baseline_preimage = _baseline_preimage(baseline_manifest, file_entry["dest_rel"])
        if baseline_preimage.get("state") == "unavailable":
            raise PromotionConflictError(
                f"promotion destination '{file_entry['dest_rel']}' has unavailable baseline preimage"
            )
        current_preimage = _current_preimage(
            parent_workspace,
            file_entry["dest_rel"],
            workspace_files,
        )
        if current_preimage != baseline_preimage:
            raise PromotionConflictError(
                f"promotion destination '{file_entry['dest_rel']}' changed from baseline"
            )
        file_entry["baseline_preimage"] = baseline_preimage
        file_entry["current_preimage"] = current_preimage
        file_entry["source_sha256"] = candidate_files.sha256(file_entry["source_rel"])

    promotion_root = promotion_manifest_path.parent
    staging_root = promotion_root / "staging"
    backups_root = promotion_root / "backups"
    for directory in (staging_root, backups_root):
        relative = promotion_files.relative(directory)
        if promotion_files.exists(relative):
            promotion_files.remove_tree(relative)
        promotion_files.ensure_directory(relative)

    manifest = {
        "schema": "adjudicated_provider.promotion.v1",
        "status": "prepared",
        "selected_candidate_id": selected_candidate_id,
        "files": [_promotion_manifest_file_entry(file_entry) for file_entry in files],
        "promoted_paths": promoted_paths,
        "created_parent_dirs": _created_parent_dirs(files, workspace_files),
    }
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")

    try:
        _stage_manifest_sources(
            manifest,
            staging_root,
            candidate_files,
            promotion_files,
        )
        _validate_promotion_staging(
            expected_outputs,
            output_bundle,
            staging_root,
            promotion_files,
        )
        return _commit_promotion_manifest(
            manifest=manifest,
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            staging_root=staging_root,
            backups_root=backups_root,
            workspace_files=workspace_files,
            candidate_files=candidate_files,
            promotion_files=promotion_files,
        )
    except PromotionConflictError as exc:
        if promotion_manifest_path.exists():
            try:
                if manifest.get("status") not in {"rolling_back", "failed", "committed"}:
                    manifest["status"] = "failed"
                    manifest["failure_type"] = exc.failure_type
                    manifest["failure_message"] = str(exc)
                _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
            except Exception:
                pass
        raise
    except Exception:
        if promotion_manifest_path.exists():
            try:
                manifest["status"] = "failed"
                _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
            except Exception:
                pass
        raise

def _promotion_file_plan(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    artifacts: Mapping[str, Any],
    candidate_files: WorkspaceFiles,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    promoted_paths: dict[str, str] = {}
    if output_bundle:
        bundle_rel = _safe_relpath(Path(str(output_bundle.get("path", ""))))
        bundle_source = candidate_files.workspace / bundle_rel
        files.append({"role": "bundle", "artifact": "output_bundle", "source": bundle_source, "source_rel": bundle_rel, "dest_rel": bundle_rel})
        fields = output_bundle.get("fields", [])
        bundle_doc = json.loads(candidate_files.read(bundle_rel).decode("utf-8"))
        for field_spec in fields:
            if not isinstance(field_spec, dict):
                continue
            artifact_name = str(field_spec.get("name", "artifact"))
            if field_spec.get("type") == "relpath" and field_spec.get("must_exist_target"):
                found, relpath_value = _resolve_json_pointer(bundle_doc, str(field_spec.get("json_pointer", "")))
                if found and isinstance(relpath_value, str):
                    target_rel = _safe_relpath(Path(str(artifacts.get(artifact_name, relpath_value))))
                    target_source = candidate_files.workspace / target_rel
                    files.append({"role": "relpath_target", "artifact": artifact_name, "source": target_source, "source_rel": target_rel, "dest_rel": target_rel})
                    promoted_paths[f"{artifact_name}.target"] = target_rel
        return files, promoted_paths

    for spec in expected_outputs or []:
        if not isinstance(spec, dict):
            continue
        artifact_name = str(spec.get("name", "artifact"))
        value_rel = _safe_relpath(Path(str(spec.get("path", ""))))
        value_source = candidate_files.workspace / value_rel
        files.append({"role": "value_file", "artifact": artifact_name, "source": value_source, "source_rel": value_rel, "dest_rel": value_rel})
        promoted_paths[artifact_name] = value_rel
        if spec.get("type") == "relpath" and spec.get("must_exist_target"):
            raw_target_rel = candidate_files.read(value_rel).decode("utf-8").strip()
            target_rel = _safe_relpath(Path(str(artifacts.get(artifact_name, raw_target_rel))))
            target_source = candidate_files.workspace / target_rel
            files.append({"role": "relpath_target", "artifact": artifact_name, "source": target_source, "source_rel": target_rel, "dest_rel": target_rel})
            promoted_paths[f"{artifact_name}.target"] = target_rel
    for file_entry in files:
        try:
            candidate_files.stat(file_entry["source_rel"])
        except (OSError, ValueError) as exc:
            raise PromotionConflictError(
                f"promotion source '{file_entry['source']}': {exc}"
            ) from exc
    del parent_workspace
    return files, promoted_paths


def _reject_duplicate_destinations(
    files: Sequence[Mapping[str, Any]],
    candidate_files: WorkspaceFiles,
) -> None:
    seen: dict[str, Mapping[str, Any]] = {}
    for file_entry in files:
        dest = str(file_entry["dest_rel"])
        previous = seen.get(dest)
        if previous is None:
            seen[dest] = file_entry
            continue
        if (
            candidate_files.sha256(previous["source_rel"])
            != candidate_files.sha256(file_entry["source_rel"])
            or previous["role"] != file_entry["role"]
        ):
            raise PromotionConflictError(f"duplicate promotion destination '{dest}'")


def _baseline_preimage(manifest: BaselineManifest, relpath: str) -> dict[str, Any]:
    included = manifest.included_by_path().get(relpath)
    if included is not None:
        if included.entry_type != "file":
            return {"state": "unavailable"}
        return {
            "state": "file",
            "sha256": included.sha256,
            "mode": included.mode,
        }
    if _matching_exclusion(relpath, manifest.excluded_by_path()) is not None:
        return {"state": "unavailable"}
    return {"state": "absent"}


def _current_preimage(
    parent_workspace: Path,
    relpath: str,
    workspace_files: WorkspaceFiles | None = None,
) -> dict[str, Any]:
    owns_files = workspace_files is None
    files = workspace_files or WorkspaceFiles(parent_workspace)
    try:
        result_path = files.relative(Path(parent_workspace) / relpath)
        try:
            info = files.stat(result_path)
        except FileNotFoundError:
            return {"state": "absent"}
        if not stat.S_ISREG(info.st_mode):
            return {"state": "unavailable"}
        return {
            "state": "file",
            "sha256": files.sha256(result_path),
            "mode": info.st_mode & 0o777,
        }
    except (OSError, ValueError):
        return {"state": "unavailable"}
    finally:
        if owns_files:
            files.close()


def _state_preimage(workspace_files: WorkspaceFiles, relpath: str) -> dict[str, Any]:
    """Inspect one transaction-owned output snapshot beneath its pinned root."""
    return _owned_preimage(workspace_files, _safe_relpath(Path(relpath)))


def _owned_preimage(files: WorkspaceFiles, path: str | Path) -> dict[str, Any]:
    try:
        info = files.stat(path)
        if not stat.S_ISREG(info.st_mode):
            return {"state": "unavailable"}
        return {
            "state": "file",
            "sha256": files.sha256(path),
            "mode": info.st_mode & 0o777,
        }
    except FileNotFoundError:
        return {"state": "absent"}
    except (OSError, ValueError):
        return {"state": "unavailable"}


def _promotion_manifest_file_entry(file_entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "role": file_entry["role"],
        "artifact": file_entry["artifact"],
        "source": str(file_entry["source"]),
        "dest_rel": file_entry["dest_rel"],
        "source_sha256": file_entry["source_sha256"],
        "baseline_preimage": file_entry["baseline_preimage"],
        "current_preimage": file_entry["current_preimage"],
    }


def _load_promotion_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionConflictError(f"promotion manifest cannot be read: {exc}") from exc
    if not isinstance(document, dict):
        raise PromotionConflictError("promotion manifest must be a JSON object")
    return document


def derive_promotion_rollback_authority(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    baseline_manifest: BaselineManifest,
    selected_candidate_id: str | None,
    workspace_files: WorkspaceFiles | None = None,
    run_root: Path | None = None,
    run_workspace_files: WorkspaceFiles | None = None,
) -> dict[str, Any]:
    """Derive rollback authority from contracts, candidate bytes, and snapshot."""
    owns_parent_files = workspace_files is None
    parent_files = workspace_files or WorkspaceFiles(parent_workspace)
    candidate_files: WorkspaceFiles | None = None
    baseline_files: WorkspaceFiles | None = None
    owners = ExitStack()
    if owns_parent_files:
        owners.callback(parent_files.close)
    try:
        baseline_workspace = Path(baseline_manifest.baseline_workspace)
        if run_workspace_files is not None:
            if run_root is None:
                raise ValueError("run_root is required with run_workspace_files")
            baseline_relative = baseline_workspace.relative_to(Path(run_root))
            baseline_files = run_workspace_files.subroot(baseline_relative)
        else:
            try:
                baseline_files = parent_files.subroot(baseline_workspace)
            except ValueError:
                baseline_files = WorkspaceFiles(baseline_workspace)
        owners.callback(baseline_files.close)
        if run_workspace_files is not None:
            candidate_relative = Path(candidate_workspace).relative_to(Path(run_root))
            if not run_workspace_files.exists(candidate_relative):
                candidate_files = None
            else:
                candidate_files = run_workspace_files.subroot(candidate_relative)
                owners.callback(candidate_files.close)
        elif owns_parent_files and not Path(candidate_workspace).exists():
            candidate_files = None
        else:
            try:
                candidate_files = (
                    WorkspaceFiles(candidate_workspace)
                    if owns_parent_files
                    else parent_files.subroot(candidate_workspace)
                )
                owners.callback(candidate_files.close)
            except FileNotFoundError:
                candidate_files = None
        if candidate_files is None:
            raise FileNotFoundError("candidate workspace is unavailable")
        if output_bundle:
            artifacts = validate_output_bundle(
                output_bundle,
                workspace=candidate_workspace,
                workspace_files=candidate_files,
            )
        else:
            artifacts = validate_expected_outputs(
                expected_outputs or [],
                workspace=candidate_workspace,
                workspace_files=candidate_files,
            )
        files, promoted_paths = _promotion_file_plan(
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            candidate_workspace=candidate_workspace,
            parent_workspace=parent_workspace,
            artifacts=artifacts,
            candidate_files=candidate_files,
        )
        _reject_duplicate_destinations(files, candidate_files)
        for file_entry in files:
            dest_rel = str(file_entry["dest_rel"])
            baseline_preimage = _baseline_preimage(
                baseline_manifest,
                dest_rel,
            )
            if baseline_preimage.get("state") == "unavailable":
                raise PromotionConflictError(
                    f"promotion destination '{dest_rel}' has unavailable baseline preimage"
                )
            if _state_preimage(baseline_files, dest_rel) != baseline_preimage:
                raise PromotionConflictError(
                    f"promotion baseline snapshot does not match manifest for '{dest_rel}'"
                )
            file_entry["source_sha256"] = candidate_files.sha256(file_entry["source_rel"])
            file_entry["baseline_preimage"] = baseline_preimage
            file_entry["current_preimage"] = baseline_preimage
        return {
            "selected_candidate_id": selected_candidate_id,
            "files": [_promotion_manifest_file_entry(file_entry) for file_entry in files],
            "promoted_paths": promoted_paths,
        }
    except (OutputContractError, PromotionConflictError, OSError, TypeError, ValueError) as exc:
        raise PromotionConflictError(
            f"promotion rollback authority cannot be derived: {exc}",
            failure_type="promotion_rollback_conflict",
        ) from exc
    finally:
        owners.close()


def discard_partial_promotion_visit(
    *,
    parent_workspace: Path,
    promotion_manifest_path: Path,
    expected_rollback: Mapping[str, Any],
    workspace_files: WorkspaceFiles | None = None,
    run_root: Path | None = None,
    run_workspace_files: WorkspaceFiles | None = None,
) -> None:
    """Restore one partial promotion's preimages, then remove its visit root."""
    owns_files = workspace_files is None
    files = workspace_files or WorkspaceFiles(parent_workspace)
    promotion_root = Path(promotion_manifest_path).parent
    promotion_files: WorkspaceFiles | None = None
    promotion_parent_files: WorkspaceFiles | None = None
    owners = ExitStack()
    if owns_files:
        owners.callback(files.close)
    try:
        if run_workspace_files is not None:
            if run_root is None:
                raise ValueError("run_root is required with run_workspace_files")
            root_relative = Path(promotion_root).relative_to(Path(run_root))
            root_owner = run_workspace_files
        else:
            try:
                root_relative = files.relative(promotion_root)
                root_owner = files
            except ValueError:
                promotion_parent_files, promotion_parent = _open_nearest_existing_owner(
                    promotion_root.parent
                )
                owners.callback(promotion_parent_files.close)
                root_owner = promotion_parent_files
                root_relative = promotion_root.relative_to(promotion_parent)
        try:
            if not root_owner.exists(root_relative):
                return
            promotion_files = root_owner.subroot(root_relative)
            owners.callback(promotion_files.close)
        except (OSError, ValueError) as exc:
            raise PromotionConflictError(
                f"promotion visit root cannot be opened safely: {exc}",
                failure_type="promotion_rollback_conflict",
            ) from exc
        _discard_partial_promotion_visit(
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            expected_rollback=expected_rollback,
            workspace_files=files,
            promotion_files=promotion_files,
        )
        root_owner.remove_tree(root_relative)
    finally:
        owners.close()


def _discard_partial_promotion_visit(
    *,
    parent_workspace: Path,
    promotion_manifest_path: Path,
    expected_rollback: Mapping[str, Any],
    workspace_files: WorkspaceFiles,
    promotion_files: WorkspaceFiles,
) -> None:

    promotion_root = promotion_manifest_path.parent

    try:
        if promotion_root.is_symlink() or not promotion_root.is_dir():
            raise PromotionConflictError("promotion visit root is not a canonical directory")
        if (
            promotion_manifest_path.parent != promotion_root
            or promotion_manifest_path.name != "manifest.json"
            or promotion_manifest_path.is_symlink()
        ):
            raise PromotionConflictError("promotion manifest path is not canonical")

        manifest = _load_promotion_manifest(promotion_manifest_path)
        status = _validate_discard_promotion_manifest(
            manifest,
            parent_workspace=parent_workspace,
            promotion_root=promotion_root,
            promotion_files=promotion_files,
        )
        _require_expected_rollback_authority(
            manifest=manifest,
            expected_rollback=expected_rollback,
        )
        if status == "prepared":
            _verify_manifest_preimages(manifest, parent_workspace, workspace_files)
        else:
            _rollback_promoted_files(
                files=manifest["files"],
                parent_workspace=parent_workspace,
                backups_root=promotion_root / "backups",
                workspace_files=workspace_files,
                promotion_files=promotion_files,
            )
    except PromotionConflictError as exc:
        if exc.failure_type == "promotion_rollback_conflict":
            raise
        raise PromotionConflictError(
            str(exc),
            failure_type="promotion_rollback_conflict",
        ) from exc
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PromotionConflictError(
            f"promotion visit cannot be discarded: {exc}",
            failure_type="promotion_rollback_conflict",
        ) from exc



def _require_expected_rollback_authority(
    *,
    manifest: Mapping[str, Any],
    expected_rollback: Mapping[str, Any],
) -> None:
    if not isinstance(expected_rollback, Mapping):
        raise PromotionConflictError("expected promotion rollback authority is invalid")
    if "selected_candidate_id" not in manifest or "selected_candidate_id" not in expected_rollback:
        raise PromotionConflictError("promotion rollback candidate authority is missing")
    expected_candidate_id = expected_rollback.get("selected_candidate_id")
    if expected_candidate_id is not None and (
        not isinstance(expected_candidate_id, str) or not expected_candidate_id
    ):
        raise PromotionConflictError("expected promotion rollback candidate is invalid")
    if manifest.get("selected_candidate_id") != expected_candidate_id:
        raise PromotionConflictError(
            "promotion manifest selected candidate does not match rollback authority"
        )
    if _normalized_promoted_paths(
        manifest.get("promoted_paths")
    ) != _normalized_promoted_paths(expected_rollback.get("promoted_paths")):
        raise PromotionConflictError(
            "promotion manifest promoted paths do not match rollback authority"
        )
    if _normalized_rollback_files(manifest.get("files")) != _normalized_rollback_files(
        expected_rollback.get("files")
    ):
        raise PromotionConflictError(
            "promotion manifest files do not match rollback authority"
        )


def _normalized_promoted_paths(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise PromotionConflictError("promotion rollback promoted paths are invalid")
    normalized: dict[str, str] = {}
    for artifact, raw_path in value.items():
        if (
            not isinstance(artifact, str)
            or not artifact
            or not isinstance(raw_path, str)
            or _safe_relpath(raw_path) != raw_path
        ):
            raise PromotionConflictError("promotion rollback promoted paths are invalid")
        normalized[artifact] = raw_path
    return normalized


def _normalized_rollback_files(files: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        raise PromotionConflictError("promotion rollback files must be a sequence")
    normalized: list[tuple[str, ...]] = []
    for file_entry in files:
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError("promotion rollback contains an invalid file entry")
        role = file_entry.get("role")
        artifact = file_entry.get("artifact")
        source = file_entry.get("source")
        dest_rel = file_entry.get("dest_rel")
        source_sha256 = file_entry.get("source_sha256")
        if (
            not isinstance(role, str)
            or not role
            or not isinstance(artifact, str)
            or not artifact
            or not isinstance(source, str)
            or not source
            or not isinstance(dest_rel, str)
            or _safe_relpath(dest_rel) != dest_rel
            or not _is_sha256_digest(source_sha256)
        ):
            raise PromotionConflictError("promotion rollback contains an invalid file entry")
        baseline_preimage = file_entry.get("baseline_preimage")
        current_preimage = file_entry.get("current_preimage")
        _validate_baseline_preimage(baseline_preimage, dest_rel=dest_rel)
        _validate_baseline_preimage(current_preimage, dest_rel=dest_rel)
        normalized.append(
            (
                role,
                artifact,
                Path(source).as_posix(),
                dest_rel,
                str(source_sha256),
                _canonical_json(baseline_preimage),
                _canonical_json(current_preimage),
            )
        )
    return tuple(normalized)


def _validate_discard_promotion_manifest(
    manifest: Mapping[str, Any],
    *,
    parent_workspace: Path,
    promotion_root: Path,
    promotion_files: WorkspaceFiles,
) -> str:
    if manifest.get("schema") != "adjudicated_provider.promotion.v1":
        raise PromotionConflictError("promotion manifest has an unsupported schema")
    status = manifest.get("status")
    if status not in {"prepared", "committing", "rolling_back", "failed", "committed"}:
        raise PromotionConflictError(f"promotion manifest has unsupported status '{status}'")

    files = manifest.get("files")
    if not isinstance(files, list):
        raise PromotionConflictError("promotion manifest files must be a list")
    seen: dict[str, tuple[str, str]] = {}
    allowed_created_parent_dirs: set[str] = set()
    for file_entry in files:
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError("promotion manifest contains an invalid file entry")
        dest_rel = file_entry.get("dest_rel")
        if not isinstance(dest_rel, str) or _safe_relpath(dest_rel) != dest_rel:
            raise PromotionConflictError("promotion manifest contains an invalid destination")
        parent = Path(dest_rel).parent
        while parent != Path("."):
            allowed_created_parent_dirs.add(parent.as_posix())
            parent = parent.parent
        source_sha256 = file_entry.get("source_sha256")
        if not _is_sha256_digest(source_sha256):
            raise PromotionConflictError(
                f"promotion manifest contains an invalid source hash for '{dest_rel}'"
            )
        baseline_preimage = file_entry.get("baseline_preimage")
        _validate_baseline_preimage(baseline_preimage, dest_rel=dest_rel)
        fingerprint = (
            str(source_sha256),
            _canonical_json(baseline_preimage),
        )
        previous = seen.setdefault(dest_rel, fingerprint)
        if previous != fingerprint:
            raise PromotionConflictError(
                f"promotion manifest contains ambiguous duplicate destination '{dest_rel}'"
            )

    created_parent_dirs = manifest.get("created_parent_dirs")
    if not isinstance(created_parent_dirs, list):
        raise PromotionConflictError("promotion manifest created_parent_dirs must be a list")
    for rel in created_parent_dirs:
        if not isinstance(rel, str) or _safe_relpath(rel) != rel:
            raise PromotionConflictError(
                "promotion manifest contains an invalid created parent directory"
            )
        if rel not in allowed_created_parent_dirs:
            raise PromotionConflictError(
                "promotion manifest contains an unrelated created parent directory"
            )

    backups_root = promotion_files.relative(promotion_root / "backups")
    try:
        backup_info = promotion_files.stat(backups_root)
    except FileNotFoundError:
        backup_info = None
    if backup_info is not None and not stat.S_ISDIR(backup_info.st_mode):
        raise PromotionConflictError("promotion backup root is aliased")
    return str(status)


def _validate_baseline_preimage(preimage: Any, *, dest_rel: str) -> None:
    if not isinstance(preimage, Mapping):
        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has an invalid baseline preimage"
        )
    state = preimage.get("state")
    if state == "absent":
        return
    if state != "file":
        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has unavailable baseline preimage"
        )
    mode = preimage.get("mode")
    if (
        not _is_sha256_digest(preimage.get("sha256"))
        or not isinstance(mode, int)
        or isinstance(mode, bool)
        or mode < 0
        or mode > 0o777
    ):
        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has an invalid baseline preimage"
        )


def _is_sha256_digest(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _resume_promotion_manifest(
    *,
    manifest: dict[str, Any],
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    parent_workspace: Path,
    promotion_manifest_path: Path,
    workspace_files: WorkspaceFiles,
    candidate_files: WorkspaceFiles | None,
    promotion_files: WorkspaceFiles,
) -> PromotionResult:
    promotion_root = promotion_manifest_path.parent
    staging_root = promotion_root / "staging"
    backups_root = promotion_root / "backups"
    status = manifest.get("status")

    if status == "failed":
        raise PromotionConflictError(
            str(manifest.get("failure_message") or "promotion failed"),
            failure_type=str(manifest.get("failure_type") or "promotion_conflict"),
        )

    if status == "committed":
        try:
            _validate_promotion_parent(
                expected_outputs,
                output_bundle,
                parent_workspace,
                workspace_files,
            )
        except OutputContractError as exc:
            raise PromotionConflictError(str(exc), failure_type="promotion_validation_failed") from exc
        return PromotionResult(
            status="committed",
            promoted_paths=dict(manifest.get("promoted_paths") or {}),
            manifest_path=promotion_manifest_path,
        )

    if status == "rolling_back":
        _complete_promotion_rollback(
            manifest=manifest,
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            backups_root=backups_root,
            promotion_files=promotion_files,
            workspace_files=workspace_files,
            failure_type=str(manifest.get("failure_type") or "promotion_validation_failed"),
            failure_message=str(manifest.get("failure_message") or "promotion rollback resumed"),
        )

    if status == "prepared":
        _verify_manifest_preimages(manifest, parent_workspace, workspace_files)
        _stage_manifest_sources(
            manifest,
            staging_root,
            candidate_files,
            promotion_files,
        )
        _validate_promotion_staging(
            expected_outputs,
            output_bundle,
            staging_root,
            promotion_files,
        )
        return _commit_promotion_manifest(
            manifest=manifest,
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            staging_root=staging_root,
            backups_root=backups_root,
            workspace_files=workspace_files,
            candidate_files=candidate_files,
            promotion_files=promotion_files,
        )

    if status == "committing":
        return _commit_promotion_manifest(
            manifest=manifest,
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            staging_root=staging_root,
            backups_root=backups_root,
            workspace_files=workspace_files,
            candidate_files=candidate_files,
            promotion_files=promotion_files,
        )

    raise PromotionConflictError(f"promotion manifest has unsupported status '{status}'")


def _stage_manifest_sources(
    manifest: Mapping[str, Any],
    staging_root: Path,
    candidate_files: WorkspaceFiles | None,
    promotion_files: WorkspaceFiles,
) -> None:
    for file_entry in manifest.get("files", []):
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError("promotion manifest contains an invalid file entry")
        dest_rel = str(file_entry.get("dest_rel", ""))
        source_hash = str(file_entry.get("source_sha256", ""))
        staged = staging_root / _safe_relpath(dest_rel)
        staged_rel = promotion_files.relative(staged)
        if promotion_files.exists(staged_rel):
            if promotion_files.sha256(staged_rel) == source_hash:
                continue
            promotion_files.clear(staged_rel)
        if candidate_files is None:
            raise PromotionConflictError(
                f"promotion source '{file_entry.get('source', '')}' is missing"
            )
        source = Path(str(file_entry.get("source", "")))
        source_rel = candidate_files.relative(source)
        candidate_files.copy_to(source_rel, promotion_files, staged_rel)
        if promotion_files.sha256(staged_rel) != source_hash:
            raise PromotionConflictError(f"promotion source hash changed for '{dest_rel}'")


def _verify_manifest_preimages(
    manifest: Mapping[str, Any],
    parent_workspace: Path,
    workspace_files: WorkspaceFiles,
) -> None:
    for file_entry in manifest.get("files", []):
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError("promotion manifest contains an invalid file entry")
        dest_rel = str(file_entry.get("dest_rel", ""))
        baseline_preimage = dict(file_entry.get("baseline_preimage") or {})
        if baseline_preimage.get("state") == "unavailable":
            raise PromotionConflictError(f"promotion destination '{dest_rel}' has unavailable baseline preimage")
        current_preimage = _current_preimage(parent_workspace, dest_rel, workspace_files)
        if current_preimage != baseline_preimage:
            raise PromotionConflictError(f"promotion destination '{dest_rel}' changed from baseline")


def _commit_promotion_manifest(
    *,
    manifest: dict[str, Any],
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    parent_workspace: Path,
    promotion_manifest_path: Path,
    staging_root: Path,
    backups_root: Path,
    workspace_files: WorkspaceFiles,
    candidate_files: WorkspaceFiles | None,
    promotion_files: WorkspaceFiles,
) -> PromotionResult:
    manifest["status"] = "committing"
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
    try:
        for file_entry in manifest.get("files", []):
            if not isinstance(file_entry, Mapping):
                raise PromotionConflictError("promotion manifest contains an invalid file entry")
            dest_rel = str(file_entry.get("dest_rel", ""))
            source_sha256 = str(file_entry.get("source_sha256", ""))
            baseline_preimage = dict(file_entry.get("baseline_preimage") or {})
            if baseline_preimage.get("state") == "unavailable":
                raise PromotionConflictError(f"promotion destination '{dest_rel}' has unavailable baseline preimage")

            current_preimage = _current_preimage(parent_workspace, dest_rel, workspace_files)
            if _preimage_matches_hash(current_preimage, source_sha256):
                continue
            if current_preimage != baseline_preimage:
                raise PromotionConflictError(f"promotion destination '{dest_rel}' changed before commit")

            staged = staging_root / _safe_relpath(dest_rel)
            staged_rel = promotion_files.relative(staged)
            if not promotion_files.exists(staged_rel):
                _stage_manifest_sources(
                    {"files": [file_entry]},
                    staging_root,
                    candidate_files,
                    promotion_files,
                )
            if promotion_files.sha256(staged_rel) != source_sha256:
                raise PromotionConflictError(f"promotion staged source hash changed for '{dest_rel}'")

            if baseline_preimage.get("state") == "file":
                backup = backups_root / dest_rel
                backup_rel = promotion_files.relative(backup)
                if not promotion_files.exists(backup_rel):
                    workspace_files.copy_to(dest_rel, promotion_files, backup_rel)
            promotion_files.copy_to(staged_rel, workspace_files, dest_rel)
            promotion_files.clear(staged_rel)

        try:
            _validate_promotion_parent(
                expected_outputs,
                output_bundle,
                parent_workspace,
                workspace_files,
            )
        except OutputContractError as exc:
            manifest["status"] = "rolling_back"
            manifest["failure_type"] = "promotion_validation_failed"
            manifest["failure_message"] = str(exc)
            _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
            _complete_promotion_rollback(
                manifest=manifest,
                parent_workspace=parent_workspace,
                promotion_manifest_path=promotion_manifest_path,
                backups_root=backups_root,
                failure_type="promotion_validation_failed",
                failure_message=str(exc),
                promotion_files=promotion_files,
                workspace_files=workspace_files,
            )
    except PromotionConflictError as exc:
        if manifest.get("status") != "rolling_back":
            manifest["status"] = "failed"
            manifest["failure_type"] = exc.failure_type
            manifest["failure_message"] = str(exc)
            _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
        raise

    manifest["status"] = "committed"
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
    return PromotionResult(
        status="committed",
        promoted_paths=dict(manifest.get("promoted_paths") or {}),
        manifest_path=promotion_manifest_path,
    )


def _complete_promotion_rollback(
    *,
    manifest: dict[str, Any],
    parent_workspace: Path,
    promotion_manifest_path: Path,
    backups_root: Path,
    workspace_files: WorkspaceFiles,
    promotion_files: WorkspaceFiles,
    failure_type: str,
    failure_message: str,
) -> None:
    try:
        _rollback_promoted_files(
            files=manifest.get("files", []),
            parent_workspace=parent_workspace,
            backups_root=backups_root,
            workspace_files=workspace_files,
            promotion_files=promotion_files,
        )
        _cleanup_created_parent_dirs(
            manifest.get("created_parent_dirs", []), workspace_files
        )
    except PromotionConflictError as rollback_exc:
        manifest["status"] = "rolling_back"
        manifest["failure_type"] = rollback_exc.failure_type
        manifest["failure_message"] = str(rollback_exc)
        _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
        raise
    manifest["status"] = "failed"
    manifest["failure_type"] = failure_type
    manifest["failure_message"] = failure_message
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
    raise PromotionConflictError(failure_message, failure_type=failure_type)


def _validate_promotion_staging(
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    workspace: Path,
    promotion_files: WorkspaceFiles,
) -> None:
    staging_files = promotion_files.subroot(workspace)
    try:
        if output_bundle:
            validate_output_bundle(
                output_bundle,
                workspace=workspace,
                workspace_files=staging_files,
            )
        else:
            validate_expected_outputs(
                expected_outputs or [],
                workspace=workspace,
                workspace_files=staging_files,
            )
    except OutputContractError as exc:
        raise PromotionConflictError(str(exc), failure_type="promotion_validation_failed") from exc
    finally:
        staging_files.close()


def _validate_promotion_parent(
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    workspace: Path,
    workspace_files: WorkspaceFiles,
) -> None:
    if output_bundle:
        validate_output_bundle(
            output_bundle,
            workspace=workspace,
            workspace_files=workspace_files,
        )
    else:
        validate_expected_outputs(
            expected_outputs or [],
            workspace=workspace,
            workspace_files=workspace_files,
        )


def _created_parent_dirs(
    files: Sequence[Mapping[str, Any]], workspace_files: WorkspaceFiles
) -> list[str]:
    created: set[str] = set()
    for file_entry in files:
        missing: list[Path] = []
        current = Path(str(file_entry["dest_rel"])).parent
        while current != Path(".") and not workspace_files.exists(current):
            missing.append(current)
            current = current.parent
        for path in reversed(missing):
            created.add(path.as_posix())
    return sorted(created, key=lambda item: (len(Path(item).parts), item))


def _cleanup_created_parent_dirs(
    created_parent_dirs: Any, workspace_files: WorkspaceFiles
) -> None:
    if not isinstance(created_parent_dirs, Sequence) or isinstance(created_parent_dirs, (str, bytes)):
        return
    rel_dirs = [str(item) for item in created_parent_dirs if isinstance(item, str)]
    for rel in sorted(rel_dirs, key=lambda item: (len(Path(item).parts), item), reverse=True):
        try:
            workspace_files.rmdir(rel)
        except OSError:
            continue


def _rollback_promoted_files(
    *,
    files: Sequence[Mapping[str, Any]],
    parent_workspace: Path,
    backups_root: Path,
    workspace_files: WorkspaceFiles,
    promotion_files: WorkspaceFiles,
) -> None:
    actions: list[tuple[str, dict[str, Any], str, Path | None]] = []
    for file_entry in reversed(files):
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError(
                "promotion manifest contains an invalid file entry",
                failure_type="promotion_rollback_conflict",
            )
        dest_rel = _safe_relpath(str(file_entry["dest_rel"]))
        baseline_preimage = dict(file_entry["baseline_preimage"])
        source_sha256 = str(file_entry["source_sha256"])
        current_preimage = _current_preimage(parent_workspace, dest_rel, workspace_files)
        if baseline_preimage.get("state") == "file":
            if current_preimage == baseline_preimage:
                continue
            if _preimage_matches_hash(current_preimage, source_sha256):
                backup = backups_root / dest_rel
                if _owned_preimage(
                    promotion_files,
                    promotion_files.relative(backups_root / dest_rel),
                ) != baseline_preimage:
                    raise PromotionConflictError(
                        f"promotion rollback backup does not match baseline for '{dest_rel}'",
                        failure_type="promotion_rollback_conflict",
                    )
                actions.append((dest_rel, baseline_preimage, source_sha256, backup))
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        if baseline_preimage.get("state") == "absent":
            if current_preimage.get("state") == "absent":
                continue
            if _preimage_matches_hash(current_preimage, source_sha256):
                actions.append((dest_rel, baseline_preimage, source_sha256, None))
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has unavailable baseline preimage",
            failure_type="promotion_rollback_conflict",
        )

    for dest_rel, baseline_preimage, source_sha256, backup in actions:
        current_preimage = _current_preimage(parent_workspace, dest_rel, workspace_files)
        if current_preimage == baseline_preimage:
            continue
        if not _preimage_matches_hash(current_preimage, source_sha256):
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed during rollback",
                failure_type="promotion_rollback_conflict",
            )
        if backup is None:
            workspace_files.clear(dest_rel)
        else:
            if _owned_preimage(
                promotion_files,
                promotion_files.relative(backups_root / dest_rel),
            ) != baseline_preimage:
                raise PromotionConflictError(
                    f"promotion rollback backup changed for '{dest_rel}'",
                    failure_type="promotion_rollback_conflict",
                )
            backup_rel = promotion_files.relative(backup)
            promotion_files.copy_to(backup_rel, workspace_files, dest_rel)
        if _current_preimage(parent_workspace, dest_rel, workspace_files) != baseline_preimage:
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' was not restored",
                failure_type="promotion_rollback_conflict",
            )


def _preimage_matches_hash(preimage: Mapping[str, Any], sha256_value: str) -> bool:
    return preimage.get("state") == "file" and preimage.get("sha256") == sha256_value
