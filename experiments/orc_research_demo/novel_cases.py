"""Deterministic artifact fixtures and behavioral checks for R1a qualification."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class ScenarioSpec:
    case_id: str
    scenario_id: str
    expected_selected: tuple[str, ...]
    expected_reused: tuple[str, ...]
    expected_invalidated: tuple[str, ...]
    expected_boundary: str | None
    expected_decision: str
    expected_status: str
    expected_scientific_acceptance: bool | None = None


SCENARIOS: dict[tuple[str, str], ScenarioSpec] = {
    (
        "review_completion",
        "selected_completion_preserves_unaffected",
    ): ScenarioSpec(
        "review_completion",
        "selected_completion_preserves_unaffected",
        ("revision", "approve", "selected_completion"),
        ("accepted_design",),
        ("changed_review",),
        "selection_decision",
        "APPROVE_SELECTED",
        "COMPLETED",
    ),
    (
        "conditional_judgment",
        "disagreement_triggers_bounded_reconsideration",
    ): ScenarioSpec(
        "conditional_judgment",
        "disagreement_triggers_bounded_reconsideration",
        ("review_a", "review_b", "reconsider", "accept"),
        (),
        (),
        "reconsideration_decision",
        "RECONSIDER_THEN_ACCEPT",
        "COMPLETED",
    ),
    (
        "scientific_transfer",
        "pilot_value_reconsideration",
    ): ScenarioSpec(
        "scientific_transfer",
        "pilot_value_reconsideration",
        ("diagnose", "pilot", "judge_value", "reconsider_method"),
        ("baseline_reference",),
        ("pilot_metric_gate",),
        "scientific_value_decision",
        "RECONSIDER_METHOD",
        "COMPLETED",
        False,
    ),
    (
        "scientific_transfer",
        "selective_reuse_after_correction",
    ): ScenarioSpec(
        "scientific_transfer",
        "selective_reuse_after_correction",
        ("diagnose", "correct", "reuse_unaffected", "continue"),
        ("pilot_reference", "accepted_seed_3"),
        ("affected_polish_rows",),
        "continuation_decision",
        "SELECTIVE_CONTINUE",
        "COMPLETED",
    ),
}

# Development-only approval and block branches of the same review requirement.
# The existing revision scenario above remains authoritative and unchanged.
SCENARIOS[("review_completion", "development_approval")] = ScenarioSpec(
    "review_completion", "development_approval",
    ("review", "approve", "selected_completion"), ("accepted_design",), (),
    "selection_decision", "APPROVE_SELECTED", "COMPLETED",
)
SCENARIOS[("review_completion", "development_block")] = ScenarioSpec(
    "review_completion", "development_block",
    ("review", "blocked"), ("accepted_design",),
    ("changed_review", "dependent_review"),
    "selection_decision", "BLOCKED", "BLOCKED",
)

# Task2 cases stay provisional until their assessment truth is frozen.  These
# specs constrain observable operation paths, reuse, invalidation, and the
# decision boundary without prescribing a workflow topology.
for _case_id, _family_specs in {
    "conditional_judgment": (
        ("disagreement-bounded-reconsideration",
         ("independent_assess", "compare_findings", "reconsider"),
         ("assessment_a", "assessment_b", "accepted_unaffected"),
         ("disputed_findings",), "reconsideration_decision",
         "RECONSIDER_THEN_ACCEPT", "COMPLETED", None),
        ("agreement-acceptance-without-extra-revision",
         ("independent_assess", "compare_findings", "accept"),
         ("assessment_a", "assessment_b", "accepted_findings"),
         ("pending_draft",), "acceptance_decision",
         "ACCEPT_AGREEMENT", "COMPLETED", None),
        ("revision-after-material-disagreement",
         ("independent_assess", "compare_findings", "revise"),
         ("accepted_unaffected", "shared_evidence"),
         ("disputed_findings", "dependent_conclusions"), "revision_decision",
         "REVISE_IMPLICATED_SCOPE", "COMPLETED", None),
    ),
    "scientific_transfer": (
        ("process-success-without-valid-scientific-acceptance",
         ("continue_per_item", "diagnose", "pilot", "judge_scientific_value"),
         ("baseline_reference", "pilot_execution_artifacts"),
         ("scientific_acceptance_claim",), "scientific_value_decision",
         "PROCESS_COMPLETE_SCIENTIFIC_INSUFFICIENT", "COMPLETED", False),
        ("pilot-evidence-calls-for-method-reconsideration",
         ("continue_per_item", "diagnose", "pilot", "judge_scientific_value",
          "expand_or_repair_or_rethink"),
         ("baseline_reference", "diagnostic_observations"),
         ("affected_comparison_evidence",), "scientific_value_decision",
         "RECONSIDER_METHOD", "COMPLETED", False),
        ("selective-reuse-after-relevant-correction",
         ("scope_policy_at_meaningful_boundaries",
          "selectively_reuse_after_relevant_correction",
          "preserve_unaffected_accepted_work", "continue_per_item",
          "judge_scientific_value"),
         ("pilot_reference", "accepted_seed_3"),
         ("affected_polish_rows",), "continuation_decision",
         "SELECTIVE_CONTINUE", "COMPLETED", True),
    ),
}.items():
    for (
        _scenario_id, _selected, _reused, _invalidated, _boundary, _decision,
        _status, _scientific_acceptance,
    ) in _family_specs:
        SCENARIOS[(_case_id, _scenario_id)] = ScenarioSpec(
            _case_id, _scenario_id, _selected, _reused, _invalidated,
            _boundary, _decision, _status, _scientific_acceptance,
        )
        SCENARIOS[{
            "conditional_judgment": "case-conditional-judgment-disagreement",
            "scientific_transfer": "case-multi-item-scientific-transfer",
        }[_case_id], _scenario_id] = SCENARIOS[(_case_id, _scenario_id)]


TASK2_FIXTURES: dict[tuple[str, str], dict[str, Any]] = {
    ("conditional_judgment", "disagreement-bounded-reconsideration"): {
        "inputs": {
            "finding_a": "calibration-adequate", "finding_b": "calibration-risk",
            "scope": "calibration", "confidence_a": "0.80",
            "confidence_b": "0.55", "accepted_findings": "geometry-accepted",
            "disputed_scope": "calibration",
        },
        "context": {"materiality_threshold": "0.50", "reconsideration_limit": "1"},
    },
    ("conditional_judgment", "agreement-acceptance-without-extra-revision"): {
        "inputs": {
            "finding_a": "geometry-adequate", "finding_b": "geometry-adequate",
            "scope": "geometry", "confidence_a": "0.80",
            "confidence_b": "0.78", "accepted_findings": "geometry-accepted",
            "disputed_scope": "none",
        },
        "context": {"materiality_threshold": "0.50", "reconsideration_limit": "1"},
    },
    ("conditional_judgment", "revision-after-material-disagreement"): {
        "inputs": {
            "finding_a": "background-adequate", "finding_b": "background-invalid",
            "scope": "background", "confidence_a": "0.95",
            "confidence_b": "0.10", "accepted_findings": "geometry-accepted",
            "disputed_scope": "background",
        },
        "context": {"materiality_threshold": "0.50", "reconsideration_limit": "1"},
    },
    ("scientific_transfer", "process-success-without-valid-scientific-acceptance"): {
        "inputs": {
            "item": "reconstruction-1", "remaining_backlog": "reconstruction-2",
            "item_status": "pending", "current_work": "pilot-output",
            "observed_issue": "metric-below-criterion",
            "prior_useful_evidence": "baseline-reference",
            "candidate_method": "current-method", "targeted_question": "quality",
            "item_data": "heldout-data", "metric": "0.40", "criterion": "0.80",
            "accepted_outputs": "baseline-reference",
            "unaffected_scope": "reconstruction-2",
        },
        "context": {
            "scientific_objective": "reconstruction-quality",
            "scientific_standard": "native-quality-criterion",
            "decision_boundary": "scientific_value_decision",
        },
    },
    ("scientific_transfer", "pilot-evidence-calls-for-method-reconsideration"): {
        "inputs": {
            "item": "reconstruction-1", "remaining_backlog": "reconstruction-2",
            "item_status": "pending", "current_work": "pilot-output",
            "observed_issue": "method-instability",
            "prior_useful_evidence": "baseline-reference",
            "candidate_method": "current-method", "targeted_question": "stability",
            "item_data": "heldout-data", "metric": "0.35", "criterion": "0.80",
            "accepted_outputs": "baseline-reference",
            "unaffected_scope": "reconstruction-2",
        },
        "context": {
            "scientific_objective": "reconstruction-quality",
            "scientific_standard": "native-quality-criterion",
            "decision_boundary": "scientific_value_decision",
        },
    },
    ("scientific_transfer", "selective-reuse-after-relevant-correction"): {
        "inputs": {
            "item": "seed-4", "remaining_backlog": "seed-5",
            "item_status": "corrected", "current_work": "corrected-polish",
            "observed_issue": "affected-polish-row",
            "prior_useful_evidence": "pilot-reference",
            "candidate_method": "corrected-method", "targeted_question": "polish",
            "item_data": "heldout-data", "metric": "0.90", "criterion": "0.80",
            "correction_signal": "relevant-method-correction",
            "affected_claims": "affected-polish-claim",
            "accepted_outputs": "accepted_seed_3",
            "unaffected_scope": "seed-3",
            "prior_accepted_outputs": "accepted_seed_3|pilot-reference",
            "corrected_outputs": "corrected-seed-4",
        },
        "context": {
            "item_boundaries": "seed-3,seed-4",
            "scientific_standard": "native-quality-criterion",
            "decision_boundary": "continuation_decision",
        },
    },
}

# Additional declared DEVELOPMENT values make preservation/content obligations
# inspectable. These are not native scientific results or assessment truth.
for (_family, _scenario), _fixture in TASK2_FIXTURES.items():
    _roots = _fixture["inputs"]
    if _family == "conditional_judgment":
        _fixture["context"]["reconsiderations_used"] = "0"
        _accepted_id = (
            "accepted_findings" if _roots["disputed_scope"] == "none"
            else "accepted_unaffected"
        )
        _roots["evidence_inventory"] = {
            _accepted_id: {
                "kind": "accepted", "scope": "geometry",
                "content": _roots["accepted_findings"],
            },
            "shared_evidence": {
                "kind": "shared", "scope": "all",
                "content": [_roots["finding_a"], _roots["finding_b"]],
            },
            "disputed_findings": {
                "kind": "disputed", "scope": _roots["disputed_scope"],
                "content": [_roots["finding_a"], _roots["finding_b"]],
            },
            "dependent_conclusions": {
                "kind": "dependent", "scope": _roots["disputed_scope"],
                "content": "conclusion pending resolution",
            },
            "pending_draft": {
                "kind": "draft", "scope": _roots["scope"],
                "content": "unaccepted draft",
            },
        }
    else:
        _roots["prior_evidence"] = {
            value.replace("-", "_"): {
                "content": value, "scope": _roots["unaffected_scope"],
                "admissible_for_current_comparison": False,
            }
            for value in _roots.get(
                "prior_accepted_outputs", _roots["prior_useful_evidence"]
            ).split("|")
        }
        _roots["accepted_evidence"] = {
            value.replace("-", "_"): {
                "content": value, "scope": _roots["unaffected_scope"],
                "admissible_for_current_comparison": False,
            }
            for value in _roots["accepted_outputs"].split("|")
        }
        _roots["current_claim"] = {
            "id": (
                "affected_polish_rows" if "correction_signal" in _roots
                else "affected_comparison_evidence"
                if _roots["observed_issue"] == "method-instability"
                else "scientific_acceptance_claim"
            ),
            "scope": _roots["item"],
            "content": _roots["current_work"],
        }
        _roots["observation"] = {
            "method": _roots["candidate_method"], "data": _roots["item_data"],
            "metric": _roots["metric"], "process_success": True,
            "stable": _roots["observed_issue"] != "method-instability",
        }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _value(inputs: Mapping[str, Any], context: Mapping[str, Any], name: str) -> str:
    value = inputs.get(name, context.get(name))
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty consumed value")
    return value


def _candidate_parts(payload: str) -> tuple[str, str, str]:
    parts = payload.split("|")
    if len(parts) == 4 and parts[0] == "candidate" and all(parts[1:]):
        return tuple(parts[1:])
    if (
        len(parts) == 6 and parts[0] == "revised" and all(parts[1:])
        and parts[4].startswith("resolved:")
    ):
        return tuple(parts[3:])
    raise ValueError("malformed candidate payload")


def _findings_parts(payload: str) -> tuple[str, str]:
    parts = payload.split("|")
    if (
        len(parts) != 3 or parts[0] != "findings"
        or parts[1] not in {"APPROVE", "REVISE", "BLOCK"}
        or len(parts[2]) != 64
    ):
        raise ValueError("malformed findings payload")
    return parts[1], parts[2]


def scripted_leaf(
    *, operation: str, inputs: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    """One local operation schema, used by subprocess leaves and the oracle.

    A revision resolves the changed component, preserving the accepted and
    dependent components. Completion assembles the dependent deliverable from
    the approved component values. Digests bind those actual values, not labels.
    """
    if operation in _TASK2_OPERATIONS - {"revise"} or (
        operation == "revise" and ("comparison" in inputs or "judgment" in inputs)
    ):
        return _task2_leaf(operation=operation, inputs=inputs, context=context)
    if operation == "gate":
        findings = _value(inputs, context, "findings_payload")
        status, candidate_digest = _findings_parts(findings)
        digest = _digest(findings)
        payload = f"gate|{digest}|{candidate_digest}"
        return {
            "artifact_kind": "review_gate", "operation": "gate",
            "findings_payload": findings, "findings_digest": digest,
            "review_status": status, "approved": status == "APPROVE",
            "revise_requested": status == "REVISE", "blocked": status == "BLOCK",
            "gate_payload": payload, "gate_digest": _digest(payload),
        }
    candidate = _value(inputs, context, "candidate_payload")
    accepted, changed, dependent = _candidate_parts(candidate)
    candidate_digest = _digest(candidate)
    items = {
        "accepted_item": accepted, "changed_item": changed,
        "dependent_item": dependent,
    }
    if operation == "candidate":
        if not candidate.startswith("candidate|"):
            raise ValueError("initial candidate cannot be a revision")
        return {
            "artifact_kind": "candidate", "operation": operation, **items,
            "payload": candidate, "payload_digest": candidate_digest,
        }
    if operation == "review":
        status = _value(inputs, context, "review_status")
        if status not in {"APPROVE", "REVISE", "BLOCK"}:
            raise ValueError("malformed review status")
        findings = f"findings|{status}|{candidate_digest}"
        return {
            "artifact_kind": "review_findings", "operation": operation,
            "candidate_payload": candidate, "candidate_digest": candidate_digest,
            "findings_payload": findings, "findings_digest": _digest(findings),
            "review_status": status, "approved": status == "APPROVE",
            "revise_requested": status == "REVISE", "blocked": status == "BLOCK",
        }
    findings = _value(inputs, context, "findings_payload")
    status, reviewed_digest = _findings_parts(findings)
    if reviewed_digest != candidate_digest:
        raise ValueError("findings do not describe the consumed candidate")
    findings_digest = _digest(findings)
    consumed = {
        "candidate_payload": candidate, "candidate_digest": candidate_digest,
        "findings_payload": findings, "findings_digest": findings_digest,
    }
    if operation == "revise":
        if status != "REVISE" or not candidate.startswith("candidate|"):
            raise ValueError("revision requires current revision findings")
        changed = f"resolved:{changed}"
        payload = (
            f"revised|{candidate_digest}|{findings_digest}|"
            f"{accepted}|{changed}|{dependent}"
        )
        return {
            "artifact_kind": "revised_candidate", "operation": operation,
            **items, **consumed, "changed_item": changed,
            "payload": payload, "payload_digest": _digest(payload),
            "source_candidate_digest": candidate_digest,
            "source_findings_digest": findings_digest,
        }
    if operation not in {"complete", "block"}:
        raise ValueError(f"unknown operation {operation}")
    if operation == "complete" and status != "APPROVE":
        raise ValueError("completion requires approval of its exact candidate")
    if operation == "block" and (status != "BLOCK" or candidate.startswith("revised|")):
        raise ValueError("block requires current blocked findings")
    revised = candidate.startswith("revised|")
    invalidated = (
        [changed, dependent] if operation == "block"
        else [changed.removeprefix("resolved:")] if revised else []
    )
    payload = (
        f"completion|{candidate_digest}|{findings_digest}|"
        f"{dependent}={accepted}+{changed}"
        if operation == "complete"
        else f"blocked|{candidate_digest}|{findings_digest}|{dependent}=withheld"
    )
    selected = (
        ["review", "blocked"] if operation == "block"
        else ["review", "revision", "approve", "selected_completion"] if revised
        else ["review", "approve", "selected_completion"]
    )
    return {
        "artifact_kind": "selected_completion" if operation == "complete" else "blocked_review",
        "operation": operation, **items, **consumed,
        "completion_payload": payload,
        "completion_digest": _digest(payload) if payload else "",
        "status": "COMPLETED" if operation == "complete" else "BLOCKED",
        "decision": "APPROVE_SELECTED" if operation == "complete" else "BLOCKED",
        "selected_steps": selected, "reused_items": [accepted],
        "invalidated_items": invalidated,
    }


@dataclass(frozen=True)
class OracleResult:
    ok: bool
    codes: tuple[str, ...]


def _same_value(actual: Any, expected: Any) -> bool:
    """JSON schema equality without bool/int coercion."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_value(a, b) for a, b in zip(actual, expected)
        )
    return actual == expected


