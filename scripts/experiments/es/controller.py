"""Fail-closed provider-free controller assembly for the first ES study.

The controller owns only composition: frozen-package validation, one public E2
entry invocation, artifact replay, blinded review ordering, hard-evidence
derivation, and handoff to the canonical artifact finalizer. Provider process
allocation is owned by :mod:`provider_boundary`, which records the durable
prelaunch event before starting every treatment, scorer, or review process.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, NoReturn

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.trial import ledger as trial_ledger
from orchestrator.workflow.trial.contracts import TrialCellKey
from orchestrator.workflow.trial.sdk import (
    TrialRunOptions,
    TrialRunResult,
    run_trial_entry,
)

from . import (
    attempts,
    blinding,
    controller_artifacts,
    decision_lock,
    hard_contract,
    provider_boundary,
    reviews,
    synthesis,
)


ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
WORKFLOW_RELPATH = (
    "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc"
)
ENTRY_WORKFLOW = "compare"
_SHA_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ATTEMPT_RE = re.compile(r"ES-ATTEMPT-0[1-4]\Z")
_FAILURE_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z")


class ControllerError(ValueError):
    """One controller invariant failed before unsupported work could proceed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ControllerError(code, detail)


class _ProviderCallInterrupted(ControllerError):
    """One allocated provider process ended without a durable result wrapper."""


class PostIncidentDispositionRequired(ControllerError):
    """A cause-neutral failed prefix awaits an externally adopted disposition."""

    def __init__(
        self,
        *,
        attempt_id: str,
        disposition_path: Path,
        binding: bytes,
    ) -> None:
        if _ATTEMPT_RE.fullmatch(attempt_id) is None:
            _fail("controller_post_incident_boundary_invalid", "attempt_id")
        path = _canonical_root(
            disposition_path,
            field="post_incident.disposition_path",
        )
        record = _closed_object(binding, field="post_incident.binding")
        if (
            set(record)
            != {
                "schema_version",
                "attempt_id",
                "disposition_path",
                "bindings",
                "pre_treatment_proof",
            }
            or record.get("schema_version")
            != "es.post_incident_disposition_boundary.v1"
            or record.get("attempt_id") != attempt_id
            or record.get("disposition_path") != path.as_posix()
            or not isinstance(record.get("bindings"), dict)
            or record.get("pre_treatment_proof")
            != {
                "cell_allocation_started_count": 0,
                "provider_allocation_count": 0,
            }
        ):
            _fail("controller_post_incident_boundary_invalid")
        self.attempt_id = attempt_id
        self.disposition_path = path
        self.binding = binding
        self.binding_sha256 = _digest_bytes(binding)
        super().__init__(
            "controller_post_incident_disposition_required",
            attempt_id,
        )


class _CommonEvaluationBytesInvalid(ControllerError):
    """The frozen evaluator fixture changed before its target allocation."""

    def __init__(self, authority: "_AttemptClassifierAuthority") -> None:
        self.authority = authority
        super().__init__("controller_common_evaluation_bytes_invalid")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _evidence_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
        + b"\n"
    )


def _evidence_digest(value: object) -> str:
    return _digest_bytes(_evidence_bytes(value))


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("controller_json_duplicate_key", key)
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    _fail("controller_json_number_invalid", value)


def _json_value(
    raw: bytes,
    *,
    field: str,
    line: bool = False,
    allow_finite_float: bool = False,
) -> Any:
    try:
        options: dict[str, Any] = {
            "object_pairs_hook": _strict_object,
            "parse_constant": _reject_number,
        }
        if not allow_finite_float:
            options["parse_float"] = _reject_number
        value = json.loads(raw.decode("utf-8", "strict"), **options)
    except ControllerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControllerError("controller_json_invalid", field) from exc
    canonical = canonical_json_bytes(value) + (b"\n" if line else b"")
    if raw != canonical:
        _fail("controller_json_noncanonical", field)
    return value


def _closed_object(
    raw: bytes,
    *,
    field: str,
    line: bool = False,
    allow_finite_float: bool = False,
) -> dict[str, Any]:
    value = _json_value(
        raw,
        field=field,
        line=line,
        allow_finite_float=allow_finite_float,
    )
    if not isinstance(value, dict):
        _fail("controller_json_object_required", field)
    return value


def _relative(value: str, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail("controller_path_invalid", field)
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        _fail("controller_path_invalid", field)
    return path


def _canonical_root(value: Path, *, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=False) != path:
        _fail("controller_path_not_canonical", field)
    return path


@dataclass(frozen=True, slots=True)
class BoundFile:
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _relative(self.relative_path, field="bound_file.relative_path")
        if _SHA_RE.fullmatch(self.sha256) is None:
            _fail("controller_binding_invalid", self.relative_path)


AttemptIndexBinding = controller_artifacts.AttemptIndexBinding


@dataclass(frozen=True, slots=True)
class ControllerPaths:
    workspace: Path
    state_dir: Path
    run_ref_root: Path
    evidence_root: Path

    def __post_init__(self) -> None:
        for field in ("workspace", "state_dir", "run_ref_root", "evidence_root"):
            object.__setattr__(
                self,
                field,
                _canonical_root(getattr(self, field), field=field),
            )


@dataclass(frozen=True, slots=True)
class ControllerPackage:
    paths: ControllerPaths
    workflow: BoundFile
    provider_externs: BoundFile
    prompt_externs: BoundFile
    task: BoundFile
    check_contract: BoundFile
    source_projection: BoundFile
    task_profile: BoundFile
    task_seed: BoundFile
    evaluator_fixture: BoundFile
    environment_lock: BoundFile
    prompt_manifest: BoundFile
    report_schema: BoundFile
    randomization_manifest: BoundFile
    decision_lock: BoundFile
    call_authority: BoundFile
    trial_artifact_authority: BoundFile
    expected_bindings: tuple[tuple[str, str], ...]
    model: str
    effort: str
    consumed_attempt_ids: tuple[str, ...]
    consumed_attempt_call_counts: tuple[int, ...]
    invalid_attempt_count: int
    attempt_indexes: tuple[AttemptIndexBinding, ...] = ()
    manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.paths) is not ControllerPaths:
            raise TypeError("controller paths must be exact ControllerPaths")
        for name in (
            "workflow",
            "provider_externs",
            "prompt_externs",
            "task",
            "check_contract",
            "source_projection",
            "task_profile",
            "task_seed",
            "evaluator_fixture",
            "environment_lock",
            "prompt_manifest",
            "report_schema",
            "randomization_manifest",
            "decision_lock",
            "call_authority",
            "trial_artifact_authority",
        ):
            if type(getattr(self, name)) is not BoundFile:
                raise TypeError(f"controller {name} must be exact BoundFile")
        if self.workflow.relative_path != WORKFLOW_RELPATH:
            _fail("controller_workflow_binding_invalid")
        if (
            type(self.expected_bindings) is not tuple
            or any(
                type(row) is not tuple
                or len(row) != 2
                or not isinstance(row[0], str)
                or _SHA_RE.fullmatch(row[1]) is None
                for row in self.expected_bindings
            )
            or tuple(sorted(self.expected_bindings)) != self.expected_bindings
            or len({row[0] for row in self.expected_bindings})
            != len(self.expected_bindings)
        ):
            _fail("controller_expected_bindings_invalid")
        if self.model != "gpt-5.5" or self.effort != "high":
            _fail("controller_provider_policy_invalid")
        if type(self.consumed_attempt_ids) is not tuple or any(
            _ATTEMPT_RE.fullmatch(value) is None
            for value in self.consumed_attempt_ids
        ):
            _fail("controller_attempt_history_invalid")
        if (
            type(self.consumed_attempt_call_counts) is not tuple
            or len(self.consumed_attempt_call_counts)
            != len(self.consumed_attempt_ids)
            or any(type(value) is not int or value < 0 for value in self.consumed_attempt_call_counts)
        ):
            _fail("controller_attempt_history_invalid")
        if type(self.invalid_attempt_count) is not int or self.invalid_attempt_count < 0:
            _fail("controller_attempt_history_invalid")
        if (
            type(self.attempt_indexes) is not tuple
            or any(type(row) is not AttemptIndexBinding for row in self.attempt_indexes)
            or (
                self.attempt_indexes
                and tuple(row.attempt_id for row in self.attempt_indexes)
                != self.consumed_attempt_ids
            )
            or (
                self.manifest_sha256 is not None
                and tuple(row.attempt_id for row in self.attempt_indexes)
                != self.consumed_attempt_ids
            )
        ):
            _fail("controller_attempt_history_invalid")
        if self.manifest_sha256 is not None and _SHA_RE.fullmatch(
            self.manifest_sha256
        ) is None:
            _fail("controller_package_manifest_invalid")

    @property
    def manifest_record(self) -> dict[str, Any]:
        files = {
            name: {
                "relative_path": getattr(self, name).relative_path,
                "sha256": getattr(self, name).sha256,
            }
            for name in (
                "workflow",
                "provider_externs",
                "prompt_externs",
                "task",
                "check_contract",
                "source_projection",
                "task_profile",
                "task_seed",
                "evaluator_fixture",
                "environment_lock",
                "prompt_manifest",
                "report_schema",
                "randomization_manifest",
                "decision_lock",
                "call_authority",
                "trial_artifact_authority",
            )
        }
        return {
            "schema_version": "es.controller_package.v1",
            "paths": {
                "workspace": self.paths.workspace.as_posix(),
                "state_dir": self.paths.state_dir.as_posix(),
                "run_ref_root": self.paths.run_ref_root.as_posix(),
                "evidence_root": self.paths.evidence_root.as_posix(),
            },
            "files": files,
            "expected_bindings": [
                {"name": name, "sha256": digest}
                for name, digest in self.expected_bindings
            ],
            "provider_policy": {"model": self.model, "effort": self.effort},
            "history": {
                "attempt_indexes": [
                    {
                        "attempt_id": row.attempt_id,
                        "relative_path": row.relative_path,
                        "sha256": row.sha256,
                    }
                    for row in self.attempt_indexes
                ],
                "consumed_attempt_ids": list(self.consumed_attempt_ids),
                "consumed_attempt_call_counts": list(
                    self.consumed_attempt_call_counts
                ),
                "invalid_attempt_count": self.invalid_attempt_count,
            },
        }


_PACKAGE_FILE_ROLES = (
    "workflow",
    "provider_externs",
    "prompt_externs",
    "task",
    "check_contract",
    "source_projection",
    "task_profile",
    "task_seed",
    "evaluator_fixture",
    "environment_lock",
    "prompt_manifest",
    "report_schema",
    "randomization_manifest",
    "decision_lock",
    "call_authority",
    "trial_artifact_authority",
)


def _exact_keys(value: Mapping[str, object], expected: set[str], *, field: str) -> None:
    if set(value) != expected:
        _fail("controller_package_manifest_schema_invalid", field)


def _manifest_string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        _fail("controller_package_manifest_schema_invalid", field)
    return value


def _read_manifest_file(path: Path, *, expected_sha256: str) -> bytes:
    if _SHA_RE.fullmatch(expected_sha256) is None:
        _fail("controller_package_manifest_digest_invalid")
    canonical = _canonical_root(path, field="controller_package_manifest")
    try:
        identity = canonical.lstat()
        raw = canonical.read_bytes()
    except OSError as exc:
        raise ControllerError("controller_package_manifest_unreadable") from exc
    if canonical.is_symlink() or not stat.S_ISREG(identity.st_mode):
        _fail("controller_package_manifest_unreadable")
    if _digest_bytes(raw) != expected_sha256:
        _fail("controller_package_manifest_digest_mismatch")
    return raw


def _load_attempt_history(
    package: ControllerPackage,
    *,
    preflight: "_Preflight",
) -> tuple[tuple[str, ...], tuple[int, ...], int]:
    root = package.paths.evidence_root / "attempts"
    expected_paths = {row.relative_path for row in package.attempt_indexes}
    actual_paths: set[str] = set()
    if root.exists():
        try:
            identity = root.lstat()
        except OSError as exc:
            raise ControllerError("controller_attempt_history_unreadable") from exc
        if root.is_symlink() or not stat.S_ISDIR(identity.st_mode):
            _fail("controller_attempt_history_unreadable")
        actual_paths = {
            path.relative_to(package.paths.evidence_root).as_posix()
            for path in root.glob("*/index.json")
        }
    if actual_paths != expected_paths:
        _fail("controller_attempt_history_inventory_mismatch")

    locked_ids = tuple(preflight.decision_lock["schedule"]["attempt_ids"])
    ids = tuple(row.attempt_id for row in package.attempt_indexes)
    if ids != locked_ids[: len(ids)]:
        _fail("controller_attempt_history_sequence_invalid")
    if not ids:
        next_id = attempts.select_next_attempt_id(
            (),
            decision_lock=preflight.decision_lock,
            randomization_manifest=preflight.randomization_manifest,
            expected_bindings=preflight.expected_bindings,
        )
        if next_id != locked_ids[0]:
            _fail("controller_attempt_history_sequence_invalid")
        return (), (), 0

    counts: list[int] = []
    invalid_count = 0
    for binding in package.attempt_indexes:
        path = package.paths.evidence_root.joinpath(
            *_relative(binding.relative_path, field="attempt_index").parts
        )
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(package.paths.evidence_root)
            identity = path.lstat()
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise ControllerError(
                "controller_attempt_history_unreadable",
                binding.attempt_id,
            ) from exc
        if (
            resolved != path
            or path.is_symlink()
            or not stat.S_ISREG(identity.st_mode)
            or _digest_bytes(raw) != binding.sha256
        ):
            _fail("controller_attempt_history_binding_mismatch", binding.attempt_id)
        index = _closed_object(
            raw,
            field=f"attempt_index.{binding.attempt_id}",
            line=True,
            allow_finite_float=True,
        )
        internal_digest = index.get("index_sha256")
        if not isinstance(internal_digest, str):
            _fail("controller_attempt_history_index_invalid", binding.attempt_id)
        try:
            validated = synthesis.validate_attempt_evidence_index(
                index,
                expected_index_sha256=internal_digest,
                decision_lock=preflight.decision_lock,
                randomization_manifest=preflight.randomization_manifest,
                expected_bindings=preflight.expected_bindings,
            )
        except synthesis.SynthesisError as exc:
            raise ControllerError(
                "controller_attempt_history_index_invalid",
                binding.attempt_id,
            ) from exc
        attempt_record = validated.get("attempt_record")
        if not isinstance(attempt_record, Mapping):
            _fail("controller_attempt_history_index_invalid", binding.attempt_id)
        accounting = attempt_record.get("accounting")
        if (
            attempt_record.get("attempt_id") != binding.attempt_id
            or not isinstance(accounting, Mapping)
            or type(accounting.get("call_count")) is not int
            or accounting["call_count"] < 0
            or attempt_record.get("status") not in {"VALID", "INVALID"}
        ):
            _fail("controller_attempt_history_index_invalid", binding.attempt_id)
        counts.append(accounting["call_count"])
        invalid_count += int(attempt_record["status"] == "INVALID")
    return ids, tuple(counts), invalid_count


