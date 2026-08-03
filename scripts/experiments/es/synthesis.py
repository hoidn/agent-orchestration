"""Deterministic, provider-free synthesis for the first ES study."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial.contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
    TrialOpaqueLabelBinding,
)
from orchestrator.workflow.trial.ledger import (
    TRIAL_EVENT_LEDGER_SCHEMA,
    TrialLedgerError,
    load_trial_score_rows,
)
from orchestrator.workflow.trial.packets import validate_trial_evaluation_packet

from . import attempts
from . import blinding
from . import decision_lock as decision_lock_authority
from . import hard_contract
from . import metering
from . import reviews


REPORT_SCHEMA_VERSION = "es_study_report.v1"
ATTEMPT_INDEX_SCHEMA_VERSION = "es_synthesis_attempt_index.v1"

_ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
_TIMING_SOURCE = "MONOTONIC_INVOCATION_SETTLEMENT_MS"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "experiments/orc_effectiveness/f1_es/report.schema.json"
)
_INDEX_KEYS = frozenset(
    {
        "schema_version",
        "index_sha256",
        "attempt_record",
        "attempt_record_sha256",
        "evidence_variant",
        "call_authority",
        "public_packet_replay_inputs",
        "private_blinding_replay_inputs",
        "private_blinding_join",
        "private_blinding_join_sha256",
        "packets",
        "scorer_settlements",
        "reviews",
        "integrated_prior_record_sha256s",
        "adjudication_payload",
        "adjudication_payload_sha256",
        "integrated_payload",
        "integrated_payload_sha256",
        "hard_evaluations",
        "oriented_primary",
        "oriented_primary_sha256",
        "hard_primary_outcome",
        "hard_primary_outcome_sha256",
        "call_allocations",
        "receipts",
        "elapsed_ms",
    }
)
_PARTIAL_INDEX_KEYS = _INDEX_KEYS | {
    "invalidity_authority",
    "invalidity_authority_sha256",
}
_CALL_AUTHORITY_KEYS = frozenset(
    {"schema_version", "prompt_manifest", "environment_lock"}
)
_PROMPT_MANIFEST_KEYS = frozenset({"schema_version", "calls"})
_CALL_ROW_KEYS = frozenset(
    {
        "call_slot_id",
        "role_id",
        "prompt_sha256",
        "contract_sha256",
        "normalized_argv",
    }
)
_ENVIRONMENT_LOCK_KEYS = frozenset(
    {
        "schema_version",
        "provider_family",
        "version",
        "model",
        "reasoning_effort",
        "prompt_transport",
        "executable_chain",
        "evaluation_authority",
    }
)
_EVALUATION_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "hard_evaluator_identity_digest",
        "hard_task_identity_digest",
        "hard_fixture_identity_digest",
        "scorer_evaluation_digest",
        "scorer_identity_digest",
    }
)
_EXECUTABLE_CHAIN_KEYS = frozenset(
    {
        "provider_family",
        "version",
        "launcher_path",
        "launcher_sha256",
        "interpreter_path",
        "interpreter_sha256",
    }
)
_PUBLIC_PACKET_REPLAY_KEYS = frozenset(
    {
        "schema_version",
        "request_cell_domain",
        "packet_artifact_index",
    }
)
_PRIVATE_REPLAY_KEYS = frozenset(
    {"schema_version", "sealed_opaque_label_map"}
)
_PACKET_INDEX_KEYS = frozenset(
    {
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
)
_PACKET_INDEX_ROW_KEYS = frozenset(
    {"cell", "opaque_label", "packet_digest", "packet_relpath"}
)
_HARD_REPLAY_KEYS = frozenset(
    {
        "schema_version",
        "candidate_claims",
        "evaluator_observations",
        "proof_rows",
        "frozen_registry",
        "trusted_product_freeze_digest",
        "evaluator_identity_digest",
        "task_identity_digest",
        "fixture_identity_digest",
        "frozen_proof_authority",
    }
)
_HARD_PRESENT_KEYS = frozenset(
    {
        "schema_version",
        "arm_id",
        "trusted_product_freeze_status",
        "replay_inputs",
        "freeze",
        "freeze_sha256",
        "evaluation",
        "evaluation_sha256",
    }
)
_HARD_MISSING_KEYS = frozenset(
    {
        "schema_version",
        "arm_id",
        "trusted_product_freeze_status",
        "absence_authority",
    }
)
_HARD_ABSENCE_KEYS = frozenset(
    {"schema_version", "reason", "cell", "terminal_row_digest"}
)
_CALL_ALLOCATION_KEYS = frozenset(
    {
        "schema_version",
        "call_slot_id",
        "allocation_authority",
        "allocation_sha256",
        "settlement",
        "receipt_sha256",
    }
)
_ALLOCATION_AUTHORITY_KEYS = frozenset(
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
_PARTIAL_EVIDENCE_KEYS = frozenset(
    {
        "public_packet_replay_inputs",
        "private_blinding_replay_inputs",
        "private_blinding_join",
        "private_blinding_join_sha256",
        "packets",
        "scorer_settlements",
        "reviews",
        "integrated_prior_record_sha256s",
        "adjudication_payload",
        "adjudication_payload_sha256",
        "integrated_payload",
        "integrated_payload_sha256",
        "hard_evaluations",
        "oriented_primary",
        "oriented_primary_sha256",
        "hard_primary_outcome",
        "hard_primary_outcome_sha256",
    }
)
_INVALIDITY_AUTHORITY_KEYS = frozenset(
    {"schema_version", "attempt_id", "invalidity_code", "evidence"}
)
_CONTROLLER_AUTHORITY_INVALIDITY_CODES = frozenset(
    {
        "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
        "COMMON_EVALUATION_BYTES_INVALID",
    }
)
_PRIMARY_KEYS = frozenset(
    {
        "schema_version",
        "raw_outcome",
        "derived_outcome",
        "rich_freeze_digest",
        "direct_freeze_digest",
        "rich_product_blockers",
        "direct_product_blockers",
        "rich_unresolved_blockers",
        "direct_unresolved_blockers",
        "comparable_product_blockers",
    }
)
_ORIENTED_KEYS = frozenset(
    {
        "rich_vs_direct",
        "source_pair_row_digest",
        "integrated_review_record_digest",
        "hard_evidence_record_digest",
        "unblinding_map_digest",
    }
)
_FAILURE_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "call_slot_id",
        "session_id",
        "provider_attempt_id",
        "receipt_digest",
        "failure_code",
    }
)
_FAILURE_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z")


class SynthesisError(ValueError):
    """One immutable synthesis input or locked decision invariant failed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _fail(code: str, detail: str = "") -> NoReturn:
    raise SynthesisError(code, detail)


def canonical_report_bytes(value: object) -> bytes:
    """Return strict canonical report bytes with one trailing LF."""

    try:
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
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SynthesisError("synthesis_json_invalid") from exc


