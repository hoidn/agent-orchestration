from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.cli.run_ref_root import resolve_run_ref_root
from orchestrator.run_lock import run_writer_lock
from orchestrator.state import StateManager
from tests.historical_state import write_historical_state
from tests.test_workflow_evaluated_cli import _build, _run_args, _run_argv


def _evaluated_run(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_ref_root: str | None = None,
):
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
    args.run_ref_root = run_ref_root
    monkeypatch.chdir(workspace)
    with patch.object(sys, "argv", _run_argv(files)):
        return run_workflow(args)


def _header(run_root: Path) -> dict[str, object]:
    return json.loads((run_root / "run.json").read_text(encoding="utf-8"))


def test_parser_accepts_run_ref_root_on_run_and_resume() -> None:
    parser = create_parser()

    run_args = parser.parse_args(
        ["run", "workflow.orc", "--run-ref-root", "/var/tmp/run-ref"]
    )
    resume_args = parser.parse_args(
        ["resume", "run-123", "--run-ref-root", "/var/tmp/run-ref"]
    )

    assert run_args.run_ref_root == resume_args.run_ref_root == "/var/tmp/run-ref"
    assert parser.parse_args(["run", "workflow.orc"]).run_ref_root is None
    assert parser.parse_args(["resume", "run-123"]).run_ref_root is None


def test_fresh_evaluated_run_records_default_canonical_root_without_creating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    result = _evaluated_run(workspace, monkeypatch)

    selected = resolve_run_ref_root(None)
    assert result.exit_code == 0
    assert _header(result.run_root)["run_ref_root"] == selected.as_posix()
    assert not selected.exists()


def test_fresh_evaluated_run_records_explicit_canonical_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = (tmp_path / "run-ref").resolve()

    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_ref_root=selected.as_posix(),
    )

    assert result.exit_code == 0
    assert _header(result.run_root)["run_ref_root"] == selected.as_posix()


@pytest.mark.parametrize("raw_root", ["relative/run-ref", "/var/tmp/../tmp/run-ref"])
def test_fresh_evaluated_run_rejects_noncanonical_root_before_publication(
    raw_root: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = _evaluated_run(tmp_path, monkeypatch, run_ref_root=raw_root)

    assert result.exit_code == 2
    assert "--run-ref-root must be a canonical absolute path" in caplog.text
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_resume_uses_recorded_root_when_flag_is_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = (tmp_path / "recorded-run-ref").resolve()
    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_ref_root=recorded.as_posix(),
    )
    header_bytes = (result.run_root / "run.json").read_bytes()

    assert resume_workflow(result.run_id) == 0
    assert _header(result.run_root)["run_ref_root"] == recorded.as_posix()
    assert (result.run_root / "run.json").read_bytes() == header_bytes


def test_resume_rejects_changed_root_without_mutating_evaluated_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = (tmp_path / "recorded-run-ref").resolve()
    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_ref_root=recorded.as_posix(),
    )
    before = {
        name: (result.run_root / name).read_bytes()
        for name in ("run.json", "closed_program.json", "memo.jsonl")
    }

    exit_code = resume_workflow(
        result.run_id,
        run_ref_root=(tmp_path / "different-run-ref").resolve().as_posix(),
    )

    assert exit_code == 2
    assert {
        name: (result.run_root / name).read_bytes()
        for name in before
    } == before


def test_state_only_historical_run_is_refused_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _program = _build(tmp_path)
    run_id = "historical-state-only"
    manager = StateManager(tmp_path, run_id=run_id)
    write_historical_state(
        manager,
        source.relative_to(tmp_path).as_posix(),
        bound_inputs={"score": 0.75, "threshold": 0.5},
    )
    before = manager.state_file.read_bytes()
    monkeypatch.chdir(tmp_path)

    assert resume_workflow(run_id) == 2
    assert manager.state_file.read_bytes() == before
    assert not (manager.run_root / "run.lock").exists()


def test_force_restart_refusal_releases_writer_lock_without_mutating_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _evaluated_run(tmp_path, monkeypatch)
    before = {
        name: (result.run_root / name).read_bytes()
        for name in ("run.json", "closed_program.json", "memo.jsonl")
    }

    assert resume_workflow(result.run_id, force_restart=True) == 2
    assert {
        name: (result.run_root / name).read_bytes()
        for name in before
    } == before
    with run_writer_lock(result.run_root):
        pass
