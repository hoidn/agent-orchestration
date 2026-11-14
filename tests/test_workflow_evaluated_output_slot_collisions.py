"""Output slots that collide are refused before a fresh launch; a committed row replays as recorded.

`specs/io.md` (provider output contracts): before launch, slot names and structured-result artifact names are
disjoint, slot destinations are pairwise distinct, none is the result bundle and each stays in the workspace. The
check refuses what fails or aliases after launch whatever the provider returns, and only where a provider is about
to be started: a union field that only some variants have is checked after launch, and a pending agent turn whose
work completed commits. Through the public CLI with stand-in providers on a closed PATH; assertions are on exit
codes, diagnostic codes, launches, `started` rows and attempt directories, never on prompt or message text.
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
LEAVES_WORKSPACE = "prompt_output_position_contract_mismatch"
REPO = Path(__file__).resolve().parents[1]


def _written(root: Path) -> tuple[int, int]:
    """`started` rows in every run's memo, and attempt directories: what a launch leaves."""
    runs = root / ".orchestrate" / "runs"
    started = sum(json.loads(line)["record"] == "started"
                  for memo in runs.glob("*/memo.jsonl") for line in memo.read_text(encoding="utf-8").splitlines())
    return started, len(list(runs.glob("*/effects/*/attempt-*")))


def _artifacts(root: Path) -> None:
    (root / "artifacts").mkdir()
    for name in ("report.txt", "other.txt"):
        (root / "artifacts" / name).write_text("report\n", encoding="utf-8")


def _plain(root: Path, row_id: str) -> tuple[subprocess.CompletedProcess, int]:
    row = PROVIDER_ROWS[row_id]
    _artifacts(root)
    done = provider_fixture._cli(root, provider_fixture._fixture(root, row.source), extra=row.inputs,
                                 payload=row.payload)
    return done, len(provider_fixture._requests(root))


@pytest.mark.parametrize(("row_id", "code"), [("A3-path", NAME_CLASH), ("A3-string", NAME_CLASH), ("B1", PATH_CLASH)])
def test_plain_provider_with_colliding_slots_is_refused_without_a_launch(tmp_path, row_id, code):
    done, launches = _plain(tmp_path, row_id)
    assert (done.returncode, f"[{code}]" in done.stderr, launches, _report(tmp_path)["steps"], _written(tmp_path)) \
        == (1, True, 0, [], (0, 0)), done.stderr


@pytest.mark.parametrize("row_id", ["A3-two-names", "B1-two-paths"])
def test_control_plain_provider_with_distinct_slots_commits(tmp_path, row_id):
    done, launches = _plain(tmp_path, row_id)
    assert (done.returncode, launches) == (0, 1), done.stderr


UNION_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defpath Report :kind relpath :under "artifacts" :must-exist false)
  (defunion Choice (Ready (n Int) READY_EXTRA) (Skip (reason String)))
  (defprompt review (:fills (SLOT :path :out Report)) -> Choice "Out={SLOT}")
  (defworkflow run ((message String) (report Report)) -> Choice
    (provider-result providers.review :prompt (review :SLOT report))))'''
READY = '{"variant":"Ready","n":5}'
# case: slot, extra field of Ready, the stand-in's answer, wanted (exit, launches, printed code)
UNION_CASES = {
    "field-of-one-variant-other-returned": ("reason", "", READY, (0, 1, None)),
    "field-of-one-variant-that-one-returned": ("reason", "", '{"variant":"Skip","reason":"r"}',
                                               (1, 1, "provider_result_invalid")),
    "field-of-every-variant": ("reason", "(reason String)", '{"variant":"Ready","n":5,"reason":"r"}',
                               (1, 0, NAME_CLASH)),
    "discriminant": ("variant", "", READY, (1, 0, NAME_CLASH)),
}


@pytest.mark.parametrize("case", sorted(UNION_CASES))
def test_union_slot_is_refused_before_launch_only_when_every_answer_collides(tmp_path, case):
    slot, extra, payload, wanted = UNION_CASES[case]
    _artifacts(tmp_path)
    source = UNION_SOURCE.replace("READY_EXTRA", extra).replace("SLOT", slot)
    done = provider_fixture._cli(tmp_path, provider_fixture._fixture(tmp_path, source),
                                 extra=("--input", "report=artifacts/report.txt"), payload=payload)
    code = next((code for code in (NAME_CLASH, "provider_result_invalid") if f"[{code}]" in done.stderr), None)
    assert (done.returncode, len(provider_fixture._requests(tmp_path)), code) == wanted, done.stderr


LINK_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defpath Report :kind relpath :under "artifacts" :must-exist false)
  (defrecord Result (ok Bool))
  (defprompt review (:fills (a :path :out Report)) -> Result "A={a}")
  (defworkflow run ((message String) (report Report)) -> Result
    (let* ((made (command-result mk :argv ("python" "mk.py") :returns Int))
           (done (provider-result providers.review :prompt (review :a report))))
      done)))'''
