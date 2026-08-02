"""Canonical single-writer event ledger for target-2.25 trial effects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import (
    RunRefAttemptRecord,
    RunRefLedgerError,
    RunRefVisitKey,
    SettledRunRefResultBinding,
    identify_incomplete_attempt,
    load_attempt_ledger,
    record_discarded_attempt,
    settled_result_binding,
    settled_result_binding_from_record,
)
from orchestrator.workflow.run_ref.runtime import (
    RunRefLifecycleAcknowledgement,
    RunRefLifecycleEvent,
    acknowledge_persisted_run_ref_lifecycle_event,
)

from .config import TrialRuntimeRequest
from .contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellEffectScope,
    TrialCellKey,
    TrialOpaqueLabelBinding,
)


TRIAL_EVENT_LEDGER_SCHEMA = "trial_event_ledger.v1"
_FILENAME = "trial-events.jsonl"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_ROW_KEYS = {
    "schema_version",
    "sequence",
    "previous_row_digest",
    "row_digest",
    "kind",
    "recorded_at",
    "payload",
}
_HEADER_KEYS = {
    "trial_static_config_digest",
    "trial_step_config_digest",
    "arm_run_ref_authorities",
    "trial_request_digest",
    "evaluation_digest",
    "budget_digest",
    "result_contract_digest",
    "compiler_runtime_identity_digest",
    "visit",
    "cell_domain",
    "cell_domain_digest",
    "sealed_opaque_label_map",
    "sealed_opaque_label_map_digest",
    "runtime_budget_window",
    "runtime_budget_window_digest",
}
_ALLOCATION_KEYS = {
    "cell",
    "opaque_label",
    "effect_instance_digest",
    "effect_instance_root",
    "run_ref_root",
    "e1_ledger_path",
    "attempt_ordinal",
    "e1_allocation_row_digest",
    "run_ref_step_config_digest",
    "result_contract_digest",
}
_PREPARED_KEYS = {
    "cell",
    "attempt_ordinal",
    "e1_pending_row_digest",
    "settled_result",
    "settled_result_digest",
    "result_envelope_digest",
    "artifact_projection_digest",
    "evidence_manifest_digest",
}
_SETTLEMENT_KEYS = {
    "cell",
    "attempt_ordinal",
    "prepared_trial_row_digest",
    "e1_pending_row_digest",
    "settled_result_digest",
    "outcome_digest",
    "evidence_digest",
}
_FAILED_KEYS = {
    "cell",
    "attempt_ordinal",
    "e1_authority_row_digest",
    "failure",
    "failure_digest",
    "outcome_digest",
    "evidence_digest",
}
_COMMITTED_KEYS = {
    "cell",
    "attempt_ordinal",
    "trial_settlement_row_digest",
    "e1_pending_row_digest",
    "e1_committed_row_digest",
}
_DISCARDED_KEYS = {
    "cell",
    "attempt_ordinal",
    "e1_incomplete_row_digest",
    "e1_discarded_row_digest",
    "disposition_digest",
    "next_attempt_ordinal",
}
_PAYLOAD_KEYS_BY_KIND = {
    "header": _HEADER_KEYS,
    "cell_allocated": _ALLOCATION_KEYS,
    "cell_prepared": _PREPARED_KEYS,
    "cell_settled": _SETTLEMENT_KEYS,
    "cell_failed": _FAILED_KEYS,
    "cell_e1_committed": _COMMITTED_KEYS,
    "cell_discarded": _DISCARDED_KEYS,
}


class TrialLedgerError(ValueError):
    """The exact trial ledger cannot be interpreted or advanced."""

    code = "trial_ledger_invalid"


def _fail(message: str) -> None:
    raise TrialLedgerError(message)


def _digest(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{field} must be a canonical sha256 digest")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        _fail("trial ledger timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise TrialLedgerError("trial ledger timestamp is invalid") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("trial ledger timestamp must be UTC")
    return value


def _positive_integer(value: object, *, field: str) -> int:
    if type(value) is not int or value < 1:
        _fail(f"{field} must be a positive integer")
    return value


def _optional_positive_integer(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    return _positive_integer(value, field=field)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _closed(value: object, keys: set[str], *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail(f"{field} has missing or extra fields")
    return value


def _cell(value: object) -> TrialCellKey:
    row = _closed(value, {"arm_id", "rep"}, field="trial cell")
    try:
        return TrialCellKey(arm_id=row["arm_id"], rep=row["rep"])
    except (TypeError, ValueError) as exc:
        raise TrialLedgerError("trial cell is invalid") from exc


def _failed_outcome_digest(
    *,
    cell: TrialCellKey,
    failure: Mapping[str, Any],
) -> str:
    return canonical_sha256(
        {
            "schema_version": "trial_cell_failed_outcome.v1",
            "cell": cell.record,
            "failure": dict(failure),
        }
    )


def _failed_evidence_digest(
    *,
    cell: TrialCellKey,
    failure_digest: str,
    e1_authority_row_digest: str | None,
) -> str:
    return canonical_sha256(
        {
            "schema_version": "trial_cell_partial_evidence.v1",
            "cell": cell.record,
            "failure_digest": failure_digest,
            "e1_authority_row_digest": e1_authority_row_digest,
        }
    )


def _canonical_absolute(value: object, *, field: str) -> Path:
    if not isinstance(value, (str, Path)):
        _fail(f"{field} must be an absolute path")
    path = Path(value)
    if not path.is_absolute() or "\0" in path.as_posix():
        _fail(f"{field} must be an absolute path")
    resolved = path.resolve(strict=False)
    if resolved != path:
        _fail(f"{field} must be canonical and alias-free")
    return path


@dataclass(frozen=True, slots=True)
class TrialLedgerRow:
    sequence: int
    previous_row_digest: str | None
    row_digest: str
    kind: str
    recorded_at: str
    _payload_json: bytes

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    @property
    def record(self) -> dict[str, Any]:
        return {
            "schema_version": TRIAL_EVENT_LEDGER_SCHEMA,
            "sequence": self.sequence,
            "previous_row_digest": self.previous_row_digest,
            "row_digest": self.row_digest,
            "kind": self.kind,
            "recorded_at": self.recorded_at,
            "payload": self.payload,
        }


@dataclass(frozen=True, slots=True)
class TrialEventLedger:
    rows: tuple[TrialLedgerRow, ...]


@dataclass(frozen=True, slots=True)
class TrialRuntimeBudgetWindow:
    """Durable absolute deadline authority for one trial request."""

    opened_at_unix_ns: int
    arm_deadlines: tuple[tuple[str, int], ...]
    trial_deadline_unix_ns: int

    @property
    def record(self) -> dict[str, Any]:
        return {
            "schema_version": "trial_runtime_budget_window.v1",
            "opened_at_unix_ns": self.opened_at_unix_ns,
            "arm_deadlines": [
                {"arm_id": arm_id, "deadline_unix_ns": deadline}
                for arm_id, deadline in self.arm_deadlines
            ],
            "trial_deadline_unix_ns": self.trial_deadline_unix_ns,
        }

    @property
    def digest(self) -> str:
        return canonical_sha256(self.record)


@dataclass(frozen=True, slots=True)
class InitializedTrialLedger:
    path: Path
    request: TrialRuntimeRequest
    cell_scopes: tuple[TrialCellEffectScope, ...]
    sealed_opaque_labels: SealedTrialOpaqueLabelMap
    row: TrialLedgerRow


@dataclass(frozen=True, slots=True)
class TrialCellResumeDecision:
    action: str
    cell: TrialCellKey
    attempt_ordinal: int
    next_attempt_ordinal: int | None
    trial_settlement_row_digest: str | None = None
    failure_row_digest: str | None = None


@dataclass(frozen=True, slots=True)
class TrialCellDiscardDisposition:
    cell: TrialCellKey
    attempt_ordinal: int
    next_attempt_ordinal: int
    disposition_digest: str
    trial_row_digest: str


def _row_payload(
    *,
    sequence: int,
    previous_row_digest: str | None,
    kind: str,
    recorded_at: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": TRIAL_EVENT_LEDGER_SCHEMA,
        "sequence": sequence,
        "previous_row_digest": previous_row_digest,
        "kind": kind,
        "recorded_at": recorded_at,
        "payload": dict(payload),
    }


def _build_row(
    *,
    sequence: int,
    previous_row_digest: str | None,
    kind: str,
    recorded_at: str,
    payload: Mapping[str, Any],
) -> TrialLedgerRow:
    if kind not in _PAYLOAD_KEYS_BY_KIND:
        _fail("trial ledger row kind is unsupported")
    if set(payload) != _PAYLOAD_KEYS_BY_KIND[kind]:
        _fail(f"trial ledger {kind} payload has missing or extra fields")
    timestamp = _timestamp(recorded_at)
    canonical_payload = canonical_json_bytes(dict(payload))
    normalized = json.loads(canonical_payload)
    preimage = _row_payload(
        sequence=sequence,
        previous_row_digest=previous_row_digest,
        kind=kind,
        recorded_at=timestamp,
        payload=normalized,
    )
    return TrialLedgerRow(
        sequence=sequence,
        previous_row_digest=previous_row_digest,
        row_digest=canonical_sha256(preimage),
        kind=kind,
        recorded_at=timestamp,
        _payload_json=canonical_payload,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate trial ledger JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    _fail(f"non-finite trial ledger value: {value}")


def _decode_row(value: object, *, sequence: int) -> TrialLedgerRow:
    row = _closed(value, _ROW_KEYS, field="trial ledger row")
    if row["schema_version"] != TRIAL_EVENT_LEDGER_SCHEMA:
        _fail("trial ledger schema version is invalid")
    if type(row["sequence"]) is not int or row["sequence"] != sequence:
        _fail("trial ledger sequence is not contiguous")
    previous = _digest(
        row["previous_row_digest"],
        field="previous_row_digest",
        optional=True,
    )
    kind = row["kind"]
    if not isinstance(kind, str) or kind not in _PAYLOAD_KEYS_BY_KIND:
        _fail("trial ledger row kind is unsupported")
    payload = _closed(
        row["payload"],
        _PAYLOAD_KEYS_BY_KIND[kind],
        field=f"trial ledger {kind} payload",
    )
    recorded_at = _timestamp(row["recorded_at"])
    expected = canonical_sha256(
        _row_payload(
            sequence=sequence,
            previous_row_digest=previous,
            kind=kind,
            recorded_at=recorded_at,
            payload=payload,
        )
    )
    observed = _digest(row["row_digest"], field="row_digest")
    if observed != expected:
        _fail("trial ledger row digest is invalid")
    return TrialLedgerRow(
        sequence=sequence,
        previous_row_digest=previous,
        row_digest=observed,
        kind=kind,
        recorded_at=recorded_at,
        _payload_json=canonical_json_bytes(dict(payload)),
    )


def _validate_header(row: TrialLedgerRow) -> None:
    payload = row.payload
    for field in (
        "trial_static_config_digest",
        "trial_step_config_digest",
        "trial_request_digest",
        "evaluation_digest",
        "budget_digest",
        "result_contract_digest",
        "compiler_runtime_identity_digest",
        "cell_domain_digest",
        "sealed_opaque_label_map_digest",
        "runtime_budget_window_digest",
    ):
        _digest(payload[field], field=field)
    _decode_runtime_budget_window(
        payload["runtime_budget_window"],
        expected_digest=payload["runtime_budget_window_digest"],
    )
    arm_steps = payload["arm_run_ref_authorities"]
    if not isinstance(arm_steps, list) or not arm_steps:
        _fail("trial header arm step-config digests are invalid")
    arm_step_ids: list[str] = []
    for value in arm_steps:
        binding = _closed(
            value,
            {
                "arm_id",
                "run_ref_step_config_digest",
                "result_contract_digest",
            },
            field="trial arm run-ref authority",
        )
        if not isinstance(binding["arm_id"], str) or not binding["arm_id"]:
            _fail("trial arm step-config id is invalid")
        _digest(
            binding["run_ref_step_config_digest"],
            field="run_ref_step_config_digest",
        )
        _digest(
            binding["result_contract_digest"],
            field="arm_result_contract_digest",
        )
        arm_step_ids.append(binding["arm_id"])
    if len(set(arm_step_ids)) != len(arm_step_ids):
        _fail("trial arm step-config domain is ambiguous")
    domain_value = payload["cell_domain"]
    if not isinstance(domain_value, list) or not domain_value:
        _fail("trial header cell domain is invalid")
    domain = tuple(_cell(value) for value in domain_value)
    if len(set(domain)) != len(domain):
        _fail("trial header cell domain is ambiguous")
    if canonical_sha256([cell.record for cell in domain]) != payload[
        "cell_domain_digest"
    ]:
        _fail("trial header cell domain digest is invalid")
    sealed_record = _closed(
        payload["sealed_opaque_label_map"],
        {"schema_version", "bindings"},
        field="sealed opaque-label map",
    )
    if sealed_record["schema_version"] != "trial_opaque_label_map.v1":
        _fail("sealed opaque-label map schema is invalid")
    bindings_value = sealed_record["bindings"]
    if not isinstance(bindings_value, list):
        _fail("sealed opaque-label map bindings are invalid")
    try:
        bindings = tuple(
            TrialOpaqueLabelBinding(
                cell=_cell(
                    _closed(value, {"cell", "opaque_label"}, field="opaque binding")[
                        "cell"
                    ]
                ),
                opaque_label=value["opaque_label"],
            )
            for value in bindings_value
        )
        sealed = SealedTrialOpaqueLabelMap(
            bindings=bindings,
            digest=payload["sealed_opaque_label_map_digest"],
        )
    except (TypeError, ValueError) as exc:
        raise TrialLedgerError("sealed opaque-label map is invalid") from exc
    if tuple(binding.cell for binding in sealed.bindings) != domain:
        _fail("sealed opaque-label map does not cover the exact cell domain")
    visit = _closed(
        payload["visit"],
        {
            "parent_run_id",
            "execution_frame_id",
            "call_frame_id",
            "step_id",
            "visit_count",
        },
        field="trial visit",
    )
    try:
        RunRefVisitKey(
            parent_run_id=visit["parent_run_id"],
            execution_frame_id=visit["execution_frame_id"],
            call_frame_id=visit["call_frame_id"],
            step_id=visit["step_id"],
            visit_count=visit["visit_count"],
        )
    except (TypeError, ValueError) as exc:
        raise TrialLedgerError("trial visit is invalid") from exc


def _validate_row_payload(row: TrialLedgerRow) -> None:
    payload = row.payload
    if row.kind == "header":
        _validate_header(row)
        return
    cell = _cell(payload["cell"])
    attempt = (
        _optional_positive_integer(
            payload["attempt_ordinal"],
            field="trial attempt ordinal",
        )
        if row.kind == "cell_failed"
        else _positive_integer(
            payload["attempt_ordinal"],
            field="trial attempt ordinal",
        )
    )
    if row.kind == "cell_failed":
        authority_digest = _digest(
            payload["e1_authority_row_digest"],
            field="e1_authority_row_digest",
            optional=True,
        )
        if (attempt is None) != (authority_digest is None):
            _fail("trial failed cell attempt authority is incomplete")
        failure = _closed(
            payload["failure"],
            {"code", "phase", "retryable", "secondary_causes"},
            field="trial failure",
        )
        if any(
            not isinstance(failure[field], str) or not failure[field]
            for field in ("code", "phase")
        ):
            _fail("trial failure code and phase must be non-empty text")
        if type(failure["retryable"]) is not bool:
            _fail("trial failure retryable flag must be boolean")
        if not isinstance(failure["secondary_causes"], list):
            _fail("trial failure secondary causes must be an ordered list")
        try:
            failure_digest = canonical_sha256(dict(failure))
        except (TypeError, ValueError) as exc:
            raise TrialLedgerError("trial failure is not canonical JSON") from exc
        if payload["failure_digest"] != failure_digest:
            _fail("trial failure digest disagrees")
        _digest(payload["outcome_digest"], field="outcome_digest")
        _digest(payload["evidence_digest"], field="evidence_digest")
        if payload["outcome_digest"] != _failed_outcome_digest(
            cell=cell,
            failure=failure,
        ):
            _fail("trial failed outcome digest disagrees")
        if payload["evidence_digest"] != _failed_evidence_digest(
            cell=cell,
            failure_digest=failure_digest,
            e1_authority_row_digest=authority_digest,
        ):
            _fail("trial failed evidence digest disagrees")
        return
    if row.kind == "cell_allocated":
        try:
            TrialOpaqueLabelBinding(
                cell=cell,
                opaque_label=payload["opaque_label"],
            )
        except (TypeError, ValueError) as exc:
            raise TrialLedgerError("trial allocation opaque label is invalid") from exc
        for field in (
            "effect_instance_digest",
            "e1_allocation_row_digest",
            "run_ref_step_config_digest",
            "result_contract_digest",
        ):
            _digest(payload[field], field=field)
        effect_root = _canonical_absolute(
            payload["effect_instance_root"],
            field="effect_instance_root",
        )
        _canonical_absolute(payload["run_ref_root"], field="run_ref_root")
        e1_path = _canonical_absolute(payload["e1_ledger_path"], field="e1_ledger_path")
        if e1_path != effect_root / "run-ref-attempts.jsonl":
            _fail("trial allocation E1 ledger path disagrees with effect root")
        return
    if row.kind == "cell_prepared":
        for field in (
            "e1_pending_row_digest",
            "settled_result_digest",
            "result_envelope_digest",
            "artifact_projection_digest",
            "evidence_manifest_digest",
        ):
            _digest(payload[field], field=field)
        try:
            settled = settled_result_binding_from_record(payload["settled_result"])
        except RunRefLedgerError as exc:
            raise TrialLedgerError("trial prepared settlement binding is invalid") from exc
        if (
            settled.attempt_ordinal != attempt
            or settled.pending_row_digest != payload["e1_pending_row_digest"]
            or canonical_sha256(settled.record) != payload["settled_result_digest"]
            or settled.evidence_manifest_digest != payload["evidence_manifest_digest"]
        ):
            _fail("trial prepared settlement binding disagrees")
        return
    digest_fields = {
        "cell_settled": (
            "prepared_trial_row_digest",
            "e1_pending_row_digest",
            "settled_result_digest",
            "outcome_digest",
            "evidence_digest",
        ),
        "cell_e1_committed": (
            "trial_settlement_row_digest",
            "e1_pending_row_digest",
            "e1_committed_row_digest",
        ),
        "cell_discarded": (
            "e1_incomplete_row_digest",
            "e1_discarded_row_digest",
            "disposition_digest",
        ),
    }[row.kind]
    for field in digest_fields:
        _digest(payload[field], field=field)
    if row.kind == "cell_discarded":
        next_attempt = _positive_integer(
            payload["next_attempt_ordinal"],
            field="trial next attempt ordinal",
        )
        if next_attempt != attempt + 1:
            _fail("trial discarded next attempt ordinal is invalid")


def _validate_lifecycle(
    rows: tuple[TrialLedgerRow, ...],
    *,
    path: Path,
) -> None:
    if not rows or rows[0].kind != "header":
        _fail("trial ledger requires exactly one leading header")
    if any(row.kind == "header" for row in rows[1:]):
        _fail("trial ledger contains a duplicate header")
    for row in rows:
        _validate_row_payload(row)
    domain = tuple(_cell(value) for value in rows[0].payload["cell_domain"])
    known = set(domain)
    expected_arm_ids = tuple(dict.fromkeys(cell.arm_id for cell in domain))
    arm_step_bindings = rows[0].payload["arm_run_ref_authorities"]
    if tuple(binding["arm_id"] for binding in arm_step_bindings) != expected_arm_ids:
        _fail("trial arm step-config bindings disagree with cell domain")
    request_digest = rows[0].payload["trial_request_digest"]
    opaque_labels = {
        _cell(binding["cell"]): binding["opaque_label"]
        for binding in rows[0].payload["sealed_opaque_label_map"]["bindings"]
    }
    arm_authorities = {
        binding["arm_id"]: binding
        for binding in arm_step_bindings
    }
    states: dict[TrialCellKey, dict[str, TrialLedgerRow]] = {}
    for row in rows[1:]:
        payload = row.payload
        cell = _cell(payload["cell"])
        if cell not in known:
            _fail("trial ledger row names an unknown cell")
        state = states.setdefault(cell, {})
        if row.kind == "cell_allocated":
            if "allocated" in state and "discarded" not in state:
                _fail("trial cell allocation is ambiguous")
            if "committed" in state or "settled" in state or "failed" in state:
                _fail("trial cell allocation follows a terminal settlement")
            expected_attempt = (
                state["discarded"].payload["next_attempt_ordinal"]
                if "discarded" in state
                else 1
            )
            expected_effect_digest = _effect_digest(request_digest, cell)
            expected_effect_root = _expected_effect_root_from_domain(
                path,
                domain,
                cell,
            )
            if (
                payload["attempt_ordinal"] != expected_attempt
                or payload["opaque_label"] != opaque_labels[cell]
                or payload["effect_instance_digest"] != expected_effect_digest
                or Path(payload["effect_instance_root"]) != expected_effect_root
                or Path(payload["e1_ledger_path"])
                != expected_effect_root / "run-ref-attempts.jsonl"
                or payload["run_ref_step_config_digest"]
                != arm_authorities[cell.arm_id]["run_ref_step_config_digest"]
                or payload["result_contract_digest"]
                != arm_authorities[cell.arm_id]["result_contract_digest"]
            ):
                _fail("trial cell allocation authority disagrees")
            state = {"allocated": row}
            states[cell] = state
        elif row.kind == "cell_prepared":
            if (
                "allocated" not in state
                or "prepared" in state
                or "discarded" in state
                or "failed" in state
            ):
                _fail("trial cell prepared transition is invalid")
            allocation = state["allocated"].payload
            settled = settled_result_binding_from_record(payload["settled_result"])
            if (
                payload["attempt_ordinal"] != allocation["attempt_ordinal"]
                or settled.run_ref_root.as_posix() != allocation["run_ref_root"]
                or settled.step_config_digest
                != allocation["run_ref_step_config_digest"]
                or settled.result_contract_digest
                != allocation["result_contract_digest"]
            ):
                _fail("trial cell prepared authority disagrees")
            expected_namespace = (
                settled.run_ref_root
                / "effect-instances"
                / allocation["effect_instance_digest"].removeprefix("sha256:")
            )
            try:
                relative = settled.workspace_path.relative_to(expected_namespace)
            except ValueError as exc:
                raise TrialLedgerError(
                    "trial cell prepared workspace carries cross-cell authority"
                ) from exc
            if relative == Path("."):
                _fail("trial cell prepared workspace is not a strict child")
            state["prepared"] = row
        elif row.kind == "cell_settled":
            if (
                "prepared" not in state
                or "settled" in state
                or "discarded" in state
                or "failed" in state
            ):
                _fail("trial cell settlement transition is invalid")
            prepared = state["prepared"]
            if (
                payload["attempt_ordinal"]
                != state["allocated"].payload["attempt_ordinal"]
                or payload["prepared_trial_row_digest"] != prepared.row_digest
                or payload["e1_pending_row_digest"]
                != prepared.payload["e1_pending_row_digest"]
                or payload["settled_result_digest"]
                != prepared.payload["settled_result_digest"]
            ):
                _fail("trial cell settlement authority disagrees")
            state["settled"] = row
        elif row.kind == "cell_e1_committed":
            if (
                "settled" not in state
                or "committed" in state
                or "discarded" in state
            ):
                _fail("trial cell E1 commit transition is invalid")
            settlement = state["settled"]
            if (
                payload["attempt_ordinal"]
                != state["allocated"].payload["attempt_ordinal"]
                or payload["trial_settlement_row_digest"] != settlement.row_digest
                or payload["e1_pending_row_digest"]
                != settlement.payload["e1_pending_row_digest"]
            ):
                _fail("trial cell E1 commit authority disagrees")
            state["committed"] = row
        elif row.kind == "cell_discarded":
            if (
                "allocated" not in state
                or "settled" in state
                or "discarded" in state
                or "failed" in state
            ):
                _fail("trial cell discard transition is invalid")
            if payload["attempt_ordinal"] != state["allocated"].payload[
                "attempt_ordinal"
            ]:
                _fail("trial cell discard authority disagrees")
            if "prepared" in state and payload["e1_incomplete_row_digest"] != state[
                "prepared"
            ].payload["e1_pending_row_digest"]:
                _fail("trial cell discard pending authority disagrees")
            state["discarded"] = row
        elif row.kind == "cell_failed":
            if "failed" in state or "settled" in state or "committed" in state:
                _fail("trial cell failure transition is invalid")
            attempt = payload["attempt_ordinal"]
            authority_digest = payload["e1_authority_row_digest"]
            if attempt is None:
                if "allocated" in state and "discarded" not in state:
                    _fail("trial unstarted failure follows an active allocation")
            else:
                if (
                    "allocated" not in state
                    or "prepared" in state
                    or "discarded" in state
                    or attempt != state["allocated"].payload["attempt_ordinal"]
                    or authority_digest is None
                ):
                    _fail("trial failed cell authority disagrees")
            state["failed"] = row


def _expected_effect_root_from_domain(
    path: Path,
    domain: tuple[TrialCellKey, ...],
    cell: TrialCellKey,
) -> Path:
    try:
        index = domain.index(cell) + 1
    except ValueError as exc:
        raise TrialLedgerError("trial ledger row names an unknown cell") from exc
    return path.parent / f"cell-{index:04d}" / "e1"


def load_trial_event_ledger(path: Path) -> TrialEventLedger:
    source = Path(path)
    try:
        identity = source.lstat()
        raw = source.read_bytes()
    except OSError as exc:
        raise TrialLedgerError("trial ledger is missing or unreadable") from exc
    if not stat.S_ISREG(identity.st_mode) or not raw or not raw.endswith(b"\n"):
        _fail("trial ledger is not a complete regular file")
    rows: list[TrialLedgerRow] = []
    previous: str | None = None
    for sequence, framed in enumerate(raw.splitlines(keepends=True), start=1):
        if not framed.endswith(b"\n") or framed == b"\n":
            _fail("trial ledger contains a truncated row")
        line = framed[:-1]
        try:
            value = json.loads(
                line.decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TrialLedgerError("trial ledger row is not strict JSON") from exc
        if canonical_json_bytes(value) != line:
            _fail("trial ledger row is not canonical JSON")
        row = _decode_row(value, sequence=sequence)
        if row.previous_row_digest != previous:
            _fail("trial ledger hash chain is discontinuous")
        if rows and row.recorded_at < rows[-1].recorded_at:
            _fail("trial ledger timestamps are not monotonic")
        rows.append(row)
        previous = row.row_digest
    result = TrialEventLedger(tuple(rows))
    _validate_lifecycle(result.rows, path=source)
    return result


def _persist(path: Path, rows: tuple[TrialLedgerRow, ...]) -> None:
    durable_atomic_write(
        path,
        b"".join(canonical_json_bytes(row.record) + b"\n" for row in rows),
    )


def _append(
    path: Path,
    *,
    expected_head_digest: str,
    kind: str,
    payload: Mapping[str, Any],
    recorded_at: str | None,
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    if ledger.rows[-1].row_digest != expected_head_digest:
        _fail("trial ledger concurrent head drift")
    row = _build_row(
        sequence=len(ledger.rows) + 1,
        previous_row_digest=expected_head_digest,
        kind=kind,
        recorded_at=recorded_at or _now(),
        payload=payload,
    )
    candidate = (*ledger.rows, row)
    _validate_lifecycle(candidate, path=Path(path))
    if load_trial_event_ledger(path) != ledger:
        _fail("trial ledger concurrent head drift")
    _persist(path, candidate)
    return row


def initialize_trial_event_ledger(
    *,
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
    cell_scopes: tuple[TrialCellEffectScope, ...],
    runtime_budget_window: TrialRuntimeBudgetWindow | None = None,
    recorded_at: str | None = None,
) -> InitializedTrialLedger:
    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("sealed labels must be exact SealedTrialOpaqueLabelMap")
    if not isinstance(cell_scopes, tuple) or any(
        type(scope) is not TrialCellEffectScope for scope in cell_scopes
    ):
        raise TypeError("cell scopes must be an exact tuple")
    if tuple(scope.cell for scope in cell_scopes) != request.cell_domain:
        _fail("trial cell scopes disagree with ordered domain")
    if tuple(binding.cell for binding in sealed_opaque_labels.bindings) != request.cell_domain:
        _fail("sealed labels disagree with ordered cell domain")
    window = runtime_budget_window or build_trial_runtime_budget_window(
        request,
        opened_at_unix_ns=0,
    )
    if type(window) is not TrialRuntimeBudgetWindow:
        raise TypeError("runtime budget window must be exact TrialRuntimeBudgetWindow")
    _validate_runtime_budget_window_for_request(window, request)
    roots = {scope.trial_root for scope in cell_scopes}
    if len(roots) != 1:
        _fail("trial cell scopes disagree on trial root")
    if len({scope.run_ref_root for scope in cell_scopes}) != 1:
        _fail("trial cell scopes disagree on shared run-ref root")
    expected_arm_steps = {
        binding["arm_id"]: binding["run_ref_step_config_digest"]
        for binding in request.arm_run_ref_authorities
    }
    expected_arm_results = {
        arm.arm_id: arm.run_ref.run_ref.result_digest
        for arm in request.step_config.arms
    }
    for index, scope in enumerate(cell_scopes, start=1):
        if (
            scope.cell_index != index
            or scope.effect_instance_digest
            != _effect_digest(request.digest, scope.cell)
            or scope.run_ref_step_config_digest
            != expected_arm_steps[scope.cell.arm_id]
            or scope.result_contract_digest
            != expected_arm_results[scope.cell.arm_id]
        ):
            _fail("trial cell scope authority disagrees with runtime request")
    path = next(iter(roots)) / _FILENAME
    if os.path.lexists(path):
        _fail("trial ledger already exists")
    payload = {
        "trial_static_config_digest": request.static_config_digest,
        "trial_step_config_digest": request.trial_step_config_digest,
        "arm_run_ref_authorities": [
            dict(binding)
            for binding in request.arm_run_ref_authorities
        ],
        "trial_request_digest": request.digest,
        "evaluation_digest": request.evaluation_digest,
        "budget_digest": request.budget_digest,
        "result_contract_digest": request.result_contract_digest,
        "compiler_runtime_identity_digest": request.compiler_runtime_identity_digest,
        "visit": request.visit.record,
        "cell_domain": [cell.record for cell in request.cell_domain],
        "cell_domain_digest": canonical_sha256(
            [cell.record for cell in request.cell_domain]
        ),
        "sealed_opaque_label_map": sealed_opaque_labels.record,
        "sealed_opaque_label_map_digest": sealed_opaque_labels.digest,
        "runtime_budget_window": window.record,
        "runtime_budget_window_digest": window.digest,
    }
    row = _build_row(
        sequence=1,
        previous_row_digest=None,
        kind="header",
        recorded_at=recorded_at or _now(),
        payload=payload,
    )
    _validate_lifecycle((row,), path=path)
    _persist(path, (row,))
    return InitializedTrialLedger(
        path=path,
        request=request,
        cell_scopes=cell_scopes,
        sealed_opaque_labels=sealed_opaque_labels,
        row=row,
    )


def _header_domain(ledger: TrialEventLedger) -> tuple[TrialCellKey, ...]:
    return tuple(_cell(value) for value in ledger.rows[0].payload["cell_domain"])


def _nonnegative_integer(value: object, *, field: str) -> int:
    if type(value) is not int or value < 0:
        _fail(f"{field} must be a non-negative integer")
    return value


def build_trial_runtime_budget_window(
    request: TrialRuntimeRequest,
    *,
    opened_at_unix_ns: int,
) -> TrialRuntimeBudgetWindow:
    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    opened = _nonnegative_integer(
        opened_at_unix_ns,
        field="trial runtime budget opened time",
    )
    budget = request.static_config.budget
    arm_deadline = opened + budget["arm_timeout_ms"] * 1_000_000
    return TrialRuntimeBudgetWindow(
        opened_at_unix_ns=opened,
        arm_deadlines=tuple(
            (arm.arm_id, arm_deadline) for arm in request.static_config.arms
        ),
        trial_deadline_unix_ns=(
            opened + budget["trial_timeout_ms"] * 1_000_000
        ),
    )


def _decode_runtime_budget_window(
    value: object,
    *,
    expected_digest: object,
) -> TrialRuntimeBudgetWindow:
    record = _closed(
        value,
        {
            "schema_version",
            "opened_at_unix_ns",
            "arm_deadlines",
            "trial_deadline_unix_ns",
        },
        field="trial runtime budget window",
    )
    if record["schema_version"] != "trial_runtime_budget_window.v1":
        _fail("trial runtime budget window schema is invalid")
    opened = _nonnegative_integer(
        record["opened_at_unix_ns"],
        field="trial runtime budget opened time",
    )
    deadline_rows = record["arm_deadlines"]
    if not isinstance(deadline_rows, list) or not deadline_rows:
        _fail("trial runtime arm deadlines are invalid")
    arm_deadlines: list[tuple[str, int]] = []
    for raw in deadline_rows:
        row = _closed(
            raw,
            {"arm_id", "deadline_unix_ns"},
            field="trial runtime arm deadline",
        )
        arm_id = row["arm_id"]
        if not isinstance(arm_id, str) or not arm_id:
            _fail("trial runtime arm deadline id is invalid")
        deadline = _nonnegative_integer(
            row["deadline_unix_ns"],
            field="trial runtime arm deadline",
        )
        if deadline < opened:
            _fail("trial runtime arm deadline precedes its opening")
        arm_deadlines.append((arm_id, deadline))
    if len({arm_id for arm_id, _deadline in arm_deadlines}) != len(arm_deadlines):
        _fail("trial runtime arm deadline domain is ambiguous")
    trial_deadline = _nonnegative_integer(
        record["trial_deadline_unix_ns"],
        field="trial runtime trial deadline",
    )
    if trial_deadline < opened:
        _fail("trial runtime trial deadline precedes its opening")
    window = TrialRuntimeBudgetWindow(
        opened_at_unix_ns=opened,
        arm_deadlines=tuple(arm_deadlines),
        trial_deadline_unix_ns=trial_deadline,
    )
    observed_digest = _digest(
        expected_digest,
        field="runtime_budget_window_digest",
    )
    if window.digest != observed_digest:
        _fail("trial runtime budget window digest disagrees")
    return window


def _validate_runtime_budget_window_for_request(
    window: TrialRuntimeBudgetWindow,
    request: TrialRuntimeRequest,
) -> None:
    expected = build_trial_runtime_budget_window(
        request,
        opened_at_unix_ns=window.opened_at_unix_ns,
    )
    if window != expected:
        _fail("trial runtime budget window disagrees with current runtime request")


def _validate_current_request_authority(
    ledger: TrialEventLedger,
    request: TrialRuntimeRequest,
) -> TrialRuntimeBudgetWindow:
    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    header = ledger.rows[0].payload
    expected_domain = [cell.record for cell in request.cell_domain]
    expected = {
        "trial_static_config_digest": request.static_config_digest,
        "trial_step_config_digest": request.trial_step_config_digest,
        "arm_run_ref_authorities": [
            dict(binding) for binding in request.arm_run_ref_authorities
        ],
        "trial_request_digest": request.digest,
        "evaluation_digest": request.evaluation_digest,
        "budget_digest": request.budget_digest,
        "result_contract_digest": request.result_contract_digest,
        "compiler_runtime_identity_digest": (
            request.compiler_runtime_identity_digest
        ),
        "visit": request.visit.record,
        "cell_domain": expected_domain,
        "cell_domain_digest": canonical_sha256(expected_domain),
    }
    if any(header[name] != value for name, value in expected.items()):
        _fail("trial ledger disagrees with current runtime request")
    window = _decode_runtime_budget_window(
        header["runtime_budget_window"],
        expected_digest=header["runtime_budget_window_digest"],
    )
    _validate_runtime_budget_window_for_request(window, request)
    return window


def validate_trial_event_ledger_authority(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
) -> TrialRuntimeBudgetWindow:
    """Validate the complete existing header before any resume-side mutation."""

    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("sealed labels must be exact SealedTrialOpaqueLabelMap")
    ledger = load_trial_event_ledger(path)
    window = _validate_current_request_authority(ledger, request)
    header = ledger.rows[0].payload
    if (
        header["sealed_opaque_label_map"] != sealed_opaque_labels.record
        or header["sealed_opaque_label_map_digest"]
        != sealed_opaque_labels.digest
    ):
        _fail("trial sealed opaque-label authority disagrees")
    return window


def _opaque_label(ledger: TrialEventLedger, cell: TrialCellKey) -> str:
    bindings = ledger.rows[0].payload["sealed_opaque_label_map"]["bindings"]
    matching = [row["opaque_label"] for row in bindings if _cell(row["cell"]) == cell]
    if len(matching) != 1:
        _fail("trial opaque-label binding is ambiguous")
    return matching[0]


def _effect_digest(request_digest: str, cell: TrialCellKey) -> str:
    return canonical_sha256(
        {
            "schema_version": "effect_instance_identity.v1",
            "owner_request_digest": request_digest,
            "ordinal_domain": "authored_arm_outer_rep_inner",
            "cell": cell.record,
        }
    )


def _expected_effect_root(path: Path, ledger: TrialEventLedger, cell: TrialCellKey) -> Path:
    domain = _header_domain(ledger)
    try:
        index = domain.index(cell) + 1
    except ValueError as exc:
        raise TrialLedgerError("trial ledger row names an unknown cell") from exc
    return path.parent / f"cell-{index:04d}" / "e1"


def _rows_for_cell(ledger: TrialEventLedger, cell: TrialCellKey) -> list[TrialLedgerRow]:
    return [
        row
        for row in ledger.rows[1:]
        if _cell(row.payload["cell"]) == cell
    ]


def _active_rows_for_cell(
    ledger: TrialEventLedger,
    cell: TrialCellKey,
) -> list[TrialLedgerRow]:
    rows = _rows_for_cell(ledger, cell)
    last_discard = max(
        (index for index, row in enumerate(rows) if row.kind == "cell_discarded"),
        default=-1,
    )
    return rows[last_discard + 1 :]


def append_trial_e1_boundary(
    path: Path,
    *,
    expected_head_digest: str,
    cell: TrialCellKey,
    event: RunRefLifecycleEvent,
    acknowledgement: RunRefLifecycleAcknowledgement,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    if cell not in _header_domain(ledger):
        _fail("trial boundary names an unknown cell")
    if type(event) is not RunRefLifecycleEvent or type(
        acknowledgement
    ) is not RunRefLifecycleAcknowledgement:
        raise TypeError("trial E1 boundary requires exact lifecycle authority")
    if acknowledgement.event_digest != event.event_digest:
        _fail("trial E1 boundary acknowledgement disagrees")
    authority = acknowledgement.authority
    if (
        authority.visit.record != ledger.rows[0].payload["visit"]
        or authority.stage != event.stage
        or authority.attempt_ordinal != event.attempt_ordinal
        or authority.row_digest != acknowledgement.authority_digest
    ):
        _fail("trial E1 boundary authority disagrees")
    expected_root = _expected_effect_root(Path(path), ledger, cell)
    if event.effect_instance_root != expected_root:
        _fail("trial E1 boundary carries cross-cell scope")
    e1_path = expected_root / "run-ref-attempts.jsonl"
    try:
        e1 = load_attempt_ledger(e1_path)
    except RunRefLedgerError as exc:
        raise TrialLedgerError("trial E1 ledger is missing or unreadable") from exc
    if not e1.rows or e1.rows[-1] != authority:
        _fail("trial E1 boundary authority is not the durable head")
    request_digest = ledger.rows[0].payload["trial_request_digest"]
    effect_digest = _effect_digest(request_digest, cell)
    if event.stage == "allocated":
        historical = _rows_for_cell(ledger, cell)
        active = _active_rows_for_cell(ledger, cell)
        if active:
            _fail("trial cell allocation is ambiguous")
        if historical:
            discarded = historical[-1]
            if (
                discarded.kind != "cell_discarded"
                or event.attempt_ordinal
                != discarded.payload["next_attempt_ordinal"]
                or authority.previous_row_digest
                != discarded.payload["e1_discarded_row_digest"]
            ):
                _fail("trial cell fresh allocation authority is invalid")
        bindings = authority.bindings
        expected_namespace = (
            bindings.run_ref_root
            / "effect-instances"
            / effect_digest.removeprefix("sha256:")
        )
        try:
            bindings.workspace_path.relative_to(expected_namespace)
        except ValueError as exc:
            raise TrialLedgerError("trial allocation workspace carries cross-cell scope") from exc
        payload = {
            "cell": cell.record,
            "opaque_label": _opaque_label(ledger, cell),
            "effect_instance_digest": effect_digest,
            "effect_instance_root": expected_root.as_posix(),
            "run_ref_root": bindings.run_ref_root.as_posix(),
            "e1_ledger_path": e1_path.as_posix(),
            "attempt_ordinal": authority.attempt_ordinal,
            "e1_allocation_row_digest": authority.row_digest,
            "run_ref_step_config_digest": bindings.step_config_digest,
            "result_contract_digest": bindings.result_contract_digest,
        }
        kind = "cell_allocated"
    elif event.stage == "completed_pending_parent_commit":
        matching = _active_rows_for_cell(ledger, cell)
        allocations = [row for row in matching if row.kind == "cell_allocated"]
        prepared = [row for row in matching if row.kind == "cell_prepared"]
        if len(allocations) != 1 or prepared:
            _fail("trial cell prepared boundary is ambiguous")
        allocation = allocations[0].payload
        if (
            allocation["attempt_ordinal"] != authority.attempt_ordinal
            or allocation["e1_ledger_path"] != e1_path.as_posix()
        ):
            _fail("trial prepared boundary carries cross-cell authority")
        settled = settled_result_binding(authority)
        payload = {
            "cell": cell.record,
            "attempt_ordinal": authority.attempt_ordinal,
            "e1_pending_row_digest": authority.row_digest,
            "settled_result": settled.record,
            "settled_result_digest": canonical_sha256(settled.record),
            "result_envelope_digest": event.payload["result_envelope_digest"],
            "artifact_projection_digest": event.payload[
                "artifact_projection_digest"
            ],
            "evidence_manifest_digest": event.payload[
                "evidence_manifest_digest"
            ],
        }
        kind = "cell_prepared"
    else:
        _fail("trial ledger persists only E1 allocation and prepared boundaries")
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind=kind,
        payload=payload,
        recorded_at=recorded_at,
    )


def append_trial_cell_settlement(
    path: Path,
    *,
    expected_head_digest: str,
    cell: TrialCellKey,
    settled_result: SettledRunRefResultBinding,
    outcome_digest: str,
    evidence_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    if type(settled_result) is not SettledRunRefResultBinding:
        raise TypeError("settled_result must be exact SettledRunRefResultBinding")
    _digest(outcome_digest, field="outcome_digest")
    _digest(evidence_digest, field="evidence_digest")
    rows = _active_rows_for_cell(ledger, cell)
    prepared = [row for row in rows if row.kind == "cell_prepared"]
    settled = [row for row in rows if row.kind == "cell_settled"]
    if not prepared and any(
        settled_result_binding_from_record(row.payload["settled_result"])
        == settled_result
        for row in ledger.rows[1:]
        if row.kind == "cell_prepared"
    ):
        _fail("trial cell settlement carries cross-cell authority")
    if len(prepared) != 1 or settled:
        _fail("trial cell settlement is missing or ambiguous")
    prepared_row = prepared[0]
    prepared_binding = settled_result_binding_from_record(
        prepared_row.payload["settled_result"]
    )
    if prepared_binding != settled_result:
        _fail("trial cell settlement carries cross-cell authority")
    payload = {
        "cell": cell.record,
        "attempt_ordinal": settled_result.attempt_ordinal,
        "prepared_trial_row_digest": prepared_row.row_digest,
        "e1_pending_row_digest": settled_result.pending_row_digest,
        "settled_result_digest": canonical_sha256(settled_result.record),
        "outcome_digest": outcome_digest,
        "evidence_digest": evidence_digest,
    }
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="cell_settled",
        payload=payload,
        recorded_at=recorded_at,
    )


def append_trial_cell_failure(
    path: Path,
    *,
    expected_head_digest: str,
    cell: TrialCellKey,
    failure: Mapping[str, Any],
    e1_authority: RunRefAttemptRecord | None = None,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Persist one terminal cell failure using only authority that exists.

    An active failed E1 attempt and its workspace deliberately remain intact as
    partial evidence.  The exact durable E1 head is bound here and the terminal
    trial row prevents that incident workspace from being relaunched or reused
    as a successful result.
    """

    ledger = load_trial_event_ledger(path)
    if cell not in _header_domain(ledger):
        _fail("trial failure names an unknown cell")
    failure_row = _closed(
        failure,
        {"code", "phase", "retryable", "secondary_causes"},
        field="trial failure",
    )
    if e1_authority is not None and type(e1_authority) is not RunRefAttemptRecord:
        raise TypeError("E1 authority must be exact RunRefAttemptRecord or None")
    if e1_authority is None:
        if failure_row["phase"] != "scheduling":
            _fail("trial unstarted failure phase is invalid")
    elif (
        e1_authority.status != "in_progress"
        or failure_row["phase"] != e1_authority.stage
    ):
        _fail("trial failure phase disagrees with active E1 authority")
    failure_digest = canonical_sha256(dict(failure_row))
    authority_digest = (
        None if e1_authority is None else e1_authority.row_digest
    )
    # Validate the closed value before any mutation.
    probe = _build_row(
        sequence=len(ledger.rows) + 1,
        previous_row_digest=expected_head_digest,
        kind="cell_failed",
        recorded_at=recorded_at or _now(),
        payload={
            "cell": cell.record,
            "attempt_ordinal": (
                None if e1_authority is None else e1_authority.attempt_ordinal
            ),
            "e1_authority_row_digest": (
                authority_digest
            ),
            "failure": dict(failure_row),
            "failure_digest": failure_digest,
            "outcome_digest": _failed_outcome_digest(
                cell=cell,
                failure=failure_row,
            ),
            "evidence_digest": _failed_evidence_digest(
                cell=cell,
                failure_digest=failure_digest,
                e1_authority_row_digest=authority_digest,
            ),
        },
    )
    active = _active_rows_for_cell(ledger, cell)
    if any(
        row.kind
        in {"cell_prepared", "cell_failed", "cell_settled", "cell_e1_committed"}
        for row in active
    ):
        _fail("trial cell failure follows a terminal outcome")
    allocations = [row for row in active if row.kind == "cell_allocated"]
    if e1_authority is None:
        if allocations:
            _fail("trial unstarted failure omits existing E1 authority")
    else:
        if len(allocations) != 1:
            _fail("trial failed cell E1 authority is missing or ambiguous")
        latest = _load_cell_e1_latest(ledger, allocations[0])
        if latest != e1_authority:
            _fail("trial failed cell E1 authority is not the durable head")
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="cell_failed",
        payload=probe.payload,
        recorded_at=probe.recorded_at,
    )


