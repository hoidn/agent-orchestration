"""Transactional selected-output promotion for adjudicated-provider steps."""

from __future__ import annotations

import json
import shutil
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
    _hash_file,
    _is_within,
    _matching_exclusion,
    _require_canonical_child,
    _replace_file,
    _resolve_json_pointer,
    _safe_relpath,
    _workspace_file,
    _canonical_json,
)

def promote_candidate_outputs(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    baseline_manifest: BaselineManifest,
    promotion_manifest_path: Path,
    selected_candidate_id: str | None = None,
) -> PromotionResult:
    candidate_workspace = candidate_workspace.resolve()
    parent_workspace = parent_workspace.resolve()

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
                failure_type="adjudication_resume_mismatch",
            )
        if manifest.get("status") in {"prepared", "committing", "rolling_back", "failed", "committed"}:
            return _resume_promotion_manifest(
                manifest=manifest,
                expected_outputs=expected_outputs,
                output_bundle=output_bundle,
                parent_workspace=parent_workspace,
                promotion_manifest_path=promotion_manifest_path,
            )

    try:
        if output_bundle:
            artifacts = validate_output_bundle(output_bundle, workspace=candidate_workspace)
        else:
            artifacts = validate_expected_outputs(expected_outputs or [], workspace=candidate_workspace)
    except OutputContractError as exc:
        raise PromotionConflictError(str(exc), failure_type="promotion_validation_failed") from exc

    files, promoted_paths = _promotion_file_plan(
        expected_outputs=expected_outputs,
        output_bundle=output_bundle,
        candidate_workspace=candidate_workspace,
        parent_workspace=parent_workspace,
        artifacts=artifacts,
    )
    _reject_duplicate_destinations(files)
    for file_entry in files:
        baseline_preimage = _baseline_preimage(baseline_manifest, file_entry["dest_rel"])
        if baseline_preimage.get("state") == "unavailable":
            raise PromotionConflictError(
                f"promotion destination '{file_entry['dest_rel']}' has unavailable baseline preimage"
            )
        current_preimage = _current_preimage(parent_workspace, file_entry["dest_rel"])
        if current_preimage != baseline_preimage:
            raise PromotionConflictError(
                f"promotion destination '{file_entry['dest_rel']}' changed from baseline"
            )
        file_entry["baseline_preimage"] = baseline_preimage
        file_entry["current_preimage"] = current_preimage
        file_entry["source_sha256"] = _hash_file(file_entry["source"])

    promotion_root = promotion_manifest_path.parent
    staging_root = promotion_root / "staging"
    backups_root = promotion_root / "backups"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    if backups_root.exists():
        shutil.rmtree(backups_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    backups_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "adjudicated_provider.promotion.v1",
        "status": "prepared",
        "selected_candidate_id": selected_candidate_id,
        "files": [_promotion_manifest_file_entry(file_entry) for file_entry in files],
        "promoted_paths": promoted_paths,
        "created_parent_dirs": _created_parent_dirs(parent_workspace, files),
    }
    promotion_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")

    try:
        _stage_manifest_sources(manifest, staging_root)
        _validate_promotion_staging(expected_outputs, output_bundle, staging_root)
        return _commit_promotion_manifest(
            manifest=manifest,
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            staging_root=staging_root,
            backups_root=backups_root,
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
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    promoted_paths: dict[str, str] = {}
    if output_bundle:
        bundle_rel = _safe_relpath(Path(str(output_bundle.get("path", ""))))
        bundle_source = _workspace_file(candidate_workspace, bundle_rel)
        files.append({"role": "bundle", "artifact": "output_bundle", "source": bundle_source, "dest_rel": bundle_rel})
        fields = output_bundle.get("fields", [])
        bundle_doc = json.loads(bundle_source.read_text(encoding="utf-8"))
        for field_spec in fields:
            if not isinstance(field_spec, dict):
                continue
            artifact_name = str(field_spec.get("name", "artifact"))
            if field_spec.get("type") == "relpath" and field_spec.get("must_exist_target"):
                found, relpath_value = _resolve_json_pointer(bundle_doc, str(field_spec.get("json_pointer", "")))
                if found and isinstance(relpath_value, str):
                    target_rel = _safe_relpath(Path(str(artifacts.get(artifact_name, relpath_value))))
                    target_source = _workspace_file(candidate_workspace, target_rel)
                    files.append({"role": "relpath_target", "artifact": artifact_name, "source": target_source, "dest_rel": target_rel})
                    promoted_paths[f"{artifact_name}.target"] = target_rel
        return files, promoted_paths

    for spec in expected_outputs or []:
        if not isinstance(spec, dict):
            continue
        artifact_name = str(spec.get("name", "artifact"))
        value_rel = _safe_relpath(Path(str(spec.get("path", ""))))
        value_source = _workspace_file(candidate_workspace, value_rel)
        files.append({"role": "value_file", "artifact": artifact_name, "source": value_source, "dest_rel": value_rel})
        promoted_paths[artifact_name] = value_rel
        if spec.get("type") == "relpath" and spec.get("must_exist_target"):
            raw_target_rel = value_source.read_text(encoding="utf-8").strip()
            target_rel = _safe_relpath(Path(str(artifacts.get(artifact_name, raw_target_rel))))
            target_source = _workspace_file(candidate_workspace, target_rel)
            files.append({"role": "relpath_target", "artifact": artifact_name, "source": target_source, "dest_rel": target_rel})
            promoted_paths[f"{artifact_name}.target"] = target_rel
    for file_entry in files:
        if not file_entry["source"].exists() or not file_entry["source"].is_file():
            raise PromotionConflictError(f"promotion source '{file_entry['source']}' is missing")
    del parent_workspace
    return files, promoted_paths


def _reject_duplicate_destinations(files: Sequence[Mapping[str, Any]]) -> None:
    seen: dict[str, Mapping[str, Any]] = {}
    for file_entry in files:
        dest = str(file_entry["dest_rel"])
        previous = seen.get(dest)
        if previous is None:
            seen[dest] = file_entry
            continue
        if _hash_file(previous["source"]) != _hash_file(file_entry["source"]) or previous["role"] != file_entry["role"]:
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


def _current_preimage(parent_workspace: Path, relpath: str) -> dict[str, Any]:
    try:
        path = _workspace_file(parent_workspace, relpath, must_exist=False)
    except (OSError, ValueError):
        return {"state": "unavailable"}
    if not path.exists():
        return {"state": "absent"}
    if not path.is_file():
        return {"state": "unavailable"}
    stat = path.stat()
    return {
        "state": "file",
        "sha256": _hash_file(path),
        "mode": stat.st_mode & 0o777,
    }


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
) -> dict[str, Any]:
    """Derive rollback authority from contracts, candidate bytes, and snapshot."""

    candidate_workspace = candidate_workspace.resolve()
    parent_workspace = parent_workspace.resolve()
    try:
        if output_bundle:
            artifacts = validate_output_bundle(
                output_bundle,
                workspace=candidate_workspace,
            )
        else:
            artifacts = validate_expected_outputs(
                expected_outputs or [],
                workspace=candidate_workspace,
            )
        files, promoted_paths = _promotion_file_plan(
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            candidate_workspace=candidate_workspace,
            parent_workspace=parent_workspace,
            artifacts=artifacts,
        )
        _reject_duplicate_destinations(files)
        baseline_workspace = Path(baseline_manifest.baseline_workspace)
        for file_entry in files:
            dest_rel = str(file_entry["dest_rel"])
            _require_canonical_child(
                parent_workspace / dest_rel,
                parent_workspace,
            )
            baseline_preimage = _baseline_preimage(
                baseline_manifest,
                dest_rel,
            )
            if baseline_preimage.get("state") == "unavailable":
                raise PromotionConflictError(
                    f"promotion destination '{dest_rel}' has unavailable baseline preimage"
                )
            _require_canonical_child(
                baseline_workspace / dest_rel,
                baseline_workspace,
            )
            if _current_preimage(baseline_workspace, dest_rel) != baseline_preimage:
                raise PromotionConflictError(
                    f"promotion baseline snapshot does not match manifest for '{dest_rel}'"
                )
            file_entry["source_sha256"] = _hash_file(file_entry["source"])
            file_entry["baseline_preimage"] = baseline_preimage
            file_entry["current_preimage"] = baseline_preimage
    except (OutputContractError, PromotionConflictError, OSError, TypeError, ValueError) as exc:
        raise PromotionConflictError(
            f"promotion rollback authority cannot be derived: {exc}",
            failure_type="promotion_rollback_conflict",
        ) from exc

    return {
        "selected_candidate_id": selected_candidate_id,
        "files": [_promotion_manifest_file_entry(file_entry) for file_entry in files],
        "promoted_paths": promoted_paths,
    }


