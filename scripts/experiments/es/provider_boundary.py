"""ES-local prelaunch allocation authority for metered provider calls.

The public trial runtime resolves ``codex`` through ``PATH``.  This module
provides that executable seam without changing the generic runtime: it matches
one frozen outer invocation, durably allocates its frozen inner call, and only
then enters the existing metering implementation.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import time
from typing import Any, Iterator, Mapping, NoReturn, Sequence

from orchestrator.workflow.run_ref.contracts import canonical_sha256

from . import metering


MANIFEST_PATH_ENV = "ORC_ES_PROVIDER_BOUNDARY_MANIFEST_PATH"
MANIFEST_SHA256_ENV = "ORC_ES_PROVIDER_BOUNDARY_MANIFEST_SHA256"
MANIFEST_SCHEMA_VERSION = "es.provider_boundary_manifest.v1"
ALLOCATION_SCHEMA_VERSION = "es.controller_call_allocation.v1"
SETTLEMENT_SCHEMA_VERSION = "es.controller_call_settlement.v1"

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "study_id",
        "attempt_id",
        "decision_lock_sha256",
        "evidence_root",
        "journal_path",
        "settlement_journal_path",
        "calls",
    }
)
_CALL_KEYS = frozenset(
    {
        "call_slot_id",
        "role_id",
        "cwd_selector",
        "prompt_sha256",
        "contract_sha256",
        "outer_argv",
        "metered_argv",
        "static_call_sha256",
        "provider_attempt_id",
        "raw_jsonl_path",
        "receipt_path",
        "expected_session_id",
    }
)
_ALLOCATION_KEYS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "sequence",
        "previous_allocation_sha256",
        "call_slot_id",
        "decision_lock_sha256",
        "static_call_sha256",
    }
)
_SETTLEMENT_KEYS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "sequence",
        "previous_settlement_sha256",
        "settlement_sha256",
        "call_slot_id",
        "decision_lock_sha256",
        "static_call_sha256",
        "allocation_sha256",
        "exit_status",
        "receipt_sha256",
        "elapsed_ms",
    }
)


class ProviderBoundaryError(ValueError):
    """One provider-boundary invariant failed before a permitted launch."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ProviderBoundaryError(code, detail)


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("provider_boundary_digest_invalid", field)
    return value


def _identifier(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or "\0" in value
    ):
        _fail("provider_boundary_identifier_invalid", field)
    return value


def _canonical_absolute(value: object, *, field: str) -> Path:
    if not isinstance(value, (str, Path)):
        _fail("provider_boundary_path_invalid", field)
    path = Path(value)
    if not path.is_absolute() or "\0" in path.as_posix():
        _fail("provider_boundary_path_invalid", field)
    resolved = path.resolve(strict=False)
    if resolved != path:
        _fail("provider_boundary_path_invalid", field)
    return path


def _relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail("provider_boundary_relative_path_invalid", field)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail("provider_boundary_relative_path_invalid", field)
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("provider_boundary_json_duplicate_key", key)
        result[key] = value
    return result


def _load_json(raw: bytes, *, code: str) -> object:
    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=lambda value: _fail(code, value),
            parse_constant=lambda value: _fail(code, value),
        )
    except ProviderBoundaryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderBoundaryError(code) from exc


def _write_all(descriptor: int, raw: bytes, *, code: str) -> None:
    pending = memoryview(raw)
    while pending:
        try:
            written = os.write(descriptor, pending)
        except OSError as exc:
            raise ProviderBoundaryError(code) from exc
        if written <= 0:
            _fail(code)
        pending = pending[written:]


