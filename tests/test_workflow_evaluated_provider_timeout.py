"""A provider call's timeout from a name: it reaches the launch and the `policy` part, and a value below 1 refuses
the step before its `started` record.

Through the public CLI with a stand-in `codex` on a closed PATH. Assertions are on exit codes, diagnostic codes,
memo records, attempt directories and the stand-in's launch log, never on prompt or message text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
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


def _env(root: Path) -> dict[str, str]:
    return {**os.environ, "PATH": closed_path(root / "bin"), "PYTHONPATH": str(Path(__file__).parents[1]),
           "PYTHONDONTWRITEBYTECODE": "1"}


def _orchestrator(root: Path, *argv: str, hang: bool = False) -> subprocess.CompletedProcess[str]:
    env = _env(root)
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


def _printed(lines: list[str], word: str) -> list[str]:
    """The indented commands of a refusal's recovery lines whose subcommand is `word`."""
    return [line for line in lines if line.startswith("    ") and f" -m orchestrator {word} " in line]


def _shell(root: Path, line: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(shlex.split(line), cwd=root, env=_env(root), capture_output=True, text=True,
                          check=False, timeout=120)


def test_nonpositive_default_continues_by_the_printed_run_after_the_edit(tmp_path):
    root = _workspace(tmp_path, "limit")
    source = root / "main.orc"
    source.write_text(source.read_text().replace("(limit Int)", "(limit Int :default 0)"), encoding="utf-8")

    lines = _orchestrator(root, "run", "main.orc", "--provider-externs-file", "providers.json",
                          "--input", "message=hi").stderr.splitlines()
    source.write_text(source.read_text().replace(":default 0", ":default 5"), encoding="utf-8")
    (fresh,) = _printed(lines, "run")

    assert ([line for line in lines if "--accept-changes" in line and ":default" not in line],
            _shell(root, fresh).returncode, _launches(root)) == ([], 0, 1), lines


LIMIT_FROM_A_STEP = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defrecord Limits (sec Int))
  (defprompt ask (:fills (q :text)) -> Result "Answer {q}.")
  (defworkflow run ((message String)) -> List[Result]
    (let* ((limits (command-result read-limits :argv ("python" "limits.py") :returns Limits)))
      (list/map-effect ((x (list 5 limits.sec))) :max 2
        (provider-result providers.review :model "m" :timeout-sec x :prompt (ask :q message))))))'''
READ_LIMITS = '''import json, os
from pathlib import Path
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"sec": int(Path("sec.txt").read_text())}))
'''


def test_nonpositive_value_from_a_step_names_both_steps_and_continues_by_invalidate(tmp_path):
    root = _workspace(tmp_path, "x")
    (root / "main.orc").write_text(LIMIT_FROM_A_STEP, encoding="utf-8")
    (root / "limits.py").write_text(READ_LIMITS, encoding="utf-8")
    (root / "sec.txt").write_text("0", encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(
        {"read-limits": {"stable_command": ["python", "limits.py"], "closure": ["limits.py"]}}), encoding="utf-8")

    lines = _orchestrator(root, "run", "main.orc", "--provider-externs-file", "providers.json",
                          "--command-boundaries-file", "commands.json", "--input", "message=hi").stderr.splitlines()
    (invalidate,) = [line for line in _printed(lines, "invalidate") if line.endswith("'workflow:main::run / limits'")]
    (resume,) = _printed(lines, "resume")
    (root / "sec.txt").write_text("5", encoding="utf-8")
    continued = [_shell(root, line).returncode for line in (invalidate, resume)]

    # The first item launched before the refusal and runs again after `invalidate`, with the second.
    refused_step = [line for line in lines if line.startswith("workflow:main::run / ") and "launched nothing" in line]
    assert (len(refused_step), continued, _launches(root)) == (1, [0, 0], 3), lines


MAP_OVER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defprompt ask (:fills (q :text)) -> Result "Answer {q}.")
  (defworkflow run ((message String) (limit Int)) -> List[Result]
    (list/map-effect ((x (list 5 ITEM))) :max 2
      (provider-result providers.review :model "m" :timeout-sec x :prompt (ask :q message)))))'''


def _asserted_sources(lines: list[str]) -> list[str]:
    """Lines that state, rather than suppose, where the timeout came from."""
    return [line for line in lines if "comes from the result" in line and not line.startswith("if ")]


def test_nonpositive_map_item_written_in_the_source_continues_by_the_edit(tmp_path):
    root = _workspace(tmp_path, "x")
    (root / "main.orc").write_text(MAP_OVER.replace("ITEM", "0"), encoding="utf-8")
    lines = _run(root, 5).stderr.splitlines()
    (root / "main.orc").write_text(MAP_OVER.replace("ITEM", "6"), encoding="utf-8")

    planned = _orchestrator(root, "resume", json.loads(_orchestrator(root, "report", "--format", "json").stdout)
                            ["run"]["run_id"]).stderr.splitlines()
    accepted = _shell(root, next(line for line in planned if "--accept-changes=" in line and line.startswith("    ")))

    assert (_asserted_sources(lines), any("edit it" in line for line in lines), accepted.returncode) \
        == ([], True, 0), lines


def test_nonpositive_map_item_from_an_input_continues_by_the_printed_run(tmp_path):
    root = _workspace(tmp_path, "x")
    (root / "main.orc").write_text(MAP_OVER.replace("ITEM", "limit"), encoding="utf-8")
    lines = _run(root, 0).stderr.splitlines()

    fresh = [line.replace("limit=0", "limit=5") for line in _printed(lines, "run")]

    assert (_asserted_sources(lines), len(fresh), [_shell(root, line).returncode for line in fresh]) \
        == ([], 1, [0]), lines


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