def evaluate_behavior(
    *, spec: ScenarioSpec, fixture: Mapping[str, Any], authored: Mapping[str, Any]
) -> OracleResult:
    """Validate executed values, dependency closure and terminal outputs.

    Artifact order, command names and composition identity are immaterial.
    Only artifacts whose semantic work and already-resolved inputs validate
    can become producers. Cycles and missing work cannot bootstrap evidence.
    The controller supplies both the specification and exact input/context
    fixture. Development registries are data only, never evaluation authority.
    """
    if not isinstance(spec, ScenarioSpec):
        return OracleResult(False, ("unknown_scenario",))
    try:
        if not isinstance(fixture["inputs"], Mapping) or not isinstance(fixture["context"], Mapping):
            return OracleResult(False, ("malformed_fixture",))
        binding_failures = []
        if _task2_json(authored.get("inputs")) != _task2_json(fixture["inputs"]) or (
            _task2_json(authored.get("context")) != _task2_json(fixture["context"])
        ):
            binding_failures.append("fixture_input_context_mismatch")
        if spec.case_id in {"conditional_judgment", "case-conditional-judgment-disagreement"}:
            result = _evaluate_task2(spec, fixture, authored)
        elif spec.case_id in {"scientific_transfer", "case-multi-item-scientific-transfer"}:
            result = _evaluate_task2(spec, fixture, authored)
        elif spec.case_id == "review_completion":
            result = _evaluate_review(spec, authored)
        else:
            return OracleResult(False, ("unsupported_operation_family",))
        codes = tuple(dict.fromkeys((*binding_failures, *result.codes)))
        return OracleResult(not codes, codes)
    except (KeyError, TypeError, ValueError, AttributeError):
        return OracleResult(False, ("malformed_evidence",))


