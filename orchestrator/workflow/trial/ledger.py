"""Canonical single-writer event ledger for target-2.25 trial effects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import binascii
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
from typing import Any, Literal

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.adjudication.ledger import load_score_ledger_rows
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
_ALLOCATION_STARTED_KEYS = {
    "cell",
    "attempt_ordinal",
    "e1_allocation_event_digest",
    "started_at_unix_ns",
    "started_monotonic_ns",
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
    "allocation_started_row_digest",
    "started_at_unix_ns",
    "started_monotonic_ns",
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
    "started_monotonic_ns",
    "terminal_monotonic_ns",
    "elapsed_ms",
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
    "reconciled_at_unix_ns",
    "elapsed_ms",
}
_EVIDENCE_FROZEN_KEYS = {
    "cell_evidence",
    "evidence_set_digest",
}
_CELL_CHECK_SETTLED_KEYS = {
    "cell",
    "evidence_frozen_row_digest",
    "terminal_row_digest",
    "check_id",
    "check_spec_digest",
    "check_result",
    "check_result_digest",
}
_FROZEN_CELL_EVIDENCE_KEYS = {
    "cell",
    "status",
    "terminal_row_digest",
    "outcome_digest",
    "evidence_digest",
    "e1_committed_row_digest",
}
_CHECKS_FROZEN_KEYS = {
    "cell_checks",
    "check_set_digest",
}
_FROZEN_CELL_CHECK_KEYS = {
    "cell",
    "check_result_digests",
}
_PACKETS_FROZEN_KEYS = {
    "cell_packets",
    "packet_set_digest",
}
_FROZEN_CELL_PACKET_KEYS = {
    "cell",
    "opaque_label",
    "packet_digest",
}
_SCORER_FROZEN_KEYS = {
    "scorer_identity_digest",
    "snapshot_digest",
}
_EVALUATOR_ATTEMPT_ALLOCATED_KEYS = {
    "opaque_label",
    "local_attempt",
    "global_attempt",
    "packet_digest",
    "scorer_frozen_row_digest",
    "started_at_unix_ns",
}
_EVALUATOR_ATTEMPT_SETTLED_KEYS = {
    "allocation_row_digest",
    "opaque_label",
    "local_attempt",
    "global_attempt",
    "status",
    "exit_code",
    "duration_ms",
    "token_usage",
    "cost",
    "stdout_digest",
    "stderr_digest",
    "output_digest",
    "score_row_content_digest",
}
_SCORE_SETTLED_KEYS = {
    "opaque_label",
    "score_row_content_digest",
    "terminal_attempt_settlement_row_digest",
}
_SCORES_FROZEN_KEYS = {
    "scores",
    "score_set_digest",
}
_AGGREGATION_FROZEN_KEYS = {
    "scores_frozen_row_digest",
    "sealed_opaque_label_map_digest",
    "final_outcomes_digest",
    "aggregation_input_digest",
}
_VERDICT_SETTLED_KEYS = {
    "aggregation_frozen_row_digest",
    "verdict_digest",
}
_VERDICT_PUBLISHED_KEYS = {
    "verdict_settled_row_digest",
    "verdict_artifact_digest",
    "verdict_artifact_relpath",
}
_TRIAL_PREPARED_KEYS = {
    "verdict_publication_row_digest",
    "result_contract_digest",
    "result_envelope_digest",
    "authored_outcomes_digest",
    "verdict_digest",
    "verdict_artifact_digest",
    "verdict_artifact_relpath",
    "budget_digest",
    "budget_accounting_digest",
}
_TRIAL_PARENT_COMMITTED_KEYS = {
    "trial_prepared_row_digest",
    "result_envelope_digest",
    "parent_state_settlement_digest",
}
_FROZEN_SCORE_KEYS = {
    "opaque_label",
    "score_settlement_row_digest",
    "score_row_content_digest",
}
_TRIAL_SCORE_ROW_KEYS = {
    "row_schema",
    "score_run_key",
    "row_content_digest",
    "trial_request_digest",
    "evaluation_digest",
    "evidence_frozen_digest",
    "evaluation_label",
    "evaluation_packet_digest",
    "scorer_identity_digest",
    "score_status",
    "score",
    "summary",
    "citations",
    "attempt_count",
    "charged_attempts",
    "failure",
}
_CHECK_RESULT_KEYS = {
    "check_id",
    "authority",
    "required",
    "status",
    "exit_code",
    "duration_ms",
    "output_digest",
    "output_bytes",
}
_PAYLOAD_KEYS_BY_KIND = {
    "header": _HEADER_KEYS,
    "cell_allocation_started": _ALLOCATION_STARTED_KEYS,
    "cell_allocated": _ALLOCATION_KEYS,
    "cell_prepared": _PREPARED_KEYS,
    "cell_settled": _SETTLEMENT_KEYS,
    "cell_failed": _FAILED_KEYS,
    "cell_e1_committed": _COMMITTED_KEYS,
    "cell_discarded": _DISCARDED_KEYS,
    "evidence_frozen": _EVIDENCE_FROZEN_KEYS,
    "check_settled": _CELL_CHECK_SETTLED_KEYS,
    "checks_frozen": _CHECKS_FROZEN_KEYS,
    "packets_frozen": _PACKETS_FROZEN_KEYS,
    "scorer_frozen": _SCORER_FROZEN_KEYS,
    "evaluator_attempt_allocated": _EVALUATOR_ATTEMPT_ALLOCATED_KEYS,
    "evaluator_attempt_settled": _EVALUATOR_ATTEMPT_SETTLED_KEYS,
    "score_settled": _SCORE_SETTLED_KEYS,
    "scores_frozen": _SCORES_FROZEN_KEYS,
    "aggregation_frozen": _AGGREGATION_FROZEN_KEYS,
    "verdict_settled": _VERDICT_SETTLED_KEYS,
    "verdict_published": _VERDICT_PUBLISHED_KEYS,
    "trial_prepared": _TRIAL_PREPARED_KEYS,
    "trial_parent_committed": _TRIAL_PARENT_COMMITTED_KEYS,
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


def _opaque_evaluation_label(value: object, *, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"opaque-[0-9a-f]{64}", value) is None:
        _fail(f"{field} is invalid")
    return value


def _trial_artifact_relpath(value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail("trial verdict artifact path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) < 3
        or path.parts[:2] != ("artifacts", "trials")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail("trial verdict artifact path is invalid")
    return value


def _attempt_token_usage(value: object) -> dict[str, Any]:
    if value == {"variant": "UNKNOWN"}:
        return {"variant": "UNKNOWN"}
    usage = _closed(
        value,
        {"variant", "prompt_tokens", "completion_tokens", "total_tokens"},
        field="trial evaluator attempt token usage",
    )
    if usage["variant"] != "KNOWN":
        _fail("trial evaluator attempt token usage is invalid")
    counts = tuple(
        usage[field]
        for field in ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    if any(type(count) is not int or count < 0 for count in counts):
        _fail("trial evaluator attempt token usage is invalid")
    return dict(usage)


def _attempt_cost(value: object) -> dict[str, Any]:
    if value == {"variant": "UNKNOWN"}:
        return {"variant": "UNKNOWN"}
    cost = _closed(
        value,
        {"variant", "amount", "currency"},
        field="trial evaluator attempt cost",
    )
    amount = cost["amount"]
    if (
        cost["variant"] != "KNOWN"
        or isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(float(amount))
        or float(amount) < 0.0
        or not isinstance(cost["currency"], str)
        or not cost["currency"]
    ):
        _fail("trial evaluator attempt cost is invalid")
    return dict(cost)


def _bounded_check_output(value: object) -> tuple[bytes, bytes, bool, bool, int, int]:
    if not isinstance(value, str):
        _fail("trial settled check output bytes are invalid")
    try:
        output = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, TrialLedgerError) as exc:
        raise TrialLedgerError("trial settled check output bytes are invalid") from exc
    output = _closed(
        output,
        {
            "schema_version",
            "stdout_base64",
            "stderr_base64",
            "stdout_truncated",
            "stderr_truncated",
            "stdout_size_bytes",
            "stderr_size_bytes",
        },
        field="trial settled check output bytes",
    )
    if (
        output["schema_version"] != "trial_check_output.v1"
        or canonical_json_bytes(dict(output)).decode("utf-8") != value
    ):
        _fail("trial settled check output bytes are invalid")
    decoded: list[bytes] = []
    for name in ("stdout", "stderr"):
        encoded = output[f"{name}_base64"]
        if not isinstance(encoded, str):
            _fail("trial settled check output bytes are invalid")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TrialLedgerError(
                "trial settled check output bytes are invalid"
            ) from exc
        if base64.b64encode(raw).decode("ascii") != encoded:
            _fail("trial settled check output bytes are invalid")
        decoded.append(raw)
        truncated = output[f"{name}_truncated"]
        size = output[f"{name}_size_bytes"]
        if (
            type(truncated) is not bool
            or type(size) is not int
            or size < len(raw)
            or truncated is not (size > len(raw))
        ):
            _fail("trial settled check output bytes are invalid")
    return (
        decoded[0],
        decoded[1],
        output["stdout_truncated"],
        output["stderr_truncated"],
        output["stdout_size_bytes"],
        output["stderr_size_bytes"],
    )


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
class TrialEvaluatorAttemptReplay:
    """Durable evaluator launches, including crash-visible active attempts."""

    allocations: tuple[TrialLedgerRow, ...]
    settlements: tuple[TrialLedgerRow, ...]
    active_allocations: tuple[TrialLedgerRow, ...]

    @property
    def charged_attempt_count(self) -> int:
        return len(self.allocations)


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
    if row.kind == "evidence_frozen":
        cell_evidence = payload["cell_evidence"]
        if not isinstance(cell_evidence, list) or not cell_evidence:
            _fail("trial frozen evidence set must be a non-empty ordered list")
        cells: list[TrialCellKey] = []
        for value in cell_evidence:
            evidence = _closed(
                value,
                _FROZEN_CELL_EVIDENCE_KEYS,
                field="trial frozen cell evidence",
            )
            cells.append(_cell(evidence["cell"]))
            if evidence["status"] not in {"completed", "failed"}:
                _fail("trial frozen cell evidence status is invalid")
            for field in (
                "terminal_row_digest",
                "outcome_digest",
                "evidence_digest",
            ):
                _digest(evidence[field], field=field)
            committed = _digest(
                evidence["e1_committed_row_digest"],
                field="e1_committed_row_digest",
                optional=True,
            )
            if (evidence["status"] == "completed") != (committed is not None):
                _fail("trial frozen cell E1 commit authority is incomplete")
        if len(set(cells)) != len(cells):
            _fail("trial frozen evidence cell domain is ambiguous")
        _digest(payload["evidence_set_digest"], field="evidence_set_digest")
        if canonical_sha256(cell_evidence) != payload["evidence_set_digest"]:
            _fail("trial frozen evidence-set digest disagrees")
        return
    if row.kind == "check_settled":
        _cell(payload["cell"])
        _digest(
            payload["evidence_frozen_row_digest"],
            field="evidence_frozen_row_digest",
        )
        _digest(payload["terminal_row_digest"], field="terminal_row_digest")
        check_id = payload["check_id"]
        if not isinstance(check_id, str) or not check_id:
            _fail("trial settled check identity is invalid")
        check_spec_digest = _digest(
            payload["check_spec_digest"],
            field="check_spec_digest",
        )
        result = _closed(
            payload["check_result"],
            _CHECK_RESULT_KEYS,
            field="trial settled check result",
        )
        if result["check_id"] != check_id:
            _fail("trial settled check result identity disagrees")
        if result["authority"] not in {"correctness", "invariant"}:
            _fail("trial settled check authority is invalid")
        if type(result["required"]) is not bool:
            _fail("trial settled check required flag is invalid")
        if result["status"] not in {"COMPLETED", "TIMED_OUT", "LAUNCH_FAILED"}:
            _fail("trial settled check status is invalid")
        exit_code = result["exit_code"]
        if result["status"] == "COMPLETED":
            if type(exit_code) is not int:
                _fail("completed trial check requires an integer exit code")
        elif exit_code is not None:
            _fail("non-completed trial check cannot carry an exit code")
        if type(result["duration_ms"]) is not int or result["duration_ms"] < 0:
            _fail("trial settled check duration is invalid")
        _digest(result["output_digest"], field="trial settled check output digest")
        bounded_output = _bounded_check_output(result["output_bytes"])
        if not bounded_output[2] and not bounded_output[3]:
            identity = {
                "schema_version": "trial_check_output_identity.v1",
                "stdout_digest": "sha256:"
                + hashlib.sha256(bounded_output[0]).hexdigest(),
                "stdout_size_bytes": bounded_output[4],
                "stderr_digest": "sha256:"
                + hashlib.sha256(bounded_output[1]).hexdigest(),
                "stderr_size_bytes": bounded_output[5],
            }
            if result["output_digest"] != canonical_sha256(identity):
                _fail("trial settled check output digest disagrees")
        result_digest = _digest(
            payload["check_result_digest"],
            field="check_result_digest",
        )
        if result_digest != canonical_sha256(
            {
                "schema_version": "trial_check_result.v1",
                "evidence_frozen_digest": payload["evidence_frozen_row_digest"],
                "check_spec_digest": check_spec_digest,
                "result": dict(result),
            }
        ):
            _fail("trial settled check result digest disagrees")
        return
    if row.kind == "checks_frozen":
        cell_checks = payload["cell_checks"]
        if not isinstance(cell_checks, list) or not cell_checks:
            _fail("trial frozen check set must be a non-empty ordered list")
        cells: list[TrialCellKey] = []
        for value in cell_checks:
            check_record = _closed(
                value,
                _FROZEN_CELL_CHECK_KEYS,
                field="trial frozen cell checks",
            )
            cells.append(_cell(check_record["cell"]))
            digests = check_record["check_result_digests"]
            if not isinstance(digests, list):
                _fail("trial frozen check-result digests must be an ordered list")
            for digest in digests:
                _digest(digest, field="check_result_digest")
        if len(set(cells)) != len(cells):
            _fail("trial frozen check cell domain is ambiguous")
        _digest(payload["check_set_digest"], field="check_set_digest")
        if canonical_sha256(cell_checks) != payload["check_set_digest"]:
            _fail("trial frozen check-set digest disagrees")
        return
    if row.kind == "packets_frozen":
        cell_packets = payload["cell_packets"]
        if not isinstance(cell_packets, list) or not cell_packets:
            _fail("trial frozen packet set must be a non-empty ordered list")
        cells: list[TrialCellKey] = []
        labels: list[str] = []
        for value in cell_packets:
            packet_record = _closed(
                value,
                _FROZEN_CELL_PACKET_KEYS,
                field="trial frozen cell packet",
            )
            cell = _cell(packet_record["cell"])
            try:
                binding = TrialOpaqueLabelBinding(
                    cell=cell,
                    opaque_label=packet_record["opaque_label"],
                )
            except (TypeError, ValueError) as exc:
                raise TrialLedgerError(
                    "trial frozen packet opaque label is invalid"
                ) from exc
            cells.append(cell)
            labels.append(binding.opaque_label)
            _digest(packet_record["packet_digest"], field="packet_digest")
        if len(set(cells)) != len(cells) or len(set(labels)) != len(labels):
            _fail("trial frozen packet domain is ambiguous")
        _digest(payload["packet_set_digest"], field="packet_set_digest")
        if canonical_sha256(cell_packets) != payload["packet_set_digest"]:
            _fail("trial frozen packet-set digest disagrees")
        return
    if row.kind == "scorer_frozen":
        _digest(payload["scorer_identity_digest"], field="scorer_identity_digest")
        _digest(payload["snapshot_digest"], field="snapshot_digest")
        return
    if row.kind == "evaluator_attempt_allocated":
        _opaque_evaluation_label(
            payload["opaque_label"],
            field="trial evaluator attempt opaque label",
        )
        _positive_integer(
            payload["local_attempt"],
            field="trial evaluator local attempt",
        )
        _positive_integer(
            payload["global_attempt"],
            field="trial evaluator global attempt",
        )
        _nonnegative_integer(
            payload["started_at_unix_ns"],
            field="trial evaluator allocation wall-clock start",
        )
        for field in (
            "packet_digest",
            "scorer_frozen_row_digest",
        ):
            _digest(payload[field], field=field)
        return
    if row.kind == "evaluator_attempt_settled":
        _digest(payload["allocation_row_digest"], field="allocation_row_digest")
        _opaque_evaluation_label(
            payload["opaque_label"],
            field="trial evaluator attempt opaque label",
        )
        _positive_integer(
            payload["local_attempt"],
            field="trial evaluator local attempt",
        )
        _positive_integer(
            payload["global_attempt"],
            field="trial evaluator global attempt",
        )
        status = payload["status"]
        if status not in {
            "preparation_failed",
            "provider_failed",
            "output_invalid",
            "scored",
        }:
            _fail("trial evaluator attempt status is invalid")
        if payload["exit_code"] is not None and type(payload["exit_code"]) is not int:
            _fail("trial evaluator attempt exit code is invalid")
        if type(payload["duration_ms"]) is not int or payload["duration_ms"] < 0:
            _fail("trial evaluator attempt duration is invalid")
        _attempt_token_usage(payload["token_usage"])
        _attempt_cost(payload["cost"])
        for field in (
            "stdout_digest",
            "stderr_digest",
            "output_digest",
            "score_row_content_digest",
        ):
            _digest(payload[field], field=field, optional=True)
        if status == "scored" and (
            payload["output_digest"] is None
            or payload["score_row_content_digest"] is None
        ):
            _fail("scored trial evaluator attempt lacks output or score authority")
        return
    if row.kind == "score_settled":
        _opaque_evaluation_label(
            payload["opaque_label"],
            field="trial score settlement opaque label",
        )
        _digest(
            payload["score_row_content_digest"],
            field="score_row_content_digest",
        )
        _digest(
            payload["terminal_attempt_settlement_row_digest"],
            field="terminal_attempt_settlement_row_digest",
            optional=True,
        )
        return
    if row.kind == "scores_frozen":
        scores = payload["scores"]
        if not isinstance(scores, list) or not scores:
            _fail("trial frozen score set must be a non-empty ordered list")
        labels: list[str] = []
        for value in scores:
            score = _closed(
                value,
                _FROZEN_SCORE_KEYS,
                field="trial frozen score",
            )
            labels.append(
                _opaque_evaluation_label(
                    score["opaque_label"],
                    field="trial frozen score opaque label",
                )
            )
            _digest(
                score["score_settlement_row_digest"],
                field="score_settlement_row_digest",
            )
            _digest(
                score["score_row_content_digest"],
                field="score_row_content_digest",
            )
        if len(set(labels)) != len(labels):
            _fail("trial frozen score domain is ambiguous")
        _digest(payload["score_set_digest"], field="score_set_digest")
        if canonical_sha256(scores) != payload["score_set_digest"]:
            _fail("trial frozen score-set digest disagrees")
        return
    if row.kind == "aggregation_frozen":
        for field in (
            "scores_frozen_row_digest",
            "sealed_opaque_label_map_digest",
            "final_outcomes_digest",
            "aggregation_input_digest",
        ):
            _digest(payload[field], field=field)
        return
    if row.kind == "verdict_settled":
        _digest(
            payload["aggregation_frozen_row_digest"],
            field="aggregation_frozen_row_digest",
        )
        _digest(payload["verdict_digest"], field="verdict_digest")
        return
    if row.kind == "verdict_published":
        _digest(
            payload["verdict_settled_row_digest"],
            field="verdict_settled_row_digest",
        )
        _digest(
            payload["verdict_artifact_digest"],
            field="verdict_artifact_digest",
        )
        _trial_artifact_relpath(payload["verdict_artifact_relpath"])
        return
    if row.kind == "trial_prepared":
        for field in (
            "verdict_publication_row_digest",
            "result_contract_digest",
            "result_envelope_digest",
            "authored_outcomes_digest",
            "verdict_digest",
            "verdict_artifact_digest",
            "budget_digest",
            "budget_accounting_digest",
        ):
            _digest(payload[field], field=field)
        artifact_relpath = _trial_artifact_relpath(
            payload["verdict_artifact_relpath"]
        )
        if not artifact_relpath:
            _fail("trial prepared result artifact path is invalid")
        return
    if row.kind == "trial_parent_committed":
        for field in (
            "trial_prepared_row_digest",
            "result_envelope_digest",
            "parent_state_settlement_digest",
        ):
            _digest(payload[field], field=field)
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
    if row.kind == "cell_allocation_started":
        _digest(
            payload["e1_allocation_event_digest"],
            field="trial E1 allocation event digest",
        )
        _nonnegative_integer(
            payload["started_at_unix_ns"],
            field="trial allocation wall-clock start",
        )
        _nonnegative_integer(
            payload["started_monotonic_ns"],
            field="trial allocation monotonic start",
        )
        return
    if row.kind == "cell_failed":
        authority_digest = _digest(
            payload["e1_authority_row_digest"],
            field="e1_authority_row_digest",
            optional=True,
        )
        if (attempt is None) != (authority_digest is None):
            _fail("trial failed cell attempt authority is incomplete")
        elapsed_ms = _nonnegative_integer(
            payload["elapsed_ms"],
            field="trial failed cell elapsed_ms",
        )
        started_monotonic_ns = payload["started_monotonic_ns"]
        terminal_monotonic_ns = payload["terminal_monotonic_ns"]
        if attempt is None:
            if (
                started_monotonic_ns is not None
                or terminal_monotonic_ns is not None
                or elapsed_ms != 0
            ):
                _fail("trial unstarted failure timing is invalid")
        else:
            started = _nonnegative_integer(
                started_monotonic_ns,
                field="trial failed cell monotonic start",
            )
            terminal = _nonnegative_integer(
                terminal_monotonic_ns,
                field="trial failed cell monotonic terminal",
            )
            if terminal < started:
                _fail("trial failed cell monotonic clock moved backwards")
            if elapsed_ms != (terminal - started) // 1_000_000:
                _fail("trial failed cell elapsed timing disagrees")
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
        _digest(
            payload["allocation_started_row_digest"],
            field="trial allocation-start row digest",
        )
        _nonnegative_integer(
            payload["started_at_unix_ns"],
            field="trial allocation wall-clock start",
        )
        _nonnegative_integer(
            payload["started_monotonic_ns"],
            field="trial allocation monotonic start",
        )
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
        _nonnegative_integer(
            payload["reconciled_at_unix_ns"],
            field="trial discard reconciliation wall time",
        )
        _nonnegative_integer(
            payload["elapsed_ms"],
            field="trial discarded cell elapsed_ms",
        )
        next_attempt = _positive_integer(
            payload["next_attempt_ordinal"],
            field="trial next attempt ordinal",
        )
        if next_attempt != attempt + 1:
            _fail("trial discarded next attempt ordinal is invalid")


def _validate_structural_check_order(
    rows: list[TrialLedgerRow],
    *,
    completed_domain: tuple[TrialCellKey, ...],
) -> None:
    """Validate the generic authority/check/cell ordering visible in the ledger."""

    if not rows:
        return
    if not completed_domain:
        _fail("trial settled check names a failed-only cell domain")
    groups: list[list[TrialLedgerRow]] = []
    for row in rows:
        if not groups or groups[-1][0].payload["check_id"] != row.payload["check_id"]:
            groups.append([row])
        else:
            groups[-1].append(row)
    seen_check_ids: set[str] = set()
    previous_authority = -1
    authority_order = {"correctness": 0, "invariant": 1}
    for index, group in enumerate(groups):
        first = group[0].payload
        check_id = first["check_id"]
        if check_id in seen_check_ids:
            _fail("trial settled check order repeats an earlier check")
        seen_check_ids.add(check_id)
        authority = first["check_result"]["authority"]
        authority_index = authority_order[authority]
        if authority_index < previous_authority:
            _fail("trial settled checks violate authority order")
        previous_authority = authority_index
        cells = tuple(_cell(row.payload["cell"]) for row in group)
        expected_cells = (
            completed_domain
            if index < len(groups) - 1
            else completed_domain[: len(cells)]
        )
        if cells != expected_cells:
            _fail("trial settled checks violate authored cell order")
        spec_digests = {row.payload["check_spec_digest"] for row in group}
        result_contracts = {
            (
                row.payload["check_result"]["authority"],
                row.payload["check_result"]["required"],
            )
            for row in group
        }
        if len(spec_digests) != 1 or len(result_contracts) != 1:
            _fail("trial settled check authority is substituted within a check")


def _derived_frozen_cell_checks(
    domain: tuple[TrialCellKey, ...],
    rows: list[TrialLedgerRow],
) -> list[dict[str, Any]]:
    return [
        {
            "cell": cell.record,
            "check_result_digests": [
                row.payload["check_result_digest"]
                for row in rows
                if _cell(row.payload["cell"]) == cell
            ],
        }
        for cell in domain
    ]


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
    freeze_row: TrialLedgerRow | None = None
    check_settlement_rows: list[TrialLedgerRow] = []
    checks_row: TrialLedgerRow | None = None
    packets_row: TrialLedgerRow | None = None
    scorer_row: TrialLedgerRow | None = None
    scores_row: TrialLedgerRow | None = None
    aggregation_row: TrialLedgerRow | None = None
    verdict_settlement_row: TrialLedgerRow | None = None
    verdict_publication_row: TrialLedgerRow | None = None
    trial_prepared_row: TrialLedgerRow | None = None
    trial_parent_committed_row: TrialLedgerRow | None = None
    evaluator_allocations: dict[str, TrialLedgerRow] = {}
    evaluator_settlements: dict[str, TrialLedgerRow] = {}
    score_settlements: dict[str, TrialLedgerRow] = {}
    for row in rows[1:]:
        payload = row.payload
        if trial_parent_committed_row is not None:
            _fail("trial event follows terminal parent settlement")
        if trial_prepared_row is not None and row.kind != "trial_parent_committed":
            _fail("trial parent commit must immediately follow preparation")
        if (
            verdict_publication_row is not None
            and trial_prepared_row is None
            and row.kind != "trial_prepared"
        ):
            _fail("trial event follows terminal verdict publication")
        if (
            verdict_settlement_row is not None
            and verdict_publication_row is None
            and row.kind != "verdict_published"
        ):
            _fail("trial verdict publication must immediately follow settlement")
        if (
            aggregation_row is not None
            and verdict_settlement_row is None
            and row.kind != "verdict_settled"
        ):
            _fail("trial verdict settlement must immediately follow aggregation freeze")
        if (
            scores_row is not None
            and aggregation_row is None
            and row.kind != "aggregation_frozen"
        ):
            _fail("trial aggregation freeze must immediately follow score freeze")
        if row.kind == "evidence_frozen":
            if freeze_row is not None:
                _fail("trial evidence is already frozen")
            if set(states) != known:
                _fail("trial evidence freeze precedes the complete cell domain")
            expected_evidence: list[dict[str, Any]] = []
            for cell in domain:
                state = states[cell]
                if "failed" in state:
                    terminal = state["failed"]
                    expected_evidence.append(
                        {
                            "cell": cell.record,
                            "status": "failed",
                            "terminal_row_digest": terminal.row_digest,
                            "outcome_digest": terminal.payload["outcome_digest"],
                            "evidence_digest": terminal.payload["evidence_digest"],
                            "e1_committed_row_digest": None,
                        }
                    )
                elif "settled" in state and "committed" in state:
                    settled = state["settled"]
                    committed = state["committed"]
                    expected_evidence.append(
                        {
                            "cell": cell.record,
                            "status": "completed",
                            "terminal_row_digest": committed.row_digest,
                            "outcome_digest": settled.payload["outcome_digest"],
                            "evidence_digest": settled.payload["evidence_digest"],
                            "e1_committed_row_digest": committed.payload[
                                "e1_committed_row_digest"
                            ],
                        }
                    )
                else:
                    _fail("trial evidence freeze precedes a terminal cell")
            if payload["cell_evidence"] != expected_evidence:
                _fail("trial frozen evidence set disagrees with terminal authority")
            freeze_row = row
            continue
        if row.kind == "check_settled":
            if freeze_row is None:
                _fail("trial check settlement precedes the evidence freeze")
            if checks_row is not None:
                _fail("trial check settlement follows the checks freeze")
            if payload["evidence_frozen_row_digest"] != freeze_row.row_digest:
                _fail("trial check settlement evidence-freeze authority disagrees")
            cell = _cell(payload["cell"])
            evidence_by_cell = {
                _cell(value["cell"]): value
                for value in freeze_row.payload["cell_evidence"]
            }
            if cell not in evidence_by_cell:
                _fail("trial check settlement names an unknown cell")
            evidence = evidence_by_cell[cell]
            if evidence["status"] != "completed":
                _fail("trial check settlement names a failed cell")
            if payload["terminal_row_digest"] != evidence["terminal_row_digest"]:
                _fail("trial check settlement terminal authority disagrees")
            check_settlement_rows.append(row)
            completed_domain = tuple(
                _cell(value["cell"])
                for value in freeze_row.payload["cell_evidence"]
                if value["status"] == "completed"
            )
            _validate_structural_check_order(
                check_settlement_rows,
                completed_domain=completed_domain,
            )
            continue
        if row.kind == "checks_frozen":
            if freeze_row is None:
                _fail("trial checks freeze precedes the evidence freeze")
            if checks_row is not None:
                _fail("trial checks are already frozen")
            if packets_row is not None:
                _fail("trial checks freeze follows the packet freeze")
            check_cells = tuple(
                _cell(value["cell"]) for value in payload["cell_checks"]
            )
            if check_cells != domain:
                _fail("trial checks freeze disagrees with header cell order")
            expected_cell_checks = _derived_frozen_cell_checks(
                domain,
                check_settlement_rows,
            )
            if payload["cell_checks"] != expected_cell_checks:
                _fail("trial checks freeze disagrees with settled check authority")
            checks_row = row
            continue
        if row.kind == "packets_frozen":
            if freeze_row is None:
                _fail("trial packet freeze precedes the evidence freeze")
            if checks_row is None:
                _fail("trial packet freeze precedes the checks freeze")
            if packets_row is not None:
                _fail("trial packets are already frozen")
            packet_cells = tuple(
                _cell(value["cell"]) for value in payload["cell_packets"]
            )
            if packet_cells != domain:
                _fail("trial packet freeze disagrees with header cell order")
            for cell, value in zip(domain, payload["cell_packets"], strict=True):
                if value["opaque_label"] != opaque_labels[cell]:
                    _fail("trial packet freeze disagrees with header opaque label")
            packets_row = row
            continue
        if row.kind == "scorer_frozen":
            if packets_row is None:
                _fail("trial scorer freeze precedes the packet freeze")
            if scorer_row is not None:
                _fail("trial scorer is already frozen")
            if row.previous_row_digest != packets_row.row_digest:
                _fail("trial scorer freeze does not immediately follow packets")
            scorer_row = row
            continue
        if row.kind == "evaluator_attempt_allocated":
            if scorer_row is None:
                _fail("trial evaluator allocation precedes the scorer freeze")
            if scores_row is not None:
                _fail("trial evaluator allocation follows the score freeze")
            packet_by_label = {
                value["opaque_label"]: value
                for value in packets_row.payload["cell_packets"]
            }
            label = payload["opaque_label"]
            if label not in packet_by_label:
                _fail("trial evaluator allocation names an unknown packet domain")
            if label in score_settlements:
                _fail("trial evaluator allocation follows a settled score")
            if payload["packet_digest"] != packet_by_label[label]["packet_digest"]:
                _fail("trial evaluator allocation packet digest disagrees")
            if payload["scorer_frozen_row_digest"] != scorer_row.row_digest:
                _fail("trial evaluator allocation scorer authority disagrees")
            label_allocations = [
                allocation
                for allocation in evaluator_allocations.values()
                if allocation.payload["opaque_label"] == label
            ]
            if any(
                allocation.row_digest not in evaluator_settlements
                for allocation in label_allocations
            ):
                _fail("trial evaluator allocation follows an active evaluator attempt")
            if any(
                settlement.payload["score_row_content_digest"] is not None
                and settlement.payload["opaque_label"] == label
                for settlement in evaluator_settlements.values()
            ):
                _fail("trial evaluator allocation follows a closed score row")
            expected_local = len(label_allocations) + 1
            expected_global = len(evaluator_allocations) + 1
            if payload["local_attempt"] != expected_local:
                _fail("trial evaluator local attempt is not contiguous")
            if payload["global_attempt"] != expected_global:
                _fail("trial evaluator global attempt is not contiguous")
            evaluator_allocations[row.row_digest] = row
            continue
        if row.kind == "evaluator_attempt_settled":
            if scorer_row is None:
                _fail("trial evaluator settlement precedes the scorer freeze")
            if scores_row is not None:
                _fail("trial evaluator settlement follows the score freeze")
            allocation_digest = payload["allocation_row_digest"]
            allocation = evaluator_allocations.get(allocation_digest)
            if allocation is None:
                _fail("trial evaluator settlement allocation row is unknown")
            if allocation_digest in evaluator_settlements:
                _fail("trial evaluator allocation is already settled")
            for field in ("opaque_label", "local_attempt", "global_attempt"):
                if payload[field] != allocation.payload[field]:
                    _fail("trial evaluator settlement allocation authority disagrees")
            score_digest = payload["score_row_content_digest"]
            if score_digest is not None and any(
                settlement.payload["score_row_content_digest"] is not None
                and settlement.payload["opaque_label"] == payload["opaque_label"]
                for settlement in evaluator_settlements.values()
            ):
                _fail("trial evaluator label has multiple closed score rows")
            evaluator_settlements[allocation_digest] = row
            continue
        if row.kind == "score_settled":
            if scorer_row is None:
                _fail("trial score settlement precedes the scorer freeze")
            if scores_row is not None:
                _fail("trial score settlement follows the score freeze")
            packet_labels = {
                value["opaque_label"]
                for value in packets_row.payload["cell_packets"]
            }
            label = payload["opaque_label"]
            if label not in packet_labels:
                _fail("trial score settlement names an unknown packet domain")
            if label in score_settlements:
                _fail("trial packet label already has a score settlement")
            label_allocations = [
                allocation
                for allocation in evaluator_allocations.values()
                if allocation.payload["opaque_label"] == label
            ]
            terminal_digest = payload["terminal_attempt_settlement_row_digest"]
            if terminal_digest is None:
                if label_allocations:
                    _fail(
                        "zero-attempt trial score settlement follows an evaluator attempt"
                    )
            else:
                terminal = next(
                    (
                        settlement
                        for settlement in evaluator_settlements.values()
                        if settlement.row_digest == terminal_digest
                    ),
                    None,
                )
                if terminal is None:
                    _fail("trial score settlement attempt reference is unknown")
                if terminal.payload["opaque_label"] != label:
                    _fail("trial score settlement attempt domain disagrees")
                latest_allocation = label_allocations[-1]
                latest_settlement = evaluator_settlements.get(
                    latest_allocation.row_digest
                )
                if (
                    latest_settlement is None
                    or terminal.row_digest != latest_settlement.row_digest
                ):
                    _fail(
                        "trial score settlement does not reference the latest evaluator attempt"
                    )
                terminal_score_digest = terminal.payload[
                    "score_row_content_digest"
                ]
                if (
                    terminal_score_digest is not None
                    and terminal_score_digest != payload["score_row_content_digest"]
                ):
                    _fail("trial score settlement score authority disagrees")
            score_settlements[label] = row
            continue
        if row.kind == "scores_frozen":
            if scorer_row is None:
                _fail("trial score freeze precedes the scorer freeze")
            if scores_row is not None:
                _fail("trial scores are already frozen")
            if set(evaluator_allocations) != set(evaluator_settlements):
                _fail("trial score freeze follows an active evaluator attempt")
            packet_labels = [
                value["opaque_label"]
                for value in packets_row.payload["cell_packets"]
            ]
            expected_scores: list[dict[str, Any]] = []
            for label in packet_labels:
                settlement = score_settlements.get(label)
                if settlement is None:
                    _fail("trial score freeze requires one score settlement per packet")
                expected_scores.append(
                    {
                        "opaque_label": label,
                        "score_settlement_row_digest": settlement.row_digest,
                        "score_row_content_digest": settlement.payload[
                            "score_row_content_digest"
                        ],
                    }
                )
            if payload["scores"] != expected_scores:
                _fail("trial frozen score set disagrees with settlement authority")
            scores_row = row
            continue
        if row.kind == "aggregation_frozen":
            if scores_row is None:
                _fail("trial aggregation freeze requires the score freeze")
            if aggregation_row is not None:
                _fail("trial aggregation is already frozen")
            header = rows[0].payload
            expected_input = {
                "scores_frozen_row_digest": scores_row.row_digest,
                "sealed_opaque_label_map_digest": header[
                    "sealed_opaque_label_map_digest"
                ],
                "final_outcomes_digest": payload["final_outcomes_digest"],
                "evaluation_digest": header["evaluation_digest"],
                "score_set_digest": scores_row.payload["score_set_digest"],
            }
            if payload["scores_frozen_row_digest"] != scores_row.row_digest:
                _fail("trial aggregation score freeze authority disagrees")
            if (
                payload["sealed_opaque_label_map_digest"]
                != header["sealed_opaque_label_map_digest"]
            ):
                _fail("trial aggregation opaque-label map authority disagrees")
            if payload["aggregation_input_digest"] != canonical_sha256(
                expected_input
            ):
                _fail("trial aggregation-input digest disagrees")
            aggregation_row = row
            continue
        if row.kind == "verdict_settled":
            if aggregation_row is None:
                _fail("trial verdict settlement requires the aggregation freeze")
            if verdict_settlement_row is not None:
                _fail("trial verdict is already settled")
            if (
                payload["aggregation_frozen_row_digest"]
                != aggregation_row.row_digest
            ):
                _fail("trial verdict aggregation freeze authority disagrees")
            verdict_settlement_row = row
            continue
        if row.kind == "verdict_published":
            if verdict_settlement_row is None:
                _fail("trial verdict publication requires the verdict settlement")
            if verdict_publication_row is not None:
                _fail("trial verdict is already published")
            if (
                payload["verdict_settled_row_digest"]
                != verdict_settlement_row.row_digest
            ):
                _fail("trial verdict publication settlement authority disagrees")
            verdict_publication_row = row
            continue
        if row.kind == "trial_prepared":
            if verdict_publication_row is None:
                _fail("trial preparation requires verdict publication")
            if trial_prepared_row is not None:
                _fail("trial preparation authority is ambiguous")
            header = rows[0].payload
            settlement = verdict_settlement_row
            assert settlement is not None
            assert aggregation_row is not None
            if (
                payload["authored_outcomes_digest"]
                != aggregation_row.payload["final_outcomes_digest"]
            ):
                _fail("trial prepared authored outcomes digest disagrees")
            if (
                row.previous_row_digest != verdict_publication_row.row_digest
                or payload["verdict_publication_row_digest"]
                != verdict_publication_row.row_digest
                or payload["result_contract_digest"]
                != header["result_contract_digest"]
                or payload["verdict_digest"]
                != settlement.payload["verdict_digest"]
                or payload["verdict_artifact_digest"]
                != verdict_publication_row.payload["verdict_artifact_digest"]
                or payload["verdict_artifact_relpath"]
                != verdict_publication_row.payload["verdict_artifact_relpath"]
                or payload["budget_digest"] != header["budget_digest"]
            ):
                _fail("trial preparation authority disagrees")
            trial_prepared_row = row
            continue
        if row.kind == "trial_parent_committed":
            if trial_prepared_row is None:
                _fail("trial parent settlement requires trial preparation")
            if trial_parent_committed_row is not None:
                _fail("trial parent settlement authority is ambiguous")
            if (
                row.previous_row_digest != trial_prepared_row.row_digest
                or payload["trial_prepared_row_digest"]
                != trial_prepared_row.row_digest
                or payload["result_envelope_digest"]
                != trial_prepared_row.payload["result_envelope_digest"]
            ):
                _fail("trial parent settlement authority disagrees")
            trial_parent_committed_row = row
            continue
        if freeze_row is not None:
            _fail("trial cell transition follows the evidence freeze")
        cell = _cell(payload["cell"])
        if cell not in known:
            _fail("trial ledger row names an unknown cell")
        state = states.setdefault(cell, {})
        if row.kind == "cell_allocation_started":
            if "committed" in state or "settled" in state or "failed" in state:
                _fail("trial allocation start follows a terminal settlement")
            if "allocation_started" in state and "discarded" not in state:
                _fail("trial allocation start is ambiguous")
            expected_attempt = (
                state["discarded"].payload["next_attempt_ordinal"]
                if "discarded" in state
                else 1
            )
            if payload["attempt_ordinal"] != expected_attempt:
                _fail("trial allocation start attempt authority disagrees")
            states[cell] = {"allocation_started": row}
        elif row.kind == "cell_allocated":
            if (
                "allocation_started" not in state
                or "allocated" in state
                or "committed" in state
                or "settled" in state
                or "failed" in state
            ):
                _fail("trial cell allocation is missing its start authority")
            start = state["allocation_started"]
            expected_attempt = start.payload["attempt_ordinal"]
            expected_effect_digest = _effect_digest(request_digest, cell)
            expected_effect_root = _expected_effect_root_from_domain(
                path,
                domain,
                cell,
            )
            if (
                payload["attempt_ordinal"] != expected_attempt
                or payload["allocation_started_row_digest"] != start.row_digest
                or payload["started_at_unix_ns"]
                != start.payload["started_at_unix_ns"]
                or payload["started_monotonic_ns"]
                != start.payload["started_monotonic_ns"]
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
            state = {"allocation_started": start, "allocated": row}
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
            started_at_unix_ns = state["allocated"].payload[
                "started_at_unix_ns"
            ]
            reconciled_at_unix_ns = payload["reconciled_at_unix_ns"]
            if reconciled_at_unix_ns < started_at_unix_ns:
                _fail("trial discard reconciliation clock moved backwards")
            if payload["elapsed_ms"] != (
                reconciled_at_unix_ns - started_at_unix_ns
            ) // 1_000_000:
                _fail("trial discarded cell elapsed timing disagrees")
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
                    or payload["started_monotonic_ns"]
                    != state["allocated"].payload["started_monotonic_ns"]
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


def _ordered_trial_check_specs(
    request: TrialRuntimeRequest,
) -> tuple[dict[str, Any], ...]:
    authority_order = {"correctness": 0, "invariant": 1}
    authored = tuple(
        (index, dict(check))
        for index, check in enumerate(request.static_config.evaluation["checks"])
    )
    return tuple(
        check
        for _index, check in sorted(
            authored,
            key=lambda value: (authority_order[value[1]["authority"]], value[0]),
        )
    )


def _validate_check_rows_against_request(
    ledger: TrialEventLedger,
    request: TrialRuntimeRequest,
) -> None:
    freezes = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    check_rows = [row for row in ledger.rows if row.kind == "check_settled"]
    checks_freezes = tuple(row for row in ledger.rows if row.kind == "checks_frozen")
    if not freezes:
        if check_rows or checks_freezes:
            _fail("trial check authority precedes the evidence freeze")
        return
    if len(freezes) != 1:
        _fail("trial evidence freeze authority is ambiguous")
    freeze = freezes[0]
    evidence_by_cell = {
        _cell(value["cell"]): value for value in freeze.payload["cell_evidence"]
    }
    completed_domain = tuple(
        cell
        for cell in request.cell_domain
        if evidence_by_cell[cell]["status"] == "completed"
    )
    expected = tuple(
        (check, cell)
        for check in _ordered_trial_check_specs(request)
        for cell in completed_domain
    )
    if len(check_rows) > len(expected):
        _fail("trial settled check domain exceeds current static authority")
    for row, (check, cell) in zip(check_rows, expected, strict=False):
        payload = row.payload
        result = payload["check_result"]
        bounded_output = _bounded_check_output(result["output_bytes"])
        if (
            _cell(payload["cell"]) != cell
            or payload["check_id"] != check["check_id"]
            or payload["check_spec_digest"] != canonical_sha256(check)
            or result["check_id"] != check["check_id"]
            or result["authority"] != check["authority"]
            or result["required"] is not check["required"]
            or payload["evidence_frozen_row_digest"] != freeze.row_digest
            or payload["terminal_row_digest"]
            != evidence_by_cell[cell]["terminal_row_digest"]
        ):
            _fail("trial settled check disagrees with current static authority")
        max_output_bytes = request.static_config.evaluation["max_item_bytes"]
        if len(bounded_output[0]) > max_output_bytes or len(
            bounded_output[1]
        ) > max_output_bytes:
            _fail("trial settled check output exceeds current static authority")
    if checks_freezes and len(check_rows) != len(expected):
        _fail("trial checks freeze omits current static check authority")


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
    _validate_check_rows_against_request(ledger, request)
    return window


def validate_trial_check_phase_authority(
    path: Path,
    *,
    request: TrialRuntimeRequest,
) -> TrialEventLedger:
    """Validate request-bound check progress before any check-side effect."""

    ledger = load_trial_event_ledger(path)
    _validate_current_request_authority(ledger, request)
    _validate_check_rows_against_request(ledger, request)
    return ledger


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
        if "cell" in row.payload and _cell(row.payload["cell"]) == cell
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


def append_trial_evidence_freeze(
    path: Path,
    *,
    expected_head_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Freeze the exact terminal cell domain once, before evaluation effects."""

    ledger = load_trial_event_ledger(path)
    if any(row.kind == "evidence_frozen" for row in ledger.rows):
        _fail("trial evidence is already frozen")
    cell_evidence: list[dict[str, Any]] = []
    for cell in _header_domain(ledger):
        rows = _active_rows_for_cell(ledger, cell)
        failed = [row for row in rows if row.kind == "cell_failed"]
        settled = [row for row in rows if row.kind == "cell_settled"]
        committed = [row for row in rows if row.kind == "cell_e1_committed"]
        if len(failed) == 1 and not settled and not committed:
            terminal = failed[0]
            cell_evidence.append(
                {
                    "cell": cell.record,
                    "status": "failed",
                    "terminal_row_digest": terminal.row_digest,
                    "outcome_digest": terminal.payload["outcome_digest"],
                    "evidence_digest": terminal.payload["evidence_digest"],
                    "e1_committed_row_digest": None,
                }
            )
        elif not failed and len(settled) == 1 and len(committed) == 1:
            settlement = settled[0]
            commit = committed[0]
            cell_evidence.append(
                {
                    "cell": cell.record,
                    "status": "completed",
                    "terminal_row_digest": commit.row_digest,
                    "outcome_digest": settlement.payload["outcome_digest"],
                    "evidence_digest": settlement.payload["evidence_digest"],
                    "e1_committed_row_digest": commit.payload[
                        "e1_committed_row_digest"
                    ],
                }
            )
        else:
            _fail("trial evidence freeze requires every cell to be terminal")
    payload = {
        "cell_evidence": cell_evidence,
        "evidence_set_digest": canonical_sha256(cell_evidence),
    }
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="evidence_frozen",
        payload=payload,
        recorded_at=recorded_at,
    )