def load_controller_package(
    manifest_path: Path,
    *,
    expected_sha256: str,
) -> ControllerPackage:
    """Load one externally digest-pinned, closed controller package."""

    raw = _read_manifest_file(manifest_path, expected_sha256=expected_sha256)
    record = _closed_object(raw, field="controller_package_manifest", line=True)
    _exact_keys(
        record,
        {
            "schema_version",
            "paths",
            "files",
            "expected_bindings",
            "provider_policy",
            "history",
        },
        field="root",
    )
    if record["schema_version"] != "es.controller_package.v1":
        _fail("controller_package_manifest_schema_invalid", "schema_version")

    paths = record["paths"]
    files = record["files"]
    bindings = record["expected_bindings"]
    provider = record["provider_policy"]
    history = record["history"]
    if not all(isinstance(value, Mapping) for value in (paths, files, provider, history)):
        _fail("controller_package_manifest_schema_invalid", "objects")
    assert isinstance(paths, Mapping)
    assert isinstance(files, Mapping)
    assert isinstance(provider, Mapping)
    assert isinstance(history, Mapping)
    _exact_keys(paths, {"workspace", "state_dir", "run_ref_root", "evidence_root"}, field="paths")
    _exact_keys(files, set(_PACKAGE_FILE_ROLES), field="files")
    _exact_keys(provider, {"model", "effort"}, field="provider_policy")
    _exact_keys(
        history,
        {
            "attempt_indexes",
            "consumed_attempt_ids",
            "consumed_attempt_call_counts",
            "invalid_attempt_count",
        },
        field="history",
    )

    bound_files: dict[str, BoundFile] = {}
    for role in _PACKAGE_FILE_ROLES:
        row = files[role]
        if not isinstance(row, Mapping):
            _fail("controller_package_manifest_schema_invalid", f"files.{role}")
        _exact_keys(row, {"relative_path", "sha256"}, field=f"files.{role}")
        bound_files[role] = BoundFile(
            _manifest_string(row["relative_path"], field=f"files.{role}.relative_path"),
            _manifest_string(row["sha256"], field=f"files.{role}.sha256"),
        )

    if not isinstance(bindings, list):
        _fail("controller_package_manifest_schema_invalid", "expected_bindings")
    expected_bindings: list[tuple[str, str]] = []
    for index, row in enumerate(bindings):
        if not isinstance(row, Mapping):
            _fail("controller_package_manifest_schema_invalid", "expected_bindings")
        _exact_keys(row, {"name", "sha256"}, field=f"expected_bindings.{index}")
        expected_bindings.append(
            (
                _manifest_string(row["name"], field=f"expected_bindings.{index}.name"),
                _manifest_string(row["sha256"], field=f"expected_bindings.{index}.sha256"),
            )
        )

    history_rows = history["attempt_indexes"]
    consumed_ids = history["consumed_attempt_ids"]
    consumed_counts = history["consumed_attempt_call_counts"]
    invalid_count = history["invalid_attempt_count"]
    if (
        not isinstance(history_rows, list)
        or not isinstance(consumed_ids, list)
        or not isinstance(consumed_counts, list)
        or type(invalid_count) is not int
    ):
        _fail("controller_package_manifest_schema_invalid", "history")
    attempt_indexes: list[AttemptIndexBinding] = []
    for index, row in enumerate(history_rows):
        if not isinstance(row, Mapping):
            _fail("controller_package_manifest_schema_invalid", "history.attempt_indexes")
        _exact_keys(
            row,
            {"attempt_id", "relative_path", "sha256"},
            field=f"history.attempt_indexes.{index}",
        )
        attempt_indexes.append(
            AttemptIndexBinding(
                attempt_id=_manifest_string(
                    row["attempt_id"], field=f"history.attempt_indexes.{index}.attempt_id"
                ),
                relative_path=_manifest_string(
                    row["relative_path"],
                    field=f"history.attempt_indexes.{index}.relative_path",
                ),
                sha256=_manifest_string(
                    row["sha256"], field=f"history.attempt_indexes.{index}.sha256"
                ),
            )
        )

    package = ControllerPackage(
        paths=ControllerPaths(
            workspace=Path(_manifest_string(paths["workspace"], field="paths.workspace")),
            state_dir=Path(_manifest_string(paths["state_dir"], field="paths.state_dir")),
            run_ref_root=Path(
                _manifest_string(paths["run_ref_root"], field="paths.run_ref_root")
            ),
            evidence_root=Path(
                _manifest_string(paths["evidence_root"], field="paths.evidence_root")
            ),
        ),
        **bound_files,
        expected_bindings=tuple(expected_bindings),
        model=_manifest_string(provider["model"], field="provider_policy.model"),
        effort=_manifest_string(provider["effort"], field="provider_policy.effort"),
        consumed_attempt_ids=tuple(
            _manifest_string(value, field="history.consumed_attempt_ids")
            for value in consumed_ids
        ),
        consumed_attempt_call_counts=tuple(consumed_counts),
        invalid_attempt_count=invalid_count,
        attempt_indexes=tuple(attempt_indexes),
        manifest_sha256=expected_sha256,
    )
    preflight = _preflight(package, allow_untrusted_package=False)
    derived = _load_attempt_history(package, preflight=preflight)
    declared = (
        package.consumed_attempt_ids,
        package.consumed_attempt_call_counts,
        package.invalid_attempt_count,
    )
    if derived != declared:
        _fail("controller_attempt_history_mismatch")
    return package


PersistedPacket = controller_artifacts.PersistedPacket
PersistedTrialAuthority = controller_artifacts.PersistedTrialReplay


@dataclass(frozen=True, slots=True)
class ReviewCallRequest:
    attempt_id: str
    call_slot_id: str
    review_kind: str
    perspective_id: str | None
    presentation_order: tuple[str, ...]
    packet_paths: tuple[str, ...]
    prior_records: tuple[bytes, ...]
    hard_evidence: tuple[bytes, ...]
    allocation_event: bytes
    allocation_event_path: Path


@dataclass(frozen=True, slots=True)
class ProviderCallResult:
    status: str
    payload: bytes | None
    receipt: bytes
    raw_jsonl: bytes
    elapsed_ms: int
    failure_code: str | None

    def __post_init__(self) -> None:
        if self.status not in {"SUCCEEDED", "FAILED"}:
            _fail("controller_provider_result_invalid")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            _fail("controller_provider_result_invalid")
        if self.status == "SUCCEEDED":
            if not isinstance(self.payload, bytes) or self.failure_code is not None:
                _fail("controller_provider_result_invalid")
        elif self.payload is not None or not isinstance(self.failure_code, str) or _FAILURE_RE.fullmatch(
            self.failure_code
        ) is None:
            _fail("controller_provider_result_invalid")

    @classmethod
    def succeeded(
        cls,
        *,
        payload: bytes,
        receipt: bytes,
        raw_jsonl: bytes,
        elapsed_ms: int,
    ) -> "ProviderCallResult":
        return cls("SUCCEEDED", payload, receipt, raw_jsonl, elapsed_ms, None)

    @classmethod
    def failed(
        cls,
        *,
        failure_code: str,
        receipt: bytes,
        raw_jsonl: bytes,
        elapsed_ms: int,
    ) -> "ProviderCallResult":
        return cls("FAILED", None, receipt, raw_jsonl, elapsed_ms, failure_code)


@dataclass(frozen=True, slots=True)
class HardEvidenceRequest:
    attempt_id: str
    arm_id: str
    cell: TrialCellKey
    opaque_label: str
    packet: bytes


@dataclass(frozen=True, slots=True)
class HardEvidenceInput:
    trusted_product_freeze_status: str
    canonical_inputs: bytes

    def __post_init__(self) -> None:
        if self.trusted_product_freeze_status not in {"PRESENT", "MISSING"}:
            _fail("controller_hard_input_invalid")
        _closed_object(self.canonical_inputs, field="hard_evidence_input")

    @classmethod
    def present(cls, replay_inputs: bytes) -> "HardEvidenceInput":
        return cls("PRESENT", replay_inputs)

    @classmethod
    def missing(cls, absence_authority: bytes) -> "HardEvidenceInput":
        return cls("MISSING", absence_authority)


@dataclass(frozen=True, slots=True)
class SealedReviewRecord:
    call_slot_id: str
    status: str
    canonical_record: bytes
    canonical_receipt: bytes
    raw_jsonl: bytes
    elapsed_ms: int
    allocation_event: bytes
    allocation_path: Path
    call_allocation: bytes

    @property
    def record(self) -> dict[str, Any]:
        return _closed_object(self.canonical_record, field=self.call_slot_id)


@dataclass(frozen=True, slots=True)
class _AttemptClassifierAuthority:
    common_provider_outage_proven: bool
    evaluation_bytes_valid: bool
    blinding_join_valid: bool
    invalidity_authority: bytes | None

    def __post_init__(self) -> None:
        values = (
            self.common_provider_outage_proven,
            self.evaluation_bytes_valid,
            self.blinding_join_valid,
        )
        if any(type(value) is not bool for value in values):
            raise TypeError("classifier authority fields must be exact bool")
        invalidities = (
            int(self.common_provider_outage_proven),
            int(not self.evaluation_bytes_valid),
            int(not self.blinding_join_valid),
        )
        if sum(invalidities) > 1:
            _fail("controller_classifier_authority_ambiguous")
        if self.invalidity_authority is not None:
            if not isinstance(self.invalidity_authority, bytes):
                raise TypeError("invalidity authority must be bytes or None")
            record = _closed_object(
                self.invalidity_authority,
                field="invalidity_authority",
            )
            if (
                set(record)
                != {
                    "schema_version",
                    "attempt_id",
                    "invalidity_code",
                    "evidence",
                }
                or record.get("schema_version")
                != "es.controller_invalidity_authority.v1"
                or record.get("invalidity_code") != self.invalidity_code
            ):
                _fail("controller_classifier_authority_invalid")
        record_required = self.invalidity_code in {
            "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
            "COMMON_EVALUATION_BYTES_INVALID",
        }
        if record_required != (self.invalidity_authority is not None):
            _fail("controller_classifier_authority_invalid")

    @property
    def invalidity_code(self) -> str | None:
        if self.common_provider_outage_proven:
            return "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT"
        if not self.evaluation_bytes_valid:
            return "COMMON_EVALUATION_BYTES_INVALID"
        if not self.blinding_join_valid:
            return "BLINDING_JOIN_INVALID"
        return None


def _valid_classifier_authority() -> _AttemptClassifierAuthority:
    return _AttemptClassifierAuthority(
        common_provider_outage_proven=False,
        evaluation_bytes_valid=True,
        blinding_join_valid=True,
        invalidity_authority=None,
    )


def _blinding_classifier_authority(
    error: blinding.BlindingJoinError,
) -> _AttemptClassifierAuthority:
    if type(error) is not blinding.BlindingJoinError or error.code != (
        "BLINDING_JOIN_INVALID"
    ):
        _fail("controller_blinding_classifier_authority_invalid")
    return _AttemptClassifierAuthority(
        common_provider_outage_proven=False,
        evaluation_bytes_valid=True,
        blinding_join_valid=False,
        invalidity_authority=None,
    )


def _evaluation_classifier_authority(
    authority: bytes,
) -> _AttemptClassifierAuthority:
    return _AttemptClassifierAuthority(
        common_provider_outage_proven=False,
        evaluation_bytes_valid=False,
        blinding_join_valid=True,
        invalidity_authority=authority,
    )


def _outage_classifier_authority(
    authority: bytes,
) -> _AttemptClassifierAuthority:
    return _AttemptClassifierAuthority(
        common_provider_outage_proven=True,
        evaluation_bytes_valid=True,
        blinding_join_valid=True,
        invalidity_authority=authority,
    )


@dataclass(frozen=True, slots=True)
class AttemptAssembly:
    attempt_id: str
    package: ControllerPackage
    trial_result: TrialRunResult | None
    authority: PersistedTrialAuthority | None
    private_join: blinding.PrivateBlindingJoin | None
    review_records: tuple[SealedReviewRecord, ...]
    adjudication_payload: bytes | None
    hard_evidence: tuple[tuple[str, HardEvidenceInput], ...]
    integrated_payload: bytes | None
    material_disagreement: bool
    classifier_authority: _AttemptClassifierAuthority
    journal_path: Path


@dataclass(frozen=True, slots=True)
class FinalizedAttempt:
    attempt_record: bytes
    attempt_index: bytes
    attempt_index_sha256: str
    report: bytes | None
    stopped: bool
    next_attempt_id: str | None

    def __post_init__(self) -> None:
        if _SHA_RE.fullmatch(self.attempt_index_sha256) is None:
            _fail("controller_finalized_attempt_invalid")
        if self.stopped:
            if self.report is None or self.next_attempt_id is not None:
                _fail("controller_final_report_invalid")
        elif self.report is not None or self.next_attempt_id is None:
            _fail("controller_final_report_invalid")


@dataclass(frozen=True, slots=True)
class ControllerResult:
    attempt_id: str
    trial_result: TrialRunResult | None
    attempt_record: bytes
    attempt_index: bytes
    attempt_index_sha256: str
    report: bytes | None
    stopped: bool
    next_attempt_id: str | None


RunTrial = Callable[..., TrialRunResult]
ReplayTrial = Callable[[TrialRunResult, ControllerPackage], PersistedTrialAuthority]
CallProvider = Callable[[ReviewCallRequest], ProviderCallResult]
CollectHard = Callable[[HardEvidenceRequest], HardEvidenceInput]
FinalizeAttempt = Callable[[AttemptAssembly], FinalizedAttempt]


@dataclass(frozen=True, slots=True)
class ControllerDependencies:
    run_trial: RunTrial
    replay_trial: ReplayTrial
    call_provider: CallProvider
    collect_hard_evidence: CollectHard
    finalize_attempt: FinalizeAttempt
    allow_untrusted_package_for_tests: bool = False
    common_provider_outage_disposition_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.allow_untrusted_package_for_tests) is not bool:
            raise TypeError("allow_untrusted_package_for_tests must be bool")
        if (
            self.common_provider_outage_disposition_sha256 is not None
            and (
                not isinstance(
                    self.common_provider_outage_disposition_sha256,
                    str,
                )
                or _SHA_RE.fullmatch(
                    self.common_provider_outage_disposition_sha256
                )
                is None
            )
        ):
            _fail("controller_outage_disposition_binding_invalid")


@dataclass(frozen=True, slots=True)
class _Preflight:
    decision_lock: dict[str, Any]
    randomization_manifest: dict[str, Any]
    expected_bindings: dict[str, str]
    call_authority: dict[str, Any]
    trial_artifact_authority: bytes
    task: str
    check_contract: str


