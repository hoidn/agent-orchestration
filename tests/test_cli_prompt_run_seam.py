"""Public evaluated run API and reserved-root safety contracts."""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import RunWorkflowResult, run_workflow
from orchestrator.cli.main import main
from orchestrator.providers.omp_launch_fs import directory_identity
from orchestrator.run_lock import reserved_run_writer_lock
from orchestrator.state import StateManager
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from tests.test_workflow_evaluated_cli import _build, _run_args, _run_argv


def _evaluated_run(
    tmp_path: Path,
    monkeypatch,
    *,
    run_id: str | None = None,
    **run_options,
):
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
    if run_options.get("expected_run_identity") is not None:
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
    with patch.object(sys, "argv", _run_argv(files)):
        return run_workflow(args, run_id=run_id, **run_options)


def test_state_manager_new_run_id_public_and_formatted(tmp_path: Path) -> None:
    manager = StateManager(workspace=tmp_path)
    run_id = manager.new_run_id()
    assert re.fullmatch(r"\d{8}T\d{6}Z-[a-z0-9]{6}", run_id)
    assert manager.new_run_id() != run_id


def test_run_workflow_result_immutable_and_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _evaluated_run(tmp_path, monkeypatch)

    assert isinstance(result, RunWorkflowResult)
    assert result.exit_code == 0
    assert isinstance(result.run_id, str)
    assert result.run_root == tmp_path / ".orchestrate" / "runs" / result.run_id
    assert result.workflow_outputs == {"accepted": True, "score": 0.75}
    assert result.session_status is None
    assert result.usage == {}
    with pytest.raises(FrozenInstanceError):
        result.exit_code = 1
    with pytest.raises(TypeError):
        result.workflow_outputs["accepted"] = False


def test_run_workflow_accepts_keyword_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = "20260821T000000Z-abc123"
    result = _evaluated_run(tmp_path, monkeypatch, run_id=run_id)

    assert (result.exit_code, result.run_id) == (0, run_id)
    assert result.run_root == tmp_path / ".orchestrate" / "runs" / run_id
    assert json.loads((result.run_root / "run.json").read_text())["run_id"] == run_id


def test_run_parser_exposes_no_run_id_flag() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["run", "workflow.orc", "--run-id", "x"])
    assert exc.value.code == 2


def test_main_run_dispatch_returns_exit_code_only(tmp_path: Path) -> None:
    source, _program = _build(tmp_path)

    code = main(["run", str(source), "--input", "score=0.75"])

    assert code == 0
    assert not isinstance(code, RunWorkflowResult)


def test_run_workflow_reserved_root_swapped_after_writer_lock_fails_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = "20260821T000000Z-lock001"
    run_root = tmp_path / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    original_lock = reserved_run_writer_lock

    @contextmanager
    def lock_then_swap(root: Path, reserved_identity: tuple[int, int]):
        with original_lock(root, reserved_identity) as run_fd:
            os.replace(root, root.with_name(root.name + "-swapped"))
            root.mkdir()
            yield run_fd

    monkeypatch.setattr(
        "orchestrator.cli.commands.evaluated.reserved_run_writer_lock",
        lock_then_swap,
    )
    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_id=run_id,
        expected_run_identity=identity,
    )

    replacement = tmp_path / ".orchestrate" / "runs" / run_id
    assert result.exit_code == 1
    assert "changed before publication" in caplog.text
    assert list(replacement.iterdir()) == []
    assert not (replacement / "run.lock").exists()
    assert not (replacement / "run.json").exists()


def test_run_workflow_reserved_root_pre_lock_swap_fails_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = "20260821T000000Z-swap001"
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_root = runs_root / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    os.replace(run_root, runs_root / (run_id + "-original"))
    replacement = runs_root / run_id
    replacement.mkdir()

    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_id=run_id,
        expected_run_identity=identity,
    )

    # The public call reaches the identity check through its reserved-run API.
    assert result.exit_code == 1
    assert "reserved_run_root_changed" in caplog.text
    assert list(replacement.iterdir()) == []
    assert list((runs_root / (run_id + "-original")).iterdir()) == []
    assert not (replacement / "run.lock").exists()
    assert not (replacement / "run.json").exists()


def test_run_workflow_reserved_root_pre_lock_symlink_swap_fails_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = "20260821T000000Z-swap002"
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_root = runs_root / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    os.replace(run_root, runs_root / (run_id + "-original"))
    attacker = runs_root / (run_id + "-attacker")
    attacker.mkdir()
    run_root.symlink_to(attacker, target_is_directory=True)

    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_id=run_id,
        expected_run_identity=identity,
    )

    assert result.exit_code == 1
    assert "reserved_run_root_changed" in caplog.text
    assert list((runs_root / (run_id + "-original")).iterdir()) == []
    assert list(attacker.iterdir()) == []
    assert not (attacker / "run.lock").exists()
    assert not (attacker / "run.json").exists()


def test_commands_package_exports_run_workflow_and_result() -> None:
    from orchestrator.cli.commands import RunWorkflowResult as ExportedResult
    from orchestrator.cli.commands import __all__ as exported
    from orchestrator.cli.commands import run_workflow as exported_run

    assert "run_workflow" in exported
    assert "RunWorkflowResult" in exported
    assert exported_run is run_workflow
    assert ExportedResult is RunWorkflowResult


def test_run_workflow_result_defaults_and_direct_construction_are_frozen() -> None:
    bare = RunWorkflowResult(exit_code=1)
    with pytest.raises(TypeError):
        bare.workflow_outputs["x"] = 1
    with pytest.raises(TypeError):
        bare.usage["u"] = {}

    source = {"nested": {"list": [1, 2]}}
    usage_source = {"step-a": {"session_id": "s", "usage": {"totalTokens": 3}}}
    result = RunWorkflowResult(exit_code=0, workflow_outputs=source, usage=usage_source)
    assert result.workflow_outputs == {"nested": {"list": (1, 2)}}
    with pytest.raises((TypeError, AttributeError)):
        result.workflow_outputs["nested"]["list"].append(3)
    with pytest.raises(TypeError):
        result.usage["step-a"]["usage"]["totalTokens"] = 9

    source["nested"]["list"].append(99)
    usage_source["step-a"]["session_id"] = "mutated"
    assert result.workflow_outputs["nested"]["list"] == (1, 2)
    assert result.usage["step-a"]["session_id"] == "s"


def test_run_workflow_identity_mismatch_returns_known_run_id_and_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "20260821T000000Z-caller1"
    run_root = tmp_path / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    wrong_identity = (identity[0] + 1, identity[1])

    result = _evaluated_run(
        tmp_path,
        monkeypatch,
        run_id=run_id,
        expected_run_identity=wrong_identity,
    )

    assert (result.exit_code, result.run_id, result.run_root) == (
        1,
        run_id,
        run_root,
    )
    assert list(run_root.iterdir()) == []
