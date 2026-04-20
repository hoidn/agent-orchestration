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
    for file_entry in reversed(files):
        dest_rel = str(file_entry["dest_rel"])
        baseline_preimage = dict(file_entry["baseline_preimage"])
        source_sha256 = str(file_entry["source_sha256"])
        current_preimage = _current_preimage(parent_workspace, dest_rel)
        dest = parent_workspace / dest_rel

        if baseline_preimage.get("state") == "file":
            if _preimage_matches_hash(current_preimage, source_sha256):
                backup = backups_root / dest_rel
                if not backup.exists():
                    raise PromotionConflictError(
                        f"promotion rollback backup missing for '{dest_rel}'",
                        failure_type="promotion_rollback_conflict",
                    )
                _replace_file(backup, dest)
                continue
            if _same_file_preimage(current_preimage, baseline_preimage):
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        if baseline_preimage.get("state") == "absent":
            if _preimage_matches_hash(current_preimage, source_sha256):
                if dest.exists():
                    dest.unlink()
                continue
            if current_preimage.get("state") == "absent":
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has unavailable baseline preimage",
            failure_type="promotion_rollback_conflict",
        )


def _preimage_matches_hash(preimage: Mapping[str, Any], sha256_value: str) -> bool:
    return preimage.get("state") == "file" and preimage.get("sha256") == sha256_value


def _same_file_preimage(current: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    if current.get("state") != expected.get("state"):
        return False
    if current.get("state") != "file":
        return current.get("state") == expected.get("state")
    return current.get("sha256") == expected.get("sha256")