def _fsync_directory(path: Path, *, code: str) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ProviderBoundaryError(code) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ProviderBoundaryError(code) from exc
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class CwdSelector:
    """One exact or rooted canonical working-directory selector."""

    kind: str
    path: Path

    def __post_init__(self) -> None:
        if self.kind not in {"exact", "under"}:
            _fail("provider_boundary_cwd_selector_invalid", "kind")
        object.__setattr__(
            self,
            "path",
            _canonical_absolute(self.path, field="cwd_selector.path"),
        )

    @classmethod
    def exact(cls, path: Path) -> "CwdSelector":
        return cls("exact", path)

    @classmethod
    def under(cls, path: Path) -> "CwdSelector":
        return cls("under", path)

    @property
    def record(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path.as_posix()}

    @classmethod
    def from_record(cls, value: object) -> "CwdSelector":
        if not isinstance(value, dict) or set(value) != {"kind", "path"}:
            _fail("provider_boundary_cwd_selector_invalid")
        return cls(
            str(value["kind"]),
            _canonical_absolute(value["path"], field="cwd_selector.path"),
        )

    def matches(self, cwd: Path) -> bool:
        candidate = _canonical_absolute(cwd, field="cwd")
        if self.kind == "exact":
            return candidate == self.path
        try:
            candidate.relative_to(self.path)
        except ValueError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class BoundaryCall:
    """One frozen outer invocation and its explicit inner metered call."""

    call_slot_id: str
    role_id: str
    cwd_selector: CwdSelector
    prompt_sha256: str
    contract_sha256: str
    outer_argv: tuple[str, ...]
    metered_argv: tuple[str, ...]
    static_call_sha256: str
    provider_attempt_id: str
    raw_jsonl_path: str
    receipt_path: str
    expected_session_id: str | None

    def __post_init__(self) -> None:
        for field in ("call_slot_id", "role_id", "provider_attempt_id"):
            object.__setattr__(
                self,
                field,
                _identifier(getattr(self, field), field=field),
            )
        if type(self.cwd_selector) is not CwdSelector:
            _fail("provider_boundary_cwd_selector_invalid")
        _digest(self.prompt_sha256, field="prompt_sha256")
        _digest(self.contract_sha256, field="contract_sha256")
        _digest(self.static_call_sha256, field="static_call_sha256")
        if (
            not isinstance(self.outer_argv, tuple)
            or len(self.outer_argv) < 2
            or self.outer_argv[0] != "codex"
            or any(not isinstance(value, str) or not value for value in self.outer_argv)
            or "resume" in self.outer_argv[1:]
        ):
            _fail("provider_boundary_outer_argv_invalid")
        if not isinstance(self.metered_argv, tuple):
            _fail("provider_boundary_metered_argv_invalid")
        try:
            normalized = metering.normalize_codex_argv(self.metered_argv)
        except metering.MeteringError as exc:
            raise ProviderBoundaryError(
                "provider_boundary_metered_argv_invalid", exc.code
            ) from exc
        config_values = [
            normalized[index + 1]
            for index, value in enumerate(normalized[:-1])
            if value == "--config"
        ]
        if (
            tuple(normalized) != self.metered_argv
            or not Path(self.metered_argv[0]).is_absolute()
            or config_values != ["model_reasoning_effort=high"]
            or self.metered_argv[-2:] != ("--", "-")
        ):
            _fail("provider_boundary_metered_argv_invalid")
        object.__setattr__(
            self,
            "raw_jsonl_path",
            _relative_path(self.raw_jsonl_path, field="raw_jsonl_path"),
        )
        object.__setattr__(
            self,
            "receipt_path",
            _relative_path(self.receipt_path, field="receipt_path"),
        )
        if self.raw_jsonl_path == self.receipt_path:
            _fail("provider_boundary_evidence_path_overlap")
        if self.expected_session_id is not None:
            _identifier(self.expected_session_id, field="expected_session_id")

    @property
    def record(self) -> dict[str, object]:
        return {
            "call_slot_id": self.call_slot_id,
            "role_id": self.role_id,
            "cwd_selector": self.cwd_selector.record,
            "prompt_sha256": self.prompt_sha256,
            "contract_sha256": self.contract_sha256,
            "outer_argv": list(self.outer_argv),
            "metered_argv": list(self.metered_argv),
            "static_call_sha256": self.static_call_sha256,
            "provider_attempt_id": self.provider_attempt_id,
            "raw_jsonl_path": self.raw_jsonl_path,
            "receipt_path": self.receipt_path,
            "expected_session_id": self.expected_session_id,
        }

    @classmethod
    def from_record(cls, value: object) -> "BoundaryCall":
        if not isinstance(value, dict) or set(value) != _CALL_KEYS:
            _fail("provider_boundary_call_invalid")
        outer = value["outer_argv"]
        inner = value["metered_argv"]
        if not isinstance(outer, list) or not isinstance(inner, list):
            _fail("provider_boundary_call_invalid", "argv")
        return cls(
            call_slot_id=value["call_slot_id"],  # type: ignore[arg-type]
            role_id=value["role_id"],  # type: ignore[arg-type]
            cwd_selector=CwdSelector.from_record(value["cwd_selector"]),
            prompt_sha256=value["prompt_sha256"],  # type: ignore[arg-type]
            contract_sha256=value["contract_sha256"],  # type: ignore[arg-type]
            outer_argv=tuple(outer),
            metered_argv=tuple(inner),
            static_call_sha256=value["static_call_sha256"],  # type: ignore[arg-type]
            provider_attempt_id=value["provider_attempt_id"],  # type: ignore[arg-type]
            raw_jsonl_path=value["raw_jsonl_path"],  # type: ignore[arg-type]
            receipt_path=value["receipt_path"],  # type: ignore[arg-type]
            expected_session_id=value["expected_session_id"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class BoundaryManifest:
    """Closed immutable invocation table for one ES attempt."""

    study_id: str
    attempt_id: str
    decision_lock_sha256: str
    evidence_root: Path
    journal_path: Path
    settlement_journal_path: Path
    calls: tuple[BoundaryCall, ...]
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            _fail("provider_boundary_manifest_schema_invalid")
        _identifier(self.study_id, field="study_id")
        _identifier(self.attempt_id, field="attempt_id")
        _digest(self.decision_lock_sha256, field="decision_lock_sha256")
        evidence_root = _canonical_absolute(self.evidence_root, field="evidence_root")
        journal_path = _canonical_absolute(self.journal_path, field="journal_path")
        settlement_journal_path = _canonical_absolute(
            self.settlement_journal_path,
            field="settlement_journal_path",
        )
        for candidate in (journal_path, settlement_journal_path):
            try:
                journal_relative = candidate.relative_to(evidence_root)
            except ValueError:
                _fail("provider_boundary_journal_path_invalid")
            if journal_relative == Path("."):
                _fail("provider_boundary_journal_path_invalid")
        if settlement_journal_path == journal_path:
            _fail("provider_boundary_journal_path_invalid")
        if (
            not isinstance(self.calls, tuple)
            or not self.calls
            or any(type(value) is not BoundaryCall for value in self.calls)
        ):
            _fail("provider_boundary_call_domain_invalid")
        for values, field in (
            ([value.call_slot_id for value in self.calls], "call_slot_id"),
            ([value.provider_attempt_id for value in self.calls], "provider_attempt_id"),
            ([value.raw_jsonl_path for value in self.calls], "raw_jsonl_path"),
            ([value.receipt_path for value in self.calls], "receipt_path"),
        ):
            if len(set(values)) != len(values):
                _fail("provider_boundary_call_domain_invalid", field)
        if set(value.raw_jsonl_path for value in self.calls) & set(
            value.receipt_path for value in self.calls
        ):
            _fail("provider_boundary_evidence_path_overlap")
        object.__setattr__(self, "evidence_root", evidence_root)
        object.__setattr__(self, "journal_path", journal_path)
        object.__setattr__(
            self,
            "settlement_journal_path",
            settlement_journal_path,
        )

    @property
    def record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "study_id": self.study_id,
            "attempt_id": self.attempt_id,
            "decision_lock_sha256": self.decision_lock_sha256,
            "evidence_root": self.evidence_root.as_posix(),
            "journal_path": self.journal_path.as_posix(),
            "settlement_journal_path": self.settlement_journal_path.as_posix(),
            "calls": [call.record for call in self.calls],
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.record)

    @classmethod
    def from_record(cls, value: object) -> "BoundaryManifest":
        if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
            _fail("provider_boundary_manifest_invalid")
        calls = value["calls"]
        if not isinstance(calls, list):
            _fail("provider_boundary_manifest_invalid", "calls")
        return cls(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            study_id=value["study_id"],  # type: ignore[arg-type]
            attempt_id=value["attempt_id"],  # type: ignore[arg-type]
            decision_lock_sha256=value["decision_lock_sha256"],  # type: ignore[arg-type]
            evidence_root=_canonical_absolute(value["evidence_root"], field="evidence_root"),
            journal_path=_canonical_absolute(value["journal_path"], field="journal_path"),
            settlement_journal_path=_canonical_absolute(
                value["settlement_journal_path"],
                field="settlement_journal_path",
            ),
            calls=tuple(BoundaryCall.from_record(row) for row in calls),
        )


@dataclass(frozen=True, slots=True)
class ManifestPublication:
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _canonical_absolute(self.path, field="manifest.path"))
        _digest(self.sha256, field="manifest.sha256")


