"""Task 10: preflight/launch preparation for the foreground TTY bridge.

Everything here runs before the interactive child spawns and writes nothing
to the run: launch-frame binary read, no-replace scaffold pin, frozen-conf
verify plus a fresh private copy, the profile policy/empty-cwd/helper prefix,
private staging, the exact X8 interactive argv, the argv/env-names print, and
the pinned version probe. A failure raises ``PreflightError`` and the
orchestrator publishes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from orchestrator._common.safe_tree import (
    SafeTreeError,
    read_regular_file,
    walk_regular_files,
)
from orchestrator.providers.omp_conf import OmpConfError, admit_conf_tree
from orchestrator.providers.omp_launch_contract import (
    POSITIVE_ENV_NAMES,
    build_interactive_argv,
)
from orchestrator.providers.omp_launch_fs import (
    LaunchFsError,
    create_empty_omp_cwd,
    empty_omp_cwd_path,
    open_dir_no_follow,
    stage_private_copy,
)
from orchestrator.providers.omp_protocol import loads_strict
from orchestrator.providers.omp_write_confinement import (
    MIN_LANDLOCK_ABI,
    SCHEMA_VERSION,
    canonical_policy_digest,
    landlock_abi,
    profile_root_sets,
)

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_BINARY_KEYS = frozenset({"platform", "arch", "version", "sha256"})


class PreflightError(Exception):
    """A stable, non-secret preflight failure; the bridge publishes nothing."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Everything the orchestrator needs to spawn one TTY child exactly."""

    private: str
    interactive_argv: tuple[str, ...]
    helper_prefix: tuple[str, ...] | None
    child_cwd: str
    actual_confinement: dict[str, object] | None
    conf_manifest: str | None
    empty_cwd: str | None


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def open_relative(root_fd: int, relative: str) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in PurePosixPath(relative).parts:
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError:
        os.close(descriptor)
        raise
    return descriptor


def read_frame_binary(run_fd: int, visit_key: str) -> dict[str, str]:
    try:
        metadata = loads_strict(
            read_regular_file(run_fd, f"provider_sessions/{visit_key}.json")
            .decode("utf-8")
        )
    except (SafeTreeError, UnicodeDecodeError, ValueError, OSError) as exc:
        raise PreflightError(
            "prompt_resume_invalid", f"visit metadata cannot be admitted: {exc}"
        ) from exc
    if not isinstance(metadata, dict):
        raise PreflightError("prompt_resume_invalid", "visit metadata is not an object")
    frame = metadata.get("parser_summary", {}).get("launch_frame")
    binary = frame.get("binary") if isinstance(frame, dict) else None
    if not isinstance(binary, dict) or set(binary) != _BINARY_KEYS:
        raise PreflightError("prompt_resume_invalid", "launch frame binary is not closed")
    return dict(binary)


