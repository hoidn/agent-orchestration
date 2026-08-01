"""Strict parent-owned attempt ledger for durable ``run-ref`` effects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write

from .contracts import canonical_json_bytes, canonical_sha256


RUN_REF_ATTEMPT_LEDGER_SCHEMA = "run_ref_attempt_ledger.v1"

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_TREE_RE = re.compile(r"git-tree:[0-9a-f]{40}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)

_STAGES = (
    "allocated",
    "materialized",
    "setup_completed",
    "program_prepared",
    "launched",
    "child_completed",
    "delta_captured",
    "completed_pending_parent_commit",
    "committed",
)
_STATUS_BY_STAGE = {
    **{stage: "in_progress" for stage in _STAGES[:7]},
    "completed_pending_parent_commit": "pending_parent_commit",
    "committed": "committed",
}
_INTRODUCED_BINDINGS = {
    "allocated": frozenset(),
    "materialized": frozenset({"verified_git_tree_id"}),
    "setup_completed": frozenset(
        {"setup_evidence_digest", "post_setup_baseline_digest"}
    ),
    "program_prepared": frozenset({"program_preparation_digest"}),
    "launched": frozenset({"child_launch_digest"}),
    "child_completed": frozenset(
        {"child_terminal_state_digest", "result_payload_digest"}
    ),
    "delta_captured": frozenset(
        {
            "workspace_delta_digest",
            "accounting_digest",
            "evidence_manifest_digest",
        }
    ),
    "completed_pending_parent_commit": frozenset(),
    "committed": frozenset(),
}
_PROGRESSIVE_BINDINGS = frozenset().union(*_INTRODUCED_BINDINGS.values())

_ROW_KEYS = frozenset(
    {
        "schema_version",
        "sequence",
        "previous_row_digest",
        "row_digest",
        "visit",
        "attempt_ordinal",
        "stage",
        "status",
        "recorded_at",
        "bindings",
    }
)
_VISIT_KEYS = frozenset(
    {
        "parent_run_id",
        "execution_frame_id",
        "call_frame_id",
        "step_id",
        "visit_count",
    }
)


class RunRefLedgerError(ValueError):
    """The parent attempt ledger cannot be safely interpreted or advanced."""

    code = "run_ref_ledger_invalid"


def _fail(reason: str) -> None:
    raise RunRefLedgerError(reason)


def _nonempty_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        _fail(f"{field} must be non-empty NUL-free text")
    return value


def _positive_integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{field} must be a positive integer")
    return value


def _sha256(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{field} must be a canonical sha256 digest")
    return value


def _canonical_absolute_path(value: object, *, field: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str):
        path = Path(value)
    else:
        _fail(f"{field} must be an absolute path")
    if "\0" in path.as_posix() or not path.is_absolute():
        _fail(f"{field} must be an absolute path")
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise RunRefLedgerError(f"{field} cannot be normalized") from exc
    if resolved != path:
        _fail(f"{field} must be canonical")
    return path


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        _fail("recorded_at must be canonical UTC with six fractional digits")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise RunRefLedgerError("recorded_at is not a valid timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("recorded_at must be UTC")
    return value


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True, slots=True)
class RunRefVisitKey:
    """Complete parent run/frame/step visit identity for one effect site."""

    parent_run_id: str
    execution_frame_id: str
    call_frame_id: str | None
    step_id: str
    visit_count: int

    def __post_init__(self) -> None:
        _nonempty_text(self.parent_run_id, field="parent_run_id")
        _nonempty_text(self.execution_frame_id, field="execution_frame_id")
        if self.call_frame_id is not None:
            _nonempty_text(self.call_frame_id, field="call_frame_id")
        _nonempty_text(self.step_id, field="step_id")
        _positive_integer(self.visit_count, field="visit_count")

    @property
    def record(self) -> dict[str, object]:
        return {
            "parent_run_id": self.parent_run_id,
            "execution_frame_id": self.execution_frame_id,
            "call_frame_id": self.call_frame_id,
            "step_id": self.step_id,
            "visit_count": self.visit_count,
        }


@dataclass(frozen=True, slots=True)
class RunRefAttemptBindings:
    """Closed binding snapshot carried by every event for one ordinal."""

    run_ref_root: Path
    workspace_path: Path
    source_digest: str
    program_digest: str
    input_digest: str
    policy_digest: str
    step_config_digest: str
    capsule_or_compiler_digest: str
    child_run_id: str
    result_contract_digest: str
    verified_git_tree_id: str | None = None
    setup_evidence_digest: str | None = None
    post_setup_baseline_digest: str | None = None
    program_preparation_digest: str | None = None
    child_launch_digest: str | None = None
    child_terminal_state_digest: str | None = None
    result_payload_digest: str | None = None
    workspace_delta_digest: str | None = None
    accounting_digest: str | None = None
    evidence_manifest_digest: str | None = None
    disposition_digest: str | None = None

    def __post_init__(self) -> None:
        root = _canonical_absolute_path(self.run_ref_root, field="run_ref_root")
        workspace = _canonical_absolute_path(
            self.workspace_path,
            field="workspace_path",
        )
        try:
            relative = workspace.relative_to(root)
        except ValueError as exc:
            raise RunRefLedgerError(
                "workspace_path must be below run_ref_root"
            ) from exc
        if relative == Path("."):
            _fail("workspace_path must be a strict child of run_ref_root")
        object.__setattr__(self, "run_ref_root", root)
        object.__setattr__(self, "workspace_path", workspace)

        for name in (
            "source_digest",
            "program_digest",
            "input_digest",
            "policy_digest",
            "step_config_digest",
            "capsule_or_compiler_digest",
            "result_contract_digest",
        ):
            _sha256(getattr(self, name), field=name)
        if (
            not isinstance(self.child_run_id, str)
            or _RUN_ID_RE.fullmatch(self.child_run_id) is None
        ):
            _fail("child_run_id is not canonical")
        if self.verified_git_tree_id is not None and (
            not isinstance(self.verified_git_tree_id, str)
            or _GIT_TREE_RE.fullmatch(self.verified_git_tree_id) is None
        ):
            _fail("verified_git_tree_id must be canonical")
        for name in (
            "setup_evidence_digest",
            "post_setup_baseline_digest",
            "program_preparation_digest",
            "child_launch_digest",
            "child_terminal_state_digest",
            "result_payload_digest",
            "workspace_delta_digest",
            "accounting_digest",
            "evidence_manifest_digest",
            "disposition_digest",
        ):
            _sha256(getattr(self, name), field=name, optional=True)

    @property
    def record(self) -> dict[str, object]:
        return {
            field.name: (
                getattr(self, field.name).as_posix()
                if isinstance(getattr(self, field.name), Path)
                else getattr(self, field.name)
            )
            for field in fields(self)
        }


# Defined after the dataclass so the field census cannot drift from its schema.
_IMMUTABLE_BINDINGS = frozenset(
    field.name for field in fields(RunRefAttemptBindings)
) - _PROGRESSIVE_BINDINGS - {"disposition_digest"}
_RETRY_STABLE_BINDINGS = _IMMUTABLE_BINDINGS - {
    "workspace_path",
    "child_run_id",
}


@dataclass(frozen=True, slots=True)
class RunRefAttemptRecord:
    sequence: int
    previous_row_digest: str | None
    row_digest: str
    visit: RunRefVisitKey
    attempt_ordinal: int
    stage: str
    status: str
    recorded_at: str
    bindings: RunRefAttemptBindings

    @property
    def record(self) -> dict[str, object]:
        return {
            "schema_version": RUN_REF_ATTEMPT_LEDGER_SCHEMA,
            "sequence": self.sequence,
            "previous_row_digest": self.previous_row_digest,
            "row_digest": self.row_digest,
            "visit": self.visit.record,
            "attempt_ordinal": self.attempt_ordinal,
            "stage": self.stage,
            "status": self.status,
            "recorded_at": self.recorded_at,
            "bindings": self.bindings.record,
        }


@dataclass(frozen=True, slots=True)
class RunRefAttemptLedger:
    rows: tuple[RunRefAttemptRecord, ...]


@dataclass(frozen=True, slots=True)
class SettledRunRefResultBinding:
    """Exact parent-state binding to one completed-pending ledger row."""

    visit: RunRefVisitKey
    attempt_ordinal: int
    step_config_digest: str
    run_ref_root: Path
    workspace_path: Path
    child_run_id: str
    pending_row_digest: str
    child_terminal_state_digest: str
    result_contract_digest: str
    result_payload_digest: str
    workspace_delta_digest: str
    accounting_digest: str
    evidence_manifest_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.visit, RunRefVisitKey):
            raise TypeError("visit must be RunRefVisitKey")
        _positive_integer(self.attempt_ordinal, field="attempt_ordinal")
        for name in (
            "step_config_digest",
            "pending_row_digest",
            "child_terminal_state_digest",
            "result_contract_digest",
            "result_payload_digest",
            "workspace_delta_digest",
            "accounting_digest",
            "evidence_manifest_digest",
        ):
            _sha256(getattr(self, name), field=name)
        root = _canonical_absolute_path(self.run_ref_root, field="run_ref_root")
        workspace = _canonical_absolute_path(
            self.workspace_path,
            field="workspace_path",
        )
        try:
            workspace.relative_to(root)
        except ValueError as exc:
            raise RunRefLedgerError(
                "workspace_path must be below run_ref_root"
            ) from exc
        if (
            not isinstance(self.child_run_id, str)
            or _RUN_ID_RE.fullmatch(self.child_run_id) is None
        ):
            _fail("child_run_id is not canonical")
        object.__setattr__(self, "run_ref_root", root)
        object.__setattr__(self, "workspace_path", workspace)

    @property
    def record(self) -> dict[str, object]:
        return {
            "visit": self.visit.record,
            "attempt_ordinal": self.attempt_ordinal,
            "step_config_digest": self.step_config_digest,
            "run_ref_root": self.run_ref_root.as_posix(),
            "workspace_path": self.workspace_path.as_posix(),
            "child_run_id": self.child_run_id,
            "pending_row_digest": self.pending_row_digest,
            "child_terminal_state_digest": self.child_terminal_state_digest,
            "result_contract_digest": self.result_contract_digest,
            "result_payload_digest": self.result_payload_digest,
            "workspace_delta_digest": self.workspace_delta_digest,
            "accounting_digest": self.accounting_digest,
            "evidence_manifest_digest": self.evidence_manifest_digest,
        }


_SETTLED_BINDING_KEYS = frozenset(
    field.name for field in fields(SettledRunRefResultBinding)
)


def _row_payload_without_digest(
    *,
    sequence: int,
    previous_row_digest: str | None,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
    stage: str,
    status: str,
    recorded_at: str,
    bindings: RunRefAttemptBindings,
) -> dict[str, object]:
    return {
        "schema_version": RUN_REF_ATTEMPT_LEDGER_SCHEMA,
        "sequence": sequence,
        "previous_row_digest": previous_row_digest,
        "visit": visit.record,
        "attempt_ordinal": attempt_ordinal,
        "stage": stage,
        "status": status,
        "recorded_at": recorded_at,
        "bindings": bindings.record,
    }


def _build_row(
    *,
    sequence: int,
    previous_row_digest: str | None,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
    stage: str,
    status: str,
    recorded_at: str,
    bindings: RunRefAttemptBindings,
) -> RunRefAttemptRecord:
    payload = _row_payload_without_digest(
        sequence=sequence,
        previous_row_digest=previous_row_digest,
        visit=visit,
        attempt_ordinal=attempt_ordinal,
        stage=stage,
        status=status,
        recorded_at=_timestamp(recorded_at),
        bindings=bindings,
    )
    return RunRefAttemptRecord(
        sequence=sequence,
        previous_row_digest=previous_row_digest,
        row_digest=canonical_sha256(payload),
        visit=visit,
        attempt_ordinal=attempt_ordinal,
        stage=stage,
        status=status,
        recorded_at=recorded_at,
        bindings=bindings,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    _fail(f"non-finite JSON constant: {value}")


def _closed_mapping(
    value: object,
    keys: frozenset[str],
    *,
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail(f"{field} has missing or extra fields")
    return value


def _visit_from_record(value: object) -> RunRefVisitKey:
    row = _closed_mapping(value, _VISIT_KEYS, field="visit")
    return RunRefVisitKey(
        parent_run_id=row["parent_run_id"],
        execution_frame_id=row["execution_frame_id"],
        call_frame_id=row["call_frame_id"],
        step_id=row["step_id"],
        visit_count=row["visit_count"],
    )


def _bindings_from_record(value: object) -> RunRefAttemptBindings:
    expected = frozenset(field.name for field in fields(RunRefAttemptBindings))
    row = _closed_mapping(value, expected, field="bindings")
    return RunRefAttemptBindings(**row)


def _decode_row(value: object, *, expected_sequence: int) -> RunRefAttemptRecord:
    row = _closed_mapping(value, _ROW_KEYS, field="ledger row")
    if row["schema_version"] != RUN_REF_ATTEMPT_LEDGER_SCHEMA:
        _fail("ledger row schema version is invalid")
    sequence = _positive_integer(row["sequence"], field="sequence")
    if sequence != expected_sequence:
        _fail("ledger row sequence is not contiguous")
    previous = _sha256(
        row["previous_row_digest"],
        field="previous_row_digest",
        optional=True,
    )
    visit = _visit_from_record(row["visit"])
    attempt_ordinal = _positive_integer(
        row["attempt_ordinal"],
        field="attempt_ordinal",
    )
    stage = _nonempty_text(row["stage"], field="stage")
    status = _nonempty_text(row["status"], field="status")
    recorded_at = _timestamp(row["recorded_at"])
    bindings = _bindings_from_record(row["bindings"])
    expected_digest = canonical_sha256(
        _row_payload_without_digest(
            sequence=sequence,
            previous_row_digest=previous,
            visit=visit,
            attempt_ordinal=attempt_ordinal,
            stage=stage,
            status=status,
            recorded_at=recorded_at,
            bindings=bindings,
        )
    )
    digest = _sha256(row["row_digest"], field="row_digest")
    if digest != expected_digest:
        _fail("ledger row digest does not match its canonical payload")
    return RunRefAttemptRecord(
        sequence=sequence,
        previous_row_digest=previous,
        row_digest=digest,
        visit=visit,
        attempt_ordinal=attempt_ordinal,
        stage=stage,
        status=status,
        recorded_at=recorded_at,
        bindings=bindings,
    )


def load_attempt_ledger(path: Path) -> RunRefAttemptLedger:
    """Load a complete canonical ledger; missing means no attempts yet."""

    source = Path(path)
    if not os.path.lexists(source):
        return RunRefAttemptLedger(())
    try:
        identity = source.lstat()
        payload = source.read_bytes()
    except OSError as exc:
        raise RunRefLedgerError("ledger cannot be read") from exc
    if not stat.S_ISREG(identity.st_mode):
        _fail("ledger must be a regular file")
    if not payload or not payload.endswith(b"\n"):
        _fail("ledger is empty or truncated")

    rows: list[RunRefAttemptRecord] = []
    previous_digest: str | None = None
    for sequence, framed in enumerate(payload.splitlines(keepends=True), start=1):
        if not framed.endswith(b"\n") or framed == b"\n":
            _fail("ledger contains a truncated or blank row")
        line = framed[:-1]
        try:
            value = json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RunRefLedgerError("ledger row is not strict JSON") from exc
        if canonical_json_bytes(value) != line:
            _fail("ledger row is not canonical JSON")
        row = _decode_row(value, expected_sequence=sequence)
        if row.previous_row_digest != previous_digest:
            _fail("ledger hash chain is discontinuous")
        if rows and row.recorded_at < rows[-1].recorded_at:
            _fail("ledger timestamps are not monotonic")
        rows.append(row)
        previous_digest = row.row_digest

    _validate_lifecycle(tuple(rows))
    return RunRefAttemptLedger(tuple(rows))


def _validate_lifecycle(rows: tuple[RunRefAttemptRecord, ...]) -> None:
    """Validate every ordinal and transition as one closed state machine."""

    by_visit: dict[RunRefVisitKey, dict[int, RunRefAttemptRecord]] = {}
    workspaces: set[Path] = set()
    child_runs: set[str] = set()
    for row in rows:
        if row.stage not in _STATUS_BY_STAGE:
            _fail("ledger row stage is unsupported")
        if row.status not in {_STATUS_BY_STAGE[row.stage], "discarded"}:
            _fail("ledger row status does not match its stage")
        _validate_stage_bindings(row)

        attempts = by_visit.setdefault(row.visit, {})
        if row.stage == "allocated":
            existing = attempts.get(row.attempt_ordinal)
            if existing is None:
                expected_ordinal = max(attempts, default=0) + 1
                if row.attempt_ordinal != expected_ordinal:
                    _fail("attempt ordinals are not positive and contiguous")
                if attempts:
                    predecessor = attempts[max(attempts)]
                    if predecessor.status != "discarded":
                        _fail("a fresh ordinal requires a discarded predecessor")
                    for name in _RETRY_STABLE_BINDINGS:
                        if getattr(predecessor.bindings, name) != getattr(
                            row.bindings,
                            name,
                        ):
                            _fail(f"fresh ordinal changed retry binding: {name}")
                if row.status != "in_progress":
                    _fail("allocated row must begin in progress")
                if row.bindings.workspace_path in workspaces:
                    _fail("attempt workspace binding is ambiguous")
                if row.bindings.child_run_id in child_runs:
                    _fail("child run binding is ambiguous")
                workspaces.add(row.bindings.workspace_path)
                child_runs.add(row.bindings.child_run_id)
                attempts[row.attempt_ordinal] = row
                continue
            if row.status == "discarded":
                _validate_discard_transition(existing, row)
                attempts[row.attempt_ordinal] = row
                continue
            _fail("attempt ordinal has more than one allocation")

        previous = attempts.get(row.attempt_ordinal)
        if previous is None:
            _fail("attempt transition has no allocated predecessor")
        if row.attempt_ordinal != max(attempts):
            _fail("attempt transition targets a superseded ordinal")
        if row.status == "discarded":
            _validate_discard_transition(previous, row)
            attempts[row.attempt_ordinal] = row
            continue
        if previous.status not in {"in_progress", "pending_parent_commit"}:
            _fail("attempt transition follows a terminal row")
        expected_stage = _STAGES[_STAGES.index(previous.stage) + 1]
        if row.stage != expected_stage:
            _fail("attempt stage transition is invalid")
        _validate_binding_transition(previous.bindings, row.bindings, row.stage)
        attempts[row.attempt_ordinal] = row


def _validate_stage_bindings(row: RunRefAttemptRecord) -> None:
    stage_index = _STAGES.index(row.stage)
    for candidate_stage, names in _INTRODUCED_BINDINGS.items():
        introduced_index = _STAGES.index(candidate_stage)
        for name in names:
            value = getattr(row.bindings, name)
            if introduced_index <= stage_index and value is None:
                _fail(f"{row.stage} requires binding {name}")
            if introduced_index > stage_index and value is not None:
                _fail(f"{row.stage} carries premature binding {name}")
    if row.status == "discarded":
        if row.stage == "committed" or row.bindings.disposition_digest is None:
            _fail("discarded row requires a non-committed disposition")
    elif row.bindings.disposition_digest is not None:
        _fail("non-discarded row may not carry a disposition digest")


def _validate_discard_transition(
    previous: RunRefAttemptRecord,
    current: RunRefAttemptRecord,
) -> None:
    if previous.status not in {"in_progress", "pending_parent_commit"}:
        _fail("only an incomplete attempt may be discarded")
    if current.stage != previous.stage or current.status != "discarded":
        _fail("discard transition must retain its crash-boundary stage")
    for name in _IMMUTABLE_BINDINGS | _PROGRESSIVE_BINDINGS:
        if getattr(previous.bindings, name) != getattr(current.bindings, name):
            _fail(f"discard transition changed binding: {name}")
    if (
        previous.bindings.disposition_digest is not None
        or current.bindings.disposition_digest is None
    ):
        _fail("discard transition disposition binding is invalid")


def _validate_binding_transition(
    previous: RunRefAttemptBindings,
    current: RunRefAttemptBindings,
    stage: str,
) -> None:
    for name in _IMMUTABLE_BINDINGS:
        if getattr(previous, name) != getattr(current, name):
            _fail(f"attempt immutable binding changed: {name}")
    introduced = _INTRODUCED_BINDINGS[stage]
    for name in _PROGRESSIVE_BINDINGS:
        old_value = getattr(previous, name)
        new_value = getattr(current, name)
        if name in introduced:
            if old_value is not None or new_value is None:
                _fail(f"attempt binding was not introduced at {stage}: {name}")
        elif old_value != new_value:
            _fail(f"attempt binding changed outside its stage: {name}")
    if current.disposition_digest is not None:
        _fail("ordinary transition may not carry a disposition digest")


def _persist_append(
    path: Path,
    ledger: RunRefAttemptLedger,
    row: RunRefAttemptRecord,
) -> None:
    payload = b"".join(
        canonical_json_bytes(existing.record) + b"\n"
        for existing in (*ledger.rows, row)
    )
    durable_atomic_write(Path(path), payload)


def allocate_attempt(
    path: Path,
    *,
    visit: RunRefVisitKey,
    bindings: RunRefAttemptBindings,
    recorded_at: str | None = None,
) -> RunRefAttemptRecord:
    """Allocate and durably persist the first fresh ordinal for one visit."""

    if not isinstance(visit, RunRefVisitKey):
        raise TypeError("visit must be RunRefVisitKey")
    if not isinstance(bindings, RunRefAttemptBindings):
        raise TypeError("bindings must be RunRefAttemptBindings")
    ledger = load_attempt_ledger(path)
    matching = [row for row in ledger.rows if row.visit == visit]
    if matching and matching[-1].status != "discarded":
        _fail("an attempt is already active or committed for this visit")
    if matching:
        predecessor = matching[-1]
        for name in _RETRY_STABLE_BINDINGS:
            if getattr(predecessor.bindings, name) != getattr(bindings, name):
                _fail(f"fresh ordinal changed retry binding: {name}")
        attempt_ordinal = predecessor.attempt_ordinal + 1
    else:
        attempt_ordinal = 1
    if os.path.lexists(bindings.workspace_path):
        _fail("allocated attempt workspace must not preexist")
    row = _build_row(
        sequence=len(ledger.rows) + 1,
        previous_row_digest=(ledger.rows[-1].row_digest if ledger.rows else None),
        visit=visit,
        attempt_ordinal=attempt_ordinal,
        stage="allocated",
        status="in_progress",
        recorded_at=recorded_at or _utc_timestamp(),
        bindings=bindings,
    )
    _persist_append(path, ledger, row)
    return row


def _latest_attempt(
    ledger: RunRefAttemptLedger,
    *,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
) -> RunRefAttemptRecord:
    matching = [
        row
        for row in ledger.rows
        if row.visit == visit and row.attempt_ordinal == attempt_ordinal
    ]
    if not matching:
        _fail("attempt ordinal is not present")
    return matching[-1]


def advance_attempt(
    path: Path,
    *,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
    stage: str,
    binding_updates: Mapping[str, str],
    recorded_at: str | None = None,
) -> RunRefAttemptRecord:
    """Append the one exact next crash-boundary transition for an attempt."""

    if not isinstance(visit, RunRefVisitKey):
        raise TypeError("visit must be RunRefVisitKey")
    _positive_integer(attempt_ordinal, field="attempt_ordinal")
    if stage not in _STAGES[1:-1]:
        _fail("stage is not an ordinary advance boundary")
    if not isinstance(binding_updates, Mapping):
        raise TypeError("binding_updates must be a mapping")
    expected_updates = _INTRODUCED_BINDINGS[stage]
    if set(binding_updates) != expected_updates:
        _fail("binding updates do not match the target stage")

    ledger = load_attempt_ledger(path)
    previous = _latest_attempt(
        ledger,
        visit=visit,
        attempt_ordinal=attempt_ordinal,
    )
    if previous.status != "in_progress":
        _fail("attempt is not eligible for an ordinary advance")
    expected_stage = _STAGES[_STAGES.index(previous.stage) + 1]
    if stage != expected_stage:
        _fail("attempt stage transition is invalid")
    bindings = replace(previous.bindings, **dict(binding_updates))
    row = _build_row(
        sequence=len(ledger.rows) + 1,
        previous_row_digest=ledger.rows[-1].row_digest,
        visit=visit,
        attempt_ordinal=attempt_ordinal,
        stage=stage,
        status=_STATUS_BY_STAGE[stage],
        recorded_at=recorded_at or _utc_timestamp(),
        bindings=bindings,
    )
    _validate_binding_transition(previous.bindings, row.bindings, stage)
    _validate_stage_bindings(row)
    _persist_append(path, ledger, row)
    return row


def settled_result_binding(
    pending: RunRefAttemptRecord,
) -> SettledRunRefResultBinding:
    """Build the exact parent-state binding for one pending settlement row."""

    if not isinstance(pending, RunRefAttemptRecord):
        raise TypeError("pending must be RunRefAttemptRecord")
    if (
        pending.stage != "completed_pending_parent_commit"
        or pending.status != "pending_parent_commit"
    ):
        _fail("settled parent binding requires a completed-pending row")
    bindings = pending.bindings
    required = {
        "child_terminal_state_digest": bindings.child_terminal_state_digest,
        "result_payload_digest": bindings.result_payload_digest,
        "workspace_delta_digest": bindings.workspace_delta_digest,
        "accounting_digest": bindings.accounting_digest,
        "evidence_manifest_digest": bindings.evidence_manifest_digest,
    }
    if any(value is None for value in required.values()):
        _fail("completed-pending row is missing a settlement binding")
    return SettledRunRefResultBinding(
        visit=pending.visit,
        attempt_ordinal=pending.attempt_ordinal,
        step_config_digest=bindings.step_config_digest,
        run_ref_root=bindings.run_ref_root,
        workspace_path=bindings.workspace_path,
        child_run_id=bindings.child_run_id,
        pending_row_digest=pending.row_digest,
        child_terminal_state_digest=bindings.child_terminal_state_digest,
        result_contract_digest=bindings.result_contract_digest,
        result_payload_digest=bindings.result_payload_digest,
        workspace_delta_digest=bindings.workspace_delta_digest,
        accounting_digest=bindings.accounting_digest,
        evidence_manifest_digest=bindings.evidence_manifest_digest,
    )


def settled_result_binding_from_record(
    value: object,
) -> SettledRunRefResultBinding:
    """Decode the closed binding persisted inside ``StepResult.run_ref``."""

    row = _closed_mapping(
        value,
        _SETTLED_BINDING_KEYS,
        field="settled parent binding",
    )
    return SettledRunRefResultBinding(
        visit=_visit_from_record(row["visit"]),
        attempt_ordinal=row["attempt_ordinal"],
        step_config_digest=row["step_config_digest"],
        run_ref_root=row["run_ref_root"],
        workspace_path=row["workspace_path"],
        child_run_id=row["child_run_id"],
        pending_row_digest=row["pending_row_digest"],
        child_terminal_state_digest=row["child_terminal_state_digest"],
        result_contract_digest=row["result_contract_digest"],
        result_payload_digest=row["result_payload_digest"],
        workspace_delta_digest=row["workspace_delta_digest"],
        accounting_digest=row["accounting_digest"],
        evidence_manifest_digest=row["evidence_manifest_digest"],
    )


def _exact_pending_row(
    ledger: RunRefAttemptLedger,
    settled_result: SettledRunRefResultBinding,
) -> RunRefAttemptRecord:
    candidates = [
        row
        for row in ledger.rows
        if row.row_digest == settled_result.pending_row_digest
    ]
    if len(candidates) != 1:
        _fail("settled parent result does not identify one pending row")
    pending = candidates[0]
    if settled_result_binding(pending) != settled_result:
        _fail("settled parent result disagrees with its pending row")
    return pending


def _validate_current_config(
    settled_result: SettledRunRefResultBinding,
    current_step_config_digest: str,
) -> None:
    _sha256(current_step_config_digest, field="current_step_config_digest")
    if current_step_config_digest != settled_result.step_config_digest:
        _fail("current step config disagrees with settled parent result")


def _require_authority_validator(
    value: object,
) -> Callable[[RunRefAttemptRecord], None]:
    if not callable(value):
        raise TypeError("validate_bound_authority must be callable")
    return value


def validate_pending_parent_commit(
    path: Path,
    *,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
    current_step_config_digest: str,
    settled_result: SettledRunRefResultBinding,
) -> bool:
    """Validate one exact pending settlement without changing the ledger."""

    if not isinstance(visit, RunRefVisitKey):
        raise TypeError("visit must be RunRefVisitKey")
    _positive_integer(attempt_ordinal, field="attempt_ordinal")
    if not isinstance(settled_result, SettledRunRefResultBinding):
        raise TypeError("settled_result must be SettledRunRefResultBinding")
    _validate_current_config(settled_result, current_step_config_digest)
    if settled_result.visit != visit:
        _fail("settled parent result disagrees with the expected visit")
    if settled_result.attempt_ordinal != attempt_ordinal:
        _fail("settled parent result disagrees with the expected attempt ordinal")

    ledger = load_attempt_ledger(path)
    matching = [
        row
        for row in ledger.rows
        if row.visit == visit and row.attempt_ordinal == attempt_ordinal
    ]
    pending = [
        row
        for row in matching
        if row.stage == "completed_pending_parent_commit"
        and row.status == "pending_parent_commit"
    ]
    if len(pending) != 1:
        _fail("selected attempt does not have exactly one pending parent commit")
    if matching[-1] != pending[0]:
        _fail("latest selected attempt row is not pending parent commit")
    if _exact_pending_row(ledger, settled_result) != pending[0]:
        _fail("settled parent result identifies a different pending row")
    if load_attempt_ledger(path) != ledger:
        _fail("ledger changed while pending parent commit was validated")
    return True


def reconcile_pending_parent_commit(
    path: Path,
    *,
    settled_result: SettledRunRefResultBinding,
    current_step_config_digest: str,
    validate_bound_authority: Callable[[RunRefAttemptRecord], None],
    recorded_at: str | None = None,
) -> RunRefAttemptRecord:
    """Append the missing commit only from exact settled parent authority."""

    if not isinstance(settled_result, SettledRunRefResultBinding):
        raise TypeError("settled_result must be SettledRunRefResultBinding")
    validator = _require_authority_validator(validate_bound_authority)
    _validate_current_config(settled_result, current_step_config_digest)
    ledger = load_attempt_ledger(path)
    pending = _exact_pending_row(ledger, settled_result)
    committed = [
        row
        for row in ledger.rows
        if row.visit == pending.visit
        and row.attempt_ordinal == pending.attempt_ordinal
        and row.stage == "committed"
    ]
    if len(committed) > 1:
        _fail("settled parent result has ambiguous committed rows")
    if committed:
        if committed[0].bindings != pending.bindings:
            _fail("committed row disagrees with pending bindings")
        validator(committed[0])
        return committed[0]
    latest = _latest_attempt(
        ledger,
        visit=pending.visit,
        attempt_ordinal=pending.attempt_ordinal,
    )
    if latest != pending:
        _fail("pending row is no longer the attempt head")
    validator(pending)
    if load_attempt_ledger(path) != ledger:
        _fail("ledger changed while pending authority was validated")
    row = _build_row(
        sequence=len(ledger.rows) + 1,
        previous_row_digest=ledger.rows[-1].row_digest,
        visit=pending.visit,
        attempt_ordinal=pending.attempt_ordinal,
        stage="committed",
        status="committed",
        recorded_at=recorded_at or _utc_timestamp(),
        bindings=pending.bindings,
    )
    _validate_binding_transition(pending.bindings, row.bindings, "committed")
    _persist_append(path, ledger, row)
    return row


def select_committed_reuse(
    path: Path,
    *,
    settled_result: SettledRunRefResultBinding,
    current_step_config_digest: str,
    validate_bound_authority: Callable[[RunRefAttemptRecord], None],
) -> RunRefAttemptRecord:
    """Return one unique fully validated committed attempt for zero-launch reuse."""

    if not isinstance(settled_result, SettledRunRefResultBinding):
        raise TypeError("settled_result must be SettledRunRefResultBinding")
    validator = _require_authority_validator(validate_bound_authority)
    _validate_current_config(settled_result, current_step_config_digest)
    ledger = load_attempt_ledger(path)
    pending = _exact_pending_row(ledger, settled_result)
    committed = [
        row
        for row in ledger.rows
        if row.visit == settled_result.visit
        and row.attempt_ordinal == settled_result.attempt_ordinal
        and row.stage == "committed"
    ]
    if len(committed) != 1:
        _fail("settled parent result does not have one committed row")
    candidate = committed[0]
    if (
        candidate.previous_row_digest != pending.row_digest
        or candidate.bindings != pending.bindings
    ):
        _fail("committed row is not adjacent to its exact pending row")
    validator(candidate)
    if load_attempt_ledger(path) != ledger:
        _fail("ledger changed while committed authority was validated")
    return candidate


def identify_incomplete_attempt(
    path: Path,
    *,
    visit: RunRefVisitKey,
    current_step_config_digest: str,
) -> RunRefAttemptRecord | None:
    """Return the unique nonterminal ordinal that requires disposition."""

    if not isinstance(visit, RunRefVisitKey):
        raise TypeError("visit must be RunRefVisitKey")
    _sha256(current_step_config_digest, field="current_step_config_digest")
    ledger = load_attempt_ledger(path)
    matching = [row for row in ledger.rows if row.visit == visit]
    if not matching:
        return None
    if any(
        row.bindings.step_config_digest != current_step_config_digest
        for row in matching
    ):
        _fail("attempt ledger step config differs from the current config")
    latest_by_ordinal: dict[int, RunRefAttemptRecord] = {}
    for row in matching:
        latest_by_ordinal[row.attempt_ordinal] = row
    incomplete = [
        row
        for row in latest_by_ordinal.values()
        if row.status in {"in_progress", "pending_parent_commit"}
    ]
    if len(incomplete) > 1:
        _fail("attempt ledger has ambiguous incomplete ordinals")
    return incomplete[0] if incomplete else None


def record_discarded_attempt(
    path: Path,
    *,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
    workspace_path: Path,
    disposition_digest: str,
    recorded_at: str | None = None,
) -> RunRefAttemptRecord:
    """Record disposition only after the exact bound workspace is absent."""

    if not isinstance(visit, RunRefVisitKey):
        raise TypeError("visit must be RunRefVisitKey")
    _positive_integer(attempt_ordinal, field="attempt_ordinal")
    disposition = _sha256(disposition_digest, field="disposition_digest")
    workspace = _canonical_absolute_path(workspace_path, field="workspace_path")
    ledger = load_attempt_ledger(path)
    previous = _latest_attempt(
        ledger,
        visit=visit,
        attempt_ordinal=attempt_ordinal,
    )
    if previous.status not in {"in_progress", "pending_parent_commit"}:
        _fail("only an incomplete attempt may be discarded")
    if workspace != previous.bindings.workspace_path:
        _fail("discard workspace does not match the exact attempt binding")
    if os.path.lexists(workspace):
        _fail("discard workspace still exists")
    bindings = replace(previous.bindings, disposition_digest=disposition)
    row = _build_row(
        sequence=len(ledger.rows) + 1,
        previous_row_digest=ledger.rows[-1].row_digest,
        visit=visit,
        attempt_ordinal=attempt_ordinal,
        stage=previous.stage,
        status="discarded",
        recorded_at=recorded_at or _utc_timestamp(),
        bindings=bindings,
    )
    _validate_discard_transition(previous, row)
    if os.path.lexists(workspace):
        _fail("discard workspace reappeared before disposition was recorded")
    if load_attempt_ledger(path) != ledger:
        _fail("ledger changed while discard absence was validated")
    _persist_append(path, ledger, row)
    return row


__all__ = [
    "RUN_REF_ATTEMPT_LEDGER_SCHEMA",
    "RunRefAttemptBindings",
    "RunRefAttemptLedger",
    "RunRefAttemptRecord",
    "RunRefLedgerError",
    "SettledRunRefResultBinding",
    "RunRefVisitKey",
    "advance_attempt",
    "allocate_attempt",
    "identify_incomplete_attempt",
    "load_attempt_ledger",
    "reconcile_pending_parent_commit",
    "record_discarded_attempt",
    "select_committed_reuse",
    "settled_result_binding",
    "settled_result_binding_from_record",
    "validate_pending_parent_commit",
]
