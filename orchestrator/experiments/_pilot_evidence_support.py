"""Boring validation, copy, and evaluator helpers for pilot evidence."""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    load_record,
    validate_record,
)
from .evaluation import EvaluationError
from ._evaluation_support import (
    _canonical_root,
    _overlaps,
    _relative_path,
    _safe_component,
    _source_file,
)
from ._pilot_evaluator_process import (
    _EvaluatorProcessError,
    _run_evaluator_process,
)
from .workspace import TreeManifest, freeze_product


class PilotEvidenceError(ValueError):
    """A committed attempt cannot yield trustworthy pilot evidence."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(code if not detail else f"{code}: {detail}")


def _fail(code: str, detail: str = "") -> None:
    raise PilotEvidenceError(code, detail)


def _fresh_root(path: Path, *, label: str) -> Path:
    candidate = Path(path)
    if (
        not candidate.is_absolute()
        or candidate.resolve(strict=False) != candidate
        or os.path.lexists(candidate)
    ):
        _fail("pilot_evidence_root_invalid", label)
    ancestor = candidate.parent
    while not os.path.lexists(ancestor):
        if ancestor == ancestor.parent:
            _fail("pilot_evidence_root_invalid", label)
        ancestor = ancestor.parent
    try:
        identity = ancestor.lstat()
    except OSError as exc:
        raise PilotEvidenceError(
            "pilot_evidence_root_invalid",
            label,
        ) from exc
    if (
        not stat.S_ISDIR(identity.st_mode)
        or ancestor.is_symlink()
        or ancestor.resolve(strict=True) != ancestor
    ):
        _fail("pilot_evidence_root_invalid", label)
    return candidate


def _existing_root(path: Path, *, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        _fail("pilot_evidence_root_invalid", label)
    try:
        resolved = _canonical_root(candidate, must_exist=True)
    except EvaluationError as exc:
        raise PilotEvidenceError(
            "pilot_evidence_root_invalid",
            label,
        ) from exc
    if resolved != candidate:
        _fail("pilot_evidence_root_invalid", label)
    return candidate


def _require_disjoint(roots: Mapping[str, Path]) -> None:
    items = tuple(roots.items())
    for index, (left_label, left) in enumerate(items):
        for right_label, right in items[index + 1 :]:
            if _overlaps(left, right):
                _fail(
                    "pilot_evidence_root_overlap",
                    f"{left_label}:{right_label}",
                )


def _validated_inputs(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path, Path, Path, Path]:
    try:
        lock_copy = json.loads(canonical_json_bytes(dict(lock)))
        attempt_copy = json.loads(canonical_json_bytes(dict(attempt)))
        validate_record(lock_copy)
        validate_record(attempt_copy)
    except (PilotContractError, TypeError, ValueError) as exc:
        raise PilotEvidenceError(
            "pilot_evidence_lineage_invalid",
            str(exc),
        ) from exc
    if (
        attempt_copy.get("status") != "VALID"
        or attempt_copy.get("attempt_class") not in {"SMOKE", "LIVE"}
        or attempt_copy.get("pilot_lock_digest") != canonical_sha256(lock_copy)
    ):
        _fail("pilot_evidence_lineage_invalid", "lock or terminal status")

    work = _existing_root(work_root, label="work_root")
    evaluation = _fresh_root(evaluation_root, label="evaluation_root")
    package = _fresh_root(package_root, label="package_root")
    evidence_value = lock_copy.get("evidence_root")
    control_value = lock_copy.get("apparatus", {}).get("control_root")
    repository_value = lock_copy.get("archive", {}).get("repository_root")
    if not all(
        isinstance(value, str)
        for value in (evidence_value, control_value, repository_value)
    ):
        _fail("pilot_evidence_lineage_invalid", "locked roots")
    evidence = _existing_root(Path(evidence_value), label="evidence_root")
    control = _existing_root(Path(control_value), label="control_root")
    repository = _existing_root(
        Path(repository_value),
        label="repository_root",
    )
    _require_disjoint(
        {
            "repository": repository,
            "control": control,
            "work": work,
            "evidence": evidence,
            "evaluation": evaluation,
            "package": package,
        }
    )

    block_id = _safe_component(attempt_copy.get("block_id"))
    attempt_path = evidence / block_id / "block-attempt.json"
    try:
        identity = attempt_path.lstat()
        attempt_bytes = attempt_path.read_bytes()
        disk_attempt = load_record(
            attempt_path,
            expected_kind="block_attempt.v1",
        )
    except (OSError, PilotContractError) as exc:
        raise PilotEvidenceError(
            "pilot_evidence_lineage_invalid",
            "attempt record",
        ) from exc
    if (
        not stat.S_ISREG(identity.st_mode)
        or attempt_path.is_symlink()
        or attempt_path.resolve(strict=True) != attempt_path
        or attempt_bytes != canonical_json_bytes(disk_attempt)
        or canonical_json_bytes(disk_attempt)
        != canonical_json_bytes(attempt_copy)
    ):
        _fail("pilot_evidence_lineage_invalid", "attempt record drift")
    return (
        lock_copy,
        attempt_copy,
        work,
        evaluation,
        package,
        evidence,
        control,
    )


def _product_roots(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    work_root: Path,
) -> tuple[dict[str, Path], dict[str, Mapping[str, object]]]:
    block_id = _safe_component(attempt.get("block_id"))
    executions_value = attempt.get("treatment_executions")
    treatments_value = lock.get("treatments")
    if not isinstance(executions_value, list) or not isinstance(
        treatments_value,
        list,
    ):
        _fail("pilot_evidence_lineage_invalid", "treatments")
    expected_roles = {
        item["treatment_id"]
        for item in treatments_value
        if isinstance(item, Mapping)
    }
    executions: dict[str, Mapping[str, object]] = {}
    products: dict[str, Path] = {}
    for execution in executions_value:
        if not isinstance(execution, Mapping):
            _fail("pilot_evidence_lineage_invalid", "execution")
        role = execution.get("treatment_id")
        label = _safe_component(execution.get("opaque_arm_label"))
        if not isinstance(role, str) or role in executions:
            _fail("pilot_evidence_lineage_invalid", "execution role")
        products[role] = _existing_root(
            work_root / block_id / label / "workspace",
            label=f"product:{role}",
        )
        executions[role] = execution
    if set(executions) != expected_roles:
        _fail("pilot_evidence_lineage_invalid", "treatment coverage")
    return products, executions


def _copy_projected_product(
    source_root: Path,
    destination: Path,
    manifest: TreeManifest,
) -> None:
    if any(entry.kind not in {"directory", "file"} for entry in manifest.entries):
        _fail("pilot_evidence_product_unsafe", str(source_root))
    destination.mkdir(mode=0o755)
    directories = tuple(
        entry for entry in manifest.entries if entry.kind == "directory"
    )
    for entry in sorted(
        directories,
        key=lambda item: (len(PurePosixPath(item.path).parts), item.path.encode()),
    ):
        destination.joinpath(*PurePosixPath(entry.path).parts).mkdir(
            mode=0o755,
            exist_ok=False,
        )
    for entry in (item for item in manifest.entries if item.kind == "file"):
        relative = _relative_path(entry.path)
        _source, data, mode = _source_file(source_root, relative)
        target = destination.joinpath(*relative.parts)
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        target.chmod(mode)
    for entry in sorted(
        directories,
        key=lambda item: (-len(PurePosixPath(item.path).parts), item.path.encode()),
    ):
        destination.joinpath(*PurePosixPath(entry.path).parts).chmod(entry.mode)
    if freeze_product(destination, ()) != manifest:
        _fail("pilot_evidence_copy_manifest_mismatch", str(destination))


_EVALUATOR_ADAPTER = """
import importlib.util, json, pathlib, sys
module_path = pathlib.Path(sys.argv[1]).resolve(strict=True)
product_root = pathlib.Path(sys.argv[2]).resolve(strict=True)
spec = importlib.util.spec_from_file_location("locked_pilot_evaluator", module_path)
if spec is None or spec.loader is None: raise RuntimeError("cannot load evaluator")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.evaluate_workspace(product_root)
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False))
"""


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
        raise PilotEvidenceError(
            "pilot_evidence_evaluator_malformed",
            "JSON value",
        ) from exc


def _parse_evaluator_output(data: bytes) -> tuple[dict[str, Any], bytes]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                _fail("pilot_evidence_evaluator_malformed", "duplicate key")
            value[key] = item
        return value

    def constant(value: str) -> None:
        _fail("pilot_evidence_evaluator_malformed", value)

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        PilotEvidenceError,
    ) as exc:
        if isinstance(exc, PilotEvidenceError):
            raise
        raise PilotEvidenceError(
            "pilot_evidence_evaluator_malformed",
            "transport",
        ) from exc
    canonical = _json_evidence_bytes(value)
    if data != canonical or not isinstance(value, dict):
        _fail("pilot_evidence_evaluator_malformed", "canonical object")
    if set(value) != {
        "failure_categories",
        "soft_quality",
        "summary",
        "verdict",
    }:
        _fail("pilot_evidence_evaluator_malformed", "top-level keys")
    categories = value["failure_categories"]
    summary = value["summary"]
    verdict = value["verdict"]
    if (
        verdict not in {"PASS", "FAIL"}
        or not isinstance(categories, list)
        or any(not isinstance(item, str) or not item for item in categories)
        or not isinstance(summary, dict)
        or not isinstance(value["soft_quality"], dict)
        or not isinstance(summary.get("hidden_tests_passed"), bool)
        or summary["hidden_tests_passed"] != (verdict == "PASS")
        or (verdict == "PASS" and categories)
    ):
        _fail("pilot_evidence_evaluator_malformed", "result contract")
    return value, canonical


def _run_evaluator(
    *,
    module_path: Path,
    product_root: Path,
    runtime_root: Path,
    timeout_milliseconds: int,
    quiescence_grace_milliseconds: int,
) -> tuple[dict[str, Any], bytes]:
    home = runtime_root / "home"
    temporary = runtime_root / "tmp"
    home.mkdir(parents=True)
    temporary.mkdir()
    try:
        completed = _run_evaluator_process(
            command=[
                sys.executable,
                "-I",
                "-B",
                "-c",
                _EVALUATOR_ADAPTER,
                str(module_path),
                str(product_root),
            ],
            cwd=runtime_root,
            environment={
                "HOME": str(home),
                "TMPDIR": str(temporary),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            },
            timeout_milliseconds=timeout_milliseconds,
            quiescence_grace_milliseconds=quiescence_grace_milliseconds,
        )
    except _EvaluatorProcessError as exc:
        raise PilotEvidenceError(
            "pilot_evidence_evaluator_execution_failed",
            exc.reason,
        ) from exc
    if completed.returncode != 0:
        _fail(
            "pilot_evidence_evaluator_execution_failed",
            f"exit:{completed.returncode}",
        )
    return _parse_evaluator_output(completed.stdout)
