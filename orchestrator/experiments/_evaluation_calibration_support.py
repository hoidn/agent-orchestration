"""Calibration lock, evaluator, and evidence-binding helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any
from unittest import mock

from ._evaluation_support import (
    EvaluationError,
    _fail,
    _relative_path,
    _safe_component,
    _sha256_bytes,
    _write_payload,
)


def _run_visible_check(
    *,
    root: Path,
    argv: Sequence[str],
    environment: Mapping[str, str],
    timeout_milliseconds: int,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            tuple(argv),
            cwd=root,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_milliseconds / 1000,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "verdict": "FAIL",
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "verdict": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "stdout": result.stdout.decode("utf-8", errors="replace"),
        "stderr": result.stderr.decode("utf-8", errors="replace"),
    }


def _load_oracle(path: Path) -> ModuleType:
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise EvaluationError("calibration_oracle_invalid", str(path)) from exc
    name = f"lean_pilot_oracle_{hashlib.sha256(source).hexdigest()}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        _fail("calibration_oracle_invalid", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(name, None)
        raise EvaluationError("calibration_oracle_invalid", str(path)) from exc
    return module


def _run_hidden_evaluator(
    *,
    evaluator_module: ModuleType,
    oracle_module: ModuleType,
    root: Path,
    environment: Mapping[str, str],
) -> dict[str, object]:
    evaluate = getattr(evaluator_module, "evaluate_workspace", None)
    loader = getattr(evaluator_module, "_load_oracle_module", None)
    if not callable(evaluate) or not callable(loader):
        _fail("calibration_evaluator_invalid")
    with (
        mock.patch.object(
            evaluator_module,
            "_load_oracle_module",
            return_value=oracle_module,
        ),
        mock.patch.dict(os.environ, dict(environment), clear=True),
    ):
        value = evaluate(root)
    if not isinstance(value, dict) or value.get("verdict") not in {"PASS", "FAIL"}:
        _fail("calibration_evaluator_invalid", "result")
    return value


def _reviewable_evaluator_result(
    value: Mapping[str, object],
    *,
    hidden_roots: Sequence[Path],
) -> dict[str, object]:
    result = {
        "verdict": value["verdict"],
        "failure_categories": value.get("failure_categories", []),
        "summary": value.get("summary", {}),
    }
    return _normalize_evidence_paths(result, hidden_roots=hidden_roots)


def _normalize_evidence_paths(
    value: Any,
    *,
    hidden_roots: Sequence[Path],
) -> Any:
    if isinstance(value, str):
        for root in hidden_roots:
            value = value.replace(str(root), "<candidate-root>")
        return value
    if isinstance(value, list):
        return [
            _normalize_evidence_paths(item, hidden_roots=hidden_roots)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _normalize_evidence_paths(item, hidden_roots=hidden_roots)
            for key, item in value.items()
        }
    return value


def _json_evidence_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise EvaluationError("calibration_evaluator_invalid", "evidence") from exc


def _existing_file_binding(path: Path, *, relative_to: Path) -> dict[str, object]:
    data = path.read_bytes()
    identity = path.stat()
    return {
        "evidence_path": path.relative_to(relative_to).as_posix(),
        "mode": stat.S_IMODE(identity.st_mode),
        "size": len(data),
        "sha256": _sha256_bytes(data),
    }


def _file_binding(
    source: Path, evidence: Path, *, relative_to: Path
) -> dict[str, object]:
    try:
        data = source.read_bytes()
        identity = source.stat()
    except OSError as exc:
        raise EvaluationError("calibration_binding_invalid", str(source)) from exc
    _write_payload(evidence, data, stat.S_IMODE(identity.st_mode))
    return {
        "evidence_path": evidence.relative_to(relative_to).as_posix(),
        "mode": stat.S_IMODE(identity.st_mode),
        "size": len(data),
        "sha256": _sha256_bytes(data),
    }


def _validate_reviewer_execution(
    value: object,
    *,
    code: str,
) -> Path:
    keys = {
        "provider_family",
        "model",
        "reasoning_effort",
        "tool_policy",
        "timeout_milliseconds",
        "cli",
        "environment",
        "invocation_payload_schema_digest",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail(code, "reviewer_execution")
    for key in ("provider_family", "model", "reasoning_effort", "tool_policy"):
        if not isinstance(value.get(key), str) or not value.get(key):
            _fail(code, f"reviewer_execution.{key}")
    timeout = value.get("timeout_milliseconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        _fail(code, "reviewer_execution.timeout_milliseconds")
    cli = value.get("cli")
    if not isinstance(cli, Mapping) or set(cli) != {
        "entry_path",
        "entry_sha256",
        "version",
    }:
        _fail(code, "reviewer_execution.cli")
    entry_path = cli.get("entry_path")
    entry_digest = cli.get("entry_sha256")
    version = cli.get("version")
    if (
        not isinstance(entry_path, str)
        or not entry_path
        or "\\" in entry_path
        or "\x00" in entry_path
        or not PurePosixPath(entry_path).is_absolute()
        or PurePosixPath(entry_path).as_posix() != entry_path
        or not isinstance(entry_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", entry_digest) is None
        or not isinstance(version, str)
        or not version
    ):
        _fail(code, "reviewer_execution.cli")
    entry = Path(entry_path)
    try:
        identity = entry.lstat()
        resolved = entry.resolve(strict=True)
        data = entry.read_bytes()
    except OSError as exc:
        raise EvaluationError(code, "reviewer_execution.cli") from exc
    if (
        entry.is_symlink()
        or not stat.S_ISREG(identity.st_mode)
        or resolved != entry
        or _sha256_bytes(data) != entry_digest
    ):
        _fail(code, "reviewer_execution.cli")
    environment = value.get("environment")
    if not isinstance(environment, Mapping) or set(environment) != {
        "identity",
        "allowed_keys",
        "credential_keys",
    }:
        _fail(code, "reviewer_execution.environment")
    environment_identity = environment.get("identity")
    allowed = environment.get("allowed_keys")
    credentials = environment.get("credential_keys")
    key_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    if (
        not isinstance(environment_identity, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", environment_identity) is None
        or not isinstance(allowed, list)
        or not allowed
        or any(
            not isinstance(key, str) or key_pattern.fullmatch(key) is None
            for key in allowed
        )
        or len(set(allowed)) != len(allowed)
        or not isinstance(credentials, list)
        or any(
            not isinstance(key, str) or key_pattern.fullmatch(key) is None
            for key in credentials
        )
        or len(set(credentials)) != len(credentials)
        or not set(credentials).issubset(allowed)
    ):
        _fail(code, "reviewer_execution.environment")
    payload_digest = value.get("invocation_payload_schema_digest")
    if (
        not isinstance(payload_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", payload_digest) is None
    ):
        _fail(code, "reviewer_execution.invocation_payload_schema_digest")
    return entry


_BASE_IDENTITY_KEYS = {
    "repository_identity",
    "revision_identity",
    "archive_digest",
    "product_manifest_digest",
}


def _validate_base_identity(value: object, *, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BASE_IDENTITY_KEYS:
        _fail(code, "base_identity")
    repository_identity = value.get("repository_identity")
    revision_identity = value.get("revision_identity")
    archive_digest = value.get("archive_digest")
    product_manifest_digest = value.get("product_manifest_digest")
    if (
        not isinstance(repository_identity, str)
        or not repository_identity
        or not isinstance(revision_identity, str)
        or not revision_identity
        or not isinstance(archive_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", archive_digest) is None
        or not isinstance(product_manifest_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", product_manifest_digest) is None
    ):
        _fail(code, "base_identity")
    return {
        "repository_identity": repository_identity,
        "revision_identity": revision_identity,
        "archive_digest": archive_digest,
        "product_manifest_digest": product_manifest_digest,
    }


def _calibration_shape(
    lock: Mapping[str, object],
) -> tuple[str, int, int, tuple[str, str], tuple[str, str, str]]:
    common_keys = {
        "schema_version",
        "calibration_id",
        "round",
        "revision",
        "base_identity",
        "product_projection_exclusions",
        "task",
        "reference_patch",
        "rubric",
        "selected_final_files",
        "evaluator",
        "oracle",
        "environment_identity",
        "reviewer_execution",
        "visible_check",
        "hidden_evaluator_class",
        "expected_contrast",
        "reviewer_ids",
        "package_ids",
        "mapping_seed",
    }
    calibration_id = lock.get("calibration_id")
    round_number = lock.get("round")
    revision = lock.get("revision")
    reviewer_ids = lock.get("reviewer_ids")
    package_ids = lock.get("package_ids")
    if (
        lock.get("schema_version") != "calibration-lock.v1"
        or set(lock) != common_keys | ({"predecessor"} if round_number == 2 else set())
        or
        not isinstance(calibration_id, str)
        or not calibration_id
        or isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or round_number not in {1, 2}
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 0
        or not isinstance(reviewer_ids, list)
        or len(reviewer_ids) != 2
        or len(set(reviewer_ids)) != 2
        or any(not isinstance(value, str) or not value for value in reviewer_ids)
        or not isinstance(package_ids, list)
        or len(package_ids) != 3
        or len(set(package_ids)) != 3
        or any(not isinstance(value, str) or not value for value in package_ids)
    ):
        _fail("calibration_lock_invalid")
    _safe_component(calibration_id)
    for value in reviewer_ids:
        _safe_component(value)
    for value in package_ids:
        _safe_component(value)
    if (round_number, revision) not in {(1, 0), (2, 1)}:
        _fail("calibration_revision_limit_exceeded")
    exact_nested = {
        "base_identity": _BASE_IDENTITY_KEYS,
        "task": {"path", "digest"},
        "reference_patch": {"path", "digest"},
        "rubric": {"path", "digest"},
        "evaluator": {"module_digest", "class"},
        "oracle": {"digest"},
        "visible_check": {"argv", "timeout_milliseconds", "class"},
        "expected_contrast": {
            "base_visible",
            "reference_visible",
            "base_hidden",
            "reference_hidden",
        },
    }
    for key, keys in exact_nested.items():
        value = lock.get(key)
        if not isinstance(value, Mapping) or set(value) != keys:
            _fail("calibration_lock_invalid", key)
    selected_values = lock.get("selected_final_files")
    if (
        not isinstance(lock.get("mapping_seed"), str)
        or not lock.get("mapping_seed")
        or not isinstance(selected_values, list)
        or not selected_values
        or any(not isinstance(value, str) for value in selected_values)
        or len(set(selected_values)) != len(selected_values)
    ):
        _fail("calibration_lock_invalid", "bindings")
    exclusions_value = lock.get("product_projection_exclusions")
    if (
        not isinstance(exclusions_value, list)
        or any(not isinstance(value, str) for value in exclusions_value)
        or len(set(exclusions_value)) != len(exclusions_value)
    ):
        _fail("calibration_lock_invalid", "product exclusions")
    for value in exclusions_value:
        _relative_path(value)
    _validate_base_identity(
        lock.get("base_identity"),
        code="calibration_lock_invalid",
    )
    _validate_reviewer_execution(
        lock.get("reviewer_execution"),
        code="calibration_lock_invalid",
    )
    predecessor = lock.get("predecessor")
    if round_number == 2 and (
        not isinstance(predecessor, Mapping)
        or set(predecessor) != {"lock_digest", "status"}
        or predecessor.get("status") != "FAILED"
        or not isinstance(predecessor.get("lock_digest"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", predecessor["lock_digest"]) is None
    ):
        _fail("calibration_lock_invalid", "predecessor")
    return (
        calibration_id,
        round_number,
        revision,
        (reviewer_ids[0], reviewer_ids[1]),
        (package_ids[0], package_ids[1], package_ids[2]),
    )