def verify_scaffold(
    *,
    workspace: str,
    scaffold_relpath: str,
    expected_digest: str,
    frame_binary: dict[str, str],
    provider_name: str,
) -> None:
    """Pin the no-replace scaffold: digest, frame binary, and provider."""
    try:
        workspace_fd = open_dir_no_follow(workspace)
    except LaunchFsError as exc:
        raise PreflightError(
            "prompt_resume_scaffold_invalid", f"workspace cannot be opened: {exc}"
        ) from exc
    descriptor = os.dup(workspace_fd)
    os.close(workspace_fd)
    try:
        for part in PurePosixPath(scaffold_relpath).parts:
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        try:
            raw = read_regular_file(descriptor, "scaffold.json")
        finally:
            os.close(descriptor)
    except (OSError, SafeTreeError) as exc:
        raise PreflightError(
            "prompt_resume_scaffold_invalid", f"scaffold cannot be admitted: {exc}"
        ) from exc
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise PreflightError(
            "prompt_resume_scaffold_invalid",
            "scaffold manifest digest disagrees with the link",
        )
    try:
        manifest = loads_strict(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PreflightError(
            "prompt_resume_scaffold_invalid", "scaffold manifest cannot be parsed"
        ) from exc
    binary = manifest.get("binary") if isinstance(manifest, dict) else None
    provider = manifest.get("provider") if isinstance(manifest, dict) else None
    if binary != frame_binary:
        raise PreflightError(
            "prompt_resume_scaffold_invalid",
            "scaffold binary disagrees with the launch frame",
        )
    if not isinstance(provider, dict) or provider.get("registry_name") != provider_name:
        raise PreflightError(
            "prompt_resume_scaffold_invalid", "scaffold provider disagrees with the link"
        )


def copy_conf_tree(
    *, run_fd: int, frozen_relpath: str, expected_digest: str, runtime_base: str
) -> str:
    """Verify the frozen conf manifest, then materialize a fresh private copy."""
    try:
        frozen_fd = open_relative(run_fd, frozen_relpath)
    except OSError as exc:
        raise PreflightError(
            "prompt_resume_conf_invalid", f"frozen conf cannot be opened: {exc}"
        ) from exc
    try:
        try:
            frozen = admit_conf_tree(frozen_fd)
            rows = list(walk_regular_files(frozen_fd))
        except (OmpConfError, SafeTreeError, OSError, TypeError, ValueError) as exc:
            raise PreflightError(
                "prompt_resume_conf_invalid", f"frozen conf cannot be admitted: {exc}"
            ) from exc
        if frozen.manifest_sha256 != expected_digest:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                "frozen conf manifest disagrees with the link",
            )
        nonce = secrets.token_hex(16)
        parent = os.path.join(runtime_base, nonce)
        dest = os.path.join(parent, "conf")
        os.makedirs(parent, mode=0o700, exist_ok=False)
        os.mkdir(dest, mode=0o700)
        try:
            for row in rows:
                target = os.path.join(dest, row.relative_path)
                os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
                data = read_regular_file(frozen_fd, row.relative_path, expected=row)
                fd = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                )
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
        except (OSError, SafeTreeError) as exc:
            raise PreflightError(
                "prompt_resume_conf_invalid", f"fresh conf copy failed: {exc}"
            ) from exc
    finally:
        os.close(frozen_fd)
    try:
        copy_fd = open_dir_no_follow(dest)
    except LaunchFsError as exc:
        raise PreflightError(
            "prompt_resume_conf_invalid",
            f"fresh conf copy cannot be re-opened: {exc}",
        ) from exc
    try:
        try:
            copy_manifest = admit_conf_tree(copy_fd)
        except (OmpConfError, SafeTreeError, OSError, TypeError, ValueError) as exc:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                f"fresh conf copy cannot be admitted: {exc}",
            ) from exc
        if copy_manifest.manifest_sha256 != expected_digest:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                "fresh conf copy manifest disagrees with the link",
            )
        return dest
    finally:
        os.close(copy_fd)


def env_roots(env: dict[str, str]) -> dict[str, str]:
    return {
        name: env[env_name]
        for name, env_name in (
            ("data", "XDG_DATA_HOME"),
            ("state", "XDG_STATE_HOME"),
            ("cache", "XDG_CACHE_HOME"),
            ("temp", "TMPDIR"),
        )
    }


def helper_prefix(*, digest: str, protected, write, read) -> tuple[str, ...]:
    argv = [
        sys.executable,
        "-m",
        "orchestrator.providers.omp_write_confinement",
        "--abi",
        str(MIN_LANDLOCK_ABI),
        "--digest",
        digest,
    ]
    for role, rows in (("protected", protected), ("write", write), ("read", read)):
        for label, path in rows:
            argv += [f"--{role}", f"{label}={path}"]
    return tuple(argv)


def run_version_probe(
    *, private: str, env: dict[str, str], cwd: str, pin, prefix: tuple[str, ...] | None
) -> None:
    argv = (
        [*prefix, "--", private, "--version"]
        if prefix is not None
        else [private, "--version"]
    )
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            close_fds=True,
        )
    except OSError as exc:
        raise PreflightError(
            "prompt_resume_probe_failed", f"version probe could not start: {exc}"
        ) from exc
    expected = f"omp/{pin.version}\n".encode("utf-8")
    if proc.returncode != 0 or proc.stderr or proc.stdout != expected:
        raise PreflightError(
            "prompt_resume_probe_failed",
            "version probe did not match the pinned executable",
        )


