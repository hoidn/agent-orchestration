"""Editing a prompt mid-run and continuing, through the public CLI.

Pins the behavior documented in docs/runtime_execution_lifecycle.md, "Edit a
prompt and continue": a prompt kept in a file bound by the prompt manifest can
be edited and the run continued; an inline `defprompt` edit is a program change.
Assertions are on exit codes, refusal codes and which attempts ran, never on
prompt text.
"""

from __future__ import annotations

import hashlib
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

# Stand-in provider: counts calls in calls.log, fails the call numbered SHIM_FAIL_CALL, else returns {"ok": true}.
SHIM = r'''import os, sys
from pathlib import Path
sys.stdin.buffer.read()
log = Path("calls.log")
calls = (len(log.read_text().splitlines()) if log.exists() else 0) + 1
with log.open("a") as stream:
    stream.write("call\n")
if os.environ.get("SHIM_FAIL_CALL") == str(calls):
    sys.exit(9)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}')
'''

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


def _run_root(root: Path) -> Path:
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


def _attempts(root: Path) -> dict[str, list[int]]:
    """Attempt ordinals started for each step, by the step name that ends its identity."""
    started: dict[str, list[int]] = {}
    for line in (_run_root(root) / "memo.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["record"] == "started":
            started.setdefault(row["identity"].rsplit(" / ", 1)[-1], []).append(row["attempt"])
    return started


def _prompt_bytes(root: Path, identity: str, attempt: int) -> bytes:
    effect = hashlib.sha256(identity.encode()).hexdigest()
    return (_run_root(root) / "effects" / effect / f"attempt-{attempt}" / "prompt.txt").read_bytes()


def _edit(path: Path) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace("Step two", "Step two, revised"), encoding="utf-8")


def test_editing_the_prompt_file_of_a_failed_step_resumes_with_a_new_attempt(tmp_path):
    _fixture(tmp_path)
    assert _run(tmp_path, fail_call=2).returncode == 1
    _edit(tmp_path / "two.md")
    resumed = _orchestrator(tmp_path, "resume", _run_root(tmp_path).name)
    assert resumed.returncode == 0, resumed.stderr
    assert _attempts(tmp_path) == {"one": [1], "two": [1, 2], "three": [1]}
    assert _prompt_bytes(tmp_path, TWO, 1) != _prompt_bytes(tmp_path, TWO, 2)


def test_editing_a_committed_prompt_file_refuses_then_invalidate_reruns_the_suffix(tmp_path):
    _fixture(tmp_path)
    assert _run(tmp_path).returncode == 0
    run_id = _run_root(tmp_path).name
    _edit(tmp_path / "two.md")
    refused = _orchestrator(tmp_path, "resume", run_id)
    assert refused.returncode == 2
    assert "[effect_input_diverged]" in refused.stderr and "source:asset_file:two.md" in refused.stderr
    assert _attempts(tmp_path) == {"one": [1], "two": [1], "three": [1]}
    assert _orchestrator(tmp_path, "invalidate", run_id, TWO).returncode == 0
    resumed = _orchestrator(tmp_path, "resume", run_id)
    assert resumed.returncode == 0, resumed.stderr
    assert _attempts(tmp_path) == {"one": [1], "two": [1, 2], "three": [1, 2]}


def test_editing_an_inline_prompt_refuses_as_a_program_change(tmp_path):
    _fixture(tmp_path, inline_two=True)
    assert _run(tmp_path, fail_call=2).returncode == 1
    _edit(tmp_path / "main.orc")
    refused = _orchestrator(tmp_path, "resume", _run_root(tmp_path).name)
    assert refused.returncode == 2
    assert "[resume_program_changed]" in refused.stderr
    assert _attempts(tmp_path) == {"one": [1], "two": [1]}
