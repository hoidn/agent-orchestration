"""UI01–UI11: full improve behavior through native imports and public commands.

The retained typed wire projection is converted only in the comparison helper.
Both callers add the same rubric operand to review; the native consumer captures
it separately from revision's goal without changing the typed stdlib API.
"""

from __future__ import annotations

from contextlib import chdir
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.dynamic.evaluator import evaluate
from orchestrator.workflow.dynamic.state import load_dynamic_view
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram
from tests.test_workflow_dynamic_source import compile_source, write_source
from tests.workflow_lisp_improve_stdlib_sources import (
    REVIEW_PROBE, REVISE_PROBE, entry_source, inline_entry_source, wrapped_review_sources,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/workflow_lisp/dynamic"


def _write_probes(
    root: Path,
    *,
    review_script: str = REVIEW_PROBE,
    revise_script: str = REVISE_PROBE,
) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    probes = {}
    for name, script, hook in (
        ("probe_review", review_script, "review"),
        ("probe_revise", revise_script, "revise"),
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
    entry = entry_source(seed=seed, limit=limit, probes=probes).replace(
        "candidate.title brief.goal)", 'candidate.title brief.goal "clear")', 1)
    if wrapped:
        _write_sources(root, {name: source.replace("candidate.title brief.goal)",
            'candidate.title brief.goal "clear")', 1)
            for name, source in wrapped_review_sources(entry, probes).items()})
    else:
        _write_sources(root, {"grt/entry.orc": inline_entry_source(entry) if inline else entry})


def _typed_run(root: Path, *, seed: str, limit: int, inline: bool = False,
               wrapped: bool = False, entry_source_text: str | None = None,
               review_script: str = REVIEW_PROBE, revise_script: str = REVISE_PROBE
               ) -> tuple[dict[str, object], list[dict[str, object]]]:
    probes = _write_probes(root, review_script=review_script, revise_script=revise_script)
    if entry_source_text is None:
        _typed_sources(root, probes, seed=seed, limit=limit, inline=inline, wrapped=wrapped)
    else:
        _write_sources(root, {"grt/entry.orc": entry_source_text})
    from tests.test_workflow_lisp_improve_stdlib import _compile
    from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle

    compiled = _compile(root, probes=probes)
    bundle = compiled.validated_bundles_by_name["grt/entry::run"]
    with patch.dict(os.environ, {"DYNAMIC_IMPROVE_EVENT_LOG": str(root / "hook-events.jsonl")}):
        state = _execute_bundle(bundle, workflow_path=root / "grt/entry.orc", workspace=root, run_id="run")
    return state, _events(root)


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
        events.append({"hook": "review", "argv": [title, "tidy", "clear"]})
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



def _stage_dynamic(root, *, source_text=None, inline=False, wrapped=False,
                   review_script=REVIEW_PROBE, revise_script=REVISE_PROBE,
                   types_text=None, extra_sources=None):
    probes = _write_probes(root, review_script=review_script, revise_script=revise_script)
    directory = root / "dynamic_consumer"
    directory.mkdir(exist_ok=True)
    shutil.copyfile(FIXTURES / "consumer_types.orc", directory / "types.orc")
    if types_text is not None:
        (directory / "types.orc").write_text(types_text)
    if extra_sources:
        _write_sources(root, extra_sources)
    source = source_text or (FIXTURES / ("improve_inline.orc" if inline else "improve.orc")).read_text()
    if wrapped:
        shutil.copyfile(FIXTURES / "review.orc", directory / "review.orc")
        start = source.index("  (define (review-for")
        end = source.index("  (define (revise-for")
        source = source[:start] + '''  (define (review-for goal rubric)
    (fn (current) (assess current goal rubric)))

''' + source[end:]
        source = source.replace("  (export run)",
            "  (import dynamic_consumer/review :only (assess))\n  (export run)")
    path = directory / "improve.orc"
    path.write_text(source)
    manifest = root / "commands.json"
    manifest.write_text(json.dumps({
        name: {"kind": "external_tool", "stable_command": ["python", probe.name], "closure": []}
        for name, probe in probes.items()
    }))
    return path, manifest


def _dynamic_run(root, *, seed, limit, goal="tidy", rubric="clear", inline=False,
                 wrapped=False, source_text=None, review_script=REVIEW_PROBE,
                 revise_script=REVISE_PROBE, types_text=None, extra_sources=None,
                 budget=None):
    if budget is not None:
        source_text = (source_text or (FIXTURES / "improve.orc").read_text()).replace(
            "(:budget 1000)", f"(:budget {budget})", 1)
    path, manifest = _stage_dynamic(root, source_text=source_text, inline=inline, wrapped=wrapped,
        review_script=review_script, revise_script=revise_script,
        types_text=types_text, extra_sources=extra_sources)
    args = create_parser().parse_args([
        "run", str(path), "--command-boundaries-file", str(manifest),
        "--input", f"seed={seed}", "--input", f"limit={limit}",
        "--input", f"goal={goal}", "--input", f"rubric={rubric}",
    ])
    from orchestrator.workflow.executor import WorkflowExecutor

    with chdir(root), patch.dict(os.environ, {"DYNAMIC_IMPROVE_EVENT_LOG": str(root / "hook-events.jsonl")}), \
         patch.object(WorkflowExecutor, "__init__", side_effect=AssertionError("dynamic constructed WorkflowExecutor")):
        result = run_workflow(args)
    assert result.run_root is not None
    view = load_dynamic_view(result.run_root)
    return {"result": result, "view": view, "value": result.workflow_outputs,
            "events": _events(root), "path": path, "manifest": manifest}


def _assert_effects(dynamic, statuses):
    view = dynamic["view"]
    assert [row["ordinal"] for row in view["effects"]] == list(range(1, len(statuses) + 1))
    assert [row["status"] for row in view["effects"]] == statuses
    run_root = dynamic["result"].run_root
    for row in view["effects"]:
        attempt = run_root / "effects" / str(row["ordinal"]) / "attempt-1"
        assert (attempt / "stdout.txt").is_file()
        assert (attempt / "stderr.txt").is_file()
        if row["status"] == "completed":
            assert (attempt / "result.json").is_file()
    assert 0 < view["steps_used"] <= view["budget"]


def test_UI01_initial_approval_keeps_the_initial_draft_and_evidence(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="approve", limit=3)
    typed, events = _typed_run(tmp_path / "t", seed="approve", limit=3)
    expected = {"variant": "APPROVED", "value": {"title": "approve", "score": 0},
                "evidence": {"note": "ok:approve:tidy"}}
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == events == _expected_events("approve")
    assert dynamic["view"]["status"] == typed["status"] == "completed"
    _assert_effects(dynamic, ["completed"])


def test_UI02_blocked_review_keeps_the_revised_draft_and_reason(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="block", limit=3)
    typed, events = _typed_run(tmp_path / "t", seed="block", limit=3)
    expected = {"variant": "BLOCKED", "value": {"title": "block+r", "score": 1},
                "reason": {"why": "refused:block+r"}}
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == events == _expected_events("block")
    assert dynamic["view"]["status"] == typed["status"] == "completed"
    _assert_effects(dynamic, ["completed"] * 3)


def test_UI03_limit_exhaustion_keeps_the_last_revision_without_an_extra_review(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="draft", limit=3)
    typed, events = _typed_run(tmp_path / "t", seed="draft", limit=3)
    expected = {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == expected
    assert dynamic["events"] == events == _expected_events("draft")
    assert len(events) == 6
    assert dynamic["view"]["status"] == typed["status"] == "completed"
    _assert_effects(dynamic, ["completed"] * 6)


def test_UI04_malformed_review_fails_its_typed_boundary_before_revision(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="malformed", limit=3)
    typed, events = _typed_run(tmp_path / "t", seed="malformed", limit=3)
    assert dynamic["value"] is None and not typed.get("workflow_outputs")
    assert dynamic["view"]["status"] == typed["status"] == "failed"
    assert dynamic["events"] == events == _expected_events("malformed")
    assert dynamic["view"]["error"]["code"] == "dynamic_command_result_invalid"
    row, = dynamic["view"]["effects"]
    assert row["error"]["code"] == "dynamic_command_result_invalid"
    assert json.loads((dynamic["result"].run_root / row["result_path"]).read_text()) == {
        "variant": "APPROVE", "evidence": {"score": 1}}
    assert "malformed" not in json.dumps(dynamic["view"]["error"])
    from tests.test_workflow_lisp_improve_stdlib import _failed_hook_steps
    assert _failed_hook_steps(typed) == {"probe_review": "contract_violation"}
    _assert_effects(dynamic, ["failed"])


def test_UI05_failure_in_the_final_permitted_revision_is_not_exhaustion(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="fail", limit=2)
    typed, events = _typed_run(tmp_path / "t", seed="fail", limit=2)
    assert dynamic["value"] is None and not typed.get("workflow_outputs")
    assert dynamic["view"]["status"] == typed["status"] == "failed"
    assert dynamic["events"] == events == _expected_events("fail", limit=2)
    assert [event["hook"] for event in events] == ["review", "revise", "review", "revise"]
    assert dynamic["view"]["error"]["code"] == "command_exit_nonzero"
    assert not (dynamic["result"].run_root / dynamic["view"]["effects"][-1]["result_path"]).exists()
    from tests.test_workflow_lisp_improve_stdlib import _failed_hook_steps
    assert _failed_hook_steps(typed) == {"probe_revise": "command_failed"}
    _assert_effects(dynamic, ["completed"] * 3 + ["failed"])


def test_UI06_dynamic_review_wrapper_matches_the_typed_imported_wrapper(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="draft", limit=2, wrapped=True)
    typed, events = _typed_run(tmp_path / "t", seed="draft", limit=2, wrapped=True)
    assert dynamic["value"] == _typed_domain_result(typed["workflow_outputs"]) == {
        "variant": "EXHAUSTED", "value": {"title": "draft+r+r", "score": 2}}
    assert dynamic["events"] == events == _expected_events("draft", limit=2)
    _assert_effects(dynamic, ["completed"] * 4)


def _compare_imported_inline_and_typed(root, *, seed, limit):
    typed, events = _typed_run(root / "ti", seed=seed, limit=limit)
    typed_inline, inline_events = _typed_run(root / "tl", seed=seed, limit=limit, inline=True)
    imported = _dynamic_run(root / "di", seed=seed, limit=limit)
    inline = _dynamic_run(root / "dl", seed=seed, limit=limit, inline=True)
    assert typed["status"] == typed_inline["status"] == "completed"
    expected = _typed_domain_result(typed["workflow_outputs"])
    assert imported["value"] == inline["value"] == _typed_domain_result(typed_inline["workflow_outputs"]) == expected
    assert events == inline_events == imported["events"] == inline["events"] == _expected_events(seed, limit=limit)
    imported_program = DynamicProgram.from_artifact((imported["result"].run_root / "closed_program.json").read_bytes())
    inline_program = DynamicProgram.from_artifact((inline["result"].run_root / "closed_program.json").read_bytes())
    assert "std/dynamic/improve::improve" in imported_program.definitions
    assert "std/dynamic/improve::improve" not in inline_program.definitions
    assert "dynamic_consumer/improve::inline-improve" in inline_program.definitions
    for result in (imported, inline):
        _assert_effects(result, ["completed"] * len(events))


def test_UI07_imported_and_inline_approval_agree_with_typed_imported_and_inline_controls(tmp_path):
    _compare_imported_inline_and_typed(tmp_path, seed="approve", limit=3)


def test_UI08_imported_and_inline_blocked_outcomes_agree_with_typed_controls(tmp_path):
    _compare_imported_inline_and_typed(tmp_path, seed="block", limit=3)


def test_UI09_imported_and_inline_exhaustion_agree_with_typed_controls(tmp_path):
    _compare_imported_inline_and_typed(tmp_path, seed="draft", limit=3)


def test_UI10_zero_limit_fails_before_either_hook_and_typed_control_refuses_at_compile_time(tmp_path):
    dynamic = _dynamic_run(tmp_path / "d", seed="approve", limit=0)
    assert dynamic["view"]["error"]["code"] == "dynamic_explicit_failure"
    assert dynamic["view"]["error"]["metadata"]["reason"] == "invalid_limit"
    assert dynamic["events"] == dynamic["view"]["effects"] == []
    from tests.test_workflow_lisp_improve_stdlib import _compile
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    probes = _write_probes(tmp_path / "t")
    _typed_sources(tmp_path / "t", probes, seed="approve", limit=0)
    with pytest.raises(LispFrontendCompileError) as error:
        _compile(tmp_path / "t", probes=probes)
    assert error.value.diagnostics[0].code == "workflow_boundary_type_invalid"
    assert _events(tmp_path / "t") == []


def test_UI11_blocked_domain_result_matches_the_public_typed_wire_output(tmp_path, monkeypatch):
    dynamic = _dynamic_run(tmp_path / "d", seed="block", limit=3)
    public_root = tmp_path / "t"
    probes = _write_probes(public_root)
    _typed_sources(public_root, probes, seed="block", limit=3)
    from tests.test_workflow_lisp_generic_unions_runtime import _public_run, _public_run_files
    monkeypatch.chdir(public_root)
    with patch.dict(os.environ, {"DYNAMIC_IMPROVE_EVENT_LOG": str(public_root / "hook-events.jsonl")}):
        result = _public_run(_public_run_files(public_root, probes))
    assert result.exit_code == dynamic["result"].exit_code == 0
    assert dynamic["value"] == _typed_domain_result(result.workflow_outputs) == {
        "variant": "BLOCKED", "value": {"title": "block+r", "score": 1},
        "reason": {"why": "refused:block+r"}}
    assert dynamic["events"] == _events(public_root) == _expected_events("block")


@pytest.mark.parametrize("limit", [0, -1])
def test_nonpositive_limit_refuses_before_hooks(tmp_path, limit):
    dynamic = _dynamic_run(tmp_path, seed="approve", limit=limit)
    assert dynamic["result"].exit_code == 1
    assert dynamic["view"]["error"]["code"] == "dynamic_explicit_failure"
    assert dynamic["events"] == dynamic["view"]["effects"] == []


@pytest.mark.parametrize("hook", ["review", "revise"])
def test_invalid_hook_refuses_before_dispatch(tmp_path, hook):
    source = (FIXTURES / "improve.orc").read_text().replace(
        "(improve initial (review-for goal rubric) (revise-for goal) limit)",
        "(improve initial false (revise-for goal) limit)" if hook == "review" else
        "(improve initial (review-for goal rubric) false limit)")
    dynamic = _dynamic_run(tmp_path, seed="draft", limit=1, source_text=source)
    assert dynamic["view"]["error"]["code"] == "dynamic_not_callable"
    assert dynamic["value"] is None
    assert [event["hook"] for event in dynamic["events"]] == ([] if hook == "review" else ["review"])
    assert [row["status"] for row in dynamic["view"]["effects"]] == ([] if hook == "review" else ["completed"])


def test_unreached_invalid_revision_hook_keeps_initial_approval(tmp_path):
    source = (FIXTURES / "improve.orc").read_text().replace(
        "(improve initial (review-for goal rubric) (revise-for goal) limit)",
        "(improve initial (review-for goal rubric) false limit)")
    dynamic = _dynamic_run(tmp_path, seed="approve", limit=1, source_text=source)
    assert dynamic["value"]["variant"] == "APPROVED"
    assert dynamic["events"] == _expected_events("approve", limit=1)
    _assert_effects(dynamic, ["completed"])


def test_review_and_revision_capture_their_separate_context_values(tmp_path):
    dynamic = _dynamic_run(tmp_path, seed="draft", limit=1, goal="ship", rubric="precise")
    assert dynamic["value"] == {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    assert dynamic["events"] == [
        {"hook": "review", "argv": ["draft", "ship", "precise"]},
        {"hook": "revise", "argv": ["draft", "ship", "fb0"]},
    ]
    program = DynamicProgram.from_artifact((dynamic["result"].run_root / "closed_program.json").read_bytes())
    assert program.definitions["dynamic_consumer/improve::review-for$fn/body"]["captures"] == ("goal", "rubric")
    assert program.definitions["dynamic_consumer/improve::revise-for$fn/body"]["captures"] == ("goal",)
    _assert_effects(dynamic, ["completed"] * 2)


def test_public_compile_run_and_source_free_consumer_report(tmp_path):
    path, manifest = _stage_dynamic(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
           "DYNAMIC_IMPROVE_EVENT_LOG": str(tmp_path / "hook-events.jsonl")}

    def cli(*arguments):
        return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *map(str, arguments)],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)

    compile_args = [path, "--command-boundaries-file", manifest]
    compiled = cli("compile", *compile_args, "--diagnostics-json")
    assert compiled.returncode == 0, compiled.stderr
    assert json.loads(compiled.stdout)["status"] == "accepted"
    dry = cli("run", *compile_args, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert _events(tmp_path) == [] and not (tmp_path / ".orchestrate/runs").exists()
    completed = cli("run", *compile_args, "--input", "seed=block")
    assert completed.returncode == 0, completed.stderr
    run_root, = (tmp_path / ".orchestrate/runs").iterdir()
    assert _events(tmp_path) == _expected_events("block")
    for source in (tmp_path / "dynamic_consumer").glob("*.orc"):
        source.unlink()
    manifest.unlink()
    for probe in tmp_path.glob("probe_*.py"):
        probe.unlink()
    before = {p.relative_to(run_root): p.read_bytes() for p in run_root.rglob("*") if p.is_file()}
    report = cli("report", "--run-id", run_root.name, "--format", "json")
    assert report.returncode == 0, report.stderr
    document = json.loads(report.stdout)
    assert document["run"]["workflow_outputs"] == {
        "variant": "BLOCKED", "value": {"title": "block+r", "score": 1},
        "reason": {"why": "refused:block+r"}}
    assert document["run"]["resumable"] is False
    assert len(document["steps"]) == 3
    assert {p.relative_to(run_root): p.read_bytes() for p in run_root.rglob("*") if p.is_file()} == before
def test_imported_improve_uses_std_declaration_identity_and_no_typed_body(tmp_path):
    path = write_source(tmp_path, "demo/main", '''
      (import std/dynamic/improve :as dynamic :only (improve))
      (import std/improve :only (Decision Improvement))
      (export main)
      (defrecord Draft (title String) (score Int))
      (defrecord Feedback (note String))
      (defrecord Blocker (why String))
      (defworkflow main () -> Improvement[Draft Feedback Blocker]
        (improve (record (title "approve") (score 0))
          (fn (current) (record (variant "APPROVE") (evidence (record (note "ok")))))
          (fn (current feedback) current) 1))
    ''')
    program = compile_source(path, tmp_path)
    assert "std/dynamic/improve::improve" in program.definitions
    assert "std/improve::improve" not in program.definitions
    helper = program.definitions["std/dynamic/improve::improve"]
    assert helper["params"] == ("initial", "review", "revise", "limit")
    assert helper["boundary"] is None
    assert any(name.startswith("std/improve::Improvement[") for name in program.schemas)
    path.unlink()
    round_trip = DynamicProgram.from_artifact(program.artifact())
    assert evaluate(round_trip, {}).json_value() == {
        "variant": "APPROVED", "value": {"title": "approve", "score": 0},
        "evidence": {"note": "ok"},
    }
