from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from jsonschema import Draft202012Validator
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from orchestrator.workflow.run_ref.contracts import canonical_sha256  # noqa: E402
from orchestrator.workflow.trial.contracts import (  # noqa: E402
    TrialCellKey,
    build_sealed_opaque_label_map,
)
from orchestrator.workflow.trial import ledger as trial_ledger  # noqa: E402
from scripts.experiments.es import (  # noqa: E402
    blinding,
    decision_lock,
    f1_evaluator,
    hard_contract,
    metering,
    reviews,
)


SCHEMA_PATH = ROOT / "experiments/orc_effectiveness/f1_es/report.schema.json"
ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
SCIENTIFIC = "SCIENTIFIC_APPLICATION_SEMANTICS"
API = "API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
FAILED_CLAUSE = "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"


def _study_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _study_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_study_bytes(value)).hexdigest()


def _raw_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha(fill: str) -> str:
    return "sha256:" + fill * 64


def _closed_schemas(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for member in value.values():
            _closed_schemas(member)
    elif isinstance(value, list):
        for member in value:
            _closed_schemas(member)


def _call_authority() -> dict[str, Any]:
    executable_chain = {
        "provider_family": "codex-cli",
        "version": "codex-cli 0.145.0",
        "launcher_path": "/opt/codex",
        "launcher_sha256": "sha256:134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477",
        "interpreter_path": "/opt/node",
        "interpreter_sha256": _sha("6"),
    }
    argv = [
        "/opt/codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.5",
        "--config",
        "model_reasoning_effort=high",
        "--",
        "-",
    ]
    slots = decision_lock._receipt_call_slots(
        decision_lock.derive_terminal_routes(),
        decision_lock.derive_evaluation_routes(),
    )
    return {
        "schema_version": "es.frozen_call_authority.v1",
        "prompt_manifest": {
            "schema_version": "es.prompt_manifest.v1",
            "calls": [
                {
                    "call_slot_id": slot,
                    "role_id": slot,
                    "prompt_sha256": _sha("3"),
                    "contract_sha256": _sha("4"),
                    "normalized_argv": argv,
                }
                for slot in slots
            ],
        },
        "environment_lock": {
            "schema_version": "es.environment_lock.v1",
            "provider_family": "codex-cli",
            "version": "codex-cli 0.145.0",
            "model": "gpt-5.5",
            "reasoning_effort": "high",
            "prompt_transport": "STDIN",
            "executable_chain": executable_chain,
            "evaluation_authority": {
                "schema_version": "es.evaluation_authority.v1",
                "hard_evaluator_identity_digest": _sha("c"),
                "hard_task_identity_digest": _sha("d"),
                "hard_fixture_identity_digest": _sha("e"),
                "scorer_evaluation_digest": _sha("d"),
                "scorer_identity_digest": _sha("f"),
            },
        },
    }


def _call_allocations(
    synthesis,
    lock: Mapping[str, Any],
    *,
    attempt_id: str,
    rows: list[tuple[str, str, str | None]],
) -> list[dict[str, Any]]:
    frozen = _call_authority()
    executable_chain = frozen["environment_lock"]["executable_chain"]
    static_by_slot = {
        row["call_slot_id"]: {**row, "executable_chain": executable_chain}
        for row in frozen["prompt_manifest"]["calls"]
    }
    result: list[dict[str, Any]] = []
    previous: str | None = None
    for sequence, (slot, settlement, receipt_sha256) in enumerate(rows, start=1):
        allocation = synthesis._allocation_row(
            attempt_id=attempt_id,
            call_slot_id=slot,
            sequence=sequence,
            previous_allocation_sha256=previous,
            decision_lock_sha256=decision_lock.decision_lock_digest(lock),
            static_call_sha256=canonical_sha256(static_by_slot[slot]),
            settlement=settlement,
            receipt_sha256=receipt_sha256,
        )
        result.append(allocation)
        previous = allocation["allocation_sha256"]
    return result


def _rechain_allocations(
    synthesis,
    lock: Mapping[str, Any],
    *,
    attempt_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _call_allocations(
        synthesis,
        lock,
        attempt_id=attempt_id,
        rows=[
            (row["call_slot_id"], row["settlement"], row["receipt_sha256"])
            for row in rows
        ],
    )


def _lock_and_schedule() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    schedule = decision_lock.generate_randomization_manifest(_sha("a"))
    authority = _call_authority()
    bindings = {
        "arm_workflow_sha256": _sha("1"),
        "environment_lock_sha256": canonical_sha256(
            authority["environment_lock"]
        ),
        "evaluator_fixture_manifest_sha256": _sha("3"),
        "prompt_manifest_sha256": canonical_sha256(authority["prompt_manifest"]),
        "randomization_manifest_sha256": decision_lock.decision_lock_digest(
            schedule
        ),
        "report_schema_sha256": _raw_digest(SCHEMA_PATH),
        "source_projection_manifest_sha256": _sha("7"),
        "task_profile_sha256": _sha("8"),
        "task_seed_manifest_sha256": _sha("9"),
    }
    return (
        decision_lock.build_decision_lock(
            bindings=bindings,
            randomization_manifest=schedule,
        ),
        schedule,
        bindings,
    )


def _hard_replay_inputs(
    candidate_id: str,
    *,
    unresolved: bool = False,
    oracle_defect: bool = False,
) -> dict[str, Any]:
    assert not (unresolved and oracle_defect)
    failed_hard_clause = unresolved or oracle_defect
    observations = [
        {
            "clause_id": clause_id,
            "details": "controller observation",
            "evidence": [_sha(f"{index:x}")],
            "satisfied": not (failed_hard_clause and clause_id == FAILED_CLAUSE),
        }
        for index, clause_id in enumerate(f1_evaluator.HARD_CLAUSE_IDS, start=1)
    ]
    proof_rows: list[dict[str, Any]] = []
    if failed_hard_clause:
        failed = next(
            row for row in observations if row["clause_id"] == FAILED_CLAUSE
        )
        proof_rows.append(
            {
                "schema_version": "es.hard_disposition_proof.v1",
                "proof_kind": "ORACLE_CONTRADICTION",
                "candidate_id": candidate_id,
                "clause_id": FAILED_CLAUSE,
                "observation_digest": _study_digest(failed),
                "evidence_digest": _study_digest(failed["evidence"]),
                "control_digests": [_sha("7")],
                "requirement_digests": [],
                "treatment_local": False,
                "evaluator_identity_digest": _sha("c"),
                "task_identity_digest": _sha("d"),
                "fixture_identity_digest": _sha("e"),
            }
        )
    frozen_proof_authority = []
    if oracle_defect:
        proof = proof_rows[0]
        frozen_proof_authority = [
            {
                "schema_version": "es.hard_proof_authority.v1",
                "proof_kind": proof["proof_kind"],
                "candidate_id": candidate_id,
                "clause_id": FAILED_CLAUSE,
                "control_digests": deepcopy(proof["control_digests"]),
                "requirement_digests": [],
                "evaluator_identity_digest": _sha("c"),
                "task_identity_digest": _sha("d"),
                "fixture_identity_digest": _sha("e"),
            }
        ]
    return {
        "schema_version": "es.hard_evaluation_replay_inputs.v1",
        "candidate_claims": {
            "candidate_id": candidate_id,
            "nominated_architectures": {
                "representative": "ffno",
                "witness": "es_f1_witness",
            },
            "structural_fields": [
                {"name": "width", "baseline": 4, "alternate": 8}
            ],
            "claims": [
                {
                    "claim_id": "PUBLIC_CONSTRUCTION",
                    "evidence_path": "tests/control.json",
                }
            ],
        },
        "evaluator_observations": observations,
        "proof_rows": proof_rows,
        "frozen_registry": ["ffno"],
        "trusted_product_freeze_digest": _sha("b"),
        "evaluator_identity_digest": _sha("c"),
        "task_identity_digest": _sha("d"),
        "fixture_identity_digest": _sha("e"),
        "frozen_proof_authority": frozen_proof_authority,
    }


def _hard_freeze(
    candidate_id: str,
    *,
    unresolved: bool = False,
    oracle_defect: bool = False,
) -> hard_contract.HardEvaluationFreeze:
    replay = _hard_replay_inputs(
        candidate_id,
        unresolved=unresolved,
        oracle_defect=oracle_defect,
    )
    return _freeze_from_replay(replay)


def _freeze_from_replay(
    replay: Mapping[str, Any],
) -> hard_contract.HardEvaluationFreeze:
    return hard_contract.derive_hard_evaluation(
        candidate_claims=replay["candidate_claims"],
        evaluator_observations=replay["evaluator_observations"],
        proof_rows=replay["proof_rows"],
        frozen_registry=set(replay["frozen_registry"]),
        trusted_product_freeze_digest=replay["trusted_product_freeze_digest"],
        evaluator_identity_digest=replay["evaluator_identity_digest"],
        task_identity_digest=replay["task_identity_digest"],
        fixture_identity_digest=replay["fixture_identity_digest"],
        frozen_proof_authority=replay["frozen_proof_authority"],
    )


def _packet(label: str) -> dict[str, Any]:
    return {
        "schema": "trial.evaluation_packet.v1",
        "evaluation_id": label,
        "items": [
            {
                "id": "task_spec",
                "kind": "task_spec",
                "value": {"contract": "frozen"},
            }
        ],
        "citable_item_ids": ["task_spec"],
    }


def _pair_payload(
    labels: tuple[str, ...],
    *,
    rich_label: str,
    direct_label: str,
    outcome: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for left, right in reviews.canonical_pair_order(labels):
        pair_outcome = "TIE"
        if {left, right} == {rich_label, direct_label}:
            if outcome in {"TIE", "INDETERMINATE"}:
                pair_outcome = outcome
            else:
                winner = rich_label if outcome == "RICH" else direct_label
                pair_outcome = "A" if left == winner else "B"
        rows.append(
            {
                "candidate_a_label": left,
                "candidate_b_label": right,
                "outcome": pair_outcome,
                "rationale": "bounded packet-local comparison",
                "citations": [
                    {"opaque_label": left, "citable_item_id": "task_spec"},
                    {"opaque_label": right, "citable_item_id": "task_spec"},
                ],
            }
        )
    return {
        "schema_version": "es-f1-integrated-review.v1",
        "pairwise_results": rows,
    }


def _initial_payload(
    labels: tuple[str, ...],
    perspective: str,
    pair_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    perspective_rows = json.loads(
        (
            ROOT
            / "experiments/orc_effectiveness/f1_es/evaluator/reviewer-perspectives.json"
        ).read_text(encoding="utf-8")
    )["perspectives"]
    dimensions = next(
        row["owned_dimensions"]
        for row in perspective_rows
        if row["perspective_id"] == perspective
    )
    schema = {
        SCIENTIFIC: (
            "es-f1-initial-scientific-application-semantics-review.v1"
        ),
        API: "es-f1-initial-api-persistence-migration-maintainability-review.v1",
    }[perspective]
    return {
        "schema_version": schema,
        "candidates": [
            {
                "opaque_label": label,
                "dimensions": [
                    {
                        "dimension": dimension,
                        "assessment": "PASS",
                        "rationale": "bounded packet-local assessment",
                        "citations": [
                            {
                                "opaque_label": label,
                                "citable_item_id": "task_spec",
                            }
                        ],
                    }
                    for dimension in dimensions
                ],
            }
            for label in labels
        ],
        "pairwise_results": deepcopy(pair_rows),
    }


def _review_failure_record(
    *,
    attempt_id: str,
    call_slot_id: str,
    ordinal: int,
) -> dict[str, Any]:
    return {
        "schema_version": "es_evaluator_call_failure.v1",
        "attempt_id": attempt_id,
        "call_slot_id": call_slot_id,
        "session_id": f"{attempt_id}-review-session-{ordinal}",
        "provider_attempt_id": f"{attempt_id}-review-provider-{ordinal}",
        "receipt_digest": _sha(str(ordinal)),
        "failure_code": "TYPED_OUTPUT_INVALID",
    }


def _receipt(
    attempt_id: str,
    slot: str,
    *,
    tokens: int,
    ordinal: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> tuple[dict[str, Any], bytes]:
    authority = _call_authority()
    call = next(
        row
        for row in authority["prompt_manifest"]["calls"]
        if row["call_slot_id"] == slot
    )
    argv = deepcopy(call["normalized_argv"])
    session_id = f"{attempt_id}-session-{ordinal:02d}"
    raw = (
        json.dumps(
            {"type": "thread.started", "thread_id": session_id},
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": tokens,
                    "cached_input_tokens": cached_tokens,
                    "cache_write_input_tokens": cache_write_tokens,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                },
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    usage = metering.parse_codex_jsonl(raw, expected_session_id=session_id)
    receipt = metering.build_usage_receipt(
        usage,
        study_id="F1-ES",
        block_id=attempt_id,
        role_id=slot,
        call_slot_id=slot,
        provider_attempt_id=f"{attempt_id}-provider-{ordinal:02d}",
        prompt_sha256=call["prompt_sha256"],
        contract_sha256=call["contract_sha256"],
        raw_jsonl_path=f"receipts/{attempt_id.lower()}-{ordinal:02d}.jsonl",
        executable_chain=authority["environment_lock"]["executable_chain"],
        process={
            "argv": argv,
            "pid": 1_000 + ordinal,
        },
        exit_status=0,
    )
    return receipt, raw


def _score_evidence(
    *,
    packets: Mapping[str, Mapping[str, Any]],
    labels_by_arm: Mapping[str, str],
    failed_arm: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    score_rows: dict[str, dict[str, Any]] = {}
    settlement_rows: dict[str, dict[str, Any]] = {}
    for ordinal, arm in enumerate(ARMS, start=1):
        label = labels_by_arm[arm]
        failed = arm == failed_arm
        identity = {
            "schema_version": "trial_score_identity.v1",
            "trial_request_digest": _sha("9"),
            "evaluation_digest": _sha("d"),
            "evidence_frozen_digest": _sha("c"),
            "evaluation_label": label,
            "evaluation_packet_digest": canonical_sha256(packets[arm]),
            "scorer_identity_digest": _sha("f"),
        }
        score_body: dict[str, Any] = {
            "row_schema": "trial.score.v1",
            "score_run_key": canonical_sha256(identity),
            **{key: value for key, value in identity.items() if key != "schema_version"},
            "score_status": "evaluation_failed" if failed else "scored",
            "score": None if failed else 0.75,
            "summary": None if failed else "packet-local score",
            "citations": [] if failed else ["task_spec"],
            "attempt_count": 1,
            "charged_attempts": [
                {
                    "attempt": 1,
                    "global_attempt": ordinal,
                    "status": "output_invalid" if failed else "scored",
                    "exit_code": 0,
                    "duration_ms": ordinal * 5,
                    "token_usage": {
                        "variant": "KNOWN",
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    },
                    "cost": {"variant": "UNKNOWN"},
                }
            ],
            "failure": (
                {"code": "SCORER_TYPED_OUTPUT_INVALID", "retryable": False}
                if failed
                else None
            ),
        }
        score_row = {
            **score_body,
            "row_content_digest": canonical_sha256(score_body),
        }
        settlement_preimage = {
            "schema_version": trial_ledger.TRIAL_EVENT_LEDGER_SCHEMA,
            "sequence": 100 + ordinal,
            "previous_row_digest": _sha(f"{ordinal + 8:x}"),
            "kind": "score_settled",
            "recorded_at": f"2026-08-03T00:00:0{ordinal}.000000Z",
            "payload": {
                "opaque_label": label,
                "score_row_content_digest": score_row["row_content_digest"],
                "terminal_attempt_settlement_row_digest": _sha(f"{ordinal:x}"),
            },
        }
        settlement = {
            **settlement_preimage,
            "row_digest": canonical_sha256(settlement_preimage),
        }
        score_rows[label] = score_row
        settlement_rows[label] = settlement
    return score_rows, settlement_rows


def _attempt_index(
    synthesis,
    lock: Mapping[str, Any],
    schedule: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    ordinal: int,
    outcome: str,
    rich_tokens: int = 200,
    direct_tokens: int = 100,
    rich_failed: bool = False,
    direct_failed: bool = False,
    rich_unresolved: bool = False,
    invalidity_code: str | None = None,
    failed_review_slot: str | None = None,
    adjudicator_failure: bool = False,
    raw_path_override: str | None = None,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    failed_scorer_arm: str | None = None,
    oracle_defect_arm: str | None = None,
    missing_freeze_arm: str | None = None,
    initial_disagreement_without_adjudicator: bool = False,
    adjudicator_with_agreement: bool = False,
    initial_rationale_difference: bool = False,
) -> dict[str, Any]:
    attempt_id = f"ES-ATTEMPT-{ordinal:02d}"
    schedule_row = schedule["attempts"][ordinal - 1]
    labels_by_arm = {
        arm: f"opaque-{ordinal * 10 + index:064x}"
        for index, arm in enumerate(ARMS, start=1)
    }
    packets = {arm: _packet(labels_by_arm[arm]) for arm in ARMS}
    request_cell_domain = tuple(TrialCellKey(arm, 1) for arm in ARMS)
    sealed_labels = build_sealed_opaque_label_map(
        request_cell_domain,
        labels=tuple(labels_by_arm[arm] for arm in ARMS),
    )
    packet_rows = [
        {
            "cell": TrialCellKey(arm, 1).record,
            "opaque_label": labels_by_arm[arm],
            "packet_digest": canonical_sha256(packets[arm]),
        }
        for arm in ARMS
    ]
    packet_set_digest = canonical_sha256(packet_rows)
    request_hex = _sha("9").removeprefix("sha256:")
    packet_index = {
        "schema_version": "trial.packet_artifact_index.v1",
        "trial_request_digest": _sha("9"),
        "header_row_digest": _sha("b"),
        "evidence_frozen_row_digest": _sha("c"),
        "checks_frozen_row_digest": _sha("d"),
        "packets_frozen_row_digest": _sha("e"),
        "sealed_opaque_label_map_digest": sealed_labels.digest,
        "packet_set_digest": packet_set_digest,
        "packets": [
            {
                **row,
                "packet_relpath": (
                    f"artifacts/trials/{request_hex}/packets/"
                    f"{row['packet_digest'].removeprefix('sha256:')}.json"
                ),
            }
            for row in packet_rows
        ],
    }
    public_packet_replay_inputs = {
        "schema_version": "es.public_packet_replay_inputs.v1",
        "request_cell_domain": [cell.record for cell in request_cell_domain],
        "packet_artifact_index": packet_index,
    }
    private_replay_inputs = {
        "schema_version": "es.private_blinding_replay_inputs.v2",
        "sealed_opaque_label_map": sealed_labels.record,
    }
    attempt_schedule = blinding.AttemptPackageSchedule(
        attempt_id=attempt_id,
        arm_order=tuple(schedule_row["arm_order"]),
        opaque_package_order=tuple(schedule_row["opaque_package_order"]),
        randomization_row_digest=decision_lock.decision_lock_digest(schedule_row),
        decision_lock_digest=decision_lock.decision_lock_digest(lock),
    )
    private_join = blinding.build_private_blinding_join(
        attempt=attempt_schedule,
        randomization_manifest=schedule,
        decision_lock=lock,
        expected_bindings=bindings,
        request_cell_domain=request_cell_domain,
        sealed_opaque_labels=sealed_labels,
        packet_index=packet_index,
    )
    rows = private_join.rows
    labels = tuple(
        next(row.opaque_label for row in rows if row.package_id == package)
        for package in attempt_schedule.opaque_package_order
    )
    pair_payload = _pair_payload(
        labels,
        rich_label=labels_by_arm["RICH"],
        direct_label=labels_by_arm["DIRECT"],
        outcome=outcome,
    )
    citable = {label: ("task_spec",) for label in labels}
    initial_scientific_payload = _initial_payload(
        labels,
        SCIENTIFIC,
        pair_payload["pairwise_results"],
    )
    initial_api_rows = deepcopy(pair_payload["pairwise_results"])
    if adjudicator_failure or initial_disagreement_without_adjudicator:
        initial_api_rows[0]["outcome"] = (
            "B" if initial_api_rows[0]["outcome"] != "B" else "A"
        )
    if initial_rationale_difference:
        initial_api_rows[0]["rationale"] = "Independent rationale, same outcome."
    initial_api_payload = _initial_payload(labels, API, initial_api_rows)
    review_specs: tuple[tuple[str, str, str | None], ...] = (
        ("EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS", "INITIAL", SCIENTIFIC),
        (
            "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
            "INITIAL",
            API,
        ),
    )
    if adjudicator_failure or adjudicator_with_agreement:
        review_specs += (("EVAL.ADJUDICATOR", "ADJUDICATOR", None),)
    review_specs += (("EVAL.INTEGRATED_REVIEW", "INTEGRATED", None),)
    review_records: dict[str, dict[str, Any]] = {}
    integrated_payload = pair_payload
    adjudication_payload: dict[str, Any] | None = None
    for review_index, (slot, kind, perspective) in enumerate(review_specs, start=1):
        is_failure = slot == failed_review_slot or (
            (adjudicator_failure or adjudicator_with_agreement)
            and slot == "EVAL.ADJUDICATOR"
        )
        if is_failure:
            review_records[slot] = _review_failure_record(
                attempt_id=attempt_id,
                call_slot_id=slot,
                ordinal=review_index,
            )
            continue
        if kind == "INITIAL":
            payload = (
                initial_scientific_payload
                if perspective == SCIENTIFIC
                else initial_api_payload
            )
        elif kind == "INTEGRATED":
            payload = integrated_payload
        else:
            raise AssertionError("test only models failed adjudication")
        review_records[slot] = reviews.seal_review_record(
            payload,
            attempt_id=attempt_id,
            review_kind=kind,
            perspective_id=perspective,
            session_id=f"{attempt_id}-review-session-{review_index}",
            provider_attempt_id=f"{attempt_id}-review-provider-{review_index}",
            receipt_digest=_sha(str(review_index)),
            packet_set_digest=packet_set_digest,
            presentation_order=labels,
            citable_item_ids_by_label=citable,
            existing_records=tuple(review_records.values()),
        )

    initial_records = (
        review_records["EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS"],
        review_records["EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"],
    )
    initial_failed = failed_review_slot in {
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    }
    if adjudicator_failure and not initial_failed:
        adjudication_payload = reviews.resolve_adjudication(
            *initial_records,
            review_records["EVAL.ADJUDICATOR"],
            citable_item_ids_by_label=citable,
        )
    if failed_review_slot == "EVAL.INTEGRATED_REVIEW":
        integrated_payload = reviews.resolve_integrated_review(
            review_records["EVAL.INTEGRATED_REVIEW"],
            attempt_id=attempt_id,
            packet_set_digest=packet_set_digest,
            presentation_order=labels,
            citable_item_ids_by_label=citable,
            existing_records=tuple(review_records.values())[:-1],
        )

    terminal_route_ids = {
        "DIRECT": "DIRECT.EMPTY" if direct_failed else "DIRECT.I",
        "DESIGN_QA": "DESIGN_QA.D_DR_I",
        "PRODUCT_QA": "PRODUCT_QA.I_PR",
        "RICH": "RICH.D_DR_I" if rich_failed else "RICH.D_DR_I_PR",
    }
    route_by_id = {
        row["route_id"]: row for row in lock["route_contract"]["terminal_routes"]
    }
    evaluation_route = next(
        row
        for row in lock["route_contract"]["evaluation_routes"]
        if row["adjudication"] is (adjudicator_failure or adjudicator_with_agreement)
    )
    slots: list[str] = []
    for arm in ARMS:
        slots.extend(route_by_id[terminal_route_ids[arm]]["call_slots"])
    slots.extend(evaluation_route["call_slots"])
    receipts: dict[str, dict[str, Any]] = {}
    raw_jsonl: dict[str, bytes] = {}
    for receipt_index, slot in enumerate(slots, start=1):
        token_count = 50
        if slot.startswith("RICH."):
            token_count = rich_tokens // 4
        elif slot.startswith("DIRECT."):
            token_count = direct_tokens
        receipt, raw = _receipt(
            attempt_id,
            slot,
            tokens=token_count,
            ordinal=receipt_index,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        receipts[slot] = receipt
        raw_jsonl[slot] = raw
    if raw_path_override is not None:
        first_slot = slots[0]
        receipts[first_slot]["raw_jsonl"]["path"] = raw_path_override
    for slot, record in review_records.items():
        record["receipt_digest"] = _study_digest(receipts[slot])
        if "payload" in record:
            record["payload_digest"] = reviews.canonical_payload_digest(record["payload"])

    status = "INVALID" if invalidity_code is not None else "VALID"
    arm_status = {
        "DIRECT": "failed" if direct_failed else "completed",
        "DESIGN_QA": "completed",
        "PRODUCT_QA": "completed",
        "RICH": "failed" if rich_failed else "completed",
    }
    review_settlements = [
        {
            "call_slot_id": slot,
            "status": (
                "FAILED"
                if slot == failed_review_slot
                or (
                    (adjudicator_failure or adjudicator_with_agreement)
                    and slot == "EVAL.ADJUDICATOR"
                )
                else "SUCCEEDED"
            ),
            "record_sha256": _study_digest(review_records[slot]),
            "receipt_sha256": _study_digest(receipts[slot]),
        }
        for slot, _kind, _perspective in review_specs
    ]
    score_rows, score_settlement_rows = _score_evidence(
        packets=packets,
        labels_by_arm=labels_by_arm,
        failed_arm=failed_scorer_arm,
    )
    attempt_record: dict[str, Any] = {
        "schema_version": "es_attempt_record.v1",
        "attempt_id": attempt_id,
        "decision_lock_sha256": decision_lock.decision_lock_digest(lock),
        "randomization_manifest_sha256": decision_lock.decision_lock_digest(schedule),
        "randomization_row_sha256": decision_lock.decision_lock_digest(schedule_row),
        "trial_request_digest": _sha("9"),
        "resume_policy": "FORBIDDEN",
        "interrupted": False,
        "classifier_inputs": {
            "source_task_binding_valid": True,
            "controller_launch_preallocation_failed": False,
            "common_provider_outage_proven": False,
            "evaluation_bytes_valid": invalidity_code
            != "COMMON_EVALUATION_BYTES_INVALID",
            "blinding_join_valid": invalidity_code != "BLINDING_JOIN_INVALID",
        },
        "e2_authority": {
            "ledger_input_status": "VALIDATED",
            "ledger_valid": True,
            "coherent_allocation": True,
            "header_row_digest": _sha("b"),
            "ledger_head_digest": _sha("c"),
            "trial_request_digest": _sha("9"),
            "treatment_started": True,
            "arm_settlements": [
                {
                    "cell": {"arm_id": arm, "rep": 1},
                    "status": arm_status[arm],
                    "terminal_row_digest": _sha(str(index)),
                }
                for index, arm in enumerate(ARMS, start=1)
            ],
            "scorer_settlements": [
                {
                    "opaque_label": labels_by_arm[arm],
                    "settlement_row_digest": score_settlement_rows[
                        labels_by_arm[arm]
                    ]["row_digest"],
                }
                for arm in ARMS
            ],
        },
        "accounting": {
            "arm_routes": [
                {"arm": arm, "route_id": terminal_route_ids[arm]} for arm in ARMS
            ],
            "evaluation_route_id": evaluation_route["route_id"],
            "material_disagreement": adjudicator_failure or adjudicator_with_agreement,
            "review_settlements": review_settlements,
            "receipt_bindings": [
                {
                    "call_slot_id": slot,
                    "receipt_sha256": _study_digest(receipts[slot]),
                }
                for slot in slots
            ],
            "call_count": len(slots),
            "terminal_authority_complete": True,
        },
        "status": status,
        "invalidity_code": invalidity_code,
    }
    hard_replay_inputs = {
        arm: _hard_replay_inputs(
            labels_by_arm[arm],
            unresolved=rich_unresolved and arm == "RICH",
            oracle_defect=oracle_defect_arm == arm,
        )
        for arm in ARMS
    }
    if oracle_defect_arm is not None:
        shared_proof_authority = deepcopy(
            hard_replay_inputs[oracle_defect_arm]["frozen_proof_authority"]
        )
        for replay in hard_replay_inputs.values():
            replay["frozen_proof_authority"] = deepcopy(shared_proof_authority)
    freezes = {
        arm: (
            None
            if missing_freeze_arm == arm
            else _freeze_from_replay(hard_replay_inputs[arm])
        )
        for arm in ARMS
    }
    hard_specs = {
        arm: (
            {
                "trusted_product_freeze_status": "MISSING",
                "absence_authority": {
                    "schema_version": "es.trusted_product_freeze_absence.v1",
                    "reason": "TERMINAL_TREATMENT_FAILURE",
                    "cell": {"arm_id": arm, "rep": 1},
                    "terminal_row_digest": next(
                        row["terminal_row_digest"]
                        for row in attempt_record["e2_authority"]["arm_settlements"]
                        if row["cell"]["arm_id"] == arm
                    ),
                },
            }
            if missing_freeze_arm == arm
            else {
                "trusted_product_freeze_status": "PRESENT",
                "replay_inputs": hard_replay_inputs[arm],
            }
        )
        for arm in ARMS
    }
    integrated_record = review_records["EVAL.INTEGRATED_REVIEW"]
    rich_direct_row = next(
        row
        for row in integrated_payload["pairwise_results"]
        if {
            row["candidate_a_label"],
            row["candidate_b_label"],
        }
        == {labels_by_arm["RICH"], labels_by_arm["DIRECT"]}
    )
    hard_evidence_digest = _study_digest(
        [synthesis._hard_row_from_spec(arm, hard_specs[arm]) for arm in ARMS]
    )
    oriented = blinding.orient_integrated_primary_pair(
        private_join,
        integrated_pair=blinding.FrozenIntegratedPairOutcome(
            integrated_review_record_digest=_study_digest(integrated_record),
            packet_set_digest=packet_set_digest,
            source_pair_row_digest=_study_digest(rich_direct_row),
            candidate_a_label=rich_direct_row["candidate_a_label"],
            candidate_b_label=rich_direct_row["candidate_b_label"],
            outcome=rich_direct_row["outcome"],
        ),
        hard_evidence=blinding.FrozenHardEvidence(
            record_digest=hard_evidence_digest,
            packet_set_digest=packet_set_digest,
        ),
    )
    primary = hard_contract.derive_primary_outcome(
        raw_outcome=oriented.rich_vs_direct,
        rich_freeze=freezes["RICH"],
        direct_freeze=freezes["DIRECT"],
    )
    return synthesis.build_attempt_evidence_index(
        attempt_record=attempt_record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
        private_join=private_join,
        public_packet_replay_inputs=public_packet_replay_inputs,
        private_blinding_replay_inputs=private_replay_inputs,
        packets_by_arm=packets,
        review_records_by_slot=review_records,
        adjudication_payload=adjudication_payload,
        integrated_payload=integrated_payload,
        hard_evidence_by_arm=hard_specs,
        oriented_primary=oriented,
        hard_primary_outcome=primary,
        receipts_by_slot=receipts,
        raw_jsonl_by_slot=raw_jsonl,
        frozen_call_authority=_call_authority(),
        call_allocations=_call_allocations(
            synthesis,
            lock,
            attempt_id=attempt_id,
            rows=[
                (slot, "RECEIPT_FROZEN", _study_digest(receipts[slot]))
                for slot in slots
            ],
        ),
        elapsed_ms_by_slot={slot: index * 10 for index, slot in enumerate(slots, 1)},
        scorer_settlement_rows_by_label=score_settlement_rows,
        score_rows_by_label=score_rows,
    )


def _rehash_index(index: dict[str, Any]) -> None:
    body = {key: value for key, value in index.items() if key != "index_sha256"}
    index["index_sha256"] = _study_digest(body)


def _rehash_hard_row(index: dict[str, Any], arm_index: int) -> None:
    row = index["hard_evaluations"][arm_index]
    row["evaluation_sha256"] = _study_digest(row["evaluation"])
    row["freeze"]["evaluation_digest"] = row["evaluation_sha256"]
    freeze_body = {
        key: value for key, value in row["freeze"].items() if key != "freeze_digest"
    }
    row["freeze"]["freeze_digest"] = _study_digest(freeze_body)
    row["freeze_sha256"] = row["freeze"]["freeze_digest"]
    _rehash_index(index)


def _rehash_receipt_row(index: dict[str, Any], receipt_index: int) -> None:
    row = index["receipts"][receipt_index]
    row["record_sha256"] = _study_digest(row["record"])
    binding = next(
        value
        for value in index["attempt_record"]["accounting"]["receipt_bindings"]
        if value["call_slot_id"] == row["call_slot_id"]
    )
    binding["receipt_sha256"] = row["record_sha256"]
    allocation = next(
        value
        for value in index["call_allocations"]
        if value["call_slot_id"] == row["call_slot_id"]
    )
    allocation["receipt_sha256"] = row["record_sha256"]
    index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    _rehash_index(index)


def _rehash_scorer_projection(index: dict[str, Any], scorer_index: int) -> None:
    projection = index["scorer_settlements"][scorer_index]
    score = projection["score_row"]
    score_body = {
        key: value for key, value in score.items() if key != "row_content_digest"
    }
    score["row_content_digest"] = canonical_sha256(score_body)
    settlement = projection["settlement_row"]
    settlement["payload"]["score_row_content_digest"] = score[
        "row_content_digest"
    ]
    settlement_body = {
        key: value for key, value in settlement.items() if key != "row_digest"
    }
    settlement["row_digest"] = canonical_sha256(settlement_body)
    e2_row = next(
        row
        for row in index["attempt_record"]["e2_authority"]["scorer_settlements"]
        if row["opaque_label"] == projection["opaque_label"]
    )
    e2_row["settlement_row_digest"] = settlement["row_digest"]
    index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    _rehash_index(index)


def _rehash_all_scorer_identity(
    index: dict[str, Any],
    *,
    field: str,
    value: str,
) -> None:
    identity_fields = (
        "trial_request_digest",
        "evaluation_digest",
        "evidence_frozen_digest",
        "evaluation_label",
        "evaluation_packet_digest",
        "scorer_identity_digest",
    )
    for scorer_index, projection in enumerate(index["scorer_settlements"]):
        score = projection["score_row"]
        score[field] = value
        score["score_run_key"] = canonical_sha256(
            {
                "schema_version": "trial_score_identity.v1",
                **{name: score[name] for name in identity_fields},
            }
        )
        _rehash_scorer_projection(index, scorer_index)


def _rehash_all_hard_identity(
    index: dict[str, Any],
    synthesis,
    *,
    field: str,
    value: str,
) -> None:
    rows: list[dict[str, Any]] = []
    freezes: dict[str, hard_contract.HardEvaluationFreeze] = {}
    for arm, existing in zip(ARMS, index["hard_evaluations"], strict=True):
        replay = deepcopy(existing["replay_inputs"])
        replay[field] = value
        for proof in replay["proof_rows"]:
            proof[field] = value
        for authority in replay["frozen_proof_authority"]:
            authority[field] = value
        row = synthesis._hard_row_from_spec(
            arm,
            {
                "trusted_product_freeze_status": "PRESENT",
                "replay_inputs": replay,
            },
        )
        rows.append(row)
        freezes[arm] = _freeze_from_replay(replay)
    index["hard_evaluations"] = rows
    index["oriented_primary"]["hard_evidence_record_digest"] = _study_digest(rows)
    index["oriented_primary_sha256"] = _study_digest(index["oriented_primary"])
    primary = hard_contract.derive_primary_outcome(
        raw_outcome=index["oriented_primary"]["rich_vs_direct"],
        rich_freeze=freezes["RICH"],
        direct_freeze=freezes["DIRECT"],
    ).record
    index["hard_primary_outcome"] = primary
    index["hard_primary_outcome_sha256"] = _study_digest(primary)
    _rehash_index(index)


@pytest.fixture()
def synthesis():
    from scripts.experiments.es import synthesis as module

    return module


def _report(
    synthesis,
    outcomes: tuple[str, ...],
    **attempt_options: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=index,
            outcome=outcome,
            **attempt_options,
        )
        for index, outcome in enumerate(outcomes, start=1)
    ]
    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )
    return report, indexes


def _sparse_invalid_index(
    synthesis,
    lock: Mapping[str, Any],
    schedule: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    ordinal: int,
    invalidity_code: str = "APPARATUS_ACCOUNTING_INCOMPLETE",
    retain_first_incurred_call: bool = False,
) -> dict[str, Any]:
    complete = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=ordinal,
        outcome="RICH",
    )
    record = deepcopy(complete["attempt_record"])
    record["e2_authority"]["arm_settlements"] = []
    record["e2_authority"]["scorer_settlements"] = []
    retained_receipts = complete["receipts"][:1] if retain_first_incurred_call else []
    record["accounting"] = {
        "arm_routes": (
            [{"arm": "DIRECT", "route_id": "DIRECT.I"}]
            if retain_first_incurred_call
            else []
        ),
        "evaluation_route_id": None,
        "material_disagreement": False,
        "review_settlements": [],
        "receipt_bindings": [
            {
                "call_slot_id": row["call_slot_id"],
                "receipt_sha256": row["record_sha256"],
            }
            for row in retained_receipts
        ],
        "call_count": len(retained_receipts),
        "terminal_authority_complete": False,
    }
    if invalidity_code == "COMMON_EVALUATION_BYTES_INVALID":
        record["classifier_inputs"]["evaluation_bytes_valid"] = False
    record["status"] = "INVALID"
    record["invalidity_code"] = invalidity_code
    return synthesis.build_invalid_attempt_evidence_index(
        attempt_record=record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
        receipts_by_slot={row["call_slot_id"]: row["record"] for row in retained_receipts},
        raw_jsonl_by_slot={
            row["call_slot_id"]: row["raw_jsonl"].encode("utf-8")
            for row in retained_receipts
        },
        frozen_call_authority=_call_authority(),
        call_allocations=_call_allocations(
            synthesis,
            lock,
            attempt_id=record["attempt_id"],
            rows=[
                (
                    row["call_slot_id"],
                    "RECEIPT_FROZEN",
                    row["record_sha256"],
                )
                for row in retained_receipts
            ],
        ),
        elapsed_ms_by_slot={
            row["call_slot_id"]: next(
                elapsed["elapsed_ms"]
                for elapsed in complete["elapsed_ms"]
                if elapsed["call_slot_id"] == row["call_slot_id"]
            )
            for row in retained_receipts
        },
    )


def _partial_invalid_index(
    synthesis,
    lock: Mapping[str, Any],
    schedule: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    ordinal: int,
    phase: str,
    failed_first_review: bool = False,
) -> dict[str, Any]:
    complete = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=ordinal,
        outcome="RICH",
        failed_review_slot=(
            "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS"
            if failed_first_review
            else None
        ),
    )
    record = deepcopy(complete["attempt_record"])
    treatment_receipts = [
        row for row in complete["receipts"] if not row["call_slot_id"].startswith("EVAL.")
    ]
    scorer_receipts = [
        row
        for row in complete["receipts"]
        if row["call_slot_id"].startswith("EVAL.SCORER_")
    ]
    review_receipts = [
        row
        for row in complete["receipts"]
        if row["call_slot_id"].startswith("EVAL.INITIAL_")
    ]
    if phase == "SCORER":
        record["e2_authority"]["scorer_settlements"] = record["e2_authority"][
            "scorer_settlements"
        ][:2]
        record["accounting"]["review_settlements"] = []
        retained = treatment_receipts + scorer_receipts[:2]
        in_flight_slot = scorer_receipts[2]["call_slot_id"]
        partial_scorers = complete["scorer_settlements"][:2]
        partial_reviews: list[dict[str, Any]] = []
    elif phase == "REVIEW":
        record["accounting"]["review_settlements"] = record["accounting"][
            "review_settlements"
        ][:1]
        retained = treatment_receipts + scorer_receipts + review_receipts[:1]
        in_flight_slot = review_receipts[1]["call_slot_id"]
        partial_scorers = complete["scorer_settlements"]
        partial_reviews = complete["reviews"][:1]
    else:
        raise AssertionError(phase)
    record["accounting"]["material_disagreement"] = False
    record["accounting"]["receipt_bindings"] = [
        {
            "call_slot_id": row["call_slot_id"],
            "receipt_sha256": row["record_sha256"],
        }
        for row in retained
    ]
    record["accounting"]["call_count"] = len(retained)
    record["accounting"]["terminal_authority_complete"] = False
    record["status"] = "INVALID"
    record["invalidity_code"] = "APPARATUS_ACCOUNTING_INCOMPLETE"
    partial_evidence = {
        "public_packet_replay_inputs": complete[
            "public_packet_replay_inputs"
        ],
        "private_blinding_replay_inputs": complete[
            "private_blinding_replay_inputs"
        ],
        "private_blinding_join": complete["private_blinding_join"],
        "private_blinding_join_sha256": complete["private_blinding_join_sha256"],
        "packets": complete["packets"],
        "scorer_settlements": partial_scorers,
        "reviews": partial_reviews,
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
    allocations = _call_allocations(
        synthesis,
        lock,
        attempt_id=record["attempt_id"],
        rows=[
            (
                row["call_slot_id"],
                "RECEIPT_FROZEN",
                row["record_sha256"],
            )
            for row in retained
        ]
        + [(in_flight_slot, "INTERRUPTED_IN_FLIGHT", None)],
    )
    return synthesis.build_invalid_attempt_evidence_index(
        attempt_record=record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
        receipts_by_slot={row["call_slot_id"]: row["record"] for row in retained},
        raw_jsonl_by_slot={
            row["call_slot_id"]: row["raw_jsonl"].encode("utf-8") for row in retained
        },
        elapsed_ms_by_slot={
            row["call_slot_id"]: next(
                elapsed["elapsed_ms"]
                for elapsed in complete["elapsed_ms"]
                if elapsed["call_slot_id"] == row["call_slot_id"]
            )
            for row in retained
        },
        frozen_call_authority=_call_authority(),
        call_allocations=allocations,
        partial_evidence=partial_evidence,
    )


def _partial_stage_index(
    synthesis,
    lock: Mapping[str, Any],
    schedule: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    ordinal: int,
    scorer_count: int,
    review_count: int,
    hard_count: int,
    retain_primary: bool = False,
    disagreement: bool = False,
    evaluation_route_override: str | None = None,
) -> dict[str, Any]:
    complete = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=ordinal,
        outcome="RICH",
        adjudicator_failure=disagreement,
    )
    record = deepcopy(complete["attempt_record"])
    record["e2_authority"]["scorer_settlements"] = record["e2_authority"][
        "scorer_settlements"
    ][:scorer_count]
    record["accounting"]["review_settlements"] = record["accounting"][
        "review_settlements"
    ][:review_count]
    record["accounting"]["material_disagreement"] = (
        disagreement and review_count >= 2
    )
    if evaluation_route_override is not None:
        record["accounting"]["evaluation_route_id"] = evaluation_route_override
    selected_review_rows = complete["reviews"][:review_count]
    selected_review_slots = {
        row["call_slot_id"] for row in selected_review_rows
    }
    scorer_receipts = [
        row
        for row in complete["receipts"]
        if row["call_slot_id"].startswith("EVAL.SCORER_")
    ][:scorer_count]
    scorer_slots = {row["call_slot_id"] for row in scorer_receipts}
    retained = [
        row
        for row in complete["receipts"]
        if not row["call_slot_id"].startswith("EVAL.")
        or row["call_slot_id"] in scorer_slots
        or row["call_slot_id"] in selected_review_slots
    ]
    record["accounting"]["receipt_bindings"] = [
        {
            "call_slot_id": row["call_slot_id"],
            "receipt_sha256": row["record_sha256"],
        }
        for row in retained
    ]
    record["accounting"]["call_count"] = len(retained)
    integrated_selected = any(
        row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
        for row in selected_review_rows
    )
    if integrated_selected:
        record["interrupted"] = True
        record["accounting"]["terminal_authority_complete"] = True
        record["status"] = "VALID"
        record["invalidity_code"] = None
    else:
        record["accounting"]["terminal_authority_complete"] = False
        record["status"] = "INVALID"
        record["invalidity_code"] = "APPARATUS_ACCOUNTING_INCOMPLETE"
    adjudicator_selected = any(
        row["call_slot_id"] == "EVAL.ADJUDICATOR"
        for row in selected_review_rows
    )
    partial_evidence = {
        "public_packet_replay_inputs": complete[
            "public_packet_replay_inputs"
        ],
        "private_blinding_replay_inputs": complete[
            "private_blinding_replay_inputs"
        ],
        "private_blinding_join": complete["private_blinding_join"],
        "private_blinding_join_sha256": complete["private_blinding_join_sha256"],
        "packets": complete["packets"],
        "scorer_settlements": complete["scorer_settlements"][:scorer_count],
        "reviews": selected_review_rows,
        "integrated_prior_record_sha256s": (
            complete["integrated_prior_record_sha256s"]
            if integrated_selected
            else []
        ),
        "adjudication_payload": (
            complete["adjudication_payload"] if adjudicator_selected else None
        ),
        "adjudication_payload_sha256": (
            complete["adjudication_payload_sha256"]
            if adjudicator_selected
            else None
        ),
        "integrated_payload": (
            complete["integrated_payload"] if integrated_selected else None
        ),
        "integrated_payload_sha256": (
            complete["integrated_payload_sha256"]
            if integrated_selected
            else None
        ),
        "hard_evaluations": complete["hard_evaluations"][:hard_count],
        "oriented_primary": complete["oriented_primary"] if retain_primary else None,
        "oriented_primary_sha256": (
            complete["oriented_primary_sha256"] if retain_primary else None
        ),
        "hard_primary_outcome": (
            complete["hard_primary_outcome"] if retain_primary else None
        ),
        "hard_primary_outcome_sha256": (
            complete["hard_primary_outcome_sha256"] if retain_primary else None
        ),
    }
    return synthesis.build_invalid_attempt_evidence_index(
        attempt_record=record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
        receipts_by_slot={row["call_slot_id"]: row["record"] for row in retained},
        raw_jsonl_by_slot={
            row["call_slot_id"]: row["raw_jsonl"].encode("utf-8")
            for row in retained
        },
        elapsed_ms_by_slot={
            row["call_slot_id"]: next(
                elapsed["elapsed_ms"]
                for elapsed in complete["elapsed_ms"]
                if elapsed["call_slot_id"] == row["call_slot_id"]
            )
            for row in retained
        },
        frozen_call_authority=_call_authority(),
        call_allocations=_call_allocations(
            synthesis,
            lock,
            attempt_id=record["attempt_id"],
            rows=[
                (
                    row["call_slot_id"],
                    "RECEIPT_FROZEN",
                    row["record_sha256"],
                )
                for row in retained
            ],
        ),
        partial_evidence=partial_evidence,
    )


def _blinding_invalid_retained_index(
    synthesis,
    lock: Mapping[str, Any],
    schedule: Mapping[str, Any],
    bindings: Mapping[str, str],
    *,
    ordinal: int,
    scorer_count: int = 2,
    retain_malformed_join: bool = True,
    rich_failed: bool = False,
    failed_scorer_arm: str | None = None,
) -> dict[str, Any]:
    complete = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=ordinal,
        outcome="RICH",
        rich_failed=rich_failed,
        failed_scorer_arm=failed_scorer_arm,
    )
    public_replay = complete["public_packet_replay_inputs"]
    private_replay = complete["private_blinding_replay_inputs"]
    attempted_join = (
        deepcopy(complete["private_blinding_join"])
        if retain_malformed_join
        else None
    )
    if attempted_join is not None:
        attempted_join["rows"][0]["cell"]["rep"] = 2
    record = deepcopy(complete["attempt_record"])
    record["classifier_inputs"]["blinding_join_valid"] = False
    record["e2_authority"]["scorer_settlements"] = record["e2_authority"][
        "scorer_settlements"
    ][:scorer_count]
    record["accounting"]["material_disagreement"] = False
    record["accounting"]["review_settlements"] = []
    scorer_receipts = [
        row
        for row in complete["receipts"]
        if row["call_slot_id"].startswith("EVAL.SCORER_")
    ][:scorer_count]
    retained = [
        row
        for row in complete["receipts"]
        if not row["call_slot_id"].startswith("EVAL.")
    ] + scorer_receipts
    record["accounting"]["receipt_bindings"] = [
        {
            "call_slot_id": row["call_slot_id"],
            "receipt_sha256": row["record_sha256"],
        }
        for row in retained
    ]
    record["accounting"]["call_count"] = len(retained)
    record["accounting"]["terminal_authority_complete"] = False
    record["status"] = "INVALID"
    record["invalidity_code"] = "BLINDING_JOIN_INVALID"
    partial_evidence = {
        "public_packet_replay_inputs": public_replay,
        "private_blinding_replay_inputs": (
            private_replay if retain_malformed_join else None
        ),
        "private_blinding_join": attempted_join,
        "private_blinding_join_sha256": (
            canonical_sha256(attempted_join) if attempted_join is not None else None
        ),
        "packets": complete["packets"],
        "scorer_settlements": complete["scorer_settlements"][:scorer_count],
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
    return synthesis.build_invalid_attempt_evidence_index(
        attempt_record=record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
        receipts_by_slot={row["call_slot_id"]: row["record"] for row in retained},
        raw_jsonl_by_slot={
            row["call_slot_id"]: row["raw_jsonl"].encode("utf-8")
            for row in retained
        },
        elapsed_ms_by_slot={
            row["call_slot_id"]: next(
                elapsed["elapsed_ms"]
                for elapsed in complete["elapsed_ms"]
                if elapsed["call_slot_id"] == row["call_slot_id"]
            )
            for row in retained
        },
        frozen_call_authority=_call_authority(),
        call_allocations=_call_allocations(
            synthesis,
            lock,
            attempt_id=record["attempt_id"],
            rows=[
                (
                    row["call_slot_id"],
                    "RECEIPT_FROZEN",
                    row["record_sha256"],
                )
                for row in retained
            ],
        ),
        partial_evidence=partial_evidence,
    )


def test_report_schema_is_draft_2020_12_and_every_object_is_closed() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    _closed_schemas(schema)


def test_two_rich_wins_emit_complete_typed_report_and_regenerate_byte_identically(
    synthesis,
) -> None:
    report, indexes = _report(synthesis, ("RICH", "RICH"))
    lock, schedule, bindings = _lock_and_schedule()

    assert report["screen_result"] == "SCREEN_PASSED"
    assert report["e3_readiness_input"] == "BLACK_BOX_SUFFICIENT"
    assert [row["derived_outcome"] for row in report["primary_sequence"]] == [
        "RICH",
        "RICH",
    ]
    assert all(len(row["arms"]) == 4 for row in report["four_arm_vectors"])
    assert all("expected_call" not in row for index in indexes for row in index["receipts"])
    environment = indexes[0]["call_authority"]["environment_lock"]
    assert environment["model"] == "gpt-5.5"
    assert environment["reasoning_effort"] == "high"
    assert environment["prompt_transport"] == "STDIN"
    coefficients = {
        row["contrast_id"]: [member["coefficient"] for member in row["coefficients"]]
        for row in report["factorial_mechanism_contrasts"]
    }
    assert coefficients == {
        "TOTAL_RICH_VS_DIRECT": [
            {"numerator": -1, "denominator": 1},
            {"numerator": 0, "denominator": 1},
            {"numerator": 0, "denominator": 1},
            {"numerator": 1, "denominator": 1},
        ],
        "DESIGN_QA_COMPONENT": [
            {"numerator": -1, "denominator": 2},
            {"numerator": 1, "denominator": 2},
            {"numerator": -1, "denominator": 2},
            {"numerator": 1, "denominator": 2},
        ],
        "PRODUCT_QA_COMPONENT": [
            {"numerator": -1, "denominator": 2},
            {"numerator": -1, "denominator": 2},
            {"numerator": 1, "denominator": 2},
            {"numerator": 1, "denominator": 2},
        ],
        "INTERACTION_COMPONENT": [
            {"numerator": 1, "denominator": 1},
            {"numerator": -1, "denominator": 1},
            {"numerator": -1, "denominator": 1},
            {"numerator": 1, "denominator": 1},
        ],
        "DESIGN_QA_VS_PRODUCT_QA_DESCRIPTIVE": [
            {"numerator": 0, "denominator": 1},
            {"numerator": 1, "denominator": 1},
            {"numerator": -1, "denominator": 1},
            {"numerator": 0, "denominator": 1},
        ],
    }
    assert all(
        row["scalar_effect"] is None
        and sum(row["aggregate_relation_counts"].values())
        == sum(len(block["relations"]) for block in row["per_attempt"])
        for row in report["factorial_mechanism_contrasts"]
    )
    descriptive = next(
        row
        for row in report["factorial_mechanism_contrasts"]
        if row["contrast_id"] == "DESIGN_QA_VS_PRODUCT_QA_DESCRIPTIVE"
    )
    assert all(
        [(relation["first_arm"], relation["second_arm"])
         for relation in block["relations"]]
        == [("DESIGN_QA", "PRODUCT_QA")]
        for block in descriptive["per_attempt"]
    )
    assert len(report["distributions"]["tokens"]["arm_treatment_totals"]) == 8
    assert {
        (row["attempt_id"], row["arm_id"])
        for row in report["distributions"]["tokens"]["arm_treatment_totals"]
    } == {
        (f"ES-ATTEMPT-{attempt:02d}", arm)
        for attempt in (1, 2)
        for arm in ARMS
    }
    assert all(
        len(row["elapsed_row_sha256s"]) == len(row["receipt_sha256s"])
        for row in report["indexed_attempts"]
    )
    assert report["decision"]["required_non_tied_comparisons"] == 2
    assert report["decision"]["maximum_valid_blocks"] == 3
    assert report["decision"]["all_cost_cells_known"] is True
    assert report["decision"]["median_rich_direct_token_ratio_at_most_cap"] is True
    assert report["viability"]["passes"] is True
    assert report["claim_limits"] == lock["claim_limits"]
    assert Draft202012Validator(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    ).is_valid(report)

    regenerated = synthesis.synthesize_report(
        indexed_attempts=deepcopy(indexes),
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )
    assert synthesis.canonical_report_bytes(regenerated) == (
        synthesis.canonical_report_bytes(report)
    )


def test_call_accounting_discloses_every_receipt_component_without_double_counting_cache(
    synthesis,
) -> None:
    report, indexes = _report(
        synthesis,
        ("RICH", "RICH"),
        cached_tokens=7,
        cache_write_tokens=3,
    )

    rows = report["call_accounting"]
    assert len(rows) == sum(len(index["receipts"]) for index in indexes)
    assert all(
        row["timing_source"] == "MONOTONIC_INVOCATION_SETTLEMENT_MS"
        and row["cached_input_tokens"] == 7
        and row["cache_write_input_tokens"] == 3
        and row["receipt_sha256"].startswith("sha256:")
        and row["elapsed_row_sha256"].startswith("sha256:")
        for row in rows
    )
    reported = sum(row["reported_total_tokens"] for row in rows)
    assert report["distributions"]["tokens"]["total"] == reported
    assert reported != sum(
        row["reported_total_tokens"] + row["cached_input_tokens"] for row in rows
    )


def test_sparse_invalid_discloses_every_incurred_call(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _sparse_invalid_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            retain_first_incurred_call=True,
        ),
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=2,
            outcome="RICH",
        ),
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=3,
            outcome="RICH",
        ),
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    invalid_rows = [
        row
        for row in report["call_accounting"]
        if row["attempt_id"] == "ES-ATTEMPT-01"
    ]
    assert len(invalid_rows) == 1
    assert invalid_rows[0]["category"] == "TREATMENT"


def test_tie_and_indeterminate_do_not_accrue_and_m_exhaustion_is_insufficient(
    synthesis,
) -> None:
    report, _ = _report(synthesis, ("TIE", "INDETERMINATE", "RICH"))

    assert report["decision"]["non_tied_count"] == 1
    assert report["screen_result"] == "INSUFFICIENT_EVIDENCE"
    assert report["e3_readiness_input"] == "STOP_E3_HYPOTHESIS"


def test_direct_primary_is_not_repaired_from_cost_or_other_pairwise_values(
    synthesis,
) -> None:
    report, _ = _report(synthesis, ("DIRECT", "RICH"), rich_tokens=1)

    assert report["primary_sequence"][0]["derived_outcome"] == "DIRECT"
    assert report["screen_result"] == "SCREEN_NOT_PASSED"


def test_zero_direct_reference_cost_is_undefined_and_cannot_pass(synthesis) -> None:
    report, _ = _report(
        synthesis,
        ("RICH", "RICH"),
        rich_tokens=1,
        direct_tokens=0,
    )

    assert report["distributions"]["tokens"]["median_rich_direct_ratio"] is None
    assert all(
        row["ratio_status"] == "UNDEFINED_ZERO_REFERENCE"
        for row in report["distributions"]["tokens"]["rich_direct_ratios"]
    )
    assert report["decision"]["median_rich_direct_token_ratio_at_most_cap"] is False
    assert report["screen_result"] == "SCREEN_NOT_PASSED"


@pytest.mark.parametrize(
    ("outcomes", "options", "decision_field", "expected_screen"),
    [
        (("RICH", "RICH"), {"rich_failed": True}, "viability_passes", "SCREEN_NOT_PASSED"),
        (("RICH", "RICH"), {"rich_tokens": 500, "direct_tokens": 100}, "median_rich_direct_token_ratio_at_most_cap", "SCREEN_NOT_PASSED"),
        (("RICH", "RICH", "RICH"), {"rich_unresolved": True}, "no_unresolved_rich_blocker", "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_each_non_primary_screen_gate_fails_closed(
    synthesis,
    outcomes: tuple[str, ...],
    options: dict[str, Any],
    decision_field: str,
    expected_screen: str,
) -> None:
    report, _ = _report(synthesis, outcomes, **options)

    assert report["decision"][decision_field] is False
    assert report["screen_result"] == expected_screen


def test_one_permitted_invalid_is_disclosed_but_replaced_outside_m_n_accrual(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _sparse_invalid_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            invalidity_code="COMMON_EVALUATION_BYTES_INVALID",
        ),
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=2,
            outcome="RICH",
        ),
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=3,
            outcome="RICH",
        ),
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert report["screen_result"] == "SCREEN_PASSED"
    assert report["decision"]["valid_block_count"] == 2
    assert report["decision"]["invalid_attempt_count"] == 1
    assert report["failure_classes"] == [
        {
            "attempt_id": "ES-ATTEMPT-01",
            "arm_id": None,
            "failure_class": "APPARATUS_INVALID",
            "failure_code": "COMMON_EVALUATION_BYTES_INVALID",
        }
    ]


def test_sparse_invalid_is_not_forced_to_fabricate_downstream_evidence(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _sparse_invalid_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
        ),
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=2,
            outcome="RICH",
        ),
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=3,
            outcome="RICH",
        ),
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert report["screen_result"] == "SCREEN_PASSED"
    assert report["indexed_attempts"][0]["packet_set_digest"] is None
    assert report["indexed_attempts"][0]["review_sha256s"] == []


