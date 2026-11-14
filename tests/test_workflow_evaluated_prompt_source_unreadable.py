"""A declared prompt file that cannot be read fails the step before any provider launch.

Through the public CLI with stand-in providers on a closed PATH. Assertions are on exit codes,
diagnostic codes, the attempts `report --format json` shows and the stand-in's launch record,
never on prompt or message text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.agent_session_shims import closed_path, install_agent_shims

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (provider-result providers.review :prompt prompts.one :inputs (message)
      :model "m" :effort "low" :returns Result)))'''

# Stand-in provider: records each launch in calls.log, then returns {"ok": true}.
SHIM = r"""import os, sys
from pathlib import Path
sys.stdin.buffer.read()
with Path("calls.log").open("a") as stream:
    stream.write("launched\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}')
"""


def _fixture(root: Path, kind: str) -> Path:
    (root / "main.orc").write_text(SOURCE, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    (root / "prompts.json").write_text(json.dumps({"prompts.one": {kind: "one.md"}}), encoding="utf-8")
    shim = root / "bin" / "codex"
    shim.parent.mkdir()
    shim.write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
    shim.chmod(0o700)
    return root / "one.md"


def _break(path: Path, state: str) -> None:
    if state == "directory":
        path.mkdir()
    elif state == "unreadable":
        path.write_text("Authored prompt.\n", encoding="utf-8")
        path.chmod(0)


def _restore(path: Path) -> None:
    if path.is_dir():
        path.rmdir()
    elif path.exists():
        path.chmod(0o600)
    path.write_text("Authored prompt.\n", encoding="utf-8")


def _orchestrator(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": closed_path(root / "bin"),
           "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *argv], cwd=root, env=env,
                          capture_output=True, text=True, check=False, timeout=120)


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return _orchestrator(root, "run", "main.orc", "--provider-externs-file", "providers.json",
                         "--prompt-externs-file", "prompts.json", "--input", "message=hi")


def _report(root: Path) -> dict:
    shown = _orchestrator(root, "report", "--format", "json")
    assert shown.returncode == 0, shown.stderr
    return json.loads(shown.stdout)


def _launches(root: Path) -> int:
    log = root / "calls.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


STATES = ["missing", "directory"] + ([] if os.geteuid() == 0 else ["unreadable"])


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("kind", ["input_file", "asset_file"])
def test_unreadable_prompt_file_fails_with_its_source_code(tmp_path, kind, state):
    _break(_fixture(tmp_path, kind), state)
    failed = _run(tmp_path)
    assert (failed.returncode, f"[{kind}_read_failed]" in failed.stderr) == (1, True), failed.stderr


@pytest.mark.parametrize("kind", ["input_file", "asset_file"])
def test_unreadable_prompt_file_never_launches_the_provider(tmp_path, kind):
    _fixture(tmp_path, kind)
    _run(tmp_path)
    assert _launches(tmp_path) == 0


@pytest.mark.parametrize("kind", ["input_file", "asset_file"])
def test_unreadable_prompt_file_records_no_attempt(tmp_path, kind):
    _fixture(tmp_path, kind)
    _run(tmp_path)
    assert _report(tmp_path)["steps"] == []


@pytest.mark.parametrize("kind", ["input_file", "asset_file"])
def test_resume_after_restoring_the_prompt_file_runs_the_step_once(tmp_path, kind):
    path = _fixture(tmp_path, kind)
    _run(tmp_path)
    _restore(path)
    resumed = _orchestrator(tmp_path, "resume", _report(tmp_path)["run"]["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    assert (_launches(tmp_path), [step["attempt"] for step in _report(tmp_path)["steps"]]) == (1, [1])


def test_resume_with_the_prompt_file_still_missing_fails_again_without_a_launch(tmp_path):
    _fixture(tmp_path, "input_file")
    _run(tmp_path)
    resumed = _orchestrator(tmp_path, "resume", _report(tmp_path)["run"]["run_id"])
    assert ("[input_file_read_failed]" in resumed.stderr, _launches(tmp_path)) == (True, 0), resumed.stderr


def test_deleting_a_committed_prompt_file_refuses_resume_without_a_launch(tmp_path):
    path = _fixture(tmp_path, "input_file")
    path.write_text("Authored prompt.\n", encoding="utf-8")
    assert _run(tmp_path).returncode == 0
    path.unlink()
    refused = _orchestrator(tmp_path, "resume", _report(tmp_path)["run"]["run_id"])
    assert (refused.returncode, "[effect_input_diverged]" in refused.stderr, _launches(tmp_path)) == (2, True, 1), \
        refused.stderr


def test_empty_prompt_file_is_still_a_prompt(tmp_path):
    _fixture(tmp_path, "input_file").write_bytes(b"")
    assert (_run(tmp_path).returncode, _launches(tmp_path)) == (0, 1)


AGENT_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Draft (text String))
  (defworkflow run ((task String)) -> Draft
    (let* ((designer (agent providers.claude :model "planner" :effort "high")))
      (provider-result designer :prompt prompts.one :inputs (task) :returns Draft :timeout-sec 60))))'''


def test_agent_turn_with_a_missing_prompt_file_never_launches(tmp_path, monkeypatch):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex",
                        claude_home=tmp_path / "claude",
                        plan={"claude": [{"mode": "success", "result": {"text": "d"}}], "codex": []})
    (tmp_path / "main.orc").write_text(AGENT_SOURCE, encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace"}))
    (tmp_path / "prompts.json").write_text(json.dumps({"prompts.one": {"input_file": "one.md"}}))
    failed = subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--provider-externs-file", "providers.json",
         "--prompt-externs-file", "prompts.json", "--input", "task=t"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False, timeout=120)
    assert ("[input_file_read_failed]" in failed.stderr, (tmp_path / "bin" / ".claude.calls").exists()) == (True, False), \
        failed.stderr
