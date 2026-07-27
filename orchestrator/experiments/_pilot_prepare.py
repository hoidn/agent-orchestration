"""Private one-pilot apparatus preparation and lock derivation."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ._pilot_prepare_support import (
    PilotPreparationError,
    _archive,
    _bundle,
    _calibration,
    _configs,
    _directory,
    _fail,
    _fresh,
    _json,
    _obj,
    _regular,
    _sha,
    _sources,
)
from ._pilot_prepare_validation import _shape
from ._treatment_runtime import derive_treatment_runtime
from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)


def _derive_lock(
    value: dict[str, object],
    repo: Path,
    control: Path,
    evidence: Path,
    manifest_rows: list[dict[str, str]],
    treatment_runtime: Mapping[str, str],
) -> dict[str, Any]:
    manifest = {row["path"]: row for row in manifest_rows}
    apparatus = _obj(value["apparatus"], "apparatus")
    review = _obj(value["review"], "review")
    expected = _obj(value["expected_derived_digests"], "expected digests")
    expected_sources = _obj(
        expected["treatment_sources"], "expected treatment digests"
    )

    treatments = []
    for raw in value["treatments"]:  # type: ignore[union-attr]
        row = dict(_obj(raw, "treatment"))
        treatment_id = str(row["treatment_id"])
        source_paths = list(row["source_asset_paths"])
        source_digest = _bundle(source_paths, manifest)
        if expected_sources.get(treatment_id) != source_digest:
            _fail(f"derived digest mismatch: {treatment_id}")
        row.update(
            source_digest=source_digest,
            command_digest=manifest[str(row["command_config_path"])]["sha256"],
        )
        treatments.append(row)

    evaluator = _obj(review["evaluator"], "evaluator")
    reviewer = _obj(review["reviewer_command"], "reviewer command")
    evaluator_digest = _bundle(list(evaluator["asset_paths"]), manifest)
    reviewer_digest = _bundle(list(reviewer["asset_paths"]), manifest)
    if (
        expected["evaluator_bundle"] != evaluator_digest
        or expected["reviewer_command_bundle"] != reviewer_digest
    ):
        _fail("derived digest mismatch: bundle")

    archive = _obj(value["archive"], "archive")
    pilot = _obj(value["pilot"], "pilot")
    task_digest = manifest[str(apparatus["task_path"])]["sha256"]
    profile = canonical_sha256(
        {
            "profile_version": "lean-pilot-task-profile.v1",
            "task_id": pilot["task_id"],
            "source_path": archive["task_source_path"],
            "brief_digest": task_digest,
            "archive_digest": archive["archive_digest"],
            "selected_final_files": review["selected_final_files"],
            "permitted_check_evidence_names": review[
                "permitted_check_evidence_names"
            ],
            "visible_check": apparatus["visible_check"],
            "product_projection_exclusions": apparatus[
                "product_projection_exclusions"
            ],
            "evaluator_bundle_digest": evaluator_digest,
        }
    )
    if expected["task_profile"] != profile:
        _fail("derived digest mismatch: task profile")

    lock: dict[str, Any] = {
        "record_kind": "pilot_lock.v1",
        "pilot_id": pilot["pilot_id"],
        "task": {
            "task_id": pilot["task_id"],
            "source_path": archive["task_source_path"],
            "profile_digest": profile,
            "brief_digest": task_digest,
        },
        "archive": {
            key: archive[key]
            for key in (
                "repository_identity",
                "revision_identity",
                "source_subtree_path",
                "source_tree_identity",
                "archive_digest",
            )
        }
        | {"repository_root": repo.as_posix()},
        "provider_policy": value["provider_policy"],
        "review": {
            "reviewer_ids": review["reviewer_ids"],
            "disagreement_policy": review["disagreement_policy"],
            "selected_final_files": review["selected_final_files"],
            "permitted_check_evidence_names": review[
                "permitted_check_evidence_names"
            ],
            "rubric_path": review["rubric_path"],
            "rubric_digest": manifest[str(review["rubric_path"])]["sha256"],
            "calibration_evidence_path": review["calibration_evidence_path"],
            "calibration_evidence_digest": manifest[
                str(review["calibration_evidence_path"])
            ]["sha256"],
            "evaluator": dict(evaluator) | {"bundle_digest": evaluator_digest},
            "reviewer_command": dict(reviewer)
            | {"bundle_digest": reviewer_digest},
        },
        "apparatus": dict(apparatus)
        | {
            "control_root": control.as_posix(),
            "asset_manifest": manifest_rows,
            "treatment_runtime": dict(treatment_runtime),
        },
        "randomization_seed": pilot["randomization_seed"],
        "evidence_root": evidence.as_posix(),
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "smoke_id": pilot["smoke_id"],
        "live_attempt_ids": pilot["live_attempt_ids"],
        "claim_level": "exploratory_controlled_task",
        "treatments": treatments,
    }
    try:
        validate_record(lock)
    except PilotContractError as exc:
        raise PilotPreparationError(
            f"derived pilot lock is invalid: {exc}"
        ) from exc
    return lock


def _materialize(
    root: Path,
    manifest: Sequence[dict[str, str]],
    content: Mapping[str, bytes],
) -> None:
    try:
        root.mkdir(mode=0o755)
        for row in manifest:
            path = root.joinpath(*PurePosixPath(row["path"]).parts)
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(content[row["path"]])
            path.chmod(0o644)
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if actual != {row["path"] for row in manifest}:
            _fail("materialized tree has missing or extra assets")
        for row in manifest:
            if (
                _sha(_regular(root / row["path"], "materialized asset"))
                != row["sha256"]
            ):
                _fail(f"materialized asset digest mismatch: {row['path']}")
    except OSError as exc:
        raise PilotPreparationError(
            "cannot materialize exclusive control tree"
        ) from exc


def _publish_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise PilotPreparationError(
            f"lock output already exists: {path}"
        ) from exc
    except OSError as exc:
        raise PilotPreparationError(
            f"cannot publish pilot lock: {path}"
        ) from exc


def prepare_pilot(
    *,
    source_map_path: Path,
    repository_root: Path,
    apparatus_revision: str,
    control_root: Path,
    evidence_root: Path,
    calibration_seal_path: Path,
    lock_output_path: Path,
) -> dict[str, Any]:
    """Materialize and freeze the prospective pilot from explicit inputs."""

    value = _json(_regular(source_map_path, "source map"), "source map")
    _shape(value)
    repo = _directory(repository_root, "repository root")
    treatment_runtime = derive_treatment_runtime(repo, apparatus_revision)
    revision = treatment_runtime["revision_identity"][7:]
    control = _fresh(control_root, "control root")
    evidence = _fresh(evidence_root, "evidence root")
    output = _fresh(lock_output_path, "lock output")
    if (
        control == evidence
        or control.is_relative_to(evidence)
        or evidence.is_relative_to(control)
    ):
        _fail("control and evidence roots must be disjoint")
    if control.is_relative_to(repo) or evidence.is_relative_to(repo):
        _fail("control and evidence roots must be external")

    manifest, content = _sources(
        value, repo, revision, calibration_seal_path
    )
    apparatus = _obj(value["apparatus"], "apparatus")
    _archive(value, repo, content[str(apparatus["task_path"])])
    _configs(value, content)
    _calibration(value, content)
    lock = _derive_lock(
        value,
        repo,
        control,
        evidence,
        manifest,
        treatment_runtime,
    )

    _materialize(control, manifest, content)
    try:
        evidence.mkdir(mode=0o755)
    except OSError as exc:
        raise PilotPreparationError(
            "cannot create fresh evidence root"
        ) from exc
    _publish_exclusive(output, canonical_json_bytes(lock))
    return lock
