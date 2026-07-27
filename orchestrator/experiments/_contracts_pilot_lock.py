"""Cross-field semantics for the closed lean-pilot lock."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _bundle_digest(
    *,
    paths: list[str],
    manifest: dict[str, dict[str, str]],
    canonical_sha256: Callable[[object], str],
) -> str:
    return canonical_sha256(
        [manifest[path] for path in sorted(paths, key=lambda item: item.encode())]
    )


def _require_manifest_paths(
    *,
    paths: list[str],
    manifest: dict[str, dict[str, str]],
    label: str,
    error: type[ValueError],
) -> None:
    for path in paths:
        if path not in manifest:
            raise error(f"missing_apparatus_asset:{label}:{path}")


def validate_pilot_lock(
    record: dict[str, Any],
    *,
    canonical_sha256: Callable[[object], str],
    error: type[ValueError],
) -> None:
    """Validate relationships that JSON Schema cannot express."""

    if record["smoke_id"] in record["live_attempt_ids"]:
        raise error("$.smoke_id: must not collide with a live attempt ID")

    apparatus = record["apparatus"]
    treatment_runtime = apparatus.get("treatment_runtime")
    if treatment_runtime is not None:
        archive = record["archive"]
        if treatment_runtime["import_root"] != archive["repository_root"]:
            raise error("treatment_runtime_import_root_mismatch")

    manifest: dict[str, dict[str, str]] = {}
    for index, asset in enumerate(apparatus["asset_manifest"]):
        path = asset["path"]
        if path in manifest:
            raise error(
                f"duplicate_asset_manifest_path:{path}:"
                f"$.apparatus.asset_manifest[{index}].path"
            )
        manifest[path] = asset

    role_names = (
        "task_path",
        "provider_config_path",
        "prompt_config_path",
        "command_config_path",
    )
    for role in role_names:
        path = apparatus[role]
        if path not in manifest:
            raise error(f"missing_apparatus_asset:{role}:{path}")

    task_path = apparatus["task_path"]
    if manifest[task_path]["sha256"] != record["task"]["brief_digest"]:
        raise error(f"task_brief_digest_mismatch:{task_path}")

    environment = apparatus["environment"]
    allowed_keys = set(environment["allowed_keys"])
    credential_keys = set(environment["credential_keys"])
    for controller_key in ("HOME", "TMPDIR"):
        if controller_key not in allowed_keys:
            raise error(
                f"missing_controller_environment_key:{controller_key}"
            )
        if controller_key in credential_keys:
            raise error(
                "controller_environment_key_cannot_be_credential:"
                f"{controller_key}"
            )
    for credential_key in sorted(credential_keys - allowed_keys):
        raise error(f"credential_key_not_allowed:{credential_key}")
    if treatment_runtime is not None:
        for runtime_key in ("PYTHONDONTWRITEBYTECODE", "PYTHONPATH"):
            if runtime_key not in allowed_keys:
                raise error(
                    f"missing_treatment_runtime_environment_key:{runtime_key}"
                )
            if runtime_key in credential_keys:
                raise error(
                    "treatment_runtime_environment_key_cannot_be_credential:"
                    f"{runtime_key}"
                )

    treatment_asset_paths = apparatus["treatment_asset_paths"]
    _require_manifest_paths(
        paths=treatment_asset_paths,
        manifest=manifest,
        label="treatment_asset_paths",
        error=error,
    )
    treatment_asset_set = set(treatment_asset_paths)
    for role in role_names:
        if apparatus[role] not in treatment_asset_set:
            raise error(f"treatment_asset_missing:{role}:{apparatus[role]}")

    review = record["review"]
    controller_paths = {
        review["rubric_path"],
        review["calibration_evidence_path"],
        *review["evaluator"]["asset_paths"],
        *review["reviewer_command"]["asset_paths"],
    }
    classified_paths = treatment_asset_set | controller_paths
    orphan_paths = set(manifest) - classified_paths
    unmanifested_paths = classified_paths - set(manifest)
    if orphan_paths:
        raise error("orphan_apparatus_asset:" + ",".join(sorted(orphan_paths)))
    if unmanifested_paths:
        raise error(
            "missing_classified_apparatus_asset:"
            + ",".join(sorted(unmanifested_paths))
        )
    overlap = treatment_asset_set.intersection(controller_paths)
    if overlap:
        raise error(
            "controller_asset_staged:" + ",".join(sorted(overlap))
        )

    treatment_command_paths: set[str] = set()
    for treatment in record["treatments"]:
        treatment_id = treatment["treatment_id"]
        command_path = treatment["command_config_path"]
        if command_path in treatment_command_paths:
            raise error(
                f"duplicate_treatment_command_config_path:{command_path}"
            )
        treatment_command_paths.add(command_path)
        if command_path not in manifest:
            raise error(
                "missing_treatment_command_config_asset:"
                f"{treatment_id}:{command_path}"
            )
        if manifest[command_path]["sha256"] != treatment["command_digest"]:
            raise error(
                "treatment_command_digest_mismatch:"
                f"{treatment_id}:{command_path}"
            )
        source_paths = treatment["source_asset_paths"]
        _require_manifest_paths(
            paths=source_paths,
            manifest=manifest,
            label=f"{treatment_id}.source_asset_paths",
            error=error,
        )
        if command_path not in source_paths:
            raise error(
                f"treatment_command_missing_from_source:{treatment_id}"
            )
        if not set(source_paths) <= treatment_asset_set:
            raise error(f"treatment_source_not_staged:{treatment_id}")
        expected_source_digest = _bundle_digest(
            paths=source_paths,
            manifest=manifest,
            canonical_sha256=canonical_sha256,
        )
        if treatment["source_digest"] != expected_source_digest:
            raise error(f"source_digest_mismatch:{treatment_id}")

    for label, path, digest in (
        ("rubric", review["rubric_path"], review["rubric_digest"]),
        (
            "calibration_evidence",
            review["calibration_evidence_path"],
            review["calibration_evidence_digest"],
        ),
    ):
        if path not in manifest:
            raise error(f"missing_apparatus_asset:{label}:{path}")
        if manifest[path]["sha256"] != digest:
            raise error(f"{label}_digest_mismatch:{path}")

    for label in ("evaluator", "reviewer_command"):
        bundle = review[label]
        paths = bundle["asset_paths"]
        _require_manifest_paths(
            paths=paths,
            manifest=manifest,
            label=f"review.{label}.asset_paths",
            error=error,
        )
        if bundle["config_path"] not in paths:
            raise error(f"{label}_config_missing_from_bundle")
        expected = _bundle_digest(
            paths=paths,
            manifest=manifest,
            canonical_sha256=canonical_sha256,
        )
        if bundle["bundle_digest"] != expected:
            raise error(f"{label}_bundle_digest_mismatch")

    expected_profile = canonical_sha256(
        {
            "profile_version": "lean-pilot-task-profile.v1",
            "task_id": record["task"]["task_id"],
            "source_path": record["task"]["source_path"],
            "brief_digest": record["task"]["brief_digest"],
            "archive_digest": record["archive"]["archive_digest"],
            "selected_final_files": review["selected_final_files"],
            "permitted_check_evidence_names": review[
                "permitted_check_evidence_names"
            ],
            "visible_check": apparatus["visible_check"],
            "product_projection_exclusions": apparatus[
                "product_projection_exclusions"
            ],
            "evaluator_bundle_digest": review["evaluator"]["bundle_digest"],
        }
    )
    if record["task"]["profile_digest"] != expected_profile:
        raise error("task_profile_digest_mismatch")