@pytest.mark.parametrize("phase", ["SCORER", "REVIEW"])
def test_partial_invalid_retains_exact_incurred_prefix_and_in_flight_allocation(
    synthesis,
    phase: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        phase=phase,
    )

    assert index["evidence_variant"] == "PARTIAL"
    assert index["private_blinding_join"] is not None
    assert len(index["scorer_settlements"]) == (2 if phase == "SCORER" else 4)
    assert len(index["reviews"]) == (0 if phase == "SCORER" else 1)
    assert index["call_allocations"][-1]["settlement"] == "INTERRUPTED_IN_FLIGHT"
    assert index["call_allocations"][-1]["receipt_sha256"] is None
    assert len(index["call_allocations"]) == len(index["receipts"]) + 1


@pytest.mark.parametrize("phase", ["SCORER", "REVIEW"])
def test_partial_invalid_rejects_tampered_incurred_evidence(
    synthesis,
    phase: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        phase=phase,
    )
    if phase == "SCORER":
        index["scorer_settlements"][0]["score_row"][
            "evaluation_packet_digest"
        ] = _sha("f")
        _rehash_scorer_projection(index, 0)
    else:
        row = index["reviews"][0]
        row["record"]["perspective_id"] = API
        row["record_sha256"] = _study_digest(row["record"])
        settlement = index["attempt_record"]["accounting"]["review_settlements"][0]
        settlement["record_sha256"] = row["record_sha256"]
        index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
        _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_partial_invalid_report_counts_allocation_without_imputing_usage_and_failures(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _partial_invalid_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            phase="REVIEW",
            failed_first_review=True,
        ),
        _attempt_index(
            synthesis, lock, schedule, bindings, ordinal=2, outcome="RICH"
        ),
        _attempt_index(
            synthesis, lock, schedule, bindings, ordinal=3, outcome="RICH"
        ),
    ]
    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    first_allocations = [
        row for row in report["call_allocations"] if row["attempt_id"] == "ES-ATTEMPT-01"
    ]
    first_receipts = [
        row for row in report["call_accounting"] if row["attempt_id"] == "ES-ATTEMPT-01"
    ]
    assert len(first_allocations) == len(first_receipts) + 1
    assert first_allocations[-1]["settlement"] == "INTERRUPTED_IN_FLIGHT"
    assert first_allocations[-1]["receipt_sha256"] is None
    assert report["distributions"]["calls"]["per_attempt"][0]["value"] == len(
        first_allocations
    )
    assert any(
        row["failure_class"] == "EVALUATION_FAILURE"
        and row["failure_code"] == "TYPED_OUTPUT_INVALID"
        for row in report["failure_classes"]
    )