def prepare_launch(
    *,
    run_fd: int,
    resolved,
    active,
    mode: str,
    pin,
    binary_resolver,
    bridge_env: dict[str, str],
    workspace: str,
    runtime_base: str,
    stderr_fd: int,
) -> LaunchPlan:
    """Run every preflight check and build the exact child launch plan."""
    link = resolved.link.document
    provider_name = link["provider"]["name"]
    lane = link["provider"]["lane"]
    profile = lane in ("no-tools", "conf")
    live_dir = os.path.join(os.fspath(resolved.run_root), link["paths"]["live"])
    frame_binary = read_frame_binary(run_fd, resolved.visit_key)
    verify_scaffold(
        workspace=workspace,
        scaffold_relpath=link["scaffold_relpath"],
        expected_digest=link["digests"]["scaffold_manifest_sha256"],
        frame_binary=frame_binary,
        provider_name=provider_name,
    )
    conf_manifest = link["digests"]["conf_manifest_sha256"]
    actual_confinement: dict[str, object] | None = None
    helper_prefix_: tuple[str, ...] | None = None
    child_cwd = workspace
    empty_cwd: str | None = None
    if profile:
        conf_copy = copy_conf_tree(
            run_fd=run_fd,
            frozen_relpath=link["paths"]["conf"],
            expected_digest=conf_manifest,
            runtime_base=runtime_base,
        )
        roots = env_roots(bridge_env)
        home_omp = os.path.join(bridge_env["HOME"], ".omp")
        empty_cwd = empty_omp_cwd_path(
            home=bridge_env["HOME"],
            lane=lane,
            workspace=workspace,
            session_dir=live_dir,
            conf_root=conf_copy,
            env_roots=roots,
            nonce=secrets.token_hex(8),
        )
        create_empty_omp_cwd(empty_cwd)
        policy_digest = canonical_policy_digest(
            lane=lane,
            home_omp=home_omp,
            session_dir=live_dir,
            conf_root=conf_copy,
            workspace=workspace,
            empty_cwd=empty_cwd,
            env_roots=roots,
        )
        protected, write, read = profile_root_sets(
            lane=lane,
            home_omp=home_omp,
            session_dir=live_dir,
            conf_root=conf_copy,
            workspace=workspace,
            empty_cwd=empty_cwd,
            env_roots=roots,
        )
        helper_prefix_ = helper_prefix(
            digest=policy_digest, protected=protected, write=write, read=read
        )
        child_cwd = empty_cwd
        actual_confinement = {
            "schema_version": SCHEMA_VERSION,
            "landlock_abi": landlock_abi(),
            "policy_sha256": policy_digest,
        }
    private = stage_private_copy(binary_resolver(), pin, bridge_env["XDG_CACHE_HOME"])
    interactive_argv = build_interactive_argv(
        provider_name,
        link["provider"]["model"],
        private_binary=private,
        live_dir=live_dir,
        mode=mode,
        source_session_id=active.session_id,
        workspace=workspace,
        empty_cwd=empty_cwd,
    )
    os.write(stderr_fd, f"prompt resume: argv: {' '.join(interactive_argv)}\n".encode("utf-8"))
    os.write(
        stderr_fd,
        f"prompt resume: env names: {' '.join(sorted(POSITIVE_ENV_NAMES))}\n".encode("utf-8"),
    )
    run_version_probe(
        private=private, env=bridge_env, cwd=child_cwd, pin=pin, prefix=helper_prefix_
    )
    return LaunchPlan(
        private=private,
        interactive_argv=interactive_argv,
        helper_prefix=helper_prefix_,
        child_cwd=child_cwd,
        actual_confinement=actual_confinement,
        conf_manifest=conf_manifest,
        empty_cwd=empty_cwd,
    )