def _evaluate_review(spec: ScenarioSpec, authored: Mapping[str, Any]) -> OracleResult:
    if not isinstance(authored, Mapping):
        return OracleResult(False, ("malformed_evidence",))
    rows = authored.get("artifacts")
    if (
        not isinstance(rows, Sequence) or isinstance(rows, (str, bytes))
        or not rows or any(not isinstance(row, Mapping) for row in rows)
    ):
        return OracleResult(False, ("missing_or_malformed_artifacts",))
    inputs = authored["inputs"]
    outputs = authored["outputs"]
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        return OracleResult(False, ("malformed_evidence",))
    values = [_value(inputs, {}, name) for name in (
        "accepted_item", "changed_item", "dependent_item",
    )]
    expected_candidate = "candidate|" + "|".join(values)
    initial_status = _value(inputs, {}, "review_status")
    if initial_status not in {"APPROVE", "REVISE", "BLOCK"}:
        return OracleResult(False, ("malformed_evidence",))
    kinds = {
        "candidate": "candidate", "review_findings": "review",
        "review_gate": "gate", "revised_candidate": "revise",
        "selected_completion": "complete", "blocked_review": "block",
    }
    failures: list[str] = []
    pending = list(rows)
    candidates: dict[str, str] = {}
    findings: dict[str, str] = {}
    valid: list[Mapping[str, Any]] = []
    while pending:
        progressed = False
        for row in pending[:]:
            kind = row.get("artifact_kind")
            if not isinstance(kind, str) or kind not in kinds:
                return OracleResult(False, ("malformed_artifact_kind",))
            operation = kinds[kind]
            if row.get("operation") != operation:
                return OracleResult(False, ("malformed_operation",))
            if operation == "candidate":
                consumed = {"candidate_payload": row["payload"]}
                if row["payload"] != expected_candidate:
                    failures.append("stale_consumed_input")
            else:
                consumed = {
                    "candidate_payload": row.get("candidate_payload"),
                    "findings_payload": row.get("findings_payload"),
                    "review_status": row.get("review_status"),
                }
                if operation != "gate":
                    digest = row["candidate_digest"]
                    if not isinstance(digest, str):
                        raise ValueError("malformed candidate digest")
                    if candidates.get(digest) != consumed["candidate_payload"]:
                        continue
                if operation != "review":
                    digest = row["findings_digest"]
                    if not isinstance(digest, str):
                        raise ValueError("malformed findings digest")
                    if findings.get(digest) != consumed["findings_payload"]:
                        continue
            try:
                expected = scripted_leaf(operation=operation, inputs=consumed, context={})
            except ValueError:
                failures.append(f"invalid_work:{operation}")
                pending.remove(row)
                progressed = True
                continue
            if set(row) != set(expected) or any(
                not _same_value(row.get(key), value) for key, value in expected.items()
            ):
                failures.append(f"invalid_payload:{operation}")
            else:
                valid.append(row)
                if operation in {"candidate", "revise"}:
                    candidates[row["payload_digest"]] = row["payload"]
                if operation == "review":
                    findings[row["findings_digest"]] = row["findings_payload"]
            pending.remove(row)
            progressed = True
        if not progressed:
            failures.append("unresolved_consumed_input")
            break
    initial = [r for r in valid if r["operation"] == "candidate"]
    reviews = [r for r in valid if r["operation"] == "review"]
    revisions = [r for r in valid if r["operation"] == "revise"]
    terminals = [r for r in valid if r["operation"] in {"complete", "block"}]
    if len(initial) != 1:
        failures.append("candidate_count")
    initial_reviews = [r for r in reviews if r["candidate_payload"] == expected_candidate]
    if not any(r["review_status"] == initial_status for r in initial_reviews):
        failures.append("missing_required_review")
    if (initial_status == "REVISE" or any(r["review_status"] == "REVISE" for r in reviews)) and not revisions:
        failures.append("missing_required_revision")
    if initial_status != "REVISE" and revisions:
        failures.append("unexpected_revision")
    approved = [r for r in reviews if r["review_status"] == "APPROVE"]
    obligations = {
        "review": bool(reviews), "revision": bool(revisions), "revise": bool(revisions),
        "approve": bool(approved),
        "selected_completion": any(r["operation"] == "complete" for r in terminals),
        "blocked": any(r["operation"] == "block" for r in terminals),
    }
    for token in spec.expected_selected:
        if not obligations.get(token, False):
            failures.append(f"missing_required_operation:{token}")
    if (initial_status == "BLOCK" or any(r["review_status"] == "BLOCK" for r in reviews)) and any(
        r["operation"] == "complete" for r in rows
    ):
        failures.append("completion_after_block")
    if len(terminals) != 1:
        failures.append("terminal_control_mismatch")
    else:
        terminal = terminals[0]
        if terminal["status"] != spec.expected_status or terminal["decision"] != spec.expected_decision:
            failures.append("terminal_outcome_mismatch")
        if tuple(terminal["reused_items"]) != spec.expected_reused:
            failures.append("reuse_obligation_mismatch")
        if tuple(terminal["invalidated_items"]) != spec.expected_invalidated:
            failures.append("invalidation_obligation_mismatch")
        if revisions and terminal["candidate_digest"] not in {
            r["payload_digest"] for r in revisions
        }:
            failures.append("completion_did_not_consume_revision")
        # Reuse/invalidation is grounded in a validated value transformation:
        # accepted/dependent content is preserved, changed content is resolved,
        # and completion actually incorporates those resulting component values.
        if len(initial) == 1:
            expected_outputs = {
                key: terminal[key] for key in (
                    "status", "decision", "selected_steps", "reused_items",
                    "invalidated_items", "completion_payload", "completion_digest",
                    "findings_payload", "findings_digest",
                )
            }
            expected_outputs.update({
                "candidate_payload": initial[0]["payload"],
                "candidate_digest": initial[0]["payload_digest"],
                "reviewed_candidate_digest": terminal["candidate_digest"],
                "final_candidate_digest": terminal["candidate_digest"],
                "decision_boundary": spec.expected_boundary,
            })
            if any(not _same_value(outputs.get(k), v) for k, v in expected_outputs.items()):
                failures.append("workflow_outputs_mismatch")
    if authored.get("execution_status") != "completed":
        failures.append("execution_not_completed")
    return OracleResult(not failures, tuple(dict.fromkeys(failures)))