@dataclass(frozen=True, slots=True)
class AllocationEvent:
    attempt_id: str
    sequence: int
    previous_allocation_sha256: str | None
    call_slot_id: str
    decision_lock_sha256: str
    static_call_sha256: str
    schema_version: str = ALLOCATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ALLOCATION_SCHEMA_VERSION:
            _fail("provider_boundary_allocation_schema_invalid")
        _identifier(self.attempt_id, field="allocation.attempt_id")
        _identifier(self.call_slot_id, field="allocation.call_slot_id")
        if type(self.sequence) is not int or self.sequence < 1:
            _fail("provider_boundary_allocation_sequence_invalid")
        if self.previous_allocation_sha256 is not None:
            _digest(
                self.previous_allocation_sha256,
                field="previous_allocation_sha256",
            )
        _digest(self.decision_lock_sha256, field="decision_lock_sha256")
        _digest(self.static_call_sha256, field="static_call_sha256")

    @property
    def record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "sequence": self.sequence,
            "previous_allocation_sha256": self.previous_allocation_sha256,
            "call_slot_id": self.call_slot_id,
            "decision_lock_sha256": self.decision_lock_sha256,
            "static_call_sha256": self.static_call_sha256,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.record)

    @classmethod
    def from_record(cls, value: object) -> "AllocationEvent":
        if not isinstance(value, dict) or set(value) != _ALLOCATION_KEYS:
            _fail("provider_boundary_allocation_journal_invalid")
        return cls(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            attempt_id=value["attempt_id"],  # type: ignore[arg-type]
            sequence=value["sequence"],  # type: ignore[arg-type]
            previous_allocation_sha256=(
                value["previous_allocation_sha256"]  # type: ignore[arg-type]
            ),
            call_slot_id=value["call_slot_id"],  # type: ignore[arg-type]
            decision_lock_sha256=value["decision_lock_sha256"],  # type: ignore[arg-type]
            static_call_sha256=value["static_call_sha256"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class SettlementEvent:
    """One receipt-backed terminal settlement in global append order."""

    attempt_id: str
    sequence: int
    previous_settlement_sha256: str | None
    call_slot_id: str
    decision_lock_sha256: str
    static_call_sha256: str
    allocation_sha256: str
    exit_status: int
    receipt_sha256: str
    elapsed_ms: int
    schema_version: str = SETTLEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SETTLEMENT_SCHEMA_VERSION:
            _fail("provider_boundary_settlement_schema_invalid")
        _identifier(self.attempt_id, field="settlement.attempt_id")
        _identifier(self.call_slot_id, field="settlement.call_slot_id")
        if type(self.sequence) is not int or self.sequence < 1:
            _fail("provider_boundary_settlement_sequence_invalid")
        if self.previous_settlement_sha256 is not None:
            _digest(
                self.previous_settlement_sha256,
                field="previous_settlement_sha256",
            )
        _digest(self.decision_lock_sha256, field="decision_lock_sha256")
        _digest(self.static_call_sha256, field="static_call_sha256")
        _digest(self.allocation_sha256, field="allocation_sha256")
        _digest(self.receipt_sha256, field="receipt_sha256")
        if type(self.exit_status) is not int:
            _fail("provider_boundary_settlement_exit_status_invalid")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            _fail("provider_boundary_settlement_elapsed_invalid")

    @property
    def body_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "sequence": self.sequence,
            "previous_settlement_sha256": self.previous_settlement_sha256,
            "call_slot_id": self.call_slot_id,
            "decision_lock_sha256": self.decision_lock_sha256,
            "static_call_sha256": self.static_call_sha256,
            "allocation_sha256": self.allocation_sha256,
            "exit_status": self.exit_status,
            "receipt_sha256": self.receipt_sha256,
            "elapsed_ms": self.elapsed_ms,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.body_record)

    @property
    def record(self) -> dict[str, object]:
        return {**self.body_record, "settlement_sha256": self.sha256}

    @classmethod
    def from_record(cls, value: object) -> "SettlementEvent":
        if not isinstance(value, dict) or set(value) != _SETTLEMENT_KEYS:
            _fail("provider_boundary_settlement_journal_invalid")
        observed_sha256 = _digest(
            value["settlement_sha256"],
            field="settlement_sha256",
        )
        event = cls(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            attempt_id=value["attempt_id"],  # type: ignore[arg-type]
            sequence=value["sequence"],  # type: ignore[arg-type]
            previous_settlement_sha256=(
                value["previous_settlement_sha256"]  # type: ignore[arg-type]
            ),
            call_slot_id=value["call_slot_id"],  # type: ignore[arg-type]
            decision_lock_sha256=value["decision_lock_sha256"],  # type: ignore[arg-type]
            static_call_sha256=value["static_call_sha256"],  # type: ignore[arg-type]
            allocation_sha256=value["allocation_sha256"],  # type: ignore[arg-type]
            exit_status=value["exit_status"],  # type: ignore[arg-type]
            receipt_sha256=value["receipt_sha256"],  # type: ignore[arg-type]
            elapsed_ms=value["elapsed_ms"],  # type: ignore[arg-type]
        )
        if event.sha256 != observed_sha256:
            _fail("provider_boundary_settlement_journal_invalid")
        return event


@dataclass(frozen=True, slots=True)
class BoundaryExecution:
    allocation: AllocationEvent
    settlement: SettlementEvent
    exit_status: int
    receipt_bytes: bytes

    def __post_init__(self) -> None:
        if type(self.allocation) is not AllocationEvent:
            raise TypeError("allocation must be exact AllocationEvent")
        if type(self.settlement) is not SettlementEvent:
            raise TypeError("settlement must be exact SettlementEvent")
        if type(self.exit_status) is not int:
            raise TypeError("exit_status must be an integer")
        if not isinstance(self.receipt_bytes, bytes) or not self.receipt_bytes:
            raise TypeError("receipt_bytes must be non-empty bytes")
        if (
            self.settlement.allocation_sha256 != self.allocation.sha256
            or self.settlement.exit_status != self.exit_status
            or self.settlement.receipt_sha256
            != "sha256:" + hashlib.sha256(self.receipt_bytes).hexdigest()
        ):
            raise ValueError("settlement does not bind boundary execution")


def write_manifest_exclusive(path: Path, manifest: BoundaryManifest) -> ManifestPublication:
    """Publish one immutable content-addressed invocation manifest."""

    target = _canonical_absolute(path, field="manifest.path")
    if type(manifest) is not BoundaryManifest:
        raise TypeError("manifest must be exact BoundaryManifest")
    raw = metering.canonical_json_bytes(manifest.record)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o400,
        )
    except OSError as exc:
        raise ProviderBoundaryError("provider_boundary_manifest_publication_failed") from exc
    try:
        _write_all(
            descriptor,
            raw,
            code="provider_boundary_manifest_publication_failed",
        )
        os.fsync(descriptor)
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    finally:
        os.close(descriptor)
    _fsync_directory(
        target.parent,
        code="provider_boundary_manifest_publication_failed",
    )
    return ManifestPublication(target, manifest.sha256)


