"""Stable prompt-import failure boundaries for private snapshot races."""

import pytest

from orchestrator.cli.main import main
from tests.test_cli_prompt import fake_runtime
from tests.test_cli_prompt_import import _real_private_resolved


def test_private_reuse_preplanted_snapshot_exits_one_without_traceback(
    tmp_path, monkeypatch: pytest.MonkeyPatch, fake_runtime, capsys
) -> None:
    from orchestrator.cli.commands import prompt_run_service

    resolved, _private = _real_private_resolved(tmp_path)
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.resolve_prompt_session",
        lambda *_args: resolved,
    )
    original = prompt_run_service._create_prompt_inputs_root

    def preplanted(run_root, identity, *, run_root_fd=None):
        root, root_fd = original(run_root, identity, run_root_fd=run_root_fd)
        (root / "prompt.md").write_bytes(b"planted")
        return root, root_fd

    monkeypatch.setattr(
        prompt_run_service, "_create_prompt_inputs_root", preplanted
    )
    assert main(["prompt", "import", "run-1", "--reuse-run-contract"]) == 1
    assert fake_runtime.executed == []
    stderr = capsys.readouterr().err
    assert "prompt import:" in stderr
    assert "Traceback" not in stderr


def test_private_reuse_fstat_failure_closes_run_and_exits_one(
    tmp_path, monkeypatch: pytest.MonkeyPatch, fake_runtime, capsys
) -> None:
    from orchestrator.cli.commands import prompt_import

    resolved, _private = _real_private_resolved(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(prompt_import, "resolve_prompt_session", lambda *_: resolved)
    original_close = prompt_import.os.close
    closed = []
    monkeypatch.setattr(
        prompt_import.os,
        "close",
        lambda descriptor: (closed.append(descriptor), original_close(descriptor))[1],
    )
    monkeypatch.setattr(
        prompt_import.os,
        "fstat",
        lambda _descriptor: (_ for _ in ()).throw(OSError("fstat failed")),
    )
    assert main(["prompt", "import", "run-1", "--reuse-run-contract"]) == 1
    assert closed
    assert fake_runtime.executed == []
    assert "Traceback" not in capsys.readouterr().err