MAKE_LINK = '''import os
from pathlib import Path
Path("artifacts").mkdir(exist_ok=True)
os.symlink(os.environ["OUTSIDE"], "artifacts/out")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("1")
'''


def test_slot_through_a_link_an_earlier_step_made_out_of_the_workspace_is_refused(tmp_path, monkeypatch):
    root, outside = tmp_path / "workspace", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "mk.py").write_text(MAKE_LINK, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps({"mk": {"stable_command": ["python", "mk.py"],
                                                           "closure": ["mk.py"]}}), encoding="utf-8")
    monkeypatch.setenv("OUTSIDE", str(outside))
    done = provider_fixture._cli(root, provider_fixture._fixture(root, LINK_SOURCE), extra=(
        "--input", "report=artifacts/out/x.txt", "--command-boundaries-file", "commands.json"))
    # The command's attempt is the one `started` row and the one attempt directory.
    assert (done.returncode, f"[{LEAVES_WORKSPACE}]" in done.stderr, len(provider_fixture._requests(root)),
            _written(root)) == (1, True, 0, (1, 1)), done.stderr


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


def _agent_source(code: str) -> str:
    field, fills, template, arguments = AGENT_SHAPES[code]
    return (AGENT_SOURCE.replace("FIELD", field).replace("FILLS", fills).replace("TEMPLATE", template)
            .replace("ARGUMENTS", arguments))


def _agent_workspace(root: Path, monkeypatch, source: str, mode: str) -> None:
    install_agent_shims(root / "bin", monkeypatch, codex_home=root / "codex", claude_home=root / "claude",
                        plan={"claude": [{"mode": mode, "result": {"text": "d"}}], "codex": []})
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace"}))
    _artifacts(root)


# A run before the check: the same CLI with the launch-time agent-turn check switched off. A pending agent turn
# cannot be kept as a recorded fixture (its launch cwd is pinned and does not relocate), so it is built here.
WITHOUT_THE_CHECK = ("import runpy, orchestrator.workflow.evaluated.agent_turns as turns; "
                     "turns._check_output_slots = lambda *args, **kwargs: None; "
                     "runpy.run_module('orchestrator', run_name='__main__')")