def append_trial_check_settlement(
    path: Path,
    *,
    expected_head_digest: str,
    request: TrialRuntimeRequest,
    cell: TrialCellKey,
    result: Any,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Commit the next exact per-cell check result under frozen evidence."""

    from .checks import TrialCheckResult

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    if type(cell) is not TrialCellKey:
        raise TypeError("cell must be exact TrialCellKey")
    if type(result) is not TrialCheckResult:
        raise TypeError("result must be exact TrialCheckResult")
    ledger = load_trial_event_ledger(path)
    _validate_current_request_authority(ledger, request)
    _validate_check_rows_against_request(ledger, request)
    if any(row.kind == "checks_frozen" for row in ledger.rows):
        _fail("trial checks are already frozen")
    freezes = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    if len(freezes) != 1:
        _fail("trial check settlement requires the evidence freeze")
    freeze = freezes[0]
    evidence_by_cell = {
        _cell(value["cell"]): value for value in freeze.payload["cell_evidence"]
    }
    completed_domain = tuple(
        candidate
        for candidate in request.cell_domain
        if evidence_by_cell[candidate]["status"] == "completed"
    )
    expected = tuple(
        (check, candidate)
        for check in _ordered_trial_check_specs(request)
        for candidate in completed_domain
    )
    existing = tuple(row for row in ledger.rows if row.kind == "check_settled")
    if len(existing) >= len(expected):
        _fail("trial settled check domain is already complete")
    check, expected_cell = expected[len(existing)]
    check_spec_digest = canonical_sha256(check)
    if (
        cell != expected_cell
        or result.check_id != check["check_id"]
        or result.authority != check["authority"]
        or result.required is not check["required"]
        or result.evidence_frozen_digest != freeze.row_digest
        or result.check_spec_digest != check_spec_digest
    ):
        _fail("trial settled check disagrees with next static authority")
    evidence = evidence_by_cell[cell]
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="check_settled",
        payload={
            "cell": cell.record,
            "evidence_frozen_row_digest": freeze.row_digest,
            "terminal_row_digest": evidence["terminal_row_digest"],
            "check_id": result.check_id,
            "check_spec_digest": check_spec_digest,
            "check_result": result.record,
            "check_result_digest": result.digest,
        },
        recorded_at=recorded_at,
    )


def append_trial_checks_freeze(
    path: Path,
    *,
    expected_head_digest: str,
    request: TrialRuntimeRequest,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Derive and freeze exact per-cell digests from settled check rows."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    ledger = load_trial_event_ledger(path)
    _validate_current_request_authority(ledger, request)
    _validate_check_rows_against_request(ledger, request)
    if any(row.kind == "checks_frozen" for row in ledger.rows):
        _fail("trial checks are already frozen")
    freezes = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    if len(freezes) != 1 or ledger.rows[-1].kind not in {
        "evidence_frozen",
        "check_settled",
    }:
        _fail("trial checks freeze requires settled checks after evidence freeze")
    evidence_by_cell = {
        _cell(value["cell"]): value
        for value in freezes[0].payload["cell_evidence"]
    }
    completed_count = sum(
        evidence_by_cell[cell]["status"] == "completed"
        for cell in request.cell_domain
    )
    check_rows = [row for row in ledger.rows if row.kind == "check_settled"]
    expected_count = len(_ordered_trial_check_specs(request)) * completed_count
    if len(check_rows) != expected_count:
        _fail("trial checks freeze omits current static check authority")
    normalized = _derived_frozen_cell_checks(_header_domain(ledger), check_rows)
    payload = {
        "cell_checks": normalized,
        "check_set_digest": canonical_sha256(normalized),
    }
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="checks_frozen",
        payload=payload,
        recorded_at=recorded_at,
    )


def append_trial_packets_freeze(
    path: Path,
    *,
    expected_head_digest: str,
    cell_packets: list[Mapping[str, Any]],
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Freeze ordered per-cell packet digests under sealed opaque labels."""

    ledger = load_trial_event_ledger(path)
    if any(row.kind == "packets_frozen" for row in ledger.rows):
        _fail("trial packets are already frozen")
    if ledger.rows[-1].kind != "checks_frozen":
        _fail("trial packet freeze requires the checks freeze")
    if not isinstance(cell_packets, list) or not cell_packets:
        _fail("trial frozen packet set must be a non-empty ordered list")
    normalized: list[dict[str, Any]] = []
    cells: list[TrialCellKey] = []
    for value in cell_packets:
        record = _closed(
            value,
            _FROZEN_CELL_PACKET_KEYS,
            field="trial frozen cell packet",
        )
        cell = _cell(record["cell"])
        packet_digest = _digest(record["packet_digest"], field="packet_digest")
        try:
            binding = TrialOpaqueLabelBinding(
                cell=cell,
                opaque_label=record["opaque_label"],
            )
        except (TypeError, ValueError) as exc:
            raise TrialLedgerError(
                "trial frozen packet opaque label is invalid"
            ) from exc
        cells.append(cell)
        normalized.append(
            {
                "cell": cell.record,
                "opaque_label": binding.opaque_label,
                "packet_digest": packet_digest,
            }
        )
    if tuple(cells) != _header_domain(ledger):
        _fail("trial packet freeze disagrees with header cell order")
    for cell, record in zip(cells, normalized, strict=True):
        if record["opaque_label"] != _opaque_label(ledger, cell):
            _fail("trial packet freeze disagrees with header opaque label")
    payload = {
        "cell_packets": normalized,
        "packet_set_digest": canonical_sha256(normalized),
    }
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="packets_frozen",
        payload=payload,
        recorded_at=recorded_at,
    )


