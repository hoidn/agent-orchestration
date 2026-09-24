from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.cli.main import main
from orchestrator.run_lock import run_writer_lock
from orchestrator.state import StateManager
from orchestrator.workflow.human_input import (
    get_human_input,
    record_human_input,
)


def _manager(tmp_path: Path, *, custom_state_dir: Path | None = None) -> StateManager:
    (tmp_path / "workflow.yaml").write_text(
        "version: 1\nsteps: []\n", encoding="utf-8"
    )
    manager = StateManager(tmp_path, run_id="human", state_dir=custom_state_dir)
    manager.initialize("workflow.yaml")
    assert manager.state is not None
    manager.state.current_step = {
        "name": "request",
        "step_id": "request",
        "visit_count": 1,
    }
    manager.state.step_visits = {"request": 1}
    manager._write_state()
    return manager


def _pending(
    manager: StateManager, *, question: str = "Continue?"
) -> dict[str, object]:
    return record_human_input(
        manager,
        runtime_step_id="request",
        enclosing_step={
            "step_name": "request",
            "step_id": "request",
            "visit_count": 1,
        },
        loop_iteration=None,
        question=question,
    )


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


def test_input_answer_accepts_empty_text_without_resuming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manager = _manager(tmp_path)
    pending = _pending(manager, question="")

    assert main(
        ["input", "answer", "human", pending["request_id"], "--text", ""]
    ) == 0

    answered = json.loads(capsys.readouterr().out)
    assert answered["status"] == "answered"
    assert answered["reply"] == {"variant": "ANSWERED", "text": ""}
    assert get_human_input(manager.run_root) == answered
    assert manager.load().status == "suspended"


def test_input_cancel_uses_a_custom_state_root(
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
    ) == 0

    cancelled = json.loads(capsys.readouterr().out)
    assert cancelled["reply"] == {"variant": "CANCELLED"}
    assert manager.load().status == "suspended"


def test_input_rejects_stale_and_conflicting_answers_without_mutation(
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
    ) != 0
    assert capsys.readouterr().out == ""
    assert manager.state_file.read_bytes() == before

    assert main(
        ["input", "answer", "human", pending["request_id"], "--text", "yes"]
    ) == 0
    answered = json.loads(capsys.readouterr().out)
    assert main(["input", "cancel", "human", pending["request_id"]]) != 0
    assert capsys.readouterr().out == ""
    assert get_human_input(manager.run_root) == answered


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
        ) != 0

    assert capsys.readouterr().out == ""
    assert manager.state_file.read_bytes() == before