def _bound_bytes(package: ControllerPackage, bound: BoundFile) -> bytes:
    workspace = package.paths.workspace
    path = workspace.joinpath(*_relative(bound.relative_path, field="bound").parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(workspace)
        identity = path.lstat()
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ControllerError("controller_binding_unreadable", bound.relative_path) from exc
    if (
        resolved != path
        or path.is_symlink()
        or not stat.S_ISREG(identity.st_mode)
        or _digest_bytes(raw) != bound.sha256
    ):
        _fail("controller_binding_mismatch", bound.relative_path)
    return raw


def _preflight(
    package: ControllerPackage,
    *,
    allow_untrusted_package: bool = False,
    allow_evaluator_mismatch: bool = False,
) -> _Preflight:
    if type(package) is not ControllerPackage:
        raise TypeError("package must be exact ControllerPackage")
    if type(allow_untrusted_package) is not bool or type(
        allow_evaluator_mismatch
    ) is not bool:
        raise TypeError("preflight policy flags must be exact bool")
    if package.manifest_sha256 is None:
        if not allow_untrusted_package:
            _fail("controller_package_manifest_required")
    elif _digest_bytes(canonical_json_bytes(package.manifest_record) + b"\n") != (
        package.manifest_sha256
    ):
        _fail("controller_package_manifest_digest_mismatch")
    raw: dict[str, bytes] = {}
    for name in (
        "workflow",
        "provider_externs",
        "prompt_externs",
        "task",
        "check_contract",
        "source_projection",
        "task_profile",
        "task_seed",
        "evaluator_fixture",
        "environment_lock",
        "prompt_manifest",
        "report_schema",
        "randomization_manifest",
        "decision_lock",
        "call_authority",
        "trial_artifact_authority",
    ):
        if name == "evaluator_fixture" and allow_evaluator_mismatch:
            continue
        raw[name] = _bound_bytes(package, getattr(package, name))
    try:
        schedule = decision_lock.load_canonical_json(
            package.paths.workspace / package.randomization_manifest.relative_path
        )
        lock = decision_lock.load_canonical_json(
            package.paths.workspace / package.decision_lock.relative_path
        )
    except (OSError, decision_lock.DecisionLockError) as exc:
        raise ControllerError("controller_lock_binding_invalid") from exc
    bindings = dict(package.expected_bindings)
    expected_names = {
        "arm_workflow_sha256",
        "environment_lock_sha256",
        "evaluator_fixture_manifest_sha256",
        "prompt_manifest_sha256",
        "randomization_manifest_sha256",
        "report_schema_sha256",
        "source_projection_manifest_sha256",
        "task_profile_sha256",
        "task_seed_manifest_sha256",
    }
    if set(bindings) != expected_names:
        _fail("controller_expected_bindings_invalid")
    actual = {
        "arm_workflow_sha256": package.workflow.sha256,
        "environment_lock_sha256": package.environment_lock.sha256,
        "evaluator_fixture_manifest_sha256": package.evaluator_fixture.sha256,
        "prompt_manifest_sha256": package.prompt_manifest.sha256,
        "randomization_manifest_sha256": decision_lock.decision_lock_digest(schedule),
        "report_schema_sha256": package.report_schema.sha256,
        "source_projection_manifest_sha256": package.source_projection.sha256,
        "task_profile_sha256": package.task_profile.sha256,
        "task_seed_manifest_sha256": package.task_seed.sha256,
    }
    if bindings != actual:
        _fail("controller_binding_cross_link_invalid")
    try:
        checked_schedule = decision_lock.validate_randomization_manifest(schedule)
        checked_lock = decision_lock.validate_decision_lock(
            lock,
            randomization_manifest=checked_schedule,
            expected_bindings=bindings,
        )
    except decision_lock.DecisionLockError as exc:
        raise ControllerError("controller_lock_binding_invalid", exc.code) from exc
    call_authority = _closed_object(raw["call_authority"], field="call_authority")
    environment = _closed_object(raw["environment_lock"], field="environment_lock")
    prompts = _closed_object(raw["prompt_manifest"], field="prompt_manifest")
    if call_authority != {
        "schema_version": "es.frozen_call_authority.v1",
        "prompt_manifest": prompts,
        "environment_lock": environment,
    }:
        _fail("controller_call_authority_invalid")
    if environment.get("model") != package.model or environment.get(
        "reasoning_effort"
    ) != package.effort:
        _fail("controller_provider_policy_invalid")
    try:
        frozen_trial_authority = attempts.load_frozen_trial_artifact_authority(
            raw["trial_artifact_authority"]
        )
    except attempts.AttemptAccountingError as exc:
        raise ControllerError("controller_trial_artifact_authority_invalid") from exc
    try:
        task = raw["task"].decode("utf-8", "strict")
        checks = raw["check_contract"].decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ControllerError("controller_text_binding_invalid") from exc
    return _Preflight(
        decision_lock=checked_lock,
        randomization_manifest=checked_schedule,
        expected_bindings=bindings,
        call_authority=call_authority,
        trial_artifact_authority=frozen_trial_authority.canonical_bytes,
        task=task,
        check_contract=checks,
    )


def replay_persisted_trial_authority(
    result: TrialRunResult,
    package: ControllerPackage,
) -> PersistedTrialAuthority:
    """Adapt the public result to the one canonical persisted-artifact replay."""

    try:
        return controller_artifacts.replay_trial_run_artifacts(
            result,
            workspace=package.paths.workspace,
            state_dir=package.paths.state_dir,
            evidence_root=package.paths.evidence_root,
        )
    except controller_artifacts.ControllerArtifactError as exc:
        raise ControllerError("controller_trial_artifact_replay_failed") from exc


def _schedule(
    attempt_id: str,
    *,
    lock: Mapping[str, Any],
    schedule: Mapping[str, Any],
) -> blinding.AttemptPackageSchedule:
    rows = schedule.get("attempts")
    if not isinstance(rows, list):
        _fail("controller_randomization_invalid")
    matching = [row for row in rows if isinstance(row, dict) and row.get("attempt_id") == attempt_id]
    if len(matching) != 1:
        _fail("controller_randomization_invalid", attempt_id)
    row = matching[0]
    return blinding.AttemptPackageSchedule(
        attempt_id=attempt_id,
        arm_order=tuple(row["arm_order"]),
        opaque_package_order=tuple(row["opaque_package_order"]),
        randomization_row_digest=decision_lock.decision_lock_digest(row),
        decision_lock_digest=decision_lock.decision_lock_digest(lock),
    )


def _call_authority_by_slot(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    prompts = value.get("prompt_manifest")
    environment = value.get("environment_lock")
    calls = prompts.get("calls") if isinstance(prompts, Mapping) else None
    chain = environment.get("executable_chain") if isinstance(environment, Mapping) else None
    if not isinstance(calls, list) or not isinstance(chain, Mapping):
        _fail("controller_call_authority_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in calls:
        if not isinstance(row, dict) or not isinstance(row.get("call_slot_id"), str):
            _fail("controller_call_authority_invalid")
        slot = row["call_slot_id"]
        if slot in result:
            _fail("controller_call_authority_invalid", slot)
        result[slot] = {**row, "executable_chain": dict(chain)}
    return result


def _receipt(value: ProviderCallResult, *, attempt_id: str, slot: str) -> dict[str, Any]:
    record = _closed_object(value.receipt, field=f"receipt.{slot}")
    if (
        record.get("block_id") != attempt_id
        or record.get("call_slot_id") != slot
        or not isinstance(record.get("session_id"), str)
        or not isinstance(record.get("provider_attempt_id"), str)
    ):
        _fail("controller_receipt_binding_invalid", slot)
    return record


def _hard_spec(value: HardEvidenceInput, request: HardEvidenceRequest) -> HardEvidenceInput:
    row = _closed_object(value.canonical_inputs, field=f"hard.{request.arm_id}")
    if value.trusted_product_freeze_status == "MISSING":
        return value
    try:
        freeze = hard_contract.derive_hard_evaluation(
            candidate_claims=row["candidate_claims"],
            evaluator_observations=row["evaluator_observations"],
            proof_rows=row["proof_rows"],
            frozen_registry=set(row["frozen_registry"]),
            trusted_product_freeze_digest=row["trusted_product_freeze_digest"],
            evaluator_identity_digest=row["evaluator_identity_digest"],
            task_identity_digest=row["task_identity_digest"],
            fixture_identity_digest=row["fixture_identity_digest"],
            frozen_proof_authority=row["frozen_proof_authority"],
        )
    except (KeyError, TypeError, ValueError, hard_contract.HardContractError) as exc:
        raise ControllerError("controller_hard_evaluation_failed", request.arm_id) from exc
    if freeze.candidate_id != request.opaque_label:
        _fail("controller_hard_evaluation_binding_invalid", request.arm_id)
    return value


def _packet_record(packet: PersistedPacket) -> dict[str, Any]:
    return dict(packet.artifact.value)


def _write_exclusive_evidence(
    path: Path,
    payload: bytes,
    *,
    code: str,
    detail: str,
) -> None:
    descriptor: int | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        parent_identity = path.parent.lstat()
        if path.parent.is_symlink() or not stat.S_ISDIR(parent_identity.st_mode):
            _fail(code, detail)
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("evidence write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        parent = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except ControllerError:
        raise
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise ControllerError(code, detail) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if path.read_bytes() != payload:
        _fail(code, detail)


def _trial_replay_binding(authority: PersistedTrialAuthority) -> dict[str, Any]:
    return {
        "run_id": authority.run_id,
        "terminal_status": authority.terminal_status,
        "trial_request_digest": authority.trial_request_digest,
        "header_row_digest": authority.header_row_digest,
        "trial_event_ledger_sha256": authority.trial_event_ledger.sha256,
        "verdict_artifact_sha256": (
            None if authority.verdict is None else authority.verdict.sha256
        ),
        "packet_artifact_index_sha256": (
            None
            if authority.packet_artifact_index is None
            else authority.packet_artifact_index.sha256
        ),
    }


def _publish_trial_prefix(
    result: TrialRunResult,
    authority: PersistedTrialAuthority,
    *,
    attempt_id: str,
    attempt_root: Path,
) -> Path:
    record = {
        "schema_version": "es.controller_trial_prefix.v1",
        "attempt_id": attempt_id,
        "trial_result": dict(result.record),
        "replay_binding": _trial_replay_binding(authority),
    }
    path = attempt_root / "trial-prefix.json"
    _write_exclusive_evidence(
        path,
        canonical_json_bytes(record) + b"\n",
        code="controller_trial_prefix_publication_failed",
        detail=attempt_id,
    )
    return path


def _read_regular_evidence(path: Path, *, code: str) -> bytes:
    try:
        identity = path.lstat()
        payload = path.read_bytes()
    except OSError as exc:
        raise ControllerError(code) from exc
    if path.is_symlink() or not stat.S_ISREG(identity.st_mode):
        _fail(code)
    return payload


def _load_trial_prefix(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    attempt_id: str,
    attempt_root: Path,
) -> tuple[TrialRunResult, PersistedTrialAuthority]:
    value = _closed_object(
        _read_regular_evidence(
            attempt_root / "trial-prefix.json",
            code="controller_trial_prefix_unreadable",
        ),
        field="trial_prefix",
        line=True,
    )
    if set(value) != {
        "schema_version",
        "attempt_id",
        "trial_result",
        "replay_binding",
    } or value.get("schema_version") != "es.controller_trial_prefix.v1":
        _fail("controller_trial_prefix_invalid")
    if value.get("attempt_id") != attempt_id:
        _fail("controller_trial_prefix_binding_mismatch")
    raw_result = value.get("trial_result")
    if not isinstance(raw_result, dict) or set(raw_result) != {
        "schema_version",
        "run_id",
        "terminal_status",
        "verdict_digest",
        "verdict_path",
        "failure_diagnostic",
    }:
        _fail("controller_trial_prefix_invalid")
    try:
        if raw_result.get("terminal_status") == "completed":
            result = TrialRunResult.completed(
                run_id=raw_result["run_id"],
                verdict_digest=raw_result["verdict_digest"],
                verdict_path=raw_result["verdict_path"],
            )
        elif raw_result.get("terminal_status") == "failed":
            failure = raw_result.get("failure_diagnostic")
            if not isinstance(failure, dict) or set(failure) != {"code", "message"}:
                _fail("controller_trial_prefix_invalid")
            result = TrialRunResult.failed(
                run_id=raw_result["run_id"],
                code=failure["code"],
                message=failure["message"],
            )
        else:
            _fail("controller_trial_prefix_invalid")
    except (KeyError, TypeError, ValueError) as exc:
        raise ControllerError("controller_trial_prefix_invalid") from exc
    if dict(result.record) != raw_result:
        _fail("controller_trial_prefix_invalid")
    try:
        authority = dependencies.replay_trial(result, package)
    except Exception as exc:
        raise ControllerError("controller_trial_prefix_replay_failed") from exc
    if type(authority) is not PersistedTrialAuthority:
        raise TypeError("replay must return exact PersistedTrialAuthority")
    if (
        authority.run_id != result.run_id
        or authority.terminal_status != result.terminal_status
        or value.get("replay_binding") != _trial_replay_binding(authority)
    ):
        _fail("controller_trial_prefix_binding_mismatch")
    return result, authority


def _review_prefix_path(attempt_root: Path, call_slot_id: str) -> Path:
    if re.fullmatch(r"[A-Z0-9_.]+", call_slot_id) is None:
        _fail("controller_review_prefix_slot_invalid", call_slot_id)
    return attempt_root / "review-prefix" / f"{call_slot_id}.json"


def _publish_review_prefix(
    row: SealedReviewRecord,
    *,
    attempt_id: str,
    allocation_sha256: str,
    attempt_root: Path,
) -> Path:
    try:
        raw_jsonl = row.raw_jsonl.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ControllerError(
            "controller_review_prefix_raw_jsonl_invalid",
            row.call_slot_id,
        ) from exc
    record = {
        "schema_version": "es.review_prefix.v1",
        "attempt_id": attempt_id,
        "call_slot_id": row.call_slot_id,
        "status": row.status,
        "allocation_sha256": allocation_sha256,
        "record": row.record,
        "receipt": _closed_object(
            row.canonical_receipt,
            field=f"receipt.{row.call_slot_id}",
        ),
        "raw_jsonl_utf8": raw_jsonl,
        "elapsed_ms": row.elapsed_ms,
    }
    payload = canonical_json_bytes(record) + b"\n"
    path = _review_prefix_path(attempt_root, row.call_slot_id)
    _write_exclusive_evidence(
        path,
        payload,
        code="controller_review_prefix_publication_failed",
        detail=row.call_slot_id,
    )
    return path


@dataclass(frozen=True, slots=True)
class _EvaluatorFixtureObservation:
    status: str
    identity: dict[str, int] | None
    sha256: str | None

    @property
    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "identity": self.identity,
            "sha256": self.sha256,
        }


def _file_identity(value: os.stat_result) -> dict[str, int]:
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
    }


def _observe_evaluator_fixture(
    package: ControllerPackage,
) -> _EvaluatorFixtureObservation | None:
    path = package.paths.workspace.joinpath(
        *_relative(
            package.evaluator_fixture.relative_path,
            field="evaluator_fixture.relative_path",
        ).parts
    )
    try:
        before = path.lstat()
    except FileNotFoundError:
        return _EvaluatorFixtureObservation("MISSING", None, None)
    except OSError:
        return _EvaluatorFixtureObservation("UNREADABLE", None, None)
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        return _EvaluatorFixtureObservation(
            "NONREGULAR",
            _file_identity(before),
            None,
        )
    try:
        if path.resolve(strict=True) != path:
            return _EvaluatorFixtureObservation(
                "IDENTITY_CHANGED",
                _file_identity(before),
                None,
            )
    except FileNotFoundError:
        return _EvaluatorFixtureObservation(
            "IDENTITY_CHANGED",
            _file_identity(before),
            None,
        )
    except (OSError, RuntimeError):
        return _EvaluatorFixtureObservation(
            "UNREADABLE",
            _file_identity(before),
            None,
        )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        path_after = path.lstat()
        resolved_after = path.resolve(strict=True)
    except FileNotFoundError:
        return _EvaluatorFixtureObservation(
            "IDENTITY_CHANGED",
            _file_identity(before),
            None,
        )
    except (OSError, RuntimeError):
        return _EvaluatorFixtureObservation(
            "UNREADABLE",
            _file_identity(before),
            None,
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
    identities = tuple(
        _file_identity(value) for value in (before, opened, after, path_after)
    )
    raw = b"".join(chunks)
    digest = _digest_bytes(raw)
    if any(identity != identities[0] for identity in identities[1:]):
        return _EvaluatorFixtureObservation(
            "IDENTITY_CHANGED",
            identities[-1],
            digest,
        )
    if resolved_after != path:
        return _EvaluatorFixtureObservation(
            "IDENTITY_CHANGED",
            identities[-1],
            digest,
        )
    if digest != package.evaluator_fixture.sha256:
        return _EvaluatorFixtureObservation(
            "DIGEST_MISMATCH",
            identities[0],
            digest,
        )
    return None


def _validated_trial_ledger(
    package: ControllerPackage,
    authority: PersistedTrialAuthority,
) -> trial_ledger.TrialEventLedger:
    path = authority.trial_event_ledger.path
    try:
        path.relative_to(package.paths.state_dir)
    except ValueError as exc:
        raise ControllerError("controller_trial_ledger_path_invalid") from exc
    if path.resolve(strict=False) != path:
        _fail("controller_trial_ledger_path_invalid")
    raw = _read_regular_evidence(
        path,
        code="controller_trial_ledger_authority_invalid",
    )
    if (
        raw != authority.trial_event_ledger.canonical_bytes
        or _digest_bytes(raw) != authority.trial_event_ledger.sha256
    ):
        _fail("controller_trial_ledger_authority_invalid")
    try:
        ledger = trial_ledger.load_trial_event_ledger(path)
    except trial_ledger.TrialLedgerError as exc:
        raise ControllerError("controller_trial_ledger_authority_invalid") from exc
    if (
        _read_regular_evidence(
            path,
            code="controller_trial_ledger_authority_invalid",
        )
        != raw
        or ledger.rows[0].row_digest != authority.header_row_digest
        or ledger.rows[0].payload.get("trial_request_digest")
        != authority.trial_request_digest
    ):
        _fail("controller_trial_ledger_authority_invalid")
    return ledger


def _common_invalidity_bindings(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    journal_path: Path,
) -> dict[str, str]:
    if package.manifest_sha256 is None:
        _fail("controller_invalidity_authority_package_unbound")
    ledger = _validated_trial_ledger(package, authority)
    expected_manifest = _build_provider_boundary_manifest(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        journal_path=journal_path,
    )
    try:
        manifest = provider_boundary.load_manifest(
            journal_path.parent / "provider-boundary.json",
            expected_sha256=expected_manifest.sha256,
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError(
            "controller_invalidity_authority_manifest_invalid"
        ) from exc
    if manifest != expected_manifest:
        _fail("controller_invalidity_authority_manifest_invalid")
    return {
        "run_id": authority.run_id,
        "trial_request_digest": authority.trial_request_digest,
        "header_row_digest": authority.header_row_digest,
        "trial_event_ledger_head_digest": ledger.rows[-1].row_digest,
        "trial_event_ledger_sha256": authority.trial_event_ledger.sha256,
        "package_manifest_sha256": package.manifest_sha256,
        "decision_lock_sha256": decision_lock.decision_lock_digest(
            preflight.decision_lock
        ),
        "provider_boundary_manifest_sha256": expected_manifest.sha256,
    }


def _post_incident_disposition_boundary(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
) -> PostIncidentDispositionRequired | None:
    if package.manifest_sha256 is None:
        return None
    if (
        trial_result.terminal_status != "failed"
        or authority.terminal_status != "failed"
        or authority.verdict is not None
        or authority.packet_artifact_index is not None
        or authority.packets
        or authority.score_ledger is not None
        or authority.score_rows
        or authority.scorer_settlement_rows
    ):
        return None
    ledger = _validated_trial_ledger(package, authority)
    cell_starts = sum(
        row.kind == "cell_allocation_started" for row in ledger.rows
    )
    if len(ledger.rows) != 1 or ledger.rows[0].kind != "header":
        return None
    if cell_starts != 0 or allocations:
        return None
    disposition_path = (
        journal_path.parent / "common-provider-outage-disposition.json"
    )
    binding = canonical_json_bytes(
        {
            "schema_version": "es.post_incident_disposition_boundary.v1",
            "attempt_id": attempt_id,
            "disposition_path": disposition_path.as_posix(),
            "bindings": _common_invalidity_bindings(
                package=package,
                preflight=preflight,
                attempt_id=attempt_id,
                authority=authority,
                journal_path=journal_path,
            ),
            "pre_treatment_proof": {
                "cell_allocation_started_count": 0,
                "provider_allocation_count": 0,
            },
        }
    )
    return PostIncidentDispositionRequired(
        attempt_id=attempt_id,
        disposition_path=disposition_path,
        binding=binding,
    )


def _publish_evaluator_invalidity_authority(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    slot: str,
    observation: _EvaluatorFixtureObservation,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
) -> bytes:
    if any(row.call_slot_id == slot for row in allocations):
        _fail("controller_evaluator_invalidity_frontier_invalid", slot)
    record = {
        "schema_version": "es.controller_invalidity_authority.v1",
        "attempt_id": attempt_id,
        "invalidity_code": "COMMON_EVALUATION_BYTES_INVALID",
        "evidence": {
            "bindings": _common_invalidity_bindings(
                package=package,
                preflight=preflight,
                attempt_id=attempt_id,
                authority=authority,
                journal_path=journal_path,
            ),
            "target_call_slot": slot,
            "evaluator_fixture": {
                "expected_path": (
                    package.paths.workspace / package.evaluator_fixture.relative_path
                ).as_posix(),
                "expected_sha256": package.evaluator_fixture.sha256,
                "observed": observation.record,
            },
            "allocation_frontier": {
                "allocation_count": len(allocations),
                "allocation_head_sha256": (
                    None if not allocations else allocations[-1].sha256
                ),
                "target_slot_allocated": False,
            },
        },
    }
    canonical = canonical_json_bytes(record)
    _write_exclusive_evidence(
        journal_path.parent / "invalidity-authority.json",
        canonical + b"\n",
        code="controller_evaluator_invalidity_publication_failed",
        detail=slot,
    )
    return canonical


def _invalidity_authority_record(
    raw: bytes,
    *,
    attempt_id: str,
    invalidity_code: str,
) -> dict[str, Any]:
    record = _closed_object(raw, field="invalidity_authority")
    if (
        set(record)
        != {"schema_version", "attempt_id", "invalidity_code", "evidence"}
        or record.get("schema_version")
        != "es.controller_invalidity_authority.v1"
        or record.get("attempt_id") != attempt_id
        or record.get("invalidity_code") != invalidity_code
        or not isinstance(record.get("evidence"), dict)
    ):
        _fail("controller_invalidity_authority_invalid", invalidity_code)
    return record


def _validate_observed_evaluator_fixture(
    value: object,
    *,
    expected_sha256: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "identity",
        "sha256",
    }:
        _fail("controller_evaluator_invalidity_authority_invalid")
    status_value = value.get("status")
    identity = value.get("identity")
    digest = value.get("sha256")
    if identity is not None and (
        not isinstance(identity, dict)
        or set(identity) != {"device", "inode", "mode", "size", "mtime_ns"}
        or any(type(item) is not int or item < 0 for item in identity.values())
    ):
        _fail("controller_evaluator_invalidity_authority_invalid")
    if digest is not None and (
        not isinstance(digest, str) or _SHA_RE.fullmatch(digest) is None
    ):
        _fail("controller_evaluator_invalidity_authority_invalid")
    if status_value == "MISSING":
        valid = identity is None and digest is None
    elif status_value == "UNREADABLE":
        valid = digest is None and (
            identity is None
            or (isinstance(identity, dict) and stat.S_ISREG(identity["mode"]))
        )
    elif status_value == "NONREGULAR":
        valid = (
            isinstance(identity, dict)
            and not stat.S_ISREG(identity["mode"])
            and digest is None
        )
    elif status_value == "IDENTITY_CHANGED":
        valid = isinstance(identity, dict)
    elif status_value == "DIGEST_MISMATCH":
        valid = (
            isinstance(identity, dict)
            and stat.S_ISREG(identity["mode"])
            and isinstance(digest, str)
            and digest != expected_sha256
        )
    else:
        valid = False
    if not valid:
        _fail("controller_evaluator_invalidity_authority_invalid")


def _validate_evaluator_invalidity_authority(
    raw: bytes,
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
    review_records: tuple[SealedReviewRecord, ...],
    material_disagreement: bool,
) -> _AttemptClassifierAuthority:
    record = _invalidity_authority_record(
        raw,
        attempt_id=attempt_id,
        invalidity_code="COMMON_EVALUATION_BYTES_INVALID",
    )
    evidence = record["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {
        "bindings",
        "target_call_slot",
        "evaluator_fixture",
        "allocation_frontier",
    }:
        _fail("controller_evaluator_invalidity_authority_invalid")
    if evidence.get("bindings") != _common_invalidity_bindings(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
    ):
        _fail("controller_evaluator_invalidity_authority_invalid")
    target = evidence.get("target_call_slot")
    valid_targets = _CONTROLLER_REVIEW_SLOTS | {
        f"HARD.{arm}" for arm in ARMS
    }
    if not isinstance(target, str) or target not in valid_targets:
        _fail("controller_evaluator_invalidity_authority_invalid")
    fixture = evidence.get("evaluator_fixture")
    expected_path = (
        package.paths.workspace / package.evaluator_fixture.relative_path
    ).as_posix()
    if (
        not isinstance(fixture, dict)
        or set(fixture) != {"expected_path", "expected_sha256", "observed"}
        or fixture.get("expected_path") != expected_path
        or fixture.get("expected_sha256") != package.evaluator_fixture.sha256
    ):
        _fail("controller_evaluator_invalidity_authority_invalid")
    _validate_observed_evaluator_fixture(
        fixture.get("observed"),
        expected_sha256=package.evaluator_fixture.sha256,
    )
    frontier = evidence.get("allocation_frontier")
    expected_frontier = {
        "allocation_count": len(allocations),
        "allocation_head_sha256": (
            None if not allocations else allocations[-1].sha256
        ),
        "target_slot_allocated": False,
    }
    if frontier != expected_frontier or any(
        row.call_slot_id == target for row in allocations
    ):
        _fail("controller_evaluator_invalidity_frontier_invalid")
    initial_slots = (
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    expected_prior: tuple[str, ...]
    if target == initial_slots[0]:
        expected_prior = ()
    elif target == initial_slots[1]:
        expected_prior = initial_slots[:1]
    elif target == "EVAL.ADJUDICATOR":
        expected_prior = initial_slots
    elif target == "EVAL.INTEGRATED_REVIEW":
        expected_prior = initial_slots + (
            ("EVAL.ADJUDICATOR",) if material_disagreement else ()
        )
    else:
        expected_prior = initial_slots + (
            ("EVAL.ADJUDICATOR",) if material_disagreement else ()
        )
    if tuple(row.call_slot_id for row in review_records) != expected_prior:
        _fail("controller_evaluator_invalidity_frontier_invalid")
    return _evaluation_classifier_authority(raw)


def _load_evaluator_invalidity_authority(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
    review_records: tuple[SealedReviewRecord, ...],
    material_disagreement: bool,
) -> _AttemptClassifierAuthority | None:
    path = journal_path.parent / "invalidity-authority.json"
    if not path.exists():
        return None
    raw = _read_regular_evidence(
        path,
        code="controller_evaluator_invalidity_authority_invalid",
    )
    record = _closed_object(raw, field="invalidity_authority", line=True)
    canonical = canonical_json_bytes(record)
    return _validate_evaluator_invalidity_authority(
        canonical,
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
        allocations=allocations,
        review_records=review_records,
        material_disagreement=material_disagreement,
    )


def _validate_owner_adoption_timestamp(value: object) -> None:
    if not isinstance(value, str):
        _fail("controller_outage_disposition_owner_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControllerError(
            "controller_outage_disposition_owner_invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("controller_outage_disposition_owner_invalid")


def _validate_outage_disposition_authority(
    raw: bytes,
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
) -> _AttemptClassifierAuthority:
    record = _invalidity_authority_record(
        raw,
        attempt_id=attempt_id,
        invalidity_code="COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
    )
    if (
        trial_result.terminal_status != "failed"
        or authority.terminal_status != "failed"
        or authority.verdict is not None
        or authority.packet_artifact_index is not None
        or authority.packets
        or authority.score_ledger is not None
        or authority.score_rows
        or authority.scorer_settlement_rows
        or allocations
    ):
        _fail("controller_outage_disposition_prefix_invalid")
    ledger = _validated_trial_ledger(package, authority)
    if (
        len(ledger.rows) != 1
        or ledger.rows[0].kind != "header"
        or any(row.kind == "cell_allocation_started" for row in ledger.rows)
    ):
        _fail("controller_outage_disposition_prefix_invalid")
    evidence = record["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {
        "bindings",
        "pre_treatment_proof",
        "evidence_status",
        "authorized_disposition",
        "owner",
        "owner_adoption",
    }:
        _fail("controller_outage_disposition_invalid")
    if evidence.get("bindings") != _common_invalidity_bindings(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
    ):
        _fail("controller_outage_disposition_binding_invalid")
    if evidence.get("pre_treatment_proof") != {
        "cell_allocation_started_count": 0,
        "provider_allocation_count": 0,
    }:
        _fail("controller_outage_disposition_prefix_invalid")
    if (
        evidence.get("evidence_status") != "owner_confirmed"
        or evidence.get("authorized_disposition")
        != "classify_common_provider_outage_before_treatment"
    ):
        _fail("controller_outage_disposition_invalid")
    owner = evidence.get("owner")
    if (
        not isinstance(owner, dict)
        or set(owner) != {"name", "role"}
        or any(
            not isinstance(owner.get(field), str) or not owner[field].strip()
            for field in ("name", "role")
        )
    ):
        _fail("controller_outage_disposition_owner_invalid")
    adoption = evidence.get("owner_adoption")
    if (
        not isinstance(adoption, dict)
        or set(adoption) != {"adopted_at", "statement"}
        or adoption.get("statement")
        != (
            "I confirm the shared provider was unavailable before any treatment "
            "began and personally adopt this exact bound attempt as "
            "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT."
        )
    ):
        _fail("controller_outage_disposition_owner_invalid")
    _validate_owner_adoption_timestamp(adoption.get("adopted_at"))
    return _outage_classifier_authority(raw)


def _load_outage_disposition_authority(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
) -> _AttemptClassifierAuthority | None:
    path = journal_path.parent / "common-provider-outage-disposition.json"
    expected = dependencies.common_provider_outage_disposition_sha256
    if expected is None:
        if path.exists():
            _fail("controller_outage_disposition_binding_required")
        return None
    raw = _read_regular_evidence(
        path,
        code="controller_outage_disposition_unreadable",
    )
    if _digest_bytes(raw) != expected:
        _fail("controller_outage_disposition_digest_mismatch")
    record = _closed_object(raw, field="outage_disposition", line=True)
    return _validate_outage_disposition_authority(
        canonical_json_bytes(record),
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=trial_result,
        authority=authority,
        journal_path=journal_path,
        allocations=allocations,
    )


def _guard_evaluator_fixture(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    target: str,
    allocations: tuple[provider_boundary.AllocationEvent, ...],
) -> None:
    observation = _observe_evaluator_fixture(package)
    if observation is None:
        return
    frozen = _publish_evaluator_invalidity_authority(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
        slot=target,
        observation=observation,
        allocations=allocations,
    )
    raise _CommonEvaluationBytesInvalid(
        _evaluation_classifier_authority(frozen)
    )


def _review_call(
    *,
    package: ControllerPackage,
    deps: ControllerDependencies,
    preflight: _Preflight,
    journal_path: Path,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    slot: str,
    kind: str,
    perspective: str | None,
    presentation_order: tuple[str, ...],
    prior: tuple[SealedReviewRecord, ...],
    hard_evidence: tuple[tuple[str, HardEvidenceInput], ...],
) -> SealedReviewRecord:
    decision_lock_sha256 = decision_lock.decision_lock_digest(
        preflight.decision_lock
    )
    try:
        existing_allocations = (
            provider_boundary.load_allocation_journal(
                journal_path,
                attempt_id=attempt_id,
                decision_lock_sha256=decision_lock_sha256,
            )
            if journal_path.exists()
            else ()
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_allocation_journal_invalid") from exc
    attempts.enforce_absolute_call_ceiling(
        (*package.consumed_attempt_call_counts, len(existing_allocations) + 1),
        invalid_attempt_count=package.invalid_attempt_count,
        decision_lock=preflight.decision_lock,
        randomization_manifest=preflight.randomization_manifest,
        expected_bindings=preflight.expected_bindings,
    )
    static = _call_authority_by_slot(preflight.call_authority).get(slot)
    if static is None:
        _fail("controller_call_authority_missing", slot)
    _guard_evaluator_fixture(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
        target=slot,
        allocations=existing_allocations,
    )
    try:
        publication = provider_boundary.publish_allocation(
            journal_path,
            attempt_id=attempt_id,
            decision_lock_sha256=decision_lock_sha256,
            call_slot_id=slot,
            static_call_sha256=canonical_sha256(static),
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_allocation_publish_failed", slot) from exc
    canonical_event = canonical_json_bytes(publication.record)
    request = ReviewCallRequest(
        attempt_id=attempt_id,
        call_slot_id=slot,
        review_kind=kind,
        perspective_id=perspective,
        presentation_order=presentation_order,
        packet_paths=tuple(packet.relative_path for packet in authority.packets),
        prior_records=tuple(row.canonical_record for row in prior),
        hard_evidence=tuple(value.canonical_inputs for _arm, value in hard_evidence),
        allocation_event=canonical_event,
        allocation_event_path=journal_path,
    )
    try:
        outcome = deps.call_provider(request)
    except Exception as exc:
        raise _ProviderCallInterrupted(
            "controller_provider_call_interrupted",
            slot,
        ) from exc
    if type(outcome) is not ProviderCallResult:
        raise TypeError("provider call must return exact ProviderCallResult")
    receipt = _receipt(outcome, attempt_id=attempt_id, slot=slot)
    receipt_digest = _evidence_digest(receipt)
    citable = {
        packet.opaque_label: tuple(_packet_record(packet)["citable_item_ids"])
        for packet in authority.packets
    }
    packet_index = authority.packet_index_record
    if packet_index is None:
        _fail("controller_completed_trial_packet_index_missing")
    status = outcome.status
    if status == "SUCCEEDED":
        assert outcome.payload is not None
        try:
            payload = _json_value(outcome.payload, field=f"payload.{slot}")
            record = reviews.seal_review_record(
                payload,
                attempt_id=attempt_id,
                review_kind=kind,
                perspective_id=perspective,
                session_id=str(receipt["session_id"]),
                provider_attempt_id=str(receipt["provider_attempt_id"]),
                receipt_digest=receipt_digest,
                packet_set_digest=str(packet_index["packet_set_digest"]),
                presentation_order=presentation_order,
                citable_item_ids_by_label=citable,
                existing_records=tuple(row.record for row in prior),
            )
        except (ControllerError, reviews.ReviewContractError):
            status = "FAILED"
            record = {
                "schema_version": "es_evaluator_call_failure.v1",
                "attempt_id": attempt_id,
                "call_slot_id": slot,
                "session_id": receipt["session_id"],
                "provider_attempt_id": receipt["provider_attempt_id"],
                "receipt_digest": receipt_digest,
                "failure_code": "PROVIDER_TYPED_OUTPUT_INVALID",
            }
    else:
        record = {
            "schema_version": "es_evaluator_call_failure.v1",
            "attempt_id": attempt_id,
            "call_slot_id": slot,
            "session_id": receipt["session_id"],
            "provider_attempt_id": receipt["provider_attempt_id"],
            "receipt_digest": receipt_digest,
            "failure_code": outcome.failure_code,
        }
    event = publication.record
    allocation = {
        "schema_version": "es.call_allocation.v2",
        "call_slot_id": slot,
        "allocation_authority": event,
        "allocation_sha256": canonical_sha256(event),
        "settlement": "RECEIPT_FROZEN",
        "receipt_sha256": receipt_digest,
    }
    sealed = SealedReviewRecord(
        call_slot_id=slot,
        status=status,
        canonical_record=canonical_json_bytes(record),
        canonical_receipt=canonical_json_bytes(receipt),
        raw_jsonl=outcome.raw_jsonl,
        elapsed_ms=outcome.elapsed_ms,
        allocation_event=canonical_event,
        allocation_path=journal_path,
        call_allocation=canonical_json_bytes(allocation),
    )
    _publish_review_prefix(
        sealed,
        attempt_id=attempt_id,
        allocation_sha256=publication.sha256,
        attempt_root=journal_path.parent,
    )
    try:
        provider_boundary.publish_settlement(
            journal_path.with_name("call-settlements.jsonl"),
            allocation_journal_path=journal_path,
            allocation=publication,
            receipt_bytes=canonical_json_bytes(receipt) + b"\n",
            elapsed_ms=outcome.elapsed_ms,
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_settlement_publish_failed", slot) from exc
    return sealed


def canonical_finalize_attempt(assembly: AttemptAssembly) -> FinalizedAttempt:
    """Settle one attempt from only its frozen package and durable evidence."""

    return _canonical_finalize_attempt_impl(assembly)


_INITIAL_REVIEW_SLOTS = (
    "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
    "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
)

_CONTROLLER_REVIEW_SLOTS = frozenset(
    {
        *_INITIAL_REVIEW_SLOTS,
        "EVAL.ADJUDICATOR",
        "EVAL.INTEGRATED_REVIEW",
    }
)

_CONTROLLER_REVIEW_CONTRACT = {
    "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS": (
        reviews.INITIAL,
        reviews.SCIENTIFIC_APPLICATION_SEMANTICS,
    ),
    "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY": (
        reviews.INITIAL,
        reviews.API_PERSISTENCE_MIGRATION_MAINTAINABILITY,
    ),
    "EVAL.ADJUDICATOR": (reviews.ADJUDICATOR, None),
    "EVAL.INTEGRATED_REVIEW": (reviews.INTEGRATED, None),
}


def _review_prefix_inventory(attempt_root: Path) -> dict[str, Path]:
    root = attempt_root / "review-prefix"
    if not root.exists():
        return {}
    try:
        identity = root.lstat()
        children = tuple(root.iterdir())
    except OSError as exc:
        raise ControllerError("controller_review_prefix_inventory_invalid") from exc
    if root.is_symlink() or not stat.S_ISDIR(identity.st_mode):
        _fail("controller_review_prefix_inventory_invalid")
    result: dict[str, Path] = {}
    for path in children:
        try:
            child_identity = path.lstat()
        except OSError as exc:
            raise ControllerError(
                "controller_review_prefix_inventory_invalid"
            ) from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(child_identity.st_mode)
            or path.suffix != ".json"
            or path.stem not in _CONTROLLER_REVIEW_SLOTS
            or path.stem in result
        ):
            _fail("controller_review_prefix_inventory_invalid")
        result[path.stem] = path
    return result


def _load_review_prefixes(
    *,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
    journal_path: Path,
) -> tuple[SealedReviewRecord, ...]:
    decision_lock_sha256 = decision_lock.decision_lock_digest(
        preflight.decision_lock
    )
    try:
        settlement_path = journal_path.with_name("call-settlements.jsonl")
        allocations = (
            provider_boundary.load_allocation_journal(
                journal_path,
                attempt_id=attempt_id,
                decision_lock_sha256=decision_lock_sha256,
            )
            if journal_path.exists()
            else ()
        )
        settlements = (
            provider_boundary.load_settlement_journal(
                settlement_path,
                allocation_journal_path=journal_path,
                attempt_id=attempt_id,
                decision_lock_sha256=decision_lock_sha256,
            )
            if settlement_path.exists()
            else ()
        )
        if settlements and not allocations:
            _fail("controller_attempt_prefix_journal_invalid")
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_attempt_prefix_journal_invalid") from exc
    call_authority = _call_authority_by_slot(preflight.call_authority)
    for allocation in allocations:
        static = call_authority.get(allocation.call_slot_id)
        if static is None or allocation.static_call_sha256 != canonical_sha256(static):
            _fail("controller_attempt_prefix_allocation_invalid")
    settlements_by_slot = {row.call_slot_id: row for row in settlements}
    inventory = _review_prefix_inventory(journal_path.parent)
    review_allocations = tuple(
        row for row in allocations if row.call_slot_id in _CONTROLLER_REVIEW_SLOTS
    )
    citable = {
        packet.opaque_label: tuple(_packet_record(packet)["citable_item_ids"])
        for packet in authority.packets
    }
    result: list[SealedReviewRecord] = []
    validated_inventory: set[str] = set()
    missing_seen = False
    for allocation in review_allocations:
        slot = allocation.call_slot_id
        path = inventory.get(slot)
        if path is None:
            if slot in settlements_by_slot:
                _fail("controller_review_prefix_settlement_mismatch", slot)
            if any(row.sequence > allocation.sequence for row in allocations):
                _fail("controller_review_prefix_noncontiguous", slot)
            missing_seen = True
            continue
        if missing_seen:
            _fail("controller_review_prefix_noncontiguous", slot)
        validated_inventory.add(slot)
        wrapper = _closed_object(
            _read_regular_evidence(
                path,
                code="controller_review_prefix_unreadable",
            ),
            field=f"review_prefix.{slot}",
            line=True,
        )
        if set(wrapper) != {
            "schema_version",
            "attempt_id",
            "call_slot_id",
            "status",
            "allocation_sha256",
            "record",
            "receipt",
            "raw_jsonl_utf8",
            "elapsed_ms",
        } or wrapper.get("schema_version") != "es.review_prefix.v1":
            _fail("controller_review_prefix_invalid", slot)
        if (
            wrapper.get("attempt_id") != attempt_id
            or wrapper.get("call_slot_id") != slot
            or wrapper.get("allocation_sha256") != allocation.sha256
            or wrapper.get("status") not in {"SUCCEEDED", "FAILED"}
            or type(wrapper.get("elapsed_ms")) is not int
            or wrapper["elapsed_ms"] < 0
            or not isinstance(wrapper.get("raw_jsonl_utf8"), str)
            or not isinstance(wrapper.get("receipt"), dict)
            or not isinstance(wrapper.get("record"), dict)
        ):
            _fail("controller_review_prefix_binding_mismatch", slot)
        receipt = wrapper["receipt"]
        record = wrapper["record"]
        assert isinstance(receipt, dict)
        assert isinstance(record, dict)
        receipt_digest = _evidence_digest(receipt)
        if (
            receipt.get("block_id") != attempt_id
            or receipt.get("call_slot_id") != slot
            or not isinstance(receipt.get("session_id"), str)
            or not isinstance(receipt.get("provider_attempt_id"), str)
            or type(receipt.get("exit_status")) is not int
        ):
            _fail("controller_review_prefix_receipt_invalid", slot)
        settlement = settlements_by_slot.get(slot)
        if settlement is not None and (
            settlement.allocation_sha256 != allocation.sha256
            or settlement.receipt_sha256 != receipt_digest
            or settlement.elapsed_ms != wrapper["elapsed_ms"]
            or settlement.exit_status != receipt["exit_status"]
        ):
            _fail("controller_review_prefix_settlement_mismatch", slot)
        prior_records = tuple(row.record for row in result)
        if wrapper["status"] == "SUCCEEDED":
            expected_kind, expected_perspective = _CONTROLLER_REVIEW_CONTRACT[slot]
            try:
                validated = reviews.validate_review_record(
                    record,
                    citable_item_ids_by_label=citable,
                    existing_records=prior_records,
                )
            except reviews.ReviewContractError as exc:
                raise ControllerError("controller_review_prefix_record_invalid", slot) from exc
            if (
                validated != record
                or record.get("attempt_id") != attempt_id
                or record.get("review_kind") != expected_kind
                or record.get("perspective_id") != expected_perspective
                or record.get("session_id") != receipt["session_id"]
                or record.get("provider_attempt_id")
                != receipt["provider_attempt_id"]
                or record.get("receipt_digest") != receipt_digest
            ):
                _fail("controller_review_prefix_record_invalid", slot)
        else:
            if set(record) != {
                "schema_version",
                "attempt_id",
                "call_slot_id",
                "session_id",
                "provider_attempt_id",
                "receipt_digest",
                "failure_code",
            } or (
                record.get("schema_version") != "es_evaluator_call_failure.v1"
                or record.get("attempt_id") != attempt_id
                or record.get("call_slot_id") != slot
                or record.get("session_id") != receipt["session_id"]
                or record.get("provider_attempt_id")
                != receipt["provider_attempt_id"]
                or record.get("receipt_digest") != receipt_digest
                or not isinstance(record.get("failure_code"), str)
                or _FAILURE_RE.fullmatch(record["failure_code"]) is None
            ):
                _fail("controller_review_prefix_record_invalid", slot)
        if settlement is None:
            if any(row.sequence > allocation.sequence for row in allocations):
                _fail("controller_review_prefix_noncontiguous", slot)
            missing_seen = True
            continue
        allocation_record = {
            "schema_version": "es.call_allocation.v2",
            "call_slot_id": slot,
            "allocation_authority": allocation.record,
            "allocation_sha256": allocation.sha256,
            "settlement": "RECEIPT_FROZEN",
            "receipt_sha256": receipt_digest,
        }
        result.append(
            SealedReviewRecord(
                call_slot_id=slot,
                status=wrapper["status"],
                canonical_record=canonical_json_bytes(record),
                canonical_receipt=canonical_json_bytes(receipt),
                raw_jsonl=wrapper["raw_jsonl_utf8"].encode("utf-8", "strict"),
                elapsed_ms=wrapper["elapsed_ms"],
                allocation_event=canonical_json_bytes(allocation.record),
                allocation_path=journal_path,
                call_allocation=canonical_json_bytes(allocation_record),
            )
        )
    if set(inventory) != validated_inventory:
        _fail("controller_review_prefix_inventory_invalid")
    return tuple(result)


def _build_provider_boundary_manifest(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    journal_path: Path,
) -> provider_boundary.BoundaryManifest:
    by_slot = _call_authority_by_slot(preflight.call_authority)
    route = preflight.decision_lock.get("route_contract")
    locked_slots = route.get("receipt_call_slots") if isinstance(route, Mapping) else None
    if (
        not isinstance(locked_slots, list)
        or any(not isinstance(slot, str) for slot in locked_slots)
        or not _CONTROLLER_REVIEW_SLOTS.issubset(locked_slots)
    ):
        _fail("controller_call_authority_invalid")
    public_slots = tuple(
        slot for slot in locked_slots if slot not in _CONTROLLER_REVIEW_SLOTS
    )
    if not public_slots or any(slot not in by_slot for slot in public_slots):
        _fail("controller_call_authority_invalid")
    outer_argv = (
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        package.model,
        "--config",
        f"reasoning_effort={package.effort}",
    )
    calls: list[provider_boundary.BoundaryCall] = []
    for ordinal, slot in enumerate(locked_slots, start=1):
        if slot not in public_slots:
            continue
        static = by_slot[slot]
        normalized_argv = static.get("normalized_argv")
        output_bundle_path = static.get("output_bundle_path")
        provider_attempt_site_key = static.get("provider_attempt_site_key")
        scorer = slot.startswith("EVAL.SCORER_")
        if (
            "output_bundle_path" not in static
            or "provider_attempt_site_key" not in static
            or not isinstance(normalized_argv, list)
            or any(not isinstance(value, str) for value in normalized_argv)
            or (scorer and output_bundle_path is not None)
            or (not scorer and not isinstance(output_bundle_path, str))
            or (scorer and provider_attempt_site_key is not None)
            or (
                not scorer
                and not isinstance(provider_attempt_site_key, str)
            )
        ):
            _fail("controller_call_authority_invalid", slot)
        slug = slot.lower().replace(".", "-").replace("_", "-")
        prefix = f"attempts/{attempt_id}"
        try:
            call = provider_boundary.BoundaryCall(
                call_slot_id=slot,
                role_id=str(static["role_id"]),
                cwd_selector=provider_boundary.CwdSelector.under(
                    package.paths.state_dir if scorer else package.paths.run_ref_root
                ),
                output_bundle_path=output_bundle_path,
                provider_attempt_site_key=provider_attempt_site_key,
                prompt_sha256s=tuple(static["prompt_sha256s"]),
                contract_sha256=str(static["contract_sha256"]),
                outer_argv=outer_argv,
                metered_argv=tuple(normalized_argv),
                static_call_sha256=canonical_sha256(static),
                provider_attempt_id=f"{attempt_id}-provider-{ordinal:02d}",
                raw_jsonl_path=f"{prefix}/raw/{ordinal:02d}-{slug}.jsonl",
                receipt_path=f"{prefix}/receipts/{ordinal:02d}-{slug}.json",
                expected_session_id=None,
            )
        except (KeyError, provider_boundary.ProviderBoundaryError) as exc:
            raise ControllerError("controller_call_authority_invalid", slot) from exc
        calls.append(call)
    return provider_boundary.BoundaryManifest(
        study_id="F1-ES",
        attempt_id=attempt_id,
        decision_lock_sha256=decision_lock.decision_lock_digest(
            preflight.decision_lock
        ),
        evidence_root=package.paths.evidence_root,
        journal_path=journal_path,
        settlement_journal_path=journal_path.with_name("call-settlements.jsonl"),
        calls=tuple(calls),
    )


def _publish_provider_boundary(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    journal_path: Path,
) -> dict[str, str]:
    attempt_root = journal_path.parent
    manifest = _build_provider_boundary_manifest(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        journal_path=journal_path,
    )
    try:
        publication = provider_boundary.write_manifest_exclusive(
            attempt_root / "provider-boundary.json",
            manifest,
        )
        shim = provider_boundary.install_path_shim(
            attempt_root / "provider-shim"
        )
        inherited_path = os.environ.get("PATH")
        if not inherited_path:
            _fail("controller_provider_environment_invalid")
        return provider_boundary.boundary_environment(
            shim_dir=shim.parent,
            manifest=publication,
            inherited_path=inherited_path,
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_provider_boundary_publication_failed") from exc


def _settled_controller_result(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult | None,
    finalized: FinalizedAttempt,
) -> ControllerResult:
    if type(finalized) is not FinalizedAttempt:
        raise TypeError("finalizer must return exact FinalizedAttempt")
    expected_next: str | None = None
    if not finalized.stopped:
        expected_next = attempts.select_next_attempt_id(
            (*package.consumed_attempt_ids, attempt_id),
            decision_lock=preflight.decision_lock,
            randomization_manifest=preflight.randomization_manifest,
            expected_bindings=preflight.expected_bindings,
        )
        if finalized.next_attempt_id != expected_next:
            _fail("controller_next_attempt_mismatch")
    return ControllerResult(
        attempt_id=attempt_id,
        trial_result=trial_result,
        attempt_record=finalized.attempt_record,
        attempt_index=finalized.attempt_index,
        attempt_index_sha256=finalized.attempt_index_sha256,
        report=finalized.report,
        stopped=finalized.stopped,
        next_attempt_id=expected_next,
    )


def _finalize_preallocation_failure(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    preflight: _Preflight,
    attempt_id: str,
    journal_path: Path,
) -> ControllerResult:
    finalized = dependencies.finalize_attempt(
        AttemptAssembly(
            attempt_id=attempt_id,
            package=package,
            trial_result=None,
            authority=None,
            private_join=None,
            review_records=(),
            adjudication_payload=None,
            hard_evidence=(),
            integrated_payload=None,
            material_disagreement=False,
            classifier_authority=_valid_classifier_authority(),
            journal_path=journal_path,
        )
    )
    return _settled_controller_result(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=None,
        finalized=finalized,
    )


def _finalize_interrupted_provider_call(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult,
    authority: PersistedTrialAuthority,
    private_join: blinding.PrivateBlindingJoin,
    review_records: Sequence[SealedReviewRecord],
    adjudication_payload: bytes | None,
    hard_evidence: Sequence[tuple[str, HardEvidenceInput]],
    material_disagreement: bool,
    journal_path: Path,
) -> ControllerResult:
    """Consume an attempt whose allocated provider call did not return."""

    finalized = dependencies.finalize_attempt(
        AttemptAssembly(
            attempt_id=attempt_id,
            package=package,
            trial_result=trial_result,
            authority=authority,
            private_join=private_join,
            review_records=tuple(review_records),
            adjudication_payload=adjudication_payload,
            hard_evidence=tuple(hard_evidence),
            integrated_payload=None,
            material_disagreement=material_disagreement,
            classifier_authority=_valid_classifier_authority(),
            journal_path=journal_path,
        )
    )
    return _settled_controller_result(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=trial_result,
        finalized=finalized,
    )


def _finalize_common_invalidity(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult,
    authority: PersistedTrialAuthority,
    private_join: blinding.PrivateBlindingJoin | None,
    review_records: Sequence[SealedReviewRecord],
    adjudication_payload: bytes | None,
    hard_evidence: Sequence[tuple[str, HardEvidenceInput]],
    material_disagreement: bool,
    classifier_authority: _AttemptClassifierAuthority,
    journal_path: Path,
) -> ControllerResult:
    if classifier_authority.invalidity_code not in {
        "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
        "COMMON_EVALUATION_BYTES_INVALID",
    }:
        _fail("controller_common_invalidity_classifier_invalid")
    finalized = dependencies.finalize_attempt(
        AttemptAssembly(
            attempt_id=attempt_id,
            package=package,
            trial_result=trial_result,
            authority=authority,
            private_join=private_join,
            review_records=tuple(review_records),
            adjudication_payload=adjudication_payload,
            hard_evidence=tuple(hard_evidence),
            integrated_payload=None,
            material_disagreement=material_disagreement,
            classifier_authority=classifier_authority,
            journal_path=journal_path,
        )
    )
    return _settled_controller_result(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=trial_result,
        finalized=finalized,
    )


def _finalize_blinding_join_invalid(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    preflight: _Preflight,
    attempt_id: str,
    trial_result: TrialRunResult,
    authority: PersistedTrialAuthority,
    journal_path: Path,
    error: blinding.BlindingJoinError,
) -> ControllerResult:
    finalized = dependencies.finalize_attempt(
        AttemptAssembly(
            attempt_id=attempt_id,
            package=package,
            trial_result=trial_result,
            authority=authority,
            private_join=None,
            review_records=(),
            adjudication_payload=None,
            hard_evidence=(),
            integrated_payload=None,
            material_disagreement=False,
            classifier_authority=_blinding_classifier_authority(error),
            journal_path=journal_path,
        )
    )
    return _settled_controller_result(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=trial_result,
        finalized=finalized,
    )


def _private_join_projection(
    *,
    package: ControllerPackage,
    preflight: _Preflight,
    attempt_id: str,
    authority: PersistedTrialAuthority,
) -> tuple[blinding.PrivateBlindingJoin, tuple[str, ...]]:
    packet_index = authority.packet_index_record
    if packet_index is None:
        _fail("controller_completed_trial_packet_index_missing")
    schedule = _schedule(
        attempt_id,
        lock=preflight.decision_lock,
        schedule=preflight.randomization_manifest,
    )
    private_join = blinding.build_private_blinding_join(
        attempt=schedule,
        randomization_manifest=preflight.randomization_manifest,
        decision_lock=preflight.decision_lock,
        expected_bindings=preflight.expected_bindings,
        request_cell_domain=authority.cell_domain,
        sealed_opaque_labels=authority.sealed_opaque_labels,
        packet_index=packet_index,
    )
    projection = blinding.build_public_review_projection(private_join)
    return private_join, tuple(
        packet.opaque_label for packet in projection.packets
    )


@dataclass(frozen=True, slots=True)
class _FinalizerEvidence:
    allocations: tuple[provider_boundary.AllocationEvent, ...]
    provider: tuple[controller_artifacts.ProviderEvidenceInput, ...]
    reviews: tuple[controller_artifacts.ReviewEvidenceInput, ...]
    receipt_bindings: tuple[bytes, ...]
    review_settlements: tuple[bytes, ...]
    call_allocations: tuple[bytes, ...]


def _arm_terminal_status_by_arm(
    authority: PersistedTrialAuthority,
) -> dict[str, str]:
    """Project the validated immutable evidence freeze into arm outcomes."""

    if type(authority) is not PersistedTrialAuthority:
        raise TypeError("authority must be exact PersistedTrialAuthority")
    records = tuple(
        _closed_object(
            line,
            field="trial_event_ledger_row",
            line=True,
        )
        for line in authority.trial_event_ledger.canonical_bytes.splitlines(
            keepends=True
        )
    )
    freezes = tuple(row for row in records if row.get("kind") == "evidence_frozen")
    if not freezes:
        return {}
    if len(freezes) != 1:
        _fail("controller_terminal_status_authority_invalid")
    payload = freezes[0].get("payload")
    if not isinstance(payload, Mapping):
        _fail("controller_terminal_status_authority_invalid")
    evidence = payload.get("cell_evidence")
    if not isinstance(evidence, list):
        _fail("controller_terminal_status_authority_invalid")
    statuses: dict[str, str] = {}
    for row in evidence:
        if not isinstance(row, Mapping):
            _fail("controller_terminal_status_authority_invalid")
        cell = row.get("cell")
        status = row.get("status")
        if (
            not isinstance(cell, Mapping)
            or cell.get("arm_id") not in ARMS
            or cell.get("rep") != 1
            or status not in {"completed", "failed"}
            or cell["arm_id"] in statuses
        ):
            _fail("controller_terminal_status_authority_invalid")
        statuses[str(cell["arm_id"])] = str(status)
    if set(statuses) != set(ARMS):
        _fail("controller_terminal_status_authority_invalid")
    return statuses


def _selected_routes(
    *,
    preflight: _Preflight,
    allocations: Sequence[provider_boundary.AllocationEvent],
    arm_terminal_status_by_arm: Mapping[str, object] | None = None,
    evaluation_adjudication: bool | None = None,
) -> tuple[tuple[tuple[str, str], ...], str | None]:
    contract = preflight.decision_lock.get("route_contract")
    if not isinstance(contract, Mapping):
        _fail("controller_route_contract_invalid")
    arms = contract.get("arms")
    terminal = contract.get("terminal_routes")
    evaluations = contract.get("evaluation_routes")
    if (
        arms != list(ARMS)
        or not isinstance(terminal, list)
        or not isinstance(evaluations, list)
    ):
        _fail("controller_route_contract_invalid")
    statuses = (
        {}
        if arm_terminal_status_by_arm is None
        else arm_terminal_status_by_arm
    )
    if (
        not isinstance(statuses, Mapping)
        or any(arm not in ARMS for arm in statuses)
        or any(status not in {"completed", "failed"} for status in statuses.values())
    ):
        _fail("controller_terminal_status_authority_invalid")
    if (
        evaluation_adjudication is not None
        and type(evaluation_adjudication) is not bool
    ):
        _fail("controller_evaluation_route_adjudication_invalid")
    observed_slots = tuple(row.call_slot_id for row in allocations)
    routes: list[tuple[str, str]] = []
    for arm in ARMS:
        candidates = tuple(
            row
            for row in terminal
            if isinstance(row, Mapping) and row.get("arm") == arm
        )
        legal = {
            slot
            for row in candidates
            for slot in row.get("call_slots", [])
            if isinstance(slot, str)
        }
        observed = tuple(slot for slot in observed_slots if slot in legal)
        sequence_matching = tuple(
            row
            for row in candidates
            if isinstance(row.get("call_slots"), list)
            and tuple(row["call_slots"]) == observed
            and isinstance(row.get("route_id"), str)
        )
        status = statuses.get(arm)
        matching = tuple(
            row
            for row in sequence_matching
            if status is None
            or row.get("completed") is (status == "completed")
        )
        if not any(
            isinstance(row.get("call_slots"), list)
            and tuple(row["call_slots"][: len(observed)]) == observed
            for row in candidates
        ):
            _fail("controller_terminal_route_sequence_invalid", arm)
        if sequence_matching and status is not None and not matching:
            _fail("controller_terminal_route_outcome_invalid", arm)
        if len(matching) > 1:
            _fail("controller_terminal_route_ambiguous", arm)
        if matching:
            routes.append((arm, str(matching[0]["route_id"])))
    evaluation_legal = {
        slot
        for row in evaluations
        if isinstance(row, Mapping)
        for slot in row.get("call_slots", [])
        if isinstance(slot, str)
    }
    observed_evaluation = tuple(
        slot for slot in observed_slots if slot in evaluation_legal
    )

    def evaluation_sequence_matches(
        row: Mapping[str, object],
        *,
        exact: bool,
    ) -> bool:
        raw_slots = row.get("call_slots")
        if not isinstance(raw_slots, list) or not all(
            isinstance(slot, str) for slot in raw_slots
        ):
            return False
        locked = tuple(raw_slots)
        scorer_count = len(ARMS)
        if len(locked) < scorer_count:
            return False
        if len(observed_evaluation) <= scorer_count:
            prefix_valid = (
                len(set(observed_evaluation)) == len(observed_evaluation)
                and set(observed_evaluation).issubset(set(locked[:scorer_count]))
            )
            return prefix_valid and (not exact or observed_evaluation == locked)
        scorer_prefix = observed_evaluation[:scorer_count]
        suffix = observed_evaluation[scorer_count:]
        prefix_valid = (
            len(set(scorer_prefix)) == scorer_count
            and set(scorer_prefix) == set(locked[:scorer_count])
            and suffix == locked[scorer_count : scorer_count + len(suffix)]
        )
        return prefix_valid and (not exact or len(observed_evaluation) == len(locked))

    matching_evaluations = tuple(
        row
        for row in evaluations
        if isinstance(row, Mapping)
        and (
            evaluation_adjudication is None
            or row.get("adjudication") is evaluation_adjudication
        )
        and evaluation_sequence_matches(row, exact=True)
        and isinstance(row.get("route_id"), str)
    )
    prefix_evaluations = tuple(
        row
        for row in evaluations
        if isinstance(row, Mapping)
        and (
            evaluation_adjudication is None
            or row.get("adjudication") is evaluation_adjudication
        )
        and evaluation_sequence_matches(row, exact=False)
        and isinstance(row.get("route_id"), str)
    )
    if not prefix_evaluations:
        _fail("controller_evaluation_route_sequence_invalid")
    if len(matching_evaluations) > 1:
        _fail("controller_evaluation_route_ambiguous")
    selected_evaluation = (
        matching_evaluations[0]
        if matching_evaluations
        else prefix_evaluations[0]
        if len(prefix_evaluations) == 1
        else None
    )
    return (
        tuple(routes),
        (
            None
            if selected_evaluation is None
            else str(selected_evaluation["route_id"])
        ),
    )


def _read_relative_evidence(
    root: Path,
    relative_path: str,
    *,
    field: str,
) -> bytes:
    relative = _relative(relative_path, field=field)
    path = root.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        identity = path.lstat()
        payload = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ControllerError("controller_provider_evidence_unreadable", field) from exc
    if resolved != path or path.is_symlink() or not stat.S_ISREG(identity.st_mode):
        _fail("controller_provider_evidence_unreadable", field)
    return payload


def _allocation_record(
    allocation: provider_boundary.AllocationEvent,
    *,
    receipt_sha256: str | None,
) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": "es.call_allocation.v2",
            "call_slot_id": allocation.call_slot_id,
            "allocation_authority": allocation.record,
            "allocation_sha256": allocation.sha256,
            "settlement": (
                "RECEIPT_FROZEN"
                if receipt_sha256 is not None
                else "INTERRUPTED_IN_FLIGHT"
            ),
            "receipt_sha256": receipt_sha256,
        }
    )


def _load_finalizer_evidence(
    assembly: AttemptAssembly,
    *,
    preflight: _Preflight,
) -> _FinalizerEvidence:
    attempt_id = assembly.attempt_id
    journal_path = assembly.journal_path
    expected_manifest = _build_provider_boundary_manifest(
        package=assembly.package,
        preflight=preflight,
        attempt_id=attempt_id,
        journal_path=journal_path,
    )
    try:
        manifest = provider_boundary.load_manifest(
            journal_path.parent / "provider-boundary.json",
            expected_sha256=expected_manifest.sha256,
        )
        if manifest != expected_manifest:
            _fail("controller_attempt_prefix_manifest_invalid")
        lock_sha256 = decision_lock.decision_lock_digest(preflight.decision_lock)
        allocations = (
            provider_boundary.load_allocation_journal(
                journal_path,
                attempt_id=attempt_id,
                decision_lock_sha256=lock_sha256,
            )
            if journal_path.exists()
            else ()
        )
        settlement_path = journal_path.with_name("call-settlements.jsonl")
        settlements = (
            provider_boundary.load_settlement_journal(
                settlement_path,
                allocation_journal_path=journal_path,
                attempt_id=attempt_id,
                decision_lock_sha256=lock_sha256,
            )
            if settlement_path.exists()
            else ()
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_finalizer_evidence_invalid") from exc
    call_authority = _call_authority_by_slot(preflight.call_authority)
    for allocation in allocations:
        static = call_authority.get(allocation.call_slot_id)
        if static is None or allocation.static_call_sha256 != canonical_sha256(static):
            _fail("controller_finalizer_allocation_invalid")
    if assembly.authority is None:
        if assembly.review_records:
            _fail("controller_finalizer_review_prefix_invalid")
        persisted_reviews: tuple[SealedReviewRecord, ...] = ()
    else:
        persisted_reviews = _load_review_prefixes(
            preflight=preflight,
            attempt_id=attempt_id,
            authority=assembly.authority,
            journal_path=journal_path,
        )
        if persisted_reviews != assembly.review_records:
            _fail("controller_finalizer_review_prefix_mismatch")
    review_by_slot = {row.call_slot_id: row for row in persisted_reviews}
    settlement_by_slot = {row.call_slot_id: row for row in settlements}
    manifest_by_slot = {row.call_slot_id: row for row in manifest.calls}
    provider_rows: list[controller_artifacts.ProviderEvidenceInput] = []
    review_rows: list[controller_artifacts.ReviewEvidenceInput] = []
    receipt_rows: list[bytes] = []
    review_settlements: list[bytes] = []
    allocation_rows: list[bytes] = []
    evidence_slots: set[str] = set()
    for allocation in allocations:
        slot = allocation.call_slot_id
        settlement = settlement_by_slot.get(slot)
        if settlement is None:
            allocation_rows.append(
                _allocation_record(allocation, receipt_sha256=None)
            )
            continue
        if slot in _CONTROLLER_REVIEW_SLOTS:
            row = review_by_slot.get(slot)
            if row is None:
                _fail("controller_finalizer_review_prefix_mismatch", slot)
            receipt = _closed_object(
                row.canonical_receipt,
                field=f"finalizer.receipt.{slot}",
            )
            receipt_sha256 = _evidence_digest(receipt)
            if (
                settlement.receipt_sha256 != receipt_sha256
                or settlement.elapsed_ms != row.elapsed_ms
            ):
                _fail("controller_finalizer_settlement_mismatch", slot)
            call_allocation = _allocation_record(
                allocation,
                receipt_sha256=receipt_sha256,
            )
            review_rows.append(
                controller_artifacts.ReviewEvidenceInput(
                    call_slot_id=slot,
                    canonical_record=row.canonical_record,
                    canonical_receipt=row.canonical_receipt,
                    raw_jsonl=row.raw_jsonl,
                    elapsed_ms=row.elapsed_ms,
                    call_allocation=call_allocation,
                )
            )
            review_settlements.append(
                canonical_json_bytes(
                    {
                        "call_slot_id": slot,
                        "status": row.status,
                        "record_sha256": _evidence_digest(row.record),
                        "receipt_sha256": receipt_sha256,
                    }
                )
            )
        else:
            call = manifest_by_slot.get(slot)
            if call is None:
                _fail("controller_finalizer_provider_call_missing", slot)
            receipt_raw = _read_relative_evidence(
                assembly.package.paths.evidence_root,
                call.receipt_path,
                field=f"receipt.{slot}",
            )
            receipt = _closed_object(
                receipt_raw,
                field=f"provider_receipt.{slot}",
                line=True,
            )
            raw_jsonl = _read_relative_evidence(
                assembly.package.paths.evidence_root,
                call.raw_jsonl_path,
                field=f"raw_jsonl.{slot}",
            )
            try:
                raw_jsonl.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise ControllerError(
                    "controller_provider_evidence_invalid",
                    slot,
                ) from exc
            receipt_sha256 = _evidence_digest(receipt)
            if (
                receipt.get("block_id") != attempt_id
                or receipt.get("call_slot_id") != slot
                or type(receipt.get("exit_status")) is not int
                or settlement.receipt_sha256 != receipt_sha256
                or settlement.exit_status != receipt["exit_status"]
            ):
                _fail("controller_finalizer_settlement_mismatch", slot)
            call_allocation = _allocation_record(
                allocation,
                receipt_sha256=receipt_sha256,
            )
            provider_rows.append(
                controller_artifacts.ProviderEvidenceInput(
                    call_slot_id=slot,
                    canonical_receipt=canonical_json_bytes(receipt),
                    raw_jsonl=raw_jsonl,
                    elapsed_ms=settlement.elapsed_ms,
                    call_allocation=call_allocation,
                )
            )
        evidence_slots.add(slot)
        receipt_rows.append(
            canonical_json_bytes(
                {
                    "call_slot_id": slot,
                    "receipt_sha256": settlement.receipt_sha256,
                }
            )
        )
        allocation_rows.append(call_allocation)
    if set(settlement_by_slot) != evidence_slots:
        _fail("controller_finalizer_settlement_domain_invalid")
    return _FinalizerEvidence(
        allocations=allocations,
        provider=tuple(provider_rows),
        reviews=tuple(review_rows),
        receipt_bindings=tuple(receipt_rows),
        review_settlements=tuple(review_settlements),
        call_allocations=tuple(allocation_rows),
    )


def _contract_ordered_receipt_bindings(
    evidence: _FinalizerEvidence,
    *,
    preflight: _Preflight,
    arm_routes: tuple[tuple[str, str], ...],
    evaluation_route_id: str | None,
) -> tuple[bytes, ...]:
    if len(arm_routes) != len(ARMS) or evaluation_route_id is None:
        return evidence.receipt_bindings
    route_contract = preflight.decision_lock["route_contract"]
    terminal = {
        row["route_id"]: row
        for row in route_contract["terminal_routes"]
    }
    evaluations = {
        row["route_id"]: row
        for row in route_contract["evaluation_routes"]
    }
    try:
        expected_slots = tuple(
            slot
            for arm, route_id in arm_routes
            for slot in terminal[route_id]["call_slots"]
        ) + tuple(evaluations[evaluation_route_id]["call_slots"])
    except (KeyError, TypeError) as exc:
        raise ControllerError("controller_route_contract_invalid") from exc
    by_slot: dict[str, bytes] = {}
    for row in evidence.receipt_bindings:
        value = _closed_object(row, field="receipt_binding")
        slot = value.get("call_slot_id")
        if not isinstance(slot, str) or slot in by_slot:
            _fail("controller_receipt_binding_invalid")
        by_slot[slot] = row
    if set(by_slot) != set(expected_slots) or len(by_slot) != len(expected_slots):
        return evidence.receipt_bindings
    return tuple(by_slot[slot] for slot in expected_slots)


def _validate_classifier_authority(
    assembly: AttemptAssembly,
    *,
    preflight: _Preflight,
    evidence: _FinalizerEvidence,
) -> None:
    authority = assembly.classifier_authority
    if type(authority) is not _AttemptClassifierAuthority:
        raise TypeError("classifier authority must be exact")
    code = authority.invalidity_code
    if code is None:
        return
    if code == "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT":
        if (
            type(assembly.trial_result) is not TrialRunResult
            or assembly.trial_result.terminal_status != "failed"
            or type(assembly.authority) is not PersistedTrialAuthority
            or assembly.authority.terminal_status != "failed"
            or assembly.private_join is not None
            or assembly.review_records
            or assembly.adjudication_payload is not None
            or assembly.hard_evidence
            or assembly.integrated_payload is not None
            or assembly.material_disagreement
            or authority.invalidity_authority is None
        ):
            _fail("controller_outage_disposition_prefix_invalid")
        frozen = _read_regular_evidence(
            assembly.journal_path.parent
            / "common-provider-outage-disposition.json",
            code="controller_outage_disposition_invalid",
        )
        record = _closed_object(
            frozen,
            field="outage_disposition",
            line=True,
        )
        canonical = canonical_json_bytes(record)
        if canonical != authority.invalidity_authority:
            _fail("controller_outage_disposition_invalid")
        validated = _validate_outage_disposition_authority(
            canonical,
            package=assembly.package,
            preflight=preflight,
            attempt_id=assembly.attempt_id,
            trial_result=assembly.trial_result,
            authority=assembly.authority,
            journal_path=assembly.journal_path,
            allocations=evidence.allocations,
        )
        if validated != authority:
            _fail("controller_outage_disposition_invalid")
        return
    if code == "COMMON_EVALUATION_BYTES_INVALID":
        if (
            type(assembly.trial_result) is not TrialRunResult
            or assembly.trial_result.terminal_status != "completed"
            or type(assembly.authority) is not PersistedTrialAuthority
            or assembly.authority.terminal_status != "completed"
            or type(assembly.private_join) is not blinding.PrivateBlindingJoin
            or assembly.integrated_payload is not None
            or authority.invalidity_authority is None
        ):
            _fail("controller_evaluator_invalidity_authority_invalid")
        frozen = _read_regular_evidence(
            assembly.journal_path.parent / "invalidity-authority.json",
            code="controller_evaluator_invalidity_authority_invalid",
        )
        record = _closed_object(
            frozen,
            field="invalidity_authority",
            line=True,
        )
        canonical = canonical_json_bytes(record)
        if canonical != authority.invalidity_authority:
            _fail("controller_evaluator_invalidity_authority_invalid")
        validated = _validate_evaluator_invalidity_authority(
            canonical,
            package=assembly.package,
            preflight=preflight,
            attempt_id=assembly.attempt_id,
            authority=assembly.authority,
            journal_path=assembly.journal_path,
            allocations=evidence.allocations,
            review_records=assembly.review_records,
            material_disagreement=assembly.material_disagreement,
        )
        if validated != authority:
            _fail("controller_evaluator_invalidity_authority_invalid")
        return
    if code != "BLINDING_JOIN_INVALID":
        _fail("controller_classifier_authority_substrate_missing", code)
    if (
        type(assembly.trial_result) is not TrialRunResult
        or assembly.trial_result.terminal_status != "completed"
        or type(assembly.authority) is not PersistedTrialAuthority
        or assembly.authority.terminal_status != "completed"
        or assembly.private_join is not None
        or assembly.review_records
        or assembly.adjudication_payload is not None
        or assembly.hard_evidence
        or assembly.integrated_payload is not None
        or assembly.material_disagreement
    ):
        _fail("controller_blinding_classifier_authority_invalid")
    try:
        _private_join_projection(
            package=assembly.package,
            preflight=preflight,
            attempt_id=assembly.attempt_id,
            authority=assembly.authority,
        )
    except blinding.BlindingJoinError as exc:
        _blinding_classifier_authority(exc)
        return
    _fail("controller_blinding_classifier_authority_invalid")


def _canonical_finalize_attempt_impl(assembly: AttemptAssembly) -> FinalizedAttempt:
    if type(assembly) is not AttemptAssembly:
        raise TypeError("assembly must be exact AttemptAssembly")
    if type(assembly.package) is not ControllerPackage:
        raise TypeError("assembly package must be exact ControllerPackage")
    if assembly.trial_result is None:
        if assembly.authority is not None:
            _fail("controller_finalizer_trial_prefix_invalid")
    elif (
        type(assembly.trial_result) is not TrialRunResult
        or type(assembly.authority) is not PersistedTrialAuthority
    ):
        _fail("controller_finalizer_trial_prefix_invalid")
    expected_journal = (
        assembly.package.paths.evidence_root
        / "attempts"
        / assembly.attempt_id
        / "call-allocations.jsonl"
    )
    if assembly.journal_path != expected_journal:
        _fail("controller_finalizer_journal_path_invalid")
    if type(assembly.classifier_authority) is not _AttemptClassifierAuthority:
        raise TypeError("classifier authority must be exact")

    preflight = _preflight(
        assembly.package,
        allow_untrusted_package=False,
        allow_evaluator_mismatch=(
            assembly.classifier_authority.invalidity_code
            == "COMMON_EVALUATION_BYTES_INVALID"
        ),
    )
    evidence = _load_finalizer_evidence(assembly, preflight=preflight)
    _validate_classifier_authority(
        assembly,
        preflight=preflight,
        evidence=evidence,
    )
    if assembly.authority is None:
        arm_routes: tuple[tuple[str, str], ...] = ()
        evaluation_route_id: str | None = None
    else:
        settled_review_slots = tuple(
            row.call_slot_id for row in evidence.reviews
        )
        arm_routes, evaluation_route_id = _selected_routes(
            preflight=preflight,
            allocations=evidence.allocations,
            arm_terminal_status_by_arm=_arm_terminal_status_by_arm(
                assembly.authority
            ),
            evaluation_adjudication=(
                assembly.material_disagreement
                if settled_review_slots[: len(_INITIAL_REVIEW_SLOTS)]
                == _INITIAL_REVIEW_SLOTS
                else None
            ),
        )
    receipt_bindings = _contract_ordered_receipt_bindings(
        evidence,
        preflight=preflight,
        arm_routes=arm_routes,
        evaluation_route_id=evaluation_route_id,
    )
    hard_evidence = tuple(
        controller_artifacts.HardEvidenceInput(
            arm_id=arm_id,
            trusted_product_freeze_status=value.trusted_product_freeze_status,
            canonical_inputs=value.canonical_inputs,
        )
        for arm_id, value in assembly.hard_evidence
    )
    frozen_call_authority = canonical_json_bytes(preflight.call_authority)
    all_allocations_settled = (
        len(evidence.provider) + len(evidence.reviews)
        == len(evidence.allocations)
    )
    complete = (
        assembly.trial_result is not None
        and assembly.trial_result.terminal_status == "completed"
        and assembly.authority is not None
        and assembly.authority.terminal_status == "completed"
        and type(assembly.private_join) is blinding.PrivateBlindingJoin
        and isinstance(assembly.integrated_payload, bytes)
        and tuple(arm_id for arm_id, _value in assembly.hard_evidence) == ARMS
        and len(arm_routes) == len(ARMS)
        and evaluation_route_id is not None
        and all_allocations_settled
    )
    try:
        if complete:
            assert assembly.authority is not None
            assert assembly.private_join is not None
            assert assembly.integrated_payload is not None
            index_inputs: (
                controller_artifacts.CompleteIndexInputs
                | controller_artifacts.PartialIndexInputs
            ) = controller_artifacts.build_complete_index_inputs(
                replay=assembly.authority,
                private_join=assembly.private_join,
                review_evidence=evidence.reviews,
                hard_evidence=hard_evidence,
                adjudication_payload=assembly.adjudication_payload,
                integrated_payload=assembly.integrated_payload,
                frozen_call_authority=frozen_call_authority,
                provider_evidence=evidence.provider,
            )
        else:
            index_inputs = controller_artifacts.build_partial_index_inputs(
                replay=assembly.authority,
                private_join=assembly.private_join,
                review_evidence=evidence.reviews,
                provider_evidence=evidence.provider,
                frozen_call_authority=frozen_call_authority,
                call_allocations=evidence.call_allocations,
                adjudication_payload=assembly.adjudication_payload,
                integrated_payload=assembly.integrated_payload,
                hard_evidence=hard_evidence,
                invalidity_authority=(
                    assembly.classifier_authority.invalidity_authority
                ),
            )
        attempt_inputs = controller_artifacts.AttemptRecordInputs(
            attempt_id=assembly.attempt_id,
            replay=assembly.authority,
            trial_result=assembly.trial_result,
            frozen_trial_artifact_authority=(
                preflight.trial_artifact_authority
            ),
            trial_event_ledger_path=(
                None
                if assembly.authority is None
                else assembly.authority.trial_event_ledger_path
            ),
            arm_route_ids=arm_routes,
            evaluation_route_id=evaluation_route_id,
            material_disagreement=assembly.material_disagreement,
            review_settlements=evidence.review_settlements,
            receipt_bindings=receipt_bindings,
            source_task_binding_valid=True,
            controller_launch_preallocation_failed=(
                assembly.trial_result is None
            ),
            common_provider_outage_proven=(
                assembly.classifier_authority.common_provider_outage_proven
            ),
            evaluation_bytes_valid=(
                assembly.classifier_authority.evaluation_bytes_valid
            ),
            blinding_join_valid=assembly.classifier_authority.blinding_join_valid,
            interrupted=not complete,
        )
        call_bounds = preflight.decision_lock["derived"]["call_bounds"]
        absolute_ceiling = call_bounds[
            "absolute_with_invalid_attempt_capacity"
        ]
        if type(absolute_ceiling) is not int:
            _fail("controller_finalizer_call_ceiling_invalid")
        finalized = controller_artifacts.finalize_attempt_artifacts(
            controller_artifacts.FinalizationAssembly(
                evidence_root=assembly.package.paths.evidence_root,
                decision_lock=canonical_json_bytes(preflight.decision_lock),
                randomization_manifest=canonical_json_bytes(
                    preflight.randomization_manifest
                ),
                expected_bindings=tuple(sorted(preflight.expected_bindings.items())),
                attempt=attempt_inputs,
                index=index_inputs,
                prior_indexes=assembly.package.attempt_indexes,
                expected_attempt_record=None,
                expected_absolute_call_ceiling=absolute_ceiling,
                expected_denominator=len(assembly.package.attempt_indexes) + 1,
            )
        )
    except (
        ControllerError,
        controller_artifacts.ControllerArtifactError,
        TypeError,
        ValueError,
    ) as exc:
        if isinstance(exc, ControllerError):
            raise
        raise ControllerError("controller_canonical_finalization_failed") from exc
    return FinalizedAttempt(
        attempt_record=finalized.attempt_record,
        attempt_index=finalized.attempt_index,
        attempt_index_sha256=finalized.attempt_index_sha256,
        report=finalized.report,
        stopped=finalized.stopped,
        next_attempt_id=finalized.next_attempt_id,
    )


def _recover_open_attempt(
    *,
    package: ControllerPackage,
    dependencies: ControllerDependencies,
    preflight: _Preflight,
    attempt_id: str,
    journal_path: Path,
) -> ControllerResult:
    """Close one immutable interrupted prefix without resuming its work."""

    expected_manifest = _build_provider_boundary_manifest(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        journal_path=journal_path,
    )
    try:
        observed_manifest = provider_boundary.load_manifest(
            journal_path.parent / "provider-boundary.json",
            expected_sha256=expected_manifest.sha256,
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_attempt_prefix_manifest_invalid") from exc
    if observed_manifest != expected_manifest:
        _fail("controller_attempt_prefix_manifest_invalid")
    decision_lock_sha256 = decision_lock.decision_lock_digest(
        preflight.decision_lock
    )
    try:
        allocations = (
            provider_boundary.load_allocation_journal(
                journal_path,
                attempt_id=attempt_id,
                decision_lock_sha256=decision_lock_sha256,
            )
            if journal_path.exists()
            else ()
        )
    except provider_boundary.ProviderBoundaryError as exc:
        raise ControllerError("controller_attempt_prefix_journal_invalid") from exc
    attempts.enforce_absolute_call_ceiling(
        (*package.consumed_attempt_call_counts, len(allocations)),
        invalid_attempt_count=package.invalid_attempt_count,
        decision_lock=preflight.decision_lock,
        randomization_manifest=preflight.randomization_manifest,
        expected_bindings=preflight.expected_bindings,
    )
    trial_prefix_path = journal_path.parent / "trial-prefix.json"
    if not trial_prefix_path.exists():
        if allocations or journal_path.with_name("call-settlements.jsonl").exists():
            _fail("controller_attempt_prefix_trial_result_missing")
        return _finalize_preallocation_failure(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            journal_path=journal_path,
        )
    trial_result, authority = _load_trial_prefix(
        package=package,
        dependencies=dependencies,
        attempt_id=attempt_id,
        attempt_root=journal_path.parent,
    )
    review_rows = _load_review_prefixes(
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
    )
    if trial_result.terminal_status == "failed":
        if review_rows:
            _fail("controller_failed_trial_review_prefix_invalid")
        outage = _load_outage_disposition_authority(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            journal_path=journal_path,
            allocations=allocations,
        )
        if outage is not None:
            return _finalize_common_invalidity(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=None,
                review_records=(),
                adjudication_payload=None,
                hard_evidence=(),
                material_disagreement=False,
                classifier_authority=outage,
                journal_path=journal_path,
            )
        finalized = dependencies.finalize_attempt(
            AttemptAssembly(
                attempt_id=attempt_id,
                package=package,
                trial_result=trial_result,
                authority=authority,
                private_join=None,
                review_records=(),
                adjudication_payload=None,
                hard_evidence=(),
                integrated_payload=None,
                material_disagreement=False,
                classifier_authority=_valid_classifier_authority(),
                journal_path=journal_path,
            )
        )
        return _settled_controller_result(
            package=package,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            finalized=finalized,
        )

    try:
        private_join, presentation_order = _private_join_projection(
            package=package,
            preflight=preflight,
            attempt_id=attempt_id,
            authority=authority,
        )
    except blinding.BlindingJoinError as exc:
        return _finalize_blinding_join_invalid(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            journal_path=journal_path,
            error=exc,
        )
    citable = {
        packet.opaque_label: tuple(_packet_record(packet)["citable_item_ids"])
        for packet in authority.packets
    }
    initial_slots = (
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    observed_slots = tuple(row.call_slot_id for row in review_rows)
    if observed_slots != initial_slots[: len(observed_slots)] and len(
        observed_slots
    ) < 2:
        _fail("controller_review_prefix_sequence_invalid")
    disagreement = False
    if len(review_rows) >= 2 and all(
        row.status == "SUCCEEDED" for row in review_rows[:2]
    ):
        disagreement = bool(
            reviews.material_disagreements(
                review_rows[0].record,
                review_rows[1].record,
                citable_item_ids_by_label=citable,
            )
        )
    expected_slots = [*initial_slots]
    if disagreement:
        expected_slots.append("EVAL.ADJUDICATOR")
    expected_slots.append("EVAL.INTEGRATED_REVIEW")
    if observed_slots != tuple(expected_slots[: len(observed_slots)]):
        _fail("controller_review_prefix_sequence_invalid")
    adjudication_payload: bytes | None = None
    if disagreement and len(review_rows) >= 3:
        adjudication_payload = canonical_json_bytes(
            reviews.resolve_adjudication(
                review_rows[0].record,
                review_rows[1].record,
                review_rows[2].record,
                citable_item_ids_by_label=citable,
            )
        )
    evaluator_invalidity = _load_evaluator_invalidity_authority(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        authority=authority,
        journal_path=journal_path,
        allocations=allocations,
        review_records=review_rows,
        material_disagreement=disagreement,
    )
    if evaluator_invalidity is not None:
        return _finalize_common_invalidity(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            private_join=private_join,
            review_records=review_rows,
            adjudication_payload=adjudication_payload,
            hard_evidence=(),
            material_disagreement=disagreement,
            classifier_authority=evaluator_invalidity,
            journal_path=journal_path,
        )
    return _finalize_interrupted_provider_call(
        package=package,
        dependencies=dependencies,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=trial_result,
        authority=authority,
        private_join=private_join,
        review_records=review_rows,
        adjudication_payload=adjudication_payload,
        hard_evidence=(),
        material_disagreement=disagreement,
        journal_path=journal_path,
    )


def execute_attempt(
    package: ControllerPackage,
    dependencies: ControllerDependencies,
) -> ControllerResult:
    """Execute one fresh locked attempt; this function never resumes a run."""

    if type(dependencies) is not ControllerDependencies:
        raise TypeError("dependencies must be exact ControllerDependencies")
    preflight = _preflight(
        package,
        allow_untrusted_package=dependencies.allow_untrusted_package_for_tests,
    )
    attempt_id = attempts.select_next_attempt_id(
        package.consumed_attempt_ids,
        decision_lock=preflight.decision_lock,
        randomization_manifest=preflight.randomization_manifest,
        expected_bindings=preflight.expected_bindings,
    )
    attempts.enforce_absolute_call_ceiling(
        (*package.consumed_attempt_call_counts, 0),
        invalid_attempt_count=package.invalid_attempt_count,
        decision_lock=preflight.decision_lock,
        randomization_manifest=preflight.randomization_manifest,
        expected_bindings=preflight.expected_bindings,
    )
    journal_path = (
        package.paths.evidence_root
        / "attempts"
        / attempt_id
        / "call-allocations.jsonl"
    )
    attempt_root = journal_path.parent
    if attempt_root.exists() and any(attempt_root.iterdir()):
        return _recover_open_attempt(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            journal_path=journal_path,
        )
    environment_overlay = _publish_provider_boundary(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        journal_path=journal_path,
    )
    options = TrialRunOptions(
        source_roots=(
            package.paths.workspace / "workflows/experiments",
            package.paths.workspace / "workflows/library",
        ),
        provider_externs_file=(
            package.paths.workspace / package.provider_externs.relative_path
        ),
        prompt_externs_file=(
            package.paths.workspace / package.prompt_externs.relative_path
        ),
        max_retries=0,
        retry_delay_ms=0,
    )
    previous_environment = {
        key: os.environ.get(key) for key in environment_overlay
    }
    trial_result: TrialRunResult | None = None
    runner_error: Exception | None = None
    try:
        os.environ.update(environment_overlay)
        try:
            trial_result = dependencies.run_trial(
                workflow_file=package.paths.workspace / package.workflow.relative_path,
                entry_workflow=ENTRY_WORKFLOW,
                inputs={
                    "task": preflight.task,
                    "check_contract": preflight.check_contract,
                    "model": package.model,
                    "effort": package.effort,
                },
                workspace=package.paths.workspace,
                state_dir=package.paths.state_dir,
                run_ref_root=package.paths.run_ref_root,
                options=options,
            )
        except Exception as exc:
            runner_error = exc
    finally:
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if runner_error is not None:
        try:
            allocations = (
                provider_boundary.load_allocation_journal(
                    journal_path,
                    attempt_id=attempt_id,
                    decision_lock_sha256=decision_lock.decision_lock_digest(
                        preflight.decision_lock
                    ),
                )
                if journal_path.exists()
                else ()
            )
        except provider_boundary.ProviderBoundaryError as exc:
            raise ControllerError("controller_trial_entry_failure_prefix_invalid") from exc
        if allocations:
            raise ControllerError(
                "controller_trial_entry_failure_after_allocation"
            ) from runner_error
        return _finalize_preallocation_failure(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            journal_path=journal_path,
        )
    if type(trial_result) is not TrialRunResult:
        raise TypeError("runner must return exact TrialRunResult")
    authority = dependencies.replay_trial(trial_result, package)
    if type(authority) is not PersistedTrialAuthority:
        raise TypeError("replay must return exact PersistedTrialAuthority")
    if authority.terminal_status != trial_result.terminal_status:
        _fail("controller_trial_replay_status_mismatch")
    _publish_trial_prefix(
        trial_result,
        authority,
        attempt_id=attempt_id,
        attempt_root=attempt_root,
    )
    if trial_result.terminal_status == "failed":
        try:
            allocations = (
                provider_boundary.load_allocation_journal(
                    journal_path,
                    attempt_id=attempt_id,
                    decision_lock_sha256=decision_lock.decision_lock_digest(
                        preflight.decision_lock
                    ),
                )
                if journal_path.exists()
                else ()
            )
        except provider_boundary.ProviderBoundaryError as exc:
            raise ControllerError(
                "controller_trial_failure_prefix_invalid"
            ) from exc
        boundary = _post_incident_disposition_boundary(
            package=package,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            journal_path=journal_path,
            allocations=allocations,
        )
        if boundary is not None:
            raise boundary
        finalized = dependencies.finalize_attempt(
            AttemptAssembly(
                attempt_id=attempt_id,
                package=package,
                trial_result=trial_result,
                authority=authority,
                private_join=None,
                review_records=(),
                adjudication_payload=None,
                hard_evidence=(),
                integrated_payload=None,
                material_disagreement=False,
                classifier_authority=_valid_classifier_authority(),
                journal_path=journal_path,
            )
        )
        return _settled_controller_result(
            package=package,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            finalized=finalized,
        )
    try:
        private_join, presentation_order = _private_join_projection(
            package=package,
            preflight=preflight,
            attempt_id=attempt_id,
            authority=authority,
        )
    except blinding.BlindingJoinError as exc:
        return _finalize_blinding_join_invalid(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            journal_path=journal_path,
            error=exc,
        )
    packet_index = authority.packet_index_record
    assert packet_index is not None
    review_rows: list[SealedReviewRecord] = []
    adjudication_payload: bytes | None = None
    hard_rows: list[tuple[str, HardEvidenceInput]] = []
    disagreement = False
    for slot, perspective in (
        (
            "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
            reviews.SCIENTIFIC_APPLICATION_SEMANTICS,
        ),
        (
            "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
            reviews.API_PERSISTENCE_MIGRATION_MAINTAINABILITY,
        ),
    ):
        try:
            review = _review_call(
                package=package,
                deps=dependencies,
                preflight=preflight,
                journal_path=journal_path,
                attempt_id=attempt_id,
                authority=authority,
                slot=slot,
                kind=reviews.INITIAL,
                perspective=perspective,
                presentation_order=presentation_order,
                prior=tuple(review_rows),
                hard_evidence=(),
            )
        except _CommonEvaluationBytesInvalid as exc:
            return _finalize_common_invalidity(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=private_join,
                review_records=review_rows,
                adjudication_payload=adjudication_payload,
                hard_evidence=hard_rows,
                material_disagreement=disagreement,
                classifier_authority=exc.authority,
                journal_path=journal_path,
            )
        except _ProviderCallInterrupted:
            return _finalize_interrupted_provider_call(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=private_join,
                review_records=review_rows,
                adjudication_payload=adjudication_payload,
                hard_evidence=hard_rows,
                material_disagreement=disagreement,
                journal_path=journal_path,
            )
        review_rows.append(review)
    citable = {
        packet.opaque_label: tuple(_packet_record(packet)["citable_item_ids"])
        for packet in authority.packets
    }
    if any(row.status == "FAILED" for row in review_rows):
        disagreement = False
    else:
        disagreement = bool(
            reviews.material_disagreements(
                review_rows[0].record,
                review_rows[1].record,
                citable_item_ids_by_label=citable,
            )
        )
    if disagreement:
        try:
            adjudicator = _review_call(
                package=package,
                deps=dependencies,
                preflight=preflight,
                journal_path=journal_path,
                attempt_id=attempt_id,
                authority=authority,
                slot="EVAL.ADJUDICATOR",
                kind=reviews.ADJUDICATOR,
                perspective=None,
                presentation_order=presentation_order,
                prior=tuple(review_rows),
                hard_evidence=(),
            )
        except _CommonEvaluationBytesInvalid as exc:
            return _finalize_common_invalidity(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=private_join,
                review_records=review_rows,
                adjudication_payload=adjudication_payload,
                hard_evidence=hard_rows,
                material_disagreement=disagreement,
                classifier_authority=exc.authority,
                journal_path=journal_path,
            )
        except _ProviderCallInterrupted:
            return _finalize_interrupted_provider_call(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=private_join,
                review_records=review_rows,
                adjudication_payload=adjudication_payload,
                hard_evidence=hard_rows,
                material_disagreement=disagreement,
                journal_path=journal_path,
            )
        review_rows.append(adjudicator)
        adjudication_payload = canonical_json_bytes(
            reviews.resolve_adjudication(
                review_rows[0].record,
                review_rows[1].record,
                adjudicator.record,
                citable_item_ids_by_label=citable,
            )
        )
    by_arm = {packet.arm_id: packet for packet in authority.packets}
    for arm in ARMS:
        packet = by_arm[arm]
        request = HardEvidenceRequest(
            attempt_id=attempt_id,
            arm_id=arm,
            cell=packet.cell,
            opaque_label=packet.opaque_label,
            packet=packet.canonical_packet,
        )
        try:
            try:
                allocations = (
                    provider_boundary.load_allocation_journal(
                        journal_path,
                        attempt_id=attempt_id,
                        decision_lock_sha256=decision_lock.decision_lock_digest(
                            preflight.decision_lock
                        ),
                    )
                    if journal_path.exists()
                    else ()
                )
            except provider_boundary.ProviderBoundaryError as exc:
                raise ControllerError(
                    "controller_allocation_journal_invalid"
                ) from exc
            _guard_evaluator_fixture(
                package=package,
                preflight=preflight,
                attempt_id=attempt_id,
                authority=authority,
                journal_path=journal_path,
                target=f"HARD.{arm}",
                allocations=allocations,
            )
            value = dependencies.collect_hard_evidence(request)
            if type(value) is not HardEvidenceInput:
                raise TypeError("hard collector must return exact HardEvidenceInput")
            hard_rows.append((arm, _hard_spec(value, request)))
        except _CommonEvaluationBytesInvalid as exc:
            return _finalize_common_invalidity(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=private_join,
                review_records=review_rows,
                adjudication_payload=adjudication_payload,
                hard_evidence=hard_rows,
                material_disagreement=disagreement,
                classifier_authority=exc.authority,
                journal_path=journal_path,
            )
        except Exception:
            return _finalize_interrupted_provider_call(
                package=package,
                dependencies=dependencies,
                preflight=preflight,
                attempt_id=attempt_id,
                trial_result=trial_result,
                authority=authority,
                private_join=private_join,
                review_records=review_rows,
                adjudication_payload=adjudication_payload,
                hard_evidence=hard_rows,
                material_disagreement=disagreement,
                journal_path=journal_path,
            )
    try:
        integrated = _review_call(
            package=package,
            deps=dependencies,
            preflight=preflight,
            journal_path=journal_path,
            attempt_id=attempt_id,
            authority=authority,
            slot="EVAL.INTEGRATED_REVIEW",
            kind=reviews.INTEGRATED,
            perspective=None,
            presentation_order=presentation_order,
            prior=tuple(review_rows),
            hard_evidence=tuple(hard_rows),
        )
    except _CommonEvaluationBytesInvalid as exc:
        return _finalize_common_invalidity(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            private_join=private_join,
            review_records=review_rows,
            adjudication_payload=adjudication_payload,
            hard_evidence=hard_rows,
            material_disagreement=disagreement,
            classifier_authority=exc.authority,
            journal_path=journal_path,
        )
    except _ProviderCallInterrupted:
        return _finalize_interrupted_provider_call(
            package=package,
            dependencies=dependencies,
            preflight=preflight,
            attempt_id=attempt_id,
            trial_result=trial_result,
            authority=authority,
            private_join=private_join,
            review_records=review_rows,
            adjudication_payload=adjudication_payload,
            hard_evidence=hard_rows,
            material_disagreement=disagreement,
            journal_path=journal_path,
        )
    review_rows.append(integrated)
    integrated_payload = canonical_json_bytes(
        reviews.resolve_integrated_review(
            integrated.record,
            attempt_id=attempt_id,
            packet_set_digest=str(packet_index["packet_set_digest"]),
            presentation_order=presentation_order,
            citable_item_ids_by_label=citable,
            existing_records=tuple(row.record for row in review_rows[:-1]),
        )
    )
    assembly = AttemptAssembly(
        attempt_id=attempt_id,
        package=package,
        trial_result=trial_result,
        authority=authority,
        private_join=private_join,
        review_records=tuple(review_rows),
        adjudication_payload=adjudication_payload,
        hard_evidence=tuple(hard_rows),
        integrated_payload=integrated_payload,
        material_disagreement=disagreement,
        classifier_authority=_valid_classifier_authority(),
        journal_path=journal_path,
    )
    finalized = dependencies.finalize_attempt(assembly)
    return _settled_controller_result(
        package=package,
        preflight=preflight,
        attempt_id=attempt_id,
        trial_result=trial_result,
        finalized=finalized,
    )


def default_controller_dependencies(
    *,
    call_provider: CallProvider,
    collect_hard_evidence: CollectHard,
    common_provider_outage_disposition_sha256: str | None = None,
) -> ControllerDependencies:
    """Build the production dependency set around public replay and SDK calls."""

    return ControllerDependencies(
        run_trial=run_trial_entry,
        replay_trial=replay_persisted_trial_authority,
        call_provider=call_provider,
        collect_hard_evidence=collect_hard_evidence,
        finalize_attempt=canonical_finalize_attempt,
        common_provider_outage_disposition_sha256=(
            common_provider_outage_disposition_sha256
        ),
    )


__all__ = [
    "AttemptIndexBinding",
    "AttemptAssembly",
    "BoundFile",
    "ControllerDependencies",
    "ControllerError",
    "ControllerPackage",
    "ControllerPaths",
    "ControllerResult",
    "FinalizedAttempt",
    "HardEvidenceInput",
    "HardEvidenceRequest",
    "PersistedPacket",
    "PersistedTrialAuthority",
    "PostIncidentDispositionRequired",
    "ProviderCallResult",
    "ReviewCallRequest",
    "SealedReviewRecord",
    "TrialRunOptions",
    "canonical_finalize_attempt",
    "default_controller_dependencies",
    "execute_attempt",
    "load_controller_package",
    "replay_persisted_trial_authority",
]