def test_partial_review_requires_all_four_scorer_settlements(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    with pytest.raises(synthesis.SynthesisError, match="scorer|partial"):
        _partial_stage_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            scorer_count=3,
            review_count=1,
            hard_count=0,
        )


def test_partial_hard_prefix_follows_resolved_initial_reviews_before_integrated(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    index = _partial_stage_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        scorer_count=4,
        review_count=2,
        hard_count=2,
    )

    assert len(index["hard_evaluations"]) == 2
    assert index["integrated_payload"] is None
    assert index["hard_primary_outcome"] is None


def test_partial_integrated_review_requires_all_four_hard_rows(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    with pytest.raises(
        synthesis.SynthesisError, match="hard|integrated|partial|provider_authority"
    ):
        _partial_stage_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            scorer_count=4,
            review_count=3,
            hard_count=3,
        )


def test_partial_integrated_review_after_four_hard_rows_may_await_primary(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    index = _partial_stage_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        scorer_count=4,
        review_count=3,
        hard_count=4,
    )

    assert index["integrated_payload"] is not None
    assert len(index["hard_evaluations"]) == 4
    assert index["oriented_primary"] is None
    assert index["hard_primary_outcome"] is None


def test_partial_disagreeing_initials_may_pause_pending_adjudicator(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    index = _partial_stage_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        scorer_count=4,
        review_count=2,
        hard_count=0,
        disagreement=True,
    )

    assert index["attempt_record"]["accounting"]["material_disagreement"] is True
    assert [row["call_slot_id"] for row in index["reviews"]] == [
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    ]
    assert index["adjudication_payload"] is None