def append_trial_scorer_freeze(
    path: Path,
    *,
    expected_head_digest: str,
    scorer_identity_digest: str,
    snapshot_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Freeze exact scorer identity and snapshot after packet construction."""

    ledger = load_trial_event_ledger(path)
    if any(row.kind == "scorer_frozen" for row in ledger.rows):
        _fail("trial scorer is already frozen")
    if ledger.rows[-1].kind != "packets_frozen":
        _fail("trial scorer freeze requires the packet freeze")
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="scorer_frozen",
        payload={
            "scorer_identity_digest": _digest(
                scorer_identity_digest,
                field="scorer_identity_digest",
            ),
            "snapshot_digest": _digest(snapshot_digest, field="snapshot_digest"),
        },
        recorded_at=recorded_at,
    )


def replay_trial_evaluator_attempts(path: Path) -> TrialEvaluatorAttemptReplay:
    """Replay launch charges and expose allocations left active by a crash."""

    ledger = load_trial_event_ledger(path)
    allocations = tuple(
        row for row in ledger.rows if row.kind == "evaluator_attempt_allocated"
    )
    settlements = tuple(
        row for row in ledger.rows if row.kind == "evaluator_attempt_settled"
    )
    settled_allocations = {
        row.payload["allocation_row_digest"] for row in settlements
    }
    active = tuple(
        row for row in allocations if row.row_digest not in settled_allocations
    )
    return TrialEvaluatorAttemptReplay(
        allocations=allocations,
        settlements=settlements,
        active_allocations=active,
    )


def append_trial_evaluator_attempt_allocation(
    path: Path,
    *,
    expected_head_digest: str,
    opaque_label: str,
    local_attempt: int,
    global_attempt: int,
    packet_digest: str,
    scorer_frozen_row_digest: str,
    started_at_unix_ns: int,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Charge one evaluator launch before provider preparation begins."""

    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="evaluator_attempt_allocated",
        payload={
            "opaque_label": _opaque_evaluation_label(
                opaque_label,
                field="trial evaluator attempt opaque label",
            ),
            "local_attempt": _positive_integer(
                local_attempt,
                field="trial evaluator local attempt",
            ),
            "global_attempt": _positive_integer(
                global_attempt,
                field="trial evaluator global attempt",
            ),
            "packet_digest": _digest(packet_digest, field="packet_digest"),
            "scorer_frozen_row_digest": _digest(
                scorer_frozen_row_digest,
                field="scorer_frozen_row_digest",
            ),
            "started_at_unix_ns": _nonnegative_integer(
                started_at_unix_ns,
                field="trial evaluator allocation wall-clock start",
            ),
        },
        recorded_at=recorded_at,
    )


