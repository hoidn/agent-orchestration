"""Private calibrated live-review execution and binding publication."""

from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ._evaluation_calibration_support import (
    _calibration_shape,
    _validate_reviewer_execution,
)
from ._evaluation_ingest import _verify_closed_package_tree
from ._evaluation_support import (
    EvaluationError,
    _canonical_root,
    _fail,
    _publish_new_payload,
    _relative_path,
    _sha256_bytes,
    _source_file,
)
from ._pilot_review_schema import _DIMENSIONS, _validate_live_schema
from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)


_CONFIG_KEYS = {
    "schema_version",
    "reviewer_execution",
    "calibration_lock_path",
    "live_output_schema_path",
    "live_output_schema_digest",
}


def _manifest(lock: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    apparatus = lock.get("apparatus")
    if not isinstance(apparatus, Mapping):
        _fail("live_reviewer_apparatus_invalid", "apparatus")
    rows = apparatus.get("asset_manifest")
    if not isinstance(rows, list):
        _fail("live_reviewer_apparatus_invalid", "asset manifest")
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("path"), str)
            or row["path"] in result
        ):
            _fail("live_reviewer_apparatus_invalid", "asset manifest row")
        result[row["path"]] = row
    return result


def _bound_bytes(
    root: Path,
    manifest: Mapping[str, Mapping[str, object]],
    relative_value: object,
    *,
    code: str,
) -> tuple[Path, bytes]:
    relative = _relative_path(relative_value)
    row = manifest.get(relative.as_posix())
    if row is None:
        _fail(code, "asset is not manifest-bound")
    try:
        path, data, _mode = _source_file(root, relative)
    except EvaluationError as exc:
        raise EvaluationError(code, str(exc)) from exc
    if row.get("sha256") != _sha256_bytes(data):
        _fail(code, "asset digest")
    return path, data


def _load_environment(
    path: Path,
    execution: Mapping[str, object],
) -> dict[str, str]:
    try:
        resolved = path.resolve(strict=True)
        identity = path.lstat()
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_environment_invalid", str(exc)) from exc
    environment = execution.get("environment")
    if (
        path.is_symlink()
        or resolved != path
        or not stat.S_ISREG(identity.st_mode)
        or not isinstance(value, dict)
        or canonical_json_bytes(value) != data
        or not isinstance(environment, Mapping)
        or set(value) != set(environment.get("allowed_keys", ()))
        or any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items())
        or canonical_sha256([[key, value[key]] for key in sorted(value)])
        != environment.get("identity")
    ):
        _fail("live_reviewer_environment_invalid", str(path))
    return value


