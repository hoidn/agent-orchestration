"""Review fixes of Phase 3a: processes of the run left alive, everything the flag accepts, "needed".

Stand-in scripts only, no provider or model call; helpers come from the main script-fix module.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tests.test_cli_run_output import cli, env
from tests.test_workflow_evaluated_script_fix_retry import (
    BAD, GOOD, IDENTITIES, ITEM_GOOD, SELF_WRITE, _provider_env, failed_rows, fix, item, kill_when_started,
    refuses_without_writes, run_four, run_id, run_parallel, started, write_four_steps, write_parallel,
)


# Review fixes: live processes of a failed attempt, everything the flag accepts, segment match, "needed"

DETACHED_WRITER = '''import subprocess, sys
child = """import time
from pathlib import Path
time.sleep(2)
Path("s3.py").open("a").write("# written by a leftover process\\\\n")
Path("child-done").write_text("")
"""
subprocess.Popen([sys.executable, "-c", child], start_new_session=True,
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sys.exit(3)
'''
WAITING_PARENT = '''import subprocess, sys
subprocess.run([sys.executable, "-c", "import time; time.sleep(0.3)"], check=True)
sys.exit(3)
'''


def test_failed_attempt_with_a_live_detached_child_records_changed_and_resume_refuses(tmp_path: Path) -> None:
    import time
    write_four_steps(tmp_path, {"s3": DETACHED_WRITER})
    assert run_four(tmp_path).returncode == 1
    deadline = time.monotonic() + 30
    while not (tmp_path / "child-done").exists():
        assert time.monotonic() < deadline
        time.sleep(0.05)

    (failed,) = failed_rows(tmp_path)
    assert failed["closure"] == "changed"
    refuses_without_writes(tmp_path, "effect_input_diverged")


def test_command_that_waits_for_its_children_records_unchanged(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": WAITING_PARENT})

    assert run_four(tmp_path).returncode == 1

    (failed,) = failed_rows(tmp_path)
    assert failed["closure"] == "unchanged"


def test_parallel_refusal_names_every_attempt_the_flag_accepts(tmp_path: Path) -> None:
    write_parallel(tmp_path, {"alpha": BAD, "beta": SELF_WRITE})
    assert run_parallel(tmp_path).returncode == 1
    assert {row["identity"]: row["closure"] for row in failed_rows(tmp_path)}[item(1)] == "changed"
    (tmp_path / "alpha" / "work" / "probe.py").write_text(ITEM_GOOD, encoding="utf-8")

    refused = refuses_without_writes(tmp_path, "effect_input_diverged")

    lines = refused.stderr.splitlines()
    offer = next(index for index, line in enumerate(lines) if line.endswith(" --accept-changes"))
    before_offer = "\n".join(lines[1:offer])
    assert item(0) in before_offer and item(1) in before_offer


def test_serial_step_whose_binder_looks_like_a_parallel_segment_retries_on_plain_resume(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": BAD})
    source = tmp_path / "main.orc"
    source.write_text(source.read_text(encoding="utf-8").replace("(c (command-result s3", "(par-map:c (command-result s3")
                      .replace("s4.py\" c)", "s4.py\" par-map:c)"), encoding="utf-8")
    assert run_four(tmp_path).returncode == 1
    (failed,) = failed_rows(tmp_path)
    assert failed["identity"] == "workflow:main::run / par-map:c"
    fix(tmp_path, "s3")

    resumed = cli(tmp_path, "resume", run_id(tmp_path))

    assert resumed.returncode == 0, resumed.stderr


SLEEP_ONCE = ('import json, os, sys, time\nfrom pathlib import Path\n'
              'if Path("slow").exists():\n    Path("started-s3").write_text("")\n    time.sleep(60)\n'
              'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[1]) + 1))\n')


def test_killed_step_with_unchanged_files_needs_no_flag(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": SLEEP_ONCE})
    (tmp_path / "slow").write_text("", encoding="utf-8")
    kill_when_started(tmp_path, [tmp_path / "started-s3"],
                      ["run", "main.orc", "--command-boundaries-file", "commands.json", "--input", "n=1"])
    (tmp_path / "slow").unlink()

    refuses_without_writes(tmp_path, "resume_preflight_failed", "--accept-changes")
    resumed = cli(tmp_path, "resume", run_id(tmp_path))

    assert resumed.returncode == 0, resumed.stderr
    assert started(resumed.stderr) == [IDENTITIES["s3"], IDENTITIES["s4"]]


# Re-review: a live process of ANY attempt of the run makes a failure `changed`; no false positive otherwise

def _detached_writer(target: str, done: str, delay: float) -> str:
    """A command body that starts, once, a detached process appending to `target` after `delay` seconds."""
    child = (f"import time\nfrom pathlib import Path\ntime.sleep({delay})\n"
             f"Path({target!r}).open('a').write('# written by a leftover process\\n')\nPath({done!r}).write_text('')\n")
    return ("import subprocess, sys\nfrom pathlib import Path\n"
            f"if not Path({done!r} + '.spawned').exists():\n"
            f"    Path({done!r} + '.spawned').write_text('')\n"
            f"    subprocess.Popen([sys.executable, '-c', {child!r}], start_new_session=True,\n"
            "                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n")


def _wait_for(path: Path) -> None:
    import time
    deadline = time.monotonic() + 30
    while not path.exists():
        assert time.monotonic() < deadline
        time.sleep(0.05)


def test_writer_left_by_an_earlier_attempt_of_the_step_makes_a_later_failure_changed(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": _detached_writer("s3.py", "child-done", 6) + "sys.exit(3)\n"})
    assert run_four(tmp_path).returncode == 1
    retried = cli(tmp_path, "resume", run_id(tmp_path))  # files still equal: attempt 2 runs and fails
    assert retried.returncode == 1, retried.stderr
    _wait_for(tmp_path / "child-done")

    assert [row["closure"] for row in failed_rows(tmp_path)] == ["changed", "changed"]
    refuses_without_writes(tmp_path, "effect_input_diverged")


def test_writer_left_by_an_earlier_step_makes_a_later_failure_changed(tmp_path: Path) -> None:
    s2 = _detached_writer("s3.py", "child-done", 3) + GOOD.replace("{name}", "s2")
    write_four_steps(tmp_path, {"s2": s2, "s3": BAD})
    assert run_four(tmp_path).returncode == 1
    _wait_for(tmp_path / "child-done")

    (failed,) = failed_rows(tmp_path)
    assert (failed["identity"], failed["closure"]) == (IDENTITIES["s3"], "changed")
    refuses_without_writes(tmp_path, "effect_input_diverged")


AFTER_PROVIDER_AND_MAP = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Int
    (let* ((p (provider-result providers.review :prompt prompts.base :inputs (message) :model "m" :effort "low"
                :returns Result))
           (m (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
                :workspace (string/concat repo "/work")
                (command-result fetch :argv ("python" "probe.py" "${loop.index}") :returns Int)))
           (c (command-result bad :argv ("python" "bad.py" p.ok) :returns Int)))
      c)))'''


def test_failure_after_a_provider_step_and_a_completed_map_records_unchanged(tmp_path: Path) -> None:
    from tests.test_workflow_evaluated_providers import _fixture
    _source, providers, prompts, _ = _fixture(tmp_path, AFTER_PROVIDER_AND_MAP)
    write_parallel(tmp_path, {})
    (tmp_path / "main.orc").write_text(AFTER_PROVIDER_AND_MAP, encoding="utf-8")
    (tmp_path / "bad.py").write_text(BAD, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps({
        "fetch": {"stable_command": ["python", "probe.py"], "closure": []},
        "bad": {"stable_command": ["python", "bad.py"], "closure": ["bad.py"]}}), encoding="utf-8")

    result = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--provider-externs-file",
        providers.name, "--prompt-externs-file", prompts.name, "--command-boundaries-file", "commands.json",
        "--input", "message=x"], cwd=tmp_path, env=_provider_env(tmp_path, "success"), capture_output=True, text=True)

    assert result.returncode == 1, result.stderr
    assert [(row["identity"], row["closure"]) for row in failed_rows(tmp_path)] == [
        ("workflow:main::run / c", "unchanged")]


AFTER_AGENT_TURNS = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Draft (text String))
  (defprompt draft (:fills (task :text)) -> Draft "Draft: {task}")
  (defworkflow run ((task String)) -> Int
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
           (a1 (provider-result designer :prompt (draft :task task) :timeout-sec 60))
           (a2 (provider-result designer :prompt (draft :task a1.text) :timeout-sec 60))
           (c (command-result bad :argv ("python" "bad.py" a2.text) :returns Int)))
      c)))'''


def test_failure_after_observed_agent_turns_records_unchanged(tmp_path: Path, monkeypatch) -> None:
    """Agent turns start the run's tmux observation server; it and the agents carry no locator at the failure."""
    from tests.agent_session_shims import install_agent_shims
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={"claude": [{"mode": "success", "result": {"text": "d1"}},
                                         {"mode": "success", "result": {"text": "d2"}}], "codex": []})
    (tmp_path / "main.orc").write_text(AFTER_AGENT_TURNS, encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace"}))
    (tmp_path / "bad.py").write_text(BAD, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps(
        {"bad": {"stable_command": ["python", "bad.py"], "closure": ["bad.py"]}}), encoding="utf-8")

    result = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--source-root", ".",
        "--provider-externs-file", "providers.json", "--command-boundaries-file", "commands.json", "--input", "task=t"],
        cwd=tmp_path, env={**env(), "PATH": os.environ["PATH"]}, capture_output=True, text=True)

    assert result.returncode == 1, result.stderr
    assert "[provider_observation] agent view" in result.stderr
    assert [(row["identity"], row["closure"]) for row in failed_rows(tmp_path)] == [
        ("workflow:main::run / c", "unchanged")]


