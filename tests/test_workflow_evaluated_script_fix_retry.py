"""A failed command records whether its declared files were left unchanged, and resume retries after a fix.

Four steps, each with its own script; stand-in scripts only, no provider or model call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_cli_run_output import cli, effect_rows, env

PIPELINE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run ((n Int)) -> Int
    (let* ((a (command-result s1 :argv ("python" "s1.py" n) :returns Int))
           (b (command-result s2 :argv ("python" "s2.py" a) :returns Int))
           (c (command-result s3 :argv ("python" "s3.py" b) :returns Int))
           (d (command-result s4 :argv ("python" "s4.py" c) :returns Int)))
      d)))
'''
STEPS = ("s1", "s2", "s3", "s4")
IDENTITIES = {step: f"workflow:main::run / {label}" for step, label in zip(STEPS, "abcd")}
GOOD = '''import json, os, sys
from pathlib import Path
Path("log.txt").open("a").write("{name}\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[1]) + 1))
'''
BAD = 'import sys\nsys.exit(3)\n'
SELF_WRITE = 'import sys\nfrom pathlib import Path\nPath(__file__).open("a").write("# written by its attempt\\n")\nsys.exit(3)\n'
SELF_REMOVE = 'import sys\nfrom pathlib import Path\nPath(__file__).unlink()\nsys.exit(3)\n'


def write_four_steps(root: Path, scripts: dict[str, str] | None = None, *, manifest: dict | None = None) -> None:
    (root / "main.orc").write_text(PIPELINE, encoding="utf-8")
    for step in STEPS:
        body = (scripts or {}).get(step, GOOD)
        if body is not None:
            (root / f"{step}.py").write_text(body.replace("{name}", step), encoding="utf-8")
    boundaries = {step: {"stable_command": ["python", f"{step}.py"], "closure": [f"{step}.py"]} for step in STEPS}
    boundaries.update(manifest or {})
    (root / "commands.json").write_text(json.dumps(boundaries), encoding="utf-8")


def run_four(root: Path) -> subprocess.CompletedProcess[str]:
    return cli(root, "run", "main.orc", "--command-boundaries-file", "commands.json", "--input", "n=1")


def run_id(root: Path, runs: str = ".orchestrate/runs") -> str:
    (only,) = (root / runs).iterdir()
    return only.name


def memo_path(root: Path) -> Path:
    return root / ".orchestrate" / "runs" / run_id(root) / "memo.jsonl"


def journal(root: Path) -> list[dict]:
    return [json.loads(line) for line in memo_path(root).read_text(encoding="utf-8").splitlines()]


def failed_rows(root: Path) -> list[dict]:
    return [row for row in journal(root) if row["record"] == "failed"]


def fix(root: Path, step: str) -> None:
    (root / f"{step}.py").write_text(GOOD.replace("{name}", step), encoding="utf-8")


def started(stderr: str) -> list[str]:
    return [identity for word, identity in effect_rows(stderr) if word == "start"]


# T1: the `closure` field of a failed command


def test_failed_command_records_its_files_unchanged(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": BAD})

    assert run_four(tmp_path).returncode == 1

    (failed,) = failed_rows(tmp_path)
    assert (failed["identity"], failed["closure"]) == (IDENTITIES["s3"], "unchanged")


def test_failed_command_that_wrote_its_script_records_changed(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": SELF_WRITE})

    assert run_four(tmp_path).returncode == 1

    (failed,) = failed_rows(tmp_path)
    assert failed["closure"] == "changed"


def test_failed_command_that_removed_a_declared_file_records_changed(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": SELF_REMOVE})

    result = run_four(tmp_path)

    assert result.returncode == 1, result.stderr
    (failed,) = failed_rows(tmp_path)
    assert (failed["code"], failed["closure"]) == ("command_exit_nonzero", "changed")


def test_command_without_start_evidence_records_unchanged(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": None}, manifest={"s3": {"stable_command": ["python", "s3.py"], "closure": []}})

    assert run_four(tmp_path).returncode == 1

    (start,) = [row for row in journal(tmp_path) if row["record"] == "started" and row["identity"] == IDENTITIES["s3"]]
    (failed,) = failed_rows(tmp_path)
    assert (start["implementation_files"], failed["closure"]) == ({}, "unchanged")


def _provider_env(root: Path, mode: str) -> dict[str, str]:
    return {**env(), "PATH": str(root / "bin") + os.pathsep + env()["PATH"], "PROVIDER_SHIM_MODE": mode}


def failed_provider_run(root: Path):
    """A one-provider run whose stand-in exits non-zero; returns the resume command's environment maker."""
    from tests.test_workflow_evaluated_providers import _fixture
    source, providers, prompts, _ = _fixture(root)
    result = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", source.name,
        "--provider-externs-file", providers.name, "--prompt-externs-file", prompts.name, "--input", "message=x"],
        cwd=root, env=_provider_env(root, "nonzero"), capture_output=True, text=True, check=False)
    assert result.returncode == 1, result.stderr
    return lambda *arguments, mode="success": subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", *arguments], cwd=root, env=_provider_env(root, mode),
        capture_output=True, text=True, check=False)


