"""Deterministic post-score unblinding, aggregation, and trial verdicts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256

from .contracts import SealedTrialOpaqueLabelMap, TrialCellKey


_POSITIVE_DISPOSITIONS = {"superior", "non_inferior_lower_cost"}
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class TrialVerdictError(ValueError):
    """The sealed join or verdict inputs are incomplete or inconsistent."""

    code = "trial_verdict_invalid"


@dataclass(frozen=True, slots=True)
class TrialVerdictArtifact:
    path: Path
    relpath: str
    record: dict[str, Any]


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise TrialVerdictError(f"{field} must be a canonical sha256 digest")
    return value


def _cell(value: object) -> TrialCellKey:
    if not isinstance(value, Mapping) or set(value) != {"arm_id", "rep"}:
        raise TrialVerdictError("trial verdict cell is invalid")
    try:
        return TrialCellKey(arm_id=value["arm_id"], rep=value["rep"])
    except (TypeError, ValueError) as exc:
        raise TrialVerdictError("trial verdict cell is invalid") from exc


def _finite_number(value: object, *, field: str, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrialVerdictError(f"{field} must be finite numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or (nonnegative and numeric < 0):
        raise TrialVerdictError(f"{field} must be finite numeric")
    return numeric


def _cost_fact(value: object) -> tuple[str, float | None, str | None]:
    if value == "UNKNOWN" or value == {"variant": "UNKNOWN"}:
        return "unknown", None, None
    if not isinstance(value, Mapping) or set(value) != {
        "variant",
        "amount",
        "currency",
    }:
        raise TrialVerdictError("trial cost fact is invalid")
    if value["variant"] != "KNOWN":
        raise TrialVerdictError("trial cost fact is invalid")
    amount = _finite_number(value["amount"], field="trial cost amount", nonnegative=True)
    currency = value["currency"]
    if not isinstance(currency, str) or not currency.strip():
        raise TrialVerdictError("trial cost currency is invalid")
    return "known", amount, currency


def _combined_cost(facts: Sequence[object]) -> tuple[str, float | None, str | None]:
    normalized = tuple(_cost_fact(fact) for fact in facts)
    if any(status == "unknown" for status, _amount, _currency in normalized):
        return "unknown", None, None
    currencies = {currency for _status, _amount, currency in normalized}
    if len(currencies) != 1:
        return "incomparable", None, None
    return (
        "known",
        sum(amount for _status, amount, _currency in normalized if amount is not None),
        next(iter(currencies)),
    )


def _combined_tokens(facts: Sequence[object]) -> dict[str, Any]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for value in facts:
        if value == "UNKNOWN" or value == {"variant": "UNKNOWN"}:
            return {"variant": "UNKNOWN"}
        if not isinstance(value, Mapping) or set(value) != {
            "variant",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }:
            raise TrialVerdictError("trial token fact is invalid")
        if value["variant"] != "KNOWN":
            raise TrialVerdictError("trial token fact is invalid")
        for field in totals:
            count = value[field]
            if type(count) is not int or count < 0:
                raise TrialVerdictError("trial token fact is invalid")
            totals[field] += count
    return {"variant": "KNOWN", **totals}


def aggregate_trial_verdict(
    *,
    authored_arm_order: tuple[str, ...],
    reps: int,
    cell_outcomes: Sequence[Mapping[str, Any]],
    score_rows: Sequence[Mapping[str, Any]],
    sealed_label_map: SealedTrialOpaqueLabelMap,
    success_rule: Mapping[str, Any],
) -> dict[str, Any]:
    """Join opaque scores exactly once and compute the closed trial verdict."""

    if (
        not isinstance(authored_arm_order, tuple)
        or len(authored_arm_order) < 2
        or any(not isinstance(arm_id, str) or not arm_id for arm_id in authored_arm_order)
        or len(set(authored_arm_order)) != len(authored_arm_order)
        or type(reps) is not int
        or reps < 1
    ):
        raise TrialVerdictError("trial verdict authored domain is invalid")
    if type(sealed_label_map) is not SealedTrialOpaqueLabelMap:
        raise TrialVerdictError("trial verdict requires an exact sealed label map")
    expected_cells = tuple(
        TrialCellKey(arm_id=arm_id, rep=rep)
        for arm_id in authored_arm_order
        for rep in range(1, reps + 1)
    )
    bindings = sealed_label_map.bindings
    if tuple(binding.cell for binding in bindings) != expected_cells:
        raise TrialVerdictError("trial sealed label domain disagrees with authored cells")

    required_outcome_keys = {
        "cell",
        "outcome",
        "child_attempts",
        "elapsed_ms",
        "token_usage",
        "cost",
    }
    outcome_by_cell: dict[TrialCellKey, Mapping[str, Any]] = {}
    for raw in cell_outcomes:
        if not isinstance(raw, Mapping) or set(raw) != required_outcome_keys:
            raise TrialVerdictError("trial verdict outcome is not closed")
        cell = _cell(raw["cell"])
        if cell in outcome_by_cell or cell not in expected_cells:
            raise TrialVerdictError("trial verdict outcome domain is ambiguous")
        if raw["outcome"] not in {"COMPLETED", "FAILED"}:
            raise TrialVerdictError("trial verdict outcome status is invalid")
        for field in ("child_attempts", "elapsed_ms"):
            if type(raw[field]) is not int or raw[field] < 0:
                raise TrialVerdictError("trial verdict accounting is invalid")
        _cost_fact(raw["cost"])
        _combined_tokens((raw["token_usage"],))
        outcome_by_cell[cell] = raw
    if tuple(outcome_by_cell) != expected_cells:
        raise TrialVerdictError("trial verdict outcomes do not cover the exact cell domain")

    label_to_cell = {binding.opaque_label: binding.cell for binding in bindings}
    score_by_cell: dict[TrialCellKey, Mapping[str, Any]] = {}
    for raw in score_rows:
        if not isinstance(raw, Mapping):
            raise TrialVerdictError("trial score join row is invalid")
        label = raw.get("evaluation_label")
        cell = label_to_cell.get(label)
        if cell is None or cell in score_by_cell:
            raise TrialVerdictError("trial score join is not an exact label bijection")
        status = raw.get("score_status")
        if status == "scored":
            score = _finite_number(raw.get("score"), field="trial score")
            if not 0 <= score <= 1:
                raise TrialVerdictError("trial score is outside [0,1]")
        elif status == "evaluation_failed":
            if raw.get("score") is not None:
                raise TrialVerdictError("failed trial score carries a numeric score")
        else:
            raise TrialVerdictError("trial score status is invalid")
        attempts = raw.get("charged_attempts")
        if not isinstance(attempts, list):
            raise TrialVerdictError("trial evaluator attempt accounting is invalid")
        for attempt in attempts:
            if (
                not isinstance(attempt, Mapping)
                or "duration_ms" not in attempt
                or type(attempt["duration_ms"]) is not int
                or attempt["duration_ms"] < 0
                or "token_usage" not in attempt
                or "cost" not in attempt
            ):
                raise TrialVerdictError(
                    "trial evaluator attempt accounting is invalid"
                )
            _combined_tokens((attempt["token_usage"],))
            _cost_fact(attempt["cost"])
        score_by_cell[cell] = raw
    if set(score_by_cell) != set(expected_cells):
        raise TrialVerdictError("trial scores do not cover the exact sealed label domain")

    per_repetition: list[dict[str, Any]] = []
    aggregate_scores: list[dict[str, Any]] = []
    for arm_id in authored_arm_order:
        arm_cells = tuple(cell for cell in expected_cells if cell.arm_id == arm_id)
        arm_scores: list[float] = []
        completed = 0
        failed = 0
        for cell in arm_cells:
            outcome = outcome_by_cell[cell]
            row = score_by_cell[cell]
            score = (
                float(row["score"])
                if outcome["outcome"] == "COMPLETED"
                and row["score_status"] == "scored"
                else None
            )
            if score is not None:
                arm_scores.append(score)
            if outcome["outcome"] == "COMPLETED":
                completed += 1
            else:
                failed += 1
            per_repetition.append(
                {
                    "arm_id": arm_id,
                    "rep": cell.rep,
                    "outcome": outcome["outcome"],
                    "score": score,
                }
            )
        aggregate_scores.append(
            {
                "arm_id": arm_id,
                "score": (
                    float(median(arm_scores))
                    if completed == reps and len(arm_scores) == reps
                    else None
                ),
                "completed_count": completed,
                "failed_count": failed,
            }
        )

    authored_index = {arm_id: index for index, arm_id in enumerate(authored_arm_order)}
    scored = [row for row in aggregate_scores if row["score"] is not None]
    scored.sort(key=lambda row: (-row["score"], authored_index[row["arm_id"]]))
    unscored = [row for row in aggregate_scores if row["score"] is None]
    ranking = [row["arm_id"] for row in scored + unscored]

    if not isinstance(success_rule, Mapping) or set(success_rule) != {
        "min_abs_improvement",
        "max_cost_ratio",
        "min_cost_reduction",
    }:
        raise TrialVerdictError("trial success rule is invalid")
    min_improvement = _finite_number(
        success_rule["min_abs_improvement"], field="minimum absolute improvement", nonnegative=True
    )
    max_cost_ratio = _finite_number(
        success_rule["max_cost_ratio"], field="maximum cost ratio", nonnegative=True
    )
    min_cost_reduction = _finite_number(
        success_rule["min_cost_reduction"], field="minimum cost reduction", nonnegative=True
    )
    if max_cost_ratio <= 0:
        raise TrialVerdictError("maximum cost ratio must be positive")

    disposition = "insufficient_scored_arms"
    selected_arm: str | None = None
    if len(scored) >= 2:
        leader, alternative = scored[:2]

        def arm_cost_facts(arm_id: str) -> tuple[object, ...]:
            result: list[object] = []
            for cell in expected_cells:
                if cell.arm_id != arm_id:
                    continue
                result.append(outcome_by_cell[cell]["cost"])
                result.extend(
                    attempt["cost"]
                    for attempt in score_by_cell[cell]["charged_attempts"]
                )
            return tuple(result)

        leader_cost = _combined_cost(arm_cost_facts(leader["arm_id"]))
        alternative_cost = _combined_cost(arm_cost_facts(alternative["arm_id"]))
        if "unknown" in {leader_cost[0], alternative_cost[0]}:
            disposition = "cost_unknown"
        elif (
            "incomparable" in {leader_cost[0], alternative_cost[0]}
            or leader_cost[2] != alternative_cost[2]
        ):
            disposition = "cost_incomparable"
        else:
            leader_amount = leader_cost[1]
            alternative_amount = alternative_cost[1]
            assert leader_amount is not None and alternative_amount is not None
            if alternative_amount == 0:
                ratio = 1.0 if leader_amount == 0 else math.inf
            else:
                ratio = leader_amount / alternative_amount
            score_delta = leader["score"] - alternative["score"]
            improvement_met = score_delta >= min_improvement or math.isclose(
                score_delta,
                min_improvement,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            if improvement_met and ratio <= max_cost_ratio:
                disposition = "superior"
                selected_arm = leader["arm_id"]
            else:
                reduction = (
                    (alternative_amount - leader_amount) / alternative_amount
                    if alternative_amount > 0
                    else -math.inf
                )
                if leader["score"] >= alternative["score"] and reduction >= min_cost_reduction:
                    disposition = "non_inferior_lower_cost"
                    selected_arm = leader["arm_id"]
                else:
                    disposition = "no_material_advantage"

    all_cost_facts: list[object] = []
    all_token_facts: list[object] = []
    evaluator_attempts = 0
    for cell in expected_cells:
        all_cost_facts.append(outcome_by_cell[cell]["cost"])
        all_token_facts.append(outcome_by_cell[cell]["token_usage"])
        attempts = score_by_cell[cell]["charged_attempts"]
        evaluator_attempts += len(attempts)
        all_cost_facts.extend(attempt["cost"] for attempt in attempts)
        all_token_facts.extend(attempt["token_usage"] for attempt in attempts)
    total_cost = _combined_cost(tuple(all_cost_facts))
    budget_cost = (
        {"variant": "KNOWN", "amount": total_cost[1], "currency": total_cost[2]}
        if total_cost[0] == "known"
        else {"variant": "UNKNOWN"}
    )
    budget = {
        "cell_count": len(expected_cells),
        "completed_count": sum(row["outcome"] == "COMPLETED" for row in cell_outcomes),
        "failed_count": sum(row["outcome"] == "FAILED" for row in cell_outcomes),
        "child_attempts": sum(row["child_attempts"] for row in cell_outcomes),
        "evaluator_attempts": evaluator_attempts,
        "elapsed_ms": sum(row["elapsed_ms"] for row in cell_outcomes)
        + sum(
            attempt["duration_ms"]
            for row in score_rows
            for attempt in row["charged_attempts"]
        ),
        "token_usage": _combined_tokens(tuple(all_token_facts)),
        "cost": budget_cost,
    }
    if (selected_arm is not None) != (disposition in _POSITIVE_DISPOSITIONS):
        raise TrialVerdictError("trial selected arm disagrees with disposition")
    return {
        "authored_arm_order": list(authored_arm_order),
        "per_repetition": per_repetition,
        "aggregate_scores": aggregate_scores,
        "ranking": ranking,
        "selected_arm": selected_arm,
        "success_rule_disposition": disposition,
        "budget_accounting": budget,
    }


def persist_trial_verdict_artifact(
    *,
    workspace: Path,
    trial_request_digest: str,
    evaluation_digest: str,
    evidence_frozen_digest: str,
    checks_frozen_digest: str,
    score_rows: Sequence[Mapping[str, Any]],
    scorer_identity_digest: str,
    sealed_label_map_digest: str,
    authored_outcomes: Sequence[Mapping[str, Any]],
    verdict: Mapping[str, Any],
) -> TrialVerdictArtifact:
    """Write one canonical content-addressed verdict artifact below the workspace."""

    root = Path(workspace)
    if not root.is_absolute() or root.resolve(strict=False) != root:
        raise TrialVerdictError("trial verdict workspace must be canonical and absolute")
    for field, value in (
        ("trial request digest", trial_request_digest),
        ("evaluation digest", evaluation_digest),
        ("evidence freeze digest", evidence_frozen_digest),
        ("checks-frozen digest", checks_frozen_digest),
        ("scorer identity digest", scorer_identity_digest),
        ("sealed label map digest", sealed_label_map_digest),
    ):
        _digest(value, field=field)
    if isinstance(score_rows, (str, bytes)) or not isinstance(score_rows, Sequence):
        raise TrialVerdictError("trial verdict score rows are invalid")
    if isinstance(authored_outcomes, (str, bytes)) or not isinstance(
        authored_outcomes, Sequence
    ):
        raise TrialVerdictError("trial verdict authored outcomes are invalid")
    if not isinstance(verdict, Mapping):
        raise TrialVerdictError("trial verdict value is invalid")
    try:
        normalized_scores = json.loads(canonical_json_bytes(list(score_rows)))
        normalized_outcomes = json.loads(canonical_json_bytes(list(authored_outcomes)))
        normalized_verdict = json.loads(canonical_json_bytes(dict(verdict)))
    except (TypeError, ValueError) as exc:
        raise TrialVerdictError("trial verdict artifact inputs are not canonical JSON") from exc
    score_digest = canonical_sha256(normalized_scores)
    verdict_digest = canonical_sha256(normalized_verdict)
    aggregation_digest = canonical_sha256(
        {
            "schema_version": "trial_aggregation.v1",
            "sealed_label_map_digest": sealed_label_map_digest,
            "authored_outcomes": normalized_outcomes,
            "score_digest": score_digest,
            "verdict_digest": verdict_digest,
        }
    )
    authority = {
        "schema_version": "trial.verdict_artifact.v1",
        "trial_request_digest": trial_request_digest,
        "evaluation_digest": evaluation_digest,
        "evidence_frozen_digest": evidence_frozen_digest,
        "checks_frozen_digest": checks_frozen_digest,
        "score_digest": score_digest,
        "scorer_identity_digest": scorer_identity_digest,
        "sealed_label_map_digest": sealed_label_map_digest,
        "aggregation_digest": aggregation_digest,
        "verdict_digest": verdict_digest,
        "authored_outcomes": normalized_outcomes,
        "verdict": normalized_verdict,
    }
    record = {**authority, "artifact_digest": canonical_sha256(authority)}
    relpath = (
        "artifacts/trials/"
        + trial_request_digest.removeprefix("sha256:")
        + "/verdict.json"
    )
    path = root / relpath
    payload = canonical_json_bytes(record) + b"\n"
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise TrialVerdictError("trial verdict artifact is unreadable") from exc
        if existing != payload:
            raise TrialVerdictError("persisted trial verdict artifact disagrees")
    else:
        durable_atomic_write(path, payload)
    return TrialVerdictArtifact(path=path, relpath=relpath, record=record)


__all__ = [
    "TrialVerdictArtifact",
    "TrialVerdictError",
    "aggregate_trial_verdict",
    "persist_trial_verdict_artifact",
]