def append_trial_evaluator_attempt_settlement(
    path: Path,
    *,
    expected_head_digest: str,
    allocation_row_digest: str,
    opaque_label: str,
    local_attempt: int,
    global_attempt: int,
    status: str,
    exit_code: int | None,
    duration_ms: int,
    token_usage: Mapping[str, Any],
    cost: Mapping[str, Any],
    stdout_digest: str | None,
    stderr_digest: str | None,
    output_digest: str | None,
    score_row_content_digest: str | None,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Close the exact charged evaluator attempt without erasing its cost."""

    if status not in {
        "preparation_failed",
        "provider_failed",
        "output_invalid",
        "scored",
    }:
        _fail("trial evaluator attempt status is invalid")
    if exit_code is not None and type(exit_code) is not int:
        _fail("trial evaluator attempt exit code is invalid")
    if type(duration_ms) is not int or duration_ms < 0:
        _fail("trial evaluator attempt duration is invalid")
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="evaluator_attempt_settled",
        payload={
            "allocation_row_digest": _digest(
                allocation_row_digest,
                field="allocation_row_digest",
            ),
            "opaque_label": _opaque_evaluation_label(
                opaque_label,
                field="trial evaluator attempt opaque label",
            ),
            "local_attempt": _positive_integer(
                local_attempt,
                field="trial evaluator local attempt",
            ),
            "global_attempt": _positive_integer(
                global_attempt,
                field="trial evaluator global attempt",
            ),
            "status": status,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "token_usage": _attempt_token_usage(token_usage),
            "cost": _attempt_cost(cost),
            "stdout_digest": _digest(
                stdout_digest,
                field="stdout_digest",
                optional=True,
            ),
            "stderr_digest": _digest(
                stderr_digest,
                field="stderr_digest",
                optional=True,
            ),
            "output_digest": _digest(
                output_digest,
                field="output_digest",
                optional=True,
            ),
            "score_row_content_digest": _digest(
                score_row_content_digest,
                field="score_row_content_digest",
                optional=True,
            ),
        },
        recorded_at=recorded_at,
    )


def append_trial_score_settlement(
    path: Path,
    *,
    expected_head_digest: str,
    opaque_label: str,
    score_row_content_digest: str,
    terminal_attempt_settlement_row_digest: str | None,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Settle one packet score after its terminal evaluator attempt, if any."""

    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="score_settled",
        payload={
            "opaque_label": _opaque_evaluation_label(
                opaque_label,
                field="trial score settlement opaque label",
            ),
            "score_row_content_digest": _digest(
                score_row_content_digest,
                field="score_row_content_digest",
            ),
            "terminal_attempt_settlement_row_digest": _digest(
                terminal_attempt_settlement_row_digest,
                field="terminal_attempt_settlement_row_digest",
                optional=True,
            ),
        },
        recorded_at=recorded_at,
    )


