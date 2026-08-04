"""Closed attempt validity and accounting for the first ES study."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.trial.config import TrialRuntimeRequest
from orchestrator.workflow.trial.contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
    TrialOpaqueLabelBinding,
)
from orchestrator.workflow.trial.ledger import (
    TrialEventLedger,
    load_trial_event_ledger,
    validate_trial_event_ledger_authority,
)
from orchestrator.workflow.trial.packet_artifacts import (
    PACKET_ARTIFACT_INDEX_SCHEMA,
)
from orchestrator.workflow.trial.sdk import TrialRunResult
try:
    from . import decision_lock as decision_lock_authority
except ImportError:  # pragma: no cover - direct script import mode
    import decision_lock as decision_lock_authority  # type: ignore[no-redef]


ATTEMPT_RECORD_SCHEMA = "es_attempt_record.v2"
FROZEN_TRIAL_ARTIFACT_AUTHORITY_SCHEMA = (
    "es.frozen_trial_artifact_authority.v1"
)
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


_FROZEN_AUTHORITY_KEYS = {
    "schema_version",
    "parent_run_id_binding",
    "request_template",
    "visit_template",
    "evaluation",
    "trial_schedule",
    "runtime_budget",
    "ordered_check_specs",
    "check_max_item_bytes",
    "sealed_opaque_label_policy",
}
_REQUEST_TEMPLATE_KEYS = {
    "schema_version",
    "trial_static_config_digest",
    "trial_step_config_digest",
    "arm_run_ref_authorities",
    "evaluation_digest",
    "budget_digest",
    "result_contract_digest",
    "compiler_runtime_identity_digest",
    "resolved_inputs_by_arm",
    "cell_domain",
    "cell_domain_digest",
}
_VISIT_TEMPLATE_KEYS = {
    "execution_frame_id",
    "call_frame_id",
    "step_id",
    "visit_count",
}
_BUDGET_KEYS = {
    "arm_timeout_ms",
    "trial_timeout_ms",
    "max_evaluator_attempts",
    "max_evaluator_concurrency",
}
_TRIAL_SCHEDULE_KEYS = {"reps", "max_concurrency"}
_CHECK_KEYS = {"check_id", "command", "authority", "required", "timeout_ms"}
_EVALUATION_KEYS = {
    "checks",
    "provider",
    "rubric_asset",
    "evidence_confidentiality",
    "max_item_bytes",
    "max_packet_bytes",
    "observation_include",
    "diff_cap_bytes",
    "reveal_provider_identity",
    "aggregation_mode",
    "rep_combine",
    "tie",
    "min_abs_improvement",
    "max_cost_ratio",
    "min_cost_reduction",
    "count_failures_as_outcomes",
}
_OBSERVATION_INCLUDES = {
    "task_spec",
    "validated_result",
    "workspace_delta",
    "check_results",
    "declared_artifacts",
    "failure_evidence",
}


@dataclass(frozen=True, slots=True)
class FrozenTrialArtifactAuthority:
    """Canonical pre-run authority sufficient for request-free ledger replay."""

    _canonical_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self._canonical_bytes, bytes) or not self._canonical_bytes:
            raise TypeError("frozen trial artifact authority must be nonempty bytes")

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def record(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes.decode("utf-8", "strict"))
        assert isinstance(value, dict)
        return value

    @property
    def digest(self) -> str:
        return canonical_sha256(self.record)


def _authority_fail(detail: str) -> NoReturn:
    _fail("frozen_trial_artifact_authority_invalid", detail)


def _authority_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _authority_fail(field)
    return value


def _closed_authority_mapping(
    value: object,
    keys: set[str],
    *,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _authority_fail(field)
    return value


def _authority_json_mapping(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not payload or payload.endswith(b"\n"):
        _authority_fail("canonical_bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _authority_fail("duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda _value: _authority_fail("nonfinite_value"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AttemptAccountingError(
            "frozen_trial_artifact_authority_invalid",
            "json",
        ) from exc
    if not isinstance(value, dict):
        _authority_fail("record")
    try:
        expected = canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise AttemptAccountingError(
            "frozen_trial_artifact_authority_invalid",
            "canonical_json",
        ) from exc
    if payload != expected:
        _authority_fail("canonical_json")
    return value


def _ordered_checks(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks = evaluation.get("checks")
    if not isinstance(checks, list) or any(
        not isinstance(value, dict) for value in checks
    ):
        _authority_fail("evaluation.checks")
    authority_order = {"correctness": 0, "invariant": 1}
    normalized: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, raw in enumerate(checks):
        check = _closed_authority_mapping(
            raw,
            _CHECK_KEYS,
            field="evaluation.checks",
        )
        check_id = check["check_id"]
        command = check["command"]
        if (
            not isinstance(check_id, str)
            or not check_id
            or check_id in seen
            or not isinstance(command, list)
            or not command
            or any(not isinstance(item, str) or not item for item in command)
            or check["authority"] not in authority_order
            or type(check["required"]) is not bool
            or type(check["timeout_ms"]) is not int
            or check["timeout_ms"] < 1
        ):
            _authority_fail("evaluation.checks")
        seen.add(check_id)
        normalized.append((index, dict(check)))
    return [
        check
        for _index, check in sorted(
            normalized,
            key=lambda row: (authority_order[row[1]["authority"]], row[0]),
        )
    ]


def _validate_public_evaluation(value: object) -> list[dict[str, Any]]:
    evaluation = _closed_authority_mapping(
        value,
        _EVALUATION_KEYS,
        field="evaluation",
    )
    ordered_checks = _ordered_checks(evaluation)
    for field in ("provider", "rubric_asset"):
        if not isinstance(evaluation[field], str) or not evaluation[field]:
            _authority_fail(f"evaluation.{field}")
    rubric = PurePosixPath(evaluation["rubric_asset"])
    if (
        rubric.is_absolute()
        or rubric.as_posix() != evaluation["rubric_asset"]
        or any(part in {"", ".", ".."} for part in rubric.parts)
    ):
        _authority_fail("evaluation.rubric_asset")
    if evaluation["evidence_confidentiality"] != "same_trust_boundary":
        _authority_fail("evaluation.evidence_confidentiality")
    for field in ("max_item_bytes", "max_packet_bytes", "diff_cap_bytes"):
        if type(evaluation[field]) is not int or evaluation[field] < 1:
            _authority_fail(f"evaluation.{field}")
    if evaluation["max_packet_bytes"] < evaluation["max_item_bytes"]:
        _authority_fail("evaluation.max_packet_bytes")
    includes = evaluation["observation_include"]
    if (
        not isinstance(includes, list)
        or any(
            not isinstance(item, str) or item not in _OBSERVATION_INCLUDES
            for item in includes
        )
        or len(set(includes)) != len(includes)
    ):
        _authority_fail("evaluation.observation_include")
    if (
        evaluation["reveal_provider_identity"] is not False
        or evaluation["aggregation_mode"] != "independent_rubric"
        or evaluation["rep_combine"] != "median"
        or evaluation["tie"] != "authored_order"
        or evaluation["count_failures_as_outcomes"] is not True
    ):
        _authority_fail("evaluation.closed_policy")
    for field in (
        "min_abs_improvement",
        "max_cost_ratio",
        "min_cost_reduction",
    ):
        raw = evaluation[field]
        if type(raw) not in {int, float}:
            _authority_fail(f"evaluation.{field}")
        try:
            numeric = float(raw)
        except OverflowError as exc:
            raise AttemptAccountingError(
                "frozen_trial_artifact_authority_invalid",
                f"evaluation.{field}",
            ) from exc
        if (
            not math.isfinite(numeric)
            or numeric < 0
            or (field == "max_cost_ratio" and numeric <= 0)
        ):
            _authority_fail(f"evaluation.{field}")
    return ordered_checks


def _decode_sealed_labels(
    record: Mapping[str, Any],
    *,
    digest: str,
    domain: Sequence[Mapping[str, object]],
) -> SealedTrialOpaqueLabelMap:
    if set(record) != {"schema_version", "bindings"} or record.get(
        "schema_version"
    ) != "trial_opaque_label_map.v1":
        _authority_fail("sealed_opaque_label_map")
    bindings = record.get("bindings")
    if not isinstance(bindings, list):
        _authority_fail("sealed_opaque_label_map.bindings")
    try:
        sealed = SealedTrialOpaqueLabelMap(
            bindings=tuple(
                TrialOpaqueLabelBinding(
                    cell=TrialCellKey(
                        arm_id=value["cell"]["arm_id"],
                        rep=value["cell"]["rep"],
                    ),
                    opaque_label=value["opaque_label"],
                )
                for value in bindings
            ),
            digest=digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AttemptAccountingError(
            "frozen_trial_artifact_authority_invalid",
            "sealed_opaque_label_map",
        ) from exc
    if sealed.record != dict(record) or [
        binding.cell.record for binding in sealed.bindings
    ] != [dict(cell) for cell in domain]:
        _authority_fail("sealed_opaque_label_map.domain")
    return sealed


def _validate_frozen_authority_record(record: Mapping[str, Any]) -> None:
    value = _closed_authority_mapping(
        record,
        _FROZEN_AUTHORITY_KEYS,
        field="record",
    )
    if (
        value["schema_version"] != FROZEN_TRIAL_ARTIFACT_AUTHORITY_SCHEMA
        or value["parent_run_id_binding"] != "trial_run_result.run_id"
    ):
        _authority_fail("schema_or_binding")
    template = _closed_authority_mapping(
        value["request_template"],
        _REQUEST_TEMPLATE_KEYS,
        field="request_template",
    )
    if template["schema_version"] != "trial_runtime_request.v1":
        _authority_fail("request_template.schema_version")
    for field in (
        "trial_static_config_digest",
        "trial_step_config_digest",
        "evaluation_digest",
        "budget_digest",
        "result_contract_digest",
        "compiler_runtime_identity_digest",
        "cell_domain_digest",
    ):
        _authority_digest(template[field], field=f"request_template.{field}")
    visit = _closed_authority_mapping(
        value["visit_template"],
        _VISIT_TEMPLATE_KEYS,
        field="visit_template",
    )
    if (
        not isinstance(visit["execution_frame_id"], str)
        or not visit["execution_frame_id"]
        or (
            visit["call_frame_id"] is not None
            and (
                not isinstance(visit["call_frame_id"], str)
                or not visit["call_frame_id"]
            )
        )
        or not isinstance(visit["step_id"], str)
        or not visit["step_id"]
        or type(visit["visit_count"]) is not int
        or visit["visit_count"] < 1
    ):
        _authority_fail("visit_template")
    arm_rows = template["arm_run_ref_authorities"]
    resolved_rows = template["resolved_inputs_by_arm"]
    domain = template["cell_domain"]
    if (
        not isinstance(arm_rows, list)
        or not arm_rows
        or not isinstance(resolved_rows, list)
        or not isinstance(domain, list)
        or not domain
    ):
        _authority_fail("request_template.domain")
    arm_ids: list[str] = []
    for row in arm_rows:
        arm = _closed_authority_mapping(
            row,
            {
                "arm_id",
                "run_ref_step_config_digest",
                "result_contract_digest",
            },
            field="arm_run_ref_authority",
        )
        if not isinstance(arm["arm_id"], str) or not arm["arm_id"]:
            _authority_fail("arm_run_ref_authority.arm_id")
        _authority_digest(
            arm["run_ref_step_config_digest"],
            field="arm_run_ref_authority.step",
        )
        _authority_digest(
            arm["result_contract_digest"],
            field="arm_run_ref_authority.result",
        )
        arm_ids.append(arm["arm_id"])
    if len(set(arm_ids)) != len(arm_ids):
        _authority_fail("arm_run_ref_authority.domain")
    resolved_ids: list[str] = []
    for row in resolved_rows:
        resolved = _closed_authority_mapping(
            row,
            {"arm_id", "inputs"},
            field="resolved_inputs_by_arm",
        )
        if not isinstance(resolved["arm_id"], str) or not isinstance(
            resolved["inputs"], dict
        ):
            _authority_fail("resolved_inputs_by_arm")
        resolved_ids.append(resolved["arm_id"])
    domain_rows: list[dict[str, object]] = []
    for raw in domain:
        cell = _closed_authority_mapping(
            raw,
            {"arm_id", "rep"},
            field="cell_domain",
        )
        if (
            not isinstance(cell["arm_id"], str)
            or type(cell["rep"]) is not int
            or cell["rep"] < 1
        ):
            _authority_fail("cell_domain")
        domain_rows.append({"arm_id": cell["arm_id"], "rep": cell["rep"]})
    domain_arm_ids = list(dict.fromkeys(cell["arm_id"] for cell in domain_rows))
    if (
        resolved_ids != arm_ids
        or domain_arm_ids != arm_ids
        or len({(cell["arm_id"], cell["rep"]) for cell in domain_rows})
        != len(domain_rows)
        or canonical_sha256(domain_rows) != template["cell_domain_digest"]
    ):
        _authority_fail("request_template.domain")
    evaluation = value["evaluation"]
    schedule = value["trial_schedule"]
    budget = value["runtime_budget"]
    expected_checks = _validate_public_evaluation(evaluation)
    budget_row = _closed_authority_mapping(
        budget,
        _BUDGET_KEYS,
        field="runtime_budget",
    )
    schedule_row = _closed_authority_mapping(
        schedule,
        _TRIAL_SCHEDULE_KEYS,
        field="trial_schedule",
    )
    if any(type(raw) is not int or raw < 1 for raw in budget_row.values()) or (
        budget_row["max_evaluator_concurrency"]
        > budget_row["max_evaluator_attempts"]
    ) or any(type(raw) is not int or raw < 1 for raw in schedule_row.values()):
        _authority_fail("runtime_budget")
    reps = schedule_row["reps"]
    max_concurrency = schedule_row["max_concurrency"]
    total_cells = len(arm_ids) * reps
    expected_domain = [
        {"arm_id": arm_id, "rep": rep}
        for arm_id in arm_ids
        for rep in range(1, reps + 1)
    ]
    if (
        not 2 <= len(arm_ids) <= 16
        or not 1 <= reps <= 64
        or total_cells > 256
        or not 1 <= max_concurrency <= 32
        or max_concurrency > total_cells
        or domain_rows != expected_domain
    ):
        _authority_fail("trial_schedule")
    if (
        canonical_sha256(evaluation) != template["evaluation_digest"]
        or canonical_sha256(
            {
                "reps": schedule_row["reps"],
                "max_concurrency": schedule_row["max_concurrency"],
                "budget": budget_row,
            }
        )
        != template["budget_digest"]
    ):
        _authority_fail("static_identity")
    max_item = evaluation.get("max_item_bytes")
    if (
        value["ordered_check_specs"] != expected_checks
        or type(max_item) is not int
        or max_item < 1
        or value["check_max_item_bytes"] != max_item
    ):
        _authority_fail("check_authority")
    policy = _closed_authority_mapping(
        value["sealed_opaque_label_policy"],
        {
            "schema_version",
            "cell_domain",
            "opaque_label_pattern",
            "labels_unique",
            "digest_contract",
        },
        field="sealed_opaque_label_policy",
    )
    if policy != {
        "schema_version": "trial_opaque_label_map.v1",
        "cell_domain": domain_rows,
        "opaque_label_pattern": "^opaque-[0-9a-f]{64}$",
        "labels_unique": True,
        "digest_contract": "canonical_sha256(record)",
    }:
        _authority_fail("sealed_opaque_label_policy")


def load_frozen_trial_artifact_authority(
    payload: bytes,
) -> FrozenTrialArtifactAuthority:
    """Load one exact canonical authority snapshot from package bytes."""

    record = _authority_json_mapping(payload)
    _validate_frozen_authority_record(record)
    return FrozenTrialArtifactAuthority(bytes(payload))


def freeze_trial_artifact_authority(
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
) -> FrozenTrialArtifactAuthority:
    """Freeze request-template authority before the dynamic run ID is known."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("authority request must be exact TrialRuntimeRequest")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("authority labels must be exact SealedTrialOpaqueLabelMap")
    request_record = request.record
    visit = request_record.pop("visit")
    if not isinstance(visit, dict):
        _authority_fail("request.visit")
    visit.pop("parent_run_id", None)
    evaluation = request.static_config.evaluation
    if not isinstance(request.cell_domain, tuple) or any(
        type(cell) is not TrialCellKey for cell in request.cell_domain
    ):
        _authority_fail("request.cell_domain")
    cell_domain = cast(tuple[TrialCellKey, ...], request.cell_domain)
    if [
        binding.cell.record for binding in sealed_opaque_labels.bindings
    ] != [cell.record for cell in cell_domain]:
        _authority_fail("sealed_opaque_label_policy.domain")
    record = {
        "schema_version": FROZEN_TRIAL_ARTIFACT_AUTHORITY_SCHEMA,
        "parent_run_id_binding": "trial_run_result.run_id",
        "request_template": request_record,
        "visit_template": visit,
        "evaluation": evaluation,
        "trial_schedule": {
            "reps": request.static_config.reps,
            "max_concurrency": request.static_config.max_concurrency,
        },
        "runtime_budget": request.static_config.budget,
        "ordered_check_specs": _ordered_checks(evaluation),
        "check_max_item_bytes": evaluation["max_item_bytes"],
        "sealed_opaque_label_policy": {
            "schema_version": "trial_opaque_label_map.v1",
            "cell_domain": [cell.record for cell in cell_domain],
            "opaque_label_pattern": "^opaque-[0-9a-f]{64}$",
            "labels_unique": True,
            "digest_contract": "canonical_sha256(record)",
        },
    }
    return load_frozen_trial_artifact_authority(canonical_json_bytes(record))


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
        checked_lock.get("schema_version") != "decision_lock.v2"
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
    trial_request_digest: str | None,
    *,
    ledger_input_status: str,
) -> dict[str, object]:
    return {
        "ledger_input_status": ledger_input_status,
        "ledger_valid": False,
        "coherent_allocation": False,
        "header_row_digest": None,
        "ledger_head_digest": None,
        "trial_request_digest": trial_request_digest,
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


def _request_identity_is_closed(
    *,
    record_digest: object,
    e2: Mapping[str, object],
    accounting: Mapping[str, object],
    classifier: Mapping[str, object],
) -> bool:
    e2_digest = e2.get("trial_request_digest")
    if isinstance(record_digest, str) and _SHA256_RE.fullmatch(record_digest):
        return e2_digest == record_digest
    if record_digest is not None or e2_digest is not None:
        return False
    exact_early_fault = (
        (classifier.get("source_task_binding_valid") is False)
        != (classifier.get("controller_launch_preallocation_failed") is True)
        and classifier.get("common_provider_outage_proven") is False
        and classifier.get("evaluation_bytes_valid") is True
        and classifier.get("blinding_join_valid") is True
    )
    no_accounting = (
        accounting.get("arm_routes") == []
        and accounting.get("evaluation_route_id") is None
        and accounting.get("material_disagreement") is False
        and accounting.get("review_settlements") == []
        and accounting.get("receipt_bindings") == []
        and accounting.get("call_count") == 0
        and accounting.get("terminal_authority_complete") is False
    )
    return (
        exact_early_fault
        and no_accounting
        and e2.get("ledger_input_status") == "NOT_SUPPLIED"
        and e2.get("ledger_valid") is False
        and e2.get("coherent_allocation") is False
        and e2.get("header_row_digest") is None
        and e2.get("ledger_head_digest") is None
        and e2.get("treatment_started") is False
        and e2.get("arm_settlements") == []
        and e2.get("scorer_settlements") == []
    )


def _e2_authority(
    path: Path | None,
    *,
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
) -> dict[str, object]:
    if path is None:
        return _empty_e2(request.digest, ledger_input_status="NOT_SUPPLIED")
    try:
        validate_trial_event_ledger_authority(
            Path(path),
            request=request,
            sealed_opaque_labels=sealed_opaque_labels,
        )
        ledger = load_trial_event_ledger(Path(path))
    except (OSError, ValueError):
        return _empty_e2(request.digest, ledger_input_status="INVALID_SUPPLIED")
    return _e2_from_ledger(ledger, trial_request_digest=request.digest)


def _e2_from_ledger(
    ledger: TrialEventLedger,
    *,
    trial_request_digest: str,
) -> dict[str, object]:
    rows = ledger.rows
    evidence_rows = tuple(
        row for row in rows if row.kind == "evidence_frozen"
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
        for row in rows
        if row.kind == "score_settled"
    ]
    return {
        "ledger_input_status": "VALIDATED",
        "ledger_valid": True,
        "coherent_allocation": True,
        "header_row_digest": rows[0].row_digest,
        "ledger_head_digest": rows[-1].row_digest,
        "trial_request_digest": trial_request_digest,
        "treatment_started": any(
            row.kind == "cell_allocation_started" for row in rows
        ),
        "arm_settlements": arm_settlements,
        "scorer_settlements": scorer_settlements,
    }


def _bound_frozen_request(
    authority: FrozenTrialArtifactAuthority,
    result: TrialRunResult,
) -> tuple[dict[str, Any], str]:
    value = authority.record
    template = dict(value["request_template"])
    template["visit"] = {
        "parent_run_id": result.run_id,
        **dict(value["visit_template"]),
    }
    digest = canonical_sha256(template)
    return template, digest


def _check_output_lengths(value: object) -> tuple[int, int]:
    if not isinstance(value, str):
        _fail("attempt_artifact_authority_invalid", "check_output")
    try:
        output = json.loads(value)
        stdout = base64.b64decode(output["stdout_base64"], validate=True)
        stderr = base64.b64decode(output["stderr_base64"], validate=True)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, binascii.Error) as exc:
        raise AttemptAccountingError(
            "attempt_artifact_authority_invalid",
            "check_output",
        ) from exc
    return len(stdout), len(stderr)