def test_accept_changes_after_invalidate_prints_the_unreached_attempts_it_accepts(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": SLEEP_ONCE})
    (tmp_path / "slow").write_text("", encoding="utf-8")
    kill_when_started(tmp_path, [tmp_path / "started-s3"],
                      ["run", "main.orc", "--command-boundaries-file", "commands.json", "--input", "n=1"])
    (tmp_path / "slow").unlink()
    assert cli(tmp_path, "invalidate", run_id(tmp_path), IDENTITIES["s1"]).returncode == 0

    accepted = cli(tmp_path, "resume", run_id(tmp_path), "--accept-changes")

    assert accepted.returncode == 0, accepted.stderr
    lines = accepted.stderr.splitlines()
    first_start = next(index for index, line in enumerate(lines) if line.startswith("start "))
    assert any(line.startswith(f"  {IDENTITIES['s3']}: ") for line in lines[:first_start]), accepted.stderr


MANY = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list {items}))) :max 22 :parallel 4
      :workspace (string/concat repo "/work")
      (command-result fetch :argv ("python" "probe.py" "${{loop.index}}") :returns Int))))
'''


def test_the_list_of_accepted_attempts_stops_at_twenty(tmp_path: Path) -> None:
    names = [f"i{index:02d}" for index in range(22)]
    (tmp_path / "main.orc").write_text(MANY.format(items=" ".join(f'"{name}"' for name in names)), encoding="utf-8")
    for name in names:
        (tmp_path / name / "work").mkdir(parents=True)
        (tmp_path / name / "work" / "probe.py").write_text(SELF_WRITE, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps(
        {"fetch": {"stable_command": ["python", "probe.py"], "closure": []}}), encoding="utf-8")
    assert run_parallel(tmp_path).returncode == 1
    assert len(failed_rows(tmp_path)) == 22

    refused = refuses_without_writes(tmp_path, "effect_input_diverged")

    listed = [line for line in refused.stderr.splitlines() if line.startswith("  workflow:main::run / par-map:")]
    assert (len(listed), "  ... and 2 more" in refused.stderr.splitlines()) == (20, True)