def append_trial_scores_freeze(
    path: Path,
    *,
    expected_head_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Freeze one explicit score settlement for each packet."""

    ledger = load_trial_event_ledger(path)
    if any(row.kind == "scores_frozen" for row in ledger.rows):
        _fail("trial scores are already frozen")
    replay = replay_trial_evaluator_attempts(path)
    if replay.active_allocations:
        _fail("trial score freeze follows an active evaluator attempt")
    packets = next(
        (row for row in ledger.rows if row.kind == "packets_frozen"),
        None,
    )
    if packets is None:
        _fail("trial score freeze requires the packet freeze")
    score_settlements = tuple(
        row for row in ledger.rows if row.kind == "score_settled"
    )
    scores: list[dict[str, Any]] = []
    for packet in packets.payload["cell_packets"]:
        label = packet["opaque_label"]
        candidates = [
            row
            for row in score_settlements
            if row.payload["opaque_label"] == label
        ]
        if len(candidates) != 1:
            _fail("trial score freeze requires one score settlement per packet")
        settlement = candidates[0]
        scores.append(
            {
                "opaque_label": label,
                "score_settlement_row_digest": settlement.row_digest,
                "score_row_content_digest": settlement.payload[
                    "score_row_content_digest"
                ],
            }
        )
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="scores_frozen",
        payload={
            "scores": scores,
            "score_set_digest": canonical_sha256(scores),
        },
        recorded_at=recorded_at,
    )


def append_trial_aggregation_freeze(
    path: Path,
    *,
    expected_head_digest: str,
    scores_frozen_row_digest: str,
    sealed_opaque_label_map_digest: str,
    final_outcomes_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Freeze the exact score, unblinding, and final-outcome authorities."""

    ledger = load_trial_event_ledger(path)
    scores = next(
        (row for row in ledger.rows if row.kind == "scores_frozen"),
        None,
    )
    if scores is None:
        _fail("trial aggregation freeze requires the score freeze")
    header = ledger.rows[0].payload
    scores_digest = _digest(
        scores_frozen_row_digest,
        field="scores_frozen_row_digest",
    )
    label_map_digest = _digest(
        sealed_opaque_label_map_digest,
        field="sealed_opaque_label_map_digest",
    )
    outcomes_digest = _digest(
        final_outcomes_digest,
        field="final_outcomes_digest",
    )
    if scores_digest != scores.row_digest:
        _fail("trial aggregation score freeze authority disagrees")
    if label_map_digest != header["sealed_opaque_label_map_digest"]:
        _fail("trial aggregation opaque-label map authority disagrees")
    authority = {
        "scores_frozen_row_digest": scores_digest,
        "sealed_opaque_label_map_digest": label_map_digest,
        "final_outcomes_digest": outcomes_digest,
        "evaluation_digest": header["evaluation_digest"],
        "score_set_digest": scores.payload["score_set_digest"],
    }
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="aggregation_frozen",
        payload={
            "scores_frozen_row_digest": scores_digest,
            "sealed_opaque_label_map_digest": label_map_digest,
            "final_outcomes_digest": outcomes_digest,
            "aggregation_input_digest": canonical_sha256(authority),
        },
        recorded_at=recorded_at,
    )


