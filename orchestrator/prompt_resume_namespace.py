"""Pinned Bubblewrap boundary for interactive prompt resume children."""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass

from orchestrator._common.safe_tree import open_directory

from orchestrator.providers.isolation_backend import (
    BubblewrapBackend,
    PinnedProviderIsolationBackend,
)

_ENV_EXEC = "/usr/bin/env"


class ResumeNamespaceError(Exception):
    """The controller-only namespace boundary could not be admitted."""


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1 << 16):
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return "sha256:" + digest.hexdigest()


def _admit_env_exec() -> tuple[int, int]:
    try:
        fd = os.open(_ENV_EXEC, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise ResumeNamespaceError("environment scrubber is unavailable") from exc
    try:
        observed = os.fstat(fd)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != 0
            or observed.st_nlink != 1
            or observed.st_mode & 0o022
            or not observed.st_mode & 0o111
        ):
            raise ResumeNamespaceError("environment scrubber is not trusted")
        return observed.st_dev, observed.st_ino
    finally:
        os.close(fd)


@dataclass(slots=True)
class ResumeNamespace:
    """Retained executable and bind-source descriptors for one child."""

    backend: PinnedProviderIsolationBackend
    control_fd: int
    live_fd: int
    control_identity: tuple[int, int]
    live_identity: tuple[int, int]
    env_exec: str
    env_identity: tuple[int, int]
    policy_fds: tuple[int, ...]
    policy_identities: tuple[tuple[int, int], ...]
    prefix: tuple[str, ...]

    @property
    def pass_fds(self) -> tuple[int, ...]:
        return (
            self.backend.executable_fd,
            self.control_fd,
            self.live_fd,
            *self.policy_fds,
        )

    def wrap_command(self, nested: tuple[str, ...] | None) -> tuple[str, ...]:
        env = (self.env_exec, "-u", "PWD")
        if nested is None:
            return (*self.prefix, "--", *env)
        root_args = tuple(
            part
            for fd in self.policy_fds
            for part in ("--root-fd", str(fd))
        )
        return (*self.prefix, "--", *env, "--", *nested, *root_args)

    def revalidate(self) -> None:
        try:
            backend = os.fstat(self.backend.executable_fd)
            control = os.fstat(self.control_fd)
            live = os.fstat(self.live_fd)
            env_exec = os.stat(self.env_exec, follow_symlinks=False)
            policies = tuple(os.fstat(fd) for fd in self.policy_fds)
        except OSError as exc:
            raise ResumeNamespaceError("namespace authority descriptor changed") from exc
        executable = self.backend.identity.executable
        if (
            (backend.st_dev, backend.st_ino, backend.st_size)
            != (executable.device, executable.inode, executable.size)
            or stat.S_IMODE(backend.st_mode) != executable.mode
            or _hash_fd(self.backend.executable_fd) != executable.digest
            or (control.st_dev, control.st_ino) != self.control_identity
            or (live.st_dev, live.st_ino) != self.live_identity
            or (env_exec.st_dev, env_exec.st_ino) != self.env_identity
            or env_exec.st_uid != 0
            or env_exec.st_nlink != 1
            or env_exec.st_mode & 0o022
            or not env_exec.st_mode & 0o111
            or tuple((row.st_dev, row.st_ino) for row in policies)
            != self.policy_identities
        ):
            raise ResumeNamespaceError("namespace authority identity changed")

    def close(self) -> None:
        self.backend.close()
        for name in ("control_fd", "live_fd"):
            fd = getattr(self, name)
            if fd >= 0:
                os.close(fd)
                setattr(self, name, -1)
        for fd in self.policy_fds:
            os.close(fd)
        self.policy_fds = ()


def prepare_resume_namespace(
    *,
    control_fd: int,
    live_fd: int,
    control_path: str,
    live_path: str,
    child_cwd: str,
    pinned_backend: PinnedProviderIsolationBackend | None = None,
    policy_paths: tuple[str, ...] = (),
) -> ResumeNamespace:
    """Mask the controller root read-only, reopening only the live journal."""
    backend = pinned_backend
    duplicate_control_fd = duplicate_live_fd = -1
    policy_fds: list[int] = []
    try:
        if backend is None:
            backend = BubblewrapBackend().preflight()
        env_identity = _admit_env_exec()
        duplicate_control_fd = os.dup(control_fd)
        duplicate_live_fd = os.dup(live_fd)
        control_stat = os.fstat(duplicate_control_fd)
        live_stat = os.fstat(duplicate_live_fd)
        for path in policy_paths:
            policy_fds.append(open_directory(path))
        policy_identities = tuple(
            (kind.st_dev, kind.st_ino)
            for kind in (os.fstat(fd) for fd in policy_fds)
        )
        prefix = (
            f"/proc/self/fd/{backend.executable_fd}",
            "--unshare-user",
            "--unshare-ipc",
            "--unshare-pid",
            "--disable-userns",
            "--assert-userns-disabled",
            "--uid",
            "0",
            "--gid",
            "0",
            "--cap-drop",
            "ALL",
            "--die-with-parent",
            "--bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--ro-bind-fd",
            str(duplicate_control_fd),
            control_path,
            "--bind-fd",
            str(duplicate_live_fd),
            live_path,
            "--proc",
            "/proc",
            "--chdir",
            child_cwd,
        )
        return ResumeNamespace(
            backend=backend,
            control_fd=duplicate_control_fd,
            live_fd=duplicate_live_fd,
            control_identity=(control_stat.st_dev, control_stat.st_ino),
            env_exec=_ENV_EXEC,
            env_identity=env_identity,
            live_identity=(live_stat.st_dev, live_stat.st_ino),
            policy_fds=tuple(policy_fds),
            policy_identities=policy_identities,
            prefix=prefix,
        )
    except BaseException as exc:
        for fd in (duplicate_live_fd, duplicate_control_fd):
            if fd >= 0:
                os.close(fd)
        for fd in policy_fds:
            os.close(fd)
        if backend is not None:
            backend.close()
        if isinstance(exc, ResumeNamespaceError):
            raise
        raise ResumeNamespaceError("resume namespace cannot be prepared") from exc


def run_version_probe(
    *,
    namespace: ResumeNamespace,
    prefix: tuple[str, ...],
    private: str,
    env: dict[str, str],
    cwd: str,
    version: str,
) -> None:
    namespace.revalidate()
    argv = [*prefix, "--", private, "--version"]
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            close_fds=True,
            pass_fds=namespace.pass_fds,
        )
    except OSError as exc:
        raise ResumeNamespaceError("version probe could not start") from exc
    if (
        proc.returncode != 0
        or proc.stderr
        or proc.stdout != f"omp/{version}\n".encode("utf-8")
    ):
        raise ResumeNamespaceError("version probe did not match the pinned executable")


__all__ = [
    "ResumeNamespace",
    "ResumeNamespaceError",
    "prepare_resume_namespace",
    "run_version_probe",
]
