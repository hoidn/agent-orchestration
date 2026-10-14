"""Public evaluated run and resume behavior under a held writer lock."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import main
from orchestrator.providers.omp_launch_fs import directory_identity
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_evaluated_cli import _build, _run_args, _run_argv


def _run(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    source, _program = _build(workspace)
    files = {
        "source": source,
        "source_root": workspace,
        "providers": workspace / "providers.json",
        "prompts": workspace / "prompts.json",
    }
    files["providers"].write_text("{}", encoding="utf-8")
    files["prompts"].write_text("{}", encoding="utf-8")
    args = _run_args(files)
    args.input = ["score=0.75"]
    monkeypatch.chdir(workspace)
    with patch.object(sys, "argv", _run_argv(files)):
        return run_workflow(args)


def test_resume_of_evaluated_run_with_writer_lock_held_is_refused_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = _run(tmp_path, monkeypatch)
    before = {
        name: (result.run_root / name).read_bytes()
        for name in ("run.json", "closed_program.json", "memo.jsonl")
    }

    with _subprocess_writer(result.run_root):
        exit_code = main(["resume", result.run_id])

    assert (exit_code, "run_already_active" in caplog.text) == (2, True)
    assert {
        name: (result.run_root / name).read_bytes()
        for name in before
    } == before


def test_new_run_with_held_caller_selected_root_is_refused_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
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
    run_id = "20261013T000000Z-locked1"
    run_root = tmp_path / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    request = FrontendBuildRequest(
        source_path=source,
        source_roots=(tmp_path,),
        entry_workflow="run",
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        workspace_root=tmp_path,
    )
    args.physical_build_request = request
    args.logical_build_request = request
    args.logical_input_file = None
    monkeypatch.chdir(tmp_path)

    with _subprocess_writer(run_root):
        with patch.object(sys, "argv", _run_argv(files)):
            result = run_workflow(
                args,
                run_id=run_id,
                expected_run_identity=identity,
            )

    assert (result.exit_code, "run_already_active" in caplog.text) == (2, True)
    assert list(run_root.iterdir()) == [run_root / "run.lock"]
