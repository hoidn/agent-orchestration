"""What `run` and `resume` print while a pipeline runs, when it fails and when it succeeds."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tests.workflow_evaluated_host_input_helpers import build as build_host_input

REPO = Path(__file__).parents[1]

PIPELINE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (total Int) (first Int))
  (defworkflow run ((n Int)) -> Result
    (let* ((a (command-result step :argv ("python" "step.py" "one" n) :returns Int))
           (b (command-result step :argv ("python" "step.py" "two" a) :returns Int))
           (c (command-result step :argv ("python" "step.py" "three" b) :returns Int)))
      (record Result :total c :first a))))
'''

STEP = '''\
import json, os, sys
from pathlib import Path
name, value = sys.argv[1], int(sys.argv[2])
if Path("fail-" + name).exists():
    print("step " + name + " is broken", file=sys.stderr)
    sys.exit(3)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value + 1))
'''

RESULT_LINE = '{"first":2,"total":4}'
IDENTITIES = [f"workflow:main::run / {name}" for name in ("a", "b", "c")]


def env() -> dict[str, str]:
    return {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(REPO),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *arguments], cwd=root, env=env(),
                          capture_output=True, text=True, check=False)


def shell(root: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, shell=True, cwd=root, env=env(), capture_output=True, text=True, check=False)


def write_pipeline(root: Path) -> None:
    (root / "main.orc").write_text(PIPELINE, encoding="utf-8")
    (root / "step.py").write_text(STEP, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(
        {"step": {"stable_command": ["python", "step.py"], "closure": ["step.py"]}}), encoding="utf-8")


def run_pipeline(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return cli(root, "run", "main.orc", "--command-boundaries-file", "commands.json", "--input", "n=1", *flags)


def printed(stderr: str, word: str) -> list[str]:
    """The lines whose first word is `word`, without that word."""
    return [line.split(None, 1)[1] for line in stderr.splitlines() if line.split(None, 1)[:1] == [word]]


def resume_command(stderr: str) -> str:
    (command,) = printed(stderr, "resume")
    return command


def effect_rows(stderr: str) -> list[tuple[str, str]]:
    rows = []
    for line in stderr.splitlines():
        word, _, rest = line.partition(" ")
        if word in {"start", "commit"}:
            rows.append((word, rest.strip().split("  ")[0]))
    return rows


def failed_run(root: Path) -> subprocess.CompletedProcess[str]:
    write_pipeline(root)
    (root / "fail-two").write_text("", encoding="utf-8")
    result = run_pipeline(root)
    assert result.returncode == 1, result.stderr
    return result


def test_run_prints_run_id_first_then_each_effect_and_the_result(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = run_pipeline(tmp_path)

    assert result.returncode == 0, result.stderr
    word, run_id, run_root = result.stderr.splitlines()[0].split()
    assert word == "run"
    assert Path(run_root) == tmp_path / ".orchestrate" / "runs" / run_id
    assert Path(run_root).is_dir()
    assert effect_rows(result.stderr) == [(kind, identity) for identity in IDENTITIES for kind in ("start", "commit")]
    assert result.stdout.splitlines()[-1] == RESULT_LINE


def test_failed_run_prints_the_step_its_stderr_and_the_resume_command(tmp_path: Path) -> None:
    result = failed_run(tmp_path)

    run_id = result.stderr.splitlines()[0].split()[1]
    assert printed(result.stderr, "failed")[0].startswith(IDENTITIES[1] + "  attempt 1  [command_exit_nonzero]")
    assert "| step two is broken" in result.stderr
    assert resume_command(result.stderr) == f"python -m orchestrator resume {run_id}"
    assert result.stdout == ""


def test_quiet_run_prints_only_the_result(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = run_pipeline(tmp_path, "--quiet")

    assert (result.returncode, result.stderr, result.stdout) == (0, "", RESULT_LINE + "\n")


def test_resume_prints_only_the_effects_it_runs_and_the_result(tmp_path: Path) -> None:
    failed = failed_run(tmp_path)
    (tmp_path / "fail-two").unlink()

    resumed = shell(tmp_path, resume_command(failed.stderr))

    assert resumed.returncode == 0, resumed.stderr
    assert effect_rows(resumed.stderr) == [("start", IDENTITIES[1]), ("commit", IDENTITIES[1]),
                                           ("start", IDENTITIES[2]), ("commit", IDENTITIES[2])]
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


def test_resume_accepts_quiet(tmp_path: Path) -> None:
    failed = failed_run(tmp_path)
    (tmp_path / "fail-two").unlink()

    resumed = shell(tmp_path, resume_command(failed.stderr) + " --quiet")

    assert (resumed.returncode, resumed.stderr, resumed.stdout) == (0, "", RESULT_LINE + "\n")


def test_dry_run_reports_what_it_checked(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = run_pipeline(tmp_path, "--dry-run")

    assert (result.returncode, result.stdout) == (0, "")
    assert result.stderr.splitlines() == ["checked workflow:main::run  3 effect sites"]


def test_suspended_run_prints_the_input_command_and_no_result(tmp_path: Path) -> None:
    build_host_input(tmp_path)

    result = cli(tmp_path, "run", "host/entry.orc", "--source-root", ".", "--command-boundaries-file", "commands.json")

    assert (result.returncode, result.stdout) == (0, "")
    (waiting,) = printed(result.stderr, "waiting")
    identity, command = waiting.split("  ")
    assert identity.startswith("workflow:host/entry::run")
    request = shell(tmp_path, command)
    assert request.returncode == 0, request.stderr
    assert "request_id" in json.loads(request.stdout)


WARNED = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule warn) (export run)
  (defunion Outcome (A) (B))
  (defworkflow run () -> Outcome
    (command-result emit :argv ("python" "emit.py") :returns Outcome)))
'''

EMIT = '''\
import json, os
from pathlib import Path
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"variant": "A"}))
'''


def test_run_shows_compile_warnings_unless_quiet(tmp_path: Path) -> None:
    (tmp_path / "warn.orc").write_text(WARNED, encoding="utf-8")
    (tmp_path / "emit.py").write_text(EMIT, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps(
        {"emit": {"stable_command": ["python", "emit.py"], "closure": ["emit.py"]}}), encoding="utf-8")
    arguments = ("run", "warn.orc", "--command-boundaries-file", "commands.json")

    shown, quiet = cli(tmp_path, *arguments), cli(tmp_path, *arguments, "--quiet")

    assert (shown.returncode, quiet.returncode) == (0, 0), shown.stderr + quiet.stderr
    assert "warn.orc:4:3: [variant_output_without_variant_specific_fields]" in shown.stderr
    assert "variant_output_without_variant_specific_fields" not in quiet.stderr


def test_failed_step_prints_no_contract_pointer(tmp_path: Path) -> None:
    result = failed_run(tmp_path)

    assert "specs/cli.md" not in result.stderr
