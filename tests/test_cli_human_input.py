from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.historical_state import write_historical_state

from orchestrator.cli.main import main
from orchestrator.run_lock import run_writer_lock
from orchestrator.state import StateManager
from orchestrator.workflow.human_input import (
    get_human_input,
)


def _manager(tmp_path: Path, *, custom_state_dir: Path | None = None) -> StateManager:
    (tmp_path / "workflow.yaml").write_text(
        "version: 1\nsteps: []\n", encoding="utf-8"
    )
    manager = StateManager(tmp_path, run_id="human", state_dir=custom_state_dir)
    write_historical_state(manager, "workflow.yaml")
    assert manager.state is not None
    manager.state.current_step = {
        "name": "request",
        "step_id": "request",
        "visit_count": 1,
    }
    manager.state.step_visits = {"request": 1}
    manager._write_state()
    return manager


def _pending(manager: StateManager, *, question: str = "Continue?") -> dict[str, object]:
    record = {
        "request_id": "00000000-0000-4000-8000-000000000001",
        "resume_scope": {"root_workflow_file": "workflow.yaml", "call_frame_ids": []},
        "runtime_step_id": "request",
        "enclosing_step": {"step_name": "request", "step_id": "request", "visit_count": 1},
        "loop_iteration": None, "question": question, "status": "pending",
    }
    manager.state.human_input = record
    manager.state.status = "suspended"
    manager._write_state()
    return record


def test_input_get_prints_the_pending_record_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = _manager(tmp_path)
    pending = _pending(manager)
    before = manager.state_file.read_bytes()

    assert main(["input", "get", "human"]) == 0

    assert json.loads(capsys.readouterr().out) == pending
    assert manager.state_file.read_bytes() == before


def test_input_answer_is_retired_without_mutating_the_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = _manager(tmp_path)
    pending = _pending(manager, question="")

    assert main(
        ["input", "answer", "human", pending["request_id"], "--text", ""]
    ) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert "workflow_execution_profile_retired" in output.err
    assert get_human_input(manager.run_root) == pending
    assert manager.load().status == "suspended"


def test_input_cancel_is_retired_for_a_custom_state_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "custom-runs"
    manager = _manager(tmp_path, custom_state_dir=state_dir)
    pending = _pending(manager)

    assert main(
        [
            "input",
            "cancel",
            "human",
            pending["request_id"],
            "--state-dir",
            str(state_dir),
        ]
    ) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert "workflow_execution_profile_retired" in output.err
    assert get_human_input(manager.run_root) == pending
    assert manager.load().status == "suspended"


def test_input_answer_and_cancel_are_retired_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = _manager(tmp_path)
    pending = _pending(manager)
    before = manager.state_file.read_bytes()

    assert main(
        [
            "input",
            "answer",
            "human",
            "00000000-0000-4000-8000-000000000099",
            "--text",
            "no",
        ]
    ) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "workflow_execution_profile_retired" in output.err
    assert manager.state_file.read_bytes() == before

    assert main(
        ["input", "answer", "human", pending["request_id"], "--text", "yes"]
    ) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "workflow_execution_profile_retired" in output.err
    assert main(["input", "cancel", "human", pending["request_id"]]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "workflow_execution_profile_retired" in output.err
    assert manager.state_file.read_bytes() == before
    assert get_human_input(manager.run_root) == pending


def test_input_writer_lock_denial_does_not_mutate_the_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = _manager(tmp_path)
    pending = _pending(manager)
    before = manager.state_file.read_bytes()

    with run_writer_lock(manager.run_root):
        assert main(
            ["input", "answer", "human", pending["request_id"], "--text", "yes"]
        ) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert "workflow_execution_profile_retired" in output.err
    assert manager.state_file.read_bytes() == before