def append_trial_e1_committed(
    path: Path,
    *,
    expected_head_digest: str,
    cell: TrialCellKey,
    committed_authority: RunRefAttemptRecord,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    if type(committed_authority) is not RunRefAttemptRecord:
        raise TypeError("committed_authority must be exact RunRefAttemptRecord")
    rows = _active_rows_for_cell(ledger, cell)
    settlements = [row for row in rows if row.kind == "cell_settled"]
    commits = [row for row in rows if row.kind == "cell_e1_committed"]
    allocations = [row for row in rows if row.kind == "cell_allocated"]
    if len(settlements) != 1 or len(allocations) != 1 or commits:
        _fail("trial E1 commit is missing or ambiguous")
    settlement = settlements[0]
    pending_digest = settlement.payload["e1_pending_row_digest"]
    if (
        committed_authority.stage != "committed"
        or committed_authority.status != "committed"
        or committed_authority.attempt_ordinal != settlement.payload["attempt_ordinal"]
        or committed_authority.previous_row_digest != pending_digest
    ):
        _fail("trial E1 committed authority carries cross-cell binding")
    e1_path = Path(allocations[0].payload["e1_ledger_path"])
    try:
        e1 = load_attempt_ledger(e1_path)
    except RunRefLedgerError as exc:
        raise TrialLedgerError("trial E1 ledger is missing or unreadable") from exc
    if not e1.rows or e1.rows[-1] != committed_authority:
        _fail("trial E1 committed authority is not the durable head")
    payload = {
        "cell": cell.record,
        "attempt_ordinal": committed_authority.attempt_ordinal,
        "trial_settlement_row_digest": settlement.row_digest,
        "e1_pending_row_digest": pending_digest,
        "e1_committed_row_digest": committed_authority.row_digest,
    }
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="cell_e1_committed",
        payload=payload,
        recorded_at=recorded_at,
    )


