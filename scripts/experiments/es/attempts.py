"""Closed attempt validity and accounting for the first ES study."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import re
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

from orchestrator.workflow.trial.config import TrialRuntimeRequest
from orchestrator.workflow.trial.contracts import SealedTrialOpaqueLabelMap
from orchestrator.workflow.trial.ledger import (
    load_trial_event_ledger,
    validate_trial_event_ledger_authority,
)
try:
    from . import decision_lock as decision_lock_authority
except ImportError:  # pragma: no cover - direct script import mode
    import decision_lock as decision_lock_authority  # type: ignore[no-redef]


ATTEMPT_RECORD_SCHEMA = "es_attempt_record.v1"
INVALIDITY_CODES = (
    "SOURCE_OR_TASK_BINDING_INVALID",
    "CONTROLLER_LAUNCH_PREALLOCATION_FAILED",
    "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
    "COMMON_EVALUATION_BYTES_INVALID",
    "BLINDING_JOIN_INVALID",
    "APPARATUS_ACCOUNTING_INCOMPLETE",
)

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCORER_SLOTS = (
    "EVAL.SCORER_DIRECT",
    "EVAL.SCORER_DESIGN_QA",
    "EVAL.SCORER_PRODUCT_QA",
    "EVAL.SCORER_RICH",
)
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "experiments/orc_effectiveness/f1_es/attempt-record.schema.json"
)


class AttemptAccountingError(ValueError):
    """An ES attempt cannot be represented under the frozen accounting lock."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _fail(code: str, detail: str = "") -> NoReturn:
    raise AttemptAccountingError(code, detail)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8", "strict")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AttemptAccountingError("attempt_json_invalid") from exc


def _sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("attempt_digest_invalid", field)
    return value


