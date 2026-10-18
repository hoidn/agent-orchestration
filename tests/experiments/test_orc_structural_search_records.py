"""Behavior of the structural search records log, skeleton hash and final-choice rule."""

from __future__ import annotations

import pytest

from experiments.orc_structural_search.records import (
    append_record,
    final_choice,
    read_records,
    skeleton_hash,
)

SOURCE = """
(workflow-lisp
  (:language "0.1")
  (defproc helper ((x Int)) -> Int :effects () x)
  (defworkflow review ((brief Brief) (limit Int)) -> Result
    (let* ((draft (provider-result providers.codex
                    :prompt prompts.draft
                    :inputs (brief.question "head")
                    :model "gpt-5.4"
                    :effort "high"
                    :timeout-sec 7200
                    :returns Draft))
           (total (+ limit 3)))
      (match draft
        ((APPROVED approved) (record Result :text approved.text :score total))
        ((BLOCKED blocked) (record Result :text blocked.reason :score 0))))))
"""


def _hash(source: str) -> str:
    return skeleton_hash(source, definitions=["review"])


def test_skeleton_is_invariant_under_rename_prompt_text_and_literals():
    variant = (
        SOURCE.replace("brief", "request")
        .replace("draft", "candidate")
        .replace("approved", "ok")
        .replace("total", "points")
        .replace('"head"', '"other text"')
        .replace("7200", "60")
        .replace("3)", "41)")
        .replace("prompts.candidate", "prompts.rewritten")
    )
    assert _hash(variant) == _hash(SOURCE)


def test_skeleton_differs_for_control_flow_change():
    variant = SOURCE.replace(
        "(total (+ limit 3))", "(total (if (= limit 0) 1 (+ limit 3)))"
    )
    assert _hash(variant) != _hash(SOURCE)


def test_skeleton_ignores_provider_swap_and_model_change():
    variant = SOURCE.replace("providers.codex", "providers.claude").replace(
        '"gpt-5.4"', '"opus"'
    ).replace('"high"', '"low"')
    assert _hash(variant) == _hash(SOURCE)


def test_append_and_read_records_preserve_unavailable_marker(tmp_path):
    log = tmp_path / "records.jsonl"
    append_record(log, {"candidate_id": "c1", "consumption": "unavailable"})
    append_record(log, {"candidate_id": "c2", "consumption": 1.5})
    assert read_records(log) == [
        {"candidate_id": "c1", "consumption": "unavailable"},
        {"candidate_id": "c2", "consumption": 1.5},
    ]


def _row(cid, success, cost, calls, *, reference=False):
    return {
        "candidate_id": cid,
        "is_reference": reference,
        "validation_success": success,
        "mean_cost": cost,
        "provider_calls": calls,
    }


CRITERION = {
    "criterion_sha256": "ab" * 32,
    "mean_cost_ceiling": 10.0,
    "equivalence_tolerance": 0.05,
}


def test_final_choice_picks_highest_validation_then_lower_cost():
    rows = [
        _row("seed", 0.5, 1.0, 2, reference=True),
        _row("b", 0.90, 6.0, 4),
        _row("c", 0.88, 3.0, 4),
        _row("d", 0.70, 0.5, 1),
    ]
    assert final_choice(rows, criterion=CRITERION) == "c"


def test_final_choice_refuses_without_criterion_hash():
    rows = [_row("seed", 0.5, 1.0, 2, reference=True)]
    criterion = {k: v for k, v in CRITERION.items() if k != "criterion_sha256"}
    with pytest.raises(ValueError, match="criterion_sha256 required"):
        final_choice(rows, criterion=criterion)


def test_final_choice_refuses_without_reference_seed():
    with pytest.raises(ValueError, match="reference seed missing"):
        final_choice([_row("b", 0.9, 1.0, 1)], criterion=CRITERION)


def test_final_choice_compares_reference_seed():
    rows = [
        _row("seed", 0.95, 2.0, 2, reference=True),
        _row("b", 0.80, 1.0, 1),
        _row("c", 0.99, 20.0, 6),
    ]
    assert final_choice(rows, criterion=CRITERION) == "seed"


def test_final_choice_breaks_ties_by_calls_then_candidate_id():
    rows = [
        _row("seed", 0.9, 1.0, 3, reference=True),
        _row("b", 0.9, 1.0, 2),
        _row("a", 0.9, 1.0, 2),
    ]
    assert final_choice(rows, criterion=CRITERION) == "a"


def test_final_choice_treats_unavailable_cost_as_over_ceiling_when_ceiling_is_in_cost_units():
    rows = [
        _row("seed", 0.6, 1.0, 2, reference=True),
        _row("b", 0.99, "unavailable", 1),
    ]
    assert final_choice(rows, criterion=CRITERION) == "seed"


def test_final_choice_keeps_unavailable_cost_when_ceiling_is_unavailable():
    rows = [
        _row("seed", 0.6, "unavailable", 2, reference=True),
        _row("b", 0.99, "unavailable", 1),
    ]
    criterion = {**CRITERION, "mean_cost_ceiling": "unavailable"}
    assert final_choice(rows, criterion=criterion) == "b"