def load_manifest(path: Path, *, expected_sha256: str) -> BoundaryManifest:
    """Load a canonical manifest only when its external digest still agrees."""

    source = _canonical_absolute(path, field="manifest.path")
    expected = _digest(expected_sha256, field="manifest.sha256")
    try:
        identity = source.lstat()
        raw = source.read_bytes()
    except OSError as exc:
        raise ProviderBoundaryError("provider_boundary_manifest_unreadable") from exc
    if not stat.S_ISREG(identity.st_mode):
        _fail("provider_boundary_manifest_unreadable")
    value = _load_json(raw, code="provider_boundary_manifest_json_invalid")
    if not isinstance(value, dict) or metering.canonical_json_bytes(value) != raw:
        _fail("provider_boundary_manifest_noncanonical")
    manifest = BoundaryManifest.from_record(value)
    if manifest.sha256 != expected:
        _fail("provider_boundary_manifest_digest_mismatch")
    return manifest


def resolve_call(
    manifest: BoundaryManifest,
    *,
    cwd: Path,
    prompt: bytes,
    argv: Sequence[str],
) -> BoundaryCall:
    """Resolve exactly one slot from only wrapper-visible invocation facts."""

    if type(manifest) is not BoundaryManifest:
        raise TypeError("manifest must be exact BoundaryManifest")
    if not isinstance(prompt, bytes):
        raise TypeError("prompt must be bytes")
    if (
        not isinstance(argv, Sequence)
        or isinstance(argv, (str, bytes))
        or any(not isinstance(value, str) or not value for value in argv)
    ):
        _fail("provider_boundary_outer_argv_invalid")
    outer = tuple(argv)
    prompt_sha256 = "sha256:" + hashlib.sha256(prompt).hexdigest()
    matches = tuple(
        call
        for call in manifest.calls
        if call.prompt_sha256 == prompt_sha256
        and call.outer_argv == outer
        and call.cwd_selector.matches(cwd)
    )
    if not matches:
        _fail("provider_boundary_call_absent")
    if len(matches) != 1:
        _fail("provider_boundary_call_ambiguous")
    return matches[0]