def append_trial_verdict_settlement(
    path: Path,
    *,
    expected_head_digest: str,
    aggregation_frozen_row_digest: str,
    verdict_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Settle the verdict against the immediately preceding aggregation."""

    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="verdict_settled",
        payload={
            "aggregation_frozen_row_digest": _digest(
                aggregation_frozen_row_digest,
                field="aggregation_frozen_row_digest",
            ),
            "verdict_digest": _digest(verdict_digest, field="verdict_digest"),
        },
        recorded_at=recorded_at,
    )


def append_trial_verdict_publication(
    path: Path,
    *,
    expected_head_digest: str,
    verdict_settled_row_digest: str,
    verdict_artifact_digest: str,
    verdict_artifact_relpath: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Publish the settled verdict artifact and terminate the Task-8 grammar."""

    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="verdict_published",
        payload={
            "verdict_settled_row_digest": _digest(
                verdict_settled_row_digest,
                field="verdict_settled_row_digest",
            ),
            "verdict_artifact_digest": _digest(
                verdict_artifact_digest,
                field="verdict_artifact_digest",
            ),
            "verdict_artifact_relpath": _trial_artifact_relpath(
                verdict_artifact_relpath
            ),
        },
        recorded_at=recorded_at,
    )


def append_trial_preparation(
    path: Path,
    *,
    expected_head_digest: str,
    verdict_publication_row_digest: str,
    result_contract_digest: str,
    result_envelope_digest: str,
    authored_outcomes_digest: str,
    verdict_digest: str,
    verdict_artifact_digest: str,
    verdict_artifact_relpath: str,
    budget_digest: str,
    budget_accounting_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Prepare one exact terminal trial result for atomic parent settlement."""

    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="trial_prepared",
        payload={
            "verdict_publication_row_digest": _digest(
                verdict_publication_row_digest,
                field="verdict_publication_row_digest",
            ),
            "result_contract_digest": _digest(
                result_contract_digest,
                field="result_contract_digest",
            ),
            "result_envelope_digest": _digest(
                result_envelope_digest,
                field="result_envelope_digest",
            ),
            "authored_outcomes_digest": _digest(
                authored_outcomes_digest,
                field="authored_outcomes_digest",
            ),
            "verdict_digest": _digest(verdict_digest, field="verdict_digest"),
            "verdict_artifact_digest": _digest(
                verdict_artifact_digest,
                field="verdict_artifact_digest",
            ),
            "verdict_artifact_relpath": _trial_artifact_relpath(
                verdict_artifact_relpath
            ),
            "budget_digest": _digest(budget_digest, field="budget_digest"),
            "budget_accounting_digest": _digest(
                budget_accounting_digest,
                field="budget_accounting_digest",
            ),
        },
        recorded_at=recorded_at,
    )


def append_trial_parent_commit(
    path: Path,
    *,
    expected_head_digest: str,
    trial_prepared_row_digest: str,
    result_envelope_digest: str,
    parent_state_settlement_digest: str,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Record the adjacent edge after the caller atomically settles state."""

    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="trial_parent_committed",
        payload={
            "trial_prepared_row_digest": _digest(
                trial_prepared_row_digest,
                field="trial_prepared_row_digest",
            ),
            "result_envelope_digest": _digest(
                result_envelope_digest,
                field="result_envelope_digest",
            ),
            "parent_state_settlement_digest": _digest(
                parent_state_settlement_digest,
                field="parent_state_settlement_digest",
            ),
        },
        recorded_at=recorded_at,
    )


