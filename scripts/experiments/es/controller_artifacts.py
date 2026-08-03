"""Canonical persisted-artifact replay and publication for the ES controller."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, NoReturn

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.trial.contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
    build_sealed_opaque_label_map,
)
from orchestrator.workflow.trial.ledger import (
    TrialEventLedger,
    TrialLedgerError,
    TrialLedgerRow,
    load_trial_event_ledger,
    load_trial_score_rows,
)
from orchestrator.workflow.trial.packets import (
    TrialPacketError,
    validate_trial_evaluation_packet,
)
from orchestrator.workflow.trial.sdk import TrialRunResult

from . import attempts, blinding, hard_contract, reviews, synthesis


_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PACKET_INDEX_KEYS = {
    "schema_version",
    "trial_request_digest",
    "header_row_digest",
    "evidence_frozen_row_digest",
    "checks_frozen_row_digest",
    "packets_frozen_row_digest",
    "sealed_opaque_label_map_digest",
    "packet_set_digest",
    "packets",
}
_VERDICT_KEYS = {
    "schema_version",
    "trial_request_digest",
    "evaluation_digest",
    "evidence_frozen_digest",
    "checks_frozen_digest",
    "score_digest",
    "scorer_identity_digest",
    "sealed_label_map_digest",
    "aggregation_digest",
    "verdict_digest",
    "authored_outcomes",
    "verdict",
    "artifact_digest",
}
_CALL_ALLOCATION_KEYS = {
    "schema_version",
    "call_slot_id",
    "allocation_authority",
    "allocation_sha256",
    "settlement",
    "receipt_sha256",
}
_INVALIDITY_AUTHORITY_KEYS = {
    "schema_version",
    "attempt_id",
    "invalidity_code",
    "evidence",
}


class ControllerArtifactError(ValueError):
    """Persisted ES controller authority is missing, ambiguous, or altered."""

    code = "es_controller_artifact_invalid"


def _fail(message: str) -> NoReturn:
    raise ControllerArtifactError(message)


def _raw_sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_json_value(payload: bytes, *, field: str) -> object:
    if not payload.endswith(b"\n") or payload == b"\n":
        _fail(f"{field} is not newline-framed canonical JSON")
    try:
        value = json.loads(
            payload[:-1].decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerArtifactError(f"{field} is not strict JSON") from exc
    try:
        expected = canonical_json_bytes(value) + b"\n"
    except (TypeError, ValueError) as exc:
        raise ControllerArtifactError(f"{field} is not canonical JSON") from exc
    if payload != expected:
        _fail(f"{field} is not canonical JSON")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant {value}")


def _json_mapping(payload: bytes, *, field: str) -> dict[str, Any]:
    value = _canonical_json_value(payload, field=field)
    if not isinstance(value, dict):
        _fail(f"{field} is not a JSON object")
    return value


def _input_mapping(payload: bytes, *, field: str) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not payload or payload.endswith(b"\n"):
        _fail(f"{field} is not canonical in-memory JSON")
    try:
        value = json.loads(
            payload.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerArtifactError(f"{field} is not strict JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != payload:
        _fail(f"{field} is not a canonical JSON object")
    return value


def _invalidity_authority_mapping(payload: bytes) -> dict[str, Any]:
    record = _input_mapping(payload, field="invalidity_authority")
    if (
        set(record) != _INVALIDITY_AUTHORITY_KEYS
        or record.get("schema_version")
        != "es.controller_invalidity_authority.v1"
        or not isinstance(record.get("attempt_id"), str)
        or not record["attempt_id"]
        or not isinstance(record.get("invalidity_code"), str)
        or not record["invalidity_code"]
        or not isinstance(record.get("evidence"), Mapping)
    ):
        _fail("invalidity authority envelope is invalid")
    return record


def _validate_named_json_rows(
    values: tuple[tuple[str, bytes], ...],
    *,
    field: str,
) -> None:
    if type(values) is not tuple or any(
        type(row) is not tuple
        or len(row) != 2
        or not isinstance(row[0], str)
        or not row[0]
        or not isinstance(row[1], bytes)
        for row in values
    ):
        raise ValueError(f"{field} is malformed")
    if len({row[0] for row in values}) != len(values):
        raise ValueError(f"{field} contains duplicate names")
    for name, payload in values:
        _input_mapping(payload, field=f"{field}.{name}")


def _validate_named_raw_rows(
    values: tuple[tuple[str, bytes], ...],
    *,
    field: str,
) -> None:
    if type(values) is not tuple or any(
        type(row) is not tuple
        or len(row) != 2
        or not isinstance(row[0], str)
        or not row[0]
        or not isinstance(row[1], bytes)
        for row in values
    ):
        raise ValueError(f"{field} is malformed")
    if len({row[0] for row in values}) != len(values):
        raise ValueError(f"{field} contains duplicate names")


def _canonical_directory(value: Path, *, field: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{field} must be a Path")
    path = value
    if not path.is_absolute() or path.resolve(strict=False) != path:
        _fail(f"{field} must be a canonical absolute directory")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ControllerArtifactError(f"{field} is missing or unreadable") from exc
    if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
        _fail(f"{field} must be a canonical regular directory")
    return path


def _strict_relative(value: str, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        _fail(f"{field} is not a strict relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        _fail(f"{field} is not a strict relative path")
    return relative


def _strict_child_path(root: Path, relative: PurePosixPath, *, field: str) -> Path:
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise ControllerArtifactError(f"{field} is missing or unreadable") from exc
        if current.is_symlink():
            _fail(f"{field} is aliased")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            _fail(f"{field} parent is non-directory")
    if current.resolve(strict=False) != current:
        _fail(f"{field} escapes its canonical root")
    return current


def _read_regular(path: Path, *, field: str) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError as exc:
        raise ControllerArtifactError(f"{field} is missing or unreadable") from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        _fail(f"{field} is aliased or nonregular")
    return payload


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        _fail(f"{field} is not a canonical digest")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalByteArtifact:
    """One immutable snapshot of a canonical regular file."""

    path: Path
    relative_path: str
    sha256: str
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("canonical artifact path must be absolute")
        _strict_relative(self.relative_path, field="canonical artifact relative path")
        _digest(self.sha256, field="canonical artifact digest")
        if not isinstance(self.canonical_bytes, bytes) or not self.canonical_bytes:
            raise ValueError("canonical artifact bytes must be nonempty")
        if self.sha256 != _raw_sha256(self.canonical_bytes):
            raise ValueError("canonical artifact digest disagrees with its bytes")


@dataclass(frozen=True, slots=True)
class CanonicalArtifact(CanonicalByteArtifact):
    """One immutable canonical JSON object artifact."""

    def __post_init__(self) -> None:
        super(CanonicalArtifact, self).__post_init__()
        _json_mapping(self.canonical_bytes, field="canonical artifact")

    @property
    def value(self) -> Mapping[str, object]:
        return _json_mapping(self.canonical_bytes, field="canonical artifact")


@dataclass(frozen=True, slots=True)
class CanonicalLedgerRow:
    """One immutable validated trial-ledger row projection."""

    kind: str
    row_digest: str
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("canonical ledger row kind must be nonempty")
        _digest(self.row_digest, field="canonical ledger row digest")
        value = _json_mapping(self.canonical_bytes, field="canonical ledger row")
        if value.get("kind") != self.kind or value.get("row_digest") != self.row_digest:
            raise ValueError("canonical ledger row identity disagrees")

    @property
    def value(self) -> Mapping[str, object]:
        return _json_mapping(self.canonical_bytes, field="canonical ledger row")


@dataclass(frozen=True, slots=True)
class CanonicalScoreRow:
    """One immutable validated score-ledger row projection."""

    opaque_label: str
    row_content_digest: str
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        _digest(self.row_content_digest, field="canonical score row digest")
        value = _json_mapping(self.canonical_bytes, field="canonical score row")
        if (
            value.get("evaluation_label") != self.opaque_label
            or value.get("row_content_digest") != self.row_content_digest
        ):
            raise ValueError("canonical score row identity disagrees")

    @property
    def value(self) -> Mapping[str, object]:
        return _json_mapping(self.canonical_bytes, field="canonical score row")


@dataclass(frozen=True, slots=True)
class PersistedPacket:
    """One exact packet artifact under a frozen trial cell/label binding."""

    cell: TrialCellKey
    opaque_label: str
    artifact: CanonicalArtifact
    packet_sha256: str

    def __post_init__(self) -> None:
        if type(self.cell) is not TrialCellKey:
            raise TypeError("persisted packet cell must be exact TrialCellKey")
        _digest(self.packet_sha256, field="persisted packet digest")
        if canonical_sha256(dict(self.artifact.value)) != self.packet_sha256:
            raise ValueError("persisted packet digest disagrees with packet bytes")

    @property
    def arm_id(self) -> str:
        return self.cell.arm_id

    @property
    def relative_path(self) -> str:
        return self.artifact.relative_path

    @property
    def canonical_packet(self) -> bytes:
        return self.artifact.canonical_bytes[:-1]


@dataclass(frozen=True, slots=True)
class PersistedTrialReplay:
    """Closed replay of every validated authority available for one trial run."""

    run_id: str
    terminal_status: str
    failure_code: str | None
    failure_message: str | None
    workspace: Path
    state_dir: Path
    evidence_root: Path
    trial_request_digest: str
    header_row_digest: str
    cell_domain: tuple[TrialCellKey, ...]
    sealed_opaque_labels: SealedTrialOpaqueLabelMap
    trial_event_ledger: CanonicalByteArtifact
    verdict: CanonicalArtifact | None
    packet_artifact_index: CanonicalArtifact | None
    packets: tuple[PersistedPacket, ...]
    score_ledger: CanonicalByteArtifact | None
    score_rows: tuple[CanonicalScoreRow, ...]
    scorer_settlement_rows: tuple[CanonicalLedgerRow, ...]

    def __post_init__(self) -> None:
        if self.terminal_status not in {"completed", "failed"}:
            raise ValueError("persisted replay terminal status is invalid")
        if not isinstance(self.cell_domain, tuple) or not self.cell_domain:
            raise ValueError("persisted replay cell domain is empty")
        _digest(self.trial_request_digest, field="persisted replay request digest")
        _digest(self.header_row_digest, field="persisted replay header digest")
        if self.terminal_status == "completed":
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("completed persisted replay carries failure data")
            if self.verdict is None or self.packet_artifact_index is None:
                raise ValueError("completed persisted replay is incomplete")
        elif not self.failure_code or not self.failure_message:
            raise ValueError("failed persisted replay lacks its diagnostic")

    @property
    def packet_index(self) -> Mapping[str, object] | None:
        return (
            None
            if self.packet_artifact_index is None
            else self.packet_artifact_index.value
        )

    @property
    def packet_index_record(self) -> Mapping[str, object] | None:
        return self.packet_index

    @property
    def trial_event_ledger_path(self) -> Path:
        return self.trial_event_ledger.path

    @property
    def score_ledger_path(self) -> Path | None:
        return None if self.score_ledger is None else self.score_ledger.path


@dataclass(frozen=True, slots=True)
class AttemptRecordInputs:
    """Closed non-provider inputs for the public artifact-backed attempt builder."""

    attempt_id: str
    replay: PersistedTrialReplay | None
    trial_result: TrialRunResult | None
    frozen_trial_artifact_authority: bytes
    trial_event_ledger_path: Path | None
    arm_route_ids: tuple[tuple[str, str], ...]
    evaluation_route_id: str | None
    material_disagreement: bool
    review_settlements: tuple[bytes, ...]
    receipt_bindings: tuple[bytes, ...]
    source_task_binding_valid: bool
    controller_launch_preallocation_failed: bool
    common_provider_outage_proven: bool
    evaluation_bytes_valid: bool
    blinding_join_valid: bool
    interrupted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id:
            raise ValueError("attempt finalization id must be nonempty")
        attempts.load_frozen_trial_artifact_authority(
            self.frozen_trial_artifact_authority
        )
        if self.replay is not None:
            if type(self.replay) is not PersistedTrialReplay:
                raise TypeError("attempt finalization replay must be exact or None")
            if (
                type(self.trial_result) is not TrialRunResult
                or self.trial_result.run_id != self.replay.run_id
                or self.trial_result.terminal_status != self.replay.terminal_status
                or self.trial_event_ledger_path
                != self.replay.trial_event_ledger_path
            ):
                raise ValueError("attempt replay prefix binding disagrees")
        elif self.trial_result is not None and type(self.trial_result) is not TrialRunResult:
            raise TypeError("attempt trial result must be exact or None")
        if self.trial_event_ledger_path is not None and not isinstance(
            self.trial_event_ledger_path,
            Path,
        ):
            raise TypeError("attempt ledger path must be Path or None")
        if type(self.arm_route_ids) is not tuple or any(
            type(row) is not tuple
            or len(row) != 2
            or not all(isinstance(value, str) and value for value in row)
            for row in self.arm_route_ids
        ):
            raise ValueError("attempt finalization routes are malformed")
        for name in ("review_settlements", "receipt_bindings"):
            values = getattr(self, name)
            if type(values) is not tuple:
                raise TypeError(f"{name} must be an exact tuple")
            for index, value in enumerate(values):
                _input_mapping(value, field=f"{name}[{index}]")
        for name in (
            "material_disagreement",
            "source_task_binding_valid",
            "controller_launch_preallocation_failed",
            "common_provider_outage_proven",
            "evaluation_bytes_valid",
            "blinding_join_valid",
            "interrupted",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be exact bool")


@dataclass(frozen=True, slots=True)
class PartialIndexInputs:
    """Closed sparse evidence inputs for one invalid/interrupted attempt."""

    frozen_call_authority: bytes
    receipts_by_slot: tuple[tuple[str, bytes], ...]
    raw_jsonl_by_slot: tuple[tuple[str, bytes], ...]
    elapsed_ms_by_slot: tuple[tuple[str, int], ...]
    call_allocations: tuple[bytes, ...]
    partial_evidence: bytes | None
    invalidity_authority: bytes | None = None

    def __post_init__(self) -> None:
        _input_mapping(self.frozen_call_authority, field="frozen_call_authority")
        _validate_named_json_rows(self.receipts_by_slot, field="receipts_by_slot")
        _validate_named_raw_rows(self.raw_jsonl_by_slot, field="raw_jsonl_by_slot")
        if type(self.elapsed_ms_by_slot) is not tuple or any(
            type(row) is not tuple
            or len(row) != 2
            or not isinstance(row[0], str)
            or type(row[1]) is not int
            or row[1] < 0
            for row in self.elapsed_ms_by_slot
        ):
            raise ValueError("elapsed_ms_by_slot is malformed")
        if type(self.call_allocations) is not tuple:
            raise TypeError("call_allocations must be an exact tuple")
        for index, row in enumerate(self.call_allocations):
            _input_mapping(row, field=f"call_allocations[{index}]")
        if self.partial_evidence is not None:
            _input_mapping(self.partial_evidence, field="partial_evidence")
        if self.invalidity_authority is not None:
            _invalidity_authority_mapping(self.invalidity_authority)


@dataclass(frozen=True, slots=True)
class CompleteIndexInputs:
    """Closed complete evidence inputs for the public synthesis index builder."""

    private_join: blinding.PrivateBlindingJoin
    public_packet_replay_inputs: bytes
    private_blinding_replay_inputs: bytes
    packets_by_arm: tuple[tuple[str, bytes], ...]
    review_records_by_slot: tuple[tuple[str, bytes], ...]
    adjudication_payload: bytes | None
    integrated_payload: bytes
    hard_evidence_by_arm: tuple[tuple[str, bytes], ...]
    oriented_primary: blinding.OrientedPrimaryPair
    hard_primary_outcome: hard_contract.HardPrimaryOutcome
    receipts_by_slot: tuple[tuple[str, bytes], ...]
    raw_jsonl_by_slot: tuple[tuple[str, bytes], ...]
    frozen_call_authority: bytes
    call_allocations: tuple[bytes, ...]
    elapsed_ms_by_slot: tuple[tuple[str, int], ...]
    scorer_settlement_rows_by_label: tuple[tuple[str, bytes], ...]
    score_rows_by_label: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        if type(self.private_join) is not blinding.PrivateBlindingJoin:
            raise TypeError("complete finalization private join must be exact")
        if type(self.oriented_primary) is not blinding.OrientedPrimaryPair:
            raise TypeError("complete finalization oriented primary must be exact")
        if type(self.hard_primary_outcome) is not hard_contract.HardPrimaryOutcome:
            raise TypeError("complete finalization hard primary must be exact")
        for name in (
            "public_packet_replay_inputs",
            "private_blinding_replay_inputs",
            "integrated_payload",
            "frozen_call_authority",
        ):
            _input_mapping(getattr(self, name), field=name)
        if self.adjudication_payload is not None:
            _input_mapping(self.adjudication_payload, field="adjudication_payload")
        for name in (
            "packets_by_arm",
            "review_records_by_slot",
            "hard_evidence_by_arm",
            "receipts_by_slot",
            "scorer_settlement_rows_by_label",
            "score_rows_by_label",
        ):
            _validate_named_json_rows(getattr(self, name), field=name)
        _validate_named_raw_rows(self.raw_jsonl_by_slot, field="raw_jsonl_by_slot")
        if type(self.call_allocations) is not tuple:
            raise TypeError("call_allocations must be an exact tuple")
        for index, row in enumerate(self.call_allocations):
            _input_mapping(row, field=f"call_allocations[{index}]")
        if type(self.elapsed_ms_by_slot) is not tuple or any(
            type(row) is not tuple
            or len(row) != 2
            or not isinstance(row[0], str)
            or type(row[1]) is not int
            or row[1] < 0
            for row in self.elapsed_ms_by_slot
        ):
            raise ValueError("elapsed_ms_by_slot is malformed")


@dataclass(frozen=True, slots=True)
class ProviderEvidenceInput:
    """One frozen treatment/scorer receipt and its prelaunch allocation row."""

    call_slot_id: str
    canonical_receipt: bytes
    raw_jsonl: bytes
    elapsed_ms: int
    call_allocation: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.call_slot_id, str) or not self.call_slot_id:
            raise ValueError("provider evidence call slot must be nonempty")
        _input_mapping(self.canonical_receipt, field="provider receipt")
        _input_mapping(self.call_allocation, field="provider call allocation")
        if not isinstance(self.raw_jsonl, bytes):
            raise TypeError("provider raw JSONL must be bytes")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            raise ValueError("provider elapsed time is invalid")


@dataclass(frozen=True, slots=True)
class ReviewEvidenceInput:
    """One frozen controller review, receipt, and allocation row."""

    call_slot_id: str
    canonical_record: bytes
    canonical_receipt: bytes
    raw_jsonl: bytes
    elapsed_ms: int
    call_allocation: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.call_slot_id, str) or not self.call_slot_id:
            raise ValueError("review evidence call slot must be nonempty")
        for name in ("canonical_record", "canonical_receipt", "call_allocation"):
            _input_mapping(getattr(self, name), field=f"review {name}")
        if not isinstance(self.raw_jsonl, bytes):
            raise TypeError("review raw JSONL must be bytes")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            raise ValueError("review elapsed time is invalid")


@dataclass(frozen=True, slots=True)
class HardEvidenceInput:
    """One arm's frozen PRESENT replay or MISSING absence authority."""

    arm_id: str
    trusted_product_freeze_status: str
    canonical_inputs: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, str) or not self.arm_id:
            raise ValueError("hard evidence arm must be nonempty")
        if self.trusted_product_freeze_status not in {"PRESENT", "MISSING"}:
            raise ValueError("hard evidence status is invalid")
        _input_mapping(self.canonical_inputs, field=f"hard evidence {self.arm_id}")


