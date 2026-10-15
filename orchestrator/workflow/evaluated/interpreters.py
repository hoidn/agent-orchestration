"""C3 interpreter resolution and resume checks for evaluated runs.

Host runs pin a bare first token through host `PATH` (`{path, digest}`). Confined
run-ref children (`run_ref_confinement.v1`) pin every command executable inside the
admitted image instead (`{image, path, resolved, digest}`): the image tree digest, the
guest spelling argv[0] receives, the guest path it resolves to and its bytes. Host
`which`, host files and host absolute paths never authorize an image pin.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path
import posixpath
import shutil
import stat
from typing import Any

from orchestrator._common.safe_tree import SafeTreeError, hash_regular_file, open_directory

# The guest PATH the holder sets; bare tokens resolve through it inside the image.
GUEST_PATH = ("/usr/local/bin", "/usr/bin", "/bin")
# Guest roots that hold the clone or guest-writable scratch, never image bytes.
GUEST_MUTABLE_ROOTS = ("/workspace", "/result", "/tmp", "/dev", "/run", "/proc")
_SYMLINK_HOPS = 40
_ENVIRONMENT_UNAVAILABLE = "run_ref_environment_unavailable"


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


def validate_command_interpreter_pin_shape(pin: object) -> None:
    """Validate a host or an image pin without observing the filesystem."""
    if is_image_pin(pin):
        _validate_image_pin_shape(pin)
    else:
        _validate_host_pin_shape(pin)


def _validate_host_pin_shape(pin: object) -> None:
    if (
        not isinstance(pin, Mapping)
        or set(pin) != {"path", "digest"}
        or not isinstance(pin.get("path"), str)
        or "\x00" in pin["path"]
        or not os.path.isabs(pin["path"])
        or not _valid_digest(pin.get("digest"))
    ):
        raise ValueError("interpreter pin is malformed")


def check_command_interpreter(pin: Mapping[str, str]) -> str | None:
    """Check the recorded executable, ignoring PATH, and report byte changes."""

    _validate_host_pin_shape(pin)
    try:
        current = _launchable_digest(pin["path"])
    except OSError as exc:
        raise InterpreterError(
            f"resume interpreter is missing or unusable: {pin['path']}",
            code="resume_interpreter_missing",
        ) from exc
    return "interpreter_changed" if current != pin["digest"] else None


def is_image_pin(pin: object) -> bool:
    return isinstance(pin, Mapping) and "image" in pin


def _validate_image_pin_shape(pin: Mapping[str, Any]) -> None:
    paths = (pin.get("path"), pin.get("resolved"))
    if (set(pin) != {"image", "path", "resolved", "digest"}
            or not all(isinstance(path, str) and image_resolvable(path) and path.startswith("/")
                       and "\x00" not in path for path in paths)
            or not _valid_digest(pin.get("image")) or not _valid_digest(pin.get("digest"))):
        raise ValueError("image interpreter pin is malformed")


def image_resolvable(token: str) -> bool:
    """True when a guest argv[0] names image bytes, not the clone or guest scratch."""
    if "/" not in token:
        return True
    if not token.startswith("/"):
        return False
    normal = posixpath.normpath(token)
    return not any(normal == root or normal.startswith(root + "/") for root in GUEST_MUTABLE_ROOTS)


def resolve_image_path(root_fd: int, path: str) -> str:
    """Resolve absolute guest `path` as the guest would, by text, beneath the image root.

    No host symlink is followed; absolute link targets restart at the image root.
    """
    # ponytail: same walk as run_ref.image_store._resolve_in_root (private there); share one when exposed.
    pending = [part for part in path.split("/") if part]
    resolved: list[str] = []
    hops = _SYMLINK_HOPS
    while pending:
        part = pending.pop(0)
        if part in (".", ".."):
            resolved = resolved[:-1] if part == ".." else resolved
            continue
        candidate = "/".join([*resolved, part])
        if not stat.S_ISLNK(os.stat(candidate, dir_fd=root_fd, follow_symlinks=False).st_mode):
            resolved.append(part)
            continue
        hops -= 1
        if hops < 0:
            raise OSError(f"image path {path} has a symlink loop")
        target = os.readlink(candidate, dir_fd=root_fd)
        resolved = [] if target.startswith("/") else resolved
        pending = [item for item in target.split("/") if item] + pending
    return "/" + "/".join(resolved)


def image_file_digest(root_fd: int, resolved: str) -> str:
    """Hash one resolved image file, no-follow at every component."""
    return "sha256:" + hash_regular_file(root_fd, resolved.lstrip("/"))


def _image_executable(root_fd: int, path: str) -> tuple[str, str]:
    resolved = resolve_image_path(root_fd, path)
    if not image_resolvable(resolved):
        raise InterpreterError(f"image executable {path} resolves into guest scratch: {resolved}",
                               code=_ENVIRONMENT_UNAVAILABLE)
    info = os.stat(resolved.lstrip("/"), dir_fd=root_fd, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
        raise InterpreterError(f"image executable {path} is not an executable file",
                               code=_ENVIRONMENT_UNAVAILABLE)
    return resolved, image_file_digest(root_fd, resolved)


def pin_image_interpreter(image: Any, token: str) -> dict[str, str]:
    """Pin an image-resolvable argv[0] inside `image` (a SealedImage), never on the host."""
    if not isinstance(token, str) or not token or not image_resolvable(token):
        raise ValueError(f"command executable {token!r} is not image-resolvable")
    candidates = [token] if token.startswith("/") else [f"{root}/{token}" for root in GUEST_PATH]
    for path in candidates:
        try:
            resolved, digest = _image_executable(image.root_fd, path)
        except (OSError, SafeTreeError):
            continue
        return {"image": image.record["tree_digest"], "path": path, "resolved": resolved, "digest": digest}
    raise InterpreterError(f"image has no executable {token!r} on the guest PATH",
                           code=_ENVIRONMENT_UNAVAILABLE)


def check_image_interpreter(pin: Mapping[str, str], image: Any) -> str | None:
    """Resume check of an image pin against the admitted image: drift is a changed environment."""
    _validate_image_pin_shape(pin)
    try:
        current = pin_image_interpreter(image, pin["path"])
    except (InterpreterError, ValueError):
        return "run_ref_environment_changed"
    return None if current == dict(pin) else "run_ref_environment_changed"


__all__ = [
    "GUEST_PATH",
    "InterpreterError",
    "check_command_interpreter",
    "check_image_interpreter",
    "image_resolvable",
    "is_image_pin",
    "pin_command_interpreter",
    "pin_image_interpreter",
    "resolve_image_path",
    "validate_command_interpreter_pin_shape",
]