def _agent_cli(root: Path, *argv: str, without_the_check: bool = False) -> subprocess.CompletedProcess:
    head = ["-c", WITHOUT_THE_CHECK] if without_the_check else ["-m", "orchestrator"]
    return subprocess.run([sys.executable, "-B", *head, *argv], cwd=root, capture_output=True, text=True, check=False,
                          timeout=180, env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"})


AGENT_RUN = ("run", "main.orc", "--provider-externs-file", "providers.json", "--input", "task=t",
             "--input", "report=artifacts/report.txt")


@pytest.mark.parametrize("code", sorted(AGENT_SHAPES))
def test_agent_turn_with_colliding_slots_is_refused_without_a_launch(tmp_path, monkeypatch, code):
    _agent_workspace(tmp_path, monkeypatch, _agent_source(code), "success")
    failed = _agent_cli(tmp_path, *AGENT_RUN)
    launched = (tmp_path / "bin" / ".claude.calls").exists()
    # The agent allocation `designer` is the one `started` row and the one attempt directory; the turn left none.
    assert (failed.returncode, f"[{code}]" in failed.stderr, launched, _written(tmp_path)) == (1, True, False, (1, 1)), \
        failed.stderr


@pytest.mark.parametrize("program", ["unchanged", "edited"])
def test_pending_agent_turn_whose_work_completed_commits_on_resume_without_a_call(tmp_path, monkeypatch, program):
    source = _agent_source(PATH_CLASH).replace(":timeout-sec 60", ":timeout-sec 5")
    _agent_workspace(tmp_path, monkeypatch, source, "complete-then-hang")
    first = _agent_cli(tmp_path, *AGENT_RUN, without_the_check=True)
    assert "[agent_turn_unresolved]" in first.stderr, first.stderr
    if program == "edited":
        (tmp_path / "main.orc").write_text(source.replace("(defprompt", "(defrecord Unused (u Int))\n  (defprompt"),
                                           encoding="utf-8")
    resumed = _agent_cli(tmp_path, "resume", _report(tmp_path)["run"]["run_id"])
    calls = len((tmp_path / "bin" / ".claude.calls").read_text(encoding="utf-8"))
    assert (resumed.returncode, calls, _report(tmp_path)["run"]["status"]) == (0, 1, "completed"), resumed.stderr


def test_pending_agent_turn_that_would_be_dispatched_again_refuses_in_preflight(tmp_path, monkeypatch):
    """The stand-in times out before writing its store: nothing to recover, so `resume` would dispatch anew."""
    source = _agent_source(PATH_CLASH).replace(":timeout-sec 60", ":timeout-sec 5")
    _agent_workspace(tmp_path, monkeypatch, source, "timeout")
    first = _agent_cli(tmp_path, *AGENT_RUN, without_the_check=True)
    assert "[agent_turn_unresolved]" in first.stderr, first.stderr
    run_id = _report(tmp_path)["run"]["run_id"]
    memo = tmp_path / ".orchestrate" / "runs" / run_id / "memo.jsonl"
    before = memo.read_bytes()
    refused = _agent_cli(tmp_path, "resume", run_id)
    calls = len((tmp_path / "bin" / ".claude.calls").read_text(encoding="utf-8"))
    assert (refused.returncode, f"[{PATH_CLASH}]" in refused.stderr, calls, memo.read_bytes()) \
        == (2, True, 1, before), refused.stderr


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
    assert (failed.returncode, f"[{code}]" in failed.stderr, public_events(root), _written(root)) \
        == (1, True, [], (0, 0)), failed.stderr


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
OPEN_PRE_CHANGE = Path(__file__).parent / "fixtures" / "output_alias_open_pre_change"


def _recorded(root: Path, fixture: Path, run_id: str | None = None) -> str:
    """Copy a run recorded before the check, with its program, externs and stand-in, into `root`; its run id."""
    for name in ("main.orc", "providers.json", "prompts.json", "two.md"):
        shutil.copy2(fixture / name, root / name)
    _artifacts(root)
    shim = root / "bin" / "codex"
    shim.parent.mkdir()
    shim.write_text(f"#!{sys.executable}\n" + (fixture / "codex_shim.py").read_text(encoding="utf-8"), encoding="utf-8")
    shim.chmod(0o700)
    (run_id,) = [run_id] if run_id else [path.name for path in (fixture / "runs").iterdir()]
    shutil.copytree(fixture / "runs" / run_id, root / ".orchestrate" / "runs" / run_id)
    return run_id


def test_resume_replays_two_slots_committed_on_one_path_before_the_check(tmp_path):
    """Recorded before this check: step `one` committed slots `a` and `b` on one file, step `two` failed."""
    resumed = _orchestrator(tmp_path, "resume", _recorded(tmp_path, PRE_CHANGE))
    assert (resumed.returncode, _launches(tmp_path)) == (0, 1), resumed.stderr


def test_resume_at_a_pending_start_recorded_before_the_check_refuses_in_preflight(tmp_path):
    run_id = _recorded(tmp_path, OPEN_PRE_CHANGE, "20261114T185034Z-9aoawq")
    memo = tmp_path / ".orchestrate" / "runs" / run_id / "memo.jsonl"
    before = memo.read_bytes()
    refused = _orchestrator(tmp_path, "resume", run_id)
    assert (refused.returncode, f"[{PATH_CLASH}]" in refused.stderr, _launches(tmp_path), memo.read_bytes(),
            _written(tmp_path)) == (2, True, 0, before, (1, 1)), refused.stderr


def test_resume_after_a_failed_attempt_recorded_before_the_check_is_refused_without_a_launch(tmp_path):
    run_id = _recorded(tmp_path, OPEN_PRE_CHANGE, "20261114T185036Z-q87d4k")
    refused = _orchestrator(tmp_path, "resume", run_id)
    assert (refused.returncode, f"[{PATH_CLASH}]" in refused.stderr, _launches(tmp_path), _written(tmp_path)) \
        == (1, True, 0, (1, 1)), refused.stderr