def test_partial_disagreement_cannot_advance_to_hard_before_adjudicator(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    with pytest.raises(synthesis.SynthesisError, match="adjudication|hard|partial"):
        _partial_stage_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            scorer_count=4,
            review_count=2,
            hard_count=1,
            disagreement=True,
        )


def test_partial_primary_cannot_precede_integrated_review(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    with pytest.raises(synthesis.SynthesisError, match="integrated|primary|partial"):
        _partial_stage_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            scorer_count=4,
            review_count=2,
            hard_count=4,
            retain_primary=True,
        )


def test_blinding_invalid_retains_public_packets_and_scorer_prefix(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    index = _blinding_invalid_retained_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
    )

    assert index["attempt_record"]["invalidity_code"] == "BLINDING_JOIN_INVALID"
    assert index["public_packet_replay_inputs"] is not None
    assert len(index["packets"]) == 4
    assert len(index["scorer_settlements"]) == 2
    assert index["private_blinding_join"]["rows"][0]["cell"]["rep"] == 2
    assert index["reviews"] == []
    assert index["hard_evaluations"] == []


def test_blinding_invalid_rejects_tampered_retained_public_packet(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _blinding_invalid_retained_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
    )
    index["packets"][0]["packet"]["evaluation_id"] = f"opaque-{999:064x}"
    index["packets"][0]["packet_sha256"] = canonical_sha256(
        index["packets"][0]["packet"]
    )
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="packet"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_blinding_invalid_report_uses_e2_cells_for_treatment_failures_without_join(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _blinding_invalid_retained_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            retain_malformed_join=False,
            rich_failed=True,
        ),
        _attempt_index(
            synthesis, lock, schedule, bindings, ordinal=2, outcome="RICH"
        ),
        _attempt_index(
            synthesis, lock, schedule, bindings, ordinal=3, outcome="RICH"
        ),
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert {
        "attempt_id": "ES-ATTEMPT-01",
        "arm_id": "RICH",
        "failure_class": "TREATMENT_METHOD_FAILURE",
        "failure_code": "RICH.D_DR_I",
    } in report["failure_classes"]