def _parse_journal(raw: bytes) -> tuple[AllocationEvent, ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\n"):
        _fail("provider_boundary_allocation_journal_invalid")
    events: list[AllocationEvent] = []
    seen_slots: set[str] = set()
    previous: str | None = None
    for sequence, line in enumerate(raw.splitlines(keepends=True), start=1):
        if line == b"\n":
            _fail("provider_boundary_allocation_journal_invalid")
        value = _load_json(
            line,
            code="provider_boundary_allocation_journal_invalid",
        )
        if not isinstance(value, dict) or metering.canonical_json_bytes(value) != line:
            _fail("provider_boundary_allocation_journal_invalid")
        event = AllocationEvent.from_record(value)
        if (
            event.sequence != sequence
            or event.previous_allocation_sha256 != previous
            or event.call_slot_id in seen_slots
        ):
            _fail("provider_boundary_allocation_journal_invalid")
        events.append(event)
        seen_slots.add(event.call_slot_id)
        previous = event.sha256
    return tuple(events)


def load_allocation_journal(
    path: Path,
    *,
    attempt_id: str,
    decision_lock_sha256: str,
) -> tuple[AllocationEvent, ...]:
    """Validate and return the complete global append-order authority chain."""

    source = _canonical_absolute(path, field="journal.path")
    expected_attempt = _identifier(attempt_id, field="attempt_id")
    expected_lock = _digest(decision_lock_sha256, field="decision_lock_sha256")
    try:
        descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_allocation_journal_unreadable"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_allocation_journal_unreadable"
        ) from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    events = _parse_journal(raw)
    if any(
        event.attempt_id != expected_attempt
        or event.decision_lock_sha256 != expected_lock
        for event in events
    ):
        _fail("provider_boundary_allocation_journal_binding_mismatch")
    return events


