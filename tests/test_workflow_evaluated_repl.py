"""Public CLI behavior for the evaluated Workflow Lisp REPL."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from orchestrator.run_lock import run_writer_lock
from tests.test_workflow_evaluated_providers import _fixture as _provider_fixture
from tests.test_workflow_evaluated_resume import _snapshot


SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
  (defmodule main) (export run)
  (defrecord Plan (steps List[String]))
  (defrecord Feedback (findings List[String]))
  (defproc plan-size ((plan Plan)) -> Int :effects () :lowering inline
    (list/length plan.steps))
  (defproc request-feedback ((task String)) -> Feedback
    :effects ((uses-provider providers.review)) :lowering inline
    (provider-result providers.review :prompt prompts.base :inputs (task)
      :model "chosen-model" :effort "low" :returns Feedback))
  (defun count-steps ((plan Plan)) -> Int (list/length plan.steps))
  (defun count-through-proc ((plan Plan)) -> Int (plan-size plan))
  (defworkflow run ((task String) (scale Float)) -> Feedback
    {body}))'''

BODY = '''(let* ((draft (provider-result providers.plan :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Plan))
           (feedback (provider-result providers.review :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Feedback)))
      feedback)'''

PLAN = {"steps": ["one", "two"]}
FEEDBACK = {"findings": []}


def _fixture(root: Path, source: str | None = None):
    fixture = _provider_fixture(root, source or SOURCE.format(target="2.35", body=BODY))
    fixture[1].write_text(
        json.dumps({"providers.plan": "codex", "providers.review": "codex"}),
        encoding="utf-8",
    )
    return fixture


def _env(root: Path, results=(PLAN, FEEDBACK)):
    payloads = [value if isinstance(value, str) else json.dumps(value) for value in results]
    env = {
        **os.environ,
        "PATH": str(root / "bin"),
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PROVIDER_SHIM_RESULTS": json.dumps(payloads),
    }
    env.pop("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", None)
    return env


def _run(root: Path, fixture, *inputs: str, results=(PLAN, FEEDBACK)):
    source, providers, prompts, _request = fixture
    return subprocess.run(
        [
            sys.executable, "-B", "-m", "orchestrator", "run", str(source),
            "--source-root", str(source.parent),
            "--provider-externs-file", str(providers),
            "--prompt-externs-file", str(prompts),
            *(item for value in inputs for item in ("--input", value)),
        ],
        cwd=root, env=_env(root, results), capture_output=True, text=True, check=False,
    )


def _repl(root: Path, lines, *, fixture=None, run_id=None, state_dir=None,
          results=(PLAN, FEEDBACK)):
    command = [sys.executable, "-B", "-m", "orchestrator", "repl"]
    if fixture is not None:
        source, providers, prompts, _request = fixture
        command.extend((
            str(source), "--source-root", str(source.parent),
            "--provider-externs-file", str(providers),
            "--prompt-externs-file", str(prompts),
        ))
    if run_id is not None:
        command.extend(("--run-id", run_id))
    if state_dir is not None:
        command.extend(("--state-dir", str(state_dir)))
    return subprocess.run(
        command, input="\n".join(lines) + "\n", cwd=root, env=_env(root, results),
        capture_output=True, text=True, check=False,
    )


def _run_root(root: Path, state_dir: Path | None = None) -> Path:
    runs = state_dir or root / ".orchestrate" / "runs"
    (run_root,) = runs.iterdir()
    return run_root


def _typed_values(stdout: str):
    lines = stdout.splitlines()
    values = []
    for index, line in enumerate(lines[:-1]):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if lines[index + 1].startswith(": "):
            values.append((value, lines[index + 1][2:]))
    return values


def _report(root: Path, run_root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "report", "--run-id", run_root.name,
         "--runs-root", str(run_root.parent), "--format", "json"],
        cwd=root, env=_env(root), capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _binding_names(stdout: str) -> list[str]:
    return [line.split(" : ", 1)[0] for line in stdout.splitlines() if " : " in line]


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_public_repl_attaches_to_completed_run_and_evaluates_typed_values(tmp_path, target):
    fixture = _fixture(tmp_path, SOURCE.format(target=target, body=BODY))
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    outputs = _report(tmp_path, run_root)["run"]["workflow_outputs"]
    before = _snapshot(tmp_path / ".orchestrate")

    with run_writer_lock(run_root):
        repl = _repl(tmp_path, [
            ":bindings", "feedback.findings",
            "(list/empty? feedback.findings)", "(list/length draft.steps)", "(plan-size draft)",
            "(count-steps draft)", "(count-through-proc draft)", ":result", ":quit",
        ], fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert _typed_values(repl.stdout) == [
        ([], "List[String]"), (True, "Bool"), (2, "Int"), (2, "Int"), (2, "Int"),
        (2, "Int"),
        (outputs, "Feedback"),
    ], f"stdout={repl.stdout!r}\nstderr={repl.stderr!r}"
    assert {"task", "scale", "draft", "feedback"} <= set(_binding_names(repl.stdout))
    assert _snapshot(tmp_path / ".orchestrate") == before


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_public_completed_repl_reads_lists_without_mutating_run(tmp_path, target):
    fixture = _fixture(tmp_path, SOURCE.format(target=target, body=BODY))
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    outputs = _report(tmp_path, run_root)["run"]["workflow_outputs"]
    before = _snapshot(tmp_path / ".orchestrate")
    requests = (tmp_path / "requests.jsonl").read_bytes()

    with run_writer_lock(run_root):
        repl = _repl(tmp_path, [
            "feedback.findings", "(list/length draft.steps)",
            "(list/empty? feedback.findings)", ":result", ":quit",
        ], fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert _typed_values(repl.stdout) == [
        ([], "List[String]"), (2, "Int"), (True, "Bool"), (outputs, "Feedback"),
    ], f"stdout={repl.stdout!r}\nstderr={repl.stderr!r}"
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests


def test_interrupted_provider_captures_outer_scope_and_effect_identity(tmp_path):
    body = '''(let* ((draft (provider-result providers.plan :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Plan))
           (feedback (provider-result providers.review :prompt prompts.base
                    :inputs ((if true (let* ((scratch (+ 1 2))) task) task))
                    :model "chosen-model" :effort "low" :returns Feedback)))
      feedback)'''
    fixture = _fixture(tmp_path, SOURCE.format(target="2.35", body=body))
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0",
               results=(PLAN, "not json"))
    assert run.returncode == 1, run.stderr
    run_root = _run_root(tmp_path)
    starts = [json.loads(row) for row in (run_root / "memo.jsonl").read_text().splitlines()
              if json.loads(row)["record"] == "started"]
    identity = starts[-1]["identity"]
    before = _snapshot(tmp_path / ".orchestrate")

    repl = _repl(tmp_path, [":bindings", "feedback", ":quit"],
                 fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert set(_binding_names(repl.stdout)) == {"task", "scale", "draft"}
    assert len(_binding_names(repl.stdout)) == 3
    assert f"position: {identity}" in repl.stdout
    assert "[name_unknown]" in repl.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before


def test_interrupted_callee_keeps_inner_shadowed_binding(tmp_path):
    body = '''(let* ((draft (provider-result providers.plan :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Plan)))
      (let* ((task "workflow shadow") (feedback (request-feedback "callee shadow")))
        feedback))'''
    fixture = _fixture(tmp_path, SOURCE.format(target="2.35", body=body))
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0",
               results=(PLAN, "not json"))
    assert run.returncode == 1, run.stderr
    run_root = _run_root(tmp_path)

    repl = _repl(tmp_path, [":bindings", '(= task "callee shadow")', "draft.steps",
                            "feedback", ":quit"], fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert _binding_names(repl.stdout) == ["task"]
    assert _typed_values(repl.stdout) == [(True, "Bool")]
    assert repl.stderr.count("[name_unknown]") == 2


def test_effectful_expressions_refuse_without_changing_run_and_session_recovers(tmp_path):
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    before = _snapshot(tmp_path / ".orchestrate")
    requests = (tmp_path / "requests.jsonl").read_bytes()
    direct_effect = (
        '(provider-result providers.review :prompt prompts.base :inputs (task) '
        ':model "chosen-model" :effort "low" :returns Feedback)'
    )

    repl = _repl(tmp_path, [direct_effect, "(request-feedback task)", "not_a_name",
                            "(list/empty? feedback.findings)", "(count-steps draft)", ":quit"],
                 fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert repl.stderr.count("[repl_effect_refused]") == 2
    assert "[name_unknown]" in repl.stderr
    assert _typed_values(repl.stdout) == [(True, "Bool"), (2, "Int")], repl.stdout
    assert (tmp_path / "requests.jsonl").read_bytes() == requests
    assert _snapshot(tmp_path / ".orchestrate") == before


def test_changed_loaded_source_refuses_attachment(tmp_path):
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    source = fixture[0]
    changed = SOURCE.format(target="2.35", body=BODY.replace(
        '"chosen-model"', '"changed-model"', 1))
    source.write_text(changed, encoding="utf-8")

    repl = _repl(tmp_path, [":quit"], fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 2
    assert "[resume_program_changed]" in repl.stderr


def test_recipe_only_attachment_does_not_publish_build_cache(tmp_path):
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    build_cache = tmp_path / ".orchestrate" / "build"
    shutil.rmtree(build_cache, ignore_errors=True)

    repl = _repl(tmp_path, ["draft.steps", ":quit"], run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert _typed_values(repl.stdout) == [(["one", "two"], "List[String]")]
    assert not build_cache.exists()


def test_attachment_without_rebuild_recipe_refuses_readonly(tmp_path):
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=typed task", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_bytes())
    header.pop("resume_request")
    header_path.write_text(json.dumps(header, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    before = _snapshot(tmp_path / ".orchestrate")

    repl = _repl(tmp_path, [":quit"], run_id=run_root.name)

    assert repl.returncode == 2
    assert "[resume_request_missing]" in repl.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before


@pytest.mark.parametrize("after_draft", [False, True])
def test_failed_pure_expression_capture_has_only_in_scope_bindings(tmp_path, after_draft):
    draft = '''(draft (provider-result providers.plan :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Plan))'''
    bad = "(bad (/ 1.0 scale))"
    bindings = [bad, draft] if not after_draft else [draft, bad]
    body = f'''(let* ({" ".join(bindings)}
           (feedback (provider-result providers.review :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Feedback)))
      feedback)'''
    fixture = _fixture(tmp_path, SOURCE.format(target="2.35", body=body))
    run = _run(tmp_path, fixture, "task=typed task", "scale=0.0")
    assert run.returncode == 1, run.stderr
    run_root = _run_root(tmp_path)
    before = _snapshot(tmp_path / ".orchestrate")

    repl = _repl(tmp_path, [":bindings", ":result", ":quit"], run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    expected = {"task", "scale", "draft"} if after_draft else {"task", "scale"}
    assert set(_binding_names(repl.stdout)) == expected
    assert len(_binding_names(repl.stdout)) == len(expected)
    assert "position: failed:pure_expr_division_by_zero" in repl.stdout
    assert "[repl_no_result]" in repl.stderr
    assert _snapshot(tmp_path / ".orchestrate") == before


def test_repl_run_uses_session_and_command_state_directories(tmp_path):
    fixture = _fixture(tmp_path)
    source, providers, prompts, _request = fixture
    session_root, override_root = tmp_path / "runs", tmp_path / "override-runs"
    load = (f":load {source} --source-root {source.parent} "
            f"--provider-externs-file {providers} --prompt-externs-file {prompts}")
    run_line = ":run --input task=typed --input scale=2.0"
    override_line = f":run --state-dir {override_root} --input task=typed --input scale=2.0"

    repl = _repl(tmp_path, [load, run_line, "draft.steps", override_line, "draft.steps", ":quit"],
                 state_dir=session_root, results=(PLAN, FEEDBACK, PLAN, FEEDBACK))

    assert repl.returncode == 0, repl.stderr
    ids = re.findall(r"^run_id: (\S+)$", repl.stdout, re.MULTILINE)
    assert len(ids) == 2
    assert (session_root / ids[0] / "run.json").is_file()
    assert (override_root / ids[1] / "run.json").is_file()
    assert _typed_values(repl.stdout) == [(["one", "two"], "List[String]")]*2
    assert repl.stdout.count("exit_code: 0") == 2


def test_nested_enum_binding_keeps_its_frontend_type(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defenum Color red blue)
      (defrecord Input (color Color))
      (defworkflow run ((input Input)) -> Color
        (let* ((local input.color)) local)))'''
    fixture = _fixture(tmp_path, source)
    run = _run(tmp_path, fixture, 'input={"color":"red"}')
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)

    repl = _repl(tmp_path, [":bindings", "(= local input.color)", ":result", ":quit"],
                 fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert "local : Color" in repl.stdout
    assert _typed_values(repl.stdout) == [(True, "Bool"), ("red", "Color")]


@pytest.mark.parametrize("seed_block", [False, True])
def test_completed_root_loop_captures_done_result_not_seed_halt(tmp_path, seed_block):
    seed = "(let* ((a 3)) a)" if seed_block else "0"
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run () -> Int
        (loop/recur :max 1 :state (loop-state (i Int {seed}))
          :on-exhausted 99 (fn (state) (done 7)))))'''
    fixture = _fixture(tmp_path, source)
    run = _run(tmp_path, fixture)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)

    repl = _repl(tmp_path, [":bindings", ":result", ":quit"],
                 fixture=fixture, run_id=run_root.name)

    assert repl.returncode == 0, repl.stderr
    assert "position: halt" in repl.stdout
    assert _typed_values(repl.stdout) == [(7, "Int")]
    assert "state" in _binding_names(repl.stdout)
    if seed_block:
        assert "a" not in _binding_names(repl.stdout)


def test_public_repl_introspection_smoke(tmp_path):
    """Run the maintained authored specimen through deterministic provider shims."""
    import hashlib
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.sexpr import ListExpr, SymbolAtom

    example = Path(__file__).parents[1] / "workflows/examples/plan_review_execute.orc"
    fixture = _fixture(tmp_path, example.read_text(encoding="utf-8"))
    source = tmp_path / example.name
    fixture[0].rename(source)
    providers, prompts = fixture[1:3]
    shutil.copyfile(example.parent / "inputs/plan_review_execute/providers.json", providers)
    prompts.write_text("{}", encoding="utf-8")
    shutil.copy2(tmp_path / "bin/codex", tmp_path / "bin/claude")
    fixture = (source, providers, prompts, None)
    execution = {"summary": "fixture completed"}
    replies = (PLAN, FEEDBACK, PLAN, execution)
    run = _run(tmp_path, fixture, "task=fixture inspection smoke", results=replies)
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    before = _snapshot(tmp_path / ".orchestrate")
    requests = (tmp_path / "requests.jsonl").read_bytes()
    with run_writer_lock(run_root):
        repl = _repl(tmp_path, [":browse", ":info Plan", ":info revise-plan", ":source revise-plan",
                              ":type revised.steps", ":bindings", ":result", ":quit"],
                     fixture=fixture, run_id=run_root.name, results=replies)
    assert repl.returncode == 0, repl.stderr
    assert "steps: List[String]" in repl.stdout
    assert "task: text" in repl.stdout and "findings: value" in repl.stdout
    assert "type: List[String]\neffects: ()" in repl.stdout
    assert "revised : Plan" in repl.stdout
    assert _typed_values(repl.stdout) == [(execution, "Execution")]
    parsed = read_sexpr_text(source.read_text(encoding="utf-8"), source_path=str(source))
    declaration = next(form for form in parsed.items[0].items if isinstance(form, ListExpr)
                       and len(form.items) > 1 and isinstance(form.items[0], SymbolAtom)
                       and form.items[0].value == "defprompt" and isinstance(form.items[1], SymbolAtom)
                       and form.items[1].value == "revise-plan")
    expected = source.read_text(encoding="utf-8")[declaration.span.start.offset:declaration.span.end.offset]
    assert expected in repl.stdout
    assert f"loaded snapshot: sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}" in repl.stdout
    assert len(requests.splitlines()) == 4
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests
