"""Fail-closed launch preparation for the foreground OMP TTY bridge."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from orchestrator._common.safe_tree import (
    SafeTreeError,
    read_regular_file,
    walk_regular_files,
)
from orchestrator.prompt_scaffold import ScaffoldVerification
from orchestrator.prompt_session import PromptSessionError
from orchestrator.prompt_session_scaffold import (
    verify_captured_occupant,
    verify_private_scaffold,
)
from orchestrator.prompt_resume_namespace import (
    ResumeNamespace,
    ResumeNamespaceError,
    prepare_resume_namespace,
    run_version_probe,
)
from orchestrator.providers.omp_conf import (
    ConfSnapshot,
    OmpConfError,
    admit_conf_tree,
    materialize_conf_at_discovery_path,
)
from orchestrator.providers.omp_launch import EXEC_ONLY_PREFIX, build_profile_env
from orchestrator.providers.omp_launch_contract import (
    BROKER_TOKEN_ENV,
    BROKER_URL_ENV,
    build_interactive_argv,
)
from orchestrator.providers.omp_launch_fs import (
    LaunchFsError,
    create_empty_omp_cwd,
    empty_omp_cwd_path,
    open_dir_no_follow,
    stage_private_copy,
)
from orchestrator.providers.omp_launch_policy import (
    ProfileAttemptAuthority,
    attempt_env_roots,
    create_profile_attempt_authority,
    profile_attempt_roots,
)
from orchestrator.providers.observation import terminal_safe_line
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


def _write_diagnostic(descriptor: int, text: str) -> None:
    os.write(descriptor, (terminal_safe_line(text) + "\n").encode())


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
    source_binary: str
    frame_binary: dict[str, str]
    scaffold: ScaffoldVerification
    interactive_argv: tuple[str, ...]
    helper_prefix: tuple[str, ...]
    namespace: ResumeNamespace
    child_cwd: str
    actual_confinement: dict[str, object] | None
    conf_manifest: str | None
    empty_cwd: str | None
    profile_attempt: ProfileAttemptAuthority | None
    conf_snapshot: ConfSnapshot | None

    def close(self) -> None:
        self.namespace.close()
        if self.profile_attempt is not None:
            self.profile_attempt.close()


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


def _open_public_scaffold(workspace: str, scaffold_relpath: str) -> int:
    try:
        descriptor = open_dir_no_follow(workspace)
    except LaunchFsError as exc:
        raise PreflightError(
            "prompt_resume_scaffold_invalid",
            f"workspace cannot be opened: {exc}",
        ) from exc
    try:
        for part in PurePosixPath(scaffold_relpath).parts:
            child = os.open(part, _DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise PreflightError(
            "prompt_resume_scaffold_invalid",
            f"scaffold cannot be opened: {exc}",
        ) from exc


def capture_scaffold_inputs(
    *,
    run_fd: int,
    workspace: str,
    scaffold_relpath: str,
    link,
    frame_binary: dict[str, str],
) -> ScaffoldVerification:
    private_fd = public_fd = -1
    try:
        private_fd = open_relative(run_fd, "prompt-inputs")
        public_fd = _open_public_scaffold(workspace, scaffold_relpath)
        verification = verify_private_scaffold(private_fd, link)
        verify_captured_occupant(public_fd, verification, private=False)
        manifest = loads_strict(
            verification.manifest_bytes.decode("utf-8")
        )
        binary = (
            manifest.get("binary")
            if isinstance(manifest, dict)
            else None
        )
        if binary != frame_binary:
            raise PromptSessionError(
                "session_link_invalid",
                "captured scaffold binary disagrees with the launch frame",
            )
        return verification
    except (
        OSError,
        PromptSessionError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise PreflightError(
            "prompt_resume_scaffold_invalid",
            f"captured scaffold cannot be admitted: {exc}",
        ) from exc
    finally:
        if public_fd >= 0:
            os.close(public_fd)
        if private_fd >= 0:
            os.close(private_fd)


def copy_conf_tree(
    *, run_fd: int, frozen_relpath: str, expected_digest: str, runtime_base: str
) -> tuple[str, ConfSnapshot]:
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
        return dest, copy_manifest
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


def prepare_launch(
    *,
    run_fd: int,
    live_fd: int,
    control_fd: int,
    control_path: str,
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
    scaffold = capture_scaffold_inputs(
        run_fd=run_fd,
        workspace=workspace,
        scaffold_relpath=link["scaffold_relpath"],
        link=resolved.link,
        frame_binary=frame_binary,
    )
    conf_manifest = link["digests"]["conf_manifest_sha256"]
    source_binary = binary_resolver()
    private = stage_private_copy(
        source_binary, pin, bridge_env["XDG_CACHE_HOME"]
    )
    actual_confinement: dict[str, object] | None = None
    helper_prefix_: tuple[str, ...] | None = tuple(EXEC_ONLY_PREFIX)
    policy_paths: tuple[str, ...] = ()
    child_cwd = workspace
    empty_cwd: str | None = None
    profile_attempt: ProfileAttemptAuthority | None = None
    conf_snapshot: ConfSnapshot | None = None
    if profile:
        try:
            conf_copy, conf_snapshot = copy_conf_tree(
                run_fd=run_fd,
                frozen_relpath=link["paths"]["conf"],
                expected_digest=conf_manifest,
                runtime_base=runtime_base,
            )
            caller_roots = env_roots(bridge_env)
            nonce = secrets.token_hex(8)
            empty_cwd = empty_omp_cwd_path(
                home=bridge_env["HOME"],
                lane=lane,
                workspace=workspace,
                session_dir=live_dir,
                conf_root=conf_copy,
                env_roots=caller_roots,
                nonce=nonce,
            )
            create_empty_omp_cwd(empty_cwd)
            attempt = profile_attempt_roots(
                env_roots=caller_roots,
                lane=lane,
                workspace=workspace,
                session_dir=live_dir,
                conf_root=conf_copy,
                nonce=nonce,
            )
            profile_attempt = create_profile_attempt_authority(attempt)
            materialize_conf_at_discovery_path(profile_attempt, conf_snapshot)
            roots = attempt_env_roots(attempt)
            home_omp = os.path.join(attempt["HOME"], ".omp")
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
            policy_paths = tuple(
                path for _label, path in protected + write + read
            )
            helper_prefix_ = helper_prefix(
                digest=policy_digest,
                protected=protected,
                write=write,
                read=read,
            )
            child_cwd = empty_cwd
            child_env = build_profile_env(
                bridge_env,
                attempt,
                bridge_env[BROKER_URL_ENV],
                bridge_env[BROKER_TOKEN_ENV],
            )
            bridge_env.clear()
            bridge_env.update(child_env)
            actual_confinement = {
                "schema_version": SCHEMA_VERSION,
                "landlock_abi": landlock_abi(),
                "policy_sha256": policy_digest,
            }
        except BaseException:
            if profile_attempt is not None:
                profile_attempt.close()
            raise
    try:
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
        _write_diagnostic(
            stderr_fd, f"prompt resume: argv: {' '.join(interactive_argv)}"
        )
        _write_diagnostic(
            stderr_fd, f"prompt resume: env names: {' '.join(sorted(bridge_env))}"
        )
    except BaseException:
        if profile_attempt is not None:
            profile_attempt.close()
        raise
    try:
        namespace = prepare_resume_namespace(
            control_fd=control_fd,
            live_fd=live_fd,
            control_path=control_path,
            live_path=live_dir,
            child_cwd=child_cwd,
            policy_paths=policy_paths,
        )
    except ResumeNamespaceError as exc:
        if profile_attempt is not None:
            profile_attempt.close()
        raise PreflightError(
            "prompt_resume_namespace_unavailable", str(exc)
        ) from exc
    helper_prefix_ = namespace.wrap_command(helper_prefix_)
    try:
        run_version_probe(
            namespace=namespace,
            prefix=helper_prefix_,
            private=private,
            env=bridge_env,
            cwd=child_cwd,
            version=pin.version,
        )
    except ResumeNamespaceError as exc:
        namespace.close()
        if profile_attempt is not None:
            profile_attempt.close()
        raise PreflightError("prompt_resume_probe_failed", str(exc)) from exc
    return LaunchPlan(
        private=private,
        source_binary=source_binary,
        frame_binary=dict(frame_binary),
        scaffold=scaffold,
        interactive_argv=interactive_argv,
        helper_prefix=helper_prefix_,
        namespace=namespace,
        child_cwd=child_cwd,
        actual_confinement=actual_confinement,
        conf_manifest=conf_manifest,
        empty_cwd=empty_cwd,
        profile_attempt=profile_attempt,
        conf_snapshot=conf_snapshot,
    )