def test_evaluation_authority_is_frozen_across_attempts(synthesis) -> None:
    _report_value, indexes = _report(synthesis, ("RICH", "RICH"))

    authorities = [
        index["call_authority"]["environment_lock"]["evaluation_authority"]
        for index in indexes
    ]
    assert authorities[0] == authorities[1]
    assert set(authorities[0]) == {
        "schema_version",
        "hard_evaluator_identity_digest",
        "hard_task_identity_digest",
        "hard_fixture_identity_digest",
        "scorer_evaluation_digest",
        "scorer_identity_digest",
    }


def test_hard_identity_cannot_drift_coherently_from_frozen_evaluation_authority(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis, lock, schedule, bindings, ordinal=1, outcome="RICH"
    )
    _rehash_all_hard_identity(
        index,
        synthesis,
        field="evaluator_identity_digest",
        value=_sha("a"),
    )

    with pytest.raises(synthesis.SynthesisError, match="authority"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


@pytest.mark.parametrize(
    "field",
    [
        "evidence_frozen_digest",
        "evaluation_digest",
        "scorer_identity_digest",
    ],
)
def test_scorer_identity_must_match_packet_and_frozen_evaluation_authority(
    synthesis,
    field: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis, lock, schedule, bindings, ordinal=1, outcome="RICH"
    )
    _rehash_all_scorer_identity(index, field=field, value=_sha("a"))

    with pytest.raises(synthesis.SynthesisError, match="scorer"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_partial_allocations_cannot_undercount_selected_treatment_route(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis, lock, schedule, bindings, ordinal=1, phase="SCORER"
    )
    treatment_rows = [
        row
        for row in index["call_allocations"]
        if not row["call_slot_id"].startswith("EVAL.")
    ]
    removed_slot = treatment_rows[-1]["call_slot_id"]
    index["call_allocations"] = [
        row
        for row in index["call_allocations"]
        if row["call_slot_id"] != removed_slot
    ]
    index["receipts"] = [
        row for row in index["receipts"] if row["call_slot_id"] != removed_slot
    ]
    index["elapsed_ms"] = [
        row for row in index["elapsed_ms"] if row["call_slot_id"] != removed_slot
    ]
    accounting = index["attempt_record"]["accounting"]
    accounting["receipt_bindings"] = [
        row
        for row in accounting["receipt_bindings"]
        if row["call_slot_id"] != removed_slot
    ]
    accounting["call_count"] -= 1
    index["call_allocations"] = _rechain_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=index["call_allocations"],
    )
    index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="allocation"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_e2_terminal_settlement_requires_matching_selected_terminal_route(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis, lock, schedule, bindings, ordinal=1, phase="SCORER"
    )
    removed_slot = "DIRECT.I"
    accounting = index["attempt_record"]["accounting"]
    accounting["arm_routes"] = [
        row for row in accounting["arm_routes"] if row["arm"] != "DIRECT"
    ]
    accounting["receipt_bindings"] = [
        row
        for row in accounting["receipt_bindings"]
        if row["call_slot_id"] != removed_slot
    ]
    accounting["call_count"] -= 1
    index["receipts"] = [
        row for row in index["receipts"] if row["call_slot_id"] != removed_slot
    ]
    index["elapsed_ms"] = [
        row for row in index["elapsed_ms"] if row["call_slot_id"] != removed_slot
    ]
    index["call_allocations"] = _rechain_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=[
            row
            for row in index["call_allocations"]
            if row["call_slot_id"] != removed_slot
        ],
    )
    index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="allocation"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_frozen_public_packet_domain_requires_all_terminal_arm_authorities(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_stage_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        scorer_count=0,
        review_count=0,
        hard_count=0,
    )
    removed_slot = "DIRECT.I"
    record = index["attempt_record"]
    record["e2_authority"]["arm_settlements"] = [
        row
        for row in record["e2_authority"]["arm_settlements"]
        if row["cell"]["arm_id"] != "DIRECT"
    ]
    accounting = record["accounting"]
    accounting["arm_routes"] = [
        row for row in accounting["arm_routes"] if row["arm"] != "DIRECT"
    ]
    accounting["receipt_bindings"] = [
        row
        for row in accounting["receipt_bindings"]
        if row["call_slot_id"] != removed_slot
    ]
    accounting["call_count"] -= 1
    index["receipts"] = [
        row for row in index["receipts"] if row["call_slot_id"] != removed_slot
    ]
    index["elapsed_ms"] = [
        row for row in index["elapsed_ms"] if row["call_slot_id"] != removed_slot
    ]
    index["call_allocations"] = _rechain_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=[
            row
            for row in index["call_allocations"]
            if row["call_slot_id"] != removed_slot
        ],
    )
    index["attempt_record_sha256"] = _study_digest(record)
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="allocation"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_partial_allocation_rows_preserve_order_within_each_arm(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis, lock, schedule, bindings, ordinal=1, phase="SCORER"
    )
    first = next(
        index
        for index, row in enumerate(index["call_allocations"])
        if row["call_slot_id"] == "DESIGN_QA.D"
    )
    second = next(
        index
        for index, row in enumerate(index["call_allocations"])
        if row["call_slot_id"] == "DESIGN_QA.DR"
    )
    index["call_allocations"][first], index["call_allocations"][second] = (
        index["call_allocations"][second],
        index["call_allocations"][first],
    )
    index["call_allocations"] = _rechain_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=index["call_allocations"],
    )
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="allocation"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_allocation_chain_accepts_concurrent_frontier_interleaving(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis, lock, schedule, bindings, ordinal=1, outcome="RICH"
    )
    rows_by_slot = {
        row["call_slot_id"]: row for row in index["call_allocations"]
    }
    treatment_order = [
        "DIRECT.I",
        "DESIGN_QA.D",
        "PRODUCT_QA.I",
        "RICH.D",
        "DESIGN_QA.DR",
        "PRODUCT_QA.PR",
        "RICH.DR",
        "DESIGN_QA.I",
        "RICH.I",
        "RICH.PR",
    ]
    scorer_order = [
        "EVAL.SCORER_RICH",
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_DESIGN_QA",
    ]
    serial_order = [
        row["call_slot_id"]
        for row in index["call_allocations"]
        if row["call_slot_id"]
        not in set(treatment_order) | set(scorer_order)
    ]
    index["call_allocations"] = _rechain_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=[
            rows_by_slot[slot]
            for slot in treatment_order + scorer_order + serial_order
        ],
    )
    _rehash_index(index)

    synthesis.validate_attempt_evidence_index(
        index,
        expected_index_sha256=index["index_sha256"],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )


