"""Pinned OMP launch adapter."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import threading
from importlib import resources
from typing import Any, cast

from .omp_conf import ConfSnapshot, admit_conf_tree, materialize_conf_at_discovery_path, revalidate_conf_tree, revalidate_materialized_conf
from .omp_launch_fs import LaunchFsError, create_empty_omp_cwd, empty_omp_cwd_path, open_empty_omp_cwd, profile_attempt_key, sha256_fd, stage_private_copy
from .omp_observation import OmpObservationError, observe_close, recognized_preset_topologies
from .omp_launch_contract import (
    AMBIENT_POLICIES, BROKER_TOKEN_ENV, BROKER_URL_ENV, LANE_POLICY,
    PROFILE_ENV_NAMES, PROFILE_POLICIES, build_child_argv, parse_adapter_argv,
    relay_child_output, validate_broker_pair,
)
from .omp_launch_policy import (
    ATTEMPT_FDS_ENV, CARRIER_ENV_NAMES, EMPTY_CWD_ENV, SESSION_IDENTITY_ENV,
    SESSION_PATH_FD_ENV,
    ProfileAttemptAuthority, adopt_profile_attempt_authority,
    attempt_env_roots, create_profile_attempt_authority,
    empty_omp_cwd_nonce, inherited_profile_conf_fd,
    open_session_dir_verified, parse_session_identity,
    profile_attempt_roots, strip_omp_carriers,
)
from .omp_pin import OMP_BINARY_PIN, OmpBinaryPin
from .omp_write_confinement import SCHEMA_VERSION, canonical_policy_digest, landlock_abi, profile_root_sets

empty_omp_cwd = empty_omp_cwd_path
FRAME_TYPE = "orchestrator.omp_launch.v1"
MIN_LANDLOCK_ABI = 3

EXEC_ONLY_PREFIX = [sys.executable, "-m", "orchestrator.providers.omp_write_confinement", "--exec-only"]

_PROFILE_OPTIONAL_ENV = ("COLORTERM", "LANG", "LC_ALL", "LC_CTYPE", "NO_COLOR",
                         "NODE_EXTRA_CA_CERTS", "SSL_CERT_DIR", "SSL_CERT_FILE", "TERM", "TZ")


class LaunchError(Exception):
    pass

def binary_projection(pin: OmpBinaryPin) -> dict[str, str]:
    return {"platform": pin.platform, "arch": pin.arch, "version": pin.version,
            "sha256": pin.executable_sha256}


def neutral_conf_root() -> str:
    return os.fspath(cast(os.PathLike[str], resources.files("orchestrator.omp_assets").joinpath("confs", "neutral")))


def resolve_omp_binary(env) -> str:
    """Resolve the first regular ``omp`` file from the admitted parent PATH."""
    path = env.get("PATH")
    if not path:
        raise LaunchError("admitted parent PATH is absent")
    for directory in path.split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, "omp")
        try:
            st = os.lstat(candidate)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            raise LaunchError(f"omp on PATH is not a regular file: {candidate}")
        return candidate
    raise LaunchError("omp is absent from the admitted parent PATH")


def _env_roots(env: dict[str, str]) -> dict[str, str]:
    missing = [
        name for name in ("HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                          "XDG_CACHE_HOME", "TMPDIR")
        if not env.get(name)
    ]
    if missing:
        raise LaunchError(
            "profile launch requires " + ", ".join(missing) + " in the caller environment"
        )
    return {
        "data": env["XDG_DATA_HOME"],
        "state": env["XDG_STATE_HOME"],
        "cache": env["XDG_CACHE_HOME"],
        "temp": env["TMPDIR"],
    }


def build_profile_env(
    caller_env: dict[str, str],
    attempt: dict[str, str],
    url: str,
    token: str,
) -> dict[str, str]:
    path = caller_env.get("PATH")
    if not path:
        raise LaunchError("profile launch requires PATH in the caller environment")
    env = {
        "HOME": attempt["HOME"],
        "XDG_CONFIG_HOME": attempt["XDG_CONFIG_HOME"],
        "XDG_DATA_HOME": attempt["XDG_DATA_HOME"],
        "XDG_STATE_HOME": attempt["XDG_STATE_HOME"],
        "XDG_CACHE_HOME": attempt["XDG_CACHE_HOME"],
        "TMPDIR": attempt["TMPDIR"],
        "SHELL": "/bin/bash",
        "PATH": path,
        "PI_CODING_AGENT_DIR": os.path.join(attempt["HOME"], ".omp", "agent"),
        BROKER_URL_ENV: url,
        BROKER_TOKEN_ENV: token,
    }
    for name in _PROFILE_OPTIONAL_ENV:
        value = caller_env.get(name)
        if value:
            env[name] = value
    return env


def _private_copy(source_path: str, pin: OmpBinaryPin, cache_home: str) -> str:
    try:
        return stage_private_copy(source_path, pin, cache_home)
    except LaunchFsError as exc:
        raise LaunchError(str(exc)) from exc


def _helper_prefix(
    *, digest: str, protected, write, read, root_fds=()
) -> list[str]:
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
    for descriptor in root_fds:
        argv += ["--root-fd", str(descriptor)]
    return argv


def _run_version_probe(
    private: str,
    env: dict[str, str],
    cwd: str,
    pin: OmpBinaryPin,
    prefix: list[str] | None,
    pass_fds: tuple[int, ...] = (),
) -> None:
    argv = ([*prefix, "--", private, "--version"] if prefix is not None else [private, "--version"])
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            close_fds=True,
            pass_fds=pass_fds,
        )
    except OSError as exc:
        raise LaunchError(f"version probe failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise LaunchError(f"version probe exited {proc.returncode}")
    if proc.stderr:
        raise LaunchError("version probe wrote to stderr")
    expected = f"omp/{pin.version}\n".encode("utf-8")
    if proc.stdout != expected:
        raise LaunchError("version probe output does not match the pinned version")


def run(*, argv: list[str], env: dict[str, str], stdin, out, err, pin: OmpBinaryPin, binary_resolver) -> int:
    empty_cwd: str | None = None
    conf_fd: int | None = None
    session_fd: int | None = None
    attempt: dict[str, str] | None = None
    empty_cwd_fd: int | None = None
    attempt_authority: ProfileAttemptAuthority | None = None
    child_env: dict[str, str] = {}
    try:
        try:
            args = parse_adapter_argv(argv, set(LANE_POLICY))
        except ValueError as exc:
            raise LaunchError(str(exc)) from exc
        lane = args["lane"]
        model = args["model"]
        policy = LANE_POLICY[lane]
        session_dir = args["session_dir"]
        persistence = "fresh" if session_dir is not None else "none"
        workspace = os.getcwd()
        profile = policy in PROFILE_POLICIES
        conf_root = args["conf_root"]
        if profile and conf_root is None: conf_root = neutral_conf_root()
        caller_env_roots = _env_roots(env) if profile else None
        carrier = env.get(ATTEMPT_FDS_ENV) if profile else None
        attempt_key = None
        if profile:
            assert conf_root is not None and caller_env_roots is not None
            attempt_key = profile_attempt_key(
                lane=policy, workspace=workspace, session_dir=session_dir,
                conf_root=conf_root, env_roots=caller_env_roots)
        broker_url = broker_token = None
        conf_snapshot = None
        conf_manifest = None
        if profile:
            assert conf_root is not None and caller_env_roots is not None
            try:
                broker_url, broker_token = validate_broker_pair(env)
            except ValueError as exc:
                raise LaunchError(str(exc)) from exc
            inherited_conf_fd = (
                inherited_profile_conf_fd(carrier) if carrier is not None else None)
            try:
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                conf_fd = (os.dup(inherited_conf_fd)
                           if inherited_conf_fd is not None
                           else os.open(conf_root, flags))
            except OSError as exc:
                raise LaunchError(f"cannot admit conf tree: {exc}") from exc
            try:
                conf_snapshot = admit_conf_tree(conf_fd)
            except Exception as exc:
                raise LaunchError(f"conf admission failed: {exc}") from exc
            conf_manifest = conf_snapshot.manifest_sha256
            expected_device = args["conf_root_device"]
            if expected_device is not None:
                expected_inode = args["conf_root_inode"]
                assert expected_inode is not None
                observed = os.fstat(conf_fd)
                expected_identity = (int(expected_device), int(expected_inode))
                if (observed.st_dev, observed.st_ino) != expected_identity:
                    raise LaunchError("frozen conf root identity disagrees")
                if conf_manifest != args["conf_manifest_sha256"]:
                    raise LaunchError("frozen conf manifest disagrees")

        if profile:
            assert attempt_key is not None and caller_env_roots is not None
            assert conf_snapshot is not None and broker_url is not None and broker_token is not None
            requested = env.get(EMPTY_CWD_ENV)
            if requested is not None:
                try:
                    nonce = empty_omp_cwd_nonce(
                        requested, expected_key=attempt_key
                    )
                    empty_cwd_fd = open_empty_omp_cwd(requested)
                except LaunchFsError as exc:
                    raise LaunchError(
                        f"cannot open the prepared empty OMP cwd: {exc}"
                    ) from exc
                empty_cwd = requested
            else:
                nonce = None
                empty_cwd = empty_omp_cwd_path(
                    home=env["HOME"],
                    lane=policy,
                    workspace=workspace,
                    session_dir=session_dir,
                    conf_root=conf_root,
                    env_roots=caller_env_roots,
                )
                try:
                    create_empty_omp_cwd(empty_cwd)
                    empty_cwd_fd = open_empty_omp_cwd(empty_cwd)
                except LaunchFsError as exc:
                    raise LaunchError(str(exc)) from exc
            attempt = profile_attempt_roots(
                env_roots=caller_env_roots,
                lane=policy,
                workspace=workspace,
                session_dir=session_dir,
                conf_root=conf_root,
                nonce=nonce,
            )
            try:
                attempt_authority = (
                    adopt_profile_attempt_authority(attempt, carrier)
                    if carrier is not None
                    else create_profile_attempt_authority(attempt)
                )
                materialize_conf_at_discovery_path(
                    attempt_authority, conf_snapshot
                )
            except Exception as exc:
                raise LaunchError(
                    f"profile attempt preparation failed: {exc}"
                ) from exc
            policy_args = cast(dict[str, Any], dict(
                lane=policy, workspace=workspace, session_dir=session_dir,
                conf_root=conf_root, env_roots=attempt_env_roots(attempt)))
            home_omp = os.path.join(attempt["HOME"], ".omp")
            protected, write, read = profile_root_sets(
                home_omp=home_omp, empty_cwd=empty_cwd, **policy_args
            )
            fd_by_path = {
                **attempt_authority.path_fds,
                conf_root: conf_fd,
                empty_cwd: empty_cwd_fd,
            }
            helper_root_fds = tuple(
                fd_by_path.get(path, -1)
                for rows in (protected, write, read)
                for _label, path in rows
            )
            digest = canonical_policy_digest(
                home_omp=home_omp, empty_cwd=empty_cwd,
                root_fds=helper_root_fds, **policy_args)
            helper_prefix = _helper_prefix(
                digest=digest,
                protected=protected,
                write=write,
                read=read,
                root_fds=helper_root_fds,
            )
            child_cwd = empty_cwd
            child_env = build_profile_env(env, attempt, broker_url, broker_token)
        else:
            digest = None
            child_cwd = workspace
            helper_root_fds = ()
            helper_prefix = EXEC_ONLY_PREFIX
            child_env = dict(env)
            strip_omp_carriers(child_env)
        child_env.pop("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", None)
        if session_dir is not None:
            expected_identity = None
            carrier = env.get(SESSION_IDENTITY_ENV)
            if carrier is not None:
                try:
                    expected_identity = parse_session_identity(carrier)
                except LaunchFsError as exc:
                    raise LaunchError(str(exc)) from exc
            try:
                session_fd = open_session_dir_verified(
                    session_dir, expected_identity
                )
            except LaunchFsError as exc:
                raise LaunchError(str(exc)) from exc

        private_cache = (cast(dict[str, str], attempt)["XDG_CACHE_HOME"]
                         if profile else env.get("XDG_CACHE_HOME"))
        if not private_cache: raise LaunchError("ambient launch requires XDG_CACHE_HOME")
        private = _private_copy(binary_resolver(), pin, private_cache)
        passed_root_fds = tuple(
            sorted({fd for fd in helper_root_fds if fd >= 0})
        )
        _run_version_probe(
            private, child_env, child_cwd, pin, helper_prefix, passed_root_fds)
        child_session_dir = session_dir
        child_pass_fds = passed_root_fds
        if session_fd is not None:
            child_session_dir = f"/proc/self/fd/{session_fd}"
            session_kind = os.fstat(session_fd)
            child_env[SESSION_PATH_FD_ENV] = str(session_fd)
            child_env[SESSION_IDENTITY_ENV] = f"{session_kind.st_dev}:{session_kind.st_ino}"
            child_pass_fds = tuple(sorted({*passed_root_fds, session_fd}))

        child_argv = build_child_argv(
            lane, policy, model, child_session_dir, workspace, empty_cwd)
        if isinstance(stdin, bytes):
            stdin_bytes, stdin_arg = stdin, subprocess.PIPE
        elif hasattr(stdin, "fileno"):
            stdin_bytes, stdin_arg = None, stdin.fileno()
        else:
            stdin_bytes, stdin_arg = stdin.read(), subprocess.PIPE
        try:
            proc = subprocess.Popen(
                [*helper_prefix, "--", private, *child_argv],
                stdin=stdin_arg,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=child_cwd,
                env=child_env,
                close_fds=True,
                pass_fds=child_pass_fds,
            )
            strip_omp_carriers(child_env)
        except OSError as exc:
            raise LaunchError(f"child failed to start: {exc}") from exc

        if stdin_bytes is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()

        redact_token = env.get(BROKER_TOKEN_ENV)
        session_id, terminal_seen = relay_child_output(
            proc, out, err,
            redact=redact_token.encode("utf-8") if redact_token else None,
        )
        if proc.returncode != 0:
            err.write(f"omp_launch: child exited {proc.returncode}\n")
            return proc.returncode
        if not terminal_seen:
            err.write("omp_launch: OMP child stream did not settle\n")
            return 1

        visit_key = None
        primary_relpath = None
        primary_sha256 = None
        advisor_relpaths: list[str] = []
        child_relpaths: list[str] = []
        if session_dir is not None:
            visit_key = os.path.basename(session_dir.rstrip(os.sep))
            if session_id is None:
                raise LaunchError("fresh session requires a header session id")
            assert session_fd is not None
            try:
                child_home = cast(dict[str, str], attempt)["HOME"] if profile else env["HOME"]
                report = observe_close(
                    session_root_fd=session_fd,
                    stdout_session_id=session_id,
                    conf_manifest_sha256=conf_manifest,
                    recognized_topologies=recognized_preset_topologies(),
                    isolated_worktree_root=os.path.join(child_home, ".omp", "wt"),
                )
            except OmpObservationError as exc:
                raise LaunchError(str(exc)) from exc
            primary_relpath = report.primary_relpath
            primary_sha256 = report.primary_sha256
            advisor_relpaths = list(report.advisor_relpaths)
            child_relpaths = list(report.child_relpaths)

        if profile:
            assert conf_fd is not None and conf_snapshot is not None and attempt_authority is not None
            try:
                revalidate_conf_tree(conf_fd, conf_snapshot)
            except Exception as exc:
                raise LaunchError(f"conf tree changed during the run: {exc}") from exc
            try:
                revalidate_materialized_conf(
                    attempt_authority, conf_snapshot
                )
            except Exception as exc:
                raise LaunchError(
                    f"materialized conf changed during the run: {exc}"
                ) from exc

        confinement = None
        if profile:
            confinement = {
                "schema_version": SCHEMA_VERSION,
                "landlock_abi": landlock_abi(),
                "policy_sha256": digest,
            }
        frame = {
            "type": FRAME_TYPE,
            "lane": policy,
            "persistence": persistence,
            "binary": binary_projection(pin),
            "child": {
                "argv": argv,
                "cwd": child_cwd,
                "env_names": sorted(child_env),
                "exit_code": proc.returncode,
            },
            "session": {
                "id": session_id,
                "visit_key": visit_key,
                "primary_relpath": primary_relpath,
                "primary_sha256": primary_sha256,
            },
            "conf": {"manifest_sha256": conf_manifest},
            "confinement": confinement,
                        "observed": {"advisor_relpaths": advisor_relpaths, "child_relpaths": child_relpaths},
        }
        out.write(json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n")
        return 0
    except LaunchError as exc:
        err.write(f"omp_launch: {exc}\n")
        return 2
    finally:
        if conf_fd is not None: os.close(conf_fd)
        if session_fd is not None: os.close(session_fd)
        if empty_cwd is not None:
            try:
                os.rmdir(empty_cwd)  # child cannot write it (read root)
            except OSError:
                pass
        if attempt_authority is not None: attempt_authority.close()
        if empty_cwd_fd is not None: os.close(empty_cwd_fd)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    return run(argv=argv, env=dict(os.environ), stdin=sys.stdin.buffer, out=sys.stdout.buffer,
               err=sys.stderr, pin=OMP_BINARY_PIN,
               binary_resolver=lambda: resolve_omp_binary(os.environ))


if __name__ == "__main__":
    sys.exit(main())
