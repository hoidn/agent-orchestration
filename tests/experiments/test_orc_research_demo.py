"""Retained research algorithms and oracle-unit fixtures, without workflow execution.

The retired execution tests are preserved byte-exact in
``tests/fixtures/retired_execution/orc_research_demo.py.txt`` (SHA-256
2d5e9ae9282975575a5e7a8c5c6077a48e8c21149217d279d77e20f791c82a4d).
The execution_status field below is oracle input data, never execution evidence.
These fixed leaf compositions confer no workflow/runtime qualification.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from experiments.orc_research_demo.novel_cases import (
    evaluate_behavior,
    SCENARIOS,
    TASK2_FIXTURES,
    scripted_leaf,
)


def _review_fixture(inputs: dict[str, str], *, gated: bool = False) -> dict[str, object]:
    """Compose candidate -> review -> revision/reapproval -> completion unit inputs."""
    payload = "candidate|" + "|".join(inputs[key] for key in (
        "accepted_item", "changed_item", "dependent_item",
    ))
    candidate = scripted_leaf(operation="candidate", inputs={"candidate_payload": payload}, context={})
    review = scripted_leaf(operation="review", inputs={
        "candidate_payload": payload, "review_status": inputs["review_status"],
    }, context={})
    rows = [candidate, review]
    if gated:
        gate = scripted_leaf(operation="gate", inputs={
            "findings_payload": review["findings_payload"],
        }, context={})
        rows.append(gate)
    if inputs["review_status"] == "REVISE":
        revision = scripted_leaf(operation="revise", inputs={
            "candidate_payload": payload, "findings_payload": review["findings_payload"],
        }, context={})
        payload = revision["payload"]
        review = scripted_leaf(operation="review", inputs={
            "candidate_payload": payload, "review_status": "APPROVE",
        }, context={})
        rows.extend([revision, review])
    terminal = scripted_leaf(
        operation="block" if inputs["review_status"] == "BLOCK" else "complete",
        inputs={"candidate_payload": payload, "findings_payload": review["findings_payload"]},
        context={},
    )
    rows.append(terminal)
    outputs = {key: terminal[key] for key in (
        "status", "decision", "selected_steps", "reused_items", "invalidated_items",
        "completion_payload", "completion_digest", "findings_payload", "findings_digest",
    )}
    outputs.update(
        candidate_payload=candidate["payload"], candidate_digest=candidate["payload_digest"],
        reviewed_candidate_digest=review["candidate_digest"],
        final_candidate_digest=terminal["candidate_digest"], decision_boundary="selection_decision",
    )
    return {"execution_status": "completed", "inputs": deepcopy(inputs), "context": {},
            "artifacts": rows, "outputs": outputs}


def _judgment_fixture(fixture: dict[str, object], *, gated: bool = False) -> dict[str, object]:
    """Compose two independent assessments -> comparison -> optional gate -> resolution."""
    roots, context = fixture["inputs"], fixture["context"]
    if gated:
        b = scripted_leaf(operation="independent_assess", inputs={
            "roots": roots, "finding": roots["finding_b"],
            "confidence": roots["confidence_b"], "scope": roots["scope"],
        }, context=context)
    a = scripted_leaf(operation="independent_assess", inputs={
        "roots": roots, "finding": roots["finding_a"],
        "confidence": roots["confidence_a"], "scope": roots["scope"],
    }, context=context)
    if not gated:
        b = scripted_leaf(operation="independent_assess", inputs={
            "roots": roots, "finding": roots["finding_b"],
            "confidence": roots["confidence_b"], "scope": roots["scope"],
        }, context=context)
    comparison = scripted_leaf(operation="compare_findings", inputs={
        "roots": roots, "assessment_a": a, "assessment_b": b,
    }, context=context)
    rows = [b, a, comparison] if gated else [a, b, comparison]
    source, source_name = comparison, "comparison"
    if gated:
        source = scripted_leaf(operation="judgment_gate", inputs={
            "roots": roots, "comparison": comparison,
        }, context=context)
        rows.append(source)
        source_name = "judgment"
    terminal = scripted_leaf(
        operation={"ACCEPT": "accept", "RECONSIDER": "reconsider", "REVISE": "revise"}[
            comparison["result"]["decision"]
        ], inputs={"roots": roots, source_name: source}, context=context,
    )
    return {**deepcopy(fixture), "execution_status": "completed", "artifacts": rows + [terminal],
            "outputs": {**terminal["result"], "terminal_artifact_digest": terminal["artifact_digest"]}}


def _scientific_fixture(fixture: dict[str, object], *, gated: bool = False) -> dict[str, object]:
    """Compose diagnosis/pilot -> optional correction/preservation -> item -> judgment."""
    roots, context = fixture["inputs"], fixture["context"]
    diagnosis = scripted_leaf(operation="diagnose", inputs={"roots": roots}, context=context)
    pilot = scripted_leaf(operation="pilot", inputs={"roots": roots, "diagnosis": diagnosis}, context=context)
    rows = [diagnosis, pilot]
    evidence = pilot
    if gated:
        evidence = scripted_leaf(operation="evidence_gate", inputs={
            "roots": roots, "evidence": pilot,
        }, context=context)
        rows.append(evidence)
    correction = {}
    if diagnosis["result"]["corrected"]:
        policy = scripted_leaf(operation="scope_policy_at_meaningful_boundaries", inputs={
            "roots": roots, "diagnosis": diagnosis, "pilot": evidence,
        }, context=context)
        if gated:
            preserved = scripted_leaf(operation="preserve_unaffected_accepted_work", inputs={
                "roots": roots, "policy": policy,
            }, context=context)
        reuse = scripted_leaf(operation="selectively_reuse_after_relevant_correction", inputs={
            "roots": roots, "policy": policy, "pilot": evidence,
        }, context=context)
        if not gated:
            preserved = scripted_leaf(operation="preserve_unaffected_accepted_work", inputs={
                "roots": roots, "policy": policy,
            }, context=context)
        rows.extend([policy, preserved, reuse] if gated else [policy, reuse, preserved])
        correction = {"reuse": reuse, "preserved": preserved}
    item = scripted_leaf(operation="continue_per_item", inputs={
        "roots": roots, "per_item_decision": diagnosis, "pilot": evidence, **correction,
    }, context=context)
    rows.append(item)
    if gated:
        item = scripted_leaf(operation="item_gate", inputs={"roots": roots, "item": item}, context=context)
        rows.append(item)
    terminal = scripted_leaf(operation="judge_scientific_value", inputs={
        "roots": roots, "current_item_output": item, "current_comparison_evidence": evidence,
    }, context=context)
    rows.append(terminal)
    if diagnosis["result"]["rethink"]:
        terminal = scripted_leaf(operation="expand_or_repair_or_rethink", inputs={
            "roots": roots, "diagnosis": diagnosis, "judgment": terminal,
        }, context=context)
        rows.append(terminal)
    return {**deepcopy(fixture), "execution_status": "completed", "artifacts": rows,
            "outputs": {**terminal["result"], "terminal_artifact_digest": terminal["artifact_digest"]}}


def _qualify(authored: dict[str, object], review_status: str):
    scenario = {
        "APPROVE": "development_approval",
        "REVISE": "selected_completion_preserves_unaffected",
        "BLOCK": "development_block",
    }[review_status]
    return evaluate_behavior(
        spec=SCENARIOS[("review_completion", scenario)],
        fixture={"inputs": _development_inputs(review_status), "context": {}},
        authored=authored,
    )


def _development_inputs(review_status: str) -> dict[str, str]:
    return {
        "review_status": review_status,
        "accepted_item": "accepted_design",
        "changed_item": "changed_review",
        "dependent_item": "dependent_review",
    }



def test_review_oracle_fixtures_preserve_selected_work_and_reject_controls() -> None:
    for review_status in ("APPROVE", "REVISE", "BLOCK"):
        inputs = _development_inputs(review_status)
        positives = [_review_fixture(inputs, gated=gated) for gated in (False, True)]
        for authored in positives:
            result = _qualify(authored, review_status)
            assert result.ok, result.codes
        assert not any(row["operation"] == "gate" for row in positives[0]["artifacts"])
        assert any(row["operation"] == "gate" for row in positives[1]["artifacts"])
        assert positives[0]["outputs"] == positives[1]["outputs"]
        final = positives[0]["outputs"]
        assert final["candidate_payload"] == "candidate|accepted_design|changed_review|dependent_review"
        if review_status == "REVISE":
            [revision] = [row for row in positives[0]["artifacts"] if row["operation"] == "revise"]
            assert revision["accepted_item"] == "accepted_design"
            assert revision["changed_item"] == "resolved:changed_review"
            assert revision["dependent_item"] == "dependent_review"
            assert final["completion_payload"].endswith(
                "|dependent_review=accepted_design+resolved:changed_review"
            )
            assert final["reused_items"] == ["accepted_design"]
            assert final["invalidated_items"] == ["changed_review"]
        elif review_status == "BLOCK":
            assert final["completion_payload"].endswith("|dependent_review=withheld")
            assert final["decision"] == "BLOCKED"
            assert final["invalidated_items"] == ["changed_review", "dependent_review"]
        else:
            assert final["completion_payload"].endswith(
                "|dependent_review=accepted_design+changed_review"
            )

        # Fresh-input mutations isolate skipped work from stale-input diagnostics.
        broken = deepcopy(positives[0])
        if review_status == "APPROVE":
            broken["artifacts"][-1].update(
                completion_payload="skipped", completion_digest=hashlib.sha256(b"skipped").hexdigest(),
            )
        elif review_status == "REVISE":
            broken = _review_fixture({**inputs, "review_status": "APPROVE"})
            broken["inputs"] = inputs
            broken["artifacts"].insert(1, positives[0]["artifacts"][1])
        else:
            broken = _review_fixture({**inputs, "review_status": "APPROVE"})
            broken["inputs"] = inputs
            blocked = positives[0]["artifacts"][1]
            broken["artifacts"][1] = blocked
            for key in ("findings_payload", "findings_digest"):
                broken["artifacts"][-1][key] = blocked[key]
                broken["outputs"][key] = blocked[key]
        assert broken["execution_status"] == "completed"
        assert broken["outputs"]["candidate_payload"] == (
            "candidate|accepted_design|changed_review|dependent_review"
        )
        result = _qualify(broken, review_status)
        assert not result.ok
        assert "stale_consumed_input" not in result.codes
        assert {
            "APPROVE": "invalid_payload:complete", "REVISE": "missing_required_revision",
            "BLOCK": "completion_after_block",
        }[review_status] in result.codes
        if review_status == "REVISE":
            assert "unresolved_consumed_input" not in result.codes

    skipped_review = _review_fixture(_development_inputs("APPROVE"))
    skipped_review["artifacts"] = [row for row in skipped_review["artifacts"] if row["operation"] != "review"]
    result = _qualify(skipped_review, "APPROVE")
    assert not result.ok
    assert "missing_required_review" in result.codes
    assert "stale_consumed_input" not in result.codes

    inputs = _development_inputs("REVISE")
    stale = _review_fixture({**inputs, "accepted_item": "stale_accepted_design"})
    stale["inputs"] = inputs
    result = _qualify(stale, "REVISE")
    assert not result.ok
    assert "stale_consumed_input" in result.codes
    assert any(row["operation"] == "revise" for row in stale["artifacts"])
    assert any(row["operation"] == "complete" for row in stale["artifacts"])


def test_behavior_oracle_rejects_missing_stale_and_skipped_evidence() -> None:
    inputs = _development_inputs("REVISE")
    authored = _review_fixture(inputs, gated=True)
    assert _qualify(authored, "REVISE").ok
    rows = authored["artifacts"]
    [revision] = [row for row in rows if row["operation"] == "revise"]
    [approval] = [
        row for row in rows
        if row["operation"] == "review" and row["review_status"] == "APPROVE"
    ]
    [completion] = [row for row in rows if row["operation"] == "complete"]
    # Regression for the observed failure: an APPROVE re-review of the revised
    # payload is the required completion input, not the original REVISE findings.
    assert scripted_leaf(
        operation="complete",
        inputs={
            "candidate_payload": revision["payload"],
            "findings_payload": approval["findings_payload"],
        },
        context={},
    ) == completion

    # Oracle acceptance is independent of artifact enumeration and composition names.
    permuted = deepcopy(authored)
    permuted["artifacts"].reverse()
    permuted["outputs"]["composition_id"] = "unseen-name"
    assert _qualify(permuted, "REVISE").ok

    # Self-consistent hashes of unrelated findings, arbitrary revisions and
    # skipped deliverables must not substitute for the declared work.
    mutations = (
        ("review", "findings_payload", "findings_digest", "findings|REVISE|" + "0" * 64),
        ("revise", "payload", "payload_digest", revision["payload"].rsplit("|", 1)[0] + "|arbitrary"),
        ("complete", "completion_payload", "completion_digest", "skipped"),
    )
    for operation, payload_key, digest_key, payload in mutations:
        tampered = deepcopy(authored)
        row = next(r for r in tampered["artifacts"] if r["operation"] == operation)
        row[payload_key] = payload
        row[digest_key] = hashlib.sha256(payload.encode()).hexdigest()
        result = _qualify(tampered, "REVISE")
        assert not result.ok
        assert f"invalid_payload:{operation}" in result.codes

    for operation in ("review", "revise", "complete"):
        missing = deepcopy(authored)
        missing["artifacts"] = [r for r in rows if r["operation"] != operation]
        assert not _qualify(missing, "REVISE").ok

    for key, replacement in (
        ("status", "BLOCKED"), ("decision", "BLOCKED"),
        ("reused_items", []), ("invalidated_items", []),
        ("selected_steps", []), ("decision_boundary", "unrelated"),
        ("candidate_payload", "stale"), ("candidate_digest", "0" * 64),
        ("reviewed_candidate_digest", "0" * 64),
        ("final_candidate_digest", "0" * 64),
        ("findings_payload", "unrelated"), ("findings_digest", "0" * 64),
        ("completion_payload", "skipped"), ("completion_digest", "0" * 64),
    ):
        bad_output = deepcopy(authored)
        bad_output["outputs"][key] = replacement
        assert "workflow_outputs_mismatch" in _qualify(bad_output, "REVISE").codes
    # ScenarioSpec obligations apply even to a completely self-consistent packet
    # whose current input values differ from the required scenario resources.
    different_inputs = {
        **inputs, "accepted_item": "other_accepted", "changed_item": "other_changed",
    }
    different = _review_fixture(different_inputs)
    result = _qualify(different, "REVISE")
    assert different["execution_status"] == "completed"
    assert "stale_consumed_input" not in result.codes
    assert "reuse_obligation_mismatch" in result.codes
    assert "invalidation_obligation_mismatch" in result.codes

    assert not _qualify({**authored, "execution_status": "failed"}, "REVISE").ok

    changed_inputs = {**inputs, "accepted_item": "other_accepted"}
    assert "stale_consumed_input" in _qualify(
        {**authored, "inputs": changed_inputs}, "REVISE"
    ).codes
    for malformed in ({}, {"artifacts": []}, {"artifacts": [None]}, None):
        assert not _qualify(malformed, "REVISE").ok
    for row in rows:
        for key in row:
            for malformed_value in (None, [], {}, 7, False):
                if row[key] == malformed_value and type(row[key]) is type(malformed_value):
                    continue
                malformed = deepcopy(authored)
                index = rows.index(row)
                malformed["artifacts"][index][key] = malformed_value
                result = _qualify(malformed, "REVISE")
                assert not result.ok, (key, malformed_value)
    assert not _qualify(
        {**authored, "artifacts": [*rows, {"artifact_kind": []}]}, "REVISE"
    ).ok



def _assert_task2_controls(family: str, scenario_id: str, correct: dict[str, object]) -> None:
    fixture = TASK2_FIXTURES[(family, scenario_id)]
    spec = SCENARIOS[(family, scenario_id)]
    rows = correct["artifacts"]
    # A valid comparison/pilot is an intentionally incomplete terminal closure.
    operation = "compare_findings" if family == "conditional_judgment" else "pilot"
    terminal = next(row for row in rows if row["operation"] == operation)
    missing = {**deepcopy(correct), "artifacts": [row for row in rows if row["operation"] in {
        "independent_assess", "compare_findings", "diagnose", "pilot",
    }], "outputs": {**terminal["result"], "terminal_artifact_digest": terminal["artifact_digest"]}}
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=missing)
    assert missing["outputs"]
    assert not result.ok
    assert any(code.startswith("missing_required_operation:") for code in result.codes)
    assert not any(code.startswith("invalid_payload:") for code in result.codes)
    assert "terminal_control_mismatch" not in result.codes
    disconnected = deepcopy(missing)
    disconnected["artifacts"].extend(rows)
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=disconnected)
    assert not result.ok
    assert any(code.startswith("missing_required_operation:") for code in result.codes)

    terminal = next(row for row in rows if row["artifact_digest"] == correct["outputs"]["terminal_artifact_digest"])
    reset = scripted_leaf(operation="reset_all_work", inputs={
        "roots": fixture["inputs"], "terminal": terminal,
    }, context=fixture["context"])
    destructive = {**deepcopy(correct), "artifacts": [*rows, reset], "outputs": {
        **reset["result"], "terminal_artifact_digest": reset["artifact_digest"],
    }}
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=destructive)
    assert not result.ok
    assert "invalidation_obligation_mismatch" in result.codes
    assert "reuse_obligation_mismatch" in result.codes
    assert not any(code.startswith("invalid_payload:") for code in result.codes)
    for row in destructive["artifacts"]:
        assert scripted_leaf(operation=row["operation"], inputs=row["inputs"], context=row["context"]) == row

    stale_fixture = deepcopy(fixture)
    stale_roots = stale_fixture["inputs"]
    if family == "conditional_judgment":
        stale_roots["accepted_findings"] = "stale:" + stale_roots["accepted_findings"]
        for value in stale_roots["evidence_inventory"].values():
            if value["kind"] == "accepted":
                value["content"] = stale_roots["accepted_findings"]
        stale = _judgment_fixture(stale_fixture, gated=True)
    else:
        stale_roots["current_work"] = "stale:" + stale_roots["current_work"]
        stale = _scientific_fixture(stale_fixture, gated=True)
    assert evaluate_behavior(spec=spec, fixture=stale_fixture, authored=stale).ok
    for row in stale["artifacts"]:
        assert scripted_leaf(operation=row["operation"], inputs=row["inputs"], context=row["context"]) == row
    stale["inputs"] = deepcopy(fixture["inputs"])
    stale["context"] = deepcopy(fixture["context"])
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=stale)
    assert not result.ok
    assert "fixture_input_context_mismatch" not in result.codes
    assert any(code.startswith("invalid_payload:") for code in result.codes)

    stale_digest = deepcopy(correct)
    stale_digest["artifacts"][0]["result"]["unrelated"] = "tampered without updating digest"
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=stale_digest)
    assert not result.ok
    assert any(code.startswith("invalid_payload:") for code in result.codes)

    missing = deepcopy(correct)
    dependency = "independent_assess" if family == "conditional_judgment" else "pilot"
    missing["artifacts"] = [row for row in missing["artifacts"] if row["operation"] != dependency]
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=missing)
    assert not result.ok
    assert "unresolved_consumed_input" in result.codes
    for forbidden in ("candidate_id", "global_role", "scenario_id"):
        mutated = deepcopy(correct)
        mutated["artifacts"][0][forbidden] = "answer-bearing"
        assert not evaluate_behavior(spec=spec, fixture=fixture, authored=mutated).ok
    wrong_context = deepcopy(correct)
    wrong_context["context"]["decision_boundary"] = "wrong-boundary"
    assert not evaluate_behavior(spec=spec, fixture=fixture, authored=wrong_context).ok

    wrong_terminal = deepcopy(correct)
    wrong_terminal["outputs"]["terminal_artifact_digest"] = "0" * 64
    assert "terminal_control_mismatch" in evaluate_behavior(
        spec=spec, fixture=fixture, authored=wrong_terminal,
    ).codes
    wrong_output = deepcopy(correct)
    wrong_output["outputs"]["decision"] = "invented"
    assert "workflow_outputs_mismatch" in evaluate_behavior(
        spec=spec, fixture=fixture, authored=wrong_output,
    ).codes
    # Rehashing a consumer does not make its altered nested producer equal to the real row.
    wrong_producer = deepcopy(correct)
    consumer = next(row for row in wrong_producer["artifacts"] if row["operation"] == (
        "compare_findings" if family == "conditional_judgment" else "pilot"
    ))
    source = consumer["inputs"]["assessment_a" if family == "conditional_judgment" else "diagnosis"]
    # Detach the nested reference from deepcopy's preserved shared references.
    source = deepcopy(source)
    consumer["inputs"]["assessment_a" if family == "conditional_judgment" else "diagnosis"] = source
    source["result"]["unrelated"] = "different consumed producer"
    body = {key: value for key, value in consumer.items() if key != "artifact_digest"}
    consumer["artifact_digest"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    assert f"invalid_payload:{consumer['operation']}" in evaluate_behavior(
        spec=spec, fixture=fixture, authored=wrong_producer,
    ).codes


def test_conditional_judgment_leaf_compositions_and_oracle_controls() -> None:
    scenarios = (
        "disagreement-bounded-reconsideration",
        "agreement-acceptance-without-extra-revision",
        "revision-after-material-disagreement",
    )
    for index, scenario_id in enumerate(scenarios):
        outputs = []
        operations = []
        for composition in ("a", "b"):
            authored = _judgment_fixture(
                TASK2_FIXTURES[("conditional_judgment", scenario_id)], gated=composition == "b",
            )
            result = evaluate_behavior(
                spec=SCENARIOS[("case-conditional-judgment-disagreement", scenario_id)],
                fixture=TASK2_FIXTURES[("conditional_judgment", scenario_id)],
                authored=authored,
            )
            assert result.ok, result.codes
            assert authored["outputs"]["decision"] == (
                "RECONSIDER_THEN_ACCEPT", "ACCEPT_AGREEMENT", "REVISE_IMPLICATED_SCOPE",
            )[index]
            outputs.append(authored["outputs"])
            operations.append({row["operation"] for row in authored["artifacts"]})
            resolved = authored["outputs"]["produced_outputs"]["resolved_findings"]
            assert resolved["findings_considered"] == [
                authored["inputs"]["finding_a"], authored["inputs"]["finding_b"],
            ]
            assert resolved["accepted_basis"] == authored["inputs"]["accepted_findings"]
            assert authored["outputs"]["reconsiderations_used"] == (
                1 if scenario_id == "disagreement-bounded-reconsideration" else 0
            )
            if "revise" in operations[-1]:
                assert "dependent_conclusions" in authored["outputs"]["produced_outputs"]
        assert "judgment_gate" not in operations[0]
        assert "judgment_gate" in operations[1]
        terminal = authored["artifacts"][-1]
        assert terminal["inputs"]["judgment"]["operation"] == "judgment_gate"
        assert terminal["inputs"]["judgment"]["inputs"]["comparison"]["operation"] == "compare_findings"
        assert [row["inputs"]["finding"] for row in authored["artifacts"][:2]] == [
            authored["inputs"]["finding_b"], authored["inputs"]["finding_a"],
        ]
        assert {
            k: v for k, v in outputs[0].items() if k != "terminal_artifact_digest"
        } == {k: v for k, v in outputs[1].items() if k != "terminal_artifact_digest"}
        _assert_task2_controls("conditional_judgment", scenario_id, authored)


def test_scientific_transfer_leaf_compositions_and_oracle_controls() -> None:
    scenarios = (
        "process-success-without-valid-scientific-acceptance",
        "pilot-evidence-calls-for-method-reconsideration",
        "selective-reuse-after-relevant-correction",
    )
    for index, scenario_id in enumerate(scenarios):
        outputs = []
        operations = []
        for composition in ("a", "b"):
            authored = _scientific_fixture(
                TASK2_FIXTURES[("scientific_transfer", scenario_id)], gated=composition == "b",
            )
            result = evaluate_behavior(
                spec=SCENARIOS[("case-multi-item-scientific-transfer", scenario_id)],
                fixture=TASK2_FIXTURES[("scientific_transfer", scenario_id)],
                authored=authored,
            )
            assert result.ok, result.codes
            assert authored["outputs"]["decision"] == (
                "PROCESS_COMPLETE_SCIENTIFIC_INSUFFICIENT", "RECONSIDER_METHOD", "SELECTIVE_CONTINUE",
            )[index]
            output = authored["outputs"]
            outputs.append(output)
            operations.append({row["operation"] for row in authored["artifacts"]})
            assert output["process_status"] == "COMPLETED"
            assert output["scientific_acceptance"] is (index == 2)
            assert output["next_item"] == authored["inputs"]["remaining_backlog"]
            if index == 2:
                roots = authored["inputs"]
                changed = output["produced_outputs"][roots["current_claim"]["id"]]
                assert changed["content"] == roots["corrected_outputs"]
                assert changed["content"] != roots["current_claim"]["content"]
                for key, value in roots["accepted_evidence"].items():
                    assert output["preserved_outputs"][key] == value
                assert all(
                    not value["admissible_for_current_comparison"]
                    for value in output["evidence_classification"]["prior_useful"].values()
                )
            if index == 1:
                plan = output["produced_outputs"]["method_plan"]
                assert plan["content"]["hold_current_comparison"]
                assert plan["content"]["investigate"] == authored["inputs"]["observed_issue"]
        assert "evidence_gate" not in operations[0]
        assert {"evidence_gate", "item_gate"} <= operations[1]
        judgment = next(row for row in authored["artifacts"] if row["operation"] == "judge_scientific_value")
        assert judgment["inputs"]["current_item_output"]["operation"] == "item_gate"
        assert judgment["inputs"]["current_comparison_evidence"]["operation"] == "evidence_gate"
        if index == 2:
            order = [row["operation"] for row in authored["artifacts"]]
            assert order.index("preserve_unaffected_accepted_work") < order.index("selectively_reuse_after_relevant_correction")
        assert {
            k: v for k, v in outputs[0].items() if k != "terminal_artifact_digest"
        } == {k: v for k, v in outputs[1].items() if k != "terminal_artifact_digest"}
        _assert_task2_controls("scientific_transfer", scenario_id, authored)


@pytest.mark.parametrize(
    ("confidence", "other_confidence", "expected"),
    (
        ("0.799999", "0.30", "RECONSIDER"),
        ("0.80", "0.30", "REVISE"),
        ("0.800001", "0.30", "REVISE"),
        ("0.70", "0.20", "REVISE"),
    ),
)
def test_materiality_leaf_boundary_consumes_assessments(
    confidence: str, other_confidence: str, expected: str,
) -> None:
    scenario = "disagreement-bounded-reconsideration"
    fixture = deepcopy(TASK2_FIXTURES[("conditional_judgment", scenario)])
    fixture["inputs"].update(confidence_a=confidence, confidence_b=other_confidence)
    authored = _judgment_fixture(fixture, gated=True)
    comparison = next(
        row for row in authored["artifacts"] if row["operation"] == "compare_findings"
    )
    assert comparison["inputs"]["assessment_a"]["inputs"]["confidence"] == confidence
    assert comparison["inputs"]["assessment_b"]["inputs"]["confidence"] == other_confidence
    assert comparison["result"]["assessment_values"] == [
        {"finding": fixture["inputs"]["finding_a"], "scope": "calibration", "confidence": float(confidence)},
        {"finding": fixture["inputs"]["finding_b"], "scope": "calibration", "confidence": float(other_confidence)},
    ]
    assert comparison["result"]["decision"] == expected
    assert authored["outputs"]["reconsiderations_used"] == int(expected == "RECONSIDER")


@pytest.mark.parametrize(("field", "bad"), (
    ("confidence_a", "malformed"),
    ("materiality_threshold", "NaN"),
    ("metric", "Infinity"),
    ("criterion", "-Infinity"),
    ("confidence_a", "-0.1"),
    ("confidence_a", "-1e-9999"),
    ("criterion", "1.1"),
    ("reconsideration_limit", "1.1"),
    ("reconsiderations_used", "-0.1"),
))
def test_task2_numeric_policy_fails_closed(field: str, bad: str) -> None:
    # These retained leaf-level boundaries require no workflow executor.
    conditional = field not in {"metric", "criterion"}
    fixture = deepcopy(TASK2_FIXTURES[
        ("conditional_judgment", "disagreement-bounded-reconsideration")
        if conditional else
        ("scientific_transfer", "process-success-without-valid-scientific-acceptance")
    ])
    roots, context = fixture["inputs"], fixture["context"]
    (context if field in context else roots)[field] = bad
    with pytest.raises(ValueError):
        if conditional:
            a = scripted_leaf(operation="independent_assess", inputs={
                "roots": roots, "finding": roots["finding_a"],
                "confidence": roots["confidence_a"], "scope": roots["scope"],
            }, context=context)
            b = scripted_leaf(operation="independent_assess", inputs={
                "roots": roots, "finding": roots["finding_b"],
                "confidence": roots["confidence_b"], "scope": roots["scope"],
            }, context=context)
            scripted_leaf(operation="compare_findings", inputs={
                "roots": roots, "assessment_a": a, "assessment_b": b,
            }, context=context)
        else:
            if field == "metric":
                roots["observation"]["metric"] = bad
            diagnosis = scripted_leaf(operation="diagnose", inputs={"roots": roots}, context=context)
            pilot = scripted_leaf(operation="pilot", inputs={
                "roots": roots, "diagnosis": diagnosis,
            }, context=context)
            item = scripted_leaf(operation="continue_per_item", inputs={
                "roots": roots, "per_item_decision": diagnosis, "pilot": pilot,
            }, context=context)
            scripted_leaf(operation="judge_scientific_value", inputs={
                "roots": roots, "current_item_output": item,
                "current_comparison_evidence": pilot,
            }, context=context)


@pytest.mark.parametrize("used", ("0", "1"))
def test_reconsideration_leaf_consumes_allowance(used: str) -> None:
    scenario = "disagreement-bounded-reconsideration"
    fixture = deepcopy(TASK2_FIXTURES[("conditional_judgment", scenario)])
    fixture["context"].update(reconsideration_limit="1", reconsiderations_used=used)
    authored = _judgment_fixture(fixture, gated=True)
    operations = {row["operation"] for row in authored["artifacts"]}
    assert authored["outputs"]["reconsiderations_used"] == 1
    if used == "1":
        assert "reconsider" not in operations
        assert "revise" in operations
        comparison = next(row for row in authored["artifacts"] if row["operation"] == "compare_findings")
        with pytest.raises(ValueError, match="contradicts"):
            scripted_leaf(operation="reconsider", inputs={
                "roots": fixture["inputs"], "comparison": comparison,
            }, context=fixture["context"])
    else:
        assert "reconsider" in operations
        assert "revise" not in operations


@pytest.mark.parametrize(("metric", "accepted"), (
    ("0.799999", False), ("0.80", True), ("0.800001", True),
    ("0.799999999999999999999999", False),
))
def test_scientific_leaf_threshold_uses_declared_pilot_value(
    metric: str, accepted: bool,
) -> None:
    scenario = "process-success-without-valid-scientific-acceptance"
    fixture = deepcopy(TASK2_FIXTURES[("scientific_transfer", scenario)])
    fixture["inputs"]["metric"] = metric
    fixture["inputs"]["observation"]["metric"] = metric
    authored = _scientific_fixture(fixture)
    assert authored["outputs"]["process_status"] == "COMPLETED"
    assert authored["outputs"]["scientific_acceptance"] is accepted
    pilot = next(row for row in authored["artifacts"] if row["operation"] == "pilot")
    item = next(row for row in authored["artifacts"] if row["operation"] == "continue_per_item")
    assert pilot["inputs"]["roots"]["observation"]["metric"] == metric
    assert pilot["inputs"]["roots"]["metric"] == metric
    assert pilot["result"]["metric"] == float(metric)
    assert pilot["result"]["method"] == "current-method"
    assert pilot["result"]["data"] == "heldout-data"
    assert item["inputs"]["pilot"] == pilot
    assert item["result"]["pilot_value"] == pilot["result"]
    assert authored["outputs"]["evidence_classification"]["current_comparison"] == pilot["result"]


def test_behavior_binds_explicit_nonregistry_fixture_and_context() -> None:
    from dataclasses import replace

    family = "conditional_judgment"
    scenario = "agreement-acceptance-without-extra-revision"
    fixture = deepcopy(TASK2_FIXTURES[(family, scenario)])
    fixture["inputs"].update(
        scope="nonregistry-scope", finding_a="nonregistry-finding",
        finding_b="nonregistry-finding",
    )
    fixture["context"]["materiality_threshold"] = "0.3333333333333333"
    spec = replace(SCENARIOS[(family, scenario)], scenario_id="nonregistry-binding")
    assert (family, spec.scenario_id) not in SCENARIOS
    authored = _judgment_fixture(fixture, gated=True)
    result = evaluate_behavior(spec=spec, fixture=fixture, authored=authored)
    assert result.ok, result.codes
    # An internally valid result cannot supply or override controller truth.
    assert "fixture_input_context_mismatch" in evaluate_behavior(
        spec=spec, fixture=TASK2_FIXTURES[(family, scenario)], authored=authored,
    ).codes
    for field in ("inputs", "context"):
        wrong = deepcopy(authored)
        wrong[field] = TASK2_FIXTURES[(family, scenario)][field]
        assert "fixture_input_context_mismatch" in evaluate_behavior(
            spec=spec, fixture=fixture, authored=wrong,
        ).codes
    comparison = next(row for row in authored["artifacts"] if row["operation"] == "compare_findings")
    for field in ("inputs", "context"):
        foreign = deepcopy(fixture)
        foreign[field] = TASK2_FIXTURES[(family, scenario)][field]
        with pytest.raises(ValueError, match="different roots or context"):
            scripted_leaf(
                operation="accept", inputs={"roots": foreign["inputs"], "comparison": comparison},
                context=foreign["context"],
            )
