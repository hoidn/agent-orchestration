"""UE01–UE04 and UD01–UD06: paired source edits and failure costs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.experiments.test_dynamic_core_utility_improve import (
    FIXTURES,
    IMPROVE_DEFINITIONS,
    ROOT,
    UTILITY_LEAVES,
    _candidate_source,
    _dynamic_run,
    _events,
    _typed_domain_result,
    _typed_run,
    _write_probes,
)
from tests.workflow_lisp_improve_stdlib_sources import (
    REVIEW_PROBE,
    REVISE_PROBE,
    entry_source,
    string_inputs_entry_source,
)


def _replace_once(source: str, before: str, after: str) -> str:
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


def _save_receipt(root: Path, case: str, receipt: dict[str, object], sources: dict[str, str]) -> None:
    evidence = root / "evidence" / case
    evidence.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        path = evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    (evidence / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _dynamic_leaf_states(root: Path) -> list[dict[str, object]]:
    states = []
    for state_path in sorted((root / ".orchestrate/runs").glob("*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        states.append(
            {
                "run_id": state["run_id"],
                "status": state["status"],
                "workflow_outputs": state.get("workflow_outputs"),
                "state_path": state_path.relative_to(root).as_posix(),
                "run_files": sorted(path.relative_to(state_path.parent).as_posix()
                                     for path in state_path.parent.rglob("*") if path.is_file()),
            }
        )
    return states


def _origin_revise_probe() -> str:
    return _replace_once(
        REVISE_PROBE,
        'payload = {"title": title + "+r", "score": title.count("+r") + 1}',
        'payload = {"title": title + "+r", "score": title.count("+r") + 1, "origin": sys.argv[4]}',
    )


def _origin_utility_source() -> str:
    source = UTILITY_LEAVES.read_text(encoding="utf-8")
    source = _replace_once(
        source,
        "(defrecord Draft (title String) (score Int))",
        "(defrecord Draft (title String) (score Int) (origin String))",
    )
    source = _replace_once(
        source,
        'draft.title goal)',
        'draft.title goal draft.origin)',
    )
    source = _replace_once(
        source,
        'draft.title goal feedback.note)',
        'draft.title goal feedback.note draft.origin)',
    )
    return source


def _origin_typed_entry(probes: dict[str, Path], *, limit: int = 1) -> str:
    source = entry_source(seed="draft", limit=limit, probes=probes)
    source = _replace_once(
        source,
        "(defrecord Candidate (title String) (score Int))",
        "(defrecord Candidate (title String) (score Int) (origin String))",
    )
    source = _replace_once(source, "candidate.title brief.goal)", "candidate.title brief.goal candidate.origin)")
    source = _replace_once(
        source,
        "candidate.title brief.goal feedback.note)",
        "candidate.title brief.goal feedback.note candidate.origin)",
    )
    source = _replace_once(
        source,
        '(record Candidate :title "draft" :score 0)',
        '(record Candidate :title "draft" :score 0 :origin "seed")',
    )
    return source


def test_UE01_origin_boundary_and_internal_state_edits_are_counted_separately(tmp_path: Path) -> None:
    typed_root = tmp_path / "typed"
    dynamic_root = tmp_path / "dynamic"
    dynamic_root.mkdir(parents=True)
    typed_probes = {
        "probe_review": typed_root / "probe_review.py",
        "probe_revise": typed_root / "probe_revise.py",
    }
    typed_before = entry_source(seed="draft", limit=1, probes=typed_probes)
    typed_source = _origin_typed_entry(typed_probes)
    utility_before = UTILITY_LEAVES.read_text(encoding="utf-8")
    utility_after = _origin_utility_source()
    probe_before = REVISE_PROBE
    dynamic_probe = _origin_revise_probe()
    candidate_path = _candidate_source(
        dynamic_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = candidate_path.read_text(encoding="utf-8")
    candidate_after = _replace_once(
        candidate_before,
        '(record (title "draft") (score 0))',
        '(record (title "draft") (score 0) (origin "seed"))',
    )
    score_forwarding = '(draft__score (field current "score"))'
    assert candidate_after.count(score_forwarding) == 2
    candidate_after = candidate_after.replace(
        score_forwarding,
        score_forwarding + '\n                         (draft__origin (field current "origin"))',
    )
    candidate_after = _replace_once(
        candidate_after,
        '(score (field wire "return__score")))',
        '(score (field wire "return__score"))\n            (origin (field wire "return__origin")))',
    )
    dynamic_before = _dynamic_run(
        dynamic_root / "before",
        seed="draft",
        limit=1,
        utility_source_text=utility_after,
        candidate_source_text=candidate_before,
        revise_script=dynamic_probe,
    )
    typed, typed_calls = _typed_run(
        typed_root,
        seed="draft",
        limit=1,
        entry_source_text=typed_source,
        revise_script=dynamic_probe,
    )
    dynamic = _dynamic_run(
        dynamic_root,
        seed="draft",
        limit=1,
        utility_source_text=utility_after,
        candidate_source_text=candidate_after,
        revise_script=dynamic_probe,
    )
    _save_receipt(
        tmp_path,
        "UE01",
        {
            "typed_boundary_sites": [
                "Candidate schema field",
                "review leaf argv origin",
                "revision leaf argv and result origin",
            ],
            "typed_internal_state_sites": ["initial Candidate seed"],
            "typed_duplicated_facts": [
                "current Candidate.origin is forwarded independently at review and revision call sites",
            ],
            "dynamic_boundary_sites": [
                "Draft schema field",
                "review leaf argv origin",
                "revision leaf argv and result origin",
            ],
            "dynamic_internal_state_sites": [
                "initial candidate origin",
                "review and revise effect forwarding",
                "revision result reconstruction",
            ],
            "dynamic_duplicated_facts": [
                "current origin is forwarded independently at review and revision call sites",
            ],
            "typed_status": typed["status"],
            "typed_outputs": typed.get("workflow_outputs"),
            "typed_calls": typed_calls,
            "typed_value": {
                "variant": typed["workflow_outputs"]["return__variant"],
                "value": {
                    "title": typed["workflow_outputs"]["return__value__title"],
                    "score": typed["workflow_outputs"]["return__value__score"],
                    "origin": typed["workflow_outputs"]["return__value__origin"],
                },
            },
            "dynamic_red_error": getattr(dynamic_before.get("error"), "code", None),
            "dynamic_red_calls": dynamic_before.get("events"),
            "dynamic_value": dynamic.get("value"),
            "dynamic_calls": dynamic.get("events"),
            "concepts": ["typed field addition", "internal state forwarding", "returned-record reconstruction"],
            "required_changes": [
                "add origin to the utility Draft schema and revision result",
                "add Candidate.origin and initialize the caller's origin seed",
                "forward origin at both effect sites and reconstruct it from the revise result",
            ],
            "observed_repairs": [
                "apply one scripted caller repair batch after the boundary-invalid RED, then verify full typed/dynamic value and effect parity",
            ],
            "timing": "unmeasured",
        },
        {
            "utility.before.orc": utility_before,
            "utility.after.orc": utility_after,
            "candidate.before.orc": candidate_before,
            "candidate.after.orc": candidate_after,
            "typed.before.orc": typed_before,
            "typed.after.orc": typed_source,
            "probe_revise.before.py": probe_before,
            "probe_revise.after.py": dynamic_probe,
        },
    )
    assert dynamic_before["error"].code == "dynamic_boundary_invalid"
    assert dynamic_before["events"] == []
    assert "error" not in dynamic, dynamic.get("error")
    expected = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1, "origin": "seed"}}
    assert dynamic["value"] == expected
    assert typed["status"] == "completed"
    assert {
        "variant": typed["workflow_outputs"]["return__variant"],
        "value": {
            "title": typed["workflow_outputs"]["return__value__title"],
            "score": typed["workflow_outputs"]["return__value__score"],
            "origin": typed["workflow_outputs"]["return__value__origin"],
        },
    } == expected
    expected_calls = [
        {"hook": "review", "argv": ["draft", "tidy", "seed"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0", "seed"]},
    ]
    assert dynamic["events"] == typed_calls == expected_calls


def _message_review_probe() -> str:
    assert REVIEW_PROBE.count('"note":') == 2
    return REVIEW_PROBE.replace('"note":', '"message":')


def _message_utility_source() -> str:
    source = UTILITY_LEAVES.read_text(encoding="utf-8")
    source = _replace_once(source, "(defrecord Feedback (note String))", "(defrecord Feedback (message String))")
    source = _replace_once(source, "feedback.note)", "feedback.message)")
    return source


def _message_candidate(source: str) -> str:
    source = _replace_once(source, 'return__evidence__note', 'return__evidence__message')
    source = _replace_once(source, 'return__feedback__note', 'return__feedback__message')
    return _replace_once(source, '(field feedback "note")', '(field feedback "message")')


def _repair_message_candidate(candidate: str) -> str:
    old = '(record (note (field wire "return__'
    assert candidate.count(old) == 2
    return candidate.replace(old, '(record (message (field wire "return__')


def _repair_message_revision_input(candidate: str) -> str:
    return _replace_once(candidate, "(feedback__note ", "(feedback__message ")


def _message_typed_entry(probes: dict[str, Path], *, seed: str, limit: int) -> str:
    source = entry_source(seed=seed, limit=limit, probes=probes)
    source = _replace_once(source, "(defrecord Feedback (note String))", "(defrecord Feedback (message String))")
    return _replace_once(source, "feedback.note)", "feedback.message)")


def _typed_message_value(outputs: dict[str, object]) -> dict[str, object]:
    tag = outputs["return__variant"]
    value = {
        "variant": tag,
        "value": {
            "title": outputs["return__value__title"],
            "score": outputs["return__value__score"],
        },
    }
    if tag == "APPROVED":
        value["evidence"] = {"message": outputs["return__evidence__message"]}
    return value


def test_UE02_feedback_and_evidence_field_rename_updates_both_consumers(tmp_path: Path) -> None:
    typed_root = tmp_path / "typed"
    dynamic_root = tmp_path / "dynamic"
    dynamic_root.mkdir(parents=True)
    probe_before = REVIEW_PROBE
    probe_after = _message_review_probe()
    utility_before = UTILITY_LEAVES.read_text(encoding="utf-8")
    utility_after = _message_utility_source()
    initial_candidate_path = _candidate_source(
        dynamic_root,
        seed="approve",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = initial_candidate_path.read_text(encoding="utf-8")
    candidate_red = _message_candidate(candidate_before)
    candidate_labels_repaired = _repair_message_candidate(candidate_red)
    candidate_after = _repair_message_revision_input(candidate_labels_repaired)

    dynamic_red = _dynamic_run(
        dynamic_root / "red",
        seed="approve",
        limit=1,
        utility_source_text=utility_after,
        candidate_source_text=candidate_red,
        review_script=probe_after,
    )
    dynamic_late_red = _dynamic_run(
        dynamic_root / "late-red",
        seed="draft",
        limit=1,
        utility_source_text=utility_after,
        candidate_source_text=candidate_labels_repaired.replace('"approve"', '"draft"', 1),
        review_script=probe_after,
    )

    outcomes = []
    sources: dict[str, str] = {
        "utility.before.orc": utility_before,
        "utility.after.orc": utility_after,
        "candidate.before.orc": candidate_before,
        "candidate.red.orc": candidate_red,
        "candidate.labels-repaired.orc": candidate_labels_repaired,
        "probe_review.before.py": probe_before,
        "probe_review.after.py": probe_after,
    }
    expected_calls_by_seed = {
        "approve": [{"hook": "review", "argv": ["approve", "tidy"]}],
        "draft": [
            {"hook": "review", "argv": ["draft", "tidy"]},
            {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
        ],
    }
    for seed, limit, expected in (
        (
            "approve",
            1,
            {"variant": "APPROVED", "value": {"title": "approve", "score": 0},
             "evidence": {"message": "ok:approve:tidy"}},
        ),
        ("draft", 1, {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}),
    ):
        typed_probes = {
            "probe_review": typed_root / seed / "probe_review.py",
            "probe_revise": typed_root / seed / "probe_revise.py",
        }
        typed_before = entry_source(seed=seed, limit=limit, probes=typed_probes)
        typed_source = _message_typed_entry(typed_probes, seed=seed, limit=limit)
        typed, typed_events = _typed_run(
            typed_root / seed,
            seed=seed,
            limit=limit,
            entry_source_text=typed_source,
            review_script=probe_after,
        )
        candidate = candidate_after.replace('"approve"', f'"{seed}"', 1)
        sources[f"typed.{seed}.before.orc"] = typed_before
        sources[f"typed.{seed}.after.orc"] = typed_source
        sources[f"candidate.{seed}.after.orc"] = candidate
        dynamic = _dynamic_run(
            dynamic_root / seed,
            seed=seed,
            limit=limit,
            utility_source_text=utility_after,
            candidate_source_text=candidate,
            review_script=probe_after,
        )
        assert "error" not in dynamic, dynamic.get("error")
        assert dynamic["value"] == expected
        assert typed["status"] == "completed"
        typed_value = _typed_message_value(typed["workflow_outputs"])
        expected_calls = expected_calls_by_seed[seed]
        assert typed_value == dynamic["value"] == expected
        assert typed_events == dynamic["events"] == expected_calls
        outcomes.append({
            "seed": seed,
            "expected": expected,
            "typed_value": typed_value,
            "dynamic_value": dynamic["value"],
            "expected_calls": expected_calls,
            "dynamic_events": dynamic["events"],
            "typed_events": typed_events,
        })

    _save_receipt(
        tmp_path,
        "UE02",
        {
            "typed_boundary_sites": ["Feedback.note schema renamed to message", "review producer approve evidence.note key renamed", "review producer revise feedback.note key renamed"],
            "typed_internal_edit_sites": ["revise candidate argv projection reads feedback.message"],
            "typed_retained_internal_behavior": ["generic helper forwards active F payload opaquely"],
            "typed_duplicated_facts": ["message is named on the distinct approve evidence and revise Feedback payloads"],
            "dynamic_boundary_sites": ["Feedback schema", "compiled review result message projection", "revise leaf input field"],
            "dynamic_internal_edit_sites": [
                "approve normalization wire key return__evidence__note renamed to return__evidence__message",
                "approve normalized evidence field note renamed to message",
                "revise normalization wire key return__feedback__note renamed to return__feedback__message",
                "revise normalized feedback field note renamed to message",
                "revise hook field read feedback.note renamed to feedback.message",
                "revise effect input feedback__note renamed to feedback__message",
            ],
            "dynamic_duplicated_facts": ["message is named on the distinct approve evidence and revise Feedback payloads"],
            "initial_dynamic_failure": {
                "code": dynamic_red["error"].code,
                "location": dynamic_red["error"].location,
                "validator_error": dynamic_red["error"].metadata["validator_error"],
                "calls": dynamic_red["events"],
            },
            "late_dynamic_failure": {
                "code": dynamic_late_red["error"].code,
                "location": dynamic_late_red["error"].location,
                "expected_inputs": dynamic_late_red["error"].metadata["expected_inputs"],
                "calls": dynamic_late_red["events"],
            },
            "outcomes": outcomes,
            "concepts": ["union payload field rename", "strict transport contract update", "consumer projection update"],
            "observed_repairs": [
                "after result-contract rejection, rename the two branch-local normalized payload field labels",
                "after review-only execution, rename the feedback__note revise input to feedback__message",
            ],
            "timing": "unmeasured",
        },
        sources,
    )
    assert dynamic_red["error"].code == "dynamic_boundary_invalid"
    assert dynamic_red["error"].location == "/result"
    assert dynamic_red["error"].metadata["validator_error"] == "$/evidence record fields are missing or extra"
    assert dynamic_red["events"] == [{"hook": "review", "argv": ["approve", "tidy"]}]
    assert dynamic_late_red["error"].code == "dynamic_boundary_invalid"
    assert dynamic_late_red["error"].location.endswith("revise-hook/body/bindings/0/1")
    assert dynamic_late_red["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]


def _rubric_review_probe() -> str:
    source = _replace_once(REVIEW_PROBE, "title, goal = sys.argv[1], sys.argv[2]", "title, goal, rubric = sys.argv[1], sys.argv[2], sys.argv[3]")
    source = _replace_once(source, '"ok:" + title + ":" + goal', '"ok:" + title + ":" + goal + ":" + rubric')
    return _replace_once(source, '"fb" + str(title.count("+r"))', '"fb" + str(title.count("+r")) + ":" + rubric')


def _rubric_typed_entry(probes: dict[str, Path], *, limit: int) -> str:
    source = entry_source(seed="draft", limit=limit, probes=probes)
    source = _replace_once(source, "(defrecord Brief (goal String))", "(defrecord Brief (goal String) (rubric String))")
    source = _replace_once(source, "candidate.title brief.goal)", "candidate.title brief.goal brief.rubric)")
    return _replace_once(source, '(record Brief :goal "tidy")', '(record Brief :goal "tidy" :rubric "clarity")')


def _rubric_utility_source() -> str:
    source = UTILITY_LEAVES.read_text(encoding="utf-8")
    source = _replace_once(
        source,
        "((draft Draft) (goal String))\n    -> Decision[Feedback Blocker]",
        "((draft Draft) (goal String) (rubric String))\n    -> Decision[Feedback Blocker]",
    )
    return _replace_once(source, "draft.title goal)\n      :returns Decision[Feedback Blocker]", "draft.title goal rubric)\n      :returns Decision[Feedback Blocker]")


def _captured_rubric_candidate(source: str) -> str:
    review_start = source.index("(define (review-hook current)")
    revise_start = source.index("(define (revise-hook current feedback)", review_start)
    run_start = source.index("  (run (improve ", revise_start)
    review_and_revise = '''(define (review-for goal rubric)
  (fn (current)
    (let* ((wire (effect review (record (draft__title (field current "title"))
                                        (draft__score (field current "score"))
                                        (goal goal)
                                        (rubric rubric)))))
      (normalize-review wire))))
(define (revise-for goal)
  (fn (current feedback)
    (let* ((wire (effect revise (record
                 (draft__title (field current "title"))
                 (draft__score (field current "score"))
                 (goal goal)
                 (feedback__note (field feedback "note"))))))
      (record (title (field wire "return__title"))
              (score (field wire "return__score"))))))
'''
    source = source[:review_start] + review_and_revise + source[run_start:]
    return _replace_once(
        source,
        "review-hook revise-hook 1)))",
        '(review-for "tidy" "clarity") (revise-for "tidy") 1)))',
    )


def test_UE03_review_captures_rubric_independently_and_revision_uses_goal(tmp_path: Path) -> None:
    typed_root, dynamic_root = tmp_path / "typed", tmp_path / "dynamic"
    typed_probe_paths = {
        "probe_review": typed_root / "probe_review.py",
        "probe_revise": typed_root / "probe_revise.py",
    }
    probe_before = REVIEW_PROBE
    probe_after = _rubric_review_probe()
    typed_before = entry_source(seed="draft", limit=1, probes=typed_probe_paths)
    typed_source = _rubric_typed_entry(typed_probe_paths, limit=1)
    utility_before = UTILITY_LEAVES.read_text(encoding="utf-8")
    utility_after = _rubric_utility_source()
    dynamic_root.mkdir(parents=True)
    candidate_path = _candidate_source(
        dynamic_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = candidate_path.read_text(encoding="utf-8")
    candidate_after = _captured_rubric_candidate(candidate_before)
    typed, typed_calls = _typed_run(
        typed_root,
        seed="draft",
        limit=1,
        entry_source_text=typed_source,
        review_script=probe_after,
    )
    dynamic = _dynamic_run(
        dynamic_root,
        seed="draft",
        limit=1,
        utility_source_text=utility_after,
        candidate_source_text=candidate_after,
        review_script=probe_after,
    )
    expected_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    expected_calls = [
        {"hook": "review", "argv": ["draft", "tidy", "clarity"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0:clarity"]},
    ]
    typed_value = {
        "variant": typed["workflow_outputs"]["return__variant"],
        "value": {
            "title": typed["workflow_outputs"]["return__value__title"],
            "score": typed["workflow_outputs"]["return__value__score"],
        },
    }
    _save_receipt(
        tmp_path,
        "UE03",
        {
            "typed_boundary_sites": ["Brief.rubric declaration", "review command consumes Brief.rubric", "explicit Brief passed to std/improve"],
            "typed_retained_internal_behavior": ["unchanged std/improve plumbing passes the same Brief to both hooks; revise consumes only Brief.goal"],
            "typed_duplicated_facts": ["the shared Brief is passed to both hooks although revise needs only goal"],
            "dynamic_boundary_sites": ["review leaf rubric input and argv"],
            "dynamic_internal_state_sites": ["review closure captures goal and rubric", "revise closure separately captures goal"],
            "dynamic_duplicated_facts": ["goal literal is captured at both review and revise closure construction sites"],
            "typed_value": typed_value,
            "dynamic_value": dynamic.get("value"),
            "typed_calls": typed_calls,
            "dynamic_calls": dynamic.get("events"),
            "credit": ["the existing typed helper already accepts a single String context", "W3 is proposed and not implemented"],
            "observed_repairs": [],
            "timing": "unmeasured",
        },
        {
            "typed.before.orc": typed_before,
            "typed.after.orc": typed_source,
            "utility.before.orc": utility_before,
            "utility.after.orc": utility_after,
            "candidate.before.orc": candidate_before,
            "candidate.after.orc": candidate_after,
            "probe_review.before.py": probe_before,
            "probe_review.after.py": probe_after,
        },
    )
    assert "error" not in dynamic, dynamic.get("error")
    assert typed["status"] == "completed"
    assert dynamic["value"] == typed_value == expected_value
    assert dynamic["events"] == typed_calls == expected_calls


def _typed_feedback_helper_entry(probes: dict[str, Path], *, limit: int) -> str:
    source = entry_source(seed="draft", limit=limit, probes=probes)
    declaration = (
        "  (defproc feedback-to-revision-input ((feedback Feedback)) -> String\n"
        "    :effects ()\n"
        "    :lowering inline\n"
        "    feedback.note)\n"
    )
    source = _replace_once(source, "  (defrecord Blocker (why String))\n", declaration + "  (defrecord Blocker (why String))\n")
    start = source.index("  (defproc revise-candidate\n")
    end = source.index("  (defworkflow run", start)
    revise = source[start:end]
    revise = _replace_once(
        revise,
        "    (command-result probe_revise\n",
        "    (let* ((revision-note (feedback-to-revision-input feedback)))\n"
        "      (command-result probe_revise\n",
    )
    revise = _replace_once(revise, "feedback.note)", "revision-note)")
    revise = _replace_once(revise, ":returns Candidate))", ":returns Candidate)))")
    return source[:start] + revise + source[end:]


def _dynamic_feedback_helper_candidate(source: str) -> str:
    helper = (
        '(define (feedback-to-revision-input feedback)\n'
        '  (field feedback "note"))\n'
    )
    source = _replace_once(source, "(define (normalize-review wire)", helper + "(define (normalize-review wire)")
    return _replace_once(
        source,
        '(feedback__note (field feedback "note"))',
        '(feedback__note (feedback-to-revision-input feedback))',
    )


def test_UE04_pure_feedback_helper_preserves_payload_and_effect_order(tmp_path: Path) -> None:
    typed_root, dynamic_root = tmp_path / "typed", tmp_path / "dynamic"
    typed_probes = {
        "probe_review": typed_root / "probe_review.py",
        "probe_revise": typed_root / "probe_revise.py",
    }
    typed_before = entry_source(seed="draft", limit=1, probes=typed_probes)
    typed_after = _typed_feedback_helper_entry(typed_probes, limit=1)
    dynamic_root.mkdir(parents=True)
    candidate_path = _candidate_source(
        dynamic_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = candidate_path.read_text(encoding="utf-8")
    candidate_after = _dynamic_feedback_helper_candidate(candidate_before)
    typed, typed_calls = _typed_run(
        typed_root,
        seed="draft",
        limit=1,
        entry_source_text=typed_after,
    )
    dynamic = _dynamic_run(
        dynamic_root,
        seed="draft",
        limit=1,
        candidate_source_text=candidate_after,
    )
    expected_calls = [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
    ]
    typed_value = {
        "variant": typed["workflow_outputs"]["return__variant"],
        "value": {
            "title": typed["workflow_outputs"]["return__value__title"],
            "score": typed["workflow_outputs"]["return__value__score"],
        },
    }
    expected_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    _save_receipt(
        tmp_path,
        "UE04",
        {
            "typed_value": typed_value,
            "dynamic_value": dynamic.get("value"),
            "typed_calls": typed_calls,
            "dynamic_calls": dynamic.get("events"),
            "typed_boundary_sites": ["pure helper accepts Feedback and returns String", "revision leaf consumes projected String"],
            "typed_internal_edit_sites": ["feedback.note projection moved from revise argv into one pure helper"],
            "typed_duplicated_facts": [],
            "dynamic_boundary_sites": ["caller-local pure helper accepts normalized Feedback and returns String", "revision effect consumes projected String"],
            "dynamic_internal_edit_sites": ["feedback.note projection moved from revise effect input into one pure helper"],
            "dynamic_duplicated_facts": [],
            "concepts": ["typed pure defproc call", "ordinary pure dynamic function call", "unchanged leaf contract"],
            "observed_repairs": [],
            "timing": "unmeasured",
        },
        {
            "typed.before.orc": typed_before,
            "typed.after.orc": typed_after,
            "candidate.before.orc": candidate_before,
            "candidate.after.orc": candidate_after,
        },
    )
    assert "error" not in dynamic, dynamic.get("error")
    assert typed["status"] == "completed"
    assert dynamic["value"] == typed_value == expected_value
    assert dynamic["events"] == typed_calls == expected_calls


def test_UD01_unbound_lexical_name_fails_at_compile_before_any_dispatch(tmp_path: Path) -> None:
    typed_root, dynamic_root = tmp_path / "typed", tmp_path / "dynamic"
    typed_probe_paths = {
        "probe_review": typed_root / "probe_review.py",
        "probe_revise": typed_root / "probe_revise.py",
    }
    typed_before = entry_source(seed="draft", limit=1, probes=typed_probe_paths)
    typed_bad = _replace_once(typed_before, "candidate.title brief.goal)", "candidate.title missing_goal)")
    dynamic_root.mkdir(parents=True)
    candidate_path = _candidate_source(
        dynamic_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = candidate_path.read_text(encoding="utf-8")
    assert candidate_before.count('(goal "tidy")') == 2
    candidate_bad = candidate_before.replace('(goal "tidy")', "(goal missing_rubric)", 1)
    with pytest.raises(EvaluatedValueError) as dynamic_error:
        _dynamic_run(dynamic_root / "bad", seed="draft", limit=1, candidate_source_text=candidate_bad)
    with pytest.raises(LispFrontendCompileError) as typed_error:
        _typed_run(typed_root / "bad", seed="draft", limit=1, entry_source_text=typed_bad)

    dynamic_error_info = {
        "code": dynamic_error.value.code,
        "location": dynamic_error.value.location,
        "message": str(dynamic_error.value),
    }
    typed_diagnostic = typed_error.value.diagnostics[0]
    typed_error_info = {
        "code": typed_diagnostic.code,
        "location": {
            "line": typed_diagnostic.span.start.line,
            "column": typed_diagnostic.span.start.column,
        },
        "message": typed_diagnostic.message,
    }
    assert dynamic_error.value.code == "dynamic_source_invalid"
    assert "unbound name 'missing_rubric'" in str(dynamic_error.value)
    assert ":42:" in dynamic_error.value.location
    assert typed_diagnostic.code == "name_unknown"
    assert typed_diagnostic.message == "unknown name `missing_goal`"
    assert typed_diagnostic.span.start.line == 17
    assert _events(dynamic_root / "bad") == _events(typed_root / "bad") == []
    assert not (dynamic_root / "bad/.orchestrate/runs").exists()
    assert not (typed_root / "bad/.orchestrate/runs").exists()

    typed_repaired, typed_repaired_calls = _typed_run(typed_root / "repaired", seed="draft", limit=1)
    dynamic_repaired = _dynamic_run(
        dynamic_root / "repaired",
        seed="draft",
        limit=1,
        candidate_source_text=candidate_before,
    )
    typed_repaired_value = _typed_domain_result(typed_repaired["workflow_outputs"])
    expected_repaired_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    expected_repaired_calls = [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
    ]
    _save_receipt(
        tmp_path,
        "UD01",
        {
            "dynamic_error": dynamic_error_info,
            "typed_error": typed_error_info,
            "dynamic_stage": "source admission before evaluation",
            "typed_stage": "frontend name validation before execution",
            "dynamic_calls": _events(dynamic_root / "bad"),
            "typed_calls": _events(typed_root / "bad"),
            "repaired_dynamic_value": dynamic_repaired.get("value"),
            "repaired_typed_value": typed_repaired_value,
            "expected_repaired_value": expected_repaired_value,
            "repaired_dynamic_calls": dynamic_repaired.get("events"),
            "repaired_typed_calls": typed_repaired_calls,
            "expected_repaired_calls": expected_repaired_calls,
            "concepts": ["lexical name binding", "source-location diagnostics"],
            "observed_repairs": ["replace dynamic missing name with goal and typed missing name with brief.goal, then rerun"],
            "timing": "unmeasured",
        },
        {
            "typed.before.orc": typed_before,
            "typed.invalid.orc": typed_bad,
            "candidate.before.orc": candidate_before,
            "candidate.invalid.orc": candidate_bad,
        },
    )
    assert "error" not in dynamic_repaired, dynamic_repaired.get("error")
    assert typed_repaired["status"] == "completed"
    assert dynamic_repaired["value"] == typed_repaired_value == expected_repaired_value
    assert dynamic_repaired["events"] == typed_repaired_calls == expected_repaired_calls


def _identity_dynamic_candidate(source: str) -> str:
    return _replace_once(source, "(define (normalize-review wire)", "(define (identity value) value)\n(define (normalize-review wire)")


def _typed_identity_arity_entry(probes: dict[str, Path], *, site: str) -> str:
    source = entry_source(seed="draft", limit=1, probes=probes)
    identity = (
        "  (defproc identity ((value String)) -> String\n"
        "    :effects ()\n"
        "    :lowering inline\n"
        "    value)\n"
    )
    source = _replace_once(source, "  (defproc review-candidate\n", identity + "  (defproc review-candidate\n")
    if site == "before-effect":
        return _replace_once(source, "candidate.title brief.goal)", 'candidate.title (identity "tidy" "extra"))')
    assert site == "after-review"
    return _replace_once(source, "feedback.note)", ' (identity feedback.note "extra"))')


def _dynamic_arity_source(source: str, *, site: str) -> str:
    source = _identity_dynamic_candidate(source)
    if site == "before-effect":
        assert source.count('(goal "tidy")') == 2
        return source.replace('(goal "tidy")', '(goal (identity "tidy" "extra"))', 1)
    assert site == "after-review"
    return _replace_once(source, '(field feedback "note")', '(field (identity feedback "extra") "note")')


def test_UD02_wrong_call_arity_costs_zero_or_one_completed_review_and_one_site_repair(tmp_path: Path) -> None:
    dynamic_root = tmp_path / "dynamic"
    dynamic_root.mkdir()
    candidate_path = _candidate_source(
        dynamic_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = candidate_path.read_text(encoding="utf-8")
    before_bad = _dynamic_arity_source(candidate_before, site="before-effect")
    after_bad = _dynamic_arity_source(candidate_before, site="after-review")
    repaired = _replace_once(after_bad, '(identity feedback "extra")', '(identity feedback)')
    before = _dynamic_run(dynamic_root / "before", seed="draft", limit=1, candidate_source_text=before_bad)
    after = _dynamic_run(dynamic_root / "after", seed="draft", limit=1, candidate_source_text=after_bad)
    dynamic_final = _dynamic_run(dynamic_root / "repaired", seed="draft", limit=1, candidate_source_text=repaired)

    typed_before_root, typed_after_root = tmp_path / "typed-before", tmp_path / "typed-after"
    typed_before_paths = {
        "probe_review": typed_before_root / "probe_review.py",
        "probe_revise": typed_before_root / "probe_revise.py",
    }
    typed_after_paths = {
        "probe_review": typed_after_root / "probe_review.py",
        "probe_revise": typed_after_root / "probe_revise.py",
    }
    typed_before_bad = _typed_identity_arity_entry(typed_before_paths, site="before-effect")
    typed_after_bad = _typed_identity_arity_entry(typed_after_paths, site="after-review")
    with pytest.raises(LispFrontendCompileError) as typed_before_error:
        _typed_run(typed_before_root, seed="draft", limit=1, entry_source_text=typed_before_bad)
    with pytest.raises(LispFrontendCompileError) as typed_after_error:
        _typed_run(typed_after_root, seed="draft", limit=1, entry_source_text=typed_after_bad)
    typed_final, typed_calls = _typed_run(tmp_path / "typed-repaired", seed="draft", limit=1)

    error_info = lambda error: {
        "code": error.code,
        "location": error.location,
        "metadata": error.metadata,
    }
    _save_receipt(
        tmp_path,
        "UD02",
        {
            "dynamic_before_effect": {**error_info(before["error"]), "calls": before["events"], "states": before["states"]},
            "dynamic_after_review": {**error_info(after["error"]), "calls": after["events"], "states": after["states"]},
            "typed_before_effect": {
                "code": typed_before_error.value.diagnostics[0].code,
                "line": typed_before_error.value.diagnostics[0].span.start.line,
            },
            "typed_after_review": {
                "code": typed_after_error.value.diagnostics[0].code,
                "line": typed_after_error.value.diagnostics[0].span.start.line,
            },
            "repaired_dynamic_value": dynamic_final.get("value"),
            "repaired_typed_outputs": typed_final.get("workflow_outputs"),
            "repaired_dynamic_calls": dynamic_final.get("events"),
            "repaired_typed_calls": typed_calls,
            "concepts": ["ordinary function arity", "effect-prefix accounting", "one-site repair"],
            "observed_repairs": ["remove the extra argument at revise-hook's identity call, then rerun"],
            "timing": "unmeasured",
        },
        {
            "candidate.before.orc": candidate_before,
            "candidate.before-effect-invalid.orc": before_bad,
            "candidate.after-review-invalid.orc": after_bad,
            "candidate.repaired.orc": repaired,
            "typed.before-effect-invalid.orc": typed_before_bad,
            "typed.after-review-invalid.orc": typed_after_bad,
        },
    )
    assert before["error"].code == after["error"].code == "dynamic_call_arity"
    assert before["events"] == []
    assert before["states"] == []
    assert after["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert len(after["states"]) == 1 and after["states"][0]["status"] == "completed"
    assert typed_before_error.value.diagnostics[0].code == typed_after_error.value.diagnostics[0].code == "procedure_arity_mismatch"
    assert _events(typed_before_root) == _events(typed_after_root) == []
    assert dynamic_final["value"] == {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    assert typed_final["status"] == "completed"
    assert dynamic_final["events"] == typed_calls == [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
    ]


def test_UD03_missing_internal_field_fails_after_review_then_one_site_repair(tmp_path: Path) -> None:
    dynamic_root = tmp_path / "dynamic"
    dynamic_root.mkdir()
    candidate_path = _candidate_source(
        dynamic_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    )
    candidate_before = candidate_path.read_text(encoding="utf-8")
    candidate_invalid = _replace_once(candidate_before, '(field feedback "note")', '(field feedback "missing")')
    dynamic_bad = _dynamic_run(
        dynamic_root / "invalid",
        seed="draft",
        limit=1,
        candidate_source_text=candidate_invalid,
    )
    dynamic_repaired = _dynamic_run(
        dynamic_root / "repaired",
        seed="draft",
        limit=1,
        candidate_source_text=candidate_before,
    )

    typed_root = tmp_path / "typed"
    typed_invalid_root = typed_root / "invalid"
    typed_probes = {
        "probe_review": typed_invalid_root / "probe_review.py",
        "probe_revise": typed_invalid_root / "probe_revise.py",
    }
    typed_before = entry_source(seed="draft", limit=1, probes=typed_probes)
    typed_invalid = _replace_once(typed_before, "feedback.note)", "feedback.missing)")
    with pytest.raises(LispFrontendCompileError) as typed_error:
        _typed_run(typed_invalid_root, seed="draft", limit=1, entry_source_text=typed_invalid)
    typed_repaired, typed_calls = _typed_run(typed_root / "repaired", seed="draft", limit=1)
    diagnostic = typed_error.value.diagnostics[0]
    review_output = dynamic_bad["states"][0]["workflow_outputs"]
    dynamic_value = dynamic_repaired.get("value")
    typed_value = _typed_domain_result(typed_repaired["workflow_outputs"])
    expected_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    expected_calls = [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
    ]
    _save_receipt(
        tmp_path,
        "UD03",
        {
            "dynamic_error": {
                "code": dynamic_bad["error"].code,
                "location": dynamic_bad["error"].location,
                "metadata": {
                    **{key: value for key, value in dynamic_bad["error"].metadata.items()
                       if key != "call_context"},
                    "call_context": [list(frame) for frame in dynamic_bad["error"].metadata["call_context"]],
                },
            },
            "dynamic_effect_prefix": dynamic_bad["events"],
            "dynamic_completed_leaf_outputs": [state["workflow_outputs"] for state in dynamic_bad["states"]],
            "dynamic_remaining_operations": ["revise"],
            "dynamic_leaf_states": dynamic_bad["states"],
            "typed_compile_diagnostic": {
                "code": diagnostic.code,
                "message": diagnostic.message,
                "line": diagnostic.span.start.line,
                "column": diagnostic.span.start.column,
                "typed_effects": _events(typed_root / "invalid"),
            },
            "repaired_dynamic_value": dynamic_value,
            "repaired_typed_value": typed_value,
            "expected_value": expected_value,
            "dynamic_calls": dynamic_repaired["events"],
            "typed_calls": typed_calls,
            "expected_calls": expected_calls,
            "concepts": ["dynamic field lookup at reached hook", "typed field validation at compile time", "partial leaf publication"],
            "observed_repairs": ["change the one revise-hook field projection back to note and rerun"],
            "timing": "unmeasured",
        },
        {
            "candidate.before.orc": candidate_before,
            "candidate.invalid.orc": candidate_invalid,
            "typed.before.orc": typed_before,
            "typed.invalid.orc": typed_invalid,
        },
    )
    assert dynamic_bad["error"].code == "dynamic_field_missing"
    assert dynamic_bad["error"].location.endswith("/inputs/fields/3/1")
    assert dynamic_bad["error"].metadata["steps"] > 0
    assert dynamic_bad["error"].metadata["call_context"][-1][2] == "helper/revise-hook"
    assert dynamic_bad["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert len(dynamic_bad["states"]) == 1 and dynamic_bad["states"][0]["status"] == "completed"
    assert review_output == {"return__variant": "REVISE", "return__feedback__note": "fb0"}
    assert diagnostic.code == "record_field_unknown"
    assert diagnostic.message == "unknown field `missing`"
    assert diagnostic.span.start.line == 25
    assert _events(typed_root / "invalid") == []
    assert "error" not in dynamic_repaired
    assert typed_repaired["status"] == "completed"
    assert dynamic_value == typed_value == expected_value
    assert dynamic_repaired["events"] == typed_calls == expected_calls


def test_UD04_budget_failure_after_completed_effect_is_repaired_by_a_fresh_run(tmp_path: Path) -> None:
    dynamic_root = tmp_path / "dynamic"
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True)
    candidate_before = _candidate_source(
        source_root,
        seed="draft",
        limit=1,
        goal="tidy",
        helper_definitions=IMPROVE_DEFINITIONS.read_text(encoding="utf-8"),
        helper_name="improve",
    ).read_text(encoding="utf-8")
    failed = _dynamic_run(
        dynamic_root / "budget-80",
        seed="draft",
        limit=1,
        candidate_source_text=candidate_before,
        budget=80,
    )
    repaired = _dynamic_run(
        dynamic_root / "budget-1000",
        seed="draft",
        limit=1,
        candidate_source_text=candidate_before,
    )
    typed, typed_calls = _typed_run(tmp_path / "typed", seed="draft", limit=1)
    error = failed["error"]
    typed_value = _typed_domain_result(typed["workflow_outputs"])
    expected_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    expected_calls = [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
    ]
    _save_receipt(
        tmp_path,
        "UD04",
        {
            "dynamic_error": {
                "code": error.code,
                "location": error.location,
                "metadata": {
                    **{key: value for key, value in error.metadata.items() if key != "call_context"},
                    "call_context": [list(frame) for frame in error.metadata["call_context"]],
                },
            },
            "dynamic_completed_effect_prefix": failed["events"],
            "dynamic_completed_leaf_outputs": [state["workflow_outputs"] for state in failed["states"]],
            "dynamic_leaf_states": failed["states"],
            "fresh_rerun_value": repaired.get("value"),
            "typed_value": typed_value,
            "expected_value": expected_value,
            "fresh_rerun_calls": repaired["events"],
            "typed_calls": typed_calls,
            "expected_calls": expected_calls,
            "recovery": "dynamic evaluation has no saved continuation; the checked comparison uses an explicit fresh run at the default budget",
            "concepts": ["deterministic VM node budget", "completed side effect before VM failure", "fresh run rather than continuation resume"],
            "observed_repairs": ["raise the admitted source budget from 80 to 1000 and rerun"],
            "timing": "unmeasured",
        },
        {
            "candidate.before.orc": candidate_before,
            "candidate.budget-80.orc": failed["source"],
            "candidate.budget-1000.orc": repaired["source"],
        },
    )
    assert error.code == "dynamic_budget_exhausted"
    assert error.location == "/definitions/helper~1revise-hook/body/bindings/0/1"
    assert error.metadata["steps"] == 80
    assert error.metadata["call_context"][-1][2] == "helper/revise-hook"
    assert failed["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert len(failed["states"]) == 1 and failed["states"][0]["status"] == "completed"
    assert failed["states"][0]["workflow_outputs"] == {"return__variant": "REVISE", "return__feedback__note": "fb0"}
    assert "error" not in repaired
    assert typed["status"] == "completed"
    assert repaired["value"] == typed_value == expected_value
    assert repaired["events"] == typed_calls == expected_calls


def _events_from_typed_hook_logs(calls: tuple[list[str], list[str]]) -> list[dict[str, object]]:
    reviews, revisions = calls
    events = []
    for index, review in enumerate(reviews):
        events.append({"hook": "review", "argv": review.split()})
        if index < len(revisions):
            events.append({"hook": "revise", "argv": revisions[index].split()})
    return events


def test_UD05_dynamic_restart_repeats_effect_pair_while_typed_resume_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_workflow_lisp_generic_unions_runtime import _public_run_files
    from tests.test_workflow_lisp_improve_stdlib import (
        _hook_calls,
        _resume,
        _run_until_the_first_committed_iteration,
        _write_project,
    )

    class AfterDynamicPair(BaseException):
        pass

    dynamic_root = tmp_path / "dynamic"
    observed_outputs: list[dict[str, object]] = []

    def interrupt_after_revise(operation: str, output: object) -> None:
        observed_outputs.append({"operation": operation, "result": dict(output)})
        if operation == "revise":
            raise AfterDynamicPair

    with pytest.raises(AfterDynamicPair):
        _dynamic_run(
            dynamic_root,
            seed="draft",
            limit=3,
            after_effect=interrupt_after_revise,
        )
    dynamic_prefix = _events(dynamic_root)
    dynamic_states_before = _dynamic_leaf_states(dynamic_root)
    first_run_ids = {state["run_id"] for state in dynamic_states_before}
    dynamic_files_before = sorted(
        path.relative_to(dynamic_root).as_posix()
        for run_id in first_run_ids
        for path in (dynamic_root / ".orchestrate" / "runs" / run_id).rglob("*")
        if path.is_file()
    )
    candidate_source = (dynamic_root / "candidate.orc").read_text(encoding="utf-8")
    artifact_before = (dynamic_root / "candidate.json").read_text(encoding="utf-8")
    dynamic_final = _dynamic_run(dynamic_root, seed="draft", limit=3)
    dynamic_all_events = dynamic_final["events"]
    dynamic_states_after = _dynamic_leaf_states(dynamic_root)
    artifact_after = (dynamic_root / "candidate.json").read_text(encoding="utf-8")

    typed_root = tmp_path / "typed"
    probes = _write_project(typed_root, seed="draft", limit=3)
    typed_source = (typed_root / "grt/entry.orc").read_text(encoding="utf-8")
    monkeypatch.chdir(typed_root)
    files = _public_run_files(typed_root, probes)
    typed_run_id = _run_until_the_first_committed_iteration(monkeypatch, files)
    typed_partial = json.loads((typed_root / ".orchestrate/runs" / typed_run_id / "state.json").read_text(encoding="utf-8"))
    typed_prefix = _hook_calls(probes)
    typed_final = _resume(typed_run_id)
    typed_all_calls = _hook_calls(probes)
    typed_interleaving_from_separate_logs = _events_from_typed_hook_logs(typed_all_calls)

    expected_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}
    expected_events = [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]},
        {"hook": "review", "argv": ["draft+r", "tidy"]},
        {"hook": "revise", "argv": ["draft+r", "tidy", "fb1"]},
        {"hook": "review", "argv": ["draft+r+r", "tidy"]},
        {"hook": "revise", "argv": ["draft+r+r", "tidy", "fb2"]},
    ]
    expected_dynamic_restart_events = expected_events[:2] + expected_events
    dynamic_files_after = sorted(
        path.relative_to(dynamic_root).as_posix()
        for path in dynamic_root.rglob("*")
        if path.is_file() and ".orchestrate/runs" in path.as_posix()
    )
    _save_receipt(
        tmp_path,
        "UD05",
        {
            "dynamic_interruption": "observer raised immediately after the real revise leaf returned successfully",
            "dynamic_observed_leaf_outputs": observed_outputs,
            "dynamic_prefix_before_restart": dynamic_prefix,
            "dynamic_states_before_restart": dynamic_states_before,
            "dynamic_persisted_state_files_before_restart": dynamic_files_before,
            "dynamic_events_after_fresh_run": dynamic_all_events,
            "compiled_artifact_before_and_after_are_identical": artifact_before == artifact_after,
            "dynamic_states_after_fresh_run": dynamic_states_after,
            "dynamic_first_run_ids_retained": sorted(first_run_ids & {state["run_id"] for state in dynamic_states_after}),
            "typed_committed_prefix_before_resume": typed_prefix,
            "typed_interrupted_state": {
                "run_id": typed_run_id,
                "status": typed_partial["status"],
                "workflow_outputs": typed_partial.get("workflow_outputs"),
            },
            "typed_calls_after_resume": typed_all_calls,
            "typed_interleaving_derived_from_separate_hook_logs": typed_interleaving_from_separate_logs,
            "typed_event_order_note": "separate per-hook log arrays are interleaved for display; typed_calls_after_resume are the directly observed records",
            "dynamic_final_value": dynamic_final.get("value"),
            "typed_final_value": _typed_domain_result(typed_final["workflow_outputs"]),
            "expected_value": expected_value,
            "expected_events": expected_events,
            "expected_dynamic_events_after_restart": expected_dynamic_restart_events,
            "concepts": ["completed side effects", "fresh dynamic source execution", "public typed run resume from committed iteration"],
            "observed_repairs": [],
            "timing": "unmeasured",
        },
        {
            "candidate.orc": candidate_source,
            "typed.entry.orc": typed_source,
        },
    )
    assert dynamic_prefix == expected_events[:2]
    assert [item["operation"] for item in observed_outputs] == ["review", "revise"]
    assert len(dynamic_states_before) == 2 and all(state["status"] == "completed" for state in dynamic_states_before)
    assert dynamic_files_before
    assert "error" not in dynamic_final
    assert first_run_ids <= {state["run_id"] for state in dynamic_states_after}
    assert set(dynamic_files_before) <= set(dynamic_files_after)
    assert artifact_before == artifact_after
    assert dynamic_all_events == expected_dynamic_restart_events
    assert typed_prefix == (["draft tidy"], ["draft tidy fb0"])
    assert typed_partial["status"] != "completed"
    assert typed_final["status"] == "completed"
    assert typed_all_calls == (
        ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
        ["draft tidy fb0", "draft+r tidy fb1", "draft+r+r tidy fb2"],
    )
    assert dynamic_final["value"] == _typed_domain_result(typed_final["workflow_outputs"]) == expected_value


def test_UD06_captured_goal_restart_repeats_while_typed_string_input_resume_preserves_goal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_workflow_lisp_generic_unions_runtime import _public_run_files
    from tests.test_workflow_lisp_improve_stdlib import (
        _hook_calls,
        _resume,
        _run_until_the_first_committed_iteration,
        _write_project,
    )

    class AfterDynamicPair(BaseException):
        pass

    dynamic_root = tmp_path / "dynamic"
    dynamic_observed: list[str] = []

    def interrupt_after_revise(operation: str, _output: object) -> None:
        dynamic_observed.append(operation)
        if operation == "revise":
            raise AfterDynamicPair

    with pytest.raises(AfterDynamicPair):
        _dynamic_run(
            dynamic_root,
            seed="draft",
            limit=3,
            goal="steady",
            wrapped=True,
            after_effect=interrupt_after_revise,
        )
    dynamic_prefix = _events(dynamic_root)
    first_dynamic_states = _dynamic_leaf_states(dynamic_root)
    first_run_ids = {state["run_id"] for state in first_dynamic_states}
    candidate_source = (dynamic_root / "candidate.orc").read_text(encoding="utf-8")
    dynamic_final = _dynamic_run(dynamic_root, seed="draft", limit=3, goal="steady", wrapped=True)
    dynamic_all_events = dynamic_final["events"]
    all_dynamic_states = _dynamic_leaf_states(dynamic_root)

    typed_root = tmp_path / "typed"
    probes = _write_project(typed_root, seed="draft", limit=3)
    entry_path = typed_root / "grt/entry.orc"
    typed_before = entry_path.read_text(encoding="utf-8")
    typed_source = string_inputs_entry_source(typed_before)
    entry_path.write_text(typed_source, encoding="utf-8")
    inputs = typed_root / "inputs.json"
    inputs.write_text(json.dumps({"goal": "steady"}), encoding="utf-8")
    monkeypatch.chdir(typed_root)
    files = _public_run_files(typed_root, probes)
    typed_run_id = _run_until_the_first_committed_iteration(monkeypatch, files, input_file=inputs)
    typed_partial = json.loads((typed_root / ".orchestrate/runs" / typed_run_id / "state.json").read_text(encoding="utf-8"))
    typed_prefix = _hook_calls(probes)
    typed_final = _resume(typed_run_id)
    typed_all_calls = _hook_calls(probes)
    typed_interleaving_from_separate_logs = _events_from_typed_hook_logs(typed_all_calls)

    expected_value = {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}
    expected_events = [
        {"hook": "review", "argv": ["draft", "steady"]},
        {"hook": "revise", "argv": ["draft", "steady", "fb0"]},
        {"hook": "review", "argv": ["draft+r", "steady"]},
        {"hook": "revise", "argv": ["draft+r", "steady", "fb1"]},
        {"hook": "review", "argv": ["draft+r+r", "steady"]},
        {"hook": "revise", "argv": ["draft+r+r", "steady", "fb2"]},
    ]
    expected_dynamic_restart_events = expected_events[:2] + expected_events
    _save_receipt(
        tmp_path,
        "UD06",
        {
            "dynamic_context": "goal is captured by review-for/revise-for closures",
            "dynamic_interruption": "observer raised after the actual revise leaf returned",
            "dynamic_effect_prefix": dynamic_prefix,
            "dynamic_observed_operations": dynamic_observed,
            "dynamic_leaf_states_before_restart": first_dynamic_states,
            "dynamic_leaf_states_after_restart": all_dynamic_states,
            "dynamic_first_run_ids_retained": sorted(first_run_ids & {state["run_id"] for state in all_dynamic_states}),
            "dynamic_events_after_restart": dynamic_all_events,
            "typed_context": "String workflow input `goal` supplied by inputs.json",
            "typed_committed_prefix_before_resume": typed_prefix,
            "typed_interrupted_state": {
                "run_id": typed_run_id,
                "status": typed_partial["status"],
                "workflow_outputs": typed_partial.get("workflow_outputs"),
            },
            "typed_calls_after_resume": typed_all_calls,
            "typed_interleaving_derived_from_separate_hook_logs": typed_interleaving_from_separate_logs,
            "typed_event_order_note": "separate per-hook log arrays are interleaved for display; typed_calls_after_resume are the directly observed records",
            "dynamic_final_value": dynamic_final.get("value"),
            "typed_final_value": _typed_domain_result(typed_final["workflow_outputs"]),
            "expected_value": expected_value,
            "expected_events": expected_events,
            "expected_dynamic_events_after_restart": expected_dynamic_restart_events,
            "concepts": ["dynamic lexical closure capture", "typed I=String context", "dynamic fresh execution vs public typed resume"],
            "credit": ["typed inputs already support String context", "proposed W3 capture mechanism is not implemented"],
            "observed_repairs": [],
            "timing": "unmeasured",
        },
        {
            "candidate.orc": candidate_source,
            "typed.entry.orc": typed_source,
            "typed.inputs.json": inputs.read_text(encoding="utf-8"),
        },
    )
    assert dynamic_prefix == expected_events[:2]
    assert dynamic_observed == ["review", "revise"]
    assert len(first_dynamic_states) == 2 and all(state["status"] == "completed" for state in first_dynamic_states)
    assert "error" not in dynamic_final
    assert first_run_ids <= {state["run_id"] for state in all_dynamic_states}
    assert dynamic_all_events == expected_dynamic_restart_events
    assert typed_prefix == (["draft steady"], ["draft steady fb0"])
    assert typed_partial["status"] != "completed"
    assert typed_final["status"] == "completed"
    assert typed_all_calls == (
        ["draft steady", "draft+r steady", "draft+r+r steady"],
        ["draft steady fb0", "draft+r steady fb1", "draft+r+r steady fb2"],
    )
    assert dynamic_final["value"] == _typed_domain_result(typed_final["workflow_outputs"]) == expected_value
