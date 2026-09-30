"""Public CLI exit codes when a run writer is already active."""

from pathlib import Path

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import main
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args
from tests.test_workflow_resume_after_known_failure import SEQUENCE, _install, _log, _run


def test_resume_of_a_run_whose_writer_lock_another_process_holds_is_refused_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    files = _install(tmp_path, SEQUENCE, broken=("check",))
    monkeypatch.chdir(tmp_path)
    assert _run(files) == 1
    run_root = next((tmp_path / ".orchestrate" / "runs").iterdir())

    with _subprocess_writer(run_root):
        exit_code = main(["resume", run_root.name])

    assert (exit_code, "run_already_active" in caplog.text, _log(files["probe"])) == (2, True, ["prepare", "check"])


def test_run_with_a_run_id_whose_writer_lock_another_process_holds_is_refused_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    files = _install(tmp_path, SEQUENCE)
    monkeypatch.chdir(tmp_path)
    run_root = tmp_path / ".orchestrate" / "runs" / "requested-run"
    run_root.mkdir(parents=True)
    args = _run_args(files)
    args.command_boundaries_file = str(files["commands"])

    with _subprocess_writer(run_root):
        exit_code = run_workflow(args, run_id="requested-run").exit_code

    assert (exit_code, "run_already_active" in caplog.text, _log(files["probe"])) == (2, True, [])
