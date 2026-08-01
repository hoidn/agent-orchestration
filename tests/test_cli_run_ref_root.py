from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.state import StateManager


def _write_workflow(workspace: Path) -> Path:
    workflow = workspace / "workflow.orc"
    workflow.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule workflow)",
                "  (export orchestrate)",
                "  (defrecord ResumeValue",
                "    (status String)",
                "    (ready Bool))",
                "  (defworkflow orchestrate",
                "    ((approved Bool)",
                "     (status String))",
                "    -> ResumeValue",
                "    (record ResumeValue",
                "      :status status",
                "      :ready approved)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return workflow


def _run_args(workflow: Path, *, run_ref_root: str | None = None) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=["approved=true", "status=ready"],
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        dry_run=False,
        debug=False,
        quiet=False,
        verbose=False,
        log_level="info",
        backup_state=False,
        state_dir=None,
        run_ref_root=run_ref_root,
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        stream_output=False,
        step_summaries=False,
        summary_mode=None,
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_provider="claude_sonnet_summary",
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow=None,
        source_root=None,
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def _only_state(workspace: Path) -> dict[str, object]:
    run_roots = sorted(
        path
        for path in (workspace / ".orchestrate" / "runs").iterdir()
        if path.is_dir()
    )
    assert len(run_roots) == 1
    return json.loads((run_roots[0] / "state.json").read_text(encoding="utf-8"))


def _initialize_resumable_run(
    workspace: Path,
    *,
    run_id: str,
    run_ref_root: Path | None = None,
) -> StateManager:
    manager = StateManager(workspace, run_id=run_id)
    state = manager.initialize(
        "workflow.orc",
        bound_inputs={"approved": True, "status": "ready"},
    )
    if run_ref_root is not None:
        manager.bind_run_ref_root(run_ref_root)
    state.status = "failed"
    manager._write_state()
    return manager


def test_parser_accepts_run_ref_root_on_run_and_resume() -> None:
    parser = create_parser()

    run_args = parser.parse_args(
        ["run", "workflow.orc", "--run-ref-root", "/var/tmp/run-ref"]
    )
    resume_args = parser.parse_args(
        ["resume", "run-123", "--run-ref-root", "/var/tmp/run-ref"]
    )

    assert run_args.run_ref_root == "/var/tmp/run-ref"
    assert resume_args.run_ref_root == "/var/tmp/run-ref"
    assert parser.parse_args(["run", "workflow.orc"]).run_ref_root is None
    assert parser.parse_args(["resume", "run-123"]).run_ref_root is None


def test_fresh_run_leaves_the_default_binding_lazy_until_run_ref_executes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    workflow = _write_workflow(workspace)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(workspace)

    with patch("orchestrator.cli.commands.run.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        assert run_workflow(_run_args(workflow)) == 0

    assert "run_ref_root" not in _only_state(workspace)


def test_fresh_run_binds_explicit_canonical_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workflow = _write_workflow(workspace)
    selected = (tmp_path / "run-ref").resolve()
    monkeypatch.chdir(workspace)

    with patch("orchestrator.cli.commands.run.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        assert run_workflow(
            _run_args(workflow, run_ref_root=selected.as_posix())
        ) == 0

    assert _only_state(workspace)["run_ref_root"] == selected.as_posix()


@pytest.mark.parametrize(
    "raw_root",
    ["relative/run-ref", "/var/tmp/../tmp/run-ref"],
)
def test_fresh_run_rejects_explicit_noncanonical_or_relative_root(
    raw_root: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _write_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert run_workflow(_run_args(workflow, run_ref_root=raw_root)) == 2
    assert not (tmp_path / ".orchestrate").exists()


def test_resume_uses_recorded_root_when_flag_is_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_workflow(tmp_path)
    recorded = (tmp_path / "recorded-run-ref").resolve()
    _initialize_resumable_run(
        tmp_path,
        run_id="resume-recorded-root",
        run_ref_root=recorded,
    )
    monkeypatch.chdir(tmp_path)

    with patch("orchestrator.cli.commands.resume.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        assert resume_workflow(run_id="resume-recorded-root") == 0

    persisted = StateManager(tmp_path, run_id="resume-recorded-root").load()
    assert persisted is not None
    assert persisted.run_ref_root == recorded.as_posix()


def test_resume_rejects_explicit_root_that_differs_from_recorded_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_workflow(tmp_path)
    recorded = (tmp_path / "recorded-run-ref").resolve()
    _initialize_resumable_run(
        tmp_path,
        run_id="resume-root-mismatch",
        run_ref_root=recorded,
    )
    monkeypatch.chdir(tmp_path)

    with patch("orchestrator.cli.commands.resume.WorkflowExecutor") as executor_cls:
        assert resume_workflow(
            run_id="resume-root-mismatch",
            run_ref_root=(tmp_path / "different-run-ref").resolve().as_posix(),
        ) == 1

    assert "run-ref root binding changed" in capsys.readouterr().err
    executor_cls.assert_not_called()


@pytest.mark.parametrize("explicit", [False, True])
def test_resume_binds_only_an_explicit_root_for_older_unbound_state(
    explicit: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_workflow(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _initialize_resumable_run(tmp_path, run_id="resume-unbound-root")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    selected = (
        (tmp_path / "explicit-run-ref").resolve()
        if explicit
        else (home / ".local" / "state" / "orchestrator" / "run-ref").resolve()
    )

    with patch("orchestrator.cli.commands.resume.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        assert resume_workflow(
            run_id="resume-unbound-root",
            run_ref_root=selected.as_posix() if explicit else None,
        ) == 0

    persisted = StateManager(tmp_path, run_id="resume-unbound-root").load()
    assert persisted is not None
    assert persisted.run_ref_root == (
        selected.as_posix() if explicit else None
    )


def test_force_restart_binds_selected_root_on_the_new_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_workflow(tmp_path)
    old_root = (tmp_path / "old-run-ref").resolve()
    selected = (tmp_path / "replacement-run-ref").resolve()
    _initialize_resumable_run(
        tmp_path,
        run_id="force-restart-old-run",
        run_ref_root=old_root,
    )
    monkeypatch.chdir(tmp_path)

    with patch("orchestrator.cli.commands.resume.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        assert resume_workflow(
            run_id="force-restart-old-run",
            force_restart=True,
            run_ref_root=selected.as_posix(),
        ) == 0

    run_roots = {
        path.name: path
        for path in (tmp_path / ".orchestrate" / "runs").iterdir()
        if path.is_dir()
    }
    assert set(run_roots) != {"force-restart-old-run"}
    new_run_id = next(run_id for run_id in run_roots if run_id != "force-restart-old-run")
    new_state = json.loads(
        (run_roots[new_run_id] / "state.json").read_text(encoding="utf-8")
    )
    assert new_state["run_ref_root"] == selected.as_posix()