def _validate_frozen_check_authority(
    ledger: TrialEventLedger,
    authority: FrozenTrialArtifactAuthority,
) -> None:
    value = authority.record
    template = value["request_template"]
    domain = template["cell_domain"]
    freezes = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    check_rows = [row for row in ledger.rows if row.kind == "check_settled"]
    check_freezes = tuple(row for row in ledger.rows if row.kind == "checks_frozen")
    if not freezes:
        if check_rows or check_freezes:
            _fail("attempt_artifact_authority_invalid", "check_order")
        return
    if len(freezes) != 1:
        _fail("attempt_artifact_authority_invalid", "evidence_freeze")
    freeze = freezes[0]
    evidence_by_cell = {
        (row["cell"]["arm_id"], row["cell"]["rep"]): row
        for row in freeze.payload["cell_evidence"]
    }
    completed = [
        cell
        for cell in domain
        if evidence_by_cell[(cell["arm_id"], cell["rep"])]["status"]
        == "completed"
    ]
    expected = [
        (check, cell)
        for check in value["ordered_check_specs"]
        for cell in completed
    ]
    if len(check_rows) > len(expected):
        _fail("attempt_artifact_authority_invalid", "check_domain")
    for row, (check, cell) in zip(check_rows, expected, strict=False):
        payload = row.payload
        result = payload["check_result"]
        evidence = evidence_by_cell[(cell["arm_id"], cell["rep"])]
        stdout_size, stderr_size = _check_output_lengths(result["output_bytes"])
        if (
            payload["cell"] != cell
            or payload["check_id"] != check["check_id"]
            or payload["check_spec_digest"] != canonical_sha256(check)
            or result["check_id"] != check["check_id"]
            or result["authority"] != check["authority"]
            or result["required"] is not check["required"]
            or payload["evidence_frozen_row_digest"] != freeze.row_digest
            or payload["terminal_row_digest"] != evidence["terminal_row_digest"]
            or stdout_size > value["check_max_item_bytes"]
            or stderr_size > value["check_max_item_bytes"]
        ):
            _fail("attempt_artifact_authority_invalid", "check_authority")
    if check_freezes and len(check_rows) != len(expected):
        _fail("attempt_artifact_authority_invalid", "check_freeze")