def publish_allocation(
    path: Path,
    *,
    attempt_id: str,
    decision_lock_sha256: str,
    call_slot_id: str,
    static_call_sha256: str,
) -> AllocationEvent:
    """Append and fsync one allocation, continuing the validated global chain."""

    target = _canonical_absolute(path, field="journal.path")
    expected_attempt = _identifier(attempt_id, field="attempt_id")
    expected_lock = _digest(decision_lock_sha256, field="decision_lock_sha256")
    slot = _identifier(call_slot_id, field="call_slot_id")
    static_digest = _digest(static_call_sha256, field="static_call_sha256")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            target,
            os.O_RDWR
            | os.O_CREAT
            | os.O_APPEND
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_allocation_journal_publication_failed"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        existing = _parse_journal(b"".join(chunks))
        if any(
            event.attempt_id != expected_attempt
            or event.decision_lock_sha256 != expected_lock
            for event in existing
        ):
            _fail("provider_boundary_allocation_journal_binding_mismatch")
        if any(event.call_slot_id == slot for event in existing):
            _fail("provider_boundary_allocation_duplicate")
        event = AllocationEvent(
            attempt_id=expected_attempt,
            sequence=len(existing) + 1,
            previous_allocation_sha256=(existing[-1].sha256 if existing else None),
            call_slot_id=slot,
            decision_lock_sha256=expected_lock,
            static_call_sha256=static_digest,
        )
        os.lseek(descriptor, 0, os.SEEK_END)
        _write_all(
            descriptor,
            metering.canonical_json_bytes(event.record),
            code="provider_boundary_allocation_journal_publication_failed",
        )
        os.fsync(descriptor)
        _fsync_directory(
            target.parent,
            code="provider_boundary_allocation_journal_publication_failed",
        )
        return event
    except ProviderBoundaryError:
        raise
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_allocation_journal_publication_failed"
        ) from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _parse_settlement_journal(raw: bytes) -> tuple[SettlementEvent, ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\n"):
        _fail("provider_boundary_settlement_journal_invalid")
    events: list[SettlementEvent] = []
    seen_slots: set[str] = set()
    previous: str | None = None
    for sequence, line in enumerate(raw.splitlines(keepends=True), start=1):
        if line == b"\n":
            _fail("provider_boundary_settlement_journal_invalid")
        value = _load_json(
            line,
            code="provider_boundary_settlement_journal_invalid",
        )
        if not isinstance(value, dict) or metering.canonical_json_bytes(value) != line:
            _fail("provider_boundary_settlement_journal_invalid")
        event = SettlementEvent.from_record(value)
        if (
            event.sequence != sequence
            or event.previous_settlement_sha256 != previous
            or event.call_slot_id in seen_slots
        ):
            _fail("provider_boundary_settlement_journal_invalid")
        events.append(event)
        seen_slots.add(event.call_slot_id)
        previous = event.sha256
    return tuple(events)


def _validate_settlement_allocation_bindings(
    settlements: Sequence[SettlementEvent],
    allocations: Sequence[AllocationEvent],
    *,
    attempt_id: str,
    decision_lock_sha256: str,
) -> None:
    by_slot = {event.call_slot_id: event for event in allocations}
    for settlement in settlements:
        allocation = by_slot.get(settlement.call_slot_id)
        if allocation is None:
            _fail("provider_boundary_settlement_allocation_missing")
        if (
            settlement.attempt_id != attempt_id
            or settlement.decision_lock_sha256 != decision_lock_sha256
            or settlement.attempt_id != allocation.attempt_id
            or settlement.decision_lock_sha256
            != allocation.decision_lock_sha256
            or settlement.static_call_sha256 != allocation.static_call_sha256
            or settlement.allocation_sha256 != allocation.sha256
        ):
            _fail("provider_boundary_settlement_allocation_mismatch")


def load_settlement_journal(
    path: Path,
    *,
    allocation_journal_path: Path,
    attempt_id: str,
    decision_lock_sha256: str,
) -> tuple[SettlementEvent, ...]:
    """Validate the global settlement chain and every allocation binding."""

    source = _canonical_absolute(path, field="settlement_journal.path")
    expected_attempt = _identifier(attempt_id, field="attempt_id")
    expected_lock = _digest(decision_lock_sha256, field="decision_lock_sha256")
    try:
        identity = source.lstat()
        if not stat.S_ISREG(identity.st_mode):
            raise OSError("settlement journal is not regular")
        descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_settlement_journal_unreadable"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        settlements = _parse_settlement_journal(b"".join(chunks))
    except ProviderBoundaryError:
        raise
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_settlement_journal_unreadable"
        ) from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    allocations = load_allocation_journal(
        allocation_journal_path,
        attempt_id=expected_attempt,
        decision_lock_sha256=expected_lock,
    )
    _validate_settlement_allocation_bindings(
        settlements,
        allocations,
        attempt_id=expected_attempt,
        decision_lock_sha256=expected_lock,
    )
    return settlements


