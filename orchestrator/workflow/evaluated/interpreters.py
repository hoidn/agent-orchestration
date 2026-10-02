"""C3 interpreter resolution and resume checks for evaluated runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import shutil
import stat

from orchestrator._common.safe_tree import SafeTreeError, hash_regular_file, open_directory


class InterpreterError(ValueError):
    """An interpreter pin cannot be created or used on resume."""

    def __init__(self, message: str, *, code: str = "command_interpreter_missing") -> None:
        super().__init__(message)
        self.code = code


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _digest(path: str) -> str:
    resolved = Path(path).resolve(strict=True)
    root_fd = open_directory(os.sep)
    try:
        return "sha256:" + hash_regular_file(root_fd, str(resolved).lstrip(os.sep))
    finally:
        os.close(root_fd)


def _launchable_digest(path: str) -> str:
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
            raise OSError("interpreter is not launchable")
        return _digest(path)
    except (SafeTreeError, RuntimeError, ValueError) as exc:
        raise OSError(f"interpreter cannot be resolved or read: {path}: {exc}") from exc


def pin_command_interpreter(
    stable_command: Sequence[str], *, path: str | None = None
) -> dict[str, str] | None:
    """Pin the first bare stable-command token once, at run creation."""

    if not stable_command or isinstance(stable_command, (str, bytes)):
        raise ValueError("stable command is empty or malformed")
    token = stable_command[0]
    if not isinstance(token, str) or not token:
        raise ValueError("stable command interpreter is invalid")
    if token.startswith("/") or "/" in token:
        return None
    found = shutil.which(token, path=path)
    if found is None:
        raise InterpreterError(f"cannot resolve interpreter {token!r} on PATH")
    recorded_path = found if os.path.isabs(found) else os.path.join(os.getcwd(), found)
    try:
        digest = _launchable_digest(recorded_path)
    except OSError as exc:
        raise InterpreterError(f"interpreter is not launchable: {recorded_path}: {exc}") from exc
    return {"path": recorded_path, "digest": digest}


def check_command_interpreter(pin: Mapping[str, str]) -> str | None:
    """Check the recorded executable, ignoring PATH, and report byte changes."""

    if (
        not isinstance(pin, Mapping)
        or set(pin) != {"path", "digest"}
        or not isinstance(pin.get("path"), str)
        or not os.path.isabs(pin["path"])
        or not _valid_digest(pin.get("digest"))
    ):
        raise ValueError("interpreter pin is malformed")
    try:
        current = _launchable_digest(pin["path"])
    except OSError as exc:
        raise InterpreterError(
            f"resume interpreter is missing or unusable: {pin['path']}",
            code="resume_interpreter_missing",
        ) from exc
    return "interpreter_changed" if current != pin["digest"] else None


__all__ = ["InterpreterError", "check_command_interpreter", "pin_command_interpreter"]