def _validate_frozen_header_authority(
    ledger: TrialEventLedger,
    authority: FrozenTrialArtifactAuthority,
    *,
    request_record: Mapping[str, Any],
    request_digest: str,
    sealed: SealedTrialOpaqueLabelMap,
) -> None:
    header = ledger.rows[0].payload
    expected = {
        "trial_static_config_digest": request_record["trial_static_config_digest"],
        "trial_step_config_digest": request_record["trial_step_config_digest"],
        "arm_run_ref_authorities": request_record["arm_run_ref_authorities"],
        "trial_request_digest": request_digest,
        "evaluation_digest": request_record["evaluation_digest"],
        "budget_digest": request_record["budget_digest"],
        "result_contract_digest": request_record["result_contract_digest"],
        "compiler_runtime_identity_digest": request_record[
            "compiler_runtime_identity_digest"
        ],
        "visit": request_record["visit"],
        "cell_domain": request_record["cell_domain"],
        "cell_domain_digest": request_record["cell_domain_digest"],
    }
    if any(header.get(name) != expected_value for name, expected_value in expected.items()):
        _fail("attempt_artifact_authority_invalid", "header")
    if (
        header.get("sealed_opaque_label_map") != sealed.record
        or header.get("sealed_opaque_label_map_digest") != sealed.digest
    ):
        _fail("attempt_artifact_authority_invalid", "sealed_labels")
    value = authority.record
    window = header["runtime_budget_window"]
    budget = value["runtime_budget"]
    opened = window["opened_at_unix_ns"]
    arm_deadline = opened + budget["arm_timeout_ms"] * 1_000_000
    expected_deadlines = [
        {"arm_id": row["arm_id"], "deadline_unix_ns": arm_deadline}
        for row in request_record["arm_run_ref_authorities"]
    ]
    if (
        window["arm_deadlines"] != expected_deadlines
        or window["trial_deadline_unix_ns"]
        != opened + budget["trial_timeout_ms"] * 1_000_000
        or canonical_sha256(window) != header["runtime_budget_window_digest"]
    ):
        _fail("attempt_artifact_authority_invalid", "runtime_budget_window")
    _validate_frozen_check_authority(ledger, authority)


