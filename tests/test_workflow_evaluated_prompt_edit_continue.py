"""Editing a prompt mid-run and continuing, through the public CLI.

Pins the behavior documented in docs/runtime_execution_lifecycle.md, "Edit a
prompt and continue": a prompt kept in a file bound by the prompt manifest can
be edited and the run continued; an inline `defprompt` edit is a program change.
Assertions are on exit codes, refusal codes, the attempts `report --format json`
shows and the provider calls made, never on prompt text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

STEP = '''(provider-result providers.review :prompt {prompt}
                  :model "m" :effort "low"{returns})'''

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  {declarations}
  (defworkflow run ((message String)) -> Result
    (let* ((one {one})
           (two {two})
           (three {three}))
      three)))'''

FILE_STEP = STEP.format(prompt="prompts.{name} :inputs (message)", returns=" :returns Result")
INLINE_TWO = '(defprompt two (:fills (message :text)) -> Result "Step two: {message}")'

# Stand-in provider: logs the sha256 of each prompt it receives to calls.log, fails the call numbered
# SHIM_FAIL_CALL, else returns {"ok": true}.
SHIM = r"""import hashlib, os, sys
from pathlib import Path
digest = hashlib.sha256(sys.stdin.buffer.read()).hexdigest()
log = Path("calls.log")
calls = (len(log.read_text().splitlines()) if log.exists() else 0) + 1
with log.open("a") as stream:
    stream.write(digest + "\n")
if os.environ.get("SHIM_FAIL_CALL") == str(calls):
    sys.exit(9)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}')
"""

TWO = "workflow:main::run / two"


def _source(*, inline_two: bool) -> str:
    two = STEP.format(prompt="(two :message message)", returns="") if inline_two else FILE_STEP.format(name="two")
    return SOURCE.format(declarations=INLINE_TWO if inline_two else "", one=FILE_STEP.format(name="one"),
                         two=two, three=FILE_STEP.format(name="three"))


def _fixture(root: Path, *, inline_two: bool = False) -> None:
    (root / "main.orc").write_text(_source(inline_two=inline_two), encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    prompts = {f"prompts.{name}": {"asset_file": f"{name}.md"} for name in ("one", "two", "three")}
    (root / "prompts.json").write_text(json.dumps(prompts), encoding="utf-8")
    for name in ("one", "two", "three"):
        (root / f"{name}.md").write_text(f"Step {name}.\n", encoding="utf-8")
    shim = root / "bin" / "codex"
    shim.parent.mkdir()
    shim.write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
    shim.chmod(0o700)


def _orchestrator(root: Path, *argv: str, fail_call: int | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
           "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("SHIM_FAIL_CALL", None)
    if fail_call is not None:
        env["SHIM_FAIL_CALL"] = str(fail_call)
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *argv], cwd=root, env=env,
                          capture_output=True, text=True, check=False)


def _run(root: Path, *, fail_call: int | None = None) -> subprocess.CompletedProcess[str]:
    return _orchestrator(root, "run", "main.orc", "--provider-externs-file", "providers.json",
                         "--prompt-externs-file", "prompts.json", "--input", "message=hi", fail_call=fail_call)


def _report(root: Path) -> dict:
    shown = _orchestrator(root, "report", "--format", "json")
    assert shown.returncode == 0, shown.stderr
    return json.loads(shown.stdout)


def _run_id(root: Path) -> str:
    return _report(root)["run"]["run_id"]


def _attempts(root: Path) -> dict[str, int]:
    """The latest attempt of each step, by the step name that ends its identity."""
    return {step["identity"].rsplit(" / ", 1)[-1]: step["attempt"] for step in _report(root)["steps"]}


def _prompt_digests(root: Path) -> list[str]:
    """The digest of the prompt each provider call received, in call order."""
    return (root / "calls.log").read_text().splitlines()


def _revise(path: Path) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace("Step ", "Revised step "), encoding="utf-8")


def test_editing_the_prompt_file_of_a_failed_step_resumes_with_a_new_attempt(tmp_path):
    _fixture(tmp_path)
    assert _run(tmp_path, fail_call=2).returncode == 1
    _revise(tmp_path / "two.md")
    resumed = _orchestrator(tmp_path, "resume", _run_id(tmp_path))
    assert resumed.returncode == 0, resumed.stderr
    assert _attempts(tmp_path) == {"one": 1, "two": 2, "three": 1}
    _one, two_failed, two_retried, _three = _prompt_digests(tmp_path)
    assert two_failed != two_retried


def test_editing_the_prompt_file_of_a_step_not_yet_run_resumes_without_refusal(tmp_path):
    _fixture(tmp_path)
    assert _run(tmp_path, fail_call=2).returncode == 1
    _revise(tmp_path / "three.md")
    resumed = _orchestrator(tmp_path, "resume", _run_id(tmp_path))
    assert resumed.returncode == 0, resumed.stderr
    assert _attempts(tmp_path) == {"one": 1, "two": 2, "three": 1}


def test_editing_a_committed_prompt_file_refuses_then_invalidate_reruns_the_suffix(tmp_path):
    _fixture(tmp_path)
    assert _run(tmp_path).returncode == 0
    run_id = _run_id(tmp_path)
    _revise(tmp_path / "two.md")
    refused = _orchestrator(tmp_path, "resume", run_id)
    assert refused.returncode == 2
    assert "[effect_input_diverged]" in refused.stderr and "source:asset_file:two.md" in refused.stderr
    assert _attempts(tmp_path) == {"one": 1, "two": 1, "three": 1}
    assert _orchestrator(tmp_path, "invalidate", run_id, TWO).returncode == 0
    resumed = _orchestrator(tmp_path, "resume", run_id)
    assert resumed.returncode == 0, resumed.stderr
    assert _attempts(tmp_path) == {"one": 1, "two": 2, "three": 2}


def test_restoring_a_committed_prompt_file_resumes_without_running_anything(tmp_path):
    _fixture(tmp_path)
    assert _run(tmp_path).returncode == 0
    run_id, original = _run_id(tmp_path), (tmp_path / "two.md").read_bytes()
    _revise(tmp_path / "two.md")
    assert _orchestrator(tmp_path, "resume", run_id).returncode == 2
    (tmp_path / "two.md").write_bytes(original)
    resumed = _orchestrator(tmp_path, "resume", run_id)
    assert resumed.returncode == 0, resumed.stderr
    assert len(_prompt_digests(tmp_path)) == 3


def test_editing_an_inline_prompt_refuses_as_a_program_change(tmp_path):
    _fixture(tmp_path, inline_two=True)
    assert _run(tmp_path, fail_call=2).returncode == 1
    _revise(tmp_path / "main.orc")
    refused = _orchestrator(tmp_path, "resume", _run_id(tmp_path))
    assert refused.returncode == 2
    assert "[resume_program_changed]" in refused.stderr
    assert _attempts(tmp_path) == {"one": 1, "two": 1}