def _canonical_copy(value: object) -> Any:
    try:
        return json.loads(canonical_report_bytes(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:  # pragma: no cover
        raise SynthesisError("synthesis_json_invalid") from exc


def _study_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_report_bytes(value)).hexdigest()


def _raw_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SynthesisError("synthesis_schema_unreadable", str(path)) from exc


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("synthesis_digest_invalid", field)
    return value


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SynthesisError("synthesis_schema_unreadable", str(path)) from exc
    if not isinstance(value, dict):
        _fail("synthesis_schema_invalid", str(path))
    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:
        raise SynthesisError("synthesis_schema_invalid", str(path)) from exc
    return value


def _checked_contract(
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    schema_digest = _raw_digest(_SCHEMA_PATH)
    if (
        not isinstance(expected_bindings, Mapping)
        or expected_bindings.get("report_schema_sha256") != schema_digest
    ):
        _fail("synthesis_report_schema_binding_mismatch")
    try:
        schedule = decision_lock_authority.validate_randomization_manifest(
            randomization_manifest
        )
        lock = decision_lock_authority.validate_decision_lock(
            decision_lock,
            randomization_manifest=schedule,
            expected_bindings=expected_bindings,
        )
    except decision_lock_authority.DecisionLockError as exc:
        raise SynthesisError("synthesis_decision_lock_invalid", exc.code) from exc
    lock_bindings = lock.get("bindings")
    if (
        not isinstance(lock_bindings, Mapping)
        or lock_bindings.get("report_schema_sha256") != schema_digest
    ):
        _fail("synthesis_report_schema_binding_mismatch")
    derived = lock.get("derived")
    authored = lock.get("authored_choices")
    outcomes = lock.get("outcome_contract")
    if (
        not isinstance(derived, Mapping)
        or not isinstance(authored, Mapping)
        or not isinstance(outcomes, Mapping)
    ):
        _fail("synthesis_decision_lock_invalid")
    operating = derived.get("operating_characteristics")
    if not isinstance(operating, Mapping):
        _fail("synthesis_decision_lock_invalid")
    if (
        operating.get("required_non_tied_comparisons") != 2
        or operating.get("critical_rich_wins") != 2
        or operating.get("maximum_valid_blocks") != 3
        or authored.get("maximum_median_rich_direct_token_cost_ratio") != "4"
        or authored.get("viability_rule")
        != "RICH_TREATMENT_FAILURES_LTE_DIRECT"
        or outcomes.get("invalid_attempt_capacity") != 1
    ):
        _fail("synthesis_decision_lock_values_mismatch")
    return lock, schedule, schema_digest


def _validated_call_authority(
    value: object,
    *,
    decision_lock: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate the two content-addressed static call authorities."""

    authority = _canonical_copy(value)
    if (
        not isinstance(authority, dict)
        or set(authority) != _CALL_AUTHORITY_KEYS
        or authority.get("schema_version") != "es.frozen_call_authority.v1"
    ):
        _fail("synthesis_call_authority_invalid")
    prompt_manifest = authority["prompt_manifest"]
    environment_lock = authority["environment_lock"]
    if (
        not isinstance(prompt_manifest, dict)
        or set(prompt_manifest) != _PROMPT_MANIFEST_KEYS
        or prompt_manifest.get("schema_version") != "es.prompt_manifest.v1"
        or not isinstance(environment_lock, dict)
        or set(environment_lock) != _ENVIRONMENT_LOCK_KEYS
        or environment_lock.get("schema_version") != "es.environment_lock.v1"
        or canonical_sha256(prompt_manifest)
        != expected_bindings.get("prompt_manifest_sha256")
        or canonical_sha256(environment_lock)
        != expected_bindings.get("environment_lock_sha256")
    ):
        _fail("synthesis_call_authority_binding_mismatch")
    provider = decision_lock.get("provider_contract")
    chain = environment_lock.get("executable_chain")
    evaluation_authority = environment_lock.get("evaluation_authority")
    if (
        not isinstance(provider, Mapping)
        or not isinstance(chain, dict)
        or set(chain) != _EXECUTABLE_CHAIN_KEYS
        or environment_lock.get("provider_family") != provider.get("provider_family")
        or environment_lock.get("version") != provider.get("version")
        or chain.get("provider_family") != provider.get("provider_family")
        or chain.get("version") != provider.get("version")
        or chain.get("launcher_sha256") != provider.get("launcher_sha256")
        or not isinstance(environment_lock.get("model"), str)
        or not environment_lock["model"]
        or environment_lock.get("reasoning_effort") != "high"
        or environment_lock.get("prompt_transport") != "STDIN"
        or not isinstance(evaluation_authority, dict)
        or set(evaluation_authority) != _EVALUATION_AUTHORITY_KEYS
        or evaluation_authority.get("schema_version")
        != "es.evaluation_authority.v1"
    ):
        _fail("synthesis_call_authority_provider_mismatch")
    for field in ("launcher_path", "interpreter_path"):
        if not isinstance(chain.get(field), str) or not chain[field]:
            _fail("synthesis_call_authority_invalid", field)
    for field in ("launcher_sha256", "interpreter_sha256"):
        _digest(chain.get(field), field=f"call_authority.{field}")
    for field in _EVALUATION_AUTHORITY_KEYS - {"schema_version"}:
        _digest(
            evaluation_authority.get(field),
            field=f"evaluation_authority.{field}",
        )

    route = decision_lock.get("route_contract")
    calls = prompt_manifest.get("calls")
    if not isinstance(route, Mapping) or not isinstance(calls, list):
        _fail("synthesis_call_authority_invalid")
    locked_slots = route.get("receipt_call_slots")
    if (
        not isinstance(locked_slots, list)
        or len(calls) != len(locked_slots)
        or any(not isinstance(row, dict) for row in calls)
        or [row.get("call_slot_id") for row in calls] != locked_slots
    ):
        _fail("synthesis_call_authority_domain_mismatch")
    by_slot: dict[str, dict[str, Any]] = {}
    model = environment_lock["model"]
    for row in calls:
        assert isinstance(row, dict)
        if (
            set(row) != _CALL_ROW_KEYS
            or not isinstance(row.get("call_slot_id"), str)
            or not isinstance(row.get("role_id"), str)
            or not row["role_id"]
            or not isinstance(row.get("normalized_argv"), list)
        ):
            _fail("synthesis_call_authority_invalid")
        slot = row["call_slot_id"]
        _digest(row.get("prompt_sha256"), field=f"{slot}.prompt_sha256")
        _digest(row.get("contract_sha256"), field=f"{slot}.contract_sha256")
        argv = row["normalized_argv"]
        try:
            normalized = metering.normalize_codex_argv(argv)
        except metering.MeteringError as exc:
            raise SynthesisError("synthesis_call_authority_argv_invalid", slot) from exc
        if (
            list(normalized) != argv
            or not argv
            or argv[0] != chain["launcher_path"]
            or argv.count("--model") != 1
            or argv.index("--model") + 1 >= len(argv)
            or argv[argv.index("--model") + 1] != model
            or argv.count("--config") != 1
            or argv[argv.index("--config") + 1] != "model_reasoning_effort=high"
            or argv[-2:] != ["--", "-"]
        ):
            _fail("synthesis_call_authority_argv_invalid", slot)
        by_slot[slot] = {**row, "executable_chain": deepcopy(chain)}
    return authority, by_slot


def _evaluation_authority(
    call_authority: Mapping[str, object],
) -> Mapping[str, object]:
    environment = call_authority.get("environment_lock")
    authority = (
        environment.get("evaluation_authority")
        if isinstance(environment, Mapping)
        else None
    )
    if not isinstance(authority, Mapping):  # validated call authority invariant
        _fail("synthesis_evaluation_authority_invalid")
    return authority


def _validated_failure_record(
    record: object,
    *,
    attempt_id: str,
    call_slot_id: str,
) -> dict[str, Any]:
    value = _canonical_copy(record)
    if (
        not isinstance(value, dict)
        or set(value) != _FAILURE_RECORD_KEYS
        or value.get("schema_version") != "es_evaluator_call_failure.v1"
        or value.get("attempt_id") != attempt_id
        or value.get("call_slot_id") != call_slot_id
        or not isinstance(value.get("session_id"), str)
        or not value["session_id"]
        or not isinstance(value.get("provider_attempt_id"), str)
        or not value["provider_attempt_id"]
        or not isinstance(value.get("failure_code"), str)
        or _FAILURE_CODE_RE.fullmatch(value["failure_code"]) is None
    ):
        _fail("synthesis_review_failure_record_invalid", call_slot_id)
    _digest(value.get("receipt_digest"), field="failure.receipt_digest")
    return value


def _validated_receipt_rows(
    receipt_rows: object,
    receipt_bindings: Sequence[Mapping[str, object]],
    *,
    attempt_id: str,
    call_authority_by_slot: Mapping[str, Mapping[str, object]],
) -> list[dict[str, Any]]:
    values = _canonical_copy(receipt_rows)
    if not isinstance(values, list) or len(values) != len(receipt_bindings):
        _fail("synthesis_receipt_domain_invalid")
    with tempfile.TemporaryDirectory(prefix="es-synthesis-receipts-") as temporary:
        root = Path(temporary)
        receipt_paths: list[Path] = []
        expected_calls: list[dict[str, object]] = []
        normalized: list[dict[str, Any]] = []
        for ordinal, (binding, row) in enumerate(
            zip(receipt_bindings, values, strict=True), start=1
        ):
            slot = str(binding["call_slot_id"])
            if (
                not isinstance(row, dict)
                or set(row)
                != {
                    "call_slot_id",
                    "record",
                    "record_sha256",
                    "raw_jsonl",
                }
                or row["call_slot_id"] != slot
            ):
                _fail("synthesis_receipt_domain_invalid", slot)
            receipt = _canonical_copy(row["record"])
            if (
                not isinstance(receipt, dict)
                or row["record_sha256"] != _study_digest(receipt)
                or row["record_sha256"] != binding["receipt_sha256"]
                or receipt.get("block_id") != attempt_id
                or receipt.get("call_slot_id") != slot
                or not isinstance(row["raw_jsonl"], str)
            ):
                _fail("synthesis_receipt_digest_mismatch", slot)
            raw_path_member = receipt.get("raw_jsonl")
            if not isinstance(raw_path_member, Mapping) or not isinstance(
                raw_path_member.get("path"), str
            ):
                _fail("synthesis_receipt_binding_mismatch", slot)
            raw_relative = raw_path_member["path"]
            raw_parts = raw_relative.split("/")
            if (
                not raw_relative
                or raw_relative.startswith("/")
                or "\\" in raw_relative
                or any(part in {"", ".", ".."} for part in raw_parts)
                or PurePosixPath(raw_relative).is_absolute()
            ):
                _fail("synthesis_receipt_raw_path_invalid", slot)
            raw_path = root.joinpath(*PurePosixPath(raw_relative).parts)
            try:
                raw_path.resolve().relative_to(root.resolve())
            except (OSError, ValueError) as exc:
                raise SynthesisError(
                    "synthesis_receipt_raw_path_invalid", slot
                ) from exc
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(row["raw_jsonl"].encode("utf-8", "strict"))
            receipt_path = root / f"receipt-{ordinal:02d}.json"
            receipt_path.write_bytes(metering.canonical_json_bytes(receipt))
            receipt_paths.append(receipt_path)
            static_call = call_authority_by_slot.get(slot)
            process = receipt.get("process")
            if (
                not isinstance(static_call, Mapping)
                or not isinstance(process, Mapping)
                or process.get("argv") != static_call.get("normalized_argv")
                or receipt.get("role_id") != static_call.get("role_id")
                or receipt.get("prompt_sha256") != static_call.get("prompt_sha256")
                or receipt.get("contract_sha256")
                != static_call.get("contract_sha256")
                or receipt.get("executable_chain")
                != static_call.get("executable_chain")
                or not isinstance(receipt.get("provider_attempt_id"), str)
            ):
                _fail("synthesis_call_authority_binding_mismatch", slot)
            expected_calls.append(
                {
                    "study_id": "F1-ES",
                    "block_id": attempt_id,
                    "role_id": static_call["role_id"],
                    "call_slot_id": slot,
                    "provider_attempt_id": receipt["provider_attempt_id"],
                    "prompt_sha256": static_call["prompt_sha256"],
                    "contract_sha256": static_call["contract_sha256"],
                    "executable_chain": deepcopy(static_call["executable_chain"]),
                }
            )
            normalized.append(row)
        try:
            metering.validate_receipt_join(
                receipt_paths,
                expected_calls,
                evidence_root=root,
            )
        except metering.MeteringError as exc:
            raise SynthesisError("synthesis_receipt_join_invalid", exc.code) from exc
    return normalized


def _allocation_row(
    *,
    attempt_id: str,
    call_slot_id: str,
    sequence: int,
    previous_allocation_sha256: str | None,
    decision_lock_sha256: str,
    static_call_sha256: str,
    settlement: str,
    receipt_sha256: str | None,
) -> dict[str, Any]:
    """Build the controller event envelope that must be durable before launch.

    Synthesis can validate the event's content-addressed chain and its causal
    consequences.  The controller/metering seam remains responsible for making
    the event durable before it starts the provider process.
    """

    authority = {
        "schema_version": "es.controller_call_allocation.v1",
        "attempt_id": attempt_id,
        "sequence": sequence,
        "previous_allocation_sha256": previous_allocation_sha256,
        "call_slot_id": call_slot_id,
        "decision_lock_sha256": decision_lock_sha256,
        "static_call_sha256": static_call_sha256,
    }
    return {
        "schema_version": "es.call_allocation.v2",
        "call_slot_id": call_slot_id,
        "allocation_authority": authority,
        "allocation_sha256": canonical_sha256(authority),
        "settlement": settlement,
        "receipt_sha256": receipt_sha256,
    }


def _selected_call_routes(
    accounting: Mapping[str, object],
    decision_lock: Mapping[str, object],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...], bool | None]:
    route_contract = decision_lock.get("route_contract")
    arm_route_rows = accounting.get("arm_routes")
    if not isinstance(route_contract, Mapping) or not isinstance(
        arm_route_rows, list
    ):
        _fail("synthesis_call_allocation_route_invalid")
    terminal_routes = route_contract.get("terminal_routes")
    evaluation_routes = route_contract.get("evaluation_routes")
    if not isinstance(terminal_routes, list) or not isinstance(
        evaluation_routes, list
    ):
        _fail("synthesis_call_allocation_route_invalid")
    terminal_by_id = {
        row.get("route_id"): row
        for row in terminal_routes
        if isinstance(row, Mapping)
    }
    selected_by_arm: dict[str, tuple[str, ...]] = {}
    for selected in arm_route_rows:
        if not isinstance(selected, Mapping):
            _fail("synthesis_call_allocation_route_invalid")
        arm = selected.get("arm")
        route = terminal_by_id.get(selected.get("route_id"))
        slots = route.get("call_slots") if isinstance(route, Mapping) else None
        if (
            not isinstance(arm, str)
            or arm in selected_by_arm
            or not isinstance(route, Mapping)
            or route.get("arm") != arm
            or not isinstance(slots, list)
            or any(not isinstance(slot, str) for slot in slots)
        ):
            _fail("synthesis_call_allocation_route_invalid")
        selected_by_arm[arm] = tuple(cast(list[str], slots))

    evaluation_route_id = accounting.get("evaluation_route_id")
    if evaluation_route_id is None:
        return selected_by_arm, (), None
    evaluation_route = next(
        (
            row
            for row in evaluation_routes
            if isinstance(row, Mapping)
            and row.get("route_id") == evaluation_route_id
        ),
        None,
    )
    if not isinstance(evaluation_route, Mapping) or not isinstance(
        evaluation_route.get("call_slots"), list
    ):
        _fail("synthesis_call_allocation_route_invalid")
    slots = evaluation_route["call_slots"]
    if any(not isinstance(slot, str) for slot in slots) or type(
        evaluation_route.get("adjudication")
    ) is not bool:
        _fail("synthesis_call_allocation_route_invalid")
    return (
        selected_by_arm,
        tuple(cast(list[str], slots)),
        cast(bool, evaluation_route["adjudication"]),
    )


def _allocation_evidence_slots(
    evidence: Mapping[str, object],
) -> tuple[bool, set[str], set[str], set[str]]:
    public_replay = evidence.get("public_packet_replay_inputs")
    public_ready = public_replay is not None
    labels_to_arms: dict[str, str] = {}
    if public_ready:
        packet_index = (
            public_replay.get("packet_artifact_index")
            if isinstance(public_replay, Mapping)
            else None
        )
        packet_rows = (
            packet_index.get("packets")
            if isinstance(packet_index, Mapping)
            else None
        )
        if not isinstance(packet_rows, list):
            _fail("synthesis_call_allocation_evidence_invalid")
        for row in packet_rows:
            cell = row.get("cell") if isinstance(row, Mapping) else None
            label = row.get("opaque_label") if isinstance(row, Mapping) else None
            arm = cell.get("arm_id") if isinstance(cell, Mapping) else None
            if not isinstance(label, str) or arm not in _ARMS:
                _fail("synthesis_call_allocation_evidence_invalid")
            labels_to_arms[label] = str(arm)

    scorer_rows = evidence.get("scorer_settlements")
    review_rows = evidence.get("reviews")
    hard_rows = evidence.get("hard_evaluations")
    if not isinstance(scorer_rows, list) or not isinstance(
        review_rows, list
    ) or not isinstance(hard_rows, list):
        _fail("synthesis_call_allocation_evidence_invalid")
    scorer_slots: set[str] = set()
    for row in scorer_rows:
        label = row.get("opaque_label") if isinstance(row, Mapping) else None
        arm = labels_to_arms.get(str(label))
        if arm is None:
            _fail("synthesis_call_allocation_evidence_invalid")
        scorer_slots.add(f"EVAL.SCORER_{arm}")
    review_slots = {
        str(row["call_slot_id"])
        for row in review_rows
        if isinstance(row, Mapping) and isinstance(row.get("call_slot_id"), str)
    }
    if len(review_slots) != len(review_rows):
        _fail("synthesis_call_allocation_evidence_invalid")
    hard_arms = {
        str(row["arm_id"])
        for row in hard_rows
        if isinstance(row, Mapping) and row.get("arm_id") in _ARMS
    }
    if len(hard_arms) != len(hard_rows):
        _fail("synthesis_call_allocation_evidence_invalid")
    return public_ready, scorer_slots, review_slots, hard_arms


def _validated_call_allocations(
    rows: object,
    *,
    attempt_id: str,
    accounting: Mapping[str, object],
    decision_lock: Mapping[str, object],
    call_authority_by_slot: Mapping[str, Mapping[str, object]],
    evidence: Mapping[str, object],
    complete: bool,
) -> list[dict[str, Any]]:
    values = _canonical_copy(rows)
    receipt_bindings = accounting.get("receipt_bindings")
    if (
        not isinstance(values, list)
        or not isinstance(receipt_bindings, list)
        or any(not isinstance(row, Mapping) for row in receipt_bindings)
    ):
        _fail("synthesis_call_allocation_invalid")
    by_receipt_slot = {
        str(row["call_slot_id"]): row["receipt_sha256"] for row in receipt_bindings
    }
    treatment_by_arm, evaluation_slots, route_adjudication = (
        _selected_call_routes(accounting, decision_lock)
    )
    attempt_record = evidence.get("attempt_record")
    e2 = (
        attempt_record.get("e2_authority")
        if isinstance(attempt_record, Mapping)
        else None
    )
    arm_settlements = (
        e2.get("arm_settlements") if isinstance(e2, Mapping) else None
    )
    selected_arm_routes = accounting.get("arm_routes")
    route_contract = decision_lock.get("route_contract")
    terminal_routes = (
        route_contract.get("terminal_routes")
        if isinstance(route_contract, Mapping)
        else None
    )
    if (
        not isinstance(arm_settlements, list)
        or not isinstance(selected_arm_routes, list)
        or not isinstance(terminal_routes, list)
    ):
        _fail("synthesis_call_allocation_route_invalid")
    selected_route_id_by_arm = {
        row.get("arm"): row.get("route_id")
        for row in selected_arm_routes
        if isinstance(row, Mapping)
    }
    terminal_by_id = {
        row.get("route_id"): row
        for row in terminal_routes
        if isinstance(row, Mapping)
    }
    settled_arms: set[str] = set()
    for settlement in arm_settlements:
        cell = settlement.get("cell") if isinstance(settlement, Mapping) else None
        arm = cell.get("arm_id") if isinstance(cell, Mapping) else None
        status = settlement.get("status") if isinstance(settlement, Mapping) else None
        route = terminal_by_id.get(selected_route_id_by_arm.get(arm))
        if (
            not isinstance(arm, str)
            or arm in settled_arms
            or status not in {"completed", "failed"}
            or not isinstance(route, Mapping)
            or route.get("arm") != arm
            or route.get("completed") is not (status == "completed")
        ):
            _fail("synthesis_call_allocation_route_settlement_mismatch")
        settled_arms.add(arm)
    treatment_slots = {
        slot for slots in treatment_by_arm.values() for slot in slots
    }
    legal_slots = treatment_slots | set(evaluation_slots)
    decision_lock_sha256 = decision_lock_authority.decision_lock_digest(
        decision_lock
    )
    seen_slots: set[str] = set()
    seen_allocations: set[str] = set()
    normalized: list[dict[str, Any]] = []
    previous_allocation_sha256: str | None = None
    for sequence, row in enumerate(values, start=1):
        if not isinstance(row, dict) or set(row) != _CALL_ALLOCATION_KEYS:
            _fail("synthesis_call_allocation_invalid")
        slot = row.get("call_slot_id")
        authority = row.get("allocation_authority")
        static_call = (
            call_authority_by_slot.get(slot) if isinstance(slot, str) else None
        )
        if (
            not isinstance(slot, str)
            or slot not in legal_slots
            or slot in seen_slots
            or not isinstance(authority, dict)
            or set(authority) != _ALLOCATION_AUTHORITY_KEYS
            or authority.get("schema_version")
            != "es.controller_call_allocation.v1"
            or authority.get("attempt_id") != attempt_id
            or authority.get("sequence") != sequence
            or authority.get("previous_allocation_sha256")
            != previous_allocation_sha256
            or authority.get("call_slot_id") != slot
            or authority.get("decision_lock_sha256") != decision_lock_sha256
            or not isinstance(static_call, Mapping)
            or authority.get("static_call_sha256")
            != canonical_sha256(static_call)
            or row.get("schema_version") != "es.call_allocation.v2"
            or row.get("allocation_sha256") != canonical_sha256(authority)
            or row["allocation_sha256"] in seen_allocations
            or row.get("settlement")
            not in {"RECEIPT_FROZEN", "INTERRUPTED_IN_FLIGHT"}
        ):
            _fail("synthesis_call_allocation_invalid", str(slot))
        receipt_digest = row.get("receipt_sha256")
        if row["settlement"] == "RECEIPT_FROZEN":
            if (
                _digest(receipt_digest, field=f"allocation.{slot}.receipt_sha256")
                != by_receipt_slot.get(slot)
            ):
                _fail("synthesis_call_allocation_receipt_mismatch", slot)
        elif receipt_digest is not None or slot in by_receipt_slot:
            _fail("synthesis_call_allocation_receipt_mismatch", slot)
        seen_slots.add(slot)
        seen_allocations.add(row["allocation_sha256"])
        normalized.append(row)
        previous_allocation_sha256 = row["allocation_sha256"]
    if set(by_receipt_slot) - seen_slots:
        _fail("synthesis_call_allocation_receipt_mismatch")

    allocated_by_slot = {str(row["call_slot_id"]): row for row in normalized}
    positions = {
        str(row["call_slot_id"]): sequence
        for sequence, row in enumerate(normalized, start=1)
    }
    if not treatment_slots.issubset(allocated_by_slot):
        _fail("synthesis_call_allocation_treatment_undercount")
    for arm, arm_slots in treatment_by_arm.items():
        if [positions[slot] for slot in arm_slots] != sorted(
            positions[slot] for slot in arm_slots
        ):
            _fail("synthesis_call_allocation_arm_order_invalid", arm)
        for predecessor in arm_slots[:-1]:
            if allocated_by_slot[predecessor]["settlement"] != "RECEIPT_FROZEN":
                _fail("synthesis_call_allocation_arm_prefix_invalid", arm)

    public_ready, scorer_evidence, review_evidence, hard_evidence = (
        _allocation_evidence_slots(evidence)
    )
    if public_ready and settled_arms != set(_ARMS):
        _fail("synthesis_call_allocation_packet_terminal_domain_invalid")
    required_slots = (
        treatment_slots
        | set(by_receipt_slot)
        | scorer_evidence
        | review_evidence
    )
    if not required_slots.issubset(allocated_by_slot):
        _fail("synthesis_call_allocation_evidence_undercount")

    scorer_slots = {
        slot for slot in evaluation_slots if slot.startswith("EVAL.SCORER_")
    }
    initial_slots = {
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    } & set(evaluation_slots)
    adjudicator_slot = (
        "EVAL.ADJUDICATOR"
        if "EVAL.ADJUDICATOR" in evaluation_slots
        else None
    )
    integrated_slot = (
        "EVAL.INTEGRATED_REVIEW"
        if "EVAL.INTEGRATED_REVIEW" in evaluation_slots
        else None
    )
    allocated_scorers = scorer_slots & set(allocated_by_slot)
    allocated_initials = initial_slots & set(allocated_by_slot)
    adjudicator_allocated = (
        adjudicator_slot is not None and adjudicator_slot in allocated_by_slot
    )
    integrated_allocated = (
        integrated_slot is not None and integrated_slot in allocated_by_slot
    )

    def _stage_precedes(left: set[str], right: set[str]) -> bool:
        present_left = left & set(positions)
        present_right = right & set(positions)
        return not present_left or not present_right or max(
            positions[slot] for slot in present_left
        ) < min(positions[slot] for slot in present_right)

    if not _stage_precedes(treatment_slots, scorer_slots) or not _stage_precedes(
        scorer_slots, initial_slots
    ):
        _fail("synthesis_call_allocation_stage_order_invalid")
    later_review_slots = {
        slot
        for slot in (adjudicator_slot, integrated_slot)
        if slot is not None
    }
    if not _stage_precedes(initial_slots, later_review_slots):
        _fail("synthesis_call_allocation_stage_order_invalid")
    if (
        adjudicator_slot is not None
        and integrated_slot is not None
        and not _stage_precedes({adjudicator_slot}, {integrated_slot})
    ):
        _fail("synthesis_call_allocation_stage_order_invalid")

    if public_ready or allocated_scorers:
        if any(
            allocated_by_slot[slot]["settlement"] != "RECEIPT_FROZEN"
            for slot in treatment_slots
        ):
            _fail("synthesis_call_allocation_treatment_barrier_invalid")
    if allocated_scorers and not public_ready:
        _fail("synthesis_call_allocation_packet_barrier_invalid")
    if (
        allocated_initials
        or adjudicator_allocated
        or integrated_allocated
        or hard_evidence
    ):
        if (
            scorer_evidence != scorer_slots
            or allocated_scorers != scorer_slots
            or any(
                allocated_by_slot[slot]["settlement"] != "RECEIPT_FROZEN"
                for slot in scorer_slots
            )
        ):
            _fail("synthesis_call_allocation_scorer_barrier_invalid")
    if adjudicator_allocated or integrated_allocated or hard_evidence:
        if (
            review_evidence & initial_slots != initial_slots
            or allocated_initials != initial_slots
            or any(
                allocated_by_slot[slot]["settlement"] != "RECEIPT_FROZEN"
                for slot in initial_slots
            )
        ):
            _fail("synthesis_call_allocation_initial_barrier_invalid")
    if adjudicator_allocated and route_adjudication is not True:
        _fail("synthesis_call_allocation_adjudicator_forbidden")
    if (integrated_allocated or hard_evidence) and route_adjudication is True:
        if (
            adjudicator_slot is None
            or adjudicator_slot not in review_evidence
            or adjudicator_slot not in allocated_by_slot
            or allocated_by_slot[adjudicator_slot]["settlement"]
            != "RECEIPT_FROZEN"
        ):
            _fail("synthesis_call_allocation_adjudicator_barrier_invalid")
    if integrated_allocated and hard_evidence != set(_ARMS):
        _fail("synthesis_call_allocation_hard_barrier_invalid")

    unsettled = {
        slot
        for slot, row in allocated_by_slot.items()
        if row["settlement"] == "INTERRUPTED_IN_FLIGHT"
    }
    unsettled_treatment = unsettled & treatment_slots
    unsettled_scorers = unsettled & scorer_slots
    unsettled_initials = unsettled & initial_slots
    unsettled_serial = unsettled - (
        treatment_slots | scorer_slots | initial_slots
    )
    if unsettled_treatment and (
        public_ready
        or allocated_scorers
        or allocated_initials
        or adjudicator_allocated
        or integrated_allocated
        or hard_evidence
    ):
        _fail("synthesis_call_allocation_frontier_invalid")
    if unsettled_scorers and (
        allocated_initials
        or adjudicator_allocated
        or integrated_allocated
        or hard_evidence
    ):
        _fail("synthesis_call_allocation_frontier_invalid")
    if unsettled_initials and (
        adjudicator_allocated or integrated_allocated or hard_evidence
    ):
        _fail("synthesis_call_allocation_frontier_invalid")
    if len(unsettled_serial) > 1:
        _fail("synthesis_call_allocation_frontier_invalid")

    if complete:
        if (
            set(allocated_by_slot) != legal_slots
            or set(by_receipt_slot) != legal_slots
            or any(
                row["settlement"] != "RECEIPT_FROZEN" for row in normalized
            )
        ):
            _fail("synthesis_call_allocation_complete_mismatch")
    return normalized


def _derive_hard_freeze(
    replay: Mapping[str, object], *, arm: str
) -> hard_contract.HardEvaluationFreeze:
    frozen_registry = replay.get("frozen_registry")
    candidate_claims = replay.get("candidate_claims")
    evaluator_observations = replay.get("evaluator_observations")
    proof_rows = replay.get("proof_rows")
    frozen_proof_authority = replay.get("frozen_proof_authority")
    trusted_product_freeze_digest = replay.get("trusted_product_freeze_digest")
    evaluator_identity_digest = replay.get("evaluator_identity_digest")
    task_identity_digest = replay.get("task_identity_digest")
    fixture_identity_digest = replay.get("fixture_identity_digest")
    if (
        set(replay) != _HARD_REPLAY_KEYS
        or replay.get("schema_version") != "es.hard_evaluation_replay_inputs.v1"
        or not isinstance(frozen_registry, list)
        or any(not isinstance(value, str) or not value for value in frozen_registry)
        or frozen_registry != sorted(set(frozen_registry))
        or not isinstance(candidate_claims, Mapping)
        or not isinstance(evaluator_observations, list)
        or any(not isinstance(row, Mapping) for row in evaluator_observations)
        or not isinstance(proof_rows, list)
        or any(not isinstance(row, Mapping) for row in proof_rows)
        or not isinstance(frozen_proof_authority, list)
        or any(not isinstance(row, Mapping) for row in frozen_proof_authority)
        or not isinstance(trusted_product_freeze_digest, str)
        or not isinstance(evaluator_identity_digest, str)
        or not isinstance(task_identity_digest, str)
        or not isinstance(fixture_identity_digest, str)
    ):
        _fail("synthesis_hard_evaluation_invalid", arm)
    try:
        return hard_contract.derive_hard_evaluation(
            candidate_claims=cast(Mapping[str, Any], candidate_claims),
            evaluator_observations=cast(
                Sequence[Mapping[str, Any]], evaluator_observations
            ),
            proof_rows=cast(Sequence[Mapping[str, Any]], proof_rows),
            frozen_registry=set(cast(list[str], frozen_registry)),
            trusted_product_freeze_digest=trusted_product_freeze_digest,
            evaluator_identity_digest=evaluator_identity_digest,
            task_identity_digest=task_identity_digest,
            fixture_identity_digest=fixture_identity_digest,
            frozen_proof_authority=cast(
                Sequence[Mapping[str, Any]], frozen_proof_authority
            ),
        )
    except (TypeError, hard_contract.HardContractError) as exc:
        raise SynthesisError("synthesis_hard_evaluation_invalid", arm) from exc


def _hard_row_from_spec(
    arm: str,
    spec: Mapping[str, object],
) -> dict[str, Any]:
    status = spec.get("trusted_product_freeze_status")
    if status == "PRESENT" and set(spec) == {
        "trusted_product_freeze_status",
        "replay_inputs",
    }:
        replay = _canonical_copy(spec["replay_inputs"])
        if not isinstance(replay, dict):
            _fail("synthesis_hard_evaluation_invalid", arm)
        freeze = _derive_hard_freeze(replay, arm=arm)
        return {
            "schema_version": "es.hard_evaluation_evidence.v1",
            "arm_id": arm,
            "trusted_product_freeze_status": "PRESENT",
            "replay_inputs": replay,
            "freeze": freeze.record,
            "freeze_sha256": freeze.digest,
            "evaluation": freeze.evaluation,
            "evaluation_sha256": freeze.evaluation_digest,
        }
    if status == "MISSING" and set(spec) == {
        "trusted_product_freeze_status",
        "absence_authority",
    }:
        return {
            "schema_version": "es.hard_evaluation_evidence.v1",
            "arm_id": arm,
            "trusted_product_freeze_status": "MISSING",
            "absence_authority": _canonical_copy(spec["absence_authority"]),
        }
    _fail("synthesis_hard_evaluation_invalid", arm)


def _validated_hard_evaluations(
    rows: object,
    *,
    labels_by_arm: Mapping[str, str],
    attempt_record: Mapping[str, object],
    evaluation_authority: Mapping[str, object],
    require_complete: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, hard_contract.HardEvaluationFreeze | None]]:
    values = _canonical_copy(rows)
    if (
        not isinstance(values, list)
        or len(values) > 4
        or (require_complete and len(values) != 4)
    ):
        _fail("synthesis_hard_evaluation_domain_invalid")
    e2 = attempt_record.get("e2_authority")
    settlements = e2.get("arm_settlements") if isinstance(e2, Mapping) else None
    if not isinstance(settlements, list):
        _fail("synthesis_hard_evaluation_domain_invalid")
    settlement_by_arm = {
        row.get("cell", {}).get("arm_id"): row
        for row in settlements
        if isinstance(row, Mapping) and isinstance(row.get("cell"), Mapping)
    }
    freezes: dict[str, hard_contract.HardEvaluationFreeze | None] = {}
    shared_authority: tuple[str, str, str, str] | None = None
    for arm, row in zip(_ARMS[: len(values)], values, strict=True):
        if (
            not isinstance(row, dict)
            or row.get("schema_version") != "es.hard_evaluation_evidence.v1"
            or row.get("arm_id") != arm
        ):
            _fail("synthesis_hard_evaluation_invalid", arm)
        status = row.get("trusted_product_freeze_status")
        if status == "MISSING":
            absence = row.get("absence_authority")
            settlement = settlement_by_arm.get(arm)
            if (
                set(row) != _HARD_MISSING_KEYS
                or not isinstance(absence, dict)
                or set(absence) != _HARD_ABSENCE_KEYS
                or absence.get("schema_version")
                != "es.trusted_product_freeze_absence.v1"
                or absence.get("reason") != "TERMINAL_TREATMENT_FAILURE"
                or absence.get("cell") != {"arm_id": arm, "rep": 1}
                or not isinstance(settlement, Mapping)
                or settlement.get("status") != "failed"
                or absence.get("terminal_row_digest")
                != settlement.get("terminal_row_digest")
            ):
                _fail("synthesis_hard_evaluation_absence_invalid", arm)
            freezes[arm] = None
            continue
        if status != "PRESENT" or set(row) != _HARD_PRESENT_KEYS:
            _fail("synthesis_hard_evaluation_invalid", arm)
        replay = row.get("replay_inputs")
        if not isinstance(replay, dict):
            _fail("synthesis_hard_evaluation_invalid", arm)
        reconstructed = _derive_hard_freeze(replay, arm=arm)
        if (
            reconstructed.evaluator_identity_digest
            != evaluation_authority.get("hard_evaluator_identity_digest")
            or reconstructed.task_identity_digest
            != evaluation_authority.get("hard_task_identity_digest")
            or reconstructed.fixture_identity_digest
            != evaluation_authority.get("hard_fixture_identity_digest")
        ):
            _fail("synthesis_hard_evaluation_authority_mismatch", arm)
        if (
            reconstructed.candidate_id != labels_by_arm.get(arm)
            or row.get("freeze") != reconstructed.record
            or row.get("freeze_sha256") != reconstructed.digest
            or row.get("evaluation") != reconstructed.evaluation
            or row.get("evaluation_sha256") != reconstructed.evaluation_digest
        ):
            _fail("synthesis_hard_evaluation_replay_mismatch", arm)
        authority = (
            reconstructed.evaluator_identity_digest,
            reconstructed.task_identity_digest,
            reconstructed.fixture_identity_digest,
            reconstructed.proof_authority_digest,
        )
        if shared_authority is None:
            shared_authority = authority
        elif authority != shared_authority:
            _fail("synthesis_hard_evaluation_authority_mismatch", arm)
        freezes[arm] = reconstructed
    return values, freezes


def _trial_cell(value: object, *, field: str) -> TrialCellKey:
    if not isinstance(value, dict) or set(value) != {"arm_id", "rep"}:
        _fail("synthesis_private_join_invalid", field)
    try:
        return TrialCellKey(value["arm_id"], value["rep"])
    except (TypeError, ValueError) as exc:
        raise SynthesisError("synthesis_private_join_invalid", field) from exc


def _validated_public_packet_replay(
    value: object,
    *,
    attempt_record: Mapping[str, object],
) -> tuple[
    tuple[TrialCellKey, ...],
    dict[str, Any],
    dict[str, str],
    dict[str, str],
]:
    """Validate packet authority without relying on a private join projection."""

    replay = _canonical_copy(value)
    if (
        not isinstance(replay, dict)
        or set(replay) != _PUBLIC_PACKET_REPLAY_KEYS
        or replay.get("schema_version") != "es.public_packet_replay_inputs.v1"
        or not isinstance(replay.get("request_cell_domain"), list)
        or not isinstance(replay.get("packet_artifact_index"), dict)
    ):
        _fail("synthesis_public_packet_replay_invalid")
    cells = tuple(
        _trial_cell(row, field="public_packet_request_cell_domain")
        for row in replay["request_cell_domain"]
    )
    if cells != tuple(TrialCellKey(arm, 1) for arm in _ARMS):
        _fail("synthesis_public_packet_replay_invalid", "cell_domain")
    packet_index = replay["packet_artifact_index"]
    if (
        set(packet_index) != _PACKET_INDEX_KEYS
        or packet_index.get("schema_version")
        != "trial.packet_artifact_index.v1"
    ):
        _fail("synthesis_public_packet_replay_invalid", "packet_index")
    digests = {
        field: _digest(packet_index.get(field), field=f"packet_index.{field}")
        for field in (
            "trial_request_digest",
            "header_row_digest",
            "evidence_frozen_row_digest",
            "checks_frozen_row_digest",
            "packets_frozen_row_digest",
            "sealed_opaque_label_map_digest",
            "packet_set_digest",
        )
    }
    e2 = attempt_record.get("e2_authority")
    if (
        not isinstance(e2, Mapping)
        or digests["trial_request_digest"]
        != attempt_record.get("trial_request_digest")
        or digests["header_row_digest"] != e2.get("header_row_digest")
    ):
        _fail("synthesis_public_packet_replay_invalid", "attempt_authority")
    index_rows = packet_index.get("packets")
    if not isinstance(index_rows, list) or len(index_rows) != len(_ARMS):
        _fail("synthesis_public_packet_replay_invalid", "packet_domain")
    request_hex = digests["trial_request_digest"].removeprefix("sha256:")
    labels_by_arm: dict[str, str] = {}
    packet_digests_by_arm: dict[str, str] = {}
    frozen_rows: list[dict[str, object]] = []
    paths: list[str] = []
    for arm, expected_cell, row in zip(_ARMS, cells, index_rows, strict=True):
        if not isinstance(row, dict) or set(row) != _PACKET_INDEX_ROW_KEYS:
            _fail("synthesis_public_packet_replay_invalid", arm)
        cell = _trial_cell(row.get("cell"), field="public_packet_index_cell")
        label = row.get("opaque_label")
        if cell != expected_cell or not isinstance(label, str):
            _fail("synthesis_public_packet_replay_invalid", arm)
        try:
            TrialOpaqueLabelBinding(cell=cell, opaque_label=label)
        except (TypeError, ValueError) as exc:
            raise SynthesisError(
                "synthesis_public_packet_replay_invalid", arm
            ) from exc
        packet_digest = _digest(
            row.get("packet_digest"), field=f"packet_index.{arm}.packet_digest"
        )
        expected_path = (
            f"artifacts/trials/{request_hex}/packets/"
            f"{packet_digest.removeprefix('sha256:')}.json"
        )
        if row.get("packet_relpath") != expected_path:
            _fail("synthesis_public_packet_replay_invalid", arm)
        labels_by_arm[arm] = label
        packet_digests_by_arm[arm] = packet_digest
        paths.append(expected_path)
        frozen_rows.append(
            {
                "cell": cell.record,
                "opaque_label": label,
                "packet_digest": packet_digest,
            }
        )
    if (
        len(set(labels_by_arm.values())) != len(_ARMS)
        or len(set(packet_digests_by_arm.values())) != len(_ARMS)
        or len(set(paths)) != len(_ARMS)
        or canonical_sha256(frozen_rows) != digests["packet_set_digest"]
    ):
        _fail("synthesis_public_packet_replay_invalid", "packet_bijection")
    return cells, packet_index, labels_by_arm, packet_digests_by_arm


def _validated_public_packet_evidence(
    replay_value: object,
    packet_rows_value: object,
    *,
    attempt_record: Mapping[str, object],
) -> tuple[
    list[dict[str, Any]],
    dict[str, str],
    dict[str, str],
    dict[str, tuple[str, ...]],
    str,
    str,
]:
    (
        _cells,
        packet_index,
        labels_by_arm,
        packet_digests_by_arm,
    ) = _validated_public_packet_replay(
        replay_value,
        attempt_record=attempt_record,
    )
    packet_rows = _canonical_copy(packet_rows_value)
    if (
        not isinstance(packet_rows, list)
        or len(packet_rows) != len(_ARMS)
        or [
            row.get("arm_id")
            for row in packet_rows
            if isinstance(row, Mapping)
        ]
        != list(_ARMS)
    ):
        _fail("synthesis_packet_domain_invalid")
    citable_items: dict[str, tuple[str, ...]] = {}
    normalized: list[dict[str, Any]] = []
    for arm, row in zip(_ARMS, packet_rows, strict=True):
        if not isinstance(row, dict) or set(row) != {
            "arm_id",
            "packet",
            "packet_sha256",
        }:
            _fail("synthesis_packet_invalid", arm)
        packet = validate_trial_evaluation_packet(row["packet"])
        digest = canonical_sha256(packet)
        if (
            row["packet_sha256"] != digest
            or digest != packet_digests_by_arm[arm]
            or packet["evaluation_id"] != labels_by_arm[arm]
        ):
            _fail("synthesis_packet_digest_mismatch", arm)
        normalized.append(
            {"arm_id": arm, "packet": packet, "packet_sha256": digest}
        )
        citable_items[labels_by_arm[arm]] = tuple(packet["citable_item_ids"])
    return (
        normalized,
        labels_by_arm,
        packet_digests_by_arm,
        citable_items,
        str(packet_index["packet_set_digest"]),
        str(packet_index["evidence_frozen_row_digest"]),
    )


def _validated_private_join(
    value: object,
    replay_value: object,
    public_replay_value: object,
    *,
    attempt_record: Mapping[str, object],
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> tuple[blinding.PrivateBlindingJoin, dict[str, str]]:
    """Rebuild only the private projection over validated packet authority."""

    replay = _canonical_copy(replay_value)
    if (
        not isinstance(replay, dict)
        or set(replay) != _PRIVATE_REPLAY_KEYS
        or replay.get("schema_version") != "es.private_blinding_replay_inputs.v2"
    ):
        _fail("synthesis_private_join_invalid", "replay_inputs")
    sealed_record = replay["sealed_opaque_label_map"]
    if (
        not isinstance(sealed_record, dict)
        or set(sealed_record) != {"schema_version", "bindings"}
        or sealed_record.get("schema_version") != "trial_opaque_label_map.v1"
        or not isinstance(sealed_record.get("bindings"), list)
    ):
        _fail("synthesis_private_join_invalid", "replay_inputs")
    cells, packet_index, _public_labels, _public_digests = (
        _validated_public_packet_replay(
            public_replay_value,
            attempt_record=attempt_record,
        )
    )
    try:
        bindings_list: list[TrialOpaqueLabelBinding] = []
        for row in sealed_record["bindings"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"cell", "opaque_label"}
                or not isinstance(row.get("opaque_label"), str)
            ):
                _fail(
                    "synthesis_private_join_invalid", "sealed_opaque_label_map"
                )
            bindings_list.append(
                TrialOpaqueLabelBinding(
                    cell=_trial_cell(
                        row.get("cell"), field="sealed_opaque_label_map"
                    ),
                    opaque_label=row["opaque_label"],
                )
            )
        sealed = SealedTrialOpaqueLabelMap(
            bindings=tuple(bindings_list),
            digest=canonical_sha256(sealed_record),
        )
    except (TypeError, ValueError) as exc:
        raise SynthesisError(
            "synthesis_private_join_invalid", "sealed_opaque_label_map"
        ) from exc
    attempt_id = str(attempt_record.get("attempt_id"))
    schedule_rows = randomization_manifest.get("attempts")
    if not isinstance(schedule_rows, list):
        _fail("synthesis_private_join_invalid", "schedule")
    matches = [
        row
        for row in schedule_rows
        if isinstance(row, dict) and row.get("attempt_id") == attempt_id
    ]
    if len(matches) != 1:
        _fail("synthesis_private_join_invalid", "schedule")
    schedule_row = matches[0]
    try:
        attempt = blinding.AttemptPackageSchedule(
            attempt_id=attempt_id,
            arm_order=tuple(schedule_row["arm_order"]),
            opaque_package_order=tuple(schedule_row["opaque_package_order"]),
            randomization_row_digest=decision_lock_authority.decision_lock_digest(
                schedule_row
            ),
            decision_lock_digest=decision_lock_authority.decision_lock_digest(
                decision_lock
            ),
        )
    except (KeyError, TypeError, blinding.BlindingJoinError) as exc:
        raise SynthesisError("synthesis_private_join_invalid", "schedule") from exc
    e2 = attempt_record.get("e2_authority")
    if (
        not isinstance(packet_index, dict)
        or not isinstance(e2, Mapping)
        or packet_index.get("trial_request_digest")
        != attempt_record.get("trial_request_digest")
        or packet_index.get("header_row_digest") != e2.get("header_row_digest")
    ):
        _fail("synthesis_private_join_invalid", "packet_authority")
    try:
        reconstructed = blinding.build_private_blinding_join(
            attempt=attempt,
            randomization_manifest=randomization_manifest,
            decision_lock=decision_lock,
            expected_bindings=expected_bindings,
            request_cell_domain=cells,
            sealed_opaque_labels=sealed,
            packet_index=packet_index,
        )
    except (TypeError, blinding.BlindingJoinError) as exc:
        raise SynthesisError("synthesis_private_join_invalid", str(exc)) from exc
    join = _canonical_copy(value)
    if join != reconstructed.record:
        _fail("synthesis_private_join_binding_mismatch")
    return reconstructed, {
        row.arm_id: row.opaque_label for row in reconstructed.rows
    }


def _labels_from_validated_join(value: Mapping[str, object]) -> dict[str, str]:
    rows = value.get("rows")
    assert isinstance(rows, list)
    return {
        str(row["arm_id"]): str(row["opaque_label"])
        for row in rows
        if isinstance(row, Mapping)
    }


def _validated_scorer_settlements(
    *,
    scorer_rows: object,
    attempt_record: Mapping[str, object],
    labels_by_arm: Mapping[str, str],
    packet_digests_by_arm: Mapping[str, str],
    packet_evidence_frozen_digest: str,
    evaluation_authority: Mapping[str, object],
    require_complete: bool = True,
) -> list[dict[str, Any]]:
    values = _canonical_copy(scorer_rows)
    if (
        not isinstance(values, list)
        or len(values) > 4
        or (require_complete and len(values) != 4)
    ):
        _fail("synthesis_scorer_domain_invalid")
    e2 = attempt_record.get("e2_authority")
    if not isinstance(e2, Mapping):
        _fail("synthesis_scorer_domain_invalid")
    authority_rows = e2.get("scorer_settlements")
    arm_settlements = e2.get("arm_settlements")
    if (
        not isinstance(authority_rows, list)
        or not isinstance(arm_settlements, list)
        or len(authority_rows) != len(values)
        or (require_complete and len(authority_rows) != 4)
    ):
        _fail("synthesis_scorer_domain_invalid")
    authority_by_label = {
        row.get("opaque_label"): row
        for row in authority_rows
        if isinstance(row, Mapping)
    }
    expected_labels = {row.get("opaque_label") for row in authority_rows}
    if set(authority_by_label) != expected_labels:
        _fail("synthesis_scorer_domain_invalid")
    authority_order = [str(row["opaque_label"]) for row in authority_rows]
    if [row.get("opaque_label") for row in values if isinstance(row, Mapping)] != (
        authority_order
    ):
        _fail("synthesis_scorer_domain_invalid")
    arm_by_label = {label: arm for arm, label in labels_by_arm.items()}
    terminal_by_arm = {
        row.get("cell", {}).get("arm_id"): row.get("terminal_row_digest")
        for row in arm_settlements
        if isinstance(row, Mapping) and isinstance(row.get("cell"), Mapping)
    }

    if not values:
        return []

    score_values: list[dict[str, Any]] = []
    for projection in values:
        if not isinstance(projection, dict) or set(projection) != {
            "opaque_label",
            "settlement_row",
            "score_row",
        }:
            _fail("synthesis_scorer_projection_invalid")
        label = str(projection["opaque_label"])
        arm = arm_by_label.get(label)
        if arm is None:
            _fail("synthesis_scorer_projection_invalid")
        settlement = projection["settlement_row"]
        score = projection["score_row"]
        if (
            not isinstance(settlement, dict)
            or set(settlement)
            != {
                "schema_version",
                "sequence",
                "previous_row_digest",
                "row_digest",
                "kind",
                "recorded_at",
                "payload",
            }
            or settlement.get("schema_version") != TRIAL_EVENT_LEDGER_SCHEMA
            or settlement.get("kind") != "score_settled"
            or type(settlement.get("sequence")) is not int
            or settlement["sequence"] < 1
            or not isinstance(settlement.get("recorded_at"), str)
            or not settlement["recorded_at"].endswith("Z")
            or not isinstance(settlement.get("payload"), dict)
            or set(settlement["payload"])
            != {
                "opaque_label",
                "score_row_content_digest",
                "terminal_attempt_settlement_row_digest",
            }
            or settlement["payload"]["opaque_label"] != label
            or not isinstance(score, dict)
        ):
            _fail("synthesis_scorer_projection_invalid", arm)
        previous = settlement["previous_row_digest"]
        if previous is not None:
            _digest(previous, field=f"scorer.{arm}.previous_row_digest")
        terminal = settlement["payload"]["terminal_attempt_settlement_row_digest"]
        if not isinstance(terminal, str):
            _fail("synthesis_scorer_binding_mismatch", arm)
        _digest(terminal, field=f"scorer.{arm}.terminal_settlement")
        settlement_preimage = {
            key: value for key, value in settlement.items() if key != "row_digest"
        }
        authority = authority_by_label[label]
        if (
            settlement["row_digest"] != canonical_sha256(settlement_preimage)
            or settlement["row_digest"] != authority.get("settlement_row_digest")
            or settlement["payload"]["score_row_content_digest"]
            != score.get("row_content_digest")
            or terminal != terminal_by_arm.get(arm)
        ):
            _fail("synthesis_scorer_binding_mismatch", arm)
        score_values.append(score)

    with tempfile.TemporaryDirectory(prefix="es-synthesis-scores-") as temporary:
        path = Path(temporary) / "scores.ndjson"
        path.write_bytes(b"".join(canonical_report_bytes(row) for row in score_values))
        try:
            checked_scores = load_trial_score_rows(path, validation_mode="complete")
        except (OSError, ValueError, TrialLedgerError) as exc:
            raise SynthesisError("synthesis_scorer_row_invalid") from exc
    checked_by_label = {row["evaluation_label"]: row for row in checked_scores}
    shared_authority: tuple[object, object, object] | None = None
    for projection in values:
        label = str(projection["opaque_label"])
        arm = arm_by_label[label]
        score = checked_by_label.get(label)
        if (
            score is None
            or projection["score_row"] != score
            or score["trial_request_digest"] != attempt_record["trial_request_digest"]
            or score["evaluation_packet_digest"] != packet_digests_by_arm[arm]
            or score["evidence_frozen_digest"]
            != packet_evidence_frozen_digest
            or score["evaluation_digest"]
            != evaluation_authority.get("scorer_evaluation_digest")
            or score["scorer_identity_digest"]
            != evaluation_authority.get("scorer_identity_digest")
        ):
            _fail("synthesis_scorer_binding_mismatch", arm)
        authority = (
            score["evaluation_digest"],
            score["evidence_frozen_digest"],
            score["scorer_identity_digest"],
        )
        if shared_authority is None:
            shared_authority = authority
        elif authority != shared_authority:
            _fail("synthesis_scorer_authority_mismatch", arm)
    return values


def build_attempt_evidence_index(
    *,
    attempt_record: Mapping[str, object],
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    private_join: blinding.PrivateBlindingJoin,
    public_packet_replay_inputs: Mapping[str, object],
    private_blinding_replay_inputs: Mapping[str, object],
    packets_by_arm: Mapping[str, Mapping[str, object]],
    review_records_by_slot: Mapping[str, Mapping[str, object]],
    adjudication_payload: Mapping[str, object] | None,
    integrated_payload: Mapping[str, object],
    hard_evidence_by_arm: Mapping[str, Mapping[str, object]],
    oriented_primary: blinding.OrientedPrimaryPair,
    hard_primary_outcome: hard_contract.HardPrimaryOutcome,
    receipts_by_slot: Mapping[str, Mapping[str, object]],
    raw_jsonl_by_slot: Mapping[str, bytes],
    frozen_call_authority: Mapping[str, object],
    call_allocations: Sequence[Mapping[str, object]],
    elapsed_ms_by_slot: Mapping[str, int],
    scorer_settlement_rows_by_label: Mapping[str, Mapping[str, object]],
    score_rows_by_label: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    """Freeze one complete attempt into the only synthesis input shape."""

    lock, schedule, _schema_digest = _checked_contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    try:
        checked_attempt = attempts.validate_attempt_record(
            attempt_record,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=expected_bindings,
        )
    except attempts.AttemptAccountingError as exc:
        raise SynthesisError("synthesis_attempt_record_invalid", exc.code) from exc
    if checked_attempt["status"] != "VALID":
        _fail("synthesis_complete_index_requires_valid_attempt")
    if type(private_join) is not blinding.PrivateBlindingJoin:
        raise TypeError("private join must be exact PrivateBlindingJoin")
    if type(oriented_primary) is not blinding.OrientedPrimaryPair:
        raise TypeError("oriented primary must be exact OrientedPrimaryPair")
    if type(hard_primary_outcome) is not hard_contract.HardPrimaryOutcome:
        raise TypeError("hard primary must be exact HardPrimaryOutcome")
    attempt_id = str(checked_attempt["attempt_id"])
    call_authority, call_authority_by_slot = _validated_call_authority(
        frozen_call_authority,
        decision_lock=lock,
        expected_bindings=expected_bindings,
    )
    evaluation_authority = _evaluation_authority(call_authority)
    reconstructed_join, labels_by_arm = _validated_private_join(
        private_join.record,
        private_blinding_replay_inputs,
        public_packet_replay_inputs,
        attempt_record=checked_attempt,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=expected_bindings,
    )
    if (
        reconstructed_join.attempt.attempt_id != attempt_id
        or reconstructed_join.decision_lock_digest
        != decision_lock_authority.decision_lock_digest(lock)
        or reconstructed_join.randomization_row_digest
        != checked_attempt["randomization_row_sha256"]
        or reconstructed_join.trial_request_digest
        != checked_attempt["trial_request_digest"]
    ):
        _fail("synthesis_private_join_binding_mismatch")
    private_join = reconstructed_join
    if set(packets_by_arm) != set(_ARMS):
        _fail("synthesis_packet_domain_invalid")
    (
        packet_rows,
        public_labels_by_arm,
        packet_digests_by_arm,
        citable_items,
        public_packet_set_digest,
        packet_evidence_frozen_digest,
    ) = _validated_public_packet_evidence(
        public_packet_replay_inputs,
        [
            {
                "arm_id": arm,
                "packet": packets_by_arm[arm],
                "packet_sha256": canonical_sha256(packets_by_arm[arm]),
            }
            for arm in _ARMS
        ],
        attempt_record=checked_attempt,
    )
    if (
        public_labels_by_arm != labels_by_arm
        or public_packet_set_digest != private_join.packet_set_digest
    ):
        _fail("synthesis_private_join_binding_mismatch")

    expected_labels = {labels_by_arm[arm] for arm in _ARMS}
    if (
        set(scorer_settlement_rows_by_label) != expected_labels
        or set(score_rows_by_label) != expected_labels
    ):
        _fail("synthesis_scorer_domain_invalid")
    checked_e2 = checked_attempt["e2_authority"]
    assert isinstance(checked_e2, Mapping)
    checked_scorer_authority = checked_e2["scorer_settlements"]
    assert isinstance(checked_scorer_authority, list)
    assert all(isinstance(row, Mapping) for row in checked_scorer_authority)
    scorer_rows = _validated_scorer_settlements(
        scorer_rows=[
            {
                "opaque_label": str(authority_row["opaque_label"]),
                "settlement_row": scorer_settlement_rows_by_label[
                    str(authority_row["opaque_label"])
                ],
                "score_row": score_rows_by_label[
                    str(authority_row["opaque_label"])
                ],
            }
            for authority_row in checked_scorer_authority
        ],
        attempt_record=checked_attempt,
        labels_by_arm=labels_by_arm,
        packet_digests_by_arm=packet_digests_by_arm,
        packet_evidence_frozen_digest=packet_evidence_frozen_digest,
        evaluation_authority=evaluation_authority,
    )

    accounting = checked_attempt["accounting"]
    assert isinstance(accounting, Mapping)
    review_settlements = accounting["review_settlements"]
    assert isinstance(review_settlements, list)
    review_rows: list[dict[str, Any]] = []
    prior_records: list[dict[str, Any]] = []
    for settlement in review_settlements:
        assert isinstance(settlement, Mapping)
        slot = str(settlement["call_slot_id"])
        source = review_records_by_slot.get(slot)
        if source is None:
            _fail("synthesis_review_missing", slot)
        record = _canonical_copy(source)
        digest = _study_digest(record)
        if digest != settlement["record_sha256"]:
            _fail("synthesis_review_digest_mismatch", slot)
        if settlement["status"] == "SUCCEEDED":
            try:
                record = reviews.validate_review_record(
                    record,
                    citable_item_ids_by_label=citable_items,
                    existing_records=prior_records,
                )
            except reviews.ReviewContractError as exc:
                raise SynthesisError("synthesis_review_invalid", slot) from exc
            if (
                record["attempt_id"] != attempt_id
                or record["packet_set_digest"] != private_join.packet_set_digest
            ):
                _fail("synthesis_review_binding_mismatch", slot)
        else:
            record = _validated_failure_record(
                record,
                attempt_id=attempt_id,
                call_slot_id=slot,
            )
        if any(
            prior.get("session_id") == record.get("session_id")
            or prior.get("provider_attempt_id") == record.get("provider_attempt_id")
            for prior in prior_records
        ):
            _fail("synthesis_review_identity_reused", slot)
        prior_records.append(record)
        review_rows.append(
            {
                "call_slot_id": slot,
                "status": settlement["status"],
                "record": record,
                "record_sha256": digest,
            }
        )
    if set(review_records_by_slot) != {
        str(row["call_slot_id"]) for row in review_settlements
    }:
        _fail("synthesis_review_domain_invalid")
    presentation_order = tuple(
        next(
            row.opaque_label
            for row in private_join.rows
            if row.package_id == package_id
        )
        for package_id in private_join.attempt.opaque_package_order
    )
    try:
        integrated = reviews.validate_review_payload(
            integrated_payload,
            review_kind=reviews.INTEGRATED,
            perspective_id=None,
            presentation_order=presentation_order,
            citable_item_ids_by_label=citable_items,
        )
    except reviews.ReviewContractError as exc:
        raise SynthesisError("synthesis_integrated_payload_invalid") from exc
    by_slot = {row["call_slot_id"]: row for row in review_rows}
    initial_rows = [
        by_slot.get("EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS"),
        by_slot.get("EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"),
    ]
    if any(row is None for row in initial_rows):
        _fail("synthesis_initial_review_resolution_invalid")
    adjudicator_row = by_slot.get("EVAL.ADJUDICATOR")
    initial_failed = any(
        row is not None and row["status"] == "FAILED" for row in initial_rows
    )
    if initial_failed:
        material_disagreement = False
    else:
        assert initial_rows[0] is not None and initial_rows[1] is not None
        try:
            material_disagreement = bool(
                reviews.material_disagreements(
                    initial_rows[0]["record"],
                    initial_rows[1]["record"],
                    citable_item_ids_by_label=citable_items,
                )
            )
        except reviews.ReviewContractError as exc:
            raise SynthesisError("synthesis_initial_review_resolution_invalid") from exc
    _arm_slots, _evaluation_slots, selected_route_adjudication = (
        _selected_call_routes(accounting, lock)
    )
    if selected_route_adjudication is not material_disagreement:
        _fail("synthesis_evaluation_route_adjudication_mismatch")
    if initial_failed:
        if adjudicator_row is not None or adjudication_payload is not None:
            _fail("synthesis_adjudication_forbidden_after_initial_failure")
        if accounting.get("material_disagreement") is not False:
            _fail("synthesis_material_disagreement_mismatch")
        adjudication = None
    elif not material_disagreement:
        if accounting.get("material_disagreement") is not False:
            _fail("synthesis_material_disagreement_mismatch")
        if adjudicator_row is not None or adjudication_payload is not None:
            _fail("synthesis_adjudication_payload_unexpected")
        adjudication = None
    else:
        if accounting.get("material_disagreement") is not True:
            _fail("synthesis_material_disagreement_mismatch")
        if adjudicator_row is None:
            _fail("synthesis_adjudication_required")
        assert initial_rows[0] is not None and initial_rows[1] is not None
        expected_adjudication = reviews.resolve_adjudication(
            initial_rows[0]["record"],
            initial_rows[1]["record"],
            adjudicator_row["record"],
            citable_item_ids_by_label=citable_items,
        )
        if adjudication_payload != expected_adjudication:
            _fail("synthesis_adjudication_payload_binding_mismatch")
        adjudication = expected_adjudication
    integrated_row = by_slot.get("EVAL.INTEGRATED_REVIEW")
    if integrated_row is None:
        _fail("synthesis_integrated_payload_binding_mismatch")
    if integrated_row["status"] == "SUCCEEDED":
        if integrated_row["record"].get("payload") != integrated:
            _fail("synthesis_integrated_payload_binding_mismatch")
    else:
        expected_integrated = reviews.resolve_integrated_review(
            integrated_row["record"],
            attempt_id=attempt_id,
            packet_set_digest=private_join.packet_set_digest,
            presentation_order=presentation_order,
            citable_item_ids_by_label=citable_items,
            existing_records=tuple(
                row["record"]
                for row in review_rows
                if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
            ),
        )
        if integrated != expected_integrated:
            _fail("synthesis_integrated_payload_binding_mismatch")
    integrated_record_digest = str(integrated_row["record_sha256"])
    integrated_prior_record_sha256s = [
        str(row["record_sha256"])
        for row in review_rows
        if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
    ]

    if set(hard_evidence_by_arm) != set(_ARMS):
        _fail("synthesis_hard_evaluation_domain_invalid")
    hard_rows = [
        _hard_row_from_spec(arm, hard_evidence_by_arm[arm]) for arm in _ARMS
    ]
    hard_rows, hard_freezes_by_arm = _validated_hard_evaluations(
        hard_rows,
        labels_by_arm=labels_by_arm,
        attempt_record=checked_attempt,
        evaluation_authority=evaluation_authority,
    )
    hard_evidence_digest = _study_digest(hard_rows)
    expected_primary = hard_contract.derive_primary_outcome(
        raw_outcome=oriented_primary.rich_vs_direct,
        rich_freeze=hard_freezes_by_arm["RICH"],
        direct_freeze=hard_freezes_by_arm["DIRECT"],
    )
    if hard_primary_outcome != expected_primary:
        _fail("synthesis_hard_primary_mismatch")
    primary_pair = next(
        row
        for row in integrated["pairwise_results"]
        if {
            row["candidate_a_label"],
            row["candidate_b_label"],
        }
        == {labels_by_arm["RICH"], labels_by_arm["DIRECT"]}
    )
    if (
        oriented_primary.integrated_review_record_digest
        != integrated_record_digest
        or oriented_primary.source_pair_row_digest != _study_digest(primary_pair)
        or oriented_primary.hard_evidence_record_digest != hard_evidence_digest
        or oriented_primary.unblinding_map_digest != private_join.digest
    ):
        _fail("synthesis_oriented_primary_binding_mismatch")

    receipt_bindings = accounting["receipt_bindings"]
    assert isinstance(receipt_bindings, list)
    expected_slots = [str(row["call_slot_id"]) for row in receipt_bindings]
    if (
        set(receipts_by_slot) != set(expected_slots)
        or set(raw_jsonl_by_slot) != set(expected_slots)
        or set(elapsed_ms_by_slot) != set(expected_slots)
        or not set(expected_slots).issubset(call_authority_by_slot)
    ):
        _fail("synthesis_receipt_domain_invalid")
    receipt_rows: list[dict[str, Any]] = []
    elapsed_rows: list[dict[str, Any]] = []
    for binding in receipt_bindings:
        assert isinstance(binding, Mapping)
        slot = str(binding["call_slot_id"])
        try:
            raw_text = raw_jsonl_by_slot[slot].decode("utf-8", "strict")
        except (AttributeError, UnicodeDecodeError) as exc:
            raise SynthesisError("synthesis_receipt_raw_invalid", slot) from exc
        receipt = _canonical_copy(receipts_by_slot[slot])
        receipt_digest = _study_digest(receipt)
        if receipt_digest != binding["receipt_sha256"]:
            _fail("synthesis_receipt_digest_mismatch", slot)
        receipt_rows.append(
            {
                "call_slot_id": slot,
                "record": receipt,
                "record_sha256": receipt_digest,
                "raw_jsonl": raw_text,
            }
        )
        elapsed = elapsed_ms_by_slot[slot]
        if type(elapsed) is not int or elapsed < 0:
            _fail("synthesis_elapsed_invalid", slot)
        elapsed_body = {
            "call_slot_id": slot,
            "timing_source": _TIMING_SOURCE,
            "elapsed_ms": elapsed,
        }
        elapsed_rows.append({**elapsed_body, "row_sha256": _study_digest(elapsed_body)})
    receipt_rows = _validated_receipt_rows(
        receipt_rows,
        receipt_bindings,
        attempt_id=attempt_id,
        call_authority_by_slot=call_authority_by_slot,
    )
    receipt_by_slot = {row["call_slot_id"]: row for row in receipt_rows}
    for row in review_rows:
        receipt = receipt_by_slot.get(row["call_slot_id"])
        if (
            receipt is None
            or row["record"].get("receipt_digest") != receipt["record_sha256"]
        ):
            _fail("synthesis_review_receipt_mismatch", str(row["call_slot_id"]))
    allocation_rows = _canonical_copy(call_allocations)
    if not isinstance(allocation_rows, list):
        _fail("synthesis_call_allocation_invalid")

    body: dict[str, Any] = {
        "schema_version": ATTEMPT_INDEX_SCHEMA_VERSION,
        "evidence_variant": "COMPLETE",
        "call_authority": call_authority,
        "attempt_record": checked_attempt,
        "attempt_record_sha256": _study_digest(checked_attempt),
        "public_packet_replay_inputs": _canonical_copy(
            public_packet_replay_inputs
        ),
        "private_blinding_replay_inputs": _canonical_copy(
            private_blinding_replay_inputs
        ),
        "private_blinding_join": private_join.record,
        "private_blinding_join_sha256": private_join.digest,
        "packets": packet_rows,
        "scorer_settlements": scorer_rows,
        "reviews": review_rows,
        "integrated_prior_record_sha256s": integrated_prior_record_sha256s,
        "adjudication_payload": adjudication,
        "adjudication_payload_sha256": (
            None
            if adjudication is None
            else reviews.canonical_payload_digest(adjudication)
        ),
        "integrated_payload": integrated,
        "integrated_payload_sha256": reviews.canonical_payload_digest(integrated),
        "hard_evaluations": hard_rows,
        "oriented_primary": oriented_primary.record,
        "oriented_primary_sha256": _study_digest(oriented_primary.record),
        "hard_primary_outcome": hard_primary_outcome.record,
        "hard_primary_outcome_sha256": _study_digest(hard_primary_outcome.record),
        "call_allocations": allocation_rows,
        "receipts": receipt_rows,
        "elapsed_ms": elapsed_rows,
    }
    result = {**body, "index_sha256": _study_digest(body)}
    validate_attempt_evidence_index(
        result,
        expected_index_sha256=result["index_sha256"],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=expected_bindings,
    )
    return result


def build_invalid_attempt_evidence_index(
    *,
    attempt_record: Mapping[str, object],
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    receipts_by_slot: Mapping[str, Mapping[str, object]],
    raw_jsonl_by_slot: Mapping[str, bytes],
    elapsed_ms_by_slot: Mapping[str, int],
    frozen_call_authority: Mapping[str, object],
    call_allocations: Sequence[Mapping[str, object]],
    partial_evidence: Mapping[str, object] | None = None,
    invalidity_authority: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Freeze the closed partial-evidence shape for an INVALID attempt."""

    lock, schedule, _schema_digest = _checked_contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    try:
        checked_attempt = attempts.validate_attempt_record(
            attempt_record,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=expected_bindings,
        )
    except attempts.AttemptAccountingError as exc:
        raise SynthesisError("synthesis_attempt_record_invalid", exc.code) from exc
    if checked_attempt["status"] != "INVALID" and not (
        checked_attempt["status"] == "VALID"
        and checked_attempt.get("interrupted") is True
    ):
        _fail("synthesis_sparse_invalid_status_required")
    call_authority, call_authority_by_slot = _validated_call_authority(
        frozen_call_authority,
        decision_lock=lock,
        expected_bindings=expected_bindings,
    )
    accounting = checked_attempt["accounting"]
    assert isinstance(accounting, Mapping)
    bindings = accounting["receipt_bindings"]
    assert isinstance(bindings, list)
    slots = [str(row["call_slot_id"]) for row in bindings]
    if (
        set(receipts_by_slot) != set(slots)
        or set(raw_jsonl_by_slot) != set(slots)
        or set(elapsed_ms_by_slot) != set(slots)
        or not set(slots).issubset(call_authority_by_slot)
    ):
        _fail("synthesis_receipt_domain_invalid")
    receipt_rows: list[dict[str, Any]] = []
    elapsed_rows: list[dict[str, Any]] = []
    for binding in bindings:
        assert isinstance(binding, Mapping)
        slot = str(binding["call_slot_id"])
        try:
            raw = raw_jsonl_by_slot[slot].decode("utf-8", "strict")
        except (AttributeError, UnicodeDecodeError) as exc:
            raise SynthesisError("synthesis_receipt_raw_invalid", slot) from exc
        receipt = _canonical_copy(receipts_by_slot[slot])
        receipt_rows.append(
            {
                "call_slot_id": slot,
                "record": receipt,
                "record_sha256": _study_digest(receipt),
                "raw_jsonl": raw,
            }
        )
        elapsed = elapsed_ms_by_slot[slot]
        if type(elapsed) is not int or elapsed < 0:
            _fail("synthesis_elapsed_invalid", slot)
        elapsed_body = {
            "call_slot_id": slot,
            "timing_source": _TIMING_SOURCE,
            "elapsed_ms": elapsed,
        }
        elapsed_rows.append({**elapsed_body, "row_sha256": _study_digest(elapsed_body)})
    receipt_rows = _validated_receipt_rows(
        receipt_rows,
        bindings,
        attempt_id=str(checked_attempt["attempt_id"]),
        call_authority_by_slot=call_authority_by_slot,
    )
    allocation_rows = _canonical_copy(call_allocations)
    if not isinstance(allocation_rows, list):
        _fail("synthesis_call_allocation_invalid")
    evidence: dict[str, Any] = {
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
    if partial_evidence is not None:
        checked_partial = _canonical_copy(partial_evidence)
        if not isinstance(checked_partial, dict) or set(checked_partial) != (
            _PARTIAL_EVIDENCE_KEYS
        ):
            _fail("synthesis_partial_evidence_shape_invalid")
        evidence = checked_partial
    checked_invalidity_authority: dict[str, Any] | None = None
    if invalidity_authority is not None:
        normalized_authority = _canonical_copy(invalidity_authority)
        if not isinstance(normalized_authority, dict):
            _fail("synthesis_invalidity_authority_shape_invalid")
        checked_invalidity_authority = normalized_authority
    body: dict[str, Any] = {
        "schema_version": ATTEMPT_INDEX_SCHEMA_VERSION,
        "evidence_variant": "PARTIAL",
        "call_authority": call_authority,
        "attempt_record": checked_attempt,
        "attempt_record_sha256": _study_digest(checked_attempt),
        **evidence,
        "invalidity_authority": checked_invalidity_authority,
        "invalidity_authority_sha256": (
            None
            if checked_invalidity_authority is None
            else _study_digest(checked_invalidity_authority)
        ),
        "call_allocations": allocation_rows,
        "receipts": receipt_rows,
        "elapsed_ms": elapsed_rows,
    }
    result = {**body, "index_sha256": _study_digest(body)}
    validate_attempt_evidence_index(
        result,
        expected_index_sha256=result["index_sha256"],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=expected_bindings,
    )
    return result


def _oriented_primary_from_pair(
    row: Mapping[str, object],
    *,
    rich_label: str,
    direct_label: str,
) -> str:
    if {row.get("candidate_a_label"), row.get("candidate_b_label")} != {
        rich_label,
        direct_label,
    }:
        _fail("synthesis_primary_pair_invalid")
    outcome = row.get("outcome")
    if outcome in {"TIE", "INDETERMINATE"}:
        return str(outcome)
    if outcome not in {"A", "B"}:
        _fail("synthesis_primary_pair_invalid")
    winner = (
        row.get("candidate_a_label")
        if outcome == "A"
        else row.get("candidate_b_label")
    )
    return "RICH" if winner == rich_label else "DIRECT"


def _validate_index_receipt_evidence(
    index: Mapping[str, Any],
    accounting: Mapping[str, object],
    *,
    attempt_id: str,
    review_rows: Sequence[Mapping[str, Any]],
    call_authority_by_slot: Mapping[str, Mapping[str, object]],
) -> list[dict[str, Any]]:
    receipt_bindings = accounting.get("receipt_bindings")
    receipt_rows = index.get("receipts")
    elapsed_rows = index.get("elapsed_ms")
    if (
        not isinstance(receipt_bindings, list)
        or not isinstance(receipt_rows, list)
        or not isinstance(elapsed_rows, list)
        or len(receipt_rows) != len(receipt_bindings)
        or len(elapsed_rows) != len(receipt_bindings)
        or any(not isinstance(binding, Mapping) for binding in receipt_bindings)
    ):
        _fail("synthesis_receipt_domain_invalid")
    normalized_receipts = _validated_receipt_rows(
        receipt_rows,
        receipt_bindings,
        attempt_id=attempt_id,
        call_authority_by_slot=call_authority_by_slot,
    )
    for binding, elapsed_row in zip(
        receipt_bindings,
        elapsed_rows,
        strict=True,
    ):
        slot = str(binding["call_slot_id"])
        if (
            not isinstance(elapsed_row, dict)
            or set(elapsed_row)
            != {"call_slot_id", "timing_source", "elapsed_ms", "row_sha256"}
            or elapsed_row["call_slot_id"] != slot
            or elapsed_row["timing_source"] != _TIMING_SOURCE
            or type(elapsed_row["elapsed_ms"]) is not int
            or elapsed_row["elapsed_ms"] < 0
            or elapsed_row["row_sha256"]
            != _study_digest(
                {
                    "call_slot_id": slot,
                    "timing_source": _TIMING_SOURCE,
                    "elapsed_ms": elapsed_row["elapsed_ms"],
                }
            )
        ):
            _fail("synthesis_elapsed_binding_mismatch", slot)
    receipts_by_slot = {
        str(row["call_slot_id"]): row for row in normalized_receipts
    }
    for review_row in review_rows:
        slot = str(review_row["call_slot_id"])
        receipt = receipts_by_slot.get(slot)
        record = review_row.get("record")
        if (
            receipt is None
            or not isinstance(record, Mapping)
            or record.get("receipt_digest") != receipt["record_sha256"]
        ):
            _fail("synthesis_review_receipt_mismatch", slot)
    return normalized_receipts


def _validate_invalidity_authority(
    index: Mapping[str, Any],
    *,
    attempt_record: Mapping[str, object],
) -> None:
    authority = index.get("invalidity_authority")
    authority_digest = index.get("invalidity_authority_sha256")
    invalidity_code = attempt_record.get("invalidity_code")
    requires_authority = invalidity_code in _CONTROLLER_AUTHORITY_INVALIDITY_CODES
    if authority is None:
        if authority_digest is not None:
            _fail("synthesis_invalidity_authority_shape_invalid")
        if requires_authority:
            _fail("synthesis_invalidity_authority_missing")
        return
    if not requires_authority:
        _fail("synthesis_invalidity_authority_forbidden")
    if (
        not isinstance(authority, Mapping)
        or set(authority) != _INVALIDITY_AUTHORITY_KEYS
        or authority.get("schema_version")
        != "es.controller_invalidity_authority.v1"
        or not isinstance(authority.get("evidence"), Mapping)
    ):
        _fail("synthesis_invalidity_authority_shape_invalid")
    if (
        authority.get("attempt_id") != attempt_record.get("attempt_id")
        or authority.get("invalidity_code") != invalidity_code
        or authority_digest != _study_digest(authority)
    ):
        _fail("synthesis_invalidity_authority_binding_mismatch")


def _validate_partial_attempt_index(
    index: dict[str, Any],
    *,
    attempt_record: Mapping[str, object],
    accounting: Mapping[str, object],
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    call_authority_by_slot: Mapping[str, Mapping[str, object]],
    evaluation_authority: Mapping[str, object],
) -> dict[str, Any]:
    """Validate a closed prefix of evidence incurred by one invalid attempt."""

    attempt_id = str(attempt_record["attempt_id"])
    _validate_invalidity_authority(index, attempt_record=attempt_record)
    empty_after_join = {
        "public_packet_replay_inputs": None,
        "private_blinding_replay_inputs": None,
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
    interrupted_valid = (
        attempt_record["status"] == "VALID"
        and attempt_record.get("interrupted") is True
    )
    if attempt_record["status"] != "INVALID" and not interrupted_valid:
        _fail("synthesis_partial_invalid_status_required")
    if index["public_packet_replay_inputs"] is None:
        e2 = attempt_record.get("e2_authority")
        if (
            index["private_blinding_join"] is not None
            or any(
                index[field] != expected
                for field, expected in empty_after_join.items()
            )
            or accounting.get("review_settlements") != []
            or (
                isinstance(e2, Mapping)
                and e2.get("scorer_settlements") != []
            )
        ):
            _fail("synthesis_partial_evidence_shape_invalid")
        _validate_index_receipt_evidence(
            index,
            accounting,
            attempt_id=attempt_id,
            review_rows=(),
            call_authority_by_slot=call_authority_by_slot,
        )
        return index
    (
        packet_rows,
        public_labels_by_arm,
        packet_digests,
        citable_items,
        public_packet_set_digest,
        packet_evidence_frozen_digest,
    ) = _validated_public_packet_evidence(
        index["public_packet_replay_inputs"],
        index["packets"],
        attempt_record=attempt_record,
    )
    scorer_rows = _validated_scorer_settlements(
        scorer_rows=index["scorer_settlements"],
        attempt_record=attempt_record,
        labels_by_arm=public_labels_by_arm,
        packet_digests_by_arm=packet_digests,
        packet_evidence_frozen_digest=packet_evidence_frozen_digest,
        evaluation_authority=evaluation_authority,
        require_complete=False,
    )
    if attempt_record.get("invalidity_code") == "BLINDING_JOIN_INVALID":
        no_private_downstream = {
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
        if (
            accounting.get("review_settlements") != []
            or any(
                index[field] != expected
                for field, expected in no_private_downstream.items()
            )
        ):
            _fail("synthesis_blinding_invalid_downstream_evidence_forbidden")
        attempted_join = index["private_blinding_join"]
        if attempted_join is None:
            if (
                index["private_blinding_replay_inputs"] is not None
                or index["private_blinding_join_sha256"] is not None
            ):
                _fail("synthesis_blinding_invalid_attempt_record_mismatch")
        else:
            if (
                not isinstance(attempted_join, Mapping)
                or index["private_blinding_join_sha256"]
                != canonical_sha256(attempted_join)
            ):
                _fail("synthesis_blinding_invalid_attempt_record_mismatch")
            try:
                _validated_private_join(
                    attempted_join,
                    index["private_blinding_replay_inputs"],
                    index["public_packet_replay_inputs"],
                    attempt_record=attempt_record,
                    decision_lock=decision_lock,
                    randomization_manifest=randomization_manifest,
                    expected_bindings=expected_bindings,
                )
            except SynthesisError:
                pass
            else:
                _fail("synthesis_blinding_invalidity_mismatch")
        _validate_index_receipt_evidence(
            index,
            accounting,
            attempt_id=attempt_id,
            review_rows=(),
            call_authority_by_slot=call_authority_by_slot,
        )
        return index
    if not interrupted_valid and attempt_record.get("invalidity_code") not in {
        "APPARATUS_ACCOUNTING_INCOMPLETE",
        "COMMON_EVALUATION_BYTES_INVALID",
    }:
        _fail("synthesis_partial_evidence_invalidity_mismatch")
    if index["private_blinding_join"] is None:
        _fail("synthesis_private_join_missing")
    join_object, labels_by_arm = _validated_private_join(
        index["private_blinding_join"],
        index["private_blinding_replay_inputs"],
        index["public_packet_replay_inputs"],
        attempt_record=attempt_record,
        decision_lock=decision_lock,
        randomization_manifest=randomization_manifest,
        expected_bindings=expected_bindings,
    )
    if (
        index["private_blinding_join_sha256"] != join_object.digest
        or public_labels_by_arm != labels_by_arm
        or public_packet_set_digest != join_object.packet_set_digest
    ):
        _fail("synthesis_private_join_binding_mismatch")

    settlements = accounting.get("review_settlements")
    review_rows = index["reviews"]
    if (
        not isinstance(settlements, list)
        or not isinstance(review_rows, list)
        or len(settlements) != len(review_rows)
    ):
        _fail("synthesis_review_domain_invalid")
    if review_rows and len(scorer_rows) != len(_ARMS):
        _fail("synthesis_partial_review_requires_complete_scorers")
    route_contract = decision_lock.get("route_contract")
    evaluation_routes = (
        route_contract.get("evaluation_routes")
        if isinstance(route_contract, Mapping)
        else None
    )
    if not isinstance(evaluation_routes, list):
        _fail("synthesis_review_domain_invalid")
    evaluation_route = next(
        (
            row
            for row in evaluation_routes
            if isinstance(row, Mapping)
            and row.get("route_id") == accounting.get("evaluation_route_id")
        ),
        None,
    )
    if not isinstance(evaluation_route, Mapping) or not isinstance(
        evaluation_route.get("call_slots"), list
    ):
        _fail("synthesis_review_domain_invalid")
    expected_review_slots = list(evaluation_route["call_slots"])[4:]
    if [row.get("call_slot_id") for row in settlements] != expected_review_slots[
        : len(settlements)
    ]:
        _fail("synthesis_review_domain_invalid")
    prior_records: list[dict[str, Any]] = []
    checked_rows: list[dict[str, Any]] = []
    for settlement, row in zip(settlements, review_rows, strict=True):
        if (
            not isinstance(settlement, Mapping)
            or not isinstance(row, dict)
            or set(row) != {"call_slot_id", "status", "record", "record_sha256"}
            or row["call_slot_id"] != settlement["call_slot_id"]
            or row["status"] != settlement["status"]
            or row["record_sha256"] != settlement["record_sha256"]
            or row["record_sha256"] != _study_digest(row["record"])
        ):
            _fail("synthesis_review_digest_mismatch")
        slot = str(row["call_slot_id"])
        if row["status"] == "SUCCEEDED":
            try:
                checked = reviews.validate_review_record(
                    row["record"],
                    citable_item_ids_by_label=citable_items,
                    existing_records=prior_records,
                )
            except reviews.ReviewContractError as exc:
                raise SynthesisError("synthesis_review_invalid", slot) from exc
            if (
                checked["attempt_id"] != attempt_id
                or checked["packet_set_digest"] != join_object.packet_set_digest
            ):
                _fail("synthesis_review_binding_mismatch", slot)
        else:
            checked = _validated_failure_record(
                row["record"], attempt_id=attempt_id, call_slot_id=slot
            )
        if any(
            prior.get("session_id") == checked.get("session_id")
            or prior.get("provider_attempt_id") == checked.get("provider_attempt_id")
            for prior in prior_records
        ):
            _fail("synthesis_review_identity_reused", slot)
        prior_records.append(checked)
        checked_rows.append({**row, "record": checked})

    by_slot = {row["call_slot_id"]: row for row in checked_rows}
    initial_slots = (
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    first_initial = by_slot.get(initial_slots[0])
    second_initial = by_slot.get(initial_slots[1])
    adjudicator_row = by_slot.get("EVAL.ADJUDICATOR")
    integrated_row = by_slot.get("EVAL.INTEGRATED_REVIEW")
    review_resolution_complete = False
    if first_initial is None or second_initial is None:
        if (
            accounting.get("material_disagreement") is not False
            or second_initial is not None
            or adjudicator_row is not None
            or integrated_row is not None
            or index["adjudication_payload"] is not None
            or index["adjudication_payload_sha256"] is not None
        ):
            _fail("synthesis_partial_review_prefix_invalid")
    else:
        initial_pair = (first_initial, second_initial)
        initial_failed = any(row["status"] == "FAILED" for row in initial_pair)
        if initial_failed:
            disagreement = False
        else:
            disagreement = bool(
                reviews.material_disagreements(
                    first_initial["record"],
                    second_initial["record"],
                    citable_item_ids_by_label=citable_items,
                )
            )
        if accounting.get("material_disagreement") is not disagreement:
            _fail("synthesis_material_disagreement_mismatch")
        if evaluation_route.get("adjudication") is not disagreement:
            _fail("synthesis_evaluation_route_adjudication_mismatch")
        if initial_failed or not disagreement:
            if adjudicator_row is not None:
                _fail("synthesis_adjudication_payload_unexpected")
            if (
                index["adjudication_payload"] is not None
                or index["adjudication_payload_sha256"] is not None
            ):
                _fail("synthesis_adjudication_payload_unexpected")
            review_resolution_complete = True
        else:
            if adjudicator_row is None:
                if (
                    integrated_row is not None
                    or index["adjudication_payload"] is not None
                    or index["adjudication_payload_sha256"] is not None
                ):
                    _fail("synthesis_adjudication_required")
            else:
                expected_adjudication = reviews.resolve_adjudication(
                    first_initial["record"],
                    second_initial["record"],
                    adjudicator_row["record"],
                    citable_item_ids_by_label=citable_items,
                )
                if (
                    index["adjudication_payload"] != expected_adjudication
                    or index["adjudication_payload_sha256"]
                    != reviews.canonical_payload_digest(expected_adjudication)
                ):
                    _fail("synthesis_adjudication_payload_binding_mismatch")
                review_resolution_complete = True

    hard_rows, hard_freezes = _validated_hard_evaluations(
        index["hard_evaluations"],
        labels_by_arm=labels_by_arm,
        attempt_record=attempt_record,
        evaluation_authority=evaluation_authority,
        require_complete=False,
    )
    no_integrated = {
        "integrated_prior_record_sha256s": [],
        "integrated_payload": None,
        "integrated_payload_sha256": None,
    }
    no_primary = {
        "oriented_primary": None,
        "oriented_primary_sha256": None,
        "hard_primary_outcome": None,
        "hard_primary_outcome_sha256": None,
    }
    if not review_resolution_complete:
        if (
            hard_rows
            or integrated_row is not None
            or any(index[field] != expected for field, expected in no_integrated.items())
            or any(index[field] != expected for field, expected in no_primary.items())
        ):
            _fail("synthesis_partial_review_resolution_pending")
    elif integrated_row is None:
        if (
            any(index[field] != expected for field, expected in no_integrated.items())
            or any(index[field] != expected for field, expected in no_primary.items())
        ):
            _fail("synthesis_partial_integrated_review_pending")
    else:
        if len(hard_rows) != len(_ARMS):
            if interrupted_valid:
                _fail("synthesis_provider_authority_incomplete")
            _fail("synthesis_integrated_review_requires_complete_hard_evidence")
        expected_prior = [
            str(row["record_sha256"])
            for row in checked_rows
            if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
        ]
        if index["integrated_prior_record_sha256s"] != expected_prior:
            _fail("synthesis_integrated_prior_binding_mismatch")
        presentation_order = tuple(
            next(
                row.opaque_label
                for row in join_object.rows
                if row.package_id == package
            )
            for package in join_object.attempt.opaque_package_order
        )
        try:
            integrated = reviews.validate_review_payload(
                index["integrated_payload"],
                review_kind=reviews.INTEGRATED,
                perspective_id=None,
                presentation_order=presentation_order,
                citable_item_ids_by_label=citable_items,
            )
        except reviews.ReviewContractError as exc:
            raise SynthesisError("synthesis_integrated_payload_invalid") from exc
        if index["integrated_payload_sha256"] != reviews.canonical_payload_digest(
            integrated
        ):
            _fail("synthesis_integrated_payload_binding_mismatch")
        if integrated_row["status"] == "SUCCEEDED":
            if integrated_row["record"].get("payload") != integrated:
                _fail("synthesis_integrated_payload_binding_mismatch")
        else:
            fallback = reviews.resolve_integrated_review(
                integrated_row["record"],
                attempt_id=attempt_id,
                packet_set_digest=join_object.packet_set_digest,
                presentation_order=presentation_order,
                citable_item_ids_by_label=citable_items,
                existing_records=tuple(
                    row["record"]
                    for row in checked_rows
                    if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
                ),
            )
            if integrated != fallback:
                _fail("synthesis_integrated_payload_binding_mismatch")
        oriented = index["oriented_primary"]
        primary = index["hard_primary_outcome"]
        if (oriented is None) != (primary is None):
            _fail("synthesis_partial_evidence_shape_invalid")
        if oriented is None:
            if (
                index["oriented_primary_sha256"] is not None
                or index["hard_primary_outcome_sha256"] is not None
            ):
                _fail("synthesis_partial_evidence_shape_invalid")
        else:
            if (
                not isinstance(oriented, dict)
                or set(oriented) != _ORIENTED_KEYS
                or index["oriented_primary_sha256"] != _study_digest(oriented)
            ):
                _fail("synthesis_oriented_primary_invalid")
            primary_pair = next(
                row
                for row in integrated["pairwise_results"]
                if {row["candidate_a_label"], row["candidate_b_label"]}
                == {labels_by_arm["RICH"], labels_by_arm["DIRECT"]}
            )
            raw = _oriented_primary_from_pair(
                primary_pair,
                rich_label=labels_by_arm["RICH"],
                direct_label=labels_by_arm["DIRECT"],
            )
            if (
                oriented["rich_vs_direct"] != raw
                or oriented["source_pair_row_digest"] != _study_digest(primary_pair)
                or oriented["integrated_review_record_digest"]
                != integrated_row["record_sha256"]
                or oriented["hard_evidence_record_digest"]
                != _study_digest(hard_rows)
                or oriented["unblinding_map_digest"] != join_object.digest
            ):
                _fail("synthesis_oriented_primary_binding_mismatch")
            expected_primary = hard_contract.derive_primary_outcome(
                raw_outcome=raw,
                rich_freeze=hard_freezes["RICH"],
                direct_freeze=hard_freezes["DIRECT"],
            ).record
            if (
                primary != expected_primary
                or index["hard_primary_outcome_sha256"]
                != _study_digest(expected_primary)
            ):
                _fail("synthesis_hard_primary_mismatch")

    _validate_index_receipt_evidence(
        index,
        accounting,
        attempt_id=attempt_id,
        review_rows=checked_rows,
        call_authority_by_slot=call_authority_by_slot,
    )
    return index


def validate_attempt_evidence_index(
    value: object,
    *,
    expected_index_sha256: str,
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> dict[str, Any]:
    """Revalidate one immutable index and every record/digest join."""

    lock, schedule, _schema_digest = _checked_contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    index = _canonical_copy(value)
    expected_keys = (
        _PARTIAL_INDEX_KEYS
        if isinstance(index, dict) and index.get("evidence_variant") == "PARTIAL"
        else _INDEX_KEYS
    )
    if (
        not isinstance(index, dict)
        or set(index) != expected_keys
        or index.get("schema_version") != ATTEMPT_INDEX_SCHEMA_VERSION
    ):
        _fail("synthesis_index_schema_invalid")
    index_digest = _digest(index["index_sha256"], field="index_sha256")
    expected = _digest(expected_index_sha256, field="expected_index_sha256")
    body = {key: member for key, member in index.items() if key != "index_sha256"}
    if index_digest != expected or index_digest != _study_digest(body):
        _fail("synthesis_index_digest_mismatch")
    try:
        attempt_record = attempts.validate_attempt_record(
            index["attempt_record"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=expected_bindings,
        )
    except attempts.AttemptAccountingError as exc:
        raise SynthesisError("synthesis_attempt_record_invalid", exc.code) from exc
    if index["attempt_record_sha256"] != _study_digest(attempt_record):
        _fail("synthesis_attempt_record_digest_mismatch")
    attempt_id = str(attempt_record["attempt_id"])
    accounting = attempt_record["accounting"]
    assert isinstance(accounting, Mapping)
    call_authority, call_authority_by_slot = _validated_call_authority(
        index["call_authority"],
        decision_lock=lock,
        expected_bindings=expected_bindings,
    )
    evaluation_authority = _evaluation_authority(call_authority)
    if index["evidence_variant"] not in {"COMPLETE", "PARTIAL"}:
        _fail("synthesis_evidence_variant_invalid")
    if index["evidence_variant"] == "PARTIAL":
        validated = _validate_partial_attempt_index(
            index,
            attempt_record=attempt_record,
            accounting=accounting,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=expected_bindings,
            call_authority_by_slot=call_authority_by_slot,
            evaluation_authority=_evaluation_authority(call_authority),
        )
        _validated_call_allocations(
            validated["call_allocations"],
            attempt_id=attempt_id,
            accounting=accounting,
            decision_lock=lock,
            call_authority_by_slot=call_authority_by_slot,
            evidence=validated,
            complete=False,
        )
        return validated
    if index["evidence_variant"] != "COMPLETE":
        _fail("synthesis_complete_evidence_variant_invalid")
    if attempt_record["status"] != "VALID":
        _fail("synthesis_complete_index_requires_valid_attempt")
    reconstructed_join, labels_by_arm = _validated_private_join(
        index["private_blinding_join"],
        index["private_blinding_replay_inputs"],
        index["public_packet_replay_inputs"],
        attempt_record=attempt_record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=expected_bindings,
    )
    join = reconstructed_join.record
    if (
        index["private_blinding_join_sha256"] != reconstructed_join.digest
        or join["attempt_id"] != attempt_id
        or join["decision_lock_digest"]
        != decision_lock_authority.decision_lock_digest(lock)
        or join["randomization_row_digest"]
        != attempt_record["randomization_row_sha256"]
        or join["trial_request_digest"] != attempt_record["trial_request_digest"]
    ):
        _fail("synthesis_private_join_binding_mismatch")
    join_rows = {row.arm_id: row for row in reconstructed_join.rows}
    packets = index["packets"]
    if not isinstance(packets, list) or [row.get("arm_id") for row in packets] != list(
        _ARMS
    ):
        _fail("synthesis_packet_domain_invalid")
    packet_set_rows: list[dict[str, object]] = []
    citable_items: dict[str, tuple[str, ...]] = {}
    for arm, row in zip(_ARMS, packets, strict=True):
        if not isinstance(row, dict) or set(row) != {
            "arm_id",
            "packet",
            "packet_sha256",
        }:
            _fail("synthesis_packet_invalid", arm)
        packet = validate_trial_evaluation_packet(row["packet"])
        packet_digest = canonical_sha256(packet)
        if (
            row["packet_sha256"] != packet_digest
            or packet["evaluation_id"] != labels_by_arm[arm]
            or join_rows[arm].packet_digest != packet_digest
        ):
            _fail("synthesis_packet_digest_mismatch", arm)
        packet_set_rows.append(
            {
                "cell": {"arm_id": arm, "rep": 1},
                "opaque_label": labels_by_arm[arm],
                "packet_digest": packet_digest,
            }
        )
        citable_items[labels_by_arm[arm]] = tuple(packet["citable_item_ids"])
    if canonical_sha256(packet_set_rows) != reconstructed_join.packet_set_digest:
        _fail("synthesis_packet_set_digest_mismatch")
    public_replay = index["public_packet_replay_inputs"]
    packet_index = (
        public_replay.get("packet_artifact_index")
        if isinstance(public_replay, Mapping)
        else None
    )
    if not isinstance(packet_index, Mapping):
        _fail("synthesis_public_packet_replay_invalid")
    scorer_rows = _validated_scorer_settlements(
        scorer_rows=index["scorer_settlements"],
        attempt_record=attempt_record,
        labels_by_arm=labels_by_arm,
        packet_digests_by_arm={
            arm: str(row["packet_sha256"])
            for arm, row in zip(_ARMS, packets, strict=True)
        },
        packet_evidence_frozen_digest=_digest(
            packet_index.get("evidence_frozen_row_digest"),
            field="packet_index.evidence_frozen_row_digest",
        ),
        evaluation_authority=evaluation_authority,
    )

    settlements = accounting["review_settlements"]
    assert isinstance(settlements, list)
    review_rows = index["reviews"]
    if not isinstance(review_rows, list) or len(review_rows) != len(settlements):
        _fail("synthesis_review_domain_invalid")
    prior_records: list[dict[str, Any]] = []
    by_slot: dict[str, dict[str, Any]] = {}
    for settlement, row in zip(settlements, review_rows, strict=True):
        if (
            not isinstance(settlement, Mapping)
            or not isinstance(row, dict)
            or set(row)
            != {"call_slot_id", "status", "record", "record_sha256"}
            or row["call_slot_id"] != settlement["call_slot_id"]
            or row["status"] != settlement["status"]
            or row["record_sha256"] != settlement["record_sha256"]
            or row["record_sha256"] != _study_digest(row["record"])
        ):
            _fail("synthesis_review_digest_mismatch")
        slot = str(row["call_slot_id"])
        if row["status"] == "SUCCEEDED":
            try:
                checked = reviews.validate_review_record(
                    row["record"],
                    citable_item_ids_by_label=citable_items,
                    existing_records=prior_records,
                )
            except reviews.ReviewContractError as exc:
                raise SynthesisError("synthesis_review_invalid") from exc
            if (
                checked["attempt_id"] != attempt_id
                or checked["packet_set_digest"]
                != reconstructed_join.packet_set_digest
            ):
                _fail("synthesis_review_binding_mismatch")
        else:
            checked = _validated_failure_record(
                row["record"],
                attempt_id=attempt_id,
                call_slot_id=slot,
            )
        if any(
            prior.get("session_id") == checked.get("session_id")
            or prior.get("provider_attempt_id")
            == checked.get("provider_attempt_id")
            for prior in prior_records
        ):
            _fail("synthesis_review_identity_reused", slot)
        prior_records.append(checked)
        by_slot[slot] = {**row, "record": checked}

    initial_rows = [
        by_slot.get("EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS"),
        by_slot.get("EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"),
    ]
    if any(row is None for row in initial_rows):
        _fail("synthesis_initial_review_resolution_invalid")
    adjudicator_row = by_slot.get("EVAL.ADJUDICATOR")
    initial_failed = any(
        row is not None and row["status"] == "FAILED" for row in initial_rows
    )
    if initial_failed:
        material_disagreement = False
    else:
        assert initial_rows[0] is not None and initial_rows[1] is not None
        try:
            material_disagreement = bool(
                reviews.material_disagreements(
                    initial_rows[0]["record"],
                    initial_rows[1]["record"],
                    citable_item_ids_by_label=citable_items,
                )
            )
        except reviews.ReviewContractError as exc:
            raise SynthesisError("synthesis_initial_review_resolution_invalid") from exc
    _arm_slots, _evaluation_slots, selected_route_adjudication = (
        _selected_call_routes(accounting, lock)
    )
    if selected_route_adjudication is not material_disagreement:
        _fail("synthesis_evaluation_route_adjudication_mismatch")
    if initial_failed:
        if (
            adjudicator_row is not None
            or index["adjudication_payload"] is not None
            or index["adjudication_payload_sha256"] is not None
        ):
            _fail("synthesis_adjudication_forbidden_after_initial_failure")
        if accounting.get("material_disagreement") is not False:
            _fail("synthesis_material_disagreement_mismatch")
    elif not material_disagreement:
        if accounting.get("material_disagreement") is not False:
            _fail("synthesis_material_disagreement_mismatch")
        if adjudicator_row is not None or (
            index["adjudication_payload"] is not None
            or index["adjudication_payload_sha256"] is not None
        ):
            _fail("synthesis_adjudication_payload_unexpected")
    else:
        if accounting.get("material_disagreement") is not True:
            _fail("synthesis_material_disagreement_mismatch")
        if adjudicator_row is None:
            _fail("synthesis_adjudication_required")
        assert initial_rows[0] is not None and initial_rows[1] is not None
        expected_adjudication = reviews.resolve_adjudication(
            initial_rows[0]["record"],
            initial_rows[1]["record"],
            adjudicator_row["record"],
            citable_item_ids_by_label=citable_items,
        )
        if (
            index["adjudication_payload"] != expected_adjudication
            or index["adjudication_payload_sha256"]
            != reviews.canonical_payload_digest(expected_adjudication)
        ):
            _fail("synthesis_adjudication_payload_binding_mismatch")

    integrated_row = by_slot.get("EVAL.INTEGRATED_REVIEW")
    if integrated_row is None:
        _fail("synthesis_integrated_payload_binding_mismatch")
    expected_prior_digests = [
        str(row["record_sha256"])
        for row in review_rows
        if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
    ]
    if index["integrated_prior_record_sha256s"] != expected_prior_digests:
        _fail("synthesis_integrated_prior_binding_mismatch")
    integrated = _canonical_copy(index["integrated_payload"])
    presentation_order = tuple(
        next(
            row.opaque_label
            for row in reconstructed_join.rows
            if row.package_id == package
        )
        for package in reconstructed_join.attempt.opaque_package_order
    )
    try:
        integrated = reviews.validate_review_payload(
            integrated,
            review_kind=reviews.INTEGRATED,
            perspective_id=None,
            presentation_order=presentation_order,
            citable_item_ids_by_label=citable_items,
        )
    except reviews.ReviewContractError as exc:
        raise SynthesisError("synthesis_integrated_payload_invalid") from exc
    if index["integrated_payload_sha256"] != reviews.canonical_payload_digest(
        integrated
    ):
        _fail("synthesis_integrated_payload_binding_mismatch")
    if integrated_row["status"] == "SUCCEEDED":
        if integrated_row["record"].get("payload") != integrated:
            _fail("synthesis_integrated_payload_binding_mismatch")
    else:
        expected_integrated = reviews.resolve_integrated_review(
            integrated_row["record"],
            attempt_id=attempt_id,
            packet_set_digest=reconstructed_join.packet_set_digest,
            presentation_order=presentation_order,
            citable_item_ids_by_label=citable_items,
            existing_records=tuple(
                row["record"]
                for row in by_slot.values()
                if row["call_slot_id"] != "EVAL.INTEGRATED_REVIEW"
            ),
        )
        if integrated != expected_integrated:
            _fail("synthesis_integrated_payload_binding_mismatch")
    hard_rows, hard_freezes = _validated_hard_evaluations(
        index["hard_evaluations"],
        labels_by_arm=labels_by_arm,
        attempt_record=attempt_record,
        evaluation_authority=evaluation_authority,
    )
    oriented = index["oriented_primary"]
    if (
        not isinstance(oriented, dict)
        or set(oriented) != _ORIENTED_KEYS
        or index["oriented_primary_sha256"] != _study_digest(oriented)
    ):
        _fail("synthesis_oriented_primary_invalid")
    primary_pair = next(
        row
        for row in integrated["pairwise_results"]
        if {row["candidate_a_label"], row["candidate_b_label"]}
        == {labels_by_arm["RICH"], labels_by_arm["DIRECT"]}
    )
    raw_primary = _oriented_primary_from_pair(
        primary_pair,
        rich_label=labels_by_arm["RICH"],
        direct_label=labels_by_arm["DIRECT"],
    )
    hard_evidence_digest = _study_digest(hard_rows)
    if (
        oriented["rich_vs_direct"] != raw_primary
        or oriented["source_pair_row_digest"] != _study_digest(primary_pair)
        or oriented["integrated_review_record_digest"]
        != integrated_row["record_sha256"]
        or oriented["hard_evidence_record_digest"] != hard_evidence_digest
        or oriented["unblinding_map_digest"] != canonical_sha256(join)
    ):
        _fail("synthesis_oriented_primary_binding_mismatch")
    primary = index["hard_primary_outcome"]
    try:
        expected_primary = hard_contract.derive_primary_outcome(
            raw_outcome=raw_primary,
            rich_freeze=hard_freezes["RICH"],
            direct_freeze=hard_freezes["DIRECT"],
        ).record
    except hard_contract.HardContractError as exc:
        raise SynthesisError("synthesis_hard_primary_mismatch") from exc
    if (
        not isinstance(primary, dict)
        or set(primary) != _PRIMARY_KEYS
        or primary != expected_primary
        or index["hard_primary_outcome_sha256"] != _study_digest(primary)
    ):
        _fail("synthesis_hard_primary_mismatch")

    _validate_index_receipt_evidence(
        index,
        accounting,
        attempt_id=attempt_id,
        review_rows=review_rows,
        call_authority_by_slot=call_authority_by_slot,
    )
    _validated_call_allocations(
        index["call_allocations"],
        attempt_id=attempt_id,
        accounting=accounting,
        decision_lock=lock,
        call_authority_by_slot=call_authority_by_slot,
        evidence=index,
        complete=True,
    )
    return index


def _fraction_record(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _median(values: Sequence[Fraction]) -> Fraction:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _pair_relation(
    payload: Mapping[str, Any],
    labels_by_arm: Mapping[str, str],
    first_arm: str,
    second_arm: str,
) -> dict[str, str]:
    first_label = labels_by_arm[first_arm]
    second_label = labels_by_arm[second_arm]
    rows = payload["pairwise_results"]
    row = next(
        value
        for value in rows
        if {value["candidate_a_label"], value["candidate_b_label"]}
        == {first_label, second_label}
    )
    outcome = row["outcome"]
    if outcome in {"TIE", "INDETERMINATE"}:
        oriented = outcome
    else:
        winner = (
            row["candidate_a_label"]
            if outcome == "A"
            else row["candidate_b_label"]
        )
        oriented = "FIRST" if winner == first_label else "SECOND"
    return {"first_arm": first_arm, "second_arm": second_arm, "outcome": oriented}


_CONTRASTS: tuple[
    tuple[str, tuple[Fraction, ...], tuple[tuple[str, str], ...]], ...
] = (
    (
        "TOTAL_RICH_VS_DIRECT",
        (Fraction(-1), Fraction(0), Fraction(0), Fraction(1)),
        (("DIRECT", "RICH"),),
    ),
    (
        "DESIGN_QA_COMPONENT",
        (Fraction(-1, 2), Fraction(1, 2), Fraction(-1, 2), Fraction(1, 2)),
        (("DIRECT", "DESIGN_QA"), ("PRODUCT_QA", "RICH")),
    ),
    (
        "PRODUCT_QA_COMPONENT",
        (Fraction(-1, 2), Fraction(-1, 2), Fraction(1, 2), Fraction(1, 2)),
        (("DIRECT", "PRODUCT_QA"), ("DESIGN_QA", "RICH")),
    ),
    (
        "INTERACTION_COMPONENT",
        (Fraction(1), Fraction(-1), Fraction(-1), Fraction(1)),
        (
            ("DIRECT", "DESIGN_QA"),
            ("PRODUCT_QA", "RICH"),
            ("DIRECT", "PRODUCT_QA"),
            ("DESIGN_QA", "RICH"),
        ),
    ),
    (
        "DESIGN_QA_VS_PRODUCT_QA_DESCRIPTIVE",
        (Fraction(0), Fraction(1), Fraction(-1), Fraction(0)),
        (("DESIGN_QA", "PRODUCT_QA"),),
    ),
)


def _factorial_contrasts(valid: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for contrast_id, coefficients, pairs in _CONTRASTS:
        per_attempt: list[dict[str, Any]] = []
        counts = {"first": 0, "second": 0, "tie": 0, "indeterminate": 0}
        for index in valid:
            labels = _labels_from_validated_join(index["private_blinding_join"])
            payload = index["integrated_payload"]
            relations = [
                _pair_relation(payload, labels, first, second)
                for first, second in pairs
            ]
            for relation in relations:
                counts[relation["outcome"].lower()] += 1
            per_attempt.append(
                {
                    "attempt_id": index["attempt_record"]["attempt_id"],
                    "relations": relations,
                }
            )
        result.append(
            {
                "contrast_id": contrast_id,
                "coefficients": [
                    {"arm_id": arm, "coefficient": _fraction_record(coefficient)}
                    for arm, coefficient in zip(_ARMS, coefficients, strict=True)
                ],
                "per_attempt": per_attempt,
                "aggregate_relation_counts": counts,
                "scalar_effect": None,
            }
        )
    return result


def _receipt_tokens(index: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(row["call_slot_id"]): int(row["record"]["usage"]["reported_total_tokens"])
        for row in index["receipts"]
    }


def _elapsed_values(index: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(row["call_slot_id"]): int(row["elapsed_ms"])
        for row in index["elapsed_ms"]
    }


def _materialize_deterministic_primary_suffix(
    index: dict[str, Any],
) -> dict[str, Any]:
    """Derive the provider-free primary suffix for an interrupted VALID block."""

    record = index.get("attempt_record")
    if (
        not isinstance(record, Mapping)
        or record.get("status") != "VALID"
        or record.get("interrupted") is not True
        or index.get("evidence_variant") != "PARTIAL"
    ):
        return index
    oriented = index.get("oriented_primary")
    primary = index.get("hard_primary_outcome")
    if oriented is not None and primary is not None:
        return index
    if oriented is not None or primary is not None:
        _fail("synthesis_provider_authority_incomplete")

    join = index.get("private_blinding_join")
    integrated = index.get("integrated_payload")
    review_rows = index.get("reviews")
    hard_rows = index.get("hard_evaluations")
    if (
        not isinstance(join, Mapping)
        or not isinstance(integrated, Mapping)
        or not isinstance(review_rows, list)
        or not isinstance(hard_rows, list)
        or len(hard_rows) != len(_ARMS)
    ):
        _fail("synthesis_provider_authority_incomplete")
    integrated_row = next(
        (
            row
            for row in review_rows
            if isinstance(row, Mapping)
            and row.get("call_slot_id") == "EVAL.INTEGRATED_REVIEW"
        ),
        None,
    )
    if not isinstance(integrated_row, Mapping):
        _fail("synthesis_provider_authority_incomplete")
    labels = _labels_from_validated_join(join)
    if set(labels) != set(_ARMS):
        _fail("synthesis_provider_authority_incomplete")
    pair_rows = integrated.get("pairwise_results")
    if not isinstance(pair_rows, list):
        _fail("synthesis_provider_authority_incomplete")
    primary_pair = next(
        (
            row
            for row in pair_rows
            if isinstance(row, Mapping)
            and {row.get("candidate_a_label"), row.get("candidate_b_label")}
            == {labels["RICH"], labels["DIRECT"]}
        ),
        None,
    )
    if not isinstance(primary_pair, Mapping):
        _fail("synthesis_provider_authority_incomplete")
    call_authority = index.get("call_authority")
    if not isinstance(call_authority, Mapping):
        _fail("synthesis_provider_authority_incomplete")
    try:
        checked_hard_rows, hard_freezes = _validated_hard_evaluations(
            hard_rows,
            labels_by_arm=labels,
            attempt_record=record,
            evaluation_authority=_evaluation_authority(call_authority),
        )
        raw = _oriented_primary_from_pair(
            primary_pair,
            rich_label=labels["RICH"],
            direct_label=labels["DIRECT"],
        )
        oriented_record = blinding.OrientedPrimaryPair(
            rich_vs_direct=raw,
            source_pair_row_digest=_study_digest(primary_pair),
            integrated_review_record_digest=str(
                integrated_row["record_sha256"]
            ),
            hard_evidence_record_digest=_study_digest(checked_hard_rows),
            unblinding_map_digest=canonical_sha256(join),
        ).record
        primary_record = hard_contract.derive_primary_outcome(
            raw_outcome=raw,
            rich_freeze=hard_freezes["RICH"],
            direct_freeze=hard_freezes["DIRECT"],
        ).record
    except (
        KeyError,
        TypeError,
        blinding.BlindingJoinError,
        hard_contract.HardContractError,
        SynthesisError,
    ) as exc:
        raise SynthesisError("synthesis_provider_authority_incomplete") from exc

    materialized = _canonical_copy(index)
    materialized["oriented_primary"] = oriented_record
    materialized["oriented_primary_sha256"] = _study_digest(oriented_record)
    materialized["hard_primary_outcome"] = primary_record
    materialized["hard_primary_outcome_sha256"] = _study_digest(primary_record)
    return materialized


def synthesize_report(
    *,
    indexed_attempts: Sequence[Mapping[str, object]],
    expected_index_digests: Sequence[str],
    decision_lock: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> dict[str, Any]:
    """Regenerate one terminal ES report solely from immutable attempt indexes."""

    lock, schedule, schema_digest = _checked_contract(
        decision_lock,
        randomization_manifest,
        expected_bindings,
    )
    if (
        isinstance(indexed_attempts, (str, bytes))
        or not isinstance(indexed_attempts, Sequence)
        or not indexed_attempts
        or isinstance(expected_index_digests, (str, bytes))
        or not isinstance(expected_index_digests, Sequence)
        or len(indexed_attempts) != len(expected_index_digests)
        or len(indexed_attempts) > 4
    ):
        _fail("synthesis_attempt_index_domain_invalid")
    validated_indexes = [
        validate_attempt_evidence_index(
            value,
            expected_index_sha256=expected,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=expected_bindings,
        )
        for value, expected in zip(
            indexed_attempts,
            expected_index_digests,
            strict=True,
        )
    ]
    indexes = [
        _materialize_deterministic_primary_suffix(index)
        for index in validated_indexes
    ]
    attempt_ids = [str(row["attempt_record"]["attempt_id"]) for row in indexes]
    locked_ids = list(lock["schedule"]["attempt_ids"])
    if attempt_ids != locked_ids[: len(attempt_ids)]:
        _fail("synthesis_attempt_sequence_invalid")

    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    non_tied: list[str] = []
    stopped = False
    for row in indexes:
        record = row["attempt_record"]
        if stopped:
            _fail("synthesis_post_stop_attempt")
        if record["status"] == "INVALID":
            invalid.append(row)
            if len(invalid) > 1:
                stopped = True
            continue
        valid.append(row)
        outcome = str(row["hard_primary_outcome"]["derived_outcome"])
        if outcome in {"RICH", "DIRECT"}:
            non_tied.append(outcome)
        if len(non_tied) == 2 or len(valid) == 3:
            stopped = True
    if not stopped:
        _fail("synthesis_attempt_missing")

    indexed_summary: list[dict[str, Any]] = []
    for row in indexes:
        record = row["attempt_record"]
        indexed_summary.append(
            {
                "attempt_id": record["attempt_id"],
                "status": record["status"],
                "invalidity_code": record["invalidity_code"],
                "index_sha256": row["index_sha256"],
                "attempt_record_sha256": row["attempt_record_sha256"],
                "packet_set_digest": (
                    None
                    if row["public_packet_replay_inputs"] is None
                    else row["public_packet_replay_inputs"][
                        "packet_artifact_index"
                    ]["packet_set_digest"]
                ),
                "private_join_sha256": row["private_blinding_join_sha256"],
                "review_sha256s": [value["record_sha256"] for value in row["reviews"]],
                "hard_evaluation_sha256s": [
                    value["freeze_sha256"]
                    for value in row["hard_evaluations"]
                    if value["trusted_product_freeze_status"] == "PRESENT"
                ],
                "call_allocation_sha256s": [
                    value["allocation_sha256"] for value in row["call_allocations"]
                ],
                "hard_primary_sha256": row["hard_primary_outcome_sha256"],
                "receipt_sha256s": [
                    value["record_sha256"] for value in row["receipts"]
                ],
                "elapsed_row_sha256s": [
                    value["row_sha256"] for value in row["elapsed_ms"]
                ],
            }
        )

    four_arm_vectors: list[dict[str, Any]] = []
    primary_sequence: list[dict[str, Any]] = []
    hard_findings: list[dict[str, Any]] = []
    failure_classes: list[dict[str, Any]] = []
    rich_failures = 0
    direct_failures = 0
    unresolved_rich = False
    arm_token_rows: list[dict[str, Any]] = []
    evaluation_token_rows: list[dict[str, Any]] = []
    ratio_rows: list[dict[str, Any]] = []
    ratios: list[Fraction] = []
    ratio_undefined = False
    call_accounting: list[dict[str, Any]] = []
    call_allocations: list[dict[str, Any]] = []
    for index in indexes:
        record = index["attempt_record"]
        attempt_id = str(record["attempt_id"])
        call_allocations.extend(
            {"attempt_id": attempt_id, **allocation}
            for allocation in index["call_allocations"]
        )
        for receipt_row, elapsed_row in zip(
            index["receipts"],
            index["elapsed_ms"],
            strict=True,
        ):
            receipt = receipt_row["record"]
            usage = receipt["usage"]
            slot = str(receipt_row["call_slot_id"])
            call_accounting.append(
                {
                    "attempt_id": attempt_id,
                    "call_slot_id": slot,
                    "role_id": receipt["role_id"],
                    "category": (
                        "EVALUATION" if slot.startswith("EVAL.") else "TREATMENT"
                    ),
                    "receipt_sha256": receipt_row["record_sha256"],
                    "elapsed_row_sha256": elapsed_row["row_sha256"],
                    "timing_source": elapsed_row["timing_source"],
                    "input_tokens": usage["input_tokens"],
                    "cached_input_tokens": usage["cached_input_tokens"],
                    "cache_write_input_tokens": usage[
                        "cache_write_input_tokens"
                    ],
                    "output_tokens": usage["output_tokens"],
                    "reasoning_output_tokens": usage[
                        "reasoning_output_tokens"
                    ],
                    "reported_total_tokens": usage["reported_total_tokens"],
                    "elapsed_ms": elapsed_row["elapsed_ms"],
                }
            )
        if record["status"] == "INVALID":
            public_replay = index["public_packet_replay_inputs"]
            if public_replay is not None:
                packet_index = public_replay["packet_artifact_index"]
                public_arm_by_label = {
                    row["opaque_label"]: row["cell"]["arm_id"]
                    for row in packet_index["packets"]
                }
                for scorer in index["scorer_settlements"]:
                    score = scorer["score_row"]
                    if score["score_status"] == "evaluation_failed":
                        failure_classes.append(
                            {
                                "attempt_id": attempt_id,
                                "arm_id": public_arm_by_label[
                                    scorer["opaque_label"]
                                ],
                                "failure_class": "EVALUATION_FAILURE",
                                "failure_code": score["failure"]["code"],
                            }
                        )
            partial_routes = {
                row["arm"]: row["route_id"]
                for row in record["accounting"]["arm_routes"]
            }
            for settlement in record["e2_authority"]["arm_settlements"]:
                arm = settlement["cell"]["arm_id"]
                if settlement["status"] == "failed":
                    failure_classes.append(
                        {
                            "attempt_id": attempt_id,
                            "arm_id": arm,
                            "failure_class": "TREATMENT_METHOD_FAILURE",
                            "failure_code": partial_routes.get(
                                arm, "TERMINAL_TREATMENT_FAILURE"
                            ),
                        }
                    )
            for review in index["reviews"]:
                if review["status"] == "FAILED":
                    failure_classes.append(
                        {
                            "attempt_id": attempt_id,
                            "arm_id": None,
                            "failure_class": "EVALUATION_FAILURE",
                            "failure_code": review["record"]["failure_code"],
                        }
                    )
            failure_classes.append(
                {
                    "attempt_id": attempt_id,
                    "arm_id": None,
                    "failure_class": "APPARATUS_INVALID",
                    "failure_code": record["invalidity_code"],
                }
            )
            continue
        join = index["private_blinding_join"]
        labels = _labels_from_validated_join(join)
        arm_by_label = {label: arm for arm, label in labels.items()}
        for scorer in index["scorer_settlements"]:
            score = scorer["score_row"]
            if score["score_status"] == "evaluation_failed":
                failure_classes.append(
                    {
                        "attempt_id": attempt_id,
                        "arm_id": arm_by_label[scorer["opaque_label"]],
                        "failure_class": "EVALUATION_FAILURE",
                        "failure_code": score["failure"]["code"],
                    }
                )
        token_by_slot = _receipt_tokens(index)
        elapsed_by_slot = _elapsed_values(index)
        settlements = {
            row["cell"]["arm_id"]: row
            for row in record["e2_authority"]["arm_settlements"]
        }
        route_ids = {
            row["arm"]: row["route_id"] for row in record["accounting"]["arm_routes"]
        }
        freeze_by_arm = {
            row["arm_id"]: row for row in index["hard_evaluations"]
        }
        arms: list[dict[str, Any]] = []
        arm_totals: dict[str, int] = {}
        for arm in _ARMS:
            prefix = f"{arm}."
            slots = [slot for slot in token_by_slot if slot.startswith(prefix)]
            tokens = sum(token_by_slot[slot] for slot in slots)
            elapsed = sum(elapsed_by_slot[slot] for slot in slots)
            arm_totals[arm] = tokens
            arm_token_rows.append(
                {"attempt_id": attempt_id, "arm_id": arm, "value": tokens}
            )
            failed = settlements[arm]["status"] == "failed"
            if failed:
                failure_classes.append(
                    {
                        "attempt_id": attempt_id,
                        "arm_id": arm,
                        "failure_class": "TREATMENT_METHOD_FAILURE",
                        "failure_code": str(route_ids[arm]),
                    }
                )
            if arm == "RICH" and failed:
                rich_failures += 1
            if arm == "DIRECT" and failed:
                direct_failures += 1
            arms.append(
                {
                    "arm_id": arm,
                    "opaque_label": labels[arm],
                    "settlement": "METHOD_FAILED" if failed else "COMPLETED",
                    "route_id": route_ids[arm],
                    "treatment_call_count": len(slots),
                    "reported_total_tokens": tokens,
                    "elapsed_ms": elapsed,
                    "hard_evidence_status": freeze_by_arm[arm][
                        "trusted_product_freeze_status"
                    ],
                    "hard_evaluation_freeze_sha256": freeze_by_arm[arm].get(
                        "freeze_sha256"
                    ),
                }
            )
            if freeze_by_arm[arm]["trusted_product_freeze_status"] == "MISSING":
                continue
            freeze = freeze_by_arm[arm]["freeze"]
            evaluation = freeze_by_arm[arm]["evaluation"]
            if arm == "RICH" and freeze["unresolved_blockers"]:
                unresolved_rich = True
            for finding in evaluation["hard_findings"]:
                hard_findings.append(
                    {
                        "attempt_id": attempt_id,
                        "arm_id": arm,
                        "freeze_sha256": freeze["freeze_digest"],
                        "finding_sha256": _study_digest(finding),
                        "clause_id": finding["clause_id"],
                        "disposition": finding["disposition"],
                    }
                )
        evaluation_tokens = sum(
            token_by_slot[slot]
            for slot in token_by_slot
            if slot.startswith("EVAL.")
        )
        evaluation_token_rows.append(
            {"attempt_id": attempt_id, "status": "VALID", "value": evaluation_tokens}
        )
        direct_tokens = arm_totals["DIRECT"]
        if direct_tokens == 0:
            ratio_undefined = True
            ratio_rows.append(
                {
                    "attempt_id": attempt_id,
                    "ratio_status": "UNDEFINED_ZERO_REFERENCE",
                    "ratio": None,
                }
            )
        else:
            ratio = Fraction(arm_totals["RICH"], direct_tokens)
            ratios.append(ratio)
            ratio_rows.append(
                {
                    "attempt_id": attempt_id,
                    "ratio_status": "DEFINED",
                    "ratio": _fraction_record(ratio),
                }
            )
        four_arm_vectors.append({"attempt_id": attempt_id, "arms": arms})
        primary = index["hard_primary_outcome"]
        primary_sequence.append(
            {
                "attempt_id": attempt_id,
                "raw_outcome": primary["raw_outcome"],
                "derived_outcome": primary["derived_outcome"],
                "hard_primary_sha256": index["hard_primary_outcome_sha256"],
            }
        )
        for review in index["reviews"]:
            if review["status"] == "FAILED":
                failure_classes.append(
                    {
                        "attempt_id": attempt_id,
                        "arm_id": None,
                        "failure_class": "EVALUATION_FAILURE",
                        "failure_code": review["record"]["failure_code"],
                    }
                )

    viability_passes = rich_failures <= direct_failures
    viability = {
        "rule": "RICH_TREATMENT_FAILURES_LTE_DIRECT",
        "rich_treatment_failures": rich_failures,
        "direct_treatment_failures": direct_failures,
        "passes": viability_passes,
    }
    median_ratio = None if ratio_undefined or not ratios else _median(ratios)
    ratio_cap = decision_lock_authority.parse_canonical_decimal(
        lock["authored_choices"]["maximum_median_rich_direct_token_cost_ratio"]
    )
    ratio_passes = median_ratio is not None and median_ratio <= ratio_cap
    call_rows = [
        {
            "attempt_id": index["attempt_record"]["attempt_id"],
            "status": index["attempt_record"]["status"],
            "value": len(index["call_allocations"]),
        }
        for index in indexes
    ]
    token_rows = [
        {
            "attempt_id": index["attempt_record"]["attempt_id"],
            "status": index["attempt_record"]["status"],
            "value": sum(_receipt_tokens(index).values()),
        }
        for index in indexes
    ]
    elapsed_rows = [
        {
            "attempt_id": index["attempt_record"]["attempt_id"],
            "status": index["attempt_record"]["status"],
            "value": sum(_elapsed_values(index).values()),
        }
        for index in indexes
    ]
    distributions = {
        "calls": {
            "unit": "PROVIDER_INVOCATIONS",
            "per_attempt": call_rows,
            "values": [row["value"] for row in call_rows],
            "total": sum(row["value"] for row in call_rows),
        },
        "tokens": {
            "unit": "CODEX_REPORTED_TOTAL_TOKENS",
            "per_attempt": token_rows,
            "values": [row["value"] for row in token_rows],
            "total": sum(row["value"] for row in token_rows),
            "arm_treatment_totals": arm_token_rows,
            "evaluation_totals": evaluation_token_rows,
            "rich_direct_ratios": ratio_rows,
            "median_rich_direct_ratio": (
                None if median_ratio is None else _fraction_record(median_ratio)
            ),
        },
        "elapsed_time": {
            "unit": "MILLISECONDS",
            "per_attempt": elapsed_rows,
            "values": [row["value"] for row in elapsed_rows],
            "total": sum(row["value"] for row in elapsed_rows),
        },
    }
    absolute_call_ceiling = lock["derived"]["call_bounds"][
        "absolute_with_invalid_attempt_capacity"
    ]
    if distributions["calls"]["total"] > absolute_call_ceiling:
        _fail("synthesis_call_allocation_ceiling_exceeded")
    decision = {
        "required_non_tied_comparisons": 2,
        "maximum_valid_blocks": 3,
        "critical_rich_wins": 2,
        "valid_block_count": len(valid),
        "invalid_attempt_count": len(invalid),
        "non_tied_count": len(non_tied),
        "rich_win_count": non_tied.count("RICH"),
        "non_tied_target_reached": len(non_tied) == 2,
        "all_non_tied_favor_rich": len(non_tied) == 2
        and all(value == "RICH" for value in non_tied),
        "viability_passes": viability_passes,
        "all_cost_cells_known": True,
        "median_rich_direct_token_ratio_at_most_cap": ratio_passes,
        "no_unresolved_rich_blocker": not unresolved_rich,
    }
    if len(invalid) > 1:
        screen = "STOP_ES_INVALID"
    elif len(non_tied) < 2:
        screen = "INSUFFICIENT_EVIDENCE"
    elif not (
        decision["all_non_tied_favor_rich"]
        and decision["viability_passes"]
        and decision["all_cost_cells_known"]
        and decision["median_rich_direct_token_ratio_at_most_cap"]
        and decision["no_unresolved_rich_blocker"]
    ):
        screen = "SCREEN_NOT_PASSED"
    else:
        screen = "SCREEN_PASSED"
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "decision_lock_sha256": decision_lock_authority.decision_lock_digest(lock),
        "randomization_manifest_sha256": decision_lock_authority.decision_lock_digest(
            schedule
        ),
        "report_schema_sha256": schema_digest,
        "indexed_attempts": indexed_summary,
        "four_arm_vectors": four_arm_vectors,
        "primary_sequence": primary_sequence,
        "factorial_mechanism_contrasts": _factorial_contrasts(valid),
        "hard_findings": hard_findings,
        "viability": viability,
        "call_allocations": call_allocations,
        "call_accounting": call_accounting,
        "distributions": distributions,
        "failure_classes": failure_classes,
        "decision": decision,
        "claim_limits": deepcopy(lock["claim_limits"]),
        "screen_result": screen,
        "e3_readiness_input": (
            "BLACK_BOX_SUFFICIENT"
            if screen == "SCREEN_PASSED"
            else "STOP_E3_HYPOTHESIS"
        ),
    }
    errors = sorted(
        Draft202012Validator(_load_schema(_SCHEMA_PATH)).iter_errors(report),
        key=str,
    )
    if errors:
        _fail("synthesis_report_schema_invalid", errors[0].message)
    return report


__all__ = [
    "ATTEMPT_INDEX_SCHEMA_VERSION",
    "REPORT_SCHEMA_VERSION",
    "SynthesisError",
    "build_attempt_evidence_index",
    "build_invalid_attempt_evidence_index",
    "canonical_report_bytes",
    "synthesize_report",
    "validate_attempt_evidence_index",
]