def discard_partial_promotion_visit(
    *,
    parent_workspace: Path,
    promotion_manifest_path: Path,
    expected_rollback: Mapping[str, Any],
) -> None:
    """Restore one partial promotion's preimages, then remove its visit root."""

    promotion_root = promotion_manifest_path.parent
    if not promotion_root.exists() and not promotion_root.is_symlink():
        return

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
        )
        _require_expected_rollback_authority(
            manifest=manifest,
            expected_rollback=expected_rollback,
        )
        if status == "prepared":
            _verify_manifest_preimages(manifest, parent_workspace)
        else:
            _rollback_promoted_files(
                files=manifest["files"],
                parent_workspace=parent_workspace,
                backups_root=promotion_root / "backups",
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

    try:
        shutil.rmtree(promotion_root)
    except OSError as exc:
        raise PromotionConflictError(
            f"promotion visit cannot be removed: {exc}",
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
                Path(source).resolve().as_posix(),
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
        _require_canonical_child(
            parent_workspace.resolve() / dest_rel,
            parent_workspace.resolve(),
        )
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
        _require_canonical_child(
            parent_workspace.resolve() / rel,
            parent_workspace.resolve(),
        )

    backups_root = promotion_root / "backups"
    if backups_root.is_symlink():
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
            _validate_promotion_parent(expected_outputs, output_bundle, parent_workspace)
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
            failure_type=str(manifest.get("failure_type") or "promotion_validation_failed"),
            failure_message=str(manifest.get("failure_message") or "promotion rollback resumed"),
        )

    if status == "prepared":
        _verify_manifest_preimages(manifest, parent_workspace)
        _stage_manifest_sources(manifest, staging_root)
        _validate_promotion_staging(expected_outputs, output_bundle, staging_root)
        return _commit_promotion_manifest(
            manifest=manifest,
            expected_outputs=expected_outputs,
            output_bundle=output_bundle,
            parent_workspace=parent_workspace,
            promotion_manifest_path=promotion_manifest_path,
            staging_root=staging_root,
            backups_root=backups_root,
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
        )

    raise PromotionConflictError(f"promotion manifest has unsupported status '{status}'")


def _stage_manifest_sources(manifest: Mapping[str, Any], staging_root: Path) -> None:
    for file_entry in manifest.get("files", []):
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError("promotion manifest contains an invalid file entry")
        dest_rel = str(file_entry.get("dest_rel", ""))
        source_hash = str(file_entry.get("source_sha256", ""))
        staged = staging_root / _safe_relpath(dest_rel)
        if staged.exists():
            if _hash_file(staged) == source_hash:
                continue
            staged.unlink()
        source = Path(str(file_entry.get("source", "")))
        if not source.exists() or not source.is_file():
            raise PromotionConflictError(f"promotion source '{source}' is missing")
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staged)
        if _hash_file(staged) != source_hash:
            raise PromotionConflictError(f"promotion source hash changed for '{dest_rel}'")


