"""Pinned OMP launch adapter (Task 5, OMP-I1).

Spawns the pinned OMP binary through a private digest-named copy, a strict
positive environment, an exact argv grammar, and (for profile lanes) the
Landlock write-confinement exec helper, then appends one adapter launch frame
immediately after the child's stdout. Grammar: ``python -m
orchestrator.providers.omp_launch run --lane <lane> --model <model>
[--conf-root <path>] [--provider-session-dir <path>]``. Lanes are the registry
template names mapping to code-owned policy lanes; ``--provider-session-dir``
selects the exclusive fresh path. Production ``main()`` supplies the code-owned
pin and resolver; tests exercise ``run(..., pin=..., binary_resolver=...)``.
"""

from __future__ import annotations

import io
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
from importlib import resources

from .omp_conf import admit_conf_tree, revalidate_conf_tree
from .omp_launch_fs import (
    LaunchFsError,
    create_empty_omp_cwd,
    empty_omp_cwd_path,
    open_empty_omp_cwd,
    primary_journal_identity_fd,
    session_inventory_fd,
    sha256_fd,
    stage_private_copy,
)
from .omp_launch_contract import POSITIVE_ENV_NAMES, parse_adapter_argv
from .omp_launch_policy import (
    CARRIER_ENV_NAMES,
    EMPTY_CWD_ENV,
    SESSION_IDENTITY_ENV,
    open_session_dir_verified,
    parse_session_identity,
)
from .omp_pin import OMP_BINARY_PIN, OmpBinaryPin
from .omp_write_confinement import SCHEMA_VERSION, canonical_policy_digest, landlock_abi, profile_root_sets

# Compatibility re-exports used by the parent expectation derivation and tests.
empty_omp_cwd = empty_omp_cwd_path

FRAME_TYPE = "orchestrator.omp_launch.v1"
MIN_LANDLOCK_ABI = 3

# Ambient lanes route the probe AND the child through the confinement helper's
# fd-exec mode: no Landlock, but the private target is opened no-follow and
# rehashed on the same fd so a swapped copy fails closed exactly like the
# confined path.
_EXEC_ONLY_PREFIX = [sys.executable, "-m", "orchestrator.providers.omp_write_confinement", "--exec-only"]

# Registry template name -> code-owned policy lane (frame/expectation vocab).
LANE_POLICY = {"omp": "ambient", "omp_unrestricted_workspace": "ambient-unrestricted",
               "omp_no_tools": "no-tools", "omp_conf": "conf", "omp_conf_inference": "conf-inference"}
AMBIENT_POLICIES = frozenset({"ambient", "ambient-unrestricted"})
PROFILE_POLICIES = frozenset({"no-tools", "conf", "conf-inference"})

# Task 1's recorded acceptance-build executable (root-a evidence), verified
# whole-file against the pin at every launch.
PRODUCTION_BINARY_PATH = "/home/ollie/.cache/omp-i1/root-a-evidence/dist-omp"

# The positive set minus the three values the adapter itself derives.
_PASS_THROUGH_ENV = frozenset(POSITIVE_ENV_NAMES) - {"PI_CODING_AGENT_DIR", "OMP_BROKER_URL", "OMP_BROKER_TOKEN"}


class LaunchError(Exception):
    """Adapter setup/validation failure; the child must never produce a frame."""


def binary_projection(pin: OmpBinaryPin) -> dict[str, str]:
    """Credential-minimized binary identity for frames and expectations."""
    return {
        "platform": pin.platform,
        "arch": pin.arch,
        "version": pin.version,
        "sha256": pin.executable_sha256,
    }


def neutral_conf_root() -> str:
    """Filesystem path of the launch-time neutral conf package."""
    return os.fspath(resources.files("orchestrator.omp_assets").joinpath("confs", "neutral"))




def _loopback_broker_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _positive_env(caller_env: dict[str, str]) -> dict[str, str]:
    """Build the exhaustive positive child environment."""
    env: dict[str, str] = {}
    for name in _PASS_THROUGH_ENV:
        value = caller_env.get(name)
        if not value:
            raise LaunchError(f"positive launch environment requires {name}")
        env[name] = value
    env["PI_CODING_AGENT_DIR"] = os.path.join(env["HOME"], ".omp", "agent")
    env["OMP_BROKER_URL"] = _loopback_broker_url()
    env["OMP_BROKER_TOKEN"] = secrets.token_hex(32)
    return env


