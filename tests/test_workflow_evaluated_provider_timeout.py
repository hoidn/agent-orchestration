"""A provider call's timeout from a name: it reaches the launch and the `policy` part, and a value below 1 refuses
the step before its `started` record.

Through the public CLI with a stand-in `codex` on a closed PATH. Assertions are on exit codes, diagnostic codes,
memo records, attempt directories and the stand-in's launch log, never on prompt or message text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tests.agent_session_shims import closed_path

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defprompt ask (:fills (q :text)) -> Result "Answer {q}.")
  (defworkflow run ((message String) (limit Int)) -> Result
    (provider-result providers.review :model "m" :effort "low" :timeout-sec TIMEOUT :prompt (ask :q message))))'''

# Stand-in provider: logs each launch in calls.log; hangs when SHIM_HANG is set, else returns {"ok": true}.
SHIM = r"""import os, sys, time
from pathlib import Path
sys.stdin.buffer.read()
with Path("calls.log").open("a") as stream:
    stream.write("launched\n")
if os.environ.get("SHIM_HANG"):
    time.sleep(30)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}')
"""
PRE_CHANGE = Path(__file__).parent / "fixtures" / "provider_timeout_literal_pre_change"


def _install_shim(root: Path, shim: str) -> None:
    binary = root / "bin" / "codex"
    binary.parent.mkdir(parents=True)
    binary.write_text(f"#!{sys.executable}\n" + shim, encoding="utf-8")
    binary.chmod(0o700)


def _workspace(root: Path, timeout: str) -> Path:
    _install_shim(root, SHIM)
    (root / "main.orc").write_text(SOURCE.replace("TIMEOUT", timeout), encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    return root


def _orchestrator(root: Path, *argv: str, hang: bool = False) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": closed_path(root / "bin"), "PYTHONPATH": str(Path(__file__).parents[1]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("SHIM_HANG", None)
    if hang:
        env["SHIM_HANG"] = "1"
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *argv], cwd=root, env=env,
                          capture_output=True, text=True, check=False, timeout=120)


def _run(root: Path, limit: int, *, hang: bool = False) -> subprocess.CompletedProcess[str]:
    return _orchestrator(root, "run", "main.orc", "--provider-externs-file", "providers.json",
                         "--input", "message=hi", "--input", f"limit={limit}", hang=hang)


def _records(root: Path, record: str) -> list[dict]:
    rows = [json.loads(line) for memo in (root / ".orchestrate" / "runs").glob("*/memo.jsonl")
            for line in memo.read_text(encoding="utf-8").splitlines()]
    return [row for row in rows if row["record"] == record]


def _launches(root: Path) -> int:
    log = root / "calls.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


def test_timeout_from_an_input_reaches_the_launch_and_the_policy_part(tmp_path):
    hung = _workspace(tmp_path / "hung", "limit")
    timed_out = _run(hung, 1, hang=True)
    (step,) = json.loads(_orchestrator(hung, "report", "--format", "json").stdout)["steps"]
    assert (timed_out.returncode, step["error"]["code"], step["error"]["exit_info"]["error"]["context"]["timeout_sec"]) \
        == (1, "provider_timeout", 1), timed_out.stderr

    roots = [_workspace(tmp_path / name, timeout) for name, timeout in (("named", "limit"), ("literal", "60"),
                                                                       ("other", "limit"))]
    assert [_run(root, limit).returncode for root, limit in zip(roots, (60, 60, 61))] == [0, 0, 0]
    named, literal, other = (_records(root, "committed")[0]["input_parts"]["policy"] for root in roots)
    assert (named == literal, named == other) == (True, False)


def test_nonpositive_timeout_refuses_before_started(tmp_path):
    root = _workspace(tmp_path, "limit")

    refused = _run(root, 0)

    attempts = list((root / ".orchestrate" / "runs").glob("*/effects/*/attempt-*"))
    assert (refused.returncode, "[provider_timeout_nonpositive]" in refused.stderr, _records(root, "started"),
            attempts, _launches(root)) == (1, True, [], [], 0), refused.stderr


def test_nonpositive_timeout_recovery_offers_a_new_run_or_an_edit_not_resume(tmp_path):
    root = _workspace(tmp_path, "limit")

    lines = _run(root, 0).stderr.splitlines()

    fresh = [line for line in lines if line.startswith("    ") and " run main.orc " in line]
    assert (len(fresh), "--input limit=0" in fresh[0], any("--accept-changes" in line for line in lines),
            [line for line in lines if line.startswith("resume ") or "about [" in line]) == (1, True, True, []), lines


def test_run_recorded_with_a_literal_timeout_resumes_unchanged(tmp_path):
    """A run the package recorded before the operand: step `one` committed, step `two` failed; never regenerated."""
    for name in ("main.orc", "providers.json"):
        shutil.copy2(PRE_CHANGE / name, tmp_path / name)
    _install_shim(tmp_path, (PRE_CHANGE / "codex_shim.py").read_text(encoding="utf-8"))
    shutil.copytree(PRE_CHANGE / "runs", tmp_path / ".orchestrate" / "runs")
    (run_id,) = [path.name for path in (tmp_path / ".orchestrate" / "runs").iterdir()]

    resumed = _orchestrator(tmp_path, "resume", run_id)

    assert (resumed.returncode, _launches(tmp_path), [row["attempt"] for row in _records(tmp_path, "committed")]) \
        == (0, 1, [1, 2]), resumed.stderr