def _verify_manifest_preimages(manifest: Mapping[str, Any], parent_workspace: Path) -> None:
    for file_entry in manifest.get("files", []):
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError("promotion manifest contains an invalid file entry")
        dest_rel = str(file_entry.get("dest_rel", ""))
        baseline_preimage = dict(file_entry.get("baseline_preimage") or {})
        if baseline_preimage.get("state") == "unavailable":
            raise PromotionConflictError(f"promotion destination '{dest_rel}' has unavailable baseline preimage")
        current_preimage = _current_preimage(parent_workspace, dest_rel)
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

            current_preimage = _current_preimage(parent_workspace, dest_rel)
            if _preimage_matches_hash(current_preimage, source_sha256):
                continue
            if current_preimage != baseline_preimage:
                raise PromotionConflictError(f"promotion destination '{dest_rel}' changed before commit")

            staged = staging_root / _safe_relpath(dest_rel)
            if not staged.exists() or not staged.is_file():
                _stage_manifest_sources({"files": [file_entry]}, staging_root)
            if _hash_file(staged) != source_sha256:
                raise PromotionConflictError(f"promotion staged source hash changed for '{dest_rel}'")

            dest = parent_workspace / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if baseline_preimage.get("state") == "file":
                backup = backups_root / dest_rel
                if not backup.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, backup)
            _replace_file(staged, dest)

        try:
            _validate_promotion_parent(expected_outputs, output_bundle, parent_workspace)
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
    failure_type: str,
    failure_message: str,
) -> None:
    try:
        _rollback_promoted_files(
            files=manifest.get("files", []),
            parent_workspace=parent_workspace,
            backups_root=backups_root,
        )
        _cleanup_created_parent_dirs(parent_workspace, manifest.get("created_parent_dirs", []))
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
) -> None:
    try:
        if output_bundle:
            validate_output_bundle(output_bundle, workspace=workspace)
        else:
            validate_expected_outputs(expected_outputs or [], workspace=workspace)
    except OutputContractError as exc:
        raise PromotionConflictError(str(exc), failure_type="promotion_validation_failed") from exc


