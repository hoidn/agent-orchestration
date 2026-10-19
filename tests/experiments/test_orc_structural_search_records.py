"""Behavior of the structural search records log, skeleton hash and final-choice rule."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from experiments.orc_structural_search.records import (
    append_record,
    final_choice,
    python_program_digest,
    python_skeleton_hash,
    read_records,
    skeleton_hash,
)
from tests.experiments.orc_structural_search_support import PYTHON_PARENT

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


SEEDS = Path(__file__).resolve().parents[2] / "experiments" / "orc_structural_search" / "seeds"


def _rename_in_run(source: str, old: str, new: str) -> str:
    """Rename the symbol `old` inside `(defworkflow run ...)`, never keywords or fill names."""

    start = source.index("(defworkflow run")
    pattern = rf"(?<![:\w.{{-]){re.escape(old)}(?![\w}}-])"
    return source[:start] + re.sub(pattern, new, source[start:])


@pytest.mark.parametrize(
    ("seed", "binder"),
    [
        ("implement_review_revise.orc", "state"),  # fn parameter inside loop/recur
        ("best_of_n.orc", "label"),  # list/map-effect binding
        ("implement_review_revise.orc", "review"),  # let* name used as match subject
        ("best_of_n.orc", "task"),  # workflow parameter passed as a prompt fill value
    ],
)
def test_skeleton_is_invariant_under_binder_rename_in_real_seed(seed, binder):
    source = (SEEDS / seed).read_text(encoding="utf-8")
    renamed = _rename_in_run(source, binder, "renamed_binder")
    assert renamed != source
    assert skeleton_hash(renamed, definitions=["run"]) == skeleton_hash(source, definitions=["run"])


LET_PROC_SOURCE = """
(defworkflow run ((question String)) -> Result
  (let-proc ((ask (topic) (provider-result providers.codex :prompt prompts.ask :inputs (topic))))
    (ask question)))
"""


def test_skeleton_is_invariant_under_let_proc_name_and_parameter_rename():
    renamed = LET_PROC_SOURCE.replace("ask ", "query ").replace("(ask", "(query").replace("topic", "subject")
    assert skeleton_hash(renamed, definitions=["run"]) == skeleton_hash(LET_PROC_SOURCE, definitions=["run"])


PROMPT_CALL_SOURCE = """
(defworkflow run ((task String) (intent String) (repo String)) -> Outcome
  (provider-result providers.coder
    :prompt (propose-prompt :task task :repo repo)
    :model "claude-sonnet-5-5"))
"""


def test_skeleton_changes_when_a_prompt_fill_is_rewired():
    rewired = PROMPT_CALL_SOURCE.replace(":task task", ":task intent")
    assert skeleton_hash(rewired, definitions=["run"]) != skeleton_hash(PROMPT_CALL_SOURCE, definitions=["run"])


def test_skeleton_ignores_prompt_name_and_fill_value_binder_rename():
    renamed = (
        PROMPT_CALL_SOURCE.replace("propose-prompt", "other-prompt")
        .replace("(task String)", "(job String)")
        .replace(":task task", ":task job")
    )
    assert skeleton_hash(renamed, definitions=["run"]) == skeleton_hash(PROMPT_CALL_SOURCE, definitions=["run"])


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


def test_final_choice_refuses_non_numeric_cost_ceiling():
    rows = [
        _row("seed", 0.6, "unavailable", 2, reference=True),
        _row("b", 0.99, "unavailable", 1),
    ]
    criterion = {**CRITERION, "mean_cost_ceiling": "unavailable"}
    with pytest.raises(ValueError, match="mean_cost_ceiling must be numeric"):
        final_choice(rows, criterion=criterion)


PYTHON = (PYTHON_PARENT / "direct.py").read_text()  # the I3 parent


def _python_edit(*edits: tuple[str, str]) -> str:
    source = PYTHON
    for old, new in edits:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    return source


def test_python_skeleton_is_invariant_under_renames_and_literals_and_differs_for_a_branch():
    renamed = _python_edit(("    change = provider_result", "    outcome = provider_result"),
                           ("summary=change.summary", "summary=outcome.summary"),
                           ('model="gpt-6.1-sol", effort="high", timeout_sec=5400',
                            'model="other", effort="low", timeout_sec=60'))
    branched = _python_edit(("    return DONE(summary=change.summary)",
                             "    if not change.account:\n        return BLOCKED(reason=intent)\n"
                             "    return DONE(summary=change.summary)"))
    looped = _python_edit(("    change = provider_result", "    for _ in range(2):\n        change = provider_result"))
    called = _python_edit(("    return DONE(summary=change.summary)",
                           "    dev_check()\n    return DONE(summary=change.summary)"))
    hashes = [python_skeleton_hash(source, definitions=["run"])
              for source in (PYTHON, renamed, branched, looped, called)]
    assert [digest == hashes[0] for digest in hashes[1:]] == [True, False, False, False]


def test_python_program_digest_ignores_comments_and_changes_with_a_rename():
    commented = _python_edit(("def run(", "# the policy\n\n\ndef run("))
    renamed = _python_edit(("    change = provider_result", "    outcome = provider_result"),
                           ("summary=change.summary", "summary=outcome.summary"))
    digests = [python_program_digest(source) for source in (PYTHON, commented, renamed)]
    assert (digests[0].startswith("sha256:"), digests[1] == digests[0], digests[2] == digests[0]) == (True, True, False)
