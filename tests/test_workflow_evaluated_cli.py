from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.evaluated import bind_program_inputs
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv


PROGRAM = '''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule evaluated/inputs)
  (export run)
  (defrecord Result (accepted Bool) (score Float))
  (defworkflow run ((score Float) (threshold Float :default 0.5)) -> Result
    (record Result :accepted (> score threshold) :score score)))
'''


def _build(root: Path):
    source = root / "evaluated" / "inputs.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(PROGRAM, encoding="utf-8")
    result = build_closed_program_bundle(
        FrontendBuildRequest(source_path=source, workspace_root=root)
    )
    return source, result.program


def _run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", "run", *arguments],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_input_binding_applies_defaults_and_rejects_bad_inputs(tmp_path: Path) -> None:
    _source, program = _build(tmp_path)

    assert bind_program_inputs(program, {"score": "0.75"}, workspace=tmp_path) == {
        "score": 0.75,
        "threshold": 0.5,
    }
    for invalid in ({}, {"score": "0.75", "extra": "x"}, {"score": "nope"}, {"score": "NaN"}):
        with pytest.raises(ValueError):
            bind_program_inputs(program, invalid, workspace=tmp_path)


def test_public_dry_run_validates_without_run_authority(tmp_path: Path) -> None:
    source, _program = _build(tmp_path)

    result = _run_cli(tmp_path, str(source), "--dry-run", "--input", "score=0.75")

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".orchestrate" / "runs").exists()


@pytest.mark.parametrize(
    "inputs",
    [(), ("score=0.75", "extra=x"), ("score=not-a-float",), ("score=NaN",)],
    ids=["missing", "unknown", "wrong-type", "nonfinite"],
)
def test_public_dry_run_rejects_invalid_inputs_without_run_authority(
    tmp_path: Path, inputs: tuple[str, ...]
) -> None:
    source, _program = _build(tmp_path)
    arguments = [str(source), "--dry-run"]
    for value in inputs:
        arguments.extend(["--input", value])

    result = _run_cli(tmp_path, *arguments)

    assert result.returncode == 2
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_public_pure_run_persists_checked_terminal(tmp_path: Path) -> None:
    source, _program = _build(tmp_path)

    result = _run_cli(tmp_path, str(source), "--input", "score=0.75")

    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    header = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    memo_path = run_root / "memo.jsonl"
    snapshot = read_memo(memo_path, {})
    assert header["bound_inputs"] == {"score": 0.75, "threshold": 0.5}
    assert snapshot.terminal is not None
    assert snapshot.terminal.data == {
        "record": "terminal",
        "outcome": "completed",
        "value": {"accepted": True, "score": 0.75},
    }


def test_public_pure_evaluation_failure_persists_failed_terminal(
    tmp_path: Path,
) -> None:
    source = tmp_path / "evaluated" / "failure.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule evaluated/failure) (export run) '
        '(defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))\n',
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, str(source), "--input", "divisor=0")

    assert result.returncode == 1
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert (run_root / "run.json").is_file()
    snapshot = read_memo(run_root / "memo.jsonl", {})
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["outcome"] == "failed"
    assert snapshot.terminal.data["code"] == "pure_expr_division_by_zero"


def test_public_run_returns_terminal_record_fields_without_an_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _program = _build(tmp_path)
    files = {
        "source": source,
        "source_root": tmp_path,
        "providers": tmp_path / "providers.json",
        "prompts": tmp_path / "prompts.json",
    }
    files["providers"].write_text("{}", encoding="utf-8")
    files["prompts"].write_text("{}", encoding="utf-8")
    args = _run_args(files)
    args.input = ["score=0.75"]
    argv = [*_run_argv(files), "--input", "score=0.75"]
    monkeypatch.chdir(tmp_path)

    with patch.object(sys, "argv", argv):
        result = run_workflow(args)

    assert result.exit_code == 0
    assert result.run_root is not None
    assert result.run_root.parent == tmp_path / ".orchestrate" / "runs"
    assert dict(result.workflow_outputs) == {"accepted": True, "score": 0.75}