def validate_live_reviewer_apparatus(
    *,
    lock: Mapping[str, object],
    control_root: Path,
    reviewer_environment_path: Path,
) -> dict[str, object]:
    """Validate the calibrated live-review apparatus before slot publication."""

    try:
        validate_record(dict(lock))
    except PilotContractError as exc:
        raise EvaluationError("live_reviewer_apparatus_invalid", str(exc)) from exc
    control = _canonical_root(control_root, must_exist=True)
    if control.as_posix() != lock["apparatus"]["control_root"]:  # type: ignore[index]
        _fail("live_reviewer_apparatus_invalid", "control root")
    manifest = _manifest(lock)
    review = lock["review"]
    assert isinstance(review, Mapping)
    config_path, config_bytes = _bound_bytes(
        control,
        manifest,
        review["reviewer_command"]["config_path"],  # type: ignore[index]
        code="live_reviewer_command_invalid",
    )
    try:
        config = json.loads(config_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_command_invalid", str(exc)) from exc
    if (
        not isinstance(config, Mapping)
        or set(config) != _CONFIG_KEYS
        or config.get("schema_version")
        != "lean-pilot-live-review-command.v1"
        or config_bytes
        not in {
            canonical_json_bytes(config),
            canonical_json_bytes(config) + b"\n",
        }
    ):
        _fail("live_reviewer_command_invalid", "config shape")
    calibration_path, calibration_bytes = _bound_bytes(
        control,
        manifest,
        config.get("calibration_lock_path"),
        code="live_reviewer_execution_invalid",
    )
    try:
        calibration = json.loads(calibration_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_execution_invalid", str(exc)) from exc
    execution = config.get("reviewer_execution")
    try:
        _calibration_shape(calibration)
    except EvaluationError as exc:
        raise EvaluationError(
            "live_reviewer_execution_invalid",
            str(exc),
        ) from exc
    if (
        not isinstance(calibration, Mapping)
        or calibration_bytes
        not in {
            canonical_json_bytes(calibration),
            canonical_json_bytes(calibration) + b"\n",
        }
        or execution != calibration.get("reviewer_execution")
        or calibration.get("reviewer_ids") != review.get("reviewer_ids")
        or execution is None
    ):
        _fail("live_reviewer_execution_invalid", "calibration binding")
    cli_entry = _validate_reviewer_execution(
        execution,
        code="live_reviewer_execution_invalid",
    )
    if not isinstance(execution, Mapping) or (
        execution.get("provider_family"),
        execution.get("model"),
        execution.get("reasoning_effort"),
        execution.get("tool_policy"),
    ) != ("codex-cli", "gpt-5.5", "high", "read-only-package"):
        _fail("live_reviewer_execution_invalid", "calibrated command")
    schema_path, schema_bytes = _bound_bytes(
        control,
        manifest,
        config.get("live_output_schema_path"),
        code="live_reviewer_schema_invalid",
    )
    if _sha256_bytes(schema_bytes) != config.get("live_output_schema_digest"):
        _fail("live_reviewer_schema_invalid", "schema digest")
    try:
        schema = json.loads(schema_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_schema_invalid", str(exc)) from exc
    _validate_live_schema(schema)
    rubric_path, rubric_bytes = _bound_bytes(
        control,
        manifest,
        review.get("rubric_path"),
        code="live_reviewer_rubric_invalid",
    )
    if _sha256_bytes(rubric_bytes) != review.get("rubric_digest"):
        _fail("live_reviewer_rubric_invalid", "rubric digest")
    _seal_path, seal_bytes = _bound_bytes(
        control,
        manifest,
        review.get("calibration_evidence_path"),
        code="live_reviewer_calibration_invalid",
    )
    if _sha256_bytes(seal_bytes) != review.get("calibration_evidence_digest"):
        _fail("live_reviewer_calibration_invalid", "seal digest")
    try:
        seal = json.loads(seal_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_calibration_invalid", str(exc)) from exc
    bindings = seal.get("review_bindings") if isinstance(seal, Mapping) else None
    session_ids = (
        [item.get("session_id") for item in bindings if isinstance(item, Mapping)]
        if isinstance(bindings, list)
        else []
    )
    reviewer_matrix = (
        {
            (item.get("reviewer_id"), item.get("package_id"))
            for item in bindings
            if isinstance(item, Mapping)
        }
        if isinstance(bindings, list)
        else set()
    )
    expected_matrix = {
        (reviewer, package)
        for reviewer in calibration["reviewer_ids"]
        for package in calibration["package_ids"]
    }
    if (
        not isinstance(seal, Mapping)
        or canonical_json_bytes(seal) != seal_bytes
        or seal.get("status") != "PASSED"
        or seal.get("calibration_id") != calibration.get("calibration_id")
        or seal.get("round") != calibration.get("round")
        or seal.get("revision") != calibration.get("revision")
        or seal.get("calibration_lock_digest") != canonical_sha256(calibration)
        or seal.get("rubric_digest") != review.get("rubric_digest")
        or not isinstance(seal.get("validation"), Mapping)
        or seal["validation"].get("result") != "PASSED"
        or len(session_ids) != 6
        or len(set(session_ids)) != 6
        or any(not isinstance(item, str) or not item for item in session_ids)
        or reviewer_matrix != expected_matrix
    ):
        _fail("live_reviewer_calibration_invalid", "passing seal")
    environment = _load_environment(reviewer_environment_path, execution)
    return {
        "control_root": control,
        "config_path": config_path,
        "schema_path": schema_path,
        "schema_bytes": schema_bytes,
        "schema": schema,
        "rubric_path": rubric_path,
        "rubric_bytes": rubric_bytes,
        "cli_entry": cli_entry,
        "execution": execution,
        "environment": environment,
        "reviewer_ids": tuple(review["reviewer_ids"]),
        "calibration_session_ids": frozenset(session_ids),
        "calibration_lock_path": calibration_path,
    }


def _package_contract(package_root: Path, block_id: str) -> dict[str, object]:
    package = _canonical_root(package_root, must_exist=True)
    try:
        _manifest_path, data, _manifest_mode = _source_file(
            package,
            PurePosixPath("manifest.json"),
        )
        manifest = json.loads(data)
    except (EvaluationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("live_reviewer_package_invalid", str(exc)) from exc
    if (
        not isinstance(manifest, dict)
        or canonical_json_bytes(manifest) != data
        or manifest.get("package_id") != block_id
        or not isinstance(manifest.get("candidate_labels"), list)
        or len(manifest["candidate_labels"]) != 3
        or len(set(manifest["candidate_labels"])) != 3
        or not isinstance(manifest.get("files"), list)
    ):
        _fail("live_reviewer_package_invalid", "manifest")
    package_files = ["manifest.json"]
    observed_paths: set[str] = set()
    for row in manifest["files"]:
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "mode",
            "size",
            "sha256",
        }:
            _fail("live_reviewer_package_invalid", "manifest row")
        relative = _relative_path(row["path"])
        path_text = relative.as_posix()
        if path_text in observed_paths or path_text == "manifest.json":
            _fail("live_reviewer_package_invalid", "manifest path")
        observed_paths.add(path_text)
        try:
            _path, payload, mode = _source_file(package, relative)
        except EvaluationError as exc:
            raise EvaluationError(
                "live_reviewer_package_invalid",
                str(exc),
            ) from exc
        if (
            row["mode"] != mode
            or row["size"] != len(payload)
            or row["sha256"] != _sha256_bytes(payload)
        ):
            _fail("live_reviewer_package_invalid", path_text)
        package_files.append(path_text)
    if manifest.get("task_path") not in observed_paths:
        _fail("live_reviewer_package_invalid", "task path")
    try:
        _verify_closed_package_tree(
            package,
            permitted_files=observed_paths,
        )
    except EvaluationError as exc:
        raise EvaluationError("live_reviewer_package_invalid", str(exc)) from exc
    return {
        "root": package,
        "manifest": manifest,
        "manifest_digest": _sha256_bytes(data),
        "package_files": tuple(package_files),
    }


def _prompt(
    *,
    package: Mapping[str, object],
    rubric_path: Path,
    reviewer_id: str,
) -> dict[str, object]:
    manifest = package["manifest"]
    assert isinstance(manifest, Mapping)
    return {
        "role": "blinded_quality_reviewer",
        "review_context": {
            "reviewer_id": reviewer_id,
            "package_id": manifest["package_id"],
        },
        "inspection_contract": {
            "instruction": "Inspect only the manifest-declared package files and the named rubric.",
            "package_files": list(package["package_files"]),
            "rubric_path": rubric_path.as_posix(),
        },
        "output_contract": {
            "candidate_labels": manifest["candidate_labels"],
            "candidate_count": 3,
            "dimensions": list(_DIMENSIONS),
            "pair_count": 3,
            "pair_rule": "all unordered candidate pairs exactly once",
            "sealed_treatment_guess_required": True,
        },
    }


def _command(
    apparatus: Mapping[str, object],
    *,
    last_message_path: Path,
) -> list[str]:
    execution = apparatus["execution"]
    assert isinstance(execution, Mapping)
    return [
        apparatus["cli_entry"].as_posix(),  # type: ignore[union-attr]
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--model",
        str(execution["model"]),
        "--config",
        f'model_reasoning_effort="{execution["reasoning_effort"]}"',
        "--output-schema",
        apparatus["schema_path"].as_posix(),  # type: ignore[union-attr]
        "--output-last-message",
        last_message_path.as_posix(),
        "-",
    ]


def _publish(root: Path, relative: str, value: bytes, *, code: str) -> None:
    try:
        _publish_new_payload(
            root=root,
            relative=_relative_path(relative),
            data=value,
        )
    except EvaluationError as exc:
        raise EvaluationError(code, str(exc)) from exc
