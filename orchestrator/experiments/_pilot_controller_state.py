"""Immutable package-preparation state for the bounded pilot controller."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping
from pathlib import Path

from ._evaluation_ingest import _verify_closed_package_tree
from ._evaluation_support import EvaluationError, _relative_path, _source_file
from .contracts import canonical_json_bytes, canonical_sha256


class PilotControllerStateError(ValueError):
    """A committed valid attempt cannot safely continue under this lock."""


def _fail(code: str) -> None:
    raise PilotControllerStateError(code)


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _canonical_file(path: Path, *, code: str) -> bytes:
    try:
        identity = path.lstat()
        resolved = path.resolve(strict=True)
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise PilotControllerStateError(code) from exc
    if (
        path.is_symlink()
        or resolved != path
        or not stat.S_ISREG(identity.st_mode)
    ):
        _fail(code)
    return data


def _canonical_object(path: Path, *, code: str) -> dict[str, object]:
    data = _canonical_file(path, code=code)
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotControllerStateError(code) from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        _fail(code)
    return value


def _publish(path: Path, value: Mapping[str, object], *, code: str) -> None:
    try:
        parent = path.parent.resolve(strict=True)
        parent_identity = path.parent.lstat()
    except OSError as exc:
        raise PilotControllerStateError(code) from exc
    if (
        parent != path.parent
        or path.parent.is_symlink()
        or not stat.S_ISDIR(parent_identity.st_mode)
    ):
        _fail(code)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(dict(value)))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise PilotControllerStateError(code) from exc


def _binding(path: Path, *, code: str) -> dict[str, object]:
    data = _canonical_file(path, code=code)
    return {
        "path": path.as_posix(),
        "size": len(data),
        "sha256": _sha256_bytes(data),
    }


def _verified_package_binding(
    package: Path,
    *,
    block_id: str,
) -> dict[str, object]:
    code = "package_preparation_completion_invalid"
    try:
        identity = package.lstat()
        resolved = package.resolve(strict=True)
    except OSError as exc:
        raise PilotControllerStateError(code) from exc
    if (
        package.is_symlink()
        or resolved != package
        or not stat.S_ISDIR(identity.st_mode)
    ):
        _fail(code)

    manifest_path = package / "manifest.json"
    data = _canonical_file(manifest_path, code=code)
    try:
        manifest = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotControllerStateError(code) from exc
    if (
        not isinstance(manifest, dict)
        or canonical_json_bytes(manifest) != data
        or set(manifest)
        != {"package_id", "task_path", "candidate_labels", "files"}
        or manifest.get("package_id") != block_id
    ):
        _fail(code)
    labels = manifest.get("candidate_labels")
    rows = manifest.get("files")
    if (
        not isinstance(labels, list)
        or len(labels) != 3
        or len(set(labels)) != 3
        or any(not isinstance(label, str) or not label for label in labels)
        or not isinstance(rows, list)
    ):
        _fail(code)

    observed_paths: set[str] = set()
    try:
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {
                "path",
                "mode",
                "size",
                "sha256",
            }:
                _fail(code)
            relative = _relative_path(row.get("path"))
            path_text = relative.as_posix()
            mode_value = row.get("mode")
            size_value = row.get("size")
            digest_value = row.get("sha256")
            if (
                path_text in observed_paths
                or path_text == "manifest.json"
                or isinstance(mode_value, bool)
                or not isinstance(mode_value, int)
                or mode_value < 0
                or isinstance(size_value, bool)
                or not isinstance(size_value, int)
                or size_value < 0
                or not isinstance(digest_value, str)
            ):
                _fail(code)
            observed_paths.add(path_text)
            _path, payload, mode = _source_file(package, relative)
            if (
                mode_value != mode
                or size_value != len(payload)
                or digest_value != _sha256_bytes(payload)
            ):
                _fail(code)
        task_path = _relative_path(manifest.get("task_path")).as_posix()
        if task_path not in observed_paths:
            _fail(code)
        _verify_closed_package_tree(
            package,
            permitted_files=observed_paths,
        )
    except EvaluationError as exc:
        raise PilotControllerStateError(code) from exc
    return {
        "path": manifest_path.as_posix(),
        "size": len(data),
        "sha256": _sha256_bytes(data),
    }


def _expected_executions(
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
) -> dict[str, str]:
    treatments = lock.get("treatments")
    executions = attempt.get("treatment_executions")
    if not isinstance(treatments, list) or not isinstance(executions, list):
        _fail("package_preparation_lineage_invalid")
    expected_roles = {
        row.get("treatment_id")
        for row in treatments
        if isinstance(row, Mapping)
    }
    by_role: dict[str, str] = {}
    for row in executions:
        if not isinstance(row, Mapping):
            _fail("package_preparation_lineage_invalid")
        role = row.get("treatment_id")
        label = row.get("opaque_arm_label")
        if (
            not isinstance(role, str)
            or not isinstance(label, str)
            or role in by_role
        ):
            _fail("package_preparation_lineage_invalid")
        by_role[role] = label
    if set(by_role) != expected_roles:
        _fail("package_preparation_lineage_invalid")
    return by_role


def _intent(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
) -> dict[str, object]:
    block_id = attempt.get("block_id")
    if not isinstance(block_id, str) or not block_id:
        _fail("package_preparation_lineage_invalid")
    return {
        "schema_version": "lean-pilot-package-preparation-intent.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_digest": canonical_sha256(attempt),
        "block_id": block_id,
        "work_root": work_root.as_posix(),
        "evaluation_root": evaluation_root.as_posix(),
        "package_root": package_root.as_posix(),
    }


def _completion(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    intent: Mapping[str, object],
    result: Mapping[str, object],
    package_root: Path,
    evidence_root: Path,
) -> dict[str, object]:
    block_id = attempt["block_id"]
    assert isinstance(block_id, str)
    expected_package = package_root / block_id
    actual_package = result.get("package_root")
    label_map = result.get("label_map_path")
    if (
        result.get("package_id") != block_id
        or not isinstance(actual_package, Path)
        or actual_package != expected_package
        or not isinstance(label_map, Path)
        or label_map != evidence_root / "label-maps" / f"{block_id}.json"
    ):
        _fail("package_preparation_completion_invalid")
    manifest_binding = _verified_package_binding(
        actual_package,
        block_id=block_id,
    )
    label_binding = _binding(
        label_map,
        code="package_preparation_completion_invalid",
    )
    if (
        result.get("package_manifest_digest")
        != manifest_binding["sha256"]
        or result.get("label_map_digest") != label_binding["sha256"]
    ):
        _fail("package_preparation_completion_invalid")

    observed = result.get("evaluator_evidence")
    if not isinstance(observed, Mapping):
        _fail("package_preparation_completion_invalid")
    rows = []
    for role, label in sorted(_expected_executions(lock, attempt).items()):
        value = observed.get(role)
        if not isinstance(value, Mapping):
            _fail("package_preparation_completion_invalid")
        path = value.get("path")
        expected_path = (
            evidence_root / block_id / label / "hidden-evaluator.json"
        )
        if not isinstance(path, Path) or path != expected_path:
            _fail("package_preparation_completion_invalid")
        binding = _binding(
            path,
            code="package_preparation_completion_invalid",
        )
        verdict = value.get("verdict")
        if (
            value.get("digest") != binding["sha256"]
            or verdict not in {"PASS", "FAIL"}
        ):
            _fail("package_preparation_completion_invalid")
        rows.append(
            {
                "treatment_id": role,
                "opaque_arm_label": label,
                "verdict": verdict,
                "evidence": binding,
            }
        )
    if set(observed) != {row["treatment_id"] for row in rows}:
        _fail("package_preparation_completion_invalid")
    return {
        "schema_version": "lean-pilot-package-preparation-completion.v1",
        "intent_digest": canonical_sha256(intent),
        "package_id": block_id,
        "package_root": actual_package.as_posix(),
        "package_manifest": manifest_binding,
        "label_map": label_binding,
        "evaluator_evidence": rows,
    }


def _load_completion(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    intent: Mapping[str, object],
    completion_path: Path,
    package_root: Path,
    evidence_root: Path,
) -> dict[str, object]:
    value = _canonical_object(
        completion_path,
        code="package_preparation_completion_invalid",
    )
    expected_keys = {
        "schema_version",
        "intent_digest",
        "package_id",
        "package_root",
        "package_manifest",
        "label_map",
        "evaluator_evidence",
    }
    block_id = attempt["block_id"]
    if (
        set(value) != expected_keys
        or value.get("schema_version")
        != "lean-pilot-package-preparation-completion.v1"
        or value.get("intent_digest") != canonical_sha256(intent)
        or value.get("package_id") != block_id
        or value.get("package_root")
        != (package_root / str(block_id)).as_posix()
    ):
        _fail("package_preparation_completion_invalid")

    package_binding = _verified_package_binding(
        Path(str(value["package_root"])),
        block_id=str(block_id),
    )
    label_binding = _binding(
        evidence_root / "label-maps" / f"{block_id}.json",
        code="package_preparation_completion_invalid",
    )
    if (
        value.get("package_manifest") != package_binding
        or value.get("label_map") != label_binding
    ):
        _fail("package_preparation_completion_invalid")
    rows = value.get("evaluator_evidence")
    expected = _expected_executions(lock, attempt)
    if not isinstance(rows, list) or len(rows) != len(expected):
        _fail("package_preparation_completion_invalid")
    evaluator: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "treatment_id",
            "opaque_arm_label",
            "verdict",
            "evidence",
        }:
            _fail("package_preparation_completion_invalid")
        role = row["treatment_id"]
        label = row["opaque_arm_label"]
        if (
            not isinstance(role, str)
            or expected.get(role) != label
            or role in evaluator
            or row["verdict"] not in {"PASS", "FAIL"}
        ):
            _fail("package_preparation_completion_invalid")
        path = evidence_root / str(block_id) / str(label) / "hidden-evaluator.json"
        binding = _binding(
            path,
            code="package_preparation_completion_invalid",
        )
        if row["evidence"] != binding:
            _fail("package_preparation_completion_invalid")
        evaluator[role] = {
            "path": path,
            "digest": binding["sha256"],
            "verdict": row["verdict"],
        }
    if set(evaluator) != set(expected):
        _fail("package_preparation_completion_invalid")
    return {
        "package_id": block_id,
        "package_root": Path(str(value["package_root"])),
        "package_manifest_digest": package_binding["sha256"],
        "label_map_path": evidence_root / "label-maps" / f"{block_id}.json",
        "label_map_digest": label_binding["sha256"],
        "evaluator_evidence": evaluator,
    }


def prepare_or_load_block_package(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
    evidence_root: Path,
    prepare: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Run package preparation exactly once, or validate its completion."""

    block_id = attempt.get("block_id")
    if not isinstance(block_id, str) or not block_id:
        _fail("package_preparation_lineage_invalid")
    block_root = evidence_root / block_id
    intent_path = block_root / "package-preparation-intent.json"
    completion_path = block_root / "package-preparation-completion.json"
    intent = _intent(
        lock=lock,
        attempt=attempt,
        work_root=work_root,
        evaluation_root=evaluation_root,
        package_root=package_root,
    )
    if os.path.lexists(intent_path):
        if _canonical_object(
            intent_path,
            code="package_preparation_intent_invalid",
        ) != intent:
            _fail("package_preparation_intent_invalid")
        if not os.path.lexists(completion_path):
            _fail("post_valid_preparation_requires_new_lock")
        return _load_completion(
            lock=lock,
            attempt=attempt,
            intent=intent,
            completion_path=completion_path,
            package_root=package_root,
            evidence_root=evidence_root,
        )
    if os.path.lexists(completion_path):
        _fail("package_preparation_completion_invalid")
    _publish(
        intent_path,
        intent,
        code="package_preparation_intent_invalid",
    )
    result = prepare(
        lock=lock,
        attempt=attempt,
        work_root=work_root,
        evaluation_root=evaluation_root,
        package_root=package_root,
    )
    completion = _completion(
        lock=lock,
        attempt=attempt,
        intent=intent,
        result=result,
        package_root=package_root,
        evidence_root=evidence_root,
    )
    _publish(
        completion_path,
        completion,
        code="package_preparation_completion_invalid",
    )
    return result