def append_trial_e1_allocation_start(
    path: Path,
    *,
    expected_head_digest: str,
    cell: TrialCellKey,
    event: RunRefLifecycleEvent,
    started_at_unix_ns: int,
    started_monotonic_ns: int,
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Persist the explicit clock authority before the nested E1 allocation."""

    ledger = load_trial_event_ledger(path)
    if cell not in _header_domain(ledger):
        _fail("trial allocation start names an unknown cell")
    if type(event) is not RunRefLifecycleEvent:
        raise TypeError("trial allocation start requires an exact lifecycle event")
    expected_root = _expected_effect_root(Path(path), ledger, cell)
    if (
        event.event_kind != "allocation"
        or event.stage != "allocated"
        or event.visit.record != ledger.rows[0].payload["visit"]
        or event.effect_instance_root != expected_root
    ):
        _fail("trial allocation start carries cross-cell authority")
    wall_start = _nonnegative_integer(
        started_at_unix_ns,
        field="trial allocation wall-clock start",
    )
    monotonic_start = _nonnegative_integer(
        started_monotonic_ns,
        field="trial allocation monotonic start",
    )
    historical = _rows_for_cell(ledger, cell)
    active = _active_rows_for_cell(ledger, cell)
    if active:
        if (
            len(active) == 1
            and active[0].kind == "cell_allocation_started"
            and active[0].payload["cell"] == cell.record
            and active[0].payload["attempt_ordinal"] == event.attempt_ordinal
            and active[0].payload["e1_allocation_event_digest"]
            == event.event_digest
            and active[0].payload["started_at_unix_ns"] == wall_start
            and active[0].payload["started_monotonic_ns"] == monotonic_start
            and ledger.rows[-1].row_digest == expected_head_digest
        ):
            return active[0]
        _fail("trial allocation start authority is missing or ambiguous")
    expected_attempt = (
        historical[-1].payload["next_attempt_ordinal"]
        if historical and historical[-1].kind == "cell_discarded"
        else 1
    )
    if event.attempt_ordinal != expected_attempt:
        _fail("trial allocation start attempt authority disagrees")
    payload = {
        "cell": cell.record,
        "attempt_ordinal": event.attempt_ordinal,
        "e1_allocation_event_digest": event.event_digest,
        "started_at_unix_ns": wall_start,
        "started_monotonic_ns": monotonic_start,
    }
    if historical and historical[-1].kind != "cell_discarded":
        _fail("trial allocation start follows a terminal settlement")
    return _append(
        Path(path),
        expected_head_digest=expected_head_digest,
        kind="cell_allocation_started",
        payload=payload,
        recorded_at=recorded_at,
    )


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
        starts = [
            row for row in active if row.kind == "cell_allocation_started"
        ]
        allocations = [row for row in active if row.kind == "cell_allocated"]
        if len(starts) != 1 or len(active) != 1 or allocations:
            _fail("trial allocation start is missing or ambiguous")
        start = starts[0]
        if (
            start.payload["e1_allocation_event_digest"] != event.event_digest
            or start.payload["attempt_ordinal"] != event.attempt_ordinal
        ):
            _fail("trial allocation start authority disagrees")
        prior = historical[:-1]
        if prior:
            discarded = prior[-1]
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
            "allocation_started_row_digest": start.row_digest,
            "started_at_unix_ns": start.payload["started_at_unix_ns"],
            "started_monotonic_ns": start.payload["started_monotonic_ns"],
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
    terminal_monotonic_ns: int | None = None,
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
        if terminal_monotonic_ns is not None:
            _fail("trial unstarted failure cannot carry terminal timing")
        started_monotonic_ns = None
        terminal = None
        elapsed_ms = 0
    else:
        if len(allocations) != 1:
            _fail("trial failed cell E1 authority is missing or ambiguous")
        latest = _load_cell_e1_latest(ledger, allocations[0])
        if latest != e1_authority:
            _fail("trial failed cell E1 authority is not the durable head")
        started_monotonic_ns = allocations[0].payload[
            "started_monotonic_ns"
        ]
        terminal = _nonnegative_integer(
            terminal_monotonic_ns,
            field="trial failed cell monotonic terminal",
        )
        if terminal < started_monotonic_ns:
            _fail("trial failed cell monotonic clock moved backwards")
        elapsed_ms = (terminal - started_monotonic_ns) // 1_000_000
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
            "e1_authority_row_digest": authority_digest,
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
            "started_monotonic_ns": started_monotonic_ns,
            "terminal_monotonic_ns": terminal,
            "elapsed_ms": elapsed_ms,
        },
    )
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
    active = _active_rows_for_cell(ledger, scope.cell)
    starts = [row for row in active if row.kind == "cell_allocation_started"]
    if len(starts) != 1 or active != starts:
        _fail("trial orphan E1 allocation start authority is missing or ambiguous")
    start = starts[0]
    prior = historical[:-1]
    if prior and prior[-1].kind != "cell_discarded":
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
    if prior:
        discarded = prior[-1]
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
    if (
        start.payload["attempt_ordinal"] != expected_attempt
        or start.payload["e1_allocation_event_digest"] != event.event_digest
    ):
        _fail("trial orphan E1 allocation start authority disagrees")
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
    starts = [row for row in rows if row.kind == "cell_allocation_started"]
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
                _fail("trial orphan E1 allocation start authority is missing")
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
                _fail("trial orphan E1 allocation start authority is missing")
            return TrialCellResumeDecision(
                action="allocate_fresh",
                cell=cell,
                attempt_ordinal=discarded.payload["attempt_ordinal"],
                next_attempt_ordinal=discarded.payload["next_attempt_ordinal"],
            )
    if starts and not allocations:
        if len(starts) != 1 or rows != starts:
            _fail("trial allocation start authority is ambiguous")
        start = starts[0]
        orphan_path = _expected_effect_root(Path(path), ledger, cell) / (
            "run-ref-attempts.jsonl"
        )
        try:
            orphan = load_attempt_ledger(orphan_path)
        except RunRefLedgerError as exc:
            raise TrialLedgerError("trial orphan E1 ledger is unreadable") from exc
        if orphan.rows:
            historical = _rows_for_cell(ledger, cell)
            prior = historical[:-1]
            predecessor = None
            suffix = orphan.rows
            if prior:
                discarded_digest = prior[-1].payload["e1_discarded_row_digest"]
                predecessors = [
                    row
                    for row in orphan.rows
                    if row.row_digest == discarded_digest
                ]
                if len(predecessors) != 1:
                    _fail("trial orphan E1 predecessor is missing or ambiguous")
                predecessor = predecessors[0]
                suffix = orphan.rows[orphan.rows.index(predecessor) + 1 :]
            if (
                len(suffix) != 1
                or suffix[0].stage != "allocated"
                or suffix[0].status != "in_progress"
                or suffix[0].attempt_ordinal != start.payload["attempt_ordinal"]
                or suffix[0].previous_row_digest
                != (None if predecessor is None else predecessor.row_digest)
            ):
                _fail("trial orphan E1 allocation is ambiguous")
            return TrialCellResumeDecision(
                action="reconcile_orphan_e1_allocation",
                cell=cell,
                attempt_ordinal=start.payload["attempt_ordinal"],
                next_attempt_ordinal=None,
            )
        return TrialCellResumeDecision(
            action="allocate_fresh",
            cell=cell,
            attempt_ordinal=start.payload["attempt_ordinal"] - 1,
            next_attempt_ordinal=start.payload["attempt_ordinal"],
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


def select_trial_e1_allocation_start(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    cell: TrialCellKey,
    event: RunRefLifecycleEvent,
) -> TrialLedgerRow | None:
    """Return the exact pending start authority for one fresh E1 allocation."""

    if type(event) is not RunRefLifecycleEvent:
        raise TypeError("trial allocation start selector requires an exact event")
    ledger = load_trial_event_ledger(path)
    decision = classify_trial_cell_resume(
        path,
        request=request,
        cell=cell,
    )
    expected_root = _expected_effect_root(Path(path), ledger, cell)
    if (
        decision.action != "allocate_fresh"
        or decision.next_attempt_ordinal != event.attempt_ordinal
        or event.sequence != 1
        or event.event_kind != "allocation"
        or event.stage != "allocated"
        or event.visit != request.visit
        or event.effect_instance_root != expected_root
    ):
        _fail("trial allocation start selector authority disagrees")
    active = _active_rows_for_cell(ledger, cell)
    if not active:
        return None
    if len(active) != 1 or active[0].kind != "cell_allocation_started":
        _fail("trial allocation start selector authority is ambiguous")
    start = active[0]
    if (
        start.payload["cell"] != cell.record
        or start.payload["attempt_ordinal"] != event.attempt_ordinal
        or start.payload["e1_allocation_event_digest"] != event.event_digest
    ):
        _fail("trial allocation start selector authority disagrees")
    return start


def discard_incomplete_trial_cell(
    path: Path,
    *,
    expected_head_digest: str,
    request: TrialRuntimeRequest,
    cell: TrialCellKey,
    current_step_config_digest: str,
    reconciliation_wall_time_ns: int | None = None,
    recorded_at: str | None = None,
) -> TrialCellDiscardDisposition:
    reconciled_at_unix_ns = _nonnegative_integer(
        time.time_ns()
        if reconciliation_wall_time_ns is None
        else reconciliation_wall_time_ns,
        field="trial discard reconciliation wall time",
    )
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
    started_at_unix_ns = allocation.payload["started_at_unix_ns"]
    if reconciled_at_unix_ns < started_at_unix_ns:
        _fail("trial discard reconciliation clock moved backwards")
    elapsed_ms = (reconciled_at_unix_ns - started_at_unix_ns) // 1_000_000
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
            "reconciled_at_unix_ns": reconciled_at_unix_ns,
            "elapsed_ms": elapsed_ms,
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


def load_trial_score_rows(
    path: Path,
    *,
    validation_mode: Literal["complete", "partial"] = "complete",
) -> list[dict[str, Any]]:
    """Load and validate the treatment-blind trial score ledger."""

    if validation_mode not in {"complete", "partial"}:
        _fail("trial score validation mode is invalid")

    rows = load_score_ledger_rows(Path(path))
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    global_attempts: list[int] = []
    for index, raw in enumerate(rows):
        row = _closed(raw, _TRIAL_SCORE_ROW_KEYS, field=f"trial score row[{index}]")
        if row["row_schema"] != "trial.score.v1":
            _fail("trial score row schema is invalid")
        _digest(row["row_content_digest"], field="trial score row content digest")
        content = {key: value for key, value in row.items() if key != "row_content_digest"}
        if row["row_content_digest"] != canonical_sha256(content):
            _fail("trial score row content digest is invalid")
        for field in (
            "score_run_key",
            "trial_request_digest",
            "evaluation_digest",
            "evidence_frozen_digest",
            "evaluation_packet_digest",
            "scorer_identity_digest",
        ):
            _digest(row[field], field=f"trial score {field}")
        label = row["evaluation_label"]
        if (
            not isinstance(label, str)
            or re.fullmatch(r"opaque-[0-9a-f]{64}", label) is None
            or label in seen
        ):
            _fail("trial score evaluation label is invalid or duplicated")
        seen.add(label)
        identity = {
            "schema_version": "trial_score_identity.v1",
            "trial_request_digest": row["trial_request_digest"],
            "evaluation_digest": row["evaluation_digest"],
            "evidence_frozen_digest": row["evidence_frozen_digest"],
            "evaluation_label": label,
            "evaluation_packet_digest": row["evaluation_packet_digest"],
            "scorer_identity_digest": row["scorer_identity_digest"],
        }
        if row["score_run_key"] != canonical_sha256(identity):
            _fail("trial score row identity is invalid")
        attempts = row["charged_attempts"]
        if not isinstance(attempts, list) or row["attempt_count"] != len(attempts):
            _fail("trial score attempt accounting is invalid")
        previous_global_attempt = 0
        for attempt_index, attempt in enumerate(attempts, start=1):
            attempt_row = _closed(
                attempt,
                {
                    "attempt",
                    "global_attempt",
                    "status",
                    "exit_code",
                    "duration_ms",
                    "token_usage",
                    "cost",
                },
                field="trial score charged attempt",
            )
            if (
                attempt_row["attempt"] != attempt_index
                or type(attempt_row["global_attempt"]) is not int
                or attempt_row["global_attempt"] < 1
                or attempt_row["global_attempt"] <= previous_global_attempt
                or attempt_row["status"] not in {
                "preparation_failed",
                "provider_failed",
                "output_invalid",
                "scored",
                }
            ):
                _fail("trial score charged attempt is invalid")
            previous_global_attempt = attempt_row["global_attempt"]
            global_attempts.append(previous_global_attempt)
            if attempt_row["exit_code"] is not None and type(
                attempt_row["exit_code"]
            ) is not int:
                _fail("trial score attempt exit code is invalid")
            if type(attempt_row["duration_ms"]) is not int or attempt_row["duration_ms"] < 0:
                _fail("trial score attempt duration is invalid")
            token_usage = _closed(
                attempt_row["token_usage"],
                (
                    {"variant"}
                    if attempt_row["token_usage"] == {"variant": "UNKNOWN"}
                    else {"variant", "prompt_tokens", "completion_tokens", "total_tokens"}
                ),
                field="trial score attempt token usage",
            )
            if token_usage["variant"] == "KNOWN":
                counts = tuple(
                    token_usage[field]
                    for field in ("prompt_tokens", "completion_tokens", "total_tokens")
                )
                if any(type(count) is not int or count < 0 for count in counts):
                    _fail("trial score attempt token usage is invalid")
            elif token_usage["variant"] != "UNKNOWN":
                _fail("trial score attempt token usage is invalid")
            cost = _closed(
                attempt_row["cost"],
                (
                    {"variant"}
                    if attempt_row["cost"] == {"variant": "UNKNOWN"}
                    else {"variant", "amount", "currency"}
                ),
                field="trial score attempt cost",
            )
            if cost["variant"] == "KNOWN":
                amount = cost["amount"]
                if (
                    isinstance(amount, bool)
                    or not isinstance(amount, (int, float))
                    or not math.isfinite(float(amount))
                    or float(amount) < 0
                    or not isinstance(cost["currency"], str)
                    or not cost["currency"].strip()
                ):
                    _fail("trial score attempt cost is invalid")
            elif cost["variant"] != "UNKNOWN":
                _fail("trial score attempt cost is invalid")
        status = row["score_status"]
        if status == "scored":
            score = row["score"]
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
                or not 0 <= float(score) <= 1
                or not isinstance(row["summary"], str)
                or not row["summary"].strip()
                or not isinstance(row["citations"], list)
                or any(not isinstance(value, str) for value in row["citations"])
                or row["failure"] is not None
                or not attempts
                or attempts[-1]["status"] != "scored"
            ):
                _fail("trial scored row settlement is invalid")
        elif status == "evaluation_failed":
            failure = row["failure"]
            if (
                row["score"] is not None
                or row["summary"] is not None
                or row["citations"] != []
                or not isinstance(failure, Mapping)
                or set(failure) != {"code", "retryable"}
                or not isinstance(failure["code"], str)
                or not failure["code"]
                or type(failure["retryable"]) is not bool
            ):
                _fail("trial failed score row settlement is invalid")
        else:
            _fail("trial score status is invalid")
        normalized.append(json.loads(canonical_json_bytes(dict(row))))
    if len(set(global_attempts)) != len(global_attempts):
        _fail("trial score global attempt domain is invalid")
    if (
        validation_mode == "complete"
        and sorted(global_attempts) != list(range(1, len(global_attempts) + 1))
    ):
        _fail("trial score global attempt domain is invalid")
    return normalized


__all__ = [
    "TRIAL_EVENT_LEDGER_SCHEMA",
    "InitializedTrialLedger",
    "TrialCellDiscardDisposition",
    "TrialCellResumeDecision",
    "TrialEventLedger",
    "TrialEvaluatorAttemptReplay",
    "TrialLedgerError",
    "TrialLedgerRow",
    "TrialRuntimeBudgetWindow",
    "append_trial_cell_failure",
    "append_trial_cell_settlement",
    "append_trial_aggregation_freeze",
    "append_trial_check_settlement",
    "append_trial_checks_freeze",
    "append_trial_e1_allocation_start",
    "append_trial_e1_boundary",
    "append_trial_e1_committed",
    "append_trial_evidence_freeze",
    "append_trial_evaluator_attempt_allocation",
    "append_trial_evaluator_attempt_settlement",
    "append_trial_packets_freeze",
    "append_trial_parent_commit",
    "append_trial_preparation",
    "append_trial_score_settlement",
    "append_trial_scorer_freeze",
    "append_trial_scores_freeze",
    "append_trial_verdict_publication",
    "append_trial_verdict_settlement",
    "classify_trial_cell_resume",
    "build_trial_runtime_budget_window",
    "discard_incomplete_trial_cell",
    "initialize_trial_event_ledger",
    "load_trial_event_ledger",
    "load_trial_score_rows",
    "reconcile_orphan_trial_cell_allocation",
    "replay_trial_evaluator_attempts",
    "select_trial_e1_allocation_start",
    "validate_trial_check_phase_authority",
    "validate_trial_event_ledger_authority",
]