_TASK2_INPUTS = {
    "independent_assess": ({"roots", "finding", "confidence", "scope"},),
    "compare_findings": ({"roots", "assessment_a", "assessment_b"},),
    "judgment_gate": ({"roots", "comparison"},),
    "accept": ({"roots", "comparison"}, {"roots", "judgment"}),
    "reconsider": ({"roots", "comparison"}, {"roots", "judgment"}),
    "revise": ({"roots", "comparison"}, {"roots", "judgment"}),
    "diagnose": ({"roots"},),
    "pilot": ({"roots", "diagnosis"},),
    "evidence_gate": ({"roots", "evidence"},),
    "scope_policy_at_meaningful_boundaries": ({"roots", "diagnosis", "pilot"},),
    "selectively_reuse_after_relevant_correction": ({"roots", "policy", "pilot"},),
    "preserve_unaffected_accepted_work": ({"roots", "policy"},),
    "continue_per_item": (
        {"roots", "per_item_decision", "pilot"},
        {"roots", "per_item_decision", "pilot", "reuse", "preserved"},
    ),
    "item_gate": ({"roots", "item"},),
    "judge_scientific_value": ({"roots", "current_item_output", "current_comparison_evidence"},),
    "expand_or_repair_or_rethink": ({"roots", "diagnosis", "judgment"},),
    # An honest destructive operation for executable over-invalidation controls.
    # It is locally valid, but cannot satisfy these scenarios' preservation duty.
    "reset_all_work": ({"roots", "terminal"},),
}
_TASK2_OPERATIONS = set(_TASK2_INPUTS)


