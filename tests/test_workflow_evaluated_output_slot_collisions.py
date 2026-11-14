"""Output slots that collide are refused before a fresh launch; a committed row replays as recorded.

`specs/io.md` (provider output contracts): before launch, slot names and structured-result artifact names are
disjoint, slot destinations are pairwise distinct and none is the result bundle. Through the public CLI with
stand-in providers on a closed PATH; assertions are on exit codes, diagnostic codes, launches and the attempts
`report --format json` shows, never on prompt or message text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.providers import ProviderPerformerError, ResolvedProviderInput, check_output_slots
from tests import test_workflow_evaluated_providers as provider_fixture
from tests.agent_session_shims import install_agent_shims
from tests.test_workflow_evaluated_prompt_source_unreadable import _launches, _orchestrator, _report
from tests.test_workflow_lisp_defect_backlog import PROVIDER_ROWS
from tests.workflow_evaluated_phased_helpers import public_case, public_cli, public_events

NAME_CLASH = "duplicate_artifact_name"
PATH_CLASH = "prompt_output_position_destination_collision"


def _plain(root: Path, row_id: str) -> tuple[subprocess.CompletedProcess, int]:
    row = PROVIDER_ROWS[row_id]
    (root / "artifacts").mkdir()
    for name in ("report.txt", "other.txt"):
        (root / "artifacts" / name).write_text("report\n", encoding="utf-8")
    done = provider_fixture._cli(root, provider_fixture._fixture(root, row.source), extra=row.inputs,
                                 payload=row.payload)
    return done, len(provider_fixture._requests(root))


@pytest.mark.parametrize(("row_id", "code"), [("A3-path", NAME_CLASH), ("A3-string", NAME_CLASH), ("B1", PATH_CLASH)])
def test_plain_provider_with_colliding_slots_is_refused_without_a_launch(tmp_path, row_id, code):
    done, launches = _plain(tmp_path, row_id)
    assert (done.returncode, f"[{code}]" in done.stderr, launches, _report(tmp_path)["steps"]) == (1, True, 0, []), \
        done.stderr


@pytest.mark.parametrize("row_id", ["A3-two-names", "B1-two-paths"])
def test_control_plain_provider_with_distinct_slots_commits(tmp_path, row_id):
    done, launches = _plain(tmp_path, row_id)
    assert (done.returncode, launches) == (0, 1), done.stderr


AGENT_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defpath Report :kind relpath :under "artifacts" :must-exist false)
  (defrecord Draft (text String) FIELD)
  (defprompt draft (:fills FILLS) -> Draft "TEMPLATE")
  (defworkflow run ((task String) (report Report)) -> Draft
    (let* ((designer (agent providers.claude :model "planner" :effort "high")))
      (provider-result designer :prompt (draft ARGUMENTS) :timeout-sec 60))))'''
AGENT_SHAPES = {
    NAME_CLASH: ("(report String)", "(report :path :out Report)", "R={report}", ":report report"),
    PATH_CLASH: ("", "(a :path :out Report) (b :path :out Report)", "A={a} B={b}", ":a report :b report"),
}


@pytest.mark.parametrize("code", sorted(AGENT_SHAPES))
def test_agent_turn_with_colliding_slots_is_refused_without_a_launch(tmp_path, monkeypatch, code):
    field, fills, template, arguments = AGENT_SHAPES[code]
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={"claude": [{"mode": "success", "result": {"text": "d"}}], "codex": []})
    (tmp_path / "main.orc").write_text(AGENT_SOURCE.replace("FIELD", field).replace("FILLS", fills)
                                       .replace("TEMPLATE", template).replace("ARGUMENTS", arguments), encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace"}))
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "report.txt").write_text("report\n", encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--provider-externs-file", "providers.json",
         "--input", "task=t", "--input", "report=artifacts/report.txt"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False, timeout=120)
    launched = (tmp_path / "bin" / ".claude.calls").exists()
    assert (failed.returncode, f"[{code}]" in failed.stderr, launched) == (1, True, False), failed.stderr


PHASED_SHAPES = {
    NAME_CLASH: [("(defrecord Review (approved Bool))", "(defrecord Review (approved Bool) (report String))")],
    PATH_CLASH: [("(report :path :out Report))", "(report :path :out Report) (copy :path :out Report))"),
                 (":report report)", ":report report :copy report)"), ("{report}.", "{report} {copy}.")],
}


@pytest.mark.parametrize("code", sorted(PHASED_SHAPES))
def test_phased_provider_with_colliding_slots_is_refused_without_a_process(tmp_path, code):
    args, _env, root = case = public_case(tmp_path)
    source = root / "tests/fixtures/phased_239/main.orc"
    text = source.read_text(encoding="utf-8").replace('"2.39"', '"2.40"')
    for old, new in PHASED_SHAPES[code]:
        assert old in text
        text = text.replace(old, new)
    source.write_text(text, encoding="utf-8")
    failed = public_cli(case, args)
    assert (failed.returncode, f"[{code}]" in failed.stderr, public_events(root)) == (1, True, []), failed.stderr


def _resolved(*paths: str) -> ResolvedProviderInput:
    outputs = [{"name": f"slot{index}", "path": path, "type": "string", "required": True}
               for index, path in enumerate(paths)]
    return ResolvedProviderInput(prompt="", policy={}, input_parts={}, expected_outputs=outputs)


OK_CONTRACT = {"contract": {"kind": "output_bundle", "payload": {"fields": [{"name": "ok", "json_pointer": "/ok"}]}}}


def test_a_slot_on_the_result_bundle_is_refused(tmp_path):
    with pytest.raises(ProviderPerformerError) as refused:
        check_output_slots(OK_CONTRACT, _resolved("runs/r/result.json"), workspace=tmp_path,
                           result_path="runs/r/result.json")
    assert refused.value.code == PATH_CLASH


PRE_CHANGE = Path(__file__).parent / "fixtures" / "output_alias_pre_change"


def test_resume_replays_two_slots_committed_on_one_path_before_the_check(tmp_path):
    """Recorded before this check: step `one` committed slots `a` and `b` on one file, step `two` failed."""
    for name in ("main.orc", "providers.json", "prompts.json", "two.md"):
        shutil.copy2(PRE_CHANGE / name, tmp_path / name)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "report.txt").write_text("report\n", encoding="utf-8")
    shim = tmp_path / "bin" / "codex"
    shim.parent.mkdir()
    shim.write_text(f"#!{sys.executable}\n" + (PRE_CHANGE / "codex_shim.py").read_text(encoding="utf-8"),
                    encoding="utf-8")
    shim.chmod(0o700)
    shutil.copytree(PRE_CHANGE / "runs", tmp_path / ".orchestrate" / "runs")
    (run_id,) = [path.name for path in (tmp_path / ".orchestrate" / "runs").iterdir()]
    resumed = _orchestrator(tmp_path, "resume", run_id)
    assert (resumed.returncode, _launches(tmp_path)) == (0, 1), resumed.stderr
