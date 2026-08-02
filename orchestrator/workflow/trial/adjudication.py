"""Production composition of frozen trial evidence into one typed verdict."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.type_descriptor import validate_transport_value

from .checks import TrialCheckResult, ensure_trial_checks_frozen
from .config import TrialRuntimeRequest
from .contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
    TrialOpaqueLabelBinding,
)
from .evaluation import (
    TrialEvaluationResult,
    build_trial_scorer_config,
    ensure_trial_evidence_freeze,
    evaluate_trial_packets,
)
from .ledger import (
    TrialEventLedger,
    TrialLedgerRow,
    append_trial_aggregation_freeze,
    append_trial_packets_freeze,
    append_trial_verdict_publication,
    append_trial_verdict_settlement,
    load_trial_event_ledger,
    validate_trial_event_ledger_authority,
)
from .packets import (
    build_trial_cell_evaluation_packet,
    validate_trial_cell_evaluation_packet,
)
from .runtime import TrialCellOutcome, TrialRuntimeExecution
from .verdict import (
    TrialVerdictArtifact,
    aggregate_trial_verdict,
    persist_trial_verdict_artifact,
)


class TrialAdjudicationError(ValueError):
    """The production trial evaluation composition is inconsistent."""

    code = "trial_adjudication_invalid"


@dataclass(frozen=True, slots=True)
class TrialEvaluationDependencies:
    """The complete effect seams used by production trial evaluation."""

    provider_registry: Any
    prompt_composer: Any
    provider_executor: Any
    check_runner: Callable[..., Any]

    def __post_init__(self) -> None:
        if not callable(self.check_runner):
            raise TypeError("trial check runner must be callable")
        for name, member in (
            ("provider registry", self.provider_registry),
            ("prompt composer", self.prompt_composer),
            ("provider executor", self.provider_executor),
        ):
            if member is None:
                raise TypeError(f"trial {name} is required")


@dataclass(frozen=True, slots=True)
class TrialAdjudicationExecution:
    """One fully validated typed trial value and its durable artifact."""

    authored_outcomes: tuple[dict[str, Any], ...]
    verdict: dict[str, Any]
    verdict_artifact: TrialVerdictArtifact


def _cell(value: Mapping[str, Any]) -> TrialCellKey:
    try:
        return TrialCellKey(arm_id=value["arm_id"], rep=value["rep"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TrialAdjudicationError("trial ledger cell is invalid") from exc


def _one_row(
    ledger: TrialEventLedger,
    kind: str,
    *,
    required: bool = True,
) -> TrialLedgerRow | None:
    rows = tuple(row for row in ledger.rows if row.kind == kind)
    if len(rows) > 1 or (required and len(rows) != 1):
        raise TrialAdjudicationError(
            f"trial {kind.replace('_', ' ')} authority is missing or ambiguous"
        )
    return rows[0] if rows else None


def _sealed_label_map(
    ledger: TrialEventLedger,
    request: TrialRuntimeRequest,
) -> SealedTrialOpaqueLabelMap:
    header = ledger.rows[0].payload
    try:
        bindings = tuple(
            TrialOpaqueLabelBinding(
                cell=_cell(value["cell"]),
                opaque_label=value["opaque_label"],
            )
            for value in header["sealed_opaque_label_map"]["bindings"]
        )
        sealed = SealedTrialOpaqueLabelMap(
            bindings=bindings,
            digest=header["sealed_opaque_label_map_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TrialAdjudicationError(
            "trial sealed opaque-label authority is invalid"
        ) from exc
    if tuple(binding.cell for binding in sealed.bindings) != request.cell_domain:
        raise TrialAdjudicationError(
            "trial sealed opaque-label authority disagrees with the request"
        )
    return sealed


def _rows_for_cell(
    ledger: TrialEventLedger,
    cell: TrialCellKey,
) -> tuple[TrialLedgerRow, ...]:
    return tuple(
        row
        for row in ledger.rows[1:]
        if isinstance(row.payload.get("cell"), Mapping)
        and row.payload["cell"] == cell.record
    )


def _validate_execution(
    request: TrialRuntimeRequest,
    execution: TrialRuntimeExecution,
) -> tuple[TrialEventLedger, SealedTrialOpaqueLabelMap]:
    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    if type(execution) is not TrialRuntimeExecution:
        raise TypeError("execution must be exact TrialRuntimeExecution")
    ledger = load_trial_event_ledger(execution.ledger_path)
    sealed = _sealed_label_map(ledger, request)
    validate_trial_event_ledger_authority(
        execution.ledger_path,
        request=request,
        sealed_opaque_labels=sealed,
    )
    if tuple(outcome.cell for outcome in execution.outcomes) != request.cell_domain:
        raise TrialAdjudicationError(
            "trial runtime outcomes disagree with the exact cell domain"
        )
    for outcome in execution.outcomes:
        rows = _rows_for_cell(ledger, outcome.cell)
        if outcome.status == "completed":
            prepared = tuple(row for row in rows if row.kind == "cell_prepared")
            settled = tuple(row for row in rows if row.kind == "cell_settled")
            committed = tuple(row for row in rows if row.kind == "cell_e1_committed")
            if len(prepared) != 1 or len(settled) != 1 or len(committed) != 1:
                raise TrialAdjudicationError(
                    "completed trial outcome lacks exact terminal authority"
                )
            if (
                outcome.envelope is None
                or outcome.artifacts is None
                or outcome.settled_result is None
                or canonical_sha256(dict(outcome.envelope))
                != prepared[0].payload["result_envelope_digest"]
                or canonical_sha256(dict(outcome.artifacts))
                != prepared[0].payload["artifact_projection_digest"]
                or outcome.settled_result.record
                != prepared[0].payload["settled_result"]
                or outcome.committed_row_digest
                != committed[0].payload["e1_committed_row_digest"]
            ):
                raise TrialAdjudicationError(
                    "completed trial outcome disagrees with durable authority"
                )
            expected_outcome_digest = canonical_sha256(
                {
                    "schema_version": "trial_cell_execution_outcome.v1",
                    "cell": outcome.cell.record,
                    "status": "completed",
                    "result_envelope_digest": canonical_sha256(
                        dict(outcome.envelope)
                    ),
                    "artifact_projection_digest": canonical_sha256(
                        dict(outcome.artifacts)
                    ),
                }
            )
            if settled[0].payload["outcome_digest"] != expected_outcome_digest:
                raise TrialAdjudicationError(
                    "completed trial outcome digest disagrees"
                )
        else:
            failed = tuple(row for row in rows if row.kind == "cell_failed")
            if (
                len(failed) != 1
                or outcome.failure is None
                or failed[0].payload["failure"] != outcome.failure.record
                or failed[0].payload["e1_authority_row_digest"]
                != outcome.e1_authority_row_digest
            ):
                raise TrialAdjudicationError(
                    "failed trial outcome disagrees with durable authority"
                )
    return ledger, sealed


def _check_result(row: TrialLedgerRow) -> TrialCheckResult:
    payload = row.payload
    value = payload["check_result"]
    result = TrialCheckResult(
        check_id=value["check_id"],
        authority=value["authority"],
        required=value["required"],
        status=value["status"],
        exit_code=value["exit_code"],
        duration_ms=value["duration_ms"],
        output_digest=value["output_digest"],
        output_bytes=value["output_bytes"],
        evidence_frozen_digest=payload["evidence_frozen_row_digest"],
        check_spec_digest=payload["check_spec_digest"],
        stdout_bytes=b"",
        stderr_bytes=b"",
        stdout_truncated=False,
        stderr_truncated=False,
    )
    if result.digest != payload["check_result_digest"]:
        raise TrialAdjudicationError("trial check-result authority disagrees")
    return result


def _checks_by_cell(
    ledger: TrialEventLedger,
    request: TrialRuntimeRequest,
) -> dict[TrialCellKey, tuple[TrialCheckResult, ...]]:
    results = {cell: [] for cell in request.cell_domain}
    for row in ledger.rows:
        if row.kind == "check_settled":
            results[_cell(row.payload["cell"])].append(_check_result(row))
    return {cell: tuple(values) for cell, values in results.items()}


def _packets(
    *,
    request: TrialRuntimeRequest,
    execution: TrialRuntimeExecution,
    sealed: SealedTrialOpaqueLabelMap,
    checks: Mapping[TrialCellKey, tuple[TrialCheckResult, ...]],
) -> tuple[dict[str, Any], ...]:
    bindings = {binding.cell: binding for binding in sealed.bindings}
    packets = tuple(
        build_trial_cell_evaluation_packet(
            request,
            outcome,
            opaque_label_binding=bindings[outcome.cell],
            trusted_check_results=checks[outcome.cell],
        )
        for outcome in execution.outcomes
    )
    for packet, outcome in zip(packets, execution.outcomes, strict=True):
        validate_trial_cell_evaluation_packet(
            packet,
            request=request,
            cell=outcome.cell,
            opaque_label_binding=bindings[outcome.cell],
        )
    return packets


def _ensure_packets_frozen(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    sealed: SealedTrialOpaqueLabelMap,
    packets: Sequence[Mapping[str, Any]],
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    existing = tuple(row for row in ledger.rows if row.kind == "packets_frozen")
    expected = [
        {
            "cell": cell.record,
            "opaque_label": binding.opaque_label,
            "packet_digest": canonical_sha256(packet),
        }
        for cell, binding, packet in zip(
            request.cell_domain,
            sealed.bindings,
            packets,
            strict=True,
        )
    ]
    if len(existing) == 1:
        if existing[0].payload["cell_packets"] != expected:
            raise TrialAdjudicationError(
                "trial packet freeze disagrees with rebuilt packet authority"
            )
        return existing[0]
    if existing:
        raise TrialAdjudicationError("trial packet freeze is ambiguous")
    return append_trial_packets_freeze(
        path,
        expected_head_digest=ledger.rows[-1].row_digest,
        cell_packets=expected,
    )


def _required_check_failures(
    values: Sequence[TrialCheckResult],
) -> tuple[TrialCheckResult, ...]:
    return tuple(
        value
        for value in values
        if value.required
        and not (value.status == "COMPLETED" and value.exit_code == 0)
    )


def _evaluator_failure(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("failure")
    if not isinstance(raw, Mapping):
        raise TrialAdjudicationError(
            "failed trial evaluation lacks explicit failure authority"
        )
    code = raw.get("code")
    retryable = raw.get("retryable")
    if not isinstance(code, str) or not code or type(retryable) is not bool:
        raise TrialAdjudicationError("trial evaluator failure is invalid")
    return {
        "code": code,
        "phase": "evaluation",
        "retryable": retryable,
        "secondary_causes": [],
    }


def _check_failure(values: Sequence[TrialCheckResult]) -> dict[str, Any]:
    failures = _required_check_failures(values)
    if not failures:
        raise TrialAdjudicationError("required check failure is missing")
    return {
        "code": "trial_required_check_failed",
        "phase": "checks",
        "retryable": False,
        "secondary_causes": [
            {
                "check_id": value.check_id,
                "authority": value.authority,
                "status": value.status,
                "exit_code": value.exit_code,
            }
            for value in failures
        ],
    }


def _merge_secondary(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = dict(primary)
    causes = list(result["secondary_causes"])
    if secondary is not None:
        causes.append(dict(secondary))
    result["secondary_causes"] = causes
    return result


def _partial_facts(
    *,
    outcome: TrialCellOutcome,
    check_results: Sequence[TrialCheckResult],
    packet_digest: str,
    score_row: Mapping[str, Any],
    scorer_identity_digest: str,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if outcome.status == "completed":
        assert outcome.envelope is not None and outcome.settled_result is not None
        facts.extend(
            (
                {
                    "variant": "WorkspaceDelta",
                    "workspace_delta": outcome.envelope["workspace_delta"],
                },
                {
                    "variant": "RunAccounting",
                    "accounting": outcome.envelope["accounting"],
                },
                {
                    "variant": "CheckResults",
                    "check_results": [value.record for value in check_results],
                },
            )
        )
    facts.extend(
        (
            {
                "variant": "EvaluationLabel",
                "evaluation_label": score_row["evaluation_label"],
            },
            {"variant": "PacketIdentity", "packet_identity": packet_digest},
            {
                "variant": "ScorerIdentity",
                "scorer_identity": scorer_identity_digest,
            },
        )
    )
    if score_row["score_status"] == "scored":
        facts.append({"variant": "Score", "score": score_row["score"]})
    if outcome.status == "completed":
        assert outcome.settled_result is not None
        facts.extend(
            (
                {
                    "variant": "ChildRunId",
                    "child_run_id": outcome.settled_result.child_run_id,
                },
                {
                    "variant": "AttemptOrdinal",
                    "attempt_ordinal": outcome.settled_result.attempt_ordinal,
                },
            )
        )
    return facts


def _authored_outcomes(
    *,
    execution: TrialRuntimeExecution,
    packets: Sequence[Mapping[str, Any]],
    checks: Mapping[TrialCellKey, tuple[TrialCheckResult, ...]],
    evaluation: TrialEvaluationResult,
) -> tuple[dict[str, Any], ...]:
    scores = {
        row["evaluation_label"]: row
        for row in evaluation.rows
    }
    result: list[dict[str, Any]] = []
    for outcome, packet in zip(execution.outcomes, packets, strict=True):
        packet_digest = canonical_sha256(packet)
        score = scores.get(packet["evaluation_id"])
        if score is None:
            raise TrialAdjudicationError(
                "trial score domain does not cover the exact packet domain"
            )
        cell_checks = checks[outcome.cell]
        check_failures = _required_check_failures(cell_checks)
        evaluator_failed = score["score_status"] != "scored"
        if outcome.status == "completed" and not check_failures and not evaluator_failed:
            assert outcome.envelope is not None and outcome.settled_result is not None
            result.append(
                {
                    "variant": "Completed",
                    "arm_id": outcome.cell.arm_id,
                    "rep": outcome.cell.rep,
                    "value": outcome.envelope["value"],
                    "evidence": {
                        "workspace_delta": outcome.envelope["workspace_delta"],
                        "accounting": outcome.envelope["accounting"],
                        "check_results": [value.record for value in cell_checks],
                        "evaluation_label": score["evaluation_label"],
                        "packet_identity": packet_digest,
                        "scorer_identity": evaluation.scorer_identity_digest,
                        "score": score["score"],
                        "child_run_id": outcome.settled_result.child_run_id,
                        "attempt_ordinal": outcome.settled_result.attempt_ordinal,
                    },
                }
            )
            continue
        secondary = _evaluator_failure(score) if evaluator_failed else None
        if outcome.status == "failed":
            assert outcome.failure is not None
            failure = _merge_secondary(outcome.failure.record, secondary)
        elif check_failures:
            failure = _merge_secondary(_check_failure(cell_checks), secondary)
        else:
            assert secondary is not None
            failure = secondary
        result.append(
            {
                "variant": "Failed",
                "arm_id": outcome.cell.arm_id,
                "rep": outcome.cell.rep,
                "failure": failure,
                "evidence": {
                    "facts": _partial_facts(
                        outcome=outcome,
                        check_results=cell_checks,
                        packet_digest=packet_digest,
                        score_row=score,
                        scorer_identity_digest=evaluation.scorer_identity_digest,
                    )
                },
            }
        )
    return tuple(result)


def _child_attempts(
    ledger: TrialEventLedger,
    cell: TrialCellKey,
) -> int:
    paths = {
        Path(row.payload["e1_ledger_path"])
        for row in _rows_for_cell(ledger, cell)
        if row.kind == "cell_allocated"
    }
    return sum(
        row.stage == "launched"
        for path in paths
        for row in load_attempt_ledger(path).rows
    )


def _aggregate_outcomes(
    *,
    ledger: TrialEventLedger,
    execution: TrialRuntimeExecution,
    authored: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    authored_by_cell = {
        TrialCellKey(arm_id=value["arm_id"], rep=value["rep"]): value
        for value in authored
    }
    rows: list[dict[str, Any]] = []
    for outcome in execution.outcomes:
        cell_rows = _rows_for_cell(ledger, outcome.cell)
        discarded = tuple(row for row in cell_rows if row.kind == "cell_discarded")
        discarded_elapsed = sum(row.payload["elapsed_ms"] for row in discarded)
        final = authored_by_cell[outcome.cell]
        if outcome.status == "completed":
            assert outcome.envelope is not None
            accounting = outcome.envelope["accounting"]
            elapsed_ms = discarded_elapsed + accounting["elapsed_ms"]
            token_usage: object = accounting["token_usage"]
            cost: object = accounting["cost"]
            if discarded:
                token_usage = {"variant": "UNKNOWN"}
                cost = {"variant": "UNKNOWN"}
        else:
            failed = tuple(row for row in cell_rows if row.kind == "cell_failed")
            if len(failed) != 1:
                raise TrialAdjudicationError(
                    "failed trial outcome lacks exact timing authority"
                )
            elapsed_ms = discarded_elapsed + failed[0].payload["elapsed_ms"]
            token_usage = {"variant": "UNKNOWN"}
            cost = {"variant": "UNKNOWN"}
        rows.append(
            {
                "cell": outcome.cell.record,
                "outcome": "COMPLETED" if final["variant"] == "Completed" else "FAILED",
                "child_attempts": _child_attempts(ledger, outcome.cell),
                "elapsed_ms": elapsed_ms,
                "token_usage": token_usage,
                "cost": cost,
            }
        )
    return tuple(rows)


def _ensure_aggregation(
    path: Path,
    *,
    sealed: SealedTrialOpaqueLabelMap,
    authored_outcomes: Sequence[Mapping[str, Any]],
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    scores = _one_row(ledger, "scores_frozen")
    assert scores is not None
    expected_outcomes_digest = canonical_sha256(list(authored_outcomes))
    existing = _one_row(ledger, "aggregation_frozen", required=False)
    if existing is not None:
        if (
            existing.payload["scores_frozen_row_digest"] != scores.row_digest
            or existing.payload["sealed_opaque_label_map_digest"] != sealed.digest
            or existing.payload["final_outcomes_digest"]
            != expected_outcomes_digest
        ):
            raise TrialAdjudicationError(
                "trial aggregation freeze disagrees with final outcomes"
            )
        return existing
    return append_trial_aggregation_freeze(
        path,
        expected_head_digest=ledger.rows[-1].row_digest,
        scores_frozen_row_digest=scores.row_digest,
        sealed_opaque_label_map_digest=sealed.digest,
        final_outcomes_digest=expected_outcomes_digest,
    )


def _ensure_verdict_settled(
    path: Path,
    *,
    aggregation: TrialLedgerRow,
    verdict: Mapping[str, Any],
) -> TrialLedgerRow:
    ledger = load_trial_event_ledger(path)
    digest = canonical_sha256(verdict)
    existing = _one_row(ledger, "verdict_settled", required=False)
    if existing is not None:
        if existing.payload != {
            "aggregation_frozen_row_digest": aggregation.row_digest,
            "verdict_digest": digest,
        }:
            raise TrialAdjudicationError(
                "trial verdict settlement disagrees with recomputed verdict"
            )
        return existing
    return append_trial_verdict_settlement(
        path,
        expected_head_digest=ledger.rows[-1].row_digest,
        aggregation_frozen_row_digest=aggregation.row_digest,
        verdict_digest=digest,
    )


def _path_validator(workspace: Path) -> Callable[[str, Mapping[str, Any]], str]:
    def validate(value: str, descriptor: Mapping[str, Any]) -> str:
        path = PurePosixPath(value)
        under = PurePosixPath(descriptor["under"])
        if (
            path.is_absolute()
            or path.as_posix() != value
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.parts[: len(under.parts)] != under.parts
        ):
            raise ValueError("trial verdict artifact path violates its root contract")
        target = workspace.joinpath(*path.parts)
        if descriptor["must_exist_target"] and not target.is_file():
            raise ValueError("trial verdict artifact path target does not exist")
        return value

    return validate


def evaluate_trial_execution(
    request: TrialRuntimeRequest,
    execution: TrialRuntimeExecution,
    *,
    parent_workspace: Path,
    dependencies: TrialEvaluationDependencies,
) -> TrialAdjudicationExecution:
    """Drive or exactly resume every Task-8 adjudication boundary."""

    if type(dependencies) is not TrialEvaluationDependencies:
        raise TypeError("dependencies must be exact TrialEvaluationDependencies")
    workspace = Path(parent_workspace)
    if not workspace.is_absolute() or workspace.resolve(strict=False) != workspace:
        raise ValueError("trial parent workspace must be canonical and absolute")
    ledger, sealed = _validate_execution(request, execution)
    evidence = ensure_trial_evidence_freeze(execution.ledger_path)
    ensure_trial_checks_frozen(
        execution.ledger_path,
        request=request,
        runner=dependencies.check_runner,
    )
    ledger = load_trial_event_ledger(execution.ledger_path)
    checks_frozen = _one_row(ledger, "checks_frozen")
    assert checks_frozen is not None
    checks = _checks_by_cell(ledger, request)
    packets = _packets(
        request=request,
        execution=execution,
        sealed=sealed,
        checks=checks,
    )
    _ensure_packets_frozen(
        execution.ledger_path,
        request=request,
        sealed=sealed,
        packets=packets,
    )
    ledger = load_trial_event_ledger(execution.ledger_path)
    deadline = ledger.rows[0].payload["runtime_budget_window"][
        "trial_deadline_unix_ns"
    ]
    budget = request.static_config.budget
    trial_root = execution.ledger_path.parent
    evaluated = evaluate_trial_packets(
        packets=packets,
        trial_request_digest=request.digest,
        evaluation_digest=request.evaluation_digest,
        evidence_frozen_digest=evidence.row_digest,
        scorer_config=build_trial_scorer_config(request),
        provider_registry=dependencies.provider_registry,
        prompt_composer=dependencies.prompt_composer,
        provider_executor=dependencies.provider_executor,
        scorer_root=trial_root / "scorer",
        score_ledger_path=trial_root / "scores.jsonl",
        trial_event_ledger_path=execution.ledger_path,
        evaluator_workspace=trial_root / "evaluator",
        max_evaluator_attempts=budget["max_evaluator_attempts"],
        max_evaluator_concurrency=budget["max_evaluator_concurrency"],
        deadline_unix_ns=deadline,
    )
    authored = _authored_outcomes(
        execution=execution,
        packets=packets,
        checks=checks,
        evaluation=evaluated,
    )
    ledger = load_trial_event_ledger(execution.ledger_path)
    aggregate_inputs = _aggregate_outcomes(
        ledger=ledger,
        execution=execution,
        authored=authored,
    )
    evaluation_config = request.static_config.evaluation
    verdict = aggregate_trial_verdict(
        authored_arm_order=tuple(arm.arm_id for arm in request.static_config.arms),
        reps=request.static_config.reps,
        cell_outcomes=aggregate_inputs,
        score_rows=evaluated.rows,
        sealed_label_map=sealed,
        success_rule={
            name: evaluation_config[name]
            for name in (
                "min_abs_improvement",
                "max_cost_ratio",
                "min_cost_reduction",
            )
        },
    )
    aggregation = _ensure_aggregation(
        execution.ledger_path,
        sealed=sealed,
        authored_outcomes=authored,
    )
    settled = _ensure_verdict_settled(
        execution.ledger_path,
        aggregation=aggregation,
        verdict=verdict,
    )
    artifact = persist_trial_verdict_artifact(
        workspace=workspace,
        trial_request_digest=request.digest,
        evaluation_digest=request.evaluation_digest,
        evidence_frozen_digest=evidence.row_digest,
        checks_frozen_digest=checks_frozen.row_digest,
        score_rows=evaluated.rows,
        scorer_identity_digest=evaluated.scorer_identity_digest,
        sealed_label_map_digest=sealed.digest,
        authored_outcomes=authored,
        verdict=verdict,
    )
    ledger = load_trial_event_ledger(execution.ledger_path)
    publication = _one_row(ledger, "verdict_published", required=False)
    expected_publication = {
        "verdict_settled_row_digest": settled.row_digest,
        "verdict_artifact_digest": artifact.record["artifact_digest"],
        "verdict_artifact_relpath": artifact.relpath,
    }
    if publication is None:
        append_trial_verdict_publication(
            execution.ledger_path,
            expected_head_digest=ledger.rows[-1].row_digest,
            verdict_settled_row_digest=settled.row_digest,
            verdict_artifact_digest=artifact.record["artifact_digest"],
            verdict_artifact_relpath=artifact.relpath,
        )
    elif publication.payload != expected_publication:
        raise TrialAdjudicationError(
            "trial verdict publication disagrees with durable artifact"
        )
    envelope = {
        "outcomes": list(authored),
        "verdict": verdict,
        "verdict_artifact": artifact.relpath,
    }
    validated = validate_transport_value(
        envelope,
        request.static_config.result_descriptor["envelope"],
        allow_nested_structures=True,
        path_validator=_path_validator(workspace),
    )
    return TrialAdjudicationExecution(
        authored_outcomes=tuple(validated["outcomes"]),
        verdict=validated["verdict"],
        verdict_artifact=artifact,
    )


__all__ = [
    "TrialAdjudicationError",
    "TrialAdjudicationExecution",
    "TrialEvaluationDependencies",
    "evaluate_trial_execution",
]