def _validate_packet_index_authority(
    ledger: TrialEventLedger,
    *,
    trial_request_digest: str,
    sealed: SealedTrialOpaqueLabelMap,
    packet_artifact_index: Mapping[str, object] | None,
) -> None:
    header = ledger.rows[0]
    packet_rows = tuple(row for row in ledger.rows if row.kind == "packets_frozen")
    if packet_artifact_index is None:
        if packet_rows:
            _fail("attempt_artifact_authority_invalid", "packet_index_missing")
        return
    evidence_rows = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    checks_rows = tuple(row for row in ledger.rows if row.kind == "checks_frozen")
    if len(evidence_rows) != 1 or len(checks_rows) != 1 or len(packet_rows) != 1:
        _fail("attempt_artifact_authority_invalid", "packet_freeze_domain")
    frozen = packet_rows[0]
    expected_packet_rows = []
    for packet in frozen.payload["cell_packets"]:
        packet_digest = packet["packet_digest"]
        expected_packet_rows.append(
            {
                **packet,
                "packet_relpath": (
                    "artifacts/trials/"
                    + trial_request_digest.removeprefix("sha256:")
                    + "/packets/"
                    + packet_digest.removeprefix("sha256:")
                    + ".json"
                ),
            }
        )
    expected = {
        "schema_version": PACKET_ARTIFACT_INDEX_SCHEMA,
        "trial_request_digest": trial_request_digest,
        "header_row_digest": header.row_digest,
        "evidence_frozen_row_digest": evidence_rows[0].row_digest,
        "checks_frozen_row_digest": checks_rows[0].row_digest,
        "packets_frozen_row_digest": frozen.row_digest,
        "sealed_opaque_label_map_digest": sealed.digest,
        "packet_set_digest": frozen.payload["packet_set_digest"],
        "packets": expected_packet_rows,
    }
    if dict(packet_artifact_index) != expected:
        _fail("attempt_artifact_authority_invalid", "packet_index")


