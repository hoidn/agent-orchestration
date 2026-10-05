"""UE01–UE04/UD01–UD06: native authoring edits and observed failure/restart costs.

Terminal failures qualify the Task8 fresh-run comparison. Actual external kills
remain Task9; the typed comparator retains its committed-checkpoint helper.
"""
from contextlib import chdir
import json
import os
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram
from orchestrator.workflow_lisp.dynamic.source import compile_source
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.test_workflow_dynamic_improve import (
    FIXTURES, _assert_effects, _dynamic_run, _events,
    _stage_dynamic, _typed_domain_result, _typed_run,
)
from tests.workflow_lisp_improve_stdlib_sources import (
    REVIEW_PROBE, REVISE_PROBE, entry_source, string_inputs_entry_source,
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


def _origin_revise_probe() -> str:
    return _replace_once(
        REVISE_PROBE,
        'payload = {"title": title + "+r", "score": title.count("+r") + 1}',
        'payload = {"title": title + "+r", "score": title.count("+r") + 1, "origin": sys.argv[4]}',
    )


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


def _message_review_probe() -> str:
    assert REVIEW_PROBE.count('"note":') == 2
    return REVIEW_PROBE.replace('"note":', '"message":')


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


def _rubric_review_probe() -> str:
    source = _replace_once(REVIEW_PROBE, "title, goal = sys.argv[1], sys.argv[2]", "title, goal, rubric = sys.argv[1], sys.argv[2], sys.argv[3]")
    source = _replace_once(source, '"ok:" + title + ":" + goal', '"ok:" + title + ":" + goal + ":" + rubric')
    return _replace_once(source, '"fb" + str(title.count("+r"))', '"fb" + str(title.count("+r")) + ":" + rubric')


def _rubric_typed_entry(probes: dict[str, Path], *, limit: int) -> str:
    source = entry_source(seed="draft", limit=limit, probes=probes)
    source = _replace_once(source, "(defrecord Brief (goal String))", "(defrecord Brief (goal String) (rubric String))")
    source = _replace_once(source, "candidate.title brief.goal)", "candidate.title brief.goal brief.rubric)")
    return _replace_once(source, '(record Brief :goal "tidy")', '(record Brief :goal "tidy" :rubric "clarity")')


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


def _base_source():
    return (FIXTURES / "improve.orc").read_text().replace(
        '(field current "title") goal rubric)', '(field current "title") goal)', 1)


def _probes(root):
    return {name: root / (name + ".py") for name in ("probe_review", "probe_revise")}


def _snapshot(root):
    return {str(p.relative_to(root)): (('symlink', os.readlink(p)) if p.is_symlink() else
            ('dir' if p.is_dir() else p.read_bytes())) for p in root.rglob('*')}


def _compile_dynamic(root, source):
    path, _ = _stage_dynamic(root, source_text=source)
    return compile_source(path, source_roots=(root,), command_boundaries={
        name: ExternalToolBinding(name, ('python', name + '.py'), closure=())
        for name in ('probe_review', 'probe_revise')}).program


def test_UE01_origin_boundary_and_internal_state_edits_are_counted_separately(tmp_path):
    base = _base_source()
    types_before = (FIXTURES / "consumer_types.orc").read_text()
    types_after = _replace_once(types_before, '(defrecord Draft (title String) (score Int))',
        '(defrecord Draft (title String) (score Int) (origin String))')
    boundary = base.replace('(field current "title") goal)',
        '(field current "title") goal (field current "origin"))', 1).replace(
        '(field feedback "note"))', '(field feedback "note") (field current "origin"))', 1)
    failed = _dynamic_run(tmp_path / "bad", seed="draft", limit=1, source_text=boundary,
        types_text=types_after, revise_script=_origin_revise_probe())
    assert failed["view"]["error"]["code"] == "dynamic_field_missing"
    assert failed["events"] == failed["view"]["effects"] == []
    repaired = _replace_once(boundary, '(record (title seed) (score 0))',
        '(record (title seed) (score 0) (origin "seed"))')
    dynamic = _dynamic_run(tmp_path / "good", seed="draft", limit=1, source_text=repaired,
        types_text=types_after, revise_script=_origin_revise_probe())
    typed_root = tmp_path / "typed"
    typed_source = _origin_typed_entry(_probes(typed_root))
    typed, calls = _typed_run(typed_root, seed="draft", limit=1,
        entry_source_text=typed_source, revise_script=_origin_revise_probe())
    expected = {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1, "origin": "seed"}}
    assert dynamic["value"] == expected
    assert {"variant": typed["workflow_outputs"]["return__variant"], "value": {
        name: typed["workflow_outputs"]["return__value__" + name] for name in ("title", "score", "origin")}} == expected
    assert dynamic["events"] == calls == [
        {"hook": "review", "argv": ["draft", "tidy", "seed"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0", "seed"]}]
    _assert_effects(dynamic, ["completed"] * 2)
    _save_receipt(tmp_path, "UE01", {
        "boundary_edits": ["Draft.origin schema", "review argv origin", "revise argv/native result origin"],
        "internal_edits": ["initial origin field"], "native_reconstruction_edits": [],
        "red_error": failed["view"]["error"], "red_effects": failed["view"]["effects"],
        "value": expected, "requests": calls, "timing": "unmeasured"}, {
        "types.before.orc": types_before, "types.after.orc": types_after,
        "consumer.before.orc": base, "consumer.boundary.orc": boundary,
        "consumer.repaired.orc": repaired, "typed.repaired.orc": typed_source})


def test_UE02_feedback_and_evidence_field_rename_updates_both_consumers(tmp_path):
    types = (FIXTURES / "consumer_types.orc").read_text().replace(
        '(defrecord Feedback (note String))', '(defrecord Feedback (message String))', 1)
    base = _base_source()
    bad_producer = _dynamic_run(tmp_path / "producer", seed="approve", limit=1,
        source_text=base, types_text=types)
    assert bad_producer["view"]["error"]["code"] == "dynamic_command_result_invalid"
    _assert_effects(bad_producer, ["failed"])
    bad_consumer = _dynamic_run(tmp_path / "consumer", seed="draft", limit=1,
        source_text=base, types_text=types, review_script=_message_review_probe())
    assert bad_consumer["view"]["error"]["code"] == "dynamic_field_missing"
    _assert_effects(bad_consumer, ["completed"])
    repaired = _replace_once(base, '(field feedback "note")', '(field feedback "message")')
    outcomes = []
    for seed in ("approve", "draft"):
        dynamic = _dynamic_run(tmp_path / seed / "d", seed=seed, limit=1,
            source_text=repaired, types_text=types, review_script=_message_review_probe())
        typed_root = tmp_path / seed / "t"
        typed, calls = _typed_run(typed_root, seed=seed, limit=1,
            entry_source_text=_message_typed_entry(_probes(typed_root), seed=seed, limit=1),
            review_script=_message_review_probe())
        assert dynamic["value"] == _typed_message_value(typed["workflow_outputs"])
        assert dynamic["events"] == calls
        outcomes.append({"seed": seed, "value": dynamic["view"]["workflow_outputs"], "requests": calls})
    _save_receipt(tmp_path, "UE02", {"producer_error": bad_producer["view"]["error"],
        "consumer_error": bad_consumer["view"]["error"], "outcomes": outcomes,
        "boundary_edits": ["Feedback.message declaration", "review producer payload"],
        "consumer_edits": ["revision message projection"],
        "native_approval_reconstruction_edits": [], "timing": "unmeasured"}, {
        "types.after.orc": types, "consumer.before.orc": base, "consumer.after.orc": repaired})


def test_UE03_review_captures_rubric_independently_and_revision_uses_goal(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="draft", limit=1, rubric="clarity",
        review_script=_rubric_review_probe())
    typed_root = tmp_path / "t"
    typed_source = _rubric_typed_entry(_probes(typed_root), limit=1)
    typed, calls = _typed_run(typed_root, seed="draft", limit=1,
        entry_source_text=typed_source, review_script=_rubric_review_probe())
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == {
        "variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    assert dynamic["events"] == calls == [
        {"hook": "review", "argv": ["draft", "tidy", "clarity"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0:clarity"]}]
    program = DynamicProgram.from_artifact((dynamic["result"].run_root / "closed_program.json").read_bytes())
    assert program.definitions["dynamic_consumer/improve::review-for$fn/body"]["captures"] == ("goal", "rubric")
    assert program.definitions["dynamic_consumer/improve::revise-for$fn/body"]["captures"] == ("goal",)
    _save_receipt(tmp_path, "UE03", {"value": dynamic["view"]["workflow_outputs"], "requests": calls,
        "credit": ["typed String context already supported", "typed Brief carries both values", "W3 remains proposed"],
        "timing": "unmeasured"}, {"consumer.orc": (FIXTURES / "improve.orc").read_text(), "typed.orc": typed_source})


def test_UE04_pure_feedback_helper_preserves_payload_and_effect_order(tmp_path):
    base = _base_source()
    source = base.replace('  (export run)',
        '  (import dynamic_consumer/feedback :only (feedback-to-revision-input))\n  (export run)', 1)
    source = _replace_once(source, '(field feedback "note")', '(feedback-to-revision-input feedback)')
    dynamic = _dynamic_run(tmp_path / "d", seed="draft", limit=1, source_text=source,
        extra_sources={"dynamic_consumer/feedback.orc": (FIXTURES / "feedback.orc").read_text()})
    typed_root = tmp_path / "t"
    typed_source = _typed_feedback_helper_entry(_probes(typed_root), limit=1)
    typed, calls = _typed_run(typed_root, seed="draft", limit=1, entry_source_text=typed_source)
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == {
        "variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    assert dynamic["events"] == calls == [
        {"hook": "review", "argv": ["draft", "tidy"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}]
    program = DynamicProgram.from_artifact((dynamic["result"].run_root / "closed_program.json").read_bytes())
    assert program.definitions["dynamic_consumer/feedback::feedback-to-revision-input"]["boundary"] is None
    _save_receipt(tmp_path, "UE04", {"value": dynamic["view"]["workflow_outputs"], "requests": calls, "timing": "unmeasured"},
        {"consumer.before.orc": base, "consumer.after.orc": source, "typed.orc": typed_source})


def _typed_control(root, *, seed="draft", limit=1):
    return _typed_run(root, seed=seed, limit=limit,
        entry_source_text=entry_source(seed=seed, limit=limit, probes=_probes(root)))


def _assert_late_failure(actual, code, statuses):
    assert actual["result"].exit_code == 1 and actual["value"] is None
    assert actual["view"]["status"] == "failed"
    error = actual["view"]["error"]
    assert error["code"] == code
    assert error["metadata"]["span"]["start"]["path"].endswith("improve.orc")
    assert error["metadata"]["call_stack"]
    assert error["metadata"]["call_context"]
    assert "fb0" not in json.dumps(error)
    _assert_effects(actual, statuses)
    return error


def test_UD01_unbound_lexical_name_fails_at_compile_before_any_dispatch(tmp_path):
    base = _base_source()
    bad = _replace_once(base, '(field current "title") goal)', '(field current "title") missing_goal)')
    with pytest.raises(LispFrontendCompileError) as dynamic_error:
        _compile_dynamic(tmp_path / "d", bad)
    assert dynamic_error.value.diagnostics[0].code == "dynamic_source_invalid"
    assert dynamic_error.value.diagnostics[0].span.start.path.endswith("improve.orc")
    typed_root = tmp_path / "t"
    typed_before = entry_source(seed="draft", limit=1, probes=_probes(typed_root))
    typed_bad = _replace_once(typed_before, 'candidate.title brief.goal)', 'candidate.title missing_goal)')
    with pytest.raises(LispFrontendCompileError) as typed_error:
        _typed_run(typed_root, seed="draft", limit=1, entry_source_text=typed_bad)
    assert typed_error.value.diagnostics[0].code == "name_unknown"
    for root in (tmp_path / "d", typed_root):
        assert _events(root) == []
        assert not (root / ".orchestrate/runs").exists()
    repaired = _dynamic_run(tmp_path / "good", seed="draft", limit=1, source_text=base)
    typed, calls = _typed_control(tmp_path / "typed-good")
    assert repaired["value"] == _typed_domain_result(typed["workflow_outputs"])
    assert repaired["events"] == calls
    _save_receipt(tmp_path, "UD01", {"dynamic_error": dynamic_error.value.diagnostics[0].code,
        "typed_error": typed_error.value.diagnostics[0].code, "failed_dispatches": 0,
        "repaired_value": repaired["view"]["workflow_outputs"], "repaired_requests": calls, "timing": "unmeasured"}, {
        "consumer.before.orc": base, "consumer.invalid.orc": bad,
        "typed.before.orc": typed_before, "typed.invalid.orc": typed_bad})


def test_UD02_wrong_call_arity_costs_zero_or_one_completed_review_and_one_site_repair(tmp_path):
    base = _base_source().replace('  (export run)', '  (export run)\n  (define (identity value) value)', 1)
    before_bad = _replace_once(base, '(field current "title") goal)',
        '(field current "title") (identity goal "extra"))')
    after_bad = _replace_once(base, '(field feedback "note")', '(field (identity feedback "extra") "note")')
    repaired = _replace_once(after_bad, '(identity feedback "extra")', '(identity feedback)')
    before = _dynamic_run(tmp_path / "before", seed="draft", limit=1, source_text=before_bad)
    after = _dynamic_run(tmp_path / "after", seed="draft", limit=1, source_text=after_bad)
    _assert_late_failure(before, "dynamic_call_arity", [])
    _assert_late_failure(after, "dynamic_call_arity", ["completed"])
    assert before["events"] == []
    assert after["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert json.loads((after["result"].run_root / after["view"]["effects"][0]["result_path"]).read_text()) == {
        "variant": "REVISE", "feedback": {"note": "fb0"}}
    errors = []
    for site in ("before-effect", "after-review"):
        root = tmp_path / site
        typed_bad = _typed_identity_arity_entry(_probes(root), site=site)
        with pytest.raises(LispFrontendCompileError) as error:
            _typed_run(root, seed="draft", limit=1, entry_source_text=typed_bad)
        assert error.value.diagnostics[0].code == "procedure_arity_mismatch"
        assert _events(root) == []
        errors.append(error.value.diagnostics[0].code)
    dynamic = _dynamic_run(tmp_path / "repaired", seed="draft", limit=1, source_text=repaired)
    typed, calls = _typed_control(tmp_path / "typed-repaired")
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"])
    assert dynamic["events"] == calls
    _save_receipt(tmp_path, "UD02", {"zero_cost_error": before["view"]["error"],
        "one_review_error": after["view"]["error"], "completed_effects_before_repair": [0, 1],
        "typed_compile_errors": errors, "value": dynamic["view"]["workflow_outputs"], "requests": calls,
        "timing": "unmeasured"}, {"consumer.before.orc": base,
        "consumer.pre-effect-invalid.orc": before_bad, "consumer.post-review-invalid.orc": after_bad,
        "consumer.repaired.orc": repaired})


def test_UD03_missing_internal_field_fails_after_review_then_one_site_repair(tmp_path):
    base = _base_source()
    bad = _replace_once(base, '(field feedback "note")', '(field feedback "missing")')
    failed = _dynamic_run(tmp_path / "d", seed="draft", limit=1, source_text=bad)
    error = _assert_late_failure(failed, "dynamic_field_missing", ["completed"])
    assert failed["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert error["metadata"]["call_stack"][-1]["callee"].endswith("revise-for$fn/body")
    row, = failed["view"]["effects"]
    assert json.loads((failed["result"].run_root / row["result_path"]).read_text()) == {
        "variant": "REVISE", "feedback": {"note": "fb0"}}
    typed_root = tmp_path / "typed-bad"
    typed_bad = entry_source(seed="draft", limit=1, probes=_probes(typed_root)).replace(
        'feedback.note)', 'feedback.missing)', 1)
    with pytest.raises(LispFrontendCompileError) as typed_error:
        _typed_run(typed_root, seed="draft", limit=1, entry_source_text=typed_bad)
    assert typed_error.value.diagnostics[0].code == "record_field_unknown"
    assert _events(typed_root) == []
    dynamic = _dynamic_run(tmp_path / "good", seed="draft", limit=1, source_text=base)
    typed, calls = _typed_control(tmp_path / "typed-good")
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"])
    assert dynamic["events"] == calls
    _save_receipt(tmp_path, "UD03", {"error": error, "completed_review": row,
        "typed_error": typed_error.value.diagnostics[0].code, "value": dynamic["view"]["workflow_outputs"],
        "requests": calls, "timing": "unmeasured"}, {
        "consumer.before.orc": base, "consumer.invalid.orc": bad, "typed.invalid.orc": typed_bad})


def test_UD04_budget_failure_after_completed_effect_is_repaired_by_a_fresh_run(tmp_path):
    root = tmp_path / "d"
    failed = _dynamic_run(root, seed="draft", limit=1, source_text=_base_source(), budget=60)
    error = _assert_late_failure(failed, "dynamic_budget_exhausted", ["completed"])
    assert failed["events"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert failed["view"]["steps_used"] == error["metadata"]["steps"] == 60
    before = _snapshot(failed["result"].run_root)
    low_budget_source = failed["path"].read_text()
    dynamic = _dynamic_run(root, seed="draft", limit=1, source_text=_base_source(), budget=1000)
    assert dynamic["result"].run_id != failed["result"].run_id
    assert _snapshot(failed["result"].run_root) == before
    typed, calls = _typed_control(tmp_path / "t")
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"])
    assert dynamic["events"] == failed["events"] + calls
    _save_receipt(tmp_path, "UD04", {"error": error, "failed_run": failed["result"].run_id,
        "fresh_run": dynamic["result"].run_id, "old_files_retained": sorted(before),
        "completed_prefix": failed["events"], "all_requests": dynamic["events"],
        "value": dynamic["view"]["workflow_outputs"], "timing": "unmeasured"}, {
        "consumer.low-budget.orc": low_budget_source,
        "consumer.repaired.orc": dynamic["path"].read_text()})


def _restart_comparison(tmp_path, monkeypatch, *, goal, string_context):
    from tests.test_workflow_lisp_generic_unions_runtime import _public_run_files
    from tests.test_workflow_lisp_improve_stdlib import (
        _hook_calls, _resume, _run_until_the_first_committed_iteration, _write_project,
    )

    base = _base_source()
    stopped_source = _replace_once(base, '    (fn (current feedback)\n      (command-result',
        '    (fn (current feedback)\n      (let* ((next (command-result')
    stopped_source = _replace_once(stopped_source, ':returns Draft)))',
        ':returns Draft)))\n        (fail "stop_after_pair"))))')
    root = tmp_path / "d"
    failed = _dynamic_run(root, seed="draft", limit=3, goal=goal, source_text=stopped_source)
    _assert_late_failure(failed, "dynamic_explicit_failure", ["completed", "completed"])
    assert failed["view"]["error"]["metadata"]["reason"] == "stop_after_pair"
    prefix = [{"hook": "review", "argv": ["draft", goal]},
              {"hook": "revise", "argv": ["draft", goal, "fb0"]}]
    assert failed["events"] == prefix
    old_root = failed["result"].run_root
    old_files = _snapshot(old_root)
    first_program = (old_root / "closed_program.json").read_bytes()
    fresh = _dynamic_run(root, seed="draft", limit=3, goal=goal, source_text=base)
    assert fresh["result"].run_id != failed["result"].run_id
    assert _snapshot(old_root) == old_files
    expected_events = []
    for iteration in range(3):
        title = "draft" + "+r" * iteration
        expected_events.extend([
            {"hook": "review", "argv": [title, goal]},
            {"hook": "revise", "argv": [title, goal, f"fb{iteration}"]}])
    assert fresh["events"] == prefix + expected_events
    _assert_effects(fresh, ["completed"] * 6)
    assert 0 < fresh["view"]["steps_used"] <= fresh["view"]["budget"]
    assert (old_root / "closed_program.json").read_bytes() == first_program

    typed_root = tmp_path / "t"
    probes = _write_project(typed_root, seed="draft", limit=3)
    entry = typed_root / "grt/entry.orc"
    typed_source = entry.read_text()
    inputs = None
    if string_context:
        typed_source = string_inputs_entry_source(typed_source)
        entry.write_text(typed_source)
        inputs = typed_root / "inputs.json"
        inputs.write_text(json.dumps({"goal": goal}))
    assert string_context or goal == "tidy"
    with chdir(typed_root):
        run_id = _run_until_the_first_committed_iteration(monkeypatch,
            _public_run_files(typed_root, probes), input_file=inputs)
        typed_prefix = _hook_calls(probes)
        assert typed_prefix == ([f"draft {goal}"], [f"draft {goal} fb0"])
        partial = json.loads((typed_root / ".orchestrate/runs" / run_id / "state.json").read_text())
        assert partial["status"] != "completed"
        typed = _resume(run_id)
        typed_calls = _hook_calls(probes)
    assert typed["status"] == fresh["view"]["status"] == "completed"
    assert typed_calls == (
        [f"draft {goal}", f"draft+r {goal}", f"draft+r+r {goal}"],
        [f"draft {goal} fb0", f"draft+r {goal} fb1", f"draft+r+r {goal} fb2"])
    expected = {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}
    assert fresh["value"] == _typed_domain_result(typed["workflow_outputs"]) == expected
    case = "UD06" if string_context else "UD05"
    _save_receipt(tmp_path, case, {
        "stop_mechanism": "real explicit terminal failure after settled review+revision; no external kill",
        "dynamic_old_run": failed["result"].run_id, "dynamic_fresh_run": fresh["result"].run_id,
        "dynamic_retained_files": sorted(old_files), "dynamic_failed_view": failed["view"],
        "dynamic_prefix": prefix, "dynamic_all_requests": fresh["events"],
        "typed_partial_run": run_id, "typed_prefix": typed_prefix, "typed_calls_after_resume": typed_calls,
        "value": expected, "typed_context": "String" if string_context else "Brief",
        "credit": ["typed String context is existing behavior", "typed resume avoids prior hook work", "W3 remains proposed"],
        "dynamic_steps_failed": failed["view"]["steps_used"], "dynamic_steps_fresh": fresh["view"]["steps_used"],
        "external_kill_obligation": "Task9 UD05/UD06", "timing": "unmeasured",
    }, {"consumer.failed-terminal.orc": stopped_source, "consumer.fresh.orc": base,
        "typed.entry.orc": typed_source, "typed.inputs.json": inputs.read_text() if inputs else "{}"})


def test_UD05_dynamic_restart_repeats_effect_pair_while_typed_resume_does_not(tmp_path, monkeypatch):
    _restart_comparison(tmp_path, monkeypatch, goal="tidy", string_context=False)


def test_UD06_captured_goal_restart_repeats_while_typed_string_input_resume_preserves_goal(tmp_path, monkeypatch):
    _restart_comparison(tmp_path, monkeypatch, goal="steady", string_context=True)