def _settlement_receipt_authority(
    receipt_bytes: bytes,
    *,
    allocation: AllocationEvent,
) -> tuple[int, str]:
    if not isinstance(receipt_bytes, bytes) or not receipt_bytes:
        _fail("provider_boundary_settlement_receipt_invalid")
    value = _load_json(
        receipt_bytes,
        code="provider_boundary_settlement_receipt_invalid",
    )
    if (
        not isinstance(value, dict)
        or metering.canonical_json_bytes(value) != receipt_bytes
        or value.get("block_id") != allocation.attempt_id
        or value.get("call_slot_id") != allocation.call_slot_id
        or type(value.get("exit_status")) is not int
    ):
        _fail("provider_boundary_settlement_receipt_invalid")
    return (
        value["exit_status"],
        "sha256:" + hashlib.sha256(receipt_bytes).hexdigest(),
    )


def publish_settlement(
    path: Path,
    *,
    allocation_journal_path: Path,
    allocation: AllocationEvent,
    receipt_bytes: bytes,
    elapsed_ms: int,
) -> SettlementEvent:
    """Append one receipt-backed settlement after validating its allocation."""

    target = _canonical_absolute(path, field="settlement_journal.path")
    allocation_path = _canonical_absolute(
        allocation_journal_path,
        field="journal.path",
    )
    if type(allocation) is not AllocationEvent:
        raise TypeError("allocation must be exact AllocationEvent")
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        _fail("provider_boundary_settlement_elapsed_invalid")
    exit_status, receipt_sha256 = _settlement_receipt_authority(
        receipt_bytes,
        allocation=allocation,
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            target,
            os.O_RDWR
            | os.O_CREAT
            | os.O_APPEND
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_settlement_journal_publication_failed"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        allocations = load_allocation_journal(
            allocation_path,
            attempt_id=allocation.attempt_id,
            decision_lock_sha256=allocation.decision_lock_sha256,
        )
        matching = tuple(
            event
            for event in allocations
            if event.call_slot_id == allocation.call_slot_id
        )
        if matching != (allocation,):
            _fail("provider_boundary_settlement_allocation_missing")
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        existing = _parse_settlement_journal(b"".join(chunks))
        _validate_settlement_allocation_bindings(
            existing,
            allocations,
            attempt_id=allocation.attempt_id,
            decision_lock_sha256=allocation.decision_lock_sha256,
        )
        if any(event.call_slot_id == allocation.call_slot_id for event in existing):
            _fail("provider_boundary_settlement_duplicate")
        event = SettlementEvent(
            attempt_id=allocation.attempt_id,
            sequence=len(existing) + 1,
            previous_settlement_sha256=(existing[-1].sha256 if existing else None),
            call_slot_id=allocation.call_slot_id,
            decision_lock_sha256=allocation.decision_lock_sha256,
            static_call_sha256=allocation.static_call_sha256,
            allocation_sha256=allocation.sha256,
            exit_status=exit_status,
            receipt_sha256=receipt_sha256,
            elapsed_ms=elapsed_ms,
        )
        os.lseek(descriptor, 0, os.SEEK_END)
        _write_all(
            descriptor,
            metering.canonical_json_bytes(event.record),
            code="provider_boundary_settlement_journal_publication_failed",
        )
        os.fsync(descriptor)
        _fsync_directory(
            target.parent,
            code="provider_boundary_settlement_journal_publication_failed",
        )
        return event
    except ProviderBoundaryError:
        raise
    except OSError as exc:
        raise ProviderBoundaryError(
            "provider_boundary_settlement_journal_publication_failed"
        ) from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def install_path_shim(
    shim_dir: Path,
    *,
    python_executable: str = sys.executable,
) -> Path:
    """Install one deterministic ``codex`` executable that enters this module."""

    directory = _canonical_absolute(shim_dir, field="shim_dir")
    python = _canonical_absolute(python_executable, field="python_executable")
    repository_root = Path(__file__).resolve().parents[3]
    raw = (
        f"#!{python}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(repository_root)!r})\n"
        "from scripts.experiments.es.provider_boundary import main\n"
        "raise SystemExit(main())\n"
    ).encode("utf-8", "strict")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "codex"
        descriptor = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o500,
        )
    except OSError as exc:
        raise ProviderBoundaryError("provider_boundary_shim_publication_failed") from exc
    try:
        _write_all(
            descriptor,
            raw,
            code="provider_boundary_shim_publication_failed",
        )
        os.fsync(descriptor)
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    finally:
        os.close(descriptor)
    _fsync_directory(
        target.parent,
        code="provider_boundary_shim_publication_failed",
    )
    return target