@dataclass(frozen=True, slots=True)
class AttemptIndexBinding:
    """One controller-package history row bound to exact index file bytes."""

    attempt_id: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        if self.relative_path != attempt_index_relative_path(self.attempt_id):
            raise ValueError("attempt index history path is noncanonical")
        _digest(self.sha256, field="attempt index history digest")


@dataclass(frozen=True, slots=True)
class FinalizationAssembly:
    """One closed in-memory attempt ready for canonical evidence settlement."""

    evidence_root: Path
    decision_lock: bytes
    randomization_manifest: bytes
    expected_bindings: tuple[tuple[str, str], ...]
    attempt: AttemptRecordInputs
    index: CompleteIndexInputs | PartialIndexInputs
    prior_indexes: tuple[AttemptIndexBinding, ...]
    expected_attempt_record: bytes | None
    expected_absolute_call_ceiling: int
    expected_denominator: int

    def __post_init__(self) -> None:
        _canonical_directory(self.evidence_root, field="evidence_root")
        _input_mapping(self.decision_lock, field="decision_lock")
        _input_mapping(self.randomization_manifest, field="randomization_manifest")
        if type(self.expected_bindings) is not tuple or any(
            type(row) is not tuple
            or len(row) != 2
            or not isinstance(row[0], str)
            or _DIGEST_RE.fullmatch(row[1]) is None
            for row in self.expected_bindings
        ):
            raise ValueError("finalization expected bindings are malformed")
        if tuple(sorted(self.expected_bindings)) != self.expected_bindings:
            raise ValueError("finalization expected bindings are not canonical")
        if type(self.attempt) is not AttemptRecordInputs:
            raise TypeError("finalization attempt inputs must be exact")
        if type(self.index) not in {CompleteIndexInputs, PartialIndexInputs}:
            raise TypeError("finalization index inputs are unsupported")
        if type(self.prior_indexes) is not tuple or any(
            type(row) is not AttemptIndexBinding for row in self.prior_indexes
        ):
            raise TypeError("finalization history must be exact bindings")
        if self.expected_attempt_record is not None:
            _input_mapping(
                self.expected_attempt_record,
                field="expected_attempt_record",
            )
        for name in ("expected_absolute_call_ceiling", "expected_denominator"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class FinalizedArtifacts:
    """Canonical current-attempt bytes and the derived locked transition."""

    attempt_record: bytes
    attempt_index: bytes
    attempt_index_sha256: str
    index_binding: AttemptIndexBinding
    report: bytes | None
    stopped: bool
    next_attempt_id: str | None


def attempt_index_relative_path(attempt_id: str) -> str:
    if not isinstance(attempt_id, str) or re.fullmatch(
        r"ES-ATTEMPT-[0-9]{2}", attempt_id
    ) is None:
        raise ValueError("attempt id is invalid")
    return f"attempts/{attempt_id}/index.json"


def attempt_record_relative_path(attempt_id: str) -> str:
    attempt_index_relative_path(attempt_id)
    return f"attempts/{attempt_id}/record.json"


def _artifact(
    *,
    root: Path,
    relative_path: str,
    field: str,
) -> CanonicalArtifact:
    relative = _strict_relative(relative_path, field=field)
    path = _strict_child_path(root, relative, field=field)
    payload = _read_regular(path, field=field)
    _json_mapping(payload, field=field)
    return CanonicalArtifact(
        path=path,
        relative_path=relative.as_posix(),
        sha256=_raw_sha256(payload),
        canonical_bytes=payload,
    )


def _ledger_candidates(run_root: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for directory, names, files in os.walk(run_root, followlinks=False):
        root = Path(directory)
        retained: list[str] = []
        for name in names:
            path = root / name
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise ControllerArtifactError(
                    "trial run tree is unreadable"
                ) from exc
            if path.is_symlink():
                _fail("trial run tree contains an aliased directory")
            if not stat.S_ISDIR(metadata.st_mode):
                _fail("trial run tree contains a non-directory traversal entry")
            retained.append(name)
        names[:] = retained
        if "trial-events.jsonl" not in files:
            continue
        candidate = root / "trial-events.jsonl"
        _read_regular(candidate, field="trial event ledger")
        candidates.append(candidate)
    return tuple(sorted(candidates))


def _one_row(
    ledger: TrialEventLedger,
    kind: str,
    *,
    required: bool,
) -> TrialLedgerRow | None:
    rows = tuple(row for row in ledger.rows if row.kind == kind)
    if len(rows) > 1 or (required and len(rows) != 1):
        _fail(f"trial {kind} authority is missing or ambiguous")
    return rows[0] if rows else None


def _sealed_labels(header: Mapping[str, Any]) -> tuple[
    tuple[TrialCellKey, ...], SealedTrialOpaqueLabelMap
]:
    try:
        raw_domain = header["cell_domain"]
        raw_map = header["sealed_opaque_label_map"]
        raw_digest = header["sealed_opaque_label_map_digest"]
    except KeyError as exc:
        raise ControllerArtifactError("trial header authority is incomplete") from exc
    if not isinstance(raw_domain, list) or not isinstance(raw_map, Mapping):
        _fail("trial header domain or label map is malformed")
    try:
        domain = tuple(
            TrialCellKey(arm_id=value["arm_id"], rep=value["rep"])
            for value in raw_domain
            if isinstance(value, Mapping) and set(value) == {"arm_id", "rep"}
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ControllerArtifactError("trial header cell domain is malformed") from exc
    if len(domain) != len(raw_domain) or not domain:
        _fail("trial header cell domain is malformed")
    bindings = raw_map.get("bindings")
    if raw_map.get("schema_version") != "trial_opaque_label_map.v1" or not isinstance(
        bindings, list
    ):
        _fail("trial header sealed-label map is malformed")
    labels: list[str] = []
    for cell, value in zip(domain, bindings, strict=True):
        if (
            not isinstance(value, Mapping)
            or set(value) != {"cell", "opaque_label"}
            or value.get("cell") != cell.record
            or not isinstance(value.get("opaque_label"), str)
        ):
            _fail("trial header sealed-label map is malformed")
        labels.append(str(value["opaque_label"]))
    try:
        sealed = build_sealed_opaque_label_map(domain, labels=tuple(labels))
    except (TypeError, ValueError) as exc:
        raise ControllerArtifactError("trial header sealed-label map is malformed") from exc
    if sealed.record != raw_map or sealed.digest != raw_digest:
        _fail("trial header sealed-label digest disagrees")
    return domain, sealed


def _packet_authority(
    *,
    workspace: Path,
    ledger: TrialEventLedger,
    trial_request_digest: str,
    header_row_digest: str,
    domain: tuple[TrialCellKey, ...],
    sealed: SealedTrialOpaqueLabelMap,
    completed: bool,
) -> tuple[CanonicalArtifact | None, tuple[PersistedPacket, ...]]:
    evidence = _one_row(ledger, "evidence_frozen", required=completed)
    checks = _one_row(ledger, "checks_frozen", required=completed)
    frozen = _one_row(ledger, "packets_frozen", required=completed)
    request_hex = trial_request_digest.removeprefix("sha256:")
    index_relpath = f"artifacts/trials/{request_hex}/packets/index.json"
    index_path = workspace.joinpath(*PurePosixPath(index_relpath).parts)
    index_exists = os.path.lexists(index_path)
    if frozen is None:
        return None, ()
    if evidence is None or checks is None:
        _fail("packet freeze lacks evidence/check authority")
    raw_frozen = frozen.payload.get("cell_packets")
    if not isinstance(raw_frozen, list) or len(raw_frozen) != len(domain):
        _fail("packet-freeze domain is malformed")
    expected_rows: list[dict[str, object]] = []
    for cell, binding, raw in zip(
        domain,
        sealed.bindings,
        raw_frozen,
        strict=True,
    ):
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"cell", "opaque_label", "packet_digest"}
            or raw.get("cell") != cell.record
            or raw.get("opaque_label") != binding.opaque_label
        ):
            _fail("packet-freeze row is malformed")
        packet_digest = _digest(raw.get("packet_digest"), field="packet digest")
        expected_rows.append(
            {
                "cell": cell.record,
                "opaque_label": binding.opaque_label,
                "packet_digest": packet_digest,
                "packet_relpath": (
                    f"artifacts/trials/{request_hex}/packets/"
                    f"{packet_digest.removeprefix('sha256:')}.json"
                ),
            }
        )
    if not index_exists:
        if completed:
            _fail("completed trial packet index is missing")
        return None, _available_packets(
            workspace=workspace,
            expected_rows=expected_rows,
            domain=domain,
        )
    index_artifact = _artifact(
        root=workspace,
        relative_path=index_relpath,
        field="packet artifact index",
    )
    index = dict(index_artifact.value)
    expected_index = {
        "schema_version": "trial.packet_artifact_index.v1",
        "trial_request_digest": trial_request_digest,
        "header_row_digest": header_row_digest,
        "evidence_frozen_row_digest": evidence.row_digest,
        "checks_frozen_row_digest": checks.row_digest,
        "packets_frozen_row_digest": frozen.row_digest,
        "sealed_opaque_label_map_digest": sealed.digest,
        "packet_set_digest": frozen.payload.get("packet_set_digest"),
        "packets": expected_rows,
    }
    if set(index) != _PACKET_INDEX_KEYS or index != expected_index:
        _fail("packet artifact index disagrees with frozen trial authority")
    packets = _available_packets(
        workspace=workspace,
        expected_rows=expected_rows,
        domain=domain,
    )
    if len(packets) != len(domain):
        _fail("packet artifact set is incomplete")
    expected_names = {"index.json"} | {
        PurePosixPath(str(row["packet_relpath"])).name for row in expected_rows
    }
    packet_dir = index_artifact.path.parent
    try:
        observed_names = {path.name for path in packet_dir.iterdir()}
    except OSError as exc:
        raise ControllerArtifactError("packet artifact directory is unreadable") from exc
    if observed_names != expected_names:
        _fail("packet artifact directory is not the exact frozen set")
    return index_artifact, packets


def _available_packets(
    *,
    workspace: Path,
    expected_rows: Sequence[Mapping[str, object]],
    domain: tuple[TrialCellKey, ...],
) -> tuple[PersistedPacket, ...]:
    packets: list[PersistedPacket] = []
    for cell, row in zip(domain, expected_rows, strict=True):
        relpath = str(row["packet_relpath"])
        relative = _strict_relative(relpath, field="packet artifact path")
        path = workspace.joinpath(*relative.parts)
        if not os.path.lexists(path):
            continue
        artifact = _artifact(
            root=workspace,
            relative_path=relpath,
            field="packet artifact",
        )
        packet = dict(artifact.value)
        try:
            checked = validate_trial_evaluation_packet(packet)
        except (TypeError, ValueError, TrialPacketError) as exc:
            raise ControllerArtifactError("packet artifact is invalid") from exc
        digest = canonical_sha256(checked)
        if (
            digest != row["packet_digest"]
            or packet != checked
            or packet.get("evaluation_id") != row["opaque_label"]
        ):
            _fail("packet artifact digest or label disagrees")
        packets.append(
            PersistedPacket(
                cell=cell,
                opaque_label=str(row["opaque_label"]),
                artifact=artifact,
                packet_sha256=digest,
            )
        )
    return tuple(packets)


def _score_authority(
    *,
    state_dir: Path,
    ledger_path: Path,
    ledger: TrialEventLedger,
    completed: bool,
) -> tuple[
    CanonicalByteArtifact | None,
    tuple[CanonicalScoreRow, ...],
    tuple[CanonicalLedgerRow, ...],
]:
    path = ledger_path.parent / "scores.jsonl"
    settlements = tuple(row for row in ledger.rows if row.kind == "score_settled")
    if not os.path.lexists(path):
        if settlements or completed:
            _fail("trial score ledger is missing")
        return None, (), ()
    raw = _read_regular(path, field="trial score ledger")
    try:
        scores = load_trial_score_rows(
            path,
            validation_mode="complete" if completed else "partial",
        )
    except (OSError, ValueError, TrialLedgerError) as exc:
        raise ControllerArtifactError("trial score ledger is invalid") from exc
    by_label = {str(row["evaluation_label"]): row for row in scores}
    settlement_records: list[CanonicalLedgerRow] = []
    for row in settlements:
        label = str(row.payload["opaque_label"])
        score = by_label.get(label)
        if (
            score is None
            or score.get("row_content_digest")
            != row.payload.get("score_row_content_digest")
        ):
            _fail("trial score settlement disagrees with score ledger")
        settlement_records.append(
            CanonicalLedgerRow(
                kind=row.kind,
                row_digest=row.row_digest,
                canonical_bytes=canonical_json_bytes(row.record) + b"\n",
            )
        )
    if completed and (
        len(scores) != len(settlements)
        or {str(row["evaluation_label"]) for row in scores}
        != {str(row.payload["opaque_label"]) for row in settlements}
    ):
        _fail("completed trial score authority is incomplete")
    artifact = CanonicalByteArtifact(
        path=path,
        relative_path=path.relative_to(state_dir).as_posix(),
        sha256=_raw_sha256(raw),
        canonical_bytes=raw,
    )
    score_records = tuple(
        CanonicalScoreRow(
            opaque_label=str(row["evaluation_label"]),
            row_content_digest=str(row["row_content_digest"]),
            canonical_bytes=canonical_json_bytes(row) + b"\n",
        )
        for row in scores
    )
    return artifact, score_records, tuple(settlement_records)


def _verdict_authority(
    *,
    result: TrialRunResult,
    workspace: Path,
    ledger: TrialEventLedger,
    trial_request_digest: str,
    sealed: SealedTrialOpaqueLabelMap,
    score_rows: tuple[CanonicalScoreRow, ...],
    completed: bool,
) -> CanonicalArtifact | None:
    evidence = _one_row(ledger, "evidence_frozen", required=completed)
    checks = _one_row(ledger, "checks_frozen", required=completed)
    scorer = _one_row(ledger, "scorer_frozen", required=completed)
    scores = _one_row(ledger, "scores_frozen", required=completed)
    aggregation = _one_row(ledger, "aggregation_frozen", required=completed)
    settled = _one_row(ledger, "verdict_settled", required=completed)
    published = _one_row(ledger, "verdict_published", required=completed)
    prepared = _one_row(ledger, "trial_prepared", required=completed)
    committed = _one_row(ledger, "trial_parent_committed", required=completed)
    del committed
    if published is None:
        return None
    relpath = published.payload.get("verdict_artifact_relpath")
    expected_relpath = (
        "artifacts/trials/"
        + trial_request_digest.removeprefix("sha256:")
        + "/verdict.json"
    )
    if relpath != expected_relpath:
        _fail("trial verdict path disagrees with request identity")
    artifact = _artifact(
        root=workspace,
        relative_path=expected_relpath,
        field="trial verdict artifact",
    )
    record = dict(artifact.value)
    if set(record) != _VERDICT_KEYS or record.get("schema_version") != (
        "trial.verdict_artifact.v1"
    ):
        _fail("trial verdict artifact is not a closed supported record")
    authority = {key: value for key, value in record.items() if key != "artifact_digest"}
    if record.get("artifact_digest") != canonical_sha256(authority):
        _fail("trial verdict artifact digest disagrees")
    if canonical_sha256(record.get("verdict")) != record.get("verdict_digest"):
        _fail("trial verdict value digest disagrees")
    if canonical_sha256(record.get("authored_outcomes")) != (
        aggregation.payload.get("final_outcomes_digest") if aggregation else None
    ):
        _fail("trial verdict authored outcomes disagree")
    score_values = [dict(row.value) for row in score_rows]
    if canonical_sha256(score_values) != record.get("score_digest"):
        _fail("trial verdict score digest disagrees")
    header = ledger.rows[0].payload
    expected = {
        "trial_request_digest": trial_request_digest,
        "evaluation_digest": header.get("evaluation_digest"),
        "evidence_frozen_digest": evidence.row_digest if evidence else None,
        "checks_frozen_digest": checks.row_digest if checks else None,
        "scorer_identity_digest": (
            scorer.payload.get("scorer_identity_digest") if scorer else None
        ),
        "sealed_label_map_digest": sealed.digest,
        "verdict_digest": settled.payload.get("verdict_digest") if settled else None,
        "artifact_digest": published.payload.get("verdict_artifact_digest"),
    }
    if any(record.get(key) != value for key, value in expected.items()):
        _fail("trial verdict artifact authority disagrees with ledger")
    if prepared is not None and (
        prepared.payload.get("verdict_artifact_relpath") != expected_relpath
        or prepared.payload.get("verdict_artifact_digest") != record["artifact_digest"]
        or prepared.payload.get("verdict_digest") != record["verdict_digest"]
    ):
        _fail("trial prepared verdict authority disagrees")
    if completed and (
        result.verdict_path != expected_relpath
        or result.verdict_digest != record["verdict_digest"]
    ):
        _fail("public trial result disagrees with verdict artifact")
    if scores is None or aggregation is None:
        _fail("published trial verdict lacks score aggregation authority")
    return artifact


def replay_trial_run_artifacts(
    result: TrialRunResult,
    *,
    workspace: Path,
    state_dir: Path,
    evidence_root: Path,
) -> PersistedTrialReplay:
    """Replay one public trial result solely from its canonical persisted bytes."""

    if type(result) is not TrialRunResult:
        raise TypeError("trial replay result must be exact TrialRunResult")
    root = _canonical_directory(workspace, field="workspace")
    runs = _canonical_directory(state_dir, field="state_dir")
    evidence = _canonical_directory(evidence_root, field="evidence_root")
    if _RUN_ID_RE.fullmatch(result.run_id) is None:
        _fail("trial run_id is not a safe state-directory segment")
    run_root = _strict_child_path(
        runs,
        PurePosixPath(result.run_id),
        field="trial run root",
    )
    try:
        run_metadata = run_root.lstat()
    except OSError as exc:
        raise ControllerArtifactError("trial run root is missing") from exc
    if not stat.S_ISDIR(run_metadata.st_mode) or run_root.is_symlink():
        _fail("trial run root is aliased or non-directory")
    candidates = _ledger_candidates(run_root)
    if len(candidates) != 1:
        _fail("trial event ledger is missing or ambiguous")
    ledger_path = candidates[0]
    ledger_raw = _read_regular(ledger_path, field="trial event ledger")
    try:
        ledger = load_trial_event_ledger(ledger_path)
    except (OSError, ValueError, TrialLedgerError) as exc:
        raise ControllerArtifactError("trial event ledger is invalid") from exc
    header_row = ledger.rows[0]
    header = header_row.payload
    trial_request_digest = _digest(
        header.get("trial_request_digest"),
        field="trial request digest",
    )
    domain, sealed = _sealed_labels(header)
    completed = result.terminal_status == "completed"
    packet_index, packets = _packet_authority(
        workspace=root,
        ledger=ledger,
        trial_request_digest=trial_request_digest,
        header_row_digest=header_row.row_digest,
        domain=domain,
        sealed=sealed,
        completed=completed,
    )
    score_ledger, score_rows, score_settlements = _score_authority(
        state_dir=runs,
        ledger_path=ledger_path,
        ledger=ledger,
        completed=completed,
    )
    verdict = _verdict_authority(
        result=result,
        workspace=root,
        ledger=ledger,
        trial_request_digest=trial_request_digest,
        sealed=sealed,
        score_rows=score_rows,
        completed=completed,
    )
    failure = result.failure_diagnostic
    return PersistedTrialReplay(
        run_id=result.run_id,
        terminal_status=result.terminal_status,
        failure_code=None if failure is None else failure.code,
        failure_message=None if failure is None else failure.message,
        workspace=root,
        state_dir=runs,
        evidence_root=evidence,
        trial_request_digest=trial_request_digest,
        header_row_digest=header_row.row_digest,
        cell_domain=domain,
        sealed_opaque_labels=sealed,
        trial_event_ledger=CanonicalByteArtifact(
            path=ledger_path,
            relative_path=ledger_path.relative_to(runs).as_posix(),
            sha256=_raw_sha256(ledger_raw),
            canonical_bytes=ledger_raw,
        ),
        verdict=verdict,
        packet_artifact_index=packet_index,
        packets=packets,
        score_ledger=score_ledger,
        score_rows=score_rows,
        scorer_settlement_rows=score_settlements,
    )


def _contract_values(
    assembly: FinalizationAssembly,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    lock = _input_mapping(assembly.decision_lock, field="decision_lock")
    schedule = _input_mapping(
        assembly.randomization_manifest,
        field="randomization_manifest",
    )
    bindings = dict(assembly.expected_bindings)
    if len(bindings) != len(assembly.expected_bindings):
        _fail("finalization expected bindings are duplicated")
    return lock, schedule, bindings


def _attempt_record(
    assembly: FinalizationAssembly,
    *,
    lock: Mapping[str, object],
    schedule: Mapping[str, object],
    bindings: Mapping[str, object],
) -> dict[str, Any]:
    value = assembly.attempt
    replay = value.replay
    packet_index = None if replay is None else replay.packet_index_record
    try:
        record = attempts.build_attempt_record_from_artifacts(
            attempt_id=value.attempt_id,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
            frozen_trial_artifact_authority=(
                value.frozen_trial_artifact_authority
            ),
            trial_result=value.trial_result,
            observed_header_row_digest=(
                None if replay is None else replay.header_row_digest
            ),
            observed_sealed_opaque_labels=(
                None if replay is None else replay.sealed_opaque_labels
            ),
            trial_event_ledger_path=value.trial_event_ledger_path,
            packet_artifact_index=(
                None if packet_index is None else dict(packet_index)
            ),
            arm_route_ids=dict(value.arm_route_ids),
            evaluation_route_id=value.evaluation_route_id,
            material_disagreement=value.material_disagreement,
            review_settlements=[
                _input_mapping(row, field="review_settlement")
                for row in value.review_settlements
            ],
            receipt_bindings=[
                _input_mapping(row, field="receipt_binding")
                for row in value.receipt_bindings
            ],
            source_task_binding_valid=value.source_task_binding_valid,
            controller_launch_preallocation_failed=(
                value.controller_launch_preallocation_failed
            ),
            common_provider_outage_proven=value.common_provider_outage_proven,
            evaluation_bytes_valid=value.evaluation_bytes_valid,
            blinding_join_valid=value.blinding_join_valid,
            interrupted=value.interrupted,
        )
    except (TypeError, ValueError, attempts.AttemptAccountingError) as exc:
        raise ControllerArtifactError("attempt record finalization failed") from exc
    encoded = canonical_json_bytes(record)
    if (
        assembly.expected_attempt_record is not None
        and assembly.expected_attempt_record != encoded
    ):
        _fail("attempt record disagrees with controller assembly")
    return record


def _named_mappings(
    values: tuple[tuple[str, bytes], ...],
    *,
    field: str,
) -> dict[str, dict[str, Any]]:
    return {
        name: _input_mapping(payload, field=f"{field}.{name}")
        for name, payload in values
    }


def _study_digest(value: object) -> str:
    return _raw_sha256(canonical_json_bytes(value) + b"\n")


def _scorer_settlement_label(row: CanonicalLedgerRow) -> str:
    payload = row.value.get("payload")
    if not isinstance(payload, Mapping):
        _fail("scorer settlement payload is malformed")
    label = payload.get("opaque_label")
    if not isinstance(label, str) or not label:
        _fail("scorer settlement label is malformed")
    return label


def _hard_spec_and_freeze(
    value: HardEvidenceInput,
) -> tuple[dict[str, Any], dict[str, Any], hard_contract.HardEvaluationFreeze | None]:
    inputs = _input_mapping(
        value.canonical_inputs,
        field=f"hard evidence {value.arm_id}",
    )
    if value.trusted_product_freeze_status == "MISSING":
        spec = {
            "trusted_product_freeze_status": "MISSING",
            "absence_authority": inputs,
        }
        row = {
            "schema_version": "es.hard_evaluation_evidence.v1",
            "arm_id": value.arm_id,
            **spec,
        }
        return spec, row, None
    try:
        freeze = hard_contract.derive_hard_evaluation(
            candidate_claims=inputs["candidate_claims"],
            evaluator_observations=inputs["evaluator_observations"],
            proof_rows=inputs["proof_rows"],
            frozen_registry=set(inputs["frozen_registry"]),
            trusted_product_freeze_digest=inputs[
                "trusted_product_freeze_digest"
            ],
            evaluator_identity_digest=inputs["evaluator_identity_digest"],
            task_identity_digest=inputs["task_identity_digest"],
            fixture_identity_digest=inputs["fixture_identity_digest"],
            frozen_proof_authority=inputs["frozen_proof_authority"],
        )
    except (KeyError, TypeError, ValueError, hard_contract.HardContractError) as exc:
        raise ControllerArtifactError(
            f"hard evidence replay is invalid for {value.arm_id}"
        ) from exc
    spec = {
        "trusted_product_freeze_status": "PRESENT",
        "replay_inputs": inputs,
    }
    row = {
        "schema_version": "es.hard_evaluation_evidence.v1",
        "arm_id": value.arm_id,
        "trusted_product_freeze_status": "PRESENT",
        "replay_inputs": inputs,
        "freeze": freeze.record,
        "freeze_sha256": freeze.digest,
        "evaluation": freeze.evaluation,
        "evaluation_sha256": freeze.evaluation_digest,
    }
    return spec, row, freeze


def _ordered_partial_call_evidence(
    *,
    provider_evidence: tuple[ProviderEvidenceInput, ...],
    review_evidence: tuple[ReviewEvidenceInput, ...],
    call_allocations: tuple[bytes, ...],
) -> tuple[ProviderEvidenceInput | ReviewEvidenceInput, ...]:
    if type(provider_evidence) is not tuple or any(
        type(value) is not ProviderEvidenceInput for value in provider_evidence
    ):
        raise TypeError("provider_evidence must be an exact tuple")
    if type(review_evidence) is not tuple or any(
        type(value) is not ReviewEvidenceInput for value in review_evidence
    ):
        raise TypeError("review_evidence must be an exact tuple")
    if type(call_allocations) is not tuple:
        raise TypeError("call_allocations must be an exact tuple")

    evidence = (*provider_evidence, *review_evidence)
    evidence_by_slot: dict[str, ProviderEvidenceInput | ReviewEvidenceInput] = {}
    for value in evidence:
        if value.call_slot_id in evidence_by_slot:
            _fail("partial call evidence contains duplicate slots")
        evidence_by_slot[value.call_slot_id] = value

    allocation_bytes_by_slot: dict[str, bytes] = {}
    settled_slots: set[str] = set()
    ordered_slots: list[str] = []
    for index, raw in enumerate(call_allocations):
        allocation = _input_mapping(raw, field=f"call_allocations[{index}]")
        if set(allocation) != _CALL_ALLOCATION_KEYS:
            _fail("partial call allocation shape is invalid")
        slot = allocation["call_slot_id"]
        authority = allocation["allocation_authority"]
        if (
            allocation["schema_version"] != "es.call_allocation.v2"
            or not isinstance(slot, str)
            or not slot
            or slot in allocation_bytes_by_slot
            or not isinstance(authority, dict)
            or authority.get("call_slot_id") != slot
            or allocation["allocation_sha256"] != canonical_sha256(authority)
        ):
            _fail("partial call allocation binding is invalid")
        settlement = allocation["settlement"]
        receipt_digest = allocation["receipt_sha256"]
        if settlement == "RECEIPT_FROZEN":
            _digest(receipt_digest, field="partial call receipt digest")
            settled_slots.add(slot)
        elif settlement == "INTERRUPTED_IN_FLIGHT":
            if receipt_digest is not None:
                _fail("in-flight call allocation carries a receipt")
        else:
            _fail("partial call allocation settlement is invalid")
        allocation_bytes_by_slot[slot] = raw
        ordered_slots.append(slot)

    if settled_slots != set(evidence_by_slot):
        _fail("partial settled call evidence domain disagrees")
    for slot, value in evidence_by_slot.items():
        allocation_bytes = allocation_bytes_by_slot.get(slot)
        if allocation_bytes is None or value.call_allocation != allocation_bytes:
            _fail("partial call evidence allocation disagrees")
        allocation = _input_mapping(
            allocation_bytes,
            field=f"call_allocation.{slot}",
        )
        receipt_digest = _raw_sha256(value.canonical_receipt + b"\n")
        if allocation.get("receipt_sha256") != receipt_digest:
            _fail("partial call evidence receipt disagrees")
    return tuple(
        evidence_by_slot[slot] for slot in ordered_slots if slot in settled_slots
    )


def _partial_evidence_projection(
    *,
    replay: PersistedTrialReplay | None,
    private_join: blinding.PrivateBlindingJoin | None,
    review_evidence: tuple[ReviewEvidenceInput, ...],
    adjudication_payload: bytes | None,
    integrated_payload: bytes | None,
    hard_evidence: tuple[HardEvidenceInput, ...],
) -> bytes | None:
    if replay is not None and type(replay) is not PersistedTrialReplay:
        raise TypeError("partial replay must be exact or None")
    if private_join is not None and type(private_join) is not blinding.PrivateBlindingJoin:
        raise TypeError("partial private join must be exact or None")
    if type(hard_evidence) is not tuple or any(
        type(value) is not HardEvidenceInput for value in hard_evidence
    ):
        raise TypeError("partial hard evidence must be an exact tuple")
    partial: dict[str, Any] = {
        "public_packet_replay_inputs": None,
        "private_blinding_replay_inputs": None,
        "private_blinding_join": None,
        "private_blinding_join_sha256": None,
        "packets": [],
        "scorer_settlements": [],
        "reviews": [],
        "integrated_prior_record_sha256s": [],
        "adjudication_payload": None,
        "adjudication_payload_sha256": None,
        "integrated_payload": None,
        "integrated_payload_sha256": None,
        "hard_evaluations": [],
        "oriented_primary": None,
        "oriented_primary_sha256": None,
        "hard_primary_outcome": None,
        "hard_primary_outcome_sha256": None,
    }
    packet_index = None if replay is None else replay.packet_index_record
    if packet_index is None:
        if (
            private_join is not None
            or review_evidence
            or hard_evidence
            or adjudication_payload is not None
            or integrated_payload is not None
        ):
            _fail("partial downstream evidence lacks durable packet authority")
        return None
    assert replay is not None

    public_replay = {
        "schema_version": "es.public_packet_replay_inputs.v1",
        "request_cell_domain": [cell.record for cell in replay.cell_domain],
        "packet_artifact_index": dict(packet_index),
    }
    packet_rows = [
        {
            "arm_id": packet.arm_id,
            "packet": dict(packet.artifact.value),
            "packet_sha256": packet.packet_sha256,
        }
        for packet in replay.packets
    ]
    settlement_by_label = {
        _scorer_settlement_label(row): dict(row.value)
        for row in replay.scorer_settlement_rows
    }
    score_by_label = {
        row.opaque_label: dict(row.value) for row in replay.score_rows
    }
    if (
        len(settlement_by_label) != len(replay.scorer_settlement_rows)
        or len(score_by_label) != len(replay.score_rows)
        or set(settlement_by_label) != set(score_by_label)
    ):
        _fail("partial scorer prefix is ambiguous")
    scorer_rows = [
        {
            "opaque_label": label,
            "settlement_row": settlement_by_label[label],
            "score_row": score_by_label[label],
        }
        for label in settlement_by_label
    ]

    if private_join is None:
        if (
            review_evidence
            or hard_evidence
            or adjudication_payload is not None
            or integrated_payload is not None
        ):
            _fail("partial private downstream evidence lacks a validated join")
        private_replay: dict[str, object] | None = None
        private_record: dict[str, Any] | None = None
        private_digest: str | None = None
    else:
        private_replay = {
            "schema_version": "es.private_blinding_replay_inputs.v2",
            "sealed_opaque_label_map": replay.sealed_opaque_labels.record,
        }
        private_record = private_join.record
        private_digest = private_join.digest

    review_rows: list[dict[str, Any]] = []
    for value in review_evidence:
        record = _input_mapping(
            value.canonical_record,
            field=f"review_evidence.{value.call_slot_id}",
        )
        review_rows.append(
            {
                "call_slot_id": value.call_slot_id,
                "status": (
                    "FAILED"
                    if record.get("schema_version")
                    == "es_evaluator_call_failure.v1"
                    else "SUCCEEDED"
                ),
                "record": record,
                "record_sha256": _study_digest(record),
            }
        )
    adjudication = (
        None
        if adjudication_payload is None
        else _input_mapping(adjudication_payload, field="adjudication_payload")
    )
    integrated = (
        None
        if integrated_payload is None
        else _input_mapping(integrated_payload, field="integrated_payload")
    )
    hard_rows: list[dict[str, Any]] = []
    seen_arms: set[str] = set()
    for value in hard_evidence:
        if value.arm_id in seen_arms:
            _fail("partial hard evidence contains duplicate arms")
        seen_arms.add(value.arm_id)
        _spec, row, _freeze = _hard_spec_and_freeze(value)
        hard_rows.append(row)
    partial.update({
        "public_packet_replay_inputs": public_replay,
        "private_blinding_replay_inputs": private_replay,
        "private_blinding_join": private_record,
        "private_blinding_join_sha256": private_digest,
        "packets": packet_rows,
        "scorer_settlements": scorer_rows,
        "reviews": review_rows,
        "integrated_prior_record_sha256s": [
            row["record_sha256"]
            for row in review_rows
            if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
        ],
        "adjudication_payload": adjudication,
        "adjudication_payload_sha256": (
            None
            if adjudication is None
            else reviews.canonical_payload_digest(adjudication)
        ),
        "integrated_payload": integrated,
        "integrated_payload_sha256": (
            None
            if integrated is None
            else reviews.canonical_payload_digest(integrated)
        ),
        "hard_evaluations": hard_rows,
        "oriented_primary": None,
        "oriented_primary_sha256": None,
        "hard_primary_outcome": None,
        "hard_primary_outcome_sha256": None,
    })
    return canonical_json_bytes(partial)


def build_partial_index_inputs(
    *,
    replay: PersistedTrialReplay | None,
    private_join: blinding.PrivateBlindingJoin | None,
    review_evidence: tuple[ReviewEvidenceInput, ...],
    provider_evidence: tuple[ProviderEvidenceInput, ...],
    frozen_call_authority: bytes,
    call_allocations: tuple[bytes, ...],
    adjudication_payload: bytes | None = None,
    integrated_payload: bytes | None = None,
    hard_evidence: tuple[HardEvidenceInput, ...] = (),
    invalidity_authority: bytes | None = None,
) -> PartialIndexInputs:
    """Adapt one validated durable prefix into sparse synthesis inputs."""

    _input_mapping(frozen_call_authority, field="frozen_call_authority")
    ordered = _ordered_partial_call_evidence(
        provider_evidence=provider_evidence,
        review_evidence=review_evidence,
        call_allocations=call_allocations,
    )
    partial = _partial_evidence_projection(
        replay=replay,
        private_join=private_join,
        review_evidence=review_evidence,
        adjudication_payload=adjudication_payload,
        integrated_payload=integrated_payload,
        hard_evidence=hard_evidence,
    )
    if invalidity_authority is not None:
        _invalidity_authority_mapping(invalidity_authority)
    return PartialIndexInputs(
        frozen_call_authority=frozen_call_authority,
        receipts_by_slot=tuple(
            (value.call_slot_id, value.canonical_receipt) for value in ordered
        ),
        raw_jsonl_by_slot=tuple(
            (value.call_slot_id, value.raw_jsonl) for value in ordered
        ),
        elapsed_ms_by_slot=tuple(
            (value.call_slot_id, value.elapsed_ms) for value in ordered
        ),
        call_allocations=call_allocations,
        partial_evidence=partial,
        invalidity_authority=invalidity_authority,
    )


def build_complete_index_inputs(
    *,
    replay: PersistedTrialReplay,
    private_join: blinding.PrivateBlindingJoin,
    review_evidence: tuple[ReviewEvidenceInput, ...],
    hard_evidence: tuple[HardEvidenceInput, ...],
    adjudication_payload: bytes | None,
    integrated_payload: bytes,
    frozen_call_authority: bytes,
    provider_evidence: tuple[ProviderEvidenceInput, ...],
) -> CompleteIndexInputs:
    """Adapt controller settlements into the exact complete synthesis inputs."""

    if type(replay) is not PersistedTrialReplay or replay.terminal_status != "completed":
        _fail("complete index inputs require one completed persisted replay")
    if replay.packet_index_record is None or replay.score_ledger is None:
        _fail("complete index inputs require packet and score authority")
    if type(private_join) is not blinding.PrivateBlindingJoin:
        raise TypeError("private_join must be exact PrivateBlindingJoin")
    if type(review_evidence) is not tuple or any(
        type(value) is not ReviewEvidenceInput for value in review_evidence
    ):
        raise TypeError("review_evidence must be an exact tuple")
    if type(hard_evidence) is not tuple or any(
        type(value) is not HardEvidenceInput for value in hard_evidence
    ):
        raise TypeError("hard_evidence must be an exact tuple")
    if type(provider_evidence) is not tuple or any(
        type(value) is not ProviderEvidenceInput for value in provider_evidence
    ):
        raise TypeError("provider_evidence must be an exact tuple")
    arms = tuple(cell.arm_id for cell in replay.cell_domain)
    if tuple(value.arm_id for value in hard_evidence) != arms:
        _fail("hard evidence does not cover the exact replay arm order")
    if private_join.trial_request_digest != replay.trial_request_digest:
        _fail("private join request binding disagrees with replay")
    if adjudication_payload is not None:
        _input_mapping(adjudication_payload, field="adjudication_payload")
    integrated = _input_mapping(integrated_payload, field="integrated_payload")
    _input_mapping(frozen_call_authority, field="frozen_call_authority")

    hard_specs: list[tuple[str, bytes]] = []
    hard_rows: list[dict[str, Any]] = []
    freezes: dict[str, hard_contract.HardEvaluationFreeze | None] = {}
    for value in hard_evidence:
        spec, row, freeze = _hard_spec_and_freeze(value)
        hard_specs.append((value.arm_id, canonical_json_bytes(spec)))
        hard_rows.append(row)
        freezes[value.arm_id] = freeze

    labels_by_arm = {row.arm_id: row.opaque_label for row in private_join.rows}
    try:
        pair_rows = integrated["pairwise_results"]
        primary_pair = next(
            row
            for row in pair_rows
            if isinstance(row, Mapping)
            and {row.get("candidate_a_label"), row.get("candidate_b_label")}
            == {labels_by_arm["RICH"], labels_by_arm["DIRECT"]}
        )
        integrated_review = next(
            value
            for value in review_evidence
            if value.call_slot_id == "EVAL.INTEGRATED_REVIEW"
        )
    except (KeyError, StopIteration, TypeError) as exc:
        raise ControllerArtifactError(
            "integrated primary authority is missing or ambiguous"
        ) from exc
    try:
        oriented = blinding.orient_integrated_primary_pair(
            private_join,
            integrated_pair=blinding.FrozenIntegratedPairOutcome(
                integrated_review_record_digest=_study_digest(
                    _input_mapping(
                        integrated_review.canonical_record,
                        field="integrated review record",
                    )
                ),
                packet_set_digest=private_join.packet_set_digest,
                source_pair_row_digest=_study_digest(primary_pair),
                candidate_a_label=str(primary_pair["candidate_a_label"]),
                candidate_b_label=str(primary_pair["candidate_b_label"]),
                outcome=str(primary_pair["outcome"]),
            ),
            hard_evidence=blinding.FrozenHardEvidence(
                record_digest=_study_digest(hard_rows),
                packet_set_digest=private_join.packet_set_digest,
            ),
        )
        primary = hard_contract.derive_primary_outcome(
            raw_outcome=oriented.rich_vs_direct,
            rich_freeze=freezes["RICH"],
            direct_freeze=freezes["DIRECT"],
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        blinding.BlindingJoinError,
        hard_contract.HardContractError,
    ) as exc:
        raise ControllerArtifactError("integrated primary derivation failed") from exc

    all_calls: tuple[ProviderEvidenceInput | ReviewEvidenceInput, ...] = (
        *provider_evidence,
        *review_evidence,
    )
    slots = tuple(value.call_slot_id for value in all_calls)
    if len(set(slots)) != len(slots):
        _fail("complete evidence contains duplicate call slots")
    packet_index = dict(replay.packet_index_record)
    public_replay = {
        "schema_version": "es.public_packet_replay_inputs.v1",
        "request_cell_domain": [cell.record for cell in replay.cell_domain],
        "packet_artifact_index": packet_index,
    }
    private_replay = {
        "schema_version": "es.private_blinding_replay_inputs.v2",
        "sealed_opaque_label_map": replay.sealed_opaque_labels.record,
    }
    return CompleteIndexInputs(
        private_join=private_join,
        public_packet_replay_inputs=canonical_json_bytes(public_replay),
        private_blinding_replay_inputs=canonical_json_bytes(private_replay),
        packets_by_arm=tuple(
            (
                packet.arm_id,
                canonical_json_bytes(dict(packet.artifact.value)),
            )
            for packet in replay.packets
        ),
        review_records_by_slot=tuple(
            (value.call_slot_id, value.canonical_record)
            for value in review_evidence
        ),
        adjudication_payload=adjudication_payload,
        integrated_payload=integrated_payload,
        hard_evidence_by_arm=tuple(hard_specs),
        oriented_primary=oriented,
        hard_primary_outcome=primary,
        receipts_by_slot=tuple(
            (value.call_slot_id, value.canonical_receipt) for value in all_calls
        ),
        raw_jsonl_by_slot=tuple(
            (value.call_slot_id, value.raw_jsonl) for value in all_calls
        ),
        frozen_call_authority=frozen_call_authority,
        call_allocations=tuple(value.call_allocation for value in all_calls),
        elapsed_ms_by_slot=tuple(
            (value.call_slot_id, value.elapsed_ms) for value in all_calls
        ),
        scorer_settlement_rows_by_label=tuple(
            (
                _scorer_settlement_label(row),
                canonical_json_bytes(dict(row.value)),
            )
            for row in replay.scorer_settlement_rows
        ),
        score_rows_by_label=tuple(
            (row.opaque_label, canonical_json_bytes(dict(row.value)))
            for row in replay.score_rows
        ),
    )


def _attempt_index(
    inputs: CompleteIndexInputs | PartialIndexInputs,
    *,
    attempt_record: Mapping[str, object],
    lock: Mapping[str, object],
    schedule: Mapping[str, object],
    bindings: Mapping[str, object],
) -> dict[str, Any]:
    try:
        if isinstance(inputs, PartialIndexInputs):
            return synthesis.build_invalid_attempt_evidence_index(
                attempt_record=attempt_record,
                decision_lock=lock,
                randomization_manifest=schedule,
                expected_bindings=bindings,
                receipts_by_slot=_named_mappings(
                    inputs.receipts_by_slot,
                    field="receipts_by_slot",
                ),
                raw_jsonl_by_slot=dict(inputs.raw_jsonl_by_slot),
                elapsed_ms_by_slot=dict(inputs.elapsed_ms_by_slot),
                frozen_call_authority=_input_mapping(
                    inputs.frozen_call_authority,
                    field="frozen_call_authority",
                ),
                call_allocations=[
                    _input_mapping(value, field="call_allocation")
                    for value in inputs.call_allocations
                ],
                partial_evidence=(
                    None
                    if inputs.partial_evidence is None
                    else _input_mapping(
                        inputs.partial_evidence,
                        field="partial_evidence",
                    )
                ),
                invalidity_authority=(
                    None
                    if inputs.invalidity_authority is None
                    else _invalidity_authority_mapping(
                        inputs.invalidity_authority
                    )
                ),
            )
        if not isinstance(inputs, CompleteIndexInputs):
            raise TypeError("attempt index inputs are unsupported")
        return synthesis.build_attempt_evidence_index(
            attempt_record=attempt_record,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
            private_join=inputs.private_join,
            public_packet_replay_inputs=_input_mapping(
                inputs.public_packet_replay_inputs,
                field="public_packet_replay_inputs",
            ),
            private_blinding_replay_inputs=_input_mapping(
                inputs.private_blinding_replay_inputs,
                field="private_blinding_replay_inputs",
            ),
            packets_by_arm=_named_mappings(
                inputs.packets_by_arm,
                field="packets_by_arm",
            ),
            review_records_by_slot=_named_mappings(
                inputs.review_records_by_slot,
                field="review_records_by_slot",
            ),
            adjudication_payload=(
                None
                if inputs.adjudication_payload is None
                else _input_mapping(
                    inputs.adjudication_payload,
                    field="adjudication_payload",
                )
            ),
            integrated_payload=_input_mapping(
                inputs.integrated_payload,
                field="integrated_payload",
            ),
            hard_evidence_by_arm=_named_mappings(
                inputs.hard_evidence_by_arm,
                field="hard_evidence_by_arm",
            ),
            oriented_primary=inputs.oriented_primary,
            hard_primary_outcome=inputs.hard_primary_outcome,
            receipts_by_slot=_named_mappings(
                inputs.receipts_by_slot,
                field="receipts_by_slot",
            ),
            raw_jsonl_by_slot=dict(inputs.raw_jsonl_by_slot),
            frozen_call_authority=_input_mapping(
                inputs.frozen_call_authority,
                field="frozen_call_authority",
            ),
            call_allocations=[
                _input_mapping(value, field="call_allocation")
                for value in inputs.call_allocations
            ],
            elapsed_ms_by_slot=dict(inputs.elapsed_ms_by_slot),
            scorer_settlement_rows_by_label=_named_mappings(
                inputs.scorer_settlement_rows_by_label,
                field="scorer_settlement_rows_by_label",
            ),
            score_rows_by_label=_named_mappings(
                inputs.score_rows_by_label,
                field="score_rows_by_label",
            ),
        )
    except (TypeError, ValueError, synthesis.SynthesisError) as exc:
        raise ControllerArtifactError("attempt index finalization failed") from exc


def _load_prior_indexes(
    assembly: FinalizationAssembly,
    *,
    lock: Mapping[str, object],
    schedule: Mapping[str, object],
    bindings: Mapping[str, object],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for expected_ordinal, binding in enumerate(assembly.prior_indexes, start=1):
        expected_id = f"ES-ATTEMPT-{expected_ordinal:02d}"
        if binding.attempt_id != expected_id:
            _fail("attempt history is not the locked prefix")
        relative = _strict_relative(
            binding.relative_path,
            field="attempt history relative path",
        )
        path = _strict_child_path(
            assembly.evidence_root,
            relative,
            field="attempt history index",
        )
        raw = _read_regular(path, field="attempt history index")
        if _raw_sha256(raw) != binding.sha256:
            _fail("attempt history raw digest disagrees")
        index = _json_mapping(raw, field="attempt history index")
        internal = _digest(
            index.get("index_sha256"),
            field="attempt history internal digest",
        )
        try:
            checked = synthesis.validate_attempt_evidence_index(
                index,
                expected_index_sha256=internal,
                decision_lock=lock,
                randomization_manifest=schedule,
                expected_bindings=bindings,
            )
        except (TypeError, ValueError, synthesis.SynthesisError) as exc:
            raise ControllerArtifactError("attempt history index is invalid") from exc
        record = checked.get("attempt_record")
        if not isinstance(record, Mapping) or record.get("attempt_id") != expected_id:
            _fail("attempt history index identity disagrees")
        result.append(checked)
    return result


def _ensure_publication_directory(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            metadata = current.lstat()
        except OSError as exc:
            raise ControllerArtifactError(
                "evidence publication directory is unreadable"
            ) from exc
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            _fail("evidence publication directory is aliased or non-directory")
    return current


def _publish_exclusive(
    root: Path,
    relative_path: str,
    canonical_value: bytes,
) -> Path:
    _input_mapping(canonical_value, field="published evidence")
    relative = _strict_relative(relative_path, field="evidence publication path")
    parent = _ensure_publication_directory(root, relative.parent)
    destination = parent / relative.name
    if os.path.lexists(destination):
        _fail("evidence publication destination already exists")
    payload = canonical_value + b"\n"
    temporary = parent / (
        f".orc-es-{os.getpid()}-{hashlib.sha256(payload).hexdigest()[:16]}.tmp"
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
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
        os.link(temporary, destination, follow_symlinks=False)
        parent_descriptor = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except FileExistsError as exc:
        raise ControllerArtifactError(
            "evidence publication destination already exists"
        ) from exc
    except OSError as exc:
        raise ControllerArtifactError("evidence publication failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if _read_regular(destination, field="published evidence") != payload:
        _fail("published evidence durability check failed")
    return destination


def _safe_evidence_name(value: object, *, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9._-]+", value) is None:
        _fail(f"{field} is not a safe evidence name")
    return value


def _derived_attempt_prefix(
    *,
    attempt_id: str,
    attempt_record: bytes,
    attempt_index: bytes,
) -> dict[str, bytes]:
    record = _input_mapping(attempt_record, field="attempt_record")
    index = _input_mapping(attempt_index, field="attempt_index")
    if index.get("attempt_record") != record:
        _fail("attempt index record disagrees with derived attempt record")
    reviews = index.get("reviews")
    hard_rows = index.get("hard_evaluations")
    if not isinstance(reviews, list) or not isinstance(hard_rows, list):
        _fail("attempt index publication stages are malformed")

    expected: dict[str, bytes] = {}
    for row in reviews:
        if not isinstance(row, Mapping) or not isinstance(row.get("record"), Mapping):
            _fail("attempt review publication row is malformed")
        slot = _safe_evidence_name(
            row.get("call_slot_id"),
            field="review call slot",
        )
        relative = f"attempts/{attempt_id}/reviews/{slot}.json"
        if relative in expected:
            _fail("attempt review publication contains duplicate call slots")
        expected[relative] = canonical_json_bytes(dict(row["record"]))
    for row in hard_rows:
        if not isinstance(row, Mapping):
            _fail("attempt hard-evidence publication row is malformed")
        arm = _safe_evidence_name(row.get("arm_id"), field="hard-evidence arm")
        relative = f"attempts/{attempt_id}/hard/{arm}.json"
        if relative in expected:
            _fail("attempt hard-evidence publication contains duplicate arms")
        expected[relative] = canonical_json_bytes(dict(row))
    expected[attempt_record_relative_path(attempt_id)] = attempt_record
    return expected


def _preflight_existing_directory(
    path: Path,
    *,
    field: str,
) -> bool:
    if not os.path.lexists(path):
        return False
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ControllerArtifactError(f"{field} is unreadable") from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        _fail(f"{field} is aliased or non-directory")
    return True


def _preflight_derived_attempt_prefix(
    *,
    root: Path,
    attempt_id: str,
    expected: Mapping[str, bytes],
) -> set[str]:
    attempt_index_relative_path(attempt_id)
    attempts_directory = root / "attempts"
    if not _preflight_existing_directory(
        attempts_directory,
        field="attempts evidence directory",
    ):
        return set()
    attempt_directory = attempts_directory / attempt_id
    if not _preflight_existing_directory(
        attempt_directory,
        field="attempt evidence directory",
    ):
        return set()

    adopted: set[str] = set()
    for category in ("reviews", "hard"):
        directory = attempt_directory / category
        if not _preflight_existing_directory(
            directory,
            field=f"attempt {category} evidence directory",
        ):
            continue
        try:
            entries = tuple(directory.iterdir())
        except OSError as exc:
            raise ControllerArtifactError(
                f"attempt {category} evidence directory is unreadable"
            ) from exc
        for path in entries:
            relative = path.relative_to(root).as_posix()
            expected_value = expected.get(relative)
            if expected_value is None:
                _fail(f"attempt {category} evidence contains an extra entry")
            payload = _read_regular(path, field=f"attempt {category} evidence")
            if payload != expected_value + b"\n":
                _fail(f"attempt {category} evidence disagrees with derived bytes")
            adopted.add(relative)

    record_relative = attempt_record_relative_path(attempt_id)
    record_path = root / PurePosixPath(record_relative)
    if os.path.lexists(record_path):
        payload = _read_regular(record_path, field="attempt record evidence")
        if payload != expected[record_relative] + b"\n":
            _fail("attempt record evidence disagrees with derived bytes")
        adopted.add(record_relative)
    return adopted


def adopt_or_publish_derived_attempt_prefix(
    *,
    evidence_root: Path,
    attempt_id: str,
    attempt_record: bytes,
    attempt_index: bytes,
) -> None:
    """Adopt exact derived files from a prior finalizer, then publish gaps."""

    root = _canonical_directory(evidence_root, field="evidence_root")
    expected = _derived_attempt_prefix(
        attempt_id=attempt_id,
        attempt_record=attempt_record,
        attempt_index=attempt_index,
    )
    adopted = _preflight_derived_attempt_prefix(
        root=root,
        attempt_id=attempt_id,
        expected=expected,
    )
    for relative, payload in expected.items():
        if relative not in adopted:
            _publish_exclusive(root, relative, payload)


def _preflight_exact_final_boundary(
    *,
    root: Path,
    relative_path: str,
    expected: bytes,
    field: str,
) -> bool:
    _input_mapping(expected, field=field)
    relative = _strict_relative(relative_path, field=f"{field} path")
    destination = root / relative
    if not os.path.lexists(destination):
        return False
    path = _strict_child_path(root, relative, field=field)
    if _read_regular(path, field=field) != expected + b"\n":
        _fail(f"{field} disagrees with derived bytes")
    return True


def _publish_finalized_evidence(
    *,
    root: Path,
    attempt_id: str,
    attempt_record: Mapping[str, object],
    attempt_index: Mapping[str, object],
    report: Mapping[str, object] | None,
) -> AttemptIndexBinding:
    root = _canonical_directory(root, field="evidence_root")
    attempt_record_bytes = canonical_json_bytes(dict(attempt_record))
    attempt_index_bytes = canonical_json_bytes(dict(attempt_index))
    expected_prefix = _derived_attempt_prefix(
        attempt_id=attempt_id,
        attempt_record=attempt_record_bytes,
        attempt_index=attempt_index_bytes,
    )
    adopted_prefix = _preflight_derived_attempt_prefix(
        root=root,
        attempt_id=attempt_id,
        expected=expected_prefix,
    )
    index_relative = attempt_index_relative_path(attempt_id)
    index_adopted = _preflight_exact_final_boundary(
        root=root,
        relative_path=index_relative,
        expected=attempt_index_bytes,
        field="attempt index evidence",
    )
    report_bytes = None if report is None else canonical_json_bytes(dict(report))
    if report_bytes is None:
        if os.path.lexists(root / "report.json"):
            _fail("unexpected terminal report evidence exists")
        report_adopted = False
    else:
        report_adopted = _preflight_exact_final_boundary(
            root=root,
            relative_path="report.json",
            expected=report_bytes,
            field="terminal report evidence",
        )

    for relative, payload in expected_prefix.items():
        if relative not in adopted_prefix:
            _publish_exclusive(root, relative, payload)
    index_path = root / PurePosixPath(index_relative)
    if not index_adopted:
        index_path = _publish_exclusive(
            root,
            index_relative,
            attempt_index_bytes,
        )
    if report is not None:
        assert report_bytes is not None
        if not report_adopted:
            _publish_exclusive(root, "report.json", report_bytes)
    return AttemptIndexBinding(
        attempt_id=attempt_id,
        relative_path=index_relative,
        sha256=_raw_sha256(index_path.read_bytes()),
    )


def finalize_attempt_artifacts(
    assembly: FinalizationAssembly,
) -> FinalizedArtifacts:
    """Build, validate, and exclusively publish one locked attempt transition."""

    if type(assembly) is not FinalizationAssembly:
        raise TypeError("finalization assembly must be exact")
    lock, schedule, bindings = _contract_values(assembly)
    prior = _load_prior_indexes(
        assembly,
        lock=lock,
        schedule=schedule,
        bindings=bindings,
    )
    prior_ids = tuple(
        str(index["attempt_record"]["attempt_id"]) for index in prior
    )
    try:
        selected = attempts.select_next_attempt_id(
            prior_ids,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )
    except (TypeError, ValueError, attempts.AttemptAccountingError) as exc:
        raise ControllerArtifactError("attempt selection failed") from exc
    if assembly.attempt.attempt_id != selected:
        _fail("attempt finalization does not use the next locked id")
    record = _attempt_record(
        assembly,
        lock=lock,
        schedule=schedule,
        bindings=bindings,
    )
    index = _attempt_index(
        assembly.index,
        attempt_record=record,
        lock=lock,
        schedule=schedule,
        bindings=bindings,
    )
    expected_internal = _digest(
        index.get("index_sha256"),
        field="current attempt index digest",
    )
    try:
        index = synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=expected_internal,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )
    except (TypeError, ValueError, synthesis.SynthesisError) as exc:
        raise ControllerArtifactError("current attempt index is invalid") from exc
    indexes = [*prior, index]
    if assembly.expected_denominator != len(indexes):
        _fail("attempt denominator drift")
    try:
        absolute_ceiling = lock["derived"]["call_bounds"][
            "absolute_with_invalid_attempt_capacity"
        ]
    except (KeyError, TypeError) as exc:
        raise ControllerArtifactError("decision lock call ceiling is malformed") from exc
    if (
        type(absolute_ceiling) is not int
        or assembly.expected_absolute_call_ceiling != absolute_ceiling
    ):
        _fail("absolute call ceiling drift")
    records = [value["attempt_record"] for value in indexes]
    if any(not isinstance(value, Mapping) for value in records):
        _fail("attempt index record domain is malformed")
    call_counts: list[int] = []
    for value in records:
        accounting = value.get("accounting")
        call_count = (
            accounting.get("call_count")
            if isinstance(accounting, Mapping)
            else None
        )
        if type(call_count) is not int or call_count < 0:
            _fail("attempt call count is malformed")
        call_counts.append(call_count)
    invalid_count = sum(value.get("status") == "INVALID" for value in records)
    try:
        attempts.enforce_absolute_call_ceiling(
            call_counts,
            invalid_attempt_count=invalid_count,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )
    except (TypeError, ValueError, attempts.AttemptAccountingError) as exc:
        raise ControllerArtifactError("attempt call ceiling validation failed") from exc
    internal_digests = [str(value["index_sha256"]) for value in indexes]
    report: dict[str, Any] | None
    try:
        report = synthesis.synthesize_report(
            indexed_attempts=indexes,
            expected_index_digests=internal_digests,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )
    except synthesis.SynthesisError as exc:
        if exc.code != "synthesis_attempt_missing":
            raise ControllerArtifactError("attempt report synthesis failed") from exc
        report = None
    if report is None:
        try:
            next_attempt_id = attempts.select_next_attempt_id(
                (*prior_ids, selected),
                decision_lock=lock,
                randomization_manifest=schedule,
                expected_bindings=bindings,
            )
        except (TypeError, ValueError, attempts.AttemptAccountingError) as exc:
            raise ControllerArtifactError("next attempt selection failed") from exc
    else:
        next_attempt_id = None
    binding = _publish_finalized_evidence(
        root=assembly.evidence_root,
        attempt_id=selected,
        attempt_record=record,
        attempt_index=index,
        report=report,
    )
    return FinalizedArtifacts(
        attempt_record=canonical_json_bytes(record),
        attempt_index=canonical_json_bytes(index),
        attempt_index_sha256=str(index["index_sha256"]),
        index_binding=binding,
        report=None if report is None else canonical_json_bytes(report),
        stopped=report is not None,
        next_attempt_id=next_attempt_id,
    )


__all__ = [
    "AttemptIndexBinding",
    "AttemptRecordInputs",
    "CanonicalArtifact",
    "CanonicalByteArtifact",
    "CanonicalLedgerRow",
    "CanonicalScoreRow",
    "CompleteIndexInputs",
    "ControllerArtifactError",
    "FinalizationAssembly",
    "FinalizedArtifacts",
    "HardEvidenceInput",
    "PartialIndexInputs",
    "PersistedPacket",
    "PersistedTrialReplay",
    "ProviderEvidenceInput",
    "ReviewEvidenceInput",
    "adopt_or_publish_derived_attempt_prefix",
    "attempt_index_relative_path",
    "attempt_record_relative_path",
    "build_complete_index_inputs",
    "build_partial_index_inputs",
    "finalize_attempt_artifacts",
    "replay_trial_run_artifacts",
]