def _task2_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _task2_forbid_routing(value: Any) -> None:
    if isinstance(value, Mapping):
        if any(key in {
            "candidate_id", "global_role", "role_sequence", "scenario_id",
            "composition_id", "topology",
        } for key in value):
            raise ValueError("identity or global-role routing is forbidden")
        for nested in value.values():
            _task2_forbid_routing(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _task2_forbid_routing(nested)


def _task2_text(inputs: Mapping[str, Any], name: str) -> str:
    value = inputs.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty input")
    return value


def _task2_number(values: Mapping[str, Any], name: str) -> float:
    try:
        value = Decimal(_task2_text(values, name))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal number") from exc
    if not value.is_finite() or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between zero and one")
    return float(value)


def _task2_count(values: Mapping[str, Any], name: str) -> int:
    text = _task2_text(values, name)
    if not text.isdecimal():
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(text)


def _task2_artifact(
    operation: str,
    inputs: Mapping[str, Any],
    context: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "artifact_kind": "task2_operation", "operation": operation,
        "inputs": dict(inputs), "context": dict(context), "result": dict(result),
    }
    return {**body, "artifact_digest": _digest(_task2_json(body))}


def _task2_ref(
    inputs: Mapping[str, Any], name: str, operations: str | tuple[str, ...]
) -> Mapping[str, Any]:
    allowed = (operations,) if isinstance(operations, str) else operations
    value = inputs.get(name)
    if (
        not isinstance(value, Mapping)
        or value.get("artifact_kind") != "task2_operation"
        or value.get("operation") not in allowed
    ):
        raise ValueError(f"{name} must consume one of {allowed}")
    expected = _task2_artifact(
        value["operation"], value["inputs"], value["context"], value["result"]
    )
    if not _same_value(dict(value), expected):
        raise ValueError(f"{name} has a stale artifact digest")
    return value


def _task2_leaf(
    *, operation: str, inputs: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    """A single deterministic operation, never a program or scenario executor.

    Roots include declared observations, not results from a live native runner.
    Dependencies are complete consumed producer values; the evaluator separately
    requires that each producer actually occurred in the runtime evidence.
    """
    _task2_forbid_routing(inputs)
    _task2_forbid_routing(context)
    if set(inputs) not in _TASK2_INPUTS[operation]:
        raise ValueError(f"unexpected or missing consumed inputs for {operation}")
    roots = inputs["roots"]
    if not isinstance(roots, Mapping):
        raise ValueError("operation requires root inputs")
    for source in _task2_nested_refs(inputs):
        if _task2_json(source["inputs"].get("roots")) != _task2_json(roots) or (
            _task2_json(source["context"]) != _task2_json(context)
        ):
            raise ValueError("consumed producer belongs to different roots or context")

    def ref(name: str, allowed: str | tuple[str, ...]) -> Mapping[str, Any]:
        return _task2_ref(inputs, name, allowed)["result"]

    if operation == "independent_assess":
        finding = _task2_text(inputs, "finding")
        confidence = _task2_number(inputs, "confidence")
        scope = _task2_text(inputs, "scope")
        if scope != roots["scope"] or (finding, inputs["confidence"]) not in (
            (roots["finding_a"], roots["confidence_a"]),
            (roots["finding_b"], roots["confidence_b"]),
        ):
            raise ValueError("assessment is not grounded in a declared finding")
        result = {"finding": finding, "scope": scope, "confidence": confidence}
    elif operation == "compare_findings":
        a = ref("assessment_a", "independent_assess")
        b = ref("assessment_b", "independent_assess")
        for assessment, suffix in ((a, "a"), (b, "b")):
            if assessment != {
                "finding": roots[f"finding_{suffix}"], "scope": roots["scope"],
                "confidence": _task2_number(roots, f"confidence_{suffix}"),
            }:
                raise ValueError("comparison must consume both independent findings")
        _task2_number(context, "materiality_threshold")
        allowance = _task2_count(context, "reconsideration_limit")
        used = _task2_count(context, "reconsiderations_used")
        if used > allowance:
            raise ValueError("reconsideration count exceeds the configured bound")
        # Compare the consumed decimal inputs exactly; floats are display values.
        delta = abs(
            Fraction(inputs["assessment_a"]["inputs"]["confidence"])
            - Fraction(inputs["assessment_b"]["inputs"]["confidence"])
        )
        agreement = a["finding"] == b["finding"]
        material = not agreement and delta >= Fraction(context["materiality_threshold"])
        result = {
            "decision": "ACCEPT" if agreement else (
                "REVISE" if material or used >= allowance else "RECONSIDER"
            ),
            "agreement": agreement, "material": material, "confidence_delta": float(delta),
            "assessment_values": [dict(a), dict(b)],
            "accepted_findings": _task2_text(roots, "accepted_findings"),
            "disputed_scope": _task2_text(roots, "disputed_scope"),
            "reconsiderations_used": used, "reconsideration_limit": allowance,
        }
    elif operation == "judgment_gate":
        result = dict(ref("comparison", "compare_findings"))
    elif operation in {"accept", "reconsider", "revise"}:
        source = (
            ref("judgment", "judgment_gate") if "judgment" in inputs
            else ref("comparison", "compare_findings")
        )
        required = {"accept": "ACCEPT", "reconsider": "RECONSIDER", "revise": "REVISE"}
        if source["decision"] != required[operation]:
            raise ValueError("terminal work contradicts consumed judgment")
        inventory = roots["evidence_inventory"]
        accepted = {
            key: value for key, value in inventory.items() if value["kind"] == "accepted"
        }
        if not accepted or any(
            value["content"] != source["accepted_findings"] for value in accepted.values()
        ):
            raise ValueError("accepted content does not match comparison evidence")
        preserved = dict(accepted)
        if operation == "revise":
            preserved.update({
                key: value for key, value in inventory.items() if value["kind"] == "shared"
            })
        else:
            preserved = {
                "assessment_a": source["assessment_values"][0],
                "assessment_b": source["assessment_values"][1], **preserved,
            }
        invalid_kinds = {
            "accept": {"draft"}, "reconsider": {"disputed"},
            "revise": {"disputed", "dependent"},
        }[operation]
        invalidated = [
            key for key, value in inventory.items() if value["kind"] in invalid_kinds
        ]
        a, b = source["assessment_values"]
        used = source["reconsiderations_used"]
        if operation == "reconsider":
            if used >= source["reconsideration_limit"]:
                raise ValueError("reconsideration allowance exhausted")
            used += 1
        # Deterministic fixture resolution incorporates both assessments and
        # accepted content; revision also rebuilds dependent conclusions.
        resolution = {
            "scope": source["disputed_scope"],
            "accepted_basis": source["accepted_findings"],
            "findings_considered": [a["finding"], b["finding"]],
            "resolved_finding": max((a, b), key=lambda row: row["confidence"])["finding"],
            "confidence": (a["confidence"] + b["confidence"]) / 2,
            "resolution_kind": operation,
        }
        produced = {"resolved_findings": resolution}
        if operation == "revise":
            produced["dependent_conclusions"] = {
                "scope": resolution["scope"], "basis": resolution,
                "content": f"conclusion from {resolution['resolved_finding']}",
            }
        result = {
            "status": "COMPLETED",
            "decision": {
                "accept": "ACCEPT_AGREEMENT", "reconsider": "RECONSIDER_THEN_ACCEPT",
                "revise": "REVISE_IMPLICATED_SCOPE",
            }[operation],
            "decision_boundary": {
                "accept": "acceptance_decision", "reconsider": "reconsideration_decision",
                "revise": "revision_decision",
            }[operation],
            "reused_items": list(preserved), "invalidated_items": invalidated,
            "preserved_outputs": preserved, "produced_outputs": produced,
            "reconsiderations_used": used,
        }
    elif operation == "diagnose":
        issue = _task2_text(roots, "observed_issue")
        signal = roots.get("correction_signal")
        if signal not in {None, "relevant-method-correction"}:
            raise ValueError("unsupported declared correction signal")
        item_status = _task2_text(roots, "item_status")
        corrected = signal == "relevant-method-correction"
        if corrected != (item_status == "corrected"):
            raise ValueError("correction signal and item status disagree")
        result = {
            "issue": issue, "work": _task2_text(roots, "current_work"),
            "item": _task2_text(roots, "item"),
            "prior_useful": roots["prior_evidence"],
            "corrected": corrected,
            "rethink": issue == "method-instability",
            "per_item_decision": "continue" if item_status in {"pending", "corrected"} else "hold",
        }
    elif operation == "pilot":
        diagnosis = ref("diagnosis", "diagnose")
        observation = roots["observation"]
        method = _task2_text(roots, "candidate_method")
        data = _task2_text(roots, "item_data")
        if observation["method"] != method or observation["data"] != data:
            raise ValueError("observation is not bound to the executed method/data")
        if observation["metric"] != roots["metric"] or (
            type(observation["process_success"]) is not bool
            or type(observation["stable"]) is not bool
        ):
            raise ValueError("malformed declared observation")
        result = {
            "method": method, "data": data,
            "metric": _task2_number(observation, "metric"),
            "process_success": observation["process_success"],
            "stable": observation["stable"], "question": roots["targeted_question"],
            "item": diagnosis["item"], "work": diagnosis["work"],
            "corrected_output": roots.get("corrected_outputs"),
            "diagnostic_observations": dict(diagnosis),
        }
    elif operation == "evidence_gate":
        result = dict(ref("evidence", "pilot"))
    elif operation == "scope_policy_at_meaningful_boundaries":
        diagnosis = ref("diagnosis", "diagnose")
        pilot = ref("pilot", ("pilot", "evidence_gate"))
        if not diagnosis["corrected"] or not pilot["corrected_output"]:
            raise ValueError("scoped correction requires changed producer content")
        boundaries = _task2_text(context, "item_boundaries").split(",")
        affected = roots["current_claim"]
        unaffected = _task2_text(roots, "unaffected_scope")
        if affected["scope"] not in boundaries or unaffected not in boundaries:
            raise ValueError("correction is outside meaningful item boundaries")
        if affected["scope"] == unaffected:
            raise ValueError("affected and unaffected scope overlap")
        if pilot["corrected_output"] == affected["content"]:
            raise ValueError("correction did not change the content")
        result = {
            "correction_signal": roots["correction_signal"],
            "affected_claims": _task2_text(roots, "affected_claims"),
            "affected": dict(affected), "unaffected_scope": unaffected,
            "corrected": {
                **affected, "content": pilot["corrected_output"],
                "method": pilot["method"], "data": pilot["data"],
            },
            "eligible": {
                key: value for key, value in roots["prior_evidence"].items()
                if value["scope"] == unaffected
            },
        }
    elif operation == "selectively_reuse_after_relevant_correction":
        policy = ref("policy", "scope_policy_at_meaningful_boundaries")
        pilot = ref("pilot", ("pilot", "evidence_gate"))
        if policy["corrected"]["content"] != pilot["corrected_output"]:
            raise ValueError("reuse consumes a different corrected producer")
        if policy["eligible"] != {
            key: value for key, value in roots["prior_evidence"].items()
            if value["scope"] == policy["unaffected_scope"]
        }:
            raise ValueError("reuse eligibility is not grounded in prior values")
        result = {
            "preserved_outputs": dict(policy["eligible"]),
            "produced_outputs": {policy["affected"]["id"]: policy["corrected"]},
            "invalidated_items": [policy["affected"]["id"]],
            "reopened_claims": [policy["affected_claims"]],
        }
    elif operation == "preserve_unaffected_accepted_work":
        policy = ref("policy", "scope_policy_at_meaningful_boundaries")
        preserved = {
            key: value for key, value in roots["accepted_evidence"].items()
            if value["scope"] == policy["unaffected_scope"]
        }
        if any(policy["eligible"].get(key) != value for key, value in preserved.items()):
            raise ValueError("accepted content is absent from eligible prior evidence")
        result = {"preserved_outputs": preserved, "scope": policy["unaffected_scope"]}
    elif operation == "continue_per_item":
        diagnosis = ref("per_item_decision", "diagnose")
        pilot = ref("pilot", ("pilot", "evidence_gate"))
        if diagnosis["per_item_decision"] != "continue" or not pilot["process_success"]:
            raise ValueError("continuation is not authorized by item result")
        corrected = diagnosis["corrected"]
        if corrected != ("reuse" in inputs and "preserved" in inputs):
            raise ValueError("corrected continuation must consume reuse and preservation")
        if corrected:
            reuse = ref("reuse", "selectively_reuse_after_relevant_correction")
            preservation = ref("preserved", "preserve_unaffected_accepted_work")
            preserved = dict(reuse["preserved_outputs"])
            if any(preserved.get(k) != v for k, v in preservation["preserved_outputs"].items()):
                raise ValueError("continuation lost accepted producer values")
            # Preserve prior-useful first, then accepted values; no ID-specific branch.
            prior_id = roots["prior_useful_evidence"].replace("-", "_")
            preserved = {
                prior_id: preserved[prior_id],
                **{k: v for k, v in preserved.items() if k != prior_id},
            }
            produced = dict(reuse["produced_outputs"])
            if not any(v["content"] == pilot["corrected_output"] for v in produced.values()):
                raise ValueError("corrected producer is disconnected from continuation")
            invalidated = reuse["invalidated_items"]
        else:
            preserved = {
                **diagnosis["prior_useful"], "pilot_execution_artifacts": dict(pilot),
            }
            produced = {roots["item"]: {
                "content": pilot["work"], "method": pilot["method"], "data": pilot["data"],
            }}
            invalidated = []
        remaining = _task2_text(roots, "remaining_backlog").split(",")
        result = {
            "item": roots["item"], "item_status": roots["item_status"],
            "next_item": remaining[0], "remaining_backlog": remaining[1:],
            "corrected": corrected, "preserved_outputs": preserved,
            "produced_outputs": produced, "invalidated_items": invalidated,
            "pilot_value": dict(pilot),
        }
    elif operation == "item_gate":
        result = dict(ref("item", "continue_per_item"))
    elif operation == "judge_scientific_value":
        item = ref("current_item_output", ("continue_per_item", "item_gate"))
        pilot = ref("current_comparison_evidence", ("pilot", "evidence_gate"))
        if item["pilot_value"] != pilot:
            raise ValueError("judgment does not consume the continued item's evidence")
        _task2_number(roots, "criterion")
        accepted = (
            pilot["process_success"] and pilot["stable"]
            and Fraction(roots["observation"]["metric"]) >= Fraction(roots["criterion"])
        )
        rethink = not pilot["stable"]
        invalidated = list(item["invalidated_items"])
        if not accepted and roots["current_claim"]["id"] not in invalidated:
            invalidated.append(roots["current_claim"]["id"])
        boundary = "continuation_decision" if item["corrected"] else "scientific_value_decision"
        if context["decision_boundary"] != boundary:
            raise ValueError("judgment uses the wrong declared decision boundary")
        result = {
            "status": "COMPLETED",
            "process_status": "COMPLETED" if pilot["process_success"] else "FAILED",
            "scientific_standard": _task2_text(context, "scientific_standard"),
            "scientific_acceptance": accepted, "rethink": rethink,
            "decision": (
                "SELECTIVE_CONTINUE" if item["corrected"] and accepted
                else "SCIENTIFIC_INSUFFICIENT" if rethink
                else "PROCESS_COMPLETE_SCIENTIFIC_INSUFFICIENT" if not accepted
                else "SCIENTIFIC_ACCEPT"
            ),
            "decision_boundary": boundary,
            "reused_items": list(item["preserved_outputs"]),
            "invalidated_items": invalidated,
            "preserved_outputs": item["preserved_outputs"],
            "produced_outputs": item["produced_outputs"],
            "next_item": item["next_item"],
            "evidence_classification": {
                "prior_useful": roots["prior_evidence"],
                "current_comparison": dict(pilot),
                "objective": context.get("scientific_objective", roots["targeted_question"]),
            },
        }
    elif operation == "expand_or_repair_or_rethink":
        diagnosis = ref("diagnosis", "diagnose")
        judgment = ref("judgment", "judge_scientific_value")
        if not diagnosis["rethink"] or not judgment["rethink"]:
            raise ValueError("method reconsideration requires instability evidence")
        preserved = {
            **diagnosis["prior_useful"], "diagnostic_observations": dict(diagnosis),
        }
        result = {
            **judgment, "decision": "RECONSIDER_METHOD", "action": "rethink",
            "reused_items": list(preserved), "preserved_outputs": preserved,
            "produced_outputs": {
                "method_plan": {
                    "previous_method": roots["candidate_method"],
                    "required_scope": diagnosis["item"],
                    "excluded_evidence": judgment["invalidated_items"],
                    "content": {
                        "hold_current_comparison": True,
                        "investigate": diagnosis["issue"],
                        "question": roots["targeted_question"],
                    },
                },
            },
        }
    elif operation == "reset_all_work":
        terminal = ref("terminal", (
            "accept", "reconsider", "revise", "judge_scientific_value",
            "expand_or_repair_or_rethink",
        ))
        result = {
            **terminal, "reused_items": [], "preserved_outputs": {},
            "produced_outputs": {},
            "invalidated_items": list(dict.fromkeys(
                terminal["invalidated_items"] + terminal["reused_items"]
            )),
        }
    else:
        raise ValueError(f"unknown Task2 operation {operation}")
    return _task2_artifact(operation, inputs, context, result)


def _task2_output(terminal: Mapping[str, Any]) -> dict[str, Any]:
    return {**terminal["result"], "terminal_artifact_digest": terminal["artifact_digest"]}


def _evaluate_task2(
    spec: ScenarioSpec, fixture: Mapping[str, Any], authored: Mapping[str, Any]
) -> OracleResult:
    rows = authored.get("artifacts")
    if (
        not isinstance(rows, Sequence) or isinstance(rows, (str, bytes))
        or any(not isinstance(row, Mapping) for row in rows)
    ):
        return OracleResult(False, ("missing_or_malformed_artifacts",))
    failures: list[str] = []
    pending = list(rows)
    available: dict[str, Mapping[str, Any]] = {}
    while pending:
        progressed = False
        for row in pending[:]:
            try:
                operation = row["operation"]
                if operation not in _TASK2_OPERATIONS:
                    raise ValueError("unknown operation")
                _task2_forbid_routing(row)
                if _task2_json(row["inputs"]["roots"]) != _task2_json(fixture["inputs"]) or (
                    _task2_json(row["context"]) != _task2_json(fixture["context"])
                ):
                    raise ValueError("operation roots/context differ from actual root bindings")
                references = _task2_nested_refs(row["inputs"])
                if any(source["artifact_digest"] not in available for source in references):
                    continue
                if any(
                    not _same_value(dict(source), dict(available[source["artifact_digest"]]))
                    for source in references
                ):
                    raise ValueError("consumed dependency differs from actual producer")
                expected = scripted_leaf(
                    operation=operation, inputs=row["inputs"], context=row["context"]
                )
                if not _same_value(dict(row), expected):
                    raise ValueError("invalid operation value")
                available[row["artifact_digest"]] = row
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
                failures.append(f"invalid_payload:{row.get('operation', 'unknown')}")
            pending.remove(row)
            progressed = True
        if not progressed:
            failures.append("unresolved_consumed_input")
            break
    output = authored.get("outputs", {})
    terminal = available.get(output.get("terminal_artifact_digest"))
    if terminal is None:
        failures.append("terminal_control_mismatch")
    else:
        # Required work must lie in the output's consumed dependency closure.
        # Extra rows (including disconnected correct work) cannot qualify it.
        closure: dict[str, Mapping[str, Any]] = {}
        todo = [terminal]
        while todo:
            row = todo.pop()
            digest = row["artifact_digest"]
            if digest not in closure:
                closure[digest] = row
                todo.extend(_task2_nested_refs(row["inputs"]))
        operations = {row["operation"] for row in closure.values()}
        for operation in spec.expected_selected:
            if operation not in operations:
                failures.append(f"missing_required_operation:{operation}")
        result = terminal["result"]
        if result.get("decision") != spec.expected_decision:
            failures.append("terminal_outcome_mismatch")
        if result.get("status") != spec.expected_status:
            failures.append("terminal_status_mismatch")
        if result.get("decision_boundary") != spec.expected_boundary:
            failures.append("decision_boundary_mismatch")
        for field, expected, code in (
            ("reused_items", spec.expected_reused, "reuse_obligation_mismatch"),
            ("invalidated_items", spec.expected_invalidated, "invalidation_obligation_mismatch"),
        ):
            actual = result.get(field, [])
            if len(actual) != len(set(actual)) or set(actual) != set(expected):
                failures.append(code)
        if set(result.get("preserved_outputs", {})) != set(spec.expected_reused):
            failures.append("preservation_obligation_mismatch")
        if set(result.get("reused_items", [])) & set(result.get("invalidated_items", [])):
            failures.append("preservation_exclusion_mismatch")
        if spec.expected_scientific_acceptance is not None and result.get(
            "scientific_acceptance"
        ) is not spec.expected_scientific_acceptance:
            failures.append("scientific_acceptance_mismatch")
        if not _same_value(output, _task2_output(terminal)):
            failures.append("workflow_outputs_mismatch")
    if authored.get("execution_status") != "completed":
        failures.append("execution_not_completed")
    return OracleResult(not failures, tuple(dict.fromkeys(failures)))


def _task2_nested_refs(value: Any) -> list[Mapping[str, Any]]:
    refs: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if "artifact_digest" in value:
            refs.append(value)
        else:
            for nested in value.values():
                refs.extend(_task2_nested_refs(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            refs.extend(_task2_nested_refs(nested))
    return refs