def _contract(
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> dict[str, Any]:
    try:
        checked_manifest = decision_lock_authority.validate_randomization_manifest(
            randomization_manifest
        )
        checked_lock = decision_lock_authority.validate_decision_lock(
            decision_lock,
            randomization_manifest=checked_manifest,
            expected_bindings=expected_bindings,
        )
    except decision_lock_authority.DecisionLockError as exc:
        raise AttemptAccountingError(
            "attempt_contract_invalid",
            exc.code,
        ) from exc
    try:
        provider = checked_lock["provider_contract"]
        outcome = checked_lock["outcome_contract"]
        schedule = checked_lock["schedule"]
        routes = checked_lock["route_contract"]
        derived = checked_lock["derived"]
        manifest_attempts = checked_manifest["attempts"]
    except KeyError as exc:
        raise AttemptAccountingError("attempt_contract_invalid") from exc
    if (
        checked_lock.get("schema_version") != "decision_lock.v1"
        or checked_manifest.get("schema_version")
        != "es_randomization_manifest.v1"
        or not isinstance(provider, Mapping)
        or provider.get("resume_forbidden") is not True
        or not isinstance(outcome, Mapping)
        or outcome.get("attempt_resume") != "FORBIDDEN"
        or not isinstance(schedule, Mapping)
        or not isinstance(routes, Mapping)
        or not isinstance(derived, Mapping)
        or not isinstance(manifest_attempts, list)
    ):
        _fail("attempt_contract_invalid")
    manifest_digest = _sha256(checked_manifest)
    if schedule.get("manifest_sha256") != manifest_digest:
        _fail("attempt_schedule_digest_mismatch")
    lock_attempt_ids = schedule.get("attempt_ids")
    manifest_attempt_ids = [
        row.get("attempt_id") if isinstance(row, Mapping) else None
        for row in manifest_attempts
    ]
    if (
        not isinstance(lock_attempt_ids, list)
        or any(not isinstance(value, str) for value in lock_attempt_ids)
        or lock_attempt_ids != manifest_attempt_ids
        or len(lock_attempt_ids) != 4
        or len(set(lock_attempt_ids)) != 4
    ):
        _fail("attempt_schedule_invalid")
    arms = routes.get("arms")
    terminal_routes = routes.get("terminal_routes")
    evaluation_routes = routes.get("evaluation_routes")
    receipt_catalog = routes.get("receipt_call_slots")
    if (
        not isinstance(arms, list)
        or any(not isinstance(value, str) for value in arms)
        or len(arms) != 4
        or len(set(arms)) != 4
        or not isinstance(terminal_routes, list)
        or not isinstance(evaluation_routes, list)
        or len(evaluation_routes) != 2
        or not isinstance(receipt_catalog, list)
        or any(not isinstance(value, str) for value in receipt_catalog)
        or len(receipt_catalog) != len(set(receipt_catalog))
    ):
        _fail("attempt_route_contract_invalid")
    try:
        ceiling = derived["call_bounds"]["absolute_with_invalid_attempt_capacity"]
        per_attempt_maximum = derived["call_bounds"]["valid_block"]["maximum"]
        invalid_capacity = outcome["invalid_attempt_capacity"]
        maximum_valid = derived["operating_characteristics"][
            "maximum_valid_blocks"
        ]
    except (KeyError, TypeError) as exc:
        raise AttemptAccountingError("attempt_contract_invalid") from exc
    if (
        type(ceiling) is not int
        or ceiling < 0
        or type(per_attempt_maximum) is not int
        or per_attempt_maximum < 0
        or type(invalid_capacity) is not int
        or invalid_capacity < 0
        or type(maximum_valid) is not int
        or maximum_valid < 1
    ):
        _fail("attempt_contract_invalid")
    return {
        "lock_digest": decision_lock_authority.decision_lock_digest(checked_lock),
        "manifest_digest": manifest_digest,
        "attempt_ids": tuple(lock_attempt_ids),
        "manifest_attempts": tuple(manifest_attempts),
        "arms": tuple(arms),
        "terminal_routes": tuple(terminal_routes),
        "evaluation_routes": tuple(evaluation_routes),
        "receipt_catalog": tuple(receipt_catalog),
        "absolute_ceiling": ceiling,
        "per_attempt_maximum": per_attempt_maximum,
        "invalid_capacity": invalid_capacity,
        "maximum_valid": maximum_valid,
    }


def _empty_e2(
    request: TrialRuntimeRequest,
    *,
    ledger_input_status: str,
) -> dict[str, object]:
    return {
        "ledger_input_status": ledger_input_status,
        "ledger_valid": False,
        "coherent_allocation": False,
        "header_row_digest": None,
        "ledger_head_digest": None,
        "trial_request_digest": request.digest,
        "treatment_started": False,
        "arm_settlements": [],
        "scorer_settlements": [],
    }


def _e2_input_status_consistent(e2: Mapping[str, object]) -> bool:
    status = e2.get("ledger_input_status")
    if status == "VALIDATED":
        return (
            e2.get("ledger_valid") is True
            and e2.get("coherent_allocation") is True
            and isinstance(e2.get("header_row_digest"), str)
            and isinstance(e2.get("ledger_head_digest"), str)
        )
    if status in {"NOT_SUPPLIED", "INVALID_SUPPLIED"}:
        return (
            e2.get("ledger_valid") is False
            and e2.get("coherent_allocation") is False
            and e2.get("header_row_digest") is None
            and e2.get("ledger_head_digest") is None
            and e2.get("treatment_started") is False
            and e2.get("arm_settlements") == []
            and e2.get("scorer_settlements") == []
        )
    return False


def _e2_authority(
    path: Path | None,
    *,
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
) -> dict[str, object]:
    if path is None:
        return _empty_e2(request, ledger_input_status="NOT_SUPPLIED")
    try:
        validate_trial_event_ledger_authority(
            Path(path),
            request=request,
            sealed_opaque_labels=sealed_opaque_labels,
        )
        ledger = load_trial_event_ledger(Path(path))
    except (OSError, ValueError):
        return _empty_e2(request, ledger_input_status="INVALID_SUPPLIED")
    evidence_rows = tuple(
        row for row in ledger.rows if row.kind == "evidence_frozen"
    )
    arm_settlements: list[dict[str, object]] = []
    if len(evidence_rows) == 1:
        arm_settlements = [
            {
                "cell": dict(row["cell"]),
                "status": row["status"],
                "terminal_row_digest": row["terminal_row_digest"],
            }
            for row in evidence_rows[0].payload["cell_evidence"]
        ]
    scorer_settlements = [
        {
            "opaque_label": row.payload["opaque_label"],
            "settlement_row_digest": row.row_digest,
        }
        for row in ledger.rows
        if row.kind == "score_settled"
    ]
    return {
        "ledger_input_status": "VALIDATED",
        "ledger_valid": True,
        "coherent_allocation": True,
        "header_row_digest": ledger.rows[0].row_digest,
        "ledger_head_digest": ledger.rows[-1].row_digest,
        "trial_request_digest": request.digest,
        "treatment_started": any(
            row.kind == "cell_allocation_started" for row in ledger.rows
        ),
        "arm_settlements": arm_settlements,
        "scorer_settlements": scorer_settlements,
    }


def _normalize_routes(
    arm_route_ids: Mapping[str, object],
    *,
    arms: tuple[str, ...],
) -> list[dict[str, str]]:
    if not isinstance(arm_route_ids, Mapping):
        return []
    return [
        {"arm": arm, "route_id": str(arm_route_ids[arm])}
        for arm in arms
        if arm in arm_route_ids and isinstance(arm_route_ids[arm], str)
    ]


def _normalize_review_settlements(
    values: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return []
    rows: list[dict[str, object]] = []
    keys = {"call_slot_id", "status", "record_sha256", "receipt_sha256"}
    for value in values:
        if not isinstance(value, Mapping) or set(value) != keys:
            continue
        if (
            not isinstance(value["call_slot_id"], str)
            or value["status"] not in {"SUCCEEDED", "FAILED"}
        ):
            continue
        try:
            record_digest = _digest(
                value["record_sha256"], field="review.record_sha256"
            )
            receipt_digest = _digest(
                value["receipt_sha256"], field="review.receipt_sha256"
            )
        except AttemptAccountingError:
            continue
        rows.append(
            {
                "call_slot_id": value["call_slot_id"],
                "status": value["status"],
                "record_sha256": record_digest,
                "receipt_sha256": receipt_digest,
            }
        )
    return rows


def _normalize_receipts(
    values: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return []
    rows: list[dict[str, str]] = []
    for value in values:
        if (
            not isinstance(value, Mapping)
            or set(value) != {"call_slot_id", "receipt_sha256"}
            or not isinstance(value["call_slot_id"], str)
        ):
            continue
        try:
            digest = _digest(
                value["receipt_sha256"], field="receipt.receipt_sha256"
            )
        except AttemptAccountingError:
            continue
        rows.append(
            {
                "call_slot_id": value["call_slot_id"],
                "receipt_sha256": digest,
            }
        )
    return rows


def _accounting_complete(
    *,
    e2: Mapping[str, object],
    arm_routes: Sequence[Mapping[str, object]],
    evaluation_route_id: object,
    material_disagreement: object,
    reviews: Sequence[Mapping[str, object]],
    receipts: Sequence[Mapping[str, object]],
    contract: Mapping[str, Any],
) -> bool:
    arms = contract["arms"]
    settlements = e2.get("arm_settlements")
    scorers = e2.get("scorer_settlements")
    if (
        e2.get("ledger_valid") is not True
        or e2.get("coherent_allocation") is not True
        or not isinstance(settlements, list)
        or not isinstance(scorers, list)
        or len(settlements) != 4
        or len(scorers) != 4
    ):
        return False
    cells: list[Mapping[str, object]] = []
    statuses: dict[object, object] = {}
    for row in settlements:
        if not isinstance(row, Mapping):
            return False
        cell = row.get("cell")
        if not isinstance(cell, Mapping):
            return False
        cells.append(cell)
        statuses[cell.get("arm_id")] = row.get("status")
    if [cell.get("arm_id") for cell in cells] != list(arms):
        return False
    if any(cell.get("rep") != 1 for cell in cells):
        return False
    if set(statuses) != set(arms) or any(
        status not in {"completed", "failed"} for status in statuses.values()
    ):
        return False
    scorer_labels = [
        row.get("opaque_label") for row in scorers if isinstance(row, Mapping)
    ]
    if len(scorer_labels) != 4 or len(set(scorer_labels)) != 4:
        return False

    route_rows = {
        row.get("route_id"): row
        for row in contract["terminal_routes"]
        if isinstance(row, Mapping)
    }
    if len(arm_routes) != 4 or [row.get("arm") for row in arm_routes] != list(arms):
        return False
    treatment_slots: list[str] = []
    for selected in arm_routes:
        arm = selected.get("arm")
        route = route_rows.get(selected.get("route_id"))
        if (
            not isinstance(route, Mapping)
            or route.get("arm") != arm
            or route.get("completed") is not (statuses[arm] == "completed")
            or not isinstance(route.get("call_slots"), list)
        ):
            return False
        treatment_slots.extend(route["call_slots"])

    evaluation = next(
        (
            row
            for row in contract["evaluation_routes"]
            if isinstance(row, Mapping) and row.get("route_id") == evaluation_route_id
        ),
        None,
    )
    if not isinstance(evaluation, Mapping) or not isinstance(
        evaluation.get("call_slots"), list
    ):
        return False
    if (
        type(material_disagreement) is not bool
        or evaluation.get("adjudication") is not material_disagreement
    ):
        return False
    evaluation_slots = evaluation["call_slots"]
    if tuple(evaluation_slots[:4]) != _SCORER_SLOTS:
        return False
    expected_review_slots = evaluation_slots[4:]
    if [row.get("call_slot_id") for row in reviews] != expected_review_slots:
        return False
    receipt_by_slot = {
        row.get("call_slot_id"): row.get("receipt_sha256") for row in receipts
    }
    expected_slots = treatment_slots + evaluation_slots
    if (
        len(receipts) != len(expected_slots)
        or len(receipt_by_slot) != len(receipts)
        or [row.get("call_slot_id") for row in receipts] != expected_slots
        or any(slot not in contract["receipt_catalog"] for slot in expected_slots)
    ):
        return False
    return all(
        receipt_by_slot.get(row["call_slot_id"]) == row.get("receipt_sha256")
        for row in reviews
    )


def _classify(
    *,
    classifier: Mapping[str, object],
    e2: Mapping[str, object],
    accounting_complete: bool,
) -> str | None:
    coherent = e2.get("coherent_allocation") is True
    treatment_started = e2.get("treatment_started") is True
    ledger_input_status = e2.get("ledger_input_status")
    if ledger_input_status == "INVALID_SUPPLIED":
        return "APPARATUS_ACCOUNTING_INCOMPLETE"
    candidates: list[str] = []
    if classifier.get("source_task_binding_valid") is False:
        if ledger_input_status != "NOT_SUPPLIED" or coherent:
            _fail("source_task_binding_invalid_after_allocation")
        candidates.append("SOURCE_OR_TASK_BINDING_INVALID")
    if classifier.get("controller_launch_preallocation_failed") is True:
        if (
            ledger_input_status != "NOT_SUPPLIED"
            or coherent
            or treatment_started
        ):
            _fail("controller_preallocation_failure_after_allocation")
        candidates.append("CONTROLLER_LAUNCH_PREALLOCATION_FAILED")
    if classifier.get("common_provider_outage_proven") is True:
        if treatment_started:
            _fail("common_provider_outage_after_treatment")
        if not coherent:
            _fail("common_provider_outage_without_coherent_allocation")
        candidates.append("COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT")
    if classifier.get("evaluation_bytes_valid") is False:
        if not coherent:
            _fail("evaluation_bytes_invalid_without_coherent_allocation")
        candidates.append("COMMON_EVALUATION_BYTES_INVALID")
    if classifier.get("blinding_join_valid") is False:
        if not coherent:
            _fail("blinding_join_invalid_without_coherent_allocation")
        candidates.append("BLINDING_JOIN_INVALID")
    if len(candidates) > 1:
        _fail("attempt_invalidity_ambiguous")
    if candidates:
        return candidates[0]
    if not accounting_complete:
        return "APPARATUS_ACCOUNTING_INCOMPLETE"
    return None


def build_attempt_record(
    *,
    attempt_id: str,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
    trial_event_ledger_path: Path | None,
    arm_route_ids: Mapping[str, object],
    evaluation_route_id: str | None,
    material_disagreement: bool,
    review_settlements: Sequence[Mapping[str, object]],
    receipt_bindings: Sequence[Mapping[str, object]],
    source_task_binding_valid: bool,
    controller_launch_preallocation_failed: bool,
    common_provider_outage_proven: bool,
    evaluation_bytes_valid: bool,
    blinding_join_valid: bool,
    interrupted: bool,
) -> dict[str, object]:
    """Build one immutable attempt record from E2 and controller authority."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("attempt request must be exact TrialRuntimeRequest")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("attempt labels must be exact SealedTrialOpaqueLabelMap")
    flags = (
        source_task_binding_valid,
        controller_launch_preallocation_failed,
        common_provider_outage_proven,
        evaluation_bytes_valid,
        blinding_join_valid,
        material_disagreement,
        interrupted,
    )
    if any(type(value) is not bool for value in flags):
        raise TypeError("attempt classifier inputs must be exact booleans")
    contract = _contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    if attempt_id not in contract["attempt_ids"]:
        _fail("attempt_id_not_locked", attempt_id)
    schedule_row = next(
        row
        for row in contract["manifest_attempts"]
        if isinstance(row, Mapping) and row.get("attempt_id") == attempt_id
    )
    e2 = _e2_authority(
        trial_event_ledger_path,
        request=request,
        sealed_opaque_labels=sealed_opaque_labels,
    )
    arm_routes = _normalize_routes(arm_route_ids, arms=contract["arms"])
    reviews = _normalize_review_settlements(review_settlements)
    receipts = _normalize_receipts(receipt_bindings)
    early_fault = (
        e2["ledger_input_status"] != "INVALID_SUPPLIED"
        and (
            source_task_binding_valid is False
            or controller_launch_preallocation_failed is True
            or common_provider_outage_proven is True
        )
    )
    if (
        early_fault
        and e2["treatment_started"] is False
        and (
            arm_routes
            or evaluation_route_id is not None
            or material_disagreement is True
            or reviews
            or receipts
        )
    ):
        _fail("pre_treatment_accounting_inconsistent")
    accounting_complete = _accounting_complete(
        e2=e2,
        arm_routes=arm_routes,
        evaluation_route_id=evaluation_route_id,
        material_disagreement=material_disagreement,
        reviews=reviews,
        receipts=receipts,
        contract=contract,
    )
    classifier = {
        "source_task_binding_valid": source_task_binding_valid,
        "controller_launch_preallocation_failed": (
            controller_launch_preallocation_failed
        ),
        "common_provider_outage_proven": common_provider_outage_proven,
        "evaluation_bytes_valid": evaluation_bytes_valid,
        "blinding_join_valid": blinding_join_valid,
    }
    invalidity = _classify(
        classifier=classifier,
        e2=e2,
        accounting_complete=accounting_complete,
    )
    record: dict[str, object] = {
        "schema_version": ATTEMPT_RECORD_SCHEMA,
        "attempt_id": attempt_id,
        "decision_lock_sha256": contract["lock_digest"],
        "randomization_manifest_sha256": contract["manifest_digest"],
        "randomization_row_sha256": _sha256(schedule_row),
        "trial_request_digest": request.digest,
        "resume_policy": "FORBIDDEN",
        "interrupted": interrupted,
        "classifier_inputs": classifier,
        "e2_authority": e2,
        "accounting": {
            "arm_routes": arm_routes,
            "evaluation_route_id": evaluation_route_id,
            "material_disagreement": material_disagreement,
            "review_settlements": reviews,
            "receipt_bindings": receipts,
            "call_count": len(receipts),
            "terminal_authority_complete": accounting_complete,
        },
        "status": "VALID" if invalidity is None else "INVALID",
        "invalidity_code": invalidity,
    }
    validate_attempt_record(
        record,
        decision_lock=decision_lock,
        randomization_manifest=randomization_manifest,
        expected_bindings=expected_bindings,
    )
    return record


def _schema() -> dict[str, object]:
    try:
        value = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttemptAccountingError("attempt_schema_unreadable") from exc
    if not isinstance(value, dict):
        _fail("attempt_schema_invalid")
    return value


def validate_attempt_record(
    record: Mapping[str, object],
    *,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> dict[str, object]:
    """Revalidate one closed record against the same immutable lock and schedule."""

    contract = _contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    errors = sorted(Draft202012Validator(_schema()).iter_errors(record), key=str)
    if errors:
        _fail("attempt_record_schema_invalid", errors[0].message)
    value = dict(record)
    if (
        value["decision_lock_sha256"] != contract["lock_digest"]
        or value["randomization_manifest_sha256"] != contract["manifest_digest"]
        or value["attempt_id"] not in contract["attempt_ids"]
    ):
        _fail("attempt_record_binding_mismatch")
    schedule_row = next(
        row
        for row in contract["manifest_attempts"]
        if isinstance(row, Mapping) and row.get("attempt_id") == value["attempt_id"]
    )
    if value["randomization_row_sha256"] != _sha256(schedule_row):
        _fail("attempt_record_binding_mismatch")
    e2 = value["e2_authority"]
    accounting = value["accounting"]
    classifier = value["classifier_inputs"]
    assert isinstance(e2, Mapping)
    assert isinstance(accounting, Mapping)
    assert isinstance(classifier, Mapping)
    if not _e2_input_status_consistent(e2):
        _fail("attempt_record_internal_mismatch")
    if (
        value["trial_request_digest"] != e2["trial_request_digest"]
        or accounting["call_count"] != len(accounting["receipt_bindings"])
    ):
        _fail("attempt_record_internal_mismatch")
    early_fault = (
        e2["ledger_input_status"] != "INVALID_SUPPLIED"
        and (
            classifier["source_task_binding_valid"] is False
            or classifier["controller_launch_preallocation_failed"] is True
            or classifier["common_provider_outage_proven"] is True
        )
    )
    if (
        early_fault
        and e2["treatment_started"] is False
        and (
            accounting["arm_routes"]
            or accounting["evaluation_route_id"] is not None
            or accounting["material_disagreement"] is True
            or accounting["review_settlements"]
            or accounting["receipt_bindings"]
        )
    ):
        _fail("attempt_record_internal_mismatch")
    complete = _accounting_complete(
        e2=e2,
        arm_routes=accounting["arm_routes"],
        evaluation_route_id=accounting["evaluation_route_id"],
        material_disagreement=accounting["material_disagreement"],
        reviews=accounting["review_settlements"],
        receipts=accounting["receipt_bindings"],
        contract=contract,
    )
    if accounting["terminal_authority_complete"] is not complete:
        _fail("attempt_record_internal_mismatch")
    invalidity = _classify(
        classifier=classifier,
        e2=e2,
        accounting_complete=complete,
    )
    if value["invalidity_code"] != invalidity or value["status"] != (
        "VALID" if invalidity is None else "INVALID"
    ):
        _fail("attempt_record_internal_mismatch")
    return value


def select_next_attempt_id(
    consumed_attempt_ids: Sequence[str],
    *,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> str:
    """Select only the next unused precommitted ID; attempts are never resumed."""

    contract = _contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    values = tuple(consumed_attempt_ids)
    if values != contract["attempt_ids"][: len(values)]:
        _fail("attempt_sequence_invalid")
    if len(values) >= len(contract["attempt_ids"]):
        _fail("attempt_schedule_exhausted")
    return contract["attempt_ids"][len(values)]


def enforce_absolute_call_ceiling(
    attempt_call_counts: Sequence[int],
    *,
    invalid_attempt_count: int,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> int:
    """Reject denominator extension, invalid-capacity drift, or excess calls."""

    contract = _contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    counts = tuple(attempt_call_counts)
    if any(type(value) is not int or value < 0 for value in counts):
        _fail("attempt_call_count_invalid")
    if type(invalid_attempt_count) is not int or invalid_attempt_count < 0:
        _fail("invalid_attempt_count_invalid")
    if invalid_attempt_count > len(counts):
        _fail("invalid_attempt_count_invalid")
    if invalid_attempt_count > contract["invalid_capacity"]:
        _fail("invalid_attempt_capacity_exceeded")
    if any(value > contract["per_attempt_maximum"] for value in counts):
        _fail("attempt_call_count_exceeded")
    if (
        len(counts) > contract["maximum_valid"] + contract["invalid_capacity"]
        or len(counts) - invalid_attempt_count > contract["maximum_valid"]
    ):
        _fail("attempt_denominator_extended")
    total = sum(counts)
    if total > contract["absolute_ceiling"]:
        _fail("call_ceiling_exceeded")
    return total


__all__ = [
    "ATTEMPT_RECORD_SCHEMA",
    "INVALIDITY_CODES",
    "AttemptAccountingError",
    "build_attempt_record",
    "enforce_absolute_call_ceiling",
    "select_next_attempt_id",
    "validate_attempt_record",
]
