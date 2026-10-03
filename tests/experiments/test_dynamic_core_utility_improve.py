"""UI01–UI11: full improve behavior through dynamic source and compiled leaves."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.workflow_lisp_improve_stdlib_sources import (
    REVIEW_PROBE,
    REVISE_PROBE,
    entry_source,
    inline_entry_source,
    wrapped_review_sources,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "experiments/dynamic_core_evaluation/fixtures"
IMPROVE_DEFINITIONS = FIXTURES / "improve.orc"
UTILITY_LEAVES = FIXTURES / "utility_leaves.orc"
RESULT_TYPE = "Improvement[Draft Feedback Blocker]"
INLINE_IMPROVE_DEFINITIONS = '''(define (inline-improve initial review revise limit)
  (if (<= limit 0)
      (fail "invalid_limit")
      (inline-improve-loop initial review revise limit 0)))
(define (inline-improve-loop current review revise limit iteration)
  (if (= iteration limit)
      (record (variant "EXHAUSTED") (value current))
      (let* ((decision (review current))
             (tag (field decision "variant")))
        (if (= tag "APPROVE")
            (record (variant "APPROVED")
                    (value current)
                    (evidence (field decision "evidence")))
            (if (= tag "BLOCKED")
                (record (variant "BLOCKED")
                        (value current)
                        (reason (field decision "reason")))
                (if (= tag "REVISE")
                    (inline-improve-loop (revise current (field decision "feedback"))
                                         review revise limit (+ iteration 1))
                    (fail "unknown_review_decision")))))))'''


def _write_probes(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    probes = {}
    for name, script, hook in (
        ("probe_review", REVIEW_PROBE, "review"),
        ("probe_revise", REVISE_PROBE, "revise"),
    ):
        marker = '    log.write(" ".join(sys.argv[1:]) + "\\n")\n'
        event_logger = (
            'with open(os.environ["DYNAMIC_IMPROVE_EVENT_LOG"], "a", encoding="utf-8") as events:\n'
            f'    events.write(json.dumps({{"hook": {hook!r}, "argv": sys.argv[1:]}}) + "\\n")\n'
        )
        instrumented = script.replace(marker, marker + event_logger, 1)
        assert instrumented != script
        path = root / f"{name}.py"
        path.write_text(instrumented, encoding="utf-8")
        probes[name] = path
    return probes


def _events(root: Path) -> list[dict[str, object]]:
    path = root / "hook-events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _write_sources(root: Path, sources: dict[str, str]) -> None:
    for relative, source in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def _typed_sources(root: Path, probes: dict[str, Path], *, seed: str, limit: int,
                   inline: bool = False, wrapped: bool = False) -> None:
    entry = entry_source(seed=seed, limit=limit, probes=probes)
    if wrapped:
        _write_sources(root, wrapped_review_sources(entry, probes))
    else:
        _write_sources(root, {"grt/entry.orc": inline_entry_source(entry) if inline else entry})


def _typed_run(root: Path, *, seed: str, limit: int, inline: bool = False,
               wrapped: bool = False) -> tuple[dict[str, object], list[dict[str, object]]]:
    probes = _write_probes(root)
    _typed_sources(root, probes, seed=seed, limit=limit, inline=inline, wrapped=wrapped)
    from tests.test_workflow_lisp_improve_stdlib import _compile
    from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle

    compiled = _compile(root, probes=probes)
    bundle = compiled.validated_bundles_by_name["grt/entry::run"]
    with patch.dict(os.environ, {"DYNAMIC_IMPROVE_EVENT_LOG": str(root / "hook-events.jsonl")}):
        state = _execute_bundle(bundle, workflow_path=root / "grt/entry.orc", workspace=root, run_id="run")
    return state, _events(root)


def _candidate_source(root: Path, *, seed: str, limit: int, goal: str,
                      helper_definitions: str, helper_name: str,
                      wrapped: bool = False) -> Path:
    source_path = root / "candidate.orc"
    normalize_review = '''(define (normalize-review wire)
  (let* ((tag (field wire "return__variant")))
    (if (= tag "APPROVE")
        (record (variant tag) (evidence (record (note (field wire "return__evidence__note")))))
        (if (= tag "BLOCKED")
            (record (variant tag) (reason (record (why (field wire "return__reason__why")))))
            (if (= tag "REVISE")
                (record (variant tag) (feedback (record (note (field wire "return__feedback__note")))))
                (fail "unknown_review_decision"))))))'''
    if wrapped:
        caller_definitions = f'''{normalize_review}
(define (review-for goal)
  (fn (current)
    (let* ((wire (effect review (record (draft__title (field current "title"))
                                        (draft__score (field current "score"))
                                        (goal goal)))))
      (normalize-review wire))))
(define (revise-for goal)
  (fn (current feedback)
    (let* ((wire (effect revise (record
                 (draft__title (field current "title"))
                 (draft__score (field current "score"))
                 (goal goal)
                 (feedback__note (field feedback "note"))))))
      (record (title (field wire "return__title"))
              (score (field wire "return__score"))))))'''
        review_name, revise_name = f'(review-for "{goal}")', f'(revise-for "{goal}")'
    else:
        caller_definitions = f'''{normalize_review}
(define (review-hook current)
  (let* ((wire (effect review (record (draft__title (field current "title"))
                                      (draft__score (field current "score"))
                                      (goal "{goal}")))))
    (normalize-review wire)))
(define (revise-hook current feedback)
  (let* ((wire (effect revise (record
               (draft__title (field current "title"))
               (draft__score (field current "score"))
               (goal "{goal}")
               (feedback__note (field feedback "note"))))))
    (record (title (field wire "return__title"))
            (score (field wire "return__score")))))'''
        review_name, revise_name = "review-hook", "revise-hook"
    source_path.write_text(f'''(dynamic-core
  (:budget 1000)
  (:inputs )
  (:result {RESULT_TYPE})
  (:effects review revise)
{helper_definitions}
{caller_definitions}
  (run ({helper_name} (record (title "{seed}") (score 0)) {review_name} {revise_name} {limit})))
''', encoding="utf-8")
    return source_path


def _dynamic_run(root: Path, *, seed: str, limit: int, goal: str = "tidy",
                 assembled: bool = True, wrapped: bool = False) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    probes = _write_probes(root)
    utility_source = root / "utility_leaves.orc"
    source = UTILITY_LEAVES.read_text(encoding="utf-8")
    source = source.replace("PROBE_REVIEW", probes["probe_review"].as_posix())
    source = source.replace("PROBE_REVISE", probes["probe_revise"].as_posix())
    utility_source.write_text(source, encoding="utf-8")

    from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge
    from experiments.dynamic_core_evaluation.program import DynamicProgram
    from experiments.dynamic_core_evaluation.source import compile_source
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from tests.experiments.test_evaluated_execution_spike_programs import compact_controller

    _unused_sources, compact_boundaries = compact_controller(root)

    bridge = LeafBridge.compile(
        utility_source,
        root,
        operations={
            "review": "utility_leaves::review-draft",
            "revise": "utility_leaves::revise-draft",
        },
        command_boundaries={
            **compact_boundaries,
            **{
                name: ExternalToolBinding(name=name, stable_command=("python", path.as_posix()))
                for name, path in probes.items()
            },
        },
    )
    if assembled:
        helper_definitions = IMPROVE_DEFINITIONS.read_text(encoding="utf-8")
        helper_name = "improve"
        source_owner = "shared-fragment"
    else:
        # This caller owns an independent inline ORC definition set.
        helper_definitions = INLINE_IMPROVE_DEFINITIONS
        helper_name = "inline-improve"
        source_owner = "caller-inline"
    source_path = _candidate_source(
        root,
        seed=seed,
        limit=limit,
        goal=goal,
        helper_definitions=helper_definitions,
        helper_name=helper_name,
        wrapped=wrapped,
    )
    program = compile_source(source_path.read_text(encoding="utf-8"), source_path=source_path,
                             type_env=bridge.type_env)
    artifact_path = root / "candidate.json"
    artifact_path.write_text(program.artifact(), encoding="utf-8")
    restored = DynamicProgram.from_artifact(artifact_path.read_text(encoding="utf-8"))
    assert restored.digest == program.digest
    try:
        with patch.dict(os.environ, {"DYNAMIC_IMPROVE_EVENT_LOG": str(root / "hook-events.jsonl")}):
            result = evaluate(restored, {}, leaf_bridge=bridge)
    except EvaluatedValueError as error:
        states = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (root / ".orchestrate/runs").glob("*/state.json")
        ]
        states.sort(key=lambda state: state["started_at"])
        return {
            "error": error,
            "events": _events(root),
            "states": states,
            "digest": program.digest,
            "source_owner": source_owner,
            "source": source_path.read_text(encoding="utf-8"),
        }
    return {
        "value": result.json_value(),
        "steps": result.steps,
        "events": _events(root),
        "digest": program.digest,
        "source_owner": source_owner,
        "source": source_path.read_text(encoding="utf-8"),
    }


def _typed_domain_result(outputs: dict[str, object]) -> dict[str, object]:
    """Normalize the existing return__ wire projection to its declared union shape."""
    tag = outputs["return__variant"]
    value = {"title": outputs["return__value__title"], "score": outputs["return__value__score"]}
    if tag == "APPROVED":
        return {"variant": tag, "value": value,
                "evidence": {"note": outputs["return__evidence__note"]}}
    if tag == "BLOCKED":
        return {"variant": tag, "value": value,
                "reason": {"why": outputs["return__reason__why"]}}
    return {"variant": tag, "value": value}


def _expected_events(seed: str, limit: int = 3) -> list[dict[str, object]]:
    title, events = seed, []
    for _ in range(limit):
        events.append({"hook": "review", "argv": [title, "tidy"]})
        if title == "malformed" or title.startswith("approve"):
            return events
        if title.startswith("block") and "+r" in title:
            return events
        feedback = f"fb{title.count('+r')}"
        events.append({"hook": "revise", "argv": [title, "tidy", feedback]})
        if title.startswith("fail") and "+r" in title:
            return events
        title += "+r"
    return events


def test_UI01_initial_approval_keeps_the_initial_draft_and_evidence(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="approve", limit=3)
    typed, typed_events = _typed_run(tmp_path / "typed", seed="approve", limit=3)
    expected = {
        "variant": "APPROVED",
        "value": {"title": "approve", "score": 0},
        "evidence": {"note": "ok:approve:tidy"},
    }
    assert dynamic["value"] == expected
    assert _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == typed_events == _expected_events("approve")
    assert typed["status"] == "completed"


def test_UI02_blocked_review_keeps_the_revised_draft_and_reason(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="block", limit=3)
    typed, typed_events = _typed_run(tmp_path / "typed", seed="block", limit=3)
    expected = {
        "variant": "BLOCKED",
        "value": {"title": "block+r", "score": 1},
        "reason": {"why": "refused:block+r"},
    }
    assert dynamic["value"] == expected
    assert _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == typed_events == _expected_events("block")
    assert typed["status"] == "completed"


def test_UI03_limit_exhaustion_keeps_the_last_revision_without_an_extra_review(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="draft", limit=3)
    typed, typed_events = _typed_run(tmp_path / "typed", seed="draft", limit=3)
    expected = {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}
    assert dynamic["value"] == expected
    assert _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == typed_events == _expected_events("draft")
    assert len(dynamic["events"]) == 6
    assert typed["status"] == "completed"


def test_UI04_malformed_review_fails_its_typed_boundary_before_revision(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="malformed", limit=3)
    typed, typed_events = _typed_run(tmp_path / "typed", seed="malformed", limit=3)
    assert dynamic["error"].code == "dynamic_effect_failed"
    assert [event["hook"] for event in dynamic["events"]] == ["review"]
    assert typed["status"] == "failed"
    assert not typed.get("workflow_outputs")
    assert typed_events == dynamic["events"] == _expected_events("malformed")
    assert len(dynamic["states"]) == 1
    assert dynamic["states"][0]["status"] == "failed"
    failed_leaf = dynamic["states"][0]["steps"]["utility_leaves::review-draft__probe_review"]
    assert failed_leaf["error"]["context"]["cause_code"] == "leaf_result_schema_invalid"
    assert not dynamic["states"][0]["workflow_outputs"]
    assert not failed_leaf.get("artifacts")
    from tests.test_workflow_lisp_improve_stdlib import _failed_hook_steps
    assert _failed_hook_steps(typed) == {"probe_review": "contract_violation"}


def test_UI05_failure_in_the_final_permitted_revision_is_not_exhaustion(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="fail", limit=2)
    typed, typed_events = _typed_run(tmp_path / "typed", seed="fail", limit=2)
    assert dynamic["error"].code == "dynamic_effect_failed"
    assert dynamic["events"] == typed_events == _expected_events("fail", limit=2)
    assert [event["hook"] for event in dynamic["events"]] == ["review", "revise", "review", "revise"]
    assert typed["status"] == "failed"
    assert not typed.get("workflow_outputs")
    assert len(dynamic["states"]) == 4
    assert [state["status"] for state in dynamic["states"]] == ["completed", "completed", "completed", "failed"]
    failed_leaf = dynamic["states"][-1]["steps"]["utility_leaves::revise-draft__probe_revise"]
    assert failed_leaf["exit_code"] == 3
    assert failed_leaf["outcome"]["class"] == "command_failed"
    assert not dynamic["states"][-1]["workflow_outputs"]
    from tests.test_workflow_lisp_improve_stdlib import _failed_hook_steps
    assert _failed_hook_steps(typed) == {"probe_revise": "command_failed"}


def test_UI06_dynamic_review_wrapper_matches_the_typed_imported_wrapper(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="draft", limit=2, wrapped=True)
    typed, typed_events = _typed_run(tmp_path / "typed", seed="draft", limit=2, wrapped=True)
    expected = {"variant": "EXHAUSTED", "value": {"title": "draft+r+r", "score": 2}}
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == typed_events == _expected_events("draft", limit=2)


def _compare_assembled_inline_and_typed(root: Path, *, seed: str, limit: int) -> None:
    typed_imported, imported_events = _typed_run(root / "typed-imported", seed=seed, limit=limit)
    typed_inline, inline_events = _typed_run(root / "typed-inline", seed=seed, limit=limit, inline=True)
    dynamic_assembled = _dynamic_run(root / "dynamic-assembled", seed=seed, limit=limit, assembled=True)
    dynamic_inline = _dynamic_run(root / "dynamic-inline", seed=seed, limit=limit, assembled=False)
    expected = _typed_domain_result(typed_imported["workflow_outputs"])
    assert typed_imported["status"] == typed_inline["status"] == "completed"
    assert _typed_domain_result(typed_inline["workflow_outputs"]) == expected
    assert dynamic_assembled["value"] == dynamic_inline["value"] == expected
    assert imported_events == inline_events == dynamic_assembled["events"] == dynamic_inline["events"]
    assert dynamic_assembled["source_owner"] == "shared-fragment"
    assert dynamic_inline["source_owner"] == "caller-inline"
    assert "(define (improve " in dynamic_assembled["source"]
    assert "(define (inline-improve " not in dynamic_assembled["source"]
    assert "(define (inline-improve " in dynamic_inline["source"]
    assert "(define (improve " not in dynamic_inline["source"]
    assert imported_events == _expected_events(seed, limit=limit)


def test_UI07_assembled_and_inline_approval_agree_with_typed_imported_and_inline_controls(tmp_path):
    _compare_assembled_inline_and_typed(tmp_path, seed="approve", limit=3)


def test_UI08_assembled_and_inline_blocked_outcomes_agree_with_typed_controls(tmp_path):
    _compare_assembled_inline_and_typed(tmp_path, seed="block", limit=3)


def test_UI09_assembled_and_inline_exhaustion_agree_with_typed_controls(tmp_path):
    _compare_assembled_inline_and_typed(tmp_path, seed="draft", limit=3)


def test_UI10_zero_limit_fails_before_either_hook_and_typed_control_refuses_at_compile_time(tmp_path):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="approve", limit=0)
    assert dynamic["error"].code == "dynamic_explicit_failure"
    assert dynamic["error"].metadata["reason"] == "invalid_limit"
    assert dynamic["events"] == []
    assert dynamic["states"] == []

    probes = _write_probes(tmp_path / "typed")
    from tests.test_workflow_lisp_improve_stdlib import _compile
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    _typed_sources(tmp_path / "typed", probes, seed="approve", limit=0)
    with pytest.raises(LispFrontendCompileError) as error:
        _compile(tmp_path / "typed", probes=probes)
    assert error.value.diagnostics[0].code == "workflow_boundary_type_invalid"
    assert _events(tmp_path / "typed") == []


def test_UI11_blocked_domain_result_matches_the_public_typed_wire_output(tmp_path, monkeypatch):
    dynamic = _dynamic_run(tmp_path / "dynamic", seed="block", limit=3)
    public_root = tmp_path / "typed-public"
    public_root.mkdir()
    probes = _write_probes(public_root)
    _typed_sources(public_root, probes, seed="block", limit=3)
    from tests.test_workflow_lisp_generic_unions_runtime import _public_run, _public_run_files
    monkeypatch.chdir(public_root)
    with patch.dict(os.environ, {"DYNAMIC_IMPROVE_EVENT_LOG": str(public_root / "hook-events.jsonl")}):
        result = _public_run(_public_run_files(public_root, probes))
    assert result.exit_code == 0
    assert dynamic["value"] == _typed_domain_result(result.workflow_outputs)
    assert dynamic["value"] == {
        "variant": "BLOCKED",
        "value": {"title": "block+r", "score": 1},
        "reason": {"why": "refused:block+r"},
    }
    assert dynamic["events"] == _events(public_root) == _expected_events("block")