def _env_roots(env: dict[str, str]) -> dict[str, str]:
    return {
        "data": env["XDG_DATA_HOME"],
        "state": env["XDG_STATE_HOME"],
        "cache": env["XDG_CACHE_HOME"],
        "temp": env["TMPDIR"],
    }


def _private_copy(source_path: str, pin: OmpBinaryPin, cache_home: str) -> str:
    """Stage the verified private copy; translate fs errors to LaunchError."""
    try:
        return stage_private_copy(source_path, pin, cache_home)
    except LaunchFsError as exc:
        raise LaunchError(str(exc)) from exc


def _helper_prefix(*, digest: str, protected, write, read) -> list[str]:
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
    return argv


def _run_version_probe(
    private: str,
    env: dict[str, str],
    cwd: str,
    pin: OmpBinaryPin,
    prefix: list[str] | None,
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


def _child_argv(lane: str, policy: str, model: str, session_dir: str | None, workspace: str) -> list[str]:
    argv = ["--session-dir", session_dir] if session_dir is not None else ["--no-session"]
    argv += ["--mode=json"]
    argv += ["--model", model]
    if policy == "ambient-unrestricted":
        argv += ["--yolo"]
    elif policy in ("no-tools", "conf-inference"):
        argv += ["--no-tools"]
    elif policy == "conf":
        argv += ["--add-dir", workspace]
    return argv


def _relay(proc: subprocess.Popen[bytes], out, err, redact: bytes | None = None) -> tuple[str | None, bool]:
    """Relay child stdout live; return (header session id, terminal seen).

    Child stderr is copied to ``err`` with the exact broker token bytes (if
    any) replaced by ``[redacted]`` so a leaky child can never persist the
    transport credential into captured output.
    """
    session_id: str | None = None
    terminal_seen = False
    header_parsed = False
    pending = b""

    def _drain_stderr() -> None:
        try:
            data = proc.stderr.read()
        except OSError:
            return
        if redact is not None:
            data = data.replace(redact, b"[redacted]")
        err.write(data.decode("utf-8", errors="replace"))

    thread = threading.Thread(target=_drain_stderr, daemon=True)
    thread.start()
    while True:
        chunk = proc.stdout.read(1 << 16)
        if not chunk:
            break
        out.write(chunk)
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            if not header_parsed:
                header_parsed = True
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    pass
                else:
                    if event.get("type") == "session" and isinstance(event.get("id"), str):
                        session_id = event["id"]
            if b'"type":"agent_end"' in line and b'"isTerminal":true' in line:
                terminal_seen = True
    proc.wait()
    thread.join()
    return session_id, terminal_seen


def run(*, argv: list[str], env: dict[str, str], stdin, out, err, pin: OmpBinaryPin, binary_resolver) -> int:
    """Launch the pinned OMP binary through the adapter; returns an exit code."""
    empty_cwd: str | None = None
    conf_fd: int | None = None
    session_fd: int | None = None
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
        positive = _positive_env(env)
        home_omp = os.path.join(positive["HOME"], ".omp")
        workspace = os.getcwd()
        profile = policy in PROFILE_POLICIES
        conf_root = args["conf_root"]
        if profile and conf_root is None:
            conf_root = neutral_conf_root()
        env_roots = _env_roots(positive)
        conf_snapshot = None
        conf_manifest = None
        if profile:
            try:
                conf_fd = os.open(conf_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except OSError as exc:
                raise LaunchError(f"cannot admit conf tree: {exc}") from exc
            try:
                conf_snapshot = admit_conf_tree(conf_fd)
            except Exception as exc:
                raise LaunchError(f"conf admission failed: {exc}") from exc
            conf_manifest = conf_snapshot.manifest_sha256
            expected_device = args["conf_root_device"]
            if expected_device is not None:
                observed = os.fstat(conf_fd)
                expected_identity = (
                    int(expected_device),
                    int(args["conf_root_inode"]),
                )
                if (observed.st_dev, observed.st_ino) != expected_identity:
                    raise LaunchError("frozen conf root identity disagrees")
                if conf_manifest != args["conf_manifest_sha256"]:
                    raise LaunchError("frozen conf manifest disagrees")

        if profile:
            policy_args = dict(lane=policy, workspace=workspace, session_dir=session_dir,
                               conf_root=conf_root, env_roots=env_roots)
            requested = env.get(EMPTY_CWD_ENV)
            if requested is not None:
                # Parent-prepared per-invocation empty cwd: open-only, never
                # re-created or adopted; the executor froze this exact path
                # into the expectation's child_argv and carries it through
                # the code-owned carrier.
                try:
                    open_empty_omp_cwd(requested)
                except LaunchFsError as exc:
                    raise LaunchError(f"cannot open the prepared empty OMP cwd: {exc}") from exc
                empty_cwd = requested
            else:
                # Direct-seam fallback: deterministic path created EXCLUSIVELY;
                # a pre-existing directory (even an empty one) fails the launch.
                empty_cwd = empty_omp_cwd(home=positive["HOME"], **policy_args)
                try:
                    create_empty_omp_cwd(empty_cwd)
                except LaunchFsError as exc:
                    raise LaunchError(str(exc)) from exc
            digest = canonical_policy_digest(home_omp=home_omp, empty_cwd=empty_cwd, **policy_args)
            protected, write, read = profile_root_sets(home_omp=home_omp, empty_cwd=empty_cwd, **policy_args)
            child_cwd = empty_cwd
            helper_prefix = _helper_prefix(digest=digest, protected=protected, write=write, read=read)
        else:
            digest = None
            child_cwd = workspace
            helper_prefix = _EXEC_ONLY_PREFIX  # ambient: same-fd exec, no Landlock

        # Fresh visit: open ONCE no-follow, compare the frozen identity BEFORE
        # the child runs, and retain the fd for the descriptor-relative scan
        # (T5-SEC-005/006): a same-UID swap cannot redirect attribution.
        if session_dir is not None:
            expected_identity = None
            carrier = env.get(SESSION_IDENTITY_ENV)
            if carrier is not None:
                try:
                    expected_identity = parse_session_identity(carrier)
                except LaunchFsError as exc:
                    raise LaunchError(str(exc)) from exc
            try:
                session_fd = open_session_dir_verified(session_dir, expected_identity)
            except LaunchFsError as exc:
                raise LaunchError(str(exc)) from exc

        carrier_env = {
            **positive,
            **{name: env[name] for name in CARRIER_ENV_NAMES if name in env},
        }

        private = _private_copy(binary_resolver(), pin, positive["XDG_CACHE_HOME"])
        _run_version_probe(private, carrier_env, child_cwd, pin, helper_prefix)


        child_argv = _child_argv(lane, policy, model, session_dir, workspace)
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
                env=carrier_env,
                close_fds=True,
            )
        except OSError as exc:
            raise LaunchError(f"child failed to start: {exc}") from exc

        if stdin_bytes is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()

        token = positive.get("OMP_BROKER_TOKEN")
        session_id, terminal_seen = _relay(
            proc, out, err, redact=token.encode("utf-8") if token else None
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
        observed: tuple[str, ...] = ()
        if session_dir is not None:
            visit_key = os.path.basename(session_dir.rstrip(os.sep))
            if session_id is None:
                raise LaunchError("fresh session requires a header session id")
            assert session_fd is not None
            try:
                observed = tuple(session_inventory_fd(session_fd))
                primary_relpath, primary_sha256 = primary_journal_identity_fd(session_fd, session_id)
            except LaunchFsError as exc:
                raise LaunchError(str(exc)) from exc

        if profile:
            try:
                revalidate_conf_tree(conf_fd, conf_snapshot)
            except Exception as exc:
                raise LaunchError(f"conf tree changed during the run: {exc}") from exc

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
                "env_names": list(POSITIVE_ENV_NAMES),
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
            "observed": {"advisor_relpaths": [], "child_relpaths": list(observed)},
        }
        out.write(json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n")
        return 0
    except LaunchError as exc:
        err.write(f"omp_launch: {exc}\n")
        return 2
    finally:
        if conf_fd is not None:
            os.close(conf_fd)
        if session_fd is not None:
            os.close(session_fd)
        if empty_cwd is not None:
            try:
                os.rmdir(empty_cwd)  # child cannot write it (read root)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    """Production entry: code-owned pin and resolver, never caller-supplied."""
    argv = list(sys.argv[1:] if argv is None else argv)
    return run(argv=argv, env=os.environ, stdin=sys.stdin.buffer, out=sys.stdout.buffer,
               err=sys.stderr, pin=OMP_BINARY_PIN, binary_resolver=lambda: PRODUCTION_BINARY_PATH)


if __name__ == "__main__":
    sys.exit(main())
