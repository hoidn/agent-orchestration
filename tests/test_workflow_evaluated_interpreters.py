from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator._common.safe_tree import SafeTreeError
from orchestrator.workflow.evaluated import interpreters


def test_path_symlink_is_pinned_once_and_resume_ignores_new_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_bin = tmp_path / "first-bin"
    second_bin = tmp_path / "second-bin"
    first_bin.mkdir()
    second_bin.mkdir()
    executable = first_bin / "python-real"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    link = first_bin / "python"
    link.symlink_to(executable.name)
    alternative = second_bin / "python"
    alternative.write_bytes(b"#!/bin/sh\nexit 1\n")
    alternative.chmod(0o755)

    real_which = shutil.which
    calls: list[str] = []

    def counted_which(command: str, **kwargs: object) -> str | None:
        calls.append(command)
        return real_which(command, **kwargs)

    monkeypatch.setattr(interpreters.shutil, "which", counted_which)
    pin = interpreters.pin_command_interpreter(["python", "probe.py"], path=str(first_bin))
    assert pin == {
        "path": str(link),
        "digest": "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    assert calls == ["python"]

    monkeypatch.setenv("PATH", str(second_bin))
    assert interpreters.check_command_interpreter(pin) is None
    assert calls == ["python"]
    executable.write_bytes(b"#!/bin/sh\nexit 2\n")
    assert interpreters.check_command_interpreter(pin) == "interpreter_changed"
    link.unlink()
    with pytest.raises(interpreters.InterpreterError) as error:
        interpreters.check_command_interpreter(pin)
    assert error.value.code == "resume_interpreter_missing"


@pytest.mark.parametrize("relative_search_path", [False, True])
def test_path_dotdot_after_symlink_keeps_which_selection_and_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_search_path: bool,
) -> None:
    real_bin = tmp_path / "real" / "bin"
    real_bin.mkdir(parents=True)
    path_alias = tmp_path / "path-alias"
    path_alias.symlink_to("real/bin", target_is_directory=True)
    expected = tmp_path / "real" / "runner"
    expected.write_text("#!/bin/sh\nprintf 'expected\\n'\n")
    expected.chmod(0o755)
    wrong = tmp_path / "runner"
    wrong.write_text("#!/bin/sh\nprintf 'wrong\\n'\n")
    wrong.chmod(0o755)
    alternate = tmp_path / "alternate-bin"
    alternate.mkdir()
    (alternate / "runner").write_text("#!/bin/sh\nprintf 'alternate\\n'\n")
    (alternate / "runner").chmod(0o755)

    monkeypatch.chdir(tmp_path)
    search_path = "path-alias/.." if relative_search_path else str(path_alias) + "/.."
    real_which = shutil.which
    which_result = real_which("runner", path=search_path)
    assert which_result is not None
    expected_pin_path = (
        which_result if os.path.isabs(which_result)
        else os.path.join(os.getcwd(), which_result)
    )
    calls: list[tuple[str, str]] = []

    def counted_which(command: str, *, path: str | None = None) -> str | None:
        calls.append((command, path or ""))
        return real_which(command, path=path)

    monkeypatch.setattr(interpreters.shutil, "which", counted_which)
    pin = interpreters.pin_command_interpreter(["runner"], path=search_path)
    assert pin == {
        "path": expected_pin_path,
        "digest": "sha256:" + hashlib.sha256(expected.read_bytes()).hexdigest(),
    }
    assert calls == [("runner", search_path)]
    assert subprocess.check_output([pin["path"]], text=True).strip() == "expected"

    monkeypatch.setenv("PATH", str(alternate))
    assert interpreters.check_command_interpreter(pin) is None
    assert subprocess.check_output([pin["path"]], text=True).strip() == "expected"
    assert calls == [("runner", search_path)]


def test_only_a_bare_first_token_is_automatically_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_which(*args: object, **kwargs: object) -> None:
        raise AssertionError("PATH lookup is not expected for a slashed token")

    monkeypatch.setattr(interpreters.shutil, "which", unexpected_which)
    assert interpreters.pin_command_interpreter(["./python", "script.py"]) is None
    assert interpreters.pin_command_interpreter([str(tmp_path / "python")]) is None


def test_bad_pins_and_missing_start_interpreters_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(interpreters.InterpreterError) as error:
        interpreters.pin_command_interpreter(["missing-python"], path=str(tmp_path))
    assert error.value.code == "command_interpreter_missing"

    with pytest.raises(ValueError, match="malformed"):
        interpreters.check_command_interpreter(
            {"path": "/bin/sh", "digest": "sha256:abc"}
        )

    blocked = tmp_path / "blocked-python"
    blocked.write_bytes(b"interpreter")
    real_access = interpreters.os.access
    monkeypatch.setattr(interpreters.shutil, "which", lambda *_args, **_kwargs: str(blocked))
    monkeypatch.setattr(
        interpreters.os, "access",
        lambda path, mode: False if os.fspath(path) == str(blocked) else real_access(path, mode),
    )
    with pytest.raises(interpreters.InterpreterError, match="not launchable"):
        interpreters.pin_command_interpreter(["blocked-python"])
    pin = {
        "path": str(blocked),
        "digest": "sha256:" + hashlib.sha256(blocked.read_bytes()).hexdigest(),
    }
    with pytest.raises(interpreters.InterpreterError) as resume_error:
        interpreters.check_command_interpreter(pin)
    assert resume_error.value.code == "resume_interpreter_missing"


def test_safe_tree_read_errors_become_interpreter_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "python"
    executable.write_bytes(b"#!/bin/sh\n")
    executable.chmod(0o755)

    def denied_hash(*_args: object, **_kwargs: object) -> str:
        raise SafeTreeError("injected safe-tree rejection")

    monkeypatch.setattr(interpreters.shutil, "which", lambda *_args, **_kwargs: str(executable))
    monkeypatch.setattr(interpreters, "hash_regular_file", denied_hash)
    with pytest.raises(interpreters.InterpreterError) as start_error:
        interpreters.pin_command_interpreter(["python"])
    assert start_error.value.code == "command_interpreter_missing"

    pin = {"path": str(executable), "digest": "sha256:" + "0" * 64}
    with pytest.raises(interpreters.InterpreterError) as resume_error:
        interpreters.check_command_interpreter(pin)
    assert resume_error.value.code == "resume_interpreter_missing"