def boundary_environment(
    *,
    shim_dir: Path,
    manifest: ManifestPublication,
    inherited_path: str,
) -> dict[str, str]:
    """Return the exact process-environment overlay for one public entry call."""

    directory = _canonical_absolute(shim_dir, field="shim_dir")
    if type(manifest) is not ManifestPublication:
        raise TypeError("manifest must be exact ManifestPublication")
    if not isinstance(inherited_path, str) or not inherited_path:
        _fail("provider_boundary_inherited_path_invalid")
    return {
        "PATH": directory.as_posix() + os.pathsep + inherited_path,
        MANIFEST_PATH_ENV: manifest.path.as_posix(),
        MANIFEST_SHA256_ENV: manifest.sha256,
    }


@contextmanager
def _replay_stdin(prompt: bytes) -> Iterator[None]:
    """Restore captured prompt bytes to fd 0 for the existing metering path."""

    saved = os.dup(0)
    try:
        with tempfile.TemporaryFile() as replay:
            replay.write(prompt)
            replay.flush()
            replay.seek(0)
            os.dup2(replay.fileno(), 0)
            yield
    finally:
        os.dup2(saved, 0)
        os.close(saved)


def execute_boundary(
    *,
    argv: Sequence[str],
    prompt: bytes,
    cwd: Path,
    environ: Mapping[str, str],
) -> BoundaryExecution:
    """Allocate, then execute one exact inner call through existing metering."""

    manifest_path = environ.get(MANIFEST_PATH_ENV)
    manifest_sha256 = environ.get(MANIFEST_SHA256_ENV)
    if not isinstance(manifest_path, str) or not isinstance(manifest_sha256, str):
        _fail("provider_boundary_environment_invalid")
    manifest = load_manifest(
        _canonical_absolute(manifest_path, field="manifest.path"),
        expected_sha256=manifest_sha256,
    )
    call = resolve_call(manifest, cwd=cwd, prompt=prompt, argv=argv)
    allocation = publish_allocation(
        manifest.journal_path,
        attempt_id=manifest.attempt_id,
        decision_lock_sha256=manifest.decision_lock_sha256,
        call_slot_id=call.call_slot_id,
        static_call_sha256=call.static_call_sha256,
    )
    try:
        with _replay_stdin(prompt):
            started_ns = time.monotonic_ns()
            exit_status, receipt = metering.run_metered_command(
                call.metered_argv,
                evidence_root=manifest.evidence_root,
                raw_jsonl_path=call.raw_jsonl_path,
                receipt_path=call.receipt_path,
                study_id=manifest.study_id,
                block_id=manifest.attempt_id,
                role_id=call.role_id,
                call_slot_id=call.call_slot_id,
                provider_attempt_id=call.provider_attempt_id,
                prompt_sha256=call.prompt_sha256,
                contract_sha256=call.contract_sha256,
                expected_session_id=call.expected_session_id,
            )
            finished_ns = time.monotonic_ns()
    except metering.MeteringError as exc:
        raise ProviderBoundaryError("provider_boundary_metering_failed", exc.code) from exc
    receipt_bytes = metering.canonical_json_bytes(receipt)
    settlement = publish_settlement(
        manifest.settlement_journal_path,
        allocation_journal_path=manifest.journal_path,
        allocation=allocation,
        receipt_bytes=receipt_bytes,
        elapsed_ms=(finished_ns - started_ns) // 1_000_000,
    )
    return BoundaryExecution(
        allocation=allocation,
        settlement=settlement,
        exit_status=exit_status,
        receipt_bytes=receipt_bytes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Executable PATH-shim entry point."""

    outer = ("codex", *(sys.argv[1:] if argv is None else tuple(argv)))
    try:
        prompt = sys.stdin.buffer.read()
        execution = execute_boundary(
            argv=outer,
            prompt=prompt,
            cwd=Path.cwd().resolve(),
            environ=os.environ,
        )
    except ProviderBoundaryError as exc:
        sys.stderr.write(exc.code + "\n")
        sys.stderr.flush()
        return 70
    return execution.exit_status


__all__ = [
    "ALLOCATION_SCHEMA_VERSION",
    "MANIFEST_PATH_ENV",
    "MANIFEST_SCHEMA_VERSION",
    "MANIFEST_SHA256_ENV",
    "SETTLEMENT_SCHEMA_VERSION",
    "AllocationEvent",
    "BoundaryCall",
    "BoundaryExecution",
    "BoundaryManifest",
    "CwdSelector",
    "ManifestPublication",
    "ProviderBoundaryError",
    "SettlementEvent",
    "boundary_environment",
    "execute_boundary",
    "install_path_shim",
    "load_allocation_journal",
    "load_manifest",
    "load_settlement_journal",
    "main",
    "publish_allocation",
    "publish_settlement",
    "resolve_call",
    "write_manifest_exclusive",
]


if __name__ == "__main__":  # pragma: no cover - exercised through installed shim
    raise SystemExit(main())