def _load_cell_e1_latest(
    ledger: TrialEventLedger,
    allocation: TrialLedgerRow,
) -> RunRefAttemptRecord:
    payload = allocation.payload
    e1_path = Path(payload["e1_ledger_path"])
    try:
        e1 = load_attempt_ledger(e1_path)
    except RunRefLedgerError as exc:
        raise TrialLedgerError("trial E1 ledger is missing or unreadable") from exc
    if not e1.rows:
        _fail("trial E1 ledger is missing or unreadable")
    visit = _visit_from_header(ledger.rows[0].payload["visit"])
    if any(row.visit != visit for row in e1.rows):
        _fail("trial E1 ledger carries cross-cell visit authority")
    allocation_matches = [
        row
        for row in e1.rows
        if row.row_digest == payload["e1_allocation_row_digest"]
    ]
    if len(allocation_matches) != 1:
        _fail("trial E1 allocation authority is missing or ambiguous")
    e1_allocation = allocation_matches[0]
    if (
        e1_allocation.stage != "allocated"
        or e1_allocation.status != "in_progress"
        or e1_allocation.attempt_ordinal != payload["attempt_ordinal"]
        or e1_allocation.bindings.run_ref_root.as_posix() != payload["run_ref_root"]
        or e1_allocation.bindings.step_config_digest
        != payload["run_ref_step_config_digest"]
        or e1_allocation.bindings.result_contract_digest
        != payload["result_contract_digest"]
    ):
        _fail("trial E1 allocation authority disagrees")
    expected_namespace = (
        e1_allocation.bindings.run_ref_root
        / "effect-instances"
        / payload["effect_instance_digest"].removeprefix("sha256:")
    )
    try:
        relative = e1_allocation.bindings.workspace_path.relative_to(
            expected_namespace
        )
    except ValueError as exc:
        raise TrialLedgerError(
            "trial E1 allocation workspace carries cross-cell authority"
        ) from exc
    if relative == Path("."):
        _fail("trial E1 allocation workspace is not a strict child")
    latest = e1.rows[-1]
    if latest.attempt_ordinal != payload["attempt_ordinal"]:
        _fail("trial E1 attempt authority is ambiguous")
    return latest


