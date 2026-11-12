"""A failed command records whether its declared files were left unchanged, and resume retries after a fix.

Four steps, each with its own script; stand-in scripts only, no provider or model call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

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