def _artifact_e2_authority(
    path: Path | None,
    *,
    authority: FrozenTrialArtifactAuthority,
    trial_result: TrialRunResult,
    observed_header_row_digest: str | None,
    observed_sealed_opaque_labels: SealedTrialOpaqueLabelMap | None,
    packet_artifact_index: Mapping[str, object] | None,
) -> tuple[str, dict[str, object]]:
    """Classify persisted ledger bytes against frozen request-template authority."""

    request_record, request_digest = _bound_frozen_request(
        authority,
        trial_result,
    )
    if path is None:
        return request_digest, _empty_e2(
            request_digest,
            ledger_input_status="NOT_SUPPLIED",
        )
    if not isinstance(path, Path):
        raise TypeError("artifact-backed ledger path must be Path or None")
    if (
        not isinstance(observed_header_row_digest, str)
        or _SHA256_RE.fullmatch(observed_header_row_digest) is None
        or type(observed_sealed_opaque_labels) is not SealedTrialOpaqueLabelMap
    ):
        return request_digest, _empty_e2(
            request_digest,
            ledger_input_status="INVALID_SUPPLIED",
        )
    try:
        ledger = load_trial_event_ledger(path)
        if ledger.rows[0].row_digest != observed_header_row_digest:
            _fail("attempt_artifact_authority_invalid", "observed_header")
        _validate_frozen_header_authority(
            ledger,
            authority,
            request_record=request_record,
            request_digest=request_digest,
            sealed=observed_sealed_opaque_labels,
        )
        _validate_packet_index_authority(
            ledger,
            trial_request_digest=request_digest,
            sealed=observed_sealed_opaque_labels,
            packet_artifact_index=packet_artifact_index,
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return request_digest, _empty_e2(
            request_digest,
            ledger_input_status="INVALID_SUPPLIED",
        )
    return request_digest, _e2_from_ledger(
        ledger,
        trial_request_digest=request_digest,
    )


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
    """Build one immutable attempt record from request-backed E2 authority."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("attempt request must be exact TrialRuntimeRequest")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("attempt labels must be exact SealedTrialOpaqueLabelMap")
    e2 = _e2_authority(
        trial_event_ledger_path,
        request=request,
        sealed_opaque_labels=sealed_opaque_labels,
    )
    return _build_attempt_record(
        attempt_id=attempt_id,
        decision_lock=decision_lock,
        randomization_manifest=randomization_manifest,
        expected_bindings=expected_bindings,
        trial_request_digest=request.digest,
        e2=e2,
        arm_route_ids=arm_route_ids,
        evaluation_route_id=evaluation_route_id,
        material_disagreement=material_disagreement,
        review_settlements=review_settlements,
        receipt_bindings=receipt_bindings,
        source_task_binding_valid=source_task_binding_valid,
        controller_launch_preallocation_failed=(
            controller_launch_preallocation_failed
        ),
        common_provider_outage_proven=common_provider_outage_proven,
        evaluation_bytes_valid=evaluation_bytes_valid,
        blinding_join_valid=blinding_join_valid,
        interrupted=interrupted,
    )


def build_attempt_record_from_artifacts(
    *,
    attempt_id: str,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    frozen_trial_artifact_authority: bytes,
    trial_result: TrialRunResult | None,
    observed_header_row_digest: str | None,
    observed_sealed_opaque_labels: SealedTrialOpaqueLabelMap | None,
    trial_event_ledger_path: Path | None,
    packet_artifact_index: Mapping[str, object] | None,
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
    """Build from validated persisted trial bytes, without request reconstruction."""

    authority = load_frozen_trial_artifact_authority(
        frozen_trial_artifact_authority
    )
    if trial_result is None:
        no_accounting = (
            not arm_route_ids
            and evaluation_route_id is None
            and material_disagreement is False
            and not review_settlements
            and not receipt_bindings
        )
        exact_early_fault = (
            (source_task_binding_valid is False)
            != (controller_launch_preallocation_failed is True)
            and common_provider_outage_proven is False
            and evaluation_bytes_valid is True
            and blinding_join_valid is True
        )
        if (
            trial_event_ledger_path is not None
            or observed_header_row_digest is not None
            or observed_sealed_opaque_labels is not None
            or packet_artifact_index is not None
            or not no_accounting
            or not exact_early_fault
        ):
            _fail("attempt_unlaunched_authority_invalid")
        trial_request_digest: str | None = None
        e2 = _empty_e2(None, ledger_input_status="NOT_SUPPLIED")
    else:
        if type(trial_result) is not TrialRunResult:
            raise TypeError("artifact-backed trial result must be exact or None")
        trial_request_digest, e2 = _artifact_e2_authority(
            trial_event_ledger_path,
            authority=authority,
            trial_result=trial_result,
            observed_header_row_digest=observed_header_row_digest,
            observed_sealed_opaque_labels=observed_sealed_opaque_labels,
            packet_artifact_index=packet_artifact_index,
        )
    return _build_attempt_record(
        attempt_id=attempt_id,
        decision_lock=decision_lock,
        randomization_manifest=randomization_manifest,
        expected_bindings=expected_bindings,
        trial_request_digest=trial_request_digest,
        e2=e2,
        arm_route_ids=arm_route_ids,
        evaluation_route_id=evaluation_route_id,
        material_disagreement=material_disagreement,
        review_settlements=review_settlements,
        receipt_bindings=receipt_bindings,
        source_task_binding_valid=source_task_binding_valid,
        controller_launch_preallocation_failed=(
            controller_launch_preallocation_failed
        ),
        common_provider_outage_proven=common_provider_outage_proven,
        evaluation_bytes_valid=evaluation_bytes_valid,
        blinding_join_valid=blinding_join_valid,
        interrupted=interrupted,
    )


def _build_attempt_record(
    *,
    attempt_id: str,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    trial_request_digest: str | None,
    e2: Mapping[str, object],
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
        "trial_request_digest": trial_request_digest,
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
    if not _request_identity_is_closed(
        record_digest=value["trial_request_digest"],
        e2=e2,
        accounting=accounting,
        classifier=classifier,
    ) or accounting["call_count"] != len(accounting["receipt_bindings"]):
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
    "FROZEN_TRIAL_ARTIFACT_AUTHORITY_SCHEMA",
    "INVALIDITY_CODES",
    "AttemptAccountingError",
    "FrozenTrialArtifactAuthority",
    "build_attempt_record",
    "build_attempt_record_from_artifacts",
    "enforce_absolute_call_ceiling",
    "freeze_trial_artifact_authority",
    "load_frozen_trial_artifact_authority",
    "select_next_attempt_id",
    "validate_attempt_record",
]
