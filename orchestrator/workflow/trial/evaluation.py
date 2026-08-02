"""Treatment-blind evaluator transport and durable score settlement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderParams
from orchestrator.workflow.adjudication import (
    EvaluatorOutputError,
    load_scorer_snapshot,
    materialize_run_score_ledger,
    persist_scorer_snapshot,
)
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256

from .config import TrialRuntimeRequest
from .ledger import (
    TrialLedgerRow,
    append_trial_evaluator_attempt_allocation,
    append_trial_evaluator_attempt_settlement,
    append_trial_evidence_freeze,
    append_trial_score_settlement,
    append_trial_scorer_freeze,
    append_trial_scores_freeze,
    load_trial_event_ledger,
    load_trial_score_rows,
    replay_trial_evaluator_attempts,
)
from .packets import (
    TrialPacketError,
    parse_trial_evaluator_output,
    trial_scorer_identity_hash,
    validate_trial_evaluation_packet,
)


TRIAL_SCORE_ROW_SCHEMA = "trial.score.v1"
TRIAL_EVALUATOR_INSTRUCTION_ID = "trial_evaluator_instruction.v1"
TRIAL_EVALUATOR_INSTRUCTION = canonical_json_bytes(
    {
        "schema": TRIAL_EVALUATOR_INSTRUCTION_ID,
        "judgment": "score the blinded packet against the supplied rubric",
        "output": {
            "candidate_id": "exact packet evaluation_id",
            "score": "finite number in [0,1]",
            "summary": "non-empty text",
            "citations": "list of packet citable_item_ids",
        },
    }
).decode("utf-8")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCORER_CONFIG_KEYS = {
    "provider",
    "provider_params",
    "evaluator_prompt_source",
    "rubric_source",
    "evidence_limits",
    "evidence_confidentiality",
}


class TrialEvaluationError(ValueError):
    """The evaluator authority or durable score state is invalid."""

    code = "trial_evaluation_invalid"


@dataclass(frozen=True, slots=True)
class TrialEvaluationResult:
    rows: tuple[dict[str, Any], ...]
    scorer_identity_digest: str
    scorer_snapshot_path: Path
    score_ledger_path: Path


def ensure_trial_evidence_freeze(path: Path) -> TrialLedgerRow:
    """Create the exact evidence freeze once, or reuse its validated row."""

    ledger = load_trial_event_ledger(Path(path))
    frozen = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    if len(frozen) == 1:
        return frozen[0]
    if frozen:
        raise TrialEvaluationError("trial evidence freeze is ambiguous")
    return append_trial_evidence_freeze(
        Path(path),
        expected_head_digest=ledger.rows[-1].row_digest,
    )


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TrialEvaluationError(f"{field} must be a canonical sha256 digest")
    return value


def _canonical_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _text_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _source_kind_and_path(value: object, *, field: str) -> tuple[str, str]:
    if not isinstance(value, Mapping) or len(value) != 1:
        raise TrialEvaluationError(f"{field} must select exactly one prompt source")
    [(kind, path)] = value.items()
    if (
        kind not in {"input_file", "asset_file", "platform_instruction"}
        or not isinstance(path, str)
        or not path
    ):
        raise TrialEvaluationError(f"{field} prompt source is invalid")
    if (
        kind == "platform_instruction"
        and path != TRIAL_EVALUATOR_INSTRUCTION_ID
    ):
        raise TrialEvaluationError(f"{field} platform instruction is invalid")
    return kind, path


def _contract_error(message: str, context: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"type": "trial_prompt_source_invalid", "message": message, "context": context}}


def _read_prompt(
    composer: PromptComposer,
    source: Mapping[str, str],
    *,
    step_name: str,
) -> str:
    if source == {
        "platform_instruction": TRIAL_EVALUATOR_INSTRUCTION_ID,
    }:
        return TRIAL_EVALUATOR_INSTRUCTION
    content, error = composer.read_prompt_source(
        dict(source),
        step_name=step_name,
        contract_violation_result=_contract_error,
    )
    if error is not None or not isinstance(content, str):
        raise TrialEvaluationError(f"{step_name} source could not be resolved")
    return content


def build_trial_scorer_config(request: TrialRuntimeRequest) -> dict[str, Any]:
    """Derive production scorer authority from one exact trial request."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("trial scorer request must be exact TrialRuntimeRequest")
    evaluation = request.static_config.evaluation
    return {
        "provider": evaluation["provider"],
        "provider_params": {},
        "evaluator_prompt_source": {
            "platform_instruction": TRIAL_EVALUATOR_INSTRUCTION_ID,
        },
        "rubric_source": {"asset_file": evaluation["rubric_asset"]},
        "evidence_limits": {
            "max_item_bytes": evaluation["max_item_bytes"],
            "max_packet_bytes": evaluation["max_packet_bytes"],
        },
        "evidence_confidentiality": "same_trust_boundary",
    }


def _resolve_scorer(
    *,
    scorer_config: Mapping[str, Any],
    provider_registry: ProviderRegistry,
    prompt_composer: PromptComposer,
) -> tuple[dict[str, Any], str, str]:
    if set(scorer_config) != _SCORER_CONFIG_KEYS:
        raise TrialEvaluationError("trial scorer config has missing or extra fields")
    provider = scorer_config["provider"]
    params = scorer_config["provider_params"]
    if not isinstance(provider, str) or not provider or not provider_registry.exists(provider):
        raise TrialEvaluationError("trial evaluator provider is unresolved")
    if not isinstance(params, Mapping) or any(not isinstance(key, str) for key in params):
        raise TrialEvaluationError("trial evaluator params must be a string-keyed mapping")
    prompt_kind, prompt_path = _source_kind_and_path(
        scorer_config["evaluator_prompt_source"], field="evaluator"
    )
    rubric_kind, rubric_path = _source_kind_and_path(
        scorer_config["rubric_source"], field="rubric"
    )
    prompt = _read_prompt(
        prompt_composer,
        {prompt_kind: prompt_path},
        step_name="trial_evaluator_prompt",
    )
    rubric = _read_prompt(
        prompt_composer,
        {rubric_kind: rubric_path},
        step_name="trial_evaluator_rubric",
    )
    limits = scorer_config["evidence_limits"]
    if not isinstance(limits, Mapping) or set(limits) != {
        "max_item_bytes",
        "max_packet_bytes",
    }:
        raise TrialEvaluationError("trial scorer evidence limits are invalid")
    if scorer_config["evidence_confidentiality"] != "same_trust_boundary":
        raise TrialEvaluationError("trial scorer confidentiality is invalid")
    merged = provider_registry.merge_params(provider, dict(params))
    scorer = {
        "evaluator_provider": provider,
        "evaluator_params": merged,
        "evaluator_prompt_source_kind": prompt_kind,
        "evaluator_prompt_source": prompt_path,
        "evaluator_prompt_hash": _text_digest(prompt),
        "rubric_source_kind": rubric_kind,
        "rubric_source": rubric_path,
        "rubric_hash": _text_digest(rubric),
        "evidence_limits": dict(limits),
        "evidence_confidentiality": "same_trust_boundary",
    }
    scorer["scorer_identity_digest"] = trial_scorer_identity_hash(scorer)
    return scorer, prompt, rubric


def _score_row(
    *,
    trial_request_digest: str,
    evaluation_digest: str,
    evidence_frozen_digest: str,
    packet: Mapping[str, Any],
    scorer_identity_digest: str,
    parsed: Mapping[str, Any] | None,
    charged_attempts: Sequence[Mapping[str, Any]],
    failure: Mapping[str, Any] | None,
) -> dict[str, Any]:
    packet_digest = canonical_sha256(packet)
    authority = {
        "trial_request_digest": trial_request_digest,
        "evaluation_digest": evaluation_digest,
        "evidence_frozen_digest": evidence_frozen_digest,
        "evaluation_label": packet["evaluation_id"],
        "evaluation_packet_digest": packet_digest,
        "scorer_identity_digest": scorer_identity_digest,
    }
    identity = {
        "schema_version": "trial_score_identity.v1",
        **authority,
    }
    normalized_attempts = [
        {
            **dict(attempt),
            "token_usage": dict(attempt.get("token_usage", {"variant": "UNKNOWN"})),
            "cost": dict(attempt.get("cost", {"variant": "UNKNOWN"})),
        }
        for attempt in charged_attempts
    ]
    row = {
        "row_schema": TRIAL_SCORE_ROW_SCHEMA,
        "score_run_key": canonical_sha256(identity),
        **authority,
        "score_status": "scored" if parsed is not None else "evaluation_failed",
        "score": parsed["score"] if parsed is not None else None,
        "summary": parsed["summary"] if parsed is not None else None,
        "citations": list(parsed["citations"]) if parsed is not None else [],
        "attempt_count": len(normalized_attempts),
        "charged_attempts": normalized_attempts,
        "failure": dict(failure) if failure is not None else None,
    }
    return {**row, "row_content_digest": canonical_sha256(row)}


