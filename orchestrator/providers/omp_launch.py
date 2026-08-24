"""Pinned OMP launch adapter (Task 5, OMP-I1).

Spawns the pinned OMP binary through a private digest-named copy, a strict
positive environment, an exact argv grammar, and (for profile lanes) the
Landlock write-confinement exec helper, then appends one adapter launch frame
immediately after the child's stdout.

Grammar: ``python -m orchestrator.providers.omp_launch run --lane <lane>
--model <model> [--conf-root <path>] [--provider-session-dir <path>]``.

Lanes are the registry template names; each maps to a code-owned policy lane.
``--conf-root`` is accepted only on the conf lane; ``--provider-session-dir``
selects the exclusive fresh path. Production ``main()`` supplies the code-owned
pin and resolver; tests exercise ``run(..., pin=..., binary_resolver=...)``
directly.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import threading
from importlib import resources

from .omp_conf import admit_conf_tree, revalidate_conf_tree
from .omp_pin import OMP_BINARY_PIN, OmpBinaryPin
from .omp_write_confinement import SCHEMA_VERSION, canonical_policy_digest, landlock_abi, profile_root_sets

FRAME_TYPE = "orchestrator.omp_launch.v1"
MIN_LANDLOCK_ABI = 3

# Registry template name -> code-owned policy lane (the frame/expectation
# vocabulary pinned by omp_protocol).
LANE_POLICY = {
    "omp": "ambient",
    "omp_unrestricted_workspace": "ambient-unrestricted",
    "omp_no_tools": "no-tools",
    "omp_conf": "conf",
    "omp_conf_inference": "conf-inference",
}
AMBIENT_POLICIES = frozenset({"ambient", "ambient-unrestricted"})
PROFILE_POLICIES = frozenset({"no-tools", "conf", "conf-inference"})

# Task 1's recorded acceptance-build executable (root-a evidence), verified
# whole-file against the pin at every launch.
PRODUCTION_BINARY_PATH = "/home/ollie/.cache/omp-i1/root-a-evidence/dist-omp"

_POSITIVE_ENV_NAMES = frozenset({"HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "PI_CODING_AGENT_DIR", "OMP_BROKER_URL", "OMP_BROKER_TOKEN"})
# The positive set minus the three values the adapter itself derives.
_PASS_THROUGH_ENV = _POSITIVE_ENV_NAMES - {"PI_CODING_AGENT_DIR", "OMP_BROKER_URL", "OMP_BROKER_TOKEN"}


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


def empty_omp_cwd(
    *,
    home: str,
    lane: str,
    workspace: str,
    session_dir: str | None,
    conf_root: str | None,
    env_roots: dict[str, str],
) -> str:
    """Deterministic profile-isolated empty cwd under ``$HOME`` (never inside a
    write root, so the helper's container-root rejection cannot fire)."""
    canonical = json.dumps(
        {"lane": lane, "workspace": workspace, "session_dir": session_dir,
         "conf_root": conf_root, "env_roots": env_roots},
        separators=(",", ":"), sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    path = os.path.join(home, "omp-empty-" + digest)
    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        entry = os.path.join(path, name)
        if os.path.isdir(entry) and not os.path.islink(entry):
            shutil.rmtree(entry)
        else:
            os.unlink(entry)
    return path


def _parse_argv(argv: list[str]) -> dict[str, str | None]:
    if argv[:1] != ["run"]:
        raise LaunchError("expected leading 'run' subcommand")
    args: dict[str, str | None] = {"lane": None, "model": None, "conf_root": None, "session_dir": None}
    seen: set[str] = set()
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg not in ("--lane", "--model", "--conf-root", "--provider-session-dir"):
            raise LaunchError(
                f"unexpected {'option' if arg.startswith('-') else 'positional argument'} {arg!r}"
            )
        if arg in seen or index + 1 >= len(argv):
            raise LaunchError(f"duplicate option {arg!r}" if arg in seen else f"missing value for {arg!r}")
        value = argv[index + 1]
        index += 2
        seen.add(arg)
        if arg == "--lane":
            if value not in LANE_POLICY:
                raise LaunchError(f"unknown lane {value!r}")
            args["lane"] = value
        elif arg == "--model":
            if not value or any(ch.isspace() for ch in value):
                raise LaunchError("model must be a single non-whitespace token")
            args["model"] = value
        elif arg in ("--conf-root", "--provider-session-dir"):
            if not os.path.isabs(value):
                raise LaunchError(f"{arg} must be an absolute path")
            args["conf_root" if arg == "--conf-root" else "session_dir"] = value
    if args["lane"] is None:
        raise LaunchError("missing --lane")
    if args["model"] is None:
        raise LaunchError("missing --model")
    if args["conf_root"] is not None and args["lane"] != "omp_conf":
        raise LaunchError("conf-lane-only: --conf-root is accepted only on the omp_conf lane")
    if args["lane"] == "omp_conf" and args["conf_root"] is None:
        raise LaunchError("the omp_conf lane requires --conf-root")
    return args


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


def _sha256_fd(fd: int) -> str:
    """Hex sha256 of the bytes readable from ``fd`` (position preserved)."""
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1 << 16)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _private_copy(source_path: str, pin: OmpBinaryPin, cache_home: str) -> str:
    """Verify the source no-follow/owner/mode/type/digest and stage a private copy."""
    if not os.path.isabs(source_path):
        raise LaunchError("binary resolver must return an absolute source path")
    try:
        fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise LaunchError(f"cannot open source no-follow: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LaunchError("source is not a regular file")
        if st.st_uid != os.getuid():
            raise LaunchError("source is not owned by the current user")
        if st.st_mode & 0o022:
            raise LaunchError("source is group/other-writable")
        if _sha256_fd(fd) != pin.executable_sha256:
            raise LaunchError("source digest does not match the pinned executable")
        os.lseek(fd, 0, os.SEEK_SET)
        private_dir = os.path.join(cache_home, "omp-i1", "private", pin.executable_sha256)
        os.makedirs(private_dir, mode=0o700, exist_ok=True)
        target = os.path.join(private_dir, os.path.basename(source_path))
        if os.path.exists(target):
            with open(target, "rb") as handle:
                if _sha256_fd(handle.fileno()) != pin.executable_sha256:
                    raise LaunchError("private copy digest mismatch")
        else:
            staging = target + ".tmp"
            with open(staging, "wb") as handle:
                shutil.copyfileobj(os.fdopen(os.dup(fd), "rb"), handle)
            os.chmod(staging, 0o500)
            os.replace(staging, target)
    finally:
        os.close(fd)
    with open(target, "rb") as handle:
        if _sha256_fd(handle.fileno()) != pin.executable_sha256:
            raise LaunchError("private copy failed re-verification")
    return target


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


def _relay(proc: subprocess.Popen[bytes], out, err) -> tuple[str | None, bool]:
    """Relay child stdout live; return (header session id, terminal seen)."""
    session_id: str | None = None
    terminal_seen = False
    header_parsed = False
    pending = b""

    def _drain_stderr() -> None:
        try:
            data = proc.stderr.read()
        except OSError:
            return
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


def _session_inventory(session_dir: str) -> list[str]:
    try:
        return sorted(os.listdir(session_dir))
    except OSError as exc:
        raise LaunchError(f"cannot scan session directory: {exc}") from exc


def run(*, argv: list[str], env: dict[str, str], stdin, out, err, pin: OmpBinaryPin, binary_resolver) -> int:
    """Launch the pinned OMP binary through the adapter; returns an exit code."""
    try:
        args = _parse_argv(argv)
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

        if profile:
            policy_args = dict(lane=policy, workspace=workspace, session_dir=session_dir,
                               conf_root=conf_root, env_roots=env_roots)
            empty_cwd = empty_omp_cwd(home=positive["HOME"], **policy_args)
            digest = canonical_policy_digest(home_omp=home_omp, empty_cwd=empty_cwd, **policy_args)
            protected, write, read = profile_root_sets(home_omp=home_omp, empty_cwd=empty_cwd, **policy_args)
            child_cwd = empty_cwd
            helper_prefix = _helper_prefix(digest=digest, protected=protected, write=write, read=read)
        else:
            digest = None
            child_cwd = workspace
            helper_prefix = None

        private = _private_copy(binary_resolver(), pin, positive["XDG_CACHE_HOME"])
        _run_version_probe(private, positive, child_cwd, pin, helper_prefix)

        conf_fd = None
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
                os.close(conf_fd)
                raise LaunchError(f"conf admission failed: {exc}") from exc
            conf_manifest = conf_snapshot.manifest_sha256

        child_argv = _child_argv(lane, policy, model, session_dir, workspace)
        if isinstance(stdin, bytes):
            stdin_bytes, stdin_arg = stdin, subprocess.PIPE
        elif hasattr(stdin, "fileno"):
            stdin_bytes, stdin_arg = None, stdin.fileno()
        else:
            stdin_bytes, stdin_arg = stdin.read(), subprocess.PIPE
        try:
            proc = subprocess.Popen(
                [*helper_prefix, "--", private, *child_argv] if helper_prefix is not None
                else [private, *child_argv],
                stdin=stdin_arg,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=child_cwd,
                env=positive,
                close_fds=True,
            )
        except OSError as exc:
            if conf_fd is not None:
                os.close(conf_fd)
            raise LaunchError(f"child failed to start: {exc}") from exc

        if stdin_bytes is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()

        session_id, terminal_seen = _relay(proc, out, err)
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
            visit_key = os.path.basename(session_dir.rstrip(os.sep)).removesuffix(".live")
            if session_id is None:
                raise LaunchError("fresh session requires a header session id")
            entries = _session_inventory(session_dir)
            observed = tuple(entries)
            for name in entries:
                if name.endswith(".jsonl") and name[: -len(".jsonl")].rsplit("_", 1)[-1] == session_id:
                    with open(os.path.join(session_dir, name), "rb") as handle:
                        primary_relpath, primary_sha256 = name, hashlib.sha256(handle.read()).hexdigest()
                    break
            else:
                raise LaunchError("no primary session journal matches the header session id")

        if profile:
            try:
                revalidate_conf_tree(conf_fd, conf_snapshot)
            except Exception as exc:
                raise LaunchError(f"conf tree changed during the run: {exc}") from exc
            finally:
                os.close(conf_fd)

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
                "env_names": sorted(_POSITIVE_ENV_NAMES),
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


def main(argv: list[str] | None = None) -> int:
    """Production entry: code-owned pin and resolver, never caller-supplied."""
    argv = list(sys.argv[1:] if argv is None else argv)
    return run(argv=argv, env=os.environ, stdin=sys.stdin.buffer, out=sys.stdout.buffer,
               err=sys.stderr, pin=OMP_BINARY_PIN, binary_resolver=lambda: PRODUCTION_BINARY_PATH)


if __name__ == "__main__":
    sys.exit(main())