def test_allocation_chain_accepts_multiple_unsettled_concurrent_scorers(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis, lock, schedule, bindings, ordinal=1, phase="SCORER"
    )
    existing_slots = {
        row["call_slot_id"] for row in index["call_allocations"]
    }
    rows = list(index["call_allocations"])
    for slot in (
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_DESIGN_QA",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_RICH",
    ):
        if slot not in existing_slots:
            rows.append(
                {
                    "call_slot_id": slot,
                    "settlement": "INTERRUPTED_IN_FLIGHT",
                    "receipt_sha256": None,
                }
            )
    index["call_allocations"] = _rechain_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=rows,
    )
    _rehash_index(index)

    synthesis.validate_attempt_evidence_index(
        index,
        expected_index_sha256=index["index_sha256"],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )


def test_receiptless_allocation_has_closed_content_addressed_controller_event(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis, lock, schedule, bindings, ordinal=1, phase="SCORER"
    )
    final = index["call_allocations"][-1]

    assert final["settlement"] == "INTERRUPTED_IN_FLIGHT"
    assert set(final["allocation_authority"]) == {
        "schema_version",
        "attempt_id",
        "sequence",
        "previous_allocation_sha256",
        "call_slot_id",
        "decision_lock_sha256",
        "static_call_sha256",
    }
    assert final["allocation_sha256"] == canonical_sha256(
        final["allocation_authority"]
    )


@pytest.mark.parametrize(
    "field",
    ["decision_lock_sha256", "static_call_sha256"],
)
def test_allocation_authority_cannot_replay_across_frozen_context(
    synthesis,
    field: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_invalid_index(
        synthesis, lock, schedule, bindings, ordinal=1, phase="SCORER"
    )
    final = index["call_allocations"][-1]
    final["allocation_authority"][field] = _sha("a")
    final["allocation_sha256"] = canonical_sha256(
        final["allocation_authority"]
    )
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="allocation"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_partial_allocation_cannot_invent_integrated_before_hard_evidence(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_stage_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        scorer_count=4,
        review_count=2,
        hard_count=0,
    )
    index["call_allocations"] = _call_allocations(
        synthesis,
        lock,
        attempt_id="ES-ATTEMPT-01",
        rows=[
            (row["call_slot_id"], row["settlement"], row["receipt_sha256"])
            for row in index["call_allocations"]
        ]
        + [("EVAL.INTEGRATED_REVIEW", "INTERRUPTED_IN_FLIGHT", None)],
    )
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="allocation"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_report_derives_missing_deterministic_primary_without_mutating_indexes(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _partial_stage_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=ordinal,
            scorer_count=4,
            review_count=3,
            hard_count=4,
        )
        for ordinal in (1, 2)
    ]
    frozen_bytes = _study_bytes(indexes)

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert report["screen_result"] == "SCREEN_PASSED"
    assert [row["derived_outcome"] for row in report["primary_sequence"]] == [
        "RICH",
        "RICH",
    ]
    assert _study_bytes(indexes) == frozen_bytes


def test_interrupted_valid_report_fails_typed_when_provider_authority_is_incomplete(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _partial_stage_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        scorer_count=4,
        review_count=3,
        hard_count=4,
    )
    index["hard_evaluations"].pop()
    _rehash_index(index)

    with pytest.raises(
        synthesis.SynthesisError,
        match="synthesis_provider_authority_incomplete",
    ):
        synthesis.synthesize_report(
            indexed_attempts=[index],
            expected_index_digests=[index["index_sha256"]],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


@pytest.mark.parametrize(
    ("disagreement", "route_id"),
    [
        (False, "EVALUATION.WITH_ADJUDICATION"),
        (True, "EVALUATION.NO_ADJUDICATION"),
    ],
)
def test_partial_evaluation_route_adjudication_matches_recomputed_disagreement(
    synthesis,
    disagreement: bool,
    route_id: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    with pytest.raises(synthesis.SynthesisError, match="route|adjudication"):
        _partial_stage_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            scorer_count=4,
            review_count=2,
            hard_count=0,
            disagreement=disagreement,
            evaluation_route_override=route_id,
        )


def test_blinding_invalid_reports_scorer_failure_from_public_packet_mapping(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _blinding_invalid_retained_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            scorer_count=4,
            retain_malformed_join=False,
            failed_scorer_arm="PRODUCT_QA",
        ),
        _attempt_index(
            synthesis, lock, schedule, bindings, ordinal=2, outcome="RICH"
        ),
        _attempt_index(
            synthesis, lock, schedule, bindings, ordinal=3, outcome="RICH"
        ),
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert {
        "attempt_id": "ES-ATTEMPT-01",
        "arm_id": "PRODUCT_QA",
        "failure_class": "EVALUATION_FAILURE",
        "failure_code": "SCORER_TYPED_OUTPUT_INVALID",
    } in report["failure_classes"]


def test_second_sparse_invalid_is_terminal_stop_es_invalid(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _sparse_invalid_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=ordinal,
        )
        for ordinal in (1, 2)
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert report["screen_result"] == "STOP_ES_INVALID"


def test_integrated_review_failure_is_valid_indeterminate_evaluation_outcome(
    synthesis,
) -> None:
    report, indexes = _report(
        synthesis,
        ("RICH", "RICH", "RICH"),
        failed_review_slot="EVAL.INTEGRATED_REVIEW",
    )

    assert all(row["attempt_record"]["status"] == "VALID" for row in indexes)
    assert [row["derived_outcome"] for row in report["primary_sequence"]] == [
        "INDETERMINATE",
        "INDETERMINATE",
        "INDETERMINATE",
    ]
    assert report["screen_result"] == "INSUFFICIENT_EVIDENCE"
    assert [row["failure_code"] for row in report["failure_classes"]] == [
        "TYPED_OUTPUT_INVALID",
        "TYPED_OUTPUT_INVALID",
        "TYPED_OUTPUT_INVALID",
    ]


@pytest.mark.parametrize(
    "failed_slot",
    [
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    ],
)
def test_failed_initial_review_remains_valid_without_adjudication(
    synthesis,
    failed_slot: str,
) -> None:
    report, indexes = _report(
        synthesis,
        ("RICH", "RICH"),
        failed_review_slot=failed_slot,
    )

    assert all(row["attempt_record"]["status"] == "VALID" for row in indexes)
    assert all(row["adjudication_payload"] is None for row in indexes)
    assert all(
        not any(
            review["call_slot_id"] == "EVAL.ADJUDICATOR"
            for review in row["reviews"]
        )
        for row in indexes
    )
    assert report["screen_result"] == "SCREEN_PASSED"
    assert [row["failure_code"] for row in report["failure_classes"]] == [
        "TYPED_OUTPUT_INVALID",
        "TYPED_OUTPUT_INVALID",
    ]


@pytest.mark.parametrize(
    "failed_slot",
    [
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    ],
)
def test_failed_initial_review_forbids_adjudication(
    synthesis,
    failed_slot: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()

    with pytest.raises(synthesis.SynthesisError, match="adjudication"):
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            outcome="RICH",
            failed_review_slot=failed_slot,
            adjudicator_failure=True,
        )


def test_two_successful_disagreeing_initial_reviews_require_adjudication(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    with pytest.raises(
        synthesis.SynthesisError,
        match="material_disagreement|adjudication_required|route_adjudication",
    ):
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            outcome="RICH",
            initial_disagreement_without_adjudicator=True,
        )


def test_agreeing_initial_outcomes_forbid_adjudicator_even_if_rationales_differ(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    with pytest.raises(
        synthesis.SynthesisError,
        match=(
            "material_disagreement|adjudication_payload_unexpected|"
            "route_adjudication"
        ),
    ):
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            outcome="RICH",
            adjudicator_with_agreement=True,
        )
    accepted = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
        initial_rationale_difference=True,
    )
    assert accepted["attempt_record"]["accounting"]["material_disagreement"] is False


def test_integrated_review_is_bound_to_exact_prior_settlement_records(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
        failed_review_slot="EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
    )
    index["integrated_prior_record_sha256s"][0] = _sha("0")
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="integrated_prior"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_failed_adjudicator_uses_sealed_resolution_and_remains_valid(synthesis) -> None:
    report, indexes = _report(
        synthesis,
        ("RICH", "RICH"),
        adjudicator_failure=True,
    )

    assert all(row["attempt_record"]["status"] == "VALID" for row in indexes)
    assert all(
        row["adjudication_payload"] is not None
        and any(
            pair["outcome"] == "INDETERMINATE"
            for pair in row["adjudication_payload"]["pairwise_results"]
        )
        for row in indexes
    )
    assert report["screen_result"] == "SCREEN_PASSED"
    assert [row["failure_code"] for row in report["failure_classes"]] == [
        "TYPED_OUTPUT_INVALID",
        "TYPED_OUTPUT_INVALID",
    ]


def test_scorer_success_has_exact_four_slot_projection(synthesis) -> None:
    _report_value, indexes = _report(synthesis, ("RICH", "RICH"))

    assert all(
        len(index["scorer_settlements"]) == 4
        and all(
            set(row) == {"opaque_label", "settlement_row", "score_row"}
            for row in index["scorer_settlements"]
        )
        and [
            row["score_row"]["score_status"]
            for row in index["scorer_settlements"]
        ]
        == ["scored"] * 4
        for index in indexes
    )


def test_scorer_evaluation_failure_is_valid_and_disclosed_from_score_authority(
    synthesis,
) -> None:
    report, indexes = _report(
        synthesis,
        ("RICH", "RICH"),
        failed_scorer_arm="PRODUCT_QA",
    )

    failed_rows = [
        row
        for index in indexes
        for row in index["scorer_settlements"]
        if row["score_row"]["score_status"] == "evaluation_failed"
    ]
    assert len(failed_rows) == 2
    assert all(
        row["score_row"]["charged_attempts"][-1]["exit_code"] == 0
        for row in failed_rows
    )
    assert report["screen_result"] == "SCREEN_PASSED"
    scorer_failures = [
        row
        for row in report["failure_classes"]
        if row["failure_code"] == "SCORER_TYPED_OUTPUT_INVALID"
    ]
    assert scorer_failures == [
        {
            "attempt_id": f"ES-ATTEMPT-{ordinal:02d}",
            "arm_id": "PRODUCT_QA",
            "failure_class": "EVALUATION_FAILURE",
            "failure_code": "SCORER_TYPED_OUTPUT_INVALID",
        }
        for ordinal in (1, 2)
    ]


