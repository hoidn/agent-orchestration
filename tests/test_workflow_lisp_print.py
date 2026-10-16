"""`print` writes one canonical JSON line per evaluation to stdout and returns its operand."""

from __future__ import annotations

import subprocess
import sys

from tests.test_workflow_evaluated_repl import (
    FEEDBACK,
    PLAN,
    SOURCE,
    _env,
    _fixture,
    _repl,
    _run,
    _run_root,
    _typed_values,
)


BODY = '''(let* ((draft (provider-result providers.plan :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Plan))
           (shown (print draft.steps))
           (feedback (provider-result providers.review :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Feedback)))
      (print feedback))'''
BAD = '{"findings":"not a list"}'
LINES = ['["one","two"]', '{"findings":[]}']
PROPAGATION = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Plan (steps List[String]))
  (defrecord Feedback (findings List[String]))
  (defworkflow shown-steps ((plan Plan)) -> List[String] (print plan.steps))
  (defworkflow run ((task String) (scale Float)) -> Feedback
    (let* ((draft (provider-result providers.plan :prompt prompts.base
                    :inputs (task) :model "chosen-model" :effort "low" :returns Plan))
           (steps (call shown-steps :plan draft))
           (echoed (list/map ((step steps)) (print step))))
      (provider-result providers.review :prompt prompts.base
        :inputs (task) :model "chosen-model" :effort "low" :returns Feedback))))'''


def _printed(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line in LINES]


def test_print_writes_each_value_line_and_returns_the_operand(tmp_path):
    result = _run(tmp_path, _fixture(tmp_path, SOURCE.format(target="2.35", body=BODY)), "task=x", "scale=1.5")
    assert result.returncode == 0, result.stderr
    assert _printed(result.stdout) == LINES
    shown = _repl(tmp_path, [":result", "shown", ":quit"], run_id=_run_root(tmp_path).name)
    assert _typed_values(shown.stdout) == [(FEEDBACK, "Feedback"), (PLAN["steps"], "List[String]")]


def _resume(root, run_id, results):
    return subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "resume", run_id],
        cwd=root, env=_env(root, results), capture_output=True, text=True, check=False,
    )


def test_a_resumed_attempt_prints_replayed_and_new_values_once(tmp_path):
    fixture = _fixture(tmp_path, SOURCE.format(target="2.35", body=BODY))
    stopped = _run(tmp_path, fixture, "task=x", "scale=1.5", results=(PLAN, BAD, FEEDBACK))
    assert stopped.returncode != 0
    assert _printed(stopped.stdout) == [LINES[0]]
    resumed = _resume(tmp_path, _run_root(tmp_path).name, (PLAN, BAD, FEEDBACK))
    assert resumed.returncode == 0, resumed.stderr
    assert _printed(resumed.stdout) == LINES
    assert len((tmp_path / "requests.jsonl").read_text().splitlines()) == 3




def test_readers_replay_the_program_without_printing(tmp_path):
    fixture = _fixture(tmp_path, SOURCE.format(target="2.35", body=BODY))
    assert _run(tmp_path, fixture, "task=x", "scale=1.5").returncode == 0
    run_id = _run_root(tmp_path).name
    result = _repl(tmp_path, ["(print feedback.findings)", ":quit"], run_id=run_id)
    assert (result.returncode, result.stdout.splitlines()) == (0, ["[]", ": List[String]"])
    completed = _resume(tmp_path, run_id, (PLAN, FEEDBACK))
    assert (completed.returncode, _printed(completed.stdout)) == (0, [])
    report = subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "report", "--run-id", run_id,
         "--runs-root", str(tmp_path / ".orchestrate" / "runs"), "--format", "md"],
        cwd=tmp_path, env=_env(tmp_path), capture_output=True, text=True, check=False,
    )
    assert (report.returncode, _printed(report.stdout)) == (0, [])


def test_the_sink_reaches_called_workflows_and_list_map_bodies(tmp_path):
    result = _run(tmp_path, _fixture(tmp_path, PROPAGATION), "task=x", "scale=1.5")
    assert result.returncode == 0, result.stderr
    expected = ['["one","two"]', '"one"', '"two"']
    assert [line for line in result.stdout.splitlines() if line in expected] == expected