def test_failed_provider_row_has_no_closure_field(tmp_path: Path) -> None:
    failed_provider_run(tmp_path)

    (failed,) = failed_rows(tmp_path)
    assert failed["code"] == "provider_exit_nonzero" and "closure" not in failed


def _rewrite_failed(path: Path, change) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["record"] == "failed":
            change(row)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _assert_memo_inconsistent(root: Path, launch) -> None:
    resumed = launch("resume", run_id(root))
    assert resumed.returncode == 2 and "[memo_inconsistent]" in resumed.stderr, resumed.stderr
    reported = launch("report", "--run-id", run_id(root))
    assert reported.returncode == 1 and "memo_inconsistent" in reported.stdout + reported.stderr, reported.stderr


def test_misplaced_or_unknown_closure_value_is_memo_inconsistent(tmp_path: Path) -> None:
    unknown, provider = tmp_path / "unknown", tmp_path / "provider"
    unknown.mkdir(), provider.mkdir()
    write_four_steps(unknown, {"s3": BAD})
    assert run_four(unknown).returncode == 1
    _rewrite_failed(memo_path(unknown), lambda row: row.update(closure="maybe"))
    launch_provider = failed_provider_run(provider)
    _rewrite_failed(memo_path(provider), lambda row: row.update(closure="unchanged"))

    _assert_memo_inconsistent(unknown, lambda *arguments: cli(unknown, *arguments))
    _assert_memo_inconsistent(provider, launch_provider)


# T2: the retry rule and `resume --accept-changes`


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def refuses_without_writes(root: Path, code: str, *flags: str) -> subprocess.CompletedProcess[str]:
    before = tree_bytes(root / ".orchestrate")
    result = cli(root, "resume", run_id(root), *flags)
    assert result.returncode == 2, result.stderr
    assert result.stderr.startswith(f"[{code}] "), result.stderr
    assert tree_bytes(root / ".orchestrate") == before
    return result


def test_journal_without_the_field_refuses_until_accepted(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": BAD})
    assert run_four(tmp_path).returncode == 1
    _rewrite_failed(memo_path(tmp_path), lambda row: row.pop("closure"))
    fix(tmp_path, "s3")

    refuses_without_writes(tmp_path, "effect_input_diverged")
    accepted = cli(tmp_path, "resume", run_id(tmp_path), "--accept-changes")

    assert accepted.returncode == 0, accepted.stderr
    assert started(accepted.stderr) == [IDENTITIES["s3"], IDENTITIES["s4"]]


def test_must_not_repeat_refuses_after_a_fix_with_and_without_the_flag(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": BAD}, manifest={
        "s3": {"stable_command": ["python", "s3.py"], "closure": ["s3.py"], "must_not_repeat": True}})
    assert run_four(tmp_path).returncode == 1
    fix(tmp_path, "s3")

    refuses_without_writes(tmp_path, "lexical_restore_pending_effect_unsafe")
    refuses_without_writes(tmp_path, "lexical_restore_pending_effect_unsafe", "--accept-changes")


def test_missing_declared_file_refuses_with_and_without_the_flag(tmp_path: Path) -> None:
    write_four_steps(tmp_path, {"s3": BAD}, manifest={
        "s3": {"stable_command": ["python", "s3.py"], "closure": ["s3.py", "data.txt"]}})
    (tmp_path / "data.txt").write_text("data\n", encoding="utf-8")
    assert run_four(tmp_path).returncode == 1
    fix(tmp_path, "s3")
    (tmp_path / "data.txt").unlink()

    plain = refuses_without_writes(tmp_path, "effect_input_diverged")
    flagged = refuses_without_writes(tmp_path, "effect_input_diverged", "--accept-changes")

    assert "--accept-changes" not in plain.stderr.split("\n", 1)[1] + flagged.stderr.split("\n", 1)[1]


def test_accept_changes_with_nothing_to_accept_is_refused(tmp_path: Path) -> None:
    completed, fixed, provider = (tmp_path / name for name in ("completed", "fixed", "provider"))
    for root in (completed, fixed, provider):
        root.mkdir()
    write_four_steps(completed)
    assert run_four(completed).returncode == 0
    write_four_steps(fixed, {"s3": BAD})
    assert run_four(fixed).returncode == 1
    fix(fixed, "s3")
    launch_provider = failed_provider_run(provider)

    for root in (completed, fixed, provider):
        refuses_without_writes(root, "resume_preflight_failed", "--accept-changes")
    for root, resumed in ((completed, cli(completed, "resume", run_id(completed))),
                          (fixed, cli(fixed, "resume", run_id(fixed))),
                          (provider, launch_provider("resume", run_id(provider)))):
        assert resumed.returncode == 0, (root, resumed.stderr)