def test_scorer_status_tamper_is_rejected_after_coherent_digest_rehash(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    index["scorer_settlements"][0]["score_row"][
        "score_status"
    ] = "evaluation_failed"
    _rehash_scorer_projection(index, 0)

    with pytest.raises(synthesis.SynthesisError, match="scorer"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_scorer_terminal_settlement_must_join_mapped_e2_arm(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    index["scorer_settlements"][0]["settlement_row"]["payload"][
        "terminal_attempt_settlement_row_digest"
    ] = _sha("f")
    _rehash_scorer_projection(index, 0)

    with pytest.raises(synthesis.SynthesisError, match="scorer"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


@pytest.mark.parametrize("mutation", ["extra", "failure_code"])
def test_failed_review_record_is_closed_and_tamper_evident(
    synthesis,
    mutation: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
        failed_review_slot="EVAL.INTEGRATED_REVIEW",
    )
    failure = next(row for row in index["reviews"] if row["status"] == "FAILED")
    if mutation == "extra":
        failure["record"]["detail"] = "provider prose is not authority"
    else:
        failure["record"]["failure_code"] = ""
    failure["record_sha256"] = _study_digest(failure["record"])
    settlement = next(
        row
        for row in index["attempt_record"]["accounting"]["review_settlements"]
        if row["call_slot_id"] == failure["call_slot_id"]
    )
    settlement["record_sha256"] = failure["record_sha256"]
    index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    body = {key: value for key, value in index.items() if key != "index_sha256"}
    index["index_sha256"] = _study_digest(body)

    with pytest.raises(synthesis.SynthesisError, match="failure"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


@pytest.mark.parametrize("status", ["VALID", "INVALID"])
def test_valid_omission_and_self_contradictory_partial_invalid_are_rejected(
    synthesis,
    status: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    if status == "VALID":
        index["packets"] = []
    else:
        index["attempt_record"]["classifier_inputs"][
            "evaluation_bytes_valid"
        ] = False
        index["attempt_record"]["status"] = "INVALID"
        index["attempt_record"][
            "invalidity_code"
        ] = "COMMON_EVALUATION_BYTES_INVALID"
        index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    body = {key: value for key, value in index.items() if key != "index_sha256"}
    index["index_sha256"] = _study_digest(body)

    with pytest.raises(synthesis.SynthesisError):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_complete_evidence_bundle_cannot_claim_invalid_after_coherent_rehash(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    index["attempt_record"]["classifier_inputs"][
        "evaluation_bytes_valid"
    ] = False
    index["attempt_record"]["status"] = "INVALID"
    index["attempt_record"][
        "invalidity_code"
    ] = "COMMON_EVALUATION_BYTES_INVALID"
    index["attempt_record_sha256"] = _study_digest(index["attempt_record"])
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="requires_valid"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_second_invalid_attempt_routes_to_stop_es_invalid(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    indexes = [
        _sparse_invalid_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=ordinal,
            invalidity_code="COMMON_EVALUATION_BYTES_INVALID",
        )
        for ordinal in (1, 2)
    ]

    report = synthesis.synthesize_report(
        indexed_attempts=indexes,
        expected_index_digests=[row["index_sha256"] for row in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )

    assert report["screen_result"] == "STOP_ES_INVALID"


@pytest.mark.parametrize(
    "member",
    [
        "attempt_record",
        "packet",
        "review",
        "finding",
        "receipt",
        "receipt_raw",
        "elapsed",
        "index",
    ],
)
def test_regeneration_rejects_every_bound_evidence_mutation(
    synthesis,
    member: str,
) -> None:
    _report_value, indexes = _report(synthesis, ("RICH", "RICH"))
    lock, schedule, bindings = _lock_and_schedule()
    candidate = deepcopy(indexes)
    if member == "attempt_record":
        candidate[0]["attempt_record"]["interrupted"] = True
    elif member == "packet":
        candidate[0]["packets"][0]["packet"]["items"][0]["value"] = {"changed": True}
    elif member == "review":
        candidate[0]["reviews"][0]["record"]["payload"]["candidates"][0][
            "dimensions"
        ][0]["assessment"] = "FAIL"
    elif member == "finding":
        candidate[0]["hard_evaluations"][0]["evaluation"]["hard_findings"] = [
            {"clause_id": FAILED_CLAUSE, "disposition": "PRODUCT_DEFECT"}
        ]
    elif member == "receipt":
        candidate[0]["receipts"][0]["record"]["usage"]["reported_total_tokens"] += 1
    elif member == "receipt_raw":
        candidate[0]["receipts"][0]["raw_jsonl"] += "{}\n"
    elif member == "elapsed":
        candidate[0]["elapsed_ms"][0]["elapsed_ms"] += 1
    else:
        candidate[0]["schema_version"] = "es_synthesis_attempt_index.v2"

    with pytest.raises(synthesis.SynthesisError):
        synthesis.synthesize_report(
            indexed_attempts=candidate,
            expected_index_digests=[row["index_sha256"] for row in indexes],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_hard_evidence_rejects_unknown_extra_finding_after_coherent_rehash(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    row = index["hard_evaluations"][0]
    row["evaluation"]["hard_findings"].append(
        {
            "candidate_id": row["evaluation"]["candidate_id"],
            "clause_id": "F1-H99-NOT-IN-THE-LOCKED-CONTRACT",
            "details": "fabricated finding",
            "disposition": "UNRESOLVED",
            "evaluator_observation": {
                "evidence_digest": _sha("f"),
                "satisfied": False,
            },
            "schema_version": "es-f1-hard-finding.v1",
        }
    )
    _rehash_hard_row(index, 0)

    with pytest.raises(synthesis.SynthesisError, match="replay_mismatch"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_hard_evidence_rejects_cross_arm_authority_mismatch_after_coherent_rehash(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    row = index["hard_evaluations"][1]
    row["replay_inputs"]["evaluator_identity_digest"] = _sha("9")
    freeze = _freeze_from_replay(row["replay_inputs"])
    row["freeze"] = freeze.record
    row["freeze_sha256"] = freeze.digest
    row["evaluation"] = freeze.evaluation
    row["evaluation_sha256"] = freeze.evaluation_digest
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="authority_mismatch"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_hard_replay_rejects_forged_oracle_defect_after_proof_removal(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
        oracle_defect_arm="DIRECT",
    )
    row = index["hard_evaluations"][0]
    assert row["evaluation"]["hard_findings"][0]["disposition"] == "ORACLE_DEFECT"
    row["replay_inputs"]["proof_rows"] = []
    row["replay_inputs"]["frozen_proof_authority"] = []
    _rehash_index(index)

    with pytest.raises(synthesis.SynthesisError, match="replay_mismatch"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_failed_rich_arm_has_explicit_missing_freeze_and_indeterminate_primary(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
        rich_failed=True,
        missing_freeze_arm="RICH",
    )

    assert index["hard_evaluations"][3] == {
        "schema_version": "es.hard_evaluation_evidence.v1",
        "arm_id": "RICH",
        "trusted_product_freeze_status": "MISSING",
        "absence_authority": {
            "schema_version": "es.trusted_product_freeze_absence.v1",
            "reason": "TERMINAL_TREATMENT_FAILURE",
            "cell": {"arm_id": "RICH", "rep": 1},
            "terminal_row_digest": _sha("4"),
        },
    }
    assert index["hard_primary_outcome"]["raw_outcome"] == "RICH"
    assert index["hard_primary_outcome"]["derived_outcome"] == "INDETERMINATE"
    assert index["hard_primary_outcome"]["rich_freeze_digest"] is None


def test_completed_arm_cannot_claim_missing_trusted_product_freeze(synthesis) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    with pytest.raises(synthesis.SynthesisError, match="absence_invalid"):
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            outcome="RICH",
            missing_freeze_arm="RICH",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "forbidden_resume",
        "missing_unrestricted_flag",
        "wrong_prompt",
        "wrong_contract",
        "wrong_executable",
    ],
)
def test_receipt_join_rejects_static_call_authority_tampering_after_rehash(
    synthesis,
    mutation: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    receipt = index["receipts"][0]["record"]
    if mutation == "forbidden_resume":
        receipt["process"]["argv"].insert(2, "resume")
    elif mutation == "missing_unrestricted_flag":
        receipt["process"]["argv"].remove("--skip-git-repo-check")
    elif mutation == "wrong_prompt":
        receipt["prompt_sha256"] = _sha("a")
    elif mutation == "wrong_contract":
        receipt["contract_sha256"] = _sha("b")
    else:
        receipt["executable_chain"]["launcher_sha256"] = _sha("c")
    if mutation in {"forbidden_resume", "missing_unrestricted_flag"}:
        receipt["process"]["argv_sha256"] = "sha256:" + hashlib.sha256(
            metering.canonical_json_bytes(receipt["process"]["argv"])
        ).hexdigest()
    _rehash_receipt_row(index, 0)

    with pytest.raises(
        synthesis.SynthesisError,
        match="receipt_join_invalid|call_authority",
    ):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_private_join_regeneration_rejects_non_authoritative_cell_after_rehash(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    index["private_blinding_join"]["rows"][0]["cell"]["rep"] = 2
    index["private_blinding_join_sha256"] = canonical_sha256(
        index["private_blinding_join"]
    )
    index["oriented_primary"]["unblinding_map_digest"] = index[
        "private_blinding_join_sha256"
    ]
    index["oriented_primary_sha256"] = _study_digest(index["oriented_primary"])
    _rehash_index(index)

    with pytest.raises(
        synthesis.SynthesisError, match="private_join|public_packet"
    ):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


@pytest.mark.parametrize("mutation", ["packet_path", "package_bijection"])
def test_private_join_replay_rejects_path_and_bijection_tamper_after_rehash(
    synthesis,
    mutation: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    if mutation == "packet_path":
        index["public_packet_replay_inputs"]["packet_artifact_index"][
            "packets"
        ][0]["packet_relpath"] = "artifacts/trials/wrong/packets/wrong.json"
        index["private_blinding_join"]["rows"][0]["packet_path"] = (
            "artifacts/trials/wrong/packets/wrong.json"
        )
    else:
        first, second = index["private_blinding_join"]["rows"][:2]
        first["package_id"], second["package_id"] = (
            second["package_id"],
            first["package_id"],
        )
    index["private_blinding_join_sha256"] = canonical_sha256(
        index["private_blinding_join"]
    )
    index["oriented_primary"]["unblinding_map_digest"] = index[
        "private_blinding_join_sha256"
    ]
    index["oriented_primary_sha256"] = _study_digest(index["oriented_primary"])
    _rehash_index(index)

    with pytest.raises(
        synthesis.SynthesisError, match="private_join|public_packet"
    ):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


@pytest.mark.parametrize("mutation", ["launcher", "model"])
def test_static_call_authority_rejects_coherent_receipt_self_authority(
    synthesis,
    mutation: str,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    index = _attempt_index(
        synthesis,
        lock,
        schedule,
        bindings,
        ordinal=1,
        outcome="RICH",
    )
    receipt = index["receipts"][0]["record"]
    if mutation == "launcher":
        receipt["executable_chain"]["launcher_sha256"] = _sha("c")
    else:
        receipt["process"]["argv"][2:2] = ["--model", "changed-model"]
        receipt["process"]["argv_sha256"] = "sha256:" + hashlib.sha256(
            metering.canonical_json_bytes(receipt["process"]["argv"])
        ).hexdigest()
    _rehash_receipt_row(index, 0)

    with pytest.raises(synthesis.SynthesisError, match="call_authority"):
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def test_missing_attempt_denominator_extension_and_post_stop_rows_are_rejected(
    synthesis,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    rows = [
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=index,
            outcome="RICH",
        )
        for index in range(1, 4)
    ]
    cases = (
        [rows[1]],
        rows + [deepcopy(rows[-1])],
        rows,
    )
    for candidate in cases:
        with pytest.raises(synthesis.SynthesisError):
            synthesis.synthesize_report(
                indexed_attempts=candidate,
                expected_index_digests=[row["index_sha256"] for row in candidate],
                decision_lock=lock,
                randomization_manifest=schedule,
                expected_bindings=bindings,
            )


def test_schema_binding_drift_fails_closed_without_inventing_extension_route(
    synthesis,
) -> None:
    report, indexes = _report(synthesis, ("RICH", "RICH"))
    assert report["e3_readiness_input"] == "BLACK_BOX_SUFFICIENT"
    lock, schedule, bindings = _lock_and_schedule()
    drifted_bindings = dict(bindings)
    drifted_bindings["report_schema_sha256"] = _sha("0")
    with pytest.raises(synthesis.SynthesisError, match="schema"):
        synthesis.synthesize_report(
            indexed_attempts=indexes,
            expected_index_digests=[row["index_sha256"] for row in indexes],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=drifted_bindings,
        )


def test_receipt_adapter_rejects_absolute_raw_path_before_writing(
    synthesis,
    tmp_path: Path,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    escaped = tmp_path / "absolute-escape.jsonl"

    with pytest.raises(synthesis.SynthesisError):
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            outcome="RICH",
            raw_path_override=str(escaped),
        )

    assert not escaped.exists()


def test_receipt_adapter_rejects_parent_escape_before_writing(
    synthesis,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock, schedule, bindings = _lock_and_schedule()
    adapter_root = tmp_path / "adapter-root"
    adapter_root.mkdir()
    escaped = tmp_path / "relative-escape.jsonl"

    class FixedTemporaryDirectory:
        def __init__(self, *, prefix: str) -> None:
            assert prefix in {
                "es-synthesis-receipts-",
                "es-synthesis-scores-",
            }
            self._path = (
                adapter_root
                if prefix == "es-synthesis-receipts-"
                else tmp_path / "score-adapter-root"
            )
            self._path.mkdir(exist_ok=True)

        def __enter__(self) -> str:
            return str(self._path)

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        synthesis.tempfile,
        "TemporaryDirectory",
        FixedTemporaryDirectory,
    )

    with pytest.raises(synthesis.SynthesisError):
        _attempt_index(
            synthesis,
            lock,
            schedule,
            bindings,
            ordinal=1,
            outcome="RICH",
            raw_path_override="../relative-escape.jsonl",
        )

    assert not escaped.exists()