def evaluate_trial_packets(
    *,
    packets: Sequence[Mapping[str, Any]],
    trial_request_digest: str,
    evaluation_digest: str,
    evidence_frozen_digest: str,
    scorer_config: Mapping[str, Any],
    provider_registry: ProviderRegistry,
    prompt_composer: PromptComposer,
    provider_executor: ProviderExecutor,
    scorer_root: Path,
    score_ledger_path: Path,
    trial_event_ledger_path: Path,
    evaluator_workspace: Path,
    max_evaluator_attempts: int,
    max_evaluator_concurrency: int,
    deadline_unix_ns: int | None = None,
    wall_time_ns: Any = time.time_ns,
) -> TrialEvaluationResult:
    """Evaluate the exact frozen packet domain with crash-durable attempt charges."""

    for field, value in (
        ("trial request digest", trial_request_digest),
        ("evaluation digest", evaluation_digest),
        ("evidence freeze digest", evidence_frozen_digest),
    ):
        _digest(value, field=field)
    if isinstance(packets, (str, bytes)) or not isinstance(packets, Sequence) or not packets:
        raise TrialEvaluationError("trial evaluator requires one or more packets")
    normalized_packets = tuple(validate_trial_evaluation_packet(packet) for packet in packets)
    labels = tuple(packet["evaluation_id"] for packet in normalized_packets)
    if len(set(labels)) != len(labels):
        raise TrialEvaluationError("trial evaluation labels must be unique")
    if (
        type(max_evaluator_attempts) is not int
        or max_evaluator_attempts < 1
        or type(max_evaluator_concurrency) is not int
        or max_evaluator_concurrency < 1
        or max_evaluator_concurrency > max_evaluator_attempts
    ):
        raise TrialEvaluationError("trial evaluator attempt budget is invalid")
    if deadline_unix_ns is not None and (
        type(deadline_unix_ns) is not int or deadline_unix_ns < 0
    ):
        raise TrialEvaluationError("trial evaluator deadline is invalid")
    if not callable(wall_time_ns):
        raise TypeError("trial evaluator wall clock must be callable")

    def wall_now_ns() -> int:
        now = wall_time_ns()
        if type(now) is not int or now < 0:
            raise TrialEvaluationError("trial evaluator wall clock is invalid")
        return now

    def elapsed_since_allocation(allocation: TrialLedgerRow) -> int:
        started_at_unix_ns = allocation.payload["started_at_unix_ns"]
        now = wall_now_ns()
        if now < started_at_unix_ns:
            raise TrialEvaluationError(
                "trial evaluator wall clock moved backwards"
            )
        return (now - started_at_unix_ns) // 1_000_000

    event_path = Path(trial_event_ledger_path)
    event_ledger = load_trial_event_ledger(event_path)
    header = event_ledger.rows[0].payload
    if (
        header["trial_request_digest"] != trial_request_digest
        or header["evaluation_digest"] != evaluation_digest
    ):
        raise TrialEvaluationError("trial evaluator ledger authority disagrees")
    evidence_rows = [row for row in event_ledger.rows if row.kind == "evidence_frozen"]
    packet_rows = [row for row in event_ledger.rows if row.kind == "packets_frozen"]
    if len(evidence_rows) != 1 or evidence_rows[0].row_digest != evidence_frozen_digest:
        raise TrialEvaluationError("trial evaluator evidence-freeze authority disagrees")
    if len(packet_rows) != 1:
        raise TrialEvaluationError("trial evaluator packet authority is missing")
    expected_packets = [
        {
            "opaque_label": packet["evaluation_id"],
            "packet_digest": canonical_sha256(packet),
        }
        for packet in normalized_packets
    ]
    frozen_packets = [
        {
            "opaque_label": row["opaque_label"],
            "packet_digest": row["packet_digest"],
        }
        for row in packet_rows[0].payload["cell_packets"]
    ]
    if expected_packets != frozen_packets:
        raise TrialEvaluationError("trial evaluator packet authority disagrees")

    scorer, prompt, rubric = _resolve_scorer(
        scorer_config=scorer_config,
        provider_registry=provider_registry,
        prompt_composer=prompt_composer,
    )
    scorer_identity = scorer["scorer_identity_digest"]
    scorer_snapshot_digest = canonical_sha256(scorer)
    prior_scorer = load_scorer_snapshot(scorer_root)
    if prior_scorer is not None and prior_scorer != scorer:
        raise TrialEvaluationError("persisted trial scorer authority disagrees")
    scorer_rows = [row for row in event_ledger.rows if row.kind == "scorer_frozen"]
    scorer_event: TrialLedgerRow | None = None
    if len(scorer_rows) == 1:
        scorer_event = scorer_rows[0]
        if scorer_event.payload != {
            "scorer_identity_digest": scorer_identity,
            "snapshot_digest": scorer_snapshot_digest,
        }:
            raise TrialEvaluationError("persisted trial scorer event disagrees")
    elif scorer_rows:
        raise TrialEvaluationError("persisted trial scorer event is ambiguous")

    packets_by_label = {packet["evaluation_id"]: packet for packet in normalized_packets}
    prior_rows = load_trial_score_rows(
        score_ledger_path,
        validation_mode="partial",
    )
    prior_by_label: dict[str, dict[str, Any]] = {}
    for row in prior_rows:
        label = row["evaluation_label"]
        packet = packets_by_label.get(label)
        if packet is None:
            raise TrialEvaluationError("persisted trial score names an unknown label")
        expected = {
            "trial_request_digest": trial_request_digest,
            "evaluation_digest": evaluation_digest,
            "evidence_frozen_digest": evidence_frozen_digest,
            "evaluation_packet_digest": canonical_sha256(packet),
            "scorer_identity_digest": scorer_identity,
        }
        if any(row[field] != value for field, value in expected.items()):
            raise TrialEvaluationError("persisted trial score authority disagrees")
        if any(citation not in packet["citable_item_ids"] for citation in row["citations"]):
            raise TrialEvaluationError("persisted trial score citation authority disagrees")
        prior_by_label[label] = row

    def attempt_record(row: TrialLedgerRow) -> dict[str, Any]:
        payload = row.payload
        return {
            "attempt": payload["local_attempt"],
            "global_attempt": payload["global_attempt"],
            "status": payload["status"],
            "exit_code": payload["exit_code"],
            "duration_ms": payload["duration_ms"],
            "token_usage": payload["token_usage"],
            "cost": payload["cost"],
        }

    preflight_replay = replay_trial_evaluator_attempts(event_path)
    preflight_settlements = {
        row.payload["allocation_row_digest"]: row
        for row in preflight_replay.settlements
    }
    preflight_charged: dict[str, list[dict[str, Any]]] = {
        label: [] for label in labels
    }
    active_by_label: dict[str, list[TrialLedgerRow]] = {
        label: [] for label in labels
    }
    for allocation in preflight_replay.allocations:
        label = allocation.payload["opaque_label"]
        if label not in preflight_charged:
            raise TrialEvaluationError("persisted evaluator attempt names an unknown label")
        settlement = preflight_settlements.get(allocation.row_digest)
        if settlement is None:
            active_by_label[label].append(allocation)
        else:
            preflight_charged[label].append(attempt_record(settlement))
    for label, row in prior_by_label.items():
        active = active_by_label[label]
        if not active:
            expected_attempts = preflight_charged[label]
        elif len(active) == 1 and row["score_status"] == "scored":
            allocation = active[0]
            final_attempt = row["charged_attempts"][-1]
            if (
                final_attempt["attempt"] != allocation.payload["local_attempt"]
                or final_attempt["global_attempt"]
                != allocation.payload["global_attempt"]
                or final_attempt["status"] != "scored"
                or final_attempt["exit_code"] != 0
            ):
                raise TrialEvaluationError(
                    "persisted trial score attempt authority disagrees"
                )
            expected_attempts = [*preflight_charged[label], final_attempt]
        else:
            raise TrialEvaluationError("persisted trial score attempt authority disagrees")
        if row["charged_attempts"] != expected_attempts:
            raise TrialEvaluationError("persisted trial score attempt authority disagrees")
    if preflight_replay.charged_attempt_count > max_evaluator_attempts:
        raise TrialEvaluationError("persisted evaluator attempts exceed the trial budget")

    existing_score_events = {
        row.payload["opaque_label"]: row
        for row in event_ledger.rows
        if row.kind == "score_settled"
    }
    if scorer_event is not None and prior_scorer is None:
        raise TrialEvaluationError("persisted trial scorer snapshot is missing")
    if (prior_by_label or existing_score_events) and scorer_event is None:
        raise TrialEvaluationError("persisted trial score lacks scorer authority")
    for label, event in existing_score_events.items():
        row = prior_by_label.get(label)
        if (
            row is None
            or event.payload["score_row_content_digest"]
            != row["row_content_digest"]
        ):
            raise TrialEvaluationError("persisted trial score event disagrees")

    scorer_snapshot_path = (
        persist_scorer_snapshot(scorer, scorer_root)
        if prior_scorer is None
        else scorer_root / "metadata.json"
    )
    if scorer_event is None:
        scorer_event = append_trial_scorer_freeze(
            event_path,
            expected_head_digest=event_ledger.rows[-1].row_digest,
            scorer_identity_digest=scorer_identity,
            snapshot_digest=scorer_snapshot_digest,
        )

    def head_digest() -> str:
        return load_trial_event_ledger(event_path).rows[-1].row_digest

    def current_attempt_state() -> tuple[Any, dict[str, TrialLedgerRow]]:
        replay = replay_trial_evaluator_attempts(event_path)
        settlements = {row.payload["allocation_row_digest"]: row for row in replay.settlements}
        return replay, settlements

    # Reconcile any allocation left active by a crash before charging a retry.
    replay, settlements_by_allocation = current_attempt_state()
    for allocation in replay.active_allocations:
        label = allocation.payload["opaque_label"]
        prior = prior_by_label.get(label)
        if prior is not None and prior["score_status"] == "scored":
            parsed_digest = canonical_sha256(
                {
                    "candidate_id": label,
                    "score": prior["score"],
                    "summary": prior["summary"],
                    "citations": prior["citations"],
                }
            )
            settlement = append_trial_evaluator_attempt_settlement(
                event_path,
                expected_head_digest=head_digest(),
                allocation_row_digest=allocation.row_digest,
                opaque_label=label,
                local_attempt=allocation.payload["local_attempt"],
                global_attempt=allocation.payload["global_attempt"],
                status="scored",
                exit_code=0,
                duration_ms=prior["charged_attempts"][-1]["duration_ms"],
                token_usage=prior["charged_attempts"][-1]["token_usage"],
                cost=prior["charged_attempts"][-1]["cost"],
                stdout_digest=None,
                stderr_digest=None,
                output_digest=parsed_digest,
                score_row_content_digest=prior["row_content_digest"],
            )
            append_trial_score_settlement(
                event_path,
                expected_head_digest=settlement.row_digest,
                opaque_label=label,
                score_row_content_digest=prior["row_content_digest"],
                terminal_attempt_settlement_row_digest=settlement.row_digest,
            )
        else:
            elapsed_ms = elapsed_since_allocation(allocation)
            append_trial_evaluator_attempt_settlement(
                event_path,
                expected_head_digest=head_digest(),
                allocation_row_digest=allocation.row_digest,
                opaque_label=label,
                local_attempt=allocation.payload["local_attempt"],
                global_attempt=allocation.payload["global_attempt"],
                status="provider_failed",
                exit_code=None,
                duration_ms=elapsed_ms,
                token_usage={"variant": "UNKNOWN"},
                cost={"variant": "UNKNOWN"},
                stdout_digest=None,
                stderr_digest=None,
                output_digest=None,
                score_row_content_digest=None,
            )

    replay, settlements_by_allocation = current_attempt_state()
    charged_by_label: dict[str, list[dict[str, Any]]] = {label: [] for label in labels}
    last_settlement_by_label: dict[str, TrialLedgerRow] = {}
    for allocation in replay.allocations:
        settlement = settlements_by_allocation.get(allocation.row_digest)
        if settlement is None:
            raise TrialEvaluationError("trial evaluator attempt remained active")
        label = allocation.payload["opaque_label"]
        charged_by_label[label].append(attempt_record(settlement))
        last_settlement_by_label[label] = settlement

    score_events = {
        row.payload["opaque_label"]: row
        for row in load_trial_event_ledger(event_path).rows
        if row.kind == "score_settled"
    }
    states = {
        label: {
            "packet": packets_by_label[label],
            "charged": charged_by_label[label],
            "settled_row": None,
        }
        for label in labels
    }
    for label, row in prior_by_label.items():
        if row["charged_attempts"] != charged_by_label[label]:
            raise TrialEvaluationError("persisted trial score attempt authority disagrees")
        event = score_events.get(label)
        if event is None:
            terminal = last_settlement_by_label.get(label)
            append_trial_score_settlement(
                event_path,
                expected_head_digest=head_digest(),
                opaque_label=label,
                score_row_content_digest=row["row_content_digest"],
                terminal_attempt_settlement_row_digest=(
                    terminal.row_digest if terminal is not None else None
                ),
            )
        elif event.payload["score_row_content_digest"] != row["row_content_digest"]:
            raise TrialEvaluationError("persisted trial score event disagrees")
        states[label]["settled_row"] = row

    pending = [label for label in labels if states[label]["settled_row"] is None]
    attempts_used = replay.charged_attempt_count
    if attempts_used > max_evaluator_attempts:
        raise TrialEvaluationError("persisted evaluator attempts exceed the trial budget")

    def persist_rows() -> None:
        materialize_run_score_ledger(
            [
                states[label]["settled_row"]
                for label in labels
                if states[label]["settled_row"] is not None
            ],
            score_ledger_path,
        )

    def deadline_expired() -> bool:
        if deadline_unix_ns is None:
            return False
        return wall_now_ns() >= deadline_unix_ns

    evaluator_workspace.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max_evaluator_concurrency) as pool:
        while pending and attempts_used < max_evaluator_attempts and not deadline_expired():
            batch_labels = pending[:max_evaluator_concurrency]
            del pending[: len(batch_labels)]
            available = max_evaluator_attempts - attempts_used
            if len(batch_labels) > available:
                pending[0:0] = batch_labels[available:]
                batch_labels = batch_labels[:available]
            submitted: list[tuple[str, TrialLedgerRow, Future[Any] | None]] = []
            for index, label in enumerate(batch_labels):
                packet = packets_by_label[label]
                replay = replay_trial_evaluator_attempts(event_path)
                local_attempt = 1 + sum(
                    row.payload["opaque_label"] == label for row in replay.allocations
                )
                global_attempt = replay.charged_attempt_count + 1
                started_at_unix_ns = wall_now_ns()
                if (
                    deadline_unix_ns is not None
                    and started_at_unix_ns >= deadline_unix_ns
                ):
                    pending[0:0] = batch_labels[index:]
                    break
                allocation = append_trial_evaluator_attempt_allocation(
                    event_path,
                    expected_head_digest=head_digest(),
                    opaque_label=label,
                    local_attempt=local_attempt,
                    global_attempt=global_attempt,
                    packet_digest=canonical_sha256(packet),
                    scorer_frozen_row_digest=scorer_event.row_digest,
                    started_at_unix_ns=started_at_unix_ns,
                )
                attempts_used += 1
                prompt_content = (
                    prompt
                    + "\n\nRubric:\n"
                    + rubric
                    + "\n\nEvaluator Packet:\n"
                    + _canonical_text(packet)
                )
                try:
                    invocation, preparation_error = provider_executor.prepare_invocation(
                        str(scorer["evaluator_provider"]),
                        ProviderParams(params=dict(scorer["evaluator_params"])),
                        {},
                        prompt_content=prompt_content,
                    )
                except Exception:
                    invocation, preparation_error = None, {"type": "exception"}
                if invocation is None or preparation_error is not None:
                    submitted.append((label, allocation, None))
                    continue
                workspace = evaluator_workspace / label
                workspace.mkdir(parents=True, exist_ok=True)
                submitted.append(
                    (label, allocation, pool.submit(provider_executor.execute, invocation, cwd=workspace))
                )

            for label, allocation, future in submitted:
                packet = packets_by_label[label]
                status = "preparation_failed"
                exit_code: int | None = None
                duration_ms: int | None = None
                stdout = b""
                stderr = b""
                parsed: Mapping[str, Any] | None = None
                if future is not None:
                    try:
                        result = future.result()
                    except Exception:
                        status = "provider_failed"
                    else:
                        exit_code = result.exit_code
                        duration_ms = result.duration_ms
                        stdout = result.stdout if isinstance(result.stdout, bytes) else b""
                        stderr = result.stderr if isinstance(result.stderr, bytes) else b""
                        status = "provider_failed"
                        if result.exit_code == 0 and result.error is None:
                            try:
                                parsed = parse_trial_evaluator_output(result.stdout, packet=packet)
                            except (EvaluatorOutputError, TrialPacketError):
                                status = "output_invalid"
                            else:
                                status = "scored"
                if duration_ms is None:
                    duration_ms = elapsed_since_allocation(allocation)
                attempt = {
                    "attempt": allocation.payload["local_attempt"],
                    "global_attempt": allocation.payload["global_attempt"],
                    "status": status,
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    "token_usage": {"variant": "UNKNOWN"},
                    "cost": {"variant": "UNKNOWN"},
                }
                charged = [*states[label]["charged"], attempt]
                score_row = None
                output_digest = None
                if parsed is not None:
                    score_row = _score_row(
                        trial_request_digest=trial_request_digest,
                        evaluation_digest=evaluation_digest,
                        evidence_frozen_digest=evidence_frozen_digest,
                        packet=packet,
                        scorer_identity_digest=scorer_identity,
                        parsed=parsed,
                        charged_attempts=charged,
                        failure=None,
                    )
                    states[label]["settled_row"] = score_row
                    persist_rows()
                    output_digest = canonical_sha256(parsed)
                settlement = append_trial_evaluator_attempt_settlement(
                    event_path,
                    expected_head_digest=head_digest(),
                    allocation_row_digest=allocation.row_digest,
                    opaque_label=label,
                    local_attempt=allocation.payload["local_attempt"],
                    global_attempt=allocation.payload["global_attempt"],
                    status=status,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    token_usage={"variant": "UNKNOWN"},
                    cost={"variant": "UNKNOWN"},
                    stdout_digest=_bytes_digest(stdout) if stdout else None,
                    stderr_digest=_bytes_digest(stderr) if stderr else None,
                    output_digest=output_digest,
                    score_row_content_digest=(
                        score_row["row_content_digest"] if score_row is not None else None
                    ),
                )
                states[label]["charged"] = charged
                last_settlement_by_label[label] = settlement
                if score_row is None:
                    pending.append(label)
                else:
                    append_trial_score_settlement(
                        event_path,
                        expected_head_digest=settlement.row_digest,
                        opaque_label=label,
                        score_row_content_digest=score_row["row_content_digest"],
                        terminal_attempt_settlement_row_digest=settlement.row_digest,
                    )

    exhausted_code = (
        "trial_evaluator_deadline_exhausted"
        if pending and deadline_expired()
        else "trial_evaluator_attempts_exhausted"
    )
    for label in pending:
        row = _score_row(
            trial_request_digest=trial_request_digest,
            evaluation_digest=evaluation_digest,
            evidence_frozen_digest=evidence_frozen_digest,
            packet=packets_by_label[label],
            scorer_identity_digest=scorer_identity,
            parsed=None,
            charged_attempts=states[label]["charged"],
            failure={"code": exhausted_code, "retryable": False},
        )
        states[label]["settled_row"] = row
        persist_rows()
        terminal = last_settlement_by_label.get(label)
        append_trial_score_settlement(
            event_path,
            expected_head_digest=head_digest(),
            opaque_label=label,
            score_row_content_digest=row["row_content_digest"],
            terminal_attempt_settlement_row_digest=(
                terminal.row_digest if terminal is not None else None
            ),
        )

    if any(states[label]["settled_row"] is None for label in labels):
        raise TrialEvaluationError("trial evaluator left an unsettled packet")
    loaded = load_trial_score_rows(
        score_ledger_path,
        validation_mode="complete",
    )
    event_ledger = load_trial_event_ledger(event_path)
    scores_events = [row for row in event_ledger.rows if row.kind == "scores_frozen"]
    if not scores_events:
        append_trial_scores_freeze(
            event_path,
            expected_head_digest=event_ledger.rows[-1].row_digest,
        )
    elif len(scores_events) != 1:
        raise TrialEvaluationError("trial score freeze is ambiguous")
    return TrialEvaluationResult(
        rows=tuple(loaded),
        scorer_identity_digest=scorer_identity,
        scorer_snapshot_path=scorer_snapshot_path,
        score_ledger_path=score_ledger_path,
    )


__all__ = [
    "TRIAL_EVALUATOR_INSTRUCTION",
    "TRIAL_EVALUATOR_INSTRUCTION_ID",
    "TRIAL_SCORE_ROW_SCHEMA",
    "TrialEvaluationError",
    "TrialEvaluationResult",
    "build_trial_scorer_config",
    "ensure_trial_evidence_freeze",
    "evaluate_trial_packets",
]