def reconcile_orphan_trial_cell_allocation(
    path: Path,
    *,
    expected_head_digest: str,
    request: TrialRuntimeRequest,
    scope: TrialCellEffectScope,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Project the exact allocation persisted immediately before caller crash."""

    if type(scope) is not TrialCellEffectScope:
        raise TypeError("scope must be exact TrialCellEffectScope")
    ledger = load_trial_event_ledger(path)
    _validate_current_request_authority(ledger, request)
    if ledger.rows[-1].row_digest != expected_head_digest:
        _fail("trial ledger concurrent head drift")
    decision = classify_trial_cell_resume(
        path,
        request=request,
        cell=scope.cell,
    )
    if decision.action != "reconcile_orphan_e1_allocation":
        _fail("trial cell has no exact orphan E1 allocation")
    if scope.cell not in _header_domain(ledger):
        _fail("trial orphan allocation names an unknown cell")
    historical = _rows_for_cell(ledger, scope.cell)
    if historical and historical[-1].kind != "cell_discarded":
        _fail("trial orphan allocation is not adjacent to a fresh ordinal")
    expected_root = _expected_effect_root(Path(path), ledger, scope.cell)
    if scope.effect_instance_root != expected_root or scope.ledger_path != (
        expected_root / "run-ref-attempts.jsonl"
    ):
        _fail("trial orphan allocation scope disagrees")
    try:
        e1 = load_attempt_ledger(scope.ledger_path)
    except RunRefLedgerError as exc:
        raise TrialLedgerError("trial orphan E1 ledger is unreadable") from exc
    if any(row.visit != request.visit for row in e1.rows):
        _fail("trial orphan E1 ledger carries cross-cell visit authority")
    if historical:
        discarded = historical[-1]
        predecessor_digest = discarded.payload["e1_discarded_row_digest"]
        predecessors = [
            row for row in e1.rows if row.row_digest == predecessor_digest
        ]
        if len(predecessors) != 1:
            _fail("trial orphan E1 predecessor is missing or ambiguous")
        predecessor = predecessors[0]
        suffix = e1.rows[e1.rows.index(predecessor) + 1 :]
        expected_attempt = discarded.payload["next_attempt_ordinal"]
    else:
        predecessor = None
        suffix = e1.rows
        expected_attempt = 1
    if len(suffix) != 1:
        _fail("trial orphan E1 allocation is missing or ambiguous")
    authority = suffix[0]
    expected_namespace = (
        scope.run_ref_root
        / "effect-instances"
        / scope.effect_instance_digest.removeprefix("sha256:")
    )
    try:
        relative = authority.bindings.workspace_path.relative_to(expected_namespace)
    except ValueError as exc:
        raise TrialLedgerError(
            "trial orphan E1 allocation carries cross-cell scope"
        ) from exc
    if (
        authority.visit != request.visit
        or authority.previous_row_digest
        != (None if predecessor is None else predecessor.row_digest)
        or authority.attempt_ordinal != expected_attempt
        or authority.stage != "allocated"
        or authority.status != "in_progress"
        or authority.bindings.run_ref_root != scope.run_ref_root
        or authority.bindings.step_config_digest
        != scope.run_ref_step_config_digest
        or authority.bindings.result_contract_digest != scope.result_contract_digest
        or relative == Path(".")
    ):
        _fail("trial orphan E1 allocation authority disagrees")
    event = RunRefLifecycleEvent.build(
        sequence=1,
        event_kind="allocation",
        stage="allocated",
        visit=request.visit,
        attempt_ordinal=expected_attempt,
        effect_instance_root=scope.effect_instance_root,
        payload={"bindings": authority.bindings.record},
    )
    acknowledgement = acknowledge_persisted_run_ref_lifecycle_event(
        event,
        expected_row_digest=authority.row_digest,
    )
    return append_trial_e1_boundary(
        Path(path),
        expected_head_digest=expected_head_digest,
        cell=scope.cell,
        event=event,
        acknowledgement=acknowledgement,
        recorded_at=recorded_at,
    )


def _discard_disposition_record(
    *,
    cell: TrialCellKey,
    attempt_ordinal: int,
    incomplete_row_digest: str,
    workspace_path: Path,
) -> dict[str, object]:
    return {
        "schema_version": "trial_cell_incomplete_disposition.v1",
        "cell": cell.record,
        "attempt_ordinal": attempt_ordinal,
        "e1_incomplete_row_digest": incomplete_row_digest,
        "workspace_path": workspace_path.as_posix(),
        "disposition": "discard_incomplete_attempt_and_rerun_fresh",
    }


def _validate_discarded_e1_disposition(
    *,
    cell: TrialCellKey,
    discarded: RunRefAttemptRecord,
) -> tuple[str, str]:
    if (
        discarded.status != "discarded"
        or discarded.previous_row_digest is None
        or discarded.bindings.disposition_digest is None
    ):
        _fail("trial discarded E1 authority is invalid")
    workspace = discarded.bindings.workspace_path
    if os.path.lexists(workspace):
        _fail("trial discarded E1 workspace still exists")
    record = _discard_disposition_record(
        cell=cell,
        attempt_ordinal=discarded.attempt_ordinal,
        incomplete_row_digest=discarded.previous_row_digest,
        workspace_path=workspace,
    )
    digest = canonical_sha256(record)
    if digest != discarded.bindings.disposition_digest:
        _fail("trial discarded E1 disposition digest disagrees")
    disposition_path = workspace.parent / "disposition.json"
    try:
        identity = disposition_path.lstat()
        raw = disposition_path.read_bytes()
    except OSError as exc:
        raise TrialLedgerError(
            "trial discarded E1 disposition is missing or unreadable"
        ) from exc
    if (
        not stat.S_ISREG(identity.st_mode)
        or raw != canonical_json_bytes(record) + b"\n"
    ):
        _fail("trial discarded E1 disposition is invalid")
    return discarded.previous_row_digest, digest


def classify_trial_cell_resume(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    cell: TrialCellKey,
) -> TrialCellResumeDecision:
    ledger = load_trial_event_ledger(path)
    _validate_current_request_authority(ledger, request)
    if cell not in _header_domain(ledger):
        _fail("trial resume names an unknown cell")
    rows = _active_rows_for_cell(ledger, cell)
    allocations = [row for row in rows if row.kind == "cell_allocated"]
    failures = [row for row in rows if row.kind == "cell_failed"]
    if failures:
        if len(failures) != 1 or rows[-1] != failures[0]:
            _fail("trial failed cell authority is ambiguous")
        failure = failures[0]
        attempt = failure.payload["attempt_ordinal"]
        if attempt is not None:
            if len(allocations) != 1:
                _fail("trial failed cell allocation is missing or ambiguous")
            latest = _load_cell_e1_latest(ledger, allocations[0])
            if latest.row_digest != failure.payload["e1_authority_row_digest"]:
                _fail("trial failed cell E1 authority disagrees")
        return TrialCellResumeDecision(
            action="reuse_failed",
            cell=cell,
            attempt_ordinal=attempt or 0,
            next_attempt_ordinal=None,
            failure_row_digest=failure.row_digest,
        )
    if not rows:
        historical = _rows_for_cell(ledger, cell)
        if not historical:
            orphan_path = _expected_effect_root(Path(path), ledger, cell) / (
                "run-ref-attempts.jsonl"
            )
            try:
                orphan = load_attempt_ledger(orphan_path)
            except RunRefLedgerError as exc:
                raise TrialLedgerError("trial orphan E1 ledger is unreadable") from exc
            if orphan.rows:
                return TrialCellResumeDecision(
                    action="reconcile_orphan_e1_allocation",
                    cell=cell,
                    attempt_ordinal=orphan.rows[-1].attempt_ordinal,
                    next_attempt_ordinal=None,
                )
            return TrialCellResumeDecision(
                action="allocate_fresh",
                cell=cell,
                attempt_ordinal=0,
                next_attempt_ordinal=1,
            )
        if historical and historical[-1].kind == "cell_discarded":
            discarded = historical[-1]
            allocations = [
                row for row in historical[:-1] if row.kind == "cell_allocated"
            ]
            if not allocations:
                _fail("trial discarded cell lacks allocation authority")
            e1_path = Path(allocations[-1].payload["e1_ledger_path"])
            try:
                e1 = load_attempt_ledger(e1_path)
            except RunRefLedgerError as exc:
                raise TrialLedgerError("trial E1 ledger is missing or unreadable") from exc
            if not e1.rows:
                _fail("trial E1 ledger is missing or unreadable")
            visit = _visit_from_header(ledger.rows[0].payload["visit"])
            if any(row.visit != visit for row in e1.rows):
                _fail("trial E1 ledger carries cross-cell visit authority")
            matching_discarded = [
                row
                for row in e1.rows
                if row.row_digest == discarded.payload["e1_discarded_row_digest"]
            ]
            if len(matching_discarded) != 1:
                _fail("trial discarded cell authority disagrees")
            durable_discarded = matching_discarded[0]
            incomplete_digest, disposition_digest = (
                _validate_discarded_e1_disposition(
                    cell=cell,
                    discarded=durable_discarded,
                )
            )
            if (
                incomplete_digest
                != discarded.payload["e1_incomplete_row_digest"]
                or disposition_digest != discarded.payload["disposition_digest"]
                or durable_discarded.attempt_ordinal
                != discarded.payload["attempt_ordinal"]
            ):
                _fail("trial discarded cell authority disagrees")
            suffix = e1.rows[e1.rows.index(durable_discarded) + 1 :]
            if suffix:
                expected_attempt = discarded.payload["next_attempt_ordinal"]
                if (
                    len(suffix) != 1
                    or suffix[0].stage != "allocated"
                    or suffix[0].status != "in_progress"
                    or suffix[0].attempt_ordinal != expected_attempt
                    or suffix[0].previous_row_digest != durable_discarded.row_digest
                ):
                    _fail("trial orphan E1 allocation is ambiguous")
                return TrialCellResumeDecision(
                    action="reconcile_orphan_e1_allocation",
                    cell=cell,
                    attempt_ordinal=expected_attempt,
                    next_attempt_ordinal=None,
                )
            return TrialCellResumeDecision(
                action="allocate_fresh",
                cell=cell,
                attempt_ordinal=discarded.payload["attempt_ordinal"],
                next_attempt_ordinal=discarded.payload["next_attempt_ordinal"],
            )
    if len(allocations) != 1:
        _fail("trial cell allocation is missing or ambiguous")
    allocation = allocations[0]
    latest = _load_cell_e1_latest(ledger, allocation)
    attempt = allocation.payload["attempt_ordinal"]
    settlements = [row for row in rows if row.kind == "cell_settled"]
    commits = [row for row in rows if row.kind == "cell_e1_committed"]
    if not settlements:
        if commits:
            _fail("trial cell has a commit without settlement")
        if latest.status == "discarded":
            _validate_discarded_e1_disposition(cell=cell, discarded=latest)
            return TrialCellResumeDecision(
                action="reconcile_discarded_e1",
                cell=cell,
                attempt_ordinal=attempt,
                next_attempt_ordinal=attempt + 1,
            )
        if latest.status == "committed":
            _fail("trial incomplete authority is inconsistent")
        return TrialCellResumeDecision(
            action="discard_incomplete",
            cell=cell,
            attempt_ordinal=attempt,
            next_attempt_ordinal=attempt + 1,
        )
    if len(settlements) != 1:
        _fail("trial cell settlement is ambiguous")
    settlement = settlements[0]
    if not commits:
        if (
            latest.stage == "committed"
            and latest.status == "committed"
            and latest.previous_row_digest
            == settlement.payload["e1_pending_row_digest"]
        ):
            return TrialCellResumeDecision(
                action="reconcile_e1_committed",
                cell=cell,
                attempt_ordinal=attempt,
                next_attempt_ordinal=None,
                trial_settlement_row_digest=settlement.row_digest,
            )
        if (
            latest.stage != "completed_pending_parent_commit"
            or latest.row_digest != settlement.payload["e1_pending_row_digest"]
        ):
            _fail("trial pending E1 commit authority is invalid")
        return TrialCellResumeDecision(
            action="reconcile_pending_e1_commit",
            cell=cell,
            attempt_ordinal=attempt,
            next_attempt_ordinal=None,
            trial_settlement_row_digest=settlement.row_digest,
        )
    if len(commits) != 1:
        _fail("trial E1 commit authority is ambiguous")
    commit = commits[0]
    if (
        latest.stage != "committed"
        or latest.row_digest != commit.payload["e1_committed_row_digest"]
        or commit.payload["trial_settlement_row_digest"] != settlement.row_digest
    ):
        _fail("trial committed E1 authority is invalid")
    return TrialCellResumeDecision(
        action="reuse",
        cell=cell,
        attempt_ordinal=attempt,
        next_attempt_ordinal=None,
        trial_settlement_row_digest=settlement.row_digest,
    )


def discard_incomplete_trial_cell(
    path: Path,
    *,
    expected_head_digest: str,
    request: TrialRuntimeRequest,
    cell: TrialCellKey,
    current_step_config_digest: str,
    recorded_at: str | None = None,
) -> TrialCellDiscardDisposition:
    ledger = load_trial_event_ledger(path)
    if ledger.rows[-1].row_digest != expected_head_digest:
        _fail("trial ledger concurrent head drift")
    decision = classify_trial_cell_resume(path, request=request, cell=cell)
    allocation = [
        row
        for row in _active_rows_for_cell(ledger, cell)
        if row.kind == "cell_allocated"
    ][0]
    _digest(current_step_config_digest, field="current_step_config_digest")
    if current_step_config_digest != allocation.payload[
        "run_ref_step_config_digest"
    ]:
        _fail("trial current E1 step config disagrees")
    e1_path = Path(allocation.payload["e1_ledger_path"])
    if decision.action == "reconcile_discarded_e1":
        discarded = _load_cell_e1_latest(ledger, allocation)
        incomplete_row_digest, disposition_digest = (
            _validate_discarded_e1_disposition(
                cell=cell,
                discarded=discarded,
            )
        )
    elif decision.action == "discard_incomplete":
        try:
            incomplete = identify_incomplete_attempt(
                e1_path,
                visit=_visit_from_header(ledger.rows[0].payload["visit"]),
                current_step_config_digest=current_step_config_digest,
            )
        except RunRefLedgerError as exc:
            raise TrialLedgerError(
                "trial E1 incomplete authority is invalid"
            ) from exc
        if (
            incomplete is None
            or incomplete.attempt_ordinal != decision.attempt_ordinal
        ):
            _fail("trial E1 incomplete authority is missing or ambiguous")
        workspace = incomplete.bindings.workspace_path
        if os.path.lexists(workspace):
            identity = workspace.lstat()
            if not stat.S_ISDIR(identity.st_mode) or stat.S_ISLNK(identity.st_mode):
                _fail("trial incomplete workspace is not an exact directory")
            shutil.rmtree(workspace)
        if os.path.lexists(workspace):
            _fail("trial incomplete workspace discard failed")
        disposition_record = _discard_disposition_record(
            cell=cell,
            attempt_ordinal=incomplete.attempt_ordinal,
            incomplete_row_digest=incomplete.row_digest,
            workspace_path=workspace,
        )
        disposition_digest = canonical_sha256(disposition_record)
        disposition_path = workspace.parent / "disposition.json"
        durable_atomic_write(
            disposition_path,
            canonical_json_bytes(disposition_record) + b"\n",
        )
        try:
            discarded = record_discarded_attempt(
                e1_path,
                visit=incomplete.visit,
                attempt_ordinal=incomplete.attempt_ordinal,
                workspace_path=workspace,
                disposition_digest=disposition_digest,
                recorded_at=recorded_at,
            )
        except RunRefLedgerError as exc:
            raise TrialLedgerError(
                "trial E1 incomplete discard is invalid"
            ) from exc
        incomplete_row_digest = incomplete.row_digest
    else:
        _fail("trial cell is not eligible for incomplete discard")
    trial_row = _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="cell_discarded",
        payload={
            "cell": cell.record,
            "attempt_ordinal": discarded.attempt_ordinal,
            "e1_incomplete_row_digest": incomplete_row_digest,
            "e1_discarded_row_digest": discarded.row_digest,
            "disposition_digest": disposition_digest,
            "next_attempt_ordinal": discarded.attempt_ordinal + 1,
        },
        recorded_at=recorded_at,
    )
    return TrialCellDiscardDisposition(
        cell=cell,
        attempt_ordinal=discarded.attempt_ordinal,
        next_attempt_ordinal=discarded.attempt_ordinal + 1,
        disposition_digest=disposition_digest,
        trial_row_digest=trial_row.row_digest,
    )


def _visit_from_header(value: Mapping[str, Any]):
    from orchestrator.workflow.run_ref.ledger import RunRefVisitKey

    return RunRefVisitKey(
        parent_run_id=value["parent_run_id"],
        execution_frame_id=value["execution_frame_id"],
        call_frame_id=value["call_frame_id"],
        step_id=value["step_id"],
        visit_count=value["visit_count"],
    )


__all__ = [
    "TRIAL_EVENT_LEDGER_SCHEMA",
    "InitializedTrialLedger",
    "TrialCellDiscardDisposition",
    "TrialCellResumeDecision",
    "TrialEventLedger",
    "TrialLedgerError",
    "TrialLedgerRow",
    "TrialRuntimeBudgetWindow",
    "append_trial_cell_failure",
    "append_trial_cell_settlement",
    "append_trial_e1_boundary",
    "append_trial_e1_committed",
    "classify_trial_cell_resume",
    "build_trial_runtime_budget_window",
    "discard_incomplete_trial_cell",
    "initialize_trial_event_ledger",
    "load_trial_event_ledger",
    "reconcile_orphan_trial_cell_allocation",
    "validate_trial_event_ledger_authority",
]