PARALLEL = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "alpha" "beta" "gamma"))) :max 3 :parallel 2
      :workspace (string/concat repo "/work")
      (command-result fetch :argv ("python" "probe.py" "${loop.index}") :returns Int))))
'''
ITEM_GOOD = ('import json, os, sys\nfrom pathlib import Path\n'
             'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[1]) + 10))\n')
ITEM_SLEEP = 'import time\nfrom pathlib import Path\nPath("started").write_text("")\ntime.sleep(60)\n'


def write_parallel(root: Path, scripts: dict[str, str]) -> None:
    (root / "main.orc").write_text(PARALLEL, encoding="utf-8")
    for item in ("alpha", "beta", "gamma"):
        (root / item / "work").mkdir(parents=True)
        (root / item / "work" / "probe.py").write_text(scripts.get(item, ITEM_GOOD), encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(
        {"fetch": {"stable_command": ["python", "probe.py"], "closure": []}}), encoding="utf-8")


def run_parallel(root: Path) -> subprocess.CompletedProcess[str]:
    return cli(root, "run", "main.orc", "--command-boundaries-file", "commands.json")


def item(index: int) -> str:
    return f"workflow:main::run / par-map:repo[{index}] / #1"


def test_failed_parallel_item_retries_alone_with_its_fixed_script(tmp_path: Path) -> None:
    write_parallel(tmp_path, {"beta": BAD})
    assert run_parallel(tmp_path).returncode == 1
    (failed,) = failed_rows(tmp_path)
    assert (failed["identity"], failed["closure"]) == (item(1), "unchanged")
    (tmp_path / "beta" / "work" / "probe.py").write_text(ITEM_GOOD, encoding="utf-8")

    refuses_without_writes(tmp_path, "effect_input_diverged")  # a sibling ran after the failure (decision 7)
    accepted = cli(tmp_path, "resume", run_id(tmp_path), "--accept-changes")

    assert accepted.returncode == 0, accepted.stderr
    assert started(accepted.stderr) == [item(1)]
    assert accepted.stdout.splitlines()[-1] == "[10,11,12]"


def kill_when_started(root: Path, markers: list[Path], arguments: list[str]) -> None:
    import signal
    import time
    process = subprocess.Popen([sys.executable, "-B", "-m", "orchestrator", *arguments], cwd=root, env=env(),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 60
    while not all(marker.exists() for marker in markers):
        assert time.monotonic() < deadline and process.poll() is None
        time.sleep(0.05)
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=60)


def test_killed_parallel_items_refuse_until_accepted(tmp_path: Path) -> None:
    write_parallel(tmp_path, {"alpha": ITEM_SLEEP, "beta": ITEM_SLEEP})
    kill_when_started(tmp_path, [tmp_path / name / "work" / "started" for name in ("alpha", "beta")],
                      ["run", "main.orc", "--command-boundaries-file", "commands.json"])
    for name in ("alpha", "beta"):
        (tmp_path / name / "work" / "probe.py").write_text(ITEM_GOOD, encoding="utf-8")

    refuses_without_writes(tmp_path, "effect_input_diverged")
    accepted = cli(tmp_path, "resume", run_id(tmp_path), "--accept-changes")

    assert accepted.returncode == 0, accepted.stderr
    assert {item(0), item(1)} <= set(started(accepted.stderr))
    assert accepted.stdout.splitlines()[-1] == "[10,11,12]"


def _shared_script_stopped_at_three(root: Path, how: str) -> str:
    from tests.test_cli_run_output import SLOW_STEP, run_pipeline, write_pipeline
    write_pipeline(root)
    if how == "failed":
        (root / "fail-three").write_text("", encoding="utf-8")
        assert run_pipeline(root).returncode == 1
        (root / "fail-three").unlink()
    else:
        (root / "step.py").write_text(SLOW_STEP, encoding="utf-8")
        (root / "slow-three").write_text("", encoding="utf-8")
        kill_when_started(root, [root / "started-three"],
                          ["run", "main.orc", "--command-boundaries-file", "commands.json", "--input", "n=1"])
        (root / "slow-three").unlink()
    with (root / "step.py").open("a", encoding="utf-8") as stream:
        stream.write("# edited\n")
    return run_id(root)


@pytest.mark.parametrize("how", ["failed", "killed"])
def test_shared_script_fix_recovers_through_printed_invalidate_and_resume(tmp_path: Path, how: str) -> None:
    from tests.test_cli_recovery_messages import commands
    from tests.test_cli_run_output import IDENTITIES as SHARED, RESULT_LINE, shell
    run = _shared_script_stopped_at_three(tmp_path, how)

    refused = refuses_without_writes(tmp_path, "effect_input_diverged")

    invalidate, resume = commands(refused.stderr)
    assert invalidate.endswith(f" invalidate {run} '{SHARED[0]}'")
    assert resume.endswith(f" resume {run}" + (" --accept-changes" if how == "killed" else ""))
    assert shell(tmp_path, invalidate).returncode == 0
    resumed = shell(tmp_path, resume)
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


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