def _validate_promotion_parent(
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    workspace: Path,
) -> None:
    if output_bundle:
        validate_output_bundle(output_bundle, workspace=workspace)
    else:
        validate_expected_outputs(expected_outputs or [], workspace=workspace)


def _created_parent_dirs(parent_workspace: Path, files: Sequence[Mapping[str, Any]]) -> list[str]:
    created: set[str] = set()
    parent_workspace = parent_workspace.resolve()
    for file_entry in files:
        dest_parent = (parent_workspace / str(file_entry["dest_rel"])).parent
        missing: list[Path] = []
        current = dest_parent
        while current != parent_workspace and _is_within(current, parent_workspace) and not current.exists():
            missing.append(current)
            current = current.parent
        for path in reversed(missing):
            created.add(path.relative_to(parent_workspace).as_posix())
    return sorted(created, key=lambda item: (len(Path(item).parts), item))


def _cleanup_created_parent_dirs(parent_workspace: Path, created_parent_dirs: Any) -> None:
    if not isinstance(created_parent_dirs, Sequence) or isinstance(created_parent_dirs, (str, bytes)):
        return
    rel_dirs = [str(item) for item in created_parent_dirs if isinstance(item, str)]
    for rel in sorted(rel_dirs, key=lambda item: (len(Path(item).parts), item), reverse=True):
        try:
            path = _workspace_file(parent_workspace, rel, must_exist=False)
        except (OSError, ValueError):
            continue
        try:
            path.rmdir()
        except OSError:
            continue


def _rollback_promoted_files(
    *,
    files: Sequence[Mapping[str, Any]],
    parent_workspace: Path,
    backups_root: Path,
) -> None:
    actions: list[tuple[Path, str, dict[str, Any], str, Path | None]] = []
    parent_root = parent_workspace.resolve()
    backups_root = backups_root.resolve()
    for file_entry in reversed(files):
        if not isinstance(file_entry, Mapping):
            raise PromotionConflictError(
                "promotion manifest contains an invalid file entry",
                failure_type="promotion_rollback_conflict",
            )
        dest_rel = _safe_relpath(str(file_entry["dest_rel"]))
        baseline_preimage = dict(file_entry["baseline_preimage"])
        source_sha256 = str(file_entry["source_sha256"])
        current_preimage = _current_preimage(parent_workspace, dest_rel)
        dest = _require_canonical_child(parent_root / dest_rel, parent_root)

        if baseline_preimage.get("state") == "file":
            if current_preimage == baseline_preimage:
                continue
            if _preimage_matches_hash(current_preimage, source_sha256):
                backup = _require_canonical_child(
                    backups_root / dest_rel,
                    backups_root,
                )
                if _current_preimage(backups_root, dest_rel) != baseline_preimage:
                    raise PromotionConflictError(
                        f"promotion rollback backup does not match baseline for '{dest_rel}'",
                        failure_type="promotion_rollback_conflict",
                    )
                actions.append(
                    (dest, dest_rel, baseline_preimage, source_sha256, backup)
                )
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        if baseline_preimage.get("state") == "absent":
            if current_preimage.get("state") == "absent":
                continue
            if _preimage_matches_hash(current_preimage, source_sha256):
                actions.append(
                    (dest, dest_rel, baseline_preimage, source_sha256, None)
                )
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has unavailable baseline preimage",
            failure_type="promotion_rollback_conflict",
        )

    for dest, dest_rel, baseline_preimage, source_sha256, backup in actions:
        current_preimage = _current_preimage(parent_workspace, dest_rel)
        if current_preimage == baseline_preimage:
            continue
        if not _preimage_matches_hash(current_preimage, source_sha256):
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed during rollback",
                failure_type="promotion_rollback_conflict",
            )
        if backup is None:
            dest.unlink()
        else:
            if _current_preimage(backups_root, dest_rel) != baseline_preimage:
                raise PromotionConflictError(
                    f"promotion rollback backup changed for '{dest_rel}'",
                    failure_type="promotion_rollback_conflict",
                )
            _replace_file(backup, dest)
        if _current_preimage(parent_workspace, dest_rel) != baseline_preimage:
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' was not restored",
                failure_type="promotion_rollback_conflict",
            )


def _preimage_matches_hash(preimage: Mapping[str, Any], sha256_value: str) -> bool:
    return preimage.get("state") == "file" and preimage.get("sha256") == sha256_value
